"""Costura de capturas com rolagem (scroll capture).

Módulo puro (somente numpy), sem dependência de Qt, para poder ser testado
isoladamente. Recebe quadros sucessivos (arrays HxWx3 uint8) e monta uma
imagem única e contínua.

Como funciona
-------------
1. Entre o 1º e o 2º quadro detecta linhas "estáticas" no topo (cabeçalho
   fixo) e na base (rodapé fixo). Elas são excluídas do alinhamento.
2. Para cada novo quadro procura o deslocamento vertical (dy) que melhor
   alinha o quadro anterior com o atual (menor diferença média absoluta).
   A busca é feita em duas etapas (grosseira e refinada) para ser rápida.
3. Só as linhas realmente novas (as últimas dy linhas da região rolável)
   são acrescentadas ao resultado. O rodapé fixo é colocado uma única vez,
   no final.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

# Margem (fração da largura) ignorada no cálculo do erro: evita que a barra
# de rolagem, que se move entre quadros, atrapalhe o alinhamento.
_SCROLLBAR_MARGIN = 0.03
# Tolerâncias (diferença média absoluta em níveis de cinza, 0-255)
_SAME_FRAME_TOL = 0.6
_STATIC_ROW_TOL = 1.5
_MATCH_TOL = 9.0
# limite de memória do resultado final (bytes RGB)
_MAX_RESULT_BYTES = 300_000_000


class Status(Enum):
    OK = "ok"            # quadro alinhado e acrescentado
    END = "end"          # quadro igual ao anterior: fim da página
    NO_MATCH = "nomatch"  # não foi possível alinhar


@dataclass
class StepResult:
    status: Status
    dy: int = 0          # quanto o conteúdo rolou neste passo
    error: float = 0.0   # erro médio do melhor alinhamento


def _to_gray(frame: np.ndarray) -> np.ndarray:
    rgb = frame[..., :3].astype(np.float32)
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _cols(width: int) -> slice:
    usable = max(8, int(width * (1.0 - _SCROLLBAR_MARGIN)))
    return slice(0, usable)


def _mean_abs(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).mean())


def find_shift(a: np.ndarray, b: np.ndarray, hint: int | None = None) -> tuple[int, float]:
    """Retorna (dy, erro) tal que ``a[dy:] ~= b[:h-dy]`` (arrays em cinza).

    ``dy`` é quanto o conteúdo subiu entre ``a`` e ``b``. ``dy == 0`` significa
    quadros iguais. Se ``hint`` (dy esperado) for dado, a busca começa em uma
    janela ao redor dele, o que é bem mais rápido.
    """
    h = a.shape[0]
    w = a.shape[1]
    c = _cols(w)
    a = a[:, c]
    b = b[:, c]
    min_overlap = max(24, int(h * 0.10))
    max_dy = h - min_overlap
    if max_dy < 1:
        return 0, _mean_abs(a, b)

    def coarse(lo: int, hi: int) -> np.ndarray:
        errs = np.full(hi - lo + 1, np.inf, dtype=np.float64)
        for i, dy in enumerate(range(lo, hi + 1)):
            aa = a[dy::6, ::6]
            bb = b[: h - dy : 6, ::6]
            n = min(aa.shape[0], bb.shape[0])
            errs[i] = np.abs(aa[:n] - bb[:n]).mean()
        return errs

    def refine(center: int) -> tuple[int, float]:
        best_dy, best_err = center, np.inf
        for dy in range(max(0, center - 5), min(max_dy, center + 5) + 1):
            e = _mean_abs(a[dy:], b[: h - dy])
            if e < best_err - 1e-9 or (abs(e - best_err) <= 1e-9 and hint is not None
                                       and abs(dy - hint) < abs(best_dy - hint)):
                best_dy, best_err = dy, e
        return best_dy, best_err

    def pick(lo: int, hi: int) -> tuple[int, float]:
        errs = coarse(lo, hi)
        best = float(errs.min())
        # candidatos "empatados" (áreas uniformes dão vários empates)
        close = np.where(errs <= best * 1.15 + 0.4)[0]
        if hint is not None:
            idx = int(close[np.argmin(np.abs((close + lo) - hint))])
        else:
            idx = int(close[0])
        return refine(idx + lo)

    if hint is not None and hint > 0:
        lo = max(0, int(hint * 0.5) - 6)
        hi = min(max_dy, int(hint * 1.6) + 6)
        if hi > lo:
            dy, err = pick(lo, hi)
            if err <= _MATCH_TOL:
                return dy, err
    return pick(0, max_dy)


class ScrollStitcher:
    """Montagem incremental: ``add_frame()`` a cada quadro, ``result()`` no fim."""

    def __init__(self, max_height: int = 30000):
        self.max_height = max_height
        self._prev: np.ndarray | None = None
        self._prev_gray: np.ndarray | None = None
        self._strips: list[np.ndarray] = []
        self._top = 0       # linhas fixas no topo
        self._bottom = 0    # linhas fixas na base
        self._have_pair = False
        self._height = 0
        self.last_dy: int | None = None
        self.frames = 0
        self.reached_limit = False

    # ------------------------------------------------------------------
    @property
    def height(self) -> int:
        """Altura aproximada do resultado até agora."""
        return self._height + self._bottom

    @property
    def static_rows(self) -> tuple[int, int]:
        return self._top, self._bottom

    def add_frame(self, frame: np.ndarray) -> StepResult:
        frame = np.ascontiguousarray(frame[..., :3])
        gray = _to_gray(frame)
        self.frames += 1

        if self._prev is None:
            # teto de memória: a imagem final (strips + cópia da concatenação) não passa de ~600 MB
            w = frame.shape[1]
            self.max_height = min(self.max_height, max(2000, _MAX_RESULT_BYTES // (w * 3)))
            self._prev, self._prev_gray = frame, gray
            return StepResult(Status.OK)

        if frame.shape != self._prev.shape:
            return StepResult(Status.NO_MATCH)

        h = frame.shape[0]
        prev_gray = self._prev_gray

        # quadro idêntico ao anterior -> fim da página
        if _mean_abs(prev_gray[:, _cols(frame.shape[1])], gray[:, _cols(frame.shape[1])]) <= _SAME_FRAME_TOL:
            return StepResult(Status.END)

        if not self._have_pair:
            self._top, self._bottom = self._detect_static(prev_gray, gray)

        t, b = self._top, self._bottom
        band_a = prev_gray[t : h - b]
        band_b = gray[t : h - b]
        bh = band_a.shape[0]
        if bh < 48:
            return StepResult(Status.NO_MATCH)

        dy, err = find_shift(band_a, band_b, self.last_dy)
        if err > _MATCH_TOL:
            return StepResult(Status.NO_MATCH, dy, err)
        if dy == 0:
            return StepResult(Status.END, 0, err)

        if not self._have_pair:
            # primeira vez: guarda o 1º quadro inteiro (menos o rodapé fixo)
            self._strips.append(self._prev[: h - b])
            self._height = h - b
            self._have_pair = True

        new_rows = frame[h - b - dy : h - b]
        if self._height + new_rows.shape[0] + b > self.max_height:
            keep = self.max_height - self._height - b
            if keep > 0:
                self._strips.append(new_rows[:keep])
                self._height += keep
            self.reached_limit = True
            self._prev, self._prev_gray = frame, gray
            return StepResult(Status.END, dy, err)

        self._strips.append(new_rows)
        self._height += new_rows.shape[0]
        self.last_dy = dy
        self._prev, self._prev_gray = frame, gray
        return StepResult(Status.OK, dy, err)

    # ------------------------------------------------------------------
    @staticmethod
    def _detect_static(a: np.ndarray, b: np.ndarray) -> tuple[int, int]:
        h, w = a.shape
        c = _cols(w)
        row_diff = np.abs(a[:, c] - b[:, c]).mean(axis=1)
        moving = row_diff > _STATIC_ROW_TOL
        if not moving.any():
            return 0, 0
        top = int(np.argmax(moving))
        bottom = int(np.argmax(moving[::-1]))
        # a região rolável precisa ter pelo menos 40% do quadro
        if h - top - bottom < h * 0.4:
            return 0, 0
        return top, bottom

    def result(self) -> np.ndarray | None:
        if self._prev is None:
            return None
        if not self._have_pair:
            return self._prev
        h = self._prev.shape[0]
        parts = list(self._strips)
        if self._bottom:
            parts.append(self._prev[h - self._bottom :])
        return np.concatenate(parts, axis=0)


def stitch_frames(frames: list[np.ndarray], max_height: int = 30000) -> tuple[np.ndarray | None, list[StepResult]]:
    """Atalho para costurar uma lista de quadros já capturados."""
    st = ScrollStitcher(max_height=max_height)
    results = []
    for f in frames:
        r = st.add_frame(f)
        results.append(r)
        if r.status is Status.END:
            break
    return st.result(), results
