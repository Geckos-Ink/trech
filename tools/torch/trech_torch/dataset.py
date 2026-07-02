"""Unified dataset harvesting from TRECH Geant4 run outputs.

Every TRECH training path starts from the same JSONL artefacts a `trech run`
writes (see `docs/output_schema.md`):

- `trech_viz_scene.json`      -> material-scale optics samples
                                 (`derived_optics` blocks: composition+density
                                 -> n / absorption / scatter)
- `trech_event_features.jsonl`-> event-scale feature vectors + teacher labels
                                 (schema `trech_event_features_v1`)
- `trech_scores.jsonl`        -> run-scale summaries (system_* densities,
                                 event moments) + scale metadata
- `trech_provenance.jsonl`    -> the exact config (beam energy, medium box,
                                 seed) each sample was generated under

This module centralises the parsing so the optics-surrogate trainer, the
event-stratifier trainer, and the Geant4 experiment planner all consume one
schema-checked view of "what has been simulated so far".  Keep the feature
and composition schemas in lock-step with the C++ side:

- ``FEATURE_NAMES``          == ``FeaturePipeline::FeatureNames()``
  (schema id ``trech_event_features_v1``)
- ``COMPOSITION_ELEMENTS``   == ``OpticsSurrogate::kCompositionElements``
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Schemas (mirrors of the C++ contracts — keep in lock-step)
# ---------------------------------------------------------------------------

FEATURE_SCHEMA_ID = "trech_event_features_v1"

# Must match FeaturePipeline::FeatureNames() exactly (order matters).
FEATURE_NAMES = [
    "total_edep_mev",
    "total_track_length_mm",
    "total_step_count",
    "total_track_count",
    "optical_photon_steps",
    "optical_photon_tracks",
    "optical_photon_track_length_mm",
]

# Must match OpticsSurrogate::kCompositionElements exactly.
COMPOSITION_ELEMENTS = [
    "H", "C", "N", "O", "F", "Na", "Mg", "Al", "Si", "P", "S", "Cl", "I", "other",
]
INPUT_FEATURE_COUNT = len(COMPOSITION_ELEMENTS) + 1  # + density

# Minimal NIST -> element mass fraction fallback for legacy scene manifests
# that predate the engine emitting `element_mass_fractions` directly.
G4_MATERIAL_TO_MASS_FRACTIONS: Dict[str, Dict[str, float]] = {
    "G4_AIR":      {"N": 0.755, "O": 0.232, "C": 0.013},
    "G4_WATER":    {"H": 0.1119, "O": 0.8881},
    "G4_SILICON_DIOXIDE": {"Si": 0.4675, "O": 0.5325},
    "G4_C":        {"C": 1.0},
    "G4_Galactic": {"other": 1.0},
    "G4_SODIUM_IODIDE": {"Na": 0.1534, "I": 0.8466},
}

# Dimension-scale bands by characteristic length (mm).  These are the scales
# the multi-scale ML ladder distinguishes: which surrogate is trained/valid at
# which scale is tracked per run so inference never silently extrapolates
# across bands.
DIMENSION_SCALE_BANDS = [
    ("atomic", 1e-6),        # < 1 nm       (molecular MD, bonds)
    ("nano", 1e-3),          # 1 nm - 1 um  (CNT channels)
    ("micro", 1.0),          # 1 um - 1 mm  (cells, membranes)
    ("meso", 1e3),           # 1 mm - 1 m   (lab bench: cups, slabs)
    ("macro", float("inf")),  # > 1 m
]


def classify_dimension_scale(characteristic_length_mm: float) -> str:
    """Map a characteristic length in mm onto a named dimension-scale band."""
    if not characteristic_length_mm or characteristic_length_mm <= 0:
        return "unknown"
    for name, upper_mm in DIMENSION_SCALE_BANDS:
        if characteristic_length_mm < upper_mm:
            return name
    return "macro"


# ---------------------------------------------------------------------------
# Sample / metadata records
# ---------------------------------------------------------------------------


@dataclass
class OpticsSample:
    """Material-scale sample: composition vector -> optical targets."""
    material_name: str
    composition_vector: List[float]   # length INPUT_FEATURE_COUNT
    targets: List[float]              # [n, abs_len_mm, scat_len_mm]
    source: str = ""                  # scene manifest path
    anchored: bool = False            # n target from handbook anchor?
    extractor_n: float = 1.0          # physics-derived n (kept for comparison
                                      # even when an anchor overrides the target)


@dataclass
class EventSample:
    """Event-scale sample: trech_event_features_v1 vector + teacher label."""
    features: List[float]             # ordered by FEATURE_NAMES
    label: str
    exceptional: bool
    source: str                       # teacher: "thresholds" | "model" | ...
    event_id: int
    run_dir: str


@dataclass
class RunMetadata:
    """Run-scale context: what Geant4 experiment produced the samples."""
    run_dir: str
    n_events: int = 0
    seed: int = 0
    physics_list: str = ""
    determinism_mode: str = ""
    beam_particle: str = ""
    beam_energy_mev: float = 0.0
    medium_material: str = ""
    medium_box_mm: float = 0.0
    world_size_mm: float = 0.0
    system_volume_mm3: float = 0.0
    optics_enabled: bool = False
    stratify_enabled: bool = False
    characteristic_length_mm: float = 0.0
    dimension_scale: str = "unknown"
    config_hash: str = ""
    exceptional_count: int = 0
    predictable_count: int = 0
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# JSONL / run-dir plumbing
# ---------------------------------------------------------------------------


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield parsed JSON objects per line, skipping malformed lines loudly."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as err:
                    print(f"warning: {path}:{line_no}: bad JSONL line: {err}",
                          file=sys.stderr)
    except OSError as err:
        print(f"warning: cannot read {path}: {err}", file=sys.stderr)


def find_run_dirs(paths: Sequence[str]) -> List[Path]:
    """Expand paths into run dirs (dirs holding a trech_scores.jsonl)."""
    out: List[Path] = []
    seen = set()
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"warning: path not found: {p}", file=sys.stderr)
            continue
        candidates: Iterable[Path]
        if p.is_file():
            candidates = [p.parent]
        elif (p / "trech_scores.jsonl").exists():
            candidates = [p]
        else:
            candidates = sorted(f.parent for f in p.rglob("trech_scores.jsonl"))
        for c in candidates:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


def load_run_metadata(run_dir: Path) -> RunMetadata:
    """Assemble run metadata from provenance (config) + run scores."""
    meta = RunMetadata(run_dir=str(run_dir))
    prov_path = run_dir / "trech_provenance.jsonl"
    for record in iter_jsonl(prov_path):
        meta.seed = int(record.get("seed") or meta.seed)
        meta.n_events = int(record.get("n_events") or meta.n_events)
        meta.physics_list = record.get("physics_list") or meta.physics_list
        meta.determinism_mode = (record.get("determinism_mode")
                                 or meta.determinism_mode)
        meta.config_hash = record.get("config_hash") or meta.config_hash
        raw_cfg = record.get("config_json")
        if raw_cfg:
            try:
                cfg = json.loads(raw_cfg)
            except json.JSONDecodeError:
                cfg = {}
            beam = cfg.get("beam") or {}
            meta.beam_particle = beam.get("particle") or meta.beam_particle
            meta.beam_energy_mev = float(beam.get("energyMeV")
                                         or meta.beam_energy_mev)
            det = cfg.get("detector") or {}
            meta.medium_material = (det.get("mediumMaterial")
                                    or meta.medium_material)
            meta.medium_box_mm = float(det.get("mediumBoxMm")
                                       or meta.medium_box_mm)
            meta.world_size_mm = float(det.get("worldSizeMm")
                                       or meta.world_size_mm)
        break  # first record carries the run config
    for record in iter_jsonl(run_dir / "trech_scores.jsonl"):
        if record.get("phase") not in (None, "run_summary", "run_end"):
            continue
        meta.optics_enabled = bool(record.get("optics_enabled",
                                              meta.optics_enabled))
        meta.stratify_enabled = bool(record.get("stratify_enabled",
                                                meta.stratify_enabled))
        meta.system_volume_mm3 = float(record.get("system_volume_mm3")
                                       or meta.system_volume_mm3)
        meta.exceptional_count = int(record.get("stratify_exceptional_count")
                                     or meta.exceptional_count)
        meta.predictable_count = int(record.get("stratify_predictable_count")
                                     or meta.predictable_count)
        meta.n_events = int(record.get("n_events") or meta.n_events)
    # Characteristic length: prefer the scored system volume, then the medium
    # box, then the world extent.
    if meta.system_volume_mm3 > 0:
        meta.characteristic_length_mm = meta.system_volume_mm3 ** (1.0 / 3.0)
    elif meta.medium_box_mm > 0:
        meta.characteristic_length_mm = meta.medium_box_mm
    elif meta.world_size_mm > 0:
        meta.characteristic_length_mm = meta.world_size_mm
    meta.dimension_scale = classify_dimension_scale(
        meta.characteristic_length_mm)
    return meta


def load_event_samples(run_dir: Path) -> List[EventSample]:
    """Read trech_event_features.jsonl (stratify.dumpFeatures output)."""
    samples: List[EventSample] = []
    path = run_dir / "trech_event_features.jsonl"
    if not path.exists():
        return samples
    for record in iter_jsonl(path):
        if record.get("phase") != "event_features":
            continue
        feats = record.get("features") or {}
        vector = [float(feats.get(name) or 0.0) for name in FEATURE_NAMES]
        samples.append(EventSample(
            features=vector,
            label=str(record.get("label") or ""),
            exceptional=bool(record.get("exceptional", False)),
            source=str(record.get("source") or ""),
            event_id=int(record.get("event_id") or 0),
            run_dir=str(run_dir),
        ))
    return samples


def harvest_event_dataset(paths: Sequence[str],
                          ) -> tuple[List[EventSample], List[RunMetadata]]:
    """Harvest all event samples + run metadata under the given paths."""
    all_samples: List[EventSample] = []
    all_meta: List[RunMetadata] = []
    for run_dir in find_run_dirs(paths):
        meta = load_run_metadata(run_dir)
        samples = load_event_samples(run_dir)
        if not samples:
            meta.notes.append("no trech_event_features.jsonl "
                              "(enable stratify.dumpFeatures)")
        all_meta.append(meta)
        all_samples.extend(samples)
    return all_samples, all_meta


# ---------------------------------------------------------------------------
# Optics samples (scene manifests)
# ---------------------------------------------------------------------------


def encode_composition(mass_fractions: Dict[str, float],
                       density: float) -> List[float]:
    """Encode element mass fractions + density into the canonical vector.

    Mirrors OpticsSurrogate::encodeComposition: unknown elements fold into
    'other', and over-unity element sums renormalize across all 14 element
    slots; density rides in the final slot.
    """
    out = [0.0] * INPUT_FEATURE_COUNT
    for symbol, fraction in mass_fractions.items():
        if symbol in COMPOSITION_ELEMENTS:
            idx = COMPOSITION_ELEMENTS.index(symbol)
        else:
            idx = COMPOSITION_ELEMENTS.index("other")
        out[idx] += max(0.0, float(fraction))
    elem_sum = sum(out[:-1])
    if elem_sum > 1.0:
        for i in range(len(out) - 1):
            out[i] /= elem_sum
    out[-1] = float(density)
    return out


def load_anchors(path: Optional[Path]) -> Dict[str, float]:
    """Optional handbook refractive-index anchors {material_name: n}.

    Anchors are training/validation targets only; they never feed photon
    transport (see AGENTS.md invariants).
    """
    if not path:
        return {}
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as err:
        print(f"warning: cannot load anchors {path}: {err}", file=sys.stderr)
        return {}
    table = doc.get("refractive_index_589nm", doc) if isinstance(doc, dict) else {}
    return {str(k).lower(): float(v) for k, v in table.items()
            if isinstance(v, (int, float))}


def _resolve_material_mass_fractions(material_block: Dict,
                                     derived: Dict) -> Optional[Dict[str, float]]:
    """Best-effort mass-fraction recovery from a scene.materials[] entry."""
    fractions: Dict[str, float] = {}
    components = material_block.get("components") or []
    if not components:
        name = material_block.get("name") or derived.get("material_name")
        if name and name in G4_MATERIAL_TO_MASS_FRACTIONS:
            return dict(G4_MATERIAL_TO_MASS_FRACTIONS[name])
        return None
    for comp in components:
        ref = comp.get("material") or ""
        frac = float(comp.get("fraction") or 0.0)
        if frac <= 0:
            continue
        atomic = G4_MATERIAL_TO_MASS_FRACTIONS.get(ref)
        if atomic is None:
            continue
        for symbol, mass_frac in atomic.items():
            fractions[symbol] = fractions.get(symbol, 0.0) + mass_frac * frac
    if not fractions:
        return None
    return fractions


def find_scene_manifests(paths: Sequence[str]) -> List[Path]:
    """Expand paths into trech_viz_scene.json manifests."""
    out: List[Path] = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"warning: path not found: {p}", file=sys.stderr)
            continue
        if p.is_file():
            out.append(p)
        else:
            out.extend(sorted(p.rglob("trech_viz_scene.json")))
    return out


def harvest_optics_samples(scene_paths: Sequence[Path],
                           anchors: Optional[Dict[str, float]] = None,
                           ) -> List[OpticsSample]:
    """Extract (composition+density) -> (n, abs, scat) samples from scenes.

    When ``anchors`` provides a handbook n for a material, it overrides the
    extractor-derived n target (the residual-learning track); abs/scat always
    stay extractor-derived.
    """
    anchors = anchors or {}
    samples: List[OpticsSample] = []
    seen_keys = set()
    for path in scene_paths:
        try:
            scene = json.loads(Path(path).read_text())
        except Exception as err:
            print(f"warning: failed to read {path}: {err}", file=sys.stderr)
            continue
        materials_by_name = {
            (m.get("name") or "").lower(): m for m in scene.get("materials") or []
        }
        for derived in scene.get("derived_optics") or []:
            if not derived.get("available", True):
                continue
            material_name = derived.get("material_name") or ""
            config_key = derived.get("config_material_key") or ""
            # Preferred: the engine emits resolved per-element mass fractions
            # directly; fall back to the materials block / legacy table.
            mass_fractions = derived.get("element_mass_fractions") or None
            if not mass_fractions:
                mb = materials_by_name.get(config_key.lower()) or {}
                if not mb and material_name in G4_MATERIAL_TO_MASS_FRACTIONS:
                    mb = {"name": material_name, "components": [
                        {"material": material_name, "fraction": 1.0},
                    ]}
                mass_fractions = _resolve_material_mass_fractions(mb, derived)
            if not mass_fractions:
                continue
            density = float(derived.get("density_gcm3") or 0.0)
            if density <= 0:
                continue
            key = (material_name, round(density, 6))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            comp_vec = encode_composition(mass_fractions, density)
            anchor_n = (anchors.get(config_key.lower())
                        or anchors.get(material_name.lower()))
            extractor_n = float(derived.get("mean_refractive_index") or 1.0)
            n_target = float(anchor_n) if anchor_n else extractor_n
            targets = [
                n_target,
                float(derived.get("mean_absorption_length_mm") or 0.0),
                float(derived.get("mean_scatter_length_mm") or 0.0),
            ]
            samples.append(OpticsSample(
                material_name=material_name,
                composition_vector=comp_vec,
                targets=targets,
                source=str(path),
                anchored=bool(anchor_n),
                extractor_n=extractor_n,
            ))
    return samples
