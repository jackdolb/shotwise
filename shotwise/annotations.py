"""Itens de anotação, camadas de imagem, cena e comandos de desfazer/refazer do editor.

Modelo da composição
--------------------
* A imagem final é formada por uma ou mais **camadas de imagem** (``ImageLayer``)
  -- a primeira captura e as que forem adicionadas depois -- com as anotações por cima.
* A **tela** (canvas) é a união das camadas, ou o retângulo de recorte quando houver um.
  O recorte não altera pixels: só define qual parte da composição é exportada.
* Opcionalmente a tela recebe um **fundo** (cor/degradê, margem, cantos arredondados e
  sombra) e a exportação pode ser **redimensionada** por um fator.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QRadialGradient, QTransform,
                           QPainterPathStroker, QPen, QPixmap, QPolygonF, QUndoCommand, QUndoStack)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPathItem, QGraphicsRectItem, QGraphicsScene,
                               QGraphicsTextItem)
from .i18n import tr

ACCENT = QColor("#3b9cff")
HANDLE_PX = 9.0
LAYER_Z0 = -1000

RECT_KINDS = ("rect", "ellipse", "highlight", "redact", "pixelate", "blur")
EFFECT_KINDS = ("pixelate", "blur")
TOOLS = ("select", "arrow", "line", "rect", "ellipse", "highlight", "pen", "text", "step",
         "pixelate", "blur", "redact", "zoom", "crop")
ZOOM_MIN, ZOOM_MAX = 1.2, 8.0

BG_PRESETS = [
    (tr("Névoa"), "#f4f6fa", "#d5dcea"),
    (tr("Pérola"), "#ffffff", "#e9edf3"),
    (tr("Azul claro"), "#e6eefb", "#c9d9f2"),
    (tr("Lavanda"), "#efeafa", "#d9def5"),
    (tr("Areia"), "#f7f1e8", "#e6dac8"),
    (tr("Azul petróleo"), "#24506b", "#16303f"),
    (tr("Índigo"), "#3d4a8c", "#222a55"),
    (tr("Grafite"), "#343a46", "#171a21"),
]

# direção da sombra -> (dx, dy) em unidades do deslocamento
SHADOW_DIRS = {
    "down": (0.0, 1.0), "up": (0.0, -1.0), "left": (-1.0, 0.0), "right": (1.0, 0.0),
    "down_right": (0.7, 0.7), "down_left": (-0.7, 0.7), "up_right": (0.7, -0.7), "up_left": (-0.7, -0.7),
    "center": (0.0, 0.0),
}
SHADOW_SIZES = [(tr("Pequena"), 18), (tr("Média"), 36), (tr("Grande"), 60), (tr("Extra grande"), 90)]


BG_SOLIDS = [(tr("Branco"), "#ffffff"), (tr("Cinza claro"), "#e9ecef"), (tr("Grafite"), "#1b1d22"),
             (tr("Azul"), "#0a84ff"), (tr("Verde"), "#34c759"), (tr("Laranja"), "#ff9f0a"),
             (tr("Vermelho"), "#ff3b30"), (tr("Roxo"), "#bf5af2")]

_HANDLE_CURSORS = {
    "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
    "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
    "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
}


# ----------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------
def num(value, default: float = 0.0, lo: float = -1e7, hi: float = 1e7) -> float:
    """Converte para número de forma segura (usado também ao ler projetos)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(v) or math.isinf(v):
        return default
    return min(max(v, lo), hi)


def _zoom_of(item: QGraphicsItem) -> float:
    sc = item.scene()
    return max(0.05, getattr(sc, "zoom", 1.0)) if sc is not None else 1.0


def handle_points(r: QRectF) -> dict[str, QPointF]:
    cx, cy = r.center().x(), r.center().y()
    return {
        "tl": r.topLeft(), "t": QPointF(cx, r.top()), "tr": r.topRight(),
        "r": QPointF(r.right(), cy), "br": r.bottomRight(), "b": QPointF(cx, r.bottom()),
        "bl": r.bottomLeft(), "l": QPointF(r.left(), cy),
    }


def resize_anchor(name: str, r: QRectF) -> QPointF:
    return {
        "tl": r.bottomRight(), "tr": r.bottomLeft(), "bl": r.topRight(), "br": r.topLeft(),
        "t": QPointF(r.center().x(), r.bottom()), "b": QPointF(r.center().x(), r.top()),
        "l": QPointF(r.right(), r.center().y()), "r": QPointF(r.left(), r.center().y()),
    }[name]


def dragged_rect(name: str, orig: QRectF, anchor: QPointF, p: QPointF, keep_aspect: bool = False) -> QRectF:
    """Novo retângulo ao arrastar a alça ``name`` até ``p`` (``anchor`` é o ponto oposto fixo)."""
    if len(name) == 2:
        if keep_aspect and orig.height() > 0 and orig.width() > 0:
            aspect = orig.width() / orig.height()
            dx, dy = p.x() - anchor.x(), p.y() - anchor.y()
            w = max(abs(dx), abs(dy) * aspect, 8.0)
            h = w / aspect
            p = QPointF(anchor.x() + math.copysign(w, dx or 1.0), anchor.y() + math.copysign(h, dy or 1.0))
        return QRectF(anchor, p).normalized()
    if name in ("t", "b"):
        return QRectF(QPointF(orig.left(), anchor.y()), QPointF(orig.right(), p.y())).normalized()
    return QRectF(QPointF(anchor.x(), orig.top()), QPointF(p.x(), orig.bottom())).normalized()


def paint_shadow(painter: QPainter, rect: QRectF, radius: float, blur: float = 36.0,
                 direction: str = "down", opacity: float = 0.30) -> None:
    """Sombra suave desenhada com anéis translúcidos (independe da resolução).
    ``blur`` é o tamanho do esmaecimento; o deslocamento segue a direção escolhida."""
    ux, uy = SHADOW_DIRS.get(direction, SHADOW_DIRS["down"])
    off = blur * 0.38
    painter.save()
    painter.setPen(Qt.PenStyle.NoPen)
    steps = 18
    alpha = max(1, int(255 * opacity * 1.5 / steps))
    for i in range(steps, 0, -1):
        grow = blur * i / steps
        painter.setBrush(QColor(0, 0, 0, alpha))
        r = rect.translated(ux * off, uy * off).adjusted(-grow, -grow, grow, grow)
        painter.drawRoundedRect(r, radius + grow, radius + grow)
    painter.restore()


def checker_brush() -> QBrush:
    pm = QPixmap(16, 16)
    pm.fill(QColor("#ffffff"))
    p = QPainter(pm)
    p.fillRect(0, 0, 8, 8, QColor("#d9dde3"))
    p.fillRect(8, 8, 8, 8, QColor("#d9dde3"))
    p.end()
    return QBrush(pm)


_BLUR_TEX = 160


