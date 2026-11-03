"""Property inspector for the selected scene node.

Transport fields author a separate scene draft. Applying does not run physics or patch a live
kernel; the window validates the candidate against the lossless transport writer before use.
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Optional

from PySide6.QtCore import Signal

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..scene.model import SceneModel, Shape
from ..precision import PrecisionReport


def _fmt_vec(v) -> str:
    return "(" + ", ".join(f"{x:.3g}" for x in v) + ")"


class Inspector(QScrollArea):
    """Shows recorded properties and edits exportable transport scene drafts."""

    edit_requested = Signal(object, str, str)  # detached candidate, node kind/name

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._scene: Optional[SceneModel] = None
        self._precision: Optional[PrecisionReport] = None
        self._editable = False
        self._editing_reason = "Load an exportable transport run to edit its scene."
        self._draft = False
        self._fields = {}
        self._body = QWidget(self)
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self.setWidget(self._body)
        self._show_placeholder("Select a node in the outliner.")

    def set_scene(self, scene: SceneModel) -> None:
        self._scene = scene
        self._show_placeholder("Select a node in the outliner.")

    def set_editing(self, enabled: bool, reason: str = "", *, draft: bool = False) -> None:
        self._editable = enabled
        self._editing_reason = reason
        self._draft = draft

    def show_edit_error(self, message: str) -> None:
        self._edit_status.setText(message)

    def set_precision(self, precision: Optional[PrecisionReport]) -> None:
        self._precision = precision

    # --- routing ------------------------------------------------------------------------

    def show_node(self, kind: str, name: str) -> None:
        if self._scene is None:
            return
        if kind == "world":
            self._show_world()
        elif kind == "volume":
            self._show_volume(name)
        elif kind == "beam":
            self._show_beam(name)
        elif kind == "material":
            self._show_material(name)

    # --- renderers ----------------------------------------------------------------------

    def _clear(self) -> None:
        self._fields = {}
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _show_placeholder(self, text: str) -> None:
        self._clear()
        label = QLabel(text, self._body)
        label.setProperty("role", "warn")
        self._layout.addWidget(label)
        self._layout.addStretch(1)

    def _section(self, title: str) -> QFormLayout:
        header = QLabel(title, self._body)
        header.setStyleSheet("font-weight: 700; padding-top: 6px;")
        self._layout.addWidget(header)
        form = QFormLayout()
        form.setLabelAlignment(form.labelAlignment())
        container = QWidget(self._body)
        container.setLayout(form)
        self._layout.addWidget(container)
        return form

    def _edit_note(self) -> None:
        note = QLabel(
            "Scene draft — no simulation results. Export scene scenario to save; open the exported JS to run it."
            if self._draft else
            "Apply authors a scene draft; recorded playback is hidden until another run is loaded."
            if self._editable else self._editing_reason, self._body)
        note.setWordWrap(True)
        note.setProperty("role", "warn")
        self._layout.addWidget(note)

    def _text_field(self, form, label, key, value):
        field = QLineEdit(str(value), self._body)
        field.setObjectName("scene_" + key)
        self._fields[key] = field
        form.addRow(label, field)
        return field

    def _number_field(self, form, label, key, value):
        return self._text_field(form, label, key, repr(float(value)))

    def _vector_field(self, form, label, key, value):
        return self._text_field(form, label, key, ", ".join(repr(float(x)) for x in value))

    def _material_field(self, form, label, key, value):
        field = QComboBox(self._body)
        names = {value, self._scene.world_material, self._scene.medium_material}
        names.update(m.name for m in self._scene.materials)
        names.update(v.material for v in self._scene.volumes)
        field.addItems(sorted(n for n in names if n))
        field.setCurrentText(value)
        field.setObjectName("scene_" + key)
        self._fields[key] = field
        form.addRow(label, field)

    def _apply_button(self, kind, name):
        self._edit_status = QLabel(self._body)
        self._edit_status.setWordWrap(True)
        self._edit_status.setProperty("role", "warn")
        button = QPushButton("Apply scene draft", self._body)
        button.setObjectName("apply_scene_draft")
        button.clicked.connect(lambda: self._request_edit(kind, name))
        self._layout.addWidget(button)
        self._layout.addWidget(self._edit_status)

    def _request_edit(self, kind, name):
        def number(key):
            value = float(self._fields[key].text())
            if not math.isfinite(value):
                raise ValueError(f"{key} must be finite")
            return value

        def vector(key):
            value = tuple(float(x.strip()) for x in self._fields[key].text().split(","))
            if len(value) != 3 or not all(math.isfinite(x) for x in value):
                raise ValueError(f"{key} needs three finite coordinates separated by commas")
            return value

        candidate = deepcopy(self._scene)
        try:
            if kind == "world":
                candidate.world_size_mm = number("world_size")
                candidate.world_material = self._fields["world_material"].currentText()
            elif kind == "volume":
                vol = candidate.volume_by_name(name)
                vol.material = self._fields["material"].currentText()
                vol.position_mm = vector("position")
                vol.rotation_deg = vector("rotation")
                shape_type = self._fields["shape"].currentText()
                if shape_type == "box":
                    vol.shape = Shape(type=shape_type, size_mm=vector("size"))
                else:
                    vol.shape = Shape(type=shape_type, outer_radius_mm=number("outer_radius"),
                                      inner_radius_mm=number("inner_radius"),
                                      length_mm=number("length") if shape_type != "sphere" else 0.)
            elif kind == "beam":
                beam = next(b for b in candidate.beams if (b.name or b.particle) == name)
                beam.particle = self._fields["particle"].text().strip()
                if not beam.particle:
                    raise ValueError("Particle must be nonempty; TRECH validates the particle name on run")
                beam.energy_ev = number("energy")
            self.edit_requested.emit(candidate, kind, name)
        except ValueError as exc:
            self.show_edit_error(str(exc))

    def _show_world(self) -> None:
        self._clear()
        s = self._scene
        self._edit_note()
        world = self._section("World")
        if self._editable:
            self._material_field(world, "material", "world_material", s.world_material)
            self._number_field(world, "size (mm)", "world_size", s.world_size_mm)
            self._apply_button("world", "")
        else:
            world.addRow("material", QLabel(s.world_material))
            world.addRow("size (mm)", QLabel(f"{s.world_size_mm:.3g}"))
        if s.medium_size_mm:
            world.addRow("medium", QLabel(f"{s.medium_material} @ {s.medium_size_mm:.3g} mm"))
        run = self._section("Recorded run" if self._draft else "Run")
        run.addRow("events", QLabel(str(s.run.n_events)))
        run.addRow("seed", QLabel(str(s.run.seed)))
        run.addRow("determinism", QLabel(s.run.determinism_mode))
        if self._precision is not None:
            sim = self._precision.simulation
            rep = self._precision.representation
            precision = self._section("Precision")
            precision.addRow("MC events", QLabel(str(sim.get("events", 0))))
            if sim.get("trajectory_segments"):
                precision.addRow("tracks loaded / recorded", QLabel(
                    f"{sim.get('loaded_trajectories', 0)} / {sim.get('recorded_trajectories', 0)}"
                ))
                precision.addRow("native segments", QLabel(str(sim["trajectory_segments"])))
                precision.addRow("tracks dropped / capped", QLabel(
                    f"{sim.get('trajectory_dropped', 0)} / {sim.get('trajectory_capped', 0)}"
                ))
                precision.addRow("medium labels", QLabel(
                    f"{float(sim.get('medium_label_coverage', 0.0)) * 100.0:.1f} %"
                ))
                precision.addRow("process labels", QLabel(
                    f"{float(sim.get('interaction_label_coverage', 0.0)) * 100.0:.1f} %"
                ))
                precision.addRow("beam display", QLabel(
                    f"{float(rep.get('beam_display_strength', 0.0)) * 100.0:.1f} %"
                ))
                precision.addRow("ribbon width / alpha", QLabel(
                    f"{float(rep.get('beam_ribbon_width_scale', 0.0)):.3f} / "
                    f"{float(rep.get('beam_ribbon_opacity', 0.0)):.3f}"
                ))
            elif rep.get("particle_frames"):
                precision.addRow("emitted frames", QLabel(str(rep["particle_frames"])))
                precision.addRow("timeline", QLabel(str(rep.get("timeline_selection"))))
            pixels = rep.get("output_pixels")
            if pixels:
                precision.addRow("raster / supersample", QLabel(
                    f"{pixels[0]}×{pixels[1]} / {rep.get('supersample', 1)}×"
                ))
            note = QLabel("Counts/caps are simulation precision. Ribbon/sprite width, alpha, and "
                          "raster size are representation precision and never alter engine data.")
            note.setWordWrap(True)
            note.setProperty("role", "warn")
            self._layout.addWidget(note)
        self._layout.addStretch(1)

    def _show_volume(self, name: str) -> None:
        self._clear()
        vol = self._scene.volume_by_name(name)
        if vol is None:
            self._show_placeholder(f"volume '{name}' not found")
            return
        self._edit_note()
        form = self._section(f"Volume · {vol.name}")
        if self._editable and vol.shape.type in ("box", "sphere", "tube", "cylinder"):
            self._material_field(form, "material", "material", vol.material)
            shape = QComboBox(self._body)
            shape.addItems(["box", "sphere", "tube", "cylinder"])
            shape.setCurrentText(vol.shape.type)
            self._fields["shape"] = shape
            form.addRow("shape", shape)
            self._vector_field(form, "box size (mm)", "size", vol.shape.size_mm)
            self._number_field(form, "outer R (mm)", "outer_radius", vol.shape.outer_radius_mm)
            self._number_field(form, "inner R (mm)", "inner_radius", vol.shape.inner_radius_mm)
            self._number_field(form, "length (mm)", "length", vol.shape.length_mm)
            self._vector_field(form, "position (mm)", "position", vol.position_mm)
            self._vector_field(form, "rotation (deg)", "rotation", vol.rotation_deg)
            def shape_fields(kind):
                self._fields["size"].setEnabled(kind == "box")
                self._fields["outer_radius"].setEnabled(kind != "box")
                self._fields["inner_radius"].setEnabled(kind != "box")
                self._fields["length"].setEnabled(kind in ("tube", "cylinder"))
            shape.currentTextChanged.connect(shape_fields)
            shape_fields(vol.shape.type)
            self._apply_button("volume", name)
        else:
            form.addRow("material", QLabel(vol.material))
            form.addRow("shape", QLabel(vol.shape.type))
            form.addRow("size (mm)", QLabel(_fmt_vec(vol.shape.size_mm)))
            if vol.shape.outer_radius_mm:
                form.addRow("outer R (mm)", QLabel(f"{vol.shape.outer_radius_mm:.3g}"))
            form.addRow("position (mm)", QLabel(_fmt_vec(vol.position_mm)))
            form.addRow("rotation (deg)", QLabel(_fmt_vec(vol.rotation_deg)))
        form.addRow("tags", QLabel(", ".join(vol.tags) or "—"))
        form.addRow("score edep", QLabel("yes" if vol.score_edep else "no"))

        # How this volume renders: physics-derived look (at its own thickness) + authored hints.
        appear = self._scene.volume_appearance(vol)
        hint = vol.render_hint()
        look = self._section("Appearance")
        look.addRow("thickness (mm)", QLabel(f"{vol.path_length_mm():.4g}"))
        if appear is not None:
            look.addRow("derived look", QLabel(appear.descriptor))
            look.addRow("transmittance", QLabel(f"{appear.transmittance * 100.0:.1f} %"))
        else:
            look.addRow("derived look", QLabel("no derived optics (neutral placeholder)"))
        if not hint.is_empty:
            parts = []
            if hint.hidden:
                parts.append("hidden")
            if hint.solid:
                parts.append("solid")
            if hint.emissive:
                parts.append("emissive")
            if hint.opacity is not None:
                parts.append(f"opacity={hint.opacity:.2g}")
            if hint.color is not None:
                parts.append("color=" + _fmt_vec(hint.color))
            if hint.tint is not None:
                parts.append("tint=" + _fmt_vec(hint.tint))
            look.addRow("render hint", QLabel(", ".join(parts)))
            note = QLabel("render hint is an authored viz_* override — a rendering choice, "
                          "not physics.")
            note.setWordWrap(True)
            note.setProperty("role", "warn")
            self._layout.addWidget(note)
        self._layout.addStretch(1)

    def _show_beam(self, name: str) -> None:
        self._clear()
        beam = next((b for b in self._scene.beams if (b.name or b.particle) == name), None)
        if beam is None:
            self._show_placeholder(f"beam '{name}' not found")
            return
        self._edit_note()
        form = self._section(f"Beam · {beam.name or beam.particle}")
        if self._editable and (len(self._scene.beams) == 1 or all(b.name for b in self._scene.beams)):
            self._text_field(form, "particle", "particle", beam.particle)
            self._number_field(form, "energy (eV)", "energy", beam.energy_ev)
            self._apply_button("beam", name)
        else:
            form.addRow("particle", QLabel(beam.particle))
            form.addRow("energy (eV)", QLabel(f"{beam.energy_ev:.4g}"))
        form.addRow("direction", QLabel(_fmt_vec(beam.direction)))
        form.addRow("active", QLabel("yes" if beam.active else "no"))
        self._layout.addStretch(1)

    def _show_material(self, name: str) -> None:
        self._clear()
        mat = self._scene.material_by_name(name)
        if mat is None:
            self._show_placeholder(f"material '{name}' not found")
            return
        form = self._section(f"Material · {mat.name}")
        form.addRow("density (g/cm³)", QLabel(f"{mat.density_gcm3:.4g}"))
        if mat.smiles:
            form.addRow("SMILES", QLabel(mat.smiles))
        if mat.optics_available:
            # Derive the look at a nominal 20 mm body (opacity is thickness-dependent; the rest
            # — reflectance, tint, refractive index — is not). Volumes show their own thickness.
            ap = mat.appearance(path_mm=20.0)
            optics = self._section("Derived optics (Geant4)")
            optics.addRow("refractive index n", QLabel(f"{ap.refractive_index:.4g}"))
            optics.addRow("reflectivity (Fresnel R₀)", QLabel(f"{ap.reflectance * 100.0:.2f} %"))
            optics.addRow("abs length (mm)", QLabel(f"{mat.mean_absorption_length_mm:.4g}"))
            if mat.mean_scatter_length_mm:
                optics.addRow("scatter length (mm)", QLabel(f"{mat.mean_scatter_length_mm:.4g}"))
            optics.addRow("transmittance @20mm", QLabel(f"{ap.transmittance * 100.0:.1f} %"))
            optics.addRow("look", QLabel(ap.descriptor))
            note = QLabel(ap.note)
            note.setWordWrap(True)
            note.setProperty("role", "warn")
            self._layout.addWidget(note)
        else:
            note = QLabel("no derived optics for this material in this run — rendered with a "
                          "neutral placeholder colour (a labelled rendering choice).")
            note.setWordWrap(True)
            note.setProperty("role", "warn")
            self._layout.addWidget(note)
        self._layout.addStretch(1)
