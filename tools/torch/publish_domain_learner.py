"""Publish a frozen learner from a study_domain_learning.py campaign into data/.

Copies ``learned.json`` (no reservoir rows) to ``--out`` and writes a build record beside it:
the campaign's operating points, run directories, the engine budget the learner was built
under, the held-out summary and the SHA-256 of the published state. It never retrains.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True, help="study_domain_learning.py --out directory")
    parser.add_argument("--out", type=Path, required=True, help="published state, e.g. data/<family>/thermal.json")
    parser.add_argument("--model", default="learned", choices=["learned", "specialists"])
    args = parser.parse_args(argv)
    report = json.loads((args.campaign / "report.json").read_text())
    source = args.campaign / ("learned.json" if args.model == "learned" else "learned_specialists.json")
    state = json.loads(source.read_text())
    if any("rows" in leaf for leaf in state["leaves"]):
        raise SystemExit("refusing to publish a state with reservoir rows")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    root = str(Path(__file__).resolve().parents[2]) + "/"
    args.out.write_text(json.dumps(state, separators=(",", ":")).replace(root, "") + "\n")
    held_out = []
    for entry in report.get("held_out", []):
        item = entry.get(args.model) or {}
        held_out.append({
            report["operating_point"]: entry[report["operating_point"]],
            "evaluate": (item.get("evaluate") or {}).get("online"),
            "deploy_shadow": (item.get("deploy") or {}).get("shadow"),
            "observers": item.get("observers"),
            "numpy_parity": item.get("numpy_parity") or item.get("evaluate_parity"),
        })
    record = {
        "schema": "trech_domain_learner_build_v1",
        "state": str(args.out),
        "state_sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
        "scenario": report.get("scenario"),
        "operating_point": report.get("operating_point"),
        "train": report.get("train"),
        "test": report.get("test"),
        "params": report.get("params"),
        "budget": report.get("budget"),
        "domains": len(state["leaves"]),
        "calls": state["calls"],
        "lineage_entries": len(state["lineage"]),
        "runs": report.get("runs"),
        "held_out": held_out,
        "command": ("tools/torch/study_domain_learning.py --scenario {s} --train {tr} --test {te}"
                    .format(s=report.get("scenario"), tr=" ".join(map(str, report.get("train", []))),
                            te=" ".join(map(str, report.get("test", []))))),
        "note": ("Learned online by ctx.learnDomains from the scenario operator's own pre-bound rates; "
                 "measured:false. Capacity depends on the recorded budget."),
    }
    record_path = args.out.with_name(args.out.stem + ".build_record.json")
    # Repository-relative paths only.
    record_path.write_text(json.dumps(record, indent=2).replace(root, "") + "\n")
    print(json.dumps({"state": str(args.out), "record": str(record_path), "sha256": record["state_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
