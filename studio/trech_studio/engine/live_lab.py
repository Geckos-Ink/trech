"""Studio's live scenario lab: personalise a running scenario without restarting Geant4.

``LiveScenarioLab`` keeps one ``trech lab <scenario.js>`` session (``engine/lab.py``) and
turns Studio edits into the engine's transactional re-evaluations:

* an Options-panel change (a typed ``TRECH_VALUE``) becomes one ``params`` command with only
  the values that changed, debounced so a dragged slider sends one command, then one batch;
* the session runs with ``--watch``, so saving a file the active script generation read (its
  entry, a ``TRECH_INCLUDE`` or a ``TRECH_READ_JSON`` file) just runs one batch: the engine
  re-evaluates the scenario first when, and only when, those files' bytes changed (an edit
  made outside Studio counts too, and a save without changes keeps the hook state);
* ``batch()`` runs one more batch on the current script.

The engine decides what is accepted. A change that only touches the hook layer swaps in a new
script generation; one that touches initialized Geant4 state (beam, geometry, physics, models,
the set of hooks) is refused, and the previous script keeps running. Each finished batch
reports its round-plan telemetry plus the ``onRunEnd`` emits it wrote, so the effect of an
edit is visible at once.

This is a client of the engine's lab protocol, not a second engine: Studio never evaluates
the scenario or decides how anything is predicted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from .lab import LabSession
from .locator import EngineLocation


def _encode(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


class LiveScenarioLab(QObject):
    """One scenario-backed ``trech lab`` session driven by Studio edits."""

    info = Signal(str)               # human-readable progress lines for the console
    error = Signal(str)              # refusals and failures
    generation_changed = Signal(dict)  # lab_script status after a start or accepted change
    batch_finished = Signal(dict)    # {"round_plan": {...}, "emits": [...], "generation": n}
    stopped = Signal(int)

    def __init__(self, engine: EngineLocation, parent: Optional[QObject] = None,
                 debounce_ms: int = 250, session: Optional[LabSession] = None) -> None:
        super().__init__(parent)
        self.session = session if session is not None else LabSession(engine, self)
        self.output_dir: Optional[Path] = None
        self.events: Optional[int] = None    # None: the engine's adaptive round count
        self._sent: Dict[str, str] = {}      # TRECH_VALUE id -> JSON the active request used
        self._pending: Dict[str, Any] = {}
        self._emit_offset = 0
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self._flush_params)
        self.session.script_status.connect(self._on_script_status)
        self.session.round_plan.connect(self._on_round_plan)
        self.session.refused.connect(self.error.emit)
        self.session.failed.connect(self.error.emit)
        self.session.stopped.connect(self._on_stopped)

    # --- lifecycle ----------------------------------------------------------------------

    def is_active(self) -> bool:
        return self.session.is_active()

    def start(self, scenario: Path, values: Dict[str, Any], output_dir: Path,
              events: Optional[int] = None) -> bool:
        """Start the session with the Options panel's current values and run one batch."""
        if self.is_active():
            self.error.emit("a live lab is already running; stop it first")
            return False
        params: List[str] = []
        for name, value in values.items():
            params += ["--param", f"{name}={_encode(value)}"]
        self.output_dir = Path(output_dir)
        self.events = events
        self._sent = {name: _encode(value) for name, value in values.items()}
        self._pending = {}
        self._emit_offset = 0
        if not self.session.start(scenario=Path(scenario), params=params,
                                  output_dir=self.output_dir, watch=True):
            return False
        self.info.emit(f"live lab started: {Path(scenario).name} -> {self.output_dir}")
        return self.batch()

    def stop(self) -> None:
        self._debounce.stop()
        self._pending = {}
        self.session.quit()

    def batch(self) -> bool:
        return self.session.simulate(self.events)

    # --- edits --------------------------------------------------------------------------

    def values_changed(self, values: Dict[str, Any]) -> None:
        """Options-panel values; only the ones that differ from the last request are sent."""
        if not self.is_active():
            return
        for name, value in values.items():
            if self._sent.get(name) != _encode(value):
                self._pending[name] = value
            else:
                self._pending.pop(name, None)
        if self._pending:
            self._debounce.start()

    def _flush_params(self) -> None:
        if not self._pending or not self.is_active():
            return
        changes, self._pending = self._pending, {}
        # Remember what was asked; a refusal is reported and the next edit re-sends the
        # difference against what was asked, so a refused value is not retried in a loop.
        self._sent.update({name: _encode(value) for name, value in changes.items()})
        self.info.emit("live lab: params " + _encode(changes))
        self.session.set_params(changes)
        self.batch()

    def source_saved(self, path: Path) -> bool:
        """A saved file the active generation read: run a batch, which picks the edit up."""
        if not self.is_active() or not self._reads(Path(path)):
            return False
        self.info.emit(f"live lab: batch after saving {Path(path).name} "
                       "(the engine re-evaluates the scenario if its files changed)")
        self.batch()
        return True

    def _reads(self, path: Path) -> bool:
        script = self.session.script
        entry = self.session.scenario
        if not script or entry is None:
            return False
        base = entry.parent
        target = path.resolve()
        for key in ("sources", "data"):
            for item in script.get(key, []):
                if (base / item.get("path", "")).resolve() == target:
                    return True
        return False

    # --- engine output ------------------------------------------------------------------

    def _on_script_status(self, status: dict) -> None:
        digest = str(status.get("sources_sha256", ""))[:12]
        self.info.emit(
            f"live lab: script generation {status.get('generation')} "
            f"({status.get('trigger', 'start')}), sources {digest}")
        self.generation_changed.emit(status)

    def _on_round_plan(self, plan: dict) -> None:
        emits = self._new_run_end_emits()
        self.batch_finished.emit({"round_plan": plan, "emits": emits,
                                  "generation": self.session.generation})

    def _new_run_end_emits(self) -> List[dict]:
        """onRunEnd emits appended to trech_hook_emits.jsonl since the previous batch."""
        if self.output_dir is None:
            return []
        path = self.output_dir / "trech_hook_emits.jsonl"
        try:
            with path.open("rb") as handle:
                handle.seek(self._emit_offset)
                data = handle.read()
        except OSError:
            return []
        complete = data[: data.rfind(b"\n") + 1]
        self._emit_offset += len(complete)
        emits = []
        for line in complete.decode("utf-8", "replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("hook") == "onRunEnd":
                emits.append(record)
        return emits

    def _on_stopped(self, code: int) -> None:
        self._debounce.stop()
        self.info.emit(f"live lab stopped (exit {code})")
        self.stopped.emit(code)


def describe_batch(result: dict) -> str:
    """One console line per batch: rate, generation and each onRunEnd emit's payload."""
    plan = result.get("round_plan", {})
    parts = [f"live lab batch (generation {result.get('generation')}): "
             f"{plan.get('planned_rounds', '?')} events, "
             f"{float(plan.get('achieved_hz') or 0.0):.2f} Hz"]
    for emit in result.get("emits", []):
        parts.append(f"{emit.get('tag')}: {_encode(emit.get('payload'))}")
    return "\n  ".join(parts)
