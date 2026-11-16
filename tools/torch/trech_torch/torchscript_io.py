"""TorchScript named-IO sidecar (``<model>.pt.io.json``, schema ``trech_torchscript_io_v1``).

Standard library only, so trainers, validators and tests can write or check it without NumPy
or torch. The engine (``GenericSurrogate``) reads it next to a ``.pt`` module.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

TORCHSCRIPT_IO_SCHEMA = "trech_torchscript_io_v1"
# Blocks of the JSON twin the engine also reads from a TorchScript sidecar.
TORCHSCRIPT_IO_KEYS = ("feature_units", "trained_scale_bands", "holdout", "prediction_interval")


def write_torchscript_io(pt_path: Path, json_path: Path) -> Path:
    """Write ``<pt>.io.json`` so the engine can use the TorchScript twin by name.

    A raw ``.pt`` module carries no feature names; the engine's GenericSurrogate reads this
    sidecar (``trech_torchscript_io_v1``) for the input/output names, units and the carried
    held-out accuracy, and refuses it unless ``model_sha256`` matches the module bytes. Every
    value is copied from the JSON twin written from the same training run.
    """
    pt_path, json_path = Path(pt_path), Path(json_path)
    twin_bytes = json_path.read_bytes()
    twin = json.loads(twin_bytes)
    sidecar = {
        "schema": TORCHSCRIPT_IO_SCHEMA,
        "model_sha256": hashlib.sha256(pt_path.read_bytes()).hexdigest(),
        "json_twin": json_path.name,
        "json_twin_sha256": hashlib.sha256(twin_bytes).hexdigest(),
        "input_features": list(twin["input_features"]),
        "output_features": list(twin["output_features"]),
    }
    for key in TORCHSCRIPT_IO_KEYS:
        if key in twin:
            sidecar[key] = twin[key]
    out = Path(str(pt_path) + ".io.json")
    out.write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    return out