def _blur_brush(c1: QColor, c2: QColor, frame: QRectF) -> QBrush:
    """Fundo "desfocado": manchas das duas cores se misturando, bem suaves (textura pequena, esticada)."""
    n = _BLUR_TEX
    img = QImage(n, n, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(c1)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    mix = QColor((c1.red() + c2.red()) // 2, (c1.green() + c2.green()) // 2, (c1.blue() + c2.blue()) // 2)
    for cx, cy, rad, col in ((0.85, 0.15, 0.75, c2), (0.1, 0.9, 0.7, c2), (0.5, 0.5, 0.55, mix),
                             (0.15, 0.1, 0.5, c1.lighter(125))):
        g = QRadialGradient(QPointF(cx * n, cy * n), rad * n)
        solid = QColor(col)
        solid.setAlpha(255)
        clear = QColor(col)
        clear.setAlpha(0)
        g.setColorAt(0.0, solid)
        g.setColorAt(1.0, clear)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRect(0, 0, n, n)
    p.end()
    brush = QBrush(QPixmap.fromImage(img))
    tr = QTransform()
    tr.translate(frame.x(), frame.y())
    tr.scale(max(frame.width(), 1.0) / n, max(frame.height(), 1.0) / n)
    brush.setTransform(tr)
    return brush


def _mesh_brush(c1: QColor, c2: QColor, frame: QRectF) -> QBrush:
    """Degradê mesclado (mesh): várias manchas com tons intermediários entre as duas cores, bem suaves."""
    n = _BLUR_TEX

    def mixc(a: QColor, b: QColor, t: float) -> QColor:
        return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                      round(a.blue() + (b.blue() - a.blue()) * t))

    img = QImage(n, n, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(mixc(c1, c2, 0.5))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    blobs = ((0.0, 0.0, 0.85, c1), (1.0, 0.05, 0.8, mixc(c1, c2, 0.35)), (0.95, 1.0, 0.9, c2),
             (0.05, 0.95, 0.8, mixc(c1, c2, 0.7)), (0.5, 0.45, 0.55, mixc(c1.lighter(115), c2, 0.4)),
             (0.75, 0.5, 0.4, c2.lighter(112)))
    for cx, cy, rad, col in blobs:
        g = QRadialGradient(QPointF(cx * n, cy * n), rad * n)
        solid = QColor(col)
        solid.setAlpha(255)
        clear = QColor(col)
        clear.setAlpha(0)
        g.setColorAt(0.0, solid)
        g.setColorAt(1.0, clear)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRect(0, 0, n, n)
    p.end()
    brush = QBrush(QPixmap.fromImage(img))
    tf = QTransform()
    tf.translate(frame.x(), frame.y())
    tf.scale(max(frame.width(), 1.0) / n, max(frame.height(), 1.0) / n)
    brush.setTransform(tf)
    return brush


@dataclass
class BackgroundSettings:
    enabled: bool = False
    color1: str = "#667eea"
    color2: str = "#764ba2"
    transparent: bool = False
    padding: int = 40
    radius: int = 24
    shadow: bool = True
    mode: str = "linear"       # "linear" (cores se misturam nas extremidades) | "radial" (saem do centro) | "blur"
    solid: bool = False        # True: só a cor 1, sem degradê
    shadow_blur: int = 36      # tamanho do esmaecimento da sombra (px)
    shadow_dir: str = "down"   # chave de SHADOW_DIRS
    outer_radius: int = 0      # cantos do próprio fundo (0 = retos)

    def copy(self) -> "BackgroundSettings":
        return BackgroundSettings(**asdict(self))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d) -> "BackgroundSettings":
        out = cls()
        if not isinstance(d, dict):
            return out

        def col(v, default):
            c = QColor(str(v))
            return c.name() if c.isValid() else default

        out.enabled = bool(d.get("enabled", False))
        out.color1 = col(d.get("color1"), out.color1)
        out.color2 = col(d.get("color2"), out.color2)
        out.transparent = bool(d.get("transparent", False))
        out.padding = int(num(d.get("padding"), 40, 0, 400))
        out.radius = int(num(d.get("radius"), 24, 0, 120))
        out.shadow = bool(d.get("shadow", True))
        out.mode = d.get("mode") if d.get("mode") in ("linear", "radial", "blur", "mesh") else "linear"
        out.solid = bool(d.get("solid", False))
        out.shadow_blur = int(num(d.get("shadow_blur"), 36, 4, 160))
        out.shadow_dir = d.get("shadow_dir") if d.get("shadow_dir") in SHADOW_DIRS else "down"
        out.outer_radius = int(num(d.get("outer_radius"), 0, 0, 160))
        return out

    def brush(self, frame: QRectF) -> QBrush:
        if self.transparent:
            return checker_brush()
        c1, c2 = QColor(self.color1), QColor(self.color2)
        if self.solid:
            return QBrush(c1)
        if self.mode == "radial":
            g = QRadialGradient(frame.center(), max(frame.width(), frame.height()) * 0.62)
            g.setColorAt(0.0, c1)
            g.setColorAt(1.0, c2)
            return QBrush(g)
        if self.mode == "blur":
            return _blur_brush(c1, c2, frame)
        if self.mode == "mesh":
            return _mesh_brush(c1, c2, frame)
        g = QLinearGradient(frame.topLeft(), frame.bottomRight())
        g.setColorAt(0.0, c1)
        g.setColorAt(1.0, c2)
        return QBrush(g)


class AnnotMixin:
    """Contrato comum dos itens: snapshot/restore (desfazer) e estilo."""

    kind = ""

    def snapshot(self):  # pragma: no cover - interface
        raise NotImplementedError

    def restore(self, snap):  # pragma: no cover - interface
        raise NotImplementedError

    def apply_style(self, **kw):
        """Aceita color, width, strength, font_size, text_bg (ignora o que não se aplica)."""

    def content_rect(self) -> QRectF:
        """Área realmente ocupada pelo desenho, em coordenadas da cena (sem alças nem margens de seleção).
        A tela cresce para conter isso quando o desenho passa da borda da imagem."""
        return self.sceneBoundingRect()


# ----------------------------------------------------------------------
# Camada de imagem (a captura em si e as capturas adicionadas)
# ----------------------------------------------------------------------
class ImageLayer(QGraphicsItem, AnnotMixin):
    kind = "image"

    def __init__(self, image: QImage):
        super().__init__()
        self.image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        self.box = QRectF(0, 0, self.image.width(), self.image.height())
        self._resize: tuple[str, QRectF, QPointF] | None = None
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

    def scene_rect(self) -> QRectF:
        return QRectF(self.pos() + self.box.topLeft(), self.box.size())

    def boundingRect(self) -> QRectF:
        return self.box.adjusted(-16, -16, 16, 16)

    def _handle_rect(self, pt: QPointF) -> QRectF:
        s = HANDLE_PX / _zoom_of(self)
        return QRectF(pt.x() - s / 2, pt.y() - s / 2, s, s)

    def handle_at(self, pos: QPointF) -> str | None:
        pad = 3 / _zoom_of(self)
        for name, pt in handle_points(self.box).items():
            if self._handle_rect(pt).adjusted(-pad, -pad, pad, pad).contains(pos):
                return name
        return None

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.box)
        if self.isSelected():
            for pt in handle_points(self.box).values():
                path.addRect(self._handle_rect(pt))
        return path

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        sc = self.scene()
        if sc is not None and sc.clip is not None:
            painter.setClipRect(self.mapRectFromScene(sc.clip))      # recorte: o que ficou de fora não aparece
        painter.drawImage(self.box, self.image)
        painter.setClipping(False)
        if self.isSelected():
            z = _zoom_of(self)
            pen = QPen(ACCENT, 1.4 / z)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.box)
            painter.setPen(QPen(ACCENT, 1.2 / z))
            painter.setBrush(QColor("white"))
            for pt in handle_points(self.box).values():
                painter.drawRect(self._handle_rect(pt))

    # --- mouse ---------------------------------------------------------
    def hoverMoveEvent(self, ev):
        if self.isSelected():
            h = self.handle_at(ev.pos())
            self.setCursor(_HANDLE_CURSORS[h] if h else Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.isSelected():
            h = self.handle_at(ev.pos())
            if h:
                self._resize = (h, QRectF(self.box), resize_anchor(h, self.box))
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._resize:
            name, orig, anchor = self._resize
            free = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            new = dragged_rect(name, orig, anchor, ev.pos(), keep_aspect=not free)
            if new.width() >= 8 and new.height() >= 8:
                self.prepareGeometryChange()
                self.box = new
                self.update()
                sc = self.scene()
                if sc is not None:
                    sc.refresh_canvas()
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._resize = None
        super().mouseReleaseEvent(ev)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            sc = self.scene()
            if sc is not None:
                sc.refresh_canvas()
        return super().itemChange(change, value)

    # --- estado --------------------------------------------------------
    def snapshot(self):
        return (QPointF(self.pos()), QRectF(self.box))

    def restore(self, snap):
        pos, box = snap
        self.prepareGeometryChange()
        self.box = QRectF(box)
        self.setPos(pos)
        self.update()
        sc = self.scene()
        if sc is not None:
            sc.refresh_canvas()


# ----------------------------------------------------------------------
# Retângulo, elipse, marca-texto, tarja, pixelar, desfocar
# ----------------------------------------------------------------------
class ShapeItem(QGraphicsRectItem, AnnotMixin):
    def __init__(self, kind: str, rect: QRectF, color: QColor, width: int = 4, strength: int = 16,
                 fill: QColor | None = None):
        super().__init__(rect)
        self.kind = kind
        self.color = QColor(color)
        self.width = width
        self.strength = strength
        self.fill: QColor | None = QColor(fill) if fill is not None else None   # só retângulo/elipse
        self._resize: tuple[str, QRectF, QPointF] | None = None
        self._cache = None
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setAcceptHoverEvents(True)

    # --- geometria -----------------------------------------------------
    def _stroked(self) -> bool:
        """Tem contorno desenhado? (retângulo/elipse sempre; a tarja só quando tem borda)"""
        return self.kind in ("rect", "ellipse") or (self.kind == "redact" and self.fill is not None)

    def _margin(self) -> float:
        return (self.width / 2 if self._stroked() else 0) + 16

    def boundingRect(self) -> QRectF:
        m = self._margin()
        return self.rect().normalized().adjusted(-m, -m, m, m)

    def content_rect(self) -> QRectF:
        w = self.width / 2 if self._stroked() else 0
        return self.mapRectToScene(self.rect().normalized().adjusted(-w, -w, w, w))

    def shape(self) -> QPainterPath:
        r = self.rect().normalized()
        path = QPainterPath()
        if self.kind in ("rect", "ellipse"):
            base = QPainterPath()
            base.addRect(r) if self.kind == "rect" else base.addEllipse(r)
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.width, 10))
            path = stroker.createStroke(base)
            if self.fill is not None:
                path = path.united(base)          # com preenchimento, o interior também é clicável
        else:
            path.addRect(r)
        if self.isSelected():
            for pt in handle_points(r).values():
                path.addRect(self._handle_rect(pt))
        return path

    def _handle_points(self) -> dict[str, QPointF]:
        return handle_points(self.rect().normalized())

    def _handle_rect(self, pt: QPointF) -> QRectF:
        s = HANDLE_PX / _zoom_of(self)
        return QRectF(pt.x() - s / 2, pt.y() - s / 2, s, s)

    def handle_at(self, pos: QPointF) -> str | None:
        pad = 3 / _zoom_of(self)
        for name, pt in self._handle_points().items():
            if self._handle_rect(pt).adjusted(-pad, -pad, pad, pad).contains(pos):
                return name
        return None

    # --- pintura -------------------------------------------------------
    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().normalized()
        if self.kind in ("rect", "ellipse"):
            pen = QPen(self.color, self.width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(self.fill if self.fill is not None else Qt.BrushStyle.NoBrush)
            painter.drawRect(r) if self.kind == "rect" else painter.drawEllipse(r)
        elif self.kind == "highlight":
            c = QColor(self.color)
            c.setAlpha(105)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            painter.drawRect(r)
        elif self.kind == "redact":
            if self.fill is not None:                        # borda opcional (cor guardada em `fill`)
                pen = QPen(QColor(self.fill.red(), self.fill.green(), self.fill.blue()), self.width)
                pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                painter.setPen(pen)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.color.red(), self.color.green(), self.color.blue()))   # sempre opaca
            painter.drawRect(r)
        elif self.kind in EFFECT_KINDS:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            fx = self._effect()
            if fx is not None:
                pix, top_left = fx
                painter.drawPixmap(QPointF(top_left.x() - self.pos().x(), top_left.y() - self.pos().y()), pix)
        if self.isSelected():
            self._paint_selection(painter, r)

    def _paint_selection(self, painter: QPainter, r: QRectF):
        z = _zoom_of(self)
        pen = QPen(ACCENT, 1.2 / z)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)
        painter.setPen(QPen(ACCENT, 1.2 / z))
        painter.setBrush(QColor("white"))
        for pt in self._handle_points().values():
            painter.drawRect(self._handle_rect(pt))

    def _effect(self):
        """Pixmap com pixelado/desfoque da composição (camadas) sob o item."""
        sc = self.scene()
        if sc is None:
            return None
        r = self.rect().normalized()
        scene_rect = QRectF(self.pos() + r.topLeft(), r.size()).toAlignedRect()
        inter = scene_rect.intersected(sc.canvas_rect().toAlignedRect())
        if inter.isEmpty():
            return None
        key = (inter.x(), inter.y(), inter.width(), inter.height(), self.kind, self.strength, sc.version)
        if self._cache is not None and self._cache[0] == key:
            return self._cache[1], self._cache[2]
        crop = sc.composite_region(inter)
        w, h = crop.width(), crop.height()
        s = max(2, int(self.strength))
        sw, sh = max(1, w // s), max(1, h // s)
        small = crop.scaled(sw, sh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if self.kind == "pixelate":
            out = small.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        else:
            tiny = small.scaled(max(1, sw // 2), max(1, sh // 2), Qt.AspectRatioMode.IgnoreAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            out = tiny.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        pix = QPixmap.fromImage(out)
        self._cache = (key, pix, QPointF(inter.topLeft()))
        return pix, QPointF(inter.topLeft())

    # --- mouse ---------------------------------------------------------
    def hoverMoveEvent(self, ev):
        if self.isSelected():
            h = self.handle_at(ev.pos())
            self.setCursor(_HANDLE_CURSORS[h] if h else Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.isSelected():
            h = self.handle_at(ev.pos())
            if h:
                r = self.rect().normalized()
                self._resize = (h, QRectF(r), resize_anchor(h, r))
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._resize:
            name, orig, anchor = self._resize
            self.setRect(dragged_rect(name, orig, anchor, ev.pos(), False))
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._resize = None
        super().mouseReleaseEvent(ev)

    # --- estado --------------------------------------------------------
    def snapshot(self):
        return (QPointF(self.pos()), QRectF(self.rect()), QColor(self.color), self.width, self.strength,
                QColor(self.fill) if self.fill is not None else None)

    def restore(self, snap):
        pos, rect, color, width, strength, fill = snap
        self.prepareGeometryChange()
        self.setPos(pos)
        self.setRect(rect)
        self.color, self.width, self.strength = QColor(color), width, strength
        self.fill = QColor(fill) if fill is not None else None
        self._cache = None
        self.update()

    def apply_style(self, **kw):
        self.prepareGeometryChange()
        if kw.get("color") is not None:
            c = QColor(kw["color"])
            if self.kind == "redact":
                c.setAlpha(255)                              # a tarja é sempre opaca
            self.color = c
        if kw.get("redact_width") is not None and self.kind == "redact":
            self.width = kw["redact_width"]
        if kw.get("width") is not None and self.kind in ("rect", "ellipse"):
            self.width = kw["width"]
        if kw.get("strength") is not None and self.kind in EFFECT_KINDS:
            self.strength = kw["strength"]
            self._cache = None
        if "shape_fill" in kw and self.kind in ("rect", "ellipse"):
            f = kw["shape_fill"]
            self.fill = QColor(f) if f is not None else None
        if "redact_border" in kw and self.kind == "redact":
            f = kw["redact_border"]
            self.fill = QColor(f) if f is not None else None
        self.update()


class CropItem(ShapeItem):
    """Retângulo de recorte: escurece tudo que ficará de fora."""

    def __init__(self, rect: QRectF):
        super().__init__("crop", rect, QColor("#ffffff"), 2)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setZValue(10_000)

    def boundingRect(self) -> QRectF:
        return _OVERLAY_BOUNDS          # fixo: não depende do estado da cena (ver _OVERLAY_BOUNDS)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.rect().normalized())
        for pt in self._handle_points().values():
            path.addRect(self._handle_rect(pt))
        return path

    def paint(self, painter: QPainter, option, widget=None):
        r = self.rect().normalized()
        sc = self.scene()
        outer = QPainterPath()
        outer.addRect(sc.canvas_rect() if sc else r)
        inner = QPainterPath()
        inner.addRect(r)
        painter.fillPath(outer.subtracted(inner), QColor(0, 0, 0, 150))
        z = _zoom_of(self)
        painter.setPen(QPen(QColor("white"), 1.5 / z))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1 / z))
        for i in (1, 2):
            painter.drawLine(QPointF(r.left() + r.width() * i / 3, r.top()), QPointF(r.left() + r.width() * i / 3, r.bottom()))
            painter.drawLine(QPointF(r.left(), r.top() + r.height() * i / 3), QPointF(r.right(), r.top() + r.height() * i / 3))
        painter.setPen(QPen(ACCENT, 1.2 / z))
        painter.setBrush(QColor("white"))
        for pt in self._handle_points().values():
            painter.drawRect(self._handle_rect(pt))


class ZoomItem(ShapeItem):
    """Lupa elíptica: `rect` delimita a elipse de origem; a ampliação aparece em outra elipse com a mesma
    proporção, `factor` vezes maior.

    - Origem: arraste para mover; as 8 alças redimensionam como na ferramenta Elipse.
    - Ampliação: arraste para colocá-la onde quiser; as alças dos cantos mudam o tamanho (e o aumento).
    A ampliação é uma cópia da composição (camadas + anotações, inclusive tarjas e pixelados) renderizada
    por `AnnotScene.refresh_zooms()`, nunca das camadas puras, para não revelar o que foi escondido.
    """

    GAP = 34.0
    MIN_SIDE = 12.0
    _INS = ("i_tl", "i_tr", "i_br", "i_bl")

    def __init__(self, rect: QRectF, color: QColor, width: int = 3, factor: float = 2.5,
                 offset: QPointF | None = None):
        super().__init__("zoom", rect, color, width, 16, None)
        self.factor = min(max(float(factor), ZOOM_MIN), ZOOM_MAX)
        self.offset: QPointF | None = QPointF(offset) if offset is not None else None   # centro da lupa - centro da origem
        self._img: QImage | None = None
        self._pix: QPixmap | None = None
        self._skip = False                      # True enquanto a cena renderiza as ampliações (evita recursão)
        self._drag: tuple | None = None
        self.arrow = True                       # seta ligando a origem à lupa
        self.bend: QPointF | None = None        # curvatura da seta (None = curva suave automática)

    # --- geometria -----------------------------------------------------
    def src_rect(self) -> QRectF:
        return self.rect().normalized()

    @staticmethod
    def _edge_point(r: QRectF, toward: QPointF, gap: float = 3.0) -> QPointF:
        """Ponto da borda da elipse `r` na direção de `toward` (um pouco para fora)."""
        c = r.center()
        dx, dy = toward.x() - c.x(), toward.y() - c.y()
        a, b = max(r.width() / 2, 1e-6), max(r.height() / 2, 1e-6)
        k = math.hypot(dx / a, dy / b)
        if k < 1e-9:
            return QPointF(c.x() + a, c.y())
        ex, ey = dx / k, dy / k
        n = math.hypot(ex, ey) or 1.0
        return QPointF(c.x() + ex + ex / n * gap, c.y() + ey + ey / n * gap)

    def _bend_vec(self) -> QPointF:
        if self.bend is not None:
            return self.bend
        a, b = self.src_rect().center(), self.ins_center()
        d = math.hypot(b.x() - a.x(), b.y() - a.y())
        if d < 1e-6:
            return QPointF(0, 0)
        return QPointF((b.y() - a.y()) / d * d * 0.25, -(b.x() - a.x()) / d * d * 0.25)   # curva leve e elegante

    def _ctrl(self) -> QPointF:
        a, b = self.src_rect().center(), self.ins_center()
        m = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        v = self._bend_vec()
        return QPointF(m.x() + v.x(), m.y() + v.y())

    def _arrow_geom(self):
        """(início, controle, fim) da seta, ou None se oculta ou se os círculos se sobrepõem."""
        if not self.arrow:
            return None
        src, ins = self.src_rect(), self.inset_rect()
        ctrl = self._ctrl()
        start = self._edge_point(src, ctrl)
        end = self._edge_point(ins, ctrl, gap=2.0)
        if math.hypot(end.x() - start.x(), end.y() - start.y()) < 14 or src.intersects(ins):
            return None
        return start, ctrl, end

    def _bend_handle(self) -> QPointF | None:
        g = self._arrow_geom()
        if g is None:
            return None
        start, ctrl, end = g
        return QPointF(0.25 * start.x() + 0.5 * ctrl.x() + 0.25 * end.x(),
                       0.25 * start.y() + 0.5 * ctrl.y() + 0.25 * end.y())

    def ins_center(self) -> QPointF:
        r = self.src_rect()
        off = self.offset if self.offset is not None else QPointF(r.width() * (1 + self.factor) / 2 + self.GAP, 0)
        return r.center() + off

    def inset_rect(self) -> QRectF:
        r = self.src_rect()
        w, h = r.width() * self.factor, r.height() * self.factor
        c = self.ins_center()
        return QRectF(c.x() - w / 2, c.y() - h / 2, w, h)

    def _margin(self) -> float:
        return self.width / 2 + 16

    def content_rect(self) -> QRectF:
        w = self.width / 2          # só a área de origem: a ampliação é posicionada dentro da tela, não a aumenta
        return self.mapRectToScene(self.src_rect().adjusted(-w, -w, w, w))

    def boundingRect(self) -> QRectF:
        m = self._margin() + self.width * 2
        r = self.src_rect().united(self.inset_rect())
        if self.arrow:
            c = self._ctrl()
            r = r.united(QRectF(c, QSizeF(0, 0)))
        return r.adjusted(-m, -m, m, m)

    def _handle_points(self) -> dict[str, QPointF]:
        pts = dict(handle_points(self.src_rect()))
        ins = self.inset_rect()
        pts.update({"i_tl": ins.topLeft(), "i_tr": ins.topRight(), "i_br": ins.bottomRight(),
                    "i_bl": ins.bottomLeft()})
        bh = self._bend_handle()
        if bh is not None:
            pts["bend"] = bh
        return pts

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.src_rect())
        path.addEllipse(self.inset_rect())
        g = self._arrow_geom()
        if g is not None:
            curve = QPainterPath(g[0])
            curve.quadTo(g[1], g[2])
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.width + 8, 14))
            path.addPath(stroker.createStroke(curve))
        if self.isSelected():
            for pt in self._handle_points().values():
                path.addRect(self._handle_rect(pt))
        return path

    def finalize(self, canvas: QRectF, factor: float):
        """Escolhe o aumento (cabe na tela) e posiciona a lupa do lado com espaço livre."""
        r = self.src_rect()
        if r.width() < 1 or r.height() < 1:
            return
        fmax = min(canvas.width() * 0.6 / r.width(), canvas.height() * 0.6 / r.height())
        self.prepareGeometryChange()
        self.factor = min(max(min(factor, fmax), ZOOM_MIN), ZOOM_MAX)
        bw, bh = r.width() * self.factor, r.height() * self.factor
        c = self.pos() + r.center()
        src_scene = QRectF(self.pos() + r.topLeft(), r.size()).adjusted(-2, -2, 2, 2)
        dx, dy = (r.width() + bw) / 2 + self.GAP, (r.height() + bh) / 2 + self.GAP
        chosen = QPointF(dx, 0)
        for off in (QPointF(dx, 0), QPointF(-dx, 0), QPointF(0, dy), QPointF(0, -dy)):
            ctr = QPointF(c.x() + off.x(), c.y() + off.y())
            ctr = QPointF(min(max(ctr.x(), canvas.left() + bw / 2), canvas.right() - bw / 2),
                          min(max(ctr.y(), canvas.top() + bh / 2), canvas.bottom() - bh / 2))
            box = QRectF(ctr.x() - bw / 2, ctr.y() - bh / 2, bw, bh)
            if canvas.adjusted(-1, -1, 1, 1).contains(box) and not box.intersects(src_scene):
                chosen = ctr - c
                break
        self.offset = chosen
        self.update()

    # --- ampliação (renderizada pela cena) -------------------------------
    def update_snapshot(self) -> bool:
        sc = self.scene()
        if sc is None:
            return False
        r = self.src_rect()
        if r.width() < 1 or r.height() < 1:
            return False
        k = max(self.factor * max(sc.export_scale, 1.0), 1.0)
        w, h = max(1, round(r.width() * k)), max(1, round(r.height() * k))
        while w * h > 16_000_000:                      # limite de memória
            w, h = max(1, w // 2), max(1, h // 2)
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("white"))
        prev = sc._exporting
        sc._exporting = True
        try:
            p = QPainter(img)
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                             | QPainter.RenderHint.SmoothPixmapTransform)
            sc.render(p, QRectF(0, 0, w, h), QRectF(self.pos() + r.topLeft(), r.size()))
            p.end()
        finally:
            sc._exporting = prev
        if self._img is not None and self._img == img:
            return False
        self._img = img
        self._pix = QPixmap.fromImage(img)
        return True

    # --- pintura -------------------------------------------------------
    def paint(self, painter: QPainter, option, widget=None):
        if self._skip:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        src, ins = self.src_rect(), self.inset_rect()
        w = max(1.0, float(self.width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self.color, max(1.5, w * 0.6)))       # elipse de origem: anel fino
        painter.drawEllipse(src)
        g = self._arrow_geom()
        if g is not None:                                          # seta curva da origem até a lupa
            start, ctrl, end = g
            lw = max(1.5, w * 0.7)
            ang = math.atan2(end.y() - ctrl.y(), end.x() - ctrl.x())
            hl = max(10.0, lw * 4.0)
            back = QPointF(end.x() - hl * 0.7 * math.cos(ang), end.y() - hl * 0.7 * math.sin(ang))
            path = QPainterPath(start)
            path.quadTo(ctrl, back)
            painter.setPen(QPen(self.color, lw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color)
            painter.drawPolygon(QPolygonF([end,
                                           QPointF(end.x() - hl * math.cos(ang - 0.46), end.y() - hl * math.sin(ang - 0.46)),
                                           QPointF(end.x() - hl * math.cos(ang + 0.46), end.y() - hl * math.sin(ang + 0.46))]))
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(Qt.PenStyle.NoPen)                          # sombra suave sob a lupa
        painter.setBrush(QColor(0, 0, 0, 55))
        painter.drawEllipse(ins.translated(0, 2.0).adjusted(-1, -1, 1, 1))
        clip = QPainterPath()
        clip.addEllipse(ins)
        painter.save()
        painter.setClipPath(clip)
        if self._pix is not None:
            painter.drawPixmap(ins, self._pix, QRectF(self._pix.rect()))
        else:
            painter.fillRect(ins, QColor(60, 63, 70))
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self.color, w))
        painter.drawEllipse(ins)
        if self.isSelected():
            z = _zoom_of(self)
            dash = QPen(ACCENT, 1.2 / z)
            dash.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(dash)
            painter.drawRect(src)
            painter.drawRect(ins)
            painter.setPen(QPen(ACCENT, 1.2 / z))
            painter.setBrush(QColor("white"))
            for name, pt in self._handle_points().items():
                if name == "bend":
                    painter.setBrush(QColor(ACCENT))
                    painter.drawEllipse(pt, 5 / z, 5 / z)
                    painter.setBrush(QColor("white"))
                else:
                    painter.drawRect(self._handle_rect(pt))

    # --- mouse -------------------------------------------------------------
    def hoverMoveEvent(self, ev):
        if self.isSelected():
            h = self.handle_at(ev.pos())
            if h == "bend":
                self.setCursor(Qt.CursorShape.CrossCursor)
            elif h and h in self._INS:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor if h in ("i_tl", "i_br") else Qt.CursorShape.SizeBDiagCursor)
            elif h:
                self.setCursor(_HANDLE_CURSORS[h])
            else:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
        QGraphicsRectItem.hoverMoveEvent(self, ev)

    @staticmethod
    def _inside_ellipse(r: QRectF, p: QPointF) -> bool:
        if r.width() <= 0 or r.height() <= 0:
            return False
        nx, ny = (p.x() - r.center().x()) / (r.width() / 2), (p.y() - r.center().y()) / (r.height() / 2)
        return nx * nx + ny * ny <= 1.0

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            pos = QPointF(ev.pos())
            h = self.handle_at(pos) if self.isSelected() else None
            if h == "bend":
                self._drag = ("bend",)
                ev.accept()
                return
            if h in self._INS:
                self._drag = ("scale", pos, QPointF())
                ev.accept()
                return
            if h:
                r = self.src_rect()
                self._drag = ("src", h, QRectF(r), resize_anchor(h, r), QPointF(self.ins_center()))
                ev.accept()
                return
            ins = self.inset_rect()
            if self._inside_ellipse(ins, pos) and not self._inside_ellipse(self.src_rect(), pos):
                self._drag = ("move_ins", pos, QPointF(self.ins_center() - self.src_rect().center()))
                ev.accept()
                return
        QGraphicsRectItem.mousePressEvent(self, ev)

    def mouseMoveEvent(self, ev):
        if self._drag is None:
            QGraphicsRectItem.mouseMoveEvent(self, ev)
            return
        pos = QPointF(ev.pos())
        kind = self._drag[0]
        self.prepareGeometryChange()
        if kind == "move_ins":
            _, start, off0 = self._drag
            self.offset = off0 + (pos - start)
        elif kind == "bend":
            a, b = self.src_rect().center(), self.ins_center()
            m = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            # a alça fica sobre a curva (t=0,5): o controle está ao dobro da distância ao ponto médio
            self.bend = QPointF((pos.x() - m.x()) * 2, (pos.y() - m.y()) * 2)
            for _ in range(6):                          # as pontas dependem da curva: refina até a alça ficar sob o mouse
                g = self._arrow_geom()
                if g is None:
                    break
                ctrl = QPointF((pos.x() - 0.25 * g[0].x() - 0.25 * g[2].x()) / 0.5,
                               (pos.y() - 0.25 * g[0].y() - 0.25 * g[2].y()) / 0.5)
                self.bend = QPointF(ctrl.x() - m.x(), ctrl.y() - m.y())
        elif kind == "src":
            _, name, orig, anchor, ic0 = self._drag
            new = dragged_rect(name, orig, anchor, pos, False).normalized()
            if new.width() >= self.MIN_SIDE and new.height() >= self.MIN_SIDE:
                self.setRect(new)
                self.offset = ic0 - new.center()          # a lupa fica onde estava; só a origem muda
        elif kind == "scale":
            r = self.src_rect()
            c = self.ins_center()
            fx = abs(pos.x() - c.x()) / (r.width() / 2)
            fy = abs(pos.y() - c.y()) / (r.height() / 2)
            self.offset = c - r.center()                       # o centro da lupa não se move ao redimensionar
            self.factor = min(max((fx + fy) / 2, ZOOM_MIN), ZOOM_MAX)
            sc = self.scene()
            if sc is not None:
                sc.zoom_factor_changed.emit(self.factor)
        self.update()
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if self._drag is not None:
            self._drag = None
            ev.accept()
            return
        QGraphicsRectItem.mouseReleaseEvent(self, ev)

    # --- estado --------------------------------------------------------
    def snapshot(self):
        return (QPointF(self.pos()), QRectF(self.rect()), QColor(self.color), self.width, self.factor,
                QPointF(self.offset) if self.offset is not None else None,
                QPointF(self.bend) if self.bend is not None else None, self.arrow)

    def restore(self, snap):
        pos, rect, color, width, factor, offset, bend, arrow = snap
        self.prepareGeometryChange()
        self.setPos(pos)
        self.setRect(rect)
        self.color, self.width, self.factor = QColor(color), width, factor
        self.offset = QPointF(offset) if offset is not None else None
        self.bend = QPointF(bend) if bend is not None else None
        self.arrow = bool(arrow)
        self.update()

    def apply_style(self, **kw):
        self.prepareGeometryChange()
        if kw.get("color") is not None:
            self.color = QColor(kw["color"])
        if kw.get("width") is not None:
            self.width = max(1, int(kw["width"]))
        if kw.get("zoom_arrow") is not None:
            self.arrow = bool(kw["zoom_arrow"])
        if kw.get("zoom") is not None:
            c = self.ins_center()
            self.factor = min(max(float(kw["zoom"]), ZOOM_MIN), ZOOM_MAX)
            self.offset = c - self.src_rect().center()        # muda o tamanho mantendo o centro da lupa
        self.update()


