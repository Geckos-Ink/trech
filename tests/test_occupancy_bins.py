#!/usr/bin/env python3
"""The engine's occupancy bins must be the bins training counted.

`trech-train-surrogate` builds each input's occupancy histogram with
`numpy.histogram(range=(lo, hi), bins=n)`. The engine reads an input as *starved*
when it lands in a bin with a zero count, so its bin rule has to be numpy's bit
for bit: otherwise a training value near a bin edge reads as the neighbouring
bin, which may be empty, and a training row is flagged as a hole it is not.

The scaled index `(x - lo) / (hi - lo) * n` alone lands one bin off within about
one ulp of an edge, so numpy corrects it against its linspace edges. This test
runs the engine's `GenericSurrogate::occupancyBin` (through
`test_formal_laws --occupancy-bins`) and the validator's `occupancy_bins` on
values at and next to every edge, and on interior values, and compares both with
`numpy.histogram`. The proof that the corrected index is the unique containing
bin is `Trech.Methods.Domain` (`formal/Trech/Methods/Domain.lean`).

Runs under CTest; needs only numpy.
"""

from __future__ import annotations

import random
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools" / "torch"))

from trech_torch.validate_model import occupancy_bins  # noqa: E402


def cases(seed: int = 20261126):
    rng = random.Random(seed)
    for _ in range(1500):
        lo = rng.uniform(-1.0, 1.0) * 10.0 ** rng.uniform(-1.0, 2.0)
        hi = lo + 10.0 ** rng.uniform(-2.0, 2.0)
        n = rng.randint(2, 21)
        values = set()
        for edge in np.linspace(lo, hi, n + 1):
            for v in (edge, np.nextafter(edge, -np.inf), np.nextafter(edge, np.inf)):
                if lo <= v <= hi:
                    values.add(float(v))
        values.update(rng.uniform(lo, hi) for _ in range(6))
        yield lo, hi, n, sorted(values)


def numpy_bin(x: float, lo: float, hi: float, n: int) -> int:
    hist, _ = np.histogram(np.array([x]), bins=n, range=(lo, hi))
    return int(np.argmax(hist))


def main() -> int:
    binary = Path(sys.argv[1])
    rows = []
    for lo, hi, n, values in cases():
        rows.extend((x, lo, hi, n) for x in values)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bins.txt"
        path.write_text("".join(f"{x!r} {lo!r} {hi!r} {n}\n" for x, lo, hi, n in rows))
        out = subprocess.run([str(binary), "--occupancy-bins", str(path)], check=True,
                             capture_output=True, text=True).stdout.split()
    engine = [int(v) for v in out]
    assert len(engine) == len(rows), (len(engine), len(rows))
    reference = [numpy_bin(x, lo, hi, n) for x, lo, hi, n in rows]
    engine_bad = sum(e != r for e, r in zip(engine, reference))
    validator = []
    for lo, hi, n, values in cases():
        validator.extend(int(b) for b in occupancy_bins(values, lo, hi, n))
    validator_bad = sum(v != r for v, r in zip(validator, reference))
    raw = [min(n - 1, max(0, int((x - lo) / (hi - lo) * n))) for x, lo, hi, n in rows]
    raw_bad = sum(v != r for v, r in zip(raw, reference))
    print(f"{len(rows)} values: engine {engine_bad}, validator {validator_bad} differ from numpy; "
          f"the uncorrected index differs on {raw_bad}")
    assert engine_bad == 0 and validator_bad == 0
    assert raw_bad > 0, "the edge-adjacent sample no longer exercises the correction"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
