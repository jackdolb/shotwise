"""Miniatura no canto da tela após capturar: copiar, editar, salvar ou fixar.

Visual minimalista: cartão pequeno com cantos arredondados e botões circulares (só ícone) nas bordas.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .glass import GlassButton
from .i18n import tr

THUMB = QSize(220, 140)
MARGIN = 8
RADIUS = 14
BTN = 26


class QuickPreview(QWidget):
    copy_clicked = Signal(QImage)
    edit_clicked = Signal(QImage)
    save_clicked = Signal(QImage)
    pin_clicked = Signal(QImage)
    closed = Signal(object)

    def __init__(self, image: QImage, seconds: int = 8):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._image = image
        self._seconds = max(3, seconds)
        self._left_ms = self._seconds * 1000
        self._pix = QPixmap.fromImage(image).scaled(THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation)
        self.setFixedSize(max(self._pix.width(), 110) + 2 * MARGIN, max(self._pix.height(), 70) + 2 * MARGIN)

        def mk(icon, tip, sig=None, danger=False):
            b = GlassButton(icon, tip, self, BTN, danger)
            b.clicked.connect(self.close if sig is None else (lambda s=sig: self._act(s)))
            return b

        self._b_close = mk("close", tr("Fechar"), danger=True)
        self._b_pin = mk("pin", tr("Fixar na tela"), self.pin_clicked)
        self._b_edit = mk("edit", tr("Editar"), self.edit_clicked)
        self._b_copy = mk("copy", tr("Copiar"), self.copy_clicked)
        self._b_save = mk("save", tr("Salvar"), self.save_clicked)
        w, h, m = self.width(), self.height(), MARGIN + 6
        self._b_close.move(m, m)
        self._b_pin.move(w - m - BTN, m)
        self._b_edit.move(m, h - m - BTN)
        self._b_save.move(w - m - BTN, h - m - BTN)
        self._b_copy.move((w - BTN) // 2, h - m - BTN)

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._place()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        card = QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        # sombra suave
        for i in range(MARGIN, 0, -1):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 6))
            p.drawRoundedRect(card.adjusted(-i, -i + 2, i, i + 2), RADIUS + i, RADIUS + i)
        path = QPainterPath()
        path.addRoundedRect(card, RADIUS, RADIUS)
        p.setClipPath(path)
        p.fillRect(card, QColor("#1b1d23"))
        p.drawPixmap(card.toRect(), self._pix)
        p.fillRect(card, QColor(0, 0, 0, 55))                     # escurece um pouco para os botões se destacarem
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
        p.end()

    def mouseReleaseEvent(self, ev):
        # clicar na própria miniatura abre o editor
        if ev.button() == Qt.MouseButton.LeftButton:
            self._act(self.edit_clicked)

    def _place(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is not None:
            g = screen.availableGeometry()
            self.move(g.right() - self.width() - 10, g.bottom() - self.height() - 10)

    def _tick(self):
        if self.underMouse():
            self._left_ms = self._seconds * 1000          # pausa enquanto o mouse está em cima
            return
        self._left_ms -= self._timer.interval()
        if self._left_ms <= 0:
            self.close()

    def _act(self, signal):
        signal.emit(self._image)
        self.close()

    def closeEvent(self, ev):
        self._timer.stop()
        self.closed.emit(self)
        super().closeEvent(ev)