class RegionMarker(ShapeItem):
    """Retângulo tracejado temporário (seleção para reconhecimento de texto)."""

    def __init__(self, rect: QRectF):
        super().__init__("marker", rect, QColor("#ffffff"), 1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setZValue(9500)

    def shape(self) -> QPainterPath:
        return QPainterPath()

    def paint(self, painter: QPainter, option, widget=None):
        if getattr(self.scene(), "_exporting", False):
            return
        r = self.rect().normalized()
        z = _zoom_of(self)
        painter.fillRect(r, QColor(59, 156, 255, 50))
        pen = QPen(ACCENT, 1.5 / z)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)


# Retângulo delimitador FIXO das ferramentas de sobreposição. Se o boundingRect mudasse junto com o
# estado (margem, escala...), o Qt exigiria prepareGeometryChange() ANTES de cada mudança; fora dessa
# ordem o índice da cena fica inconsistente e o Windows encerra o programa (falha nativa, sem log Python).
_OVERLAY_BOUNDS = QRectF(-200000, -200000, 400000, 400000)


class _OverlayBase(QGraphicsItem):
    """Base das ferramentas com alças sobre a composição (nunca vão para a imagem exportada)."""

    def boundingRect(self) -> QRectF:
        return _OVERLAY_BOUNDS

    def __init__(self):
        super().__init__()
        self.setZValue(9000)
        self.setAcceptHoverEvents(True)
        self._drag: str | None = None

    def _s(self) -> float:
        return HANDLE_PX / _zoom_of(self)

    def _hrect(self, pt: QPointF) -> QRectF:
        s = self._s()
        return QRectF(pt.x() - s / 2, pt.y() - s / 2, s, s)

    def handles(self) -> dict[str, QPointF]:  # pragma: no cover - interface
        return {}

    def handle_at(self, pos: QPointF) -> str | None:
        pad = 4 / _zoom_of(self)
        for name, pt in self.handles().items():
            if self._hrect(pt).adjusted(-pad, -pad, pad, pad).contains(pos):
                return name
        return None

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        for pt in self.handles().values():
            path.addRect(self._hrect(pt).adjusted(-4, -4, 4, 4))
        return path

    def _exporting(self) -> bool:
        return bool(getattr(self.scene(), "_exporting", False))

    def hoverMoveEvent(self, ev):
        h = self.handle_at(ev.pos())
        if h in _HANDLE_CURSORS:
            self.setCursor(_HANDLE_CURSORS[h])
        elif h:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(ev)

    def hoverLeaveEvent(self, ev):
        self.unsetCursor()
        super().hoverLeaveEvent(ev)

    def _draw_handles(self, painter: QPainter, color: QColor = ACCENT):
        z = _zoom_of(self)
        painter.setPen(QPen(color, 1.3 / z))
        painter.setBrush(QColor("white"))
        for pt in self.handles().values():
            painter.drawRect(self._hrect(pt))

    def _label(self, painter: QPainter, text: str, at: QPointF):
        z = _zoom_of(self)
        painter.save()
        f = QFont("Segoe UI")
        f.setPixelSize(max(6, int(12 / z)))
        painter.setFont(f)
        fm = painter.fontMetrics()
        w, h = fm.horizontalAdvance(text) + 12 / z, fm.height() + 6 / z
        box = QRectF(at.x(), at.y() - h - 6 / z, w, h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(20, 20, 24, 230))
        painter.drawRoundedRect(box, 4 / z, 4 / z)
        painter.setPen(QColor("white"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class OutputFrame(_OverlayBase):
    """Ferramenta Redimensionar: moldura do tamanho FINAL; arraste as alças para escalar.

    Por padrão mantém a proporção; segure Shift para esticar livremente.
    """

    def __init__(self):
        super().__init__()
        self._live: QRectF | None = None
        self._orig = QRectF()
        self._anchor = QPointF()

    def current_rect(self) -> QRectF:
        """Moldura em unidades da cena: coincide com a imagem mostrada (a vista já aplica a escala de saída)."""
        return QRectF(self.scene().frame_rect())

    def rect(self) -> QRectF:
        return self._live if self._live is not None else self.current_rect()

    def handles(self) -> dict[str, QPointF]:
        return handle_points(self.rect()) if self.scene() is not None else {}

    def handle_at(self, pos: QPointF) -> str | None:
        """Alças e também as bordas inteiras (mais fácil de agarrar do que um quadradinho)."""
        h = super().handle_at(pos)
        if h or self.scene() is None:
            return h
        r = self.rect()
        pad = 8 / _zoom_of(self)
        if not r.adjusted(-pad, -pad, pad, pad).contains(pos) or r.adjusted(pad, pad, -pad, -pad).contains(pos):
            return None
        d = {"l": abs(pos.x() - r.left()), "r": abs(pos.x() - r.right()),
             "t": abs(pos.y() - r.top()), "b": abs(pos.y() - r.bottom())}
        name = min(d, key=d.get)
        return name if d[name] <= pad else None

    def shape(self) -> QPainterPath:
        path = super().shape()
        if self.scene() is None:
            return path
        r, pad = self.rect(), 8 / _zoom_of(self)
        ring = QPainterPath()
        ring.addRect(r.adjusted(-pad, -pad, pad, pad))
        inner = QPainterPath()
        inner.addRect(r.adjusted(pad, pad, -pad, -pad))
        return path.united(ring.subtracted(inner))

    def paint(self, painter: QPainter, option, widget=None):
        if self._exporting():
            return
        r = self.rect()
        z = _zoom_of(self)
        if self._live is not None:
            # durante o arraste: escurece o que fica fora do novo tamanho e tinge o novo quadro
            cur = self.current_rect()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 70))
            outside = QPainterPath()
            outside.addRect(cur.united(r).adjusted(-4, -4, 4, 4))
            keep = QPainterPath()
            keep.addRect(r)
            painter.drawPath(outside.subtracted(keep))
            painter.setBrush(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 28))
            painter.drawRect(r)
        pen = QPen(ACCENT, 1.6 / z)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(r)
        self._draw_handles(painter)
        sc = self.scene()
        base = sc.frame_rect()
        sx, sy = sc.scale_xy()
        pct = r.width() * sx / max(1.0, base.width()) * 100
        self._label(painter, f"{round(r.width() * sx)} × {round(r.height() * sy)} px  ({pct:.0f}%)", r.topLeft())

    def mousePressEvent(self, ev):
        h = self.handle_at(ev.pos()) if ev.button() == Qt.MouseButton.LeftButton else None
        if not h:
            ev.ignore()
            return
        self._drag, self._orig, self._anchor = h, QRectF(self.current_rect()), resize_anchor(h, self.current_rect())
        self._live = QRectF(self._orig)
        ev.accept()

    def mouseMoveEvent(self, ev):
        if not self._drag:
            return
        free = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        orig = self._orig
        new = dragged_rect(self._drag, orig, self._anchor, ev.pos(), keep_aspect=not free)
        if not free and len(self._drag) == 1 and orig.width() > 0 and orig.height() > 0:
            # alças das laterais também preservam a proporção
            if self._drag in ("l", "r"):
                f = new.width() / orig.width()
                new = QRectF(0, 0, orig.width() * f, orig.height() * f)
            else:
                f = new.height() / orig.height()
                new = QRectF(0, 0, orig.width() * f, orig.height() * f)
            new.moveTopLeft(self._anchor_corner(new))
        if new.width() >= 16 and new.height() >= 16:
            self._live = new
            self.update()
        ev.accept()

    def _anchor_corner(self, new: QRectF) -> QPointF:
        """Mantém fixo o lado oposto ao da alça arrastada ao reproporcionar pelas laterais."""
        o = self._orig
        if self._drag == "r":
            return QPointF(o.left(), o.center().y() - new.height() / 2)
        if self._drag == "l":
            return QPointF(o.right() - new.width(), o.center().y() - new.height() / 2)
        if self._drag == "b":
            return QPointF(o.center().x() - new.width() / 2, o.top())
        return QPointF(o.center().x() - new.width() / 2, o.bottom() - new.height())

    def mouseReleaseEvent(self, ev):
        if self._drag and self._live is not None:
            sc = self.scene()
            base = sc.frame_rect()
            live = self._live
            self._drag, self._live = None, None
            sx, sy = sc.scale_xy()
            sc.set_output_size(live.width() * sx, live.height() * sy, base)
            self.update()
        self._drag = None
        ev.accept()


