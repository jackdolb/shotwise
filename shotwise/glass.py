"""Botão circular translúcido, só com ícone, usado na miniatura e na captura fixada."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from .icons import ui_icon


class GlassButton(QWidget):
    clicked = Signal()

    def __init__(self, icon: str, tip: str, parent: QWidget, size: int = 28, danger: bool = False):
        super().__init__(parent)
        self._icon = ui_icon(icon, "#ffffff")
        self._hover = False
        self._down = False
        self._danger = danger
        self.setFixedSize(size, size)
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def resize_to(self, size: int):
        self.setFixedSize(size, size)

    def enterEvent(self, _ev):
        self._hover = True
        self.update()

    def leaveEvent(self, _ev):
        self._hover = False
        self._down = False
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._down = True
            self.update()
            ev.accept()

    def mouseReleaseEvent(self, ev):
        was = self._down
        self._down = False
        self.update()
        if was and ev.button() == Qt.MouseButton.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit()

    def mouseDoubleClickEvent(self, ev):
        ev.accept()          # não repassa o clique duplo à janela por baixo

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hover and self._danger:
            bg = QColor(232, 65, 65, 235)
        elif self._hover:
            bg = QColor(59, 156, 255, 235)
        else:
            bg = QColor(20, 22, 28, 175)
        if self._down:
            bg = bg.darker(125)
        p.setPen(QColor(255, 255, 255, 70))
        p.setBrush(bg)
        p.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        pad = max(4, round(self.width() * 0.2))
        self._icon.paint(p, self.rect().adjusted(pad, pad, -pad, -pad))
        p.end()

    def sizeHint(self) -> QSize:
        return self.size()
