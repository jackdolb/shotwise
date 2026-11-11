"""Gravação de GIF: captura por timer, barra de controle, moldura e janela de corte/salvamento."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

from .audiocap import default_srcs
from .gifenc import encode_gif
from .i18n import tr
from .winutil import draw_cursor, grab_cursor, mouse_pressed

log = logging.getLogger("shotwise")

MAX_BYTES = 600 * 1024 * 1024      # limite de memória dos quadros (a gravação para sozinha)
ACCENT_REC = QColor("#e5484d")


def fmt_time(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


class GifRecorder(QObject):
    """Guarda quadros (só quando a imagem muda) com o instante de cada um; a duração sai da diferença."""

    tick = Signal(int, int)          # tempo decorrido (ms), quadros guardados
    stopped = Signal(str)            # motivo: "user" | "time" | "memory"

    def __init__(self, grab: Callable[[], QImage], fps: int, max_seconds: int, max_width: int, parent=None,
                 max_bytes: int = MAX_BYTES, audio=None):
        super().__init__(parent)
        self.max_bytes = max_bytes
        self.audio = audio                     # AudioCapture opcional (só no vídeo MP4)
        self.audio_pcm = b""                   # PCM 48 kHz estéreo s16 da gravação inteira
        self._grab = grab
        self.fps = max(1, fps)
        self.max_ms = max_seconds * 1000
        self.max_width = max_width
        self.images: list[QImage] = []
        self.starts: list[int] = []
        self.end_ms = 0
        self._bytes = 0
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(round(1000 / self.fps))
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._on_tick)
        self.running = False
        self._cancelled = False

    def cancel(self) -> None:
        """Descarta a gravação sem emitir ``stopped``."""
        self._cancelled = True
        self.running = False
        self._timer.stop()
        if self.audio is not None:
            self.audio.cancel()

    def start(self) -> None:
        if self._cancelled:
            return
        self.running = True
        if self.audio is not None:
            self.audio.start()                 # abre os dispositivos antes de zerar os relógios
            self.audio.begin()
        self._clock.start()
        self._on_tick()
        self._timer.start()

    def _prepare(self, img: QImage) -> QImage:
        img.setDevicePixelRatio(1.0)
        if img.width() > self.max_width:
            img = img.scaledToWidth(self.max_width, Qt.TransformationMode.SmoothTransformation)
        return img.convertToFormat(QImage.Format.Format_RGB888)

    def _on_tick(self) -> None:
        if not self.running:
            return
        t = self._clock.elapsed()
        if t >= self.max_ms:
            self.stop("time")
            return
        try:
            img = self._prepare(self._grab())
        except Exception:  # noqa: BLE001 - um quadro ruim não derruba a gravação
            log.exception("gif: falha ao capturar quadro")
            return
        if img.isNull():
            return
        if not self.images or img != self.images[-1]:
            self.images.append(img)
            self.starts.append(t)
            self._bytes += img.sizeInBytes()
        self.tick.emit(t, len(self.images))
        if self._bytes > self.max_bytes:
            self.stop("memory")

    def stop(self, reason: str = "user") -> None:
        if not self.running:
            return
        self.running = False
        self._timer.stop()
        self.end_ms = self._clock.elapsed()
        if self.audio is not None:
            self.audio_pcm = self.audio.stop(self.end_ms)
        self.stopped.emit(reason)

    def durations(self) -> list[int]:
        ends = self.starts[1:] + [self.end_ms]
        return [max(20, e - s) for s, e in zip(self.starts, ends)]


class FrameBorder(QWidget):
    """Moldura vermelha ao redor da área gravada, na faixa de fora (não aparece no GIF) e sem capturar o mouse."""

    PAD = 3

    def __init__(self, region: QRect):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(region.adjusted(-self.PAD, -self.PAD, self.PAD, self.PAD))

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setPen(QPen(ACCENT_REC, self.PAD))
        p.drawRect(QRect(0, 0, self.width(), self.height()).adjusted(1, 1, -1, -1))


class RecordingBar(QWidget):
    """Barra pequena com tempo, Parar e Cancelar; fica fora da área gravada e fora das capturas."""

    stop_clicked = Signal()
    cancel_clicked = Signal()

    def __init__(self, region: QRect, screen_geo: QRect, max_ms: int):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setObjectName("recbar")
        self.setStyleSheet("#recbar{background:#202329;border:1px solid #3a3f49;border-radius:8px;}"
                           "QLabel{color:#e6e8ec;}"
                           "QPushButton{background:#2e323a;color:#e6e8ec;border:1px solid #444a55;border-radius:6px;"
                           "padding:4px 12px;} QPushButton:hover{background:#383d47;}"
                           "QPushButton#stop{background:#e5484d;border-color:#e5484d;color:white;}"
                           "QPushButton#stop:hover{background:#ef5b60;}")
        self._max = max_ms
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 8, 6)
        lay.setSpacing(10)
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color:#e5484d;font-size:14px;")
        self.lbl = QLabel(f"{fmt_time(0)} / {fmt_time(max_ms)}")
        self.btn_stop = QPushButton(tr("Parar"))
        self.btn_stop.setObjectName("stop")
        self.btn_cancel = QPushButton(tr("Cancelar"))
        self.btn_stop.clicked.connect(self.stop_clicked)
        self.btn_cancel.clicked.connect(self.cancel_clicked)
        for w in (self.dot, self.lbl, self.btn_stop, self.btn_cancel):
            lay.addWidget(w)
        self.adjustSize()
        self._blink = QTimer(self)
        self._blink.timeout.connect(lambda: self.dot.setVisible(not self.dot.isVisible()))
        self._blink.start(600)
        self.move(self._place(region, screen_geo))

    def _place(self, region: QRect, geo: QRect) -> QPoint:
        w, h = self.width(), self.height()
        x = min(max(region.center().x() - w // 2, geo.left() + 4), geo.right() - w - 4)
        below = region.bottom() + 10
        if below + h <= geo.bottom():
            return QPoint(x, below)
        above = region.top() - h - 10
        if above >= geo.top():
            return QPoint(x, above)
        # a área ocupa a tela toda: fica no canto (a barra é excluída da captura no Windows)
        return QPoint(geo.right() - w - 12, geo.bottom() - h - 12)

    def set_elapsed(self, ms: int) -> None:
        self.lbl.setText(f"{fmt_time(ms)} / {fmt_time(self._max)}")


class _EncodeJob(QThread):
    progress = Signal(int)
    failed = Signal(str)

    def __init__(self, images, durations, path, parent=None):
        super().__init__(parent)
        self._a = (images, durations, path)

    def run(self):
        try:
            encode_gif(*self._a, progress=self.progress.emit)
        except Exception as exc:  # noqa: BLE001
            log.exception("gif: falha ao gravar")
            self.failed.emit(str(exc))


class Timeline(QWidget):
    """Linha do tempo do clipe: eixo em tempo real, faixa selecionada (arraste as pontas) e cabeça de reprodução."""

    range_changed = Signal()
    seeked = Signal(float)               # instante (ms) onde o usuário clicou ou arrastou
    fx_selected = Signal(int)            # faixa de efeito clicada (-1 = clicou no vazio)
    fx_edge = Signal(int, str, int)      # (efeito, "a"/"b", índice do quadro sob o mouse) ao arrastar uma ponta
    fx_drag_begin = Signal()
    fx_drag_end = Signal(int)
    LANE_TOP = 50

    M = 10          # margem lateral
    GRAB = 9        # tolerância (px) para agarrar uma ponta

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fx_rows: list[int] = []
        self.setFixedHeight(74)
        self.setMouseTracking(True)
        self.fx: list[tuple[str, int, int]] = []     # (tipo, quadro inicial, quadro final)
        self.fx_sel = -1
        self._fx_drag: tuple[int, str] | None = None
        self.starts: list[int] = [0]
        self.durations: list[int] = [1]
        self.total = 1
        self.a = self.b = self.cur = 0
        self.pos = 0.0                       # cabeça de reprodução (ms): anda dentro de um quadro longo também
        self.cuts: list[int] = []            # índices de quadro onde começa um novo segmento
        self._drag: str | None = None

    def set_clip(self, durations: list[int], cuts=()) -> None:
        self.durations = list(durations) or [1]
        self.cuts = sorted({c for c in cuts if 0 < c < len(self.durations)})
        self.starts, t = [], 0
        for d in self.durations:
            self.starts.append(t)
            t += d
        self.total = max(1, t)
        self.a, self.b, self.cur, self.pos = 0, len(self.durations) - 1, 0, 0.0
        self.update()

    def set_selection(self, a: int, b: int) -> None:
        n = len(self.durations)
        a, b = sorted((min(max(a, 0), n - 1), min(max(b, 0), n - 1)))
        self.a, self.b = a, b
        self.update()
        self.range_changed.emit()

    def is_full(self) -> bool:
        return self.a == 0 and self.b == len(self.durations) - 1

    def segment_of(self, i: int) -> tuple[int, int]:
        return segment_bounds(self.cuts, len(self.durations), i)

    def _x(self, ms: float) -> float:
        return self.M + ms / self.total * max(1, self.width() - 2 * self.M)

    def _ms_at(self, x: float) -> float:
        ms = (x - self.M) / max(1, self.width() - 2 * self.M) * self.total
        return min(max(ms, 0.0), float(self.total - 1))

    def index_of_ms(self, ms: float) -> int:
        return self._index_at_ms(ms)

    def _index_at(self, x: float) -> int:
        return self._index_at_ms(self._ms_at(x))

    def _index_at_ms(self, ms: float) -> int:
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:                       # último quadro que começa antes de ``ms``
            mid = (lo + hi + 1) // 2
            if self.starts[mid] <= ms:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def _edges(self) -> tuple[float, float]:
        return self._x(self.starts[self.a]), self._x(self.starts[self.b] + self.durations[self.b])

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        accent = pal.highlight().color()
        top, h = 10, self.height() - 20
        track = QRectF(self.M, top, self.width() - 2 * self.M, h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pal.mid().color())
        p.drawRoundedRect(track, 5, 5)
        edges = [0, *self.cuts, len(self.durations)]
        for k in range(len(edges) - 1):                 # segmentos alternam de tom para ficarem visíveis
            if k % 2:
                shade = QColor(pal.text().color())
                shade.setAlpha(28)
                p.setBrush(shade)
                x0 = self._x(self.starts[edges[k]])
                x1 = self._x(self.starts[edges[k + 1] - 1] + self.durations[edges[k + 1] - 1])
                p.drawRect(QRectF(x0, top, max(1.0, x1 - x0), h))
        xa, xb = self._edges()
        fill = QColor(accent)
        fill.setAlpha(110)
        p.setBrush(fill)
        p.drawRect(QRectF(xa, top, max(1.0, xb - xa), h))
        p.setPen(QPen(accent, 2))
        p.drawLine(QPointF(xa, top), QPointF(xb, top))
        p.drawLine(QPointF(xa, top + h), QPointF(xb, top + h))
        p.setPen(QPen(pal.text().color(), 1.5))
        for c in self.cuts:                             # divisões entre segmentos
            cx = self._x(self.starts[c])
            p.drawLine(QPointF(cx, top - 2), QPointF(cx, top + h + 2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        for x in (xa, xb):
            p.drawRoundedRect(QRectF(x - 4, top - 5, 8, h + 10), 3, 3)
        lane_y, lane_h = self.LANE_TOP, 18
        colors = {"zoom": QColor("#4c8dff"), "highlight": QColor("#f0b400"), "hide": QColor("#e5484d"), "text": QColor("#34c759")}
        names = {"zoom": tr("Zoom"), "highlight": tr("Destaque"), "hide": tr("Ocultar"), "text": tr("Texto")}
        for k, (kind, fa, fb) in enumerate(self.fx):
            x0 = self._x(self.starts[fa])
            x1 = self._x(self.starts[fb] + self.durations[fb])
            row = self.fx_rows[k] if k < len(self.fx_rows) else 0
            rect = QRectF(x0, lane_y + row * self.ROW_H, max(6.0, x1 - x0), lane_h)
            col = QColor(colors.get(kind, accent))
            col.setAlpha(230 if k == self.fx_sel else 150)
            p.setPen(QPen(pal.text().color(), 2) if k == self.fx_sel else Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QColor("#101114"))
            p.drawText(rect.adjusted(6, 0, -4, 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                       names.get(kind, kind))
        x = self._x(self.pos)
        p.setPen(QPen(ACCENT_REC, 2))
        p.drawLine(QPointF(x, 3), QPointF(x, self.height() - 3))

    ROW_H = 20

    def set_fx(self, bars: list[tuple[str, int, int]], sel: int) -> None:
        """Efeitos que se sobrepõem no tempo ficam em linhas separadas (empilhados)."""
        self.fx, self.fx_sel = list(bars), sel
        rows: list[int] = []
        ends: list[int] = []                     # último quadro ocupado de cada linha
        for _kind, fa, fb in self.fx:
            for r, e in enumerate(ends):
                if fa > e:
                    ends[r] = fb
                    rows.append(r)
                    break
            else:
                ends.append(fb)
                rows.append(len(ends) - 1)
        self.fx_rows = rows
        self.setFixedHeight(self.LANE_TOP + max(1, len(ends)) * self.ROW_H + 6)
        self.update()

    def _fx_hit(self, x: float, y: float = -1.0) -> tuple[int, str]:
        """Faixa de efeito sob x: (índice, 'a'/'b' se estiver na ponta, 'body' no meio); (-1, '') se nenhuma."""
        for k in range(len(self.fx) - 1, -1, -1):
            _kind, fa, fb = self.fx[k]
            x0, x1 = self._x(self.starts[fa]), self._x(self.starts[fb] + self.durations[fb])
            if y >= 0:
                row = self.fx_rows[k] if k < len(self.fx_rows) else 0
                top = self.LANE_TOP + row * self.ROW_H
                if not (top - 1 <= y <= top + 19):
                    continue
            if x0 - 3 <= x <= max(x1, x0 + 6) + 3:
                if abs(x - x0) <= 6:
                    return k, "a"
                if abs(x - x1) <= 6:
                    return k, "b"
                return k, "body"
        return -1, ""

    def _hit(self, x: float) -> str:
        xa, xb = self._edges()
        if abs(x - xa) <= self.GRAB and abs(x - xa) <= abs(x - xb):
            return "a"
        if abs(x - xb) <= self.GRAB:
            return "b"
        return "seek"

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        x = ev.position().x()
        if ev.position().y() >= self.LANE_TOP - 2:
            k, part = self._fx_hit(x, ev.position().y())
            self.fx_selected.emit(k)
            if k >= 0 and part in ("a", "b"):
                self.fx_drag_begin.emit()
                self._fx_drag = (k, part)
            return
        self._drag = self._hit(x)
        self._press_x = x
        if self._drag != "seek":
            self._armed = True               # só vira arraste de ponta se o mouse se mover; um clique simples seleciona o segmento
            return
        self._armed = False
        self.mouseMoveEvent(ev)

    def mouseMoveEvent(self, ev):
        x = ev.position().x()
        if self._fx_drag is not None:
            self.fx_edge.emit(self._fx_drag[0], self._fx_drag[1], self._index_at(x))
            return
        if self._drag is None and ev.position().y() >= self.LANE_TOP - 2:
            self.setCursor(Qt.CursorShape.SizeHorCursor if self._fx_hit(x, ev.position().y())[1] in ("a", "b") else Qt.CursorShape.ArrowCursor)
            return
        if self._drag is None:
            self.setCursor(Qt.CursorShape.SizeHorCursor if self._hit(x) != "seek" else Qt.CursorShape.ArrowCursor)
            return
        if getattr(self, "_armed", False):
            if abs(x - self._press_x) < 4:
                return
            self._armed = False
        i = self._index_at(x)
        if self._drag == "a":
            self.set_selection(min(i, self.b), self.b)
        elif self._drag == "b":
            self.set_selection(self.a, max(i, self.a))
        else:
            ms = self._ms_at(x)
            if self.cuts:                                # clicar num segmento o seleciona
                self.set_selection(*self.segment_of(i))
            elif not (self.a <= i <= self.b):            # clicar fora da faixa volta à faixa inteira
                self.set_selection(0, len(self.durations) - 1)
            self.cur, self.pos = i, ms
            self.update()
            self.seeked.emit(ms)

    def mouseReleaseEvent(self, ev):
        if self._fx_drag is not None:
            k, self._fx_drag = self._fx_drag[0], None
            self.fx_drag_end.emit(k)
            return
        if getattr(self, "_armed", False) and self._drag in ("a", "b"):
            self._armed = False
            self._drag = "seek"
            self.mouseMoveEvent(ev)          # clique sem arrastar: trata como clique na linha do tempo (seleciona o segmento)
        self._drag = None


# --- cortes (funções puras, testáveis) ----------------------------------------------------------
def segment_bounds(cuts: list[int], n: int, i: int) -> tuple[int, int]:
    """Primeiro e último quadro do segmento que contém o quadro i."""
    edges = [0, *sorted(cuts), n]
    for k in range(len(edges) - 1):
        if edges[k] <= i < edges[k + 1]:
            return edges[k], edges[k + 1] - 1
    return 0, n - 1


def split_clip(images: list[QImage], durations: list[int], cuts: list[int], t_ms: float, srcs: list[int] | None = None):
    """Divide o clipe no instante t_ms. Se cair no meio de um quadro longo, ele é duplicado em dois pedaços
    (a imagem é compartilhada). Devolve (imagens, durações, cortes); sem mudança se t_ms estiver fora do clipe.
    Com ``srcs`` (início de cada quadro no áudio original, em ms) devolve também a lista nova, como 4º item."""
    imgs, durs, cs = list(images), list(durations), set(cuts)
    ss = list(srcs) if srcs is not None else None
    total = sum(durs)

    def out():
        return (imgs, durs, sorted(cs)) if ss is None else (imgs, durs, sorted(cs), ss)
    if t_ms <= 0 or t_ms >= total:
        return out()
    t = 0
    for k, d in enumerate(durs):
        if t <= t_ms < t + d:
            break
        t += d
    off = int(round(t_ms - t))
    if off < 1:
        if k > 0:
            cs.add(k)
    elif d - off < 1:
        if k + 1 < len(durs):
            cs.add(k + 1)
    else:
        imgs.insert(k + 1, imgs[k])
        durs[k:k + 1] = [off, d - off]
        if ss is not None:
            ss.insert(k + 1, ss[k] + off)
        cs = {c + 1 if c > k else c for c in cs}
        cs.add(k + 1)
    return out()


def delete_frames(images: list[QImage], durations: list[int], cuts: list[int], a: int, b: int,
                  srcs: list[int] | None = None):
    """Remove os quadros a..b e junta o que sobrou (sem marcar divisão na emenda)."""
    n_removed = b - a + 1
    imgs, durs = images[:a] + images[b + 1:], durations[:a] + durations[b + 1:]
    cs = {c for c in cuts if c < a} | {c - n_removed for c in cuts if c > b + 1}     # a emenda não vira divisão: as partes se juntam
    if srcs is not None:
        return imgs, durs, sorted(cs), srcs[:a] + srcs[b + 1:]
    return imgs, durs, sorted(cs)


def keep_frames(images: list[QImage], durations: list[int], cuts: list[int], a: int, b: int,
                srcs: list[int] | None = None):
    r = images[a:b + 1], durations[a:b + 1], sorted(c - a for c in cuts if a < c <= b)
    return r if srcs is None else (*r, srcs[a:b + 1])


# --- efeitos nos quadros (funções puras, testáveis) ---------------------------------------------
def fit_aspect(r: QRectF, w: int, h: int) -> QRectF:
    """Expande o retângulo r (em pixels) até ter a proporção w:h, sem sair da imagem w×h."""
    ar = w / h
    cw, ch = r.width(), r.height()
    if cw / max(ch, 1e-6) < ar:
        cw = ch * ar
    else:
        ch = cw / ar
    cw, ch = min(cw, w), min(ch, h)
    cx, cy = r.center().x(), r.center().y()
    x = min(max(cx - cw / 2, 0), w - cw)
    y = min(max(cy - ch / 2, 0), h - ch)
    return QRectF(x, y, cw, ch)


def _smooth(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def refine_range(images: list[QImage], durations: list[int], cuts: list[int], srcs: list[int], a: int, b: int,
                 step_ms: int = 100, max_pieces: int = 80):
    """Quebra os quadros longos de a..b em pedaços curtos (a imagem é compartilhada), para efeitos que variam no tempo
    (zoom) terem resolução mesmo sobre um quadro parado de vários segundos. Devolve (imagens, durações, cortes, srcs, a, b)."""
    span = sum(durations[a:b + 1])
    step = max(step_ms, -(-span // max_pieces))
    imgs, durs, ss, newidx = [], [], [], []
    for i, (im, d, s0) in enumerate(zip(images, durations, srcs)):
        newidx.append(len(imgs))
        if a <= i <= b and d > step:
            n = -(-d // step)
            base, extra = divmod(d, n)
            off = 0
            for k in range(n):
                piece = base + (1 if k < extra else 0)
                imgs.append(im)
                durs.append(piece)
                ss.append(s0 + off)
                off += piece
        else:
            imgs.append(im)
            durs.append(d)
            ss.append(s0)
    new_a = newidx[a]
    new_b = (newidx[b + 1] - 1) if b + 1 < len(newidx) else len(imgs) - 1
    return imgs, durs, sorted(newidx[c] for c in cuts if c < len(newidx)), ss, new_a, new_b


def zoom_factor(i: int, a: int, b: int, ramp: float = 0.25) -> float:
    """0 = imagem inteira, 1 = zoom total. Aproxima no início do trecho, segura e volta no fim."""
    if b <= a:
        return 1.0
    t = (i - a) / (b - a)
    return _smooth(min(t / ramp, (1 - t) / ramp, 1.0))


def apply_zoom(images: list[QImage], a: int, b: int, region: QRectF) -> list[QImage]:
    """Zoom digital nos quadros a..b sobre `region` (coordenadas normalizadas 0..1). O tamanho do quadro não muda."""
    out = list(images)
    for i in range(a, b + 1):
        im = images[i]
        w, h = im.width(), im.height()
        target = fit_aspect(QRectF(region.x() * w, region.y() * h, region.width() * w, region.height() * h), w, h)
        f = zoom_factor(i, a, b)
        r = QRectF(target.x() * f, target.y() * f,
                   w + (target.width() - w) * f, h + (target.height() - h) * f)
        out[i] = im.copy(r.toAlignedRect()).scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation)
    return out


def apply_highlight(images: list[QImage], a: int, b: int, region: QRectF) -> list[QImage]:
    """Escurece tudo fora de `region` (normalizada) nos quadros a..b e contorna a área em amarelo."""
    out = list(images)
    for i in range(a, b + 1):
        im = images[i].convertToFormat(QImage.Format.Format_ARGB32)
        w, h = im.width(), im.height()
        r = QRectF(region.x() * w, region.y() * h, region.width() * w, region.height() * h)
        p = QPainter(im)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dim = QColor(0, 0, 0, 150)
        p.fillRect(QRectF(0, 0, w, r.top()), dim)
        p.fillRect(QRectF(0, r.bottom(), w, h - r.bottom()), dim)
        p.fillRect(QRectF(0, r.top(), r.left(), r.height()), dim)
        p.fillRect(QRectF(r.right(), r.top(), w - r.right(), r.height()), dim)
        p.setPen(QPen(QColor(255, 214, 0), max(2, round(min(w, h) / 200))))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 4, 4)
        p.end()
        out[i] = im
    return out


def apply_crop(images: list[QImage], region: QRectF) -> list[QImage]:
    """Recorta todos os quadros para `region` (normalizada)."""
    out = []
    for im in images:
        w, h = im.width(), im.height()
        r = QRectF(region.x() * w, region.y() * h, region.width() * w, region.height() * h).toAlignedRect()
        out.append(im.copy(r.intersected(QRect(0, 0, w, h))))
    return out


def zoom_frame(im: QImage, region: QRectF, f: float) -> QImage:
    """Um quadro com zoom digital sobre ``region`` (normalizada); f: 0 = inteiro, 1 = zoom total. Tamanho não muda."""
    w, h = im.width(), im.height()
    target = fit_aspect(QRectF(region.x() * w, region.y() * h, region.width() * w, region.height() * h), w, h)
    r = QRectF(target.x() * f, target.y() * f, w + (target.width() - w) * f, h + (target.height() - h) * f)
    return im.copy(r.toAlignedRect()).scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def highlight_frame(im: QImage, region: QRectF) -> QImage:
    out = apply_highlight([im], 0, 0, region)
    return out[0]


def hide_frame(im: QImage, region: QRectF) -> QImage:
    """Pixeliza forte a área marcada (esconde dados sensíveis); o resto do quadro fica igual."""
    out = im.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = out.width(), out.height()
    r = QRectF(region.x() * w, region.y() * h, region.width() * w, region.height() * h).toAlignedRect().intersected(QRect(0, 0, w, h))
    if r.width() < 2 or r.height() < 2:
        return out
    part = out.copy(r)
    small = part.scaled(max(1, r.width() // 14), max(1, r.height() // 14), Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.FastTransformation)
    big = small.scaled(r.width(), r.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
    p = QPainter(out)
    p.drawImage(r.topLeft(), big)
    p.end()
    return out


FX_KINDS = ("zoom", "highlight", "hide", "text")


@dataclass
class Effect:
    """Efeito com início/fim no tempo ORIGINAL do vídeo (por isso sobrevive a cortes e divisões) e área própria."""
    kind: str
    s0: int
    s1: int
    region: QRectF
    text: str = ""


def text_frame(im: QImage, region: QRectF, text: str) -> QImage:
    """Escreve ``text`` dentro da área marcada (letras brancas sobre faixa escura; o tamanho se ajusta à área)."""
    from PySide6.QtGui import QFont, QFontMetrics
    out = im.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = out.width(), out.height()
    r = QRectF(region.x() * w, region.y() * h, region.width() * w, region.height() * h)
    if r.width() < 8 or r.height() < 8 or not text.strip():
        return out
    flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
    inner = r.adjusted(8, 4, -8, -4)
    font = QFont()
    size = max(8, int(inner.height()))
    while size > 8:
        font.setPixelSize(size)
        br = QFontMetrics(font).boundingRect(inner.toRect(), flags, text)
        if br.width() <= inner.width() and br.height() <= inner.height():
            break
        size -= 2
    font.setPixelSize(size)
    font.setBold(True)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 170))
    p.drawRoundedRect(r, 8, 8)
    p.setFont(font)
    p.setPen(QColor("#ffffff"))
    p.drawText(inner, flags, text)
    p.end()
    return out


def remap_region(r: QRectF, mode: str, arg=None) -> QRectF | None:
    """Acompanha a área de um efeito quando o vídeo é girado ('rot', ±90) ou recortado ('crop', retângulo normalizado)."""
    if mode == "rot":
        if arg > 0:
            return QRectF(1 - r.y() - r.height(), r.x(), r.height(), r.width())
        return QRectF(r.y(), 1 - r.x() - r.width(), r.height(), r.width())
    c: QRectF = arg
    n = QRectF((r.x() - c.x()) / c.width(), (r.y() - c.y()) / c.height(), r.width() / c.width(), r.height() / c.height())
    n = n.intersected(QRectF(0, 0, 1, 1))
    return n if n.width() > 0.01 and n.height() > 0.01 else None


class RegionLabel(QLabel):
    """Pré-visualização em que se arrasta um retângulo para marcar uma área (usada por zoom, destaque e recorte)."""
    region_changed = Signal()

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._p0: QPoint | None = None
        self._rect: QRect | None = None
        self.drag_enabled = True               # só marca áreas quando uma ferramenta de efeito está ativa

    def _image_rect(self) -> QRect:
        pm = self.pixmap()
        if pm is None or pm.isNull():
            return QRect()
        sz = pm.deviceIndependentSize().toSize()
        return QRect((self.width() - sz.width()) // 2, (self.height() - sz.height()) // 2, sz.width(), sz.height())

    def region(self) -> QRectF | None:
        """Área marcada em coordenadas normalizadas (0..1) da imagem, ou None."""
        ir = self._image_rect()
        if self._rect is None or ir.isEmpty():
            return None
        r = self._rect.intersected(ir)
        if r.width() < 6 or r.height() < 6:
            return None
        return QRectF((r.x() - ir.x()) / ir.width(), (r.y() - ir.y()) / ir.height(),
                      r.width() / ir.width(), r.height() / ir.height())

    def set_region(self, norm: QRectF | None):
        ir = self._image_rect()
        if norm is None or ir.isEmpty():
            self._rect = None
        else:
            self._rect = QRectF(ir.x() + norm.x() * ir.width(), ir.y() + norm.y() * ir.height(),
                                norm.width() * ir.width(), norm.height() * ir.height()).toAlignedRect()
        self.update()
        self.region_changed.emit()

    def clear_region(self):
        self.set_region(None)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self.drag_enabled:
            self._p0 = ev.position().toPoint()
            self._rect = QRect(self._p0, self._p0)
            self.update()

    def mouseMoveEvent(self, ev):
        if self._p0 is not None:
            self._rect = QRect(self._p0, ev.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, ev):
        if self._p0 is not None:
            self._p0 = None
            self.region_changed.emit()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._rect is not None:
            p = QPainter(self)
            p.setPen(QPen(QColor(255, 214, 0), 2, Qt.PenStyle.DashLine))
            p.setBrush(QColor(255, 214, 0, 40))
            p.drawRect(self._rect)
            p.end()


class GifPreviewDialog(QDialog):
    """Revisa a gravação: reproduz em laço, seleciona um trecho, mantém só a seleção ou apaga a seleção, e salva."""

    saved = Signal(str)

    def __init__(self, images: list[QImage], durations: list[int], default_path: Callable[[], str], parent=None,
                 kind: str = "gif", audio: bytes = b""):
        super().__init__(parent)
        self.kind = kind                       # "gif" | "mp4"
        self.audio = audio                     # PCM 48 kHz estéreo s16 da gravação original (vazio = sem som)
        self.setWindowTitle(tr("Gravação de vídeo (MP4)") if kind == "mp4" else tr("Gravação de GIF"))
        self.images, self.durations = list(images), list(durations)
        self.srcs: list[int] = default_srcs(self.durations)    # início de cada quadro no áudio original (ms)
        self._history: list[tuple] = []
        self.effects: list[Effect] = []        # zoom/destaque/ocultar: editáveis, aplicados só na pré-visualização e ao salvar
        self._sel_fx: int | None = None
        self._loading_region = False
        self._fx_cache: dict = {}
        self.cuts: list[int] = []
        self._at_ms = 0.0                      # posição de "Dividir em" (a cabeça de reprodução, ou um tempo digitado)
        self._sel_ms = (0.0, 0.0)              # tempos exatos da faixa (digitados ou da seleção)
        self._typing = False
        self._default_path = default_path
        self._cur = 0
        self._pos_ms = 0.0                     # cabeça de reprodução (ms)
        self._play_base = 0.0
        self._clock = QElapsedTimer()
        self._shown = -1
        self._playing = False
        self._job: _EncodeJob | None = None

        self.view = RegionLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.view.setMinimumSize(320, 200)
        self.view.setStyleSheet("background:#14161a;border-radius:6px;")
        self.timeline = Timeline()
        self.timeline.range_changed.connect(self._range_changed)
        self.timeline.seeked.connect(self._on_seek)
        self.timeline.fx_selected.connect(self._fx_select)
        self.timeline.fx_drag_begin.connect(self._push_history)
        self.timeline.fx_edge.connect(self._fx_edge)
        self.timeline.fx_drag_end.connect(self._fx_edge_done)
        self.info = QLabel()
        self.info.setStyleSheet("color:gray;")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.hide()

        from PySide6.QtGui import QKeySequence, QShortcut
        from PySide6.QtWidgets import QDoubleSpinBox
        from .icons import tool_icon, ui_icon

        def icon_btn(icon, tip: str, slot, shortcut: str = "") -> QPushButton:
            b = QPushButton()
            b.setIcon(icon)
            b.setIconSize(QSize(20, 20))
            b.setFixedSize(40, 32)
            b.setToolTip(tip + (f"  ({shortcut})" if shortcut else ""))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False: slot())
            return b

        self.btn_start = icon_btn(ui_icon("skipback"), tr("Voltar ao início da seleção"), self._to_start)
        self.btn_play = icon_btn(ui_icon("pause"), tr("Pausar"), self._toggle, tr("Espaço"))
        self.cb_loop = QCheckBox(tr("Repetir"))
        self.cb_loop.setToolTip(tr("Marcado: o vídeo recomeça sozinho ao chegar ao fim. Desmarcado: toca uma vez e para."))
        self.cb_loop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_stop = icon_btn(ui_icon("stop"), tr("Parar"), self._stop)
        self.btn_cut = icon_btn(ui_icon("trash"), tr("Excluir o segmento selecionado e juntar o que sobrou"), self._delete, "Del")
        self.btn_split = icon_btn(ui_icon("split"), tr("Divide o vídeo no tempo indicado (por padrão, a posição do cursor vermelho)"),
                                  self._split, "S")
        self.btn_merge = icon_btn(ui_icon("merge"), tr("Unificar os blocos: junta todos os segmentos que restaram num só (os apagados já saíram do vídeo)."),
                                  self._merge_all)
        self.btn_keep = icon_btn(ui_icon("keep"), tr("Manter só o segmento selecionado"), self._keep)
        self.btn_undo = icon_btn(ui_icon("undo"), tr("Desfazer"), self._undo, "Ctrl+Z")
        self.btn_rot_l = icon_btn(ui_icon("rotl"), tr("Girar o vídeo 90° para a esquerda"), lambda: self._rotate(-90))
        self.btn_rot_r = icon_btn(ui_icon("rotr"), tr("Girar o vídeo 90° para a direita"), lambda: self._rotate(90))
        self.btn_zoom = icon_btn(tool_icon("zoom"), tr("Zoom: escolha a ferramenta e arraste sobre a imagem para marcar a área; aproxima durante o segmento selecionado e volta ao normal no fim."), lambda: self._arm("zoom"))
        self.btn_hl = icon_btn(tool_icon("highlight"), tr("Destacar: escolha a ferramenta e arraste sobre a imagem; escurece o resto durante o segmento selecionado."), lambda: self._arm("highlight"))
        self.btn_hide = icon_btn(tool_icon("pixelate"), tr("Ocultar: escolha a ferramenta e arraste sobre a imagem; pixeliza a área durante o segmento selecionado."), lambda: self._arm("hide"))
        self.btn_text = icon_btn(tool_icon("text"), tr("Texto: escolha a ferramenta e arraste sobre a imagem; escreve um texto na área durante o segmento selecionado."), lambda: self._arm("text"))
        self._fx_tools = {"zoom": self.btn_zoom, "highlight": self.btn_hl, "hide": self.btn_hide, "text": self.btn_text,
                          "crop": None}
        self._tool: str | None = None
        for b in (self.btn_zoom, self.btn_hl, self.btn_hide, self.btn_text):
            b.setCheckable(True)
        self.btn_fx_del = QPushButton(tr("Remover efeito"))
        self.btn_fx_del.setToolTip(tr("Remove o efeito selecionado na faixa de efeitos (Del)"))
        self.btn_fx_del.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_fx_del.clicked.connect(self._fx_remove)
        self.btn_fx_del.setEnabled(False)
        self.btn_crop = icon_btn(tool_icon("crop"), tr("Recortar o vídeo todo: escolha a ferramenta e arraste sobre a imagem; mantém só a área marcada em TODOS os quadros (Ctrl+Z desfaz)."), lambda: self._arm("crop"))
        self.btn_crop.setCheckable(True)
        self._fx_tools["crop"] = self.btn_crop
        self.view.region_changed.connect(self._region_changed)
        self._hint_default = tr("Arraste sobre a imagem para marcar uma área (para Zoom, Destacar ou Recortar).")
        self.lbl_hint = QLabel(self._hint_default)
        self.lbl_hint.setStyleSheet("color:gray;")
        self.sp_from = QDoubleSpinBox()
        self.sp_to = QDoubleSpinBox()
        self.sp_at = QDoubleSpinBox()
        for sp in (self.sp_from, self.sp_to, self.sp_at):
            sp.setDecimals(2)
            sp.setSingleStep(0.1)
            sp.setSuffix(" s")
            sp.setKeyboardTracking(False)
        self.sp_from.editingFinished.connect(self._times_edited)
        self.sp_to.editingFinished.connect(self._times_edited)
        self.sp_at.editingFinished.connect(self._at_edited)
        self.btn_save = QPushButton(tr("Salvar"))
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._save)
        self.btn_discard = QPushButton(tr("Descartar"))
        self.btn_discard.clicked.connect(self.reject)
        self._play_icons = (ui_icon("play"), ui_icon("pause"))

        lay = QVBoxLayout(self)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.timeline)
        lay.addWidget(self.info)
        lay.addWidget(self.bar)
        tools = QHBoxLayout()
        tools.setSpacing(4)
        for b in (self.btn_start, self.btn_play, self.btn_stop):
            tools.addWidget(b)
        tools.addWidget(self.cb_loop)
        tools.addSpacing(14)
        for b in (self.btn_cut, self.btn_split, self.btn_merge, self.btn_keep, self.btn_undo):
            tools.addWidget(b)
        tools.addSpacing(14)
        for b in (self.btn_rot_l, self.btn_rot_r):
            tools.addWidget(b)
        tools.addSpacing(14)
        for b in (self.btn_zoom, self.btn_hl, self.btn_hide, self.btn_text):
            tools.addWidget(b)
        tools.addWidget(self.btn_fx_del)
        tools.addSpacing(14)
        tools.addWidget(self.btn_crop)
        tools.addStretch(1)
        lay.addLayout(tools)
        times = QHBoxLayout()
        times.addWidget(QLabel(tr("De")))
        times.addWidget(self.sp_from)
        times.addWidget(QLabel(tr("até")))
        times.addWidget(self.sp_to)
        times.addSpacing(16)
        times.addWidget(QLabel(tr("Dividir em")))
        times.addWidget(self.sp_at)
        times.addStretch(1)
        lay.addLayout(times)
        foot = QHBoxLayout()
        foot.addWidget(self.lbl_hint, 1)
        foot.addWidget(self.btn_discard)
        foot.addWidget(self.btn_save)
        lay.addLayout(foot)
        self._update_tool_ui()

        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self._toggle)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._delete_key)
        QShortcut(QKeySequence(Qt.Key.Key_S), self, activated=self._split)

        self._timer = QTimer(self)                  # relógio da reprodução: avança a cabeça pelo tempo real
        self._timer.setInterval(33)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self.timeline.set_clip(self.durations)
        self._refresh()
        self._show_frame(0)                          # começa parado: toca quando o usuário clicar em Reproduzir
        self.resize(max(640, min(980, images[0].width() + 40)), max(460, min(760, images[0].height() + 230)))

    # --- faixa e edição --------------------------------------------------------
    def selection(self) -> tuple[int, int]:
        return self.timeline.a, self.timeline.b

    def set_selection(self, a: int, b: int) -> None:
        self.timeline.set_selection(a, b)

    def selected(self) -> tuple[list[QImage], list[int]]:
        a, b = self.selection()
        return [self.frame_image(i) for i in range(a, b + 1)], self.durations[a:b + 1]

    def selected_srcs(self) -> list[int]:
        a, b = self.selection()
        return self.srcs[a:b + 1]

    def _refresh(self):
        self._range_changed()
        self.btn_play.setIcon(self._play_icons[1 if self._playing else 0])
        self.btn_play.setToolTip((tr("Pausar") if self._playing else tr("Reproduzir")) + "  (" + tr("Espaço") + ")")
        self.btn_undo.setEnabled(bool(self._history))

    def _range_changed(self, *_):
        a, b = self.selection()
        full = self.timeline.is_full()
        t0 = self.timeline.starts[a]
        t1 = self.timeline.starts[b] + self.durations[b]
        im = self.images[a]
        self.info.setText(tr("Seleção {a} a {b}  ({s:.1f} s de {t:.1f} s)  •  {n} quadros distintos  •  {w} × {h} px").format(
            a=f"{t0 / 1000:.1f} s", b=f"{t1 / 1000:.1f} s", s=(t1 - t0) / 1000, t=self.timeline.total / 1000,
            n=b - a + 1, w=im.width(), h=im.height()))
        self.btn_keep.setEnabled(not full)
        self.btn_merge.setEnabled(bool(self.cuts))
        self.btn_cut.setEnabled(not full)
        total = self.timeline.total / 1000
        if not self._typing:
            self._sel_ms = (float(t0), float(t1))
        for sp, v in ((self.sp_from, self._sel_ms[0] / 1000), (self.sp_to, self._sel_ms[1] / 1000)):
            sp.blockSignals(True)
            sp.setRange(0.0, total)
            sp.setValue(v)
            sp.blockSignals(False)
        self.sp_at.setRange(0.0, total)
        if not self._playing and not (a <= self._cur <= b):
            self._show_frame(a)

    # --- efeitos editáveis -----------------------------------------------------
    def _fx_dirty(self):
        self._fx_cache.clear()
        self.timeline.set_fx(self._fx_bars(), -1 if self._sel_fx is None else self._sel_fx)
        self.btn_fx_del.setEnabled(self._sel_fx is not None)

    def _fx_frames(self, fx: Effect) -> list[int]:
        return [i for i, s0 in enumerate(self.srcs) if fx.s0 <= s0 < fx.s1]

    def _fx_bars(self) -> list[tuple[str, int, int]]:
        bars = []
        for fx in self.effects:
            idx = self._fx_frames(fx)
            bars.append((fx.kind, idx[0], idx[-1]) if idx else (fx.kind, 0, 0))
        return bars

    def _prune_effects(self):
        keep = [fx for fx in self.effects if self._fx_frames(fx)]
        if len(keep) != len(self.effects):
            sel = self.effects[self._sel_fx] if self._sel_fx is not None else None
            self.effects = keep
            self._sel_fx = keep.index(sel) if sel in keep else None

    def frame_image(self, i: int, exclude: int | None = None) -> QImage:
        """Quadro i com os efeitos aplicados (``exclude``: índice de um efeito a deixar de fora, para ajustar sua área)."""
        key = (i, exclude)
        hit = self._fx_cache.get(key)
        if hit is not None:
            return hit
        im = self.images[i]
        mid = self.srcs[i] + self.durations[i] / 2
        for k, fx in enumerate(self.effects):
            if k == exclude or not (fx.s0 <= self.srcs[i] < fx.s1):
                continue
            if fx.kind == "zoom":
                t = (mid - fx.s0) / max(1, fx.s1 - fx.s0)
                im = zoom_frame(im, fx.region, _smooth(min(t / 0.25, (1 - t) / 0.25, 1.0)))
            elif fx.kind == "highlight":
                im = highlight_frame(im, fx.region)
            elif fx.kind == "hide":
                im = hide_frame(im, fx.region)
            elif fx.kind == "text":
                im = text_frame(im, fx.region, fx.text)
        if len(self._fx_cache) > 24:
            self._fx_cache.pop(next(iter(self._fx_cache)))
        self._fx_cache[key] = im
        return im

    def _push_history(self):
        self._history.append((self.images, self.durations, self.cuts, self.srcs, [replace(e) for e in self.effects]))
        self.btn_undo.setEnabled(True)

    def _fx_select(self, k: int):
        self._sel_fx = k if 0 <= k < len(self.effects) else None
        self._loading_region = True
        try:
            self.view.set_region(self.effects[self._sel_fx].region if self._sel_fx is not None else None)
        finally:
            self._loading_region = False
        if self._sel_fx is not None:
            fx = self.effects[self._sel_fx]
            idx = self._fx_frames(fx)
            if idx and not (idx[0] <= self._cur <= idx[-1]):
                self._show_pos(float(self.timeline.starts[idx[0]]), force=True)
            self._say(tr("Efeito selecionado: arraste na imagem para mudar a área; arraste as pontas da faixa para mudar o tempo."))
        self._fx_dirty()
        self._update_tool_ui()
        self._show_pos(self._pos_ms, force=True)

    def _fx_remove(self):
        if self._sel_fx is None:
            return
        self._push_history()
        del self.effects[self._sel_fx]
        self._sel_fx = None
        self.view.clear_region()
        self._fx_dirty()
        self._show_pos(self._pos_ms, force=True)

    def _delete_key(self):
        if self._sel_fx is not None:
            self._fx_remove()
        else:
            self._delete()

    def _fx_edge(self, k: int, side: str, idx: int):
        if not (0 <= k < len(self.effects)):
            return
        fx = self.effects[k]
        if side == "a":
            fx.s0 = min(self.srcs[idx], fx.s1 - 1)
        else:
            fx.s1 = max(self.srcs[idx] + self.durations[idx], fx.s0 + 1)
        self._fx_dirty()
        self._show_pos(self._pos_ms, force=True)

    def _fx_edge_done(self, k: int):
        """Soltou a ponta: o zoom precisa de quadros curtos no trecho para a aproximação aparecer."""
        if 0 <= k < len(self.effects) and self.effects[k].kind == "zoom":
            self._refine_fx(self.effects[k])
        self._fx_dirty()
        self._show_pos(self._pos_ms, force=True)

    def _refine_fx(self, fx: Effect):
        idx = self._fx_frames(fx)
        if not idx:
            return
        imgs, durs, cs, ss, _a, _b = refine_range(self.images, self.durations, self.cuts, self.srcs, idx[0], idx[-1])
        if len(imgs) != len(self.images):
            self._set_state(imgs, durs, cs, ss)

    def _set_state(self, images, durations, cuts, srcs):
        """Troca os quadros (ex.: quebrados para o zoom) mantendo a mesma faixa de tempo selecionada e a cabeça de reprodução."""
        pos = self._pos_ms
        tl = self.timeline
        t0, t1 = tl.starts[tl.a], tl.starts[tl.b] + self.durations[tl.b]
        self.images, self.durations = images, durations
        self.srcs, self.cuts = list(srcs), list(cuts)
        tl.set_clip(durations, self.cuts)
        a = max((i for i, st in enumerate(tl.starts) if st <= t0), default=0)
        b = max((i for i, st in enumerate(tl.starts) if st < t1), default=a)
        tl.set_selection(a, max(a, b))
        self._fx_cache.clear()
        self._fx_dirty()
        self._refresh()
        self._show_pos(pos, force=True)

    def _ask_text(self, current: str = "") -> str | None:
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(self, tr("Texto no vídeo"), tr("Texto a mostrar na área marcada:"), current)
        return text.strip() if ok and text.strip() else None

    def _fx_from_button(self, kind: str, text: str | None = None, force_new: bool = False):
        r = self.view.region()
        if r is None:
            return
        if force_new:
            self._sel_fx = None
        if kind == "text" and text is None:
            cur = self.effects[self._sel_fx].text if self._sel_fx is not None and self.effects[self._sel_fx].kind == "text" else ""
            text = self._ask_text(cur)
            if text is None:
                self.view.clear_region()
                return
        if self._sel_fx is not None:                  # há um efeito selecionado: o botão troca o tipo dele
            self._push_history()
            fx = self.effects[self._sel_fx]
            fx.kind, fx.region = kind, QRectF(r)
            if kind == "text":
                fx.text = text or ""
            if kind == "zoom":
                self._refine_fx(fx)
            self._fx_dirty()
            self._show_pos(self._pos_ms, force=True)
            return
        self._push_history()
        a, b = self.selection()
        if kind == "zoom":                            # quebra os quadros longos do trecho para a aproximação aparecer
            imgs, durs, cs, ss, _a, _b = refine_range(self.images, self.durations, self.cuts, self.srcs, a, b)
            self._set_state(imgs, durs, cs, ss)
            a, b = self.selection()
        fx = Effect(kind, self.srcs[a], self.srcs[b] + self.durations[b], QRectF(r), text or "")
        self.effects.append(fx)
        self._sel_fx = len(self.effects) - 1
        self._fx_dirty()
        self._refresh()
        self._show_pos(self._pos_ms, force=True)
        self._say(tr("Efeito criado. Para ajustar, clique na faixa dele; para criar outro, clique num espaço vazio da faixa."))

    def _arm(self, kind: str):
        """Escolhe (ou desliga) a ferramenta de efeito: com ela ativa, arrastar sobre a imagem marca a área e cria o efeito."""
        self._tool = None if self._tool == kind else kind
        for k, b in self._fx_tools.items():
            if b is not None:
                b.setChecked(k == self._tool)
        self._update_tool_ui()

    def _update_tool_ui(self):
        armed = self._tool is not None
        self.view.drag_enabled = armed or self._sel_fx is not None
        self.view.setCursor(Qt.CursorShape.CrossCursor if armed else Qt.CursorShape.ArrowCursor)
        hints = {"zoom": tr("Zoom: arraste sobre a imagem para marcar a área a aproximar."),
                 "highlight": tr("Destaque: arraste sobre a imagem para marcar a área a destacar."),
                 "hide": tr("Ocultar: arraste sobre a imagem para marcar a área a esconder."),
                 "text": tr("Texto: arraste sobre a imagem para marcar onde o texto vai aparecer."),
                 "crop": tr("Recorte: arraste sobre a imagem para marcar a área que fica em todo o vídeo.")}
        if armed:
            self._hint_default = hints[self._tool]
        else:
            self._hint_default = tr("Escolha uma ferramenta de efeito (zoom, destaque, ocultar, texto) e arraste sobre a imagem para marcar a área.")
        if hasattr(self, "lbl_hint"):
            self.lbl_hint.setText(self._hint_default)

    def _region_changed(self):
        has = self.view.region() is not None
        if self._loading_region or not has:
            return
        if self._tool is not None:                    # ferramenta ativa: a área arrastada vira um novo efeito
            kind = self._tool
            if kind == "crop":
                self._do_crop()
                self._arm("crop")                     # recorte é de uma vez só: desliga a ferramenta
            else:
                self._fx_from_button(kind, force_new=True)
        elif self._sel_fx is not None:                # sem ferramenta, com um efeito selecionado: reajusta a área dele
            self._push_history()
            self.effects[self._sel_fx].region = QRectF(self.view.region())
            self._fx_dirty()
            self._show_pos(self._pos_ms, force=True)

    def _do_zoom(self):
        self._fx_from_button("zoom")

    def _do_highlight(self):
        self._fx_from_button("highlight")

    def _do_hide(self):
        self._fx_from_button("hide")

    def _do_text(self, text: str | None = None):
        self._fx_from_button("text", text)

    def _do_crop(self):
        r = self.view.region()
        if r is None:
            return
        effects = []
        for fx in self.effects:
            nr = remap_region(fx.region, "crop", r)
            if nr is not None:
                effects.append(Effect(fx.kind, fx.s0, fx.s1, nr, fx.text))
        self._apply_edit(apply_crop(self.images, r), list(self.durations), keep_selection=self.selection(), effects=effects)

    def _times_edited(self):
        """Seleção por tempo exato (segundos): o quadro inicial é o que contém 'de'; o final, o último que começa antes de 'até'."""
        t0, t1 = self.sp_from.value() * 1000, self.sp_to.value() * 1000
        starts = self.timeline.starts
        a = max((i for i, st in enumerate(starts) if st <= t0), default=0)
        b = max((i for i, st in enumerate(starts) if st < t1), default=a)
        if t1 < t0:
            t0, t1 = t1, t0
        self._sel_ms = (t0, t1)                # "Cortar trecho" usa estes tempos exatos, não os limites dos quadros
        self._typing = True
        try:
            self.set_selection(a, max(a, b))
        finally:
            self._typing = False

    def _say(self, msg: str):
        """Mensagem curta no rodapé da janela (volta ao texto de ajuda depois de alguns segundos)."""
        self.lbl_hint.setText(msg)
        QTimer.singleShot(5000, lambda: self.lbl_hint.setText(self._hint_default) if self.isVisible() else None)

    def _at_edited(self):
        self._at_ms = self.sp_at.value() * 1000
        self._refresh()

    def _rotate(self, degrees: int):
        from PySide6.QtGui import QTransform
        tf = QTransform().rotate(degrees)
        effects = []
        for fx in self.effects:
            nr = remap_region(fx.region, "rot", degrees)
            effects.append(Effect(fx.kind, fx.s0, fx.s1, nr, fx.text))
        self._apply_edit([im.transformed(tf) for im in self.images], list(self.durations), effects=effects)

    def _apply_edit(self, images: list[QImage], durations: list[int], keep_selection: tuple[int, int] | None = None,
                    cuts: list[int] | None = None, srcs: list[int] | None = None,
                    effects: list[Effect] | None = None) -> None:
        self._push_history()
        self.images, self.durations = images, durations
        self.srcs = list(self.srcs if srcs is None else srcs)
        self.cuts = list(self.cuts if cuts is None else cuts)
        if effects is not None:
            self.effects = effects
        self._sel_fx = None
        self._prune_effects()
        self._fx_cache.clear()
        self.timeline.set_clip(durations, self.cuts)
        self._fx_dirty()
        if keep_selection is not None:
            self.timeline.set_selection(*keep_selection)
        self.view.clear_region()
        self._refresh()
        self._show_frame(keep_selection[0] if keep_selection else 0)
        if self._playing:
            self._play_from(self._pos_ms)

    def _keep(self):
        if self.timeline.is_full():
            return
        a, b = self.selection()
        imgs, durs, cs, ss = keep_frames(self.images, self.durations, self.cuts, a, b, self.srcs)
        self._apply_edit(list(imgs), list(durs), cuts=cs, srcs=ss)

    def _delete(self):
        """Exclui o segmento (ou faixa) selecionado e junta o que sobrou."""
        a, b = self.selection()
        if self.timeline.is_full():          # apagar tudo não faz sentido: o clipe precisa de ao menos um quadro
            return
        imgs, durs, cs, ss = delete_frames(self.images, self.durations, self.cuts, a, b, self.srcs)
        self._apply_edit(imgs, durs, cuts=cs, srcs=ss)

    def _index_starting_at(self, durations: list[int], t_ms: float) -> int:
        t = 0
        for i, d in enumerate(durations):
            if t >= t_ms - 0.5:
                return i
            t += d
        return len(durations) - 1

    def _split(self):
        """Divide o vídeo na posição indicada (cabeça de reprodução ou tempo digitado) e seleciona o segmento à direita."""
        self.sp_at.interpretText()
        t = self._at_ms
        if abs(self.sp_at.value() * 1000 - t) > 5:           # tempo digitado (ainda não confirmado com Enter)
            t = self._at_ms = self.sp_at.value() * 1000
        imgs, durs, cs, ss = split_clip(self.images, self.durations, self.cuts, t, self.srcs)
        if cs == self.cuts and len(imgs) == len(self.images):
            self._say(tr("Nada a dividir: escolha um tempo entre o início e o fim do vídeo."))
            return
        k = self._index_starting_at(durs, t)
        self._apply_edit(imgs, durs, keep_selection=segment_bounds(cs, len(imgs), k), cuts=cs, srcs=ss)

    def _merge_all(self):
        """Junta todos os blocos restantes num só (tira as divisões; o conteúdo e os efeitos ficam como estão)."""
        if not self.cuts:
            self._say(tr("Não há divisões para unificar."))
            return
        self._apply_edit(list(self.images), list(self.durations), cuts=[], keep_selection=(0, len(self.durations) - 1))

    def _undo(self):
        if not self._history:
            return
        self.images, self.durations, self.cuts, self.srcs, self.effects = self._history.pop()
        self._sel_fx = None
        self._fx_cache.clear()
        self.timeline.set_clip(self.durations, self.cuts)
        self._fx_dirty()
        self.view.clear_region()
        self._refresh()
        self._show_frame(0)
        if self._playing:
            self._play_from(0.0)

    # --- reprodução ---------------------------------------------------------
    def _show_pos(self, ms: float, force: bool = False):
        """Põe a cabeça de reprodução em ``ms`` (anda também dentro de um quadro longo) e mostra o quadro dessa posição."""
        total = self.timeline.total
        ms = min(max(float(ms), 0.0), float(total - 1))
        i = self.timeline.index_of_ms(ms)
        self._pos_ms = ms
        self._cur = i
        self.timeline.cur, self.timeline.pos = i, ms
        self.timeline.update()
        self._at_ms = ms
        if not self.sp_at.hasFocus():
            self.sp_at.blockSignals(True)
            self.sp_at.setValue(ms / 1000)
            self.sp_at.blockSignals(False)
        if force or i != self._shown:
            self._shown = i
            pm = QPixmap.fromImage(self.frame_image(i, exclude=self._sel_fx))
            self.view.setPixmap(pm.scaled(self.view.size() - QSize(8, 8), Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))

    def _show_frame(self, i: int):
        self._show_pos(float(self.timeline.starts[i]), force=True)

    def _sel_span(self) -> tuple[float, float]:
        """Trecho reproduzido: o vídeo inteiro (a seleção serve só para editar, então as edições de cada bloco aparecem)."""
        return 0.0, float(self.timeline.total)

    def _play_from(self, ms: float):
        """Começa (ou retoma) a reprodução a partir de ``ms``; fora da faixa selecionada, começa no início dela."""
        t0, t1 = self._sel_span()
        if not (t0 <= ms < t1):
            ms = t0
        self._show_pos(ms)
        self._play_base = ms
        self._clock.start()
        self._timer.start()

    def _tick(self):
        t0, t1 = self._sel_span()
        pos = self._play_base + self._clock.elapsed()
        if pos >= t1:
            if not self.cb_loop.isChecked():     # sem repetir: toca uma vez, para e volta ao início
                self._set_playing(False)
                self._show_pos(t0, force=True)
                return
            pos = t0 + (pos - t1) % max(1.0, t1 - t0)   # volta ao início (laço)
            self._play_base = pos
            self._clock.restart()
        self._show_pos(pos)

    def _on_seek(self, ms: float):
        self._show_pos(ms)
        if self._playing:
            self._play_base = self._pos_ms
            self._clock.restart()
            self._timer.start()

    def _set_playing(self, on: bool):
        self._playing = on
        if on:
            self._play_from(self._pos_ms)
        else:
            self._timer.stop()
        self._refresh()

    def _toggle(self):
        self._set_playing(not self._playing)

    def _to_start(self):
        t0, _ = self._sel_span()
        self._show_pos(t0)
        if self._playing:
            self._play_from(t0)

    def _stop(self):
        self._set_playing(False)
        self._show_pos(self._sel_span()[0])

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.images:
            self._show_pos(self._pos_ms, force=True)

    # --- salvar ---------------------------------------------------------------
    def _save(self):
        if self._job is not None:
            return
        path = self._default_path()
        imgs, durs = self.selected()
        self.btn_save.setEnabled(False)
        self.btn_discard.setEnabled(False)
        self.bar.setValue(0)
        self.bar.show()
        if self.kind == "mp4":
            from .videoenc import Mp4Encoder
            enc = Mp4Encoder(imgs, durs, path, self, audio=self.audio, srcs=self.selected_srcs())
            self._job = enc
            enc.progress.connect(self.bar.setValue)
            enc.failed.connect(lambda msg: self._finish(path, msg))
            enc.done.connect(lambda _p: self._finish(path, ""))
            enc.start()
            return
        self._job = _EncodeJob(imgs, durs, path, self)
        self._job.progress.connect(self.bar.setValue)
        self._job.failed.connect(lambda msg: self._finish(path, msg))
        self._job.finished.connect(lambda: self._finish(path, ""))
        self._job.start()

    def _finish(self, path: str, error: str):
        if self._job is None:
            return
        self._job = None
        if error:
            self.info.setText(tr("Não foi possível salvar o arquivo: {err}").format(err=error))
            self.btn_save.setEnabled(True)
            self.btn_discard.setEnabled(True)
            self.bar.hide()
            return
        self.saved.emit(path)
        self._show_saved(path)
        self.accept()

    def _show_saved(self, path: str):
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        is_mp4 = self.kind == "mp4"
        box.setWindowTitle(tr("Vídeo salvo") if is_mp4 else tr("GIF salvo"))
        box.setText((tr("O vídeo foi salvo em:") if is_mp4 else tr("O GIF foi salvo em:")) + "\n" + path)
        b_show = box.addButton(tr("Mostrar na pasta"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(tr("Fechar"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is b_show:
            reveal_in_folder(path)

    def closeEvent(self, ev):
        if self._job is not None:            # não fecha no meio da gravação do arquivo
            ev.ignore()
            return
        super().closeEvent(ev)

    def done(self, r):
        if self._job is not None:
            return
        self._timer.stop()
        super().done(r)


def make_grabber(screen, logical: QRect, physical: QRect, with_cursor: bool, highlight: bool = False) -> Callable[[], QImage]:
    """Função que devolve um quadro da área (em pixels reais). Se a captura parcial não bater com o tamanho
    esperado, passa a capturar a tela inteira e recortar."""
    state = {"partial": True}
    origin = screen.geometry().topLeft()

    def grab() -> QImage:
        if state["partial"]:
            img = screen.grabWindow(0, logical.x(), logical.y(), logical.width(), logical.height()).toImage()
            if abs(img.width() - physical.width()) <= 2 and abs(img.height() - physical.height()) <= 2:
                pass
            else:
                state["partial"] = False
        if not state["partial"]:
            full = screen.grabWindow(0).toImage()
            full.setDevicePixelRatio(1.0)
            img = full.copy(physical)
        img.setDevicePixelRatio(1.0)
        if with_cursor:
            img = draw_cursor(img, grab_cursor(), origin + physical.topLeft(), highlight, mouse_pressed() if highlight else False)
        return img

    return grab


def reveal_in_folder(path: str):
    """Abre a pasta do arquivo (no Windows, já com o arquivo selecionado)."""
    import sys
    from PySide6.QtCore import QProcess, QUrl
    from PySide6.QtGui import QDesktopServices
    if sys.platform == "win32":
        proc = QProcess()
        proc.setProgram("explorer.exe")
        proc.setNativeArguments('/select,"' + str(Path(path)) + '"')
        if proc.startDetached():
            return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))


def default_video_path(folder: str, pattern: str = "", by_month: bool = False) -> str:
    from .naming import DEFAULT_PATTERN, build_path
    return str(build_path(folder, "mp4", pattern or DEFAULT_PATTERN, by_month))


def default_gif_path(folder: str, pattern: str = "", by_month: bool = False) -> str:
    from .naming import DEFAULT_PATTERN, build_path
    return str(build_path(folder, "gif", pattern or DEFAULT_PATTERN, by_month))

