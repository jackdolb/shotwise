"""Shotwise - ponto de entrada."""
import os
import sys
import tempfile

# Garante que o pacote seja encontrado mesmo ao executar de outra pasta.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
# instalador "modo Python": PySide6 e numpy ficam na pasta libs, ao lado do programa
_LIBS = os.path.join(_HERE, "libs")
if os.path.isdir(_LIBS):
    sys.path.insert(1, _LIBS)

from shotwise import logsetup  # primeiro: assim erros de importação também vão para o log

log = logsetup.setup()

try:
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

    from shotwise import APP_NAME, __version__
    from shotwise.app import ShotwiseApp
    from shotwise.i18n import tr
    from shotwise.icons import app_icon
    from shotwise.theme import apply_theme, follow_system
except Exception:  # noqa: BLE001 - registra e avisa em vez de fechar em silêncio
    log.critical("Falha ao importar os módulos", exc_info=True)
    logsetup.show_fatal("O Shotwise não conseguiu iniciar (falha ao carregar os componentes).")
    sys.exit(1)


OPEN_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".shotwin", ".mp4", ".gif")
PIPE_NAME = "ShotwiseOpenFile"


def _file_args(args) -> list[str]:
    """Só caminhos de arquivos existentes com extensão de imagem/projeto (máx. 10)."""
    out = []
    for a in args:
        if a.lower().endswith(OPEN_EXTS) and os.path.isfile(a):
            out.append(os.path.abspath(a))
    return out[:10]


def _send_to_running(files: list[str]) -> bool:
    from PySide6.QtNetwork import QLocalSocket

    sock = QLocalSocket()
    sock.connectToServer(PIPE_NAME)
    if not sock.waitForConnected(1500):
        return False
    sock.write("\n".join(files).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1500)
    sock.disconnectFromServer()
    return True


def _start_open_server(controller):
    from PySide6.QtNetwork import QLocalServer

    server = QLocalServer()
    QLocalServer.removeServer(PIPE_NAME)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)     # só o próprio usuário

    def on_connection():
        while server.hasPendingConnections():
            sock = server.nextPendingConnection()
            sock.waitForReadyRead(500)
            data = bytes(sock.readAll())[:8192].decode("utf-8", "ignore")
            sock.disconnectFromServer()
            for f in _file_args(data.split("\n")):
                QTimer.singleShot(0, lambda f=f: controller.open_path(f))

    server.newConnection.connect(on_connection)
    server.listen(PIPE_NAME)
    return server


def _retire_legacy_instance() -> None:
    """Se o ShotWin antigo (até a 1.7) ainda estiver aberto, pede que ele feche e espera um pouco."""
    if sys.platform != "win32":
        return
    import ctypes
    import time

    k32 = ctypes.windll.kernel32
    k32.OpenMutexW.restype = ctypes.c_void_p
    k32.OpenEventW.restype = ctypes.c_void_p
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    k32.SetEvent.argtypes = [ctypes.c_void_p]

    def running() -> bool:
        h = k32.OpenMutexW(0x00100000, False, "ShotWinSingleInstance")
        if h:
            k32.CloseHandle(h)
        return bool(h)

    if not running():
        return
    ev = k32.OpenEventW(0x0002, False, "Local\\ShotWinQuit")
    if ev:
        k32.SetEvent(ev)
        k32.CloseHandle(ev)
    for _ in range(24):
        if not running():
            return
        time.sleep(0.25)


def _install_qt_translations(app) -> None:
    """Textos padrão do Qt (janela de cores, diálogos de arquivo, botões) no idioma escolhido nas configurações."""
    try:
        from PySide6.QtCore import QLibraryInfo, QTranslator
        from shotwise.i18n import language
        code = {"pt": "pt_BR", "es": "es", "en": "en"}.get(language(), "en")
        path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        for name in ("qtbase", "qt"):
            t = QTranslator(app)
            if t.load(f"{name}_{code}", path):
                app.installTranslator(t)
                app._qt_translators = getattr(app, "_qt_translators", []) + [t]
    except Exception:  # noqa: BLE001 - tradução do Qt é opcional
        log.debug("falha ao carregar as traduções do Qt", exc_info=True)


def main() -> int:
    log.info("Shotwise %s", __version__)
    restarted = "--restarted" in sys.argv          # reinício pedido pelo próprio app (troca de idioma)
    sys.argv = [a for a in sys.argv if a != "--restarted"]
    logsetup.install_qt_handler()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)   # continua na bandeja sem janelas abertas
    app.setWindowIcon(app_icon(128))
    _install_qt_translations(app)
    from shotwise.config import Config
    apply_theme(app, Config.load().theme)

    # Instância única: dois Shotwise disputariam os mesmos atalhos globais.
    _retire_legacy_instance()
    lock = QLockFile(os.path.join(tempfile.gettempdir(), "shotwin.lock"))
    lock.setStaleLockTime(0)
    files = _file_args(sys.argv[1:])
    if not lock.tryLock(10000 if restarted else 100):     # no reinício, espera o processo anterior sair
        if files and _send_to_running(files):       # "Abrir com": entrega a imagem ao Shotwise que já está aberto
            return 0
        QMessageBox.information(None, APP_NAME, tr("O Shotwise já está em execução (veja o ícone na bandeja)."))
        return 0

    # Mutex nomeado: o instalador/desinstalador usa o nome para saber se o Shotwise está aberto.
    if sys.platform == "win32":
        import ctypes

        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = ctypes.c_void_p
        _mutex = k32.CreateMutexW(None, False, "ShotwiseSingleInstance")  # noqa: F841
        # Evento nomeado: o instalador/desinstalador o aciona para pedir que o Shotwise se encerre sozinho.
        k32.CreateEventW.restype = ctypes.c_void_p
        k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        _quit_event = k32.CreateEventW(None, True, False, "Local\\ShotwiseQuit")
    else:
        k32 = _quit_event = None

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(None, APP_NAME, tr("A bandeja do sistema não está disponível."))

    try:
        controller = ShotwiseApp(app)  # noqa: F841 - mantém a referência viva
    except Exception:  # noqa: BLE001
        log.critical("Falha ao iniciar o aplicativo", exc_info=True)
        logsetup.show_fatal(tr("O Shotwise não conseguiu iniciar."))
        return 1
    follow_system(app, lambda: controller.cfg.theme)
    server = _start_open_server(controller)     # noqa: F841 - mantém a referência viva
    for f in files:
        QTimer.singleShot(0, lambda f=f: controller.open_path(f))
    if getattr(controller, "hotkeys_ok", True):      # não cobre o aviso de atalho em conflito
        controller.tray.showMessage(
            APP_NAME,
            tr("Em execução.") + "\n" + tr("Use {key} para capturar uma área.").format(key=controller.cfg.hotkey_area),
        )
    if _quit_event:
        quit_timer = QTimer()
        quit_timer.setInterval(500)

        def _check_quit_request():
            if k32.WaitForSingleObject(_quit_event, 0) == 0:     # sinalizado pelo instalador
                quit_timer.stop()
                log.info("Encerramento solicitado pelo instalador")
                controller.quit()

        quit_timer.timeout.connect(_check_quit_request)
        quit_timer.start()
    code = app.exec()
    lock.unlock()
    log.info("Shotwise encerrado (código %s)", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
