"""Projeto editável (.shotwin): camadas originais + anotações, para reabrir e continuar editando.

Formato: arquivo ZIP com
    meta.json      título, datas, caminho do PNG exportado
    project.json   camadas, anotações, recorte, fundo, escala
    layers/N.png   imagens originais (SEM tarjas aplicadas)
    thumb.png      miniatura (já com as anotações)

Segurança: o arquivo guarda as imagens ORIGINAIS, inclusive o que foi escondido por tarjas.
Por isso ele só é gravado na biblioteca local do app (pasta do usuário) e nunca é copiado
para a pasta de capturas. A leitura é defensiva: somente JSON (nada de pickle), nomes de
membros em lista fixa, limites de tamanho/quantidade e validação de todos os números.
"""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QImageReader

from .annotations import (AnnotScene, BackgroundSettings, ImageLayer, LineItem, PenItem, ShapeItem, StepItem,
                          TextItem, ZoomItem, RECT_KINDS, num)

FORMAT_VERSION = 1
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_PNG_BYTES = 120 * 1024 * 1024
MAX_LAYERS = 40
MAX_ITEMS = 5000
MAX_POINTS = 20000
MAX_SIDE = 40000
MAX_PIXELS = 200_000_000          # por camada
MAX_TEXT = 5000
_LAYER_NAME = re.compile(r"^layers/(\d{1,3})\.png$")
_ALLOWED_EXACT = {"meta.json", "project.json", "thumb.png"}


class ProjectError(Exception):
    pass


@dataclass
class ProjectData:
    meta: dict = field(default_factory=dict)
    layers: list[tuple[QImage, QPointF, QRectF]] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    clip: QRectF | None = None
    export_scale: float = 1.0
    export_stretch: float = 1.0
    background: BackgroundSettings = field(default_factory=BackgroundSettings)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _pt(p: QPointF) -> list[float]:
    return [round(p.x(), 3), round(p.y(), 3)]


def _rc(r: QRectF) -> list[float]:
    return [round(r.x(), 3), round(r.y(), 3), round(r.width(), 3), round(r.height(), 3)]


def _col(c: QColor | None):
    return None if c is None else c.name(QColor.NameFormat.HexArgb)


def _pt_in(v) -> QPointF:
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise ProjectError("ponto inválido")
    return QPointF(num(v[0]), num(v[1]))


def _rc_in(v) -> QRectF:
    if not isinstance(v, (list, tuple)) or len(v) != 4:
        raise ProjectError("retângulo inválido")
    return QRectF(num(v[0]), num(v[1]), num(v[2], 0, 0, 1e6), num(v[3], 0, 0, 1e6))


def _col_in(v, default="#ff3b30") -> QColor:
    c = QColor(str(v)) if v is not None else QColor(default)
    return c if c.isValid() else QColor(default)


def _col_opt(v) -> QColor | None:
    if v is None:
        return None
    c = QColor(str(v))
    return c if c.isValid() else None


# ----------------------------------------------------------------------
# serialização
# ----------------------------------------------------------------------
def scene_to_dict(scene: AnnotScene) -> tuple[dict, list[QImage]]:
    layers = scene.layers()
    doc: dict = {
        "version": FORMAT_VERSION,
        "layers": [],
        "items": [],
        "clip": _rc(scene.clip) if scene.clip is not None else None,
        "export_scale": round(scene.export_scale, 4),
        "export_stretch": round(scene.export_stretch, 4),
        "background": scene.background.to_dict(),
    }
    images: list[QImage] = []
    for i, l in enumerate(layers):
        doc["layers"].append({"file": f"layers/{i}.png", "pos": _pt(l.pos()), "box": _rc(l.box)})
        images.append(l.image)
    for it in scene.items(Qt.SortOrder.AscendingOrder):
        if isinstance(it, ImageLayer):
            continue
        d: dict | None = None
        if isinstance(it, ShapeItem) and it.kind in RECT_KINDS:
            d = {"t": it.kind, "pos": _pt(it.pos()), "rect": _rc(it.rect().normalized()),
                 "color": _col(it.color), "width": it.width, "strength": it.strength,
                 "fill": _col(it.fill)}
        elif isinstance(it, ZoomItem):
            d = {"t": "zoom", "pos": _pt(it.pos()), "rect": _rc(it.rect().normalized()), "color": _col(it.color),
                 "width": it.width, "factor": round(it.factor, 3),
                 "offset": _pt(it.offset) if it.offset is not None else None,
                 "bend": _pt(it.bend) if it.bend is not None else None, "arrow": bool(it.arrow)}
        elif isinstance(it, LineItem):
            d = {"t": it.kind, "pos": _pt(it.pos()), "p1": _pt(it.p1), "p2": _pt(it.p2),
                 "color": _col(it.color), "width": it.width, "bend": _pt(it.bend)}
        elif isinstance(it, PenItem):
            d = {"t": "pen", "pos": _pt(it.pos()), "points": [_pt(p) for p in it.points],
                 "color": _col(it.color), "width": it.width}
        elif isinstance(it, TextItem):
            d = {"t": "text", "pos": _pt(it.pos()), "text": it.toPlainText(), "color": _col(it.color),
                 "size": it.size, "bg": _col(it.bg)}
        elif isinstance(it, StepItem):
            d = {"t": "step", "pos": _pt(it.pos()), "number": it.number, "color": _col(it.color),
                 "radius": it.radius, "border": _col(it.border)}
        if d is not None:
            doc["items"].append(d)
    return doc, images


