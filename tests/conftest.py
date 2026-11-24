"""Fixture bersama untuk unit test Koreksi LJK.

Data uji dibuat sintetis (LJK oval 50 soal + nomor 6 digit) supaya tidak ada data siswa asli di repo.
"""
import json
import os
import random
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import make_synthetic as M  # noqa: E402
from koreksi_ljk import omr  # noqa: E402

PX = omr.REF_WIDTH / 210  # piksel per mm pada gambar template


def mm_rect(x0, y0, x1, y1):
    return [x0 * PX, y0 * PX, (x1 - x0) * PX, (y1 - y0) * PX]


SOAL1 = mm_rect(36, 116, 80, 283)
SOAL2 = mm_rect(121, 116, 165, 283)
NOMOR = mm_rect(116, 36, 164, 99)


@pytest.fixture(scope="session")
def blank_img():
    return M.blank()


@pytest.fixture(scope="session")
def bubbles(blank_img):
    return omr.detect_bubbles(blank_img)


def make_template(blank_img, bubbles, id_kind="nomor", name="Sintetis"):
    tpl = omr.Template(name=name, ref_path="")
    tpl.set_ref(blank_img)
    tpl.blocks.append(omr.fit_block(bubbles, SOAL1, 25, 5, "soal", "rows", start=1))
    tpl.blocks.append(omr.fit_block(bubbles, SOAL2, 25, 5, "soal", "rows", start=26))
    labels = omr.LETTERS if id_kind == "nama" else None
    tpl.blocks.append(omr.fit_block(bubbles, NOMOR, 10, 6, id_kind, "cols", labels=labels,
                                    title="Kode" if id_kind == "isian" else ""))
    return tpl


@pytest.fixture(scope="session")
def tpl(blank_img, bubbles):
    t = make_template(blank_img, bubbles)
    t.baseline()
    return t


@pytest.fixture(scope="session")
def students():
    """[(gambar_scan, kebenaran_jawaban, nomor)] — 8 siswa dengan variasi scan."""
    out = []
    for seed in range(1, 9):
        img, truth, nomor = M.student(seed)
        sc = M.scan(img, seed, rot180=(seed == 5), dpi_scale=(0.67 if seed % 3 == 0 else 1.0))
        out.append((sc, truth, nomor))
    return out


@pytest.fixture(scope="session")
def key():
    rng = random.Random(77)
    return {q: "ABCDE"[rng.randint(0, 4)] for q in range(1, 51)}


@pytest.fixture(scope="session")
def scan_folder(tmp_path_factory, students):
    import cv2
    d = tmp_path_factory.mktemp("scans")
    truths = {}
    for i, (img, truth, nomor) in enumerate(students, 1):
        name = f"siswa_{i:02d}.jpg"
        cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(str(d / name))
        truths[name] = {"answers": truth, "nomor": nomor}
    (d / "_truth.json").write_text(json.dumps(truths))
    return d


@pytest.fixture(scope="session")
def qapp():
    from koreksi_ljk.qt import QApplication, QStandardPaths, prepare_app_attributes
    QStandardPaths.setTestModeEnabled(True)  # QSettings & data aplikasi di lokasi uji, bukan milik pengguna
    QApplication.setOrganizationName("KoreksiLJKTest")
    QApplication.setApplicationName("Koreksi LJK Test")
    app = QApplication.instance()
    if app is None:
        prepare_app_attributes()
        app = QApplication([])
    from koreksi_ljk import theme
    theme.apply(app)
    yield app


@pytest.fixture
def clean_appdata(qapp):
    import shutil
    from koreksi_ljk import app as A
    from koreksi_ljk.qt import QSettings
    shutil.rmtree(A.data_dir(), ignore_errors=True)
    QSettings().clear()
    yield A.templates_dir()
    shutil.rmtree(A.data_dir(), ignore_errors=True)
    QSettings().clear()


def wait_until(qapp, cond, timeout=120):
    import time
    t0 = time.time()
    while not cond():
        qapp.processEvents()
        time.sleep(0.02)
        if time.time() - t0 > timeout:
            raise TimeoutError("menunggu terlalu lama")
    qapp.processEvents()