class BackgroundHandles(_OverlayBase):
    """Ferramenta Fundo: arraste as bordas para mudar a margem e o ponto laranja para arredondar os cantos."""

    def __init__(self):
        super().__init__()
        self._old: BackgroundSettings | None = None

    def _active(self) -> bool:
        return self.scene() is not None and self.scene().background.enabled

    def handles(self) -> dict[str, QPointF]:
        if not self._active():
            return {}
        sc = self.scene()
        frame = sc.frame_rect()
        c = sc.canvas_rect()
        bs = sc.background
        pts = {"l": QPointF(frame.left(), frame.center().y()), "r": QPointF(frame.right(), frame.center().y()),
               "t": QPointF(frame.center().x(), frame.top()), "b": QPointF(frame.center().x(), frame.bottom())}
        return pts

    def paint(self, painter: QPainter, option, widget=None):
        if self._exporting() or not self._active():
            return
        z = _zoom_of(self)
        sc = self.scene()
        dragging = bool(self._drag)
        if dragging:                       # a moldura tracejada e a medida só aparecem enquanto se arrasta
            pen = QPen(ACCENT, 1.4 / z)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(sc.frame_rect())
        painter.setPen(QPen(ACCENT, 1.3 / z))
        painter.setBrush(QColor("white"))
        for pt in self.handles().values():
            painter.drawRect(self._hrect(pt))
        if dragging:
            self._label(painter, f"margem {sc.background.padding}px", sc.frame_rect().topLeft())

    def mousePressEvent(self, ev):
        h = self.handle_at(ev.pos()) if ev.button() == Qt.MouseButton.LeftButton else None
        if not h:
            ev.ignore()
            return
        self._drag = h
        self._old = self.scene().background.copy()
        ev.accept()

    def mouseMoveEvent(self, ev):
        if not self._drag or self._old is None:
            return
        sc = self.scene()
        c = sc.canvas_rect()
        p = ev.pos()
        bs = self._old.copy()
        d = {"l": c.left() - p.x(), "r": p.x() - c.right(), "t": c.top() - p.y(), "b": p.y() - c.bottom()}[self._drag]
        bs.padding = int(min(max(d, 0), 400))
        sc.preview_background(bs)
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if self._drag and self._old is not None:
            sc = self.scene()
            new = sc.background.copy()
            old = self._old
            self._drag, self._old = None, None
            if new.to_dict() != old.to_dict():
                sc.commit_background(old, new)
        self._drag = None
        ev.accept()


