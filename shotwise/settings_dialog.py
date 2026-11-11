"""Janela de configurações."""
from __future__ import annotations

import sys
from dataclasses import replace

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QKeySequenceEdit, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from .i18n import tr
from .i18n_data import LANGUAGES
from .config import DEFAULT_HOTKEYS, Config


def set_autostart(enabled: bool) -> None:
    """Liga/desliga a inicialização com o Windows (chave HKCU\\...\\Run)."""
    if sys.platform != "win32":
        return
    import os
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    if getattr(sys, "frozen", False):
        command = f'"{sys.executable}"'
    else:
        pyw = sys.executable.replace("python.exe", "pythonw.exe")
        main = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
        command = f'"{pyw}" "{main}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, "ShotWin")      # entrada do nome antigo (até a versão 1.7)
        except FileNotFoundError:
            pass
        if enabled:
            winreg.SetValueEx(key, "Shotwise", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "Shotwise")
            except FileNotFoundError:
                pass


class _MicCombo(QComboBox):
    """Lista de microfones carregada só ao abrir a caixa (não consulta os dispositivos de áudio ao abrir as configurações)."""

    def __init__(self):
        super().__init__()
        self._loaded = False

    def showPopup(self):
        if not self._loaded:
            self._loaded = True
            cur = self.currentData() or ""
            try:
                from PySide6.QtMultimedia import QMediaDevices
                names = [d.description() for d in QMediaDevices.audioInputs()]
            except ImportError:
                names = []
            self.clear()
            self.addItem(tr("Padrão do Windows"), "")
            for n in dict.fromkeys(names):
                self.addItem(n, n)
            if cur and self.findData(cur) < 0:
                self.addItem(cur, cur)
            self.setCurrentIndex(max(0, self.findData(cur)))
        super().showPopup()


