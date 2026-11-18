"""Refit the glass-furnace operator family to measured refinement regimes."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from trech_torch.routing_domain import main as measure_routing
from trech_torch.train_surrogate import main as fit_response


ROOT = Path(__file__).resolve().parents[2]
TRAINED = ROOT / "data/glass_furnace_operators_trained"
MODELS = ("thermal_batch_solid", "thermal_melt", "thermal_glass", "chemistry_batch_solid", "chemistry_melt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit", nargs="+", required=True)
    parser.add_argument("--test", nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    dirs = args.fit + args.test
    if len({Path(path).resolve() for path in dirs}) != len(dirs):
        parser.error("fit and test must use distinct run directories")
    if args.out.exists():
        parser.error("checkpoint directory already exists")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as stage:
        checkpoint = Path(stage) / "checkpoint"
        checkpoint.mkdir()
        for name in MODELS:
            template = json.loads((TRAINED / f"{name}.json").read_text())
            output = checkpoint / f"{name}.json"
            family, kind = name.split("_", 1)
            tag = f"{family}_sample_{kind}"
            harvest = ["--runs", *args.fit, "--source", "hook_emits", "--tag", tag, "--expand", "samples"]
            manifest = output.with_suffix(".manifest.json")
            status = fit_response(harvest + [
                "--inputs", ",".join(template["input_features"]), "--outputs", ",".join(template["output_features"]),
                "--validation-runs", *args.test, "--linear", "--l2", "1e-10", "--seed", "20261118", "--measured", "false",
                "--teacher", "glass_furnace_operators reduced teacher through TRECH",
                "--out-json", str(output), "--manifest", str(manifest),
            ])
            if status or measure_routing(harvest + ["--features", "melt_fraction,glass_silica_fraction",
                                                   "--model", str(output)]):
                raise RuntimeError(f"Could not refit {name}")
            metadata = json.loads(manifest.read_text())
            metadata["model_json"] = str(args.out / output.name)
            metadata["model_size"]["model_file_bytes"] = output.stat().st_size
            metadata["model_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(metadata, indent=2) + "\n")
        checkpoint.rename(args.out)


if __name__ == "__main__":
    main()
