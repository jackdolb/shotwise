"""Captura fixada: janela sem borda que fica sempre à frente das demais."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QWidget

from .clipboard import copy_image
from .glass import GlassButton
from .i18n import tr


class PinWindow(QWidget):
    EDGE = 7               # largura (px) da borda sensível ao redimensionamento

    closed = Signal(object)
    edit_requested = Signal(QImage)
    save_requested = Signal(QImage)

    def __init__(self, image: QImage, pos: QPoint | None = None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr("Shotwise — fixada"))
        self._image = image
        self._pix = QPixmap.fromImage(image)
        self._scale = 1.0
        self._opacity = 1.0
        self._drag: QPoint | None = None
        self._resize = None
        # imagens grandes entram reduzidas para caber na tela
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            ratio = max(1.0, screen.devicePixelRatio())
            w, h = image.width() / ratio, image.height() / ratio
            fit = min(1.0, (avail.width() * 0.8) / max(1, w), (avail.height() * 0.8) / max(1, h))
            self._scale = fit / 1.0
        self._apply_size()
        if pos is not None:
            self.move(pos)
        elif screen is not None:
            self.move(screen.availableGeometry().center() - QPoint(self.width() // 2, self.height() // 2))
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip(tr("Arraste para mover · arraste as bordas: redimensionar · roda: zoom · Ctrl+roda: opacidade · clique duplo ou Esc: fechar · "
                        "botão direito: menu"))
        # botões que aparecem só com o mouse em cima: fechar, copiar, salvar, editar
        self._buttons = [
            GlassButton("copy", tr("Copiar"), self),
            GlassButton("save", tr("Salvar"), self),
            GlassButton("edit", tr("Editar"), self),
            GlassButton("close", tr("Fechar"), self, danger=True),
        ]
        self._buttons[0].clicked.connect(self._copy)
        self._buttons[1].clicked.connect(self._save)
        self._buttons[2].clicked.connect(self._edit)
        self._buttons[3].clicked.connect(self.close)
        self.setMouseTracking(True)
        self._layout_buttons()
        self._show_buttons(False)

    # toda ação feita na captura fixada fecha a fixação
    def _copy(self):
        copy_image(self._image)
        self.close()

    def _save(self):
        self.save_requested.emit(self._image)
        self.close()

    def _edit(self):
        self.edit_requested.emit(self._image)
        self.close()

    def _layout_buttons(self):
        n = len(self._buttons)
        size = 28 if self.width() >= n * 34 + 16 and self.height() >= 52 else 20
        gap = 6 if size == 28 else 4
        total = n * size + (n - 1) * gap
        x = max(2, (self.width() - total) // 2)
        for b in self._buttons:
            b.resize_to(size)
            b.move(x, 8 if self.height() >= size + 16 else 2)
            x += size + gap

    def _show_buttons(self, visible: bool):
        for b in self._buttons:
            b.setVisible(visible)

    def enterEvent(self, _ev):
        self._show_buttons(True)

    def leaveEvent(self, _ev):
        self._show_buttons(False)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if hasattr(self, "_buttons"):
            self._layout_buttons()

    def _apply_size(self):
        ratio = max(1.0, self.devicePixelRatioF())
        self.resize(max(24, round(self._image.width() / ratio * self._scale)),
                    max(24, round(self._image.height() / ratio * self._scale)))

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setOpacity(self._opacity)
        p.drawPixmap(self.rect(), self._pix)
        p.setOpacity(1.0)
        p.setPen(QPen(QColor(59, 156, 255, 200), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    # --- interação -----------------------------------------------------
    def _edges(self, pos: QPoint) -> str:
        """Quais bordas estão sob o ponto (L, R, T, B), para redimensionar arrastando."""
        m = min(self.EDGE, max(2, min(self.width(), self.height()) // 4))
        e = ""
        if pos.y() <= m:
            e += "T"
        elif pos.y() >= self.height() - m:
            e += "B"
        if pos.x() <= m:
            e += "L"
        elif pos.x() >= self.width() - m:
            e += "R"
        return e

    _CURSORS = {"L": Qt.CursorShape.SizeHorCursor, "R": Qt.CursorShape.SizeHorCursor,
                "T": Qt.CursorShape.SizeVerCursor, "B": Qt.CursorShape.SizeVerCursor,
                "TL": Qt.CursorShape.SizeFDiagCursor, "BR": Qt.CursorShape.SizeFDiagCursor,
                "TR": Qt.CursorShape.SizeBDiagCursor, "BL": Qt.CursorShape.SizeBDiagCursor}

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        edges = self._edges(ev.position().toPoint())
        if edges:
            self._resize = (edges, ev.globalPosition().toPoint(), self.geometry())
        else:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._resize is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self._do_resize(ev.globalPosition().toPoint())
        elif self._drag is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag)
        else:
            self.setCursor(self._CURSORS.get(self._edges(ev.position().toPoint()), Qt.CursorShape.SizeAllCursor))

    def _do_resize(self, gpos: QPoint):
        """Mantém a proporção: a largura (ou a altura, nas bordas de cima/baixo) define o novo tamanho."""
        edges, start, g0 = self._resize
        d = gpos - start
        ratio = g0.width() / max(1, g0.height())
        if edges in ("T", "B"):
            h = g0.height() + (d.y() if edges == "B" else -d.y())
            w = h * ratio
        else:
            w = g0.width() + (d.x() if "R" in edges else -d.x())
        w = int(min(max(w, 40), 12000))
        h = max(1, round(w / ratio))
        x = g0.right() + 1 - w if "L" in edges else g0.x()
        y = g0.bottom() + 1 - h if "T" in edges else g0.y()
        base = self._image.width() / max(1.0, self.devicePixelRatioF())
        self._scale = w / base
        self.setGeometry(x, y, w, h)
        self.update()

    def mouseReleaseEvent(self, _ev):
        self._drag = None
        self._resize = None

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.close()

    def wheelEvent(self, ev):
        step = 1 if ev.angleDelta().y() > 0 else -1
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._opacity = min(1.0, max(0.15, self._opacity + 0.1 * step))
        else:
            center = self.geometry().center()
            self._scale = min(8.0, max(0.1, self._scale * (1.1 if step > 0 else 1 / 1.1)))
            self._apply_size()
            self.move(center - QPoint(self.width() // 2, self.height() // 2))
        self.update()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.close()

    def contextMenuEvent(self, ev):
        m = QMenu(self)
        m.addAction(tr("Copiar"), self._copy)
        m.addAction(tr("Salvar"), self._save)
        m.addAction(tr("Abrir no editor"), self._edit)
        m.addAction(tr("Tamanho original (100%)"), self._reset_scale)
        m.addSeparator()
        m.addAction(tr("Fechar"), self.close)
        m.exec(ev.globalPos())

    def _reset_scale(self):
        self._scale = 1.0
        self._apply_size()
        self.update()

    def closeEvent(self, ev):
        self.closed.emit(self)
        super().closeEvent(ev)

    def sizeHint(self) -> QSize:
        return self.size()
