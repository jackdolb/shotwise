"""Atualização do Shotwise: procura uma versão mais nova num repositório (GitHub Releases) ou numa pasta
(local ou de rede), baixa o instalador, confere o SHA-256 quando ele é informado e executa em modo silencioso."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from . import __version__

SETUP_RE = re.compile(r"^Shotwise(-Python)?-Setup-(\d+(?:\.\d+)*)\.exe$", re.IGNORECASE)
TIMEOUT = 20
MAX_INSTALLER_BYTES = 600 * 1024 * 1024     # um instalador maior que isso não é aceito
MAX_MANIFEST_BYTES = 1024 * 1024


@dataclass
class UpdateInfo:
    version: str
    source: str                 # caminho da pasta/arquivo ou URL https
    name: str                   # nome do instalador
    sha256: str | None = None
    is_url: bool = False


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def wanted_prefix() -> bool:
    """True = instalador completo (PyInstaller); False = instalador "modo Python"."""
    return bool(getattr(sys, "frozen", False))


def _matches_flavor(name: str, frozen: bool) -> re.Match | None:
    m = SETUP_RE.match(name)
    if m is None:
        return None
    is_python = bool(m.group(1))
    return m if is_python == (not frozen) else None


def find_in_folder(folder: str, frozen: bool | None = None) -> UpdateInfo | None:
    """Procura o instalador mais novo na pasta. Aceita um `latest.json` ({"version","file","sha256"}) ou,
    na falta dele, o maior número de versão entre os arquivos Shotwise[-Python]-Setup-X.Y.Z.exe."""
    frozen = wanted_prefix() if frozen is None else frozen
    d = Path(folder)
    if not folder or not d.is_dir():
        raise FileNotFoundError(folder)
    manifest = d / "latest.json"
    if manifest.is_file():
        if manifest.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("latest.json grande demais")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        files = data.get("files")
        entry = None
        if isinstance(files, dict):               # {"installer": {...}, "python": {...}}
            entry = files.get("installer" if frozen else "python")
        elif data.get("file"):
            entry = {"file": data["file"], "sha256": data.get("sha256")}
        if entry and entry.get("file"):
            name = Path(entry["file"]).name       # só o nome: nunca segue caminhos relativos
            if (d / name).is_file():
                return UpdateInfo(str(data.get("version", "0")), str(d / name), name, entry.get("sha256"))
    best: tuple[tuple[int, ...], Path] | None = None
    for f in d.iterdir():
        m = _matches_flavor(f.name, frozen)
        if m and f.is_file():
            v = parse_version(m.group(2))
            if best is None or v > best[0]:
                best = (v, f)
    if best is None:
        return None
    sha_file = best[1].with_name(best[1].name + ".sha256")
    sha = None
    if sha_file.is_file():
        sha = sha_file.read_text(encoding="utf-8").split()[0]
    return UpdateInfo(".".join(map(str, best[0])), str(best[1]), best[1].name, sha)


def _repo_slug(text: str) -> str:
    text = text.strip().rstrip("/")
    m = re.search(r"github\.com[/:]([\w.-]+/[\w.-]+?)(?:\.git)?$", text)
    slug = m.group(1) if m else text
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", slug):
        raise ValueError("Use o formato usuario/repositorio")
    return slug


def _opener():
    """Abridor de URLs que só segue redirecionamentos para HTTPS."""
    import urllib.error
    import urllib.request

    class _HttpsOnly(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not newurl.lower().startswith("https://"):
                raise urllib.error.URLError("redirecionamento para endereço não seguro recusado")
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(_HttpsOnly)


def find_in_repo(repo: str, frozen: bool | None = None) -> UpdateInfo | None:
    import urllib.request

    frozen = wanted_prefix() if frozen is None else frozen
    url = f"https://api.github.com/repos/{_repo_slug(repo)}/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Shotwise-updater"})
    with _opener().open(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read(MAX_MANIFEST_BYTES + 1).decode("utf-8"))
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if _matches_flavor(name, frozen) and str(asset.get("browser_download_url", "")).startswith("https://"):
            digest = asset.get("digest") or ""
            sha = digest.split(":", 1)[1] if digest.startswith("sha256:") else None
            return UpdateInfo(str(data.get("tag_name", "0")).lstrip("vV"), asset["browser_download_url"], name, sha, True)
    return None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_thumbprints(text: str) -> list[str]:
    """Aceita impressões digitais (SHA-1, 40 hex) separadas por vírgula, ponto e vírgula ou espaço."""
    out = []
    for t in re.split(r"[\s,;]+", text or ""):
        t = t.replace(":", "").upper()
        if re.fullmatch(r"[0-9A-F]{40}", t):
            out.append(t)
    return out


def signature_ok(status: str, thumbprint: str, pinned: list[str]) -> bool:
    """Assinatura válida e, se houver impressões digitais fixadas, emitida por uma delas."""
    if status != "Valid":
        return False
    return not pinned or (thumbprint or "").upper() in pinned


def check_signature(path: Path) -> tuple[str, str]:
    """(status, impressão digital) da assinatura Authenticode, via PowerShell (só no Windows).
    O caminho vai por variável de ambiente, nunca dentro do comando."""
    if sys.platform != "win32":
        return "Unsupported", ""
    script = ("$s = Get-AuthenticodeSignature -LiteralPath $env:SHOTWISE_VERIFY_FILE; "
              "$t = ''; if ($s.SignerCertificate) { $t = $s.SignerCertificate.Thumbprint }; "
              "[Console]::Out.Write(\"$($s.Status)|$t\")")
    env = dict(os.environ, SHOTWISE_VERIFY_FILE=str(path))
    ps = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    try:
        r = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],  # nosec B603
                           capture_output=True, text=True, timeout=60, env=env, check=False)
    except (OSError, subprocess.SubprocessError):
        return "Error", ""
    status, _, thumb = (r.stdout or "").strip().partition("|")
    return status or "Error", thumb


def download(info: UpdateInfo, progress=None, *, require_hash: bool = True, require_signature: bool = False,
             signers: str = "") -> Path:
    """Copia/baixa o instalador para uma pasta temporária e o confere: SHA-256 (obrigatório por padrão) e,
    se pedido, a assinatura digital (opcionalmente de um emissor fixado). Levanta ValueError se algo não bater."""
    if require_hash and not info.sha256:
        raise ValueError("A atualização não informa o SHA-256 do instalador; por segurança ela foi recusada")
    dest_dir = Path(tempfile.mkdtemp(prefix="shotwise_update_"))
    dest = dest_dir / Path(info.name).name
    try:
        if info.is_url:
            if not info.source.startswith("https://"):
                raise ValueError("Somente downloads HTTPS são aceitos")
            with _opener().open(info.source, timeout=TIMEOUT) as r, open(dest, "wb") as out:
                total = int(r.headers.get("Content-Length") or 0)
                if total > MAX_INSTALLER_BYTES:
                    raise ValueError("Instalador grande demais")
                got = 0
                while chunk := r.read(1 << 16):
                    got += len(chunk)
                    if got > MAX_INSTALLER_BYTES:
                        raise ValueError("Instalador grande demais")
                    out.write(chunk)
                    if progress and total:
                        progress(int(got * 100 / total))
        else:
            if os.path.getsize(info.source) > MAX_INSTALLER_BYTES:
                raise ValueError("Instalador grande demais")
            shutil.copyfile(info.source, dest)
            if progress:
                progress(100)
        if info.sha256 and sha256_of(dest).lower() != info.sha256.lower():
            raise ValueError("O arquivo baixado não confere com o SHA-256 informado")
        if require_signature:
            status, thumb = check_signature(dest)
            if not signature_ok(status, thumb, normalize_thumbprints(signers)):
                raise ValueError(f"Assinatura digital do instalador recusada (estado: {status})")
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return dest


def run_installer(path: str) -> bool:
    """Executa o instalador em modo silencioso (ele mesmo fecha o Shotwise em uso)."""
    from PySide6.QtCore import QProcess

    # /RELAUNCH=1: o instalador reabre o Shotwise ao terminar (a atualização é silenciosa, sem tela final)
    return QProcess.startDetached(path, ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1"])


class UpdateWorker(QThread):
    """Verifica (mode='check') ou baixa (mode='download') em segundo plano."""
    found = Signal(object)          # UpdateInfo | None
    ready = Signal(str)             # caminho do instalador baixado
    progress = Signal(int)
    failed = Signal(str)

    def __init__(self, source: str, location: str, mode: str = "check", info: UpdateInfo | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.source, self.location, self.mode, self.info = source, location, mode, info

    def run(self):
        try:
            if self.mode == "download":
                from .config import Config
                cfg = Config.load()
                self.ready.emit(str(download(self.info, self.progress.emit, require_signature=cfg.update_require_signature,
                                             signers=cfg.update_signer)))
                return
            info = find_in_repo(self.location) if self.source == "repo" else find_in_folder(self.location)
            self.found.emit(info if info and is_newer(info.version) else None)
        except Exception as exc:  # noqa: BLE001 - qualquer falha de rede/arquivo vira mensagem para o usuário
            self.failed.emit(str(exc))
