"""The Qt-embedded wgpu viewport widget (+ a fallback when wgpu is unavailable).

``create_viewport`` returns a QWidget that either:
  - wraps a wgpu canvas driving :class:`SceneRenderer` with orbit/pan/dolly mouse controls, or
  - is a plain message label explaining that the 3D viewport is unavailable (no wgpu / no GPU),
    so the rest of Studio (code editor, output inspection) still launches and works.

Both expose ``set_scene(scene)`` and ``request_redraw()`` so the main window can treat them
uniformly.
"""

from __future__ import annotations

import math
from typing import Optional, Protocol

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..scene.model import SceneModel

# wgpu is optional: import guarded so a fresh checkout without a GPU stack still launches.
#
# The Qt canvas moved packages across wgpu-py releases: modern wgpu-py (>=0.19) ships it in the
# separate ``rendercanvas`` package as ``QRenderWidget``; older wgpu-py exposed it in-tree as
# ``wgpu.gui.qt.WgpuWidget``. Try the new location first, fall back to the old one. (Note:
# ``rendercanvas.qt`` requires a Qt binding to be imported first — the PySide6 imports above
# satisfy that.) Both are QWidget subclasses exposing ``request_draw`` + ``get_context``.
WGPU_AVAILABLE = True
_IMPORT_ERROR = ""
try:  # pragma: no cover - environment dependent
    try:
        from rendercanvas.qt import QRenderWidget as WgpuWidget  # type: ignore
    except Exception:  # noqa: BLE001 - older wgpu-py: canvas lived in wgpu.gui
        from wgpu.gui.qt import WgpuWidget  # type: ignore

    from .renderer import SceneRenderer
except Exception as exc:  # noqa: BLE001 - any import/GPU error must degrade gracefully
    WGPU_AVAILABLE = False
    _IMPORT_ERROR = str(exc)
    WgpuWidget = object  # type: ignore
    SceneRenderer = None  # type: ignore


class ViewportLike(Protocol):
    def set_scene(self, scene: SceneModel) -> None: ...
    def request_redraw(self) -> None: ...


class _FallbackViewport(QWidget):
    """Shown when the 3D viewport cannot initialise. Keeps the app usable."""

    def __init__(self, reason: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel(
            "3D viewport unavailable\n\n"
            f"{reason}\n\n"
            "Install the GPU stack with:  pip install 'wgpu>=0.19' rendercanvas\n"
            "The code editor and output inspector still work.",
            self,
        )
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

    def set_scene(self, scene: SceneModel) -> None:  # noqa: D401 - protocol no-op
        pass

    def request_redraw(self) -> None:
        pass


if WGPU_AVAILABLE:

    class WgpuViewport(WgpuWidget):  # type: ignore[misc]
        """wgpu canvas with an orbit camera.

        Controls: left-drag orbit · middle/right-drag pan · wheel dolly.
        """

        def __init__(self, background: str = "dark", parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._renderer: Optional["SceneRenderer"] = None
            self._background = background
            self._last_pos = None
            self._pending_scene: Optional[SceneModel] = None
            self.setMouseTracking(True)
            # Draw callback is registered once the renderer exists; the canvas schedules it.
            self.request_draw(self._on_draw)

        # --- lifecycle ------------------------------------------------------------------

        def _ensure_renderer(self) -> Optional["SceneRenderer"]:
            if self._renderer is None:
                try:
                    self._renderer = SceneRenderer(self, background=self._background)
                    if self._pending_scene is not None:
                        self._renderer.set_scene(self._pending_scene)
                        self._pending_scene = None
                except Exception as exc:  # noqa: BLE001 - report, don't crash the UI
                    print(f"[trech-studio] renderer init failed: {exc}")
                    self._renderer = None
            return self._renderer

        def _on_draw(self) -> None:
            renderer = self._ensure_renderer()
            if renderer is not None:
                renderer.draw()

        # --- ViewportLike ---------------------------------------------------------------

        def set_scene(self, scene: SceneModel) -> None:
            renderer = self._ensure_renderer()
            if renderer is not None:
                renderer.set_scene(scene)
                self.request_redraw()
            else:
                self._pending_scene = scene

        def request_redraw(self) -> None:
            self.request_draw()

        # --- interaction ----------------------------------------------------------------

        def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
            self._last_pos = event.position()

        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            if self._last_pos is None or self._renderer is None:
                return
            pos = event.position()
            dx = pos.x() - self._last_pos.x()
            dy = pos.y() - self._last_pos.y()
            self._last_pos = pos
            buttons = event.buttons()
            cam = self._renderer.camera
            if buttons & Qt.LeftButton:
                cam.orbit(-dx * 0.01, -dy * 0.01)
            elif buttons & (Qt.MiddleButton | Qt.RightButton):
                scale = cam.distance * 0.0015
                cam.pan(-dx * scale, dy * scale)
            else:
                return
            self.request_redraw()

        def mouseReleaseEvent(self, event) -> None:  # noqa: N802
            self._last_pos = None

        def wheelEvent(self, event) -> None:  # noqa: N802
            if self._renderer is None:
                return
            steps = event.angleDelta().y() / 120.0
            self._renderer.camera.dolly(math.pow(0.9, steps))
            self.request_redraw()


def create_viewport(background: str = "dark", parent: Optional[QWidget] = None) -> QWidget:
    """Factory: a real wgpu viewport, or a labelled fallback if wgpu is unavailable."""
    if WGPU_AVAILABLE:
        return WgpuViewport(background=background, parent=parent)
    reason = _IMPORT_ERROR or "wgpu is not installed"
    return _FallbackViewport(reason, parent=parent)
