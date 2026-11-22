"""TRECH_TRACE for Python: the engine trace's records from the training and data tools.

The same observation-only log as the engine (``docs/engine/engine_trace.md``) and
``js/trech_trace.js``, for the Python side of TRECH: Torch training, TorchScript export, numpy
data and linear algebra. Configured from the same environment::

    TRECH_TRACE=<level>[:<cat>,...]   off, summary, info, debug or trace (default off)
    TRECH_TRACE_FILE=<path>            JSONL sink (schema trech_trace_v1); stderr when unset
    TRECH_TRACE_STDERR=1               also one line per record on stderr

When ``trech arch`` starts a Python worker while tracing, it sets these for the worker and copies
the worker's records into its own trace with ``origin: "python"``.

Usage::

    from trech_torch import trace
    log = trace.channel("train")
    log.info("dataset", {"rows": 120})
    trace.array("train", "x_train", x)                  # shape, dtype, finite stats
    with trace.training("train_surrogate.mlp", net, optim, epochs=400) as t:
        for epoch in range(400):
            ...
            t.epoch(epoch, loss.item())
    trace.exported("train", path, "torchscript")

Contract: nothing here draws random numbers, changes a tensor, or returns wall time to the
caller; results are the same with the trace on or off. Categories used by the tools:
``torch`` (runtime, model structure, training, export), ``numpy`` (arrays, fits), ``data``
(dataset reads), ``arch`` (architecture search), plus any ``channel(name)``.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import math
import os
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence

LEVELS = {"off": 0, "summary": 1, "info": 2, "debug": 3, "trace": 4}
ROLES = ("validation", "reference", "teacher", "forced")
MAX_RECORDS_PER_CATEGORY = 20000


def parse_level(name: Any) -> str:
    key = str("" if name is None else name).strip().lower()
    if key in ("", "on", "true"):
        return "info"
    if key in ("none", "false", "0"):
        return "off"
    if key == "all":
        return "trace"
    if key in ("1", "2", "3", "4"):
        return ("off", "summary", "info", "debug", "trace")[int(key)]
    if key not in LEVELS:
        raise ValueError(f"unknown trace level {name!r} (expected off, summary, info, debug or trace)")
    return key


def parse_spec(spec: str) -> Dict[str, Any]:
    text = str(spec or "")
    level, _, cats = text.partition(":")
    return {"level": parse_level(level), "categories": [c.strip() for c in cats.split(",") if c.strip()]}


def _jsonable(value: Any, depth: int = 3) -> Any:
    """A bounded, JSON-safe copy (numpy and torch scalars/arrays become summaries)."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    shape = getattr(value, "shape", None)
    if shape is not None and hasattr(value, "dtype"):
        try:
            if len(shape) == 0:
                return _jsonable(value.item(), depth)
        except Exception:  # noqa: BLE001 - a summary must never fail
            pass
        return {"shape": [int(s) for s in shape], "dtype": str(value.dtype)}
    if depth <= 0:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        return {str(k): _jsonable(v, depth - 1) for k, v in list(value.items())[:64]}
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        out = [_jsonable(v, depth - 1) for v in items[:16]]
        if len(items) > 16:
            out.append(f"… {len(items)} items")
        return out
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item(), depth)
        except Exception:  # noqa: BLE001
            pass
    return str(value)


