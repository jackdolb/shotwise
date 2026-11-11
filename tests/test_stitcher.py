"""Testes do algoritmo de costura com uma "página" sintética."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shotwise.stitcher import ScrollStitcher, Status, stitch_frames  # noqa: E402


def make_page(height=3000, width=500, seed=1):
    """Página com conteúdo variado (texto simulado por blocos aleatórios)."""
    rng = np.random.default_rng(seed)
    page = np.full((height, width, 3), 245, dtype=np.uint8)
    y = 0
    while y < height:
        bh = int(rng.integers(8, 30))
        x0 = int(rng.integers(0, 80))
        x1 = int(rng.integers(200, width - 30))
        color = rng.integers(0, 200, 3)
        page[y : y + bh, x0:x1] = color
        y += bh + int(rng.integers(6, 28))
    return page


def viewport(page, offset, vh, header=None, footer=None):
    """Simula a janela: região rolável + cabeçalho/rodapé fixos."""
    h_h = 0 if header is None else header.shape[0]
    f_h = 0 if footer is None else footer.shape[0]
    body = page[offset : offset + vh - h_h - f_h]
    parts = [p for p in (header, body, footer) if p is not None]
    return np.concatenate(parts, axis=0)


def frames_for(page, vh, step, header=None, footer=None):
    h_h = 0 if header is None else header.shape[0]
    f_h = 0 if footer is None else footer.shape[0]
    body_h = vh - h_h - f_h
    max_off = page.shape[0] - body_h
    frames, off = [], 0
    while True:
        frames.append(viewport(page, off, vh, header, footer))
        if off >= max_off:
            break
        off = min(off + step, max_off)
    frames.append(frames[-1].copy())  # quadro repetido = fim
    return frames


def test_simple_scroll_reconstructs_page():
    page = make_page(3000)
    frames = frames_for(page, vh=600, step=250)
    out, res = stitch_frames(frames)
    assert out is not None
    assert out.shape == page.shape
    assert np.array_equal(out, page)
    assert res[-1].status is Status.END


def test_sticky_header_and_footer_appear_once():
    page = make_page(2400)
    header = np.full((70, page.shape[1], 3), (20, 60, 140), dtype=np.uint8)
    header[20:40, 30:200] = 255
    footer = np.full((50, page.shape[1], 3), (30, 30, 30), dtype=np.uint8)
    footer[10:30, 40:300] = 200
    frames = frames_for(page, vh=700, step=300, header=header, footer=footer)
    out, _ = stitch_frames(frames)
    # esperado = cabeçalho + página inteira + rodapé
    assert out.shape[0] == 70 + page.shape[0] + 50
    assert np.array_equal(out[:70], header)
    assert np.array_equal(out[-50:], footer)
    assert np.array_equal(out[70:-50], page)


def test_variable_step_sizes():
    page = make_page(3500, seed=7)
    vh = 700
    offs = [0, 120, 400, 720, 1100, 1500, 1900, 2300, 2800]  # passos irregulares
    frames = [viewport(page, o, vh) for o in offs]
    frames.append(frames[-1].copy())
    out, _ = stitch_frames(frames)
    assert np.array_equal(out, page[: offs[-1] + vh])


def test_scrollbar_noise_does_not_break_alignment():
    page = make_page(2500, seed=3)
    frames = frames_for(page, vh=600, step=260)
    noisy = []
    for i, f in enumerate(frames):
        f = f.copy()
        y = 10 + (i * 37) % 400
        f[y : y + 80, -8:] = 90  # "barra de rolagem" em posições diferentes
        noisy.append(f)
    out, _ = stitch_frames(noisy)
    assert out.shape[0] == page.shape[0]
    # ignora a faixa da barra de rolagem na comparação
    assert np.array_equal(out[:, :-12], page[:, :-12])


def test_single_frame_returns_itself():
    page = make_page(800)
    st = ScrollStitcher()
    st.add_frame(page[:600])
    assert np.array_equal(st.result(), page[:600])


def test_identical_frames_report_end():
    page = make_page(800)
    st = ScrollStitcher()
    st.add_frame(page[:600])
    assert st.add_frame(page[:600].copy()).status is Status.END


def test_unrelated_frame_is_no_match():
    a = make_page(800, seed=1)[:600]
    b = make_page(800, seed=99)[:600]
    st = ScrollStitcher()
    st.add_frame(a)
    assert st.add_frame(b).status is Status.NO_MATCH


def test_memory_cap_limits_wide_frames():
    # quadros muito largos: o teto de bytes reduz a altura máxima do resultado
    from shotwise import stitcher

    page = make_page(6000, width=2400, seed=11)
    frames = frames_for(page, vh=600, step=250)
    old = stitcher._MAX_RESULT_BYTES
    stitcher._MAX_RESULT_BYTES = 2400 * 3 * 2500          # ~2500 linhas
    try:
        out, _ = stitch_frames(frames, max_height=30000)
    finally:
        stitcher._MAX_RESULT_BYTES = old
    assert out.shape[0] <= 2500


def test_max_height_limit():
    page = make_page(6000, seed=5)
    frames = frames_for(page, vh=600, step=250)
    out, _ = stitch_frames(frames, max_height=2000)
    assert out.shape[0] <= 2000
