"""Penyelarasan & pembacaan lembar: akurasi, rotasi, skala, tanda ragu, identitas, kasus rusak."""
import random

import cv2
import numpy as np
import pytest

import make_synthetic as M
from conftest import make_template
from koreksi_ljk import omr


def read(img, tpl):
    res, al = omr.read_sheet(img, tpl, "x.jpg")
    assert not res.error, res.error
    return res, al


def check(res, truth):
    wrong = [q for q in range(1, 51) if res.answers.get(q) != truth[q]]
    silent = [q for q in wrong if q not in res.flags]
    return wrong, silent


def test_accuracy_all_students(tpl, students):
    total = silent_total = 0
    for img, truth, nomor in students:
        res, _ = read(img, tpl)
        wrong, silent = check(res, truth)
        total += len(wrong); silent_total += len(silent)
        assert res.nomor == nomor
    assert total == 0 and silent_total == 0


def test_double_marks_are_flagged(tpl, students):
    flagged = 0
    for img, truth, _ in students:
        res, _ = read(img, tpl)
        for q, v in truth.items():
            if v == "*":
                assert res.answers[q] == "*" and res.flags.get(q) == "ganda"
                flagged += 1
    assert flagged >= 1


@pytest.mark.parametrize("angle", [90, -90, 3.5])
def test_rotated_scans(tpl, students, angle):
    img, truth, nomor = students[0]
    if abs(angle) == 90:
        rot = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE if angle == 90 else cv2.ROTATE_90_COUNTERCLOCKWISE)
    else:
        h, w = img.shape
        M_ = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rot = cv2.warpAffine(img, M_, (w, h), borderValue=240)
    res, _ = read(rot, tpl)
    assert check(res, truth) == ([], []) and res.nomor == nomor


@pytest.mark.parametrize("scale", [0.5, 1.6])
def test_low_and_high_resolution(tpl, students, scale):
    img, truth, nomor = students[1]
    res, _ = read(cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA), tpl)
    assert check(res, truth)[1] == [] and res.nomor == nomor


def test_dark_and_low_contrast_scan(tpl, students):
    img, truth, _ = students[2]
    dark = np.clip(img.astype(np.float32) * 0.55 + 20, 0, 255).astype(np.uint8)
    res, _ = read(dark, tpl)
    assert check(res, truth)[1] == []


def test_faint_and_half_marks_never_silently_wrong(blank_img, tpl):
    silent = 0
    for seed in range(200, 206):
        rng = random.Random(seed); np.random.seed(seed)
        img = M.blank(); truth = {}
        for q in range(1, 51):
            k = rng.randint(0, 4)
            x, y = M.q_center(q, k)
            if rng.random() < 0.3:
                M.fill(img, x - 1, y, rng.uniform(0.22, 0.4), rx=1.8, ry=2.0, rng=rng)  # isian setengah & tipis
            else:
                M.fill(img, x, y, rng.uniform(0.25, 0.6), rng=rng)
            truth[q] = "ABCDE"[k]
        res, _ = read(M.scan(img, seed, dpi_scale=0.5), tpl)
        silent += len(check(res, truth)[1])
    assert silent == 0


def test_blank_sheet(tpl, blank_img):
    res, _ = read(M.scan(blank_img.copy(), 9), tpl)
    assert all(v == "" for v in res.answers.values())
    assert not [q for q in res.flags if q]          # tidak ada tanda palsu di lembar kosong
    assert res.nomor == "" and res.nomor_flag == "nomor peserta tidak diisi"


def test_wrong_document_gives_error_not_crash(tpl):
    rng = np.random.default_rng(1)
    noise = (rng.random((2400, 1700)) * 255).astype(np.uint8)
    for img in (noise, np.full((2400, 1700), 255, np.uint8), np.zeros((300, 300), np.uint8)):
        res, al = omr.read_sheet(img, tpl, "lain.jpg")
        assert res.error and al is None and res.needs_review


def _sheet_with_digits(digits):
    img = M.blank()
    for d, v in enumerate(digits):
        if v is None:
            continue
        for vv in (v if isinstance(v, tuple) else (v,)):
            M.fill(img, *M.id_center(d, vv), 0.8, rx=2.6, ry=2.1)
    return M.scan(img, 3)


@pytest.mark.parametrize("digits,nomor,flag", [
    ((0, 1, 5, None, None, None), "015", ""),                       # nomor pendek: kolom kosong di belakang
    ((None, None, 4, 2, 0, 9), "4209", ""),                          # kolom kosong di depan
    ((1, None, 3, None, None, None), "1_3", "tidak terbaca"),       # kosong di tengah
    ((1, (2, 7), 3, 4, 5, 6), "1?3456", "ganda"),                   # dua angka di satu kolom
])
def test_nomor_rules(tpl, digits, nomor, flag):
    res, _ = read(_sheet_with_digits(digits), tpl)
    assert res.nomor == nomor
    assert (flag in res.nomor_flag) if flag else res.nomor_flag == ""


def test_name_block(blank_img, bubbles):
    t = make_template(blank_img, bubbles, id_kind="nama")      # 6 huruf, pilihan A–J
    res, _ = read(_sheet_with_digits((1, 0, 3, None, 4, None)), t)   # B A D _ E _
    assert res.nama_lembar == "BAD E" and res.nomor == "" and res.nomor_flag == ""


def test_custom_field_block(blank_img, bubbles):
    t = make_template(blank_img, bubbles, id_kind="isian")
    res, _ = read(_sheet_with_digits((0, 1, None, None, None, None)), t)
    assert res.fields == {"Kode": "01"} and res.nomor == ""


def test_sheetresult_json_roundtrip(tpl, students):
    import json
    res, _ = read(students[0][0], tpl)
    d = json.loads(json.dumps(res.to_json()))   # harus bisa disimpan sebagai JSON
    back = omr.SheetResult.from_json(d)
    assert back.answers == res.answers and back.flags == res.flags and back.nomor == res.nomor
    assert isinstance(next(iter(back.answers)), int)


def test_annotate(tpl, students, key):
    res, al = read(students[0][0], tpl)
    out = omr.annotate(al, res, key)
    assert out.shape == al.shape + (3,) and out.dtype == np.uint8
    assert (out != cv2.cvtColor(al, cv2.COLOR_GRAY2BGR)).any()   # ada tanda warna


def test_build_blank_removes_student_marks(tpl, students):
    blank = omr.build_blank([s[0] for s in students])
    # LJK kosong buatan ada di bidang scan pertama; samakan dulu dengan bidang template uji
    # (di aplikasi, pengguna menggambar blok langsung di atas LJK kosong buatan ini)
    blank, _ = omr.align(blank, tpl.ref())
    t = omr.Template(name="median", ref_path=""); t.set_ref(blank)
    t.blocks = tpl.blocks
    vals = np.array(list(t.baseline().values()))
    assert vals.max() < 0.45            # tak ada bulatan yang tetap "terisi" di LJK kosong buatan
    res, _ = read(students[3][0], t)     # dan bisa dipakai sebagai template
    assert check(res, students[3][1]) == ([], [])


def test_build_blank_needs_five(students):
    with pytest.raises(ValueError):
        omr.build_blank([s[0] for s in students[:3]])
