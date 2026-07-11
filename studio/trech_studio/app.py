"""QApplication bootstrap: build the window, apply the theme, honour startup args, run the loop."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QApplication

from .settings import StudioSettings
from .ui.main_window import StudioWindow
from .ui.theme import DARK_QSS


def run_app(
    settings: StudioSettings,
    open_dir: Optional[str] = None,
    scenario: Optional[str] = None,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("TRECH Studio")
    if settings.background == "dark":
        app.setStyleSheet(DARK_QSS)

    window = StudioWindow(settings)

    if scenario:
        window.open_scenario(Path(scenario))
    if open_dir:
        window.open_output_dir(Path(open_dir))

    window.show()
    return app.exec()
