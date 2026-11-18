"""Fit a photon volume observer in two feature spaces on paired Geant4 runs."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

from build_particle_observer_models import ROOT, INPUTS, OUTPUTS, arrays, fit, metrics, model_predict
from trech_torch.torchscript_io import write_torchscript_io
from trech_torch.train_surrogate import calibration_interval, input_domain


class Observer(nn.Module):
    def __init__(self, net, scalers, coupled):
        super().__init__()
        self.net = net
        self.coupled = coupled
        for name, data in zip(("xm", "xs", "ym", "ys"), scalers):
            self.register_buffer(name, torch.from_numpy(data))

    def forward(self, raw):
        x = raw.double()
        if self.coupled:
            x = torch.cat((torch.log1p(x[:, :3] * x[:, 3:4]), torch.log(x[:, 3:])), dim=1)
        encoded = self.net((x - self.xm) / self.xs) * self.ys + self.ym
        return torch.where(torch.isfinite(encoded), torch.sigmoid(encoded), encoded).float()


def load_rows(paths):
    rows = []
    for path in paths:
        batch = json.loads(path.read_text())
        rows.extend(batch["rows"] if isinstance(batch, dict) else batch)
    for key in ("id", "script_sha256"):
        values = [r["id"] if key == "id" else r["source"][key] for r in rows]
        if len(set(values)) != len(values):
            raise ValueError(f"Repeated case {key}")
    return rows


def composition_key(row):
    return json.dumps(row["counts"], sort_keys=True)


def transformed(rows):
    x = arrays(rows)[0]
    values = np.column_stack((np.log1p(x[:, :3] * x[:, 3:4]), np.log(x[:, 3:])))
    return [dict(r, inputs=v.tolist()) for r, v in zip(rows, values)]


def model_output(nn_model, x):
    with torch.no_grad():
        return nn_model(torch.from_numpy(x).float()).numpy()


def grade(rows, predicted):
    truth = arrays(rows)[1]
    result = metrics(predicted, truth)
    gaps = abs(predicted - truth)
    limits = np.array([.03, .04])
    n = np.asarray([r["events"] for r in rows])
    uncollided_se = np.sqrt(truth[:, 0] * (1 - truth[:, 0]) / n)
    deposited_se = np.array([r["labels"]["deposited_energy_fraction_stddev"] for r in rows]) / np.sqrt(n)
    limits = np.maximum(limits, 5 * np.column_stack((uncollided_se, deposited_se)))
    passed = (gaps <= limits).all(1)
    result.update(max_abs=dict(zip(OUTPUTS, gaps.max(0).tolist())),
                  passed_cases=int(passed.sum()), failed_case_ids=[r["id"] for r, ok in zip(rows, passed) if not ok])
    return result


def coverage_flags(meta, x):
    domain = meta["input_domain"]
    z = (x - meta["input_mean"]) / meta["input_std"]
    lo, hi = np.array(domain["input_min"]), np.array(domain["input_max"])
    bins = domain["occupancy"]["bins"]
    index = ((x - lo) / np.where(hi > lo, hi - lo, 1) * bins).astype(int).clip(0, bins - 1)
    per_axis_starved = ((lo <= x) & (x <= hi) & (hi > lo)
                        & (np.asarray(domain["occupancy"]["counts"])[np.arange(x.shape[1]), index] == 0))
    joint = domain["joint"]
    distance = np.linalg.norm(z[:, None, :] - np.asarray(joint["centers"])[None, :, :], axis=-1).min(1)
    out = (abs(z) > np.array(domain["standardized_radius"]) + 1e-9).any(1)
    starved_joint = distance > joint["radius"] * (1 + 1e-9) + 1e-12
    return z, distance, out, per_axis_starved, starved_joint


def coverage(meta, rows):
    _, _, out, starved, starved_joint = coverage_flags(meta, arrays(rows)[0])
    axes = starved.any(1)
    return {"out_of_domain": int(out.sum()), "per_feature_starved": int(axes.sum()),
            "jointly_starved": int(starved_joint.sum()), "supported": int((~(out | axes | starved_joint)).sum())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fit", type=Path, nargs="+")
    parser.add_argument("--selection", type=Path, nargs="+")
    parser.add_argument("--test", type=Path, nargs="+")
    parser.add_argument("--calibration", type=Path, nargs="+")
    parser.add_argument("--compare", type=Path, nargs="*", default=[])
    parser.add_argument("--epochs", type=int, default=28000)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    path = args.out / "observer.pt"
    manifest = args.out / "manifest.json"
    baseline_paths = [ROOT / "data/particle_observer/observer_response.json", *args.compare]
    torch.set_num_threads(1)
    if args.fit or args.selection:
        if not args.fit or not args.selection or args.test or args.calibration:
            parser.error("provide fitting and selection rows before opening any test rows")
        load_rows(args.fit + args.selection)
        fitting, selection = load_rows(args.fit), load_rows(args.selection)
        if {composition_key(r) for r in fitting} & {composition_key(r) for r in selection}:
            parser.error("fitting and selection compositions overlap")
        args.out.mkdir(parents=True)
        candidates, details = {}, {}
        for key, coupled in (("raw", False), ("coupled", True)):
            net, scalers, epoch, loss = fit(transformed(fitting) if coupled else fitting,
                                            transformed(selection) if coupled else selection,
                                            epochs=args.epochs, hidden=args.width)
            model = Observer(net, scalers, coupled).eval()
            candidates[key] = model
            details[key] = grade(selection, model_output(model, arrays(selection)[0]))
            details[key].update(selected_epoch=epoch, selected_mse=loss)
        winner = min(candidates, key=lambda k: (len(details[k]["failed_case_ids"]),
                                                sum(details[k]["rmse"].values())))
        torch.jit.script(candidates[winner]).save(str(path))
        x = arrays(fitting)[0]
        xm, xs = x.mean(0), x.std(0)
        xs[xs < 1e-12] = 1
        report = {"schema": "trech_particle_observer_study_v1",
                  "note": {"geant4_trained": True, "mc_sampled": True, "measured": False,
                           "maturity": "experimental"},
                  "input_features": INPUTS, "output_features": OUTPUTS, "trained_scale_bands": ["meso"],
                  "input_mean": xm.tolist(), "input_std": xs.tolist(),
                  "input_domain": input_domain(x, (xm, xs, None, None), joint_centers=48, joint_quantile=1),
                  "fit_rows": len(fitting), "selection_rows": len(selection), "winner": winner,
                  "fit_materials": sorted({r["material"] for r in fitting}),
                  "selection_materials": sorted({r["material"] for r in selection}),
                  "fit_compositions": sorted({composition_key(r) for r in fitting}),
                  "selection_compositions": sorted({composition_key(r) for r in selection}),
                  "selection": details,
                  "reserved_test_exclusions": [r["source"]["script_sha256"] for r in fitting + selection],
                  "frozen_model_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        manifest.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        write_torchscript_io(path, manifest)
        rows = selection
        data = report
        evaluation = "selection_report.json"
    elif args.test or args.calibration:
        data = json.loads(manifest.read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest() != data["frozen_model_sha256"]:
            raise RuntimeError("Model changed after selection")
        calibration = args.calibration is not None
        if args.test and args.calibration:
            parser.error("freeze the calibration interval before opening the test panel")
        rows = load_rows(args.calibration if calibration else args.test)
        exclusions = set(data["reserved_test_exclusions"])
        compositions = set(data["fit_compositions"] + data["selection_compositions"])
        if not calibration and "calibration_compositions" in data:
            compositions.update(data["calibration_compositions"])
        if compositions & {composition_key(r) for r in rows} or exclusions & {r["source"]["script_sha256"] for r in rows}:
            parser.error("evaluation overlaps earlier data")
        if calibration:
            if "prediction_interval" in data or (args.out / "test_report.json").exists():
                parser.error("calibration is already frozen or the test panel has been opened")
            x, y = arrays(rows)
            predicted = model_output(torch.jit.load(str(path)), x)
            block = calibration_interval(y, predicted, OUTPUTS, .9, [r["id"] for r in rows])
            block["note"] = "Residual envelope on a fixed independent set of simulation conditions"
            data["prediction_interval"] = block
            data["calibration_compositions"] = sorted({composition_key(r) for r in rows})
            manifest.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
            write_torchscript_io(path, manifest)
            print(json.dumps(block, indent=2), flush=True)
            return
        evaluation = "test_report.json"
    else:
        parser.error("provide fitting and selection data or independent test rows")

    x = arrays(rows)[0]
    report = {}
    for i, other in enumerate(baseline_paths):
        model = json.loads(other.read_text())
        report["committed" if i == 0 else str(other)] = {
            "accuracy": grade(rows, model_predict(model, x)), "coverage": coverage(model, rows)}
    predicted = model_output(torch.jit.load(str(path)), x)
    report["candidate"] = {"accuracy": grade(rows, predicted), "coverage": coverage(data, rows)}
    if evaluation == "test_report.json" and "prediction_interval" in data:
        widths = [data["prediction_interval"]["half_width"][name] for name in OUTPUTS]
        covered = abs(predicted - arrays(rows)[1]) <= np.asarray(widths)
        report["candidate"]["empirical_interval_coverage"] = dict(zip(OUTPUTS, covered.mean(0).tolist()))
    (args.out / evaluation).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
