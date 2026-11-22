"""Uji akurasi pembacaan pada scan sintetis. Jalankan: python tests/test_accuracy.py"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from koreksi_ljk import omr

D = Path(__file__).parent / "data"
blank = omr.load_pages(D / "ljk_kosong.png")[0][1]
tpl = omr.Template(name="Sintetis", ref_path="")
tpl.set_ref(blank)
bub = omr.detect_bubbles(tpl.ref())
s = omr.REF_WIDTH / 210  # px per mm di gambar template
R = lambda x0, y0, x1, y1: [x0 * s, y0 * s, (x1 - x0) * s, (y1 - y0) * s]
print("bulatan terdeteksi:", len(bub))
for rect, start in [(R(36, 116, 80, 283), 1), (R(121, 116, 165, 283), 26)]:
    print(" grid tebakan:", omr.guess_grid(bub, rect))
    tpl.blocks.append(omr.fit_block(bub, rect, 25, 5, "soal", "rows", start=start))
rect = R(116, 36, 164, 99)
print(" grid nomor:", omr.guess_grid(bub, rect))
tpl.blocks.append(omr.fit_block(bub, rect, 10, 6, "nomor", "cols"))
T = json.load(open(D / "truth.json"))
errs = tot = 0; flagged_err = 0; nomor_ok = 0
for f in omr.list_sheets(D / "scans"):
    t0 = time.time()
    (label, img), = omr.load_pages(f)
    res, al = omr.read_sheet(img, tpl, str(f))
    tr = T["truths"][f.name]
    if res.error:
        print(f.name, "ERROR", res.error); errs += 50; continue
    bad = [(q, tr["answers"][str(q)], res.answers.get(q)) for q in range(1, 51) if tr["answers"][str(q)] != res.answers.get(q)]
    unflagged = [b for b in bad if b[0] not in res.flags]
    errs += len(bad); flagged_err += len(bad) - len(unflagged); tot += 50
    nomor_ok += res.nomor == tr["nomor"]
    print(f"{f.name}: {time.time()-t0:.2f}s salah={len(bad)} (tak ditandai {len(unflagged)}) "
          f"nomor {res.nomor}/{tr['nomor']} th={res.threshold:.2f} ecc={res.align_info.get('ecc')} rot={res.align_info.get('rotated')} "
          f"flags={len(res.flags)} {unflagged}")
print(f"TOTAL: {errs} salah dari {tot} jawaban; {flagged_err} di antaranya ditandai untuk dicek; nomor benar {nomor_ok}")
tpl.save(D / "template_sintetis")
