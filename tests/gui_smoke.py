"""Uji asap GUI (offscreen): template, koreksi folder, hasil, ekspor Excel, tangkapan layar."""
import json, os, shutil, sys, time
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF
from koreksi_ljk import app as A, omr

D = Path(__file__).parent / "data"; OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots"); OUT.mkdir(exist_ok=True)
QApplication.setOrganizationName("LanaAqilTest"); QApplication.setApplicationName("Koreksi LJK Test")
qa = QApplication([])
shutil.rmtree(A.templates_dir(), ignore_errors=True)
(D / "scans" / A.RESULT_FILE).unlink(missing_ok=True)
w = A.MainWindow(); w.resize(1360, 860); w.show()
# --- buat template lewat editor (tanpa dialog)
t = w.t_tpl
t.tpl = omr.Template(name="Try Out Bimbel Cerdas", ref_path=""); t.tpl.set_ref(omr.load_pages(D / "ljk_kosong.png")[0][1])
t.bubbles = omr.detect_bubbles(t.tpl.ref()); t.name.setText(t.tpl.name); t._enable(True)
s = omr.REF_WIDTH / 210
for (x0, y0, x1, y1), kind, rows, cols, along, start in [((36, 116, 80, 283), "soal", 25, 5, "rows", 1), ((121, 116, 165, 283), "soal", 25, 5, "rows", 26), ((116, 36, 164, 99), "nomor", 10, 6, "cols", 1)]:
    rect = [x0 * s, y0 * s, (x1 - x0) * s, (y1 - y0) * s]
    assert omr.guess_grid(t.bubbles, rect) == (rows, cols), omr.guess_grid(t.bubbles, rect)
    t.tpl.blocks.append(omr.fit_block(t.bubbles, rect, rows, cols, kind, along, start))
t.redraw(fit=True); t.save(); qa.processEvents()
w.tabs.setCurrentWidget(t); qa.processEvents(); t.view.fit(); qa.processEvents(); w.grab().save(str(OUT / "1_template.png"))
# --- koreksi
g = w.t_grade
T = json.load(open(D / "truth.json"))
g.key.setPlainText(" ".join(T["key"][str(q)] for q in range(1, 51)))
nomor_list = [v["nomor"] for v in T["truths"].values()]
g.students.setPlainText("\n".join(f"{n}, Siswa {i+1}" for i, n in enumerate(nomor_list[:8])))
g.folder.setText(str(D / "scans"))
w.tabs.setCurrentWidget(g); qa.processEvents(); w.grab().save(str(OUT / "2_koreksi.png"))
g.start()
while g.worker.isRunning():
    qa.processEvents(); time.sleep(0.05)
qa.processEvents(); time.sleep(0.2); qa.processEvents()
print(g.log.text())
r = w.t_res
r.table.selectRow(0); qa.processEvents()
# pilih lembar yang punya tanda
for row in range(r.table.rowCount()):
    if r.table.item(row, 0).text() == "⚠":
        r.table.selectRow(row); break
qa.processEvents(); r.view.fit(); qa.processEvents()
w.grab().save(str(OUT / "3_hasil.png"))
# cek nilai vs kebenaran
key = {int(k): v for k, v in T["key"].items()}
bad = 0
for res in w.store.results:
    tr = T["truths"][Path(res["file"]).name]
    exp = omr.grade({int(k): v for k, v in tr["answers"].items()}, key)
    got = w.store.grade(res)
    bad += exp["nilai"] != got["nilai"]
print("lembar:", len(w.store.results), "nilai berbeda dari kebenaran:", bad)
A.export_excel(str(OUT / "rekap.xlsx"), w.store)
import openpyxl
wb = openpyxl.load_workbook(OUT / "rekap.xlsx"); print(wb.sheetnames, wb["Rekap"].max_row, wb["Rekap"]["C6"].value, wb["Rekap"]["H6"].value)
w.t_grade.save_settings(); w.store.save()
print("hasil json:", (D / "scans" / A.RESULT_FILE).exists())
