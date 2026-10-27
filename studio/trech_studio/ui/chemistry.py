"""Chemistry authoring and engine-output inspection. No chemistry is computed here."""
from __future__ import annotations

import json
from typing import Any, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QComboBox, QCheckBox,
)


class ChemistryPanel(QWidget):
    open_requested = Signal()
    run_requested = Signal()
    scaffold_requested = Signal()
    import_requested = Signal()
    export_requested = Signal()
    view_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        note = QLabel("Edit explicit atoms and declared bonds, then run TRECH. Coordinates are authored; "
                      "stability, polarization and reaction mechanisms require validated learned models.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        self.open_button = QPushButton("Open chemistry scenario")
        self.run_button = QPushButton("Run chemistry ▶")
        self.open_button.clicked.connect(self.open_requested)
        self.run_button.clicked.connect(self.run_requested)
        self.run_button.setEnabled(False)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.run_button)
        layout.addLayout(buttons)
        self.view_combo = QComboBox()
        self.view_combo.setMinimumContentsLength(20)
        self.view_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.view_combo.addItem("Molecular structures", "structure")
        self.view_combo.currentIndexChanged.connect(lambda _: self.view_requested.emit(self.view_combo.currentData()))
        layout.addWidget(self.view_combo)
        view_note = QLabel("Density surfaces show supplied probability/number density, not sharp molecular boundaries. "
                           "Nuclear ensemble samples use fm and have no physical clock.")
        view_note.setWordWrap(True)
        layout.addWidget(view_note)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        editor = QWidget()
        form = QVBoxLayout(editor)
        draft_note = QLabel("Single-entity draft. Scene JSON overrides this table while enabled; add the draft as a molecule to include it there.")
        draft_note.setWordWrap(True)
        form.addWidget(draft_note)
        load_scaffold = QPushButton("Load scaffold selected in Options")
        load_scaffold.clicked.connect(self.scaffold_requested)
        form.addWidget(load_scaffold)
        self.atoms = QTableWidget(0, 5)
        self.atoms.setHorizontalHeaderLabels(["Element", "A", "x (Å)", "y (Å)", "z (Å)"])
        self.atoms.horizontalHeaderItem(1).setToolTip("Mass number; leave blank for natural isotopic composition")
        for col, width in enumerate([65, 55, 75, 75, 75]):
            self.atoms.setColumnWidth(col, width)
        self.atoms.setMinimumHeight(180)
        self.atoms.horizontalHeader().setStretchLastSection(True)
        form.addWidget(self.atoms, 1)
        atom_buttons = QHBoxLayout()
        add = QPushButton("Add atom")
        remove = QPushButton("Remove selected atom")
        add.clicked.connect(self.add_atom)
        remove.clicked.connect(self.remove_atom)
        atom_buttons.addWidget(add)
        atom_buttons.addWidget(remove)
        form.addLayout(atom_buttons)
        bond_note = QLabel("Declared bonds: JSON [index, index, order?]; indices start at 0. Omitted order is unknown.")
        bond_note.setWordWrap(True)
        form.addWidget(bond_note)
        self.bonds = QPlainTextEdit("[]")
        self.bonds.setMaximumHeight(65)
        form.addWidget(self.bonds)
        charge_row = QHBoxLayout()
        charge_row.addWidget(QLabel("Net molecular charge (e)"))
        self.charge = QSpinBox()
        self.charge.setRange(-256, 256)
        charge_row.addWidget(self.charge)
        form.addLayout(charge_row)
        self.tabs.addTab(editor, "Structure")
        scene_tab = QWidget()
        scene_layout = QVBoxLayout(scene_tab)
        self.scene_enabled = QCheckBox("Use multi-molecule JSON scene instead of the single-structure draft")
        scene_layout.addWidget(self.scene_enabled)
        scene_buttons = QHBoxLayout()
        for label, signal in (("Import JSON…", self.import_requested), ("Export JSON…", self.export_requested)):
            button = QPushButton(label)
            button.clicked.connect(signal)
            scene_buttons.addWidget(button)
        append = QPushButton("Add structure as molecule")
        append.clicked.connect(self.append_molecule)
        scene_buttons.addWidget(append)
        scene_layout.addLayout(scene_buttons)
        self.scene_json = QPlainTextEdit()
        self.scene_json.setPlaceholderText("trech_chemistry_scene_v1: molecules [{id,structure,position,rotation_deg}], links, optional timed density frames")
        scene_layout.addWidget(self.scene_json)
        self.tabs.addTab(scene_tab, "Scene JSON")
        reaction = QWidget()
        reaction_layout = QVBoxLayout(reaction)
        text = QLabel("Optional JSON: species [{name, count, structure}], channels [{name, delta}], "
                      "modelPath and dt. TRECH derives atom/isotope/charge conservation from the structures. "
                      "Without a supplied hazard model the inventory stays unchanged. "
                      "This prototype reports discrete inventories; it does not animate atomistic reaction paths.")
        text.setWordWrap(True)
        reaction_layout.addWidget(text)
        self.reaction = QPlainTextEdit()
        self.reaction.setPlaceholderText('Leave empty for structure inspection. See docs/chemistry_mode.md for the reaction contract.')
        reaction_layout.addWidget(self.reaction)
        self.tabs.addTab(reaction, "Reaction experiment")
        self.results = QPlainTextEdit()
        self.results.setReadOnly(True)
        self.results.setPlainText("No chemistry run loaded. Geant4 facts and missing model coverage will appear here.")
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        restore = QPushButton("Use loaded run structure as draft")
        restore.clicked.connect(self.restore_run)
        results_layout.addWidget(restore)
        results_layout.addWidget(self.results)
        self.tabs.addTab(results_tab, "Engine results")
        self.status = QLabel("Open the chemistry scenario to begin.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._bound = False
        self._last_state = None
        self.atoms.cellChanged.connect(self._draft_changed)
        self.bonds.textChanged.connect(self._draft_changed)
        self.charge.valueChanged.connect(self._draft_changed)
        self.reaction.textChanged.connect(self._draft_changed)
        self.scene_json.textChanged.connect(self._draft_changed)
        self.setMinimumWidth(360)

    def set_active(self, active: bool) -> None:
        self._bound = active
        self.run_button.setEnabled(active)

    def _draft_changed(self, *_args) -> None:
        self.status.setText("Draft edited. Run TRECH to update the 3D structure and engine results.")

    def restore_run(self) -> None:
        if self._last_state is None:
            self.status.setText("Open a chemistry run output first.")
            return
        state = self._last_state
        if not self._bound:
            self.open_requested.emit()
        self.set_structure(state["structure"])
        if state.get("scene"):
            self.set_scene_document(state["scene"])
        plan = state.get("reaction_plan")
        self.reaction.setPlainText(json.dumps(plan, indent=2) if plan else "")
        self.tabs.setCurrentIndex(0)

    def set_structure(self, structure: dict[str, Any]) -> None:
        atoms = structure.get("atoms", [])
        self.atoms.setRowCount(len(atoms))
        self.atoms.setVerticalHeaderLabels([str(i) for i in range(len(atoms))])
        for row, atom in enumerate(atoms):
            values = [atom["element"], atom.get("massNumber", ""), *atom["position"]]
            for col, value in enumerate(values):
                self.atoms.setItem(row, col, QTableWidgetItem(str(value)))
        self.bonds.setPlainText(json.dumps(structure.get("bonds", [])))
        self.charge.setValue(int(structure.get("charge", 0)))
        self.status.setText("Authored structure. Run TRECH to validate and inspect it in 3D.")

    def add_atom(self) -> None:
        row = self.atoms.rowCount()
        self.atoms.insertRow(row)
        self.atoms.setVerticalHeaderLabels([str(i) for i in range(row + 1)])
        for col, value in enumerate(["H", "", "0", "0", "0"]):
            self.atoms.setItem(row, col, QTableWidgetItem(value))

    def remove_atom(self) -> None:
        row = self.atoms.currentRow()
        if row < 0:
            return
        # This is index bookkeeping over authored bonds, never valence inference.
        try:
            bonds = json.loads(self.bonds.toPlainText())
            if not isinstance(bonds, list) or any(not isinstance(b, list) or len(b) not in (2, 3)
                or any(type(i) is not int for i in b) for b in bonds):
                raise ValueError("Bonds must be arrays of integer indices/order")
            rewritten = [[i - int(i > row) for i in b[:2]] + b[2:]
                         for b in bonds if row not in b[:2]]
        except (ValueError, TypeError) as exc:
            self.status.setText(f"Fix bond JSON before removing an atom: {exc}")
            return
        self.atoms.removeRow(row)
        self.atoms.setVerticalHeaderLabels([str(i) for i in range(self.atoms.rowCount())])
        self.bonds.setPlainText(json.dumps(rewritten))

    def structure(self) -> dict[str, Any]:
        atoms = []
        for row in range(self.atoms.rowCount()):
            values = [self.atoms.item(row, col).text().strip() if self.atoms.item(row, col) else ""
                      for col in range(5)]
            atom = {"element": values[0], "position": [float(v) for v in values[2:]]}
            if values[1]:
                atom["massNumber"] = int(values[1])
            atoms.append(atom)
        return {"atoms": atoms, "bonds": json.loads(self.bonds.toPlainText()), "charge": self.charge.value()}

    def command_args(self) -> list[str]:
        if not self._bound:
            return []
        # Encode through JSON once per argument; QProcess receives an argument list.
        structure = None if self.scene_enabled.isChecked() else json.dumps(self.structure(), allow_nan=False, separators=(",", ":"))
        reaction = self.reaction.toPlainText().strip()
        if reaction:
            json.loads(reaction)  # syntax feedback only; all chemistry validation is in TRECH
        args = ["--param", "reaction_json=" + json.dumps(reaction)]
        if structure is not None:
            args = ["--param", "structure_json=" + json.dumps(structure)] + args
        if self.scene_enabled.isChecked():
            scene = json.dumps(self.scene_document(), allow_nan=False, separators=(",", ":"))
            args += ["--param", "scene_json=" + json.dumps(scene), "--param", 'scene_file=""']
        return args

    def scene_document(self) -> dict:
        raw = json.loads(self.scene_json.toPlainText())
        if not isinstance(raw, dict):
            raise ValueError("Scene JSON must be an object")
        return raw

    def set_scene_document(self, scene: dict) -> None:
        self.scene_json.setPlainText(json.dumps(scene, indent=2, ensure_ascii=False))
        self.scene_enabled.setChecked(True)

    def append_molecule(self) -> None:
        try:
            scene = self.scene_document() if self.scene_json.toPlainText().strip() else {"schema": "trech_chemistry_scene_v1", "molecules": []}
            names = {m["id"] for m in scene["molecules"]}
            i = 0
            while f"molecule_{i}" in names:
                i += 1
            scene["molecules"].append({"id": f"molecule_{i}", "structure": self.structure(), "position": [0, 0, 0]})
            self.set_scene_document(scene)
            self.status.setText("Added an entity. Edit its explicit position/rotation in Scene JSON, then run TRECH.")
        except (ValueError, TypeError, KeyError) as exc:
            self.status.setText(f"Invalid scene draft: {exc}")

    def set_views(self, views: list, default: str) -> None:
        self.view_combo.blockSignals(True)
        self.view_combo.clear()
        for key, label in views:
            self.view_combo.addItem(label, key)
        self.view_combo.setCurrentIndex(max(0, self.view_combo.findData(default)))
        self.view_combo.blockSignals(False)
        self.view_combo.setToolTip(self.view_combo.currentText())

    def show_run(self, run) -> None:
        states = [e.payload for e in run.emits if e.tag == "chemistry_state" and isinstance(e.payload, dict)]
        if not states:
            self._last_state = None
            self.results.setPlainText("This run has no chemistry_state output.")
            return
        state = states[-1]
        self._last_state = state
        steps = [e.payload for e in run.emits if e.tag == "chemistry_reaction_step"]
        report = {"mode": state.get("mode"), "geometry_source": state.get("geometry_source"),
                  "transport_scope": state.get("transport_scope"), "capabilities": state.get("capabilities"),
                  "electron_count": state.get("electron_count"), "atoms": state.get("atoms"),
                  "particle_response": state.get("particle_response"),
                  "geant4_material": state.get("geant4_material"),
                  "molecules": state.get("scene", {}).get("molecules"),
                  "probability_frames": sum(e.tag == "quantum_frame" for e in run.emits),
                  "nuclear_ensembles": [e.payload for e in run.emits if e.tag == "chemistry_nuclear_ensemble"],
                  "reaction_steps_recorded": len(steps), "last_reaction_step": steps[-1] if steps else None}
        self.results.setPlainText(json.dumps(report, indent=2, ensure_ascii=False))
        self.status.setText("Showing engine-emitted results. The 3D view contains authored coordinates/bonds; "
                            "sphere sizes and colors are display choices. Edits require a new run.")
