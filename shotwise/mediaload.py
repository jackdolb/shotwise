"""Abre MP4 e GIF já salvos para editar no player: lê os quadros (e o áudio do MP4) para a memória.

- GIF: Pillow (quadros iguais seguidos são fundidos).
- MP4: o vídeo é lido com QMediaPlayer + QVideoSink (acelerado, sem som) e o áudio com QAudioDecoder (mais rápido que o tempo real).
  Os quadros guardam o instante de cada um, então o resultado mantém a duração e a velocidade originais; para caber na
  memória o vídeo é reduzido (largura máxima) e fica com no máximo os quadros por segundo configurados."""
from __future__ import annotations

import logging
import os

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QImage

log = logging.getLogger("shotwise")

MAX_FILE_BYTES = 1024 * 1024 * 1024        # recusa arquivos maiores que 1 GB
MAX_SECONDS = 900                          # lê no máximo 15 minutos
STALL_MS = 30000
DEFAULT_GIF_MS = 100


def _rgb888(img: QImage, max_width: int) -> QImage:
    if max_width > 0 and img.width() > max_width:
        from PySide6.QtCore import Qt
        img = img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
    return img.convertToFormat(QImage.Format.Format_RGB888)


def load_gif(path: str, max_width: int = 1280, max_bytes: int = 1500 * 1024 * 1024,
             max_frames: int = 6000) -> tuple[list[QImage], list[int], bool]:
    """Devolve (quadros, durações em ms, truncado). Levanta ValueError se o arquivo não for um GIF legível."""
    from PIL import Image, ImageSequence, UnidentifiedImageError
    if os.path.getsize(path) > MAX_FILE_BYTES:
        raise ValueError("arquivo grande demais")
    images: list[QImage] = []
    durations: list[int] = []
    used = 0
    truncated = False
    last_raw = None
    try:
        with Image.open(path) as im:
            if im.format != "GIF":
                raise ValueError("não é um GIF")
            for frame in ImageSequence.Iterator(im):
                dur = int(frame.info.get("duration", DEFAULT_GIF_MS) or 0)
                if dur < 20:                       # navegadores e players tratam duração muito curta como 100 ms
                    dur = DEFAULT_GIF_MS
                rgb = frame.convert("RGB")
                raw = rgb.tobytes()
                if raw == last_raw and durations:  # quadro igual ao anterior: só estende o tempo
                    durations[-1] += dur
                    continue
                last_raw = raw
                w, h = rgb.size
                qi = QImage(raw, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
                qi = _rgb888(qi, max_width)
                used += qi.sizeInBytes()
                if used > max_bytes or len(images) >= max_frames:
                    truncated = True
                    break
                images.append(qi)
                durations.append(dur)
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError(str(exc)) from exc
    if not images:
        raise ValueError("o GIF não tem quadros")
    return images, durations, truncated


class Mp4Loader(QObject):
    """Lê um MP4 em segundo plano. Sinais: ``progress(0..100)``, ``done(imagens, durações, áudio PCM, truncado)``, ``failed(msg)``."""

    progress = Signal(int)
    done = Signal(object, object, object, bool)
    failed = Signal(str)

    def __init__(self, path: str, fps: int = 15, max_width: int = 1280, max_bytes: int = 1500 * 1024 * 1024,
                 parent: QObject | None = None):
        super().__init__(parent)
        self.path = path
        self.min_gap = max(20, 1000 // max(1, fps))
        self.max_width = max_width
        self.max_bytes = max_bytes
        self._images: list[QImage] = []
        self._ts: list[int] = []                 # instante (ms) de cada quadro guardado
        self._used = 0
        self._truncated = False
        self._pcm = bytearray()
        self._finished = False
        self._duration = 0
        self._player = self._sink = self._dec = None
        self._stall = QTimer(self)
        self._stall.setSingleShot(True)
        self._stall.timeout.connect(lambda: self._fail("o vídeo parou de responder durante a leitura"))

    # --- etapa 1: áudio ----------------------------------------------------------
    def start(self) -> None:
        try:
            if os.path.getsize(self.path) > MAX_FILE_BYTES:
                self._fail("arquivo grande demais")
                return
            from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
            fmt = QAudioFormat()
            fmt.setSampleRate(48000)
            fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            dec = QAudioDecoder(self)
            dec.setAudioFormat(fmt)
            dec.setSource(QUrl.fromLocalFile(self.path))
            dec.bufferReady.connect(self._read_audio)
            dec.finished.connect(self._audio_done)
            dec.error.connect(lambda _e: self._audio_done())        # sem faixa de áudio (ou ilegível): segue sem som
            self._dec = dec
            self._stall.start(STALL_MS)
            dec.start()
        except Exception as exc:  # noqa: BLE001
            log.warning("mp4: falha ao iniciar a leitura do áudio: %s", exc)
            self._start_video()

    def _read_audio(self) -> None:
        dec = self._dec
        if dec is None:
            return
        limit = MAX_SECONDS * 192000
        while dec.bufferAvailable():
            buf = dec.read()
            if buf.isValid() and len(self._pcm) < limit:
                self._pcm.extend(bytes(buf.data()))
        self._stall.start(STALL_MS)

    def _audio_done(self) -> None:
        if self._dec is None:
            return
        dec, self._dec = self._dec, None
        try:
            self._read_audio_final(dec)
            dec.stop()
            dec.deleteLater()
        except RuntimeError:
            pass
        self._start_video()

    def _read_audio_final(self, dec) -> None:
        while dec.bufferAvailable():
            buf = dec.read()
            if buf.isValid():
                self._pcm.extend(bytes(buf.data()))

    # --- etapa 2: quadros ----------------------------------------------------------
    def _start_video(self) -> None:
        if self._finished:
            return
        from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
        self._player = QMediaPlayer(self)
        self._sink = QVideoSink(self)
        self._player.setVideoSink(self._sink)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player.durationChanged.connect(lambda d: setattr(self, "_duration", int(d)))
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(lambda _e, msg: self._fail(msg or "formato não suportado"))
        self._player.setSource(QUrl.fromLocalFile(self.path))
        self._player.setPlaybackRate(4.0)             # sem som e sem tela: lê mais rápido que o tempo real
        self._stall.start(STALL_MS)
        self._player.play()

    def _on_frame(self, frame) -> None:
        if self._finished or not frame.isValid():
            return
        self._stall.start(STALL_MS)
        t = int(frame.startTime() / 1000) if frame.startTime() >= 0 else int(self._player.position())
        if self._ts and t - self._ts[-1] < self.min_gap:
            return
        if t > MAX_SECONDS * 1000:
            self._truncated = True
            return
        img = frame.toImage()
        if img.isNull():
            return
        img = _rgb888(img, self.max_width)
        if self._images and img == self._images[-1]:            # igual ao anterior: o quadro anterior dura mais
            return
        if self._used + img.sizeInBytes() > self.max_bytes:
            self._truncated = True
            return
        self._used += img.sizeInBytes()
        self._images.append(img)
        self._ts.append(t)
        if self._duration > 0:
            self.progress.emit(min(99, int(t * 100 / self._duration)))

    def _on_status(self, status) -> None:
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._finish()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._fail("formato não suportado")

    def _finish(self) -> None:
        if self._finished:
            return
        if not self._images:
            self._fail("nenhum quadro de vídeo foi lido")
            return
        self._finished = True
        self._stall.stop()
        t0 = self._ts[0]
        ts = [t - t0 for t in self._ts]
        total = max(self._duration - t0, ts[-1] + 40)
        if self._truncated and len(ts) > 1:                 # parou antes do fim: usa só o que foi lido
            total = ts[-1] + max(40, ts[-1] - ts[-2])
        total = min(total, MAX_SECONDS * 1000)
        durs = [max(1, ts[i + 1] - ts[i]) for i in range(len(ts) - 1)] + [max(40, total - ts[-1])]
        want = sum(durs) * 192
        pcm = bytes(self._pcm[:want]) if self._pcm else b""
        if pcm and len(pcm) < want:
            pcm += bytes(want - len(pcm))
        self._teardown()
        self.progress.emit(100)
        self.done.emit(self._images, durs, pcm, self._truncated)

    def _fail(self, msg: str) -> None:
        if self._finished:
            return
        self._finished = True
        self._stall.stop()
        self._teardown()
        self.failed.emit(msg)

    def cancel(self) -> None:
        self._finished = True
        self._stall.stop()
        self._teardown()

    def _teardown(self) -> None:
        for obj in (self._dec, self._player, self._sink):
            if obj is not None:
                try:
                    if hasattr(obj, "stop"):
                        obj.stop()
                    obj.deleteLater()
                except RuntimeError:
                    pass
        self._dec = self._player = self._sink = None
