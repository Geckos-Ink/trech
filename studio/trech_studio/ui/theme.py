"""Dark theme QSS for the Studio shell (a small, self-contained stylesheet)."""

from __future__ import annotations

DARK_QSS = """
QMainWindow, QWidget { background: #16181d; color: #d7dae0; }
QMainWindow::separator { background: #24272e; width: 4px; height: 4px; }

QDockWidget { titlebar-close-icon: none; }
QDockWidget::title {
    background: #1d2027; padding: 6px 10px; font-weight: 600;
    border-bottom: 1px solid #24272e;
}

QTreeWidget, QListWidget, QPlainTextEdit, QTextEdit {
    background: #12141a; border: 1px solid #24272e; selection-background-color: #2d4a6b;
}
QTreeWidget::item:selected, QListWidget::item:selected { background: #2d4a6b; }

QHeaderView::section { background: #1d2027; padding: 4px; border: none; }

QPushButton {
    background: #262b34; border: 1px solid #333944; border-radius: 4px; padding: 5px 12px;
}
QPushButton:hover { background: #2f3540; }
QPushButton:pressed { background: #223049; }
QPushButton:disabled { color: #6b7078; background: #1c2028; }

QLabel[role="run"] { color: #7fd18b; font-weight: 600; }
QLabel[role="warn"] { color: #e0b25a; }
QLabel[role="err"] { color: #e07a7a; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #12141a; border: 1px solid #333944; border-radius: 3px; padding: 3px 6px;
}
QStatusBar { background: #1d2027; }
QTabBar::tab { background: #1d2027; padding: 6px 12px; }
QTabBar::tab:selected { background: #262b34; }
QScrollBar:vertical, QScrollBar:horizontal { background: #16181d; }
QScrollBar::handle { background: #333944; border-radius: 4px; }
"""
