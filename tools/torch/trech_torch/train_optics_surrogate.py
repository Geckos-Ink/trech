"""Train the optics surrogate from TRECH scene manifests.

Dataset construction
--------------------

We scan one or more directories of `trech_viz_scene.json` files (output by
`trech run` with `optics.derive.enable: true`) and extract, for each material
that appears with a usable `derived_optics` block:

    input  :: [mass_fraction(H), mass_fraction(C), ..., mass_fraction(other), density_gcm3]
    output :: [mean_refractive_index, mean_absorption_length_mm, mean_scatter_length_mm]

The element list is fixed and matches `OpticsSurrogate::kCompositionElements`
in the C++ header — keep them in sync.  Mass fractions are pulled from
Geant4's NIST material composition by re-parsing the `materials` block of
the scene manifest when present; for materials that ship only as G4 NIST
names we fall back to a small hard-coded lookup table for the common ones
needed by the validation scenarios.

Training
--------

Small MLP with one hidden layer (compatible with TorchScript export, no
control flow surprises).  Trains with Adam + MSE on log-scaled outputs
(absorption / scatter lengths span many orders of magnitude).

Output
------

Two files:

- `--out` (default `optics_surrogate.pt`): TorchScript module taking a
  `[1, kInputFeatureCount]` float tensor and returning a `[1, 3]` float tensor.
- `--manifest` (default `optics_surrogate.manifest.json`): training metadata
  (dataset size, element list, scaler params, expected ranges).  The engine
  doesn't read this file — it's for humans + the validation suite.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import torch
except ImportError as err:  # pragma: no cover - error path
    raise SystemExit(
        "torch is required to train the optics surrogate; "
        "install via `pip install torch`"
    ) from err

# Must match OpticsSurrogate::kCompositionElements exactly.
COMPOSITION_ELEMENTS = [
    "H", "C", "N", "O", "F", "Na", "Mg", "Al", "Si", "P", "S", "Cl", "other",
]
INPUT_FEATURE_COUNT = len(COMPOSITION_ELEMENTS) + 1  # + density
OUTPUT_FEATURE_COUNT = 3

# Minimal NIST -> element mass fraction table for the materials commonly
# referenced by the bundled scenarios.  Add to this as scenarios grow; or
# extend the engine to emit the resolved element fractions in the scene
# manifest directly.
G4_MATERIAL_TO_MASS_FRACTIONS: Dict[str, Dict[str, float]] = {
    "G4_AIR":      {"N": 0.755, "O": 0.232, "C": 0.013},
    "G4_WATER":    {"H": 0.1119, "O": 0.8881},
    "G4_SILICON_DIOXIDE": {"Si": 0.4675, "O": 0.5325},
    "G4_C":        {"C": 1.0},
    "G4_Galactic": {"other": 1.0},
    # NB: there is no G4_SODIUM_CHLORIDE in the Geant4 NIST DB; NaI is the
    # bundled halide scintillator. The engine now emits element_mass_fractions
    # so this fallback table is only for legacy manifests.
    "G4_SODIUM_IODIDE": {"Na": 0.1534, "I": 0.8466},
}


@dataclass
class Sample:
    material_name: str
    composition_vector: List[float]  # length INPUT_FEATURE_COUNT
    targets: List[float]             # [n_mean, abs_len_mm, scat_len_mm]


def _encode_composition(mass_fractions: Dict[str, float], density: float) -> List[float]:
    out = [0.0] * INPUT_FEATURE_COUNT
    for symbol, fraction in mass_fractions.items():
        if symbol in COMPOSITION_ELEMENTS:
            idx = COMPOSITION_ELEMENTS.index(symbol)
        else:
            idx = COMPOSITION_ELEMENTS.index("other")
        out[idx] += max(0.0, float(fraction))
    # Normalize the element portion.
    elem_sum = sum(out[:-1])
    if elem_sum > 1.0:
        for i in range(len(out) - 1):
            out[i] /= elem_sum
    out[-1] = float(density)
    return out


def _resolve_material_mass_fractions(material_block: Dict, derived: Dict) -> Optional[Dict[str, float]]:
    """Best-effort mass-fraction recovery from a scene.materials[] entry.

    Strategy: if `material_block` lists components with G4 NIST refs, sum
    their tabulated fractions weighted by the declared component fraction.
    """
    fractions: Dict[str, float] = {}
    components = material_block.get("components") or []
    if not components:
        # No components — try to look up the material name directly.
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


def _load_anchors(path: Optional[Path]) -> Dict[str, float]:
    """Optional handbook refractive-index anchors {material_name: n}. When given,
    they override the extractor's n target so the surrogate learns the measured
    refraction the single global valence oscillator can't reach (validated
    held-out by scripts/validate_optics_surrogate.py). abs/scat stay extractor-
    derived. Anchors are training targets only; they never feed photon transport.
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


