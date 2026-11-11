"""Utilidades do Windows via ctypes: janela ativa e ponteiro do mouse. Fora do Windows, retornam None."""
from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QPoint, QRect, QRectF
from PySide6.QtGui import QImage, QPainter

IS_WINDOWS = sys.platform == "win32"
_SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def active_window_rect() -> QRect | None:
    """Retângulo (pixels reais da tela virtual) da janela em primeiro plano, sem a sombra invisível."""
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.IsIconic.argtypes = [ctypes.c_void_p]
        user32.GetClassNameW.argtypes = [ctypes.c_void_p, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
        dwm.DwmGetWindowAttribute.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        hwnd = user32.GetForegroundWindow()
        if not hwnd or user32.IsIconic(hwnd):
            return None
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value in _SKIP_CLASSES:
            return None
        rc = wintypes.RECT()
        # DWMWA_EXTENDED_FRAME_BOUNDS = 9: limites visíveis (GetWindowRect inclui bordas invisíveis no Win10/11)
        if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rc), ctypes.sizeof(rc)) != 0:
            if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
                return None
        r = QRect(rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top)
        return r if r.width() >= 8 and r.height() >= 8 else None
    except Exception:  # noqa: BLE001 - qualquer falha de API = sem janela
        return None


class CursorSnapshot:
    """Imagem do ponteiro do mouse, o ponto ativo (hotspot) e a posição, tudo em pixels reais."""

    def __init__(self, image: QImage, hotspot: QPoint, pos: QPoint):
        self.image = image
        self.hotspot = hotspot
        self.pos = pos


def grab_cursor() -> CursorSnapshot | None:
    if not IS_WINDOWS:
        return None
    try:
        return _grab_cursor_win()
    except Exception:  # noqa: BLE001
        return None


