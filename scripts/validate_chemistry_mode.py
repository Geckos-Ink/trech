#!/usr/bin/env python3
"""Real Geant4 chemistry-workspace gates. No chemical stability/rate claim."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/rel/trech")
    parser.add_argument("--output", type=Path, default=ROOT / "build/chemistry_validation")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    isotope = {"atoms": [{"element": "H", "massNumber": 1, "position": [0, 0, 0]},
                          {"element": "H", "massNumber": 2, "position": [1, 0, 0]}],
               "bonds": [[0, 1, 1]], "charge": 0}
    reports = []
    mixed = {"atoms": [isotope["atoms"][1], {"element": "H", "position": [0, 0, 0]}],
             "bonds": [[0, 1, 1]], "charge": 0}
    for label, structure in (("natural", None), ("isotope", isotope), ("mixed", mixed)):
        for mode in ("predictive", "strict"):
            out = args.output / f"{label}_{mode}"
            command = [str(args.binary.resolve()), "run", str(ROOT / "examples/experiments/chemistry_mode.js"),
                       "--output", str(out), "--param", f'mode="{mode}"', "--param", "events=2"]
            if structure:
                command.extend(["--param", "structure_json=" + json.dumps(json.dumps(structure))])
            previous = None
            for repeat in range(2):
                if out.exists():
                    shutil.rmtree(out)
                result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                (args.output / f"{label}_{mode}_{repeat}.log").write_text(result.stdout)
                assert result.returncode == 0, f"{label}/{mode} failed; see run log"
                files = {name: (out / name).read_bytes() for name in (
                    "trech_scores.jsonl", "trech_provenance.jsonl", "trech_hook_emits.jsonl", "trech_viz_scene.json")}
                if previous is not None:
                    assert files == previous, f"{label}/{mode} changed on identical rerun"
                previous = files
            score = rows(out / "trech_scores.jsonl")[-1]
            emits = rows(out / "trech_hook_emits.jsonl")
            state = next(e["payload"] for e in emits if e["tag"] == "chemistry_state")
            frame = next(e["payload"] for e in emits if e["tag"] == "material_frame")
            expected = 10 if label == "natural" and mode == "predictive" else 0
            assert score["hook_predict_count"] == expected
            assert score["hook_emit_dropped_count"] == 0
            assert frame["physical_time_s"] == 0 and frame["length_unit"] == "angstrom"
            assert frame["positions"] == [[round(v, 4) for v in a["position"]] for a in state["structure"]["atoms"]]
            assert not state["capabilities"]["stability"]["available"]
            assert not state["capabilities"]["polarization"]["available"]
            if label != "natural":
                assert state["particle_response"] is None
                assert [a["neutrons"] for a in state["atoms"]] == ([0, 1] if label == "isotope" else [1, None])
                if label == "mixed":
                    assert 1 < state["atoms"][1]["atomic_mass_amu"] < 1.02
                probe = state["geant4_material"]
                assert abs(probe["elements"][0]["atoms_per_cm3"] / probe["elements"][1]["atoms_per_cm3"] - 1) < 1e-12
                assert abs(probe["numberDensityPerCm3"]["H"] / probe["total_atoms_per_cm3"] - 1) < 1e-12
            elif mode == "strict":
                assert state["particle_response"] is None
            else:
                response = state["particle_response"]
                probe = state["geant4_material"]
                relative_errors = []
                for i, process in enumerate(("phot", "compt", "Rayl")):
                    truth = probe["interactions"][0]["cross_sections_per_mm"][process] * 1e25 / probe["total_atoms_per_cm3"] * len(state["atoms"])
                    relative_errors.append(abs(response["sigma_barn"][i] / truth - 1))
                assert max(relative_errors) < .03, relative_errors
            reports.append({"structure": label, "mode": mode, "predictions": expected,
                            "byte_identical": True, "scope": "material response and authoring, not chemical accuracy"})
            print("PASS", label, mode, flush=True)
    (args.output / "report.json").write_text(json.dumps(reports, indent=2) + "\n")
    print(f"{len(reports) * 2} Geant4 runs passed; chemistry accuracy remains unclaimed.")


if __name__ == "__main__":
    main()
