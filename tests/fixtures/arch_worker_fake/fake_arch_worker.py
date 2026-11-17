"""Fake Evolvo architecture worker for the engine bridge test (standard library only).

The request's ``name`` selects the behaviour, so the C++ test exercises every bridge outcome
without torch: an exact (better) linear model, a worse model with a lying loss report, a
mismatched request hash, a reported unavailability, a crash without a result, and a hang.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def model(weights, bias, inputs, outputs):
    return {"model": "generic_surrogate_v1", "input_features": inputs, "output_features": outputs,
            "input_mean": [0.0] * len(inputs), "input_std": [1.0] * len(inputs),
            "output_mean": [0.0] * len(outputs), "output_std": [1.0] * len(outputs),
            "layers": [{"weights": weights, "bias": bias, "activation": "none"}],
            "trained_from": {"generator": "fake"}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    raw = Path(args.request).read_bytes()
    request = json.loads(raw)
    sha = hashlib.sha256(raw).hexdigest()
    mode = request["name"]
    result = {"schema": "trech_arch_result_v1", "request_sha256": sha, "status": "ok"}
    inputs, outputs = request["inputs"], request["outputs"]
    out = Path(request["out_prefix"] + ".json")
    if mode == "hang":
        time.sleep(60)
    if mode == "crash":
        print("fake worker: crashing", file=sys.stderr)
        return 1
    if mode == "unavailable":
        result.update(status="unavailable", error="torch is not installed (fake)")
    elif mode == "mismatch":
        result["request_sha256"] = "0" * 64
    if mode in ("better", "worse", "mismatch"):
        if mode == "worse":
            weights, bias = [[0.0] * len(inputs)], [0.0]  # constant zero: worse than any fit
        else:
            weights, bias = [[2.0, -1.0]], [0.5]          # the exact target y = 2a - b + 0.5
        out.write_text(json.dumps(model(weights, bias, inputs, outputs)))
        result["best"] = {"genome": {"schema": "evolvo_arch_genome_v1", "rows": []},
                          "describe": ["fake"], "selection_loss": 0.0, "params": 3,
                          "exports": {"json": str(out)}, "engine_native": True}
    Path(args.result).write_text(json.dumps(result))
    return 3 if mode == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
