"""WebGPU scene renderer (wgpu-py).

Draws the scene's volumes as lit surfaces plus a ground grid. Targets wgpu-py >= 0.15; a few
API calls are wrapped defensively because wgpu-py's surface has drifted across releases and we
want the skeleton to survive minor version bumps.

What is real here: device/adapter acquisition, camera + per-object uniforms, an explicit
pipeline (surface.wgsl) with alpha blending + depth, per-volume mesh upload, and a line
pipeline for the grid. Translucent meshes sort triangles and scene objects sort by depth;
intersecting separate objects still need order-independent transparency. In-viewport MSAA and
GPU picking remain deferred. Colours/opacity come from the scene
model's ``volume_color`` (derived from the run's optics — a physics-backed look, not invented).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

import wgpu

from ..scene.model import SceneModel, VolumeNode
from . import mesh as meshgen
from .camera import Camera
from .metaballs import gaussian_surface_mesh, density_surface_mesh, DensityGrid
from .density import DensityDisplay, mass_level
from .playback import Playback, bond_segments, particle_instances, vector_segments
from .adaptive import RenderBudget
from .materials import material_meshes, colored_material_mesh, sorted_triangles

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_DEPTH_FORMAT = wgpu.TextureFormat.depth24plus


# --- small helpers ----------------------------------------------------------------------

def _request_device() -> "wgpu.GPUDevice":
    """Acquire a GPU device, tolerating the sync/async API naming across wgpu-py versions."""
    gpu = getattr(wgpu, "gpu", None)
    if gpu is not None and hasattr(gpu, "request_adapter_sync"):
        adapter = gpu.request_adapter_sync(power_preference="high-performance")
        return adapter.request_device_sync()
    # Older API shape.
    adapter = wgpu.request_adapter(power_preference="high-performance")  # type: ignore[attr-defined]
    return adapter.request_device()


def _mat_bytes(m: np.ndarray) -> np.ndarray:
    """Row-major numpy matrix -> column-major float32 for a WGSL ``mat4x4``."""
    return np.ascontiguousarray(m.T, dtype=np.float32)


def _rotation_matrix(deg: Tuple[float, float, float]) -> np.ndarray:
    rx, ry, rz = (np.radians(d) for d in deg)
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float32)
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float32)
    r = np.eye(4, dtype=np.float32)
    r[:3, :3] = mz @ my @ mx
    return r


def _model_matrix(vol: VolumeNode) -> np.ndarray:
    t = np.eye(4, dtype=np.float32)
    t[:3, 3] = np.asarray(vol.position_mm, dtype=np.float32)
    return (t @ _rotation_matrix(vol.rotation_deg)).astype(np.float32)


class _GpuVolume:
    """GPU resources for a single drawn volume."""

    __slots__ = ("vbo", "ibo", "index_count", "uniform", "bind_group", "sort_vertices",
                 "sort_indices", "sort_camera", "center", "alpha", "vertex_colors")

    def __init__(self, vbo, ibo, index_count, uniform, bind_group):
        self.vbo = vbo
        self.ibo = ibo
        self.index_count = index_count
        self.uniform = uniform
        self.bind_group = bind_group
        self.sort_vertices = self.sort_indices = self.sort_camera = None
        self.center = np.zeros(3)
        self.alpha = 1.0
        self.vertex_colors = False


class SceneRenderer:
    """Owns the wgpu device/pipelines and draws a ``SceneModel`` into a canvas context."""

    def __init__(self, canvas, background: str = "dark") -> None:
        self.canvas = canvas
        self.camera = Camera()
        self._detail = 1.0
        self._render_budget = None
        self._cache_frames = 8
        self._scene = None
        self._surface_spacing = None
        self._density_display = DensityDisplay()
        self._density_volume = None
        self._density_objects = []
        self._clear = (0.06, 0.07, 0.09, 1.0) if background == "dark" else (0.9, 0.91, 0.93, 1.0)

        self.device = _request_device()
        self.context = self._configure_context()
        self._render_format = self._preferred_format()

        self._bgl_camera = self._camera_bind_group_layout()
        self._bgl_model = self._model_bind_group_layout()
        self._camera_uniform = self.device.create_buffer(
            size=96,  # mat4(64) + light vec4(16) + eye vec4(16)
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        self._camera_bind_group = self.device.create_bind_group(
            layout=self._bgl_camera,
            entries=[{"binding": 0, "resource": {"buffer": self._camera_uniform, "offset": 0, "size": 96}}],
        )

        self._surface_pipeline = self._build_surface_pipeline()
        self._density_pipeline = self._build_surface_pipeline(depth_write=False, cull_mode="back")
        self._transparent_pipeline = self._build_surface_pipeline(depth_write=False)
        self._material_pipeline = self._build_surface_pipeline(depth_write=False, vertex_colors=True)
        self._line_pipeline = self._build_line_pipeline()
        # Playback overlays draw with the depth test off so they stay legible in front of the
        # (translucent) volumes. Both particle clouds and trajectory beams need the camera eye
        # (to face their billboards), a per-instance stream, and a small size uniform.
        self._bgl_size = self._model_bind_group_layout()  # reuse: one 16-byte uniform buffer
        # Particle clouds → camera-facing sprite billboards (particles.wgsl): a dense fluid reads
        # as a body rather than 1-px noise. Radius in a small uniform.
        self._particle_pipeline = self._build_particle_pipeline()
        self._sphere_pipeline = self._build_sphere_pipeline()
        sphere = meshgen.sphere(1.0)
        self._sphere_vbo = self._upload(sphere.vertices, wgpu.BufferUsage.VERTEX)
        self._sphere_ibo = self._upload(sphere.indices, wgpu.BufferUsage.INDEX)
        self._sphere_index_count = sphere.index_count
        _, self._bond_params_bg = self._grid_params(np.array([0.72, 0.75, 0.80, 1.0], dtype=np.float32))
        _, self._vector_params_bg = self._grid_params(np.array([0.25, 0.85, 1.0, 1.0], dtype=np.float32))
        self._particle_params, self._particle_params_bg = self._make_size_uniform()
        self._particle_radius_mm = 1.0
        # Trajectory segments → glowing camera-facing beam ribbons (trajectory.wgsl), additive so
        # overlapping photon paths brighten into a beam. Half-width in a small uniform.
        self._traj_pipeline = self._build_trajectory_pipeline()
        self._traj_params, self._traj_params_bg = self._make_size_uniform()
        self._traj_width_mm = 1.0

        self._volumes: List[_GpuVolume] = []
        self._grid = self._build_grid(200.0, 10.0)

        # Playback state (set via set_playback / driven by set_playback_time from the timeline).
        self._playback: Optional[Playback] = None
        self._traj_vbo = None
        self._traj_draw_segments = 0
        self._particle_vbo = None
        self._particle_count = 0
        self._particle_frame_idx = -1
        self._particle_frame_cache = OrderedDict()
        self._bond_frame_cache = OrderedDict()
        self._bond_vbo = None
        self._bond_count = 0
        self._vector_frame_cache = OrderedDict()
        self._vector_vbo = None
        self._vector_count = 0
        self._particle_has_radii = False
        self._particle_surface: Optional[_GpuVolume] = None
        self._particle_surface_cache: OrderedDict = OrderedDict()
        self._grouped_material = None
        self._material_descriptions = []

        self._depth_view = None
        self._depth_size: Tuple[int, int] = (0, 0)
        self._fit_diag = 100.0  # diagonal of the last framed bounds (sets the beam width)
        self._scene_bounds = None

    # --- setup --------------------------------------------------------------------------

    def _configure_context(self):
        try:
            context = self.canvas.get_context("wgpu")
        except TypeError:
            context = self.canvas.get_context()
        return context

    def _preferred_format(self):
        try:
            fmt = self.context.get_preferred_format(self.device.adapter)
        except Exception:
            fmt = wgpu.TextureFormat.bgra8unorm
        self.context.configure(device=self.device, format=fmt, alpha_mode="opaque")
        return fmt

    def _load_shader(self, name: str):
        code = (_SHADER_DIR / name).read_text(encoding="utf-8")
        return self.device.create_shader_module(code=code)

    def _camera_bind_group_layout(self):
        return self.device.create_bind_group_layout(
            entries=[{
                "binding": 0,
                "visibility": wgpu.ShaderStage.VERTEX | wgpu.ShaderStage.FRAGMENT,
                "buffer": {"type": wgpu.BufferBindingType.uniform},
            }]
        )

    def _model_bind_group_layout(self):
        return self.device.create_bind_group_layout(
            entries=[{
                "binding": 0,
                "visibility": wgpu.ShaderStage.VERTEX | wgpu.ShaderStage.FRAGMENT,
                "buffer": {"type": wgpu.BufferBindingType.uniform},
            }]
        )

    def _alpha_blend(self):
        return {
            "color": {
                "src_factor": wgpu.BlendFactor.src_alpha,
                "dst_factor": wgpu.BlendFactor.one_minus_src_alpha,
                "operation": wgpu.BlendOperation.add,
            },
            "alpha": {
                "src_factor": wgpu.BlendFactor.one,
                "dst_factor": wgpu.BlendFactor.one_minus_src_alpha,
                "operation": wgpu.BlendOperation.add,
            },
        }

    def _additive_blend(self):
        """Additive glow: overlapping beam segments accumulate into a bright beam (light adds)."""
        return {
            "color": {
                "src_factor": wgpu.BlendFactor.src_alpha,
                "dst_factor": wgpu.BlendFactor.one,
                "operation": wgpu.BlendOperation.add,
            },
            "alpha": {
                "src_factor": wgpu.BlendFactor.one,
                "dst_factor": wgpu.BlendFactor.one,
                "operation": wgpu.BlendOperation.add,
            },
        }

    def _build_surface_pipeline(self, depth_write=True, cull_mode="none", vertex_colors=False):
        shader = self._load_shader("surface.wgsl")
        layout = self.device.create_pipeline_layout(
            bind_group_layouts=[self._bgl_camera, self._bgl_model]
        )
        return self.device.create_render_pipeline(
            layout=layout,
            vertex={
                "module": shader,
                "entry_point": "vs_colored" if vertex_colors else "vs_main",
                "buffers": [{
                    "array_stride": (10 if vertex_colors else 6) * 4,
                    "step_mode": wgpu.VertexStepMode.vertex,
                    "attributes": [
                        {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 0},
                        {"format": wgpu.VertexFormat.float32x3, "offset": 3 * 4, "shader_location": 1},
                    ] + ([{"format": wgpu.VertexFormat.float32x4, "offset": 6 * 4,
                            "shader_location": 2}] if vertex_colors else []),
                }],
            },
            primitive={
                "topology": wgpu.PrimitiveTopology.triangle_list,
                "cull_mode": cull_mode,
            },
            depth_stencil={
                "format": _DEPTH_FORMAT,
                "depth_write_enabled": depth_write,
                "depth_compare": wgpu.CompareFunction.less,
            },
            fragment={
                "module": shader,
                "entry_point": "fs_main",
                "targets": [{"format": self._render_format, "blend": self._alpha_blend()}],
            },
        )

    def _build_line_pipeline(self):
        shader = self._load_shader("lines.wgsl")
        layout = self.device.create_pipeline_layout(
            bind_group_layouts=[self._bgl_camera, self._bgl_model]
        )
        return self.device.create_render_pipeline(
            layout=layout,
            vertex={
                "module": shader,
                "entry_point": "vs_main",
                "buffers": [{
                    "array_stride": 3 * 4,
                    "step_mode": wgpu.VertexStepMode.vertex,
                    "attributes": [
                        {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 0},
                    ],
                }],
            },
            primitive={"topology": wgpu.PrimitiveTopology.line_list},
            depth_stencil={
                "format": _DEPTH_FORMAT,
                "depth_write_enabled": False,
                "depth_compare": wgpu.CompareFunction.less,
            },
            fragment={
                "module": shader,
                "entry_point": "fs_main",
                "targets": [{"format": self._render_format, "blend": self._alpha_blend()}],
            },
        )

    def _make_size_uniform(self):
        """A tiny (16-byte) uniform buffer + bind group holding a single vec4 size parameter."""
        buf = self.device.create_buffer(
            size=16, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        bind_group = self.device.create_bind_group(
            layout=self._bgl_size,
            entries=[{"binding": 0, "resource": {"buffer": buf, "offset": 0, "size": 16}}],
        )
        return buf, bind_group

    def _build_particle_pipeline(self):
        """Instanced billboard pipeline: one quad (6 verts) per particle, (center, RGBA) as
        per-instance attributes. Depth test off so the cloud overlays translucent volumes; the
        sprites alpha-blend so overlapping droplets accumulate into a dense body."""
        shader = self._load_shader("particles.wgsl")
        layout = self.device.create_pipeline_layout(
            bind_group_layouts=[self._bgl_camera, self._bgl_size]
        )
        return self.device.create_render_pipeline(
            layout=layout,
            vertex={
                "module": shader,
                "entry_point": "vs_main",
                "buffers": [{
                    "array_stride": 8 * 4,
                    "step_mode": wgpu.VertexStepMode.instance,
                    "attributes": [
                        {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 0},
                        {"format": wgpu.VertexFormat.float32x4, "offset": 3 * 4, "shader_location": 1},
                    ],
                }],
            },
            primitive={"topology": wgpu.PrimitiveTopology.triangle_list},
            depth_stencil={
                "format": _DEPTH_FORMAT,
                "depth_write_enabled": False,
                "depth_compare": wgpu.CompareFunction.always,
            },
            fragment={
                "module": shader,
                "entry_point": "fs_main",
                "targets": [{"format": self._render_format, "blend": self._alpha_blend()}],
            },
        )

    def _build_sphere_pipeline(self):
        """Instanced unit mesh: emitted radii keep atoms/parcels at true relative size."""
        shader = self._load_shader("spheres.wgsl")
        layout = self.device.create_pipeline_layout(bind_group_layouts=[self._bgl_camera])
        return self.device.create_render_pipeline(
            layout=layout,
            vertex={"module": shader, "entry_point": "vs_main", "buffers": [
                {"array_stride": 6 * 4, "step_mode": wgpu.VertexStepMode.vertex,
                 "attributes": [
                     {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 0},
                     {"format": wgpu.VertexFormat.float32x3, "offset": 3 * 4, "shader_location": 1}]},
                {"array_stride": 8 * 4, "step_mode": wgpu.VertexStepMode.instance,
                 "attributes": [
                     {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 2},
                     {"format": wgpu.VertexFormat.float32x4, "offset": 3 * 4, "shader_location": 3},
                     {"format": wgpu.VertexFormat.float32, "offset": 7 * 4, "shader_location": 4}]}]},
            primitive={"topology": wgpu.PrimitiveTopology.triangle_list},
            depth_stencil={"format": _DEPTH_FORMAT, "depth_write_enabled": True,
                           "depth_compare": wgpu.CompareFunction.less},
            fragment={"module": shader, "entry_point": "fs_main",
                      "targets": [{"format": self._render_format, "blend": self._alpha_blend()}]},
        )

    def _build_trajectory_pipeline(self):
        """Instanced beam-ribbon pipeline: one quad (6 verts) per trajectory segment, reading the
        existing 2-row/segment buffer as per-instance data (row0 = p0+colour+style, row1 = p1).
        Additive glow, depth test off, so photon paths read as a bright beam."""
        shader = self._load_shader("trajectory.wgsl")
        layout = self.device.create_pipeline_layout(
            bind_group_layouts=[self._bgl_camera, self._bgl_size]
        )
        return self.device.create_render_pipeline(
            layout=layout,
            vertex={
                "module": shader,
                "entry_point": "vs_main",
                "buffers": [{
                    "array_stride": 16 * 4,   # two [x,y,z,r,g,b,width,alpha] rows
                    "step_mode": wgpu.VertexStepMode.instance,
                    "attributes": [
                        {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 0},        # p0
                        {"format": wgpu.VertexFormat.float32x3, "offset": 3 * 4, "shader_location": 1},    # colour
                        {"format": wgpu.VertexFormat.float32x2, "offset": 6 * 4, "shader_location": 2},    # width, alpha
                        {"format": wgpu.VertexFormat.float32x3, "offset": 8 * 4, "shader_location": 3},    # p1
                    ],
                }],
            },
            primitive={"topology": wgpu.PrimitiveTopology.triangle_list},
            depth_stencil={
                "format": _DEPTH_FORMAT,
                "depth_write_enabled": False,
                "depth_compare": wgpu.CompareFunction.always,
            },
            fragment={
                "module": shader,
                "entry_point": "fs_main",
                "targets": [{"format": self._render_format, "blend": self._additive_blend()}],
            },
        )

    def _upload(self, data: np.ndarray, usage) -> "wgpu.GPUBuffer":
        data = np.ascontiguousarray(data)
        if hasattr(self.device, "create_buffer_with_data"):
            return self.device.create_buffer_with_data(data=data, usage=usage)
        buf = self.device.create_buffer(size=data.nbytes, usage=usage | wgpu.BufferUsage.COPY_DST)
        self.device.queue.write_buffer(buf, 0, data)
        return buf

    def _make_object_uniform(self, model: np.ndarray, color: Tuple[float, float, float, float],
                             params: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)):
        normal_mat = np.eye(4, dtype=np.float32)
        normal_mat[:3, :3] = np.linalg.inv(model[:3, :3]).T
        payload = np.concatenate([
            _mat_bytes(model).ravel(),
            _mat_bytes(normal_mat).ravel(),
            np.asarray(color, dtype=np.float32),
            np.asarray(params, dtype=np.float32),   # (reflectance R0, gloss, emissive, _)
        ]).astype(np.float32)
        buf = self.device.create_buffer(
            size=payload.nbytes,
            usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST,
        )
        self.device.queue.write_buffer(buf, 0, payload)
        bind_group = self.device.create_bind_group(
            layout=self._bgl_model,
            entries=[{"binding": 0, "resource": {"buffer": buf, "offset": 0, "size": payload.nbytes}}],
        )
        return buf, bind_group

    def _build_grid(self, half_extent: float, spacing: float, y: float = 0.0):
        pts = meshgen.grid_lines(half_extent, spacing, y=y)
        vbo = self._upload(pts, wgpu.BufferUsage.VERTEX)
        # Subtle so the grid reads as a ground reference, not a busy plane that dominates the
        # frame (and dithers into noise in the compact reference GIFs).
        color = np.array([0.26, 0.28, 0.32, 0.28], dtype=np.float32)
        buf, bind_group = self._grid_params(color)
        return {"vbo": vbo, "count": pts.shape[0], "uniform": buf, "bind_group": bind_group}

    def _grid_params(self, color: np.ndarray):
        buf = self.device.create_buffer(
            size=color.nbytes, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST
        )
        self.device.queue.write_buffer(buf, 0, color)
        bind_group = self.device.create_bind_group(
            layout=self._bgl_model,
            entries=[{"binding": 0, "resource": {"buffer": buf, "offset": 0, "size": color.nbytes}}],
        )
        return buf, bind_group

    # --- public API ---------------------------------------------------------------------

    def set_render_budget(self, budget: RenderBudget) -> None:
        """Rebuild representation resources only; retain the camera and engine clock."""
        detail = max(0.125, min(8.0, budget.detail))
        if budget.adaptive:
            size = self.canvas.get_physical_size()
            detail = min(detail, max(0.125, (max(1, size[0] * size[1]) / 70400) ** 0.5))
            if self._playback is not None and self._playback.kind == "particles":
                count = max((len(f.positions) for f in self._playback.frames), default=1)
                triangle_budget = max(16, budget.memory_mib) * 2**20 / 64
                detail = min(detail, max(0.125, (triangle_budget / (384 * max(1, count))) ** 0.5))
        changed = (abs(detail - self._detail) > 1e-6 or
                   self._render_budget is None or
                   budget.memory_mib != self._render_budget.memory_mib or
                   budget.merge_radius_scale != self._render_budget.merge_radius_scale)
        self._render_budget = replace(budget)
        if not changed:
            return
        self._detail = detail
        sphere = meshgen.sphere(1.0, rings=max(3, round(12 * detail)),
                                sectors=max(6, round(16 * detail)))
        self._sphere_vbo.destroy()
        self._sphere_ibo.destroy()
        self._sphere_vbo = self._upload(sphere.vertices, wgpu.BufferUsage.VERTEX)
        self._sphere_ibo = self._upload(sphere.indices, wgpu.BufferUsage.INDEX)
        self._sphere_index_count = sphere.index_count
        if self._scene is not None:
            self._upload_scene(self._scene)
        self._particle_surface_cache.clear()
        idx = self._particle_frame_idx
        self._particle_frame_idx = -1
        if idx >= 0:
            self._set_particle_frame(idx)

    def set_scene(self, scene: SceneModel) -> None:
        """(Re)build GPU resources for a scene and frame the camera on its bounds."""
        self._scene = scene
        self._upload_scene(scene)
        self._scene_bounds = scene.bounds_mm()
        self.fit_view(*self._scene_bounds)

    def _upload_scene(self, scene: SceneModel) -> None:
        self._volumes = []
        for vol in scene.volumes:
            if vol.is_hidden:                       # authored viz_hidden render hint
                continue
            data = meshgen.for_shape(vol.shape, self._detail)
            vbo = self._upload(data.vertices, wgpu.BufferUsage.VERTEX)
            ibo = self._upload(data.indices, wgpu.BufferUsage.INDEX | wgpu.BufferUsage.COPY_DST)
            model = _model_matrix(vol)
            color, params = scene.volume_surface(vol)
            uniform, bind_group = self._make_object_uniform(model, color, params)
            obj = _GpuVolume(vbo, ibo, data.index_count, uniform, bind_group)
            world = data.vertices.copy()
            world[:, :3] = data.vertices[:, :3] @ model[:3, :3].T + model[:3, 3]
            self._enable_alpha_sort(obj, world, data.indices, color[3])
            self._volumes.append(obj)

        # Grid + camera: a ground plane sunk to the bottom of the subject and sized to its
        # footprint, not the whole world (which left the geometry tiny in a sea of lines).

    def fit_view(self, lo, hi) -> None:
        """Frame the camera on ``lo..hi`` and rebuild the ground grid to sit under it.

        Public so the headless capture path can re-fit to a particle cloud's own extent (the
        scene box may be absent or oversized for a fluid run) and keep the grid consistent.
        """
        lo = np.asarray(lo, dtype=np.float32)
        hi = np.asarray(hi, dtype=np.float32)
        self._fit_diag = float(np.linalg.norm(hi - lo)) or 100.0
        footprint = float(max(hi[0] - lo[0], hi[2] - lo[2]))
        half = max(footprint * 0.75, 10.0)
        spacing = max(half / 12.0, 1.0)
        self._grid = self._build_grid(half, spacing, y=float(lo[1]))
        self.camera.fit_bounds(lo, hi)

    def set_playback(self, playback: Optional[Playback]) -> None:
        """(Re)upload playback GPU resources. Cursor defaults to the end (full result shown)."""
        self._playback = playback
        self.camera.projection = 'perspective'
        self._traj_vbo = None
        self._traj_draw_segments = 0
        self._particle_vbo = None
        self._particle_count = 0
        self._particle_frame_idx = -1
        self._particle_frame_cache = OrderedDict()
        self._bond_frame_cache = OrderedDict()
        self._bond_vbo = None
        self._bond_count = 0
        self._vector_frame_cache = OrderedDict()
        self._vector_vbo = None
        self._vector_count = 0
        self._particle_has_radii = False
        self._particle_surface = None
        self._grouped_material = None
        self._material_descriptions = []
        self._particle_surface_cache = OrderedDict()
        self._interface_object = None
        if playback is None or playback.is_empty:
            return
        if self._render_budget is not None:
            self.set_render_budget(self._render_budget)
        if playback.kind == "trajectory" and playback.segment_vertices is not None:
            self._traj_vbo = self._upload(playback.segment_vertices, wgpu.BufferUsage.VERTEX)
            self._traj_draw_segments = playback.segment_count  # show all until a time is set
            # Beam half-width from the *framed scene* size (the container), not the trajectory
            # extent — stray photons that shoot far past the geometry must not fatten the beam.
            self._traj_width_mm = max(self._fit_diag * 0.006, 0.3)
            self.device.queue.write_buffer(
                self._traj_params, 0,
                np.array([self._traj_width_mm, 0.0, 0.0, 0.0], dtype=np.float32),
            )
        elif playback.kind == "particles" and playback.frames:
            self._particle_radius_mm = self._estimate_particle_radius(playback)
            self.device.queue.write_buffer(
                self._particle_params, 0,
                np.array([self._particle_radius_mm, 0.0, 0.0, 0.0], dtype=np.float32),
            )
            # Frame the camera + ground on the cloud's own extent — the scene box (if any) may be
            # absent or oversized for a fluid run, and the particles carry the real geometry.
            bounds = playback.particle_bounds()
            if bounds is not None:
                # Keep the emitted cloud and its real scene apparatus in frame together. Earlier
                # particle playback replaced the scene bounds entirely, which could crop a lamp
                # cap/base or beaker rim even though those volumes came from the same run.
                if playback.length_unit == "mm" and playback.show_geant4_scene and self._scene_bounds is not None:
                    bounds = (
                        np.minimum(np.asarray(bounds[0]), np.asarray(self._scene_bounds[0])),
                        np.maximum(np.asarray(bounds[1]), np.asarray(self._scene_bounds[1])),
                    )
                self.fit_view(*bounds)
            self._set_particle_frame(len(playback.frames) - 1)
            camera = playback.frames[0].camera
            if camera is not None:
                self.camera.yaw, self.camera.pitch = np.radians(camera)
                self.camera.projection = playback.frames[0].camera_projection

    @staticmethod
    def _estimate_particle_radius(playback: Playback) -> float:
        """A world-space sprite radius from the cloud's own spacing (a rendering choice).

        Uses the in-plane spacing ``sqrt(area / N)`` of the fullest frame — the two largest bbox
        axes — so neighbouring sprites just overlap into a continuous body whatever the
        scenario's scale, and a thin sheet is handled like a 3-D blob. No particle is moved; this
        only sets how big each droplet is drawn.
        """
        frame = max(playback.frames, key=lambda f: f.positions.shape[0])
        pos = frame.positions
        n = int(pos.shape[0])
        if n < 2:
            return 2.0
        span = np.sort(pos.max(axis=0) - pos.min(axis=0))[::-1]  # descending
        area = float(max(span[0], 1e-3) * max(span[1], 1e-3))
        spacing = (area / n) ** 0.5
        return float(max(spacing * 0.85, 0.5))

    def set_density_display(self, display):
        self._density_display = display
        idx = self._particle_frame_idx
        self._particle_frame_idx = -1
        if idx >= 0:
            self._set_particle_frame(idx)

    def set_playback_time(self, t: float) -> None:
        """Move the playback cursor to time ``t`` (engine-native units: ns or s)."""
        pb = self._playback
        if pb is None or pb.is_empty:
            return
        if pb.kind == "trajectory":
            self._traj_draw_segments = pb.count_at(t)
        elif pb.kind == "particles":
            self._set_particle_frame(pb.frame_index_at(t))

    def _set_particle_frame(self, idx: int) -> None:
        pb = self._playback
        if pb is None or not pb.frames:
            return
        idx = max(0, min(idx, len(pb.frames) - 1))
        if idx == self._particle_frame_idx and (
            self._particle_vbo is not None or self._particle_surface is not None or self._grouped_material is not None
        ):
            return
        self._particle_frame_idx = idx
        self._particle_surface = None
        self._grouped_material = None
        self._material_descriptions = []
        self._density_objects = []
        frame = pb.frames[idx]
        self._interface_object = None
        if frame.interface is not None:
            key = ('interface',idx)
            obj = self._particle_surface_cache.pop(key,None)
            if obj is None:
                mesh = frame.interface
                uniform, group = self._make_object_uniform(np.eye(4,dtype=np.float32),(.85,.9,1,1),(0,0,0,1))
                obj = _GpuVolume(self._upload(mesh.vertices,wgpu.BufferUsage.VERTEX),
                    self._upload(mesh.indices,wgpu.BufferUsage.INDEX),mesh.index_count,uniform,group)
            self._particle_surface_cache[key] = obj
            while len(self._particle_surface_cache)>self._cache_frames: self._particle_surface_cache.popitem(last=False)
            self._interface_object = obj
        if frame.display is not None:
            self._density_display = frame.display
        if self._render_budget is not None:
            estimate = frame.positions.nbytes * 8 + (len(frame.bonds) * 24 if frame.bonds is not None else 0)
            self._cache_frames = self._render_budget.cache_frames(estimate)
        self._particle_has_radii = frame.radii is not None
        bonds = self._bond_frame_cache.pop(idx, None)
        if bonds is None:
            segments = bond_segments(frame)
            if frame.guides is not None:
                segments = np.concatenate((segments, frame.guides))
            bonds = ((self._upload(segments, wgpu.BufferUsage.VERTEX), len(segments))
                     if len(segments) else (None, 0))
        self._bond_frame_cache[idx] = bonds
        while len(self._bond_frame_cache) > self._cache_frames:
            self._bond_frame_cache.popitem(last=False)
        self._bond_vbo, self._bond_count = bonds
        vectors = self._vector_frame_cache.pop(idx, None)
        if vectors is None:
            segments = vector_segments(frame)
            vectors = ((self._upload(segments, wgpu.BufferUsage.VERTEX), len(segments))
                       if len(segments) else (None, 0))
        self._vector_frame_cache[idx] = vectors
        while len(self._vector_frame_cache) > self._cache_frames:
            self._vector_frame_cache.popitem(last=False)
        self._vector_vbo, self._vector_count = vectors
        if frame.density is not None:
            density = frame.density
            display = self._density_display
            if display.mode in ('volume', 'slice', 'levels'):
                if self._density_volume is None:
                    from .density_gpu import DensityVolume
                    self._density_volume = DensityVolume(self)
                self._density_volume.prepare(density, display)
            else:
                level = mass_level(density, display.mass_percent)
                threshold = level['threshold'] if level else density.isovalue
                cache_key = ('density',idx,display.mode,threshold,display.opacity)
                objects = self._particle_surface_cache.pop(cache_key,None)
                if objects is None:
                    layers = []
                    if display.mode == 'contours':
                        for percent, alpha in ((90,.12),(50,.24),(10,.55)):
                            contour = mass_level(density,percent)
                            if contour:
                                if density.quantity == 'density_difference':
                                    layers.extend([(density.values,contour['threshold'],(1.,.43,.16,alpha)),
                                                   (-density.values,contour['threshold'],(.18,.66,1.,alpha))])
                                else:
                                    layers.append((density.values,contour['threshold'],(.18,.68,1.,alpha)))
                    elif display.mode == 'phase' and density.amplitude is not None:
                        layers = [(density.amplitude,np.sqrt(threshold),(1.,.43,.16,display.opacity)),
                                  (-density.amplitude,np.sqrt(threshold),(.18,.66,1.,display.opacity))]
                    elif density.quantity == 'density_difference':
                        layers = [(density.values,threshold,(1.,.43,.16,.55)),(-density.values,threshold,(.18,.66,1.,.55))]
                    else:
                        layers = [(density.values,threshold,density.rgba)]
                    objects = []
                    for values, iso, color in layers:
                        if iso <= 0 and density.quantity != 'scalar': continue
                        if density.quantity == 'scalar':
                            color = (*density.rgba[:3], display.opacity)
                        mesh = density_surface_mesh(DensityGrid(values,density.origin,density.spacing),iso,
                            density.active_mask if density.quantity == 'scalar' else None)
                        if mesh.index_count:
                            uniform, group = self._make_object_uniform(np.eye(4,dtype=np.float32),color,(0,0,0,1))
                            objects.append(_GpuVolume(self._upload(mesh.vertices,wgpu.BufferUsage.VERTEX),
                                self._upload(mesh.indices,wgpu.BufferUsage.INDEX),mesh.index_count,uniform,group))
                self._particle_surface_cache[cache_key] = objects
                while len(self._particle_surface_cache)>self._cache_frames:
                    self._particle_surface_cache.popitem(last=False)
                self._density_objects = objects
        if frame.density is not None:
            overlay = (frame.density.overlays or {}).get(self._density_display.overlay_id)
            if overlay:
                level_list = (overlay['statistics'] or {}).get('mass_levels', [])
                threshold = level_list[self._density_display.mass_percent-1]['threshold'] if level_list else .02
                cache_key = ('overlay',idx,self._density_display.overlay_id,threshold)
                objects = self._particle_surface_cache.pop(cache_key,None)
                if objects is None:
                    objects=[]
                    for sign,color in ((1,(1.,.43,.16,.5)),(-1,(.18,.66,1.,.5))):
                        mesh=density_surface_mesh(DensityGrid(sign*overlay['amplitude'],overlay['origin'],overlay['spacing']),np.sqrt(threshold))
                        if mesh.index_count:
                            uniform, group=self._make_object_uniform(np.eye(4,dtype=np.float32),color,(0,0,0,1))
                            objects.append(_GpuVolume(self._upload(mesh.vertices,wgpu.BufferUsage.VERTEX),
                                self._upload(mesh.indices,wgpu.BufferUsage.INDEX),mesh.index_count,uniform,group))
                self._particle_surface_cache[cache_key]=objects
                while len(self._particle_surface_cache)>self._cache_frames: self._particle_surface_cache.popitem(last=False)
                self._density_objects = self._density_objects + objects
        keep = np.ones(len(frame.positions), dtype=bool)
        if frame.material_grid is not None or frame.material_groups:
            key = ('materials', idx)
            cached_material = self._particle_surface_cache.pop(key, None)
            if cached_material is None:
                max_cells = (max(8, self._render_budget.memory_mib * 2**20 // 512)
                             if self._render_budget is not None else 500000)
                merge_scale = self._render_budget.merge_radius_scale if self._render_budget else 1.0
                layers, descriptions, keep = material_meshes(frame, self._detail, max_cells, merge_scale)
                vertices, indices = colored_material_mesh(layers)
                obj = None
                if len(indices):
                    uniform, group = self._make_object_uniform(np.eye(4, dtype=np.float32),
                                                               (1, 1, 1, 1), (0, 0, 0, 1))
                    obj = _GpuVolume(self._upload(vertices, wgpu.BufferUsage.VERTEX),
                        self._upload(indices, wgpu.BufferUsage.INDEX | wgpu.BufferUsage.COPY_DST),
                        len(indices), uniform, group)
                    self._enable_alpha_sort(obj, vertices, indices, .5)
                    obj.vertex_colors = True
                    if self._render_budget is not None:
                        self._cache_frames = min(self._cache_frames, self._render_budget.cache_frames(
                            vertices.nbytes + indices.nbytes))
                cached_material = (obj, descriptions, keep)
            self._particle_surface_cache[key] = cached_material
            while len(self._particle_surface_cache) > self._cache_frames:
                self._particle_surface_cache.popitem(last=False)
            self._grouped_material, self._material_descriptions, keep = cached_material
            if not np.any(keep):
                self._particle_vbo, self._particle_count = None, 0
                return
        if frame.surface is not None and frame.surface.positions_unmodified:
            surface = frame.surface
            merge_scale = self._render_budget.merge_radius_scale if self._render_budget else 1.0
            surface = replace(surface, sigma_mm=surface.sigma_mm * merge_scale,
                              neck_mode=surface.neck_mode if merge_scale == 1 else 'none')
            if self._render_budget is not None:
                # Bound the grid estimate (including extraction temporaries),
                # while preserving every centre, kernel width and iso level.
                span = np.ptp(frame.positions, axis=0) + 6.5 * surface.sigma_mm if len(frame.positions) else np.ones(3)
                spacing = max(0.05, surface.grid_spacing_mm / self._detail)
                max_cells = max(8, self._render_budget.memory_mib * 2**20 // 512)
                for _ in range(16):
                    cells = float(np.prod(np.ceil(span / spacing) + 3))
                    if cells <= max_cells:
                        break
                    spacing *= max(1.05, (cells / max_cells) ** (1 / 3))
                surface = replace(surface, grid_spacing_mm=spacing)
            self._surface_spacing = surface.grid_spacing_mm
            surface_gpu = self._particle_surface_cache.pop(idx, None)
            if surface_gpu is None:
                mesh = gaussian_surface_mesh(frame.positions, surface)
                if self._render_budget is not None:
                    self._cache_frames = min(self._cache_frames, self._render_budget.cache_frames(mesh.vertices.nbytes + mesh.indices.nbytes))
                if mesh.index_count > 0:
                    vbo = self._upload(mesh.vertices, wgpu.BufferUsage.VERTEX)
                    ibo = self._upload(mesh.indices, wgpu.BufferUsage.INDEX | wgpu.BufferUsage.COPY_DST)
                    if frame.colors is not None and frame.colors.shape[0] > 0:
                        rgb = np.mean(frame.colors[:, :3], axis=0)
                    else:
                        rgb = np.asarray(frame.color[:3], dtype=np.float32)
                    color = (float(rgb[0]), float(rgb[1]), float(rgb[2]),
                             float(frame.surface.opacity))
                    params = (float(frame.surface.fresnel_r0), float(frame.surface.gloss), 0.0, 0.0)
                    uniform, bind_group = self._make_object_uniform(
                        np.eye(4, dtype=np.float32), color, params
                    )
                    surface_gpu = _GpuVolume(
                        vbo, ibo, mesh.index_count, uniform, bind_group
                    )
                    self._enable_alpha_sort(surface_gpu, mesh.vertices, mesh.indices, color[3])
                else:
                    surface_gpu = False
            self._particle_surface_cache[idx] = surface_gpu
            self._particle_surface_cache.move_to_end(idx)
            while len(self._particle_surface_cache) > self._cache_frames:
                self._particle_surface_cache.popitem(last=False)
            if surface_gpu is not False:
                self._particle_surface = surface_gpu
                self._particle_vbo = None
                self._particle_count = 0
                return
        cached = self._particle_frame_cache.get(idx)
        if cached is None:
            pos = np.ascontiguousarray(frame.positions, dtype=np.float32)
            if pos.shape[0] == 0:
                self._particle_vbo = None
                self._particle_count = 0
                self._particle_frame_cache[idx] = (None, 0)
                while len(self._particle_frame_cache) > self._cache_frames:
                    self._particle_frame_cache.popitem(last=False)
                return
            verts = particle_instances(frame, self._particle_radius_mm)[keep]
            cached = (self._upload(verts, wgpu.BufferUsage.VERTEX), len(verts))
            self._particle_frame_cache[idx] = cached
        self._particle_frame_cache.move_to_end(idx)
        while len(self._particle_frame_cache) > self._cache_frames:
            self._particle_frame_cache.popitem(last=False)
        self._particle_vbo, self._particle_count = cached

    @staticmethod
    def _enable_alpha_sort(obj, vertices, indices, alpha):
        obj.center = (vertices[:, :3].min(axis=0) + vertices[:, :3].max(axis=0)) * .5
        obj.alpha = float(alpha)
        if alpha < 1:
            obj.sort_vertices = vertices
            obj.sort_indices = indices

    def _draw_surface(self, render_pass, obj):
        if obj.sort_indices is not None:
            camera = tuple(self.camera.eye()) + tuple(self.camera.target)
            if camera != obj.sort_camera:
                order = sorted_triangles(obj.sort_vertices, obj.sort_indices,
                                         self.camera.eye(), self.camera.target)
                self.device.queue.write_buffer(obj.ibo, 0, order)
                obj.sort_camera = camera
        render_pass.set_pipeline(self._material_pipeline if obj.vertex_colors else
                                 self._transparent_pipeline if obj.alpha < 1 else self._surface_pipeline)
        render_pass.set_bind_group(0, self._camera_bind_group)
        render_pass.set_bind_group(1, obj.bind_group)
        render_pass.set_vertex_buffer(0, obj.vbo)
        render_pass.set_index_buffer(obj.ibo, wgpu.IndexFormat.uint32)
        render_pass.draw_indexed(obj.index_count, 1, 0, 0, 0)

    def precision_info(self) -> dict:
        """Representation precision/choices for UI and capture provenance."""
        info = {
            "engine_vertices_interpolated": False,
            "depth_tested_overlays": False,
            "fit_diagonal_mm": self._fit_diag,
            "sphere_sectors": max(6, round(16 * self._detail)),
            "render_detail_factor": self._detail,
            "merge_radius_scale": self._render_budget.merge_radius_scale if self._render_budget else 1.0,
            "authored_merge_parameters_preserved": not self._render_budget or self._render_budget.merge_radius_scale == 1,
            "gpu_cache_frame_limit": self._cache_frames,
        }
        if self._render_budget is not None:
            info.update(self._render_budget.to_dict())
            info["requested_render_detail_factor"] = self._render_budget.detail
            info["render_detail_factor"] = self._detail
        if self._playback is not None and self._playback.kind == "trajectory":
            info.update({
                "trajectory_ribbon_half_width_mm": self._traj_width_mm,
                "trajectory_strength": self._playback.display_strength,
                "trajectory_width_scale": self._playback.ribbon_width_scale,
                "trajectory_opacity": self._playback.ribbon_opacity,
            })
        elif self._playback is not None and self._playback.kind == "particles":
            frame = self._playback.frames[self._particle_frame_idx] if (
                self._playback.frames and self._particle_frame_idx >= 0
            ) else None
            if frame is not None and (frame.material_grid is not None or frame.material_groups):
                info.update(particle_representation='grouped_material_surfaces',
                    material_groups=self._material_descriptions,
                    material_triangles=self._grouped_material.index_count // 3 if self._grouped_material else 0,
                    material_positions_unmodified=True, material_transparency='display RGBA; sorted triangles; depth writes off',
                    material_points_drawn=self._particle_count)
            elif frame is not None and frame.surface is not None and self._particle_surface is not None:
                info.update({
                    "particle_representation": "gaussian_density_surface",
                    "surface_grid_spacing_mm": self._surface_spacing or frame.surface.grid_spacing_mm,
                    "surface_sigma_mm": frame.surface.sigma_mm,
                    "effective_surface_sigma_mm": frame.surface.sigma_mm * (self._render_budget.merge_radius_scale if self._render_budget else 1),
                    "surface_iso_level": frame.surface.iso_level,
                    "surface_positions_unmodified": frame.surface.positions_unmodified,
                    "surface_neck_mode": frame.surface.neck_mode,
                    "surface_neck_min_distance_mm": frame.surface.neck_min_distance_mm,
                    "surface_neck_max_distance_mm": frame.surface.neck_max_distance_mm,
                    "surface_neck_samples_per_pair": frame.surface.neck_samples,
                    "surface_neck_weight": frame.surface.neck_weight,
                    "surface_neck_preserves_component_topology": (
                        frame.surface.neck_preserves_topology
                    ),
                    "depth_tested_particle_surface": True,
                })
            else:
                info["particle_representation"] = ("emitted_radius_spheres" if self._particle_has_radii
                                                   else "camera_facing_sprites")
                if not self._particle_has_radii:
                    radius_key = ("particle_sprite_radius_mm" if self._playback.length_unit == "mm"
                                  else "particle_sprite_radius_native")
                    info[radius_key] = self._particle_radius_mm
            info["particle_length_unit"] = self._playback.length_unit
            info['gaussian_merge_available'] = bool(frame is not None and (frame.surface is not None or frame.material_groups))
            info['recorded_particle_count'] = len(frame.positions) if frame is not None else 0
            if not info['gaussian_merge_available']:
                info['authored_merge_parameters_preserved'] = True
            if info['gaussian_merge_available'] and self._render_budget and self._render_budget.merge_radius_scale != 1:
                info['merge_topology_policy'] = 'display override may change apparent connections; emitted topology counts remain authored values; neck samples disabled'
            if frame is not None and frame.density is not None:
                selected_level = mass_level(frame.density,self._density_display.mass_percent)
                info.update({"density_mass_threshold": selected_level['threshold'] if selected_level else None,
                    "density_actual_enclosed_fraction": selected_level['enclosed_fraction'] if selected_level else None,
                    "density_cutaway": self._density_display.cutaway, "density_slice_axis": self._density_display.axis, "density_slice_fraction": self._density_display.slice_fraction,
                    "density_quantity": frame.density.quantity,
                    "density_amplitude_recorded": frame.density.amplitude is not None,
                    "particle_representation": "recorded_scalar_field_and_authored_atoms",
                    "density_view_mode": self._density_display.mode, "density_orbital_overlay": self._density_display.overlay_id, "density_mass_percent": self._density_display.mass_percent,
                    "density_transfer_decades": self._density_display.decades, "density_display_opacity": self._density_display.opacity,
                    "density_volume_encoding": "maximum-scaled float16, linear display interpolation, 128 ray samples",
                    "density_isovalue": frame.density.isovalue, "density_unit": frame.density.density_unit,
                    "density_shape": list(frame.density.values.shape), "density_spacing_native": frame.density.spacing,
                    "density_source": frame.density.source_note, "density_smoothing": False,
                    "density_display_rgba": list(frame.density.rgba),
                    "density_display_style": "log gradient volume / slices / mass contours / signed amplitude lobes; display choices",
                    "density_note": "recorded scalar-field display; not a sharp molecular boundary or electron path"})
                if frame.density.quantity == 'scalar':
                    info.update(particle_representation='recorded_scalar_grid',
                        scalar_range=list(frame.density.scalar_range),scalar_transfer='linear; representation only',
                        scalar_masked_cells=int(np.count_nonzero(~frame.density.active_mask)),
                        density_display_style='linear gradient volume / axis slices / masked isosurface',
                        density_note='independently recorded scalar data; not particle-trained flow')
            if frame is not None and frame.interface is not None:
                info.update(particle_representation='recorded_interface_triangles',
                    interface_triangles=frame.interface.index_count//3,
                    interface_note='held measured geometry; format checks do not certify physical accuracy')
            if frame is not None and frame.camera is not None:
                info['authored_camera_degrees'] = list(frame.camera)
                info['authored_camera_projection'] = frame.camera_projection
            info['camera_projection'] = self.camera.projection
            info["geant4_scene_visible"] = self._playback.length_unit == "mm" and self._playback.show_geant4_scene
            info["emitted_bonds_drawn"] = len(frame.bonds) if frame is not None and frame.bonds is not None else 0
            info["display_guide_segments"] = len(frame.guides) // 2 if frame is not None and frame.guides is not None else 0
            info["emitted_vectors_drawn"] = self._vector_count // 6
            info["vector_style"] = "emitted shafts; 15% length / 6% half-width arrowheads; cyan display tint"
        return info

    def _ensure_depth(self, width: int, height: int):
        if (width, height) != self._depth_size or self._depth_view is None:
            depth = self.device.create_texture(
                size=(max(width, 1), max(height, 1), 1),
                format=_DEPTH_FORMAT,
                usage=wgpu.TextureUsage.RENDER_ATTACHMENT,
            )
            self._depth_view = depth.create_view()
            self._depth_size = (width, height)
        return self._depth_view

    def draw(self) -> None:
        """Render one frame. Wired as the canvas draw callback."""
        try:
            current = self.context.get_current_texture()
        except Exception:
            return
        color_view = current.create_view()
        size = getattr(current, "size", None) or (*self.canvas.get_physical_size(), 1)
        width, height = int(size[0]), int(size[1])
        if width == 0 or height == 0:
            return
        depth_view = self._ensure_depth(width, height)

        # Update camera uniform (view-proj + light dir + world-space eye, for specular).
        aspect = width / height
        vp = self.camera.view_proj(aspect)
        light = np.array([0.4, 0.8, 0.45, 0.0], dtype=np.float32)
        eye = np.asarray(self.camera.eye(), dtype=np.float32)
        eye4 = np.array([eye[0], eye[1], eye[2], float(self.camera.projection == 'perspective')], dtype=np.float32)
        cam_payload = np.concatenate([_mat_bytes(vp).ravel(), light, eye4]).astype(np.float32)
        self.device.queue.write_buffer(self._camera_uniform, 0, cam_payload)

        encoder = self.device.create_command_encoder()
        render_pass = encoder.begin_render_pass(
            color_attachments=[{
                "view": color_view,
                "resolve_target": None,
                "clear_value": self._clear,
                "load_op": wgpu.LoadOp.clear,
                "store_op": wgpu.StoreOp.store,
            }],
            depth_stencil_attachment={
                "view": depth_view,
                "depth_clear_value": 1.0,
                "depth_load_op": wgpu.LoadOp.clear,
                "depth_store_op": wgpu.StoreOp.store,
            },
        )

        # Ground grid (a rendering aid, not physics).
        render_pass.set_pipeline(self._line_pipeline)
        render_pass.set_bind_group(0, self._camera_bind_group)
        render_pass.set_bind_group(1, self._grid["bind_group"])
        render_pass.set_vertex_buffer(0, self._grid["vbo"])
        render_pass.draw(self._grid["count"], 1, 0, 0)

        # Opaque geometry writes depth. Translucent materials and apparatus do not, so a
        # see-through sand/melt shell cannot erase the rest of the recorded scene.
        recorded_density = bool(self._playback and self._playback.frames and self._particle_frame_idx >= 0 and
                                self._playback.frames[self._particle_frame_idx].density is not None)
        show_scene = (self._playback is None or self._playback.kind != "particles" or
                      (self._playback.length_unit == "mm" and self._playback.show_geant4_scene))
        surfaces = list(self._volumes if show_scene else [])
        if self._particle_surface is not None and not recorded_density:
            surfaces.append(self._particle_surface)
        if self._grouped_material is not None:
            surfaces.append(self._grouped_material)
        for obj in surfaces:
            if obj.alpha >= 1:
                self._draw_surface(render_pass, obj)
        forward = self.camera.target - self.camera.eye()
        for obj in sorted((s for s in surfaces if s.alpha < 1),
                          key=lambda s: float(s.center @ forward), reverse=True):
            self._draw_surface(render_pass, obj)

        # Playback overlay (trajectory polylines up to the cursor, or the current particle frame).
        pb = self._playback
        if pb is not None and not pb.is_empty:
            # Bonds remain available beside either a fused surface or spheres/sprites.
            if pb.kind == "particles" and self._bond_vbo is not None and self._bond_count:
                render_pass.set_pipeline(self._line_pipeline)
                render_pass.set_bind_group(0, self._camera_bind_group)
                render_pass.set_bind_group(1, self._bond_params_bg)
                render_pass.set_vertex_buffer(0, self._bond_vbo)
                render_pass.draw(self._bond_count, 1, 0, 0)
            if pb.kind == "particles" and self._vector_vbo is not None and self._vector_count:
                render_pass.set_pipeline(self._line_pipeline)
                render_pass.set_bind_group(0, self._camera_bind_group)
                render_pass.set_bind_group(1, self._vector_params_bg)
                render_pass.set_vertex_buffer(0, self._vector_vbo)
                render_pass.draw(self._vector_count, 1, 0, 0)
            if pb.kind == "trajectory" and self._traj_vbo is not None and self._traj_draw_segments > 0:
                # One instanced ribbon quad (6 verts) per segment → a glowing beam.
                render_pass.set_pipeline(self._traj_pipeline)
                render_pass.set_bind_group(0, self._camera_bind_group)
                render_pass.set_bind_group(1, self._traj_params_bg)
                render_pass.set_vertex_buffer(0, self._traj_vbo)
                render_pass.draw(6, self._traj_draw_segments, 0, 0)
            elif pb.kind == "particles" and self._particle_vbo is not None and self._particle_count > 0:
                if self._particle_has_radii:
                    render_pass.set_pipeline(self._sphere_pipeline)
                    render_pass.set_bind_group(0, self._camera_bind_group)
                    render_pass.set_vertex_buffer(0, self._sphere_vbo)
                    render_pass.set_vertex_buffer(1, self._particle_vbo)
                    render_pass.set_index_buffer(self._sphere_ibo, wgpu.IndexFormat.uint32)
                    render_pass.draw_indexed(self._sphere_index_count, self._particle_count, 0, 0, 0)
                else:
                    self._draw_particle_sprites(render_pass)

        if recorded_density:
            if self._density_display.mode in ('volume','slice','levels') and self._density_volume is not None:
                self._density_volume.draw(render_pass)
            for gv in self._density_objects:
                render_pass.set_pipeline(self._density_pipeline)
                render_pass.set_bind_group(0,self._camera_bind_group)
                render_pass.set_bind_group(1,gv.bind_group)
                render_pass.set_vertex_buffer(0,gv.vbo)
                render_pass.set_index_buffer(gv.ibo,wgpu.IndexFormat.uint32)
                render_pass.draw_indexed(gv.index_count,1,0,0,0)
        if getattr(self,'_interface_object',None) is not None:
            gv = self._interface_object
            render_pass.set_pipeline(self._surface_pipeline)
            render_pass.set_bind_group(0,self._camera_bind_group)
            render_pass.set_bind_group(1,gv.bind_group)
            render_pass.set_vertex_buffer(0,gv.vbo)
            render_pass.set_index_buffer(gv.ibo,wgpu.IndexFormat.uint32)
            render_pass.draw_indexed(gv.index_count,1,0,0,0)
        render_pass.end()
        self.device.queue.submit([encoder.finish()])

    def _draw_particle_sprites(self, render_pass):
        render_pass.set_pipeline(self._particle_pipeline)
        render_pass.set_bind_group(0, self._camera_bind_group)
        render_pass.set_bind_group(1, self._particle_params_bg)
        render_pass.set_vertex_buffer(0, self._particle_vbo)
        render_pass.draw(6, self._particle_count, 0, 0)
