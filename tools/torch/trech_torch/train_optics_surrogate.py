"""Train the optics surrogate from TRECH scene manifests.

Dataset construction
--------------------

We scan one or more directories of `trech_viz_scene.json` files (output by
`trech run` with `optics.derive.enable: true`) and extract, for each material
that appears with a usable `derived_optics` block:

    input  :: [mass_fraction(H), mass_fraction(C), ..., mass_fraction(other), density_gcm3]
    output :: [mean_refractive_index, mean_absorption_length_mm, mean_scatter_length_mm]

Harvesting lives in `trech_torch.dataset` (shared with the stratifier trainer
and the Geant4 experiment planner); the element list matches
`OpticsSurrogate::kCompositionElements` in the C++ header — keep them in sync.
With `--anchors`, handbook refractive indices override the extractor's n
target so the surrogate learns the measured residual (the anti-degeneration
training workstream); abs/scat always stay extractor-derived.

Training
--------

Small MLP with two hidden layers (TorchScript-compatible, no control-flow
surprises).  Inputs are standardised (the scaler is baked into the exported
module so the C++ engine feeds raw composition vectors); abs/scat targets are
log-scaled so the loss isn't dominated by 1e6-mm caps.  Training is
deterministic under `--seed` (CPU, fixed init + full-batch Adam).

Validation
----------

`--validate loo` (default) runs a leave-one-out pass: each material is
predicted by a model trained on every *other* material — the same
generalisation gate as `scripts/validate_optics_surrogate.py`.  With anchors,
the manifest records whether the held-out surrogate beats the physics
extractor (the ROADMAP promotion signal); without anchors it measures how
well the surrogate caches the extractor.

Output
------

Two files:

- `--out` (default `optics_surrogate.pt`): TorchScript module taking a
  `[1, kInputFeatureCount]` float tensor of RAW features and returning a
  `[1, 3]` float tensor `(n, abs_len_mm, scat_len_mm)` in natural units.
- `--manifest` (default `optics_surrogate.manifest.json`): training metadata
  (dataset size, element list, model size in parameters and bytes, seed,
  held-out validation metrics).  The engine doesn't read this file — it's for
  humans + the validation suite.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    import torch
except ImportError as err:  # pragma: no cover - error path
    raise SystemExit(
        "torch is required to train the optics surrogate; "
        "install via `pip install torch`"
    ) from err

from .dataset import (
    COMPOSITION_ELEMENTS,
    INPUT_FEATURE_COUNT,
    OpticsSample,
    find_scene_manifests,
    harvest_optics_samples,
    load_anchors,
)

OUTPUT_FEATURE_COUNT = 3

# Backwards-compatible aliases (older callers imported these from here).
Sample = OpticsSample
collect_samples = harvest_optics_samples


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


def _fit_scaler(x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    mean = x.mean(dim=0)
    std = x.std(dim=0, unbiased=False)
    std = torch.where(std < 1e-9, torch.ones_like(std), std)
    return mean, std


def train(samples: List[OpticsSample], epochs: int, lr: float,
          seed: int = 1234, hidden: int = 32, quiet: bool = False,
          ) -> tuple[_SurrogateMLP, torch.Tensor, torch.Tensor]:
    """Fit the MLP on standardised inputs; returns (model, mean, std)."""
    if not samples:
        raise SystemExit(
            "no usable training samples; check that scene manifests contain "
            "derived_optics with materials whose composition can be resolved."
        )
    torch.manual_seed(seed)
    x = torch.tensor([s.composition_vector for s in samples], dtype=torch.float32)
    y = torch.tensor([s.targets for s in samples], dtype=torch.float32)
    mean, std = _fit_scaler(x)
    xs = (x - mean) / std
    y_t = _target_transform(y)
    model = _SurrogateMLP(INPUT_FEATURE_COUNT, hidden=hidden)
    optim = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()
    for epoch in range(epochs):
        optim.zero_grad()
        pred = model(xs)
        loss = loss_fn(pred, y_t)
        loss.backward()
        optim.step()
        if not quiet and (epoch + 1) % max(1, epochs // 10) == 0:
            print(f"  epoch {epoch + 1}/{epochs}  loss = {loss.item():.6f}")
    return model, mean, std


class _WrappedSurrogate(torch.nn.Module):
    """Deployable module: standardises raw inputs and re-applies the inverse
    target transform so the C++ side only sees natural units."""

    def __init__(self, inner: _SurrogateMLP, mean: torch.Tensor,
                 std: torch.Tensor):
        super().__init__()
        self.inner = inner
        self.input_mean = torch.nn.Parameter(mean.clone(), requires_grad=False)
        self.input_std = torch.nn.Parameter(std.clone(), requires_grad=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        xs = (x - self.input_mean) / self.input_std
        transformed = self.inner(xs)
        out = transformed.clone()
        out[:, 1] = torch.expm1(out[:, 1])
        out[:, 2] = torch.expm1(out[:, 2])
        return out


def predict_one(model: _SurrogateMLP, mean: torch.Tensor, std: torch.Tensor,
                composition: List[float]) -> List[float]:
    with torch.no_grad():
        x = torch.tensor([composition], dtype=torch.float32)
        xs = (x - mean) / std
        pred = model(xs)
        out = pred.clone()
        out[:, 1] = torch.expm1(out[:, 1])
        out[:, 2] = torch.expm1(out[:, 2])
        return [float(v) for v in out[0]]


def leave_one_out(samples: List[OpticsSample], epochs: int, lr: float,
                  seed: int, hidden: int) -> dict:
    """Held-out generalisation gate: retrain without each material in turn.

    Returns per-material rows + aggregate MAEs.  When anchors set the target,
    `mae_extractor` measures the physics extractor against the same target so
    the manifest can record the ROADMAP promotion signal
    (`surrogate_improves_over_extractor`).
    """
    rows: List[dict] = []
    for i, held_out in enumerate(samples):
        rest = samples[:i] + samples[i + 1:]
        model, mean, std = train(rest, epochs=epochs, lr=lr, seed=seed,
                                 hidden=hidden, quiet=True)
        pred = predict_one(model, mean, std, held_out.composition_vector)
        rows.append({
            "material": held_out.material_name,
            "target_n": held_out.targets[0],
            "extractor_n": held_out.extractor_n,
            "surrogate_n_loo": pred[0],
            "err_surrogate": pred[0] - held_out.targets[0],
            "err_extractor": held_out.extractor_n - held_out.targets[0],
            "anchored": held_out.anchored,
        })
    mae_sur = sum(abs(r["err_surrogate"]) for r in rows) / len(rows)
    mae_ext = sum(abs(r["err_extractor"]) for r in rows) / len(rows)
    anchored = any(r["anchored"] for r in rows)
    return {
        "method": "leave_one_out",
        "rows": rows,
        "mae_surrogate_loo": mae_sur,
        "mae_extractor": mae_ext,
        "anchored_targets": anchored,
        # Only meaningful vs handbook anchors; without them the extractor's
        # "error" against its own output is zero by construction.
        "surrogate_improves_over_extractor": bool(anchored
                                                  and mae_sur < mae_ext),
    }


def export_torchscript(model: _SurrogateMLP, mean: torch.Tensor,
                       std: torch.Tensor, out_path: Path) -> None:
    wrapped = _WrappedSurrogate(model, mean, std)
    wrapped.eval()
    scripted = torch.jit.script(wrapped)
    scripted.save(str(out_path))


def write_manifest(samples: List[OpticsSample], out_path: Path,
                   model_path: Path, args: argparse.Namespace,
                   model: _SurrogateMLP,
                   validation: Optional[dict]) -> None:
    parameter_count = sum(p.numel() for p in model.parameters())
    manifest = {
        "schema": "trech_optics_surrogate_v2",
        "model_path": str(model_path),
        "n_samples": len(samples),
        "input_feature_count": INPUT_FEATURE_COUNT,
        "input_features": COMPOSITION_ELEMENTS + ["density_gcm3"],
        "output_features": ["refractive_index", "absorption_length_mm",
                            "scatter_length_mm"],
        "materials": sorted({s.material_name for s in samples}),
        "anchored_materials": sorted({s.material_name for s in samples
                                      if s.anchored}),
        "training": {
            "seed": args.seed,
            "epochs": args.epochs,
            "lr": args.lr,
            "hidden": args.hidden,
            "anchors": args.anchors or None,
            "input_standardization": "baked into exported module",
        },
        "model_size": {
            "parameter_count": int(parameter_count),
            "model_file_bytes": (model_path.stat().st_size
                                 if model_path.exists() else 0),
        },
        "validation": validation,
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
    parser.add_argument("--seed", type=int, default=1234,
                        help="deterministic training seed")
    parser.add_argument("--hidden", type=int, default=32,
                        help="hidden layer width")
    parser.add_argument("--validate", choices=["loo", "none"], default="loo",
                        help="held-out validation mode recorded in the manifest")
    args = parser.parse_args(argv)

    scene_paths = find_scene_manifests(args.scenes)
    if not scene_paths:
        print("error: no scene manifests found", file=sys.stderr)
        return 2

    anchors: Dict[str, float] = (load_anchors(Path(args.anchors))
                                 if args.anchors else {})
    if anchors:
        print(f"loaded {len(anchors)} handbook n anchors from {args.anchors}")
    samples = harvest_optics_samples(scene_paths, anchors=anchors)
    print(f"collected {len(samples)} unique material samples from "
          f"{len(scene_paths)} scenes")
    if not samples:
        return 2

    validation: Optional[dict] = None
    if args.validate == "loo" and len(samples) >= 4:
        print(f"leave-one-out validation over {len(samples)} materials ...")
        validation = leave_one_out(samples, epochs=args.epochs, lr=args.lr,
                                   seed=args.seed, hidden=args.hidden)
        print(f"  LOO MAE(n): surrogate {validation['mae_surrogate_loo']:.4f}"
              + (f"  extractor {validation['mae_extractor']:.4f}"
                 if validation["anchored_targets"] else ""))
    elif args.validate == "loo":
        print(f"warning: only {len(samples)} samples; skipping LOO validation",
              file=sys.stderr)

    model, mean, std = train(samples, epochs=args.epochs, lr=args.lr,
                             seed=args.seed, hidden=args.hidden)
    out_path = Path(args.out).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_torchscript(model, mean, std, out_path)
    write_manifest(samples, manifest_path, out_path, args, model, validation)
    print(f"wrote {out_path}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
