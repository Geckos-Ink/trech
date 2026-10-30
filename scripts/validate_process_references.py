#!/usr/bin/env python3
"""Real-engine conservation/replay guards, not experimental physics validation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trech", type=Path, default=Path("build/rel/trech"))
    parser.add_argument("--output", type=Path, default=Path("build/process_reference_validation"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    binary = args.trech.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Engine outputs are appendable JSONL. A rerun must never inherit records.
    output = Path(tempfile.mkdtemp(prefix="validation_", dir=output))
    results = {}

    def run(name, scenario, **parameters):
        target = output / name
        command = [str(binary), "run", str(root / "examples/scenarios" / Path(scenario).stem / scenario), "--output", str(target)]
        for key, value in parameters.items():
            command.extend(["--param", key + "=" + json.dumps(value)])
        with (output / (name + ".log")).open("w") as log:
            subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        scores = json.loads((target / "trech_scores.jsonl").read_text().splitlines()[-1])
        assert scores["hook_emit_dropped_count"] == 0, name + ": dropped emits"
        assert scores["hook_predict_count"] == 0, name + ": comparison unexpectedly performed inference"
        emits = [json.loads(line) for line in (target / "trech_hook_emits.jsonl").read_text().splitlines()]
        assert len(emits) == 2 * (scores["n_events"] + 1), name + ": missing/duplicate records"
        results[name] = {"events": scores["n_events"], "emits": len(emits), "dropped": 0, "inferences": 0}
        return [e["payload"] for e in emits if e["tag"] in ("crystallization_reference", "aerodynamics_reference")]

    salt = run("nacl", "nacl_dehydration_reference.js")
    run("nacl_replay", "nacl_dehydration_reference.js")
    wet = run("nacl_no_dehydration", "nacl_dehydration_reference.js", dehydration_fraction=0)
    assert salt[0]["inventory"]["salt_crystal"] == 0
    assert salt[-1]["inventory"]["salt_crystal"] == 64
    assert wet[-1]["inventory"]["salt_crystal"] == 0
    for frame in salt + wet:
        inv = frame["inventory"]
        assert inv["salt_dissolved"] + inv["salt_crystal"] == inv["sodium_total"] == inv["chlorine_total"] == 64
        assert inv["water_liquid"] + inv["water_vapour"] == inv["solvent_total"] == 256
        assert frame["geant4_material"]["available"]
        counts = frame["geant4_material"]["numberDensityPerCm3"]
        assert counts["Na"] == counts["Cl"] > 0

    aero = run("aerodynamics", "aerodynamics_reference.js")
    run("aerodynamics_replay", "aerodynamics_reference.js")
    uniform = run("aerodynamics_uniform", "aerodynamics_reference.js", body=False)
    slow = run("aerodynamics_slow", "aerodynamics_reference.js", mach=0.5)
    for frame in aero + uniform + slow:
        assert all(row[2] > 0 and row[5] > 0 and row[6] > 0 for row in frame["cells"])
        assert all(abs(r) < 1e-10 * max(1, abs(t)) for r, t in zip(frame["balance_residual"], frame["integral"]))
    assert uniform[0]["cells"] == uniform[-1]["cells"], "uniform open flow changed"
    assert max(row[6] for row in aero[-1]["cells"]) > max(row[6] for row in slow[-1]["cells"])
    for name in ("nacl", "aerodynamics"):
        for filename in ("trech_scores.jsonl", "trech_hook_emits.jsonl", "trech_viz_scene.json"):
            assert (output / name / filename).read_bytes() == (output / (name + "_replay") / filename).read_bytes(), (name, filename)
    report = {"scope": "implementation/replay checks only; independent physics accuracy remains unvalidated",
              "output": str(output), "runs": results}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
