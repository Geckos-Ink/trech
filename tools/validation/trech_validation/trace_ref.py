"""Check that a run's provenance trace reference belongs to its trace file.

When the engine trace is on, every Geant4 batch writes a ``batch attribution summary`` record to
``trech_trace.jsonl`` and the matching ``run_end`` provenance record carries a ``trace`` reference
(``trech_trace_ref_v1``): the batch number, the record's ``seq``, the batch totals and verdict and
``summary_hash``, the FNV-1a 64 hash of the batch summary JSON exactly as the engine serialized
it. This module recomputes the hash from the bytes of that record's ``data`` object (it never
re-serializes the JSON, so float formatting cannot differ) and compares every field.

A traced run that stopped before ``run_end`` has no reference. Its trace file can still end with
the ``run attribution summary``; :func:`verify_run` reports which of the two is present.

States: ``ok`` (every reference matches), ``mismatch``, ``unreferenced`` (a trace file but no
``run_end`` record, e.g. the scenario failed to evaluate) and ``untraced``.

Usage: ``python -m trech_validation.trace_ref <run_dir> [<run_dir> ...]`` (exit 1 on a mismatch).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

TRACE_FILE = "trech_trace.jsonl"
REF_SCHEMA = "trech_trace_ref_v1"
BATCH_MSG = "batch attribution summary"
RUN_MSG = "run attribution summary"


def fnv1a64(data: bytes) -> str:
    h = 14695981039346656037
    for byte in data:
        h = ((h ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def _summary_records(text: str) -> List[Dict]:
    """Batch and run summary records, each with the exact bytes of its ``data`` object."""
    out = []
    decoder = json.JSONDecoder()
    for number, line in enumerate(text.splitlines(), 1):
        if '"cat":"summary"' not in line:
            continue
        record = json.loads(line)
        if record.get("msg") not in (BATCH_MSG, RUN_MSG):
            continue
        start = line.find('"data":')
        if start < 0:
            continue
        start += len('"data":')
        _, end = decoder.raw_decode(line, start)
        out.append({"line": number, "msg": record["msg"], "seq": record.get("seq"), "data": record.get("data") or {},
                    "hash": fnv1a64(line[start:end].encode("utf-8"))})
    return out


def _trace_path(run_dir: Path, ref: Dict) -> Optional[Path]:
    """The file the reference names: absolute, relative to the current directory (the suite runs
    from the repository root), or the same file name inside the run directory."""
    if not ref.get("path"):
        return None
    p = Path(ref["path"])
    for candidate in ([p] if p.is_absolute() else [Path.cwd() / p, run_dir / p.name]):
        if candidate.is_file():
            return candidate
    return None


def verify_run(run_dir: Path, provenance: Optional[List[Dict]] = None) -> Dict:
    """Compare every ``run_end`` trace reference of one run directory with its trace file."""
    run_dir = Path(run_dir)
    if provenance is None:
        prov_path = run_dir / "trech_provenance.jsonl"
        provenance = [json.loads(l) for l in prov_path.read_text(encoding="utf-8").splitlines() if l.strip()] \
            if prov_path.exists() else []
    ends = [r for r in provenance if r.get("phase") == "run_end"]
    refs = [r["trace"] for r in ends if isinstance(r.get("trace"), dict)]
    trace_file = run_dir / TRACE_FILE
    report: Dict = {"run_dir": str(run_dir), "run_end_records": len(ends), "references": [], "problems": [],
                    "trace_file": trace_file.is_file()}
    records = _summary_records(trace_file.read_text(encoding="utf-8")) if trace_file.is_file() else []
    batches = {r["data"].get("batch"): r for r in records if r["msg"] == BATCH_MSG}
    run_summary = next((r for r in reversed(records) if r["msg"] == RUN_MSG), None)
    report["batch_records"] = len(batches)
    report["run_summary"] = run_summary is not None
    if not refs:
        # Untraced, or traced but stopped before any run_end record (e.g. the scenario failed to
        # evaluate): nothing to compare. A batch record without a reference is a mismatch.
        report["traced"] = trace_file.is_file()
        report["state"] = "unreferenced" if trace_file.is_file() else "untraced"
        if batches and ends:
            report["problems"].append(f"{len(batches)} batch record(s) but no run_end record carries a trace reference")
        report["note"] = ("traced, but no run_end provenance record: the run stopped before Geant4 finished a batch; "
                          f"the trace file {'ends with' if run_summary else 'has no'} run attribution summary"
                          if report["state"] == "unreferenced" else "not traced")
        report["ok"] = not report["problems"]
        if report["problems"]:
            report["state"] = "mismatch"
        return report
    report["traced"] = True
    for ref in refs:
        entry = {"batch": ref.get("batch"), "summary_hash": ref.get("summary_hash"), "problems": []}
        problems = entry["problems"]
        if ref.get("schema") != REF_SCHEMA:
            problems.append(f"schema {ref.get('schema')!r}, expected {REF_SCHEMA}")
        path = _trace_path(run_dir, ref)
        if path is None:
            problems.append(f"trace file {ref.get('path')!r} not found" if ref.get("path") else
                            "the reference names no trace file (trace written to stderr only?)")
        else:
            entry["trace_file"] = str(path)
            here = batches if trace_file.is_file() and path.resolve() == trace_file.resolve() else {
                r["data"].get("batch"): r for r in _summary_records(path.read_text(encoding="utf-8")) if r["msg"] == BATCH_MSG}
            record = here.get(ref.get("batch"))
            if record is None:
                problems.append(f"no batch attribution summary for batch {ref.get('batch')} in the trace file")
            else:
                entry["recomputed_hash"] = record["hash"]
                if record["hash"] != ref.get("summary_hash"):
                    problems.append(f"summary_hash {ref.get('summary_hash')} != recomputed {record['hash']}")
                if record["seq"] != ref.get("seq"):
                    problems.append(f"seq {ref.get('seq')} != batch record seq {record['seq']}")
                for key in ("totals", "verdict"):
                    if record["data"].get(key) != ref.get(key):
                        problems.append(f"{key} differs from the batch record")
        entry["ok"] = not problems
        report["references"].append(entry)
        report["problems"] += [f"batch {entry['batch']}: {p}" for p in problems]
    if len({r.get("batch") for r in refs}) != len(refs):
        report["problems"].append("two run_end records reference the same batch")
    if run_summary is not None and run_summary["data"].get("batches") not in (None, len(batches)):
        report["problems"].append(
            f"run summary counts {run_summary['data'].get('batches')} batches, the file has {len(batches)}")
    report["ok"] = not report["problems"]
    report["state"] = "ok" if report["ok"] else "mismatch"
    return report


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(__doc__)
        return 2
    failed = 0
    for arg in args:
        report = verify_run(Path(arg))
        refs = report["references"]
        print(f"{arg}: {report['state']}; {len(refs)} reference(s), {report['batch_records']} batch record(s), "
              f"run summary {'present' if report['run_summary'] else 'absent'}" +
              (f" ({report['note']})" if report.get("note") else ""))
        for p in report["problems"]:
            print("  - " + p)
        failed += not report["ok"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
