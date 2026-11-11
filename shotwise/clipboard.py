"""Cópia de imagens para a área de transferência com cuidado de privacidade.

No Windows 10/11 o histórico da área de transferência (Win+V) e a sincronização
na nuvem guardam tudo que é copiado. Capturas de tela costumam conter dados
sensíveis, então a imagem é marcada para ficar fora do histórico e da nuvem.
Aplicativos que respeitam essas marcas (o próprio Windows respeita) deixam de
registrar o conteúdo.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtGui import QGuiApplication, QImage

_WIN_FORMAT = 'application/x-qt-windows-mime;value="{}"'
_ZERO_DWORD = QByteArray(b"\x00\x00\x00\x00")
_EXCLUDE_FORMATS = (
    "CanIncludeInClipboardHistory",
    "CanUploadToCloudClipboard",
    "ExcludeClipboardContentFromMonitorProcessing",
)


def _mark_excluded(mime: QMimeData) -> None:
    if sys.platform == "win32":
        for fmt in _EXCLUDE_FORMATS:
            mime.setData(_WIN_FORMAT.format(fmt), _ZERO_DWORD)


def copy_image(image: QImage, exclude_from_history: bool = True) -> None:
    mime = QMimeData()
    mime.setImageData(image)
    if exclude_from_history:
        _mark_excluded(mime)
    QGuiApplication.clipboard().setMimeData(mime)


def copy_text(text: str, exclude_from_history: bool = True) -> None:
    """Texto reconhecido por OCR também pode ser sensível: fica fora do histórico (Win+V)."""
    mime = QMimeData()
    mime.setText(text)
    if exclude_from_history:
        _mark_excluded(mime)
    QGuiApplication.clipboard().setMimeData(mime)
