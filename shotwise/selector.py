"""Seleção de área na tela (overlay sobre a imagem congelada de cada monitor)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QFrame, QGraphicsView, QHBoxLayout, QPushButton, QToolButton, QWidget)

from .i18n import tr

BAR_ICON = "#e8e8ec"
ANNOT_COLORS = ["#ff3b30", "#ff9500", "#ffd60a", "#34c759", "#0a84ff", "#ffffff", "#000000"]


def annot_tools() -> list[tuple[str, str]]:
    """(ferramenta, dica) das anotações disponíveis na própria seleção."""
    return [("arrow", tr("Seta")), ("rect", tr("Retângulo")), ("ellipse", tr("Elipse")), ("line", tr("Linha")),
            ("pen", tr("Caneta")), ("text", tr("Texto")), ("highlight", tr("Destacar")), ("redact", tr("Tarja sólida"))]


class AnnotBar(QFrame):
    """Barra de ferramentas que aparece junto da área selecionada."""

    tool_changed = Signal(str)
    color_changed = Signal(str)
    undo_clicked = Signal()
    confirm_clicked = Signal()
    cancel_clicked = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        from .icons import tool_icon, ui_icon
        self.setStyleSheet(
            "AnnotBar{background:rgba(24,24,28,235);border:1px solid #3a3a42;border-radius:8px;}"
            "QToolButton,QPushButton{background:transparent;border:0;border-radius:5px;padding:4px;color:#e8e8ec;}"
            "QToolButton:hover,QPushButton:hover{background:#34343c;}"
            "QToolButton:checked{background:#2f7df6;}"
            "QToolButton:disabled,QPushButton:disabled{opacity:.4;}"
            "QPushButton#ok{background:#2f7df6;color:white;padding:4px 12px;font-weight:600;}"
            "QPushButton#ok:hover{background:#4a90ff;}")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)
        self._tools: dict[str, QToolButton] = {}

        def tbtn(name: str, icon, tip: str, checkable=True) -> QToolButton:
            b = QToolButton()
            b.setIcon(icon)
            b.setIconSize(QSize(20, 20))
            b.setFixedSize(32, 30)
            b.setCheckable(checkable)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            return b

        b = tbtn("select", tool_icon("select", BAR_ICON), tr("Selecionar: ajusta a área; com anotações, move e edita as anotações"))
        b.clicked.connect(lambda _=False: self.set_tool("select", emit=True))
        self._tools["select"] = b
        lay.addWidget(b)
        for name, tip in annot_tools():
            b = tbtn(name, tool_icon(name, BAR_ICON), tip)
            b.clicked.connect(lambda _=False, n=name: self.set_tool(n, emit=True))
            self._tools[name] = b
            lay.addWidget(b)
        lay.addSpacing(6)
        self.color = ANNOT_COLORS[0]
        self.btn_color = QToolButton()
        self.btn_color.setFixedSize(32, 30)
        self.btn_color.setToolTip(tr("Cor (abre o seletor de cores)"))
        self.btn_color.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_color.clicked.connect(self._choose_color)
        lay.addWidget(self.btn_color)
        self._pick_color(self.color, emit=False)
        lay.addSpacing(6)
        self.btn_undo = tbtn("undo", ui_icon("undo", BAR_ICON), tr("Desfazer (Ctrl+Z)"), checkable=False)
        self.btn_undo.clicked.connect(self.undo_clicked)
        self.btn_undo.setEnabled(False)
        lay.addWidget(self.btn_undo)
        lay.addSpacing(6)
        cancel = QPushButton("✕")
        cancel.setToolTip(tr("Cancelar a captura (Esc)"))
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel.clicked.connect(self.cancel_clicked)
        lay.addWidget(cancel)
        ok = QPushButton(tr("Confirmar"))
        ok.setObjectName("ok")
        ok.setToolTip(tr("Confirmar a captura (Enter).  Ctrl+C confirma e copia;  Ctrl+S confirma e salva."))
        ok.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ok.clicked.connect(self.confirm_clicked)
        lay.addWidget(ok)
        self.tool = "select"
        self._tools["select"].setChecked(True)

    def _pick_color(self, color: str, emit: bool = True):
        self.color = color
        self.btn_color.setStyleSheet(f"QToolButton{{background:{color};border:2px solid #777;border-radius:6px;margin:3px;}}"
                                     "QToolButton:hover{border-color:#4a90ff;}")
        if emit:
            self.color_changed.emit(color)

    def _choose_color(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self.color), self.window(), tr("Cor"))
        if c.isValid():
            self._pick_color(c.name())

    def set_tool(self, tool: str, emit: bool = False):
        self.tool = tool
        for n, b in self._tools.items():
            b.setChecked(n == tool)
        if emit:
            self.tool_changed.emit(tool)

    def set_state(self, can_adjust: bool, can_undo: bool):
        self.btn_undo.setEnabled(can_undo)


class RegionOverlay(QWidget):
    """Janela sem borda que cobre um monitor mostrando a tela congelada."""

    region_selected = Signal(object, QRect, QRect)  # overlay, retângulo lógico, retângulo em pixels físicos
    cancelled = Signal()

    def __init__(self, screen, frozen: QImage, hint: str, adjustable: bool = False, annotatable: bool = False):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.qscreen = screen
        self.frozen = frozen            # pixels físicos do monitor
        self._pix = QPixmap.fromImage(frozen)
        self._hint = hint
        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self._cursor: QPoint | None = None
        self.adjustable = adjustable
        self.annotatable = annotatable and adjustable   # barra de anotações na própria seleção
        self._bar: AnnotBar | None = None
        self._view: QGraphicsView | None = None
        self._scene = None
        self.action = ""                                # "" (o que estiver nas configurações) | "copy" | "save"
        self.annotation_pd = None                       # anotações feitas (ProjectData) quando a seleção é confirmada
        self._adjusting = False          # seleção feita, aguardando confirmação (Enter / clique duplo)
        self._drag: str | None = None    # 'new' | 'move' | 'tl'... durante o arraste
        self._drag_origin = QPoint()
        self._drag_rect = QRect()
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Undo), self, activated=self._undo)

    # escala lógica -> física
    @property
    def scale_x(self) -> float:
        return self.frozen.width() / max(1, self.width())

    @property
    def scale_y(self) -> float:
        return self.frozen.height() / max(1, self.height())

    def selection(self) -> QRect | None:
        if self._start is None or self._end is None:
            return None
        return QRect(self._start, self._end).normalized()

    def to_physical(self, r: QRect) -> QRect:
        sx, sy = self.scale_x, self.scale_y
        phys = QRect(round(r.x() * sx), round(r.y() * sy), round(r.width() * sx), round(r.height() * sy))
        return phys.intersected(self.frozen.rect())

    # ------------------------------------------------------------------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._pix)
        dim = QColor(0, 0, 0, 120)
        sel = self.selection()
        if sel is None or sel.isEmpty():
            p.fillRect(self.rect(), dim)
            self._draw_hint(p)
            if self._cursor is not None:
                self._draw_crosshair(p, self._cursor)
            return
        # escurece fora da seleção
        p.fillRect(QRect(0, 0, self.width(), sel.top()), dim)
        p.fillRect(QRect(0, sel.bottom() + 1, self.width(), self.height() - sel.bottom() - 1), dim)
        p.fillRect(QRect(0, sel.top(), sel.left(), sel.height()), dim)
        p.fillRect(QRect(sel.right() + 1, sel.top(), self.width() - sel.right() - 1, sel.height()), dim)
        p.setPen(QPen(QColor("#3b9cff"), 1))
        p.drawRect(sel.adjusted(0, 0, -1, -1))
        phys = self.to_physical(sel)
        label = f"{phys.width()} × {phys.height()}"
        p.setFont(QFont("Segoe UI", 9))
        fm = p.fontMetrics()
        tw, th = fm.horizontalAdvance(label) + 14, fm.height() + 8
        ty = sel.top() - th - 4 if sel.top() > th + 8 else sel.bottom() + 4
        box = QRect(sel.left(), ty, tw, th)
        p.fillRect(box, QColor(20, 20, 24, 220))
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
        if self._adjusting:
            if self._can_adjust():
                p.setPen(QPen(QColor("#3b9cff"), 1))
                p.setBrush(QColor("white"))
                for r in self._handle_rects(sel).values():
                    p.drawRect(r)
            if self.annotatable:
                msg = tr("Escolha uma ferramenta para anotar   ·   Enter: confirmar   ·   Esc: cancelar")
            else:
                msg = tr("Enter ou clique duplo: confirmar   ·   arraste para ajustar   ·   Esc: cancelar")
            p.setFont(QFont("Segoe UI", 9))
            fm = p.fontMetrics()
            mw, mh = fm.horizontalAdvance(msg) + 20, fm.height() + 10
            mbox = QRect(max(4, (self.width() - mw) // 2), 28, mw, mh)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(20, 20, 24, 225))
            p.drawRoundedRect(QRectF(mbox), 6, 6)
            p.setPen(QColor("white"))
            p.drawText(mbox, Qt.AlignmentFlag.AlignCenter, msg)

    # --- anotações na própria seleção ----------------------------------
    def has_annotations(self) -> bool:
        try:
            return self._scene is not None and self._scene.undo_stack.index() > 0
        except RuntimeError:               # cena já destruída (janela fechando)
            return False

    def _can_adjust(self) -> bool:
        """Alças e arraste só valem enquanto a ferramenta for 'Ajustar' e não houver anotações."""
        if not self.annotatable:
            return True
        return not self.has_annotations() and (self._bar is None or self._bar.tool == "select")

    def _ensure_bar(self):
        if not self.annotatable:
            return
        if self._bar is None:
            bar = AnnotBar(self)
            bar.tool_changed.connect(self._set_tool)
            bar.color_changed.connect(self._set_color)
            bar.undo_clicked.connect(self._undo)
            bar.confirm_clicked.connect(self._confirm)
            bar.cancel_clicked.connect(self.cancelled)
            self._bar = bar
        self._place_bar()
        self._bar.show()
        self._bar.raise_()

    def _place_bar(self):
        sel = self.selection()
        if self._bar is None or sel is None:
            return
        self._bar.adjustSize()
        w, h = self._bar.width(), self._bar.height()
        x = max(4, min(sel.center().x() - w // 2, self.width() - w - 4))
        y = sel.bottom() + 8
        if y + h > self.height() - 4:
            y = sel.top() - h - 8
            if y < 4:
                y = max(4, sel.bottom() - h - 8)
        self._bar.move(x, y)

    def _ensure_view(self):
        if self._view is not None:
            return
        sel = self.selection()
        img = self.frozen.copy(self.to_physical(sel))
        if sel is None or img.isNull():
            return
        from .annotations import AnnotScene
        scene = AnnotScene(img)
        scene.opt_color = QColor(self._bar.color if self._bar else ANNOT_COLORS[0])
        scene.undo_stack.indexChanged.connect(lambda _i: self._sync_bar())
        view = QGraphicsView(scene, self)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setGeometry(sel)
        view.setSceneRect(0, 0, img.width(), img.height())
        view.scale(sel.width() / img.width(), sel.height() / img.height())
        view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        view.show()
        self._view, self._scene = view, scene
        if self._bar is not None:
            self._bar.raise_()

    def _drop_view(self):
        """Descarta a camada de anotação (só quando ainda não há anotações)."""
        if self._view is not None:
            self._view.hide()
            self._view.deleteLater()
        self._view = None
        self._scene = None

    def _set_tool(self, tool: str):
        if tool == "select":
            if self._view is not None:
                if self.has_annotations():          # já há anotações: a seta seleciona/move/edita os itens
                    self._view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
                    self._scene.set_tool("select")
                    self._view.setFocus()
                else:                               # sem anotações: a seta volta a ajustar a área
                    self._view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    self.setFocus()
            else:
                self.setFocus()
        else:
            self._ensure_view()
            if self._view is None:
                return
            self._view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self._scene.set_tool(tool)
            self._view.setFocus()
        self._sync_bar()
        self.update()

    def _set_color(self, color: str):
        if self._scene is not None:
            self._scene.opt_color = QColor(color)

    def _undo(self):
        if self._scene is not None:
            self._scene.undo_stack.undo()

    def _sync_bar(self):
        if self._bar is not None:
            self._bar.set_state(not self.has_annotations(), self.has_annotations())
        self.update()

    def _finish_annotations(self):
        """Fecha um texto em edição e guarda as anotações como projeto para o editor."""
        if self._scene is None:
            return
        fi = self._scene.focusItem()
        if fi is not None:
            fi.clearFocus()
        if self.has_annotations():
            from .project import project_from_scene
            self.annotation_pd = project_from_scene(self._scene)

    def _handle_rects(self, sel: QRect) -> dict[str, QRect]:
        s = 9
        cx, cy = sel.center().x(), sel.center().y()
        pts = {"tl": sel.topLeft(), "t": QPoint(cx, sel.top()), "tr": sel.topRight(),
               "r": QPoint(sel.right(), cy), "br": sel.bottomRight(), "b": QPoint(cx, sel.bottom()),
               "bl": sel.bottomLeft(), "l": QPoint(sel.left(), cy)}
        return {k: QRect(v.x() - s // 2, v.y() - s // 2, s, s) for k, v in pts.items()}

    def _hit(self, pos: QPoint) -> str | None:
        sel = self.selection()
        if sel is None:
            return None
        for name, r in self._handle_rects(sel).items():
            if r.adjusted(-4, -4, 4, 4).contains(pos):
                return name
        return "move" if sel.contains(pos) else None

    def _confirm(self, action: str = ""):
        self.action = action
        sel = self.selection()
        if sel is not None and sel.width() >= 4 and sel.height() >= 4:
            self._adjusting = False
            self._finish_annotations()
            self.region_selected.emit(self, sel, self.to_physical(sel))

    def _draw_hint(self, p: QPainter):
        p.setFont(QFont("Segoe UI", 11))
        fm = p.fontMetrics()
        tw, th = fm.horizontalAdvance(self._hint) + 28, fm.height() + 16
        box = QRect((self.width() - tw) // 2, 28, tw, th)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 20, 24, 225))
        p.drawRoundedRect(QRectF(box), 8, 8)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, self._hint)

    def _draw_crosshair(self, p: QPainter, pt: QPoint):
        p.setPen(QPen(QColor(255, 255, 255, 140), 1, Qt.PenStyle.DashLine))
        p.drawLine(pt.x(), 0, pt.x(), self.height())
        p.drawLine(0, pt.y(), self.width(), pt.y())

    # ------------------------------------------------------------------
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
            return
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position().toPoint()
        if self._adjusting:
            if not self._can_adjust():
                return                 # com anotações a área fica travada (Ctrl+Z desfaz até liberar)
            hit = self._hit(pos)
            if hit:
                self._drag, self._drag_origin, self._drag_rect = hit, pos, QRect(self.selection())
                self._drop_view()
                if self._bar is not None:
                    self._bar.hide()
                return
        self._adjusting = False
        self._drop_view()
        if self._bar is not None:
            self._bar.hide()
            self._bar.set_tool("select")
        self._drag = "new"
        self._start = pos
        self._end = pos
        self.update()

    def mouseMoveEvent(self, ev):
        pos = ev.position().toPoint()
        self._cursor = pos
        if self._drag == "new":
            self._end = pos
        elif self._drag == "move":
            d = pos - self._drag_origin
            r = QRect(self._drag_rect).translated(d)
            dx = -r.left() if r.left() < 0 else (self.width() - 1 - r.right() if r.right() > self.width() - 1 else 0)
            dy = -r.top() if r.top() < 0 else (self.height() - 1 - r.bottom() if r.bottom() > self.height() - 1 else 0)
            r.translate(dx, dy)
            self._start, self._end = r.topLeft(), r.bottomRight()
        elif self._drag:
            r = QRect(self._drag_rect)
            x = min(max(pos.x(), 0), self.width() - 1)
            y = min(max(pos.y(), 0), self.height() - 1)
            if "l" in self._drag:
                r.setLeft(x)
            if "r" in self._drag:
                r.setRight(x)
            if "t" in self._drag:
                r.setTop(y)
            if "b" in self._drag:
                r.setBottom(y)
            r = r.normalized()
            self._start, self._end = r.topLeft(), r.bottomRight()
        elif self._adjusting:
            hit = self._hit(pos)
            cur = {"tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                   "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
                   "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
                   "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
                   "move": Qt.CursorShape.SizeAllCursor}.get(hit, Qt.CursorShape.CrossCursor)
            self.setCursor(cur)
        self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton or self._drag is None:
            return
        drag, self._drag = self._drag, None
        if drag == "new":
            self._end = ev.position().toPoint()
        sel = self.selection()
        if sel is None or sel.width() < 4 or sel.height() < 4:
            self._start = self._end = None
            self._adjusting = False
            self.update()
            return
        if self.adjustable:
            self._adjusting = True
            self._ensure_bar()
            self._sync_bar()
            self.update()
        else:
            self.region_selected.emit(self, sel, self.to_physical(sel))

    def mouseDoubleClickEvent(self, ev):
        if self._adjusting and ev.button() == Qt.MouseButton.LeftButton:
            self._confirm()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            fi = self._scene.focusItem() if self._scene is not None else None
            if fi is not None and getattr(fi, "editing", False):
                fi.clearFocus()          # Esc fecha a edição de um texto antes de cancelar a captura
                return
            self.cancelled.emit()
        elif ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._adjusting:
            self._confirm()
        elif self._adjusting and ev.matches(QKeySequence.StandardKey.Copy):       # Ctrl+C: confirma e copia
            self._confirm("copy")
        elif self._adjusting and ev.matches(QKeySequence.StandardKey.Save):       # Ctrl+S: confirma e salva
            self._confirm("save")


class RegionSelector:
    """Mostra um overlay por monitor e devolve a seleção via callbacks."""

    def __init__(self, frozen_screens: list[tuple[object, QImage]], hint: str, on_selected, on_cancelled,
                 adjustable: bool = False, annotatable: bool = False):
        self._overlays: list[RegionOverlay] = []
        self.action = ""                   # ação pedida ao confirmar: Ctrl+C = "copy", Ctrl+S = "save"
        self.annotations = None            # ProjectData com as anotações feitas antes de confirmar
        self._on_selected = on_selected
        self._on_cancelled = on_cancelled
        self._idle_s = 0
        self._last_cursor: QPoint | None = None
        self._watchdog = QTimer()
        self._watchdog.setInterval(1000)
        self._watchdog.timeout.connect(self._check_idle)
        for screen, image in frozen_screens:
            ov = RegionOverlay(screen, image, hint, adjustable, annotatable)
            ov.region_selected.connect(self._selected)
            ov.cancelled.connect(self._cancelled)
            self._overlays.append(ov)

    IDLE_LIMIT_S = 45          # sem mexer o mouse por este tempo: cancela sozinho (nunca deixa a tela presa)

    def _check_idle(self):
        from PySide6.QtGui import QCursor

        pos = QCursor.pos()
        if pos != self._last_cursor:
            self._last_cursor, self._idle_s = pos, 0
            return
        self._idle_s += 1
        limit = self.IDLE_LIMIT_S * (8 if any(o.has_annotations() for o in self._overlays) else 1)
        if self._idle_s >= limit and self._overlays:
            self._cancelled()

    def start(self):
        self._watchdog.start()
        for ov in self._overlays:
            ov.show()
        # foca o overlay do monitor onde está o cursor
        from PySide6.QtGui import QCursor

        target = next((o for o in self._overlays if o.qscreen is QGuiApplication.screenAt(QCursor.pos())),
                      self._overlays[0])
        target.activateWindow()
        target.raise_()
        target.setFocus()

    def close(self):
        self._watchdog.stop()
        for ov in self._overlays:
            ov.close()
        self._overlays.clear()

    def _selected(self, overlay, logical: QRect, physical: QRect):
        screen, frozen = overlay.qscreen, overlay.frozen
        self.annotations = overlay.annotation_pd
        self.action = overlay.action
        self.close()
        self._on_selected(screen, frozen, logical, physical)

    def _cancelled(self):
        self.close()
        self._on_cancelled()
