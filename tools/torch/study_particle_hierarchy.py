"""Fit a CHNO atom → element group → Geant4 photon transport observer.

Lower features come from the frozen, table-trained atomic model. Each element
group learns cross sections from separate Geant4 table probes. The observer is
trained end to end on independently transported photon events.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from build_particle_molecule_models import (
    ELEMENTS, PROCESSES, ROOT, Z, atom_features, labels, material, predict, run_probe,
)
from build_particle_observer_models import OUTPUTS, arrays
from study_particle_observer import composition_key, grade, load_rows
from trech_torch.train_surrogate import calibration_interval
from trech_torch import hierarchy


BASE = [f"{process}_times_areal_density" for process in PROCESSES]
GROUP = [f"group_{process}_times_areal_density" for process in PROCESSES]
CONTEXT = ["log_molecule_areal_density_barn_inv", "photon_energy_kev"]
PLAN = hierarchy.load_plan({
    "base_features": BASE,
    "levels": [
        {"name": "particle_element", "scale": "nano", "grouping": "explicit", "capacity": 16,
         "member_features": ["present", *BASE], "outputs": GROUP, "loss_weight": 1.0,
         "network": {"phi": [12], "rho": [24], "pool": "sum"}},
        {"name": "particle_volume", "scale": "meso", "grouping": "all", "capacity": 4,
         "member_features": ["present", *GROUP], "context": CONTEXT, "outputs": OUTPUTS,
         "output_transforms": ["sigmoid"] * len(OUTPUTS),
         "network": {"phi": [24], "rho": [48, 32], "pool": "sum"}},
    ],
})


def probe(binary, work, rows):
    """Collect independent table labels at the MC runs' exact energies."""
    masses = json.loads((ROOT / "data/particle_molecule/reference.json").read_text())["atomic_masses"]
    materials = [material(el, {el: 1}, masses) for el in ELEMENTS]
    energies = np.array(sorted({r["energy_kev"] * 1000 for r in rows}))
    tables, sources = {}, []
    for start in range(0, len(energies), 64):
        panel = energies[start:start + 64]
        probes, source = run_probe(binary, work, f"panel_{start:05d}", materials, panel)
        by_el = {el: labels(probes[el], {el: 1}, panel) for el in ELEMENTS}
        for i, energy in enumerate(panel):
            tables[energy] = {el: by_el[el][i] for el in ELEMENTS}
        sources.append(source)
    return tables, sources


def make_samples(rows, tables=None):
    path = ROOT / "data/particle_molecule/atomic_response.json"
    atomic = json.loads(path.read_text())
    samples = []
    for row in rows:
        density, energy = row["inputs"][-2:]
        observed = np.array([row["labels"][name] for name in OUTPUTS])
        group_ids, atoms, group_labels = [], [], {}
        for el, count in sorted(row["counts"].items()):
            response = predict(atomic, atom_features(el, energy * 1000))
            atoms.extend([response * density] * count)
            group_ids.extend([Z[el]] * count)
            if tables is not None:
                group_labels[str(Z[el])] = dict(zip(GROUP, tables[energy * 1000][el] * count * density))
        samples.append({
            "schema": hierarchy.SAMPLE_SCHEMA, "run": row["id"],
            "features": dict(zip(BASE, np.asarray(atoms).T.tolist())),
            "groups": {"particle_element": group_ids},
            "context": dict(zip(CONTEXT, [float(np.log(density)), energy])),
            "targets": {"particle_element": group_labels, "particle_volume": {"all": dict(zip(OUTPUTS, observed))}},
        })
    return samples


