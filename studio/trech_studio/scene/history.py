"""Undo/redo history for Inspector scene drafts.

Each applied draft edit records the scene before and after it, together with the node that was
selected in each state, so undo and redo can restore both the geometry and the Inspector view.
Snapshots are deep copies: later edits never reach into a recorded state. The history is
pure data (no Qt), so it is tested without a window.

Whether a restored state is unsaved is the window's call: it compares the scene with the last
saved one (the recorded run's scene, or the last export), never with the history position.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .model import SceneModel

Selection = Tuple[str, str]  # (node kind, node name), as the outliner and Inspector use them


@dataclass(frozen=True)
class SceneState:
    """One restorable scene state and the node to show with it."""

    scene: SceneModel
    selection: Selection


@dataclass(frozen=True)
class SceneEdit:
    """One applied draft edit: the states on either side of it and a short label."""

    before: SceneState
    after: SceneState
    label: str


class SceneHistory:
    """A linear undo/redo stack of applied scene edits.

    Recording a new edit after an undo drops the undone edits (the usual editor behaviour).
    ``limit`` bounds memory; the oldest edit is dropped first.
    """

    def __init__(self, limit: int = 100) -> None:
        if limit < 1:
            raise ValueError("history limit must be at least 1")
        self._limit = limit
        self._edits: List[SceneEdit] = []
        self._position = 0  # number of applied edits; edits[position:] are redoable

    # --- state ------------------------------------------------------------------------

    def clear(self) -> None:
        self._edits = []
        self._position = 0

    @property
    def can_undo(self) -> bool:
        return self._position > 0

    @property
    def can_redo(self) -> bool:
        return self._position < len(self._edits)

    @property
    def undo_label(self) -> str:
        return self._edits[self._position - 1].label if self.can_undo else ""

    @property
    def redo_label(self) -> str:
        return self._edits[self._position].label if self.can_redo else ""

    def __len__(self) -> int:
        return len(self._edits)

    # --- edits ------------------------------------------------------------------------

    def record(self, before: SceneModel, before_selection: Selection, after: SceneModel,
               after_selection: Selection, label: str) -> None:
        """Record an applied edit. Both scenes are copied, so callers may keep mutating theirs."""
        del self._edits[self._position:]
        self._edits.append(SceneEdit(SceneState(deepcopy(before), tuple(before_selection)),
                                     SceneState(deepcopy(after), tuple(after_selection)), label))
        if len(self._edits) > self._limit:
            self._edits.pop(0)
        self._position = len(self._edits)

    def undo(self) -> Optional[SceneState]:
        """Step back one edit and return a copy of the state before it (None if none)."""
        if not self.can_undo:
            return None
        self._position -= 1
        state = self._edits[self._position].before
        return SceneState(deepcopy(state.scene), state.selection)

    def redo(self) -> Optional[SceneState]:
        """Re-apply the next undone edit and return a copy of the state after it (None if none)."""
        if not self.can_redo:
            return None
        state = self._edits[self._position].after
        self._position += 1
        return SceneState(deepcopy(state.scene), state.selection)
