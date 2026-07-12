"""Headless capture of a run's viewport — a still PNG + an animation MP4/GIF for AI validation.

This renders a TRECH run's scene *and its timeline playback* (trajectory growth or particle
frames) offscreen using **Studio's own wgpu renderer** — the same code the desktop viewport
runs — and encodes the frames with ``ffmpeg``. So the captured images test Studio's rendering
of complex scenarios, not a parallel drawing path.

Honesty (studio/AGENTS.md): every position/time drawn is engine output on the engine's own
clock; a slow turntable and the trajectory/fluid colours are the only rendering choices. The
sidecar ``<prefix>.json`` records the run's seed / determinism / physics list / emit tags and
the playback kind so a validating agent has the provenance next to the pixels.

Usage::

    python -m trech_studio.capture --run build/dev/out_viz_refraction --out /tmp/viz
    python -m trech_studio.capture --run <dir> --out <prefix> --still     # PNG + JSON only

Degrades gracefully: with no GPU it writes the JSON sidecar and exits non-zero (the suite marks
the case "no-render"); with no ffmpeg it still writes the PNG via a tiny built-in encoder.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

from .engine.outputs import load_run_result
from .render.playback import Playback, build_playback
from .scene.loader import placeholder_scene, scene_from_output_dir
from .scene.model import SceneModel


# --- PNG fallback (used only when ffmpeg is unavailable) --------------------------------

def _write_png(path: Path, rgb: np.ndarray) -> None:
    """Minimal RGB PNG writer (numpy + zlib), so stills work without ffmpeg or PIL."""
    h, w, _ = rgb.shape
    rows = bytearray()
    line = np.zeros((w * 3 + 1,), dtype=np.uint8)
    for y in range(h):
        line[0] = 0  # filter type 0
        line[1:] = rgb[y].reshape(-1)
        rows.extend(line.tobytes())

    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit, colour type 2 (RGB)
    idat = zlib.compress(bytes(rows), 6)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


# --- result ----------------------------------------------------------------------------

@dataclass
class CaptureResult:
    run_dir: Path
    ok: bool = False
    message: str = ""
    playback_kind: str = "empty"
    png: Optional[Path] = None
    mp4: Optional[Path] = None
    gif: Optional[Path] = None
    meta: Optional[Path] = None
    artifacts: List[str] = field(default_factory=list)


def _even(n: int) -> int:
    return n - (n % 2)


def _have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _offscreen_renderer(width: int, height: int, background: str):
    """Create an offscreen wgpu canvas + SceneRenderer, or (None, None, reason)."""
    try:
        from rendercanvas.offscreen import RenderCanvas  # type: ignore
        from .render.renderer import SceneRenderer
    except Exception as exc:  # noqa: BLE001
        return None, None, f"render stack unavailable: {exc}"
    try:
        canvas = RenderCanvas(size=(width, height), pixel_ratio=1)
        renderer = SceneRenderer(canvas, background=background)
        canvas.request_draw(renderer.draw)
        return canvas, renderer, ""
    except Exception as exc:  # noqa: BLE001 - no GPU / device init failure
        return None, None, f"GPU init failed: {exc}"


def _frame_rgb(canvas, width: int, height: int) -> Optional[np.ndarray]:
    img = np.asarray(canvas.draw())
    if img.ndim != 3 or img.shape[0] < 2 or img.shape[1] < 2:
        return None
    return np.ascontiguousarray(img[:height, :width, :3], dtype=np.uint8)


def _particle_bounds(playback: Playback):
    """(lo, hi) mm over a few sampled particle frames (for camera framing)."""
    n = playback.frame_count
    idxs = sorted({0, n // 2, n - 1})
    pts = np.concatenate([playback.frames[i].positions for i in idxs], axis=0)
    return pts.min(axis=0), pts.max(axis=0)


def _scene_for(run_dir: Path, playback: Playback) -> SceneModel:
    """Prefer the run's viz scene; else a grid-only stage for particle runs (no fake volume),
    or the labelled placeholder cube for empty/trajectory runs with no geometry."""
    scene = scene_from_output_dir(run_dir)
    if scene is not None:
        return scene
    if playback.kind == "particles" and playback.frames:
        lo, hi = _particle_bounds(playback)
        world = float(np.max(hi - lo)) * 1.6 or 100.0
        return SceneModel(world_size_mm=world, world_material="(no viz scene)")
    return placeholder_scene()


def capture_run(
    run_dir: Path,
    out_prefix: Path,
    *,
    width: int = 960,
    height: int = 640,
    seconds: float = 6.0,
    fps: int = 24,
    orbit_deg: float = 30.0,
    background: str = "dark",
    still: bool = False,
    label: str = "",
    gif_max_colors: Optional[int] = None,
) -> CaptureResult:
    """Render a run to ``<out_prefix>.png`` (+ ``.mp4``/``.gif`` unless ``still``) + ``.json``."""
    run_dir = Path(run_dir)
    out_prefix = Path(out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    width, height = _even(max(width, 16)), _even(max(height, 16))
    res = CaptureResult(run_dir=run_dir)

    # Parse the run (all engine-file reading stays in engine.outputs / scene.loader).
    result = load_run_result(run_dir)
    playback = build_playback(result.load_trajectories(limit=4000), result.emits)
    scene = _scene_for(run_dir, playback)
    res.playback_kind = playback.kind

    # Always write the provenance sidecar so an agent has context even if rendering fails.
    meta_path = out_prefix.with_suffix(".json")
    summary = result.summary()
    meta = {
        "run_dir": str(run_dir),
        "label": label,
        "scene_source": scene.source_path,
        "world_size_mm": scene.world_size_mm,
        "volumes": len(scene.volumes),
        "playback_kind": playback.kind,
        "playback_label": playback.label,
        "playback_unit": playback.unit,
        "playback_t_max": playback.t_max,
        "emit_tags": result.emit_tags(),
        "run_summary": summary,
        "honesty": (
            "Pixels are Studio's wgpu render of engine outputs on the engine clock; "
            "turntable + trajectory/fluid colours are rendering choices, not physics."
        ),
        "artifacts": [],
    }

    canvas, renderer, reason = _offscreen_renderer(width, height, background)
    if renderer is None:
        res.ok = False
        res.message = reason
        meta["render_error"] = reason
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        res.meta = meta_path
        return res

    renderer.set_scene(scene)
    renderer.set_playback(playback)
    # Frame particle clouds on their own extent (the scene box may be absent/oversized).
    if playback.kind == "particles" and playback.frames:
        lo, hi = _particle_bounds(playback)
        renderer.camera.fit_bounds(lo, hi)
    base_yaw = renderer.camera.yaw

    # --- still: the complete result, from the base 3/4 angle -----------------------------
    if not playback.is_empty:
        renderer.set_playback_time(playback.t_max)
    still_rgb = _frame_rgb(canvas, width, height)
    png_path = out_prefix.with_suffix(".png")
    if still_rgb is not None:
        if _have_ffmpeg():
            _encode_png_ffmpeg(still_rgb, png_path, width, height)
        else:
            _write_png(png_path, still_rgb)
        res.png = png_path
        res.artifacts.append(png_path.name)
        meta["artifacts"].append(png_path.name)

    # --- animation: MP4 + GIF (skipped for --still or when ffmpeg is missing) ------------
    n_frames = max(2, int(round(seconds * fps)))
    if not still and _have_ffmpeg():
        mp4_path = out_prefix.with_suffix(".mp4")
        try:
            _encode_mp4(
                renderer, canvas, playback, mp4_path,
                width=width, height=height, fps=fps, n_frames=n_frames,
                base_yaw=base_yaw, orbit_deg=orbit_deg,
            )
            res.mp4 = mp4_path
            res.artifacts.append(mp4_path.name)
            meta["artifacts"].append(mp4_path.name)
            gif_path = out_prefix.with_suffix(".gif")
            if _mp4_to_gif(mp4_path, gif_path, fps=min(fps, 18), gif_width=min(width, 480),
                           max_colors=gif_max_colors):
                res.gif = gif_path
                res.artifacts.append(gif_path.name)
                meta["artifacts"].append(gif_path.name)
        except Exception as exc:  # noqa: BLE001 - video is best-effort; the still already landed
            meta["video_error"] = str(exc)
    elif not still and not _have_ffmpeg():
        meta["video_error"] = "ffmpeg not found on PATH; only the still PNG was written"

    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    res.meta = meta_path
    res.ok = res.png is not None
    res.message = "ok" if res.ok else "render produced no frame"
    return res


def capture_reference(
    run_dir: Path,
    gif_path: Path,
    *,
    width: int = 320,
    height: int = 220,
    seconds: float = 3.0,
    fps: int = 10,
) -> CaptureResult:
    """Render a **compact** animation GIF for committing as a repo reference.

    Deliberately small (default 320 px · 10 fps · 3 s) so a curated handful can live in git
    without bloating the repo — see ``studio/tests/reference/``. Only ever run behind the
    suite's ``--update-refs`` gate, not on every capture. Reuses the same renderer path as the
    desktop viewport (via :func:`capture_run`), then keeps just the GIF + a small sidecar.
    """
    gif_path = Path(gif_path)
    gif_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_prefix = gif_path.with_suffix("").with_name(gif_path.stem + ".__ref_tmp")
    res = capture_run(run_dir, tmp_prefix, width=width, height=height,
                      seconds=seconds, fps=fps, label=f"reference:{gif_path.stem}",
                      gif_max_colors=64)
    # Keep the GIF (compact) at the target path; drop the tmp PNG/MP4 to save space.
    if res.gif is not None and res.gif.is_file():
        shutil.move(str(res.gif), str(gif_path))
        res.gif = gif_path
    for stray in (res.png, res.mp4, res.meta):
        if stray is not None and stray.is_file() and stray != gif_path:
            try:
                stray.unlink()
            except OSError:
                pass
    res.png = res.mp4 = None
    return res


# --- ffmpeg encoders -------------------------------------------------------------------

def _encode_png_ffmpeg(rgb: np.ndarray, path: Path, width: int, height: int) -> None:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{width}x{height}",
        "-i", "-", "-frames:v", "1", str(path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    proc.communicate(rgb.tobytes())
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg png encode failed")


def _encode_mp4(renderer, canvas, playback, path: Path, *, width, height, fps, n_frames,
                base_yaw, orbit_deg) -> None:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{width}x{height}",
        "-framerate", str(fps), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        span = playback.t_max - playback.t_min if not playback.is_empty else 0.0
        for i in range(n_frames):
            frac = i / (n_frames - 1)
            # Gentle turntable so the 3D nature reads even on a static or 2-frame run.
            renderer.camera.yaw = base_yaw + np.radians(orbit_deg) * frac
            if span > 0.0:
                renderer.set_playback_time(playback.t_min + frac * span)
            rgb = _frame_rgb(canvas, width, height)
            if rgb is None:
                continue
            proc.stdin.write(rgb.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg mp4 encode failed")


def _mp4_to_gif(mp4: Path, gif: Path, *, fps: int, gif_width: int,
                max_colors: Optional[int] = None) -> bool:
    palette = mp4.with_name(mp4.stem + "_palette.png")
    vf = f"fps={fps},scale={gif_width}:-1:flags=lanczos"
    palettegen = "palettegen=stats_mode=diff"
    if max_colors:  # fewer colours -> much smaller GIF (used for committed references)
        palettegen = f"palettegen=stats_mode=diff:max_colors={max_colors}"
    gen = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4),
         "-vf", f"{vf},{palettegen}", str(palette)],
        check=False,
    )
    if gen.returncode != 0 or not palette.exists():
        return False
    use = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-i", str(palette),
         "-lavfi", f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3", str(gif)],
        check=False,
    )
    try:
        palette.unlink()
    except OSError:
        pass
    return use.returncode == 0 and gif.exists()


# --- CLI -------------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Capture a TRECH run's Studio viewport (PNG + MP4/GIF).")
    parser.add_argument("--run", required=True, type=Path, help="run output directory")
    parser.add_argument("--out", type=Path, default=None,
                        help="output path prefix, no extension (required unless --reference)")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=640)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--orbit", type=float, default=30.0, help="total turntable degrees over the clip")
    parser.add_argument("--background", choices=("dark", "light"), default="dark")
    parser.add_argument("--still", action="store_true", help="PNG + JSON only (no video)")
    parser.add_argument("--label", default="", help="human label recorded in the sidecar JSON")
    parser.add_argument("--reference", type=Path, default=None,
                        help="write a COMPACT reference GIF to this path (repo reference; small)")
    args = parser.parse_args(argv)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # in case Qt gets imported transitively
    if args.reference is not None:
        res = capture_reference(args.run, args.reference,
                                width=min(args.width, 360), height=min(args.height, 260),
                                seconds=min(args.seconds, 4.0), fps=min(args.fps, 12))
        size = res.gif.stat().st_size if res.gif and res.gif.is_file() else 0
        tag = "OK" if res.gif is not None else "FAIL"
        print(f"[{tag}] reference {args.run} -> {args.reference} ({size / 1024:.0f} KiB)  {res.message}")
        return 0 if res.gif is not None else 2

    if args.out is None:
        parser.error("--out is required unless --reference is given")
    res = capture_run(
        args.run, args.out,
        width=args.width, height=args.height, seconds=args.seconds, fps=args.fps,
        orbit_deg=args.orbit, background=args.background, still=args.still, label=args.label,
    )
    tag = "OK" if res.ok else "FAIL"
    print(f"[{tag}] {args.run} -> {', '.join(res.artifacts) or '(no artifacts)'}  {res.message}")
    return 0 if res.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