# ----------------------------------------------------------------------
# Linha e seta
# ----------------------------------------------------------------------
class LineItem(QGraphicsItem, AnnotMixin):
    """Linha ou seta. O ponto do meio (alça) curva o traço; `bend` é o deslocamento do ponto de controle
    em relação ao centro do segmento (0 = reta)."""

    def __init__(self, kind: str, p1: QPointF, p2: QPointF, color: QColor, width: int = 4, round_: int = 0,
                 bend: QPointF | None = None):
        super().__init__()
        self.kind = kind
        self.p1, self.p2 = QPointF(p1), QPointF(p2)
        self.color = QColor(color)
        self.width = width
        self.bend = QPointF(bend) if bend is not None else QPointF(0, 0)
        self._drag: str | None = None
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setAcceptHoverEvents(True)

    # --- geometria -----------------------------------------------------
    @property
    def round(self) -> int:
        """Curvatura em % (0 a 100): flecha do arco em relação ao comprimento."""
        length = QLineF(self.p1, self.p2).length()
        if length < 1:
            return 0
        return int(min(100, round(math.hypot(self.bend.x(), self.bend.y()) / length * 100)))

    def _normal(self) -> QPointF:
        d = QLineF(self.p1, self.p2)
        if d.length() < 1e-6:
            return QPointF(0, -1)
        return QPointF(d.dy() / d.length(), -d.dx() / d.length())

    def set_curvature(self, percent: int):
        """Define a curvatura mantendo o lado para o qual o traço já está curvado."""
        n = self._normal()
        side = 1.0 if (self.bend.x() * n.x() + self.bend.y() * n.y()) >= 0 else -1.0
        length = QLineF(self.p1, self.p2).length()
        k = side * min(max(percent, 0), 100) / 100.0 * length
        self.bend = QPointF(n.x() * k, n.y() * k)

    def set_points(self, p1: QPointF, p2: QPointF):
        self.prepareGeometryChange()
        self.p1, self.p2 = QPointF(p1), QPointF(p2)
        self.update()

    def _mid(self) -> QPointF:
        return QPointF((self.p1.x() + self.p2.x()) / 2, (self.p1.y() + self.p2.y()) / 2)

    def _ctrl(self) -> QPointF:
        m = self._mid()
        return QPointF(m.x() + self.bend.x(), m.y() + self.bend.y())

    def _curve_mid(self) -> QPointF:
        """Ponto da curva em t=0,5 (onde fica a alça)."""
        m = self._mid()
        return QPointF(m.x() + self.bend.x() / 2, m.y() + self.bend.y() / 2)

    def _head_len(self) -> float:
        return max(14.0, self.width * 4.5)

    def content_rect(self) -> QRectF:
        w = self.width / 2 + 1
        xs = [self.p1.x(), self.p2.x()]
        ys = [self.p1.y(), self.p2.y()]
        return self.mapRectToScene(QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys))).adjusted(-w, -w, w, w))

    def boundingRect(self) -> QRectF:
        m = self._head_len() + self.width + 14
        pts = (self.p1, self.p2, self._ctrl())
        xs = [p.x() for p in pts]
        ys = [p.y() for p in pts]
        return QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys))).adjusted(-m, -m, m, m)

    def _path(self, end: QPointF) -> QPainterPath:
        path = QPainterPath(self.p1)
        if self.bend.manhattanLength() < 0.5:
            path.lineTo(end)
        else:
            path.quadTo(self._ctrl(), end)
        return path

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.width + 8, 14))
        out = stroker.createStroke(self._path(self.p2))
        if self.isSelected():
            r = 8 / _zoom_of(self)
            for p in (self.p1, self.p2, self._curve_mid()):
                out.addEllipse(p, r, r)
        return out

    def _tangent_end(self) -> float:
        """Ângulo da tangente em p2 (a ponta da seta acompanha a curva)."""
        src = self._ctrl() if self.bend.manhattanLength() >= 0.5 else self.p1
        return math.atan2(self.p2.y() - src.y(), self.p2.x() - src.x())

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.color, self.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        length = QLineF(self.p1, self.p2).length()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == "arrow" and length > 1:
            hl = min(self._head_len(), length * 0.9)
            ang = self._tangent_end()
            spread = 0.46
            left = QPointF(self.p2.x() - hl * math.cos(ang - spread), self.p2.y() - hl * math.sin(ang - spread))
            right = QPointF(self.p2.x() - hl * math.cos(ang + spread), self.p2.y() - hl * math.sin(ang + spread))
            back = QPointF(self.p2.x() - hl * 0.7 * math.cos(ang), self.p2.y() - hl * 0.7 * math.sin(ang))
            painter.setPen(pen)
            painter.drawPath(self._path(back))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color)
            painter.drawPolygon(QPolygonF([self.p2, left, right]))
        else:
            painter.setPen(pen)
            painter.drawPath(self._path(self.p2))
        if self.isSelected():
            z = _zoom_of(self)
            painter.setPen(QPen(ACCENT, 1.2 / z))
            painter.setBrush(QColor("white"))
            r = 5 / z
            painter.drawEllipse(self.p1, r, r)
            painter.drawEllipse(self.p2, r, r)
            painter.setBrush(QColor(ACCENT))                  # alça do meio: curva o traço
            painter.drawEllipse(self._curve_mid(), r, r)

    def _end_at(self, pos: QPointF) -> str | None:
        r = 9 / _zoom_of(self)
        if QLineF(pos, self.p1).length() <= r:
            return "p1"
        if QLineF(pos, self.p2).length() <= r:
            return "p2"
        if QLineF(pos, self._curve_mid()).length() <= r:
            return "mid"
        return None

    def hoverMoveEvent(self, ev):
        if self.isSelected():
            self.setCursor(Qt.CursorShape.CrossCursor if self._end_at(ev.pos()) else Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.isSelected():
            end = self._end_at(ev.pos())
            if end:
                self._drag = end
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag:
            if self._drag == "mid":
                m = self._mid()
                self.prepareGeometryChange()
                self.bend = QPointF((ev.pos().x() - m.x()) * 2, (ev.pos().y() - m.y()) * 2)
                self.update()
                sc = self.scene()
                if sc is not None:
                    sc.curvature_changed.emit(self.round)
            elif self._drag == "p1":
                self.set_points(ev.pos(), self.p2)
            else:
                self.set_points(self.p1, ev.pos())
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._drag is not None:
            self._drag = None
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def snapshot(self):
        return (QPointF(self.pos()), QPointF(self.p1), QPointF(self.p2), QColor(self.color), self.width,
                QPointF(self.bend))

    def restore(self, snap):
        pos, p1, p2, color, width, bend = snap
        self.prepareGeometryChange()
        self.setPos(pos)
        self.p1, self.p2, self.color, self.width = QPointF(p1), QPointF(p2), QColor(color), width
        self.bend = QPointF(bend)
        self.update()

    def apply_style(self, **kw):
        self.prepareGeometryChange()
        if kw.get("color") is not None:
            self.color = QColor(kw["color"])
        if kw.get("width") is not None:
            self.width = kw["width"]
        if kw.get("arrow_round") is not None:
            self.set_curvature(int(kw["arrow_round"]))
        self.update()


# ----------------------------------------------------------------------
# Traço livre
# ----------------------------------------------------------------------
class PenItem(QGraphicsPathItem, AnnotMixin):
    kind = "pen"

    def __init__(self, start: QPointF, color: QColor, width: int = 4):
        super().__init__()
        self.points = [QPointF(start)]
        self.color = QColor(color)
        self.width = width
        self._apply_pen()
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self._rebuild()

    def _apply_pen(self):
        self.setPen(QPen(self.color, self.width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                         Qt.PenJoinStyle.RoundJoin))
        self.setBrush(Qt.BrushStyle.NoBrush)

    def add_point(self, p: QPointF):
        if QLineF(self.points[-1], p).length() >= 1.5:
            self.points.append(QPointF(p))
            self._rebuild()

    def _rebuild(self):
        pts = self.points
        path = QPainterPath(pts[0])
        if len(pts) == 1:
            path.lineTo(pts[0] + QPointF(0.01, 0))
        elif len(pts) == 2:
            path.lineTo(pts[1])
        else:
            for i in range(1, len(pts) - 1):
                mid = QPointF((pts[i].x() + pts[i + 1].x()) / 2, (pts[i].y() + pts[i + 1].y()) / 2)
                path.quadTo(pts[i], mid)
            path.lineTo(pts[-1])
        self.setPath(path)

    def snapshot(self):
        return (QPointF(self.pos()), QColor(self.color), self.width)

    def restore(self, snap):
        pos, color, width = snap
        self.setPos(pos)
        self.color, self.width = QColor(color), width
        self._apply_pen()
        self.update()

    def apply_style(self, **kw):
        if kw.get("color") is not None:
            self.color = QColor(kw["color"])
        if kw.get("width") is not None:
            self.width = kw["width"]
        self._apply_pen()
        self.update()


# ----------------------------------------------------------------------
# Texto (com fundo opcional)
# ----------------------------------------------------------------------
class TextItem(QGraphicsTextItem, AnnotMixin):
    kind = "text"

    def __init__(self, text: str, color: QColor, size: int = 28, bg: QColor | None = None):
        super().__init__(text)
        self.color = QColor(color)
        self.size = size
        self.bg: QColor | None = QColor(bg) if bg is not None else None
        self.editing = False
        self.committed = False
        self.document().setDocumentMargin(7)
        self._apply_font()
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                      | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)

    def _apply_font(self):
        f = QFont("Segoe UI")
        f.setPixelSize(int(self.size))
        f.setBold(True)
        self.setFont(f)
        self.setDefaultTextColor(self.color)

    def start_edit(self):
        self.editing = True
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        cur = self.textCursor()
        cur.select(cur.SelectionType.Document)
        self.setTextCursor(cur)

    def mouseDoubleClickEvent(self, ev):
        if not self.editing:
            self.start_edit()
        super().mouseDoubleClickEvent(ev)

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        if self.editing:
            self.editing = False
            self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            cur = self.textCursor()
            cur.clearSelection()
            self.setTextCursor(cur)
            sc = self.scene()
            if sc is not None:
                sc.text_finished(self)

    def paint(self, painter: QPainter, option, widget=None):
        from PySide6.QtWidgets import QStyle

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if self.bg is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.bg)
            painter.drawRoundedRect(self.boundingRect(), 8, 8)
        opt = type(option)(option)
        opt.state &= ~QStyle.StateFlag.State_Selected
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, opt, widget)
        if self.isSelected() or self.editing:
            z = _zoom_of(self)
            pen = QPen(ACCENT, 1.2 / z)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

    def snapshot(self):
        return (QPointF(self.pos()), QColor(self.color), self.size, QColor(self.bg) if self.bg is not None else None)

    def restore(self, snap):
        pos, color, size, bg = snap
        self.setPos(pos)
        self.color, self.size = QColor(color), size
        self.bg = QColor(bg) if bg is not None else None
        self._apply_font()
        self.update()

    def apply_style(self, **kw):
        if kw.get("color") is not None:
            self.color = QColor(kw["color"])
        if kw.get("font_size") is not None:
            self.size = kw["font_size"]
        if "text_bg" in kw:
            bg = kw["text_bg"]
            self.bg = QColor(bg) if bg is not None else None
        self._apply_font()
        self.update()


