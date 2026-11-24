"""Uji tampilan & alur aplikasi (Qt offscreen): template, koreksi folder, hasil, Excel."""
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from conftest import NOMOR, SOAL1, SOAL2, make_template, wait_until
from koreksi_ljk import omr


@pytest.fixture
def A(qapp):
    from koreksi_ljk import app
    return app


@pytest.fixture
def quiet_dialogs(A, monkeypatch):
    """Ganti kotak pesan modal dengan pencatat, supaya tes tidak tertahan."""
    log = []

    class MB:
        Yes, No, Ok = 1, 0, 1
        AcceptRole, DestructiveRole, RejectRole = 0, 1, 2

        @staticmethod
        def question(*a, **k):
            log.append(("question", a[2] if len(a) > 2 else "")); return MB.Yes

        @staticmethod
        def information(*a, **k):
            log.append(("information", a[2] if len(a) > 2 else ""))

        @staticmethod
        def warning(*a, **k):
            log.append(("warning", a[2] if len(a) > 2 else ""))

    monkeypatch.setattr(A, "QMessageBox", MB)
    return log


@pytest.fixture
def window(A, clean_appdata, quiet_dialogs):
    w = A.MainWindow()
    w.resize(1280, 800)
    w.show()
    yield w
    if w.t_grade.worker and w.t_grade.worker.isRunning():
        w.t_grade.worker.stop(); w.t_grade.worker.wait(10000)
    w.t_tpl.dirty = False
    w.close()


def save_template(window, tpl):
    t = window.t_tpl
    t.tpl = tpl; t.bubbles = omr.detect_bubbles(tpl.ref()); t.tpl_dir = None
    t.name.setText(tpl.name); t._enable(True); t.redraw(fit=True)
    t.save()
    window.t_grade.reload_templates()
    return t.tpl_dir


# ----------------------------------------------------------------------------- utilitas
def test_helpers(A):
    assert A.basename(r"E:\Scan\R1\a.GIF") == "a.GIF"
    assert A.basename("/Volumes/USB/R1/b.gif") == "b.gif"
    assert A.safe_name('Try/Out: "1"?') == "Try_Out_ _1__"
    assert A.safe_name("///") == "___" and A.safe_name("") == "template"
    for e in ("*.gif", "*.GIF", "*.pdf", "*.tif", "*.JPG"):
        assert e in A.IMAGE_FILTER


def test_qt_compat_layer(qapp):
    from koreksi_ljk import qt
    assert qt.QT_API in ("PySide6", "PySide2")

    class FakeForm:  # Qt < 6.4 tidak punya setRowVisible
        def __init__(self):
            self.lab = qt.QLabel("x")

        def labelForField(self, f):
            return self.lab
    form, field = FakeForm(), qt.QLineEdit()
    qt.set_form_row_visible(form, field, False)
    assert field.isHidden() and form.lab.isHidden()


# ----------------------------------------------------------------------------- template
def test_template_editor_save_and_list(window, tpl):
    d = save_template(window, make_template(tpl.ref(), omr.detect_bubbles(tpl.ref()), name="TO A"))
    assert (d / "template.json").exists() and (d / "ref.png").exists()
    assert window.t_tpl.list.count() == 1
    assert window.t_grade.tpl_combo.currentText() == "TO A"
    assert "50 soal" in window.t_tpl.status.text()
    assert window.t_tpl.blocks.count() == 3


def test_template_needs_question_block(window, tpl, quiet_dialogs):
    t = window.t_tpl
    t.tpl = omr.Template(name="kosong", ref_path=""); t.tpl.set_ref(tpl.ref()); t._enable(True)
    t.save()
    assert ("warning", "Tambahkan minimal satu blok jawaban soal.") in quiet_dialogs
    assert t.list.count() == 0


