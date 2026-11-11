"""Ícones desenhados em código (sem arquivos externos) e ícone do aplicativo."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

SIZE = 28
STROKE = 1.35          # traço fino: ícones suaves, sem aspecto de negrito


def _canvas(size: int = SIZE) -> tuple[QPixmap, QPainter]:
    """Pixmap em 2x (nítido em telas de alta densidade); o desenho usa coordenadas de 28x28."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    return pm, p


def _icon_color() -> str:
    app = QApplication.instance()
    return "#2d3138" if app is not None and app.property("shotwise_theme") == "light" else "#d8dbe0"


def _base_color() -> str:
    """Tom único e discreto dos ícones (sem cores): cinza-azulado claro no escuro, ardósia no claro."""
    app = QApplication.instance()
    return "#6b7487" if app is not None and app.property("shotwise_theme") == "light" else "#b4bccb"


def tool_icon(kind: str, color: str | None = None) -> QIcon:
    """Ícone da ferramenta: tom neutro; quando a ferramenta está ativa (botão marcado) o desenho fica branco."""
    icon = QIcon(_tool_pixmap(kind, QColor(color or _base_color())))
    icon.addPixmap(_tool_pixmap(kind, QColor("white")), QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(_tool_pixmap(kind, QColor("white")), QIcon.Mode.Active, QIcon.State.On)
    return icon


def _tool_pixmap(kind: str, c: QColor) -> QPixmap:
    pm, p = _canvas()
    pen = QPen(c, STROKE, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "select":
        poly = QPolygonF([QPointF(8, 5), QPointF(8, 21), QPointF(12.5, 17), QPointF(15.5, 23.5),
                          QPointF(18, 22.4), QPointF(15, 16), QPointF(21, 16)])
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 55))
        p.drawPolygon(poly)
    elif kind == "arrow":
        p.drawLine(QPointF(7, 21), QPointF(21, 7))
        p.drawLine(QPointF(21, 7), QPointF(14, 8.2))
        p.drawLine(QPointF(21, 7), QPointF(19.8, 14))
    elif kind == "line":
        p.drawLine(QPointF(7, 21), QPointF(21, 7))
    elif kind == "rect":
        p.drawRoundedRect(QRectF(6, 8, 16, 12), 1.5, 1.5)
    elif kind == "ellipse":
        p.drawEllipse(QRectF(5.5, 7.5, 17, 13))
    elif kind == "highlight":
        fill = QColor(c)
        fill.setAlpha(110)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(4, 18, 20, 5), 1.5, 1.5)
        p.setPen(QPen(c, STROKE, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(QPolygonF([QPointF(9, 16), QPointF(18, 5), QPointF(22, 8.5), QPointF(13, 16)]))
        p.drawLine(QPointF(9, 16), QPointF(13, 16))
    elif kind == "pen":
        p.drawPolygon(QPolygonF([QPointF(5, 23), QPointF(6.2, 17.2), QPointF(18.5, 4.8), QPointF(23.2, 9.5),
                                 QPointF(10.8, 21.8)]))
        p.drawLine(QPointF(16, 7.5), QPointF(20.5, 12))
        p.drawLine(QPointF(6.2, 17.2), QPointF(10.8, 21.8))
    elif kind == "resize":
        p.drawRect(QRectF(4.5, 11.5, 12, 12))
        p.drawLine(QPointF(14, 14), QPointF(23, 5))
        p.drawLine(QPointF(23, 5), QPointF(17.5, 5.4))
        p.drawLine(QPointF(23, 5), QPointF(22.6, 10.5))
    elif kind == "background":
        p.drawRoundedRect(QRectF(4, 4, 20, 20), 4, 4)
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 70))
        p.drawRoundedRect(QRectF(9, 9, 10, 10), 3, 3)
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(7.5, 7.5), 1.1, 1.1)
    elif kind == "zoom":
        p.drawEllipse(QPointF(12, 12), 6.5, 6.5)
        p.drawLine(QPointF(17, 17), QPointF(23, 23))
        p.drawLine(QPointF(9.5, 12), QPointF(14.5, 12))
        p.drawLine(QPointF(12, 9.5), QPointF(12, 14.5))
    elif kind == "ocr":
        for (x, y, dx, dy) in ((4, 4, 1, 1), (24, 4, -1, 1), (4, 24, 1, -1), (24, 24, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + dx * 5, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy * 5))
        f = QFont("Segoe UI")
        f.setPixelSize(12)
        p.setFont(f)
        p.drawText(QRectF(4, 4, 20, 20), Qt.AlignmentFlag.AlignCenter, "Aa")
    elif kind == "text":
        p.drawLine(QPointF(7, 7), QPointF(21, 7))
        p.drawLine(QPointF(14, 7), QPointF(14, 22))
        p.drawLine(QPointF(11.5, 22), QPointF(16.5, 22))
    elif kind == "step":
        p.drawEllipse(QRectF(5, 5, 18, 18))
        f = QFont("Segoe UI")
        f.setPixelSize(12)
        p.setFont(f)
        p.drawText(QRectF(5, 5, 18, 18), Qt.AlignmentFlag.AlignCenter, "1")
    elif kind == "pixelate":
        p.setPen(Qt.PenStyle.NoPen)
        s = 4.6
        for row in range(4):
            for col in range(4):
                shade = QColor(c)
                shade.setAlpha(150 if (row + col) % 2 == 0 else 55)
                p.setBrush(shade)
                p.drawRect(QRectF(5 + col * s, 5 + row * s, s, s))
    elif kind == "blur":
        p.setPen(Qt.PenStyle.NoPen)
        for r, a in ((9.5, 40), (7, 80), (4.3, 140)):
            col = QColor(c)
            col.setAlpha(a)
            p.setBrush(col)
            p.drawEllipse(QPointF(14, 14), r, r)
    elif kind == "redact":
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 90))
        p.drawRoundedRect(QRectF(4.5, 9, 19, 10), 2, 2)
    elif kind == "crop":
        p.drawLine(QPointF(9, 4), QPointF(9, 19))
        p.drawLine(QPointF(9, 19), QPointF(24, 19))
        p.drawLine(QPointF(4, 9), QPointF(19, 9))
        p.drawLine(QPointF(19, 9), QPointF(19, 24))
    p.end()
    return pm


