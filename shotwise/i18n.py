"""Tradução da interface (português, inglês e espanhol).

O texto-fonte é o português: `tr("Texto em português")` devolve a tradução do idioma escolhido nas
configurações (ou o próprio texto se não houver). O idioma vale ao iniciar o aplicativo."""
from __future__ import annotations

from .i18n_data import LANGUAGES, T

_lang: str | None = None


def language() -> str:
    global _lang
    if _lang is None:
        try:
            from .config import Config
            _lang = Config.load().language
        except Exception:  # noqa: BLE001 - o idioma nunca pode impedir o programa de abrir
            _lang = "auto"
        _lang = _resolve(_lang)
    return _lang


def _resolve(code: str) -> str:
    """'auto' segue o idioma do Windows; códigos desconhecidos viram português."""
    if code == "auto":
        try:
            import locale
            from PySide6.QtCore import QLocale
            name = (QLocale.system().name() or locale.getlocale()[0] or "pt").lower()
        except Exception:  # noqa: BLE001
            name = "pt"
        code = "en" if name.startswith("en") else "es" if name.startswith("es") else "pt"
    return code if code in dict(LANGUAGES) else "pt"


def set_language(code: str) -> None:
    global _lang
    _lang = _resolve(code)


def tr(text: str) -> str:
    lang = language()
    if lang == "pt" or not text:
        return text
    key = text.strip()
    entry = T.get(key)
    if entry is None:
        return text
    out = entry[0] if lang == "en" else entry[1]
    start = text.index(key)
    return text[:start] + out + text[start + len(key):]