def project_from_scene(scene: AnnotScene) -> ProjectData:
    """Copia o conteúdo de uma cena para um ProjectData (para abrir no editor sem passar por arquivo)."""
    doc, images = scene_to_dict(scene)
    layers = [(img, _pt_in(l["pos"]), _rc_in(l["box"])) for img, l in zip(images, doc["layers"])]
    return ProjectData(layers=layers, items=doc["items"], clip=scene.clip, export_scale=scene.export_scale,
                       export_stretch=scene.export_stretch, background=scene.background)


def make_thumb(scene: AnnotScene, size: int = 220) -> QImage:
    img = scene.render_image()
    return img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def write_project(path: str, scene: AnnotScene, meta: dict) -> None:
    doc, images = scene_to_dict(scene)
    meta = dict(meta)
    meta.setdefault("created", datetime.now().isoformat(timespec="seconds"))
    meta["updated"] = datetime.now().isoformat(timespec="seconds")
    meta["format"] = FORMAT_VERSION
    meta["size"] = list(scene.output_size())
    thumb = _png_bytes(make_thumb(scene))
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:     # PNG já é comprimido
        z.writestr("meta.json", json.dumps(meta, ensure_ascii=False))
        z.writestr("project.json", json.dumps(doc, ensure_ascii=False))
        z.writestr("thumb.png", thumb)
        for i, img in enumerate(images):
            z.writestr(f"layers/{i}.png", _png_bytes(img))
    import os

    os.replace(tmp, path)


# ----------------------------------------------------------------------
# leitura defensiva
# ----------------------------------------------------------------------
def _open_zip(path: str) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as e:
        raise ProjectError("arquivo de projeto inválido") from e
    infos = z.infolist()
    if len(infos) > MAX_LAYERS + 8:
        z.close()
        raise ProjectError("projeto com arquivos demais")
    for info in infos:
        n = info.filename
        if n not in _ALLOWED_EXACT and not _LAYER_NAME.match(n):
            z.close()
            raise ProjectError("conteúdo inesperado no projeto")
        limit = MAX_JSON_BYTES if n.endswith(".json") else MAX_PNG_BYTES
        if info.file_size > limit:
            z.close()
            raise ProjectError("arquivo interno grande demais")
    return z


def _read_member(z: zipfile.ZipFile, name: str, limit: int) -> bytes:
    with z.open(name) as f:
        data = f.read(limit + 1)
    if len(data) > limit:
        raise ProjectError("arquivo interno grande demais")
    return data


def _json_member(z: zipfile.ZipFile, name: str):
    try:
        return json.loads(_read_member(z, name, MAX_JSON_BYTES).decode("utf-8"))
    except KeyError as e:
        raise ProjectError(f"{name} ausente") from e
    except (UnicodeDecodeError, ValueError) as e:
        raise ProjectError(f"{name} inválido") from e


def read_meta(path: str) -> dict:
    """Lê só meta.json (usado na listagem da biblioteca)."""
    z = _open_zip(path)
    try:
        meta = _json_member(z, "meta.json")
        if not isinstance(meta, dict):
            raise ProjectError("meta inválido")
        return meta
    finally:
        z.close()


def read_thumb(path: str) -> QImage:
    z = _open_zip(path)
    try:
        img = QImage()
        try:
            img.loadFromData(_read_member(z, "thumb.png", 4 * 1024 * 1024), "PNG")
        except KeyError:
            pass
        return img
    finally:
        z.close()


def _decode_layer(data: bytes) -> QImage:
    ba = QByteArray(data)
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    rd = QImageReader(buf, b"PNG")
    size = rd.size()
    if (not size.isValid() or size.width() > MAX_SIDE or size.height() > MAX_SIDE
            or size.width() * size.height() > MAX_PIXELS):
        raise ProjectError("imagem interna com dimensões inválidas")
    img = rd.read()
    if img.isNull():
        raise ProjectError("imagem interna corrompida")
    return img


