"""Grava <arquivo>.sha256 no formato "hash  nome" (usado pelo atualizador do Shotwise).

Usa só Python: não depende do Get-FileHash do PowerShell (que falha quando a janela foi aberta pelo
PowerShell 7 ou em modo de linguagem restrita).
"""
import hashlib
import os
import sys


def main(paths: list[str]) -> int:
    if not paths:
        print("uso: python tools\\write_sha256.py arquivo [arquivo...]")
        return 2
    rc = 0
    for path in paths:
        if not os.path.isfile(path):
            print(f"[sha256] arquivo nao encontrado: {path}")
            rc = 1
            continue
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        line = f"{h.hexdigest()}  {os.path.basename(path)}\n"
        with open(path + ".sha256", "w", encoding="ascii", newline="\n") as out:
            out.write(line)
        print(f"[sha256] {line.strip()}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
