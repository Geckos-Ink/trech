"""Shared Qt setup for the Studio tests.

Qt allows one application object per process. A module that creates a bare ``QCoreApplication``
first leaves every later ``QApplication.instance() or QApplication([])`` holding a non-GUI app,
and the first ``QWidget`` then aborts the process (seen as ``test_live_lab.py`` followed by
``test_ui_panels.py``, 2026-11-22). Creating the GUI application here, before any test module
is imported, makes every module's ``instance()`` call return it whatever the collection order.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])
