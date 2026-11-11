"""Temas do aplicativo: escuro, claro ou o mesmo do sistema."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

THEMES = {
    "dark": dict(window="#1b1d22", bar="#23262d", edge="#32353d", text="#e4e6eb", text2="#c9ccd3", muted="#aeb3bd",
                 disabled="#6b6f78", field="#2b2e36", field_edge="#3a3e48", button="#2f333c", button_edge="#3f4450",
                 hover="#2f333c", button_hover="#3a3f4a", groove="#3a3e48", view="#15171b", accent="#1f6feb",
                 accent_press="#2a5fc0", handle="#3b9cff", check="#d4d7de"),
    "light": dict(window="#f3f4f6", bar="#ffffff", edge="#d9dce1", text="#1f2328", text2="#2d3138", muted="#5c6370",
                  disabled="#a0a5ae", field="#ffffff", field_edge="#c5c9d0", button="#ffffff", button_edge="#c5c9d0",
                  hover="#e8eaee", button_hover="#eceef2", groove="#cfd3da", view="#e2e4e9", accent="#1f6feb",
                  accent_press="#2a5fc0", handle="#1f6feb", check="#2d3138"),
}

_TEMPLATE = """
QMainWindow, QDialog { background: %(window)s; }
QToolBar { background: %(bar)s; border: none; spacing: 4px; padding: 4px; }
QToolBar#tools { border-right: 1px solid %(edge)s; spacing: 1px; padding: 2px 4px; }
QToolBar#tools QToolButton { padding: 1px 4px; }
QToolBar#options { border-bottom: 1px solid %(edge)s; }
QToolBar#main { border-bottom: 1px solid %(edge)s; }
QToolButton { color: %(text)s; border: 1px solid transparent; border-radius: 6px; padding: 4px 8px; }
QToolButton:hover { background: %(hover)s; }
QToolButton:checked { background: %(accent)s; color: white; }
QToolButton:pressed { background: %(accent_press)s; }
QToolButton:disabled { color: %(disabled)s; }
QStatusBar { background: %(bar)s; color: %(muted)s; }
QLabel { color: %(text2)s; }
QSpinBox, QDoubleSpinBox, QLineEdit, QKeySequenceEdit, QComboBox { background: %(field)s; color: %(text)s;
    border: 1px solid %(field_edge)s; border-radius: 5px; padding: 3px 6px; }
QSpinBox, QDoubleSpinBox { padding-right: 24px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right;
    width: 20px; border-left: 1px solid %(field_edge)s; border-bottom: 1px solid %(field_edge)s;
    border-top-right-radius: 5px; background: %(button)s; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right;
    width: 20px; border-left: 1px solid %(field_edge)s;
    border-bottom-right-radius: 5px; background: %(button)s; }
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: %(button_hover)s; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("%(arrow_up)s"); width: 9px; height: 9px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("%(arrow_down)s"); width: 9px; height: 9px; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { subcontrol-origin: border; subcontrol-position: center right; width: 22px; border: none; }
QComboBox::down-arrow { image: url("%(arrow_down)s"); width: 9px; height: 9px; }
QPushButton { background: %(button)s; color: %(text)s; border: 1px solid %(button_edge)s; border-radius: 6px;
    padding: 6px 14px; }