def test_template_export_import_roundtrip(window, tpl, tmp_path, A, monkeypatch):
    save_template(window, make_template(tpl.ref(), omr.detect_bubbles(tpl.ref()), id_kind="isian", name="Ekspor"))
    out = tmp_path / "x.ljktemplate"
    monkeypatch.setattr(A.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    window.t_tpl.export_template()
    with zipfile.ZipFile(out) as z:
        assert set(z.namelist()) == {"template.json", "ref.png"}
    d = window.t_tpl.import_file(str(out))
    assert d is not None and window.t_tpl.list.count() == 2
    assert omr.Template.load(d).blocks[2].title == "Kode"


def test_import_rejects_non_template(window, tmp_path, quiet_dialogs):
    bad = tmp_path / "bukan.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("lain.txt", "x")
    assert window.t_tpl.import_file(str(bad)) is None
    assert window.t_tpl.import_file(str(tmp_path / "tidak-ada.ljktemplate")) is None
    assert sum(1 for k, _ in quiet_dialogs if k == "warning") == 2


def test_export_requires_saved(window, tpl, quiet_dialogs):
    window.t_tpl.tpl = tpl; window.t_tpl.tpl_dir = None
    window.t_tpl.export_template()
    assert quiet_dialogs[-1][0] == "information"


@pytest.mark.parametrize("kind,expect", [(0, "soal"), (1, "nomor"), (2, "nama"), (3, "isian")])
def test_block_dialog_kinds(A, qapp, kind, expect):
    d = A.BlockDialog(None, 10, 4, 21)
    d.kind.setCurrentIndex(kind)
    if expect == "isian":
        d.title.setText("Ruang")
    v = d.values()
    assert v["kind"] == expect
    assert d.title.isHidden() == (expect != "isian")
    if expect == "soal":
        assert v["labels"] == "ABCD" and v["start"] == 21 and v["items_along"] == "rows"
    if expect == "nama":
        d.orient.setCurrentIndex(1)
        assert d.values()["labels"] == "ABCDEFGHIJ"
    if expect == "isian":
        d.charset.setCurrentIndex(1)
        assert v["title"] == "Ruang" and d.values()["labels"].startswith("ABCD")


def test_block_highlight(window, tpl):
    save_template(window, make_template(tpl.ref(), omr.detect_bubbles(tpl.ref())))
    t = window.t_tpl
    t.blocks.setCurrentRow(1)
    assert t._rect_items[1][0].pen().width() == 5 and t._rect_items[0][0].pen().width() == 2


# ----------------------------------------------------------------------------- kunci
def test_key_info_states(window, tpl):
    save_template(window, make_template(tpl.ref(), omr.detect_bubbles(tpl.ref())))
    g = window.t_grade
    g.key.setPlainText("ABCDE" * 10)
    assert "50 soal" in g.key_info.text() and g.key_info.property("role") == "ok"
    g.key.setPlainText("ABC")
    assert "3 dari 50" in g.key_info.text()
    g.key.setPlainText("1.A 2.K 3.B 99.C")
    assert g.key_dict() == {1: "A", 3: "B"}            # nomor di luar template dibuang


def test_key_letter_not_in_sheet(window, tpl, bubbles):
    t = omr.Template(name="ABCD", ref_path=""); t.set_ref(tpl.ref())
    t.blocks.append(omr.fit_block(bubbles, SOAL1, 25, 5, "soal", "rows", start=1, labels="ABCDF"))
    save_template(window, t)
    window.t_grade.key.setPlainText("1.E 2.A 3.B")
    assert window.t_grade.key_info.property("role") == "error"
    assert "1" in window.t_grade.key_info.text()


def test_template_cache_reloads_after_change(window, tpl):
    d = save_template(window, make_template(tpl.ref(), omr.detect_bubbles(tpl.ref()), name="Cache"))
    g = window.t_grade
    t1 = g.template(); assert g.template() is t1          # dari cache
    data = json.loads((d / "template.json").read_text(encoding="utf-8"))
    data["name"] = "Cache 2"
    import os, time
    (d / "template.json").write_text(json.dumps(data), encoding="utf-8")
    os.utime(d / "template.json", (time.time() + 5, time.time() + 5))
    assert g.template().name == "Cache 2"


def test_student_map_and_import(window, tmp_path, quiet_dialogs, A, monkeypatch):
    g = window.t_grade
    csv = tmp_path / "siswa.csv"
    csv.write_text("\ufeffnomor;nama\n001;Andi\n002;Budi Santoso\n;kosong\n", encoding="utf-8")
    monkeypatch.setattr(A.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(csv), "")))
    g.import_students()
    m = g.student_map()
    assert m["001"] == "Andi" and m["002"] == "Budi Santoso" and "" not in m


# ----------------------------------------------------------------------------- koreksi folder
def run_folder(window, folder, key_text):
    g = window.t_grade
    g.key.setPlainText(key_text)
    g.folder.setText(str(folder))
    g.start()
    wait_until(qapp_of(window), lambda: g.worker is None or (not g.worker.isRunning() and g.b_go.text() == "Mulai koreksi"))