def collect_samples(scene_paths: List[Path],
                    anchors: Optional[Dict[str, float]] = None) -> List[Sample]:
    anchors = anchors or {}
    samples: List[Sample] = []
    seen_keys = set()
    for path in scene_paths:
        try:
            scene = json.loads(path.read_text())
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
            # Preferred: the engine now emits resolved per-element mass fractions
            # directly (any material, no lookup table needed).  Fall back to the
            # materials block / hard-coded table for older manifests.
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
            comp_vec = _encode_composition(mass_fractions, density)
            # Prefer a handbook anchor for n when available, else the extractor's
            # physics-derived n. abs/scat always come from the extractor.
            anchor_n = anchors.get(config_key.lower()) or anchors.get(material_name.lower())
            n_target = float(anchor_n) if anchor_n else float(
                derived.get("mean_refractive_index") or 1.0)
            targets = [
                n_target,
                float(derived.get("mean_absorption_length_mm") or 0.0),
                float(derived.get("mean_scatter_length_mm") or 0.0),
            ]
            samples.append(Sample(material_name, comp_vec, targets))
    return samples


class _SurrogateMLP(torch.nn.Module):
    def __init__(self, n_inputs: int, hidden: int = 32, n_outputs: int = 3):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(n_inputs, hidden),
            torch.nn.SiLU(),
            torch.nn.Linear(hidden, hidden),
            torch.nn.SiLU(),
            torch.nn.Linear(hidden, n_outputs),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def _target_transform(targets: torch.Tensor) -> torch.Tensor:
    # log-space for abs/scat lengths so the loss isn't dominated by 1e6 caps.
    out = targets.clone()
    out[:, 1] = torch.log1p(out[:, 1])
    out[:, 2] = torch.log1p(out[:, 2])
    return out


def _target_inverse(transformed: torch.Tensor) -> torch.Tensor:
    out = transformed.clone()
    out[:, 1] = torch.expm1(out[:, 1])
    out[:, 2] = torch.expm1(out[:, 2])
    return out


def train(samples: List[Sample], epochs: int, lr: float) -> _SurrogateMLP:
    if not samples:
        raise SystemExit(
            "no usable training samples; check that scene manifests contain "
            "derived_optics with materials whose composition can be resolved."
        )
    x = torch.tensor([s.composition_vector for s in samples], dtype=torch.float32)
    y = torch.tensor([s.targets for s in samples], dtype=torch.float32)
    y_t = _target_transform(y)
    model = _SurrogateMLP(INPUT_FEATURE_COUNT)
    optim = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()
    for epoch in range(epochs):
        optim.zero_grad()
        pred = model(x)
        loss = loss_fn(pred, y_t)
        loss.backward()
        optim.step()
        if (epoch + 1) % max(1, epochs // 10) == 0:
            print(f"  epoch {epoch + 1}/{epochs}  loss = {loss.item():.6f}")
    return model


def export_torchscript(model: _SurrogateMLP, out_path: Path) -> None:
    # The exported module wraps the MLP and reapplies the inverse transform so
    # the C++ side only sees (n, abs_len_mm, scat_len_mm) in natural units.
    class Wrapped(torch.nn.Module):
        def __init__(self, inner: _SurrogateMLP):
            super().__init__()
            self.inner = inner

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            transformed = self.inner(x)
            out = transformed.clone()
            out[:, 1] = torch.expm1(out[:, 1])
            out[:, 2] = torch.expm1(out[:, 2])
            return out

    wrapped = Wrapped(model)
    wrapped.eval()
    scripted = torch.jit.script(wrapped)
    scripted.save(str(out_path))


def write_manifest(samples: List[Sample], out_path: Path, model_path: Path) -> None:
    manifest = {
        "schema": "trech_optics_surrogate_v1",
        "model_path": str(model_path),
        "n_samples": len(samples),
        "input_feature_count": INPUT_FEATURE_COUNT,
        "input_features": COMPOSITION_ELEMENTS + ["density_gcm3"],
        "output_features": ["refractive_index", "absorption_length_mm", "scatter_length_mm"],
        "materials": sorted({s.material_name for s in samples}),
    }
    out_path.write_text(json.dumps(manifest, indent=2) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--scenes",
        nargs="+",
        required=True,
        help="One or more directories or scene.json files to harvest as training data.",
    )
    parser.add_argument("--out", default="optics_surrogate.pt")
    parser.add_argument("--manifest", default="optics_surrogate.manifest.json")
    parser.add_argument("--anchors", default=None,
                        help="handbook anchors JSON; overrides n target with "
                             "measured refraction (e.g. data/optics_handbook_anchors.json)")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--lr", type=float, default=1.0e-3)
    args = parser.parse_args(argv)

    scene_paths: List[Path] = []
    for raw in args.scenes:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"warning: path not found: {p}", file=sys.stderr)
            continue
        if p.is_file():
            scene_paths.append(p)
        else:
            scene_paths.extend(sorted(p.rglob("trech_viz_scene.json")))
    if not scene_paths:
        print("error: no scene manifests found", file=sys.stderr)
        return 2

    anchors = _load_anchors(Path(args.anchors)) if args.anchors else {}
    if anchors:
        print(f"loaded {len(anchors)} handbook n anchors from {args.anchors}")
    samples = collect_samples(scene_paths, anchors=anchors)
    print(f"collected {len(samples)} unique material samples from {len(scene_paths)} scenes")
    if not samples:
        return 2

    model = train(samples, epochs=args.epochs, lr=args.lr)
    out_path = Path(args.out).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_torchscript(model, out_path)
    write_manifest(samples, manifest_path, out_path)
    print(f"wrote {out_path}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