QPushButton:hover { background: %(button_hover)s; }
QPushButton:default { background: %(accent)s; border-color: %(accent)s; color: white; }
QCheckBox { color: %(check)s; }
QSlider::groove:horizontal { height: 4px; background: %(groove)s; border-radius: 2px; }
QSlider::handle:horizontal { background: %(handle)s; width: 14px; margin: -6px 0; border-radius: 7px; }
QGraphicsView { border: none; background: %(view)s; }
QToolTip { background: %(field)s; color: %(text)s; border: 1px solid %(field_edge)s; }
QMenu { background: %(bar)s; color: %(text)s; border: 1px solid %(field_edge)s; }
QMenu::item:selected { background: %(accent)s; color: white; }
"""


def system_is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() != Qt.ColorScheme.Light
    except AttributeError:      # Qt antigo sem colorScheme
        return True


def resolve(mode: str) -> str:
    return mode if mode in THEMES else ("dark" if system_is_dark() else "light")


class _CheckStyle(QProxyStyle):
    """Caixas de seleção bem visíveis: contorno nítido, fundo próprio e marca branca sobre a cor de destaque."""

    SIZE = 17

    def pixelMetric(self, metric, option=None, widget=None):
        if metric in (QStyle.PixelMetric.PM_IndicatorWidth, QStyle.PixelMetric.PM_IndicatorHeight):
            return self.SIZE
        return super().pixelMetric(metric, option, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        if element != QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            super().drawPrimitive(element, option, painter, widget)
            return
        st = option.state
        enabled = bool(st & QStyle.StateFlag.State_Enabled)
        on = bool(st & QStyle.StateFlag.State_On)
        partial = bool(st & QStyle.StateFlag.State_NoChange)
        hover = bool(st & QStyle.StateFlag.State_MouseOver)
        pal = option.palette
        r = QRectF(option.rect)
        side = min(r.width(), r.height(), float(self.SIZE)) - 1.6
        box = QRectF(r.center().x() - side / 2, r.center().y() - side / 2, side, side)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if on or partial:
            fill = QColor(pal.color(QPalette.ColorRole.Highlight))
            edge = fill.darker(120)
        else:
            fill = QColor(pal.color(QPalette.ColorRole.Base))
            edge = QColor(pal.color(QPalette.ColorRole.WindowText))
            edge.setAlpha(210 if hover else 170)
        if not enabled:
            fill.setAlpha(110)
            edge.setAlpha(80)
        painter.setPen(QPen(edge, 1.5))
        painter.setBrush(fill)
        painter.drawRoundedRect(box, 4, 4)
        if on or partial:
            painter.setPen(QPen(QColor("white"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            c, s = box.center(), box.width()
            if on:
                painter.drawPolyline([QPointF(c.x() - s * 0.24, c.y() + s * 0.02), QPointF(c.x() - s * 0.06, c.y() + s * 0.22),
                                      QPointF(c.x() + s * 0.26, c.y() - s * 0.2)])
            else:
                painter.drawLine(QPointF(c.x() - s * 0.22, c.y()), QPointF(c.x() + s * 0.22, c.y()))
        painter.restore()


_check_style: _CheckStyle | None = None


def _arrow_files(name: str, color: str) -> tuple[str, str]:
    """Gera (uma vez por tema) os PNGs das setas dos campos numéricos e listas; o QSS precisa de arquivos em disco."""
    import tempfile
    from pathlib import Path

    d = Path(tempfile.gettempdir()) / "shotwise_theme"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for kind in ("up", "down"):
        f = d / f"arrow_{kind}_{name}_{color.lstrip('#')}.png"
        if not f.exists():
            from PySide6.QtGui import QImage, QPolygonF
            img = QImage(18, 18, QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.transparent)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(QColor(color), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            if kind == "up":
                p.drawPolyline(QPolygonF([QPointF(4, 11.5), QPointF(9, 6.5), QPointF(14, 11.5)]))
            else:
                p.drawPolyline(QPolygonF([QPointF(4, 6.5), QPointF(9, 11.5), QPointF(14, 6.5)]))
            p.end()
            img.save(str(f), "PNG")
        out.append(f.as_posix())
    return out[0], out[1]


def apply_theme(app: QApplication, mode: str = "dark") -> str:
    """Aplica "dark", "light" ou "system". Devolve o tema efetivo."""
    name = resolve(mode)
    c = THEMES[name]
    global _check_style
    if _check_style is None:
        _check_style = _CheckStyle("Fusion")       # referência viva: o Qt não guarda o objeto Python
        app.setStyle(_check_style)
    pal = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "window"), (QPalette.ColorRole.WindowText, "text"),
                      (QPalette.ColorRole.Base, "field"), (QPalette.ColorRole.AlternateBase, "bar"),
                      (QPalette.ColorRole.Text, "text"), (QPalette.ColorRole.Button, "button"),
                      (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "accent"),
                      (QPalette.ColorRole.ToolTipBase, "field"), (QPalette.ColorRole.ToolTipText, "text")):
        pal.setColor(role, QColor(c[key]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    app.setPalette(pal)
    up, down = _arrow_files(name, c["text"])
    app.setStyleSheet(_TEMPLATE % dict(c, arrow_up=up, arrow_down=down))
    app.setProperty("shotwise_theme", name)
    return name


def apply_dark_theme(app: QApplication) -> None:      # compatibilidade
    apply_theme(app, "dark")


def follow_system(app: QApplication, get_mode) -> None:
    """Reaplica o tema quando o Windows troca claro/escuro e a opção é "Sistema"."""
    try:
        QGuiApplication.styleHints().colorSchemeChanged.connect(
            lambda *_: apply_theme(app, get_mode()) if get_mode() == "system" else None)
    except AttributeError:
        pass
