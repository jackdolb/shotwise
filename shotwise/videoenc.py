"""Gravação de MP4 sem programa externo: usa o codificador do Qt Multimedia (QMediaRecorder + QVideoFrameInput).

Os quadros chegam com o instante de cada um (duração variável), então o vídeo respeita o tempo real da gravação.
Prefere H.264 quando o sistema oferece; senão (ou se o H.264 falhar) usa MPEG-4 parte 2, que também tem
extensão .mp4. Tudo roda no thread da interface, por sinais (não trava a janela)."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QImage

log = logging.getLogger("shotwise")

try:  # QtMultimedia pode faltar em instalações enxutas
    from PySide6.QtMultimedia import (QAudioBuffer, QAudioBufferInput, QAudioFormat, QMediaCaptureSession, QMediaFormat,
                                      QMediaRecorder, QVideoFrame, QVideoFrameFormat, QVideoFrameInput)
    AVAILABLE = True
except ImportError:  # pragma: no cover
    AVAILABLE = False

STALL_MS = 30000          # sem nenhum progresso por tanto tempo = erro
AUDIO_CHUNK_MS = 100      # tamanho dos blocos de áudio enviados ao codificador


def even_size(images: list[QImage]) -> QSize:
    """H.264 exige largura e altura pares: usa o menor tamanho comum, arredondado para baixo."""
    w = min(i.width() for i in images)
    h = min(i.height() for i in images)
    return QSize(max(2, w & ~1), max(2, h & ~1))


def pick_codec() -> str:
    """'h264' se o sistema consegue codificar H.264 em MP4, senão 'mpeg4'."""
    if not AVAILABLE:
        return "mpeg4"
    mf = QMediaFormat(QMediaFormat.FileFormat.MPEG4)
    codecs = mf.supportedVideoCodecs(QMediaFormat.ConversionMode.Encode)
    return "h264" if QMediaFormat.VideoCodec.H264 in codecs else "mpeg4"


class Mp4Encoder(QObject):
    progress = Signal(int)          # 0..100
    done = Signal(str)              # caminho do arquivo
    failed = Signal(str)

    def __init__(self, images: list[QImage], durations_ms: list[int], path: str, parent: QObject | None = None,
                 audio: bytes = b"", srcs: list[int] | None = None):
        super().__init__(parent)
        self.images, self.durations, self.path = images, durations_ms, path
        self.codec_used = ""
        self.audio_used = False
        self._pcm = b""
        if audio:                                   # áudio do trecho editado, com a duração exata do vídeo
            from .audiocap import clip_audio, default_srcs
            self._pcm = clip_audio(audio, srcs if srcs is not None else default_srcs(durations_ms), durations_ms)
        self._attempts: list[tuple[str, bool]] = []
        self._rec = self._session = self._input = self._ainput = None
        self._i = 0
        self._ai = 0
        self._finished = False
        self._stall = QTimer(self)
        self._stall.setSingleShot(True)
        self._stall.timeout.connect(lambda: self._fail("o codificador de vídeo não respondeu"))

    # --- API --------------------------------------------------------------------
    def start(self) -> None:
        if not AVAILABLE:
            self._fail("o componente de vídeo (QtMultimedia) não está disponível")
            return
        if not self.images:
            self._fail("nenhum quadro para gravar")
            return
        self._size = even_size(self.images)
        starts, t = [], 0
        for d in self.durations:
            starts.append(t)
            t += max(1, d) * 1000          # microssegundos
        self._starts, self._total_us = starts, t
        first = pick_codec()
        with_audio = bool(self._pcm)
        self._attempts = [(first, with_audio)]
        if first == "h264":
            self._attempts.append(("mpeg4", with_audio))
        if with_audio:                              # último recurso: sem a faixa de áudio
            self._attempts.append(("mpeg4", False))
        self._launch(*self._attempts.pop(0))

    # --- implementação ---------------------------------------------------------------
    def _launch(self, codec: str, with_audio: bool = False) -> None:
        self.codec_used = codec
        self.audio_used = with_audio
        self._i = 0
        self._ai = 0
        self._stopping = False
        self._teardown()
        try:
            Path(self.path).unlink(missing_ok=True)
        except OSError:
            pass
        fmt = QVideoFrameFormat(self._size, QVideoFrameFormat.PixelFormat.Format_BGRA8888)
        self._input = QVideoFrameInput(fmt, self)
        self._session = QMediaCaptureSession(self)
        self._rec = QMediaRecorder(self)
        self._session.setVideoFrameInput(self._input)
        self._session.setRecorder(self._rec)
        mfmt = QMediaFormat(QMediaFormat.FileFormat.MPEG4)
        mfmt.setVideoCodec(QMediaFormat.VideoCodec.H264 if codec == "h264" else QMediaFormat.VideoCodec.MPEG4)
        self._rec.setMediaFormat(mfmt)
        self._rec.setQuality(QMediaRecorder.Quality.HighQuality)
        mean_ms = max(1, self._total_us / 1000 / len(self.images))
        self._rec.setVideoFrameRate(min(60.0, max(1.0, 1000.0 / mean_ms)))
        self._rec.setOutputLocation(QUrl.fromLocalFile(self.path))
        self._input.readyToSendVideoFrame.connect(self._feed)
        if with_audio:
            afmt = QAudioFormat()
            afmt.setSampleRate(48000)
            afmt.setChannelCount(2)
            afmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            self._afmt = afmt
            self._ainput = QAudioBufferInput(afmt, self)
            self._session.setAudioBufferInput(self._ainput)
            self._ainput.readyToSendAudioBuffer.connect(self._feed_audio)
            if QMediaFormat.AudioCodec.AAC in mfmt.supportedAudioCodecs(QMediaFormat.ConversionMode.Encode):
                mfmt.setAudioCodec(QMediaFormat.AudioCodec.AAC)
                self._rec.setMediaFormat(mfmt)
        self._rec.errorOccurred.connect(self._on_error)
        self._rec.recorderStateChanged.connect(self._on_state)
        self._stall.start(STALL_MS)
        self._rec.record()

    def _teardown(self) -> None:
        for obj in (self._rec, self._input, self._ainput, self._session):
            if obj is not None:
                try:
                    obj.blockSignals(True)
                    obj.deleteLater()
                except RuntimeError:
                    pass
        self._rec = self._input = self._ainput = self._session = None

    def _frame(self, i: int) -> "QVideoFrame":
        img = self.images[i]
        if img.size() != self._size:
            img = img.copy(0, 0, self._size.width(), self._size.height())
        img = img.convertToFormat(QImage.Format.Format_ARGB32)
        f = QVideoFrame(img)
        f.setStartTime(self._starts[i])
        f.setEndTime(self._starts[i] + max(1, self.durations[i]) * 1000)
        return f

    def _feed(self) -> None:
        if self._finished or self._input is None:
            return
        n = len(self.images)
        while self._i < n:
            if not self._input.sendVideoFrame(self._frame(self._i)):
                return                      # fila cheia: continua no próximo readyToSendVideoFrame
            self._i += 1
            self._stall.start(STALL_MS)
            if self._i % 5 == 0:
                self.progress.emit(min(98, int(self._i * 100 / n)))
        self._maybe_stop()

    def _feed_audio(self) -> None:
        if self._finished or self._ainput is None:
            return
        step = 48 * 4 * AUDIO_CHUNK_MS
        while self._ai < len(self._pcm):
            chunk = self._pcm[self._ai:self._ai + step]
            start_us = self._ai // 4 * 1_000_000 // 48000
            if not self._ainput.sendAudioBuffer(QAudioBuffer(QByteArray(chunk), self._afmt, start_us)):
                return
            self._ai += len(chunk)
            self._stall.start(STALL_MS)
        self._maybe_stop()

    def _maybe_stop(self) -> None:
        """Encerra a gravação quando todos os quadros e todo o áudio foram enviados."""
        if self._rec is None or self._i < len(self.images):
            return
        if self._ainput is not None and self._ai < len(self._pcm):
            return
        if self._stopping:
            return
        self._stopping = True
        self.progress.emit(99)
        self._rec.stop()

    def _on_state(self, state) -> None:
        if state == QMediaRecorder.RecorderState.StoppedState and self._i >= len(self.images) and not self._finished \
                and (self._ainput is None or self._ai >= len(self._pcm)):
            self._finish()

    def _on_error(self, error, message: str) -> None:
        if self._finished:
            return
        if self._attempts:
            nxt = self._attempts.pop(0)
            log.warning("mp4: %s%s falhou (%s); tentando %s%s", self.codec_used, "+áudio" if self.audio_used else "",
                        message, nxt[0], "+áudio" if nxt[1] else "")
            QTimer.singleShot(0, lambda: self._launch(*nxt))
            return
        self._fail(message or str(error))

    def _finish(self) -> None:
        self._finished = True
        self._stall.stop()
        p = Path(self.path)
        if not p.is_file() or p.stat().st_size == 0:
            self._finished = False
            self._fail("o arquivo de vídeo não foi criado")
            return
        self.progress.emit(100)
        self._teardown()
        self.done.emit(self.path)

    def _fail(self, msg: str) -> None:
        if self._finished:
            return
        self._finished = True
        self._stall.stop()
        self._teardown()
        self.failed.emit(msg)