class Trace:
    """One trace instance (the module-level functions use the environment-configured one)."""

    def __init__(self, level: str = "off", categories: Sequence[str] = (), path: str = "",
                 to_stderr: bool = False, sink=None) -> None:
        self.level = parse_level(level)
        self.categories = list(categories)
        self.path = path
        self.to_stderr = to_stderr
        self._sink = sink
        self._lock = threading.Lock()
        self._seq = 0
        self._per_category: Dict[str, int] = {}
        self.suppressed: Dict[str, int] = {}
        self.counters: Dict[str, float] = {}
        self.authored_laws: Dict[str, int] = {}
        self.roles: Dict[str, Dict[str, Dict[str, int]]] = {}
        self.tallies: Dict[str, Dict[str, float]] = {}
        self._role = ""
        self._finished = False
        self._file = None
        if self.level != "off" and path:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._file = open(path, "a", encoding="utf-8")

    # --- core ---------------------------------------------------------------------------
    def active(self) -> bool:
        return self.level != "off"

    def enabled(self, level: str = "info", category: str = "script") -> bool:
        if LEVELS[self.level] < LEVELS[parse_level(level)]:
            return False
        return not self.categories or category in self.categories

    def record(self, level: str, category: str, message: str, data: Any = None, severity: str = "") -> None:
        loud = severity in ("warn", "error")
        if not self.enabled(level, category):
            if loud:
                sys.stderr.write(f"TRECH python {severity}: {message}"
                                 + (f" {json.dumps(_jsonable(data))}" if data is not None else "") + "\n")
            return
        with self._lock:
            if self._finished:
                return
            count = self._per_category.get(category, 0)
            if count >= MAX_RECORDS_PER_CATEGORY:
                self.suppressed[category] = self.suppressed.get(category, 0) + 1
                return
            self._per_category[category] = count + 1
            self._seq += 1
            rec: Dict[str, Any] = {"schema": "trech_trace_v1", "seq": self._seq, "level": level,
                                   "cat": category, "msg": str(message), "host": "python"}
            if severity:
                rec["severity"] = severity
            if self._role:
                rec["role"] = self._role
            if data is not None:
                rec["data"] = _jsonable(data, 4)
            self._write(rec)

    def _write(self, rec: Dict[str, Any]) -> None:
        line = json.dumps(rec, separators=(",", ":"), ensure_ascii=False)
        if self._sink is not None:
            self._sink(rec)
        if self._file is not None:
            self._file.write(line + "\n")
            self._file.flush()
        if self.to_stderr or (self._file is None and self._sink is None):
            sys.stderr.write(f"[trech:{rec['level']}] {rec['cat']} {rec['msg']}"
                             + (f" {json.dumps(rec['data'])[:400]}" if "data" in rec else "") + "\n")

    def tally(self, section: str, key: str, amount: float = 1.0) -> None:
        if not self.active():
            return
        with self._lock:
            entries = self.tallies.setdefault(section, {})
            entries[key] = entries.get(key, 0.0) + float(amount)

    def count(self, name: str, amount: float = 1.0) -> None:
        if not self.active():
            return
        with self._lock:
            self.counters[name] = self.counters.get(name, 0.0) + float(amount)

    def authored(self, law: str, detail: Any = None) -> None:
        if not self.active():
            return
        with self._lock:
            table = (self.roles.setdefault(self._role, {}).setdefault("authored", {})
                     if self._role else self.authored_laws)
            uses = table[law] = table.get(law, 0) + 1
        if uses & (uses - 1) == 0:  # records at uses 1, 2, 4, 8, ...; every use counted
            self.record("debug", "authored", law, {"uses": uses, **({"detail": detail} if detail is not None else {})})

    @contextmanager
    def role(self, name: str) -> Iterator[None]:
        if name not in ROLES:
            raise TypeError(f"TRECH_TRACE.role: unknown role {name!r} (expected {', '.join(ROLES)})")
        previous, self._role = self._role, (name if self.active() else "")
        try:
            yield
        finally:
            self._role = previous

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            out: Dict[str, Any] = {"host": "python", "counters": dict(self.counters),
                                   "authored": dict(self.authored_laws), "tallies": json.loads(json.dumps(self.tallies))}
            if self.roles:
                out["roles"] = json.loads(json.dumps(self.roles))
            if self.suppressed:
                out["suppressed_records"] = dict(self.suppressed)
        parts = []
        steps = sum(out["tallies"].get("torch.train_steps_by_learner", {}).values())
        if steps:
            parts.append(f"Torch trained {int(steps)} optimizer steps over "
                         f"{len(out['tallies']['torch.train_steps_by_learner'])} learners")
        fits = sum(out["tallies"].get("numpy.fits_by_kind", {}).values())
        if fits:
            parts.append(f"numpy ran {int(fits)} least-squares fits")
        exports = sum(out["tallies"].get("torch.exports_by_format", {}).values())
        if exports:
            parts.append(f"{int(exports)} models were exported")
        out["verdict"] = ("; ".join(parts) + ".") if parts else "No training, fit or export was traced."
        return out

    def finish(self) -> None:
        if not self.active() or self._finished:
            return
        report = self.summary()
        with self._lock:
            self._seq += 1
            self._write({"schema": "trech_trace_v1", "seq": self._seq, "level": "summary", "cat": "summary",
                         "msg": "python summary", "host": "python", "data": report})
            self._finished = True
            if self._file is not None:
                self._file.close()
                self._file = None

    # --- channels -----------------------------------------------------------------------
    def channel(self, category: str) -> "Channel":
        return Channel(self, category)


