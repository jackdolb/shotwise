"""Controlador principal: bandeja do sistema, atalhos e fluxos de captura."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QCursor, QDesktopServices, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon

from .i18n import tr
from . import APP_NAME
from .clipboard import copy_image, copy_text
from .config import apply_install_defaults, Config
from . import library, logsetup
from .dialogs import LibraryDialog
from .editor import EditorWindow, load_image_file
from .pin import PinWindow
from .preview import QuickPreview
from .project import ProjectError, read_project
from .hotkeys import IS_WINDOWS, HotkeyManager
from .icons import app_icon
from .ocr import start_ocr
from .imageutil import np_to_qimage
from .scrollcap import run_scroll_capture
from .selector import RegionSelector
from .recorder import (FrameBorder, GifPreviewDialog, GifRecorder, RecordingBar, default_gif_path, default_video_path,
                       make_grabber)
from .theme import apply_theme
from .winutil import active_window_rect, draw_cursor, exclude_from_capture, grab_cursor
from .settings_dialog import SettingsDialog, ShortcutsDialog, set_autostart


log = logsetup.get_logger("app")


class ShotwiseApp(QObject):
    def __init__(self, qapp: QApplication):
        super().__init__()
        self.qapp = qapp
        self.cfg = Config.load()
        apply_install_defaults(self.cfg)
        self._lang_in_use = self.cfg.language
        if self.cfg.autostart:                      # reescreve a entrada de inicialização (nome e caminho novos)
            try:
                set_autostart(True)
            except OSError:
                log.warning("não foi possível atualizar a inicialização automática", exc_info=True)
        self.hotkeys = HotkeyManager()
        self.editors: list[EditorWindow] = []
        self.pins: list[PinWindow] = []
        self._ocr_jobs: list = []
        self.previews: list[QuickPreview] = []
        self._library_dlg: LibraryDialog | None = None
        self._selector: RegionSelector | None = None
        self._busy = False
        self._recorder: GifRecorder | None = None
        self._rec_kind = "gif"
        self._rec_widgets: list = []
        self._gif_dialogs: list = []
        self._cursor = None
        self._settings_dlg = None
        self._shortcuts_dlg = None

        self.tray = QSystemTrayIcon(app_icon(64), self)
        self._last_gif = ""
        self._tray_action = None
        self.tray.messageClicked.connect(self._tray_message_clicked)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(self._tray_activated)
        self._build_menu()
        self.tray.show()
        self.register_hotkeys(show_ok=False)
        self._update_worker = None
        if self.cfg.update_on_start and (self.cfg.update_repo or self.cfg.update_folder):
            QTimer.singleShot(8000, self._check_update_at_start)       # espera o início terminar

    # ------------------------------------------------------------------
    def _check_update_at_start(self):
        from .updater import UpdateWorker
        c = self.cfg
        loc = c.update_repo if c.update_source == "repo" else c.update_folder
        if not loc:
            return
        w = UpdateWorker(c.update_source, loc, "check", parent=self)
        w.found.connect(self._update_available)
        w.failed.connect(lambda msg: log.info("verificação de atualização falhou: %s", msg))
        self._update_worker = w
        w.start()

    def _update_available(self, info):
        if info is None:
            return
        self._tray_action = self.open_settings
        self._notify(APP_NAME, tr("Nova versão disponível: {v}").format(v=info.version) + "\n"
                              + tr("Clique para abrir Configurações > Sobre."), QSystemTrayIcon.MessageIcon.Information, 8000)

    # ------------------------------------------------------------------
    def _build_menu(self):
        menu = QMenu()
        self.act_full = QAction(tr("Capturar tela inteira"), self)
        self.act_area = QAction(tr("Capturar área"), self)
        self.act_scroll = QAction(tr("Captura com rolagem"), self)
        self.act_full.triggered.connect(lambda: self._delayed(self.capture_fullscreen))
        self.act_area.triggered.connect(lambda: self._delayed(self.capture_area))
        self.act_scroll.triggered.connect(lambda: self._delayed(self.capture_scroll))
        self.act_repeat = QAction(tr("Repetir última área"), self)
        self.act_repeat.triggered.connect(lambda: self._delayed(self.capture_repeat))
        self.act_window = QAction(tr("Capturar janela ativa"), self)
        self.act_window.triggered.connect(lambda: self._delayed(self.capture_window))
        self.act_gif = QAction(tr("Gravar GIF da área"), self)
        self.act_gif.triggered.connect(lambda: self._delayed(self.capture_gif))
        self.act_mp4 = QAction(tr("Gravar vídeo MP4 da área"), self)
        self.act_mp4.triggered.connect(lambda: self._delayed(self.capture_mp4))
        self.act_ocr = QAction(tr("Copiar texto da área (OCR)"), self)
        self.act_ocr.triggered.connect(lambda: self._delayed(self.capture_ocr))
        act_recent = QAction(tr("Capturas recentes (editáveis)…"), self)
        act_recent.triggered.connect(self.open_library)
        act_logs = QAction(tr("Abrir pasta de logs"), self)
        act_logs.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(logsetup.log_dir()))))
        act_folder = QAction(tr("Abrir pasta de capturas"), self)
        act_folder.triggered.connect(self.open_folder)
        act_settings = QAction(tr("Configurações…"), self)
        act_settings.triggered.connect(self.open_settings)
        act_quit = QAction(tr("Sair"), self)
        act_quit.triggered.connect(self.quit)
        for a in (self.act_full, self.act_area, self.act_repeat, self.act_window, self.act_scroll, self.act_gif, self.act_mp4, self.act_ocr):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_recent)
        menu.addSeparator()
        menu.addAction(act_folder)
        menu.addAction(act_logs)
        menu.addAction(act_settings)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self._menu = menu
        self._update_menu_labels()

    def _update_menu_labels(self):
        self.act_full.setText(tr("Capturar tela inteira") + f"\t{self.cfg.hotkey_fullscreen}")
        self.act_area.setText(tr("Capturar área") + f"\t{self.cfg.hotkey_area}")
        self.act_scroll.setText(tr("Captura com rolagem") + f"\t{self.cfg.hotkey_scroll}")
        self.act_repeat.setText(tr("Repetir última área") + f"\t{self.cfg.hotkey_repeat}")
        self.act_window.setText(tr("Capturar janela ativa") + f"\t{self.cfg.hotkey_window}")
        self.act_ocr.setText(tr("Copiar texto da área (OCR)") + f"\t{self.cfg.hotkey_ocr}")
        rec_on = self._recorder is not None
        self.act_gif.setText((tr("Parar gravação") if rec_on else tr("Gravar GIF da área")) + f"\t{self.cfg.hotkey_gif}")
        self.act_mp4.setText((tr("Parar gravação") if rec_on else tr("Gravar vídeo MP4 da área")) + f"\t{self.cfg.hotkey_mp4}")

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._delayed(self.capture_area)

    def register_hotkeys(self, show_ok: bool = True) -> bool:
        """Registra os atalhos globais. Retorna False se algum não pôde ser registrado."""
        self.hotkeys.unregister_all()
        failed = []
        for label, text, cb in (
            (tr("tela inteira"), self.cfg.hotkey_fullscreen, self.capture_fullscreen),
            (tr("área"), self.cfg.hotkey_area, self.capture_area),
            (tr("repetir área"), self.cfg.hotkey_repeat, self.capture_repeat),
            (tr("janela ativa"), self.cfg.hotkey_window, self.capture_window),
            (tr("rolagem"), self.cfg.hotkey_scroll, self.capture_scroll),
            ("OCR", self.cfg.hotkey_ocr, self.capture_ocr),
            ("GIF", self.cfg.hotkey_gif, self.capture_gif),
            ("MP4", self.cfg.hotkey_mp4, self.capture_mp4),
        ):
            if not self.hotkeys.register(text, cb) and IS_WINDOWS:
                failed.append(f"{label} ({text})")
                log.warning("atalho não registrado: %s (%s) - erro do Windows %s", label, text, self.hotkeys.last_error)
        self.hotkeys_ok = not failed
        if failed:
            self._notify(APP_NAME, tr("Não foi possível registrar o(s) atalho(s):") + " " + ", ".join(failed)
                                  + tr(".\nEles estão em uso por outro programa (veja se o ShareX ou outro programa de captura "
                                    "ainda está aberto na bandeja) ou foram reservados pelo Windows."),
                                  QSystemTrayIcon.MessageIcon.Warning, 7000)
        elif show_ok and IS_WINDOWS:
            self._notify(APP_NAME, tr("Atalhos atualizados."), QSystemTrayIcon.MessageIcon.Information, 2500)
        return not failed

    # ------------------------------------------------------------------
    # capturas
    # ------------------------------------------------------------------
    def _delayed(self, fn, ms: int = 260):
        """Espera o menu da bandeja sumir antes de capturar."""
        QTimer.singleShot(ms, fn)

    @staticmethod
    def _grab_screen(screen) -> QImage:
        img = screen.grabWindow(0).toImage()
        img.setDevicePixelRatio(1.0)
        return img

    def _grab_all(self):
        return [(s, self._grab_screen(s)) for s in QGuiApplication.screens()]

    def capture_fullscreen(self):
        log.info("captura: tela inteira")
        if self._busy:
            return
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        cursor = grab_cursor() if self.cfg.include_cursor else None
        self._deliver(draw_cursor(self._grab_screen(screen), cursor, screen.geometry().topLeft()))

    def capture_window(self):
        """Captura a janela em primeiro plano (sem a sombra invisível das bordas)."""
        log.info("captura: janela ativa")
        if self._busy:
            return
        if not IS_WINDOWS:
            QMessageBox.information(None, APP_NAME, tr("A captura da janela ativa só está disponível no Windows."))
            return
        rect = active_window_rect()
        if rect is None:
            self._notify(APP_NAME, tr("Não encontrei uma janela ativa para capturar."),
                                  QSystemTrayIcon.MessageIcon.Information, 3000)
            return
        center = rect.center()
        screen = QGuiApplication.primaryScreen()
        for s in QGuiApplication.screens():
            g = s.geometry()
            native = QRect(g.x(), g.y(), round(g.width() * s.devicePixelRatio()), round(g.height() * s.devicePixelRatio()))
            if native.contains(center):
                screen = s
                break
        origin = screen.geometry().topLeft()
        frozen = self._grab_screen(screen)
        physical = rect.translated(-origin).intersected(frozen.rect())
        if physical.width() < 4 or physical.height() < 4:
            return
        cursor = grab_cursor() if self.cfg.include_cursor else None
        self._deliver(draw_cursor(frozen.copy(physical), cursor, origin + physical.topLeft()))

    def capture_area(self):
        self._start_selection(tr("Arraste para selecionar a área  •  Esc cancela"), self._area_selected, annotate=True)

    def capture_scroll(self):
        if not IS_WINDOWS:
            QMessageBox.information(None, APP_NAME, tr("A captura com rolagem só está disponível no Windows."))
            return
        self._start_selection(tr("Selecione a área que vai rolar (sem a barra de abas/título)  •  Esc cancela"),
                              self._scroll_selected)

    # --- gravação de GIF ---------------------------------------------------
    def capture_gif(self):
        """Primeira vez: escolhe a área e grava. Com a gravação em andamento: para."""
        self._capture_recording("gif")

    def capture_mp4(self):
        """Igual ao GIF, mas grava um vídeo MP4."""
        self._capture_recording("mp4")

    def _capture_recording(self, kind: str):
        if self._recorder is not None:
            self._recorder.stop("user")
            return
        if kind == "mp4":
            from .videoenc import AVAILABLE
            if not AVAILABLE:
                QMessageBox.warning(None, APP_NAME, tr("O componente de vídeo (QtMultimedia) não está disponível nesta instalação."))
                return
        self._rec_kind = kind
        hint = tr("Arraste para selecionar a área do vídeo  •  Esc cancela") if kind == "mp4" \
            else tr("Arraste para selecionar a área do GIF  •  Esc cancela")
        self._start_selection(hint, self._gif_selected)

    def _gif_selected(self, screen, frozen: QImage, logical: QRect, physical: QRect):
        self._selector = None                      # _busy continua ligado até o fim da gravação
        # dá tempo para o overlay de seleção sumir antes do primeiro quadro
        QTimer.singleShot(350, lambda: self._start_recording(screen, logical, physical))

    def _start_recording(self, screen, logical: QRect, physical: QRect):
        c = self.cfg
        grab = make_grabber(screen, logical, physical, c.include_cursor, c.gif_cursor_highlight)
        if self._rec_kind == "mp4":
            audio = None
            if c.mp4_audio_system or c.mp4_audio_mic:
                from .audiocap import AudioCapture
                audio = AudioCapture(c.mp4_audio_system, c.mp4_audio_mic, c.mp4_mic_device, self)
            rec = GifRecorder(grab, c.mp4_fps, c.mp4_max_seconds, c.mp4_max_width, self,
                              max_bytes=c.mp4_max_memory_mb * 1024 * 1024, audio=audio)
            max_seconds = c.mp4_max_seconds
        else:
            rec = GifRecorder(grab, c.gif_fps, c.gif_max_seconds, c.gif_max_width, self)
            max_seconds = c.gif_max_seconds
        geo = screen.geometry()
        region = QRect(geo.topLeft() + logical.topLeft(), logical.size())
        border = FrameBorder(region)
        bar = RecordingBar(region, geo, max_seconds * 1000)
        for w in (border, bar):
            w.show()
            exclude_from_capture(w)
        self._rec_widgets = [border, bar]
        self._recorder = rec
        rec.tick.connect(lambda t, _n: bar.set_elapsed(t))
        rec.stopped.connect(self._recording_stopped)
        bar.stop_clicked.connect(lambda: rec.stop("user"))
        bar.cancel_clicked.connect(lambda: self._cancel_recording())
        self._update_menu_labels()
        QTimer.singleShot(120, rec.start)          # a barra e a moldura já estão na tela

    def _end_recording_ui(self):
        for w in self._rec_widgets:
            w.close()
            w.deleteLater()
        self._rec_widgets = []
        self._recorder = None
        self._busy = False
        self._update_menu_labels()

    def _cancel_recording(self):
        rec = self._recorder
        if rec is None:
            return
        try:
            rec.stopped.disconnect(self._recording_stopped)
        except (RuntimeError, TypeError):
            pass
        rec.cancel()
        self._end_recording_ui()

    def _recording_stopped(self, reason: str):
        rec = self._recorder
        self._end_recording_ui()
        if rec is None or not rec.images:
            return
        if reason == "memory":
            self._notify(APP_NAME, tr("A gravação parou: o limite de memória foi atingido."),
                                  QSystemTrayIcon.MessageIcon.Warning, 4000)
        if rec.audio is not None and rec.audio.warnings:
            self._notify(APP_NAME, " ".join(dict.fromkeys(rec.audio.warnings)),
                                  QSystemTrayIcon.MessageIcon.Warning, 6000)
        self._show_player(rec.images, rec.durations(), self._rec_kind, rec.audio_pcm)

    def _show_player(self, images, durations, kind: str, audio: bytes = b""):
        """Abre o player/editor de vídeo ou GIF com os quadros dados."""
        c = self.cfg
        path_fn = (lambda: default_video_path(c.save_dir, c.file_name_pattern, c.save_by_month)) if kind == "mp4" \
            else (lambda: default_gif_path(c.save_dir, c.file_name_pattern, c.save_by_month))
        dlg = GifPreviewDialog(images, durations, path_fn, kind=kind, audio=audio)
        dlg.saved.connect(self._gif_saved)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._gif_dialogs.append(dlg)
        dlg.destroyed.connect(lambda _=None, d=dlg: self._gif_dialogs.remove(d) if d in self._gif_dialogs else None)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _notify(self, title: str, msg: str, icon=QSystemTrayIcon.MessageIcon.Information, ms: int = 10000):
        """Notificação da bandeja. Com 'Ocultar notificações' ligado, só os avisos de erro/atenção aparecem."""
        if self.cfg.hide_notifications and icon in (QSystemTrayIcon.MessageIcon.Information, QSystemTrayIcon.MessageIcon.NoIcon):
            return
        self.tray.showMessage(title, msg, icon, ms)

    def _tray_message_clicked(self):
        action, self._tray_action = self._tray_action, None
        if action is not None:
            action()
            dlg = getattr(self, "_settings_dlg", None)
            if dlg is not None:
                dlg.tabs.setCurrentIndex(dlg.tabs.count() - 1)       # aba Sobre
            return
        self._open_last_gif()

    def _open_last_gif(self):
        if self._last_gif and Path(self._last_gif).exists():
            from .recorder import reveal_in_folder
            reveal_in_folder(self._last_gif)
            self._last_gif = ""

    def _gif_saved(self, path: str):
        from PySide6.QtCore import QMimeData

        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(path)])          # permite colar o arquivo no Teams, e-mail, etc.
        QApplication.clipboard().setMimeData(md)
        self._last_gif = path
        self._tray_action = None
        msg = tr("Vídeo salvo e copiado: {name}") if path.lower().endswith(".mp4") else tr("GIF salvo e copiado: {name}")
        self._notify(APP_NAME, msg.format(name=Path(path).name) + "\n" + str(Path(path).parent),
                              QSystemTrayIcon.MessageIcon.Information, 6000)

    def capture_ocr(self):
        self._start_selection(tr("Selecione a área com o texto para copiar  •  Esc cancela"), self._ocr_selected)

    def _start_selection(self, hint: str, on_selected, on_cancelled=None, annotate: bool = False):
        if self._busy:
            return
        if QApplication.activeModalWidget() is not None:
            # uma janela modal (ex.: "Salvar como") bloquearia o mouse e o teclado do overlay de seleção
            log.warning("seleção recusada: há uma janela modal aberta")
            self._notify(APP_NAME, tr("Feche a janela aberta (caixa de diálogo) antes de selecionar uma área."),
                                  QSystemTrayIcon.MessageIcon.Warning, 4000)
            return
        self._busy = True
        self._cursor = grab_cursor() if self.cfg.include_cursor else None      # ponteiro no momento do atalho
        frozen = self._grab_all()
        self._selector = RegionSelector(frozen, hint, on_selected, on_cancelled or self._selection_cancelled,
                                        adjustable=self.cfg.adjust_selection, annotatable=annotate)
        self._selector.start()

    def _selection_cancelled(self):
        self._selector = None
        self._busy = False

    def _remember(self, screen, logical: QRect, mode: str):
        """Guarda a área para o atalho 'repetir última área' (coordenadas relativas ao monitor)."""
        self.cfg.last_region = [screen.name(), max(0, logical.x()), max(0, logical.y()), logical.width(),
                                logical.height(), mode]
        self.cfg.save()

    def _area_selected(self, screen, frozen: QImage, logical: QRect, physical: QRect):
        annotations = getattr(self._selector, "annotations", None)
        action = getattr(self._selector, "action", "") or None
        self._selector = None
        self._busy = False
        self._remember(screen, logical, "area")
        origin = screen.geometry().topLeft() + physical.topLeft()
        image = draw_cursor(frozen.copy(physical), getattr(self, "_cursor", None), origin)
        if annotations is not None:
            self._deliver_annotated(image, annotations, action)
        else:
            self._deliver(image, action)

    def _deliver_annotated(self, image: QImage, pd, mode: str | None = None):
        """Entrega uma captura que recebeu anotações antes de ser confirmada."""
        if pd.layers and pd.layers[0][0].size() == image.size():
            pd.layers[0] = (image, pd.layers[0][1], pd.layers[0][2])      # a base passa a incluir o ponteiro
        if (mode or self.cfg.after_capture) == "editor":
            ed = self.open_editor(None, project=pd)
            ed._exported = False                    # é uma captura nova: ainda não foi copiada nem salva
            ed.select_tool("arrow")
            return
        from .annotations import AnnotScene
        from .project import build_scene
        self._deliver(build_scene(pd, AnnotScene()).render_image(), mode)

    def _prune_ocr_jobs(self):
        alive = []
        for job in self._ocr_jobs:
            try:
                if job[0].isRunning():
                    alive.append(job)
            except RuntimeError:          # thread já destruída
                pass
        self._ocr_jobs[:] = alive

    def _ocr_selected(self, screen, frozen: QImage, logical: QRect, physical: QRect):
        self._selector = None
        self._busy = False
        img = frozen.copy(physical)
        big = max(img.width(), img.height())
        if 0 < big < 1000:                         # o OCR lê melhor texto maior
            f = min(3.0, 1200 / big)
            img = img.scaled(round(img.width() * f), round(img.height() * f), Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        info = QSystemTrayIcon.MessageIcon.Information
        self._prune_ocr_jobs()

        def done(text: str, err: str):
            if err:
                self._notify(APP_NAME, err, QSystemTrayIcon.MessageIcon.Warning, 6000)
            elif not text.strip():
                self._notify(APP_NAME, tr("Nenhum texto foi reconhecido nesta área."), info, 3000)
            else:
                copy_text(text)
                short = text.strip().replace("\n", " ")
                short = short[:80] + ("…" if len(short) > 80 else "")
                self._notify(APP_NAME, tr("Texto copiado: {short}").format(short=short), info, 3500)

        self._ocr_jobs.append(start_ocr(img, done, self))

    def _scroll_selected(self, screen, frozen: QImage, logical: QRect, physical: QRect):
        self._selector = None
        self._remember(screen, logical, "scroll")
        # dá tempo para os overlays sumirem antes da primeira captura
        QTimer.singleShot(300, lambda: self._run_scroll(screen, logical, physical))

    def _run_scroll(self, screen, logical: QRect, physical: QRect):
        """Executa a captura com rolagem e entrega o resultado como qualquer outra captura."""
        warn = QSystemTrayIcon.MessageIcon.Warning
        info = QSystemTrayIcon.MessageIcon.Information
        c = self.cfg
        log.info("captura com rolagem: área %sx%s", physical.width(), physical.height())
        try:
            result = run_scroll_capture(screen, logical, physical, c.scroll_delay_ms, c.scroll_max_frames,
                                        c.scroll_max_height)
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira aviso; o programa precisa ser liberado
            log.exception("captura com rolagem falhou")
            self._busy = False
            self._notify(APP_NAME, tr("A captura com rolagem falhou: {err}").format(err=exc), warn, 6000)
            return
        self._busy = False
        if result.image is None or result.frames < 1:
            self._notify(APP_NAME, tr("Nada foi capturado."), warn, 4000)
            return
        if result.frames == 1:
            # a página não rolou: avisa, mas ainda entrega o que foi capturado
            self._notify(APP_NAME, tr("A área não rolou. Posicione o mouse sobre o conteúdo que rola e tente de novo."),
                                  warn, 6000)
        else:
            self._notify(APP_NAME, f"{result.message} ({result.frames} " + tr("quadros") + ")", info, 3500)
        self._deliver(np_to_qimage(result.image))

    def capture_repeat(self):
        """Captura de novo a mesma área (mesmo monitor, mesmas coordenadas e mesmo modo)."""
        if self._busy:
            return
        region = Config._valid_region(self.cfg.last_region)
        if not region:
            self._notify(APP_NAME, tr("Ainda não há uma área anterior. Capture uma área primeiro."),
                                  QSystemTrayIcon.MessageIcon.Information, 3500)
            return
        name, x, y, w, h, mode = region
        screen = next((s for s in QGuiApplication.screens() if s.name() == name), None) or QGuiApplication.primaryScreen()
        geo = screen.geometry()
        logical = QRect(x, y, w, h).intersected(QRect(0, 0, geo.width(), geo.height()))
        if logical.width() < 4 or logical.height() < 4:
            self._notify(APP_NAME, tr("A área anterior não cabe mais neste monitor. Selecione uma nova."),
                                  QSystemTrayIcon.MessageIcon.Warning, 5000)
            return
        if mode == "scroll" and not IS_WINDOWS:
            return
        frozen = self._grab_screen(screen)
        sx, sy = frozen.width() / max(1, geo.width()), frozen.height() / max(1, geo.height())
        physical = QRect(round(logical.x() * sx), round(logical.y() * sy), round(logical.width() * sx),
                         round(logical.height() * sy)).intersected(frozen.rect())
        if mode == "scroll":
            self._busy = True
            self._run_scroll(screen, logical, physical)
        else:
            cursor = grab_cursor() if self.cfg.include_cursor else None
            self._deliver(draw_cursor(frozen.copy(physical), cursor, geo.topLeft() + physical.topLeft()))

    # ------------------------------------------------------------------
    def _deliver(self, image: QImage, mode: str | None = None):
        """Faz o que está em Configurações > Depois da captura (ou a ação pedida na pré-captura: Ctrl+C copia, Ctrl+S salva)."""
        mode = mode or self.cfg.after_capture
        info = QSystemTrayIcon.MessageIcon.Information
        if mode == "copy":
            copy_image(image)
            self._notify(APP_NAME, tr("Imagem copiada."), info, 2000)
        elif mode == "save":
            path = self._save_image(image)
            if path:
                self._notify(APP_NAME, tr("Captura salva em {path}").format(path=path), info, 3500)
        elif mode == "preview":
            self.show_preview(image)
        else:
            self.open_editor(image)

    def _save_image(self, image: QImage) -> Path | None:
        ext = "jpg" if self.cfg.save_format == "jpg" else "png"
        try:
            from .naming import build_path
            path = build_path(self.cfg.save_dir, ext, self.cfg.file_name_pattern, self.cfg.save_by_month)
        except OSError:
            path = None
        ok = False
        if path is not None:
            img = image.convertToFormat(QImage.Format.Format_RGB32) if ext == "jpg" and image.hasAlphaChannel() else image
            ok = img.save(str(path), "JPG" if ext == "jpg" else "PNG", 92 if ext == "jpg" else -1)
        if not ok:
            QMessageBox.warning(None, APP_NAME, tr("Não foi possível salvar em:\n{path}").format(path=self.cfg.save_dir))
            return None
        return path

    # --- miniatura no canto ------------------------------------------------
    def show_preview(self, image: QImage):
        for old in list(self.previews):          # só uma miniatura por vez
            old.close()
        pv = QuickPreview(image, self.cfg.preview_seconds)
        pv.closed.connect(lambda w: self.previews.remove(w) if w in self.previews else None)
        pv.copy_clicked.connect(lambda img: (copy_image(img), self._notify(
            APP_NAME, tr("Imagem copiada."), QSystemTrayIcon.MessageIcon.Information, 2000)))
        pv.edit_clicked.connect(lambda img: self.open_editor(img))
        pv.save_clicked.connect(self._preview_save)
        pv.pin_clicked.connect(self.pin_image)
        self.previews.append(pv)
        pv.show()

    def _preview_save(self, image: QImage):
        path = self._save_image(image)
        if path:
            self._notify(APP_NAME, tr("Captura salva em {path}").format(path=path), QSystemTrayIcon.MessageIcon.Information, 3000)

    # ------------------------------------------------------------------
    def open_editor(self, image: QImage | None, project=None, pid: str | None = None):
        ed = EditorWindow(image, self.cfg, project=project, pid=pid)
        ed.closed.connect(lambda w: self.editors.remove(w) if w in self.editors else None)
        ed.capture_requested.connect(lambda cb, e=ed: self._capture_for_editor(e, cb))
        ed.pin_requested.connect(self.pin_image)
        ed.library_requested.connect(self.open_library)
        ed.settings_requested.connect(self.open_settings)
        self.editors.append(ed)
        ed.show()
        ed.raise_()
        ed.activateWindow()
        return ed

    # --- inserir nova captura em um editor aberto ------------------------
    def _capture_for_editor(self, editor: EditorWindow, callback):
        if self._busy:
            return
        editor.hide()          # a janela do editor não pode aparecer na nova captura

        def back():
            if editor in self.editors:
                editor.show()
                editor.raise_()
                editor.activateWindow()

        def selected(_screen, frozen: QImage, _logical: QRect, physical: QRect):
            self._selector = None
            self._busy = False
            img = frozen.copy(physical)
            back()
            if editor in self.editors:
                callback(img)

        def cancelled():
            self._selection_cancelled()
            back()

        def start():
            self._start_selection(tr("Selecione a área da nova captura  •  Esc cancela"), selected, cancelled)

        QTimer.singleShot(280, start)

    # --- fixar captura ---------------------------------------------------
    def pin_image(self, image: QImage):
        pin = PinWindow(image)
        pin.closed.connect(lambda w: self.pins.remove(w) if w in self.pins else None)
        pin.edit_requested.connect(lambda img: self.open_editor(img))
        pin.save_requested.connect(self._preview_save)
        self.pins.append(pin)
        pin.show()
        pin.raise_()

    def close_pins(self):
        for p in list(self.pins):
            p.close()

    # --- biblioteca / abrir arquivos --------------------------------------
    def open_library(self):
        if self._library_dlg is not None:
            self._library_dlg.reload()
            self._library_dlg.show()
            self._library_dlg.raise_()
            self._library_dlg.activateWindow()
            return
        dlg = LibraryDialog()
        dlg.open_project.connect(self.open_project)
        dlg.open_file_requested.connect(self.open_file_dialog)
        dlg.finished.connect(lambda _r: setattr(self, "_library_dlg", None))
        self._library_dlg = dlg
        dlg.show()

    def open_project(self, pid: str):
        for ed in self.editors:
            if ed.pid == pid:
                ed.show()
                ed.raise_()
                ed.activateWindow()
                return
        try:
            data = library.load(pid)
        except (ProjectError, ValueError) as exc:
            QMessageBox.warning(None, APP_NAME, tr("Não foi possível abrir esta captura:\n{exc}").format(exc=exc))
            return
        self.open_editor(None, project=data, pid=pid)

    def open_file_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(None, tr("Abrir imagem ou projeto"), self.cfg.save_dir,
                                               tr("Imagens, vídeos e projetos (*.png *.jpg *.jpeg *.bmp *.webp *.shotwin *.mp4 *.gif)"))
        if fname:
            self.open_path(fname)

    def open_path(self, fname: str):
        low = fname.lower()
        if low.endswith((".mp4", ".gif")):
            self.open_media(fname)
            return
        if fname.lower().endswith(".shotwin"):
            try:
                data = read_project(fname)
            except ProjectError as exc:
                QMessageBox.warning(None, APP_NAME, tr("Projeto inválido:\n{exc}").format(exc=exc))
                return
            self.open_editor(None, project=data)
            return
        img = load_image_file(fname)
        if img is None:
            QMessageBox.warning(None, APP_NAME, tr("Não foi possível abrir essa imagem (formato ou tamanho inválido)."))
            return
        self.open_editor(img)

    # --- abrir vídeo ou GIF já salvo no player ------------------------------------
    def open_media(self, fname: str):
        c = self.cfg
        if fname.lower().endswith(".gif"):
            from .mediaload import load_gif
            try:
                images, durations, truncated = load_gif(fname, c.mp4_max_width, c.mp4_max_memory_mb * 1024 * 1024)
            except (ValueError, OSError) as exc:
                QMessageBox.warning(None, APP_NAME, tr("Não foi possível abrir este GIF:\n{exc}").format(exc=exc))
                return
            if truncated:
                self._notify(APP_NAME, tr("O GIF é grande: só o começo foi carregado (limite de memória)."),
                             QSystemTrayIcon.MessageIcon.Warning, 6000)
            self._show_player(images, durations, "gif")
            return
        from PySide6.QtWidgets import QProgressDialog

        from .mediaload import Mp4Loader
        if getattr(self, "_media_loader", None) is not None:
            return                                          # já está lendo um arquivo
        loader = Mp4Loader(fname, c.mp4_fps, c.mp4_max_width, c.mp4_max_memory_mb * 1024 * 1024, self)
        box = QProgressDialog(tr("Lendo o vídeo…") + "\n" + Path(fname).name, tr("Cancelar"), 0, 100)
        box.setWindowTitle(APP_NAME)
        box.setWindowModality(Qt.WindowModality.ApplicationModal)
        box.setMinimumDuration(0)
        box.setAutoClose(False)
        box.setAutoReset(False)
        self._media_loader = loader

        def finish():
            self._media_loader = None
            box.close()
            box.deleteLater()
            loader.deleteLater()

        def done(images, durations, pcm, truncated):
            finish()
            if truncated:
                self._notify(APP_NAME, tr("O vídeo é grande: só o começo foi carregado (limite de memória)."),
                             QSystemTrayIcon.MessageIcon.Warning, 6000)
            self._show_player(images, durations, "mp4", pcm)

        def failed(msg):
            finish()
            QMessageBox.warning(None, APP_NAME, tr("Não foi possível abrir este vídeo:\n{exc}").format(exc=msg))

        def cancelled():
            loader.cancel()
            finish()

        loader.progress.connect(box.setValue)
        loader.done.connect(done)
        loader.failed.connect(failed)
        box.canceled.connect(cancelled)
        box.show()
        loader.start()

    # ------------------------------------------------------------------
    def open_folder(self):
        Path(self.cfg.save_dir).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.cfg.save_dir))

    # Janelas de configuração NÃO são modais: um diálogo modal bloquearia o mouse e o teclado da seleção de área
    # (que é outra janela do programa) e o overlay de tela cheia deixaria o computador sem resposta.
    def _show_dialog(self, attr: str, factory, on_accept):
        current = getattr(self, attr, None)
        if current is not None:
            current.raise_()
            current.activateWindow()
            return
        dlg = factory()
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.accepted.connect(on_accept)
        dlg.destroyed.connect(lambda *_: setattr(self, attr, None))
        setattr(self, attr, dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def open_shortcuts(self):
        self._show_dialog("_shortcuts_dlg", lambda: ShortcutsDialog(self.cfg), self._shortcuts_saved)

    def _shortcuts_saved(self):
        self.cfg.save()
        self._update_menu_labels()
        self.register_hotkeys()

    def open_settings(self):
        self._show_dialog("_settings_dlg", self._make_settings, self._settings_saved)

    def _make_settings(self):
        dlg = SettingsDialog(self.cfg)
        dlg.quit_requested.connect(self.quit)
        return dlg

    def _settings_saved(self):
        old_lang = self._lang_in_use
        self.cfg.save()
        self._update_menu_labels()
        hotkeys_ok = self.register_hotkeys(show_ok=False)
        try:
            set_autostart(self.cfg.autostart)
        except OSError as exc:
            QMessageBox.warning(None, APP_NAME, tr("Não foi possível alterar a inicialização automática:\n{exc}").format(exc=exc))
        apply_theme(QApplication.instance(), self.cfg.theme)
        try:
            library.prune(self.cfg.library_max_items, self.cfg.library_max_mb)
        except OSError:
            pass
        for ed in self.editors:
            ed.apply_window_settings()
        if hotkeys_ok:
            self._notify(APP_NAME, tr("Configurações salvas."), QSystemTrayIcon.MessageIcon.Information, 2500)
        if self.cfg.language != old_lang:
            self._lang_in_use = self.cfg.language
            self._offer_restart()

    def _offer_restart(self):
        """O idioma só é lido ao iniciar: oferece reiniciar agora."""
        from .i18n import _resolve
        new = _resolve(self.cfg.language)
        ask = {"pt": "Reiniciar o Shotwise agora para aplicar o novo idioma?",
               "en": "Restart Shotwise now to apply the new language?",
               "es": "¿Reiniciar Shotwise ahora para aplicar el nuevo idioma?"}[new]
        if QMessageBox.question(None, APP_NAME, ask) != QMessageBox.StandardButton.Yes:
            return
        from PySide6.QtCore import QProcess
        prog = sys.executable
        args = [] if getattr(sys, "frozen", False) else [os.path.abspath(sys.argv[0])]
        if not getattr(sys, "frozen", False) and prog.lower().endswith("python.exe"):
            w = prog[:-len("python.exe")] + "pythonw.exe"      # sem janela de console
            prog = w if os.path.isfile(w) else prog
        # "--restarted": o novo processo espera o atual fechar (instância única) antes de abrir
        QProcess.startDetached(prog, args + ["--restarted"])
        self.quit()

    def quit(self):
        self._cancel_recording()
        self.close_pins()
        for pv in list(self.previews):
            pv.close()
        self.hotkeys.unregister_all()
        self.tray.hide()
        self.qapp.quit()