# ----------------------------------------------------------------------
# Marcador numerado
# ----------------------------------------------------------------------
class StepItem(QGraphicsItem, AnnotMixin):
    kind = "step"

    def __init__(self, number: int, color: QColor, radius: int = 16, border: QColor | None = None):
        super().__init__()
        self.number = number
        self.color = QColor(color)
        self.radius = radius
        self.border = QColor("white") if border is None else QColor(border)    # transparente = sem borda
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def content_rect(self) -> QRectF:
        r = self.radius + (max(2.0, self.radius / 8) / 2 if self.border.alpha() else 0)
        return QRectF(self.pos().x() - r, self.pos().y() - r, 2 * r, 2 * r)

    def boundingRect(self) -> QRectF:
        r = self.radius + 6
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addEllipse(QPointF(0, 0), self.radius + 2, self.radius + 2)
        return p

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        r = self.radius
        painter.setPen(QPen(self.border, max(2.0, r / 8)) if self.border.alpha() else Qt.PenStyle.NoPen)
        painter.setBrush(self.color)
        painter.drawEllipse(QPointF(0, 0), r, r)
        dark_text = self.color.lightness() > 165
        painter.setPen(QColor("#111111") if dark_text else QColor("white"))
        f = QFont("Segoe UI")
        f.setPixelSize(int(r * 1.15))
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(-r, -r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, str(self.number))
        if self.isSelected():
            z = _zoom_of(self)
            pen = QPen(ACCENT, 1.2 / z)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r + 4, r + 4)

    def snapshot(self):
        return (QPointF(self.pos()), QColor(self.color), self.radius, self.number, QColor(self.border))

    def restore(self, snap):
        pos, color, radius, number, border = snap
        self.prepareGeometryChange()
        self.setPos(pos)
        self.color, self.radius, self.number, self.border = QColor(color), radius, number, QColor(border)
        self.update()

    def apply_style(self, **kw):
        self.prepareGeometryChange()
        if kw.get("color") is not None:
            self.color = QColor(kw["color"])
        if kw.get("step_size") is not None:
            self.radius = int(min(max(kw["step_size"], 6), 120))
        if kw.get("step_border") is not None:
            self.border = QColor(kw["step_border"])
        self.update()


# ----------------------------------------------------------------------
# Comandos de desfazer/refazer
# ----------------------------------------------------------------------
class AddCommand(QUndoCommand):
    def __init__(self, scene: "AnnotScene", item: QGraphicsItem, label: str = tr("Adicionar"), reset_clip: bool = False):
        super().__init__(label)
        self.scene, self.item = scene, item
        self._first = True
        self.reset_clip = reset_clip
        self._old_clip = None

    def redo(self):
        if self.reset_clip:
            self._old_clip = self.scene.clip
            self.scene.clip = None
        if self._first:
            self._first = False
            if self.item.scene() is None:
                self.scene.addItem(self.item)
        else:
            self.scene.addItem(self.item)
        if isinstance(self.item, TextItem):
            self.item.committed = True
        self.scene.refresh_canvas()

    def undo(self):
        self.item.setSelected(False)
        self.scene.removeItem(self.item)
        if self.reset_clip:
            self.scene.clip = self._old_clip
        self.scene.refresh_canvas()


class RemoveCommand(QUndoCommand):
    def __init__(self, scene: "AnnotScene", item: QGraphicsItem):
        super().__init__("Remover")
        self.scene, self.item = scene, item

    def redo(self):
        self.item.setSelected(False)
        self.scene.removeItem(self.item)
        self.scene.refresh_canvas()

    def undo(self):
        self.scene.addItem(self.item)
        self.scene.refresh_canvas()


class StateCommand(QUndoCommand):
    def __init__(self, item: AnnotMixin, old, new, label: str = "Alterar"):
        super().__init__(label)
        self.item, self.old, self.new = item, old, new

    def redo(self):
        self.item.restore(self.new)

    def undo(self):
        self.item.restore(self.old)


class AttrCommand(QUndoCommand):
    """Altera um atributo da cena (recorte, fundo, escala de exportação)."""

    def __init__(self, scene: "AnnotScene", name: str, old, new, label: str):
        super().__init__(label)
        self.scene, self.name, self.old, self.new = scene, name, old, new

    def redo(self):
        setattr(self.scene, self.name, self.new)
        self.scene.settings_changed()

    def undo(self):
        setattr(self.scene, self.name, self.old)
        self.scene.settings_changed()


class SizeCommand(QUndoCommand):
    """Altera o tamanho de exportação: (escala, esticamento vertical)."""

    def __init__(self, scene: "AnnotScene", old: tuple[float, float], new: tuple[float, float]):
        super().__init__("Redimensionar")
        self.scene, self.old, self.new = scene, old, new

    def _apply(self, v):
        self.scene.export_scale, self.scene.export_stretch = v
        self.scene.settings_changed()

    def redo(self):
        self._apply(self.new)

    def undo(self):
        self._apply(self.old)


