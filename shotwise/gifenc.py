"""Codificação de GIF animado (Pillow) a partir de quadros QImage."""
from __future__ import annotations

from collections.abc import Callable

from PIL import Image
from PySide6.QtGui import QImage

MIN_FRAME_MS = 20          # navegadores tratam atrasos menores que isso como 100 ms


def qimage_to_pil(img: QImage) -> Image.Image:
    rgb = img.convertToFormat(QImage.Format.Format_RGB888)
    return Image.frombuffer("RGB", (rgb.width(), rgb.height()), bytes(rgb.constBits()), "raw", "RGB",
                            rgb.bytesPerLine(), 1)


def _shared_palette(frames: list[Image.Image], colors: int) -> Image.Image:
    """Uma paleta só para todos os quadros (evita cintilação de cores entre quadros)."""
    n = len(frames)
    picks = sorted({round(i * (n - 1) / max(1, min(n, 10) - 1)) for i in range(min(n, 10))})
    thumbs = []
    for i in picks:
        f = frames[i]
        k = min(1.0, 360 / max(1, f.width))
        thumbs.append(f.resize((max(1, round(f.width * k)), max(1, round(f.height * k)))) if k < 1 else f)
    w = max(t.width for t in thumbs)
    sheet = Image.new("RGB", (w, sum(t.height for t in thumbs)))
    y = 0
    for t in thumbs:
        sheet.paste(t, (0, y))
        y += t.height
    return sheet.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)


def encode_gif(images: list[QImage], durations_ms: list[int], path: str, colors: int = 256,
               progress: Callable[[int], None] | None = None) -> None:
    """Grava ``path``. ``durations_ms`` tem um valor por quadro. Lança ValueError se não houver quadros."""
    if not images or len(images) != len(durations_ms):
        raise ValueError("sem quadros para gravar")
    pil = [qimage_to_pil(i) for i in images]
    pal = _shared_palette(pil, colors)
    out = []
    for i, f in enumerate(pil):
        out.append(f.quantize(palette=pal, dither=Image.Dither.NONE))
        if progress:
            progress(int(90 * (i + 1) / len(pil)))
    durs = [max(MIN_FRAME_MS, int(d)) for d in durations_ms]
    out[0].save(path, format="GIF", save_all=True, append_images=out[1:], duration=durs, loop=0, optimize=False)
    if progress:
        progress(100)
