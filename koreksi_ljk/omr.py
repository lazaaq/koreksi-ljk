"""Inti pembacaan LJK (OMR) — tidak bergantung pada GUI.

Alur:
  1. Template dibuat dari satu scan LJK KOSONG: bulatan dideteksi otomatis, lalu
     pengguna menandai blok (soal / nomor peserta) sebagai persegi panjang.
  2. Setiap scan diselaraskan ke gambar template (ORB + RANSAC, diperhalus ECC),
     jadi LJK jenis apa pun bisa dipakai tanpa perlu penanda khusus.
  3. Tiap bulatan diukur kegelapannya relatif terhadap kertas di sekitarnya,
     dikurangi kegelapan bulatan yang sama di template kosong (huruf/garis cetak),
     lalu dibandingkan dengan ambang yang dihitung per lembar.
  4. Jawaban yang ragu (ganda, tipis, bekas hapusan) diberi tanda untuk dicek.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np

REF_WIDTH = 1700  # lebar kerja (px) — setara A4 ±200 dpi
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".gif"}
PDF_EXT = {".pdf"}
LETTERS = "ABCDEFGHIJ"
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"


# ----------------------------------------------------------------------------
# Membaca berkas
# ----------------------------------------------------------------------------
def list_sheets(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    files = [p for p in sorted(folder.iterdir(), key=lambda p: p.name.lower())
             if p.is_file() and p.suffix.lower() in IMAGE_EXT | PDF_EXT and not p.name.startswith(".")]
    return files


def load_pages(path: str | Path, dpi: int = 200) -> list[tuple[str, np.ndarray]]:
    """Mengembalikan [(label, gambar_abu2)]. PDF multi-halaman → satu entri per halaman."""
    path = Path(path)
    if path.suffix.lower() in PDF_EXT:
        import pymupdf
        out = []
        with pymupdf.open(str(path)) as doc:
            for i, page in enumerate(doc):
                pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
                img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, 0].copy()
                out.append((f"{path.name} hal. {i + 1}" if len(doc) > 1 else path.name, img))
        return out
    data = np.fromfile(str(path), dtype=np.uint8)  # aman untuk nama berkas non-ASCII di Windows
    img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if img is None:  # mis. GIF pada OpenCV lama → pakai MuPDF
        try:
            import pymupdf
            pix = pymupdf.Pixmap(str(path))
            if pix.n != 1:
                pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, 0].copy()
        except Exception:
            img = None
    if img is None:
        raise ValueError("Berkas gambar tidak bisa dibuka")
    return [(path.name, img)]


def normalize(gray: np.ndarray, width: int = REF_WIDTH) -> np.ndarray:
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if w == width:
        return gray
    return cv2.resize(gray, (width, round(h * width / w)), interpolation=cv2.INTER_AREA if w > width else cv2.INTER_CUBIC)


# ----------------------------------------------------------------------------
# Template
# ----------------------------------------------------------------------------
@dataclass
class Block:
    kind: str                 # "soal" | "nomor" | "nama" | "isian" (isian lain, mis. ruang/no HP — tidak dinilai)
    rect: list[float]         # x, y, w, h (koordinat gambar template)
    rows: int
    cols: int
    items_along: str          # "rows": tiap baris = 1 soal/digit; "cols": tiap kolom = 1 soal/digit
    start: int = 1            # nomor soal pertama (untuk kind="soal")
    labels: str = "ABCDE"     # label pilihan (soal) atau "0123456789" (nomor)
    centers: list = field(default_factory=list)   # [rows][cols] -> [x, y]
    radius: list[float] = field(default_factory=lambda: [10.0, 10.0])  # rx, ry
    title: str = ""           # nama isian (untuk kind="isian"), mis. "Ruang", "No HP"

    @property
    def n_items(self) -> int:
        return self.rows if self.items_along == "rows" else self.cols

    @property
    def n_choices(self) -> int:
        return self.cols if self.items_along == "rows" else self.rows

    def bubble(self, item: int, choice: int) -> tuple[float, float]:
        r, c = (item, choice) if self.items_along == "rows" else (choice, item)
        x, y = self.centers[r][c]
        return x, y

    def question_numbers(self) -> list[int]:
        return list(range(self.start, self.start + self.n_items)) if self.kind == "soal" else []


@dataclass
class Template:
    name: str
    ref_path: str
    blocks: list[Block] = field(default_factory=list)
    _ref: np.ndarray | None = field(default=None, repr=False, compare=False)
    _base: dict | None = field(default=None, repr=False, compare=False)

    # --- simpan / muat
    def save(self, folder: str | Path):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        ref = self.ref()
        cv2.imencode(".png", ref)[1].tofile(str(folder / "ref.png"))
        data = {"name": self.name, "version": 1, "blocks": [asdict(b) for b in self.blocks]}
        (folder / "template.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        self.ref_path = str(folder / "ref.png")

    @classmethod
    def load(cls, folder: str | Path) -> "Template":
        folder = Path(folder)
        data = json.loads((folder / "template.json").read_text(encoding="utf-8"))
        t = cls(name=data["name"], ref_path=str(folder / "ref.png"))
        t.blocks = [Block(**b) for b in data["blocks"]]
        return t

    def ref(self) -> np.ndarray:
        if self._ref is None:
            self._ref = normalize(cv2.imdecode(np.fromfile(self.ref_path, np.uint8), cv2.IMREAD_GRAYSCALE))
        return self._ref

    def set_ref(self, gray: np.ndarray):
        self._ref = normalize(gray)
        self._base = None

    # --- informasi
    def question_numbers(self) -> list[int]:
        qs = []
        for b in self.blocks:
            qs += b.question_numbers()
        return sorted(qs)

    def labels_for(self, q: int) -> str:
        for b in self.blocks:
            if b.kind == "soal" and b.start <= q < b.start + b.n_items:
                return b.labels
        return "ABCDE"

    def next_start(self) -> int:
        qs = self.question_numbers()
        return (max(qs) + 1) if qs else 1

    def baseline(self) -> dict:
        """Kegelapan tiap bulatan pada template kosong (garis & huruf cetak)."""
        if self._base is None:
            meas = Measurer(self.ref())
            self._base = {}
            for bi, b in enumerate(self.blocks):
                for r in range(b.rows):
                    for c in range(b.cols):
                        x, y = b.centers[r][c]
                        self._base[(bi, r, c)] = meas.darkness(x, y, b.radius)
        return self._base


# ----------------------------------------------------------------------------
# Deteksi bulatan pada template kosong
# ----------------------------------------------------------------------------
def detect_bubbles(gray: np.ndarray) -> list[tuple[float, float, float, float]]:
    """Cari bentuk bulat/oval/kotak kecil berongga. Hasil: [(cx, cy, w, h)]."""
    g = normalize(gray)
    W = g.shape[1]
    th = cv2.adaptiveThreshold(cv2.GaussianBlur(g, (3, 3), 0), 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, 31, 12)
    contours, _ = cv2.findContours(th, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    smin, smax = W * 0.006, W * 0.045
    cands = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if not (smin <= w <= smax and smin <= h <= smax):
            continue
        ar = w / h
        if not (0.45 <= ar <= 2.4):
            continue
        hull = cv2.convexHull(cnt)
        ha = cv2.contourArea(hull)
        if ha < 0.55 * w * h:  # bukan bentuk cembung penuh (huruf, angka)
            continue
        per = cv2.arcLength(hull, True)
        circ = 4 * math.pi * ha / (per * per + 1e-6)
        if circ < 0.6:
            continue
        cands.append((x + w / 2, y + h / 2, float(w), float(h)))
    # gabungkan kontur dalam/luar dari bulatan yang sama → ambil yang terbesar
    cands.sort(key=lambda c: -c[2] * c[3])
    out = []
    for c in cands:
        if all(abs(c[0] - o[0]) > o[2] * 0.4 or abs(c[1] - o[1]) > o[3] * 0.4 for o in out):
            out.append(c)
    return out


def _split_1d(vals: list[float], k: int) -> list[float] | None:
    """Kelompokkan nilai 1D menjadi k kelompok dengan memotong di k-1 celah terbesar."""
    if len(vals) < k or k < 1:
        return None
    v = sorted(vals)
    if k == 1:
        return [float(np.median(v))]
    gaps = sorted(range(len(v) - 1), key=lambda i: v[i + 1] - v[i], reverse=True)[:k - 1]
    cuts = sorted(gaps)
    groups, s = [], 0
    for c in cuts:
        groups.append(v[s:c + 1]); s = c + 1
    groups.append(v[s:])
    means = [float(np.median(g)) for g in groups]
    # cek jarak antar kelompok cukup seragam (grid)
    d = np.diff(means)
    if len(d) and (d.min() <= 0 or d.max() / max(d.min(), 1e-6) > 2.2):
        return None
    return means


def fit_block(bubbles, rect, rows: int, cols: int, kind: str, items_along: str,
              start: int = 1, labels: str | None = None, title: str = "") -> Block:
    x0, y0, w, h = rect
    inside = [b for b in bubbles if x0 <= b[0] <= x0 + w and y0 <= b[1] <= y0 + h]
    xs = ys = None
    if len(inside) >= max(2, 0.5 * rows * cols):
        xs = _split_1d([b[0] for b in inside], cols)
        ys = _split_1d([b[1] for b in inside], rows)
    if inside:
        rx = float(np.median([b[2] for b in inside])) / 2
        ry = float(np.median([b[3] for b in inside])) / 2
    else:
        rx = ry = min(w / cols, h / rows) * 0.32
    if xs is None:
        xs = [x0 + (j + 0.5) * w / cols for j in range(cols)]
    if ys is None:
        ys = [y0 + (i + 0.5) * h / rows for i in range(rows)]
    if labels is None:
        n_ch = cols if items_along == "rows" else rows
        labels = DIGITS[:n_ch] if kind in ("nomor", "isian") else (ALPHABET[:n_ch] if kind == "nama" else LETTERS[:n_ch])
    centers = [[[xs[j], ys[i]] for j in range(cols)] for i in range(rows)]
    return Block(kind=kind, rect=[float(v) for v in rect], rows=rows, cols=cols, items_along=items_along,
                 start=start, labels=labels, centers=centers, radius=[rx, ry], title=title)


def guess_grid(bubbles, rect) -> tuple[int, int]:
    """Tebak jumlah baris & kolom bulatan di dalam rect (untuk mengisi otomatis form)."""
    x0, y0, w, h = rect
    inside = [b for b in bubbles if x0 <= b[0] <= x0 + w and y0 <= b[1] <= y0 + h]
    if not inside:
        return 0, 0
    size = float(np.median([max(b[2], b[3]) for b in inside]))

    def count(vals):
        v = sorted(vals); n = 1
        for a, b in zip(v, v[1:]):
            if b - a > size * 0.5:
                n += 1
        return n
    return count([b[1] for b in inside]), count([b[0] for b in inside])


# ----------------------------------------------------------------------------
# Penyelarasan scan → template
# ----------------------------------------------------------------------------
class AlignError(Exception):
    pass


def _orb_affine(src: np.ndarray, dst: np.ndarray):
    orb = cv2.ORB_create(nfeatures=4000, scaleFactor=1.2, nlevels=8, fastThreshold=10)
    k1, d1 = orb.detectAndCompute(src, None)
    k2, d2 = orb.detectAndCompute(dst, None)
    if d1 is None or d2 is None or len(k1) < 10 or len(k2) < 10:
        return None, 0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    good = []
    for m in bf.knnMatch(d1, d2, k=2):
        if len(m) == 2 and m[0].distance < 0.78 * m[1].distance:
            good.append(m[0])
    if len(good) < 8:
        return None, 0
    p1 = np.float32([k1[m.queryIdx].pt for m in good])
    p2 = np.float32([k2[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(p1, p2, method=cv2.RANSAC, ransacReprojThreshold=4.0,
                                         maxIters=4000, confidence=0.995)
    if M is None:
        return None, 0
    return M, int(inl.sum())


def align(scan: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, dict]:
    """Selaraskan scan ke template. Mengembalikan (gambar_terselaraskan, info)."""
    scan = normalize(scan, ref.shape[1])
    s = 900 / ref.shape[1]
    ref_s = cv2.resize(ref, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    best = None
    for rot in (0, 180):
        img = scan if rot == 0 else cv2.rotate(scan, cv2.ROTATE_180)
        img_s = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        M, n = _orb_affine(img_s, ref_s)
        if M is not None and (best is None or n > best[2]):
            best = (img, M, n, rot)
        if best and best[2] > 150:
            break
    if best is None or best[2] < 15:
        raise AlignError("Lembar tidak cocok dengan template (pola cetak tidak dikenali). "
                         "Pastikan template yang dipilih benar dan scan tidak terpotong.")
    img, M, n_inl, rot = best
    M = M.copy(); M[:, 2] /= s  # skala balik ke resolusi penuh
    # perhalus dengan ECC (affine penuh) pada resolusi menengah
    corr = None
    try:
        m = 700 / ref.shape[1]
        a = cv2.GaussianBlur(cv2.resize(ref, None, fx=m, fy=m, interpolation=cv2.INTER_AREA), (5, 5), 0)
        b = cv2.GaussianBlur(cv2.resize(img, None, fx=m, fy=m, interpolation=cv2.INTER_AREA), (5, 5), 0)
        W = M.astype(np.float32).copy(); W[:, 2] *= m
        crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-4)
        corr, W = cv2.findTransformECC(a.astype(np.float32), b.astype(np.float32),
                                       cv2.invertAffineTransform(W).astype(np.float32),
                                       cv2.MOTION_AFFINE, crit, None, 5)
        W = cv2.invertAffineTransform(W); W[:, 2] /= m
        M = W
    except cv2.error:
        pass
    aligned = cv2.warpAffine(img, M, (ref.shape[1], ref.shape[0]), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=255)
    return aligned, {"inliers": n_inl, "ecc": None if corr is None else float(corr), "rotated": rot}


# ----------------------------------------------------------------------------
# Pengukuran & pembacaan
# ----------------------------------------------------------------------------
class Measurer:
    def __init__(self, gray: np.ndarray):
        self.g = gray
        # kecerahan kertas lokal (menghapus tanda gelap kecil)
        k = max(15, (gray.shape[1] // 60) | 1)
        paper = cv2.dilate(gray, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
        self.paper = cv2.GaussianBlur(paper, (0, 0), k / 2).astype(np.float32)

    def darkness(self, x: float, y: float, radius) -> float:
        rx, ry = radius
        rx, ry = max(2.0, rx * 0.62), max(2.0, ry * 0.62)
        x0, x1 = int(x - rx), int(math.ceil(x + rx)) + 1
        y0, y1 = int(y - ry), int(math.ceil(y + ry)) + 1
        H, W = self.g.shape
        if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
            return 0.0
        patch = self.g[y0:y1, x0:x1].astype(np.float32)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        mask = ((xx - x) / rx) ** 2 + ((yy - y) / ry) ** 2 <= 1
        if not mask.any():
            return 0.0
        inner = float(patch[mask].mean())
        bg = float(self.paper[int(y), int(x)])
        return max(0.0, 1.0 - inner / max(bg, 1.0))


def _otsu(vals: np.ndarray) -> float:
    v = np.clip(np.asarray(vals, np.float32), 0, 1)
    hist, edges = np.histogram(v, bins=100, range=(0, 1))
    p = hist / max(hist.sum(), 1)
    omega = np.cumsum(p); mu = np.cumsum(p * (edges[:-1] + 0.005)); mu_t = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        sb = (mu_t * omega - mu) ** 2 / (omega * (1 - omega))
    sb = np.nan_to_num(sb)
    return float(edges[int(np.argmax(sb)) + 1])


@dataclass
class SheetResult:
    file: str
    label: str
    page: int = 0
    nomor: str = ""
    nama_lembar: str = ""                         # nama dari bulatan huruf (bila ada blok nama)
    fields: dict = field(default_factory=dict)    # isian lain {judul: nilai}, mis. {"Ruang": "01"}
    answers: dict = field(default_factory=dict)   # {nomor_soal: "A" | "" (kosong) | "*" (ganda)}
    flags: dict = field(default_factory=dict)     # {nomor_soal: alasan}
    nomor_flag: str = ""
    error: str = ""
    threshold: float = 0.0
    align_info: dict = field(default_factory=dict)
    marks: list = field(default_factory=list)     # untuk anotasi: (x, y, rx, ry, kind, item, label, fill)

    @property
    def needs_review(self) -> bool:
        return bool(self.error or self.flags or self.nomor_flag)

    def to_json(self) -> dict:
        d = asdict(self)
        d["answers"] = {str(k): v for k, v in self.answers.items()}
        d["flags"] = {str(k): v for k, v in self.flags.items()}
        d.pop("marks", None)
        return d

    @classmethod
    def from_json(cls, d: dict) -> "SheetResult":
        d = dict(d)
        d["answers"] = {int(k): v for k, v in d.get("answers", {}).items()}
        d["flags"] = {int(k): v for k, v in d.get("flags", {}).items()}
        d.pop("marks", None)
        return cls(**d)


def read_aligned(aligned: np.ndarray, tpl: Template, file: str = "", label: str = "") -> SheetResult:
    meas = Measurer(aligned)
    base = tpl.baseline()
    fills = {}
    for bi, b in enumerate(tpl.blocks):
        for r in range(b.rows):
            for c in range(b.cols):
                x, y = b.centers[r][c]
                fills[(bi, r, c)] = max(0.0, meas.darkness(x, y, b.radius) - base[(bi, r, c)])
    allv = np.array(list(fills.values()) or [0.0])
    th = min(max(_otsu(allv), 0.16), 0.42)
    # bila hampir tak ada isian, otsu tidak bermakna → pakai ambang tetap
    if (allv > 0.16).sum() < 3:
        th = 0.25
    res = SheetResult(file=file, label=label or Path(file).name, threshold=th)
    digits = []; letters = []
    for bi, b in enumerate(tpl.blocks):
        for it in range(b.n_items):
            vals = []
            for ch in range(b.n_choices):
                r, c = (it, ch) if b.items_along == "rows" else (ch, it)
                vals.append(fills[(bi, r, c)])
            order = sorted(range(len(vals)), key=lambda i: -vals[i])
            s1 = vals[order[0]]; s2 = vals[order[1]] if len(vals) > 1 else 0.0
            if s1 < th:
                if s1 >= 0.10 and s1 > 2.2 * max(s2, 0.03):
                    # tanda tipis/setengah tapi jelas paling menonjol → ambil, tandai untuk dicek
                    val, flag = b.labels[order[0]], "tipis/ragu"
                else:
                    val, flag = "", ("tipis/ragu" if s1 > th * 0.7 else "")
            elif s2 >= th and s2 > 0.55 * s1:
                val, flag = "*", "ganda"
            else:
                val = b.labels[order[0]]
                flag = ""
                if s1 < th * 1.25:
                    flag = "tipis/ragu"
                elif s2 > max(th * 0.65, 0.5 * s1):
                    flag = "ada bekas hapusan?"
            for ch in range(b.n_choices):
                r, c = (it, ch) if b.items_along == "rows" else (ch, it)
                x, y = b.centers[r][c]
                res.marks.append((x, y, b.radius[0], b.radius[1], b.kind, it + (b.start if b.kind == "soal" else 0),
                                  b.labels[ch], vals[ch]))
            if b.kind == "soal":
                q = b.start + it
                res.answers[q] = val
                if flag:
                    res.flags[q] = flag
            elif b.kind == "nama":
                letters.append(val if val not in ("", "*") else " ")
            elif b.kind == "isian":
                key_ = b.title or f"Isian {bi + 1}"
                res.fields[key_] = res.fields.get(key_, "") + (val if val not in ("", "*") else ("?" if val == "*" else "_"))
            else:
                digits.append(val if val not in ("", "*") else ("?" if val == "*" else "_"))
                if flag and not res.nomor_flag:
                    res.nomor_flag = "nomor peserta " + flag
    res.nama_lembar = " ".join("".join(letters).split())
    res.fields = {k: v.strip("_") for k, v in res.fields.items()}
    res.nomor = "".join(digits).strip("_")  # kolom kosong di depan/belakang = nomor lebih pendek
    if not res.nomor:
        res.nomor = ""  # nomor tidak diisi sama sekali
        res.nomor_flag = "" if (res.nama_lembar or not digits) else "nomor peserta tidak diisi"
    elif "_" in res.nomor or "?" in res.nomor:  # kosong di tengah atau ganda
        res.nomor_flag = res.nomor_flag or "nomor peserta tidak terbaca lengkap"
    return res


def read_sheet(gray: np.ndarray, tpl: Template, file: str = "", label: str = "") -> tuple[SheetResult, np.ndarray | None]:
    try:
        aligned, info = align(gray, tpl.ref())
    except AlignError as e:
        return SheetResult(file=file, label=label or Path(file).name, error=str(e)), None
    res = read_aligned(aligned, tpl, file, label)
    res.align_info = info
    if info.get("ecc") is not None and info["ecc"] < 0.55:
        res.flags[0] = "penyelarasan kurang yakin"
    return res, aligned


def build_blank(images: list[np.ndarray], progress=None) -> np.ndarray:
    """Buat gambar "LJK kosong" dari beberapa scan TERISI.

    Semua scan diselaraskan ke scan pertama, lalu tiap piksel diambil nilai
    terangnya (persentil 97). Isian pensil berbeda-beda antar siswa sehingga
    hilang, sedangkan cetakan yang sama di semua lembar tetap ada.
    """
    if len(images) < 5:
        raise ValueError("Butuh minimal 5 scan terisi untuk membuat LJK kosong.")
    ref = normalize(images[0])
    stack = [ref]
    for i, im in enumerate(images[1:], 1):
        try:
            stack.append(align(im, ref)[0])
        except AlignError:
            pass
        if progress:
            progress(i, len(images) - 1)
    return np.percentile(np.stack(stack), 97, axis=0).astype(np.uint8)


# ----------------------------------------------------------------------------
# Kunci & penilaian
# ----------------------------------------------------------------------------
def parse_key(text: str, questions: list[int] | None = None) -> dict[int, str]:
    """Terima "ABCDE..." atau "1. A  2) B ..." atau satu per baris."""
    import re
    t = text.upper()
    pairs = re.findall(r"(\d+)\s*[.):\-=]?\s*([A-J])\b", t)
    if pairs and len(pairs) >= len(re.findall(r"[A-J]", re.sub(r"\d+\s*[.):\-=]?\s*[A-J]\b", "", t))):
        return {int(n): a for n, a in pairs}
    letters = re.findall(r"[A-J]", re.sub(r"\d+", " ", t))
    qs = questions or list(range(1, len(letters) + 1))
    return {q: a for q, a in zip(qs, letters)}


def grade(answers: dict[int, str], key: dict[int, str], pts=(1.0, 0.0, 0.0)) -> dict:
    pb, ps, pk = pts
    b = s = k = 0
    for q, kv in key.items():
        a = answers.get(q, "")
        if not a:
            k += 1
        elif a == kv:
            b += 1
        else:
            s += 1
    n = len(key)
    skor = b * pb + s * ps + k * pk
    nilai = round(skor / (n * pb) * 100, 2) if n and pb else 0.0
    return {"benar": b, "salah": s, "kosong": k, "skor": skor, "nilai": nilai}


# ----------------------------------------------------------------------------
# Anotasi
# ----------------------------------------------------------------------------
def annotate(aligned: np.ndarray, res: SheetResult, key: dict[int, str]) -> np.ndarray:
    img = cv2.cvtColor(aligned, cv2.COLOR_GRAY2BGR)
    GREEN, RED, BLUE, ORANGE, PURPLE = (74, 163, 22), (38, 38, 220), (235, 99, 37), (6, 119, 217), (234, 51, 147)  # BGR
    for (x, y, rx, ry, kind, item, lab, fill) in res.marks:
        c = (int(round(x)), int(round(y))); ax = (int(rx * 1.35), int(ry * 1.35))
        if kind in ("nomor", "nama", "isian"):
            if fill >= res.threshold:
                cv2.ellipse(img, c, ax, 0, 0, 360, PURPLE, 3)
            continue
        a = res.answers.get(item, ""); kv = key.get(item)
        chosen = (a == lab) or (a == "*" and fill >= res.threshold)
        if chosen:
            col = ORANGE if a == "*" else (GREEN if a == kv else RED)
            cv2.ellipse(img, c, ax, 0, 0, 360, col, 3)
        elif kv == lab and a != kv:
            cv2.ellipse(img, c, ax, 0, 0, 360, BLUE if a else ORANGE, 2)
        if lab == res_first_label(res, item) and item in res.flags:
            cv2.putText(img, "?", (int(x - rx * 3.2), int(y + ry)), cv2.FONT_HERSHEY_SIMPLEX, ry / 9, ORANGE, 2)
    return img


def res_first_label(res: SheetResult, item: int) -> str:
    for m in res.marks:
        if m[4] == "soal" and m[5] == item:
            return m[6]
    return ""