class Channel:
    def __init__(self, trace: Trace, category: str) -> None:
        self._t, self.category = trace, str(category)

    def info(self, message: str, data: Any = None) -> None:
        self._t.record("info", self.category, message, data)

    log = info

    def debug(self, message: str, data: Any = None) -> None:
        self._t.record("debug", self.category, message, data)

    def trace(self, message: str, data: Any = None) -> None:
        self._t.record("trace", self.category, message, data)

    def warn(self, message: str, data: Any = None) -> None:
        self._t.record("info", self.category, message, data, "warn")

    def error(self, message: str, data: Any = None) -> None:
        self._t.record("info", self.category, message, data, "error")

    def enabled(self, level: str = "info") -> bool:
        return self._t.enabled(level, self.category)

    def count(self, name: str, amount: float = 1.0) -> None:
        self._t.count(f"{self.category}.{name}", amount)

    @contextmanager
    def span(self, name: str, data: Any = None) -> Iterator[None]:
        if not self.enabled("debug"):
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:  # the duration goes only to the trace
            payload = {"span": name, "duration_ms": 1000.0 * (time.perf_counter() - start)}
            if data is not None:
                payload["data"] = data
            self._t.record("debug", self.category, name, payload)


def from_environment(env: Optional[Dict[str, str]] = None) -> Trace:
    env = os.environ if env is None else env
    spec = parse_spec(env.get("TRECH_TRACE", "off"))
    path = env.get("TRECH_TRACE_FILE", "")
    stderr = env.get("TRECH_TRACE_STDERR", "")
    return Trace(spec["level"], spec["categories"], path,
                 to_stderr=bool(stderr) and stderr.lower() not in ("0", "false", "off"))


_TRACE = from_environment()
atexit.register(lambda: _TRACE.finish())


def configure(trace: Trace) -> Trace:
    """Replace the module trace (tests, or a tool that configures from its own flags)."""
    global _TRACE
    _TRACE = trace
    return trace


def current() -> Trace:
    return _TRACE


def active() -> bool:
    return _TRACE.active()


def enabled(level: str = "info", category: str = "script") -> bool:
    return _TRACE.enabled(level, category)


def channel(category: str) -> Channel:
    return Channel(_TRACE, category)


def record(level: str, category: str, message: str, data: Any = None, severity: str = "") -> None:
    _TRACE.record(level, category, message, data, severity)


def tally(section: str, key: str, amount: float = 1.0) -> None:
    _TRACE.tally(section, key, amount)


def authored(law: str, detail: Any = None) -> None:
    _TRACE.authored(law, detail)


def role(name: str):
    return _TRACE.role(name)


def summary() -> Dict[str, Any]:
    return _TRACE.summary()


