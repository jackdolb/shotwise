"""Reconhecimento de texto (OCR) usando o mecanismo nativo do Windows 10/11 (Windows.Media.Ocr).

Tudo roda localmente: nenhuma imagem sai do computador e não há conexão de rede.
Os idiomas disponíveis são os pacotes de OCR instalados no Windows (Configurações > Hora e idioma >
Idioma e região > idioma > Opções de idioma > Reconhecimento óptico de caracteres).
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QThread, Signal, Slot
from PySide6.QtGui import QImage
from .i18n import tr

PREFERRED_LANGS = ("pt-BR", "pt-PT", "pt", "en-US", "en")


class OcrError(Exception):
    pass


def is_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winrt.windows.media.ocr  # noqa: F401
    except Exception:  # noqa: BLE001 - qualquer falha de importação = indisponível
        return False
    return True


def _png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


async def _recognize_async(png: bytes) -> str:  # pragma: no cover - depende do Windows
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()

    def engine_for(tag: str):
        try:
            lang = Language(tag)
            return OcrEngine.try_create_from_language(lang) if OcrEngine.is_language_supported(lang) else None
        except Exception:  # noqa: BLE001 - idioma inválido/indisponível: tenta o próximo
            return None

    engine = next((e for e in (engine_for(t) for t in PREFERRED_LANGS) if e is not None), None)
    if engine is None:
        engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrError(tr("Nenhum pacote de idioma de OCR está instalado no Windows. Instale em Configurações > "
                       "Hora e idioma > Idioma e região (Reconhecimento óptico de caracteres)."))
    result = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines)


def recognize(image: QImage) -> str:
    """Reconhece o texto da imagem (bloqueante; chame de uma thread). Levanta OcrError."""
    if sys.platform != "win32":
        raise OcrError(tr("O reconhecimento de texto usa o OCR do Windows e só funciona no Windows."))
    if image.isNull():
        raise OcrError(tr("Região vazia."))
    if image.width() > 10000 or image.height() > 10000:
        raise OcrError(tr("A região é grande demais para o OCR do Windows (limite de 10000 px). Selecione uma área menor."))
    try:
        import asyncio

        return asyncio.run(_recognize_async(_png_bytes(image)))
    except OcrError:
        raise
    except ImportError as exc:
        raise OcrError(tr("Componente de OCR ausente (pacotes winrt). Reinstale o Shotwise ou rode "
                       "'pip install -r requirements.txt'.")) from exc
    except Exception as exc:  # noqa: BLE001 - erros do WinRT vêm de vários tipos
        raise OcrError(f"Falha no OCR do Windows: {exc}") from exc


class OcrWorker(QObject):
    finished = Signal(str, str)      # texto, erro

    def __init__(self, image: QImage, func=recognize):
        super().__init__()
        self._image = image
        self._func = func

    def run(self):
        try:
            self.finished.emit(self._func(self._image), "")
        except OcrError as exc:
            self.finished.emit("", str(exc))
        except Exception as exc:  # noqa: BLE001
            self.finished.emit("", f"Erro inesperado: {exc}")


class _Relay(QObject):
    """Vive na thread da interface: o sinal do worker chega aqui em fila (queued) e só então chama o callback.

    Conectar o sinal direto a uma função simples executaria o callback na thread do OCR, e mexer na
    interface (janelas, cursor) a partir dela derruba o programa.
    """

    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    @Slot(str, str)
    def receive(self, text: str, err: str):
        self._callback(text, err)


def start_ocr(image: QImage, on_done, parent=None, func=recognize):
    """Roda o OCR em outra thread e chama on_done(texto, erro) na thread da interface."""
    thread = QThread(parent)
    worker = OcrWorker(image, func)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    relay = _Relay(on_done)
    worker._relay = relay                      # mantém o relay vivo junto com o worker
    worker.finished.connect(relay.receive)
    worker.finished.connect(thread.quit)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    return thread, worker
