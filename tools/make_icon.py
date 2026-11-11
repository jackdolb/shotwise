"""Gera assets/icon.ico a partir do ícone desenhado em código."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from shotwise.icons import app_pixmap  # noqa: E402


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 - necessário para QPixmap
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, "icon.ico")
    # o plugin ICO do Qt grava a imagem em um único tamanho (256 px)
    ok = app_pixmap(256).toImage().save(target, "ICO")
    if not ok:
        png = os.path.join(out_dir, "icon.png")
        app_pixmap(256).save(png, "PNG")
        print(f"Não foi possível gravar .ico; PNG salvo em {png}")
        return 1
    print(f"Ícone gerado: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
