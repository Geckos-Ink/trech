"""Right-sidebar controls for typed ``TRECH_VALUE`` declarations."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..engine.parameters import ScenarioParameter


class ScenarioOptions(QScrollArea):
    """Build native Qt controls from engine-validated scenario declarations."""

    values_changed = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._body = QWidget(self)
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self.setWidget(self._body)
        self._parameters: tuple[ScenarioParameter, ...] = ()
        self._widgets: Dict[str, QWidget] = {}
        self._show_message("Open a JavaScript scenario to see its custom options.")

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._widgets.clear()

    def _show_message(self, message: str) -> None:
        self._clear()
        label = QLabel(message, self._body)
        label.setWordWrap(True)
        label.setProperty("role", "warn")
        self._layout.addWidget(label)
        self._layout.addStretch(1)

    def show_error(self, message: str) -> None:
        self._parameters = ()
        self._show_message(message)

    def set_parameters(
        self, parameters: Iterable[ScenarioParameter], preserve_values: bool = True
    ) -> None:
        previous = self.values() if preserve_values else {}
        self._parameters = tuple(parameters)
        if not self._parameters:
            self._show_message("This scenario declares no custom TRECH_VALUE options.")
            return
        self._clear()
        grouped: Dict[str, list[ScenarioParameter]] = {}
        for parameter in self._parameters:
            grouped.setdefault(parameter.group or "Scenario", []).append(parameter)
        for group_name, group_parameters in grouped.items():
            box = QGroupBox(group_name, self._body)
            form = QFormLayout(box)
            for parameter in group_parameters:
                widget = self._make_widget(parameter)
                if parameter.id in previous:
                    self._set_widget_value(widget, parameter, previous[parameter.id])
                self._widgets[parameter.id] = widget
                label = parameter.label + (f" ({parameter.unit})" if parameter.unit else "")
                if parameter.description:
                    widget.setToolTip(parameter.description)
                form.addRow(label, widget)
            self._layout.addWidget(box)

        reset = QPushButton("Reset to defaults", self._body)
        reset.clicked.connect(self.reset_defaults)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(reset)
        holder = QWidget(self._body)
        holder.setLayout(row)
        self._layout.addWidget(holder)
        self._layout.addStretch(1)

    def _make_widget(self, parameter: ScenarioParameter) -> QWidget:
        if parameter.type == "number":
            widget = QDoubleSpinBox(self._body)
            widget.setDecimals(6)
            widget.setRange(
                parameter.minimum if parameter.minimum is not None else -1.0e12,
                parameter.maximum if parameter.maximum is not None else 1.0e12,
            )
            widget.setSingleStep(parameter.step if parameter.step is not None else 0.1)
            widget.setValue(float(parameter.value))
            widget.valueChanged.connect(self._emit_values)
            return widget
        if parameter.type == "integer":
            widget = QSpinBox(self._body)
            widget.setRange(
                int(parameter.minimum) if parameter.minimum is not None else -2147483647,
                int(parameter.maximum) if parameter.maximum is not None else 2147483647,
            )
            widget.setSingleStep(int(parameter.step) if parameter.step is not None else 1)
            widget.setValue(int(parameter.value))
            widget.valueChanged.connect(self._emit_values)
            return widget
        if parameter.type == "boolean":
            widget = QCheckBox(self._body)
            widget.setChecked(bool(parameter.value))
            widget.toggled.connect(self._emit_values)
            return widget
        if parameter.type == "choice":
            widget = QComboBox(self._body)
            for choice in parameter.choices:
                widget.addItem(str(choice), choice)
            self._set_widget_value(widget, parameter, parameter.value)
            widget.currentIndexChanged.connect(self._emit_values)
            return widget
        widget = QLineEdit(str(parameter.value), self._body)
        widget.textChanged.connect(self._emit_values)
        return widget

    @staticmethod
    def _set_widget_value(
        widget: QWidget, parameter: ScenarioParameter, value: Any
    ) -> None:
        if isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value))
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QComboBox):
            index = next(
                (i for i in range(widget.count()) if widget.itemData(i) == value), -1
            )
            if index >= 0:
                widget.setCurrentIndex(index)
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))

    def values(self) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for parameter in self._parameters:
            widget = self._widgets.get(parameter.id)
            if isinstance(widget, (QDoubleSpinBox, QSpinBox)):
                values[parameter.id] = widget.value()
            elif isinstance(widget, QCheckBox):
                values[parameter.id] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                values[parameter.id] = widget.currentData()
            elif isinstance(widget, QLineEdit):
                values[parameter.id] = widget.text()
        return values

    def command_args(self) -> list[str]:
        args: list[str] = []
        values = self.values()
        for parameter in self._parameters:
            encoded = json.dumps(values[parameter.id], separators=(",", ":"))
            args.extend(["--param", f"{parameter.id}={encoded}"])
        return args

    def reset_defaults(self) -> None:
        for parameter in self._parameters:
            widget = self._widgets.get(parameter.id)
            if widget is not None:
                self._set_widget_value(widget, parameter, parameter.default)
        self._emit_values()

    def _emit_values(self, *_args: object) -> None:
        self.values_changed.emit(self.values())
