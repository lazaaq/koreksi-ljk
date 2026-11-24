"""Membaca berkas: format gambar, PDF/TIFF multi-halaman, nama berkas aneh, berkas rusak."""
import cv2
import numpy as np
import pytest

from koreksi_ljk import omr


def _write(path, img, ext=None):
    ok, buf = cv2.imencode(ext or path.suffix, img)
    assert ok
    buf.tofile(str(path))
    return path


@pytest.fixture
def page():
    rng = np.random.default_rng(0)
    img = np.full((1100, 800), 245, np.uint8)
    cv2.rectangle(img, (100, 100), (700, 1000), 0, 3)
    cv2.putText(img, "LJK", (300, 500), cv2.FONT_HERSHEY_SIMPLEX, 4, 0, 6)
    img[rng.random(img.shape) < 0.001] = 0
    return img


@pytest.mark.parametrize("ext", [".png", ".jpg", ".bmp", ".tif", ".webp"])
def test_load_common_formats(tmp_path, page, ext):
    p = _write(tmp_path / f"scan{ext}", page)
    label, img = omr.load_page(p)
    assert label == p.name
    assert img.dtype == np.uint8 and img.ndim == 2 and img.shape == page.shape


def test_load_gif(tmp_path, page):
    from PIL import Image
    p = tmp_path / "SCAN.GIF"  # ekstensi huruf besar seperti hasil scanner
    Image.fromarray(page).convert("P").save(p)
    _, img = omr.load_page(p)
    assert img.shape == page.shape and img.dtype == np.uint8


def test_load_color_and_alpha(tmp_path, page):
    bgr = cv2.cvtColor(page, cv2.COLOR_GRAY2BGR)
    bgra = cv2.cvtColor(page, cv2.COLOR_GRAY2BGRA)
    for name, im in (("c.png", bgr), ("a.png", bgra)):
        _, g = omr.load_page(_write(tmp_path / name, im))
        assert g.ndim == 2 and abs(int(g.mean()) - int(page.mean())) <= 2


def test_load_16bit_tiff(tmp_path, page):
    p = _write(tmp_path / "deep.tif", page.astype(np.uint16) * 257)
    _, g = omr.load_page(p)
    assert g.dtype == np.uint8 and g.max() > 200


def test_multipage_tiff(tmp_path, page):
    p = tmp_path / "batch.tiff"
    ok, buf = cv2.imencodemulti(".tiff", [page, 255 - page, page]) if hasattr(cv2, "imencodemulti") else (False, None)
    if not ok:
        from PIL import Image
        ims = [Image.fromarray(x) for x in (page, 255 - page, page)]
        ims[0].save(p, save_all=True, append_images=ims[1:])
    else:
        buf.tofile(str(p))
    assert omr.page_count(p) == 3
    l2, g2 = omr.load_page(p, 1)
    assert "hal. 2" in l2 and g2.mean() < page.mean()
    assert len(omr.load_pages(p)) == 3


def test_multipage_pdf(tmp_path, page):
    mu = omr._mupdf()
    doc = mu.open()
    for _ in range(2):
        pg = doc.new_page(width=595, height=842)
        pg.insert_text((100, 100), "LEMBAR JAWABAN", fontsize=24)
        pg.draw_rect(mu.Rect(50, 50, 545, 792), width=2)
    p = tmp_path / "scan berkas.pdf"
    doc.save(str(p)); doc.close()
    assert omr.page_count(p) == 2
    label, img = omr.load_page(p, 1, dpi=150)
    assert label.endswith("hal. 2")
    assert img.ndim == 2 and img.shape[0] > img.shape[1] > 1000
    assert img.min() < 50  # teks/garis ikut ter-render


def test_unicode_and_space_filename(tmp_path, page):
    d = tmp_path / "Hasil Scan — Kelas 12 IPA ✓"
    d.mkdir()
    p = _write(d / "Siswa Ñandú 01.png", page)
    assert omr.load_page(p)[1].shape == page.shape
    assert omr.list_sheets(d) == [p]


def test_empty_corrupt_and_tiny_files(tmp_path, page):
    (tmp_path / "kosong.jpg").write_bytes(b"")
    (tmp_path / "rusak.png").write_bytes(b"\x89PNG bukan gambar")
    _write(tmp_path / "kecil.png", page[:100, :100])
    for name in ("kosong.jpg", "rusak.png", "kecil.png"):
        with pytest.raises(ValueError):
            omr.load_page(tmp_path / name)


def test_list_sheets_filters(tmp_path, page):
    for n in ("b.JPG", "a.png", "c.pdf", "d.GIF", "catatan.txt", "._a.png", ".DS_Store", "hasil_koreksi_ljk.json"):
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "sub.png").mkdir()  # folder bernama seperti gambar → diabaikan
    names = [p.name for p in omr.list_sheets(tmp_path)]
    assert names == ["a.png", "b.JPG", "c.pdf", "d.GIF"]  # urut abjad, abaikan berkas tersembunyi macOS


def test_normalize(page):
    assert omr.normalize(page).shape[1] == omr.REF_WIDTH
    big = cv2.resize(page, None, fx=3, fy=3)
    out = omr.normalize(big)
    assert out.shape[1] == omr.REF_WIDTH and abs(out.shape[0] / out.shape[1] - page.shape[0] / page.shape[1]) < 0.01
    assert omr.normalize(cv2.cvtColor(page, cv2.COLOR_GRAY2BGR)).ndim == 2