def finish() -> None:
    _TRACE.finish()


# --- numpy ------------------------------------------------------------------------------

def array_stats(value: Any) -> Dict[str, Any]:
    """Shape, dtype, size in bytes and finite statistics of a numpy array (or array-like)."""
    import numpy as np

    a = np.asarray(value)
    out: Dict[str, Any] = {"shape": list(a.shape), "dtype": str(a.dtype), "bytes": int(a.nbytes)}
    if a.size and np.issubdtype(a.dtype, np.number):
        finite = np.isfinite(a)
        out["nonfinite"] = int(a.size - int(finite.sum()))
        if finite.any():
            f = a[finite].astype(np.float64)
            out.update(min=float(f.min()), max=float(f.max()), mean=float(f.mean()), std=float(f.std()))
        if a.ndim == 2 and a.shape[1] <= 64:
            out["column_std_zero"] = int((a.std(axis=0) < 1e-12).sum())
    return out


def array(category: str, name: str, value: Any, level: str = "debug") -> None:
    """One record describing a numpy array: what data a fit or training actually saw."""
    if not enabled(level, category):
        return
    record(level, category, f"array {name}", {"name": name, **array_stats(value)})
    tally("numpy.arrays_by_name", name)


def linear_fit(category: str, kind: str, x: Any, y: Any, l2: float = 0.0, **details: Any) -> None:
    """A numpy least-squares/ridge fit: design and target shapes, regularisation, conditioning."""
    if not active():
        return
    tally("numpy.fits_by_kind", kind)
    if not enabled("debug", category):
        return
    import numpy as np

    xa, ya = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    data: Dict[str, Any] = {"kind": kind, "x_shape": list(xa.shape), "y_shape": list(ya.shape), "l2": l2}
    if xa.ndim == 2 and 0 < xa.shape[1] <= 512 and xa.shape[0] > 0:
        try:
            data["gram_condition"] = float(np.linalg.cond(xa.T @ xa + l2 * np.eye(xa.shape[1])))
        except Exception:  # noqa: BLE001 - diagnostics never fail the fit
            pass
    data.update(details)
    record("debug", category, f"fit {kind}", data)


# --- torch ------------------------------------------------------------------------------

def runtime() -> Dict[str, Any]:
    """Versions and threading of the numerical stack: Python, numpy, torch."""
    out: Dict[str, Any] = {"python": sys.version.split()[0]}
    try:
        import numpy as np

        out["numpy"] = np.__version__
    except ImportError:
        out["numpy"] = None
    try:
        import torch

        out.update(torch=torch.__version__, threads=torch.get_num_threads(),
                   interop_threads=torch.get_num_interop_threads(),
                   cuda=bool(torch.cuda.is_available()),
                   mps=bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()),
                   deterministic_algorithms=bool(torch.are_deterministic_algorithms_enabled()),
                   default_dtype=str(torch.get_default_dtype()))
    except ImportError:
        out["torch"] = None
    return out


_RUNTIME_SENT = False


def announce(category: str = "torch", tool: str = "") -> None:
    """Record the numerical runtime once per process (at info)."""
    global _RUNTIME_SENT
    if _RUNTIME_SENT or not enabled("info", category):
        return
    _RUNTIME_SENT = True
    record("info", category, "runtime", {"tool": tool or os.path.basename(sys.argv[0]), **runtime()})


def model_summary(module: Any) -> Dict[str, Any]:
    """Parameter counts and the layer list of a torch module."""
    params = list(module.parameters()) if hasattr(module, "parameters") else []
    layers: List[Dict[str, Any]] = []
    if hasattr(module, "named_modules"):
        for name, child in module.named_modules():
            if name and not list(child.children()):
                entry: Dict[str, Any] = {"name": name, "type": type(child).__name__}
                for attr in ("in_features", "out_features"):
                    if hasattr(child, attr):
                        entry[attr] = int(getattr(child, attr))
                layers.append(entry)
    return {"type": type(module).__name__,
            "parameters": int(sum(p.numel() for p in params)),
            "trainable": int(sum(p.numel() for p in params if getattr(p, "requires_grad", False))),
            "layers": layers[:64]}


