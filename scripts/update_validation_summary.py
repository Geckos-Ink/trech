#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import sys


def read_last_jsonl(path, phase=None):
    last = None
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}: invalid JSONL entry: {exc}") from exc
            if phase is None or data.get("phase") == phase:
                last = data
    return last


def format_value(value):
    if value is None:
        return "unknown"
    return str(value)


def main():
    parser = argparse.ArgumentParser(
        description="Update docs/validation_summary.md from TRECH JSONL outputs."
    )
    parser.add_argument(
        "--scores",
        default="trech_scores.jsonl",
        help="Path to trech_scores.jsonl (default: trech_scores.jsonl).",
    )
    parser.add_argument(
        "--provenance",
        default="trech_provenance.jsonl",
        help="Path to trech_provenance.jsonl (default: trech_provenance.jsonl).",
    )
    parser.add_argument(
        "--output",
        default=os.path.join("docs", "validation_summary.md"),
        help="Output markdown path (default: docs/validation_summary.md).",
    )
    args = parser.parse_args()

    if not os.path.exists(args.scores):
        raise SystemExit(f"Missing scores file: {args.scores}")

    scores = read_last_jsonl(args.scores)
    if not scores:
        raise SystemExit(f"{args.scores} is empty.")

    provenance = None
    provenance_path = args.provenance
    if os.path.exists(provenance_path):
        provenance = read_last_jsonl(provenance_path, phase="run_end")
    else:
        provenance_path = "missing"

    summary = {
        "phase": scores.get("phase"),
        "physics_list": scores.get("physics_list")
        or (provenance or {}).get("physics_list"),
        "geant4_version": (provenance or {}).get("geant4_version"),
        "n_events": scores.get("n_events") or (provenance or {}).get("n_events"),
        "seed": scores.get("seed") or (provenance or {}).get("seed"),
        "optics_enabled": scores.get("optics_enabled"),
        "total_edep_mev": scores.get("total_edep_mev"),
        "optical_photon_tracks": scores.get("optical_photon_tracks"),
        "optical_photon_steps": scores.get("optical_photon_steps"),
        "optical_photon_track_length_mm": scores.get(
            "optical_photon_track_length_mm"
        ),
        "config_hash": (provenance or {}).get("config_hash"),
        "output_dir": (provenance or {}).get("output_dir"),
        "macro_path": (provenance or {}).get("macro_path"),
        "rng_engine": (provenance or {}).get("rng_engine"),
    }

    timestamp = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    lines = [
        "# Validation Summary",
        "",
        f"Last updated: {timestamp}",
        "",
        "Source files:",
        f"- scores: {args.scores}",
        f"- provenance: {provenance_path}",
        "",
        "Run summary:",
    ]
    for key in [
        "phase",
        "physics_list",
        "geant4_version",
        "n_events",
        "seed",
        "optics_enabled",
        "total_edep_mev",
        "optical_photon_tracks",
        "optical_photon_steps",
        "optical_photon_track_length_mm",
        "config_hash",
        "output_dir",
        "macro_path",
        "rng_engine",
    ]:
        lines.append(f"- {key}: {format_value(summary.get(key))}")
    lines.append("")
    lines.append("Notes:")
    if provenance is None:
        lines.append("- Provenance record not found; run may have failed early.")
    else:
        lines.append("- Generated from the most recent run_end records.")

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    print("trech_scores.jsonl (last entry):")
    for key, value in summary.items():
        print(f"{key}={format_value(value)}")
    print(f"Validation summary updated: {args.output}")


if __name__ == "__main__":
    main()