def qapp_of(w):
    from koreksi_ljk.qt import QApplication
    return QApplication.instance()


def test_grade_folder_end_to_end(window, tpl, scan_folder, key, tmp_path, A):
    import shutil
    folder = tmp_path / "scan"
    shutil.copytree(scan_folder, folder)
    (folder / "rusak.jpg").write_bytes(b"bukan gambar")
    (folder / "._siswa_01.jpg").write_bytes(b"appledouble")     # berkas tersembunyi macOS di flashdisk
    save_template(window, make_template(tpl.ref(), omr.detect_bubbles(tpl.ref())))
    truths = json.loads((folder / "_truth.json").read_text())
    window.t_grade.students.setPlainText(f"{truths['siswa_01.jpg']['nomor']}, Andi")
    run_folder(window, folder, "".join(key[q] for q in range(1, 51)))
    st = window.store
    assert len(st.results) == 9                               # 8 siswa + 1 rusak; berkas tersembunyi diabaikan
    bad = [r for r in st.results if r.get("error")]
    assert len(bad) == 1 and bad[0]["label"] == "rusak.jpg" and st.needs_review(bad[0])
    for r in st.results:
        if r.get("error"):
            continue
        tr = truths[Path(r["file"]).name]
        exp = omr.grade({int(k): v for k, v in tr["answers"].items()}, key)
        assert st.grade(r)["nilai"] == exp["nilai"]
        assert r["nomor"] == tr["nomor"]
    assert next(r for r in st.results if Path(r["file"]).name == "siswa_01.jpg")["nama"] == "Andi"
    saved = json.loads((folder / A.RESULT_FILE).read_text(encoding="utf-8"))
    assert len(saved["results"]) == 9
    # tabel hasil
    rt = window.t_res
    assert rt.table.rowCount() == 9
    rt.only.setChecked(True)
    assert rt.table.rowCount() == sum(st.needs_review(r) for r in st.results)


def test_continue_only_new_files(window, tpl, scan_folder, key, tmp_path, A, monkeypatch):
    import shutil
    folder = tmp_path / "lanjut"
    folder.mkdir()
    for f in sorted(scan_folder.glob("siswa_0[1-3].jpg")):
        shutil.copy(f, folder)
    save_template(window, make_template(tpl.ref(), omr.detect_bubbles(tpl.ref())))
    run_folder(window, folder, "".join(key[q] for q in range(1, 51)))
    assert len(window.store.results) == 3
    shutil.copy(scan_folder / "siswa_04.jpg", folder)

    class Box:  # pilih "Lanjutkan (hanya berkas baru)"
        AcceptRole, DestructiveRole, RejectRole = 0, 1, 2

        def __init__(self, *a): self.btns = []

        def setWindowTitle(self, *a): pass

        def setText(self, *a): pass

        def addButton(self, *a):
            b = object(); self.btns.append(b); return b

        def exec(self): pass

        def clickedButton(self): return self.btns[0]
    monkeypatch.setattr(A, "QMessageBox", Box)
    run_folder(window, folder, "".join(key[q] for q in range(1, 51)))
    names = sorted(Path(r["file"]).name for r in window.store.results)
    assert names == ["siswa_01.jpg", "siswa_02.jpg", "siswa_03.jpg", "siswa_04.jpg"]


def test_results_edit_and_check(window, tpl, scan_folder, key):
    save_template(window, make_template(tpl.ref(), omr.detect_bubbles(tpl.ref())))
    run_folder(window, scan_folder, "".join(key[q] for q in range(1, 51)))
    st, rt = window.store, window.t_res
    i = next(i for i, r in enumerate(st.results) if not r.get("error"))
    rt.cur = i; rt._select_index(i); rt.show_selected()
    assert rt.view.pix_item is not None                       # gambar beranotasi tampil
    rt.f_ans.setText("AZ*" + "-" * 47)                          # Z bukan pilihan → kosong
    rt.f_nomor.setText("123456"); rt.f_nama.setText("Budi")
    rt.save_edit()
    r = st.results[i]
    assert r["answers"]["1"] == "A" and r["answers"]["2"] == "" and r["answers"]["3"] == "*"
    assert r["nomor"] == "123456" and r["nama"] == "Budi" and r["nomor_flag"] == ""
    assert not [k for k in r["flags"] if k != "0"]
    rt.mark_checked()
    assert st.results[i]["checked"] and not st.needs_review(st.results[i])


