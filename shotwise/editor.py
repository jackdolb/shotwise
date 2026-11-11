"""Janela do editor: visualização, barra de ferramentas, copiar/salvar."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QAction, QActionGroup, QColor, QGuiApplication, QIcon, QImage, QImageReader, QKeySequence,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QFileDialog, QGraphicsView,
                               QGridLayout, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QSizePolicy,
                               QSlider, QSpinBox, QToolBar, QToolButton, QWidget, QWidgetAction, QDockWidget,
                               QScrollArea, QFrame, QHBoxLayout, QVBoxLayout)

from .i18n import tr
from . import library
from .annotations import AnnotScene, AttrCommand, BackgroundSettings, ImageLayer, TextItem
from .clipboard import copy_image
from .config import Config
from .dialogs import BackgroundDialog, LabeledSlider, OcrDialog, ResizeDialog
from .icons import app_icon, tool_icon, ui_icon
from .ocr import start_ocr

log = logging.getLogger("shotwise")

MAX_IMPORT_PIXELS = 150_000_000

class _Handle:
    """Faz o papel de QAction nas listas de opções: mostra/esconde a linha do painel."""

    def __init__(self, widget: QWidget):
        self.widget = widget

    def setVisible(self, on: bool):
        self.widget.setVisible(on)

    def isVisible(self) -> bool:
        return not self.widget.isHidden()


class OptionsPanel(QFrame):
    """Painel flutuante de opções da ferramenta: vive sobre a área de edição, é translúcido, de cantos arredondados e
    pode ser arrastado. Cada controle ocupa uma linha; só aparece quando a ferramenta tem opções a mostrar."""

    MARGIN = 14

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("optionsPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 4, 6, 12)
        outer.setSpacing(0)
        # o conteúdo fica numa área com rolagem: em janelas pequenas o painel encolhe e rola, sem sair da tela
        self._inner = QWidget()
        self._inner.setObjectName("optionsInner")
        self._lay = QVBoxLayout(self._inner)
        self._lay.setContentsMargins(0, 0, 6, 0)
        self._lay.setSpacing(4)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("optionsScroll")
        self._scroll.setWidget(self._inner)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.viewport().setAutoFillBackground(False)
        self._inner.setAutoFillBackground(False)
        self._grip = QLabel("• • •")
        self._grip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grip.setCursor(Qt.CursorShape.SizeAllCursor)
        self._grip.setToolTip(tr("Arraste para mover este painel"))
        self._grip.setStyleSheet("color:rgba(128,128,128,0.8);font-size:9px;letter-spacing:2px;padding:2px 0 4px 0;")
        outer.addWidget(self._grip)
        outer.addWidget(self._scroll, 1)
        self._drag_off = None
        self._user_pos: QPoint | None = None                 # onde o usuário deixou o painel (None = canto superior direito)
        self.setCursor(Qt.CursorShape.ArrowCursor)           # sobre o painel o mouse é uma seta normal
        self.setStyleSheet(
            "#optionsPanel QLabel{background:transparent;}"
            "#optionsPanel QScrollArea#optionsScroll, #optionsPanel QWidget#optionsInner{background:transparent;border:none;}"
            "#optionsPanel QScrollBar:vertical{width:6px;background:transparent;margin:2px 0;}"
            "#optionsPanel QScrollBar::handle:vertical{background:rgba(128,128,128,110);border-radius:3px;min-height:24px;}"
            "#optionsPanel QScrollBar::add-line:vertical, #optionsPanel QScrollBar::sub-line:vertical{height:0;}"
            "#optionsPanel QLabel#sliderValue{color:palette(highlight);font-weight:600;}"
            "#optionsPanel QLabel#panelSection{font-weight:600;margin-top:8px;}"
            "#optionsPanel QSlider::groove:horizontal{height:4px;border-radius:2px;background:rgba(128,128,128,80);}"
            "#optionsPanel QSlider::sub-page:horizontal{height:4px;border-radius:2px;background:palette(highlight);}"
            "#optionsPanel QSlider::handle:horizontal{width:14px;height:14px;margin:-6px 0;border-radius:7px;"
            "background:palette(highlight);border:2px solid palette(window);}"
            "#optionsPanel QSlider::handle:horizontal:hover{width:16px;height:16px;margin:-7px 0;border-radius:8px;}")
        self.hide()

    def _add(self, w: QWidget) -> _Handle:
        self._lay.addWidget(w)
        return _Handle(w)

    def addWidget(self, w: QWidget) -> _Handle:
        if isinstance(w, QLabel):
            w.setText(w.text().strip())
            w.setWordWrap(True)
            w.setStyleSheet("font-weight:600;margin-top:4px;")
        return self._add(w)

    def addSection(self, text: str) -> _Handle:
        lb = QLabel(text)
        lb.setObjectName("panelSection")
        return self._add(lb)

    def addRow(self, *widgets) -> _Handle:
        """Uma linha com vários controles; ``None`` vira um espaço elástico."""
        host = QWidget()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for w in widgets:
            lay.addStretch(1) if w is None else lay.addWidget(w)
        return self._add(host)

    def addSeparator(self):
        """Sem linhas: o painel é minimalista (os títulos de cada grupo já separam os controles)."""

    # --- aparência ------------------------------------------------------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = self.palette().window().color()
        fill = QColor(base.red(), base.green(), base.blue(), 205)   # translúcido: dá para ver a imagem por trás
        edge = QColor(128, 128, 128, 90)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(edge, 1))
        p.setBrush(fill)
        p.drawRoundedRect(r, 14, 14)

    # --- posição e arraste --------------------------------------------------
    # Por padrão o painel abre no canto superior direito; pode ser arrastado para qualquer ponto (é translúcido).
    def _area(self) -> QRect:
        """Área visível da edição (sem as barras de rolagem), em coordenadas do pai."""
        par = self.parentWidget()
        vp = par.viewport() if hasattr(par, "viewport") else None
        return vp.geometry() if vp is not None else par.rect()

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        a = self._area()
        return (min(max(x, a.left() + 4), max(a.left() + 4, a.right() + 1 - self.width() - 4)),
                min(max(y, a.top() + 4), max(a.top() + 4, a.bottom() + 1 - self.height() - 4)))

    def _fit_size(self):
        """Largura do conteúdo (214–250 px) e altura limitada à área visível; o excedente rola dentro do painel."""
        self._lay.activate()
        hint = self._inner.sizeHint()
        m = self.layout().contentsMargins()
        chrome_h = m.top() + m.bottom() + self._grip.sizeHint().height()
        avail_h = max(80, self._area().height() - 8)
        h = min(hint.height() + chrome_h, avail_h)
        scrolling = hint.height() + chrome_h > avail_h
        w = min(max(hint.width(), 196), 232) + m.left() + m.right() + (14 if scrolling else 0)
        self.setFixedSize(w, h)

    def reposition(self):
        par = self.parentWidget()
        if par is None:
            return
        self._fit_size()
        a = self._area()
        if self._user_pos is None:
            x, y = a.right() + 1 - self.width() - self.MARGIN, a.top() + self.MARGIN
        else:
            x, y = self._user_pos.x(), self._user_pos.y()
        self.move(*self._clamp(x, y))
        self.raise_()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_off = ev.position().toPoint()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag_off is not None and self.parentWidget() is not None:
            x, y = self._clamp(*(lambda pt: (pt.x(), pt.y()))(self.mapToParent(ev.position().toPoint() - self._drag_off)))
            self.move(x, y)
            self._user_pos = QPoint(x, y)
            ev.accept()

    def mouseReleaseEvent(self, _ev):
        self._drag_off = None


class HintBubble(QFrame):
    """Balão de dica sobre a imagem (ferramentas sem opções, como Recortar e OCR)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("hintBubble")
        self.setCursor(Qt.CursorShape.ArrowCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 10, 8)
        lay.setSpacing(10)
        self._label = QLabel()
        self._label.setWordWrap(False)
        lay.addWidget(self._label)
        self._btn_lay = QHBoxLayout()
        self._btn_lay.setSpacing(6)
        lay.addLayout(self._btn_lay)
        self._key = None
        self.hide()

    def set_content(self, text: str, buttons=()):
        key = (text, tuple(b[0] for b in buttons))
        if key != self._key:
            self._key = key
            self._label.setText(text)
            while self._btn_lay.count():
                it = self._btn_lay.takeAt(0)
                if it.widget() is not None:
                    it.widget().deleteLater()
            for label, cb in buttons:
                b = QPushButton(label)
                b.clicked.connect(cb)
                self._btn_lay.addWidget(b)
        self.show()
        self.reposition()

    def reposition(self):
        par = self.parentWidget()
        if par is None:
            return
        self.adjustSize()
        self.move(max(4, (par.width() - self.width()) // 2), max(4, par.height() - self.height() - 18))
        self.raise_()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = self.palette().window().color()
        p.setPen(QPen(QColor(128, 128, 128, 90), 1))
        p.setBrush(QColor(base.red(), base.green(), base.blue(), 235))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)


# (id, rótulo, tecla de atalho)
TOOL_DEFS = [
    ("select", tr("Selecionar / mover"), "V"),
    ("arrow", tr("Seta"), "A"),
    ("line", tr("Linha"), "L"),
    ("rect", tr("Retângulo"), "R"),
    ("ellipse", tr("Elipse"), "E"),
    ("highlight", tr("Marca-texto"), "H"),
    ("pen", tr("Caneta livre"), "P"),
    ("text", tr("Texto"), "T"),
    ("step", tr("Marcador numerado"), "N"),
    ("pixelate", tr("Pixelar (esconder)"), "X"),
    ("blur", tr("Desfocar (esconder)"), "B"),
    ("redact", tr("Tarja sólida (esconder)"), "K"),
    ("zoom", tr("Lupa (ampliar uma região)"), "Z"),
    ("crop", tr("Recortar"), "C"),
    ("resize", tr("Redimensionar a imagem (arraste as alças)"), "S"),
    ("background", tr("Fundo, margem e cantos arredondados"), "G"),
    ("ocr", tr("Reconhecer texto na imagem (OCR)"), "O"),
]
TOOL_KEYS = {key.lower(): tid for tid, _label, key in TOOL_DEFS}

PALETTE = ["#ff3b30", "#ff9500", "#ffd60a", "#34c759", "#0a84ff", "#bf5af2", "#ffffff", "#111111"]

# opções relevantes por ferramenta
USES_WIDTH = {"arrow", "line", "rect", "ellipse", "pen", "zoom", "select"}
USES_STEP = {"step", "select"}
USES_COLOR = {"arrow", "line", "rect", "ellipse", "highlight", "pen", "text", "step", "redact", "zoom", "select"}
USES_FONT = {"text", "select"}
USES_STRENGTH = {"pixelate", "blur", "select"}
USES_TEXTBG = {"text", "select"}
USES_FILL = {"rect", "ellipse", "select"}


class ImageView(QGraphicsView):
    zoom_changed = Signal(float)

    def __init__(self, scene: AnnotScene):
        super().__init__(scene)
        self._scene = scene
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
                            | QPainter.RenderHint.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._pan_last = None
        self._z = 1.0
        self._applied_scale = (1.0, 1.0)
        scene.canvas_changed.connect(self._scale_changed)

    # O zoom é medido em pixels da tela por pixel de SAÍDA: 100% mostra a imagem final no tamanho real.
    # Por isso a escala do Redimensionar também aparece na tela (a imagem encolhe/cresce de verdade).
    @property
    def zoom_value(self) -> float:
        return self._z

    def _apply(self):
        sx, sy = self._scene.scale_xy()
        self._applied_scale = (sx, sy)
        self.resetTransform()
        self.scale(self._z * sx, self._z * sy)
        self._sync()

    def set_zoom(self, factor: float):
        self._z = min(max(factor, 0.02), 16.0)
        self._apply()

    def zoom_by(self, mult: float):
        new = min(max(self._z * mult, 0.02), 16.0)
        if new == self._z:
            return
        self.scale(new / self._z, new / self._z)       # mantém o ponto sob o mouse
        self._z = new
        self._sync()

    def _scale_changed(self):
        """O tamanho de saída mudou (Redimensionar): refaz a escala mantendo o centro da vista."""
        if self._scene.scale_xy() == self._applied_scale:
            return
        center = self.mapToScene(self.viewport().rect().center())
        self._apply()
        self.centerOn(center)

    def _sync(self):
        sx, sy = self._scene.scale_xy()
        self._scene.zoom = self._z * min(sx, sy)       # pixels da tela por unidade da cena (alças, traços)
        self._scene.update()
        self.zoom_changed.emit(self._z)

    def fit_initial(self):
        r = self._scene.frame_rect()
        ow, oh = self._scene.output_size()
        vw, vh = self.viewport().width() - 8, self.viewport().height() - 8
        if ow <= 0 or oh <= 0 or vw <= 0 or vh <= 0:
            return
        if oh / ow > 3:      # capturas por rolagem (muito altas): ajusta só a largura
            z = min(1.0, vw / ow)
        else:
            z = min(1.0, vw / ow, vh / oh)
        self.set_zoom(z)
        sy = self._scene.scale_xy()[1]
        self.centerOn(r.center().x(), r.top() + min(r.height() / 2, vh / (2 * z * sy)))

    def fit_all(self):
        r = self._scene.frame_rect()
        ow, oh = self._scene.output_size()
        self.set_zoom(min(self.viewport().width() / ow, self.viewport().height() / oh))
        self.centerOn(r.center())

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.15 ** (ev.angleDelta().y() / 120))
            ev.accept()
        else:
            super().wheelEvent(ev)

    # pan com o botão do meio
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.MiddleButton:
            self._pan_last = ev.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._pan_last is not None:
            d = ev.position() - self._pan_last
            self._pan_last = ev.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.MiddleButton and self._pan_last is not None:
            self._pan_last = None
            self.unsetCursor()
            ev.accept()
            return
        super().mouseReleaseEvent(ev)