def predictions(rows, models):
    result = [hierarchy.lift_np(sample, PLAN, models) for sample in make_samples(rows)]
    if not all(layers[-1]["valid"].tolist() == [True] for layers in result):
        raise RuntimeError("Hierarchy failed to supply a whole-system prediction")
    return np.stack([layers[-1]["features"][0, :len(OUTPUTS)] for layers in result])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--fit", type=Path, nargs="+")
    parser.add_argument("--selection", type=Path, nargs="+")
    parser.add_argument("--test", type=Path, nargs="+")
    parser.add_argument("--calibration", type=Path, nargs="+")
    parser.add_argument("--epochs", type=int, default=2600)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    if args.fit or args.selection:
        if not args.fit or not args.selection or not args.binary or args.test or args.calibration:
            parser.error("fit requires --binary, --fit and --selection; open test in a later invocation")
        fitting, selection = load_rows(args.fit), load_rows(args.selection)
        load_rows(args.fit + args.selection)
        fit_compositions = {composition_key(r) for r in fitting}
        selection_compositions = {composition_key(r) for r in selection}
        if fit_compositions & selection_compositions:
            parser.error("fit and selection compositions overlap")
        args.out.mkdir(parents=True)
        tables, sources = probe(args.binary.resolve(), args.out / "probes", fitting + selection)
        train_samples, selection_samples = make_samples(fitting, tables), make_samples(selection, tables)
        models, report = hierarchy.train(PLAN, train_samples, selection_samples=selection_samples,
                                         epochs=args.epochs, seed=20261118)
        # Selection loss chooses the stopping point. A later test measures the raw
        # fractions. Leave carried held-out accuracy empty until a separate test.
        hierarchy.finalize(PLAN, models, train_samples, [],
                           note={"geant4_trained": True, "measured": False, "maturity": "experimental",
                                 "mc_sampled": True, "label_source": "Geant4 atomic tables and MC event tallies"})
        paths = hierarchy.write_models(models, args.out, PLAN)
        report.update(plan=PLAN, fit_ids=[r["id"] for r in fitting], selection_ids=[r["id"] for r in selection],
                      fit_compositions=sorted(fit_compositions), selection_compositions=sorted(selection_compositions),
                      label_probes=sources, selection=grade(selection, predictions(selection, models)),
                      frozen_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
        (args.out / "manifest.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(json.dumps(report["selection"], indent=2), flush=True)
    elif args.test or args.calibration:
        manifest = json.loads((args.out / "manifest.json").read_text())
        models = []
        for name, digest in manifest["frozen_sha256"].items():
            data = (args.out / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"Changed checkpoint {name}")
            models.append(json.loads(data))
        if args.test and args.calibration:
            parser.error("freeze the calibration interval before opening the test panel")
        prior = set(manifest["fit_compositions"] + manifest["selection_compositions"])
        path = args.out / "calibration_report.json"
        if args.calibration:
            if path.exists() or (args.out / "test_report.json").exists():
                parser.error("calibration is already frozen or the test panel has been opened")
            rows = load_rows(args.calibration)
            used = {composition_key(r) for r in rows}
            if prior & used:
                parser.error("calibration compositions overlap earlier data")
            interval = calibration_interval(arrays(rows)[1], predictions(rows, models),
                                            OUTPUTS, .9, [r["id"] for r in rows])
            interval["note"] = "Residual envelope on a fixed independent set of simulation conditions"
            report = {"interval": interval, "compositions": sorted(used)}
        else:
            rows = load_rows(args.test)
            calibration = json.loads(path.read_text()) if path.exists() else None
            if calibration:
                prior.update(calibration["compositions"])
            if prior & {composition_key(r) for r in rows}:
                parser.error("test compositions overlap earlier data")
            predicted = predictions(rows, models)
            report = {"accuracy": grade(rows, predicted)}
            if calibration:
                widths = [calibration["interval"]["half_width"][name] for name in OUTPUTS]
                covered = abs(predicted - arrays(rows)[1]) <= np.asarray(widths)
                report["empirical_interval_coverage"] = dict(zip(OUTPUTS, covered.mean(0).tolist()))
            if args.binary:
                tables, sources = probe(args.binary.resolve(), args.out / "test_probes", rows)
                held, counts = hierarchy.chained_metrics(PLAN, models, make_samples(rows, tables))
                report["nano"] = {"metrics": held[0]["metrics"], "n": held[0]["n"]}
                report["groups"] = counts
                report["test_probe_sources"] = sources
            path = args.out / "test_report.json"
        path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(json.dumps(report, indent=2))
    else:
        parser.error("provide fit/selection inputs or a test panel")


if __name__ == "__main__":
    main()