class SettingsDialog(QDialog):
    quit_requested = Signal()       # pedido para fechar o programa depois de iniciar o instalador

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._pending_hotkeys: dict[str, str] = {}
        self.setWindowTitle(tr("Shotwise — Configurações"))
        self.setMinimumWidth(520)

        forms = {k: QFormLayout() for k in ("geral", "captura", "video", "sobre")}
        for f in forms.values():
            f.setSpacing(10)

        self.ed_dir = QLineEdit(cfg.save_dir)
        btn_dir = QPushButton(tr("Procurar…"))
        btn_dir.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.ed_dir, 1)
        row.addWidget(btn_dir)
        forms["geral"].addRow(tr("Pasta de capturas"), row)

        btn_keys = QPushButton(tr("Atalhos de teclado…"))
        btn_keys.clicked.connect(self._open_shortcuts)
        forms["captura"].addRow(tr("Atalhos"), btn_keys)

        self.sp_delay = QSpinBox()
        self.sp_delay.setRange(100, 2000)
        self.sp_delay.setSingleStep(50)
        self.sp_delay.setSuffix(" ms")
        self.sp_delay.setValue(cfg.scroll_delay_ms)
        forms["captura"].addRow(tr("Espera após cada rolagem"), self.sp_delay)

        self.sp_gif_fps = QSpinBox()
        self.sp_gif_fps.setRange(4, 20)
        self.sp_gif_fps.setSuffix(tr(" quadros/s"))
        self.sp_gif_fps.setValue(cfg.gif_fps)
        forms["video"].addRow(tr("Fluidez do GIF"), self.sp_gif_fps)
        self.sp_gif_sec = QSpinBox()
        self.sp_gif_sec.setRange(3, 180)
        self.sp_gif_sec.setSuffix(" s")
        self.sp_gif_sec.setValue(cfg.gif_max_seconds)
        forms["video"].addRow(tr("Duração máxima do GIF"), self.sp_gif_sec)
        self.sp_gif_w = QSpinBox()
        self.sp_gif_w.setRange(240, 3840)
        self.sp_gif_w.setSingleStep(80)
        self.sp_gif_w.setSuffix(" px")
        self.sp_gif_w.setValue(cfg.gif_max_width)
        self.sp_gif_w.setToolTip(tr("GIFs mais largos que isso são reduzidos (menor tamanho de arquivo)."))
        forms["video"].addRow(tr("Largura máxima do GIF"), self.sp_gif_w)
        self.sp_mp4_fps = QSpinBox()
        self.sp_mp4_fps.setRange(5, 30)
        self.sp_mp4_fps.setSuffix(tr(" quadros/s"))
        self.sp_mp4_fps.setValue(cfg.mp4_fps)
        forms["video"].addRow(tr("Fluidez do vídeo (MP4)"), self.sp_mp4_fps)
        self.sp_mp4_sec = QSpinBox()
        self.sp_mp4_sec.setRange(5, 600)
        self.sp_mp4_sec.setSuffix(" s")
        self.sp_mp4_sec.setValue(cfg.mp4_max_seconds)
        forms["video"].addRow(tr("Duração máxima do vídeo"), self.sp_mp4_sec)
        self.sp_mp4_w = QSpinBox()
        self.sp_mp4_w.setRange(320, 3840)
        self.sp_mp4_w.setSingleStep(80)
        self.sp_mp4_w.setSuffix(" px")
        self.sp_mp4_w.setValue(cfg.mp4_max_width)
        forms["video"].addRow(tr("Largura máxima do vídeo"), self.sp_mp4_w)
        self.sp_mp4_mem = QSpinBox()
        self.sp_mp4_mem.setRange(200, 4000)
        self.sp_mp4_mem.setSingleStep(100)
        self.sp_mp4_mem.setSuffix(" MB")
        self.sp_mp4_mem.setValue(cfg.mp4_max_memory_mb)
        self.sp_mp4_mem.setToolTip(tr("A gravação de vídeo para sozinha ao atingir esta memória. Largura menor e menos quadros por segundo rendem gravações mais longas."))
        forms["video"].addRow(tr("Memória máxima da gravação de vídeo"), self.sp_mp4_mem)
        self.chk_aud_sys = QCheckBox(tr("Gravar o som do sistema (o que toca nas caixas de som)"))
        self.chk_aud_sys.setChecked(cfg.mp4_audio_system)
        self.chk_aud_sys.setToolTip(tr("Somente no Windows. Precisa do componente PyAudioWPatch; sem ele o vídeo sai sem esse som."))
        forms["video"].addRow("", self.chk_aud_sys)
        self.chk_aud_mic = QCheckBox(tr("Gravar o microfone"))
        self.chk_aud_mic.setChecked(cfg.mp4_audio_mic)
        forms["video"].addRow("", self.chk_aud_mic)
        self.cmb_mic = _MicCombo()
        self.cmb_mic.addItem(tr("Padrão do Windows"), "")
        if cfg.mp4_mic_device:
            self.cmb_mic.addItem(cfg.mp4_mic_device, cfg.mp4_mic_device)
            self.cmb_mic.setCurrentIndex(1)
        forms["video"].addRow(tr("Microfone"), self.cmb_mic)
        self.cb_gif_cursor = QCheckBox(tr("Destacar o ponteiro do mouse na gravação"))
        self.cb_gif_cursor.setChecked(cfg.gif_cursor_highlight)
        forms["video"].addRow("", self.cb_gif_cursor)

        forms["captura"].addRow(tr("Formato a ser salvo"), self._combo_format(cfg))
        self.ed_pattern = QLineEdit(cfg.file_name_pattern)
        self.ed_pattern.setMaxLength(100)
        self.ed_pattern.setPlaceholderText("Shotwise_%Y-%m-%d_%H-%M-%S")
        self.ed_pattern.setToolTip(tr("Códigos: %Y ano (2026), %m mês, %d dia, %H hora, %M minuto, %S segundo, %y ano com 2 dígitos. "
                                      "Exemplo: Captura_%d-%m-%Y_%H%M%S. Se o nome já existir, o programa acrescenta _2, _3…"))
        forms["captura"].addRow(tr("Nome dos arquivos"), self.ed_pattern)
        self.lbl_pattern = QLabel()
        self.lbl_pattern.setStyleSheet("color:gray;")
        forms["captura"].addRow("", self.lbl_pattern)
        self.ed_pattern.textChanged.connect(self._update_pattern_example)
        self.cb_by_month = QCheckBox(tr("Salvar em subpastas por ano e mês (pasta de capturas\\2026\\11)"))
        self.cb_by_month.setChecked(cfg.save_by_month)
        forms["captura"].addRow("", self.cb_by_month)
        self._update_pattern_example()

        self.cmb_after = QComboBox()
        for key, label in (("editor", tr("Abrir Editor")), ("copy", tr("Copiar Imagem")), ("save", tr("Salvar Imagem")),
                           ("preview", tr("Mostrar Miniatura"))):
            self.cmb_after.addItem(label, key)
        self.cmb_after.setCurrentIndex(max(0, self.cmb_after.findData(cfg.after_capture)))
        forms["captura"].addRow(tr("Depois da captura"), self.cmb_after)
        self.sp_prev = QSpinBox()
        self.sp_prev.setRange(3, 60)
        self.sp_prev.setSuffix(" s")
        self.sp_prev.setValue(cfg.preview_seconds)
        forms["captura"].addRow(tr("Tempo da miniatura na tela"), self.sp_prev)
        self.cb_cursor = QCheckBox(tr("Mostrar a seta do mouse na captura"))
        self.cb_cursor.setChecked(cfg.include_cursor)
        forms["captura"].addRow(tr("Seta do mouse"), self.cb_cursor)
        self.cmb_close = QComboBox()
        for key, label in (("copy", tr("Copiar Imagem")), ("save", tr("Salvar Imagem"))):
            self.cmb_close.addItem(label, key)
        self.cmb_close.setCurrentIndex(max(0, self.cmb_close.findData(cfg.close_action)))
        forms["captura"].addRow(tr("Ação após fechar com ESC"), self.cmb_close)
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItem(tr("Seguir o sistema"), "auto")
        for code, name in LANGUAGES:
            self.cmb_lang.addItem(name, code)
        self.cmb_lang.setCurrentIndex(max(0, self.cmb_lang.findData(cfg.language)))
        self.cmb_lang.setToolTip(tr("O idioma é aplicado ao reiniciar o Shotwise."))
        forms["geral"].addRow(tr("Idioma"), self.cmb_lang)
        self.cmb_theme = QComboBox()
        for key, label in (("dark", tr("Escuro")), ("light", tr("Claro")), ("system", tr("Seguir o sistema"))):
            self.cmb_theme.addItem(label, key)
        self.cmb_theme.setCurrentIndex(max(0, self.cmb_theme.findData(cfg.theme)))
        forms["geral"].addRow(tr("Tema"), self.cmb_theme)
        self.cmb_tools = QComboBox()
        for key, label in (("left", tr("À esquerda")), ("right", tr("À direita")),
                           ("top", tr("Em cima (abaixo dos ícones, acima das cores)"))):
            self.cmb_tools.addItem(label, key)
        self.cmb_tools.setCurrentIndex(max(0, self.cmb_tools.findData(cfg.tools_position)))
        forms["captura"].addRow(tr("Barra de ferramentas do editor"), self.cmb_tools)
        self.cb_top = QCheckBox(tr("Sempre no topo (always on top)"))
        self.cb_top.setChecked(cfg.editor_on_top)
        forms["geral"].addRow(tr("Janela principal"), self.cb_top)
        self.cb_hide_notif = QCheckBox(tr("Ocultar notificações (os avisos de erro continuam aparecendo)"))
        self.cb_hide_notif.setChecked(cfg.hide_notifications)
        forms["geral"].addRow(self.cb_hide_notif)
        self.cb_auto = QCheckBox(tr("Iniciar com o Windows"))
        self.cb_auto.setChecked(cfg.autostart)
        forms["geral"].addRow(self.cb_auto)
        self.cb_adjust = QCheckBox(tr("Editar área de captura antes de confirmar"))
        self.cb_adjust.setChecked(cfg.adjust_selection)
        forms["captura"].addRow(self.cb_adjust)
        self.cb_lib = QCheckBox(tr("Guardar capturas recentes na biblioteca local"))
        self.cb_lib.setChecked(cfg.library_enabled)
        forms["geral"].addRow(self.cb_lib)
        self.sp_lib = QSpinBox()
        self.sp_lib.setRange(5, 500)
        self.sp_lib.setSuffix(tr(" arquivos"))
        self.sp_lib.setValue(cfg.library_max_items)
        self.sp_lib_mb = QSpinBox()
        self.sp_lib_mb.setRange(20, 20000)
        self.sp_lib_mb.setSingleStep(50)
        self.sp_lib_mb.setSuffix(" MB")
        self.sp_lib_mb.setValue(cfg.library_max_mb)
        tip = tr("Quando a quantidade ou o tamanho passa do limite, as capturas mais antigas são apagadas")
        self.sp_lib.setToolTip(tip)
        self.sp_lib_mb.setToolTip(tip)
        lib_row = QHBoxLayout()
        lib_row.addWidget(self.sp_lib)
        lib_row.addWidget(QLabel("/"))
        lib_row.addWidget(self.sp_lib_mb)
        lib_row.addStretch(1)
        forms["geral"].addRow(tr("Limite da biblioteca"), lib_row)
        self._build_about(forms["sobre"], cfg)
        self._build_update_settings(forms["geral"], cfg)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))

        self.tabs = QTabWidget()
        for key, title in (("geral", tr("Geral")), ("captura", tr("Captura")), ("video", tr("Vídeo e GIF")),
                           ("sobre", tr("Sobre"))):
            page = QWidget()
            page.setLayout(forms[key])
            self.tabs.addTab(page, title)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        lay.addWidget(buttons)

    # --- aba Sobre / atualização ---------------------------------------------------------
    def _build_about(self, form: QFormLayout, cfg: Config) -> None:
        from . import APP_AUTHOR, APP_NAME, __version__
        from .updater import UpdateInfo
        self._update_info: UpdateInfo | None = None
        self._worker = None
        title = QLabel(f"{APP_NAME} {__version__}")
        title.setStyleSheet("font-size:18px;font-weight:700;")
        form.addRow(title)
        desc = QLabel(tr("Ferramenta de captura de tela aprimorada e simplificada, uma experiência além da captura de tela."))
        desc.setWordWrap(True)
        form.addRow(desc)
        form.addRow(QLabel(tr("Desenvolvido por {author}").format(author=APP_AUTHOR)))
        self._about_text = self._about_info(__version__)
        info = QLabel(self._about_text)
        info.setStyleSheet("color:gray;")
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.setWordWrap(True)
        form.addRow(info)
        b_copy = QPushButton(tr("Copiar informações"))
        b_copy.setToolTip(tr("Copia versão, ambiente e pastas para enviar ao suporte."))
        b_copy.clicked.connect(self._copy_about)
        b_dir = QPushButton(tr("Abrir pasta de configurações"))
        b_dir.clicked.connect(self._open_config_dir)
        row_info = QHBoxLayout()
        row_info.addWidget(b_copy)
        row_info.addWidget(b_dir)
        row_info.addStretch(1)
        form.addRow(row_info)

        self.btn_check = QPushButton(tr("Verificar atualizações"))
        self.btn_check.clicked.connect(self._check_updates)
        self.btn_install = QPushButton(tr("Baixar e instalar"))
        self.btn_install.clicked.connect(self._download_update)
        self.btn_install.hide()
        row = QHBoxLayout()
        row.addWidget(self.btn_check)
        row.addWidget(self.btn_install)
        row.addStretch(1)
        form.addRow(row)
        self.lbl_upd = QLabel("")
        self.lbl_upd.setWordWrap(True)
        form.addRow(self.lbl_upd)

    def _build_update_settings(self, form: QFormLayout, cfg: Config) -> None:
        self.cmb_upd = QComboBox()
        self.cmb_upd.addItem(tr("Repositório web (padrão)"), "repo")
        self.cmb_upd.addItem(tr("Pasta local ou de rede (repositório interno)"), "folder")
        self.cmb_upd.setCurrentIndex(max(0, self.cmb_upd.findData(cfg.update_source)))
        self.cmb_upd.currentIndexChanged.connect(self._upd_source_changed)
        form.addRow(tr("Buscar atualizações em"), self.cmb_upd)

        self.ed_repo = QLineEdit(cfg.update_repo)
        self.ed_repo.setPlaceholderText("usuario/repositorio")
        self.ed_repo.setToolTip(tr("Repositório do GitHub com as versões publicadas (Releases)."))
        self.lbl_repo = QLabel(tr("Repositório"))
        # o campo do repositório web não é exibido: vem do padrão da instalação (ou do config)

        self.ed_upd_dir = QLineEdit(cfg.update_folder)
        self.ed_upd_dir.setPlaceholderText(r"\\servidor\compartilhamento\Shotwise")
        self.ed_upd_dir.setToolTip(tr("Pasta com o instalador Shotwise-Setup-X.Y.Z.exe (opcional: latest.json com a versão e o SHA-256)."))
        btn = QPushButton(tr("Procurar…"))
        btn.clicked.connect(self._browse_update_dir)
        self.row_dir = QHBoxLayout()
        self.row_dir.addWidget(self.ed_upd_dir, 1)
        self.row_dir.addWidget(btn)
        self.lbl_dir = QLabel(tr("Pasta de atualização"))
        form.addRow(self.lbl_dir, self.row_dir)
        self._dir_widgets = (self.ed_upd_dir, btn)

        self.cb_upd_start = QCheckBox(tr("Verificar atualizações ao iniciar"))
        self.cb_upd_start.setChecked(cfg.update_on_start)
        form.addRow(self.cb_upd_start)

        self._upd_source_changed()

    @staticmethod
    def _about_info(version: str) -> str:
        import platform
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import qVersion
        from .config import config_dir
        mode = tr("instalado (executável)") if getattr(sys, "frozen", False) else tr("código-fonte (Python)")
        return "\n".join((
            f"Python {platform.python_version()}  ·  PySide6 {pyside_version}  ·  Qt {qVersion()}",
            f"{tr('Modo')}: {mode}  ·  {platform.system()} {platform.release()}",
            f"{tr('Configurações e logs')}: {config_dir()}",
        ))

    def _copy_about(self):
        from . import APP_NAME, __version__
        QApplication.clipboard().setText(f"{APP_NAME} {__version__}\n{self._about_text}")
        self.lbl_upd.setText(tr("Informações copiadas."))

    def _open_config_dir(self):
        from .config import config_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(config_dir())))

    def _upd_source_changed(self):
        repo = self.cmb_upd.currentData() == "repo"
        self.lbl_dir.setVisible(not repo)
        for w in self._dir_widgets:
            w.setVisible(not repo)
        self.btn_install.hide()
        self._update_info = None

    def _browse_update_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("Pasta de atualização"), self.ed_upd_dir.text())
        if d:
            self.ed_upd_dir.setText(d)

    def _upd_location(self) -> tuple[str, str]:
        src = self.cmb_upd.currentData()
        return src, (self.ed_repo.text() if src == "repo" else self.ed_upd_dir.text()).strip()

    def _start_worker(self, worker):
        self._worker = worker
        self.btn_check.setEnabled(False)
        self.btn_install.setEnabled(False)
        worker.failed.connect(self._upd_failed)
        worker.finished.connect(lambda: (self.btn_check.setEnabled(True), self.btn_install.setEnabled(True)))
        worker.start()

    def _check_updates(self):
        from .updater import UpdateWorker
        src, loc = self._upd_location()
        if not loc:
            self.lbl_upd.setText(tr("Informe o repositório ou a pasta de atualização."))
            return
        self.lbl_upd.setText(tr("Verificando…"))
        self.btn_install.hide()
        w = UpdateWorker(src, loc, "check", parent=self)
        w.found.connect(self._upd_found)
        self._start_worker(w)

    def _upd_found(self, info):
        self._update_info = info
        if info is None:
            self.lbl_upd.setText(tr("Você já está na versão mais recente."))
            self.btn_install.hide()
            return
        self.lbl_upd.setText(tr("Nova versão disponível: {v}").format(v=info.version))
        self.btn_install.show()

    def _upd_failed(self, msg: str):
        self.lbl_upd.setText(tr("Não foi possível atualizar: {err}").format(err=msg))

    def _download_update(self):
        from .updater import UpdateWorker
        if self._update_info is None:
            return
        self.lbl_upd.setText(tr("Baixando…"))
        w = UpdateWorker("", "", "download", self._update_info, parent=self)
        w.progress.connect(lambda v: self.lbl_upd.setText(tr("Baixando… {v}%").format(v=v)))
        w.ready.connect(self._upd_downloaded)
        self._start_worker(w)

    def _upd_downloaded(self, path: str):
        from .updater import run_installer
        ask = QMessageBox.question(self, tr("Atualizar o Shotwise"),
                                   tr("O instalador foi baixado e conferido. O Shotwise será fechado e atualizado agora. Continuar?"))
        if ask != QMessageBox.StandardButton.Yes:
            self.lbl_upd.setText(tr("Atualização adiada."))
            return
        if run_installer(path):
            self.quit_requested.emit()
        else:
            self.lbl_upd.setText(tr("Não foi possível iniciar o instalador."))

    @staticmethod
    def _combo_format_build(cfg):
        cmb = QComboBox()
        cmb.addItem(tr("PNG (sem perdas)"), "png")
        cmb.addItem(tr("JPG (menor)"), "jpg")
        cmb.setCurrentIndex(max(0, cmb.findData(cfg.save_format)))
        return cmb

    def _combo_format(self, cfg):
        self.cmb_format = self._combo_format_build(cfg)
        return self.cmb_format

    def _open_shortcuts(self):
        # trabalha numa cópia: os atalhos só valem se o usuário confirmar as Configurações com OK.
        # Modal só para esta janela (não bloqueia a seleção de área, que é outra janela do programa).
        tmp = replace(self.cfg, **self._pending_hotkeys)
        dlg = ShortcutsDialog(tmp, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.accepted.connect(lambda: self._pending_hotkeys.update({k: getattr(tmp, k) for k in DEFAULT_HOTKEYS}))
        dlg.open()

    def _update_pattern_example(self, *_):
        from .naming import format_name
        ext = self.cmb_format.currentData() if hasattr(self, "cmb_format") else "png"
        self.lbl_pattern.setText(tr("Exemplo:") + " " + format_name(self.ed_pattern.text()) + "." + (ext or "png"))

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, tr("Pasta de capturas"), self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)

    def _accept(self):
        c = self.cfg
        c.save_dir = self.ed_dir.text().strip() or c.save_dir
        c.adjust_selection = self.cb_adjust.isChecked()
        c.update_source = self.cmb_upd.currentData()
        c.update_repo = self.ed_repo.text().strip()
        c.update_folder = self.ed_upd_dir.text().strip()
        c.update_on_start = self.cb_upd_start.isChecked()
        c.library_enabled = self.cb_lib.isChecked()
        c.library_max_items = self.sp_lib.value()
        c.library_max_mb = self.sp_lib_mb.value()
        c.scroll_delay_ms = self.sp_delay.value()
        c.gif_fps = self.sp_gif_fps.value()
        c.gif_max_seconds = self.sp_gif_sec.value()
        c.gif_max_width = self.sp_gif_w.value()
        c.gif_cursor_highlight = self.cb_gif_cursor.isChecked()
        c.mp4_fps = self.sp_mp4_fps.value()
        c.mp4_max_seconds = self.sp_mp4_sec.value()
        c.mp4_max_width = self.sp_mp4_w.value()
        c.mp4_max_memory_mb = self.sp_mp4_mem.value()
        c.mp4_audio_system = self.chk_aud_sys.isChecked()
        c.mp4_audio_mic = self.chk_aud_mic.isChecked()
        c.mp4_mic_device = self.cmb_mic.currentData() or ""
        c.after_capture = self.cmb_after.currentData()
        c.save_format = self.cmb_format.currentData()
        c.file_name_pattern = self.ed_pattern.text().strip() or "Shotwise_%Y-%m-%d_%H-%M-%S"
        c.save_by_month = self.cb_by_month.isChecked()
        c.hide_notifications = self.cb_hide_notif.isChecked()
        c.include_cursor = self.cb_cursor.isChecked()
        c.editor_on_top = self.cb_top.isChecked()
        c.tools_position = self.cmb_tools.currentData()
        c.theme = self.cmb_theme.currentData()
        c.language = self.cmb_lang.currentData()
        c.preview_seconds = self.sp_prev.value()
        c.close_action = self.cmb_close.currentData()
        for k, v in self._pending_hotkeys.items():
            setattr(c, k, v)
        c.autostart = self.cb_auto.isChecked()
        self.accept()