# ----------------------------------------------------------------------
# Cena
# ----------------------------------------------------------------------
class AnnotScene(QGraphicsScene):
    canvas_changed = Signal()
    tool_hint = Signal(str)
    ocr_requested = Signal(QRectF)
    curvature_changed = Signal(int)         # traço curvado pela alça do meio: sincroniza o controle
    tool_change_requested = Signal(str)     # clique em outro tipo de desenho: o editor troca para a ferramenta dele
    zoom_factor_changed = Signal(float)     # lupa redimensionada com a alça: sincroniza o controle de aumento

    def __init__(self, image: QImage | None = None, parent=None):
        super().__init__(parent)
        # poucos itens: sem índice espacial, uma geometria atualizada fora de ordem nunca derruba o programa
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.undo_stack = QUndoStack(self)
        self.version = 0
        self.zoom = 1.0
        self.tool = "select"
        self.picker = None              # conta-gotas: função chamada com a cor do próximo clique
        self._pending_hit = None
        self.opt_color = QColor("#ff3b30")
        self.opt_width = 4
        self.opt_font = 28
        self.opt_strength = 16
        self.opt_step_size = 16        # raio do marcador numerado
        self.opt_step_border = QColor("white")     # borda do marcador (transparente = sem borda)
        self._canvas_seen: QRectF | None = None
        self.opt_round = 0             # arredondamento da ponta da seta
        self.opt_text_bg: QColor | None = None
        self.opt_fill: QColor | None = None
        self.opt_redact_border: QColor | None = None
        self.opt_redact_width = 3
        self.opt_zoom = 2.5            # aumento da lupa
        self.opt_zoom_arrow = True     # seta ligando a origem à lupa
        self._refreshing = False
        self._overlay: QGraphicsItem | None = None
        self.clip: QRectF | None = None
        self.export_scale = 1.0
        self.export_stretch = 1.0      # altura = escala × esticamento (1 = proporcional)
        self.background = BackgroundSettings()
        self._exporting = False
        self._drawing: QGraphicsItem | None = None
        self._start = QPointF()
        self._snap: dict | None = None
        self._crop: CropItem | None = None
        if image is not None:
            self.add_layer(image)
        self.changed.connect(lambda _regions: (self.refresh_zooms(), self._check_canvas()))

    def refresh_zooms(self):
        """Atualiza a imagem ampliada das lupas (também antes de exportar, para refletir tarjas novas)."""
        zs = [i for i in self.items() if isinstance(i, ZoomItem)]
        if not zs or self._refreshing:
            return
        self._refreshing = True
        for z in zs:
            z._skip = True               # uma lupa não aparece dentro de outra
        try:
            for z in zs:
                if z.update_snapshot():
                    z.update()
        finally:
            for z in zs:
                z._skip = False
            self._refreshing = False

    # --- camadas / tela ------------------------------------------------
    def layers(self) -> list[ImageLayer]:
        return sorted((i for i in self.items() if isinstance(i, ImageLayer)), key=lambda l: l.zValue())

    def add_layer(self, image: QImage, pos: QPointF | None = None) -> ImageLayer:
        layer = ImageLayer(image)
        layer.setZValue(LAYER_Z0 + len(self.layers()))
        layer.setPos(pos if pos is not None else (self.next_layer_pos() if self.layers() else QPointF(0, 0)))
        self.addItem(layer)
        self.refresh_canvas()
        return layer

    def next_layer_pos(self) -> QPointF:
        """Posição padrão de uma nova camada: à direita da composição atual."""
        rect = QRectF()
        for l in self.layers():
            rect = rect.united(l.scene_rect())
        return QPointF(rect.right() + 24, rect.top()) if not rect.isNull() else QPointF(0, 0)

    GROW_MARGIN = 12            # sobra deixada além de um desenho que passa da borda da imagem
    GROW_LIMIT = 2000           # o quanto a tela pode crescer, em cada lado

    def base_rect(self) -> QRectF:
        """Área das imagens (ou do recorte), sem o crescimento causado por desenhos."""
        if self.clip is not None:
            return QRectF(self.clip)
        rect = QRectF()
        for l in self.layers():
            rect = rect.united(l.scene_rect())
        if rect.isNull() or rect.width() < 1 or rect.height() < 1:
            return QRectF(0, 0, 1, 1)
        return QRectF(rect.toAlignedRect())

    def canvas_rect(self) -> QRectF:
        """Tela de saída: a imagem, ampliada quando um desenho passa da borda (com uma pequena sobra)."""
        base = self.base_rect()
        if self.clip is not None:                # com recorte definido, a área é a do recorte
            return base
        limit = base.adjusted(-self.GROW_LIMIT, -self.GROW_LIMIT, self.GROW_LIMIT, self.GROW_LIMIT)
        grown = QRectF(base)
        m = self.GROW_MARGIN
        for it in self.items():
            if not self._is_annotation(it) or not it.isVisible() or isinstance(it, RegionMarker):
                continue
            cr = it.content_rect()
            if not base.contains(cr):            # a sobra só vale nos lados em que o desenho passa da borda
                cr = cr.adjusted(-m if cr.left() < base.left() else 0, -m if cr.top() < base.top() else 0,
                                 m if cr.right() > base.right() else 0, m if cr.bottom() > base.bottom() else 0)
                grown = grown.united(cr.intersected(limit))
        return QRectF(grown.toAlignedRect()) if grown != base else base

    def _work_rect(self) -> QRectF:
        """Onde o mouse pode desenhar: a tela e uma folga ao redor (a tela cresce junto com o desenho)."""
        base = self.base_rect()
        if self.clip is not None:
            return base
        return base.adjusted(-self.GROW_LIMIT, -self.GROW_LIMIT, self.GROW_LIMIT, self.GROW_LIMIT)

    def _check_canvas(self):
        if self._exporting:
            return
        c = self.canvas_rect()
        if c != self._canvas_seen:
            self.refresh_canvas()

    def frame_rect(self) -> QRectF:
        """Área visível da composição: tela + margem do fundo (usada para ajustar o zoom)."""
        c = self.canvas_rect()
        if self.background.enabled:
            pad = self.background.padding
            return c.adjusted(-pad, -pad, pad, pad)
        return c

    def refresh_canvas(self):
        layers = self.layers()
        multi = len(layers) > 1
        for l in layers:
            l.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, multi)
            l.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, multi)
            if not multi and l.isSelected():
                l.setSelected(False)
        c = self.canvas_rect()
        self._canvas_seen = QRectF(c)
        m = 400 + (self.background.padding if self.background.enabled else 0)
        self.setSceneRect(self.sceneRect().united(c.adjusted(-m, -m, m, m)))
        if self._overlay is not None:
            self._overlay.update()
        self.version += 1
        self.update()
        self.canvas_changed.emit()

    def settings_changed(self):
        self.refresh_canvas()

    def composite_region(self, r: QRect) -> QImage:
        """Pixels das camadas (sem anotações) dentro de ``r``, em coordenadas da cena."""
        img = QImage(r.size(), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.translate(-r.x(), -r.y())
        for l in self.layers():
            p.drawImage(l.scene_rect(), l.image)
        p.end()
        return img

    def output_size(self) -> tuple[int, int]:
        c = self.canvas_rect()
        w, h = int(c.width()), int(c.height())
        if self.background.enabled:
            w += 2 * self.background.padding
            h += 2 * self.background.padding
        s = self.export_scale
        return max(1, round(w * s)), max(1, round(h * s * self.export_stretch))

    def scale_xy(self) -> tuple[float, float]:
        return self.export_scale, self.export_scale * self.export_stretch

    # --- desenho de fundo/primeiro plano (somente na tela, nunca na exportação) --
    def drawBackground(self, painter: QPainter, rect: QRectF):
        if self._exporting:
            return
        canvas = self.canvas_rect()
        bs = self.background
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if bs.enabled:
            frame = canvas.adjusted(-bs.padding, -bs.padding, bs.padding, bs.padding)
            if bs.outer_radius > 0:
                fp = QPainterPath()
                fp.addRoundedRect(frame, bs.outer_radius, bs.outer_radius)
                painter.fillPath(fp, bs.brush(frame))
            else:
                painter.fillRect(frame, bs.brush(frame))
            if bs.shadow:
                paint_shadow(painter, canvas, bs.radius, bs.shadow_blur, bs.shadow_dir)
        else:
            painter.fillRect(canvas, QColor("white"))

    def drawForeground(self, painter: QPainter, rect: QRectF):
        if self._exporting:
            return
        canvas = self.canvas_rect()
        bs = self.background
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if bs.enabled and bs.radius > 0:
            outer = QPainterPath()
            outer.addRect(canvas)
            inner = QPainterPath()
            inner.addRoundedRect(canvas, bs.radius, bs.radius)
            frame = canvas.adjusted(-bs.padding, -bs.padding, bs.padding, bs.padding)
            painter.fillPath(outer.subtracted(inner), bs.brush(frame))
        pen = QPen(QColor(255, 255, 255, 60), 1.0 / max(self.zoom, 0.05))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(canvas)

    # --- ferramenta ----------------------------------------------------
    def _set_overlay(self, tool: str):
        if self._overlay is not None:
            if self._overlay.scene() is self:
                self.removeItem(self._overlay)
            self._overlay = None
        if tool == "resize":
            self._overlay = OutputFrame()
        elif tool == "background":
            self._overlay = BackgroundHandles()
        if self._overlay is not None:
            self.addItem(self._overlay)

    def set_tool(self, tool: str, keep_selection: bool = False):
        if tool != "crop":
            self.cancel_crop()
        self.tool = tool
        self.picker = None
        self._pending_hit = None
        self._set_overlay(tool)
        if tool != "select" and not keep_selection:
            self.clearSelection()
        hints = {
            "crop": tr("Arraste para escolher a área; Enter aplica o recorte, Esc cancela."),
            "text": tr("Clique para inserir texto. Clique duplo em um texto para editar. Use a opção Fundo para destacar."),
            "step": tr("Clique para colocar marcadores numerados em sequência."),
            "redact": tr("Tarja sólida: é a forma mais segura de esconder dados (não reversível)."),
            "pixelate": tr("Pixelar: use intensidade alta para dados sensíveis."),
            "blur": tr("Desfocar: prefira a tarja sólida para senhas, tokens e chaves."),
            "select": tr("Selecionar: o item clicado vem para a frente. Com várias capturas, arraste para mover e use as alças."),
            "resize": tr("Arraste as alças para redimensionar a imagem final (Shift = esticar livremente)."),
            "background": tr("Arraste as bordas para mudar a margem; cantos, sombra e cores ficam no painel."),
            "ocr": tr("Arraste sobre o texto que deseja reconhecer e copiar."),
            "zoom": tr("Arraste sobre a parte a ampliar (elipse; Shift = círculo). Arraste a lupa para onde quiser; as alças mudam o tamanho."),
        }
        self.tool_hint.emit(hints.get(tool, ""))

    def next_step_number(self) -> int:
        nums = [i.number for i in self.items() if isinstance(i, StepItem)]
        return (max(nums) + 1) if nums else 1

    def _clamp(self, p: QPointF) -> QPointF:
        r = self._work_rect()
        return QPointF(min(max(p.x(), r.left()), r.right()), min(max(p.y(), r.top()), r.bottom()))

    # --- mouse ---------------------------------------------------------
    def sample_color(self, pos: QPointF) -> QColor | None:
        """Cor da imagem (camadas, sem anotações) no ponto — usada pelo conta-gotas."""
        for layer in reversed(self.layers()):
            local = pos - layer.pos() - layer.box.topLeft()
            x, y = int(local.x()), int(local.y())
            if 0 <= x < layer.image.width() and 0 <= y < layer.image.height():
                c = QColor(layer.image.pixel(x, y))
                c.setAlpha(255)
                return c
        return None

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(ev)
            return
        if self.picker is not None:
            cb, self.picker = self.picker, None
            c = self.sample_color(ev.scenePos())
            if c is not None:
                cb(c)
            else:
                cb(None)
            ev.accept()
            return
        self._pending_hit = None
        if self.tool == "select":
            self._pick_and_raise(ev.scenePos())
            super().mousePressEvent(ev)
            self._snap = {it: it.snapshot() for it in self.selectedItems() if isinstance(it, AnnotMixin)
                          and not isinstance(it, CropItem)}
            return
        if self.tool in ("resize", "background"):
            ov = self._overlay
            if ov is not None and ov.handle_at(ov.mapFromScene(ev.scenePos())):
                super().mousePressEvent(ev)
            else:
                ev.accept()
            return
        pos = self._clamp(ev.scenePos())

        # Ferramenta de desenho ativa: clicar em cima de um desenho do mesmo tipo (ex.: uma seta com a ferramenta
        # seta) o seleciona, sem precisar trocar para "Selecionar".
        if self.tool not in ("ocr", "crop"):
            hit = self._same_kind_at(ev.scenePos())
            if hit is not None and not hit.isSelected():
                self.clearSelection()
                hit.setSelected(True)
                super().mousePressEvent(ev)
                self._snap = {it: it.snapshot() for it in self.selectedItems() if self._is_annotation(it)}
                return

        # O item selecionado continua editável (mover/alças). Clicar fora dele limpa a seleção;
        # com a ferramenta numeral, o mesmo clique já cria o próximo número.
        if self.tool not in ("ocr", "crop"):
            sel = [i for i in self.selectedItems() if self._is_annotation(i)]
            if sel:
                if any(i in sel for i in self.items(ev.scenePos())):
                    super().mousePressEvent(ev)
                    self._snap = {it: it.snapshot() for it in sel}
                    return
                self.clearSelection()
                if self.tool == "text":
                    ev.accept()
                    return

        if self.tool == "ocr":
            marker = RegionMarker(QRectF(pos, pos))
            self.addItem(marker)
            self._drawing, self._start = marker, pos
            ev.accept()
            return

        if self.tool == "crop":
            if self._crop is not None and self._crop.handle_at(self._crop.mapFromScene(pos)):
                super().mousePressEvent(ev)
                return
            self.cancel_crop()
            self._crop = CropItem(QRectF(pos, pos))
            self.addItem(self._crop)
            self._crop.setSelected(True)
            self._drawing, self._start = self._crop, pos
            ev.accept()
            return

        self.clearSelection()
        if self.tool not in ("text", "step"):
            # clique (sem arrastar) em outro tipo de desenho: seleciona-o e troca para a ferramenta dele
            for it in self.items(ev.scenePos()):
                if self._is_annotation(it) and getattr(it, "kind", None) not in (None, self.tool):
                    self._pending_hit = it
                    break
        if self.tool == "text":
            self._add_text(pos)
            ev.accept()
            return
        if self.tool == "step":
            item = StepItem(self.next_step_number(), self.opt_color, self.opt_step_size, self.opt_step_border)
            item.setPos(pos)
            self.addItem(item)
            self.undo_stack.push(AddCommand(self, item, tr("Adicionar marcador")))
            item.setSelected(True)           # fica selecionado (tamanho, cor e borda ajustáveis) até o próximo clique
            ev.accept()
            return

        item: QGraphicsItem
        if self.tool == "zoom":
            item = ZoomItem(QRectF(pos, pos), self.opt_color, min(self.opt_width, 6), self.opt_zoom)
            item.arrow = self.opt_zoom_arrow
        elif self.tool in RECT_KINDS:
            color = (QColor("#000000") if self.opt_color == QColor("#ff3b30") else QColor(self.opt_color)) \
                if self.tool == "redact" else (
                QColor("#ffd60a") if self.tool == "highlight" and self.opt_color == QColor("#ff3b30") else self.opt_color)
            fill = self.opt_fill if self.tool in ("rect", "ellipse") else None
            width = self.opt_width
            if self.tool == "redact":
                fill, width = self.opt_redact_border, self.opt_redact_width
            item = ShapeItem(self.tool, QRectF(pos, pos), color, width, self.opt_strength, fill)
        elif self.tool in ("line", "arrow"):
            item = LineItem(self.tool, pos, pos, self.opt_color, self.opt_width)
        elif self.tool == "pen":
            item = PenItem(pos, self.opt_color, self.opt_width)
        else:
            super().mousePressEvent(ev)
            return
        self.addItem(item)
        self._drawing, self._start = item, pos
        ev.accept()

    def mouseMoveEvent(self, ev):
        item = self._drawing
        if item is None:
            super().mouseMoveEvent(ev)
            return
        pos = self._clamp(ev.scenePos())
        shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if isinstance(item, ShapeItem):  # inclui CropItem
            end = pos
            if shift and item.kind in ("rect", "ellipse", "highlight", "crop", "zoom"):
                d = max(abs(pos.x() - self._start.x()), abs(pos.y() - self._start.y()))
                end = QPointF(self._start.x() + math.copysign(d, pos.x() - self._start.x()),
                              self._start.y() + math.copysign(d, pos.y() - self._start.y()))
                end = self._clamp(end)
            item.setRect(QRectF(self._start, end).normalized())
        elif isinstance(item, LineItem):
            end = pos
            if shift:
                dx, dy = pos.x() - self._start.x(), pos.y() - self._start.y()
                ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
                length = math.hypot(dx, dy)
                end = self._clamp(QPointF(self._start.x() + length * math.cos(ang),
                                          self._start.y() + length * math.sin(ang)))
            item.set_points(self._start, end)
        elif isinstance(item, PenItem):
            item.add_point(pos)
        ev.accept()

    def mouseReleaseEvent(self, ev):
        item = self._drawing
        if item is not None:
            self._drawing = None
            if isinstance(item, RegionMarker):
                r = item.rect().normalized()
                self.removeItem(item)
                if r.width() >= 6 and r.height() >= 6:
                    self.ocr_requested.emit(r)
                ev.accept()
                return
            if isinstance(item, CropItem):
                if item.rect().width() < 4 or item.rect().height() < 4:
                    self.cancel_crop()
                ev.accept()
                return
            ok = True
            if isinstance(item, ShapeItem):
                ok = item.rect().width() >= 3 and item.rect().height() >= 3
            elif isinstance(item, LineItem):
                ok = QLineF(item.p1, item.p2).length() >= 3
            elif isinstance(item, PenItem):
                ok = len(item.points) >= 3 or self._pending_hit is None
            if not ok:
                self.removeItem(item)
                hit, self._pending_hit = self._pending_hit, None
                if hit is not None and hit.scene() is self:
                    self.clearSelection()
                    hit.setSelected(True)
                    self.tool_change_requested.emit(hit.kind)
            else:
                if isinstance(item, ZoomItem):
                    item.finalize(self.canvas_rect(), self.opt_zoom)
                self.undo_stack.push(AddCommand(self, item, tr("Adicionar")))
                item.setSelected(True)      # fica selecionado: opções (intensidade, cor...) já valem para ele
            ev.accept()
            return

        super().mouseReleaseEvent(ev)
        if self._snap:
            changes = []
            for it, old in self._snap.items():
                new = it.snapshot()
                if new != old:
                    changes.append((it, old, new))
            if changes:
                self.undo_stack.beginMacro("Mover/redimensionar")
                for it, old, new in changes:
                    self.undo_stack.push(StateCommand(it, old, new))
                self.undo_stack.endMacro()
        self._snap = None

    def _same_kind_at(self, pos: QPointF):
        """Desenho do mesmo tipo da ferramenta ativa sob o clique (o mais acima), ou None."""
        tool = self.tool
        for it in self.items(pos):
            if self._is_annotation(it) and getattr(it, "kind", None) == tool:
                return it
        return None

    # --- ordem das camadas ----------------------------------------------
    @staticmethod
    def _is_annotation(it) -> bool:
        return isinstance(it, AnnotMixin) and not isinstance(it, (ImageLayer, CropItem))

    @staticmethod
    def _is_thin(it) -> bool:
        """Itens de traço fino: têm área de clique pequena e ficam 'escondidos' sob caixas de texto."""
        if isinstance(it, (LineItem, PenItem, StepItem)):
            return True
        return isinstance(it, ShapeItem) and it.kind in ("rect", "ellipse") and it.fill is None

    def _max_z(self) -> float:
        zs = [i.zValue() for i in self.items() if self._is_annotation(i)]
        return max(zs) if zs else 0.0

    def _pick_and_raise(self, pos: QPointF):
        """Escolhe o item sob o clique e o traz para a frente (ele vira a 'camada ativa').

        Se um texto cobre uma seta/linha, o clique exatamente sobre o traço fino seleciona o traço.
        """
        stack = [i for i in self.items(pos) if self._is_annotation(i)]
        if not stack:
            return
        chosen = next((i for i in stack if i.isSelected()), None)
        if chosen is None:
            chosen = stack[0]
            if isinstance(chosen, TextItem) and not chosen.editing:
                chosen = next((i for i in stack[1:] if self._is_thin(i)), chosen)
        if chosen.zValue() < self._max_z() or (chosen is not stack[0] and chosen.zValue() <= stack[0].zValue()):
            chosen.setZValue(min(self._max_z() + 1, 4000))

    # --- texto ---------------------------------------------------------
    def _add_text(self, pos: QPointF):
        item = TextItem(tr("Texto"), self.opt_color, self.opt_font, self.opt_text_bg)
        item.setPos(pos)
        self.addItem(item)
        item.start_edit()

    def text_finished(self, item: TextItem):
        if not item.toPlainText().strip():
            if item.scene() is self:
                self.removeItem(item)
            if item.committed:
                self.undo_stack.push(RemoveCommand(self, item))
            return
        if not item.committed:
            item.committed = True
            self.undo_stack.push(AddCommand(self, item, tr("Adicionar texto")))

    # --- teclado / edição ----------------------------------------------
    def keyPressEvent(self, ev):
        fi = self.focusItem()
        if isinstance(fi, TextItem) and fi.editing:
            super().keyPressEvent(ev)
            return
        if ev.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def delete_selected(self):
        items = [i for i in self.selectedItems() if isinstance(i, AnnotMixin) and not isinstance(i, CropItem)]
        layers_left = len(self.layers())
        allowed = []
        for it in items:
            if isinstance(it, ImageLayer):
                if layers_left <= 1:
                    continue          # sempre resta pelo menos uma imagem
                layers_left -= 1
            allowed.append(it)
        if not allowed:
            return
        self.undo_stack.beginMacro("Remover")
        for it in allowed:
            self.undo_stack.push(RemoveCommand(self, it))
        self.undo_stack.endMacro()

    def apply_style_to_selection(self, **kwargs):
        items = [i for i in self.selectedItems() if isinstance(i, AnnotMixin) and not isinstance(i, CropItem)]
        changes = []
        for it in items:
            old = it.snapshot()
            it.apply_style(**kwargs)
            new = it.snapshot()
            if new != old:
                changes.append((it, old, new))
        if changes:
            self.undo_stack.beginMacro(tr("Alterar estilo"))
            for it, old, new in changes:
                self.undo_stack.push(StateCommand(it, old, new, tr("Estilo")))
            self.undo_stack.endMacro()

    # --- camadas com desfazer ------------------------------------------
    def insert_image(self, image: QImage, label: str = tr("Adicionar captura")) -> ImageLayer:
        """Adiciona uma imagem como nova camada (à direita das atuais), com desfazer."""
        layer = ImageLayer(image)
        layer.setZValue(LAYER_Z0 + len(self.layers()))
        layer.setPos(self.next_layer_pos() if self.layers() else QPointF(0, 0))
        self.undo_stack.push(AddCommand(self, layer, label, reset_clip=True))
        return layer

    def rotate_content(self, degrees: int) -> None:
        """Gira a imagem inteira (camadas + anotações). O conteúdo é achatado numa única camada (com desfazer);
        o fundo decorativo e a escala de saída são mantidos/voltam ao tamanho original."""
        self._transform_content(QTransform().rotate(degrees), tr("Girar a imagem"))

    def flip_content(self, horizontal: bool) -> None:
        """Espelha a imagem inteira (camadas + anotações), na horizontal ou na vertical."""
        self._transform_content(QTransform().scale(-1 if horizontal else 1, 1 if horizontal else -1),
                                tr("Espelhar a imagem"))

    def _transform_content(self, tf: QTransform, label: str) -> None:
        self.cancel_crop()
        fi = self.focusItem()
        if fi is not None:
            fi.clearFocus()
        self.clearSelection()
        self.refresh_zooms()
        canvas = self.canvas_rect()
        cw, ch = max(1, int(canvas.width())), max(1, int(canvas.height()))
        flat = QImage(cw, ch, QImage.Format.Format_ARGB32_Premultiplied)
        flat.fill(Qt.GlobalColor.transparent)
        self._exporting = True
        try:
            p = QPainter(flat)
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                             | QPainter.RenderHint.SmoothPixmapTransform)
            self.render(p, QRectF(0, 0, cw, ch), canvas)
            p.end()
        finally:
            self._exporting = False
        rotated = flat.transformed(tf, Qt.TransformationMode.SmoothTransformation)
        olds = [i for i in self.items() if isinstance(i, AnnotMixin) and not isinstance(i, CropItem)]
        self.undo_stack.beginMacro(label)
        for it in olds:
            self.undo_stack.push(RemoveCommand(self, it))
        layer = ImageLayer(rotated)
        layer.setZValue(LAYER_Z0)
        layer.setPos(0, 0)
        self.undo_stack.push(AddCommand(self, layer, label, reset_clip=True))
        self.undo_stack.endMacro()
        self.export_scale, self.export_stretch = 1.0, 1.0
        self.set_export_scale(1.0)
        self.canvas_changed.emit()

    # --- recorte (não destrutivo) --------------------------------------
    @property
    def crop_active(self) -> bool:
        return self._crop is not None

    def cancel_crop(self):
        if self._crop is not None:
            if self._crop.scene() is self:
                self.removeItem(self._crop)
            self._crop = None

    def apply_crop(self) -> bool:
        if self._crop is None:
            return False
        canvas = self.canvas_rect().toAlignedRect()
        r = self._crop.rect().normalized().toAlignedRect().intersected(canvas)
        self.cancel_crop()
        if r.width() < 2 or r.height() < 2 or r == canvas:
            return False
        self.clearSelection()
        self.undo_stack.push(AttrCommand(self, "clip", self.clip, QRectF(r), tr("Recortar")))
        return True

    # --- fundo e tamanho -----------------------------------------------
    def preview_background(self, bs: BackgroundSettings):
        self.background = bs
        self.refresh_canvas()

    def commit_background(self, old: BackgroundSettings, new: BackgroundSettings):
        self.background = old            # o comando aplica o novo valor
        self.undo_stack.push(AttrCommand(self, "background", old.copy(), new.copy(), tr("Fundo")))

    def set_export_scale(self, scale: float):
        scale = min(max(scale, 0.05), 8.0)
        if abs(scale - self.export_scale) > 1e-6 or abs(self.export_stretch - 1.0) > 1e-6:
            self.undo_stack.push(SizeCommand(self, (self.export_scale, self.export_stretch), (scale, 1.0)))

    def set_output_size(self, width: float, height: float, base: QRectF | None = None):
        """Define o tamanho final em pixels (escala e esticamento) a partir de largura/altura desejadas."""
        base = base or self.frame_rect()
        bw, bh = max(1.0, base.width()), max(1.0, base.height())
        sx = min(max(width / bw, 0.05), 8.0)
        sy = min(max(height / bh, 0.05), 8.0)
        stretch = min(max(sy / sx, 0.05), 20.0)
        if abs(stretch - 1.0) < 0.004:
            stretch = 1.0
        new = (sx, stretch)
        if abs(new[0] - self.export_scale) > 1e-6 or abs(new[1] - self.export_stretch) > 1e-6:
            self.undo_stack.push(SizeCommand(self, (self.export_scale, self.export_stretch), new))

    def render_scene_rect(self, rect: QRectF, min_side: int = 0) -> QImage:
        """Renderiza uma região da composição (camadas + anotações, sem fundo) — usada pelo OCR."""
        self.cancel_crop()
        fi = self.focusItem()
        if fi is not None:
            fi.clearFocus()
        self.clearSelection()
        self.refresh_zooms()
        r = rect.intersected(self.canvas_rect())
        if r.width() < 1 or r.height() < 1:
            return QImage()
        w, h = max(1, int(r.width())), max(1, int(r.height()))
        k = 1
        if min_side and max(w, h) < min_side:
            k = min(4, max(1, round(min_side / max(w, h))))
        img = QImage(w * k, h * k, QImage.Format.Format_RGB32)
        img.fill(QColor("white"))
        self._exporting = True
        try:
            p = QPainter(img)
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                             | QPainter.RenderHint.SmoothPixmapTransform)
            self.render(p, QRectF(0, 0, w * k, h * k), r)
            p.end()
        finally:
            self._exporting = False
        return img

    # --- exportação ----------------------------------------------------
    def render_image(self) -> QImage:
        """Imagem final: camadas + anotações + fundo, já achatada e na escala de exportação."""
        self.cancel_crop()
        fi = self.focusItem()
        if fi is not None:
            fi.clearFocus()
        self.clearSelection()
        self.refresh_zooms()
        canvas = self.canvas_rect()
        cw, ch = int(canvas.width()), int(canvas.height())
        bs = self.background
        hints = (QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                 | QPainter.RenderHint.SmoothPixmapTransform)

        inner = QImage(cw, ch, QImage.Format.Format_ARGB32_Premultiplied)
        inner.fill(Qt.GlobalColor.transparent if bs.enabled else QColor("white"))
        self._exporting = True
        try:
            p = QPainter(inner)
            p.setRenderHints(hints)
            self.render(p, QRectF(0, 0, cw, ch), canvas)
            p.end()
        finally:
            self._exporting = False

        if bs.enabled:
            pad = bs.padding
            out = QImage(cw + 2 * pad, ch + 2 * pad, QImage.Format.Format_ARGB32_Premultiplied)
            out.fill(Qt.GlobalColor.transparent)
            p = QPainter(out)
            p.setRenderHints(hints)
            frame = QRectF(0, 0, out.width(), out.height())
            if not bs.transparent:
                if bs.outer_radius > 0:
                    fp = QPainterPath()
                    fp.addRoundedRect(frame, bs.outer_radius, bs.outer_radius)
                    p.fillPath(fp, bs.brush(frame))
                else:
                    p.fillRect(frame, bs.brush(frame))
            inner_rect = QRectF(pad, pad, cw, ch)
            if bs.shadow:
                paint_shadow(p, inner_rect, bs.radius, bs.shadow_blur, bs.shadow_dir)
            path = QPainterPath()
            path.addRoundedRect(inner_rect, bs.radius, bs.radius)
            p.setClipPath(path)
            p.drawImage(QPointF(pad, pad), inner)
            p.end()
            result = out if (bs.transparent or bs.outer_radius > 0) else out.convertToFormat(QImage.Format.Format_RGB32)
        else:
            result = inner.convertToFormat(QImage.Format.Format_RGB32)

        w, h = self.output_size()
        if (w, h) != (result.width(), result.height()):
            result = result.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return result