def ui_icon(name: str, color: str | None = None) -> QIcon:
    """Ícones da barra principal (somente imagem, sem texto)."""
    pm, p = _canvas()
    c = QColor(color or _base_color())
    pen = QPen(c, STROKE, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    def curved_arrow(flip: bool):
        sign = -1 if flip else 1
        cx = 14
        path = QPainterPath(QPointF(cx - sign * 6, 11))
        path.cubicTo(QPointF(cx + sign * 2, 6), QPointF(cx + sign * 8, 11), QPointF(cx + sign * 7, 17))
        p.drawPath(path)
        p.drawLine(QPointF(cx - sign * 6, 11), QPointF(cx - sign * 6, 5.5))
        p.drawLine(QPointF(cx - sign * 6, 11), QPointF(cx - sign * 0.5, 11.5))

    if name == "undo":
        curved_arrow(False)
    elif name == "redo":
        curved_arrow(True)
    elif name == "fit":
        for (x, y, dx, dy) in ((6, 6, 1, 1), (22, 6, -1, 1), (6, 22, 1, -1), (22, 22, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + dx * 6, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy * 6))
    elif name == "actual":
        f = QFont("Segoe UI")
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, SIZE, SIZE), Qt.AlignmentFlag.AlignCenter, "1:1")
    elif name == "copy":
        p.drawRoundedRect(QRectF(5, 9, 12, 14), 2, 2)
        p.drawPath(_open_path([(10, 9), (10, 5), (22, 5), (22, 19), (17, 19)]))
    elif name in ("save", "saveas"):
        p.drawPath(_open_path([(6, 6), (19, 6), (22, 9), (22, 22), (6, 22), (6, 6)]))
        p.drawRect(QRectF(10, 6, 8, 5))
        p.drawRect(QRectF(9, 15, 10, 7))
        if name == "saveas":
            p.setPen(QPen(c, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(22, 2), QPointF(22, 8))
            p.drawLine(QPointF(19, 5), QPointF(25, 5))
    elif name == "done":
        p.drawRoundedRect(QRectF(7, 9, 12, 14), 2, 2)
        p.setPen(QPen(c, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(_open_path([(11, 16), (14, 19.5), (23, 6.5)]))
    elif name == "addimg":
        p.drawRoundedRect(QRectF(4.5, 8.5, 16, 14), 2, 2)
        p.drawPath(_open_path([(6.5, 20), (11, 14.5), (14, 18), (16, 15.5), (19, 20)]))
        p.setPen(QPen(c, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(22, 3), QPointF(22, 11))
        p.drawLine(QPointF(18, 7), QPointF(26, 7))
    elif name == "bg":
        p.drawRoundedRect(QRectF(4.5, 4.5, 19, 19), 3, 3)
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 90))
        p.drawRoundedRect(QRectF(9, 9, 10, 10), 2, 2)
    elif name == "resize":
        p.drawRect(QRectF(5, 11, 12, 12))
        p.drawLine(QPointF(14, 14), QPointF(23, 5))
        p.drawPath(_open_path([(17, 5), (23, 5), (23, 11)]))
    elif name == "pin":
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(11, 5), QPointF(19, 5), QPointF(18, 12), QPointF(21, 15),
                                 QPointF(7, 15), QPointF(10, 12)]))
        p.drawLine(QPointF(14, 15), QPointF(14, 23))
    elif name == "library":
        p.drawRoundedRect(QRectF(5, 5, 8, 8), 1.5, 1.5)
        p.drawRoundedRect(QRectF(15, 5, 8, 8), 1.5, 1.5)
        p.drawRoundedRect(QRectF(5, 15, 8, 8), 1.5, 1.5)
        p.drawRoundedRect(QRectF(15, 15, 8, 8), 1.5, 1.5)
    elif name == "edit":
        p.drawPolygon(QPolygonF([QPointF(5, 23), QPointF(6.2, 17.2), QPointF(18.5, 4.8), QPointF(23.2, 9.5),
                                 QPointF(10.8, 21.8)]))
        p.drawLine(QPointF(16, 7.5), QPointF(20.5, 12))
    elif name == "settings":
        cx = cy = 14.0
        pts = []
        n = 8
        for i in range(n):
            base = 2 * math.pi * i / n
            w = math.pi / n * 0.55
            for ang, r in ((base - w * 1.25, 8.0), (base - w * 0.7, 11.0), (base + w * 0.7, 11.0), (base + w * 1.25, 8.0)):
                pts.append(QPointF(cx + r * math.cos(ang), cy + r * math.sin(ang)))
        p.drawPolygon(QPolygonF(pts))
        p.drawEllipse(QPointF(cx, cy), 3.4, 3.4)
    elif name == "keep":
        p.drawRect(QRectF(9, 6, 10, 16))
        p.drawLine(QPointF(4, 8), QPointF(4, 20))
        p.drawLine(QPointF(24, 8), QPointF(24, 20))
    elif name == "scissors":
        p.drawEllipse(QPointF(8.5, 20), 3.2, 3.2)
        p.drawEllipse(QPointF(19.5, 20), 3.2, 3.2)
        p.drawLine(QPointF(10.6, 17.4), QPointF(19.5, 5))
        p.drawLine(QPointF(17.4, 17.4), QPointF(8.5, 5))
    elif name == "split":
        p.drawLine(QPointF(14, 4), QPointF(14, 24))
        p.drawPath(_open_path([(9, 9), (4.5, 14), (9, 19)]))
        p.drawPath(_open_path([(19, 9), (23.5, 14), (19, 19)]))
    elif name == "eyedropper":
        p.drawLine(QPointF(7.5, 20.5), QPointF(17, 11))
        p.drawLine(QPointF(5, 23), QPointF(7.5, 20.5))
        p.drawLine(QPointF(14.5, 7.5), QPointF(20.5, 13.5))
        p.drawLine(QPointF(17, 5), QPointF(22.5, 10.5))
        p.drawLine(QPointF(15.5, 6.5), QPointF(21.5, 12.5))
    elif name == "merge":
        p.drawLine(QPointF(14, 4), QPointF(14, 24))
        p.drawPath(_open_path([(4.5, 9), (9, 14), (4.5, 19)]))
        p.drawPath(_open_path([(23.5, 9), (19, 14), (23.5, 19)]))
        p.drawLine(QPointF(4.5, 14), QPointF(10.5, 14))
        p.drawLine(QPointF(23.5, 14), QPointF(17.5, 14))
    elif name == "swap":
        p.drawLine(QPointF(5, 10), QPointF(22, 10))
        p.drawPath(_open_path([(18, 6), (22.5, 10), (18, 14)]))
        p.drawLine(QPointF(23, 18), QPointF(6, 18))
        p.drawPath(_open_path([(10, 14), (5.5, 18), (10, 22)]))
    elif name == "cutrange":
        p.drawLine(QPointF(7, 4), QPointF(7, 24))
        p.drawLine(QPointF(21, 4), QPointF(21, 24))
        p.setBrush(QColor(c.red(), c.green(), c.blue(), 70))
        p.drawRect(QRectF(7, 9, 14, 10))
        p.drawLine(QPointF(10.5, 11.5), QPointF(17.5, 16.5))
        p.drawLine(QPointF(17.5, 11.5), QPointF(10.5, 16.5))
    elif name == "trash":
        p.drawLine(QPointF(5.5, 8), QPointF(22.5, 8))
        p.drawPath(_open_path([(11, 8), (11, 5), (17, 5), (17, 8)]))
        p.drawPath(_open_path([(7.5, 8), (8.7, 23), (19.3, 23), (20.5, 8)]))
        p.drawLine(QPointF(12, 12), QPointF(12.4, 19))
        p.drawLine(QPointF(16, 12), QPointF(15.6, 19))
    elif name == "play":
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(9, 5.5), QPointF(22, 14), QPointF(9, 22.5)]))
    elif name == "pause":
        p.setBrush(c)
        p.drawRoundedRect(QRectF(8, 6, 4.2, 16), 1, 1)
        p.drawRoundedRect(QRectF(15.8, 6, 4.2, 16), 1, 1)
    elif name == "stop":
        p.setBrush(c)
        p.drawRoundedRect(QRectF(7.5, 7.5, 13, 13), 2, 2)
    elif name == "skipback":
        p.setBrush(c)
        p.drawLine(QPointF(7, 6), QPointF(7, 22))
        p.drawPolygon(QPolygonF([QPointF(22, 6), QPointF(22, 22), QPointF(10, 14)]))
    elif name in ("rotl", "rotr"):
        sgn = -1 if name == "rotl" else 1
        cx = 14.0
        path = QPainterPath(QPointF(cx - sgn * 7, 12))
        path.cubicTo(QPointF(cx - sgn * 5, 5), QPointF(cx + sgn * 6, 4.5), QPointF(cx + sgn * 8, 13))
        path.cubicTo(QPointF(cx + sgn * 9, 19), QPointF(cx + sgn * 3, 24), QPointF(cx - sgn * 2, 22))
        p.drawPath(path)
        p.drawPath(_open_path([(cx - sgn * 7 - sgn * 3.2, 7.2), (cx - sgn * 7, 12), (cx - sgn * 7 + sgn * 4.5, 10.2)]))
    elif name == "close":
        p.drawLine(QPointF(8, 8), QPointF(20, 20))
        p.drawLine(QPointF(20, 8), QPointF(8, 20))
    elif name == "open":
        p.drawPath(_open_path([(4, 21), (4, 7), (11, 7), (13, 10), (22, 10), (22, 21), (4, 21)]))
    p.end()
    return QIcon(pm)


def _open_path(points: list[tuple[float, float]]) -> QPainterPath:
    path = QPainterPath(QPointF(*points[0]))
    for x, y in points[1:]:
        path.lineTo(QPointF(x, y))
    return path


def app_icon(size: int = 256) -> QIcon:
    return QIcon(app_pixmap(size))


def app_pixmap(size: int = 256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing)
    s = size / 256.0
    p.scale(s, s)
    # fundo arredondado
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#1f6feb"))
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 56, 56)
    # moldura de captura (cantos)
    pen = QPen(QColor("white"), 16, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    L, a, b = 56, 70, 186
    for (x, y, dx, dy) in ((a, a, 1, 1), (b, a, -1, 1), (a, b, 1, -1), (b, b, -1, -1)):
        p.drawLine(QPointF(x, y), QPointF(x + dx * 38, y))
        p.drawLine(QPointF(x, y), QPointF(x, y + dy * 38))
    # ponto central
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("white"))
    p.drawEllipse(QPointF(128, 128), 20, 20)
    p.end()
    return pm
