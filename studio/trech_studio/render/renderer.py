"""WebGPU scene renderer (wgpu-py).

Draws the scene's volumes as lit surfaces plus a ground grid. Targets wgpu-py >= 0.15; a few
API calls are wrapped defensively because wgpu-py's surface has drifted across releases and we
want the skeleton to survive minor version bumps.

What is real here: device/adapter acquisition, camera + per-object uniforms, an explicit
pipeline (surface.wgsl) with alpha blending + depth, per-volume mesh upload, and a line
pipeline for the grid. What is deliberately deferred (ROADMAP M1): back-to-front transparency
sorting, MSAA, trajectory polylines, and GPU picking. Colours/opacity come from the scene
model's ``volume_color`` (derived from the run's optics — a physics-backed look, not invented).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

import wgpu

from ..scene.model import SceneModel, VolumeNode
from . import mesh as meshgen
from .camera import Camera
from .playback import Playback

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

    __slots__ = ("vbo", "ibo", "index_count", "uniform", "bind_group")

    def __init__(self, vbo, ibo, index_count, uniform, bind_group):
        self.vbo = vbo
        self.ibo = ibo
        self.index_count = index_count
        self.uniform = uniform
        self.bind_group = bind_group


class SceneRenderer:
    """Owns the wgpu device/pipelines and draws a ``SceneModel`` into a canvas context."""

    def __init__(self, canvas, background: str = "dark") -> None:
        self.canvas = canvas
        self.camera = Camera()
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
        self._line_pipeline = self._build_line_pipeline()
        # Playback overlays draw with the depth test off so they stay legible in front of the
        # (translucent) volumes. Both particle clouds and trajectory beams need the camera eye
        # (to face their billboards), a per-instance stream, and a small size uniform.
        self._bgl_size = self._model_bind_group_layout()  # reuse: one 16-byte uniform buffer
        # Particle clouds → camera-facing sprite billboards (particles.wgsl): a dense fluid reads
        # as a body rather than 1-px noise. Radius in a small uniform.
        self._particle_pipeline = self._build_particle_pipeline()
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
        self._particle_frame_cache: dict = {}

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

    def _build_surface_pipeline(self):
        shader = self._load_shader("surface.wgsl")
        layout = self.device.create_pipeline_layout(
            bind_group_layouts=[self._bgl_camera, self._bgl_model]
        )
        return self.device.create_render_pipeline(
            layout=layout,
            vertex={
                "module": shader,
                "entry_point": "vs_main",
                "buffers": [{
                    "array_stride": 6 * 4,
                    "step_mode": wgpu.VertexStepMode.vertex,
                    "attributes": [
                        {"format": wgpu.VertexFormat.float32x3, "offset": 0, "shader_location": 0},
                        {"format": wgpu.VertexFormat.float32x3, "offset": 3 * 4, "shader_location": 1},
                    ],
                }],
            },
            primitive={
                "topology": wgpu.PrimitiveTopology.triangle_list,
                "cull_mode": wgpu.CullMode.none,
            },
            depth_stencil={
                "format": _DEPTH_FORMAT,
                "depth_write_enabled": True,
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
                    "array_stride": 7 * 4,
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

    def set_scene(self, scene: SceneModel) -> None:
        """(Re)build GPU resources for a scene and frame the camera on its bounds."""
        self._volumes = []
        for vol in scene.volumes:
            if vol.is_hidden:                       # authored viz_hidden render hint
                continue
            data = meshgen.for_shape(vol.shape)
            vbo = self._upload(data.vertices, wgpu.BufferUsage.VERTEX)
            ibo = self._upload(data.indices, wgpu.BufferUsage.INDEX)
            model = _model_matrix(vol)
            color, params = scene.volume_surface(vol)
            uniform, bind_group = self._make_object_uniform(model, color, params)
            self._volumes.append(_GpuVolume(vbo, ibo, data.index_count, uniform, bind_group))

        # Grid + camera: a ground plane sunk to the bottom of the subject and sized to its
        # footprint, not the whole world (which left the geometry tiny in a sea of lines).
        self._scene_bounds = scene.bounds_mm()
        self.fit_view(*self._scene_bounds)

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
        self._traj_vbo = None
        self._traj_draw_segments = 0
        self._particle_vbo = None
        self._particle_count = 0
        self._particle_frame_idx = -1
        self._particle_frame_cache = {}
        if playback is None or playback.is_empty:
            return
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
                if self._scene_bounds is not None:
                    bounds = (
                        np.minimum(np.asarray(bounds[0]), np.asarray(self._scene_bounds[0])),
                        np.maximum(np.asarray(bounds[1]), np.asarray(self._scene_bounds[1])),
                    )
                self.fit_view(*bounds)
            self._set_particle_frame(len(playback.frames) - 1)

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
        if idx == self._particle_frame_idx and self._particle_vbo is not None:
            return
        self._particle_frame_idx = idx
        cached = self._particle_frame_cache.get(idx)
        if cached is None:
            frame = pb.frames[idx]
            pos = np.ascontiguousarray(frame.positions, dtype=np.float32)
            if pos.shape[0] == 0:
                self._particle_vbo = None
                self._particle_count = 0
                self._particle_frame_cache[idx] = (None, 0)
                return
            if frame.colors is not None and frame.colors.shape[0] == pos.shape[0]:
                col = np.ascontiguousarray(frame.colors[:, :4], dtype=np.float32)
            else:
                col = np.tile(np.asarray(frame.color, dtype=np.float32), (pos.shape[0], 1))
            verts = np.ascontiguousarray(np.concatenate([pos, col], axis=1), dtype=np.float32)
            cached = (self._upload(verts, wgpu.BufferUsage.VERTEX), int(pos.shape[0]))
            self._particle_frame_cache[idx] = cached
        self._particle_vbo, self._particle_count = cached

    def precision_info(self) -> dict:
        """Representation precision/choices for UI and capture provenance."""
        info = {
            "engine_vertices_interpolated": False,
            "depth_tested_overlays": False,
            "fit_diagonal_mm": self._fit_diag,
        }
        if self._playback is not None and self._playback.kind == "trajectory":
            info.update({
                "trajectory_ribbon_half_width_mm": self._traj_width_mm,
                "trajectory_strength": self._playback.display_strength,
                "trajectory_width_scale": self._playback.ribbon_width_scale,
                "trajectory_opacity": self._playback.ribbon_opacity,
            })
        elif self._playback is not None and self._playback.kind == "particles":
            info["particle_sprite_radius_mm"] = self._particle_radius_mm
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
        eye4 = np.array([eye[0], eye[1], eye[2], 1.0], dtype=np.float32)
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

        # Volumes.
        render_pass.set_pipeline(self._surface_pipeline)
        render_pass.set_bind_group(0, self._camera_bind_group)
        for gv in self._volumes:
            render_pass.set_bind_group(1, gv.bind_group)
            render_pass.set_vertex_buffer(0, gv.vbo)
            render_pass.set_index_buffer(gv.ibo, wgpu.IndexFormat.uint32)
            render_pass.draw_indexed(gv.index_count, 1, 0, 0, 0)

        # Playback overlay (trajectory polylines up to the cursor, or the current particle frame).
        pb = self._playback
        if pb is not None and not pb.is_empty:
            if pb.kind == "trajectory" and self._traj_vbo is not None and self._traj_draw_segments > 0:
                # One instanced ribbon quad (6 verts) per segment → a glowing beam.
                render_pass.set_pipeline(self._traj_pipeline)
                render_pass.set_bind_group(0, self._camera_bind_group)
                render_pass.set_bind_group(1, self._traj_params_bg)
                render_pass.set_vertex_buffer(0, self._traj_vbo)
                render_pass.draw(6, self._traj_draw_segments, 0, 0)
            elif pb.kind == "particles" and self._particle_vbo is not None and self._particle_count > 0:
                # One instanced quad (6 verts) per particle → soft camera-facing sprites.
                render_pass.set_pipeline(self._particle_pipeline)
                render_pass.set_bind_group(0, self._camera_bind_group)
                render_pass.set_bind_group(1, self._particle_params_bg)
                render_pass.set_vertex_buffer(0, self._particle_vbo)
                render_pass.draw(6, self._particle_count, 0, 0)

        render_pass.end()
        self.device.queue.submit([encoder.finish()])
