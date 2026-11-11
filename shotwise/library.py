"""Biblioteca local de capturas editáveis em %APPDATA%\\Shotwise\\library.

Cada item é um arquivo .shotwin (ver project.py). A biblioteca guarda as imagens originais,
sem tarjas; por isso há exclusão individual e limite de itens (os mais antigos são removidos).
"""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QImage

from . import project
from .config import config_dir

_ID = re.compile(r"^[0-9a-f]{16}$")


def library_dir() -> Path:
    d = config_dir() / "library"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Entry:
    id: str
    path: str
    title: str
    created: str
    updated: str
    export_path: str
    size: tuple[int, int]


def _path_for(pid: str) -> str:
    if not _ID.match(pid):
        raise ValueError("id inválido")
    return str(library_dir() / f"{pid}.shotwin")


def new_id() -> str:
    return secrets.token_hex(8)


def save(scene, pid: str | None = None, export_path: str = "", title: str = "") -> str:
    """Grava (ou atualiza) o projeto na biblioteca e devolve o id."""
    pid = pid or new_id()
    path = _path_for(pid)
    created = None
    if os.path.exists(path):
        try:
            old = project.read_meta(path)
            created = old.get("created")
            export_path = export_path or old.get("export_path", "")
            title = title or old.get("title", "")
        except project.ProjectError:
            pass
    meta = {"title": title or "Captura", "export_path": export_path}
    if created:
        meta["created"] = created
    project.write_project(path, scene, meta)
    return pid


def entries() -> list[Entry]:
    out: list[Entry] = []
    for f in library_dir().glob("*.shotwin"):
        if not _ID.match(f.stem):
            continue
        try:
            m = project.read_meta(str(f))
        except project.ProjectError:
            continue
        size = m.get("size")
        sz = (int(size[0]), int(size[1])) if isinstance(size, list) and len(size) == 2 and all(
            isinstance(v, int) for v in size) else (0, 0)
        out.append(Entry(f.stem, str(f), str(m.get("title", "Captura"))[:120], str(m.get("created", "")),
                         str(m.get("updated", "")), str(m.get("export_path", "")), sz))
    out.sort(key=lambda e: e.updated, reverse=True)
    return out


def thumb(pid: str) -> QImage:
    try:
        return project.read_thumb(_path_for(pid))
    except (project.ProjectError, ValueError):
        return QImage()


def load(pid: str) -> project.ProjectData:
    return project.read_project(_path_for(pid))


def delete(pid: str) -> bool:
    try:
        os.remove(_path_for(pid))
        return True
    except (OSError, ValueError):
        return False


def delete_all() -> int:
    n = 0
    for e in entries():
        n += delete(e.id)
    return n


def prune(max_items: int, max_mb: int = 0) -> int:
    """Remove os itens mais antigos acima dos limites (quantidade e/ou MB; 0 = sem limite de MB).

    O item mais recente nunca é apagado. Devolve quantos apagou."""
    items = entries()
    removed = 0
    for e in items[max(1, max_items):]:
        removed += delete(e.id)
    if max_mb > 0:
        keep = items[:max(1, max_items)]
        sizes = []
        for e in keep:
            try:
                sizes.append(os.path.getsize(e.path))
            except OSError:
                sizes.append(0)
        total = sum(sizes)
        limit = max_mb * 1024 * 1024
        i = len(keep) - 1
        while total > limit and i >= 1:            # do mais antigo para o mais novo
            removed += delete(keep[i].id)
            total -= sizes[i]
            i -= 1
    return removed


def total_size_mb() -> float:
    return sum(os.path.getsize(e.path) for e in entries() if os.path.exists(e.path)) / (1024 * 1024)


def find_by_export_path(export_path: str) -> str | None:
    if not export_path:
        return None
    target = os.path.normcase(os.path.abspath(export_path))
    for e in entries():
        if e.export_path and os.path.normcase(os.path.abspath(e.export_path)) == target:
            return e.id
    return None