def _grab_cursor_win() -> CursorSnapshot | None:  # pragma: no cover - depende do Windows
    import ctypes
    from ctypes import wintypes

    import numpy as np

    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    vp = ctypes.c_void_p

    class CURSORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hCursor", vp),
                    ("ptScreenPos", wintypes.POINT)]

    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                    ("hbmMask", vp), ("hbmColor", vp)]

    class BITMAP(ctypes.Structure):
        _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG), ("bmHeight", wintypes.LONG),
                    ("bmWidthBytes", wintypes.LONG), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                    ("bmBits", vp)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
    user32.GetIconInfo.argtypes = [vp, ctypes.POINTER(ICONINFO)]
    user32.DrawIconEx.argtypes = [vp, ctypes.c_int, ctypes.c_int, vp, ctypes.c_int, ctypes.c_int, wintypes.UINT,
                                  vp, wintypes.UINT]
    gdi32.GetObjectW.argtypes = [vp, ctypes.c_int, vp]
    gdi32.DeleteObject.argtypes = [vp]
    gdi32.CreateCompatibleDC.argtypes = [vp]
    gdi32.CreateCompatibleDC.restype = vp
    gdi32.CreateDIBSection.argtypes = [vp, vp, wintypes.UINT, ctypes.POINTER(vp), vp, wintypes.DWORD]
    gdi32.CreateDIBSection.restype = vp
    gdi32.SelectObject.argtypes = [vp, vp]
    gdi32.SelectObject.restype = vp
    gdi32.DeleteDC.argtypes = [vp]

    ci = CURSORINFO()
    ci.cbSize = ctypes.sizeof(ci)
    if not user32.GetCursorInfo(ctypes.byref(ci)) or not (ci.flags & 1) or not ci.hCursor:   # 1 = CURSOR_SHOWING
        return None
    ii = ICONINFO()
    if not user32.GetIconInfo(ci.hCursor, ctypes.byref(ii)):
        return None
    try:
        bm = BITMAP()
        src = ii.hbmColor or ii.hbmMask
        gdi32.GetObjectW(src, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, (bm.bmHeight if ii.hbmColor else bm.bmHeight // 2)
        if not (0 < w <= 256 and 0 < h <= 256):
            return None
        hot = QPoint(int(ii.xHotspot), int(ii.yHotspot))
    finally:
        if ii.hbmColor:
            gdi32.DeleteObject(ii.hbmColor)
        if ii.hbmMask:
            gdi32.DeleteObject(ii.hbmMask)

    hdc = gdi32.CreateCompatibleDC(None)
    if not hdc:
        return None
    try:
        hdr = BITMAPINFOHEADER()
        hdr.biSize, hdr.biWidth, hdr.biHeight = ctypes.sizeof(hdr), w, -h      # altura negativa = de cima para baixo
        hdr.biPlanes, hdr.biBitCount, hdr.biCompression = 1, 32, 0
        bits = vp()
        dib = gdi32.CreateDIBSection(hdc, ctypes.byref(hdr), 0, ctypes.byref(bits), None, 0)
        if not dib or not bits.value:
            return None
        old = gdi32.SelectObject(hdc, dib)
        try:
            shots = []
            for fill in (0x00, 0xFF):          # desenha sobre preto e sobre branco para recuperar a transparência
                ctypes.memset(bits, fill, w * h * 4)
                user32.DrawIconEx(hdc, 0, 0, ci.hCursor, w, h, 0, None, 3)      # 3 = DI_NORMAL
                gdi32.GdiFlush()
                shots.append(np.frombuffer(ctypes.string_at(bits, w * h * 4), np.uint8).reshape(h, w, 4)[..., :3]
                             .astype(np.float32))
        finally:
            gdi32.SelectObject(hdc, old)
            gdi32.DeleteObject(dib)
    finally:
        gdi32.DeleteDC(hdc)
    black, white = shots
    alpha = np.clip(1.0 - (white - black).mean(axis=2) / 255.0, 0.0, 1.0)
    safe = np.maximum(alpha, 1e-3)[..., None]
    rgb = np.clip(black / safe, 0, 255)
    out = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)            # B, G, R, A
    img = QImage(out.data, w, h, w * 4, QImage.Format.Format_ARGB32).copy()
    return CursorSnapshot(img, hot, QPoint(ci.ptScreenPos.x, ci.ptScreenPos.y))


def mouse_pressed() -> bool:
    """True se o botão esquerdo do mouse está pressionado (Windows)."""
    if not IS_WINDOWS:
        return False
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
    except Exception:  # noqa: BLE001 - só enfeite visual
        return False


def draw_cursor(image: QImage, snap: CursorSnapshot | None, origin: QPoint,
                highlight: bool = False, pressed: bool = False) -> QImage:
    """Desenha o ponteiro sobre a imagem. `origin` = posição (pixels reais) do canto superior esquerdo da imagem.
    Com `highlight`, o ponteiro é ampliado e ganha um halo amarelo; `pressed` acrescenta um anel de clique."""
    if snap is None or snap.image.isNull():
        return image
    x = snap.pos.x() - snap.hotspot.x() - origin.x()
    y = snap.pos.y() - snap.hotspot.y() - origin.y()
    scale = 1.6 if highlight else 1.0
    if highlight:
        x = snap.pos.x() - origin.x() - snap.hotspot.x() * scale
        y = snap.pos.y() - origin.y() - snap.hotspot.y() * scale
    w, h = snap.image.width() * scale, snap.image.height() * scale
    if x >= image.width() or y >= image.height() or x + w <= 0 or y + h <= 0:
        return image
    out = image.convertToFormat(QImage.Format.Format_ARGB32) if not image.hasAlphaChannel() else image.copy()
    p = QPainter(out)
    if highlight:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QPen

        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(snap.pos.x() - origin.x(), snap.pos.y() - origin.y())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 214, 0, 90))
        p.drawEllipse(c, 22, 22)
        if pressed:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 80, 0, 230), 4))
            p.drawEllipse(c, 16, 16)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(QRectF(x, y, w, h), snap.image)
    else:
        p.drawImage(x, y, snap.image)
    p.end()
    return out


def exclude_from_capture(widget) -> None:
    """Esconde a janela das capturas de tela (WDA_EXCLUDEFROMCAPTURE, Windows 10 2004+); ignora erros."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        ctypes.windll.user32.SetWindowDisplayAffinity(ctypes.c_void_p(int(widget.winId())), 0x11)
    except Exception:  # noqa: BLE001 - só um reforço; a barra já fica fora da área gravada
        logging.getLogger("shotwise").debug("SetWindowDisplayAffinity indisponível", exc_info=True)
