"""Conversões entre QImage e numpy."""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage


def qimage_to_np(img: QImage) -> np.ndarray:
    """QImage -> array HxWx3 uint8 (RGB)."""
    img = img.convertToFormat(QImage.Format.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8, count=bpl * h)
    return buf.reshape(h, bpl)[:, : w * 3].reshape(h, w, 3).copy()


def np_to_qimage(arr: np.ndarray) -> QImage:
    """Array HxWx3 uint8 (RGB) -> QImage independente do buffer original."""
    arr = np.ascontiguousarray(arr[..., :3])
    h, w, _ = arr.shape
    return QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
