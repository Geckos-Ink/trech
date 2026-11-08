"""Engine-evaluated JS process descriptions; declarative UI only, no solver."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget
from ..recipe_status import build_recipe_status, overall_summary, stage_details, stage_summary
from ..render.frame_notes import frame_notes


class ProcessesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.description = QLabel("No JS process description supplied.", self)
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.streams = QComboBox(self)
        self.streams.setToolTip("Choose an engine-recorded material stream; no frames are synthesized")
        self.streams.addItem("Automatic preview", None)
        layout.addWidget(self.streams)
        self.notes = QLabel("No recorded frame selected.", self)
        self.notes.setTextFormat(Qt.PlainText)
        self.notes.setWordWrap(True)
        self.notes.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.notes)
        self._playback = None
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Process", "Source / role"])
        layout.addWidget(self.tree)
        self.recipe_summary = QLabel("No process_recipe_state emits recorded.", self)
        self.recipe_summary.setWordWrap(True)
        self.recipe_summary.setTextFormat(Qt.PlainText)
        layout.addWidget(self.recipe_summary)
        self.recipe = QTreeWidget(self)
        self.recipe.setHeaderLabels(["Recipe stage", "Recorded execution"])
        self.recipe.setToolTip("Engine-recorded operator reports per stage; nothing is re-run or interpolated")
        layout.addWidget(self.recipe)
        self.recipe_status = None

    def set_description(self, descriptor, models):
        self.description.setText(descriptor.get("description") or "Declared processes and configured models.")
        self.tree.clear()
        for process in descriptor.get("processes", []):
            item = QTreeWidgetItem(self.tree, [process.get("label") or process.get("id", ""),
                                              process.get("kind", "")])
            item.setToolTip(0, process.get("description", ""))
            QTreeWidgetItem(item, [process.get("description", ""), "JS description; execution is owned by the engine"])
        if isinstance(models, dict):
            models = [models]
        for model in models or []:
            QTreeWidgetItem(self.tree, [str(model.get("name", "")),
                f"model · {model.get('scale', 'unscaled')} · {model.get('path', '')}"])
        self.tree.expandAll()

    def set_streams(self, emits):
        self.streams.blockSignals(True)
        self.streams.clear()
        self.streams.addItem("Automatic preview", None)
        names = dict.fromkeys(str(e.payload.get("stream") or "") for e in emits
            if e.tag == "material_frame" and isinstance(e.payload, dict))
        for name in names:
            self.streams.addItem(name or "Unnamed material stream", name)
        self.streams.blockSignals(False)

    def set_recipe_reports(self, emits, config=None):
        """Show per-stage recipe execution from recorded ``process_recipe_state`` emits."""
        self.recipe_status = build_recipe_status(emits or [], config)
        self.recipe_summary.setText(overall_summary(self.recipe_status))
        self.recipe.clear()
        for stage in self.recipe_status.stages:
            item = QTreeWidgetItem(self.recipe, [stage.process, stage_summary(stage)])
            for line in stage_details(stage):
                QTreeWidgetItem(item, ["", line])
        self.recipe.expandAll()

    def set_playback(self, playback):
        self._playback = playback
        self.set_cursor(playback.t_max if playback else 0)

    def set_cursor(self, cursor):
        self.notes.setText("\n".join(frame_notes(self._playback, cursor)) or "No recorded frame selected.")
