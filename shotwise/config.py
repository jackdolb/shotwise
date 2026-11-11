"""Configurações persistidas em %APPDATA%\\Shotwise\\config.json."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import UPDATE_REPO_DEFAULT, UPDATE_SIGNER_DEFAULT


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "Shotwise"
    old = base / "ShotWin"                 # nome anterior do programa (até a versão 1.7)
    if not d.exists() and old.exists():
        try:
            old.rename(d)                  # leva configurações, biblioteca e logs para a pasta nova
        except OSError:
            d = old                        # a pasta antiga ainda está em uso: continua nela por enquanto
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_save_dir() -> str:
    docs = Path.home() / "Documents"
    return str((docs if docs.exists() else Path.home()) / "Shotwise")


DEFAULT_HOTKEYS = {"hotkey_fullscreen": "Shift+Print", "hotkey_area": "Print", "hotkey_repeat": "Alt+Shift+R",
                   "hotkey_window": "Alt+Shift+J", "hotkey_scroll": "Alt+Shift+S", "hotkey_ocr": "Alt+Shift+T",
                   "hotkey_gif": "Alt+Shift+G", "hotkey_mp4": "Alt+Shift+V"}

# padrões antigos -> novos (quem nunca mudou os atalhos passa a usar os novos)
_OLD_HOTKEY_DEFAULTS = {"hotkey_fullscreen": ("Ctrl+Shift+3", "Shift+Print"),
                        "hotkey_area": ("Ctrl+Shift+4", "Print"),
                        "hotkey_repeat": ("Ctrl+Shift+6", "Alt+Shift+R"),
                        "hotkey_scroll": ("Ctrl+Shift+5", "Alt+Shift+S"),
                        "hotkey_ocr": ("Ctrl+Shift+7", "Alt+Shift+T")}


@dataclass
class Config:
    save_dir: str = field(default_factory=default_save_dir)
    hotkey_fullscreen: str = "Shift+Print"
    hotkey_area: str = "Print"
    hotkey_repeat: str = "Alt+Shift+R"    # repete a última área capturada
    hotkey_window: str = "Alt+Shift+J"    # captura a janela ativa
    hotkey_scroll: str = "Alt+Shift+S"
    hotkey_ocr: str = "Alt+Shift+T"       # captura uma área e copia o texto reconhecido (OCR)
    hotkey_gif: str = "Alt+Shift+G"       # grava um GIF da área (aperte de novo para parar)
    hotkey_mp4: str = "Alt+Shift+V"       # grava um vídeo MP4 da área (aperte de novo para parar)
    tool_options: dict = field(default_factory=dict)   # últimas opções das ferramentas do editor (cor, espessura, fundo…)
    adjust_selection: bool = True   # permite ajustar a área (alças) antes de confirmar
    library_enabled: bool = True    # guarda cópia editável (com originais) na biblioteca local
    library_max_items: int = 50
    library_max_mb: int = 500       # tamanho máximo da biblioteca (MB)
    last_region: list = field(default_factory=list)  # [tela, x, y, largura, altura, modo]
    after_capture: str = "editor"   # "editor" | "copy" | "save" | "preview" (miniatura no canto)
    save_format: str = "png"        # "png" | "jpg"
    file_name_pattern: str = "Shotwise_%Y-%m-%d_%H-%M-%S"   # nome dos arquivos salvos (códigos de data do strftime)
    save_by_month: bool = False     # salva em subpastas Ano/Mês dentro da pasta de capturas
    hide_notifications: bool = False  # oculta as notificações informativas (avisos de erro continuam)
    include_cursor: bool = False    # incluir o ponteiro do mouse na captura
    editor_on_top: bool = False     # janela do editor sempre à frente
    tools_position: str = "left"    # barra de ferramentas do editor: "left" | "right" | "top"
    language: str = "auto"          # "auto" (sistema) | "pt" | "en" | "es" (vale ao reiniciar)
    theme: str = "dark"             # "dark" | "light" | "system"
    preview_seconds: int = 8        # tempo da miniatura na tela
    close_action: str = "copy"      # ao fechar o editor (Esc): "copy" | "save"
    autostart: bool = False         # iniciar com o Windows
    update_source: str = "repo"     # "repo" (GitHub Releases, padrão) | "folder" (pasta local ou de rede)
    update_repo: str = UPDATE_REPO_DEFAULT   # usuario/repositorio
    update_folder: str = ""         # pasta com o instalador (e, opcionalmente, latest.json)
    update_on_start: bool = False   # verificar ao iniciar
    update_require_signature: bool = True    # só instala se o instalador tiver assinatura digital válida
    update_signer: str = UPDATE_SIGNER_DEFAULT   # impressão(ões) digital(is) aceitas, separadas por vírgula
    scroll_delay_ms: int = 300      # espera após cada rolagem
    scroll_max_height: int = 30000  # altura máxima da captura por rolagem (px)
    scroll_max_frames: int = 80
    gif_fps: int = 12               # quadros por segundo do GIF
    gif_max_seconds: int = 30       # a gravação para sozinha neste tempo
    gif_max_width: int = 960        # largura máxima do GIF (px); acima disso reduz
    mp4_fps: int = 15               # quadros por segundo do vídeo MP4
    mp4_max_seconds: int = 120      # a gravação de vídeo para sozinha neste tempo
    mp4_max_width: int = 1280       # largura máxima do vídeo (px); acima disso reduz
    mp4_max_memory_mb: int = 1500   # memória máxima dos quadros durante a gravação de vídeo
    mp4_audio_system: bool = True   # grava o som do sistema (o que toca nas caixas de som) no vídeo
    mp4_audio_mic: bool = True      # grava o microfone no vídeo
    mp4_mic_device: str = ""        # descrição do microfone; vazio = o padrão do Windows
    gif_cursor_highlight: bool = True   # ponteiro ampliado com halo e anel ao clicar

    # ------------------------------------------------------------------
    @classmethod
    def path(cls) -> Path:
        return config_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
            if data.get("open_editor") is False and "after_capture" not in data:
                data["after_capture"] = "save"          # migração da versão 1.0/1.1
            if "after_capture" not in data and any(k in data for k in ("after_editor", "after_preview", "after_save",
                                                                       "after_copy")):
                # migração da 1.3 (opções combináveis): fica a primeira marcada, nesta ordem
                data["after_capture"] = next((m for m, k in (("editor", "after_editor"), ("preview", "after_preview"),
                                                             ("save", "after_save"), ("copy", "after_copy"))
                                              if data.get(k) is True), "editor")
            if "hotkey_ocr" not in data and isinstance(data.get("hotkey_pin"), str):
                data["hotkey_ocr"] = data["hotkey_pin"]  # o atalho de "fixar" passou a ser o de OCR
            for key, value in data.items():
                # tipo exato (evita que `true` do JSON passe como número)
                if hasattr(cfg, key) and type(value) is type(getattr(cfg, key)):
                    setattr(cfg, key, value)
        except (OSError, ValueError, AttributeError):
            pass
        for key, (old, new) in _OLD_HOTKEY_DEFAULTS.items():
            if getattr(cfg, key) == old:
                setattr(cfg, key, new)
        # limites: um config.json adulterado não pode causar travamento ou uso excessivo de memória
        cfg.update_signer = cfg.update_signer[:400]
        if not cfg.update_signer.strip():           # config.json de versões antigas salvou vazio: usa o certificado fixado
            cfg.update_signer = UPDATE_SIGNER_DEFAULT
        cfg.scroll_delay_ms = min(max(cfg.scroll_delay_ms, 100), 2000)
        cfg.scroll_max_frames = min(max(cfg.scroll_max_frames, 2), 200)
        cfg.scroll_max_height = min(max(cfg.scroll_max_height, 1000), 60000)
        cfg.library_max_items = min(max(cfg.library_max_items, 5), 500)
        cfg.library_max_mb = min(max(cfg.library_max_mb, 20), 20000)
        cfg.preview_seconds = min(max(cfg.preview_seconds, 3), 60)
        cfg.gif_fps = min(max(cfg.gif_fps, 4), 20)
        cfg.gif_max_seconds = min(max(cfg.gif_max_seconds, 3), 180)
        cfg.gif_max_width = min(max(cfg.gif_max_width, 240), 3840)
        cfg.mp4_fps = min(max(cfg.mp4_fps, 5), 30)
        cfg.mp4_max_seconds = min(max(cfg.mp4_max_seconds, 5), 600)
        cfg.mp4_max_width = min(max(cfg.mp4_max_width, 320), 3840)
        cfg.mp4_max_memory_mb = min(max(cfg.mp4_max_memory_mb, 200), 4000)
        cfg.mp4_mic_device = str(cfg.mp4_mic_device or "")[:200]
        if cfg.update_source not in ("repo", "folder"):
            cfg.update_source = "folder"
        if cfg.after_capture not in ("editor", "copy", "save", "preview"):
            cfg.after_capture = "editor"
        if cfg.tools_position not in ("left", "right", "top"):
            cfg.tools_position = "left"
        if cfg.language not in ("auto", "pt", "en", "es"):
            cfg.language = "pt"
        if cfg.theme not in ("dark", "light", "system"):
            cfg.theme = "dark"
        if cfg.save_format not in ("png", "jpg"):
            cfg.save_format = "png"
        cfg.file_name_pattern = str(cfg.file_name_pattern or "").strip()[:100] or "Shotwise_%Y-%m-%d_%H-%M-%S"
        if cfg.close_action not in ("copy", "save"):
            cfg.close_action = "copy"           # inclui o antigo "ask"
        cfg.last_region = cls._valid_region(cfg.last_region)
        return cfg

    @staticmethod
    def _valid_region(v) -> list:
        """Aceita só [str, int, int, int, int, 'area'|'scroll'] com valores plausíveis."""
        if (isinstance(v, list) and len(v) == 6 and isinstance(v[0], str) and len(v[0]) < 200
                and all(type(n) is int for n in v[1:5]) and v[5] in ("area", "scroll")
                and v[1] >= 0 and v[2] >= 0 and 4 <= v[3] <= 20000 and 4 <= v[4] <= 20000):
            return list(v)
        return []

    def save(self) -> None:
        try:
            target = self.path()
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, target)          # troca atômica: uma queda no meio não corrompe o arquivo
        except OSError:
            pass


def apply_install_defaults(cfg: "Config") -> bool:
    """Aplica (uma vez) as escolhas feitas no instalador: ``install_defaults.json`` com update_source/update_folder.
    O arquivo é removido depois de lido. Devolve True se algo foi aplicado."""
    f = config_dir() / "install_defaults.json"
    if not f.is_file():
        return False
    applied = False
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            src = data.get("update_source")
            folder = data.get("update_folder")
            if src in ("repo", "folder"):
                cfg.update_source = src
                applied = True
            if isinstance(folder, str) and len(folder) <= 500:
                cfg.update_folder = folder.strip()
                applied = True
            if cfg.update_source == "folder" and not cfg.update_folder:
                cfg.update_source = "repo"          # sem pasta não há o que consultar
    except (OSError, ValueError):
        pass
    try:
        f.unlink()
    except OSError:
        pass
    if applied:
        cfg.save()
    return applied