def load_image_file(path: str) -> QImage | None:
    """Lê um arquivo de imagem com limite de tamanho (evita arquivos gigantes/malformados)."""
    rd = QImageReader(path)
    rd.setAutoTransform(True)
    size = rd.size()
    if not size.isValid() or size.width() * size.height() > MAX_IMPORT_PIXELS:
        return None
    img = rd.read()
    return None if img.isNull() else img


class EditorWindow(QMainWindow):
    closed = Signal(object)
    capture_requested = Signal(object)     # callback(QImage) que recebe a nova captura
    pin_requested = Signal(QImage)
    library_requested = Signal()
    settings_requested = Signal()

    def __init__(self, image: QImage | None, cfg: Config, project=None, pid: str | None = None):
        super().__init__()
        self.cfg = cfg
        self.pid = pid
        self.saved_path: Path | None = None
        self.title_text = datetime.now().strftime(tr("Captura") + " %d/%m %H:%M")
        self._first_show = True
        self._force_close = False
        self.apply_window_settings()
        self._exported = project is not None      # capturas novas ainda não foram copiadas nem salvas
        self._ocr_jobs: list = []
        self.scene = AnnotScene(image) if project is None else AnnotScene()
        if project is not None:
            from .project import build_scene

            build_scene(project, self.scene)
            self.title_text = str(project.meta.get("title") or self.title_text)[:120]
            exp = str(project.meta.get("export_path") or "")
            if exp and Path(exp).is_file():
                self.saved_path = Path(exp)
        self.view = ImageView(self.scene)
        self.view.setAcceptDrops(False)
        self.setAcceptDrops(True)
        self.setCentralWidget(self.view)
        self.setWindowIcon(app_icon(64))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._build_main_toolbar()
        self._build_tools()
        self._build_options()
        self._tools_pos = ""
        self._place_toolbars()
        self.restore_tool_options(new_image=project is None)
        self.scene.tool_hint.connect(lambda t: self.statusBar().showMessage(t))
        self.scene.zoom_factor_changed.connect(self._on_zoom_factor_dragged)
        self.scene.undo_stack.indexChanged.connect(lambda _i: self._sync_bg_controls())
        self.scene.curvature_changed.connect(lambda v: self.ls_round.set_quiet(v))
        self.scene.ocr_requested.connect(self.run_ocr)
        self.scene.tool_change_requested.connect(self._on_tool_change_requested)
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.scene.changed.connect(self._update_hint)
        self.scene.canvas_changed.connect(self._sync_resize_controls)
        self.scene.undo_stack.indexChanged.connect(self._sync_resize_controls)
        self.scene.undo_stack.cleanChanged.connect(self._update_title)
        self.scene.canvas_changed.connect(self._update_title)
        self.view.zoom_changed.connect(self._update_status)
        self._zoom_label = QLabel("")
        self.statusBar().addPermanentWidget(self._zoom_label)
        for txt, tip, fn in (("−", tr("Diminuir o zoom (Ctrl+-)"), lambda: self.view.zoom_by(1 / 1.25)),
                             ("+", tr("Aumentar o zoom (Ctrl+=)"), lambda: self.view.zoom_by(1.25)),
                             ("⤢", tr("Ajustar à janela"), self.view.fit_all)):
            b = QToolButton()
            b.setText(txt)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setFixedSize(26, 22)
            b.clicked.connect(lambda _=False, f=fn: f())
            self.statusBar().addPermanentWidget(b)
            if txt == "−":
                self.sl_zoom = QSlider(Qt.Orientation.Horizontal)
                self.sl_zoom.setRange(0, 1000)
                self.sl_zoom.setFixedWidth(140)
                self.sl_zoom.setToolTip(tr("Arraste para ajustar o zoom"))
                self.sl_zoom.valueChanged.connect(self._zoom_slider_moved)
                self.statusBar().addPermanentWidget(self.sl_zoom)
        self.btn_zoom100 = QToolButton()
        self.btn_zoom100.setText("100%")
        self.btn_zoom100.setToolTip(tr("Voltar ao tamanho original (100%) — Ctrl+1"))
        self.btn_zoom100.setAutoRaise(True)
        self.btn_zoom100.setFixedHeight(22)
        self.btn_zoom100.clicked.connect(lambda: self.view.set_zoom(1.0))
        self.statusBar().addPermanentWidget(self.btn_zoom100)
        self._update_status()
        self.select_tool("select" if project is not None else "arrow")
        self._update_title()
        w, h = self.scene.output_size()
        self._resize_to(w, h)

    # ------------------------------------------------------------------
    # construção da interface
    # ------------------------------------------------------------------
    def _act(self, icon: str, tip: str, slot, shortcut=None) -> QAction:
        a = QAction(ui_icon(icon), tip, self)
        a.setToolTip(f"{tip} ({QKeySequence(shortcut).toString()})" if shortcut else tip)
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(lambda _c=False: slot())
        self.addAction(a)  # garante os atalhos mesmo com a barra oculta
        return a

    def _build_main_toolbar(self):
        tb = QToolBar(tr("Principal"))
        tb.setObjectName("main")
        tb.setMovable(False)
        tb.setIconSize(QSize(24, 24))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        stack = self.scene.undo_stack
        self.act_undo = stack.createUndoAction(self, tr("Desfazer"))
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_redo = stack.createRedoAction(self, tr("Refazer"))
        self.act_redo.setShortcut(QKeySequence("Ctrl+R"))
        for act, icon, tip in ((self.act_undo, "undo", tr("Desfazer (Ctrl+Z)")), (self.act_redo, "redo", tr("Refazer (Ctrl+R)"))):
            act.setIcon(ui_icon(icon))
            act.setText(tip)          # createUndoAction acrescenta o nome do comando; fixamos o rótulo
            act.setToolTip(tip)
            tb.addAction(act)
        # atalhos de zoom continuam ativos (Ctrl+0 / Ctrl+1) sem ocupar espaço na barra
        self._act("fit", tr("Ajustar à janela"), self.view.fit_all, "Ctrl+0")
        self._act("actual", tr("Tamanho real (100%)"), lambda: self.view.set_zoom(1.0), "Ctrl+1")
        self._act("zoom_in", tr("Aumentar o zoom"), lambda: self.view.zoom_by(1.25), "Ctrl+=")
        self._act("zoom_in2", tr("Aumentar o zoom"), lambda: self.view.zoom_by(1.25), "Ctrl++")
        self._act("zoom_out", tr("Diminuir o zoom"), lambda: self.view.zoom_by(1 / 1.25), "Ctrl+-")
        tb.addSeparator()

        tb.addAction(self._act("copy", tr("Copiar imagem"), self.copy_to_clipboard, QKeySequence.StandardKey.Copy))
        tb.addAction(self._act("save", tr("Salvar e fechar"), self.save_and_close, QKeySequence.StandardKey.Save))
        tb.addAction(self._act("saveas", tr("Salvar como… e fechar"), self.save_as_and_close, "Ctrl+Shift+S"))
        tb.addSeparator()

        tb.addAction(self._act("pin", tr("Fixar na tela (sempre à frente)"), self.pin, "Ctrl+F"))
        # inserir outra imagem na composição
        self.a_paste = self._act("addimg", tr("Colar imagem da área de transferência"), self.paste_image, "Ctrl+V")
        a_new = self._act("addimg", tr("Nova captura de área"), self.add_capture)
        a_file = self._act("addimg", tr("Imagem de um arquivo…"), self.add_from_file)
        menu = QMenu(self)
        menu.addAction(tr("Nova captura de área…"), a_new.trigger)
        menu.addAction("Colar da área de transferência\tCtrl+V", self.a_paste.trigger)
        menu.addAction(tr("Imagem de um arquivo…"), a_file.trigger)
        btn_add = QToolButton()
        btn_add.setIcon(ui_icon("addimg"))
        btn_add.setToolTip(tr("Inserir imagem (nova captura, colar ou arquivo)"))
        btn_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn_add.setMenu(menu)
        tb.addWidget(btn_add)
        tb.addSeparator()
        tb.addAction(self._act("library", tr("Capturas recentes (editáveis)"), self.library_requested.emit))

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self._act("settings", tr("Configurações do Shotwise"), self.settings_requested.emit))
        # Ctrl+Enter: executa a ação de fechar configurada (copiar ou salvar) e fecha
        a_done = QAction(self)
        a_done.setShortcut("Ctrl+Return")
        a_done.triggered.connect(lambda _c=False: self.finish())
        self.addAction(a_done)

    def _build_tools(self):
        tb = QToolBar(tr("Ferramentas"), self)
        tb.setObjectName("tools")
        tb.setOrientation(Qt.Orientation.Vertical)
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        self._tools_tb = tb
        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_actions: dict[str, QAction] = {}
        for tid, label, key in TOOL_DEFS:
            act = QAction(tool_icon(tid), label, self)
            act.setCheckable(True)
            act.setToolTip(f"{label} ({key})")
            act.triggered.connect(lambda _checked, t=tid: self.select_tool(t))
            self._tool_group.addAction(act)
            tb.addAction(act)
            self._tool_actions[tid] = act
            if tid in ("select", "step", "redact"):
                tb.addSeparator()

    def _slider(self, group: str, title: str, lo: int, hi: int, value: int, fmt=None, tip: str = "") -> LabeledSlider:
        """Linha de controle deslizante no padrão do painel de fundo: título, valor à direita e a barra embaixo."""
        ls = LabeledSlider(title, lo, hi, value, fmt=fmt, tip=tip)
        self._opt_actions[group].append(self._opts_tb.addWidget(ls))
        return ls

    def _toggle_color(self, group: str, text: str, tip_check: str, tip_color: str, toggled, clicked):
        """Linha 'caixa de marcação + amostra de cor' (borda, fundo do texto, preenchimento…)."""
        cb = QCheckBox(text)
        cb.setToolTip(tip_check)
        cb.toggled.connect(toggled)
        btn = QToolButton()
        btn.setFixedSize(30, 22)
        btn.setToolTip(tip_color)
        btn.clicked.connect(clicked)
        self._opt_actions[group].append(self._opts_tb.addRow(cb, None, btn))
        return cb, btn

    def _build_options(self):
        tb = OptionsPanel(self.view)
        self._opts_tb = tb
        self._hint = HintBubble(self.view.viewport())
        self.view.installEventFilter(self)
        self.view.viewport().installEventFilter(self)
        self._opt_actions: dict[str, list] = {g: [] for g in (
            "color", "width", "font", "strength", "textbg", "fill", "step", "round", "resize", "bg", "zoomf",
            "rborder", "hlop")}

        # cor: amostra com menu (paleta e "Mais cores…") e conta-gotas só com ícone
        self.btn_color = QToolButton()
        self.btn_color.setToolTip(tr("Cor"))
        self.btn_color.setIconSize(QSize(18, 18))
        self.btn_color.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.btn_color)
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(10, 8, 10, 6)
        grid.setSpacing(6)
        for i, hexc in enumerate(PALETTE):
            sw = QToolButton()
            sw.setFixedSize(24, 24)
            sw.setToolTip(hexc.upper())
            sw.setStyleSheet(f"QToolButton{{background:{hexc};border:1px solid #8a8f99;border-radius:12px;padding:0;}}"
                             f"QToolButton:hover{{border:2px solid palette(highlight);}}")
            sw.clicked.connect(lambda _=False, c=hexc, m=menu: (self.set_color(QColor(c)), m.close()))
            grid.addWidget(sw, i // 4, i % 4)
        host_act = QWidgetAction(menu)
        host_act.setDefaultWidget(grid_host)
        menu.addAction(host_act)
        menu.addSeparator()
        menu.addAction(tr("Mais cores…"), self._pick_custom_color)
        self.btn_color.setMenu(menu)
        self.btn_eyedrop = QToolButton()
        self.btn_eyedrop.setIcon(ui_icon("eyedropper"))
        self.btn_eyedrop.setToolTip(tr("Conta-gotas: copia a cor de um ponto da imagem"))
        self.btn_eyedrop.clicked.connect(self.start_eyedropper)
        self._opt_actions["color"].append(tb.addRow(QLabel(tr("Cor")), None, self.btn_color, self.btn_eyedrop))
        self._update_color_button(self.scene.opt_color)

        # espessura
        self.ls_width = self._slider("width", tr("Espessura"), 1, 40, 4, lambda v: f"{v} px")
        self.sp_width = self.ls_width.sl
        self.sp_width.valueChanged.connect(self._on_width)

        # marca-texto: opacidade (sempre translúcido)
        from .annotations import HIGHLIGHT_DEFAULT_PCT, HIGHLIGHT_MAX_PCT, HIGHLIGHT_MIN_PCT
        self.ls_hlop = self._slider("hlop", tr("Opacidade"), HIGHLIGHT_MIN_PCT, HIGHLIGHT_MAX_PCT, HIGHLIGHT_DEFAULT_PCT,
                                    lambda v: f"{v}%",
                                    tr("Mais à direita = cor mais forte; o marca-texto continua sempre transparente"))
        self.ls_hlop.sl.valueChanged.connect(self._on_hlop)

        # tarja sólida: sempre opaca (não reversível); só borda e espessura da borda
        self._rborder_color = QColor("#ffffff")
        self.cb_rborder, self.btn_rborder = self._toggle_color(
            "rborder", tr("Borda"), tr("Desmarcado: tarja sem borda. Marcado: borda com a cor ao lado."),
            tr("Cor da borda"), lambda _c: self._on_rborder(), self._pick_rborder_color)
        self._paint_color_button(self.btn_rborder, self._rborder_color)
        self.ls_rwidth = self._slider("rborder", tr("Espessura da borda"), 1, 20, 3, lambda v: f"{v} px")
        self.ls_rwidth.sl.valueChanged.connect(self._on_rwidth)

        # linha/seta: curvatura (também ajustável arrastando o ponto do meio)
        self.ls_round = self._slider("round", tr("Curvatura"), 0, 100, 0, lambda v: f"{v}%",
                                     tr("0 = reta · arraste para curvar (ou arraste o ponto do meio no desenho)"))
        self.sl_round = self.ls_round.sl
        self.sl_round.valueChanged.connect(self._on_round)

        # marcador numerado
        self.ls_step = self._slider("step", tr("Tamanho do marcador"), 8, 80, 16, lambda v: f"{v} px",
                                    tr("Arraste para aumentar ou diminuir o marcador"))
        self.sl_step = self.ls_step.sl
        self.sl_step.valueChanged.connect(self._on_step_size)
        self._step_border_color = QColor("white")
        self.cb_step_border, self.btn_step_border = self._toggle_color(
            "step", tr("Borda"), tr("Desmarcado: marcador sem borda. Marcado: borda com a cor ao lado."),
            tr("Cor da borda do marcador"), self._on_step_border, self._pick_step_border_color)
        self.cb_step_border.setChecked(True)
        self._paint_color_button(self.btn_step_border, self._step_border_color)

        # lupa: aumento e seta
        self.ls_zoomf = self._slider("zoomf", tr("Aumento"), 12, 80, 25, lambda v: f"{v / 10:.1f}×".replace(".", ","),
                                     tr("Arraste para ampliar mais ou menos"))
        self.sl_zoomf = self.ls_zoomf.sl
        self.sl_zoomf.valueChanged.connect(self._on_zoomf)
        self.cb_zarrow = QCheckBox(tr("Seta ligando à ampliação"))
        self.cb_zarrow.setChecked(True)
        self.cb_zarrow.setToolTip(tr("Seta ligando a região à ampliação; arraste o ponto azul para curvá-la"))
        self.cb_zarrow.toggled.connect(self._on_zoom_arrow)
        self._opt_actions["zoomf"].append(tb.addWidget(self.cb_zarrow))

        # texto
        self.ls_font = self._slider("font", tr("Tamanho do texto"), 10, 240, 28, lambda v: f"{v} pt")
        self.sp_font = self.ls_font.sl
        self.sp_font.valueChanged.connect(self._on_font)
        self._textbg_color = QColor("#ffffff")
        self.cb_textbg, self.btn_textbg = self._toggle_color(
            "textbg", tr("Fundo do texto"), tr("Desmarcado: fundo transparente. Marcado: caixa de texto com a cor ao lado."),
            tr("Cor do fundo do texto (aceita transparência parcial)"), self._on_textbg, self._pick_textbg_color)
        self._paint_textbg_button()

        # preenchimento de retângulo/elipse
        self._fill_color = QColor(10, 132, 255, 90)
        self.cb_fill, self.btn_fill = self._toggle_color(
            "fill", tr("Preenchimento"), tr("Desmarcado: só o contorno. Marcado: forma preenchida com a cor ao lado."),
            tr("Cor do preenchimento (aceita transparência parcial)"), self._on_fill, self._pick_fill_color)
        self._paint_color_button(self.btn_fill, self._fill_color)
        self.ls_fillop = self._slider("fill", tr("Opacidade do preenchimento"), 5, 100,
                                      round(self._fill_color.alphaF() * 100), lambda v: f"{v}%",
                                      tr("Transparência do preenchimento: 100% = cor cheia"))
        self.sl_fillop = self.ls_fillop.sl
        self.sl_fillop.valueChanged.connect(self._on_fill_opacity)

        # intensidade (pixelar/desfocar)
        self.ls_strength = self._slider("strength", tr("Intensidade"), 8, 64, 16,
                                        lambda v: f"{round((v - 8) * 100 / 56)}%",
                                        tr("Quanto maior, menos legível fica o trecho (abaixo disso o texto pode ser reconstruído)"))
        self.sl_strength = self.ls_strength.sl
        self.sl_strength.valueChanged.connect(self._on_strength)

        # redimensionar: escala, tamanho exato, girar e espelhar
        self.ls_scale = self._slider("resize", tr("Escala"), 5, 400, 100, lambda v: f"{v}%",
                                     tr("Arraste para ampliar ou reduzir a imagem final (Shift nas alças = esticar)"))
        self._wire_scale_slider()
        self.lbl_outsize = QLabel("")
        self.lbl_outsize.setStyleSheet("color:gray;")
        self._opt_actions["resize"].append(tb.addWidget(self.lbl_outsize))
        b1 = QPushButton(tr("Tamanho exato…"))
        b1.clicked.connect(self.edit_size)
        b2 = QPushButton(tr("Original"))
        b2.setToolTip(tr("Tamanho original (100%)"))
        b2.clicked.connect(lambda: self.scene.set_export_scale(1.0))
        self._opt_actions["resize"].append(tb.addRow(b1, b2))
        self._opt_actions["resize"].append(tb.addSection(tr("Girar")))

        def mk(txt, tip, fn):
            b = QPushButton(txt)
            b.setToolTip(tip + " — " + tr("as anotações são incorporadas à imagem"))
            b.clicked.connect(fn)
            return b
        self._opt_actions["resize"].append(tb.addRow(
            mk("⟲ 90°", tr("Girar 90° para a esquerda (270° à direita)"), lambda: self.rotate_image(-90)),
            mk("⟳ 90°", tr("Girar 90° para a direita"), lambda: self.rotate_image(90)),
            mk("180°", tr("Girar 180°"), lambda: self.rotate_image(180))))
        self._opt_actions["resize"].append(tb.addSection(tr("Espelhar")))
        self._opt_actions["resize"].append(tb.addRow(
            mk("⇋  " + tr("Horizontal"), tr("Espelhar da esquerda para a direita"), lambda: self.flip_image(True)),
            mk("⇅  " + tr("Vertical"), tr("Espelhar de cima para baixo"), lambda: self.flip_image(False))))

        # fundo: tipo (degradê ou cor sólida), estilo, degradês prontos, cor 1 / cor 2, sombra e transparente
        from .annotations import BG_PRESETS, BG_SOLIDS, SHADOW_DIRS

        self.cb_bg_gradient = QCheckBox(tr(" Degradê "))
        self.cb_bg_gradient.setToolTip(tr("Marcado: degradê com duas cores. Desmarcado: uma cor sólida."))
        self.cb_bg_gradient.toggled.connect(self._bg_kind_changed)
        self._opt_actions["bg"].append(tb.addWidget(self.cb_bg_gradient))

        # degradês prontos: grade de amostras
        host = QWidget()
        grid = QGridLayout(host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(5)
        for i, (name, c1, c2) in enumerate(BG_PRESETS):
            sw = QToolButton()
            sw.setFixedSize(46, 32)
            sw.setToolTip(name)
            sw.setStyleSheet(f"QToolButton{{border:2px solid transparent;border-radius:7px;"
                             f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {c1},stop:1 {c2});}}"
                             f"QToolButton:hover{{border:2px solid palette(highlight);}}")
            sw.clicked.connect(lambda _=False, a1=c1, a2=c2: self._bg_apply(color1=a1, color2=a2, solid=False))
            grid.addWidget(sw, i // 4, i % 4)
        self._bg_act_presets = tb.addWidget(host)
        self._opt_actions["bg"].append(self._bg_act_presets)

        self._bg_style_actions: dict[str, QAction] = {}
        self.btn_bg_style = QToolButton()
        self.btn_bg_style.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_bg_style.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_bg_style.setIconSize(QSize(34, 20))
        style_menu = QMenu(self.btn_bg_style)
        grp = QActionGroup(style_menu)
        for mode, label in (("linear", tr("Linear — cores se misturam entre as extremidades")),
                            ("radial", tr("Radial — cores saindo do centro")),
                            ("blur", tr("Desfoque — manchas suaves de cor")),
                            ("mesh", tr("Mesclado (mesh) — várias cores se misturando"))):
            act = style_menu.addAction(label)
            act.setCheckable(True)
            grp.addAction(act)
            act.triggered.connect(lambda _=False, m=mode: self._bg_apply(mode=m))
            self._bg_style_actions[mode] = act
        self.btn_bg_style.setMenu(style_menu)
        self.btn_bg_swap = QToolButton()
        self.btn_bg_swap.setIcon(ui_icon("swap"))
        self.btn_bg_swap.setToolTip(tr("Inverter as cores"))
        self.btn_bg_swap.clicked.connect(self._bg_swap_colors)
        self._bg_act_style = tb.addRow(self.btn_bg_style, None, self.btn_bg_swap)
        self._bg_act_swap = self._bg_act_style
        self._opt_actions["bg"].append(self._bg_act_style)

        self.btn_bg_c1, _ = self._bg_color_button(1, BG_SOLIDS)
        self.btn_bg_c2, _ = self._bg_color_button(2, BG_SOLIDS)
        self._bg_act_c1 = tb.addRow(self.btn_bg_c1, self.btn_bg_c2)       # uma ao lado da outra
        self._bg_act_c2 = _Handle(self.btn_bg_c2)
        self._opt_actions["bg"].append(self._bg_act_c1)

        tb.addSeparator()
        self._opt_actions["bg"].append(tb.addWidget(QLabel(tr("Tamanho e cantos"))))
        self.sl_bg_pad = self._bg_slider("padding", tr("Margem do fundo"), 0, 200)
        self.sl_bg_inner = self._bg_slider("radius", tr("Cantos da imagem"), 0, 80)
        self.sl_bg_outer = self._bg_slider("outer_radius", tr("Cantos do fundo"), 0, 120)

        self.cb_bg_shadow = QCheckBox(tr(" Sombra "))
        self.cb_bg_shadow.toggled.connect(lambda on: self._bg_apply(shadow=on))
        self._opt_actions["bg"].append(tb.addWidget(self.cb_bg_shadow))
        self.sl_bg_shadow = self._bg_slider("shadow_blur", tr("Tamanho da sombra"), 4, 120)
        self.btn_bg_shadow = QToolButton()
        self.btn_bg_shadow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_bg_shadow.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_bg_shadow.setIconSize(QSize(34, 24))
        smenu = QMenu(self.btn_bg_shadow)
        self._bg_dir_actions = {}
        names = {"down": tr("Para baixo"), "up": tr("Para cima"), "left": tr("Para a esquerda"),
                 "right": tr("Para a direita"), "down_right": tr("Baixo e direita"), "down_left": tr("Baixo e esquerda"),
                 "up_right": tr("Cima e direita"), "up_left": tr("Cima e esquerda"),
                 "center": tr("Ao redor (sem deslocamento)")}
        for key in SHADOW_DIRS:
            act = smenu.addAction(names[key])
            act.setCheckable(True)
            act.triggered.connect(lambda _=False, k=key: self._bg_apply(shadow_dir=k, shadow=True))
            self._bg_dir_actions[key] = act
        self._bg_dir_names = names
        smenu.setStyleSheet("QMenu::icon{padding-left:6px;}")
        self.btn_bg_shadow.setMenu(smenu)
        self._opt_actions["bg"].append(tb.addWidget(self.btn_bg_shadow))

        tb.addSeparator()
        self.cb_bg_transp = QCheckBox(tr(" Transparente "))
        self.cb_bg_transp.setToolTip(tr("PNG com margem e sombra, sem cor de fundo"))
        self.cb_bg_transp.toggled.connect(lambda on: self._bg_apply(transparent=on))
        self._opt_actions["bg"].append(tb.addWidget(self.cb_bg_transp))
        b = QPushButton(tr("Remover fundo"))
        b.clicked.connect(self.remove_background)
        self._opt_actions["bg"].append(tb.addWidget(b))


    # ------------------------------------------------------------------
    # ferramentas e opções
    # ------------------------------------------------------------------
    # --- últimas opções das ferramentas -----------------------------------------
    @staticmethod
    def _argb(c: QColor | None):
        return None if c is None else c.name(QColor.NameFormat.HexArgb)

    def collect_tool_options(self) -> dict:
        sc = self.scene
        out = {
            "color": sc.opt_color.name(), "width": int(sc.opt_width), "font": int(sc.opt_font),
            "strength": int(sc.opt_strength), "step_size": int(sc.opt_step_size), "round": int(sc.opt_round),
            "zoom": float(sc.opt_zoom), "zoom_arrow": bool(sc.opt_zoom_arrow),
            "step_border": self._argb(sc.opt_step_border), "text_bg": self._argb(sc.opt_text_bg),
            "fill": self._argb(sc.opt_fill), "fill_color": self._argb(self._fill_color),
            "textbg_color": self._argb(self._textbg_color),
            "step_border_color": self._argb(self._step_border_color),
            "redact_width": int(sc.opt_redact_width), "highlight_opacity": int(sc.opt_highlight_opacity),
            "redact_border": self._argb(sc.opt_redact_border), "redact_border_color": self._argb(self._rborder_color),
        }
        bg = sc.background.to_dict()
        bg["enabled"] = False
        out["background"] = bg
        up = self._opts_tb._user_pos
        out["panel_pos"] = [up.x(), up.y()] if up is not None else None
        return out

    def save_tool_options(self):
        try:
            self.cfg.tool_options = self.collect_tool_options()
            self.cfg.save()
        except Exception:  # noqa: BLE001 - guardar as opções nunca pode atrapalhar o editor
            log.debug("falha ao guardar as opções das ferramentas", exc_info=True)

    def restore_tool_options(self, new_image: bool = True):
        d = self.cfg.tool_options if isinstance(self.cfg.tool_options, dict) else {}
        if not d:
            return

        def col(key):
            c = QColor(str(d.get(key) or ""))
            return c if c.isValid() else None

        def num(key, lo, hi, default):
            v = d.get(key)
            return min(max(v, lo), hi) if isinstance(v, (int, float)) and not isinstance(v, bool) else default

        try:
            c = col("color")
            if c is not None:
                self.set_color(c)
            self.sp_width.setValue(int(num("width", self.sp_width.minimum(), self.sp_width.maximum(), self.sp_width.value())))
            self.sp_font.setValue(int(num("font", self.sp_font.minimum(), self.sp_font.maximum(), self.sp_font.value())))
            self.sl_strength.setValue(int(num("strength", self.sl_strength.minimum(), self.sl_strength.maximum(),
                                              self.sl_strength.value())))
            self.sl_step.setValue(int(num("step_size", self.sl_step.minimum(), self.sl_step.maximum(), self.sl_step.value())))
            self.sl_round.setValue(int(num("round", self.sl_round.minimum(), self.sl_round.maximum(), self.sl_round.value())))
            self.sl_zoomf.setValue(round(num("zoom", 1.2, 8.0, self.scene.opt_zoom) * 10))
            self.ls_rwidth.setValue(int(num("redact_width", 1, 20, 3)))
            self.ls_hlop.setValue(int(num("highlight_opacity", self.ls_hlop.sl.minimum(), self.ls_hlop.sl.maximum(),
                                          self.ls_hlop.value())))
            rc = col("redact_border_color")
            if rc is not None:
                self._rborder_color = rc
                self._paint_color_button(self.btn_rborder, rc)
            self.cb_rborder.setChecked(d.get("redact_border") is not None)
            if isinstance(d.get("zoom_arrow"), bool):
                self.cb_zarrow.setChecked(d["zoom_arrow"])
            fc = col("fill_color")
            if fc is not None:
                self._fill_color = fc
                self._paint_color_button(self.btn_fill, fc)
                self.ls_fillop.set_quiet(max(5, round(fc.alphaF() * 100)))
            self.cb_fill.setChecked(d.get("fill") is not None)
            tc = col("textbg_color")
            if tc is not None:
                self._textbg_color = tc
                self._paint_textbg_button()
            self.cb_textbg.setChecked(d.get("text_bg") is not None)
            bc = col("step_border_color")
            if bc is not None:
                self._step_border_color = bc
                self._paint_color_button(self.btn_step_border, bc)
            sb = col("step_border")
            self.cb_step_border.setChecked(sb is None or sb.alpha() > 0)
            self._on_step_border()
            if new_image and isinstance(d.get("background"), dict):
                bs = BackgroundSettings.from_dict(d["background"])
                bs.enabled = False
                self.scene.background = bs
            pp = d.get("panel_pos")
            if isinstance(pp, list) and len(pp) == 2 and all(isinstance(v, int) for v in pp):
                self._opts_tb._user_pos = QPoint(pp[0], pp[1])
        except Exception:  # noqa: BLE001
            log.debug("falha ao restaurar as opções das ferramentas", exc_info=True)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Resize and hasattr(self, "_opts_tb"):
            if obj is self.view:
                self._opts_tb.reposition()
            elif obj is self.view.viewport():
                self._hint.reposition()
                self._apply_panel_space()
        return super().eventFilter(obj, ev)

    def _on_tool_change_requested(self, tool: str):
        if tool in self._tool_actions:
            self.select_tool(tool, keep_selection=True)

    def start_eyedropper(self):
        """Conta-gotas: o próximo clique na imagem escolhe a cor daquele ponto."""
        def done(c):
            self.view.viewport().setCursor({"select": Qt.CursorShape.ArrowCursor,
                                            "text": Qt.CursorShape.IBeamCursor}.get(self.scene.tool, Qt.CursorShape.CrossCursor))
            if c is not None:
                self.set_color(c)
                self.statusBar().showMessage(tr("Cor escolhida:") + " " + c.name().upper(), 4000)
        self.scene.picker = done
        self.view.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.statusBar().showMessage(tr("Conta-gotas: clique na imagem para escolher a cor."), 6000)

    def select_tool(self, tool: str, keep_selection: bool = False):
        if getattr(self, "_tool_opts_ready", False):
            self.save_tool_options()
        self._tool_opts_ready = True
        self.scene.set_tool(tool, keep_selection)
        if tool == "background" and not self.scene.background.enabled:
            self._enable_background()
        self._tool_actions[tool].setChecked(True)
        self._sync_bg_controls()
        cursors = {"select": Qt.CursorShape.ArrowCursor, "text": Qt.CursorShape.IBeamCursor}
        self.view.viewport().setCursor(cursors.get(tool, Qt.CursorShape.CrossCursor))
        self._update_options()

    # grupos de opções por tipo de item selecionado (ferramenta "Selecionar")
    @staticmethod
    def _groups_for_item(it) -> set[str]:
        from .annotations import LineItem, PenItem, ShapeItem, StepItem, ZoomItem

        if isinstance(it, ZoomItem):
            return {"color", "width", "zoomf"}
        if isinstance(it, ShapeItem):
            return {"rect": {"color", "width", "fill"}, "ellipse": {"color", "width", "fill"},
                    "highlight": {"color", "hlop"}, "redact": {"color", "rborder"}, "pixelate": {"strength"},
                    "blur": {"strength"}}.get(it.kind, set())
        if isinstance(it, LineItem):
            return {"color", "width"} | {"round"}
        if isinstance(it, PenItem):
            return {"color", "width"}
        if isinstance(it, TextItem):
            return {"color", "font", "textbg"}
        if isinstance(it, StepItem):
            return {"color", "step"}
        return set()

    def _tool_groups(self, tool: str) -> set[str]:
        g = set()
        for name, used in (("color", USES_COLOR), ("width", USES_WIDTH), ("font", USES_FONT), ("step", USES_STEP),
                           ("strength", USES_STRENGTH), ("textbg", USES_TEXTBG), ("fill", USES_FILL)):
            if tool in used and tool != "select":
                g.add(name)
        if tool in ("arrow", "line"):
            g.add("round")
        if tool == "zoom":
            g.add("zoomf")
        if tool == "redact":
            g.add("rborder")
        if tool == "highlight":
            g.add("hlop")
        g |= {"resize": {"resize"}, "background": {"bg"}}.get(tool, set())
        return g

    def _update_options(self):
        """Mostra as opções da ferramenta ativa ou, com 'Selecionar', as do item selecionado."""
        tool = self.scene.tool
        if tool == "select":
            groups: set[str] = set()
            sel = [i for i in self.scene.selectedItems() if self.scene._is_annotation(i)]
            for it in sel:
                groups |= self._groups_for_item(it)
            if len(sel) == 1:
                self._sync_controls(sel[0])
        else:
            groups = self._tool_groups(tool)
            sel = [i for i in self.scene.selectedItems() if self.scene._is_annotation(i)]
            if len(sel) == 1:
                self._sync_controls(sel[0])
        for group, acts in self._opt_actions.items():
            for a in acts:
                a.setVisible(group in groups)
        self._bg_visibility()
        self._opts_tb.setVisible(bool(groups))       # sem ferramenta em uso (ou item sem opções), o painel some
        self._opts_tb.reposition()
        self._apply_panel_space()
        self._update_hint()
        self._sync_resize_controls()

    def _apply_panel_space(self, *_):
        """O painel só flutua sobre a imagem (translúcido e móvel): nenhuma faixa é reservada na área de edição."""
        if self.view.viewportMargins().right():
            self.view.setViewportMargins(0, 0, 0, 0)
        self._opts_tb.reposition()

    def _update_hint(self, *_):
        """Recortar e OCR não têm opções: mostram só um balão com o que fazer."""
        try:
            tool = self.scene.tool
            if tool == "crop":
                if self.scene.crop_active:
                    self._hint.set_content(tr("Pressione Enter para confirmar o recorte (Esc cancela)."),
                                           [(tr("Confirmar"), self.apply_crop)])
                elif self.scene.clip is not None:
                    self._hint.set_content(tr("Selecione na imagem a área que deseja manter."),
                                           [(tr("Remover recorte"), self.reset_crop)])
                else:
                    self._hint.set_content(tr("Selecione na imagem a área que deseja manter."))
            elif tool == "ocr":
                self._hint.set_content(tr("Arraste sobre o texto da imagem para reconhecê-lo."),
                                       [(tr("Reconhecer a imagem inteira"),
                                         lambda: self.run_ocr(self.scene.canvas_rect()))])
            else:
                self._hint.hide()
        except RuntimeError:
            return

    def _bg_visibility(self):
        """Cor sólida esconde estilo, degradês prontos e a segunda cor."""
        if not hasattr(self, "_bg_act_c2") or self.scene.tool != "background":
            return
        gradient = not self.scene.background.solid
        for act in (self._bg_act_style, self._bg_act_presets, self._bg_act_c2, self._bg_act_swap):
            act.setVisible(gradient)

    def _sync_controls(self, it):
        """Reflete os valores do item selecionado nos controles, sem alterar o item."""
        from .annotations import LineItem, PenItem, ShapeItem, StepItem, ZoomItem

        def quiet(widget, setter, value):
            widget.blockSignals(True)
            setter(value)
            widget.blockSignals(False)
            ls = getattr(widget, "_ls", None)
            if ls is not None:
                ls.refresh()

        if isinstance(it, ZoomItem):
            quiet(self.sl_zoomf, self.sl_zoomf.setValue, round(it.factor * 10))
            quiet(self.cb_zarrow, self.cb_zarrow.setChecked, it.arrow)
            quiet(self.sp_width, self.sp_width.setValue, int(it.width))
        elif isinstance(it, ShapeItem):
            if it.kind in ("rect", "ellipse"):
                quiet(self.sp_width, self.sp_width.setValue, int(it.width))
                quiet(self.cb_fill, self.cb_fill.setChecked, it.fill is not None)
                if it.fill is not None:
                    self._fill_color = QColor(it.fill)
                    self._paint_color_button(self.btn_fill, self._fill_color)
                    quiet(self.sl_fillop, self.sl_fillop.setValue, round(self._fill_color.alphaF() * 100))
            if it.kind in ("pixelate", "blur"):
                quiet(self.sl_strength, self.sl_strength.setValue, int(it.strength))
            if it.kind == "highlight":
                from .annotations import highlight_pct
                quiet(self.ls_hlop.sl, self.ls_hlop.sl.setValue, highlight_pct(it.color))
            if it.kind == "redact":
                quiet(self.cb_rborder, self.cb_rborder.setChecked, it.fill is not None)
                quiet(self.ls_rwidth.sl, self.ls_rwidth.sl.setValue, int(it.width))
                if it.fill is not None:
                    self._rborder_color = QColor(it.fill.red(), it.fill.green(), it.fill.blue())
                    self._paint_color_button(self.btn_rborder, self._rborder_color)
        if isinstance(it, (LineItem, PenItem)):
            quiet(self.sp_width, self.sp_width.setValue, int(it.width))
        if isinstance(it, LineItem):
            quiet(self.sl_round, self.sl_round.setValue, int(it.round))
        if isinstance(it, TextItem):
            quiet(self.sp_font, self.sp_font.setValue, int(it.size))
            quiet(self.cb_textbg, self.cb_textbg.setChecked, it.bg is not None)
            if it.bg is not None:
                self._textbg_color = QColor(it.bg)
                self._paint_textbg_button()
        if isinstance(it, StepItem):
            quiet(self.sl_step, self.sl_step.setValue, int(it.radius))
            quiet(self.cb_step_border, self.cb_step_border.setChecked, it.border.alpha() > 0)
            if it.border.alpha() > 0:
                self._step_border_color = QColor(it.border.red(), it.border.green(), it.border.blue())
                self._paint_color_button(self.btn_step_border, self._step_border_color)
        color = getattr(it, "color", None)
        if color is not None:
            self._update_color_button(color)

    def set_color(self, color: QColor):
        self.scene.opt_color = QColor(color)
        self.scene.apply_style_to_selection(color=QColor(color))
        self._update_color_button(color)

    @staticmethod
    def _swatch_icon(color: QColor, size: int = 18) -> QIcon:
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#8a8f99"), 1))
        p.setBrush(color)
        p.drawEllipse(QRectF(1, 1, size - 2, size - 2))
        p.end()
        return QIcon(pm)

    def _wire_scale_slider(self):
        """Escala da saída: ao arrastar mostra ao vivo e grava um único passo de desfazer."""
        ls, sc = self.ls_scale, self.scene
        state: dict = {"old": None}

        def pressed():
            state["old"] = (sc.export_scale, sc.export_stretch)

        def changed(v: int):
            if ls.sl.isSliderDown():
                sc.export_scale = v / 100
                sc.settings_changed()
            else:
                sc.set_export_scale(v / 100)

        def released():
            old, state["old"] = state["old"], None
            if old is None:
                return
            sc.export_scale, sc.export_stretch = old
            sc.settings_changed()
            sc.set_export_scale(ls.value() / 100)

        ls.sl.sliderPressed.connect(pressed)
        ls.sl.valueChanged.connect(changed)
        ls.sl.sliderReleased.connect(released)

    def _sync_resize_controls(self, *_):
        try:
            if not self.ls_scale.sl.isSliderDown():
                self.ls_scale.set_quiet(min(max(round(self.scene.export_scale * 100), 5), 400))
            w, h = self.scene.output_size()
            self.lbl_outsize.setText(tr("Saída") + f": {w} × {h} px")
        except RuntimeError:
            return

    def _update_color_button(self, color: QColor):
        self.btn_color.setIcon(self._swatch_icon(QColor(color)))

    def _pick_custom_color(self):
        c = QColorDialog.getColor(self.scene.opt_color, self, tr("Escolher cor"))
        if c.isValid():
            self.set_color(c)

    def _on_width(self, v: int):
        self.scene.opt_width = v
        self.scene.apply_style_to_selection(width=v)

    def _on_font(self, v: int):
        self.scene.opt_font = v
        self.scene.apply_style_to_selection(font_size=v)

    def _on_selection_changed(self):
        try:
            self._update_options()
        except RuntimeError:        # a cena foi destruída (janela fechando)
            return

    def _on_round(self, v: int):
        self.scene.opt_round = v
        self.scene.apply_style_to_selection(arrow_round=v)

    def _on_zoom_factor_dragged(self, f: float):
        self.ls_zoomf.set_quiet(round(f * 10))

    def _on_zoom_arrow(self, on: bool):
        self.scene.opt_zoom_arrow = on
        self.scene.apply_style_to_selection(zoom_arrow=on)

    def _on_zoomf(self, v: int):
        self.scene.opt_zoom = v / 10
        self.scene.apply_style_to_selection(zoom=v / 10)

    def _on_step_size(self, v: int):
        self.scene.opt_step_size = v
        self.scene.apply_style_to_selection(step_size=v)

    def _on_hlop(self, v: int):
        self.scene.opt_highlight_opacity = v
        self.scene.apply_style_to_selection(highlight_opacity=v)

    def _on_rborder(self):
        b = QColor(self._rborder_color) if self.cb_rborder.isChecked() else None
        self.scene.opt_redact_border = b
        self.scene.apply_style_to_selection(redact_border=b)

    def _on_rwidth(self, v: int):
        self.scene.opt_redact_width = v
        self.scene.apply_style_to_selection(redact_width=v)

    def _pick_rborder_color(self):
        c = QColorDialog.getColor(self._rborder_color, self, tr("Cor da borda"))
        if c.isValid():
            self._rborder_color = QColor(c.red(), c.green(), c.blue())
            self._paint_color_button(self.btn_rborder, self._rborder_color)
            if not self.cb_rborder.isChecked():
                self.cb_rborder.setChecked(True)
            else:
                self._on_rborder()

    def _on_strength(self, v: int):
        self.scene.opt_strength = v
        self.scene.apply_style_to_selection(strength=v)

    def _paint_textbg_button(self):
        c = self._textbg_color
        self.btn_textbg.setStyleSheet(f"QToolButton{{background:rgba({c.red()},{c.green()},{c.blue()},{c.alpha()});"
                                      f"border:2px solid #5a5f6b;border-radius:4px;}}")

    def _current_textbg(self) -> QColor | None:
        return QColor(self._textbg_color) if self.cb_textbg.isChecked() else None

    def _on_textbg(self, _checked: bool):
        bg = self._current_textbg()
        self.scene.opt_text_bg = bg
        self.scene.apply_style_to_selection(text_bg=bg)

    def _current_step_border(self) -> QColor:
        return QColor(self._step_border_color) if self.cb_step_border.isChecked() else QColor(0, 0, 0, 0)

    def _on_step_border(self, _checked: bool = False):
        b = self._current_step_border()
        self.scene.opt_step_border = b
        self.scene.apply_style_to_selection(step_border=b)

    def _pick_step_border_color(self):
        c = QColorDialog.getColor(self._step_border_color, self, tr("Cor da borda do marcador"))
        if c.isValid():
            self._step_border_color = QColor(c.red(), c.green(), c.blue())
            self._paint_color_button(self.btn_step_border, self._step_border_color)
            if not self.cb_step_border.isChecked():
                self.cb_step_border.setChecked(True)      # dispara _on_step_border
            else:
                self._on_step_border()

    def _pick_textbg_color(self):
        c = QColorDialog.getColor(self._textbg_color, self, tr("Cor do fundo do texto"),
                                  QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self._textbg_color = c
            self._paint_textbg_button()
            if not self.cb_textbg.isChecked():
                self.cb_textbg.setChecked(True)      # dispara _on_textbg
            else:
                self._on_textbg(True)

    @staticmethod
    def _paint_color_button(btn: QToolButton, c: QColor):
        btn.setStyleSheet(f"QToolButton{{background:rgba({c.red()},{c.green()},{c.blue()},{c.alpha()});"
                          f"border:2px solid #5a5f6b;border-radius:4px;}}")

    def _current_fill(self) -> QColor | None:
        return QColor(self._fill_color) if self.cb_fill.isChecked() else None

    def _on_fill(self, _checked: bool):
        fill = self._current_fill()
        self.scene.opt_fill = fill
        self.scene.apply_style_to_selection(shape_fill=fill)

    def _on_fill_opacity(self, v: int):
        self._fill_color.setAlphaF(v / 100)
        self._paint_color_button(self.btn_fill, self._fill_color)
        if not self.cb_fill.isChecked():
            self.cb_fill.setChecked(True)          # já aplica o preenchimento
        else:
            self._on_fill(True)

    def _pick_fill_color(self):
        c = QColorDialog.getColor(self._fill_color, self, tr("Cor do preenchimento"),
                                  QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self._fill_color = c
            self._paint_color_button(self.btn_fill, c)
            self.ls_fillop.set_quiet(max(5, round(c.alphaF() * 100)))
            if not self.cb_fill.isChecked():
                self.cb_fill.setChecked(True)
            else:
                self._on_fill(True)

    def _enable_background(self):
        old = self.scene.background.copy()
        new = old.copy()
        new.enabled = True
        new.padding = new.padding or 40
        self.scene.commit_background(old, new)
        self.view.fit_initial()

    def remove_background(self):
        old = self.scene.background.copy()
        if old.enabled:
            new = old.copy()
            new.enabled = False
            self.scene.commit_background(old, new)
            self.view.fit_initial()

    # --- OCR -------------------------------------------------------------
    def run_ocr(self, rect):
        img = self.scene.render_scene_rect(rect, min_side=1200)
        if img.isNull():
            return
        self.statusBar().showMessage(tr("Reconhecendo texto…"))
        self.view.viewport().setCursor(Qt.CursorShape.BusyCursor)

        def done(text: str, err: str):
            self.view.viewport().unsetCursor()
            self.statusBar().clearMessage()
            if err:
                QMessageBox.warning(self, tr("Shotwise — OCR"), err)
            elif not text.strip():
                QMessageBox.information(self, tr("Shotwise — OCR"), tr("Nenhum texto foi reconhecido nesta região."))
            else:
                OcrDialog(text, self).exec()

        self._ocr_jobs.append(start_ocr(img, done, self))

    def apply_crop(self):
        if self.scene.apply_crop():
            # mantém o zoom atual (sem "ampliar" o recorte) e só centraliza o que sobrou
            self.view.centerOn(self.scene.canvas_rect().center())
            self.select_tool("select")

    def reset_crop(self):
        if self.scene.clip is not None:
            from .annotations import AttrCommand

            self.scene.undo_stack.push(AttrCommand(self.scene, "clip", self.scene.clip, None, tr("Remover recorte")))
            self.view.centerOn(self.scene.canvas_rect().center())

    # ------------------------------------------------------------------
    # composição: mais imagens, fundo, tamanho
    # ------------------------------------------------------------------
    def _insert(self, image: QImage, label: str):
        layer = self.scene.insert_image(image, label)
        self.select_tool("select")
        layer.setSelected(True)
        self.view.fit_initial()

    def add_capture(self):
        """Pede ao aplicativo uma nova captura de área e a insere como nova camada."""
        self.capture_requested.emit(lambda img: self._insert(img, tr("Adicionar captura")))

    def paste_image(self):
        fi = self.scene.focusItem()
        if isinstance(fi, TextItem) and fi.editing:
            fi.textCursor().insertText(QGuiApplication.clipboard().text())
            return
        img = QGuiApplication.clipboard().image()
        if img.isNull() or img.width() * img.height() > MAX_IMPORT_PIXELS:
            self.statusBar().showMessage(tr("Não há imagem na área de transferência."), 4000)
            return
        self._insert(img, tr("Colar imagem"))

    def add_from_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, tr("Inserir imagem"), str(Path(self.cfg.save_dir)),
                                               tr("Imagens (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"))
        if fname:
            self._insert_file(fname)

    def _insert_file(self, fname: str):
        img = load_image_file(fname)
        if img is None:
            QMessageBox.warning(self, "Shotwise", tr("Não foi possível abrir essa imagem (formato ou tamanho inválido)."))
            return
        self._insert(img, tr("Inserir imagem"))

    def dragEnterEvent(self, ev):
        md = ev.mimeData()
        if md.hasImage() or any(u.isLocalFile() for u in md.urls()):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        md = ev.mimeData()
        done = False
        for u in md.urls():
            if u.isLocalFile() and u.toLocalFile().lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")):
                self._insert_file(u.toLocalFile())
                done = True
        if not done and md.hasImage():
            img = QImage(md.imageData())
            if not img.isNull():
                self._insert(img, tr("Inserir imagem"))
        ev.acceptProposedAction()

    def edit_background(self):
        self._enable_background()

    def _open_bg_dialog(self):
        BackgroundDialog(self.scene, self).exec()
        self._sync_bg_controls()
        self.view.fit_initial()

    def _bg_apply(self, **changes):
        """Altera o fundo (com desfazer). Escolher cor ou estilo liga o fundo e desliga o transparente."""
        old = self.scene.background.copy()
        new = old.copy()
        for k, v in changes.items():
            setattr(new, k, v)
        if "shadow_blur" in changes:
            new.shadow = True
        if not (set(changes) <= {"shadow", "transparent", "shadow_blur", "shadow_dir", "padding", "radius", "outer_radius"}):
            new.transparent = False
        new.enabled = True
        new.padding = new.padding or 40
        if new.to_dict() != old.to_dict():
            self.scene.commit_background(old, new)
            if not old.enabled:
                self.view.fit_initial()
        self._sync_bg_controls()

    def _bg_slider(self, key: str, title: str, lo: int, hi: int):
        """Controle deslizante de um ajuste do fundo: mostra ao vivo enquanto arrasta e grava um único passo de desfazer."""
        sl = LabeledSlider(title, lo, hi, getattr(BackgroundSettings(), key))
        state: dict = {"old": None}

        def modified(v: int) -> BackgroundSettings:
            new = self.scene.background.copy()
            setattr(new, key, v)
            new.enabled = True
            if key == "shadow_blur":
                new.shadow = True
            return new

        def pressed():
            state["old"] = self.scene.background.copy()

        def changed(v: int):
            if sl.sl.isSliderDown():
                self.scene.preview_background(modified(v))
            else:
                self._bg_apply(**{key: v})

        def released():
            old, state["old"] = state["old"], None
            if old is None:
                return
            new = self.scene.background.copy()
            self.scene.preview_background(old)
            if new.to_dict() != old.to_dict():
                self.scene.commit_background(old, new)
            self._sync_bg_controls()

        sl.sl.sliderPressed.connect(pressed)
        sl.sl.valueChanged.connect(changed)
        sl.sl.sliderReleased.connect(released)
        self._opt_actions["bg"].append(self._opts_tb.addWidget(sl))
        return sl

    def _bg_swap_colors(self):
        bs = self.scene.background
        self._bg_apply(color1=bs.color2, color2=bs.color1)

    def _bg_color_button(self, which: int, solids):
        """Botão de cor do fundo: lista de cores com amostra e 'Outra cor…'."""
        btn = QToolButton()
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        menu = QMenu(btn)
        key = "color1" if which == 1 else "color2"
        for name, hexc in solids:
            act = menu.addAction(self._swatch_icon(QColor(hexc)), name)
            act.triggered.connect(lambda _=False, c=hexc, k=key: self._bg_set_color(k, c))
        menu.addSeparator()
        menu.addAction(tr("Outra cor…"), lambda k=key: self._bg_pick_color(k))
        btn.setMenu(menu)
        return btn, None

    def opts_toolbar_add(self, widget):
        return self._opts_tb.addWidget(widget)

    def _bg_set_color(self, key: str, hexc: str):
        self._bg_apply(**{key: hexc})

    def _bg_pick_color(self, key: str):
        cur = getattr(self.scene.background, key)
        title = tr("Cor do fundo") if key == "color1" else tr("Segunda cor")
        c = QColorDialog.getColor(QColor(cur), self, title)
        if c.isValid():
            self._bg_apply(**{key: c.name()})

    def _bg_kind_changed(self, gradient: bool):
        bs = self.scene.background
        if not gradient:
            self._bg_apply(solid=True)
            return
        changes = {"solid": False}
        if QColor(bs.color1) == QColor(bs.color2):         # duas cores iguais não formam degradê: sugere a segunda
            c = QColor(bs.color1)
            h, s, l, _a = c.getHsl()
            changes["color2"] = QColor.fromHsl((max(h, 0) + 40) % 360, max(s, 120), min(max(l, 90), 170)).name()
        self._bg_apply(**changes)

    def _sync_bg_controls(self):
        try:
            self._sync_bg_controls_impl()
        except RuntimeError:        # janela já fechada
            return

    @staticmethod
    def _gradient_icon(c1: str, c2: str, mode: str = "linear", size: tuple[int, int] = (28, 16)) -> QIcon:
        from .annotations import BackgroundSettings
        w, h = size
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 4, 4)
        p.fillPath(path, BackgroundSettings(True, c1, c2, False, 0, 0, False, mode).brush(QRectF(0, 0, w, h)))
        p.setPen(QPen(QColor("#8a8f99"), 1))
        p.drawPath(path)
        p.end()
        return QIcon(pm)

    @staticmethod
    def _shadow_icon(direction: str, bs, size: tuple[int, int] = (34, 24)) -> QIcon:
        """Miniatura: uma imagem sobre o fundo atual com a sombra na direção indicada."""
        from .annotations import BackgroundSettings, paint_shadow

        w, h = size
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        frame = QRectF(0.5, 0.5, w - 1, h - 1)
        path = QPainterPath()
        path.addRoundedRect(frame, 4, 4)
        bg = BackgroundSettings(True, bs.color1, bs.color2, False, 0, 0, False, bs.mode)
        p.fillPath(path, bg.brush(frame))
        p.setClipPath(path)
        inner = QRectF(9, 6, w - 18, h - 12)
        paint_shadow(p, inner, 2, 7, direction, 0.7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f5f6f8"))
        p.drawRoundedRect(inner, 2, 2)
        p.setClipping(False)
        p.setPen(QPen(QColor("#8a8f99"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()
        return QIcon(pm)

    def _sync_bg_controls_impl(self):
        if not hasattr(self, "btn_bg_style"):
            return
        bs = self.scene.background
        names = {"linear": tr("Linear — cores se misturam entre as extremidades"),
                 "radial": tr("Radial — cores saindo do centro"),
                 "blur": tr("Desfoque — manchas suaves de cor"),
                 "mesh": tr("Mesclado (mesh) — várias cores se misturando")}
        short = {"linear": tr("Linear"), "radial": tr("Radial"), "blur": tr("Desfoque"), "mesh": tr("Mesclado")}
        for mode, act in self._bg_style_actions.items():
            act.setIcon(self._gradient_icon(bs.color1, bs.color2, mode))
            act.setChecked(mode == bs.mode)
        self.btn_bg_style.setText(" " + tr("Estilo") + ": " + short.get(bs.mode, ""))
        self.btn_bg_style.setIcon(self._gradient_icon(bs.color1, bs.color2, bs.mode))
        self.btn_bg_style.setToolTip(names.get(bs.mode, ""))
        self.cb_bg_gradient.blockSignals(True)
        self.cb_bg_gradient.setChecked(not bs.solid)
        self.cb_bg_gradient.blockSignals(False)
        gradient = not bs.solid
        self._bg_visibility()
        self.btn_bg_c1.setText(" " + (tr("Cor 1") if gradient else tr("Cor")))
        self.btn_bg_c1.setIcon(self._swatch_icon(QColor(bs.color1)))
        self.btn_bg_c2.setText(" " + tr("Cor 2"))
        self.btn_bg_c2.setIcon(self._swatch_icon(QColor(bs.color2)))
        for cb, val in ((self.cb_bg_shadow, bs.shadow), (self.cb_bg_transp, bs.transparent)):
            cb.blockSignals(True)
            cb.setChecked(val)
            cb.blockSignals(False)
        for key, act in self._bg_dir_actions.items():
            act.setChecked(key == bs.shadow_dir)
            act.setIcon(self._shadow_icon(key, bs))
        self.btn_bg_shadow.setText(" " + tr("Sombra") + ": " + self._bg_dir_names.get(bs.shadow_dir, ""))
        self.btn_bg_shadow.setIcon(self._shadow_icon(bs.shadow_dir, bs))
        for sl, v in ((self.sl_bg_pad, bs.padding), (self.sl_bg_inner, bs.radius), (self.sl_bg_outer, bs.outer_radius),
                      (self.sl_bg_shadow, bs.shadow_blur)):
            if not sl.sl.isSliderDown():
                sl.set_quiet(v)

    def edit_size(self):
        dlg = ResizeDialog(self.scene, self)
        if dlg.exec():
            self.scene.set_export_scale(dlg.scale())

    def pin(self):
        self.pin_requested.emit(self.render_image())

    # ------------------------------------------------------------------
    # exportação
    # ------------------------------------------------------------------
    def render_image(self) -> QImage:
        return self.scene.render_image()

    def copy_to_clipboard(self, quiet: bool = False):
        copy_image(self.render_image())
        self._exported = True
        if not quiet:
            self.statusBar().showMessage(tr("Imagem copiada para a área de transferência."), 4000)

    def _default_path(self) -> Path:
        from .naming import build_path
        ext = "jpg" if self.cfg.save_format == "jpg" else "png"
        try:
            return build_path(self.cfg.save_dir, ext, self.cfg.file_name_pattern, self.cfg.save_by_month, create=False)
        except OSError:
            return Path(self.cfg.save_dir) / datetime.now().strftime(f"Shotwise_%Y-%m-%d_%H-%M-%S.{ext}")

    def save_project(self) -> bool:
        """Grava a cópia editável (com os originais) na biblioteca local."""
        if not self.cfg.library_enabled:
            return False
        try:
            self.pid = library.save(self.scene, self.pid, str(self.saved_path or ""), self.title_text)
            library.prune(self.cfg.library_max_items, self.cfg.library_max_mb)
            return True
        except OSError as exc:
            self.statusBar().showMessage(tr("Não foi possível guardar a cópia editável: {exc}").format(exc=exc), 8000)
            return False

    def _write(self, path: Path) -> bool:
        img = self.render_image()
        path.parent.mkdir(parents=True, exist_ok=True)
        fmt = "JPG" if path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
        if fmt == "JPG" and img.hasAlphaChannel():
            img = img.convertToFormat(QImage.Format.Format_RGB32)
        ok = img.save(str(path), fmt, 92 if fmt == "JPG" else -1)
        if ok:
            self.saved_path = path
            self._exported = True
            self.scene.undo_stack.setClean()
            kept = self.save_project()
            extra = "  •  " + tr("cópia editável guardada na biblioteca") if kept else ""
            self.statusBar().showMessage(tr("Salvo em {path}{extra}").format(path=path, extra=extra), 6000)
        else:
            QMessageBox.warning(self, "Shotwise", tr("Não foi possível salvar em:\n{path}").format(path=path))
        return ok

    def save(self):
        path = self.saved_path or self._default_path()
        return self._write(path)

    def save_as(self):
        start = str(self.saved_path or self._default_path())
        filters = ["PNG (*.png)", "JPEG (*.jpg *.jpeg)"]
        if self.cfg.save_format == "jpg":
            filters.reverse()
        fname, _ = QFileDialog.getSaveFileName(self, tr("Salvar como"), start, ";;".join(filters))
        if fname:
            return self._write(Path(fname))
        return False

    def _place_toolbars(self):
        """Posiciona a barra de ferramentas: esquerda, direita ou em cima (entre os ícones e as opções)."""
        pos = self.cfg.tools_position if self.cfg.tools_position in ("left", "right", "top") else "left"
        for tb in (self._tools_tb,):
            self.removeToolBarBreak(tb)
            self.removeToolBar(tb)
        top = Qt.ToolBarArea.TopToolBarArea
        from .theme import THEMES
        app = QApplication.instance()
        edge = THEMES.get(app.property("shotwise_theme") if app else "dark", THEMES["dark"])["edge"]
        if pos == "top":
            self.addToolBarBreak(top)
            self.addToolBar(top, self._tools_tb)
            self._tools_tb.setOrientation(Qt.Orientation.Horizontal)
            self._tools_tb.setStyleSheet(f"QToolBar#tools {{ border: none; border-bottom: 1px solid {edge}; "
                                         "padding: 2px 6px; }")
        else:
            side = Qt.ToolBarArea.LeftToolBarArea if pos == "left" else Qt.ToolBarArea.RightToolBarArea
            self.addToolBar(side, self._tools_tb)
            self._tools_tb.setOrientation(Qt.Orientation.Vertical)
            line = "border-right" if pos == "left" else "border-left"
            self._tools_tb.setStyleSheet(f"QToolBar#tools {{ border: none; {line}: 1px solid {edge}; "
                                         "padding: 2px 4px; }")
        self._tools_tb.show()
        self._tools_pos = pos

    def apply_window_settings(self):
        """Aplica 'sempre à frente' conforme as Configurações (vale também para editores já abertos)."""
        if getattr(self, "_tools_pos", self.cfg.tools_position) != self.cfg.tools_position:
            self._place_toolbars()
        want = bool(self.cfg.editor_on_top)
        if bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) != want:
            was_visible = self.isVisible()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, want)
            if was_visible:
                self.show()          # mudar a flag esconde a janela; mostra de novo

    def save_and_close(self):
        if self.save():
            self._force_close = True
            self.close()

    def save_as_and_close(self):
        if self.save_as():
            self._force_close = True
            self.close()

    def finish(self):
        """Executa a ação de fechar configurada (copiar ou salvar) e fecha o editor."""
        if self.cfg.close_action == "save":
            if not self.save():
                return
        else:
            self.copy_to_clipboard(quiet=True)
            self.save_project()
        self._force_close = True
        self.close()

    # ------------------------------------------------------------------
    # janela
    # ------------------------------------------------------------------
    def _resize_to(self, iw: int, ih: int):
        screen = QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else None
        if avail is None:
            self.resize(1100, 760)
            return
        w = max(900, min(iw + 140, int(avail.width() * 0.92)))
        h = max(700, min(ih + 190, int(avail.height() * 0.92)))
        self.resize(w, h)

    def showEvent(self, ev):
        super().showEvent(ev)
        if self._first_show:
            self._first_show = False
            self.view.fit_initial()

    def _update_title(self, *_):
        try:
            w, h = self.scene.output_size()
        except RuntimeError:        # a cena já foi destruída (janela fechando)
            return
        dirty = "" if self.scene.undo_stack.isClean() else " •"
        self.setWindowTitle(f"Shotwise — {self.title_text} — {w}×{h}{dirty}")
        self._update_status()

    _ZMIN, _ZMAX = 0.02, 16.0

    def _zoom_slider_moved(self, v: int):
        import math
        z = self._ZMIN * math.exp(math.log(self._ZMAX / self._ZMIN) * v / 1000)
        if abs(z - self.view.zoom_value) / z > 0.005:
            self.view.set_zoom(z)

    def _sync_zoom_slider(self):
        import math
        sl = getattr(self, "sl_zoom", None)
        if sl is None:
            return
        z = min(max(self.view.zoom_value, self._ZMIN), self._ZMAX)
        sl.blockSignals(True)
        sl.setValue(round(1000 * math.log(z / self._ZMIN) / math.log(self._ZMAX / self._ZMIN)))
        sl.blockSignals(False)

    def flip_image(self, horizontal: bool):
        self.scene.flip_content(horizontal)
        self.view.fit_all()
        self._update_title()

    def rotate_image(self, degrees: int):
        self.scene.rotate_content(degrees)
        self.view.fit_all()
        self._update_title()

    def _update_status(self, *_):
        self._sync_zoom_slider()
        if hasattr(self, "_zoom_label"):
            try:
                w, h = self.scene.output_size()
            except RuntimeError:
                return
            self._zoom_label.setText(tr("saída {w} × {h} px   |   zoom {z}%  ").format(w=w, h=h, z=f"{self.view.zoom_value * 100:.0f}"))

    def keyPressEvent(self, ev):
        key = ev.key()
        mods = ev.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                                 | Qt.KeyboardModifier.MetaModifier)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not mods and self.scene.crop_active:
            self.apply_crop()
            ev.accept()
            return
        if key == Qt.Key.Key_Escape:
            if self.scene.crop_active:
                self.scene.cancel_crop()
            elif self.scene.selectedItems():
                self.scene.clearSelection()
            elif self.scene.tool != "select":
                self.select_tool("select")
            else:
                self.finish()               # Esc fecha o editor com a ação escolhida (copiar ou salvar)
            ev.accept()
            return
        if not mods and ev.text() and ev.text().lower() in TOOL_KEYS:
            self.select_tool(TOOL_KEYS[ev.text().lower()])
            ev.accept()
            return
        super().keyPressEvent(ev)

    def closeEvent(self, ev):
        if not self._force_close:
            dirty = not self.scene.undo_stack.isClean()
            action = self.cfg.close_action
            if dirty or not self._exported:
                if action == "copy":
                    self.copy_to_clipboard(quiet=True)
                    self.save_project()
                elif action == "save":
                    if not self.save():
                        ev.ignore()
                        return
        self.save_tool_options()
        self.closed.emit(self)
        super().closeEvent(ev)
