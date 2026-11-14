"""Áudio da gravação de vídeo: som do sistema (loopback do Windows) + microfone, misturados em PCM 48 kHz estéreo 16 bits.

- Microfone: Qt (QAudioSource).
- Som do sistema: biblioteca opcional PyAudioWPatch (WASAPI loopback). Sem ela, a gravação segue sem esse som e o app avisa.
- Cada fonte guarda os blocos com o instante de chegada; lacunas viram silêncio (o loopback não entrega dados enquanto
  nada toca), então o áudio fica alinhado ao vídeo. A mistura e a reamostragem são feitas só no fim (numpy)."""
from __future__ import annotations

import logging
import threading
import time

import numpy as np
from PySide6.QtCore import QObject

from .i18n import tr

log = logging.getLogger("shotwise")

OUT_RATE = 48000
OUT_CH = 2
FRAME_BYTES = OUT_CH * 2                 # PCM s16 estéreo
BYTES_PER_MS = OUT_RATE // 1000 * FRAME_BYTES      # 192
GAP_MS = 60                              # lacunas maiores que isso são preenchidas com silêncio


class Track:
    """Uma fonte de áudio: acumula blocos e preenche lacunas com silêncio, usando o instante de chegada."""

    def __init__(self, rate: int, channels: int, sample: str = "s16"):
        self.rate, self.channels, self.sample = rate, max(1, channels), sample
        self.width = 4 if sample == "f32" else 2
        self.frame_bytes = self.width * self.channels
        self.frames = 0
        self._chunks: list[bytes] = []

    def _silence(self, frames: int) -> None:
        if frames > 0:
            self._chunks.append(bytes(frames * self.frame_bytes))
            self.frames += frames

    def feed(self, data: bytes, t_ms: float) -> None:
        n = len(data) // self.frame_bytes
        if n <= 0:
            return
        start_ms = t_ms - n * 1000 / self.rate
        gap_ms = start_ms - self.frames * 1000 / self.rate
        if gap_ms > GAP_MS:
            self._silence(int(gap_ms * self.rate / 1000))
        self._chunks.append(bytes(data[:n * self.frame_bytes]))
        self.frames += n

    def finish(self, end_ms: float) -> None:
        self._silence(int(end_ms * self.rate / 1000) - self.frames)

    def raw(self) -> bytes:
        return b"".join(self._chunks)


