#!/usr/bin/env python3
"""TRECH adapter for Evolvo GFSL-NN architecture search (trech_torch.evolve_architecture).

* Always (pure Python): the pinned ``thirds/evolvo`` imports ``evolvo.arch`` without NumPy, and
  random genomes of a surrogate-shaped space are valid by construction.
* With NumPy + torch: a dense-only search exports a native ``generic_surrogate_v1`` JSON whose
  NumPy evaluation matches the torch module and its TorchScript twin; a transformer search
  exports only TorchScript + sidecar + a non-loadable ``trech_evolved_arch_v1`` record; the
  sidecar is bound to the module bytes; knowledge persists across searches.

Synthetic data: tests the export contract, not physics. Self-skips the torch part.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "thirds" / "evolvo" / "src"))
sys.path.insert(0, str(REPO / "tools" / "torch"))

FAILURES = 0


def check(cond, message):
    global FAILURES
    if not cond:
        FAILURES += 1
        print(f"FAIL: {message}")


def main() -> int:
    try:
        from evolvo.arch import ArchSpace, Chooser
    except ImportError as exc:
        print(f"SKIP: thirds/evolvo is not initialized ({exc})")
        return 0
    check("numpy" not in sys.modules, "evolvo.arch imports without NumPy")
    space = ArchSpace([("vec", 5)], 2, max_rows=6, max_params=20_000)
    chooser = Chooser(random.Random(0))
    for _ in range(200):
        genome = space.random_genome(chooser)
        check(space.validate(genome) == [], "random genomes are valid by construction")
    try:
        import numpy as np
        import torch
    except ImportError:
        print("SKIP: numpy/torch not available (export part)")
        return 1 if FAILURES else 0

    from trech_torch.evolve_architecture import ARCH_SCHEMA, dense_layers, export, predict, search_architecture
    from trech_torch.train_surrogate import predict_np

    rng = np.random.default_rng(0)
    x = rng.uniform(-1, 1, size=(360, 3))
    y = np.stack([x[:, 0] * x[:, 1] + np.sin(2 * x[:, 2]), x[:, 0] - 0.5 * x[:, 2] ** 2], axis=1)
    x_tr, y_tr, x_va, y_va, x_te = x[:200], y[:200], x[200:280], y[200:280], x[280:]
    inputs, outputs = ["a", "b", "c"], ["u", "v"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        know = tmp / "knowledge.json"
        dense = search_architecture(x_tr, y_tr, x_va, y_va, ops=["linear", "act", "mlp"], max_rows=3,
                                    max_params=3000, generations=2, population=4, seed=1,
                                    hard_max_epochs=120, lr=1e-2, knowledge_path=know)
        check(know.exists(), "the knowledge file is written")
        layers = dense_layers(dense["space"], dense["genome"], dense["module"])
        check(layers is not None, "a linear/act/mlp architecture lowers to dense layers")
        paths = export(tmp / "dense", dense, inputs, outputs, x_tr, meta={"synthetic": True})
        model = json.loads(Path(paths["json"]).read_text())
        check(model["model"] == "generic_surrogate_v1", "dense chains export the native JSON")
        ref = predict(dense["module"], x_te, dense["scalers"])
        got = predict_np(x_te, model["layers"], (np.array(model["input_mean"]), np.array(model["input_std"]),
                                                 np.array(model["output_mean"]), np.array(model["output_std"])))
        check(float(np.max(np.abs(got - ref))) < 1e-4, "the JSON reproduces the torch module")
        scripted = torch.jit.load(paths["torchscript"])
        with torch.no_grad():
            ts = scripted(torch.tensor(x_te, dtype=torch.float32)).double().numpy()
        check(float(np.max(np.abs(ts - ref))) < 1e-4, "the TorchScript twin reproduces the module (raw units)")
        sidecar = json.loads(Path(paths["sidecar"]).read_text())
        check(sidecar["model_sha256"] == hashlib.sha256(Path(paths["torchscript"]).read_bytes()).hexdigest(),
              "the sidecar is bound to the module bytes")
        check(sidecar["input_features"] == inputs and sidecar["output_features"] == outputs, "sidecar names")

        deep = search_architecture(x_tr, y_tr, x_va, y_va, ops=["tokenize", "transformer", "pool"],
                                   max_rows=3, max_params=20_000, generations=1, population=3, seed=2,
                                   hard_max_epochs=40, lr=5e-3, knowledge_path=know)
        check(any(r.op == "transformer" for r in deep["genome"].rows) or
              any(r.op == "tokenize" for r in deep["genome"].rows), "the restricted space is honoured")
        check(dense_layers(deep["space"], deep["genome"], deep["module"]) is None,
              "set/attention architectures are not mistaken for dense chains")
        paths = export(tmp / "deep", deep, inputs, outputs, x_tr, meta={"synthetic": True})
        record = json.loads(Path(paths["arch"]).read_text())
        check(record["schema"] == ARCH_SCHEMA and "model" not in record and "json" not in paths,
              "non-dense architectures export TorchScript with a non-loadable arch record only")
        scripted = torch.jit.load(paths["torchscript"])
        with torch.no_grad():
            ts = scripted(torch.tensor(x_te[:7], dtype=torch.float32)).double().numpy()
        ref = predict(deep["module"], x_te[:7], deep["scalers"])
        check(float(np.max(np.abs(ts - ref))) < 1e-4, "the traced transformer runs at a new batch size")
        knowledge = json.loads(know.read_text())
        check(len(knowledge["policy"]["records"]) > 0 and len(knowledge["epochs"]["records"]) > 0,
              "learned tendencies accumulate across searches")

        # CLI on synthetic run directories (hook emits): disjoint splits, export, report.
        from trech_torch.evolve_architecture import main as cli

        runs = {}
        for split, block in (("train", (x_tr, y_tr)), ("valid", (x_va, y_va)), ("test", (x_te, y[280:]))):
            run = tmp / "runs" / split
            run.mkdir(parents=True)
            (run / "trech_scores.jsonl").write_text(json.dumps({"phase": "run_summary"}) + "\n")
            with (run / "trech_hook_emits.jsonl").open("w") as fh:
                for xi, yi in zip(*block):
                    payload = dict(zip(inputs + outputs, [float(v) for v in list(xi) + list(yi)]))
                    fh.write(json.dumps({"tag": "s", "payload": payload}) + "\n")
            runs[split] = str(run)
        common = ["--inputs", "a,b,c", "--outputs", "u,v", "--source", "hook_emits", "--tag", "s",
                  "--generations", "1", "--population", "3", "--max-rows", "2", "--max-params", "2000",
                  "--max-epochs", "40", "--ops", "linear,act,mlp", "--out", str(tmp / "cli" / "model"),
                  "--report", str(tmp / "cli_report.json")]
        try:
            cli(["--runs", runs["train"], "--validation-runs", runs["train"], "--test-runs", runs["test"]] + common)
            check(False, "overlapping train/selection runs are refused")
        except SystemExit as exc:
            check(exc.code == 2, "overlapping train/selection runs are refused")
        code = cli(["--runs", runs["train"], "--validation-runs", runs["valid"], "--test-runs", runs["test"]] + common)
        check(code == 0 and (tmp / "cli" / "model.pt.io.json").exists(), "the CLI exports TorchScript + sidecar")
        twin = tmp / "cli" / "model.json"
        exported = json.loads((twin if twin.exists() else tmp / "cli" / "model.arch.json").read_text())
        check(exported["holdout"]["n"] == len(x_te) and "genome" in exported["trained_from"],
              "the CLI carries test-run accuracy and the genome")
        check(json.loads((tmp / "cli_report.json").read_text())["schema"] == "evolvo_arch_search_v1",
              "the CLI writes the search report")
    if FAILURES:
        print(f"{FAILURES} failure(s)")
        return 1
    print("test_evolvo_arch.py: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