class TrainingTrace:
    """Per-epoch record of one training loop. ``epoch`` is cheap when the trace is off."""

    def __init__(self, learner: str, module: Any = None, optimizer: Any = None, epochs: int = 0,
                 category: str = "torch", **details: Any) -> None:
        self.learner, self.category, self.epochs = learner, category, int(epochs)
        self._module, self._optimizer = module, optimizer
        self._details = details
        self.first: Optional[float] = None
        self.last: Optional[float] = None
        self.best: Optional[float] = None
        self.steps = 0
        self._start = 0.0

    def __enter__(self) -> "TrainingTrace":
        if active():
            announce(self.category)
            self._start = time.perf_counter()
            if enabled("info", self.category):
                data: Dict[str, Any] = {"learner": self.learner, "epochs": self.epochs, **self._details}
                if self._module is not None:
                    data["model"] = model_summary(self._module)
                if self._optimizer is not None:
                    group = self._optimizer.param_groups[0] if getattr(self._optimizer, "param_groups", None) else {}
                    data["optimizer"] = {"type": type(self._optimizer).__name__,
                                         **{k: _jsonable(v) for k, v in group.items() if k != "params"}}
                record("info", self.category, "training start", data)
        return self

    def epoch(self, index: int, loss: float, **extra: Any) -> None:
        if not active():
            return
        value = float(loss)
        self.steps += 1
        if self.first is None:
            self.first = value
        self.last = value
        self.best = value if self.best is None or value < self.best else self.best
        n = index + 1
        # Epochs 1, 2, 4, 8, ... and the last at debug; every epoch at trace.
        mark = n & (n - 1) == 0 or (self.epochs and n == self.epochs)
        level = "debug" if mark else "trace"
        if not enabled(level, self.category):
            return
        data: Dict[str, Any] = {"learner": self.learner, "epoch": n, "loss": value, **extra}
        if self._optimizer is not None and getattr(self._optimizer, "param_groups", None):
            data["lr"] = float(self._optimizer.param_groups[0].get("lr", 0.0))
        if self._module is not None and enabled("trace", self.category):
            norms = [float(p.grad.detach().norm()) for p in self._module.parameters() if p.grad is not None]
            if norms:
                data["grad_norm"] = math.sqrt(sum(v * v for v in norms))
        record(level, self.category, "epoch", data)

    def __exit__(self, exc_type, exc, tb) -> None:
        if not active():
            return
        tally("torch.train_steps_by_learner", self.learner, self.steps)
        tally("torch.train_runs_by_learner", self.learner)
        if enabled("info", self.category):
            record("info", self.category, "training end",
                   {"learner": self.learner, "steps": self.steps, "loss_first": self.first,
                    "loss_last": self.last, "loss_best": self.best, "failed": exc_type is not None,
                    "duration_ms": 1000.0 * (time.perf_counter() - self._start)})


def training(learner: str, module: Any = None, optimizer: Any = None, epochs: int = 0,
             category: str = "torch", **details: Any) -> TrainingTrace:
    return TrainingTrace(learner, module, optimizer, epochs, category, **details)


def exported(category: str, path: Any, fmt: str, **details: Any) -> None:
    """A model written to disk: format, size and content hash, so a run can be matched to it."""
    if not active():
        return
    tally("torch.exports_by_format", fmt)
    if not enabled("info", category):
        return
    data: Dict[str, Any] = {"path": str(path), "format": fmt, **details}
    try:
        with open(path, "rb") as handle:
            blob = handle.read()
        data.update(bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())
    except OSError:
        data["missing"] = True
    record("info", category, "model exported", data)
