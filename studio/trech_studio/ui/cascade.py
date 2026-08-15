"""Scale-ladder panel: the multi-scale inference cascade, shown as a ladder.

A view over :func:`trech_studio.cascade.build_scale_ladder`. It answers the question the engine
thesis exists for — *what did the engine infer, from what Geant4 base, and how far up the dimension
ladder did it carry it?* — and, in the same breath, *how much should I trust each rung?*

Every badge on screen names a flag the **engine** set (extrapolating past its trained domain, in a
starved region of it, applied off its trained band, no measured accuracy). Studio adds no judgement
of its own, and a stage whose model carries no measured accuracy is labelled as exactly that rather
than being shown with a flattering blank.

Glue only: no parsing, no physics, no re-derivation.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..cascade import BADGE_DID_NOT_RUN, LadderPass, LadderStage, ScaleLadder

_CLEAN_BADGES = frozenset({BADGE_DID_NOT_RUN})


class ScaleLadderPanel(QScrollArea):
    """Scrollable view of every inference pass a run recorded."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._body = QWidget(self)
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(12, 10, 12, 12)
        self._layout.setSpacing(6)
        self.setWidget(self._body)
        self._ladder: Optional[ScaleLadder] = None
        self.show_message("No run loaded yet.")

    # --- public API ---------------------------------------------------------------------

    def ladder(self) -> Optional[ScaleLadder]:
        """The ladder currently displayed (headless tests assert on this)."""
        return self._ladder

    def show_message(self, message: str) -> None:
        self._ladder = None
        self._clear()
        label = QLabel(message, self._body)
        label.setWordWrap(True)
        label.setProperty("role", "warn")
        self._layout.addWidget(label)
        self._layout.addStretch(1)

    def show_ladder(self, ladder: ScaleLadder) -> None:
        self._ladder = ladder
        self._clear()
        if ladder.is_empty:
            self.show_message(
                "This run recorded no inference pass. A scenario surfaces the ladder by emitting "
                "its ctx.cascade / ctx.evolve result (see examples/experiments/"
                "cascade_multiscale_demo.js); a strict-mode run performs no inference at all."
            )
            return

        bands = ladder.bands_bridged
        head = QLabel(
            "<b>scale ladder · "
            + (" → ".join(bands) if bands else "no scale band recorded")
            + f"</b><br/>{len(ladder.passes)} recorded inference pass(es)",
            self._body,
        )
        head.setTextFormat(Qt.RichText)
        head.setWordWrap(True)
        self._layout.addWidget(head)

        for pass_ in ladder.passes:
            self._layout.addWidget(self._rule())
            self._add_pass(pass_)
        self._layout.addStretch(1)

    # --- internals ----------------------------------------------------------------------

    def _add_pass(self, pass_: LadderPass) -> None:
        kind = "cascade (properties)" if pass_.kind == "cascade" else "operator (state change)"
        title = QLabel(f"<b>{_escape(pass_.headline())}</b> — {kind}", self._body)
        title.setTextFormat(Qt.RichText)
        title.setWordWrap(True)
        self._layout.addWidget(title)

        if pass_.occurrences > 1:
            self._layout.addWidget(
                self._note(
                    f"emitted {pass_.occurrences}× in this run; the last one is shown",
                )
            )
        if pass_.seed_keys:
            geant4 = pass_.geant4_seed_keys
            self._layout.addWidget(
                self._note(
                    f"seeded with {len(pass_.seed_keys)} fact(s), "
                    f"{len(geant4)} from the Geant4 base: "
                    + ", ".join(geant4[:6])
                    + ("…" if len(geant4) > 6 else "")
                )
            )
        if pass_.inference_count is not None:
            ood = pass_.out_of_domain_inferences
            text = f"{pass_.inference_count} model evaluation(s)"
            if ood is not None:
                text += f", {ood} out of trained domain"
            self._layout.addWidget(self._note(text))
        if pass_.selection_status and pass_.selection_status != "selected":
            self._layout.addWidget(
                self._note(
                    f"operator selection: {pass_.selection_status} — state was left untouched",
                    warn=True,
                )
            )

        for stage in pass_.stages:
            self._add_stage(stage)

    def _add_stage(self, stage: LadderStage) -> None:
        band = stage.scale or "no band"
        kind = f" · {stage.element_kind}" if stage.element_kind else ""
        line = QLabel(
            f"    <b>{_escape(band)}</b> · {_escape(stage.model)}{_escape(kind)}", self._body
        )
        line.setTextFormat(Qt.RichText)
        line.setWordWrap(True)
        self._layout.addWidget(line)

        badges = stage.badges
        if badges:
            self._layout.addWidget(self._note(" · ".join(badges), warn=True, indent=True))
        if not stage.ran:
            return

        if stage.predicts:
            self._layout.addWidget(
                self._note("predicts " + ", ".join(stage.predicts), indent=True)
            )
        self._layout.addWidget(self._note(stage.accuracy_note(), indent=True))
        self._layout.addWidget(
            self._note(
                stage.joint_note(),
                warn=bool(stage.joint_starved
                          or (stage.elements_joint_starved or 0) > 0
                          or not stage.joint_measured),
                indent=True,
            )
        )
        if stage.trained_scale:
            self._layout.addWidget(
                self._note(f"trained on band(s): {stage.trained_scale}", indent=True)
            )
        if stage.out_of_domain_inputs:
            self._layout.addWidget(
                self._note(
                    "outside its trained domain on: " + ", ".join(stage.out_of_domain_inputs),
                    warn=True,
                    indent=True,
                )
            )
        if stage.starved_inputs:
            self._layout.addWidget(
                self._note(
                    "in an unpopulated region of the trained hull on: "
                    + ", ".join(stage.starved_inputs),
                    warn=True,
                    indent=True,
                )
            )
        if stage.missing_inputs:
            self._layout.addWidget(
                self._note(
                    "declared inputs absent from the context (defaulted to 0): "
                    + ", ".join(stage.missing_inputs),
                    warn=True,
                    indent=True,
                )
            )

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _note(self, text: str, warn: bool = False, indent: bool = False) -> QLabel:
        label = QLabel(("        " if indent else "    ") + text, self._body)
        label.setWordWrap(True)
        if warn:
            label.setProperty("role", "warn")
        return label

    def _rule(self) -> QFrame:
        line = QFrame(self._body)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def stage_summaries(ladder: ScaleLadder) -> List[str]:
    """Flat one-line-per-stage view (used by tests and by the status line)."""
    lines: List[str] = []
    for pass_ in ladder.passes:
        for stage in pass_.stages:
            badges = [b for b in stage.badges if b not in _CLEAN_BADGES]
            suffix = f" [{', '.join(badges)}]" if badges else ""
            lines.append(f"{pass_.tag} · {stage.scale or '-'} · {stage.model}{suffix}")
    return lines