def to_stereo48(raw: bytes, rate: int, channels: int, sample: str = "s16") -> np.ndarray:
    """Converte para float32 estéreo a 48 kHz (formato (n, 2), faixa -1..1)."""
    if not raw:
        return np.zeros((0, 2), np.float32)
    ch = max(1, channels)
    if sample == "f32":
        a = np.frombuffer(raw[:len(raw) // 4 * 4], dtype="<f4").astype(np.float32)
    else:
        a = np.frombuffer(raw[:len(raw) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
    a = a[:len(a) // ch * ch].reshape(-1, ch)
    if ch == 1:
        a = np.repeat(a, 2, axis=1)
    elif ch > 2:                                           # surround: pares à esquerda, ímpares à direita
        a = np.stack([a[:, 0::2].mean(axis=1), a[:, 1::2].mean(axis=1)], axis=1)
    if rate != OUT_RATE and len(a) > 1:
        m = int(len(a) * OUT_RATE / rate)
        x = np.arange(m, dtype=np.float64) * (rate / OUT_RATE)
        src = np.arange(len(a), dtype=np.float64)
        a = np.stack([np.interp(x, src, a[:, c]) for c in range(2)], axis=1).astype(np.float32)
    return a


def mix_to_pcm(arrays: list[np.ndarray]) -> bytes:
    """Soma as fontes (com limite para não estourar) e devolve PCM s16 little-endian estéreo 48 kHz."""
    arrays = [a for a in arrays if len(a)]
    if not arrays:
        return b""
    n = max(len(a) for a in arrays)
    out = np.zeros((n, 2), np.float32)
    for a in arrays:
        out[:len(a)] += a
    np.clip(out, -1.0, 1.0, out=out)
    return (out * 32767.0).astype("<i2").tobytes()


def clip_audio(pcm: bytes, srcs: list[int], durations: list[int]) -> bytes:
    """Monta o áudio do clipe editado: para cada quadro, o trecho [src, src+duração) do áudio original.
    O que faltar no original vira silêncio, então o áudio tem sempre a duração exata do vídeo."""
    parts = []
    for s, d in zip(srcs, durations):
        a, b = max(0, int(s)) * BYTES_PER_MS, max(0, int(s) + int(d)) * BYTES_PER_MS
        seg = pcm[a:b]
        if len(seg) < b - a:
            seg += bytes((b - a) - len(seg))
        parts.append(seg)
    return b"".join(parts)


def default_srcs(durations: list[int]) -> list[int]:
    out, t = [], 0
    for d in durations:
        out.append(t)
        t += d
    return out


def _loopback_devices(p, pa) -> list[dict]:
    """Todas as saídas de áudio com loopback (a padrão primeiro). Gravar todas resolve fone de ouvido, headset
    Bluetooth no modo chamada (Teams usa o "dispositivo de comunicação") e saídas que não são a padrão."""
    devs: list[dict] = []
    try:
        devs.append(p.get_default_wasapi_loopback())
    except Exception:  # noqa: BLE001 - sem saída padrão: segue com as demais
        log.debug("audio: sem loopback padrão", exc_info=True)
    seen = {d["index"] for d in devs}
    for lb in p.get_loopback_device_info_generator():
        if lb["index"] not in seen:
            devs.append(lb)
            seen.add(lb["index"])
    return devs


def probe_system_audio(seconds: float = 3.0) -> list[tuple[str, float]]:
    """Escuta todas as saídas por alguns segundos e devolve (nome, pico 0..1) de cada uma. Para o botão de teste."""
    import pyaudiowpatch as pa

    p = pa.PyAudio()
    peaks: dict[str, float] = {}
    streams = []
    try:
        for dev in _loopback_devices(p, pa):
            name = str(dev["name"]).replace(" [Loopback]", "")
            ch, rate = int(dev["maxInputChannels"]), int(dev["defaultSampleRate"])
            if ch < 1 or rate < 8000:
                continue
            peaks[name] = 0.0

            def cb(in_data, _f, _t, _s, key=name):
                a = np.frombuffer(in_data[:len(in_data) // 2 * 2], dtype="<i2")
                if len(a):
                    peaks[key] = max(peaks[key], float(np.abs(a.astype(np.int32)).max()) / 32768.0)
                return (None, pa.paContinue)
            try:
                streams.append(p.open(format=pa.paInt16, channels=ch, rate=rate, input=True,
                                      input_device_index=dev["index"], frames_per_buffer=rate // 20, stream_callback=cb))
            except Exception as e:  # noqa: BLE001
                log.info("audio: teste: não abriu %s: %s", name, e)
                peaks.pop(name, None)
        time.sleep(max(0.5, seconds))
    finally:
        for st in streams:
            try:
                st.stop_stream()
                st.close()
            except Exception:  # noqa: BLE001
                pass
        p.terminate()
    return sorted(peaks.items(), key=lambda kv: -kv[1])


class AudioCapture(QObject):
    """Captura sistema e/ou microfone durante a gravação. ``start()`` abre os dispositivos, ``begin()`` marca o instante
    zero (junto do relógio dos quadros) e ``stop(end_ms)`` devolve o PCM misturado."""

    def __init__(self, system: bool, mic: bool, mic_device: str = "", parent=None):
        super().__init__(parent)
        self.want_system, self.want_mic, self.mic_device = system, mic, mic_device
        self.warnings: list[str] = []
        self._lock = threading.Lock()
        self._t0: float | None = None
        self._tracks: dict[str, Track] = {}
        self._pa = None
        self._streams: list = []
        self._src = self._io = None

    @property
    def active(self) -> bool:
        return bool(self._tracks)

    def _now_ms(self) -> float | None:
        t0 = self._t0
        return None if t0 is None else (time.monotonic() - t0) * 1000.0

    def _feed(self, name: str, data: bytes) -> None:
        t = self._now_ms()
        if t is None:                      # antes do instante zero: descarta
            return
        with self._lock:
            tr_ = self._tracks.get(name)
            if tr_ is not None:
                tr_.feed(data, t)

    # --- abrir -----------------------------------------------------------------------
    def start(self) -> None:
        if self.want_system:
            try:
                self._start_system()
            except Exception as e:  # noqa: BLE001 - qualquer falha do dispositivo vira aviso, sem derrubar o vídeo
                log.warning("audio: sistema indisponível: %s", e)
                self.warnings.append(tr("Não foi possível capturar o som do sistema; o vídeo sairá sem ele."))
                self._close_system()
                for k in [k for k in self._tracks if k.startswith("system")]:
                    self._tracks.pop(k, None)
        if self.want_mic:
            try:
                self._start_mic()
            except Exception as e:  # noqa: BLE001
                log.warning("audio: microfone indisponível: %s", e)
                self.warnings.append(tr("Não foi possível usar o microfone; o vídeo sairá sem ele."))
                self._tracks.pop("mic", None)
                self._close_mic()

    def begin(self) -> None:
        self._t0 = time.monotonic()

    def _start_system(self) -> None:
        try:
            import pyaudiowpatch as pa
        except ImportError:
            self.warnings.append(tr("O som do sistema precisa do componente PyAudioWPatch (somente Windows); o vídeo sairá sem ele."))
            return
        p = pa.PyAudio()
        self._pa = p
        opened = []
        for dev in _loopback_devices(p, pa):
            rate, ch = int(dev["defaultSampleRate"]), int(dev["maxInputChannels"])
            if ch < 1 or rate < 8000:
                continue
            key = f"system:{dev['index']}"
            self._tracks[key] = Track(rate, ch, "s16")

            def cb(in_data, _frames, _time_info, _status, k=key):
                self._feed(k, in_data)
                return (None, pa.paContinue)
            try:
                self._streams.append(p.open(format=pa.paInt16, channels=ch, rate=rate, input=True,
                                            input_device_index=dev["index"], frames_per_buffer=rate // 20,
                                            stream_callback=cb))
                opened.append(str(dev["name"]))
            except Exception as e:  # noqa: BLE001 - uma saída com problema não impede as outras
                log.info("audio: loopback não abriu (%s): %s", dev.get("name"), e)
                self._tracks.pop(key, None)
        if not opened:
            raise RuntimeError("nenhuma saída de áudio pôde ser gravada")
        log.info("audio: gravando o som de: %s", "; ".join(opened))

    def _start_mic(self) -> None:
        from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
        devs = QMediaDevices.audioInputs()
        dev = None
        if self.mic_device:
            dev = next((d for d in devs if d.description() == self.mic_device), None)
        if dev is None:
            dev = QMediaDevices.defaultAudioInput()
        if dev.isNull():
            self.warnings.append(tr("Nenhum microfone encontrado; o vídeo sairá sem ele."))
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(OUT_RATE)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not dev.isFormatSupported(fmt):
            fmt = dev.preferredFormat()
        sf = fmt.sampleFormat()
        if sf == QAudioFormat.SampleFormat.Int16:
            kind = "s16"
        elif sf == QAudioFormat.SampleFormat.Float:
            kind = "f32"
        else:
            raise RuntimeError(f"formato de amostra não suportado ({sf})")
        src = QAudioSource(dev, fmt, self)
        io = src.start()
        if io is None or src.error() != QAudioSource.Error.NoError:
            raise RuntimeError(f"erro ao abrir o microfone ({src.error()})")
        self._tracks["mic"] = Track(fmt.sampleRate(), fmt.channelCount(), kind)
        io.readyRead.connect(lambda: self._feed("mic", bytes(io.readAll())))
        self._src, self._io = src, io

    # --- encerrar -------------------------------------------------------------------------
    def _close_system(self) -> None:
        streams, pa_ = self._streams, self._pa
        self._streams, self._pa = [], None
        for stream in streams:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:  # noqa: BLE001
                log.debug("audio: falha ao fechar o stream", exc_info=True)
        try:
            if pa_ is not None:
                pa_.terminate()
        except Exception:  # noqa: BLE001
            log.debug("audio: falha ao encerrar o PortAudio", exc_info=True)

    def _close_mic(self) -> None:
        src, io = self._src, self._io
        self._src = self._io = None
        if io is not None:
            try:
                data = bytes(io.readAll())
                if data:
                    self._feed("mic", data)
            except RuntimeError:
                pass
        if src is not None:
            try:
                src.stop()
                src.deleteLater()
            except RuntimeError:
                pass

    def cancel(self) -> None:
        self._t0 = None
        self._close_system()
        self._close_mic()
        self._tracks.clear()

    def stop(self, end_ms: float) -> bytes:
        """Fecha os dispositivos e devolve o PCM s16 estéreo 48 kHz misturado, com ``end_ms`` de duração."""
        self._close_mic()
        self._close_system()
        with self._lock:
            tracks = dict(self._tracks)
        arrays = []
        sys_peak, has_sys = 0.0, False
        for k, t in tracks.items():
            t.finish(end_ms)
            a = to_stereo48(t.raw(), t.rate, t.channels, t.sample)
            arrays.append(a)
            if k.startswith("system"):
                has_sys = True
                pk = float(np.abs(a).max()) if len(a) else 0.0
                sys_peak = max(sys_peak, pk)
                log.info("audio: %s: %d quadros, pico %.4f", k, t.frames, pk)
        if has_sys and sys_peak < 1e-3:
            self.warnings.append(tr("O som do sistema foi gravado, mas veio em silêncio. Use Configurações > Vídeo e GIF > "
                                    "Testar som do sistema para ver qual saída está recebendo o áudio."))
        pcm = mix_to_pcm(arrays)
        want = int(end_ms) * BYTES_PER_MS
        return pcm[:want] + bytes(max(0, want - len(pcm))) if pcm else b""
