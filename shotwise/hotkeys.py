"""Atalhos globais no Windows (RegisterHotKey).

Em outros sistemas o gerenciador existe, mas não registra nada; assim o
restante do código pode ser importado e testado em qualquer plataforma.
"""
from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

IS_WINDOWS = sys.platform == "win32"

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY = 0x0312

_MOD_NAMES = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT,
    "meta": MOD_WIN, "win": MOD_WIN,
}
_SPECIAL_VK = {
    "print": 0x2C, "prtsc": 0x2C, "printscreen": 0x2C, "prtscn": 0x2C, "pause": 0x13, "ins": 0x2D, "insert": 0x2D,
    "del": 0x2E, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pgup": 0x21, "pgdown": 0x22, "space": 0x20,
}


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """'Ctrl+Shift+4' -> (modificadores, código de tecla virtual)."""
    mods, vk = 0, None
    for part in (p.strip() for p in text.split("+") if p.strip()):
        low = part.lower()
        if low in _MOD_NAMES:
            mods |= _MOD_NAMES[low]
        elif low in _SPECIAL_VK:
            vk = _SPECIAL_VK[low]
        elif len(low) == 1 and low.isalnum():
            vk = ord(low.upper())
        elif low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 24:
            vk = 0x70 + int(low[1:]) - 1
        else:
            return None
    if vk is None:
        return None
    # sem modificador só vale para teclas que não digitam nada (Print Screen, F1–F24, Pause...);
    # letras, números e afins sozinhos tomariam a digitação do sistema inteiro.
    if mods == 0 and vk not in (0x2C, 0x13) and not 0x70 <= vk <= 0x87:
        return None
    return mods, vk


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey: Callable[[int], None]):
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (API do Qt)
        if bytes(event_type) == b"windows_generic_MSG":
            import ctypes
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self._on_hotkey(int(msg.wParam))
                return True, 0
        return False, 0


class HotkeyManager:
    def __init__(self):
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._next_id = 1
        self._filter: _Filter | None = None
        self.last_error = 0          # código do Windows na última falha (1409 = já usado por outro programa)

    def register(self, text: str, callback: Callable[[], None]) -> bool:
        """Registra um atalho. Retorna False se inválido ou já em uso."""
        if not IS_WINDOWS:
            return False
        parsed = parse_hotkey(text)
        if parsed is None:
            return False
        import ctypes

        mods, vk = parsed
        hk_id = self._next_id
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if not user32.RegisterHotKey(None, hk_id, mods | MOD_NOREPEAT, vk):
            self.last_error = ctypes.get_last_error()
            return False
        self._next_id += 1
        self._callbacks[hk_id] = callback
        if self._filter is None:
            self._filter = _Filter(self._dispatch)
            QCoreApplication.instance().installNativeEventFilter(self._filter)
        return True

    def unregister_all(self) -> None:
        if not IS_WINDOWS:
            return
        import ctypes

        for hk_id in list(self._callbacks):
            ctypes.windll.user32.UnregisterHotKey(None, hk_id)
        self._callbacks.clear()

    def _dispatch(self, hk_id: int) -> None:
        cb = self._callbacks.get(hk_id)
        if cb:
            cb()
