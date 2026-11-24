"""Uji berat: pensil tipis, isian setengah, miring hingga 4°, scan 150 dpi."""
import sys, random
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.path.insert(0, str(Path(__file__).parent))
import make_synthetic as M
from koreksi_ljk import omr
tpl = omr.Template.load(Path(__file__).parent / "data" / "template_sintetis")
tot = bad = unfl = flags = 0
for seed in range(100, 120):
    rng = random.Random(seed); np.random.seed(seed); img = M.blank(); truth = {}
    for q in range(1, 51):
        k = rng.randint(0, 4); s = rng.uniform(0.22, 0.5)
        if rng.random() < 0.2:
            x, y = M.q_center(q, k); M.fill(img, x - 1, y, s, rx=1.8, ry=2.0, rng=rng)
        else:
            M.fill(img, *M.q_center(q, k), s, rng=rng)
        truth[q] = "ABCDE"[k]
    h, w = img.shape; Mx = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-4, 4), 1.0)
    sc = cv2.resize(cv2.warpAffine(img, Mx, (w, h), borderValue=240), None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    sc = np.clip(sc * 0.8 + np.random.normal(0, 7, sc.shape), 0, 255).astype(np.uint8)
    res, _ = omr.read_sheet(sc, tpl)
    b = [q for q in truth if res.answers.get(q) != truth[q]]
    tot += 50; bad += len(b); unfl += len([q for q in b if q not in res.flags]); flags += len(res.flags)
print(f"salah baca {bad}/{tot}, yang lolos tanpa tanda {unfl}, rata-rata tanda per lembar {flags/20:.1f}")
