#!/usr/bin/env python3
"""`trech-measure-routing-domain`: a measured, never authored, routing_domain block.

Builds a fake run whose hook emits carry kind-tagged sample rows, measures the routing domain of
one population, writes it into a model and checks:

* min/max/scale come from the rows (scale = population std, floored for constant features);
* rows missing a feature are ignored, a population with none is refused;
* a routing feature that is already a model input is refused (input coverage handles it);
* the model's other keys are untouched and the engine's loader accepts the result
  (the C++ side is covered by `trech_state_evolution`).

Runs under CTest with TRECH_ML_PYTHON.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools" / "torch"))

from trech_torch.routing_domain import main, measure, write_block  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def run_dir(root: Path) -> Path:
    run = root / "run_a"
    run.mkdir()
    emits = [
        {"tag": "sample_melt", "payload": {"samples": [
            {"t": 1500.0, "phase": 0.6, "glass": 0.0},
            {"t": 1600.0, "phase": 1.0, "glass": 0.8},
            {"t": 1550.0, "phase": 0.8}]}},  # no glass fraction: ignored
        {"tag": "sample_solid", "payload": {"samples": [{"t": 900.0, "phase": 0.1, "glass": 0.0}]}},
    ]
    (run / "trech_hook_emits.jsonl").write_text("".join(json.dumps(e) + "\n" for e in emits))
    (run / "trech_scores.jsonl").write_text("{}\n")  # marks a run directory
    return run


def main_test() -> None:
    rows = [{"phase": 0.6, "glass": 0.0}, {"phase": 1.0, "glass": 0.8}, {"phase": 0.8}]
    block = measure(rows, ["phase", "glass"])
    check(block["n_rows"] == 2 and block["min"] == [0.6, 0.0] and block["max"] == [1.0, 0.8],
          "range over the rows that carry every feature")
    check(math.isclose(block["scale"][0], 0.2) and math.isclose(block["scale"][1], 0.4),
          "scale is the population standard deviation")
    constant = measure([{"phase": 1.0}, {"phase": 1.0}], ["phase"])
    check(constant["scale"] == [1e-9], "a constant feature gets the tiny floor")
    try:
        measure([{"phase": 1.0}], ["glass"])
        check(False, "a population without the feature must be refused")
    except ValueError:
        pass

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run = run_dir(root)
        model = root / "law.json"
        original = {"model": "generic_surrogate_v1", "input_features": ["t"], "output_features": ["d_x_dt"],
                    "layers": [{"weights": [[0.0]], "bias": [1.0], "activation": "none"}], "note": "keep"}
        model.write_text(json.dumps(original))
        code = main(["--runs", str(run), "--tag", "sample_melt", "--expand", "samples",
                     "--features", "phase,glass", "--model", str(model)])
        check(code == 0, "the CLI writes the block")
        written = json.loads(model.read_text())
        domain = written.pop("routing_domain")
        check(written == original, "every other key is untouched")
        check(domain["features"] == ["phase", "glass"] and domain["min"] == [0.6, 0.0]
              and domain["n_rows"] == 2 and domain["source"]["tag"] == "sample_melt",
              "the block records its range and its source")
        try:
            write_block(model, measure([{"t": 1.0}], ["t"]))
            check(False, "a routing feature that is an input must be refused")
        except ValueError:
            pass
    print("test_routing_domain: OK")


if __name__ == "__main__":
    main_test()
