"""Registro de erros em arquivo (somente biblioteca padrão, para funcionar mesmo se algo falhar ao importar).

Arquivo: %APPDATA%\\Shotwise\\logs\\shotwise.log (rotativo, 3 x 512 KB) e crash.log (falhas fatais do Python/Qt).
O log registra eventos e erros do programa. Ele NÃO grava imagens capturadas nem o texto reconhecido por OCR.
Defina SHOTWIN_DEBUG=1 para um registro mais detalhado.
"""
from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import os
import platform
import sys
import threading
from pathlib import Path

_LOGGER_NAME = "shotwise"
_crash_file = None  # mantém o arquivo aberto durante toda a execução


def log_dir() -> Path:
    from .config import config_dir        # a pasta de configurações já cuida da migração do nome antigo

    d = config_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME)


def setup(version: str = "") -> logging.Logger:
    """Configura o log, captura exceções não tratadas (inclusive em threads) e falhas fatais."""
    global _crash_file
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger
    level = logging.DEBUG if os.environ.get("SHOTWIN_DEBUG") == "1" else logging.INFO
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        fh = logging.handlers.RotatingFileHandler(log_dir() / "shotwise.log", maxBytes=512 * 1024, backupCount=3,
                                                  encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass
    if sys.stderr is not None:                   # com pythonw/--noconsole não há stderr
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())

    def excepthook(exc_type, exc, tb):
        logger.critical("Exceção não tratada", exc_info=(exc_type, exc, tb))

    def thread_hook(args):
        logger.critical("Exceção não tratada na thread %s", getattr(args.thread, "name", "?"),
                        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_hook
    try:
        _crash_file = open(log_dir() / "crash.log", "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(file=_crash_file, all_threads=True)
    except (OSError, RuntimeError, ValueError):
        pass

    logger.info("=== Shotwise %s iniciando · Python %s · %s ===", version or "?", platform.python_version(),
                platform.platform())
    return logger


def install_qt_handler() -> None:
    """Envia avisos e erros internos do Qt para o mesmo arquivo de log."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    logger = get_logger("qt")
    levels = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
              QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}

    def handler(mode, _context, message):
        logger.log(levels.get(mode, logging.INFO), message)

    qInstallMessageHandler(handler)


def show_fatal(message: str) -> None:
    """Mostra um aviso mesmo sem console (Windows) e indica onde está o log."""
    text = f"{message}\n\nDetalhes em:\n{log_dir() / 'shotwise.log'}"
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, text, "Shotwise", 0x10)
            return
        except Exception as exc:  # noqa: BLE001 - último recurso: cai para o stderr
            print(f"MessageBox indisponível: {exc}", file=sys.stderr)
    print(text, file=sys.stderr)