def test_flags_outside_key_do_not_need_review(A, qapp):
    st = A.ResultStore()

    class G:
        def key_dict(self): return {1: "A", 2: "B"}
    st.grader = G()
    r = {"answers": {"1": "A"}, "flags": {"55": "tipis/ragu"}, "nomor_flag": ""}
    assert not st.needs_review(r)
    r["flags"]["2"] = "ganda"
    assert st.needs_review(r) and st.relevant_flags(r) == {2: "ganda"}


def test_open_previous_without_template(window, tmp_path, A, monkeypatch, quiet_dialogs):
    f = tmp_path / A.RESULT_FILE
    f.write_text(json.dumps({"template": "Tidak Ada", "results": [
        {"file": r"E:\scan\a.jpg", "label": "a.jpg", "answers": {"1": "A"}, "flags": {}, "nomor": "01", "nama": "X"}]}))
    monkeypatch.setattr(A.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(f), "")))
    window.t_res.open_previous()
    assert window.store.tpl is None and len(window.store.results) == 1
    assert window.t_res.table.rowCount() == 1
    assert any("tidak ditemukan" in m for _, m in quiet_dialogs)
    assert window.store.locate(r"E:\scan\a.jpg") == r"E:\scan\a.jpg"
    (tmp_path / "a.jpg").write_bytes(b"x")
    assert window.store.locate(r"E:\scan\a.jpg") == str(tmp_path / "a.jpg")   # flashdisk pindah huruf drive


# ----------------------------------------------------------------------------- Excel
def test_export_excel(A, qapp, tmp_path, tpl, bubbles):
    import openpyxl
    t = make_template(tpl.ref(), bubbles, id_kind="isian")
    st = A.ResultStore(); st.tpl = t

    class G:
        pb, ps, pk = (type("V", (), {"value": lambda self, v=v: v})() for v in (1, 0, 0))

        def key_dict(self): return {1: "A", 2: "B", 3: "C"}
    st.grader = G()
    st.results = [
        {"file": "a.jpg", "label": "a.jpg", "nomor": "01", "nama": "=HYPERLINK(\"x\")", "answers": {"1": "A", "2": "B", "3": "C"},
         "flags": {}, "fields": {"Kode": "07"}},
        {"file": "b.jpg", "label": "b.jpg", "nomor": "02", "nama": "Budi", "answers": {"1": "A", "2": "", "3": "D"},
         "flags": {"3": "ganda"}, "fields": {"Kode": ""}},
        {"file": "c.jpg", "label": "c.jpg", "error": "rusak", "answers": {}, "flags": {}},
    ]
    out = tmp_path / "rekap.xlsx"
    A.export_excel(str(out), st)
    wb = openpyxl.load_workbook(out)
    ws = wb["Rekap"]
    head = [c.value for c in ws[4]]
    assert head[:9] == ["Peringkat", "Nomor Peserta", "Nama", "Kode", "Benar", "Salah", "Kosong", "Skor", "Nilai"]
    rows = [[c.value for c in r] for r in ws.iter_rows(min_row=6, max_row=7)]
    assert rows[0][2].startswith("'=") and rows[0][3] == "07" and rows[0][8] == 100.0   # bukan rumus
    assert rows[1][2] == "Budi" and rows[1][9] == "perlu dicek"
    assert ws.max_row >= 9                                      # baris rata-rata/tertinggi/terendah
    ps = wb["Per Soal"]
    assert [c.value for c in ps[2]][:5] == [1, "A", 2, 100.0, 0]


# ----------------------------------------------------------------------------- lain-lain
def test_guide_and_cursors(window, A):
    from koreksi_ljk.guide import GuideDialog
    from koreksi_ljk.qt import Qt
    g = GuideDialog(window, 2)
    assert g.findChild(A.QTabWidget).currentIndex() == 2
    assert window.tabs.tabBar().cursor().shape() == Qt.PointingHandCursor
    assert window.t_tpl.list.viewport().cursor().shape() == Qt.PointingHandCursor
    g.close()


def test_image_view_handles_none_and_images(A, qapp):
    v = A.ImageView(placeholder="kosong")
    v.set_image(None)
    assert v.pix_item is None
    v.set_image(np.full((50, 40), 128, np.uint8)); assert v.pix_item is not None
    v.set_image(np.zeros((50, 40, 3), np.uint8), keep_view=True); assert v.pix_item is not None
