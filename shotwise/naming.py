"""Nome e pasta dos arquivos salvos: padrão de nome configurável (códigos de data do strftime) e subpastas por ano/mês."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

DEFAULT_PATTERN = "Shotwise_%Y-%m-%d_%H-%M-%S"
MAX_NAME = 120
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def format_name(pattern: str, now: datetime | None = None) -> str:
    """Aplica o padrão à data/hora e deixa o resultado seguro como nome de arquivo (sem separadores de pasta nem
    caracteres que o Windows recusa). Padrão vazio ou inválido volta ao padrão de fábrica."""
    now = now or datetime.now()
    try:
        name = now.strftime((pattern or "").strip() or DEFAULT_PATTERN)
    except ValueError:
        name = now.strftime(DEFAULT_PATTERN)
    name = _BAD.sub("_", name).strip().rstrip(". ")[:MAX_NAME].rstrip(". ")
    if not name:
        name = now.strftime(DEFAULT_PATTERN)
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name


def build_path(save_dir: str, ext: str, pattern: str = DEFAULT_PATTERN, by_month: bool = False,
               now: datetime | None = None, create: bool = True) -> Path:
    """Caminho completo do próximo arquivo. Com ``by_month``, usa ``pasta/AAAA/MM``. Se o nome já existir, acrescenta _2, _3…"""
    now = now or datetime.now()
    folder = Path(save_dir)
    if by_month:
        folder = folder / f"{now:%Y}" / f"{now:%m}"
    if create:
        folder.mkdir(parents=True, exist_ok=True)
    ext = ext.lstrip(".")
    base = format_name(pattern, now)
    path = folder / f"{base}.{ext}"
    n = 2
    while path.exists() and n < 1000:
        path = folder / f"{base}_{n}.{ext}"
        n += 1
    return path
