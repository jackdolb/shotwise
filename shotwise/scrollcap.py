"""Captura com rolagem: rola a área sob o cursor, captura e costura os quadros."""
from __future__ import annotations

import sys
import time

import numpy as np
from PySide6.QtCore import QCoreApplication, QEventLoop, QPoint, QRect, QTimer
from PySide6.QtGui import QCursor, QImage

from .imageutil import qimage_to_np
from .stitcher import ScrollStitcher, Status
from .i18n import tr

IS_WINDOWS = sys.platform == "win32"
WHEEL_DELTA = 120
VK_ESCAPE = 0x1B
MOUSEEVENTF_WHEEL = 0x0800


def _sleep(ms: int) -> None:
    """Espera sem travar a interface."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def escape_pressed() -> bool:
    if not IS_WINDOWS:
        return False
    import ctypes

    return bool(ctypes.windll.user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)


def send_wheel(notches: int) -> None:
    """Gira a roda do mouse (notches > 0 rola a página para baixo)."""
    if not IS_WINDOWS:
        raise RuntimeError(tr("A captura por rolagem só funciona no Windows."))
    import ctypes

    ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, ctypes.c_ulong(-notches * WHEEL_DELTA & 0xFFFFFFFF), 0)


class ScrollResult:
    def __init__(self, image: np.ndarray | None, message: str, frames: int):
        self.image = image
        self.message = message
        self.frames = frames


def grab_region(screen, phys: QRect) -> np.ndarray:
    img: QImage = screen.grabWindow(0).toImage()
    img.setDevicePixelRatio(1.0)
    return qimage_to_np(img.copy(phys))


def grab_stable(screen, phys: QRect, tries: int = 10, gap_ms: int = 110) -> np.ndarray:
    """Captura só depois que a imagem para de mudar (rolagem suave terminou)."""
    prev = grab_region(screen, phys)
    for _ in range(tries):
        _sleep(gap_ms)
        cur = grab_region(screen, phys)
        if np.abs(cur.astype(np.int16) - prev.astype(np.int16)).mean() < 0.25:
            return cur
        prev = cur
    return prev


def run_scroll_capture(screen, logical: QRect, phys: QRect, delay_ms: int = 300,
                       max_frames: int = 80, max_height: int = 30000,
                       progress=None) -> ScrollResult:
    """Executa a captura. ``logical`` é o retângulo em coordenadas do monitor
    (usado para posicionar o cursor); ``phys`` está em pixels físicos."""
    center = screen.geometry().topLeft() + logical.center()
    QCursor.setPos(center)
    _sleep(150)

    stitcher = ScrollStitcher(max_height=max_height)
    first = grab_stable(screen, phys)
    stitcher.add_frame(first)

    notches = 1          # começa com 1 clique para calibrar
    calibrated = False
    message = tr("Fim da página alcançado.")
    stalls = 0

    for i in range(max_frames):
        if escape_pressed():
            message = "Captura interrompida (Esc)."
            break
        QCursor.setPos(center)
        send_wheel(notches)
        _sleep(delay_ms)
        frame = grab_stable(screen, phys)
        step = stitcher.add_frame(frame)

        if step.status is Status.END:
            # confirma com uma segunda tentativa (a rolagem pode ter atrasado)
            stalls += 1
            if stalls >= 2 or stitcher.reached_limit:
                if stitcher.reached_limit:
                    message = tr("Altura máxima atingida.")
                break
            _sleep(max(400, delay_ms))
            frame = grab_stable(screen, phys)
            step = stitcher.add_frame(frame)
            if step.status is Status.END:
                if stitcher.reached_limit:
                    message = tr("Altura máxima atingida.")
                break
        stalls = 0

        if step.status is Status.NO_MATCH:
            message = (tr("Não foi possível alinhar um dos quadros (conteúdo animado ou rolagem muito grande). "
                       "A imagem foi montada até esse ponto."))
            break

        if not calibrated and step.status is Status.OK and step.dy > 0:
            # ajusta o nº de cliques para rolar ~55% da altura da região
            target = phys.height() * 0.55
            notches = max(1, int(target / step.dy))
            calibrated = True

        if progress:
            progress(stitcher.frames, stitcher.height)
    else:
        message = tr("Limite de quadros atingido.")

    return ScrollResult(stitcher.result(), message, stitcher.frames)
