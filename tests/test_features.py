"""Testes dos recursos: texto com fundo, várias imagens, fundo, tamanho, projeto/biblioteca, pin, seleção."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json  # noqa: E402
import zipfile  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from shotwise import library, project  # noqa: E402
from shotwise.annotations import AddCommand, AnnotScene, BackgroundSettings, ShapeItem, TextItem  # noqa: E402
from shotwise.imageutil import qimage_to_np  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def libdir(tmp_path, monkeypatch):
    from shotwise import config as cfgmod

    monkeypatch.setattr(cfgmod, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(library, "config_dir", lambda: tmp_path)
    return tmp_path


def solid(w, h, color):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return img


def add(scene, item):
    scene.addItem(item)
    scene.undo_stack.push(AddCommand(scene, item))


# --- texto com fundo -------------------------------------------------------
def test_text_background_transparent_vs_colored(qapp):
    def render(bg):
        scene = AnnotScene(solid(300, 120, "#ffffff"))
        t = TextItem("Oi", QColor("#000000"), 30, bg)
        t.setPos(10, 10)
        add(scene, t)
        return qimage_to_np(scene.render_image())

    plain = render(None)
    colored = render(QColor("#ffd60a"))
    corner = (14, 14)                      # dentro da caixa, longe das letras
    assert tuple(plain[corner]) == (255, 255, 255)
    assert tuple(colored[corner]) != (255, 255, 255)


def test_text_background_style_is_undoable(qapp):
    scene = AnnotScene(solid(200, 100, "#fff"))
    t = TextItem("x", QColor("black"), 20)
    add(scene, t)
    t.setSelected(True)
    scene.apply_style_to_selection(text_bg=QColor("#00ff00"))
    assert t.bg == QColor("#00ff00")
    scene.undo_stack.undo()
    assert t.bg is None


# --- várias capturas na mesma imagem ---------------------------------------
def test_insert_second_image_side_by_side(qapp):
    scene = AnnotScene(solid(200, 100, "#ff0000"))
    scene.insert_image(solid(120, 80, "#0000ff"))
    assert len(scene.layers()) == 2
    w, h = scene.output_size()
    assert h == 100 and w == 200 + 24 + 120
    out = qimage_to_np(scene.render_image())
    assert tuple(out[50, 10]) == (255, 0, 0)
    assert tuple(out[40, 200 + 24 + 10]) == (0, 0, 255)
    scene.undo_stack.undo()
    assert len(scene.layers()) == 1 and scene.output_size() == (200, 100)


def test_cannot_delete_last_layer_and_effects_span_layers(qapp):
    scene = AnnotScene(solid(100, 100, "#ff0000"))
    scene.layers()[0].setSelected(True)
    scene.delete_selected()
    assert len(scene.layers()) == 1
    scene.insert_image(solid(100, 100, "#00ff00"))
    add(scene, ShapeItem("redact", QRectF(90, 10, 30, 20), QColor("black")))   # cruza as duas imagens
    out = qimage_to_np(scene.render_image())
    assert (out[12:28, 92:118] == 0).all()


def test_blur_samples_all_layers(qapp):
    scene = AnnotScene(solid(100, 100, "#ff0000"))
    scene.insert_image(solid(100, 100, "#00ff00"))
    add(scene, ShapeItem("pixelate", QRectF(0, 0, 224, 100), QColor("black"), strength=16))
    out = qimage_to_np(scene.render_image())
    assert out.shape[1] == 224


# --- fundo -----------------------------------------------------------------
def test_background_adds_padding_and_is_undoable(qapp):
    scene = AnnotScene(solid(200, 100, "#ffffff"))
    old = scene.background.copy()
    scene.commit_background(old, BackgroundSettings(True, "#ff0000", "#0000ff", False, 40, 0, False))
    assert scene.output_size() == (280, 180)
    out = qimage_to_np(scene.render_image())
    assert out.shape[:2] == (180, 280)
    assert tuple(out[60, 60]) == (255, 255, 255)          # a captura continua no centro
    assert tuple(out[2, 2]) != (255, 255, 255)            # margem com cor
    scene.undo_stack.undo()
    assert scene.output_size() == (200, 100)


def test_background_transparent_keeps_alpha(qapp):
    scene = AnnotScene(solid(100, 60, "#ffffff"))
    scene.background = BackgroundSettings(True, "#000000", "#000000", True, 30, 12, False)
    img = scene.render_image()
    assert img.hasAlphaChannel() and img.pixelColor(2, 2).alpha() == 0
    assert img.pixelColor(60, 40).alpha() == 255


# --- tamanho ---------------------------------------------------------------
def test_export_scale_resizes_output(qapp):
    scene = AnnotScene(solid(400, 200, "#abcdef"))
    scene.set_export_scale(0.5)
    assert scene.output_size() == (200, 100)
    assert scene.render_image().size().width() == 200
    scene.undo_stack.undo()
    assert scene.output_size() == (400, 200)


def test_resize_dialog_keeps_aspect(qapp):
    from shotwise.dialogs import ResizeDialog

    scene = AnnotScene(solid(400, 200, "#fff"))
    dlg = ResizeDialog(scene)
    dlg.sp_w.setValue(200)
    assert dlg.sp_h.value() == 100 and dlg.sp_p.value() == 50 and abs(dlg.scale() - 0.5) < 1e-9


# --- projeto / biblioteca --------------------------------------------------
def make_scene():
    scene = AnnotScene(solid(300, 200, "#e0e0e0"))
    scene.insert_image(solid(100, 100, "#3050a0"))
    add(scene, ShapeItem("redact", QRectF(10, 10, 60, 30), QColor("black")))
    t = TextItem("senha", QColor("#ff0000"), 24, QColor("#ffffff"))
    t.setPos(20, 120)
    add(scene, t)
    scene.background = BackgroundSettings(True, "#112233", "#445566", False, 20, 8, True)
    scene.export_scale = 0.75
    scene.refresh_canvas()
    return scene


def test_project_roundtrip_renders_identically(qapp, libdir):
    scene = make_scene()
    pid = library.save(scene, title="teste", export_path="C:/x.png")
    data = library.load(pid)
    scene2 = project.build_scene(data)
    assert scene.render_image() == scene2.render_image()
    assert scene2.undo_stack.isClean() and scene2.undo_stack.count() == 0
    e = library.entries()[0]
    assert e.id == pid and e.title == "teste" and e.export_path == "C:/x.png"
    assert library.find_by_export_path("C:/x.png") == pid


def test_project_keeps_original_pixels_under_redaction(qapp, libdir):
    scene = AnnotScene(solid(100, 100, "#ff0000"))
    add(scene, ShapeItem("redact", QRectF(0, 0, 100, 100), QColor("black")))
    pid = library.save(scene)
    scene2 = project.build_scene(library.load(pid))
    assert (qimage_to_np(scene.render_image()) == 0).all()
    assert tuple(qimage_to_np(scene2.layers()[0].image)[5, 5]) == (255, 0, 0)    # original preservado
    scene2.undo_stack.clear()
    for it in list(scene2.items()):
        if isinstance(it, ShapeItem):                       # a tarja pode ser removida: é editável
            scene2.removeItem(it)
    assert tuple(qimage_to_np(scene2.render_image())[5, 5]) == (255, 0, 0)


def test_library_prune_and_delete(qapp, libdir):
    ids = []
    for i in range(4):
        sc = AnnotScene(solid(20, 20, "#fff"))
        ids.append(library.save(sc, title=f"c{i}"))
    assert len(library.entries()) == 4
    assert library.prune(2) == 2 and len(library.entries()) == 2
    assert library.delete(library.entries()[0].id)
    assert len(library.entries()) == 1
    assert library.delete("../etc/passwd") is False          # id inválido é recusado


def _write_zip(path, members):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)


def test_project_reader_rejects_malicious_files(qapp, tmp_path):
    good = tmp_path / "good.shotwin"
    project.write_project(str(good), AnnotScene(solid(50, 50, "#fff")), {"title": "t"})
    assert project.read_project(str(good)).layers

    # membro com caminho fora da lista
    bad = tmp_path / "bad1.shotwin"
    _write_zip(bad, {"meta.json": "{}", "project.json": "{}", "../evil.txt": "x"})
    with pytest.raises(project.ProjectError):
        project.read_project(str(bad))

    # não é zip
    notzip = tmp_path / "bad2.shotwin"
    notzip.write_bytes(b"MZ not a zip")
    with pytest.raises(project.ProjectError):
        project.read_project(str(notzip))

    # JSON com números absurdos e tipos errados não quebra nem aloca gigantes
    scene = AnnotScene(solid(50, 50, "#fff"))
    doc, images = project.scene_to_dict(scene)
    doc["export_scale"] = 1e30
    doc["items"] = [{"t": "rect", "pos": [1e30, "x"], "rect": [0, 0, 1e30, 5], "color": "zzz", "width": 1e12}]
    mal = tmp_path / "bad3.shotwin"
    _write_zip(mal, {"meta.json": "{}", "project.json": json.dumps(doc),
                     "layers/0.png": project._png_bytes(images[0])})
    pd = project.read_project(str(mal))
    assert pd.export_scale == 8.0                         # limitado
    s = project.build_scene(pd)                           # não levanta exceção
    assert s.output_size()[0] > 0

    # item desconhecido é ignorado; versão errada é recusada
    doc["version"] = 99
    old = tmp_path / "bad4.shotwin"
    _write_zip(old, {"meta.json": "{}", "project.json": json.dumps(doc),
                     "layers/0.png": project._png_bytes(images[0])})
    with pytest.raises(project.ProjectError):
        project.read_project(str(old))


def test_project_reader_limits_image_dimensions(qapp, tmp_path):
    big = QImage(10, 10, QImage.Format.Format_RGB32)
    doc = {"version": 1, "layers": [{"file": "layers/0.png", "pos": [0, 0], "box": [0, 0, 10, 10]}],
           "items": []}
    old_side = project.MAX_SIDE
    project.MAX_SIDE = 5
    try:
        p = tmp_path / "big.shotwin"
        _write_zip(p, {"meta.json": "{}", "project.json": json.dumps(doc), "layers/0.png": project._png_bytes(big)})
        with pytest.raises(project.ProjectError):
            project.read_project(str(p))
    finally:
        project.MAX_SIDE = old_side


# --- editor: salvar -> fechar -> reabrir -----------------------------------
def test_editor_save_close_reopen_and_continue(qapp, libdir):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    cfg = Config()
    cfg.save_dir = str(libdir / "out")
    win = EditorWindow(solid(300, 200, "#dddddd"), cfg)
    win.show()
    add(win.scene, ShapeItem("redact", QRectF(10, 10, 100, 40), QColor("black")))
    assert win.save()
    pid = win.pid
    png = win.saved_path
    assert pid and png.is_file()
    win.finish()

    data = library.load(pid)
    win2 = EditorWindow(None, cfg, project=data, pid=pid)
    win2.show()
    assert win2.saved_path == png and win2.pid == pid
    shapes = [i for i in win2.scene.items() if isinstance(i, ShapeItem)]
    assert len(shapes) == 1
    shapes[0].setSelected(True)
    win2.scene.delete_selected()                          # continua editável: removo a tarja
    assert win2.save()
    assert len(library.entries()) == 1                    # atualizou o mesmo item
    out = QImage(str(png))
    assert qimage_to_np(out)[20, 20].tolist() == [221, 221, 221]
    win2.finish()


def test_editor_add_image_and_background_flow(qapp, libdir):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    cfg = Config()
    cfg.library_enabled = False
    win = EditorWindow(solid(300, 200, "#dddddd"), cfg)
    win.show()
    win._insert(solid(100, 100, "#ff0000"), "Adicionar captura")
    assert len(win.scene.layers()) == 2
    win.scene.commit_background(win.scene.background.copy(), BackgroundSettings(True, "#fff", "#000", False, 30, 10, True))
    win.view.fit_initial()
    w, h = win.scene.output_size()
    assert (w, h) == (300 + 24 + 100 + 60, 200 + 60)
    win.scene.undo_stack.undo()
    win.scene.undo_stack.undo()
    assert len(win.scene.layers()) == 1


# --- pin e seleção ajustável -----------------------------------------------
def test_pin_window_basics(qapp):
    from shotwise.pin import PinWindow

    pin = PinWindow(solid(200, 100, "#00ff00"))
    assert pin.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    pin.show()
    w0 = pin.width()
    pin._scale *= 2
    pin._apply_size()
    assert pin.width() == w0 * 2
    closed = []
    pin.closed.connect(closed.append)
    pin.close()
    assert closed


def test_selector_adjust_flow(qapp):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from shotwise.selector import RegionOverlay

    screen = qapp.primaryScreen()
    ov = RegionOverlay(screen, QImage(screen.size(), QImage.Format.Format_RGB32), "x", adjustable=True)
    ov.resize(800, 600)
    got = []
    ov.region_selected.connect(lambda o, l, p: got.append(l))

    def mouse(kind, x, y):
        t = {"press": QEvent.Type.MouseButtonPress, "move": QEvent.Type.MouseMove,
             "release": QEvent.Type.MouseButtonRelease}[kind]
        btn = Qt.MouseButton.LeftButton if kind != "move" else Qt.MouseButton.NoButton
        ev = QMouseEvent(t, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton, btn if kind != "move"
                         else Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        {"press": ov.mousePressEvent, "move": ov.mouseMoveEvent, "release": ov.mouseReleaseEvent}[kind](ev)

    mouse("press", 100, 100)
    mouse("move", 300, 250)
    mouse("release", 300, 250)
    assert not got and ov._adjusting                      # com ajuste, soltar NÃO confirma
    # arrasta a alça inferior direita para aumentar a área
    mouse("press", 300, 250)
    mouse("move", 400, 350)
    mouse("release", 400, 350)
    assert ov.selection() == QRect(QPoint(100, 100), QPoint(400, 350))
    # move a seleção inteira
    mouse("press", 200, 200)
    mouse("move", 230, 210)
    mouse("release", 230, 210)
    assert ov.selection().topLeft() == QPoint(130, 110)
    from PySide6.QtGui import QKeyEvent

    ov.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
    assert len(got) == 1 and got[0].topLeft() == QPoint(130, 110)


def test_selector_without_adjust_confirms_on_release(qapp):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from shotwise.selector import RegionOverlay

    screen = qapp.primaryScreen()
    ov = RegionOverlay(screen, QImage(screen.size(), QImage.Format.Format_RGB32), "x", adjustable=False)
    ov.resize(800, 600)
    got = []
    ov.region_selected.connect(lambda o, l, p: got.append(l))
    for t, x, y in ((QEvent.Type.MouseButtonPress, 10, 10), (QEvent.Type.MouseMove, 100, 80),
                    (QEvent.Type.MouseButtonRelease, 100, 80)):
        ev = QMouseEvent(t, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier)
        {QEvent.Type.MouseButtonPress: ov.mousePressEvent, QEvent.Type.MouseMove: ov.mouseMoveEvent,
         QEvent.Type.MouseButtonRelease: ov.mouseReleaseEvent}[t](ev)
    assert len(got) == 1


# --- configuração ----------------------------------------------------------
def test_config_last_region_validation(qapp, libdir):
    from shotwise.config import Config

    assert Config._valid_region(["\\\\.\\DISPLAY1", 10, 20, 300, 200, "area"]) != []
    for bad in (["x", -1, 0, 10, 10, "area"], ["x", 1, 2, 3, 4, "area"], ["x", 1, 2, 100, 100, "foo"],
                ["x", True, 2, 100, 100, "area"], "abc", [1, 2], None, ["x", 0, 0, 10**9, 100, "scroll"]):
        assert Config._valid_region(bad) == []
    (libdir / "config.json").write_text(json.dumps({"last_region": ["x", 1, 2, 3, 4, "area"],
                                                    "library_max_items": 10**9}))
    c = Config.load()
    assert c.last_region == [] and c.library_max_items == 500


# ======================================================================
# Rodada 3: preenchimento, ordem das camadas, redimensionar/fundo por arraste, OCR, miniatura
# ======================================================================
from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402


def _mouse(scene, kind, x, y, mods=Qt.KeyboardModifier.NoModifier):
    """Envia um evento de mouse à cena (coordenadas da cena)."""
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent

    t = {"press": QEvent.Type.GraphicsSceneMousePress, "move": QEvent.Type.GraphicsSceneMouseMove,
         "release": QEvent.Type.GraphicsSceneMouseRelease}[kind]
    ev = QGraphicsSceneMouseEvent(t)
    ev.setScenePos(QPointF(x, y))
    ev.setPos(QPointF(x, y))
    ev.setButton(Qt.MouseButton.LeftButton)
    ev.setButtons(Qt.MouseButton.LeftButton if kind != "release" else Qt.MouseButton.NoButton)
    ev.setModifiers(mods)
    {"press": scene.mousePressEvent, "move": scene.mouseMoveEvent, "release": scene.mouseReleaseEvent}[kind](ev)


def test_rect_fill_optional_and_undoable(qapp):
    def render(fill):
        scene = AnnotScene(solid(200, 120, "#ffffff"))
        add(scene, ShapeItem("rect", QRectF(20, 20, 100, 60), QColor("#ff0000"), 4, fill=fill))
        return qimage_to_np(scene.render_image())

    assert tuple(render(None)[50, 70]) == (255, 255, 255)           # sem fundo: interior intacto
    assert tuple(render(QColor("#00ff00"))[50, 70]) == (0, 255, 0)  # com fundo: interior colorido

    scene = AnnotScene(solid(200, 120, "#fff"))
    r = ShapeItem("ellipse", QRectF(10, 10, 80, 60), QColor("red"))
    add(scene, r)
    r.setSelected(True)
    scene.apply_style_to_selection(shape_fill=QColor("#0000ff"))
    assert r.fill == QColor("#0000ff")
    scene.undo_stack.undo()
    assert r.fill is None


def test_filled_shape_survives_project_roundtrip(qapp, libdir):
    scene = AnnotScene(solid(100, 100, "#fff"))
    add(scene, ShapeItem("rect", QRectF(10, 10, 50, 50), QColor("red"), 3, fill=QColor(0, 0, 255, 128)))
    scene.export_scale, scene.export_stretch = 0.5, 1.5
    s2 = project.build_scene(library.load(library.save(scene)))
    assert scene.render_image() == s2.render_image()
    assert s2.export_stretch == 1.5


def test_selected_item_moves_to_front_arrow_under_text(qapp):
    """Seta criada antes do texto deve poder ser clicada e vir para a frente."""
    from shotwise.annotations import LineItem

    scene = AnnotScene(solid(400, 300, "#fff"))
    arrow = LineItem("arrow", QPointF(20, 150), QPointF(380, 150), QColor("red"), 6)
    add(scene, arrow)
    text = TextItem("Texto grande sobre a seta", QColor("black"), 40)
    text.setPos(30, 120)
    add(scene, text)
    assert text.zValue() >= arrow.zValue()
    scene.set_tool("select")
    # clique exatamente sobre o traço da seta, dentro da caixa do texto
    pt = QPointF(300, 150)
    assert text.sceneBoundingRect().contains(pt)
    _mouse(scene, "press", pt.x(), pt.y())
    _mouse(scene, "release", pt.x(), pt.y())
    assert arrow.isSelected() and not text.isSelected()
    assert arrow.zValue() > text.zValue()


def test_click_on_text_still_selects_text(qapp):
    from shotwise.annotations import LineItem

    scene = AnnotScene(solid(400, 300, "#fff"))
    add(scene, LineItem("arrow", QPointF(20, 250), QPointF(380, 250), QColor("red"), 6))
    text = TextItem("Texto", QColor("black"), 40)
    text.setPos(30, 60)
    add(scene, text)
    scene.set_tool("select")
    _mouse(scene, "press", 40, 80)
    _mouse(scene, "release", 40, 80)
    assert text.isSelected()


def test_resize_tool_drag_scales_proportionally_and_free(qapp):
    scene = AnnotScene(solid(400, 200, "#fff"))
    scene.set_tool("resize")
    ov = scene._overlay
    assert ov is not None
    # alça inferior-direita de (400,200) para (200,100): metade, proporcional
    _mouse(scene, "press", 400, 200)
    _mouse(scene, "move", 200, 100)
    _mouse(scene, "release", 200, 100)
    assert scene.output_size() == (200, 100)
    scene.undo_stack.undo()
    assert scene.output_size() == (400, 200)
    # Shift: estica livremente (só a largura)
    _mouse(scene, "press", 400, 200)
    _mouse(scene, "move", 200, 200, Qt.KeyboardModifier.ShiftModifier)
    _mouse(scene, "release", 200, 200, Qt.KeyboardModifier.ShiftModifier)
    assert scene.output_size() == (200, 200)
    out = scene.render_image()
    assert (out.width(), out.height()) == (200, 200)


def test_resize_tool_side_handle_keeps_aspect_and_overlay_not_exported(qapp):
    scene = AnnotScene(solid(400, 200, "#ffffff"))
    scene.set_tool("resize")
    _mouse(scene, "press", 400, 100)            # alça direita
    _mouse(scene, "move", 800, 100)
    _mouse(scene, "release", 800, 100)
    assert scene.output_size() == (800, 400)
    img = scene.render_image()                  # a moldura/alças da ferramenta não aparecem na imagem
    arr = qimage_to_np(img)
    assert (arr == 255).all()


def test_resize_ignores_clicks_off_handles(qapp):
    scene = AnnotScene(solid(400, 200, "#fff"))
    scene.set_tool("resize")
    _mouse(scene, "press", 150, 90)
    _mouse(scene, "move", 10, 10)
    _mouse(scene, "release", 10, 10)
    assert scene.output_size() == (400, 200)


def test_background_tool_drag_padding_and_radius(qapp):
    scene = AnnotScene(solid(300, 200, "#ffffff"))
    scene.background = BackgroundSettings(True, "#112233", "#445566", False, 20, 10, True)
    scene.refresh_canvas()
    scene.set_tool("background")
    # alça direita da moldura em x = 300+20; arrasta para x = 300+60 -> margem 60
    _mouse(scene, "press", 320, 100)
    _mouse(scene, "move", 360, 100)
    _mouse(scene, "release", 360, 100)
    assert scene.background.padding == 60
    assert scene.output_size() == (300 + 120, 200 + 120)
    scene.undo_stack.undo()
    assert scene.background.padding == 20
    assert "radius" not in scene._overlay.handles()          # sem ponto laranja sobre a imagem


def test_background_rounded_corners_in_export(qapp):
    scene = AnnotScene(solid(120, 80, "#ff0000"))
    scene.background = BackgroundSettings(True, "#0000ff", "#0000ff", True, 20, 24, False)
    img = scene.render_image()
    assert img.pixelColor(20, 20).alpha() == 0          # canto da captura arredondado -> transparente
    assert img.pixelColor(60, 60).alpha() == 255


def test_ocr_tool_emits_region_and_not_in_export(qapp):
    scene = AnnotScene(solid(300, 200, "#ffffff"))
    got = []
    scene.ocr_requested.connect(got.append)
    scene.set_tool("ocr")
    _mouse(scene, "press", 20, 20)
    _mouse(scene, "move", 120, 80)
    _mouse(scene, "release", 120, 80)
    assert len(got) == 1 and got[0].width() >= 99
    img = scene.render_scene_rect(got[0], min_side=600)
    assert img.width() == 400                           # ampliado 4x (limite) para melhorar o reconhecimento
    assert (qimage_to_np(scene.render_image()) == 255).all()


def test_ocr_worker_returns_text_and_errors(qapp):
    from PySide6.QtCore import QEventLoop, QTimer

    from shotwise import ocr

    def run(func):
        out = {}
        loop = QEventLoop()

        def done(text, err):
            out["r"] = (text, err)
            loop.quit()

        keep = ocr.start_ocr(solid(10, 10, "#fff"), done, func=func)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        keep[0].wait(2000)
        return out["r"]

    assert run(lambda img: "olá mundo") == ("olá mundo", "")
    def boom(img):
        raise ocr.OcrError("sem pacote de idioma")
    assert run(boom) == ("", "sem pacote de idioma")
    if sys.platform != "win32":
        with pytest.raises(ocr.OcrError):
            ocr.recognize(solid(10, 10, "#fff"))


def test_ocr_dialog_copies_text(qapp):
    from PySide6.QtGui import QGuiApplication

    from shotwise.dialogs import OcrDialog

    dlg = OcrDialog("linha 1\nlinha 2")
    dlg._copy()
    assert QGuiApplication.clipboard().text() == "linha 1\nlinha 2"


def test_close_action_copy_save_and_ask(qapp, libdir):
    from PySide6.QtGui import QGuiApplication

    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    cfg = Config()
    cfg.save_dir = str(libdir / "out")
    cfg.library_enabled = False

    # copiar e fechar: captura nova (sem edição) copia ao fechar
    cfg.close_action = "copy"
    QGuiApplication.clipboard().clear()
    win = EditorWindow(solid(100, 60, "#00ff00"), cfg)
    win.show()
    win.close()
    assert not QGuiApplication.clipboard().image().isNull()

    # salvar e fechar: grava o PNG
    cfg.close_action = "save"
    win = EditorWindow(solid(100, 60, "#00ff00"), cfg)
    win.show()
    win.close()
    assert len(list((libdir / "out").glob("Shotwise_*.png"))) == 1

    # projeto reaberto sem alterações: fecha sem ação (não sobrescreve a área de transferência)
    cfg.close_action = "copy"
    QGuiApplication.clipboard().setText("marcador")
    sc = AnnotScene(solid(50, 50, "#fff"))
    win = EditorWindow(None, cfg, project=_pd_from(sc, libdir))
    win.show()
    win.close()
    assert QGuiApplication.clipboard().text() == "marcador"


def _pd_from(scene, libdir):
    return library.load(library.save(scene))


def test_quick_preview_buttons_and_autoclose(qapp):
    from shotwise.preview import QuickPreview

    pv = QuickPreview(solid(400, 300, "#abcdef"), seconds=3)
    got = []
    pv.copy_clicked.connect(lambda img: got.append(("copy", img.size())))
    pv.pin_clicked.connect(lambda img: got.append(("pin", img.size())))
    closed = []
    pv.closed.connect(closed.append)
    pv.show()
    pv._act(pv.edit_clicked)
    assert closed                                        # clicar numa ação fecha a miniatura
    pv2 = QuickPreview(solid(400, 300, "#abcdef"), seconds=3)
    pv2.copy_clicked.connect(lambda img: got.append(("copy", img.size())))
    pv2._act(pv2.copy_clicked)
    assert got and got[0][0] == "copy"


def test_config_after_capture_migration_and_validation(qapp, libdir):
    from shotwise.config import Config

    (libdir / "config.json").write_text(json.dumps({"open_editor": False}))
    assert Config.load().after_capture == "save"                            # migração da versão 1.0/1.1
    (libdir / "config.json").write_text(json.dumps({"after_capture": "xyz", "close_action": "ask",
                                                    "preview_seconds": 9999}))
    c = Config.load()
    assert c.after_capture == "editor" and c.close_action == "copy" and c.preview_seconds == 60
    (libdir / "config.json").write_text(json.dumps({"after_editor": False, "after_preview": True}))   # da 1.3
    assert Config.load().after_capture == "preview"


def test_editor_toolbar_order_and_tools(qapp, libdir):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(200, 100, "#fff"), Config())
    from PySide6.QtWidgets import QToolBar

    tb = win.findChild(QToolBar, "main")
    tips = [a.toolTip() for a in tb.actions() if not a.isSeparator() and a.toolTip()]
    keys = ("Desfazer", "Refazer", "Copiar imagem", "Salvar e fechar (", "Salvar como", "Fixar na tela", "Capturas recentes")
    order = [next(i for i, t in enumerate(tips) if k in t) for k in keys]
    assert order == sorted(order)
    assert not any("Copiar e fechar" in t for t in tips)
    assert any("Configurações" in t for t in tips)
    for tool in ("resize", "background", "ocr", "rect", "ellipse", "pixelate", "blur"):
        win.select_tool(tool)
    assert win.scene.tool == "blur"
    # ferramenta de fundo liga o fundo automaticamente
    win.select_tool("background")
    assert win.scene.background.enabled
    win.select_tool("select")
    assert win.scene._overlay is None


# --- log -----------------------------------------------------------------
def test_logging_captures_unhandled_exceptions(tmp_path, monkeypatch):
    import logging
    import sys as _sys
    import threading

    from shotwise import logsetup

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    lg = logging.getLogger("shotwise")
    for h in list(lg.handlers):
        lg.removeHandler(h)
    old_hook, old_thook = _sys.excepthook, threading.excepthook
    try:
        logsetup.setup("9.9.9")
        try:
            raise ValueError("falha de teste")
        except ValueError:
            _sys.excepthook(*_sys.exc_info())

        def boom():
            raise RuntimeError("falha na thread")

        t = threading.Thread(target=boom)
        t.start()
        t.join()
        for h in lg.handlers:
            h.flush()
        text = (logsetup.log_dir() / "shotwise.log").read_text(encoding="utf-8")
        assert "9.9.9" in text and "falha de teste" in text and "falha na thread" in text
        assert "Traceback" in text
    finally:
        _sys.excepthook, threading.excepthook = old_hook, old_thook
        for h in list(lg.handlers):
            lg.removeHandler(h)
            h.close()


def test_overlay_bounds_do_not_depend_on_state(qapp):
    """Regressão: boundingRect variável derrubava o programa no Windows ao arrastar o fundo/tamanho."""
    from PySide6.QtWidgets import QGraphicsScene

    scene = AnnotScene(solid(300, 200, "#fff"))
    assert scene.itemIndexMethod() == QGraphicsScene.ItemIndexMethod.NoIndex
    scene.set_tool("background")
    ov = scene._overlay
    before = QRectF(ov.boundingRect())
    scene.preview_background(BackgroundSettings(True, "#000", "#fff", False, 300, 50, True))
    assert ov.boundingRect() == before
    scene.set_tool("resize")
    ov2 = scene._overlay
    b2 = QRectF(ov2.boundingRect())
    scene.set_export_scale(4.0)
    assert ov2.boundingRect() == b2


def test_main_toolbar_has_no_double_separators(qapp):
    from PySide6.QtWidgets import QToolBar

    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(100, 60, "#fff"), Config())
    acts = win.findChild(QToolBar, "main").actions()
    flags = [a.isSeparator() for a in acts]
    assert not any(a and b for a, b in zip(flags, flags[1:]))
    assert not flags[0]


def test_step_marker_size_control(qapp):
    from shotwise.annotations import StepItem
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(300, 200, "#fff"), Config())
    win.show()
    win.select_tool("step")
    win.sl_step.setValue(40)
    assert win.scene.opt_step_size == 40
    _mouse(win.scene, "press", 100, 100)
    _mouse(win.scene, "release", 100, 100)
    step = next(i for i in win.scene.items() if isinstance(i, StepItem))
    assert step.radius == 40
    step.setSelected(True)
    win.select_tool("select")
    step.setSelected(True)
    win.sl_step.setValue(20)                 # arrastar muda também o marcador selecionado
    assert step.radius == 20
    win.scene.undo_stack.undo()
    assert step.radius == 40


def _drag_draw(scene, x0, y0, x1, y1):
    _mouse(scene, "press", x0, y0)
    _mouse(scene, "move", x1, y1)
    _mouse(scene, "release", x1, y1)


def test_drawn_effect_is_selected_and_intensity_applies(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(400, 300, "#fff"), Config())
    win.show()
    win.select_tool("pixelate")
    _drag_draw(win.scene, 50, 50, 200, 120)
    item = next(i for i in win.scene.items() if isinstance(i, ShapeItem))
    assert item.isSelected()                           # já fica selecionado ao desenhar
    win.sl_strength.setValue(40)
    assert item.strength == 40
    win.sl_strength.setValue(36)
    assert item.strength == 36
    win.scene.undo_stack.undo()
    assert item.strength == 40


def test_select_tool_shows_options_of_selected_item(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(400, 300, "#fff"), Config())
    win.show()
    px = ShapeItem("blur", QRectF(10, 10, 100, 50), QColor("black"), strength=24)
    add(win.scene, px)
    rc = ShapeItem("rect", QRectF(150, 10, 100, 50), QColor("red"), 6)
    add(win.scene, rc)
    win.select_tool("select")

    def visible(group):
        return any(a.isVisible() for a in win._opt_actions[group])

    assert not visible("strength")                      # nada selecionado: sem opções
    px.setSelected(True)
    assert visible("strength") and not visible("fill")
    assert win.sl_strength.value() == 24                # controles refletem o item
    px.setSelected(False)
    rc.setSelected(True)
    assert visible("fill") and visible("width") and not visible("strength")
    assert win.sp_width.value() == 6


def test_arrow_roundness_changes_render_and_roundtrips(qapp, libdir):
    from shotwise.annotations import LineItem

    def render(rnd):
        sc = AnnotScene(solid(200, 120, "#ffffff"))
        ln = LineItem("arrow", QPointF(20, 60), QPointF(170, 60), QColor("#000000"), 6)
        ln.set_curvature(rnd)
        add(sc, ln)
        return sc, qimage_to_np(sc.render_image())

    sc0, a0 = render(0)
    sc1, a1 = render(100)
    assert not np.array_equal(a0, a1)                   # a seta fica curva
    s2 = project.build_scene(library.load(library.save(sc1)))
    assert next(i for i in s2.items() if isinstance(i, LineItem)).round == 100

    arrow = next(i for i in sc0.items() if isinstance(i, LineItem))
    arrow.setSelected(True)
    sc0.apply_style_to_selection(arrow_round=60)
    assert arrow.round == 60
    sc0.undo_stack.undo()
    assert arrow.round == 0


def test_arrow_tool_shows_roundness_option(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(200, 100, "#fff"), Config())
    win.show()
    win.select_tool("arrow")
    assert any(a.isVisible() for a in win._opt_actions["round"])
    win.select_tool("line")
    assert any(a.isVisible() for a in win._opt_actions["round"])        # curvatura também vale para linhas
    win.select_tool("rect")
    assert not any(a.isVisible() for a in win._opt_actions["round"])


def test_pin_hover_buttons_and_preview_layout(qapp):
    from shotwise.pin import PinWindow
    from shotwise.preview import QuickPreview

    pin = PinWindow(solid(396, 143, "#336699"))
    got = []
    pin.save_requested.connect(lambda img: got.append("save"))
    pin.edit_requested.connect(lambda img: got.append("edit"))
    pin.show()
    assert all(b.isHidden() for b in pin._buttons)            # escondidos sem o mouse em cima
    pin.enterEvent(None)
    assert all(not b.isHidden() for b in pin._buttons)
    pin._buttons[1].clicked.emit()
    pin._buttons[2].clicked.emit()
    assert got == ["save", "edit"]
    pin.leaveEvent(None)
    assert all(b.isHidden() for b in pin._buttons)
    tiny = PinWindow(solid(40, 30, "#fff"))
    tiny.show()
    assert all(b.width() == 20 for b in tiny._buttons)
    pv = QuickPreview(solid(1920, 1080, "#223344"), seconds=3)
    assert pv.width() <= 220 + 16 and pv.height() <= 140 + 16
    for b in (pv._b_close, pv._b_pin, pv._b_edit, pv._b_copy, pv._b_save):
        assert pv.rect().contains(b.geometry())
    pv.grab().save("/tmp/pv.png")
    pin.enterEvent(None)
    pin.grab().save("/tmp/pin.png")


def test_pin_actions_close_and_edge_resize(qapp):
    from PySide6.QtCore import QPoint
    from shotwise.pin import PinWindow

    for idx in (0, 1, 2, 3):                                  # copiar, salvar, editar, fechar: todos fecham
        pin = PinWindow(solid(300, 200, "#336699"))
        closed = []
        pin.closed.connect(closed.append)
        pin.show()
        pin._buttons[idx].clicked.emit()
        assert closed, idx
    pin = PinWindow(solid(300, 200, "#336699"))
    pin.show()
    pin.setGeometry(100, 100, 300, 200)
    assert pin._edges(QPoint(299, 100)) == "R" and pin._edges(QPoint(150, 100)) == ""
    assert pin._edges(QPoint(0, 0)) == "TL"
    pin._resize = ("R", QPoint(400, 200), pin.geometry())
    pin._do_resize(QPoint(500, 200))                          # +100 px na largura
    assert pin.width() == 400 and pin.height() == 267 and pin.x() == 100
    pin._resize = ("TL", QPoint(100, 100), pin.geometry())
    pin._do_resize(QPoint(50, 50))                            # puxa o canto: ancora o canto oposto
    assert pin.width() == 450 and pin.geometry().right() == 499


def test_ocr_callback_runs_in_gui_thread(qapp):
    from PySide6.QtCore import QEventLoop, QThread, QTimer
    from shotwise import ocr

    seen = {}
    loop = QEventLoop()

    def done(text, err):
        seen["t"] = QThread.currentThread()
        loop.quit()

    keep = ocr.start_ocr(solid(10, 10, "#fff"), done, func=lambda img: "x")
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    keep[0].wait(2000)
    assert seen["t"] is qapp.thread()       # fora da thread do OCR (senão a interface cai)


def test_editor_save_closes_and_hotkey_migration(qapp, libdir, tmp_path):
    import json
    from shotwise.config import Config

    from shotwise.editor import EditorWindow

    cfg = Config()
    cfg.save_dir = str(tmp_path)
    win = EditorWindow(solid(100, 60, "#00ff00"), cfg)
    win.show()
    closed = []
    win.closed.connect(closed.append)
    win.save_and_close()
    assert closed and list(tmp_path.glob("*.png"))
    (libdir / "config.json").write_text(json.dumps({"hotkey_pin": "Ctrl+Alt+9"}))
    assert Config.load().hotkey_ocr == "Ctrl+Alt+9"


def test_new_default_hotkeys_and_migration(qapp, libdir):
    import json
    from shotwise.config import Config
    from shotwise.hotkeys import parse_hotkey

    c = Config()
    assert (c.hotkey_fullscreen, c.hotkey_area, c.hotkey_repeat) == ("Shift+Print", "Print", "Alt+Shift+R")
    assert parse_hotkey("Print") == (0, 0x2C)                    # Print Screen sozinha é válida
    assert parse_hotkey("Shift+Print") == (4, 0x2C)
    assert parse_hotkey("Alt+Shift+R") == (5, ord("R"))
    assert parse_hotkey("A") is None and parse_hotkey("5") is None  # letra/número sozinhos tomariam o teclado
    (libdir / "config.json").write_text(json.dumps({"hotkey_fullscreen": "Ctrl+Shift+3", "hotkey_area": "Ctrl+Shift+4",
                                                    "hotkey_repeat": "Ctrl+Shift+6", "hotkey_scroll": "Ctrl+Alt+9"}))
    c = Config.load()
    assert (c.hotkey_fullscreen, c.hotkey_area, c.hotkey_repeat) == ("Shift+Print", "Print", "Alt+Shift+R")
    assert c.hotkey_scroll == "Ctrl+Alt+9"                       # atalho personalizado é preservado
    assert (Config().hotkey_window, Config().hotkey_ocr) == ("Alt+Shift+J", "Alt+Shift+T")
    (libdir / "config.json").write_text(json.dumps({"hotkey_scroll": "Ctrl+Shift+5", "hotkey_ocr": "Ctrl+Shift+7"}))
    c = Config.load()
    assert (c.hotkey_scroll, c.hotkey_ocr) == ("Alt+Shift+S", "Alt+Shift+T")


def test_shortcuts_dialog_validation_and_restore(qapp, monkeypatch):
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QMessageBox
    from shotwise.config import Config
    from shotwise.settings_dialog import ShortcutsDialog

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    cfg = Config()
    dlg = ShortcutsDialog(cfg)
    assert dlg.edits["hotkey_area"].keySequence().toString() == "Print"
    dlg.edits["hotkey_scroll"].setKeySequence(QKeySequence("Print"))       # igual ao da área: recusa
    dlg._accept()
    assert cfg.hotkey_scroll == "Alt+Shift+S" and dlg.result() == 0
    dlg._restore()
    dlg._accept()
    assert cfg.hotkey_scroll == "Alt+Shift+S" and dlg.result() == 1


def test_settings_dialog_general_options(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from shotwise.config import Config
    from shotwise.settings_dialog import SettingsDialog

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    cfg = Config()
    dlg = SettingsDialog(cfg)
    labels = [dlg.cmb_after.itemText(i) for i in range(dlg.cmb_after.count())]
    assert labels == ["Abrir Editor", "Copiar Imagem", "Salvar Imagem", "Mostrar Miniatura"]
    dlg.cmb_format.setCurrentIndex(dlg.cmb_format.findData("jpg"))
    dlg.cmb_after.setCurrentIndex(dlg.cmb_after.findData("preview"))
    dlg.cb_cursor.setChecked(True)
    dlg.cb_top.setChecked(True)
    dlg.cmb_close.setCurrentIndex(dlg.cmb_close.findData("save"))
    dlg._accept()
    assert (cfg.save_format, cfg.after_capture) == ("jpg", "preview")
    assert cfg.include_cursor and cfg.editor_on_top and cfg.close_action == "save"


def test_editor_esc_flow_jpg_name_and_on_top(qapp, libdir):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    cfg = Config()
    cfg.save_dir = str(libdir / "out")
    cfg.library_enabled = False
    cfg.save_format = "jpg"
    cfg.close_action = "save"
    cfg.editor_on_top = True
    win = EditorWindow(solid(100, 60, "#00ff00"), cfg)
    win.show()
    assert win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    cfg.editor_on_top = False
    win.apply_window_settings()
    assert not win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    closed = []
    win.closed.connect(closed.append)
    win.select_tool("rect")
    esc = lambda: win.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    esc()                                    # 1º Esc: volta para a seta de seleção
    assert win.scene.tool == "select" and not closed
    esc()                                    # 2º Esc: fecha salvando (JPG)
    assert closed and len(list((libdir / "out").glob("Shotwise_*.jpg"))) == 1


def test_draw_cursor_composites_with_hotspot(qapp):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage
    from shotwise.winutil import CursorSnapshot, draw_cursor, grab_cursor

    cur = QImage(10, 10, QImage.Format.Format_ARGB32)
    cur.fill(QColor(255, 0, 0, 255))
    snap = CursorSnapshot(cur, QPoint(2, 2), QPoint(150, 120))      # ponta em (150,120) na tela
    base = solid(100, 100, "#ffffff")
    out = draw_cursor(base, snap, QPoint(100, 100))                  # imagem começa em (100,100)
    assert out.pixelColor(48, 18) == QColor(255, 0, 0) and out.pixelColor(47, 18) == QColor(255, 255, 255)
    assert draw_cursor(base, snap, QPoint(500, 500)).pixelColor(5, 5) == QColor(255, 255, 255)   # fora da imagem
    assert draw_cursor(base, None, QPoint(0, 0)) is base
    if sys.platform != "win32":
        assert grab_cursor() is None


def test_tools_toolbar_position(qapp):
    from PySide6.QtWidgets import QToolBar
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    cfg = Config()
    win = EditorWindow(solid(200, 100, "#fff"), cfg)
    win.show()
    tools = win.findChild(QToolBar, "tools")
    opts = win._opts_tb
    win.select_tool("rect")
    main = win.findChild(QToolBar, "main")
    assert win.toolBarArea(tools) == Qt.ToolBarArea.LeftToolBarArea
    for pos, area in (("right", Qt.ToolBarArea.RightToolBarArea), ("top", Qt.ToolBarArea.TopToolBarArea),
                      ("left", Qt.ToolBarArea.LeftToolBarArea)):
        cfg.tools_position = pos
        win.apply_window_settings()
        assert win.toolBarArea(tools) == area and tools.isVisible() and opts.isVisible()
        assert opts.parentWidget() is win.view and main.isVisible()
    cfg.tools_position = "top"
    win.apply_window_settings()
    assert tools.orientation() == Qt.Orientation.Horizontal
    assert main.geometry().bottom() <= tools.geometry().top()   # ordem vertical
    tools.setOrientation  # noqa: B018
    from shotwise.config import Config as C
    assert C(tools_position="x").tools_position == "x"      # a validação ocorre em load()


def test_crop_hides_outside_area_and_keeps_zoom(qapp):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter, QColor
    from shotwise.annotations import AnnotScene, CropItem

    sc = AnnotScene(solid(200, 100, "#ff0000"))
    sc.clip = QRectF(50, 20, 100, 60)
    sc.refresh_canvas()
    img = QImage(200, 100, QImage.Format.Format_RGB32)
    img.fill(QColor("#101010"))
    p = QPainter(img)
    sc.render(p, QRectF(0, 0, 200, 100), QRectF(0, 0, 200, 100))        # como na tela (não é exportação)
    p.end()
    assert img.pixelColor(100, 50) == QColor("#ff0000")                  # dentro do recorte: imagem
    assert img.pixelColor(10, 10) != QColor("#ff0000")                   # fora do recorte: some
    assert img.pixelColor(190, 90) != QColor("#ff0000")


def _zoom_scene():
    from shotwise.annotations import ZoomItem
    scene = AnnotScene(solid(400, 300, "#2060c0"))
    # um pedaço claro na origem da lupa
    layer = scene.layers()[0]
    from PySide6.QtGui import QPainter
    p = QPainter(layer.image)
    p.fillRect(40, 40, 40, 30, QColor("#ffff00"))
    p.end()
    z = ZoomItem(QRectF(30, 30, 60, 50), QColor("#ff3b30"), 3, 2.5)
    scene.addItem(z)
    z.finalize(scene.canvas_rect(), 2.5)
    scene.undo_stack.push(AddCommand(scene, z))
    return scene, z


def test_zoom_item_magnifies_and_exports(qapp):
    scene, z = _zoom_scene()
    ins = z.inset_rect()
    assert abs(ins.width() - 150) < 1 and abs(ins.height() - 125) < 1          # elipse 60x50 a 2,5x
    assert scene.canvas_rect().contains(ins.translated(z.pos()))              # ampliação cabe na tela
    scene.refresh_zooms()
    assert z._pix is not None and z._pix.width() == 150
    out = scene.render_image()
    cx, cy = int(ins.center().x()), int(ins.center().y())
    # o centro da ampliação mostra a parte amarela, aumentada
    assert out.pixelColor(cx, cy) == QColor("#ffff00")
    assert out.pixelColor(int(ins.left()) + 6, int(ins.top()) + 6) == QColor("#2060c0")


def test_zoom_never_leaks_redacted_content(qapp):
    scene, z = _zoom_scene()
    scene.refresh_zooms()
    add(scene, ShapeItem("redact", QRectF(30, 30, 60, 50), QColor("black")))     # tarja por cima da origem, depois
    out = scene.render_image()                                                   # exporta: atualiza a lupa antes
    ins = z.inset_rect()
    cx, cy = int(ins.center().x()), int(ins.center().y())
    assert out.pixelColor(cx, cy) == QColor("black")                             # a ampliação também está tarjada
    assert not any(out.pixelColor(x, y) == QColor("#ffff00")
                   for x in range(0, 400, 3) for y in range(0, 300, 3))


def test_zoom_roundtrip_undo_and_options(qapp, libdir):
    from shotwise.annotations import ZoomItem
    scene, z = _zoom_scene()
    z.apply_style(zoom=4.0, color=QColor("#00ff00"))
    assert z.factor == 4.0 and z.color == QColor("#00ff00")
    old = z.snapshot()
    z.offset = QPointF(500, 5)
    z.restore(old)
    assert z.offset == old[5]
    data = library.load(library.save(scene))
    scene2 = project.build_scene(data)
    z2 = next(i for i in scene2.items() if isinstance(i, ZoomItem))
    assert z2.factor == 4.0 and z2.rect() == z.rect() and z2.offset == z.offset
    assert scene.render_image() == scene2.render_image()
    scene.undo_stack.undo()
    assert not any(isinstance(i, ZoomItem) for i in scene.items())


def test_zoom_tool_in_editor(qapp, libdir):
    from shotwise.annotations import ZoomItem
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(300, 200, "#8899aa"), Config())
    win.show()
    win.select_tool("zoom")
    assert win.scene.tool == "zoom"
    assert any(a.isVisible() for a in win._opt_actions["zoomf"])
    z = ZoomItem(QRectF(10, 10, 40, 30), QColor("#ff3b30"))
    win.scene.addItem(z)
    win.scene.undo_stack.push(AddCommand(win.scene, z))
    win.select_tool("select")
    z.setSelected(True)
    win._update_options()
    win.sl_zoomf.setValue(40)
    assert abs(z.factor - 4.0) < 1e-6


def test_selector_watchdog_cancels_when_idle_and_dialogs_are_not_modal(qapp):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from shotwise.selector import RegionSelector
    from shotwise.settings_dialog import SettingsDialog, ShortcutsDialog
    from shotwise.config import Config

    screen = QApplication.primaryScreen()
    got = []
    sel = RegionSelector([(screen, solid(100, 100, "#222222"))], "x", lambda *a: got.append("sel"),
                         lambda: got.append("cancel"))
    sel.start()
    sel._last_cursor = None
    for _ in range(sel.IDLE_LIMIT_S + 3):                      # mouse parado: cancela sozinho
        sel._check_idle()
    assert got == ["cancel"] and not sel._overlays
    # janelas de configuração não bloqueiam a seleção de área
    assert not SettingsDialog(Config()).isModal() and not ShortcutsDialog(Config()).isModal()
    from PySide6.QtWidgets import QLabel
    sd = ShortcutsDialog(Config())
    text = " ".join(l.text() for l in sd.findChildren(QLabel))
    assert "Clique no campo" in text and "Configurações de teclado" in text


def test_zoom_is_elliptical_and_handles_resize(qapp):
    scene, z = _zoom_scene()
    z.setSelected(True)

    class Ev:
        def __init__(self, p): self._p = p
        def pos(self): return self._p
        def button(self): return Qt.MouseButton.LeftButton
        def accept(self): pass

    # alça de canto da lupa: muda o aumento mantendo o centro
    c = z.ins_center()
    ins = z.inset_rect()
    h = ins.bottomRight()
    assert z.handle_at(h) == "i_br"
    z.mousePressEvent(Ev(h))
    target = QPointF(c.x() + 60, c.y() + 50)            # metade de 120x100: fator 2,0 sobre 60x50
    z.mouseMoveEvent(Ev(target))
    z.mouseReleaseEvent(Ev(target))
    assert abs(z.factor - 2.0) < 1e-6 and (z.ins_center() - c).manhattanLength() < 1e-6
    # alça lateral da origem: só a largura muda (elipse livre); a lupa não sai do lugar
    ic = z.ins_center()
    r = z.src_rect()
    hr = QPointF(r.right(), r.center().y())
    assert z.handle_at(hr) == "r"
    z.mousePressEvent(Ev(hr))
    z.mouseMoveEvent(Ev(QPointF(r.right() + 40, r.center().y())))
    z.mouseReleaseEvent(Ev(hr))
    assert abs(z.src_rect().width() - 100) < 1e-6 and abs(z.src_rect().height() - 50) < 1e-6
    assert (z.ins_center() - ic).manhattanLength() < 1e-6


def test_arrow_curves_with_middle_handle_and_slider(qapp):
    from shotwise.annotations import LineItem
    scene = AnnotScene(solid(400, 300, "#ffffff"))
    ln = LineItem("arrow", QPointF(50, 150), QPointF(250, 150), QColor("#ff3b30"), 4)
    add(scene, ln)
    ln.setSelected(True)
    assert ln.round == 0
    mid = ln._curve_mid()
    assert ln._end_at(mid) == "mid"

    class Ev:
        def __init__(self, p): self._p = p
        def pos(self): return self._p
        def button(self): return Qt.MouseButton.LeftButton
        def accept(self): pass
    ln.mousePressEvent(Ev(mid))
    ln.mouseMoveEvent(Ev(QPointF(150, 100)))
    ln.mouseReleaseEvent(Ev(mid))
    assert abs(ln._curve_mid().y() - 100) < 1e-6 and ln.round == 50       # flecha de 50 px em 200 px
    before = ln.snapshot()
    ln.apply_style(arrow_round=0)
    assert ln.bend.manhattanLength() == 0
    ln.restore(before)
    assert ln.round == 50
    # a curva sai nos arquivos salvos
    data = library.load(library.save(scene))
    ln2 = next(i for i in project.build_scene(data).items() if isinstance(i, LineItem))
    assert ln2.round == 50
    assert scene.render_image().size().width() == 400


def test_fill_opacity_slider(qapp, libdir):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow
    win = EditorWindow(solid(300, 200, "#ffffff"), Config())
    win.show()
    win.select_tool("rect")
    win.cb_fill.setChecked(True)
    win.sl_fillop.setValue(100)
    assert win.scene.opt_fill.alpha() == 255
    sh = ShapeItem("rect", QRectF(20, 20, 80, 60), QColor("#ff0000"), 3, 16, QColor(0, 0, 255, 255))
    win.scene.addItem(sh)
    sh.setSelected(True)
    win.sl_fillop.setValue(40)
    assert abs(sh.fill.alphaF() - 0.4) < 0.01


def test_theme_switch_and_config(qapp):
    from shotwise.config import Config
    from shotwise.theme import apply_theme
    assert apply_theme(qapp, "light") == "light" and qapp.property("shotwise_theme") == "light"
    assert apply_theme(qapp, "dark") == "dark"
    assert apply_theme(qapp, "system") in ("dark", "light")
    cfg = Config()
    assert cfg.theme == "dark"


def test_draw_tool_keeps_item_selected_and_adjustable(qapp):
    from PySide6.QtCore import QEvent, QPointF as P
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent
    scene = AnnotScene(solid(400, 300, "#8899aa"))
    scene.set_tool("rect")

    def mouse(kind, p, buttons=Qt.MouseButton.LeftButton):
        ev = QGraphicsSceneMouseEvent(kind)
        ev.setScenePos(P(*p)); ev.setPos(P(*p)); ev.setButton(Qt.MouseButton.LeftButton); ev.setButtons(buttons)
        ev.setModifiers(Qt.KeyboardModifier.NoModifier)
        scene.sendEvent_ = None
        {QEvent.Type.GraphicsSceneMousePress: scene.mousePressEvent,
         QEvent.Type.GraphicsSceneMouseMove: scene.mouseMoveEvent,
         QEvent.Type.GraphicsSceneMouseRelease: scene.mouseReleaseEvent}[kind](ev)

    mouse(QEvent.Type.GraphicsSceneMousePress, (50, 50))
    mouse(QEvent.Type.GraphicsSceneMouseMove, (150, 120))
    mouse(QEvent.Type.GraphicsSceneMouseRelease, (150, 120))
    shapes = [i for i in scene.items() if isinstance(i, ShapeItem)]
    assert len(shapes) == 1 and shapes[0].isSelected() and scene.tool == "rect"
    # clique fora: só desmarca (não cria outro item); a ferramenta continua ativa
    mouse(QEvent.Type.GraphicsSceneMousePress, (300, 250))
    mouse(QEvent.Type.GraphicsSceneMouseRelease, (300, 250))
    assert not shapes[0].isSelected() and scene.tool == "rect"
    assert len([i for i in scene.items() if isinstance(i, ShapeItem)]) == 1
    # novo clique-arraste cria o segundo item
    mouse(QEvent.Type.GraphicsSceneMousePress, (200, 150))
    mouse(QEvent.Type.GraphicsSceneMouseMove, (260, 200))
    mouse(QEvent.Type.GraphicsSceneMouseRelease, (260, 200))
    assert len([i for i in scene.items() if isinstance(i, ShapeItem)]) == 2


def test_switching_tools_does_not_move_the_view(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow
    win = EditorWindow(solid(500, 300, "#88aacc"), Config())
    win.resize(1000, 740)
    win.show()
    qapp.processEvents()
    seen = set()
    for t in ("select", "arrow", "rect", "pixelate", "zoom", "crop", "resize", "background", "ocr", "step", "text", "select"):
        win.select_tool(t)
        qapp.processEvents()
        seen.add((win.view.viewport().height(), win.view.mapFromScene(0, 0).y()))
    assert len(seen) == 1


def test_zoom_arrow_connects_and_bends(qapp):
    scene, z = _zoom_scene()
    z.setSelected(True)
    g = z._arrow_geom()
    assert g is not None
    start, ctrl, end = g
    assert z.src_rect().adjusted(-4, -4, 4, 4).contains(start) and z.inset_rect().adjusted(-4, -4, 4, 4).contains(end)
    bh = z._bend_handle()
    assert z.handle_at(bh) == "bend"

    class Ev:
        def __init__(self, p): self._p = p
        def pos(self): return self._p
        def button(self): return Qt.MouseButton.LeftButton
        def accept(self): pass
    z.mousePressEvent(Ev(bh))
    target = QPointF(bh.x(), bh.y() + 40)
    z.mouseMoveEvent(Ev(target))
    z.mouseReleaseEvent(Ev(target))
    assert z.bend is not None and abs(z._bend_handle().y() - target.y()) < 6
    data = library.load(library.save(scene))
    z2 = next(i for i in project.build_scene(data).items() if type(i).__name__ == "ZoomItem")
    assert z2.arrow and (z2.bend - z.bend).manhattanLength() < 0.01
    z.apply_style(zoom_arrow=False)
    assert z._arrow_geom() is None


def test_library_prune_by_count_and_megabytes(qapp, libdir):
    import time
    ids = []
    for i in range(4):
        sc = AnnotScene(solid(300, 200, "#336699"))
        ids.append(library.save(sc))
        time.sleep(0.01)
    assert len(library.entries()) == 4
    assert library.prune(3) == 1 and len(library.entries()) == 3
    size_mb = library.total_size_mb()
    assert size_mb > 0
    removed = library.prune(10, 1)                      # 1 MB: cabe tudo
    assert removed == 0
    # limite minúsculo (em bytes, via função interna): mantém sempre o mais recente
    import os
    from shotwise import library as lib
    lib.prune(10, 0)
    es = lib.entries()
    tiny = lambda e: os.path.getsize(e.path)
    assert len(es) == 3 and tiny(es[0]) > 0


def test_open_with_file_args_filter(qapp, tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("shotwise_main", os.path.join(os.path.dirname(__file__), "..", "main.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = tmp_path / "a.png"
    a.write_bytes(b"x")
    b = tmp_path / "b.exe"
    b.write_bytes(b"x")
    assert mod._file_args([str(a), str(b), str(tmp_path / "nao.png"), "--flag"]) == [str(a)]


def test_i18n_every_tr_literal_has_translations():
    import ast
    import glob
    from shotwise.i18n_data import T
    missing = []
    for f in glob.glob(os.path.join(os.path.dirname(__file__), "..", "shotwise", "*.py")) + [
            os.path.join(os.path.dirname(__file__), "..", "main.py")]:
        tree = ast.parse(open(f, encoding="utf-8").read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                if n.args[0].value.strip() not in T:
                    missing.append((os.path.basename(f), n.args[0].value[:50]))
    assert not missing, missing
    for k, (en, es) in T.items():
        assert en.strip() and es.strip(), k
        # os marcadores {x} devem existir nas três línguas
        import re
        assert set(re.findall(r"\{\w+\}", k)) == set(re.findall(r"\{\w+\}", en)) == set(re.findall(r"\{\w+\}", es)), k


def test_i18n_translates_and_keeps_spaces():
    from shotwise import i18n
    try:
        i18n.set_language("en")
        assert i18n.tr(" Espessura ") == " Thickness "
        assert i18n.tr("Salvar e fechar") == "Save and close"
        assert i18n.tr("texto sem tradução") == "texto sem tradução"
        i18n.set_language("es")
        assert i18n.tr("Desfazer") == "Deshacer"
        i18n.set_language("pt")
        assert i18n.tr("Desfazer") == "Desfazer"
    finally:
        i18n.set_language("pt")


def test_resize_edges_are_grabbable_and_drag_works(qapp):
    scene = AnnotScene(solid(400, 200, "#fff"))
    scene.set_tool("resize")
    ov = scene._overlay
    assert ov.handle_at(QPointF(120, 0)) == "t"         # no meio da borda, fora de qualquer alça
    assert ov.handle_at(QPointF(400, 60)) == "r"
    assert ov.handle_at(QPointF(150, 100)) is None       # dentro da imagem: ignora
    _mouse(scene, "press", 400, 60)
    _mouse(scene, "move", 200, 60)
    _mouse(scene, "release", 200, 60)
    assert scene.output_size() == (200, 100)


def test_language_auto_resolves(qapp):
    from shotwise import i18n
    assert i18n._resolve("auto") in ("pt", "en", "es")
    assert i18n._resolve("en") == "en" and i18n._resolve("xx") == "pt"


def test_zoom_buttons_in_status_bar(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow
    win = EditorWindow(solid(500, 300, "#88aacc"), Config())
    win.show()
    qapp.processEvents()
    z0 = win.view.transform().m11()
    win.view.zoom_by(1.25)
    assert win.view.transform().m11() > z0
    from PySide6.QtWidgets import QToolButton
    assert len(win.statusBar().findChildren(QToolButton)) == 4
    # slider acompanha o zoom e arrastá-lo muda o zoom
    win.view.set_zoom(1.0)
    v1 = win.sl_zoom.value()
    win.sl_zoom.setValue(v1 + 100)
    assert win.view.zoom_value > 1.0
    win.view.set_zoom(0.5)
    assert win.sl_zoom.value() < v1
    # botão 100% volta ao tamanho original
    win.btn_zoom100.click()
    assert abs(win.view.zoom_value - 1.0) < 1e-6


def _frames(n, w=120, h=80):
    from PySide6.QtGui import QColor, QImage
    out = []
    for i in range(n):
        im = QImage(w, h, QImage.Format.Format_RGB888)
        im.fill(QColor(20 + i * 20, 90, 200 - i * 10))
        out.append(im)
    return out


def test_gif_encode_roundtrip(qapp, tmp_path):
    from PIL import Image
    from shotwise.gifenc import encode_gif
    path = str(tmp_path / "t.gif")
    prog = []
    encode_gif(_frames(4), [100, 200, 50, 10], path, progress=prog.append)
    with Image.open(path) as g:
        assert g.n_frames == 4 and g.size == (120, 80)
        durs = []
        for i in range(4):
            g.seek(i)
            durs.append(g.info["duration"])
    assert durs == [100, 200, 50, 20]            # mínimo de 20 ms
    assert prog[-1] == 100
    with pytest.raises(ValueError):
        encode_gif([], [], path)


def test_gif_recorder_dedupes_and_limits(qapp):
    from PySide6.QtGui import QColor, QImage
    from shotwise.recorder import GifRecorder
    seq = []

    def grab():
        im = QImage(1600, 900, QImage.Format.Format_RGB32)
        im.fill(QColor(10, 10, 10) if len(seq) < 3 else QColor(200, 10, 10))
        seq.append(1)
        return im

    rec = GifRecorder(grab, fps=50, max_seconds=60, max_width=800)
    reasons = []
    rec.stopped.connect(reasons.append)
    rec.start()
    for _ in range(5):
        rec._on_tick()
    rec.stop("user")
    assert reasons == ["user"]
    assert len(rec.images) == 2                       # quadros repetidos viram um só
    assert rec.images[0].width() == 800               # reduzido pela largura máxima
    assert len(rec.durations()) == 2 and all(d >= 20 for d in rec.durations())
    rec2 = GifRecorder(grab, fps=10, max_seconds=3, max_width=800)
    rec2.cancel()
    rec2.start()
    assert not rec2.running                           # cancelado antes de começar


def test_gif_preview_trim_cut_undo(qapp):
    from shotwise.recorder import GifPreviewDialog
    dlg = GifPreviewDialog(_frames(6), [100] * 6, lambda: "x.gif")
    assert dlg.timeline.is_full()
    dlg.set_selection(2, 4)
    imgs, durs = dlg.selected()
    assert len(imgs) == 3 and durs == [100, 100, 100]
    dlg.set_selection(5, 4)                           # pontas invertidas: a faixa se corrige, sem quebrar
    assert dlg.selection() == (4, 5)
    # apagar a seleção do meio junta o que sobrou
    dlg.set_selection(1, 2)
    dlg._delete()
    assert len(dlg.images) == 4 and dlg.timeline.is_full() and dlg.btn_undo.isEnabled()
    dlg._undo()
    assert len(dlg.images) == 6 and not dlg._history
    # manter só a seleção
    dlg.set_selection(0, 1)
    dlg._keep()
    assert len(dlg.images) == 2
    # apagar com a faixa inteira não faz nada (o clipe precisa de ao menos um quadro)
    dlg._delete()
    assert len(dlg.images) == 2
    # transporte: parar volta ao início da faixa e pausa; reproduzir retoma
    dlg._stop()
    assert not dlg._playing and dlg._cur == 0
    dlg._toggle()
    assert dlg._playing
    dlg.reject()


def test_gif_timeline_maps_time_to_frames(qapp):
    from shotwise.recorder import Timeline
    t = Timeline()
    t.resize(1010, 48)
    t.set_clip([1000, 100, 100, 800])                 # eixo em tempo: o 1.º quadro ocupa metade da barra
    assert t._index_at(t._x(0) + 1) == 0
    assert t._index_at(t._x(1050)) == 1
    assert t._index_at(t._x(1999)) == 3
    t.set_selection(1, 2)
    assert not t.is_full()


def test_gif_config_limits(qapp, tmp_path, monkeypatch):
    from shotwise.config import Config
    c = Config()
    c.gif_fps, c.gif_max_seconds, c.gif_max_width = 999, 99999, 5
    monkeypatch.setattr(Config, "path", classmethod(lambda cls: tmp_path / "c.json"))
    c.save()
    c2 = Config.load()
    assert (c2.gif_fps, c2.gif_max_seconds, c2.gif_max_width) == (20, 180, 240)
    assert c2.hotkey_gif == "Alt+Shift+G"


def test_background_solid_vs_gradient_ui(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow
    from shotwise.annotations import BackgroundSettings
    win = EditorWindow(solid(400, 240, "#88aacc"), Config())
    win.resize(1200, 740)
    win.show()
    win.select_tool("background")
    qapp.processEvents()
    win._bg_apply(color1="#102030", color2="#a0b0c0")
    assert win._bg_act_c2.isVisible() and win._bg_act_presets.isVisible() and win._bg_act_style.isVisible()
    win.cb_bg_gradient.setChecked(False)
    qapp.processEvents()
    bs = win.scene.background
    assert bs.solid and not win._bg_act_c2.isVisible() and not win._bg_act_style.isVisible()
    assert win.btn_bg_c1.text().strip() == "Cor"
    # a ferramenta continua mostrando só a cor ao trocar de ferramenta e voltar
    win.select_tool("arrow"); win.select_tool("background"); qapp.processEvents()
    assert not win._bg_act_c2.isVisible()
    out = win.scene.render_image()
    c = out.pixelColor(2, 2)
    assert c.name() == "#102030"                        # fundo liso: sem degradê
    win.cb_bg_gradient.setChecked(True)
    qapp.processEvents()
    assert not win.scene.background.solid and win._bg_act_c2.isVisible()
    # cores iguais ao voltar para degradê: sugere uma segunda cor diferente
    win._bg_apply(color1="#336699", color2="#336699", solid=True)
    win.cb_bg_gradient.setChecked(True)
    assert win.scene.background.color1 != win.scene.background.color2
    d = BackgroundSettings.from_dict(win.scene.background.to_dict())
    assert d.solid is False


def test_restart_flag_is_not_a_file_arg():
    import importlib.util
    spec = importlib.util.spec_from_file_location("shotwise_main", os.path.join(os.path.dirname(__file__), "..", "main.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod._file_args(["--restarted"]) == []


def test_resize_is_visible_on_screen_and_chainable(qapp):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from shotwise.config import Config
    from shotwise.editor import EditorWindow
    win = EditorWindow(solid(500, 300, "#88aacc"), Config())
    win.resize(1200, 760)
    win.show()
    win.select_tool("resize")
    qapp.processEvents()
    view, sc = win.view, win.scene
    w0 = view.mapFromScene(500, 0).x() - view.mapFromScene(0, 0).x()
    vp = view.viewport()

    def drag(handle, dx, dy):
        p = view.mapFromScene(sc._overlay.handles()[handle])
        q = QPoint(p.x() + dx, p.y() + dy)
        QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)
        QTest.mouseMove(vp, q)
        QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, q)
        qapp.processEvents()

    drag("br", -100, -60)                                  # 500x300 -> 400x240 (80%)
    assert sc.output_size() == (400, 240)
    w1 = view.mapFromScene(500, 0).x() - view.mapFromScene(0, 0).x()
    assert abs(w1 - w0 * 0.8) <= 2                         # a imagem encolheu na tela
    assert abs(view.zoom_value - 1.0) < 1e-6               # 100% = tamanho real da saída
    drag("br", -80, -48)                                   # de novo: 80% do atual (320 x 192)
    assert sc.output_size() == (320, 192)
    sc.undo_stack.undo()
    assert sc.output_size() == (400, 240)
    sc.set_export_scale(0.5)                               # "Tamanho exato…" também muda a tela
    qapp.processEvents()
    w2 = view.mapFromScene(500, 0).x() - view.mapFromScene(0, 0).x()
    assert abs(w2 - w0 * 0.5) <= 2


def test_rename_migrates_old_config_folder(tmp_path, monkeypatch):
    from shotwise import config as cfgmod
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    old = tmp_path / "ShotWin"
    (old / "library").mkdir(parents=True)
    (old / "config.json").write_text('{"language": "en"}', encoding="utf-8")
    (old / "library" / "x.shotwin").write_text("{}", encoding="utf-8")
    d = cfgmod.config_dir()
    assert d.name == "Shotwise" and not old.exists()
    assert (d / "config.json").read_text(encoding="utf-8") == '{"language": "en"}'
    assert (d / "library" / "x.shotwin").exists()          # a biblioteca vai junto
    assert cfgmod.config_dir() == d                        # segunda chamada: nada a migrar
    from shotwise import logsetup
    assert logsetup.log_dir() == d / "logs"


def test_rotate_image_swaps_size_and_undo(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow
    win = EditorWindow(solid(500, 300, "#88aacc"), Config())
    win.show()
    qapp.processEvents()
    win.rotate_image(90)
    assert win.scene.render_image().width() == 300 and win.scene.render_image().height() == 500
    win.scene.undo_stack.undo()
    assert win.scene.render_image().width() == 500


def test_gif_preview_rotate_and_exact_times(qapp):
    from shotwise.recorder import GifPreviewDialog
    dlg = GifPreviewDialog(_frames(6), [500] * 6, "x.gif")
    dlg._rotate(90)
    assert dlg.images[0].width() == 80 and dlg.images[0].height() == 120
    dlg._undo()
    assert dlg.images[0].width() == 120
    dlg.sp_from.setValue(0.5)
    dlg.sp_to.setValue(1.5)
    dlg._times_edited()
    assert dlg.selection() == (1, 2)
    dlg.close()


def test_gif_effects_zoom_highlight_crop(qapp):
    from PySide6.QtCore import QRectF
    from shotwise.recorder import GifPreviewDialog, apply_crop, apply_highlight, apply_zoom, zoom_factor
    frames = _frames(8, 200, 100)
    reg = QRectF(0.5, 0.5, 0.25, 0.25)
    z = apply_zoom(frames, 2, 5, reg)
    assert all(im.size() == frames[0].size() for im in z)
    assert z[0] is frames[0] and z[7] is frames[7]            # fora do trecho nada muda
    assert zoom_factor(2, 2, 5) == 0 and zoom_factor(5, 2, 5) == 0 and zoom_factor(3, 2, 5) > 0
    h = apply_highlight(frames, 1, 2, reg)
    assert h[1].pixelColor(5, 5).red() < frames[1].pixelColor(5, 5).red() or h[1].pixelColor(5, 5) != frames[1].pixelColor(5, 5)
    c = apply_crop(frames, reg)
    assert c[0].width() == 50 and c[0].height() == 25
    dlg = GifPreviewDialog(frames, [100] * 8, "x.gif")
    dlg.show()
    qapp.processEvents()
    assert not dlg.view.drag_enabled                      # sem ferramenta, arrastar não marca área
    dlg.view.set_region(QRectF(0.1, 0.1, 0.4, 0.4))
    assert dlg.view.region() is not None
    dlg._do_crop()
    assert dlg.images[0].width() < 200
    dlg._undo()
    assert dlg.images[0].width() == 200
    dlg.close()


def test_settings_dialog_has_tabs(qapp):
    from shotwise.config import Config
    from shotwise.settings_dialog import SettingsDialog
    dlg = SettingsDialog(Config())
    assert dlg.tabs.count() == 4
    video = dlg.tabs.widget(2)
    assert dlg.sp_gif_fps.parent() is video or video.isAncestorOf(dlg.sp_gif_fps)


def test_updater_folder_versions_and_hash(tmp_path):
    import hashlib
    from shotwise import updater
    assert updater.is_newer("1.11.0", "1.10.1") and not updater.is_newer("1.10.1", "1.10.1") and updater.is_newer("2", "1.99")
    (tmp_path / "Shotwise-Setup-1.9.0.exe").write_bytes(b"a")
    new = tmp_path / "Shotwise-Setup-1.12.0.exe"
    new.write_bytes(b"installer")
    (tmp_path / "Shotwise-Python-Setup-1.20.0.exe").write_bytes(b"py")
    info = updater.find_in_folder(str(tmp_path), frozen=True)
    assert info.version == "1.12.0" and info.name == new.name
    assert updater.find_in_folder(str(tmp_path), frozen=False).version == "1.20.0"
    # latest.json com SHA-256 correto e incorreto (e nome com caminho é reduzido ao nome do arquivo)
    good = hashlib.sha256(b"installer").hexdigest()
    (tmp_path / "latest.json").write_text('{"version":"1.12.0","file":"../x/Shotwise-Setup-1.12.0.exe","sha256":"%s"}' % good)
    info = updater.find_in_folder(str(tmp_path), frozen=True)
    path = updater.download(info)
    assert path.read_bytes() == b"installer"
    info.sha256 = "0" * 64
    import pytest
    with pytest.raises(ValueError):
        updater.download(info)


def test_settings_about_tab_saves_update_options(qapp):
    from shotwise.config import Config
    from shotwise.settings_dialog import SettingsDialog
    cfg = Config()
    dlg = SettingsDialog(cfg)
    dlg.cmb_upd.setCurrentIndex(dlg.cmb_upd.findData("repo"))
    dlg.ed_repo.setText("acme/shotwise")
    dlg.cb_upd_start.setChecked(True)
    dlg._accept()
    assert (cfg.update_source, cfg.update_repo, cfg.update_on_start) == ("repo", "acme/shotwise", True)


def test_install_defaults_applied_once(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from shotwise import config as cfgmod
    d = cfgmod.config_dir()
    d.mkdir(parents=True, exist_ok=True)
    f = d / "install_defaults.json"
    f.write_text(json.dumps({"update_source": "folder", "update_folder": r"\\srv\share\Shotwise"}), encoding="utf-8")
    cfg = cfgmod.Config()
    assert cfg.update_source == "repo"                      # padrão: repositório web
    assert cfgmod.apply_install_defaults(cfg) is True
    assert (cfg.update_source, cfg.update_folder) == ("folder", r"\\srv\share\Shotwise")
    assert not f.exists() and cfgmod.apply_install_defaults(cfg) is False
    f.write_text('{"update_source": "folder"}', encoding="utf-8")       # pasta de rede sem caminho volta ao padrão
    cfg2 = cfgmod.Config()
    cfgmod.apply_install_defaults(cfg2)
    assert cfg2.update_source == "repo"


def _wait(qapp, cond, ms=30000):
    import time
    t0 = time.time()
    while not cond() and (time.time() - t0) * 1000 < ms:
        qapp.processEvents()
        time.sleep(0.01)
    return cond()


def test_mp4_encoder_writes_valid_file(qapp, tmp_path):
    import pytest
    from shotwise import videoenc
    if not videoenc.AVAILABLE:
        pytest.skip("QtMultimedia indisponível")
    frames = _frames(8, 121, 81)                      # tamanho ímpar: o encoder arredonda para par
    out = tmp_path / "t.mp4"
    res = {}
    enc = videoenc.Mp4Encoder(frames, [100] * 4 + [300] * 4, str(out))
    enc.done.connect(lambda p: res.update(ok=p))
    enc.failed.connect(lambda m: res.update(err=m))
    enc.start()
    assert _wait(qapp, lambda: res), "o encoder não terminou"
    assert "ok" in res, res
    data = out.read_bytes()
    assert data[4:8] == b"ftyp" and len(data) > 1000
    assert videoenc.even_size(frames).width() == 120 and videoenc.even_size(frames).height() == 80


def test_preview_dialog_saves_mp4(qapp, tmp_path):
    import pytest
    from shotwise import videoenc
    from shotwise.recorder import GifPreviewDialog, default_video_path
    if not videoenc.AVAILABLE:
        pytest.skip("QtMultimedia indisponível")
    assert default_video_path(str(tmp_path)).endswith(".mp4")
    out = tmp_path / "clip.mp4"
    dlg = GifPreviewDialog(_frames(6, 120, 80), [200] * 6, lambda: str(out), kind="mp4")
    dlg._show_saved = lambda p: None                  # sem janela modal no teste
    saved = []
    dlg.saved.connect(saved.append)
    dlg.show()
    dlg._save()
    assert _wait(qapp, lambda: saved), "não salvou"
    assert out.is_file() and out.stat().st_size > 1000
    dlg.close()


def test_mp4_config_limits_and_recorder_budget(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from shotwise import config as cfgmod
    d = cfgmod.config_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps({"mp4_fps": 500, "mp4_max_width": 1, "mp4_max_memory_mb": 10 ** 9}), encoding="utf-8")
    c = cfgmod.Config.load()
    assert (c.mp4_fps, c.mp4_max_width, c.mp4_max_memory_mb) == (30, 320, 4000)
    assert cfgmod.DEFAULT_HOTKEYS["hotkey_mp4"] == "Alt+Shift+V"
    from shotwise.recorder import GifRecorder
    assert GifRecorder(lambda: None, 15, 10, 800, max_bytes=123).max_bytes == 123


def test_run_scroll_delivers_result_and_releases_app(qapp, monkeypatch):
    """O método _run_scroll existe, usa as configurações, entrega a imagem e libera o app (_busy)."""
    import numpy as np
    from PySide6.QtCore import QRect
    from shotwise import app as appmod
    from shotwise.scrollcap import ScrollResult
    calls = {}

    def fake_run(screen, logical, phys, delay, frames, height, progress=None):
        calls["args"] = (delay, frames, height)
        return ScrollResult(np.zeros((300, 100, 3), np.uint8), "Fim da página alcançado.", 4)

    class Dummy:
        cfg = type("C", (), {"scroll_delay_ms": 111, "scroll_max_frames": 7, "scroll_max_height": 999, "hide_notifications": False})()
        _busy = True
        _notify = appmod.ShotwiseApp._notify
        delivered = []

        class tray:
            @staticmethod
            def showMessage(*a, **k):
                Dummy.msgs.append(a[1])
        msgs = []

        def _deliver(self, img):
            self.delivered.append(img)

    monkeypatch.setattr(appmod, "run_scroll_capture", fake_run)
    d = Dummy()
    appmod.ShotwiseApp._run_scroll(d, None, QRect(0, 0, 100, 300), QRect(0, 0, 100, 300))
    assert calls["args"] == (111, 7, 999) and d._busy is False
    assert len(d.delivered) == 1 and (d.delivered[0].width(), d.delivered[0].height()) == (100, 300)

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(appmod, "run_scroll_capture", boom)
    d2 = Dummy()
    d2.delivered = []
    appmod.ShotwiseApp._run_scroll(d2, None, QRect(0, 0, 10, 10), QRect(0, 0, 10, 10))
    assert d2._busy is False and not d2.delivered


def test_video_split_delete_cut_range_undo(qapp):
    from shotwise.recorder import GifPreviewDialog, delete_frames, keep_frames, segment_bounds, split_clip
    # funções puras: divisão no meio de um quadro longo duplica o quadro e preserva a duração total
    imgs, durs, cs = split_clip(_frames(3), [1000, 1000, 1000], [], 1500)
    assert durs == [1000, 500, 500, 1000] and cs == [2] and len(imgs) == 4
    assert split_clip(_frames(3), [1000] * 3, [], 1000)[2] == [1]       # exatamente na fronteira
    assert split_clip(_frames(3), [1000] * 3, [], 0)[2] == []           # fora do clipe: sem efeito
    assert segment_bounds([2], 4, 0) == (0, 1) and segment_bounds([2], 4, 3) == (2, 3)
    i2, d2, c2 = delete_frames(imgs, durs, cs, 2, 3)
    assert d2 == [1000, 500] and c2 == []
    i3, d3, c3 = delete_frames(imgs, durs, [1, 3], 1, 1)                # a emenda não vira divisão
    assert d3 == [1000, 500, 1000] and c3 == [2]
    assert keep_frames(imgs, durs, cs, 1, 3)[2] == [1]

    dlg = GifPreviewDialog(_frames(4), [2500] * 4, lambda: "x.mp4", kind="mp4")   # 10 s
    dlg._timer.stop()
    dlg._show_frame(1)                                                  # playhead em 2,5 s
    dlg._split()
    assert dlg.cuts == [1] and dlg.selection() == (1, 3)
    # clicar num segmento seleciona o segmento
    dlg.timeline.resize(1000, 48)
    dlg.timeline.set_selection(0, 0)
    dlg.set_selection(*dlg.timeline.segment_of(2))
    assert dlg.selection() == (1, 3)
    dlg._delete()                                                       # exclui o segmento: sobra 2,5 s
    assert dlg.timeline.total == 2500 and len(dlg.images) == 1
    dlg._undo()
    dlg._undo()
    assert dlg.timeline.total == 10000 and dlg.cuts == []
    # apagar a parte do meio junta as pontas (sem divisão na emenda) e deixa tudo tocável
    dlg.sp_at.setValue(3.0)
    dlg._at_edited()
    dlg._split()
    dlg.sp_at.setValue(7.0)
    dlg._at_edited()
    dlg._split()
    assert len(dlg.cuts) == 2
    dlg.set_selection(*dlg.timeline.segment_of(dlg.timeline.index_of_ms(5000)))
    dlg._delete()
    assert dlg.timeline.total == 6000 and dlg.cuts == [] and dlg.timeline.is_full()
    dlg._undo()
    dlg._undo()
    dlg._undo()
    assert dlg.timeline.total == 10000
    # dividir num tempo digitado
    dlg.sp_at.setValue(4.0)
    dlg._at_edited()
    dlg._split()
    assert sum(dlg.durations) == 10000 and 2 in dlg.cuts or len(dlg.cuts) == 1
    dlg.reject()


def test_updater_requires_hash_and_signature_policy(tmp_path, monkeypatch):
    import hashlib

    import pytest

    from shotwise import updater
    f = tmp_path / "Shotwise-Setup-9.0.0.exe"
    f.write_bytes(b"installer")
    # sem SHA-256 a atualização é recusada (e nada fica na pasta temporária)
    with pytest.raises(ValueError):
        updater.download(updater.UpdateInfo("9.0.0", str(f), f.name, None))
    sha = hashlib.sha256(b"installer").hexdigest()
    info = updater.UpdateInfo("9.0.0", str(f), f.name, sha)
    assert updater.download(info).read_bytes() == b"installer"
    # política da assinatura: precisa ser válida e, se houver emissor fixado, ser dele
    pin = updater.normalize_thumbprints("ab:cd:" + "0" * 36 + " , lixo")
    assert pin == ["ABCD" + "0" * 36]
    assert updater.signature_ok("Valid", "abcd" + "0" * 36, pin)
    assert not updater.signature_ok("Valid", "1" * 40, pin)
    assert not updater.signature_ok("NotSigned", "", [])
    assert not updater.signature_ok("HashMismatch", "abcd" + "0" * 36, pin)
    assert updater.signature_ok("Valid", "1" * 40, [])
    # assinatura exigida e inválida: recusa e apaga o arquivo baixado
    monkeypatch.setattr(updater, "check_signature", lambda p: ("NotSigned", ""))
    with pytest.raises(ValueError):
        updater.download(info, require_signature=True)
    monkeypatch.setattr(updater, "check_signature", lambda p: ("Valid", "1" * 40))
    assert updater.download(info, require_signature=True).is_file()
    # limites: manifesto grande demais é recusado
    (tmp_path / "latest.json").write_text(" " * (updater.MAX_MANIFEST_BYTES + 10))
    with pytest.raises(ValueError):
        updater.find_in_folder(str(tmp_path), frozen=True)


def test_config_save_is_atomic_and_signer_clamped(tmp_path, monkeypatch):
    from shotwise import config
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    c = config.Config()
    c.update_signer = "A" * 1000
    c.save()
    assert not list(tmp_path.glob("*.tmp")) and (tmp_path / "config.json").is_file()
    assert len(config.Config.load().update_signer) == 400
    assert config.Config.load().update_require_signature is True


def test_selection_overlay_annotations_go_to_editor(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtTest import QTest

    from shotwise.config import Config
    from shotwise.editor import EditorWindow
    from shotwise.selector import RegionOverlay
    scr = qapp.primaryScreen()
    img = QImage(scr.geometry().size(), QImage.Format.Format_RGB32)
    img.fill(QColor("#2a4d7a"))
    ov = RegionOverlay(scr, img, "x", True, True)
    ov.resize(scr.geometry().size())
    ov.show()
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(ov, QPoint(420, 300))
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(420, 300))
    assert ov._adjusting and ov._bar is not None and ov._can_adjust()
    ov._bar.set_tool("rect", emit=True)
    vp = ov._view.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
    QTest.mouseMove(vp, QPoint(150, 120))
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=QPoint(150, 120))
    assert ov.has_annotations() and not ov._can_adjust()        # com anotações a área fica travada
    ov._undo()
    assert not ov.has_annotations() and not ov._can_adjust()    # ferramenta de desenho ativa
    ov._bar.set_tool("select", emit=True)
    assert ov._can_adjust()                                     # sem anotações, "Ajustar" volta a valer
    ov._bar.set_tool("arrow", emit=True)
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=QPoint(30, 150))
    QTest.mouseMove(vp, QPoint(200, 60))
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=QPoint(200, 60))
    # com anotações a seta volta a funcionar: seleciona itens (não fica presa na ferramenta de desenho)
    ov._bar.set_tool("select", emit=True)
    assert ov._scene.tool == "select" and ov._bar.tool == "select" and not ov._can_adjust()
    assert not ov._view.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    ov._bar._pick_color("#00ff00")
    assert ov._scene.opt_color.name() == "#00ff00"
    got = []
    ov.region_selected.connect(lambda *a: got.append(a))
    ov._confirm()
    assert len(got) == 1 and [d["t"] for d in ov.annotation_pd.items] == ["arrow"]
    ed = EditorWindow(None, Config(), project=ov.annotation_pd)
    assert any(type(i).__name__ == "LineItem" for i in ed.scene.items())
    # sem anotações nada é entregue ao editor
    ov2 = RegionOverlay(scr, img, "x", True, True)
    ov2.resize(scr.geometry().size())
    ov2.show()
    QTest.mousePress(ov2, Qt.MouseButton.LeftButton, pos=QPoint(50, 50))
    QTest.mouseRelease(ov2, Qt.MouseButton.LeftButton, pos=QPoint(250, 200))
    ov2._confirm()
    assert ov2.annotation_pd is None
    ov.close()
    ov2.close()


def test_video_typed_times_work_without_pressing_enter(qapp):
    """Digitar os tempos e clicar direto em Cortar trecho / Dividir (sem Enter) tem de funcionar."""
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtTest import QTest

    from shotwise.recorder import GifPreviewDialog
    frames = []
    for k in range(30):
        im = QImage(160, 90, QImage.Format.Format_RGB888)
        im.fill(QColor(k * 8, 80, 160))
        frames.append(im)
    dlg = GifPreviewDialog(frames, [100] * 30, lambda: "x.mp4", kind="mp4")     # 3 s
    dlg.show()
    dlg._timer.stop()
    assert dlg.btn_split.isEnabled()                                            # sempre disponível
    # dividir num tempo digitado, também sem Enter
    dlg.sp_at.lineEdit().setText(dlg.sp_at.textFromValue(1.5) + " s")
    dlg.btn_split.click()
    assert dlg.cuts and sum(dlg.durations) == 3000
    dlg.btn_undo.click()
    dlg.reject()


def test_audio_track_gap_fill_mix_and_clip_mapping():
    import numpy as np
    from shotwise import audiocap as ac
    # lacuna (loopback sem dados enquanto nada toca) vira silêncio: o áudio acompanha o relógio
    t = ac.Track(48000, 2)
    one_s = np.full((4800, 2), 1000, "<i2").tobytes()        # 100 ms
    t.feed(one_s, 100)                                       # ocupa 0..100 ms
    t.feed(one_s, 600)                                       # chega em 600 ms => 500..600 ms (lacuna de 400 ms)
    t.finish(800)
    assert abs(t.frames - 48000 * 0.8) < 5
    a = ac.to_stereo48(t.raw(), 48000, 2)
    assert a[:4800].min() > 0 and not a[4800:24000].any() and a[24000:28800].min() > 0
    # reamostragem 44,1 kHz -> 48 kHz e mono -> estéreo
    mono = (np.sin(np.arange(44100) / 20) * 8000).astype("<i2").tobytes()
    b = ac.to_stereo48(mono, 44100, 1)
    assert b.shape == (48000, 2) and np.allclose(b[:, 0], b[:, 1])
    # mistura com limite (sem estourar)
    loud = np.full((100, 2), 0.9, np.float32)
    pcm = ac.mix_to_pcm([loud, loud])
    assert np.frombuffer(pcm, "<i2").max() == 32767
    # o áudio acompanha as edições: cada quadro lê o trecho original certo, e falta vira silêncio
    pcm = bytes(range(256)) * (ac.BYTES_PER_MS * 4 // 256 + 1)
    out = ac.clip_audio(pcm[:ac.BYTES_PER_MS * 3], [2, 0], [2, 1])           # origem tem só 3 ms
    assert len(out) == 3 * ac.BYTES_PER_MS
    assert out[:ac.BYTES_PER_MS] == pcm[2 * ac.BYTES_PER_MS:3 * ac.BYTES_PER_MS]
    assert not any(out[ac.BYTES_PER_MS:2 * ac.BYTES_PER_MS])                  # 3..4 ms não existe: silêncio
    assert out[2 * ac.BYTES_PER_MS:] == pcm[:ac.BYTES_PER_MS]


def test_video_edits_carry_audio_sources(qapp):
    from shotwise.recorder import GifPreviewDialog, delete_frames, keep_frames, split_clip
    imgs, durs, cs, ss = split_clip(_frames(3), [1000, 1000, 1000], [], 1500, [0, 1000, 2000])
    assert durs == [1000, 500, 500, 1000] and ss == [0, 1000, 1500, 2000] and cs == [2]
    _, d2, _, s2 = delete_frames(imgs, durs, cs, 1, 1, ss)
    assert d2 == [1000, 500, 1000] and s2 == [0, 1500, 2000]                  # o trecho 1000..1500 saiu do áudio
    _, d3, _, s3 = keep_frames(imgs, durs, cs, 2, 3, ss)
    assert s3 == [1500, 2000]
    dlg = GifPreviewDialog(_frames(4), [100, 100, 100, 100], lambda: "x.mp4", kind="mp4", audio=bytes(10))
    dlg.show()
    assert dlg.srcs == [0, 100, 200, 300]
    dlg.sp_at.setValue(0.1)
    dlg._at_edited()
    dlg._split()                                                              # sem mudar o áudio: só divide
    dlg.set_selection(1, 1)
    dlg._delete()                                                             # remove 100..200 ms
    assert dlg.durations == [100, 100, 100] and dlg.srcs == [0, 200, 300]
    dlg._undo()
    dlg._undo()
    dlg._undo()
    assert dlg.srcs == [0, 100, 200, 300]
    dlg.close()


def test_mp4_with_audio_has_audio_stream(qapp, tmp_path):
    import json
    import shutil
    import subprocess

    import numpy as np
    import pytest
    from shotwise import videoenc
    if not videoenc.AVAILABLE or shutil.which("ffprobe") is None:
        pytest.skip("QtMultimedia ou ffprobe indisponível")
    t = np.arange(96000) / 48000
    sig = (np.sin(2 * np.pi * 440 * t) * 9000).astype("<i2")
    pcm = np.stack([sig, sig], 1).tobytes()
    out = tmp_path / "a.mp4"
    res = {}
    enc = videoenc.Mp4Encoder(_frames(8, 120, 80), [100] * 4 + [300] * 4, str(out), audio=pcm)
    enc.done.connect(lambda p: res.update(ok=p))
    enc.failed.connect(lambda m: res.update(err=m))
    enc.start()
    assert _wait(qapp, lambda: res), "o encoder não terminou"
    assert "ok" in res, res
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json",
                                      str(out)], capture_output=True, text=True).stdout)
    kinds = {s["codec_type"]: float(s["duration"]) for s in info["streams"]}
    assert enc.audio_used and "audio" in kinds and "video" in kinds
    assert abs(kinds["audio"] - 1.6) < 0.1


def test_audio_config_defaults_and_settings_roundtrip(qapp, monkeypatch):
    from shotwise.config import Config
    from shotwise.settings_dialog import SettingsDialog
    c = Config()
    assert c.mp4_audio_system and c.mp4_audio_mic and c.mp4_mic_device == ""
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    dlg = SettingsDialog(c)
    assert dlg.chk_aud_sys.isChecked() and dlg.chk_aud_mic.isChecked() and dlg.cmb_mic.itemData(0) == ""
    dlg.chk_aud_sys.setChecked(False)
    dlg.chk_aud_mic.setChecked(False)
    dlg._accept()
    assert c.mp4_audio_system is False and c.mp4_audio_mic is False


def test_video_player_is_time_based_and_zoom_shows_on_static_start(qapp):
    """Um quadro parado de vários segundos no início: a cabeça anda dentro dele, dá para clicar nos primeiros segundos,
    tocar a partir de 0 s, e o zoom aparece mesmo sobre esse quadro."""
    from PySide6.QtCore import QPoint, QRectF, Qt
    from PySide6.QtTest import QTest

    from shotwise.recorder import GifPreviewDialog, refine_range
    from PySide6.QtGui import QColor, QPainter
    frames = _frames(4, 160, 90)
    for im in frames:                                                             # padrão na imagem, para o zoom mudar pixels
        p = QPainter(im)
        p.fillRect(100, 50, 30, 20, QColor("white"))
        p.end()
    dlg = GifPreviewDialog(frames, [7000, 300, 300, 300], lambda: "x.gif")        # começo parado de 7 s
    dlg.show()
    dlg.resize(900, 700)
    qapp.processEvents()
    dlg._timer.stop()
    tl = dlg.timeline
    x3 = tl._x(3000)
    QTest.mouseClick(tl, Qt.MouseButton.LeftButton, pos=QPoint(int(x3), 24))      # 3 s, dentro do 1º quadro
    assert abs(dlg._pos_ms - 3000) < 60 and abs(dlg.sp_at.value() - 3.0) < 0.06
    # tocar a partir daqui avança a cabeça
    dlg._play_from(dlg._pos_ms)
    dlg._clock.start()
    dlg._play_base = 1000.0
    import time
    time.sleep(0.12)
    dlg._tick()
    assert dlg._pos_ms > 1050
    dlg._timer.stop()
    # em 0 s também toca
    dlg._show_pos(0.0)
    dlg._play_from(0.0)
    time.sleep(0.1)
    dlg._tick()
    assert dlg._pos_ms > 50
    dlg._timer.stop()
    # dividir exatamente onde a cabeça está (3 s dentro do quadro parado)
    dlg._show_pos(3000.0)
    dlg._split()
    assert dlg.cuts == [1] and sum(dlg.durations) == 7900 and dlg.durations[:2] == [3000, 4000]
    dlg._undo()
    # zoom sobre o quadro parado: o início é quebrado e a aproximação aparece
    imgs, durs, cs, ss, a, b = refine_range(dlg.images, dlg.durations, dlg.cuts, dlg.srcs, 0, 3)
    assert sum(durs) == 7900 and len(imgs) > 20 and ss[:3] == [0, durs[0], durs[0] + durs[1]]
    dlg.view.set_region(QRectF(0.2, 0.2, 0.3, 0.3))
    dlg._do_zoom()
    assert len(dlg.images) > 20 and sum(dlg.durations) == 7900
    assert any(dlg.frame_image(i) != dlg.frame_image(0) for i in range(1, 20))
    dlg.close()


def test_file_naming_pattern_and_month_folders(tmp_path):
    from datetime import datetime

    from shotwise import naming
    now = datetime(2026, 11, 9, 14, 5, 7)
    assert naming.format_name("", now) == "Shotwise_2026-11-09_14-05-07"
    assert naming.format_name("Cap_%d-%m-%Y_%H%M%S", now) == "Cap_09-11-2026_140507"
    # separadores e caracteres inválidos não saem da pasta nem quebram o Windows
    assert "/" not in naming.format_name("../x/%Y", now) and "\\" not in naming.format_name("a\\b:%Y", now)
    assert naming.format_name("CON", now) == "_CON"
    assert naming.format_name("%Y.", now) == "2026"
    p = naming.build_path(str(tmp_path), "png", "Cap_%Y", True, now)
    assert p == tmp_path / "2026" / "11" / "Cap_2026.png" and p.parent.is_dir()
    p.write_bytes(b"x")
    assert naming.build_path(str(tmp_path), "png", "Cap_%Y", True, now).name == "Cap_2026_2.png"     # não sobrescreve
    assert naming.build_path(str(tmp_path / "n"), "mp4", "Cap_%Y", False, now, create=False) == tmp_path / "n" / "Cap_2026.mp4"
    from shotwise.recorder import default_gif_path, default_video_path
    assert default_video_path(str(tmp_path), "V_%Y", True).endswith(".mp4") and default_gif_path(str(tmp_path)).endswith(".gif")


def test_hide_notifications_keeps_warnings(qapp):
    from PySide6.QtWidgets import QSystemTrayIcon

    from shotwise import app as appmod
    shown = []

    class D:
        cfg = type("C", (), {"hide_notifications": True})()
        tray = type("T", (), {"showMessage": staticmethod(lambda *a: shown.append(a[1]))})()
    appmod.ShotwiseApp._notify(D, "t", "info", QSystemTrayIcon.MessageIcon.Information, 1000)
    appmod.ShotwiseApp._notify(D, "t", "aviso", QSystemTrayIcon.MessageIcon.Warning, 1000)
    assert shown == ["aviso"]
    D.cfg.hide_notifications = False
    appmod.ShotwiseApp._notify(D, "t", "info", QSystemTrayIcon.MessageIcon.Information, 1000)
    assert shown == ["aviso", "info"]


def test_selection_overlay_ctrl_c_and_ctrl_s_confirm_with_action(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtTest import QTest

    from shotwise.selector import RegionOverlay
    scr = qapp.primaryScreen()
    img = QImage(scr.geometry().size(), QImage.Format.Format_RGB32)
    img.fill(QColor("#2a4d7a"))
    for key, want in ((Qt.Key.Key_C, "copy"), (Qt.Key.Key_S, "save")):
        ov = RegionOverlay(scr, img, "x", True, True)
        ov.resize(scr.geometry().size())
        ov.show()
        QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(60, 60))
        QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(300, 200))
        got = []
        ov.region_selected.connect(lambda *a: got.append(a))
        QTest.keyClick(ov, key, Qt.KeyboardModifier.ControlModifier)
        assert len(got) == 1 and ov.action == want
    # Enter mantém o comportamento das configurações
    ov = RegionOverlay(scr, img, "x", True, True)
    ov.resize(scr.geometry().size())
    ov.show()
    QTest.mousePress(ov, Qt.MouseButton.LeftButton, pos=QPoint(60, 60))
    QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(300, 200))
    QTest.keyClick(ov, Qt.Key.Key_Return)
    assert ov.action == ""


def test_open_saved_gif_and_mp4_in_player(qapp, tmp_path):
    import numpy as np
    import pytest
    from PIL import Image

    from shotwise import mediaload, videoenc
    # GIF: quadros iguais seguidos se fundem; duração muito curta vira 100 ms
    fr = [Image.new("RGB", (50, 40), (i * 40, 0, 0)) for i in range(4)]
    fr.insert(1, fr[0].copy())
    gif = tmp_path / "t.gif"
    fr[0].save(gif, save_all=True, append_images=fr[1:], duration=[100, 100, 50, 200, 5], loop=0)
    imgs, durs, trunc = mediaload.load_gif(str(gif))
    assert durs == [200, 50, 200, 100] and not trunc and imgs[0].width() == 50
    (tmp_path / "x.gif").write_bytes(b"nao e gif")
    with pytest.raises(ValueError):
        mediaload.load_gif(str(tmp_path / "x.gif"))
    # MP4: grava com áudio e relê; duração e áudio se mantêm
    if not videoenc.AVAILABLE:
        pytest.skip("QtMultimedia indisponível")
    t = np.arange(96000) / 48000
    sig = (np.sin(2 * np.pi * 440 * t) * 9000).astype("<i2")
    pcm = np.stack([sig, sig], 1).tobytes()
    out = tmp_path / "v.mp4"
    res = {}
    enc = videoenc.Mp4Encoder(_frames(8, 120, 80), [200] * 8, str(out), audio=pcm)
    enc.done.connect(lambda p: res.update(ok=p))
    enc.failed.connect(lambda m: res.update(err=m))
    enc.start()
    assert _wait(qapp, lambda: res) and "ok" in res, res
    got = {}
    ld = mediaload.Mp4Loader(str(out), fps=15, max_width=100)
    ld.done.connect(lambda i, d, a, tr_: got.update(ok=(i, d, a, tr_)))
    ld.failed.connect(lambda m: got.update(err=m))
    ld.start()
    assert _wait(qapp, lambda: got, 20000), "a leitura não terminou"
    assert "ok" in got, got
    imgs, durs, audio, trunc = got["ok"]
    assert abs(sum(durs) - 1600) <= 80 and imgs[0].width() == 100 and not trunc
    assert len(audio) == sum(durs) * 192 and np.abs(np.frombuffer(audio, "<i2")).max() > 1000
    # arquivo que não é vídeo falha com mensagem, sem travar
    (tmp_path / "bad.mp4").write_bytes(b"lixo" * 100)
    bad = {}
    ld2 = mediaload.Mp4Loader(str(tmp_path / "bad.mp4"))
    ld2.done.connect(lambda *a: bad.update(ok=1))
    ld2.failed.connect(lambda m: bad.update(err=m))
    ld2.start()
    assert _wait(qapp, lambda: bad, 20000) and "err" in bad


def test_editor_numeral_border_stays_selected_and_selects_same_kind(qapp):
    from shotwise.annotations import StepItem
    from shotwise.project import project_from_scene
    scene = AnnotScene(solid(400, 300, "#8899aa"))
    scene.set_tool("step")
    # numeral: cria selecionado; o clique em outra área cria o próximo (sem precisar de clique extra)
    _mouse(scene, "press", 60, 60)
    _mouse(scene, "release", 60, 60)
    steps = [i for i in scene.items() if isinstance(i, StepItem)]
    assert len(steps) == 1 and steps[0].isSelected() and steps[0].number == 1
    steps[0].apply_style(step_size=30, step_border=QColor("#00ff00"))        # tamanho e borda ajustáveis
    assert steps[0].radius == 30 and steps[0].border == QColor("#00ff00")
    _mouse(scene, "press", 250, 200)
    _mouse(scene, "release", 250, 200)
    steps = sorted((i for i in scene.items() if isinstance(i, StepItem)), key=lambda s: s.number)
    assert [s.number for s in steps] == [1, 2] and steps[1].isSelected() and not steps[0].isSelected()
    # sem borda (transparente) e persistência no projeto
    steps[1].apply_style(step_border=QColor(0, 0, 0, 0))
    assert steps[1].border.alpha() == 0 and scene.render_image().width() == 400
    pd = project_from_scene(scene)
    assert sorted(d["border"] for d in pd.items if d["t"] == "step") == ["#00000000", "#ff00ff00"]
    from shotwise.project import build_scene
    again = build_scene(pd, AnnotScene())
    assert sorted(i.border.name(QColor.NameFormat.HexArgb) for i in again.items() if isinstance(i, StepItem)) == [
        "#00000000", "#ff00ff00"]

    # ferramenta de desenho: clicar em cima de um desenho existente do mesmo tipo o seleciona
    scene2 = AnnotScene(solid(400, 300, "#8899aa"))
    scene2.set_tool("rect")
    _mouse(scene2, "press", 50, 50)
    _mouse(scene2, "move", 150, 120)
    _mouse(scene2, "release", 150, 120)
    rect = next(i for i in scene2.items() if isinstance(i, ShapeItem))
    scene2.clearSelection()
    assert not rect.isSelected()
    _mouse(scene2, "press", 50, 85)              # em cima da borda esquerda do retângulo
    _mouse(scene2, "release", 50, 85)
    assert rect.isSelected() and len([i for i in scene2.items() if isinstance(i, ShapeItem)]) == 1
    # com a ferramenta seta, clicar num retângulo NÃO o seleciona (tipo diferente): começa uma seta
    scene2.clearSelection()
    scene2.set_tool("arrow")
    _mouse(scene2, "press", 50, 85)
    _mouse(scene2, "move", 120, 200)
    _mouse(scene2, "release", 120, 200)
    assert any(getattr(i, "kind", "") == "arrow" for i in scene2.items())


def test_canvas_grows_when_shape_passes_the_image_edge(qapp):
    scene = AnnotScene(solid(200, 100, "#8899aa"))
    assert scene.canvas_rect() == QRectF(0, 0, 200, 100)
    scene.set_tool("rect")
    _mouse(scene, "press", 150, 50)
    _mouse(scene, "move", 260, 90)               # passa da borda direita
    _mouse(scene, "release", 260, 90)
    c = scene.canvas_rect()
    assert c.left() == 0 and c.top() == 0 and c.bottom() == 100          # lados sem excesso não mudam
    assert c.right() >= 260 + scene.GROW_MARGIN - 1                      # direita cresce com sobra
    out = scene.render_image()
    assert out.width() == int(c.width()) > 260 and out.height() == 100
    # desfazer volta ao tamanho original
    scene.undo_stack.undo()
    assert scene.canvas_rect() == QRectF(0, 0, 200, 100)
    # desenho dentro da imagem não altera a tela, nem com alças/seleção
    scene.undo_stack.redo()
    scene.set_tool("select")
    for it in scene.items():
        if isinstance(it, ShapeItem):
            it.setPos(-200, 0)
    assert scene.canvas_rect().left() < 0


def test_background_shadow_direction_and_outer_radius(qapp):
    from shotwise.annotations import BackgroundSettings
    d = BackgroundSettings.from_dict({"enabled": True, "shadow_blur": 999, "shadow_dir": "x", "outer_radius": 30})
    assert d.shadow_blur == 160 and d.shadow_dir == "down" and d.outer_radius == 30
    assert BackgroundSettings().padding == 40 and BackgroundSettings().radius == 24
    outs = {}
    for direction in ("down", "up"):
        scene = AnnotScene(solid(100, 100, "#ffffff"))
        scene.background = BackgroundSettings(True, "#ffffff", "#ffffff", False, 60, 0, True, shadow_blur=50,
                                              shadow_dir=direction)
        scene.refresh_canvas()
        a = qimage_to_np(scene.render_image())
        outs[direction] = (int(a[60 + 100 + 15, 110].sum()), int(a[60 - 15, 110].sum()))   # abaixo / acima da imagem
    assert outs["down"][0] < outs["down"][1]          # sombra para baixo escurece mais abaixo
    assert outs["up"][1] < outs["up"][0]
    scene.background = BackgroundSettings(True, "#ff0000", "#ff0000", False, 30, 0, False, outer_radius=40)
    scene.refresh_canvas()
    img = scene.render_image()
    assert img.pixelColor(0, 0).alpha() == 0 and img.pixelColor(img.width() // 2, 2).alpha() == 255


def test_background_dialog_builds_settings(qapp):
    from shotwise.dialogs import BackgroundDialog
    scene = AnnotScene(solid(100, 100, "#ffffff"))
    dlg = BackgroundDialog(scene)
    dlg.s_shadow.setValue(70)
    dlg.cmb_dir.setCurrentIndex(dlg.cmb_dir.findData("up"))
    dlg.s_outer.setValue(20)
    s = dlg.settings()
    assert s.shadow_blur == 70 and s.shadow_dir == "up" and s.outer_radius == 20 and s.shadow


def _drag(scene, a, b):
    _mouse(scene, "press", *a)
    _mouse(scene, "move", *b)
    _mouse(scene, "release", *b)


def test_tools_keep_selection_create_on_drag_and_switch_on_click(qapp):
    from shotwise.annotations import ShapeItem
    scene = AnnotScene(solid(400, 300, "#ffffff"))
    got = []
    scene.tool_change_requested.connect(got.append)
    scene.set_tool("rect")
    _drag(scene, (20, 20), (100, 80))
    r1 = [i for i in scene.items() if isinstance(i, ShapeItem)][0]
    assert r1.isSelected()
    _drag(scene, (200, 150), (300, 250))                      # arrastar em outro lugar cria outra forma
    assert len([i for i in scene.items() if isinstance(i, ShapeItem)]) == 2
    scene.set_tool("ellipse")
    _mouse(scene, "press", 20, 20)                            # clicar (sem arrastar) em outro tipo seleciona
    _mouse(scene, "release", 20, 20)
    assert got == ["rect"] and r1.isSelected()
    assert len([i for i in scene.items() if isinstance(i, ShapeItem)]) == 2


def test_eyedropper_samples_image_color(qapp):
    scene = AnnotScene(solid(100, 100, "#12ab34"))
    seen = []
    scene.picker = seen.append
    _mouse(scene, "press", 50, 50)
    assert seen[0].name() == "#12ab34" and scene.picker is None
    scene.opt_color = QColor("#336699")
    scene.set_tool("redact")
    _drag(scene, (10, 10), (60, 60))
    from shotwise.annotations import ShapeItem
    assert [i for i in scene.items() if isinstance(i, ShapeItem)][0].color.name() == "#336699"


def test_video_effects_are_editable_and_survive_cuts(qapp):
    from PySide6.QtCore import QRectF
    from shotwise.recorder import GifPreviewDialog
    frames = _frames(10, 200, 100)
    dlg = GifPreviewDialog(frames, [100] * 10, "x.mp4", kind="gif")
    dlg.show()
    qapp.processEvents()
    dlg.set_selection(2, 4)
    dlg.view.set_region(QRectF(0.1, 0.1, 0.3, 0.3))
    dlg._do_highlight()
    assert len(dlg.effects) == 1 and dlg._sel_fx == 0
    fx = dlg.effects[0]
    assert (fx.s0, fx.s1) == (200, 500) and dlg.timeline.fx == [("highlight", 2, 4)]
    assert dlg.images[3] is frames[3] or dlg.images[3] == frames[3]       # quadros originais intactos
    assert dlg.frame_image(3) != dlg.frame_image(8)                       # efeito só no trecho
    # reeditar a área sem Ctrl+Z: com o efeito selecionado, marcar outra área altera o mesmo efeito
    dlg.view.set_region(QRectF(0.5, 0.5, 0.3, 0.3))
    dlg._region_changed()
    assert len(dlg.effects) == 1
    # estender o efeito pela ponta da faixa
    dlg._push_history()
    dlg._fx_edge(0, "b", 6)
    assert dlg.effects[0].s1 == 700
    # um segundo efeito, distinto, em outro trecho
    dlg._fx_select(-1)
    dlg.set_selection(8, 9)
    dlg.view.set_region(QRectF(0.2, 0.2, 0.2, 0.2))
    dlg._do_hide()
    assert [e.kind for e in dlg.effects] == ["highlight", "hide"]
    # cortar um trecho mantém o efeito pelo tempo original
    dlg.set_selection(0, 1)
    dlg._delete()
    assert dlg.effects[0].s0 == 200 and dlg.timeline.fx[0][0] == "highlight"
    imgs, durs = dlg.selected()
    assert len(imgs) == len(durs) == len(dlg.images)
    dlg._fx_select(0)
    dlg._fx_remove()
    assert [e.kind for e in dlg.effects] == ["hide"]
    dlg._undo()
    assert len(dlg.effects) == 2
    dlg.close()


def test_options_panel_background_sliders_commit_one_undo_step(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow
    win = EditorWindow(solid(300, 200, "#dddddd"), Config())
    win.show()
    qapp.processEvents()
    win.select_tool("background")
    n = win.scene.undo_stack.count()
    win.sl_bg_pad.sl.setValue(90)                        # sem arrastar (teclado): um passo
    assert win.scene.background.padding == 90 and win.scene.undo_stack.count() == n + 1
    win.sl_bg_outer.sl.setValue(30)
    assert win.scene.background.outer_radius == 30
    win._bg_apply(mode="mesh")
    assert win.scene.background.mode == "mesh"
    out = win.scene.render_image()
    assert out.width() == 300 + 180
    win._bg_swap_colors()
    win.scene.undo_stack.undo()
    win.close()


def test_video_stacked_effects_text_and_whole_playback(qapp):
    from PySide6.QtCore import QRectF
    from shotwise.recorder import GifPreviewDialog
    dlg = GifPreviewDialog(_frames(10, 200, 100), [100] * 10, "x.mp4", kind="gif")
    dlg.show()
    qapp.processEvents()
    dlg.set_selection(2, 5)
    for kind, reg in (("hide", QRectF(0.1, 0.1, 0.2, 0.2)), ("highlight", QRectF(0.5, 0.5, 0.3, 0.3))):
        dlg._fx_select(-1)
        dlg.view.set_region(reg)
        dlg._fx_from_button(kind)
    dlg._fx_select(-1)
    dlg.view.set_region(QRectF(0.0, 0.7, 0.9, 0.25))
    dlg._do_text("Olá")
    assert [e.kind for e in dlg.effects] == ["hide", "highlight", "text"] and dlg.effects[2].text == "Olá"
    assert dlg.timeline.fx_rows == [0, 1, 2]                        # sobrepostos: três linhas empilhadas
    a, b = dlg.frame_image(3), dlg.frame_image(8)
    assert a != b and a.size() == b.size()
    # a reprodução cobre o vídeo todo, não só o bloco selecionado
    assert dlg._sel_span() == (0.0, float(dlg.timeline.total))
    dlg.close()


def test_video_merge_all_blocks_keeps_content_and_effects(qapp):
    from PySide6.QtCore import QRectF
    from shotwise.recorder import GifPreviewDialog
    dlg = GifPreviewDialog(_frames(10, 200, 100), [100] * 10, "x.mp4", kind="gif")
    dlg.show()
    qapp.processEvents()
    assert not dlg.btn_merge.isEnabled()
    for t in (3.0, 6.0):
        dlg.sp_at.setValue(t / 10)
        dlg._at_edited()
        dlg._split()
    assert len(dlg.cuts) == 2 and dlg.btn_merge.isEnabled()
    dlg.set_selection(*dlg.timeline.segment_of(dlg.timeline.index_of_ms(500)))
    dlg.view.set_region(QRectF(0.1, 0.1, 0.3, 0.3))
    dlg._do_highlight()
    dlg._fx_select(-1)
    total = dlg.timeline.total
    dlg._merge_all()
    assert dlg.cuts == [] and dlg.timeline.total == total and dlg.timeline.is_full() and len(dlg.effects) == 1
    dlg._undo()
    assert len(dlg.cuts) == 2
    dlg.close()


def test_editor_remembers_last_tool_options(qapp, tmp_path, monkeypatch):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow
    monkeypatch.setattr(Config, "save", lambda self: None)
    cfg = Config()
    w1 = EditorWindow(solid(300, 200, "#dddddd"), cfg)
    w1.show()
    w1.set_color(QColor("#00aa55"))
    w1.sp_width.setValue(9)
    w1.sl_strength.setValue(40)
    w1.cb_fill.setChecked(True)
    w1._bg_apply(mode="mesh", shadow_dir="up", color1="#112233")
    w1._opts_tb._user_pos = QPoint(30, 40)
    w1.save_tool_options()
    w1.close()
    opts = cfg.tool_options
    assert opts["color"] == "#00aa55" and opts["width"] == 9 and opts["background"]["mode"] == "mesh"
    w2 = EditorWindow(solid(300, 200, "#dddddd"), cfg)
    w2.show()
    assert w2.scene.opt_color.name() == "#00aa55" and w2.scene.opt_width == 9 and w2.scene.opt_strength == 40
    assert w2.scene.opt_fill is not None and w2.sp_width.value() == 9
    assert w2.scene.background.mode == "mesh" and w2.scene.background.shadow_dir == "up" and not w2.scene.background.enabled
    assert w2._opts_tb._user_pos == QPoint(30, 40)
    w2.close()


def test_video_effect_tools_and_playback_start_paused(qapp):
    from PySide6.QtCore import QRectF
    from shotwise.recorder import GifPreviewDialog
    dlg = GifPreviewDialog(_frames(10, 200, 100), [100] * 10, "x.mp4", kind="gif")
    dlg.show()
    qapp.processEvents()
    assert not dlg._playing and not dlg._timer.isActive() and not dlg.cb_loop.isChecked()
    dlg._arm("highlight")                                    # ferramenta ativa: arrastar na imagem cria o efeito
    assert dlg.btn_hl.isChecked() and dlg.view.drag_enabled
    dlg.set_selection(2, 4)
    dlg.view.set_region(QRectF(0.1, 0.1, 0.3, 0.3))
    assert [e.kind for e in dlg.effects] == ["highlight"]
    dlg.view.set_region(QRectF(0.5, 0.5, 0.2, 0.2))          # outra área, com a ferramenta ainda ativa: outro efeito
    assert len(dlg.effects) == 2
    dlg._arm("highlight")                                    # desliga
    assert not dlg.btn_hl.isChecked()
    dlg._arm("crop")
    dlg.view.set_region(QRectF(0.0, 0.0, 0.5, 0.5))
    assert dlg.images[0].width() == 100 and not dlg.btn_crop.isChecked()
    # sem repetir: toca uma vez e para no fim
    dlg._set_playing(True)
    dlg._play_base = float(dlg.timeline.total) - 1
    dlg._clock.start()
    import time
    time.sleep(0.05)
    dlg._tick()
    assert not dlg._playing
    dlg.close()


def test_panel_arrow_cursor_squeeze_and_hints(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(1200, 400, "#fff"), Config())
    win.resize(1000, 700)
    win.show()
    win.select_tool("rect")
    assert win._opts_tb.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert win.view.viewportMargins().right() == 0                          # nenhuma faixa reservada: o painel flutua
    win.select_tool("crop")
    assert not win._opts_tb.isVisible() and win.view.viewportMargins().right() == 0
    assert win._hint.isVisible() and "área" in win._hint._label.text()
    win.select_tool("ocr")
    assert win._hint.isVisible() and not win._opts_tb.isVisible()
    win.select_tool("rect")
    assert not win._hint.isVisible()


def test_redact_opacity_border_and_flip(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(300, 200, "#fff"), Config())
    win.show()
    win.select_tool("redact")
    for g in ("color", "rborder"):
        assert all(a.isVisible() for a in win._opt_actions[g])
    assert not hasattr(win, "ls_ropac")                  # a tarja não tem opacidade: é sempre sólida
    _drag_draw(win.scene, 40, 40, 160, 100)
    it = next(i for i in win.scene.items() if isinstance(i, ShapeItem))
    assert it.kind == "redact" and it.color.alpha() == 255
    win.cb_rborder.setChecked(True)
    assert it.fill is not None
    win.set_color(QColor("#123456"))
    assert it.color.alpha() == 255 and it.color.name() == "#123456"
    # espelhar mantém o tamanho e vira uma única camada
    win.select_tool("resize")
    win.flip_image(True)
    assert win.scene.output_size() == (300, 200)


def test_scale_slider_single_undo_and_bg_row(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(200, 100, "#fff"), Config())
    win.show()
    win.select_tool("resize")
    n = win.scene.undo_stack.count()
    win.ls_scale.setValue(50)
    assert win.scene.export_scale == 0.5 and win.scene.undo_stack.count() == n + 1
    assert "50" in win.ls_scale.lbl.text()
    win.scene.undo_stack.undo()
    assert win.ls_scale.value() == 100
    win.select_tool("background")
    assert win.btn_bg_c1.parentWidget() is win.btn_bg_c2.parentWidget()      # Cor 1 e Cor 2 lado a lado
    assert not win.btn_bg_shadow.icon().isNull()
    assert win.btn_bg_swap.text() == "" and not win.btn_bg_swap.icon().isNull()


def test_panel_floats_without_reserved_strip(qapp):
    from shotwise.config import Config
    from shotwise.editor import EditorWindow

    win = EditorWindow(solid(1000, 300, "#fff"), Config())
    win.resize(1150, 600)
    win.show()
    win.select_tool("pixelate")
    tb = win._opts_tb
    assert tb.isVisible() and win.view.viewportMargins().right() == 0
    tb._user_pos = QPoint(100, 50)
    tb.reposition()
    assert tb.pos() == QPoint(100, 50)
    tb._user_pos = QPoint(99999, 99999)
    tb.reposition()
    assert tb.x() + tb.width() <= win.view.width()
    win.select_tool("select")
    assert win.view.viewportMargins().right() == 0


def test_library_closes_after_opening_capture(qapp, monkeypatch):
    from shotwise import dialogs

    class E:
        id, title, updated, size = "abc", "Captura", "2026-11-10T22:00:00", (10, 10)

    monkeypatch.setattr(dialogs.library, "entries", lambda: [E()])
    monkeypatch.setattr(dialogs.library, "thumb", lambda _pid: QImage())
    dlg = dialogs.LibraryDialog()
    opened = []
    dlg.open_project.connect(opened.append)
    dlg.show()
    dlg.lst.setCurrentRow(0)
    dlg.bt_open.click()
    assert opened == ["abc"] and not dlg.isVisible()


def test_updater_pins_signer_even_with_old_empty_config(tmp_path, monkeypatch):
    import json
    from shotwise import UPDATE_SIGNER_DEFAULT, config
    from shotwise.updater import normalize_thumbprints, signature_ok

    assert len(normalize_thumbprints(UPDATE_SIGNER_DEFAULT)) == 1
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"update_signer": ""}), encoding="utf-8")
    monkeypatch.setattr(config.Config, "path", classmethod(lambda cls: f))
    cfg = config.Config.load()
    pinned = normalize_thumbprints(cfg.update_signer)
    assert pinned == normalize_thumbprints(UPDATE_SIGNER_DEFAULT)
    assert signature_ok("Valid", UPDATE_SIGNER_DEFAULT.lower(), pinned)
    assert not signature_ok("Valid", "A" * 40, pinned) and not signature_ok("NotSigned", "", pinned)
