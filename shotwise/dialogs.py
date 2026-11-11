"""Diálogos do editor: tamanho da imagem, fundo e biblioteca de capturas."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QSlider, QWidget, QPlainTextEdit, QDialog, QDialogButtonBox, QFormLayout, QGridLayout,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QSpinBox, QToolButton, QVBoxLayout)

from .i18n import tr
from . import library
from .annotations import BG_PRESETS, AnnotScene, BackgroundSettings


# ----------------------------------------------------------------------
# Tamanho da imagem exportada
# ----------------------------------------------------------------------
class ResizeDialog(QDialog):
    """Define o tamanho final da imagem (largura/altura/percentual), mantendo a proporção."""

    def __init__(self, scene: AnnotScene, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Redimensionar imagem"))
        self.scene = scene
        w, h = scene.output_size()
        s = scene.export_scale
        self.base_w = max(1, round(w / s))
        self.base_h = max(1, round(h / (s * scene.export_stretch)))
        self._busy = False

        self.sp_w = QSpinBox()
        self.sp_h = QSpinBox()
        self.sp_p = QSpinBox()
        for sp, hi in ((self.sp_w, 30000), (self.sp_h, 30000)):
            sp.setRange(1, hi)
            sp.setSuffix(" px")
        self.sp_p.setRange(5, 800)
        self.sp_p.setSuffix(" %")
        self.sp_w.setValue(w)
        self.sp_h.setValue(h)
        self.sp_p.setValue(round(s * 100))
        self.sp_w.valueChanged.connect(self._from_w)
        self.sp_h.valueChanged.connect(self._from_h)
        self.sp_p.valueChanged.connect(self._from_p)

        self.lbl = QLabel(tr("Tamanho original: {w} × {h} px").format(w=self.base_w, h=self.base_h))
        form = QFormLayout()
        form.addRow(tr("Largura"), self.sp_w)
        form.addRow(tr("Altura"), self.sp_h)
        form.addRow(tr("Escala"), self.sp_p)
        bt_reset = QPushButton(tr("Voltar ao tamanho original"))
        bt_reset.clicked.connect(lambda: self.sp_p.setValue(100))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.lbl)
        lay.addLayout(form)
        lay.addWidget(bt_reset)
        lay.addWidget(buttons)

    def _set(self, w: int, h: int, p: int):
        self._busy = True
        self.sp_w.setValue(max(1, w))
        self.sp_h.setValue(max(1, h))
        self.sp_p.setValue(max(5, min(800, p)))
        self._busy = False

    def _from_w(self, v: int):
        if not self._busy:
            f = v / self.base_w
            self._set(v, round(self.base_h * f), round(f * 100))

    def _from_h(self, v: int):
        if not self._busy:
            f = v / self.base_h
            self._set(round(self.base_w * f), v, round(f * 100))

    def _from_p(self, v: int):
        if not self._busy:
            f = v / 100
            self._set(round(self.base_w * f), round(self.base_h * f), v)

    def scale(self) -> float:
        # a largura digitada manda (preserva o valor exato em pixels)
        return self.sp_w.value() / self.base_w


# ----------------------------------------------------------------------
# Fundo
# ----------------------------------------------------------------------
class _ColorButton(QToolButton):
    changed = Signal()

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(54, 26)
        self.clicked.connect(self._pick)
        self._paint()

    def _paint(self):
        self.setStyleSheet(f"QToolButton{{background:{self.color};border:2px solid #5a5f6b;border-radius:5px;}}")

    def set_color(self, c: str):
        self.color = c
        self._paint()

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, tr("Escolher cor"))
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit()


class LabeledSlider(QWidget):
    """Rótulo + valor (à direita) + controle deslizante embaixo — o mesmo desenho do painel de fundo."""
    changed = Signal()

    def __init__(self, title: str, lo: int, hi: int, value: int, parent=None, fmt=None, tip: str = ""):
        super().__init__(parent)
        self._fmt = fmt or (lambda v: str(v))
        self.sl = QSlider(Qt.Orientation.Horizontal)
        self.sl.setRange(lo, hi)
        self.sl.setValue(value)
        self.sl._ls = self
        self.title = QLabel(title)
        self.lbl = QLabel(self._fmt(value))
        self.lbl.setObjectName("sliderValue")
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.lbl)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addLayout(head)
        lay.addWidget(self.sl)
        if tip:
            self.setToolTip(tip)
        self.sl.valueChanged.connect(lambda v: (self.lbl.setText(self._fmt(v)), self.changed.emit()))

    def value(self) -> int:
        return self.sl.value()

    def refresh(self):
        self.lbl.setText(self._fmt(self.sl.value()))

    def set_quiet(self, v: int):
        self.sl.blockSignals(True)
        self.sl.setValue(v)
        self.sl.blockSignals(False)
        self.refresh()

    def setValue(self, v: int):
        self.sl.setValue(v)


class BackgroundDialog(QDialog):
    """Painel do fundo: margem, sombra (tamanho e direção), cantos externos/internos, cor sólida ou degradê."""

    def __init__(self, scene: AnnotScene, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Fundo da imagem"))
        self.scene = scene
        self.old = scene.background.copy()
        cur = self.old.copy()
        if not cur.enabled:
            cur.padding = cur.padding or 40
        self._mode = cur.mode
        self._solid = cur.solid

        self.cb_on = QCheckBox(tr("Usar fundo"))
        self.cb_on.setChecked(self.old.enabled)
        self.cb_transp = QCheckBox(tr("Fundo transparente (PNG com margem e sombra)"))
        self.cb_transp.setChecked(cur.transparent)
        self.c1 = _ColorButton(cur.color1)
        self.c2 = _ColorButton(cur.color2)

        self.s_pad = LabeledSlider(tr("Margem"), 0, 200, cur.padding)
        self.s_shadow = LabeledSlider(tr("Sombra"), 0, 120, cur.shadow_blur if cur.shadow else 0)
        self.s_outer = LabeledSlider(tr("Cantos do fundo"), 0, 120, cur.outer_radius)
        self.s_inner = LabeledSlider(tr("Cantos da imagem"), 0, 80, cur.radius)
        self.cmb_dir = QComboBox()
        for key, name in (("down", tr("Para baixo")), ("up", tr("Para cima")), ("left", tr("Para a esquerda")),
                          ("right", tr("Para a direita")), ("down_right", tr("Baixo e direita")),
                          ("down_left", tr("Baixo e esquerda")), ("up_right", tr("Cima e direita")),
                          ("up_left", tr("Cima e esquerda")), ("center", tr("Ao redor (sem deslocamento)"))):
            self.cmb_dir.addItem(name, key)
        self.cmb_dir.setCurrentIndex(max(0, self.cmb_dir.findData(cur.shadow_dir)))

        self.tab_solid = QPushButton(tr("Sólido"))
        self.tab_grad = QPushButton(tr("Degradê"))
        for t in (self.tab_solid, self.tab_grad):
            t.setCheckable(True)
            t.setAutoExclusive(True)
        self.tab_solid.setChecked(cur.solid)
        self.tab_grad.setChecked(not cur.solid)
        tabs = QHBoxLayout()
        tabs.addWidget(self.tab_solid)
        tabs.addWidget(self.tab_grad)

        presets = QGridLayout()
        for i, (name, a, b) in enumerate(BG_PRESETS):
            btn = QToolButton()
            btn.setFixedSize(54, 40)
            btn.setToolTip(name)
            btn.setStyleSheet(f"QToolButton{{border:2px solid transparent;border-radius:7px;"
                              f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {a},stop:1 {b});}}"
                              f"QToolButton:hover{{border:2px solid palette(highlight);}}")
            btn.clicked.connect(lambda _=False, a=a, b=b: self._preset(a, b))
            presets.addWidget(btn, i // 4, i % 4)

        self.cmb_mode = QComboBox()
        for key, name in (("linear", tr("Linear")), ("radial", tr("Radial")), ("blur", tr("Desfoque")), ("mesh", tr("Mesclado (mesh)"))):
            self.cmb_mode.addItem(name, key)
        self.cmb_mode.setCurrentIndex(max(0, self.cmb_mode.findData(cur.mode)))
        self.btn_swap = QToolButton()
        self.btn_swap.setText("⇄")
        self.btn_swap.setToolTip(tr("Inverter as cores"))
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.cmb_mode, 1)
        mode_row.addWidget(self.btn_swap)

        row = QHBoxLayout()
        row.addWidget(self.c1)
        row.addWidget(QLabel("→"))
        row.addWidget(self.c2)
        row.addStretch(1)

        sliders = QGridLayout()
        sliders.addWidget(self.s_pad, 0, 0)
        sliders.addWidget(self.s_shadow, 0, 1)
        sliders.addWidget(self.s_outer, 1, 0)
        sliders.addWidget(self.s_inner, 1, 1)
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel(tr("Direção da sombra")))
        dir_row.addWidget(self.cmb_dir, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.btn_remove = buttons.addButton(tr("Remover fundo"), QDialogButtonBox.ButtonRole.DestructiveRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.btn_remove.clicked.connect(self._remove)

        lay = QVBoxLayout(self)
        lay.addWidget(self.cb_on)
        lay.addLayout(sliders)
        lay.addLayout(dir_row)
        lay.addLayout(tabs)
        lay.addLayout(presets)
        lay.addLayout(mode_row)
        lay.addLayout(row)
        lay.addWidget(self.cb_transp)
        lay.addWidget(buttons)

        self.tab_solid.toggled.connect(self._tab_changed)
        self.cb_on.toggled.connect(self._live)
        self.cb_transp.toggled.connect(self._live)
        for w in (self.s_pad, self.s_shadow, self.s_outer, self.s_inner):
            w.changed.connect(self._live)
        self.cmb_dir.currentIndexChanged.connect(self._live)
        self.cmb_mode.currentIndexChanged.connect(self._live)
        self.btn_swap.clicked.connect(self._swap)
        for w in (self.c1, self.c2):
            w.changed.connect(self._live)
        self._tab_changed()

    def _tab_changed(self, *_):
        grad = not self.tab_solid.isChecked()
        self.c2.setVisible(grad)
        self.cmb_mode.setEnabled(grad)
        self.btn_swap.setEnabled(grad)
        self._live()

    def _swap(self):
        a, b = self.c1.color, self.c2.color
        self.c1.set_color(b)
        self.c2.set_color(a)
        self._live()

    def _remove(self):
        self.cb_on.setChecked(False)
        self.accept()

    def _preset(self, a: str, b: str):
        self.c1.set_color(a)
        self.c2.set_color(b)
        self.tab_grad.setChecked(True)
        self.cb_transp.setChecked(False)
        self.cb_on.setChecked(True)
        self._live()

    def settings(self) -> BackgroundSettings:
        s = self.old.copy()
        s.enabled = self.cb_on.isChecked()
        s.color1, s.color2 = self.c1.color, self.c2.color
        s.transparent = self.cb_transp.isChecked()
        s.padding = self.s_pad.value()
        s.radius = self.s_inner.value()
        s.outer_radius = self.s_outer.value()
        s.shadow = self.s_shadow.value() > 0
        if s.shadow:
            s.shadow_blur = self.s_shadow.value()
        s.shadow_dir = self.cmb_dir.currentData()
        s.mode = self.cmb_mode.currentData()
        s.solid = self.tab_solid.isChecked()
        return s

    def _live(self, *_):
        self.scene.preview_background(self.settings())

    def accept(self):
        new = self.settings()
        if new.to_dict() != self.old.to_dict():
            self.scene.commit_background(self.old, new)
        else:
            self.scene.preview_background(self.old)
        super().accept()

    def reject(self):
        self.scene.preview_background(self.old)
        super().reject()


# ----------------------------------------------------------------------
# Biblioteca
# ----------------------------------------------------------------------
class LibraryDialog(QDialog):
    open_project = Signal(str)
    open_file_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Shotwise — Capturas recentes"))
        self.resize(820, 560)
        self.lst = QListWidget()
        self.lst.setViewMode(QListWidget.ViewMode.IconMode)
        self.lst.setIconSize(QSize(200, 140))
        self.lst.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.lst.setMovement(QListWidget.Movement.Static)
        self.lst.setSpacing(10)
        self.lst.setWordWrap(True)
        self.lst.itemDoubleClicked.connect(self._open_item)
        self.lst.itemSelectionChanged.connect(self._sel_changed)

        self.bt_open = QPushButton(tr("Abrir e editar"))
        self.bt_open.clicked.connect(lambda: self._open_item(self.lst.currentItem()))
        self.bt_del = QPushButton(tr("Excluir"))
        self.bt_del.clicked.connect(self._delete)
        bt_all = QPushButton(tr("Excluir todas…"))
        bt_all.clicked.connect(self._delete_all)
        bt_file = QPushButton(tr("Abrir arquivo…"))
        bt_file.clicked.connect(self.open_file_requested.emit)
        bt_close = QPushButton(tr("Fechar"))
        bt_close.clicked.connect(self.accept)

        note = QLabel(tr("Estas cópias editáveis guardam a imagem original, <b>sem as tarjas aplicadas</b>, "
                      "somente neste computador. Exclua as que contêm dados sensíveis depois de usar."))
        note.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.bt_open)
        row.addWidget(self.bt_del)
        row.addWidget(bt_all)
        row.addStretch(1)
        row.addWidget(bt_file)
        row.addWidget(bt_close)
        lay = QVBoxLayout(self)
        lay.addWidget(self.lst, 1)
        lay.addWidget(note)
        lay.addLayout(row)
        self.reload()

    def reload(self):
        self.lst.clear()
        for e in library.entries():
            try:
                when = datetime.fromisoformat(e.updated).strftime("%d/%m/%Y %H:%M")
            except ValueError:
                when = e.updated
            size = f"{e.size[0]}×{e.size[1]}" if e.size[0] else ""
            it = QListWidgetItem(f"{e.title}\n{when}  {size}")
            it.setData(Qt.ItemDataRole.UserRole, e.id)
            img = library.thumb(e.id)
            if not img.isNull():
                it.setIcon(QIcon(QPixmap.fromImage(img)))
            self.lst.addItem(it)
        if self.lst.count() == 0:
            self.lst.addItem(QListWidgetItem(tr("Nenhuma captura guardada ainda.")))
            self.lst.item(0).setFlags(Qt.ItemFlag.NoItemFlags)
        self._sel_changed()

    def _sel_changed(self):
        has = self.lst.currentItem() is not None and self.lst.currentItem().data(Qt.ItemDataRole.UserRole)
        self.bt_open.setEnabled(bool(has))
        self.bt_del.setEnabled(bool(has))

    def _open_item(self, item):
        pid = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if pid:
            self.open_project.emit(pid)
            self.accept()          # a captura já foi escolhida: a lista fecha (o editor tem o botão para reabri-la)

    def _delete(self):
        it = self.lst.currentItem()
        pid = it.data(Qt.ItemDataRole.UserRole) if it is not None else None
        if pid and QMessageBox.question(self, "Shotwise", tr("Excluir esta captura editável? O PNG salvo não é afetado.")
                                        ) == QMessageBox.StandardButton.Yes:
            library.delete(pid)
            self.reload()

    def _delete_all(self):
        if QMessageBox.question(self, "Shotwise", tr("Excluir TODAS as capturas editáveis da biblioteca? "
                                "Os PNGs salvos não são afetados.")) == QMessageBox.StandardButton.Yes:
            library.delete_all()
            self.reload()


# ----------------------------------------------------------------------
# OCR
# ----------------------------------------------------------------------
class OcrDialog(QDialog):
    """Mostra o texto reconhecido, permite corrigir e copiar."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Texto reconhecido"))
        self.resize(560, 360)
        self.ed = QPlainTextEdit(text)
        self.ed.setPlaceholderText(tr("Nenhum texto reconhecido."))
        self.lbl = QLabel(tr("Revise o texto antes de usar: o reconhecimento pode errar letras parecidas (0/O, 1/l)."))
        self.lbl.setWordWrap(True)
        bt_copy = QPushButton(tr("Copiar texto"))
        bt_copy.setDefault(True)
        bt_copy.clicked.connect(self._copy)
        bt_close = QPushButton(tr("Fechar"))
        bt_close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(bt_copy)
        row.addWidget(bt_close)
        lay = QVBoxLayout(self)
        lay.addWidget(self.ed, 1)
        lay.addWidget(self.lbl)
        lay.addLayout(row)

    def _copy(self):
        from .clipboard import copy_text

        copy_text(self.ed.toPlainText())
        self.lbl.setText(tr("Texto copiado para a área de transferência."))