def read_project(path: str) -> ProjectData:
    z = _open_zip(path)
    try:
        meta = _json_member(z, "meta.json")
        doc = _json_member(z, "project.json")
        if not isinstance(meta, dict) or not isinstance(doc, dict):
            raise ProjectError("estrutura inválida")
        if doc.get("version") != FORMAT_VERSION:
            raise ProjectError("versão de projeto não suportada")
        pd = ProjectData(meta=meta)
        layers = doc.get("layers")
        if not isinstance(layers, list) or not (1 <= len(layers) <= MAX_LAYERS):
            raise ProjectError("camadas inválidas")
        for entry in layers:
            if not isinstance(entry, dict):
                raise ProjectError("camada inválida")
            name = entry.get("file")
            if not isinstance(name, str) or not _LAYER_NAME.match(name):
                raise ProjectError("nome de camada inválido")
            try:
                data = _read_member(z, name, MAX_PNG_BYTES)
            except KeyError as e:
                raise ProjectError("camada ausente") from e
            img = _decode_layer(data)
            box = _rc_in(entry.get("box"))
            if box.width() < 1 or box.height() < 1:
                raise ProjectError("camada com tamanho inválido")
            pd.layers.append((img, _pt_in(entry.get("pos")), box))
        items = doc.get("items", [])
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise ProjectError("anotações inválidas")
        for d in items:
            if not isinstance(d, dict) or not isinstance(d.get("t"), str):
                raise ProjectError("anotação inválida")
            pd.items.append(d)
        clip = doc.get("clip")
        pd.clip = _rc_in(clip) if clip is not None else None
        if pd.clip is not None and (pd.clip.width() < 2 or pd.clip.height() < 2):
            pd.clip = None
        pd.export_scale = num(doc.get("export_scale"), 1.0, 0.05, 8.0)
        pd.export_stretch = num(doc.get("export_stretch"), 1.0, 0.05, 20.0)
        pd.background = BackgroundSettings.from_dict(doc.get("background"))
        return pd
    finally:
        z.close()


def build_item(d: dict):
    """Cria o item de anotação a partir de um dict validado; devolve None se desconhecido."""
    t = d.get("t")
    pos = _pt_in(d.get("pos"))
    item = None
    if t in RECT_KINDS:
        item = ShapeItem(t, _rc_in(d.get("rect")), _col_in(d.get("color")),
                         int(num(d.get("width"), 4, 1, 80)), int(num(d.get("strength"), 16, 2, 80)),
                         _col_opt(d.get("fill")))
    elif t == "zoom":
        off = d.get("offset")
        item = ZoomItem(_rc_in(d.get("rect")), _col_in(d.get("color")), int(num(d.get("width"), 3, 1, 80)),
                        num(d.get("factor"), 2.5, 1.2, 8.0), _pt_in(off) if off is not None else None)
        item.arrow = bool(d.get("arrow", True))
        if d.get("bend") is not None:
            item.bend = _pt_in(d["bend"])
    elif t in ("line", "arrow"):
        item = LineItem(t, _pt_in(d.get("p1")), _pt_in(d.get("p2")), _col_in(d.get("color")),
                        int(num(d.get("width"), 4, 1, 80)), 0,
                        _pt_in(d["bend"]) if d.get("bend") is not None else None)
    elif t == "pen":
        pts = d.get("points")
        if not isinstance(pts, list) or not (1 <= len(pts) <= MAX_POINTS):
            raise ProjectError("traço inválido")
        item = PenItem(_pt_in(pts[0]), _col_in(d.get("color")), int(num(d.get("width"), 4, 1, 80)))
        item.points = [_pt_in(p) for p in pts]
        item._rebuild()
    elif t == "text":
        text = str(d.get("text", ""))[:MAX_TEXT]
        item = TextItem(text, _col_in(d.get("color")), int(num(d.get("size"), 28, 6, 300)), _col_opt(d.get("bg")))
        item.committed = True
    elif t == "step":
        item = StepItem(int(num(d.get("number"), 1, 0, 9999)), _col_in(d.get("color")),
                        int(num(d.get("radius"), 16, 6, 120)), _col_in(d.get("border"), "#ffffffff"))
    if item is not None:
        item.setPos(pos)
    return item


def build_scene(pd: ProjectData, scene: AnnotScene | None = None) -> AnnotScene:
    scene = scene or AnnotScene()
    for img, pos, box in pd.layers:
        layer = scene.add_layer(img, pos)
        layer.prepareGeometryChange()
        layer.box = QRectF(box)
    for d in pd.items:
        it = build_item(d)
        if it is not None:
            scene.addItem(it)
    scene.clip = pd.clip
    scene.export_scale = pd.export_scale
    scene.export_stretch = pd.export_stretch
    scene.background = pd.background
    scene.refresh_canvas()
    scene.undo_stack.clear()
    return scene
