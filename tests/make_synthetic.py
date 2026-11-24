"""Membuat LJK sintetis (format berbeda dari aplikasi web) + scan palsu untuk pengujian.

Format: oval berlabel huruf, 50 soal (2 kolom x 25), nomor peserta 6 digit, TANPA penanda sudut.
"""
import json, random, sys
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

DPI = 300
MM = DPI / 25.4
W, H = int(210 * MM), int(297 * MM)
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/data")


def font(sz):
    for f in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
              "C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc"]:
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def q_center(q, k):  # q: 1..50, k: 0..4 (mm)
    col, row = divmod(q - 1, 25)
    return 40 + col * 85 + k * 9, 120 + row * 6.6


def id_center(d, v):
    return 120 + d * 8, 40 + v * 6.2


def blank():
    im = Image.new("L", (W, H), 255)
    dr = ImageDraw.Draw(im)
    f1, f2, f3 = font(int(5 * MM)), font(int(3 * MM)), font(int(2 * MM))
    dr.text((20 * MM, 14 * MM), "BIMBEL CERDAS — LEMBAR JAWABAN TRY OUT", fill=0, font=f1)
    dr.rectangle([20 * MM, 28 * MM, 105 * MM, 100 * MM], outline=0, width=4)
    for i, t in enumerate(["Nama", "Kelas", "Sekolah", "Tanggal", "Tanda tangan"]):
        dr.text((24 * MM, (34 + i * 12) * MM), t + " :", fill=0, font=f2)
        dr.line([50 * MM, (38 + i * 12) * MM, 100 * MM, (38 + i * 12) * MM], fill=0, width=2)
    dr.text((115 * MM, 30 * MM), "NOMOR PESERTA", fill=0, font=f2)
    dr.rectangle([114 * MM, 34 * MM, 166 * MM, 100 * MM], outline=0, width=3)
    for d in range(6):
        for v in range(10):
            x, y = id_center(d, v)
            dr.ellipse([(x - 2.6) * MM, (y - 2.1) * MM, (x + 2.6) * MM, (y + 2.1) * MM], outline=60, width=3)
            dr.text((x * MM, y * MM), str(v), fill=120, font=f3, anchor="mm")
    dr.rectangle([170 * MM, 30 * MM, 195 * MM, 60 * MM], outline=0, width=3)
    dr.text((172 * MM, 62 * MM), "LOGO", fill=0, font=f2)
    for q in range(1, 51):
        x, y = q_center(q, 0)
        dr.text(((x - 7) * MM, y * MM), str(q), fill=0, font=f2, anchor="rm")
        for k in range(5):
            x, y = q_center(q, k)
            dr.ellipse([(x - 3.0) * MM, (y - 2.2) * MM, (x + 3.0) * MM, (y + 2.2) * MM], outline=60, width=3)
            dr.text((x * MM, y * MM), "ABCDE"[k], fill=120, font=f3, anchor="mm")
    dr.text((20 * MM, 290 * MM), "Gunakan pensil 2B. Jangan dilipat.", fill=0, font=f2)
    return np.array(im)


def fill(img, x, y, strength, rx=3.0, ry=2.2, rng=random):
    m = np.zeros_like(img)
    cx, cy = int((x + rng.uniform(-0.4, 0.4)) * MM), int((y + rng.uniform(-0.3, 0.3)) * MM)
    cv2.ellipse(m, (cx, cy), (int(rx * MM * rng.uniform(0.8, 1.0)), int(ry * MM * rng.uniform(0.8, 1.0))), 0, 0, 360, 255, -1)
    val = int(255 * (1 - strength))
    noise = np.random.randint(-30, 30, img.shape)
    img[m > 0] = np.clip(np.minimum(img[m > 0], val + noise[m > 0]), 0, 255)


def student(seed):
    rng = random.Random(seed); np.random.seed(seed)
    img = blank()
    truth = {}
    for q in range(1, 51):
        t = rng.random()
        if t < 0.06:
            truth[q] = ""; continue
        k = rng.randint(0, 4)
        fill(img, *q_center(q, k), rng.uniform(0.45, 0.85), rng=rng)
        if t > 0.97:
            k2 = (k + 2) % 5; fill(img, *q_center(q, k2), 0.7, rng=rng); truth[q] = "*"
        else:
            truth[q] = "ABCDE"[k]
        if rng.random() < 0.05:
            fill(img, *q_center(q, rng.choice([j for j in range(5) if j != k])), 0.12, rng=rng)
    nomor = "".join(str(rng.randint(0, 9)) for _ in range(6))
    for d, v in enumerate(nomor):
        fill(img, *id_center(d, int(v)), 0.75, rx=2.6, ry=2.1, rng=rng)
    return img, truth, nomor


def scan(img, seed, rot180=False, dpi_scale=1.0):
    rng = random.Random(seed + 999)
    h, w = img.shape
    ang = rng.uniform(-2.0, 2.0)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
    M[:, 2] += [rng.uniform(-40, 40), rng.uniform(-40, 40)]
    out = cv2.warpAffine(img, M, (w, h), borderValue=245)
    out = cv2.GaussianBlur(out, (3, 3), 0)
    out = np.clip(out.astype(np.float32) * rng.uniform(0.85, 1.0) + np.random.normal(0, 5, out.shape), 0, 255).astype(np.uint8)
    if dpi_scale != 1.0:
        out = cv2.resize(out, None, fx=dpi_scale, fy=dpi_scale, interpolation=cv2.INTER_AREA)
    if rot180:
        out = cv2.rotate(out, cv2.ROTATE_180)
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scans").mkdir(exist_ok=True)
    cv2.imwrite(str(OUT / "ljk_kosong.png"), blank())
    truths = {}
    for i in range(1, 13):
        img, truth, nomor = student(i)
        s = scan(img, i, rot180=(i == 5), dpi_scale=(0.67 if i % 3 == 0 else 1.0))
        name = f"siswa_{i:02d}.jpg"
        cv2.imwrite(str(OUT / "scans" / name), s, [cv2.IMWRITE_JPEG_QUALITY, 85])
        truths[name] = {"answers": truth, "nomor": nomor}
    # kunci = lembar 'siswa' sempurna
    rng = random.Random(77)
    key = {q: "ABCDE"[rng.randint(0, 4)] for q in range(1, 51)}
    json.dump({"truths": truths, "key": key}, open(OUT / "truth.json", "w"), indent=1)
    print("ok", OUT)
