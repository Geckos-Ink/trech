"""Engine-evaluated JS process descriptions; declarative UI only, no solver."""
from PySide6.QtWidgets import QComboBox, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


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
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Process", "Source / role"])
        layout.addWidget(self.tree)

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
