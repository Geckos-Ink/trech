"""Train and replay domain specialists for CHNO photon interaction tables."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import torch

from build_particle_molecule_models import ELEMENTS, PROCESSES, ROOT, Z, material
from trech_torch.domain_specialists import main as train_specialists


OUTPUTS = [f"log_{process}_barn" for process in PROCESSES]


def scenario(binary, work, name, seed, energies, masses, model=None, strict=True):
    probe_names = ["probe_" + el for el in ELEMENTS]
    config = {
        "detector": {"worldSizeMm": 2, "worldMaterial": "G4_Galactic"},
        "beam": {"particle": "gamma", "energyMeV": .003, "direction": [0, 0, 1]},
        "run": {"nEvents": 1, "seed": seed, "threads": 1},
        "physics": {"list": "QBBC_LIV"},
        "determinism": {"mode": "strict" if strict else "predictive"},
        "materials": [material(probe, {el: 1}, masses) for probe, el in zip(probe_names, ELEMENTS)],
        "materialProbe": {"enable": True, "materials": probe_names, "interactions": {
            "particle": "gamma", "processes": PROCESSES, "energiesMeV": (energies / 1e6).tolist()}},
        "hooks": {"registered": ["onRunStart"], "maxEmitsPerCallback": 2, "maxEmitPayloadBytes": 262144},
    }
    if model:
        config["models"] = [{"name": "atomic_domains", "scale": "atomic", "path": str(model.resolve())}]
    script = work / f"{name}.js"
    script.write_text(
        "globalThis.TRECH_CONFIG=" + json.dumps(config) + ";\n"
        "const elements=" + json.dumps(Z) + ";\n"
        "const processes=" + json.dumps(PROCESSES) + ";\n"
        """
globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    const samples = [], inferred = [];
    for (const [el, atomic_number] of Object.entries(elements)) {
      const probe = ctx.materials["probe_" + el];
      for (const row of probe.interactions) {
        if (!row.available) throw new Error("Missing Geant4 interaction table");
        const facts = {atomic_number, log_energy_ev: Math.log(row.energy_mev * 1e6)};
        const labels = Object.fromEntries(processes.map(p => ["log_" + p + "_barn",
          Math.log(row.cross_sections_per_mm[p] * 1e25 / probe.numberDensityPerCm3[el])]));
        if (Object.values(labels).some(x => !Number.isFinite(x))) throw new Error("Invalid table cross section");
        samples.push({...facts, ...labels});
        if (TRECH_CONFIG.models) {
          const result = ctx.cascade(facts, ["atomic_domains"]);
          const trace = result && result.__cascade.trace[0];
          inferred.push(result && {predicted: processes.map(p => result["log_" + p + "_barn"]),
              measuredDomain: trace.domainMeasured, inDomain: trace.inDomain});
        }
      }
    }
    ctx.emit("atomic_labels", {samples});
    if (TRECH_CONFIG.models) ctx.emit("atomic_inference", {inferred});
  }
};
"""
    )
    run = work / name
    with (work / f"{name}.log").open("w") as log:
        subprocess.run([str(binary), "run", str(script), "--output", str(run)], cwd=ROOT,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    return run


def jsonl(name):
    return [json.loads(line) for line in name.read_text().splitlines()]


def replay(run, checkpoint, predictive):
    rows = {row["tag"]: row["payload"] for row in jsonl(run / "trech_hook_emits.jsonl")}
    inputs = np.array([[r["atomic_number"], r["log_energy_ev"]]
                       for r in rows["atomic_labels"]["samples"]], dtype=np.float32)
    inferred = rows["atomic_inference"]["inferred"]
    provenance = jsonl(run / "trech_provenance.jsonl")[-1]
    expected_count = len(inputs) if predictive else 0
    if provenance["hook_predict_count"] != expected_count or len(inferred) != len(inputs):
        raise RuntimeError("Unexpected inference count")
    if not predictive:
        if any(row is not None for row in inferred):
            raise RuntimeError("Strict replay produced model output")
        return {"inference_count": 0}
    model = torch.jit.load(str(checkpoint))
    with torch.no_grad():
        query = torch.from_numpy(inputs)
        expected = model(query).numpy()
        route = model.route(query).numpy()
        pooled = model.pooled(query.double()).float().numpy()
    actual = np.array([row["predicted"] for row in inferred])
    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6)
    if not all(row["measuredDomain"] for row in inferred):
        raise RuntimeError("LibTorch replay lost measured coverage metadata")
    return {"inference_count": expected_count, "route_counts": {
                str(label): int((route == label).sum()) for label in np.unique(route)},
            "rows_changed_from_pooled": int(np.any(abs(actual - pooled) > 1e-6, axis=1).sum()),
            "torchscript_max_absolute_parity_error": float(abs(actual - expected).max()),
            "out_of_domain": sum(not row["inDomain"] for row in inferred)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--epochs", default=2200, type=int)
    parser.add_argument("--width", default=24, type=int)
    args = parser.parse_args()
    work = args.out.resolve()
    work.mkdir(parents=True)
    binary = args.binary.resolve()
    masses = json.loads((ROOT / "data/particle_molecule/reference.json").read_text())["atomic_masses"]
    splits = {}
    # Interleaved, disjoint energy grids. Each run sees the same four element
    # identities. This measures table interpolation on those identities.
    grid = np.geomspace(1000., 30000., 8 * 48 + 1)
    for i, split in enumerate(("fit", "fit", "fit", "fit", "selection", "selection", "test", "test")):
        energies = grid[i::8]
        run = scenario(binary, work, f"{split}_{i}", 20261200 + i, energies, masses)
        splits.setdefault(split, []).append(str(run))
    checkpoint = work / "checkpoint"
    train_specialists([
        "--fit", *splits["fit"], "--selection", *splits["selection"], "--test", *splits["test"],
        "--inputs", "atomic_number,log_energy_ev", "--outputs", ",".join(OUTPUTS),
        "--routing-features", "atomic_number", "--tag", "atomic_labels", "--expand", "samples",
        "--scale", "atomic", "--epochs", str(args.epochs), "--width", str(args.width),
        "--out", str(checkpoint),
    ])
    model = checkpoint / "response.pt"
    report = {}
    for name, strict in (("predictive", False), ("strict", True)):
        # Include extrapolation and in-range inputs in native replay.
        energies = np.r_[500., grid[6::16], 35000.]
        run = scenario(binary, work, name, 20261300, energies, masses, model, strict)
        report[name] = replay(run, model, not strict)
    report["weights_sha256"] = hashlib.sha256(model.read_bytes()).hexdigest()
    (work / "replay.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
