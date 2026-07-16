"""Honest simulation + representation precision for Studio preview and capture.

The report never invents a quality score. It exposes the concrete Monte-Carlo sample count,
trajectory sampling/caps, metadata coverage, native spatial step, and raster/supersampling choices
that determine what the user can trust in a preview or render.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from .render.playback import Playback


@dataclass
class PrecisionReport:
    simulation: Dict[str, Any] = field(default_factory=dict)
    representation: Dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation": self.simulation,
            "representation": self.representation,
            "notes": list(self.notes),
        }

    def preview_summary(self) -> str:
        events = self.simulation.get("events", 0)
        if self.simulation.get("trajectory_segments", 0):
            segments = self.simulation["trajectory_segments"]
            coverage = self.simulation.get("medium_label_coverage", 0.0)
            strength = self.representation.get("beam_display_strength", 0.0)
            return (f"precision · {events} events · {segments} native segments · "
                    f"medium labels {coverage:.0%} · beam display {strength:.0%}")
        frames = self.representation.get("particle_frames", 0)
        if frames:
            if self.representation.get("particle_representation") == "gaussian_density_surface":
                spacing = self.representation.get("surface_grid_spacing_mm", 0.0)
                return (f"precision · {events} events · {frames} emitted frames · "
                        f"fused surface {spacing:g} mm · held (not interpolated)")
            return f"precision · {events} events · {frames} emitted frames · held (not interpolated)"
        return f"precision · {events} events · no playable spatial samples"


def _mc_standard_error(p: Any, n: int) -> Optional[float]:
    try:
        value = float(p)
    except (TypeError, ValueError):
        return None
    if n <= 0 or value < 0.0 or value > 1.0:
        return None
    return math.sqrt(max(0.0, value * (1.0 - value)) / n)


def build_precision_report(
    result: Any,
    playback: Playback,
    *,
    scene: Optional[Any] = None,
    output_px: Optional[Tuple[int, int]] = None,
    supersample: int = 1,
    purpose: str = "preview",
) -> PrecisionReport:
    """Build a precision report from parsed engine output plus explicit render settings."""
    scores = result.run_end_scores() or {}
    summary = result.summary()
    events = int(summary.get("n_events") or scores.get("n_events") or 0)
    recorded_trajectories = int(scores.get("viz_trajectories") or playback.source_track_count or 0)
    recorded_vertices = int(scores.get("viz_segments") or 0)
    trajectory_segments = playback.segment_count
    simulation: Dict[str, Any] = {
        "events": events,
        "determinism_mode": summary.get("determinism_mode"),
        "predictive_mode": summary.get("predictive_mode"),
        "physics_list": summary.get("physics_list"),
        "recorded_trajectories": recorded_trajectories,
        "loaded_trajectories": playback.source_track_count,
        "recorded_trajectory_vertices": recorded_vertices,
        "trajectory_segments": trajectory_segments,
        "trajectory_dropped": int(scores.get("viz_dropped") or 0),
        "trajectory_capped": int(scores.get("viz_capped") or 0),
        "medium_label_coverage": playback.material_label_coverage,
        "interaction_label_coverage": playback.interaction_label_coverage,
        "medium_counts": dict(playback.medium_counts),
        "interaction_counts": dict(playback.interaction_counts),
        "medium_interaction_counts": dict(playback.medium_interaction_counts),
    }
    for key in ("primaries_transmitted_fraction", "primaries_uncollided_fraction"):
        se = _mc_standard_error(scores.get(key), events)
        if se is not None:
            simulation[f"{key}_standard_error"] = se
    if scene is not None:
        viz = (getattr(scene, "raw", None) or {}).get("viz") or {}
        simulation.update({
            "trajectory_sample_every_nth": int(viz.get("sample_every_nth") or 1),
            "trajectory_max_count": int(viz.get("max_trajectories") or 0),
            "trajectory_max_segments_per_track": int(viz.get("max_segments_per_trajectory") or 0),
        })

    representation: Dict[str, Any] = {
        "purpose": purpose,
        "playback_kind": playback.kind,
        "source_tag": playback.source_tag,
        "engine_positions_interpolated": False,
        "timeline_selection": "native prefix" if playback.kind == "trajectory" else "hold-last frame",
        "supersample": max(1, int(supersample)),
    }
    if output_px is not None:
        representation["output_pixels"] = [int(output_px[0]), int(output_px[1])]
        representation["internal_render_pixels"] = [
            int(output_px[0]) * max(1, int(supersample)),
            int(output_px[1]) * max(1, int(supersample)),
        ]
    if playback.kind == "trajectory":
        representation.update({
            "rendered_trajectory_segments": playback.segment_count,
            "trajectory_segment_budget": playback.segment_budget,
            "trajectory_segment_budget_reached": playback.segment_budget_reached,
            "trajectory_load_limit_applied": recorded_trajectories > playback.source_track_count,
            "beam_display_strength": playback.display_strength,
            "beam_ribbon_width_scale": playback.ribbon_width_scale,
            "beam_ribbon_opacity": playback.ribbon_opacity,
            "native_mean_segment_length_mm": playback.mean_step_length_mm,
            "air_style": "0.58x width, 0.72x opacity; spectrum colour preserved",
        })
    elif playback.kind == "particles":
        surface = playback.frames[-1].surface if playback.frames else None
        representation.update({
            "particle_frames": playback.frame_count,
            "particle_positions_per_current_frame": (
                int(playback.frames[-1].positions.shape[0]) if playback.frames else 0
            ),
            "playback_time_accelerated": playback.time_accelerated,
            "physical_time_max_s": playback.physical_t_max,
            "particle_representation": (
                "gaussian_density_surface" if surface is not None else "camera_facing_sprites"
            ),
        })
        if surface is not None:
            representation.update({
                "surface_grid_spacing_mm": surface.grid_spacing_mm,
                "surface_sigma_mm": surface.sigma_mm,
                "surface_iso_level": surface.iso_level,
                "surface_positions_unmodified": surface.positions_unmodified,
                "surface_policy": surface.policy,
                "surface_neck_mode": surface.neck_mode,
                "surface_neck_min_distance_mm": surface.neck_min_distance_mm,
                "surface_neck_max_distance_mm": surface.neck_max_distance_mm,
                "surface_neck_samples_per_pair": surface.neck_samples,
                "surface_neck_weight": surface.neck_weight,
                "surface_neck_preserves_component_topology": surface.neck_preserves_topology,
            })

    notes = [
        "Simulation precision is reported as counts/caps/standard errors, not a subjective score.",
        "Ribbon/sprite/surface settings are labelled representation choices; coordinates and time are engine emits.",
    ]
    if playback.kind == "trajectory" and playback.interaction_label_coverage < 1.0:
        notes.append("Older trajectory vertices lack process labels; unknown bends are not called scattering.")
    if playback.kind == "trajectory" and (
        playback.segment_budget_reached or recorded_trajectories > playback.source_track_count
    ):
        notes.append("The preview/capture trajectory budget truncated recorded engine samples; counts disclose the reduction.")
    if playback.kind == "particles" and playback.time_accelerated:
        notes.append("The scenario emitted both accelerated playback time and retained physical time; Studio replays that declared mapping without interpolation.")
    return PrecisionReport(simulation=simulation, representation=representation, notes=notes)
