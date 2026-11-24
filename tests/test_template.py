"""Deteksi bulatan, pembentukan blok, simpan/muat template."""
import json

import numpy as np
import pytest

import make_synthetic as M
from conftest import NOMOR, PX, SOAL1, make_template
from koreksi_ljk import omr


def test_detect_bubbles_finds_all(bubbles):
    # 250 bulatan soal + 60 bulatan nomor; huruf/garis/logo tidak boleh ikut (toleransi kecil untuk bentuk lain)
    assert 300 <= len(bubbles) <= 520


def test_guess_grid(bubbles):
    assert omr.guess_grid(bubbles, SOAL1) == (25, 5)
    assert omr.guess_grid(bubbles, NOMOR) == (10, 6)
    assert omr.guess_grid(bubbles, [0, 0, 10, 10]) == (0, 0)


def test_fit_block_positions_match_print(bubbles):
    b = omr.fit_block(bubbles, SOAL1, 25, 5, "soal", "rows", start=1)
    for q in (1, 13, 25):
        for k in range(5):
            x_mm, y_mm = M.q_center(q, k)
            x, y = b.bubble(q - 1, k)
            assert abs(x - x_mm * PX) < 3 and abs(y - y_mm * PX) < 3, (q, k)
    assert b.labels == "ABCDE" and b.n_items == 25 and b.n_choices == 5
    assert b.question_numbers() == list(range(1, 26))


def test_fit_block_columns_orientation(bubbles):
    b = omr.fit_block(bubbles, NOMOR, 10, 6, "nomor", "cols")
    assert b.n_items == 6 and b.n_choices == 10 and b.labels == "0123456789"
    x, y = b.bubble(2, 7)            # digit ke-3, angka 7
    xm, ym = M.id_center(2, 7)
    assert abs(x - xm * PX) < 3 and abs(y - ym * PX) < 3


@pytest.mark.parametrize("kind,labels", [("soal", "ABCD"), ("nomor", "0123456789"),
                                         ("nama", omr.ALPHABET[:10]), ("isian", "0123456789")])
def test_default_labels(bubbles, kind, labels):
    along = "rows" if kind == "soal" else "cols"
    rows, cols = (25, 4) if kind == "soal" else (10, 6)
    b = omr.fit_block(bubbles, SOAL1 if kind == "soal" else NOMOR, rows, cols, kind, along)
    assert b.labels == labels


def test_fit_block_without_bubbles_falls_back_to_even_grid():
    b = omr.fit_block([], [100, 200, 400, 1000], 10, 4, "soal", "rows")
    xs = [b.centers[0][c][0] for c in range(4)]
    ys = [b.centers[r][0][1] for r in range(10)]
    assert np.allclose(np.diff(xs), 100) and np.allclose(np.diff(ys), 100)
    assert xs[0] == 150 and ys[0] == 250 and b.radius[0] > 0


def test_split_1d_rejects_non_grid():
    assert omr._split_1d([1, 2, 3], 5) is None                   # terlalu sedikit titik
    assert omr._split_1d([0, 10, 20, 30], 4) == [0, 10, 20, 30]
    assert omr._split_1d([0, 1, 2, 100], 2) is not None


def test_template_save_load_roundtrip(tmp_path, tpl):
    tpl2 = make_template(tpl.ref(), omr.detect_bubbles(tpl.ref()), id_kind="isian", name="Ujian “Akhir” — ✓")
    d = tmp_path / "tpl"
    tpl2.save(d)
    back = omr.Template.load(d)
    assert back.name == tpl2.name
    assert [b.kind for b in back.blocks] == ["soal", "soal", "isian"]
    assert back.blocks[2].title == "Kode"
    assert back.question_numbers() == list(range(1, 51))
    assert back.ref().shape == tpl2.ref().shape
    assert back.next_start() == 51 and back.labels_for(30) == "ABCDE" and back.labels_for(999) == "ABCDE"


def _copy(tpl):
    import copy
    return copy.copy(tpl)  # save() mengubah ref_path; jangan ubah fixture bersama


def test_load_old_and_future_template_formats(tmp_path, tpl):
    d = tmp_path / "lama"
    _copy(tpl).save(d)
    data = json.loads((d / "template.json").read_text(encoding="utf-8"))
    for b in data["blocks"]:
        b.pop("title", None)            # template versi lama: belum ada field "title"
        b["warna"] = "#fff"              # template versi baru: field yang belum dikenal
    (d / "template.json").write_text(json.dumps(data), encoding="utf-8")
    back = omr.Template.load(d)
    assert len(back.blocks) == 3 and all(b.title == "" for b in back.blocks)


def test_load_template_missing_image(tmp_path, tpl):
    d = tmp_path / "rusak"
    _copy(tpl).save(d)
    (d / "ref.png").unlink()
    with pytest.raises(FileNotFoundError):
        omr.Template.load(d)


def test_baseline_measures_printed_bubbles(tpl):
    base = tpl.baseline()
    assert len(base) == 25 * 5 * 2 + 60
    v = np.array(list(base.values()))
    assert (v >= 0).all() and v.max() < 0.6  # garis & huruf cetak: sedikit gelap, jauh di bawah isian penuh