SHORTCUT_ROWS = (
    ("hotkey_fullscreen", tr("Tela inteira")),
    ("hotkey_area", tr("Área")),
    ("hotkey_repeat", tr("Repetir última área")),
    ("hotkey_window", tr("Janela ativa")),
    ("hotkey_scroll", tr("Área com rolagem")),
    ("hotkey_ocr", tr("Copiar texto da área")),
    ("hotkey_gif", tr("Gravar GIF (aperte de novo para parar)")),
    ("hotkey_mp4", tr("Gravar vídeo MP4 (aperte de novo para parar)")),
)


class ShortcutsDialog(QDialog):
    """Atalhos globais de captura, separados das configurações gerais."""

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QKeySequence

        self.cfg = cfg
        self.setWindowTitle(tr("Shotwise — Atalhos de teclado"))
        self.setMinimumWidth(420)
        form = QFormLayout()
        form.setSpacing(10)
        form.setHorizontalSpacing(18)
        self.edits: dict[str, QKeySequenceEdit] = {}
        for key, label in SHORTCUT_ROWS:
            ed = QKeySequenceEdit(QKeySequence(getattr(cfg, key)))
            ed.setMaximumSequenceLength(1)
            self.edits[key] = ed
            form.addRow(label, ed)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
                                   | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self._restore)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText(tr("Restaurar padrões"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        muted = "color:gray; font-size:11px;"
        hint = QLabel(tr("Clique no campo e escolha a combinação desejada."))
        hint.setStyleSheet(muted)
        note = QLabel(tr('Print Screen abrindo outra ferramenta? Ajuste nas '
                      '<a href="ms-settings:easeofaccess-keyboard" style="color:#6cb2ff;">Configurações de teclado '
                      'do Windows</a>.'))
        note.setWordWrap(True)
        note.setStyleSheet(muted)
        note.setTextFormat(Qt.TextFormat.RichText)
        note.linkActivated.connect(lambda url: QDesktopServices.openUrl(QUrl(url)))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(14)
        lay.addWidget(hint)
        lay.addLayout(form)
        lay.addWidget(note)
        lay.addWidget(buttons)

    def _restore(self):
        from PySide6.QtGui import QKeySequence

        for key, ed in self.edits.items():
            ed.setKeySequence(QKeySequence(DEFAULT_HOTKEYS[key]))

    def _accept(self):
        from .hotkeys import parse_hotkey

        values = {k: ed.keySequence().toString() or getattr(self.cfg, k) for k, ed in self.edits.items()}
        labels = dict(SHORTCUT_ROWS)
        for k, v in values.items():
            if parse_hotkey(v) is None:
                QMessageBox.warning(self, "Shotwise", f"O atalho de \"{labels[k]}\" ({v}) não é válido. Use uma "
                                    "tecla de função, Print Screen ou uma combinação com Ctrl, Shift, Alt ou Win.")
                return
        if len(set(v.lower() for v in values.values())) < len(values):
            QMessageBox.warning(self, "Shotwise", tr("Dois comandos estão com o mesmo atalho. Escolha atalhos diferentes."))
            return
        for k, v in values.items():
            setattr(self.cfg, k, v)
        self.accept()
