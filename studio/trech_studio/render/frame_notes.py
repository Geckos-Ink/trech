"""Bounded annotations from held engine frames; no physics or file access."""
from __future__ import annotations


def frame_notes(playback, cursor=None):
    if playback is None or playback.is_empty:
        return []
    if not playback.frames:
        return [playback.label, f"Recorded trajectory clock: {playback.t_min:g}–{playback.t_max:g} {playback.unit}"]
    frame = playback.frames[playback.frame_index_at(playback.t_max if cursor is None else cursor)]
    lines = [frame.phase] if frame.phase else []
    lines.append(frame.clock_text or f"Recorded clock: {frame.time:.6g} {playback.unit}")
    if frame.physical_time_s is not None and playback.time_accelerated:
        lines.append(f"Physical time: {frame.physical_time_s:.6g} s; emitted playback acceleration {frame.time_scale:g}×")
    lines.extend(frame.hud_lines)
    if frame.legend:
        lines.append("Display legend: " + " · ".join(label for label, _ in frame.legend))
    return [str(line)[:240] for line in lines if line][:8]
