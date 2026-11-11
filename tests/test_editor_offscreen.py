"""Testes do editor sem tela (QT_QPA_PLATFORM=offscreen)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QPointF, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from shotwise.annotations import (AnnotScene, LineItem, ShapeItem, StepItem, TextItem,  # noqa: E402
                                 AddCommand)
from shotwise.imageutil import np_to_qimage, qimage_to_np  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def sample_image(w=640, h=400) -> QImage:
    """Imagem com 'texto' e ruído, para testar ocultação."""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#f4f4f4"))
    p = QPainter(img)
    p.setPen(QColor("#202020"))
    f = QFont("DejaVu Sans")
    f.setPixelSize(22)
    p.setFont(f)
    p.drawText(40, 80, "usuario: jackson.silva")
    p.drawText(40, 130, "senha: S3nh4-Sup3r-S3cr3t4!")
    p.drawText(40, 180, "token: eyJhbGciOiJIUzI1NiJ9")
    p.end()
    return img


def region_np(img: QImage, x, y, w, h):
    return qimage_to_np(img.copy(x, y, w, h))


def add(scene, item):
    scene.addItem(item)
    scene.undo_stack.push(AddCommand(scene, item))


def test_roundtrip_numpy(qapp):
    img = sample_image()
    back = np_to_qimage(qimage_to_np(img))
    assert np.array_equal(qimage_to_np(img), qimage_to_np(back))


def test_render_without_annotations_is_identical(qapp):
    img = sample_image()
    scene = AnnotScene(img)
    out = scene.render_image()
    assert out.size() == img.size()
    assert np.array_equal(qimage_to_np(out), qimage_to_np(img))


def test_redact_is_solid_and_irreversible(qapp):
    img = sample_image()
    scene = AnnotScene(img)
    add(scene, ShapeItem("redact", QRectF(30, 105, 400, 40), QColor("#000000")))
    out = scene.render_image()
    inside = region_np(out, 35, 110, 390, 30)
    assert (inside == 0).all(), "a tarja deve ser totalmente preta (sem vazamento de pixels originais)"
    # fora da tarja nada muda
    assert np.array_equal(region_np(out, 0, 0, 640, 100), region_np(img, 0, 0, 640, 100))


def test_pixelate_destroys_text_detail(qapp):
    img = sample_image()
    scene = AnnotScene(img)
    add(scene, ShapeItem("pixelate", QRectF(30, 105, 400, 40), QColor("#000"), strength=16))
    out = scene.render_image()
    before = region_np(img, 30, 105, 400, 40).astype(int)
    after = region_np(out, 30, 105, 400, 40).astype(int)
    assert np.abs(before - after).mean() > 5            # região foi alterada
    # em blocos de 16px os valores devem ser quase constantes
    block = after[8:24, 16:32]
    assert block.std() < 6


def test_blur_changes_region_only(qapp):
    img = sample_image()
    scene = AnnotScene(img)
    add(scene, ShapeItem("blur", QRectF(30, 155, 400, 40), QColor("#000"), strength=12))
    out = scene.render_image()
    assert np.abs(region_np(img, 30, 155, 400, 40).astype(int) - region_np(out, 30, 155, 400, 40).astype(int)).mean() > 3
    assert np.array_equal(region_np(out, 0, 0, 640, 140), region_np(img, 0, 0, 640, 140))


def test_effect_follows_item_when_moved(qapp):
    img = sample_image()
    scene = AnnotScene(img)
    item = ShapeItem("redact", QRectF(0, 0, 100, 30), QColor("black"))
    add(scene, item)
    item.setPos(200, 200)
    out = scene.render_image()
    assert (region_np(out, 205, 205, 90, 20) == 0).all()
    assert np.array_equal(region_np(out, 0, 0, 100, 30), region_np(img, 0, 0, 100, 30))


def test_undo_redo_add_and_remove(qapp):
    scene = AnnotScene(sample_image())
    a = ShapeItem("rect", QRectF(10, 10, 50, 50), QColor("red"))
    add(scene, a)
    assert a.scene() is scene
    scene.undo_stack.undo()
    assert a.scene() is None
    scene.undo_stack.redo()
    assert a.scene() is scene
    a.setSelected(True)
    scene.delete_selected()
    assert a.scene() is None
    scene.undo_stack.undo()
    assert a.scene() is scene


def test_arrow_text_and_step_render(qapp):
    img = sample_image()
    scene = AnnotScene(img)
    add(scene, LineItem("arrow", QPointF(300, 300), QPointF(500, 350), QColor("#ff3b30"), 6))
    t = TextItem("Atenção", QColor("#0a84ff"), 30)
    t.setPos(60, 300)
    add(scene, t)
    s = StepItem(scene.next_step_number(), QColor("#34c759"), 16)
    s.setPos(580, 60)
    add(scene, s)
    assert s.number == 1 and scene.next_step_number() == 2
    out = scene.render_image()
    assert np.abs(region_np(out, 280, 280, 240, 90).astype(int) - region_np(img, 280, 280, 240, 90).astype(int)).sum() > 0
    assert np.abs(region_np(out, 560, 40, 40, 40).astype(int) - region_np(img, 560, 40, 40, 40).astype(int)).sum() > 0


def test_crop_is_non_destructive_and_undoable(qapp):
    img = sample_image()
    scene = AnnotScene(img)
    box = ShapeItem("redact", QRectF(0, 0, 80, 30), QColor("black"))
    add(scene, box)
    box.setPos(300, 200)
    from shotwise.annotations import CropItem

    scene._crop = CropItem(QRectF(250, 150, 300, 200))
    scene.addItem(scene._crop)
    assert scene.apply_crop()
    assert scene.output_size() == (300, 200)
    assert (box.pos().x(), box.pos().y()) == (300, 200)      # itens não se movem
    out = scene.render_image()
    assert out.width() == 300 and (region_np(out, 55, 55, 70, 20) == 0).all()
    assert scene.layers()[0].image.width() == 640            # pixels originais intactos
    scene.undo_stack.undo()
    assert scene.output_size() == (640, 400)


def test_style_change_is_undoable(qapp):
    scene = AnnotScene(sample_image())
    r = ShapeItem("rect", QRectF(10, 10, 60, 40), QColor("#ff3b30"), 4)
    add(scene, r)
    r.setSelected(True)
    scene.apply_style_to_selection(color=QColor("#0a84ff"), width=9)
    assert r.color == QColor("#0a84ff") and r.width == 9
    scene.undo_stack.undo()
    assert r.color == QColor("#ff3b30") and r.width == 4


def test_clipboard_copy_roundtrip(qapp):
    from PySide6.QtGui import QGuiApplication

    from shotwise.clipboard import copy_image

    img = sample_image(120, 80)
    copy_image(img)
    back = QGuiApplication.clipboard().image()
    assert not back.isNull() and back.size() == img.size()


def test_config_load_clamps_and_rejects_wrong_types(qapp, tmp_path, monkeypatch):
    import json

    from shotwise import config as cfgmod

    monkeypatch.setattr(cfgmod, "config_dir", lambda: tmp_path)
    (tmp_path / "config.json").write_text(json.dumps({
        "scroll_delay_ms": 10**9, "scroll_max_frames": -5, "scroll_max_height": 10**12,
        "include_cursor": "sim", "save_format": "xyz",       # valores inválidos: ignorados
    }))
    c = cfgmod.Config.load()
    assert c.scroll_delay_ms == 2000 and c.scroll_max_frames == 2 and c.scroll_max_height == 60000
    assert c.include_cursor is False and c.save_format == "png"      # valores padrão mantidos


def test_editor_window_builds_and_saves(qapp, tmp_path):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    cfg = Config()
    cfg.save_dir = str(tmp_path)
    cfg.library_enabled = False
    win = EditorWindow(sample_image(), cfg)
    win.show()
    qapp.processEvents()
    for tool in ("arrow", "rect", "text", "step", "pixelate", "blur", "redact", "crop", "select"):
        win.select_tool(tool)
    win.select_tool("redact")
    add(win.scene, ShapeItem("redact", QRectF(30, 105, 300, 40), QColor("black")))
    assert win.save()
    files = list(tmp_path.glob("Shotwise_*.png"))
    assert len(files) == 1
    saved = QImage(str(files[0]))
    assert saved.size() == win.scene.layers()[0].image.size()
    assert (region_np(saved, 40, 110, 280, 30) == 0).all()
    win.finish()
