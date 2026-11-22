"""Tampilan aplikasi Koreksi LJK (PySide6) — Windows & macOS."""
from __future__ import annotations

import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF, QThread, Signal, QSettings, QStandardPaths
from PySide6.QtGui import QImage, QPixmap, QPen, QColor, QBrush, QPainter, QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QLineEdit, QPlainTextEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QFileDialog, QMessageBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsEllipseItem, QGraphicsPixmapItem, QGraphicsSimpleTextItem, QDialog, QDialogButtonBox,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QSplitter, QGroupBox,
    QAbstractItemView, QSizePolicy,
)

from . import omr
from . import __version__

APP_NAME = "Koreksi LJK"
RESULT_FILE = "hasil_koreksi_ljk.json"


def data_dir() -> Path:
    d = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    d.mkdir(parents=True, exist_ok=True)
    return d


def templates_dir() -> Path:
    d = data_dir() / "templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def to_pixmap(img: np.ndarray) -> QPixmap:
    if img.ndim == 2:
        h, w = img.shape
        q = QImage(img.data, w, h, w, QImage.Format_Grayscale8)
    else:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb.shape
        q = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
    return QPixmap.fromImage(q.copy())


def safe_name(s: str) -> str:
    keep = "".join(c if c.isalnum() or c in " -_" else "_" for c in s).strip()
    return keep or "template"


# =============================================================================
# Penampil gambar (zoom dengan roda mouse, geser dengan scrollbar / tarik kanan)
# =============================================================================
class ImageView(QGraphicsView):
    rectDrawn = Signal(QRectF)

    def __init__(self, draw_enabled=False):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor("#2b2d31"))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.draw_enabled = draw_enabled
        self._origin = None
        self._band = None
        self._pan = None
        self.pix_item: QGraphicsPixmapItem | None = None

    def set_image(self, img: np.ndarray | None, keep_view=False):
        tr = self.transform() if keep_view else None
        h0 = self.horizontalScrollBar().value(); v0 = self.verticalScrollBar().value()
        self.scene().clear(); self._band = None
        if img is None:
            self.pix_item = None
            return
        self.pix_item = self.scene().addPixmap(to_pixmap(img))
        self.scene().setSceneRect(QRectF(self.pix_item.pixmap().rect()))
        if keep_view and tr is not None:
            self.setTransform(tr); self.horizontalScrollBar().setValue(h0); self.verticalScrollBar().setValue(v0)
        else:
            self.fit()

    def fit(self):
        if self.pix_item:
            self.fitInView(self.pix_item, Qt.KeepAspectRatio)

    def wheelEvent(self, e):
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton or (e.button() == Qt.LeftButton and not self.draw_enabled):
            self._pan = e.position(); self.setCursor(Qt.ClosedHandCursor); return
        if e.button() == Qt.LeftButton and self.draw_enabled and self.pix_item:
            self._origin = self.mapToScene(e.position().toPoint())
            self._band = QGraphicsRectItem()
            self._band.setPen(QPen(QColor("#e8590c"), 2, Qt.DashLine)); self._band.pen().setCosmetic(True)
            pen = QPen(QColor("#e8590c"), 2, Qt.DashLine); pen.setCosmetic(True); self._band.setPen(pen)
            self._band.setBrush(QColor(232, 89, 12, 40))
            self.scene().addItem(self._band)
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pan is not None:
            d = e.position() - self._pan; self._pan = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        if self._origin is not None and self._band is not None:
            p = self.mapToScene(e.position().toPoint())
            self._band.setRect(QRectF(self._origin, p).normalized())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan is not None:
            self._pan = None; self.setCursor(Qt.ArrowCursor); return
        if self._origin is not None and self._band is not None:
            r = self._band.rect()
            self.scene().removeItem(self._band); self._band = None; self._origin = None
            if r.width() > 10 and r.height() > 10:
                self.rectDrawn.emit(r)
            return
        super().mouseReleaseEvent(e)


# =============================================================================
# Dialog blok template
# =============================================================================
class BlockDialog(QDialog):
    def __init__(self, parent, rows, cols, next_start):
        super().__init__(parent)
        self.setWindowTitle("Atur blok")
        lay = QFormLayout(self)
        self.kind = QComboBox(); self.kind.addItems(["Jawaban soal", "Nomor peserta"])
        self.rows = QSpinBox(); self.rows.setRange(1, 200); self.rows.setValue(max(rows, 1))
        self.cols = QSpinBox(); self.cols.setRange(1, 200); self.cols.setValue(max(cols, 1))
        self.orient = QComboBox()
        self.orient.addItems(["Tiap BARIS = 1 soal (pilihan A–E ke samping)",
                              "Tiap KOLOM = 1 soal (pilihan A–E ke bawah)"])
        self.start = QSpinBox(); self.start.setRange(1, 999); self.start.setValue(next_start)
        self.labels = QLineEdit()
        self.info = QLabel(); self.info.setWordWrap(True); self.info.setStyleSheet("color:#555")
        lay.addRow("Jenis blok", self.kind)
        lay.addRow("Jumlah baris bulatan", self.rows)
        lay.addRow("Jumlah kolom bulatan", self.cols)
        lay.addRow("Susunan", self.orient)
        lay.addRow("Nomor soal pertama", self.start)
        lay.addRow("Label pilihan", self.labels)
        lay.addRow(self.info)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addRow(bb)
        for w in (self.kind, self.orient):
            w.currentIndexChanged.connect(self._update)
        for w in (self.rows, self.cols):
            w.valueChanged.connect(self._update)
        # tebakan susunan: lebih banyak baris daripada kolom → tiap baris = 1 soal
        self.orient.setCurrentIndex(0 if rows >= cols else 1)
        self._update()

    def _update(self):
        nomor = self.kind.currentIndex() == 1
        if nomor:
            self.orient.setItemText(0, "Tiap BARIS = 1 digit (angka 0–9 ke samping)")
            self.orient.setItemText(1, "Tiap KOLOM = 1 digit (angka 0–9 ke bawah)")
        else:
            self.orient.setItemText(0, "Tiap BARIS = 1 soal (pilihan A–E ke samping)")
            self.orient.setItemText(1, "Tiap KOLOM = 1 soal (pilihan A–E ke bawah)")
        self.start.setEnabled(not nomor)
        along_rows = self.orient.currentIndex() == 0
        n_ch = self.cols.value() if along_rows else self.rows.value()
        n_it = self.rows.value() if along_rows else self.cols.value()
        self.labels.setText(omr.DIGITS[:n_ch] if nomor else omr.LETTERS[:n_ch])
        if nomor:
            self.info.setText(f"{n_it} digit nomor peserta, tiap digit {n_ch} pilihan.")
        else:
            self.info.setText(f"Soal {self.start.value()}–{self.start.value() + n_it - 1}, "
                              f"masing-masing {n_ch} pilihan.")

    def values(self):
        return dict(kind="nomor" if self.kind.currentIndex() == 1 else "soal",
                    rows=self.rows.value(), cols=self.cols.value(),
                    items_along="rows" if self.orient.currentIndex() == 0 else "cols",
                    start=self.start.value(), labels=self.labels.text().strip())


# =============================================================================
# Tab 1: Template
# =============================================================================
class TemplateTab(QWidget):
    templatesChanged = Signal()
    COLORS = {"soal": QColor("#1c7ed6"), "nomor": QColor("#ae3ec9")}

    def __init__(self):
        super().__init__()
        self.tpl: omr.Template | None = None
        self.tpl_dir: Path | None = None
        self.bubbles = []
        self.dirty = False

        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Template LJK tersimpan</b>"))
        self.list = QListWidget(); self.list.currentItemChanged.connect(self._open_selected)
        left.addWidget(self.list, 1)
        b_new = QPushButton("＋ Template baru dari LJK kosong…"); b_new.clicked.connect(self.new_template)
        b_del = QPushButton("Hapus template"); b_del.clicked.connect(self.delete_template)
        left.addWidget(b_new); left.addWidget(b_del)
        help_ = QLabel(
            "<b>Cara membuat template</b><ol style='margin-left:-20px'>"
            "<li>Scan satu LJK <b>kosong</b> (tidak diisi).</li>"
            "<li>Klik tombol di atas dan pilih hasil scannya.</li>"
            "<li>Di gambar, <b>tarik kotak</b> mengelilingi satu kelompok bulatan soal "
            "(mis. soal 1–25), lalu isi jenis & nomor soal pertama.</li>"
            "<li>Ulangi untuk kelompok soal lain dan untuk <b>nomor peserta</b>.</li>"
            "<li>Periksa titik-titik biru tepat di tengah bulatan, lalu <b>Simpan</b>.</li></ol>"
            "Roda mouse = zoom, klik kanan + tarik = geser.")
        help_.setWordWrap(True); help_.setStyleSheet("background:#f1f3f5;padding:8px;border-radius:6px")
        left.addWidget(help_)
        lw = QWidget(); lw.setLayout(left); lw.setMaximumWidth(320)

        right = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("Nama:"))
        self.name = QLineEdit(); self.name.textChanged.connect(lambda: self._set_dirty())
        top.addWidget(self.name, 1)
        self.b_fit = QPushButton("Paskan layar"); top.addWidget(self.b_fit)
        self.b_save = QPushButton("💾 Simpan template"); self.b_save.clicked.connect(self.save)
        self.b_save.setStyleSheet("font-weight:bold")
        top.addWidget(self.b_save)
        right.addLayout(top)
        self.view = ImageView(draw_enabled=True)
        self.view.rectDrawn.connect(self.add_block)
        self.b_fit.clicked.connect(self.view.fit)
        right.addWidget(self.view, 1)
        bl = QHBoxLayout()
        self.blocks = QListWidget(); self.blocks.setMaximumHeight(110)
        bl.addWidget(self.blocks, 1)
        b_rm = QPushButton("Hapus blok terpilih"); b_rm.clicked.connect(self.remove_block)
        bl.addWidget(b_rm, 0, Qt.AlignTop)
        right.addLayout(bl)
        self.status = QLabel(); right.addWidget(self.status)
        rw = QWidget(); rw.setLayout(right)

        lay = QHBoxLayout(self); lay.addWidget(lw); lay.addWidget(rw, 1)
        self.reload_list()
        self._enable(False)

    # ---------- daftar
    def reload_list(self, select: str | None = None):
        self.list.blockSignals(True); self.list.clear()
        for d in sorted(templates_dir().iterdir()):
            if (d / "template.json").exists():
                try:
                    name = json.loads((d / "template.json").read_text(encoding="utf-8"))["name"]
                except Exception:
                    continue
                it = QListWidgetItem(name); it.setData(Qt.UserRole, str(d)); self.list.addItem(it)
                if select and str(d) == select:
                    self.list.setCurrentItem(it)
        self.list.blockSignals(False)

    def _enable(self, on):
        for w in (self.name, self.b_save, self.b_fit, self.blocks):
            w.setEnabled(on)

    def _set_dirty(self, v=True):
        self.dirty = v

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, APP_NAME, "Perubahan template belum disimpan. Buang perubahan?")
        return r == QMessageBox.Yes

    def _open_selected(self, cur, prev):
        if cur is None:
            return
        if not self._confirm_discard():
            self.list.blockSignals(True); self.list.setCurrentItem(prev); self.list.blockSignals(False); return
        d = Path(cur.data(Qt.UserRole))
        try:
            self.tpl = omr.Template.load(d)
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Template rusak: {e}"); return
        self.tpl_dir = d
        self.bubbles = omr.detect_bubbles(self.tpl.ref())
        self.name.blockSignals(True); self.name.setText(self.tpl.name); self.name.blockSignals(False)
        self._enable(True); self.redraw(fit=True); self._set_dirty(False)

    def new_template(self):
        if not self._confirm_discard():
            return
        fn, _ = QFileDialog.getOpenFileName(self, "Pilih scan LJK KOSONG", "",
                                            "Gambar/PDF (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.pdf)")
        if not fn:
            return
        try:
            img = omr.load_pages(fn)[0][1]
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Gagal membuka berkas: {e}"); return
        self.tpl = omr.Template(name=Path(fn).stem, ref_path="")
        self.tpl.set_ref(img)
        self.tpl_dir = None
        self.bubbles = omr.detect_bubbles(self.tpl.ref())
        self.name.blockSignals(True); self.name.setText(self.tpl.name); self.name.blockSignals(False)
        self.list.blockSignals(True); self.list.clearSelection(); self.list.setCurrentItem(None); self.list.blockSignals(False)
        self._enable(True); self.redraw(fit=True); self._set_dirty(True)
        self.status.setText(f"{len(self.bubbles)} bulatan terdeteksi. Sekarang tarik kotak di sekeliling tiap kelompok bulatan.")

    def delete_template(self):
        it = self.list.currentItem()
        if not it:
            return
        if QMessageBox.question(self, APP_NAME, f"Hapus template “{it.text()}”?") != QMessageBox.Yes:
            return
        shutil.rmtree(it.data(Qt.UserRole), ignore_errors=True)
        self.tpl = None; self.tpl_dir = None; self.dirty = False
        self.view.set_image(None); self.blocks.clear(); self._enable(False)
        self.reload_list(); self.templatesChanged.emit()

    # ---------- blok
    def add_block(self, r: QRectF):
        if not self.tpl:
            return
        rect = [r.x(), r.y(), r.width(), r.height()]
        rows, cols = omr.guess_grid(self.bubbles, rect)
        dlg = BlockDialog(self, rows, cols, self.tpl.next_start())
        if not rows:
            dlg.info.setText("Tidak ada bulatan terdeteksi di kotak ini — isi jumlah baris/kolom secara manual; "
                             "posisi akan dibagi rata di dalam kotak.")
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        b = omr.fit_block(self.bubbles, rect, v["rows"], v["cols"], v["kind"], v["items_along"], v["start"],
                          v["labels"] or None)
        if len(b.labels) != b.n_choices:
            QMessageBox.warning(self, APP_NAME, f"Jumlah label ({len(b.labels)}) harus sama dengan jumlah pilihan ({b.n_choices})."); return
        if b.kind == "soal":
            clash = set(b.question_numbers()) & set(self.tpl.question_numbers())
            if clash:
                QMessageBox.warning(self, APP_NAME, f"Nomor soal {min(clash)}–{max(clash)} sudah dipakai blok lain."); return
        self.tpl.blocks.append(b); self.tpl._base = None
        self._set_dirty(); self.redraw()

    def remove_block(self):
        i = self.blocks.currentRow()
        if self.tpl and 0 <= i < len(self.tpl.blocks):
            self.tpl.blocks.pop(i); self.tpl._base = None; self._set_dirty(); self.redraw()

    def redraw(self, fit=False):
        if not self.tpl:
            return
        self.view.set_image(self.tpl.ref(), keep_view=not fit)
        sc = self.view.scene()
        pen = QPen(QColor(120, 120, 120, 160), 1); pen.setCosmetic(True)
        for (x, y, w, h) in self.bubbles:
            sc.addEllipse(x - w / 2, y - h / 2, w, h, pen)
        self.blocks.clear()
        for b in self.tpl.blocks:
            col = self.COLORS[b.kind]
            p = QPen(col, 2); p.setCosmetic(True)
            fill = QColor(col); fill.setAlpha(28)
            sc.addRect(QRectF(*b.rect), p, QBrush(fill))
            dot = QBrush(col); rx, ry = b.radius
            for row in b.centers:
                for (x, y) in row:
                    e = sc.addEllipse(x - rx, y - ry, 2 * rx, 2 * ry, p)
                    sc.addEllipse(x - 2.5, y - 2.5, 5, 5, QPen(Qt.NoPen), dot)
            if b.kind == "soal":
                txt = f"Soal {b.start}–{b.start + b.n_items - 1}  ({b.n_choices} pilihan: {b.labels})"
            else:
                txt = f"Nomor peserta  ({b.n_items} digit)"
            t = sc.addSimpleText(txt.split("  ")[0]); t.setBrush(col)
            f = QFont(); f.setPointSize(16); f.setBold(True); t.setFont(f)
            t.setPos(b.rect[0], b.rect[1] - 28)
            self.blocks.addItem(txt)
        qs = self.tpl.question_numbers()
        has_id = any(b.kind == "nomor" for b in self.tpl.blocks)
        self.status.setText(f"{len(qs)} soal" + (f" (nomor {min(qs)}–{max(qs)})" if qs else "") +
                            (" · nomor peserta ✓" if has_id else " · belum ada blok nomor peserta (opsional)"))

    def save(self):
        if not self.tpl:
            return
        if not self.tpl.question_numbers():
            QMessageBox.warning(self, APP_NAME, "Tambahkan minimal satu blok jawaban soal."); return
        name = self.name.text().strip() or "Template"
        self.tpl.name = name
        d = self.tpl_dir or (templates_dir() / f"{safe_name(name)}_{int(time.time())}")
        self.tpl.save(d)
        self.tpl_dir = d; self._set_dirty(False)
        self.reload_list(select=str(d)); self.templatesChanged.emit()
        self.status.setText("Template tersimpan ✓  — lanjut ke tab “2. Koreksi”.")


# =============================================================================
# Pekerja latar untuk mengoreksi folder
# =============================================================================
class GradeWorker(QThread):
    progress = Signal(int, int, str)
    result = Signal(dict, bytes)
    done = Signal()

    def __init__(self, files, tpl: omr.Template, threads=4):
        super().__init__()
        self.files = files; self.tpl = tpl; self.threads = threads; self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        tpl = self.tpl
        tpl.ref(); tpl.baseline()  # hitung sekali sebelum paralel
        jobs = []
        for f in self.files:
            try:
                for i, (label, img) in enumerate(omr.load_pages(f)):
                    jobs.append((str(f), i, label, img))
            except Exception as e:
                r = omr.SheetResult(file=str(f), label=Path(f).name, error=f"Berkas tidak bisa dibuka: {e}")
                self.result.emit(r.to_json(), b"")
        total = len(jobs)

        def work(job):
            f, i, label, img = job
            if self._stop:
                return None
            res, aligned = omr.read_sheet(img, tpl, f, label)
            res.page = i
            thumb = b""
            if aligned is not None:
                thumb = cv2.imencode(".jpg", aligned, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
            return res, thumb, res.marks

        n = 0
        with ThreadPoolExecutor(max_workers=self.threads) as ex:
            for out in ex.map(work, jobs):
                n += 1
                if out is None:
                    continue
                res, thumb, marks = out
                d = res.to_json(); d["_marks"] = marks
                self.result.emit(d, thumb)
                self.progress.emit(n, total, res.label)
        self.done.emit()


# =============================================================================
# Tab 2: Koreksi
# =============================================================================
class GradeTab(QWidget):
    started = Signal()
    finished_ = Signal()

    def __init__(self, store: "ResultStore"):
        super().__init__()
        self.store = store
        self.settings = QSettings()
        self.worker = None

        g1 = QGroupBox("1. Template && kunci jawaban")
        f1 = QGridLayout(g1)
        self.tpl_combo = QComboBox(); self.tpl_combo.currentIndexChanged.connect(self._tpl_changed)
        f1.addWidget(QLabel("Template LJK"), 0, 0); f1.addWidget(self.tpl_combo, 0, 1, 1, 3)
        self.key = QPlainTextEdit()
        self.key.setPlaceholderText("Ketik kunci berurutan, contoh:\nABCDE ABCDE ...\natau per nomor:  1.A  2.C  3.E ...")
        self.key.textChanged.connect(self._key_changed)
        f = QFont("Menlo" if sys.platform == "darwin" else "Consolas"); f.setStyleHint(QFont.Monospace)
        self.key.setFont(f); self.key.setMaximumHeight(110)
        f1.addWidget(QLabel("Kunci jawaban"), 1, 0, Qt.AlignTop); f1.addWidget(self.key, 1, 1, 1, 3)
        self.key_info = QLabel(); f1.addWidget(self.key_info, 2, 1, 1, 2)
        b_keyscan = QPushButton("Baca kunci dari scan LJK…"); b_keyscan.clicked.connect(self.key_from_scan)
        f1.addWidget(b_keyscan, 2, 3)
        self.pb = QDoubleSpinBox(); self.ps = QDoubleSpinBox(); self.pk = QDoubleSpinBox()
        for w, v in ((self.pb, 1), (self.ps, 0), (self.pk, 0)):
            w.setRange(-100, 100); w.setDecimals(2); w.setSingleStep(0.25); w.setValue(v)
        pts = QHBoxLayout()
        for lab, w in (("Benar", self.pb), ("Salah", self.ps), ("Kosong", self.pk)):
            pts.addWidget(QLabel(lab)); pts.addWidget(w)
        pts.addStretch()
        f1.addWidget(QLabel("Poin"), 3, 0); f1.addLayout(pts, 3, 1, 1, 3)

        g2 = QGroupBox("2. Daftar siswa (opsional)")
        v2 = QVBoxLayout(g2)
        self.students = QPlainTextEdit()
        self.students.setPlaceholderText("Satu siswa per baris:  nomor peserta, nama\n000123, Andi Pratama")
        self.students.setMaximumHeight(90)
        v2.addWidget(self.students)
        b_imp = QPushButton("Impor dari Excel/CSV…"); b_imp.clicked.connect(self.import_students)
        v2.addWidget(b_imp, 0, Qt.AlignLeft)

        g3 = QGroupBox("3. Folder berisi scan LJK siswa")
        h3 = QHBoxLayout(g3)
        self.folder = QLineEdit(); self.folder.setPlaceholderText("Pilih folder…")
        b_f = QPushButton("Pilih folder…"); b_f.clicked.connect(self.pick_folder)
        h3.addWidget(self.folder, 1); h3.addWidget(b_f)

        self.b_go = QPushButton("▶  Mulai koreksi")
        self.b_go.setStyleSheet("font-size:16px;font-weight:bold;padding:10px")
        self.b_go.clicked.connect(self.start)
        self.prog = QProgressBar(); self.prog.setVisible(False)
        self.log = QLabel(); self.log.setWordWrap(True)

        lay = QVBoxLayout(self)
        for w in (g1, g2, g3):
            lay.addWidget(w)
        lay.addWidget(self.b_go); lay.addWidget(self.prog); lay.addWidget(self.log); lay.addStretch()

        # muat pengaturan terakhir
        self.key.setPlainText(self.settings.value("key", ""))
        self.students.setPlainText(self.settings.value("students", ""))
        self.folder.setText(self.settings.value("folder", ""))
        for w, k in ((self.pb, "pb"), (self.ps, "ps"), (self.pk, "pk")):
            v = self.settings.value(k)
            if v is not None:
                w.setValue(float(v))
        self.reload_templates()

    # ---------- template & kunci
    def reload_templates(self):
        cur = self.tpl_combo.currentData() or self.settings.value("template", "")
        self.tpl_combo.blockSignals(True); self.tpl_combo.clear()
        for d in sorted(templates_dir().iterdir()):
            if (d / "template.json").exists():
                try:
                    name = json.loads((d / "template.json").read_text(encoding="utf-8"))["name"]
                except Exception:
                    continue
                self.tpl_combo.addItem(name, str(d))
        i = self.tpl_combo.findData(cur)
        if i >= 0:
            self.tpl_combo.setCurrentIndex(i)
        self.tpl_combo.blockSignals(False)
        self._tpl_changed()

    def template(self) -> omr.Template | None:
        d = self.tpl_combo.currentData()
        if not d:
            return None
        try:
            return omr.Template.load(d)
        except Exception:
            return None

    def _tpl_changed(self):
        self._key_changed()

    def key_dict(self) -> dict[int, str]:
        tpl = self.template()
        qs = tpl.question_numbers() if tpl else None
        k = omr.parse_key(self.key.toPlainText(), qs)
        if qs:
            k = {q: a for q, a in k.items() if q in qs}
        return k

    def _key_changed(self):
        tpl = self.template()
        if not tpl:
            self.key_info.setText("<span style='color:#c92a2a'>Belum ada template. Buat dulu di tab “1. Template”.</span>")
            return
        qs = tpl.question_numbers(); k = self.key_dict()
        miss = [q for q in qs if q not in k]
        if not k:
            self.key_info.setText(f"Template ini punya {len(qs)} soal.")
        elif miss:
            self.key_info.setText(f"<span style='color:#c92a2a'>Kunci baru {len(k)} dari {len(qs)} soal "
                                  f"(belum ada: {', '.join(map(str, miss[:10]))}{'…' if len(miss) > 10 else ''}). "
                                  f"Soal tanpa kunci tidak dinilai.</span>")
        else:
            self.key_info.setText(f"<span style='color:#2b8a3e'>Kunci lengkap: {len(k)} soal ✓</span>")

    def key_from_scan(self):
        tpl = self.template()
        if not tpl:
            return
        fn, _ = QFileDialog.getOpenFileName(self, "Pilih scan LJK berisi KUNCI", "",
                                            "Gambar/PDF (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.pdf)")
        if not fn:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res, _ = omr.read_sheet(omr.load_pages(fn)[0][1], tpl, fn)
        finally:
            QApplication.restoreOverrideCursor()
        if res.error:
            QMessageBox.warning(self, APP_NAME, res.error); return
        lines = [f"{q}. {res.answers.get(q) or '?'}" for q in tpl.question_numbers()]
        self.key.setPlainText("   ".join(lines))
        bad = [q for q in tpl.question_numbers() if res.answers.get(q) in ("", "*", None)]
        if bad:
            QMessageBox.information(self, APP_NAME, f"Soal {', '.join(map(str, bad))} kosong/ganda di LJK kunci. "
                                    "Tanda “?” perlu diganti manual.")

    # ---------- siswa
    def import_students(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Pilih daftar siswa", "", "Excel/CSV (*.xlsx *.csv *.txt)")
        if not fn:
            return
        rows = []
        try:
            if fn.lower().endswith(".xlsx"):
                import openpyxl
                ws = openpyxl.load_workbook(fn, read_only=True, data_only=True).active
                for r in ws.iter_rows(values_only=True):
                    if r and r[0] is not None and len(r) > 1 and r[1]:
                        rows.append(f"{r[0]}, {r[1]}")
            else:
                for line in Path(fn).read_text(encoding="utf-8-sig", errors="replace").splitlines():
                    p = [x.strip() for x in line.replace(";", ",").split(",")]
                    if len(p) >= 2 and p[0]:
                        rows.append(f"{p[0]}, {p[1]}")
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Gagal membaca berkas: {e}"); return
        self.students.setPlainText("\n".join(rows))
        QMessageBox.information(self, APP_NAME, f"{len(rows)} baris diimpor. Kolom A = nomor peserta, kolom B = nama.")

    def student_map(self) -> dict[str, str]:
        m = {}
        for line in self.students.toPlainText().splitlines():
            p = line.replace(";", ",").replace("\t", ",").split(",", 1)
            if len(p) == 2 and p[0].strip():
                m[p[0].strip()] = p[1].strip()
        return m

    # ---------- jalankan
    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Pilih folder scan LJK", self.folder.text())
        if d:
            self.folder.setText(d)

    def save_settings(self):
        s = self.settings
        s.setValue("key", self.key.toPlainText()); s.setValue("students", self.students.toPlainText())
        s.setValue("folder", self.folder.text()); s.setValue("template", self.tpl_combo.currentData() or "")
        s.setValue("pb", self.pb.value()); s.setValue("ps", self.ps.value()); s.setValue("pk", self.pk.value())

    def start(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop(); self.b_go.setText("Menghentikan…"); return
        tpl = self.template()
        if not tpl:
            QMessageBox.warning(self, APP_NAME, "Pilih template LJK dulu."); return
        folder = Path(self.folder.text().strip())
        if not folder.is_dir():
            QMessageBox.warning(self, APP_NAME, "Pilih folder yang berisi scan LJK."); return
        files = omr.list_sheets(folder)
        if not files:
            QMessageBox.warning(self, APP_NAME, "Tidak ada gambar (jpg/png/tif/pdf) di folder itu."); return
        if not self.key_dict():
            if QMessageBox.question(self, APP_NAME, "Kunci jawaban masih kosong. Tetap baca LJK (nilai belum dihitung)?") != QMessageBox.Yes:
                return
        self.save_settings()
        # hasil sebelumnya di folder ini?
        prev = folder / RESULT_FILE
        only_new = False
        if prev.exists():
            box = QMessageBox(self); box.setWindowTitle(APP_NAME)
            box.setText("Folder ini sudah pernah dikoreksi.")
            b_new = box.addButton("Lanjutkan (hanya berkas baru)", QMessageBox.AcceptRole)
            b_all = box.addButton("Koreksi ulang semua", QMessageBox.DestructiveRole)
            box.addButton("Batal", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() not in (b_new, b_all):
                return
            only_new = box.clickedButton() is b_new
        self.store.begin(folder, tpl, self, keep_previous=only_new)
        if only_new:
            done = {r["file"] for r in self.store.results}
            files = [f for f in files if str(f) not in done]
            if not files:
                self.log.setText("Tidak ada berkas baru."); self.finished_.emit(); return
        self.worker = GradeWorker(files, tpl)
        self.worker.result.connect(self.store.add)
        self.worker.progress.connect(self._progress)
        self.worker.done.connect(self._done)
        self.prog.setVisible(True); self.prog.setValue(0); self.prog.setMaximum(len(files))
        self.b_go.setText("■  Hentikan"); self.t0 = time.time()
        self.started.emit()
        self.worker.start()

    def _progress(self, n, total, label):
        self.prog.setMaximum(total); self.prog.setValue(n)
        self.log.setText(f"Mengoreksi {n}/{total}: {label}")

    def _done(self):
        self.b_go.setText("▶  Mulai koreksi"); self.prog.setVisible(False)
        rs = self.store.results
        rv = sum(1 for r in rs if self.store.needs_review(r))
        self.log.setText(f"Selesai: {len(rs)} lembar dalam {time.time() - self.t0:.0f} detik. "
                         f"{rv} lembar perlu dicek. Lihat tab “3. Hasil”.")
        self.store.save()
        self.finished_.emit()


# =============================================================================
# Penyimpanan hasil (dipakai bersama tab Koreksi & Hasil)
# =============================================================================
class ResultStore(QWidget):
    changed = Signal()
    added = Signal(int)

    def __init__(self):
        super().__init__()
        self.folder: Path | None = None
        self.tpl: omr.Template | None = None
        self.grader: GradeTab | None = None
        self.results: list[dict] = []
        self.cache: dict[int, tuple[bytes, list]] = {}   # index → (png aligned, marks)

    def begin(self, folder: Path, tpl, grader, keep_previous=False):
        self.folder = folder; self.tpl = tpl; self.grader = grader
        self.cache = {}
        self.results = []
        if keep_previous:
            self.load_file(folder / RESULT_FILE)
        self.changed.emit()

    def load_file(self, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.results = data.get("results", [])
        except Exception:
            self.results = []

    def add(self, d: dict, png: bytes):
        marks = d.pop("_marks", [])
        d.setdefault("nama", "")
        if not d.get("nama") and self.grader:
            m = self.grader.student_map()
            d["nama"] = m.get(d.get("nomor", ""), "") or next(
                (v for k, v in m.items() if k.lstrip("0") == d.get("nomor", "").lstrip("0") and k.lstrip("0")), "")
        d["checked"] = False
        self.results.append(d)
        i = len(self.results) - 1
        if png:
            self.cache[i] = (png, marks)
        self.added.emit(i)

    def key(self):
        return self.grader.key_dict() if self.grader else {}

    def pts(self):
        g = self.grader
        return (g.pb.value(), g.ps.value(), g.pk.value()) if g else (1, 0, 0)

    def answers(self, r: dict) -> dict[int, str]:
        return {int(k): v for k, v in r.get("answers", {}).items()}

    def grade(self, r: dict) -> dict:
        return omr.grade(self.answers(r), self.key(), self.pts())

    def needs_review(self, r: dict) -> bool:
        if r.get("checked"):
            return False
        return bool(r.get("error") or r.get("flags") or r.get("nomor_flag"))

    def save(self):
        if not self.folder:
            return
        data = {"app": APP_NAME, "version": __version__, "template": self.tpl.name if self.tpl else "",
                "saved": time.strftime("%Y-%m-%d %H:%M"), "results": self.results}
        try:
            (self.folder / RESULT_FILE).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def aligned(self, i: int):
        """(gambar_terselaraskan, SheetResult) — dari cache atau dibaca ulang."""
        r = self.results[i]
        if r.get("error") or not self.tpl:
            return None, None
        if i in self.cache:
            png, marks = self.cache[i]
            img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
        else:
            try:
                pages = omr.load_pages(r["file"])
                res, img = omr.read_sheet(pages[r.get("page", 0)][1], self.tpl, r["file"])
            except Exception:
                return None, None
            if img is None:
                return None, None
            marks = res.marks
            self.cache[i] = (cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes(), marks)
        sr = omr.SheetResult.from_json({k: v for k, v in r.items() if k in omr.SheetResult.__dataclass_fields__})
        sr.marks = marks
        return img, sr


# =============================================================================
# Tab 3: Hasil
# =============================================================================
class ResultsTab(QWidget):
    COLS = ["", "Berkas", "Nomor", "Nama", "B", "S", "K", "Nilai"]

    def __init__(self, store: ResultStore):
        super().__init__()
        self.store = store
        store.added.connect(lambda i: self.refresh())
        store.changed.connect(self.refresh)

        left = QVBoxLayout()
        top = QHBoxLayout()
        self.only = QCheckBox("Hanya yang perlu dicek"); self.only.toggled.connect(self.refresh)
        top.addWidget(self.only); top.addStretch()
        self.summary = QLabel(); top.addWidget(self.summary)
        left.addLayout(top)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents); hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self.show_selected)
        left.addWidget(self.table, 1)
        bot = QHBoxLayout()
        b_open = QPushButton("Buka hasil koreksi lama…"); b_open.clicked.connect(self.open_previous)
        self.b_x = QPushButton("⬇  Ekspor ke Excel…"); self.b_x.clicked.connect(self.export)
        self.b_x.setStyleSheet("font-weight:bold;padding:8px")
        bot.addWidget(b_open); bot.addStretch(); bot.addWidget(self.b_x)
        left.addLayout(bot)
        lw = QWidget(); lw.setLayout(left)

        right = QVBoxLayout()
        form = QGridLayout()
        self.f_nomor = QLineEdit(); self.f_nama = QLineEdit(); self.f_ans = QLineEdit()
        mono = QFont("Menlo" if sys.platform == "darwin" else "Consolas"); mono.setStyleHint(QFont.Monospace)
        self.f_ans.setFont(mono)
        form.addWidget(QLabel("Nomor"), 0, 0); form.addWidget(self.f_nomor, 0, 1)
        form.addWidget(QLabel("Nama"), 0, 2); form.addWidget(self.f_nama, 0, 3)
        form.addWidget(QLabel("Jawaban"), 1, 0); form.addWidget(self.f_ans, 1, 1, 1, 3)
        hint = QLabel("Urut sesuai nomor soal. “-” = kosong, “*” = ganda. Ubah huruf untuk membetulkan.")
        hint.setStyleSheet("color:#666;font-size:11px"); form.addWidget(hint, 2, 1, 1, 3)
        right.addLayout(form)
        self.flags = QLabel(); self.flags.setWordWrap(True)
        right.addWidget(self.flags)
        hb = QHBoxLayout()
        self.b_ok = QPushButton("✓ Sudah dicek"); self.b_ok.clicked.connect(self.mark_checked)
        self.score = QLabel(); self.score.setStyleSheet("font-size:20px;font-weight:bold;color:#0b7285")
        hb.addWidget(self.score); hb.addStretch(); hb.addWidget(self.b_ok)
        right.addLayout(hb)
        self.view = ImageView(draw_enabled=False)
        right.addWidget(self.view, 1)
        leg = QLabel("<span style='color:#28963c'>●</span> benar  <span style='color:#c83228'>●</span> salah  "
                     "<span style='color:#1e6ebe'>●</span> kunci seharusnya  <span style='color:#e68c00'>●</span> kosong/ganda/ragu  "
                     "<span style='color:#963ca0'>●</span> nomor peserta")
        right.addWidget(leg)
        rw = QWidget(); rw.setLayout(right)
        for w in (self.f_nomor, self.f_nama, self.f_ans):
            w.editingFinished.connect(self.save_edit)

        sp = QSplitter(); sp.addWidget(lw); sp.addWidget(rw); sp.setSizes([520, 620])
        QVBoxLayout(self).addWidget(sp)
        self.cur = None
        self._enable_form(False)

    def _enable_form(self, on):
        for w in (self.f_nomor, self.f_nama, self.f_ans, self.b_ok):
            w.setEnabled(on)

    def qs(self):
        return self.store.tpl.question_numbers() if self.store.tpl else sorted(
            {int(k) for r in self.store.results for k in r.get("answers", {})})

    def ans_str(self, r):
        a = self.store.answers(r)
        return "".join((a.get(q) or "-") for q in self.qs() if q > 0)

    def refresh(self):
        st = self.store
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        nil = []
        for i, r in enumerate(st.results):
            rv = st.needs_review(r)
            if self.only.isChecked() and not rv:
                continue
            g = st.grade(r) if not r.get("error") else None
            row = self.table.rowCount(); self.table.insertRow(row)
            vals = ["⚠" if rv else "✓", r.get("label", ""), r.get("nomor", ""), r.get("nama", ""),
                    g and g["benar"], g and g["salah"], g and g["kosong"], g and g["nilai"]]
            for c, v in enumerate(vals):
                it = QTableWidgetItem()
                if isinstance(v, (int, float)) and v is not None and not isinstance(v, bool):
                    it.setData(Qt.DisplayRole, v)
                else:
                    it.setText("" if v in (None, False) else str(v))
                it.setData(Qt.UserRole, i)
                if c == 0:
                    it.setForeground(QColor("#e67700" if rv else "#2b8a3e"))
                self.table.setItem(row, c, it)
            if g:
                nil.append(g["nilai"])
        self.table.setSortingEnabled(True)
        n = len(st.results); rv = sum(st.needs_review(r) for r in st.results)
        self.summary.setText(f"{n} lembar · {rv} perlu dicek" + (f" · rata-rata {sum(nil) / len(nil):.1f}" if nil else ""))
        self.b_x.setEnabled(n > 0)
        if self.cur is not None:
            self._select_index(self.cur)

    def _select_index(self, i):
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.UserRole) == i:
                self.table.blockSignals(True); self.table.selectRow(row); self.table.blockSignals(False)
                return

    def show_selected(self):
        items = self.table.selectedItems()
        if not items:
            return
        i = items[0].data(Qt.UserRole); self.cur = i
        r = self.store.results[i]
        self._enable_form(not r.get("error"))
        self.f_nomor.setText(r.get("nomor", "")); self.f_nama.setText(r.get("nama", ""))
        self.f_ans.setText(self.ans_str(r))
        self._show_flags(r)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            img, sr = self.store.aligned(i)
        finally:
            QApplication.restoreOverrideCursor()
        if img is not None:
            sr.answers = self.store.answers(r)
            sr.flags = {int(k): v for k, v in r.get("flags", {}).items()}
            self.view.set_image(omr.annotate(img, sr, self.store.key()), keep_view=True)
            if not self.view.transform().m11() or self.view.transform().m11() == 1.0:
                self.view.fit()
        else:
            self.view.set_image(None)

    def _show_flags(self, r):
        parts = []
        if r.get("error"):
            parts.append(f"<b style='color:#c92a2a'>{r['error']}</b>")
        fl = {int(k): v for k, v in r.get("flags", {}).items()}
        if 0 in fl:
            parts.append(f"<b style='color:#e67700'>{fl.pop(0)}</b>")
        if fl:
            parts.append("<b style='color:#e67700'>Perlu dicek:</b> " + ", ".join(f"no. {q} ({v})" for q, v in sorted(fl.items())))
        if r.get("nomor_flag"):
            parts.append(f"<b style='color:#e67700'>{r['nomor_flag']}</b>")
        if r.get("checked"):
            parts.append("<span style='color:#2b8a3e'>Sudah dicek ✓</span>")
        self.flags.setText("<br>".join(parts))
        g = self.store.grade(r) if not r.get("error") else None
        self.score.setText(f"Nilai {g['nilai']:g}  ·  B {g['benar']}  S {g['salah']}  K {g['kosong']}" if g else "")

    def save_edit(self):
        if self.cur is None:
            return
        r = self.store.results[self.cur]
        r["nomor"] = self.f_nomor.text().strip(); r["nama"] = self.f_nama.text().strip()
        s = self.f_ans.text().upper().replace(" ", "")
        qs = [q for q in self.qs() if q > 0]
        ans = {}
        for j, q in enumerate(qs):
            c = s[j] if j < len(s) else "-"
            ans[str(q)] = "" if c in "-_?" else c
        changed = ans != r.get("answers")
        r["answers"] = ans
        if changed:
            # jawaban yang sudah dibetulkan manual tak perlu ditandai lagi
            r["flags"] = {k: v for k, v in r.get("flags", {}).items() if k == "0"}
        if r["nomor"] and ("_" not in r["nomor"] and "?" not in r["nomor"]):
            r["nomor_flag"] = ""
            if not r["nama"] and self.store.grader:
                r["nama"] = self.store.grader.student_map().get(r["nomor"], "")
                self.f_nama.setText(r["nama"])
        self.store.save(); self.refresh(); self.show_selected()

    def mark_checked(self):
        if self.cur is None:
            return
        self.save_edit()
        self.store.results[self.cur]["checked"] = True
        self.store.save()
        # lompat ke lembar berikutnya yang perlu dicek
        nxt = next((j for j in range(len(self.store.results)) if self.store.needs_review(self.store.results[j])), None)
        if nxt is not None:
            self.cur = nxt
        self.refresh(); self.show_selected()

    def open_previous(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Buka hasil koreksi", "", f"Hasil ({RESULT_FILE})")
        if not fn:
            return
        g = self.store.grader
        try:
            data = json.loads(Path(fn).read_text(encoding="utf-8"))
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Gagal membuka: {e}"); return
        name = data.get("template", "")
        i = g.tpl_combo.findText(name)
        if i >= 0:
            g.tpl_combo.setCurrentIndex(i)
        self.store.folder = Path(fn).parent; self.store.tpl = g.template(); self.store.cache = {}
        self.store.results = data.get("results", [])
        self.cur = None; self.store.changed.emit()

    # ---------- Excel
    def export(self):
        st = self.store
        if not st.results:
            return
        default = str((st.folder or Path.home()) / f"Rekap nilai {time.strftime('%Y-%m-%d')}.xlsx")
        fn, _ = QFileDialog.getSaveFileName(self, "Simpan rekap Excel", default, "Excel (*.xlsx)")
        if not fn:
            return
        if not fn.lower().endswith(".xlsx"):
            fn += ".xlsx"
        try:
            export_excel(fn, st)
        except PermissionError:
            QMessageBox.warning(self, APP_NAME, "Berkas sedang dibuka di Excel. Tutup dulu, lalu coba lagi."); return
        QMessageBox.information(self, APP_NAME, f"Rekap tersimpan:\n{fn}")


def export_excel(fn: str, st: ResultStore):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    key = st.key(); qs = [q for q in (st.tpl.question_numbers() if st.tpl else sorted(key)) if q > 0]
    rows = []
    for r in st.results:
        if r.get("error"):
            continue
        rows.append((r, st.grade(r)))
    rows.sort(key=lambda x: (-x[1]["nilai"], x[0].get("nomor", "")))
    wb = Workbook(); ws = wb.active; ws.title = "Rekap"
    bold = Font(bold=True)
    ws["A1"] = "Rekap Nilai" + (f" — {st.tpl.name}" if st.tpl else ""); ws["A1"].font = Font(bold=True, size=14)
    pb, ps, pk = st.pts()
    ws["A2"] = f"Jumlah soal dinilai: {len(key)}  ·  Poin benar/salah/kosong: {pb:g} / {ps:g} / {pk:g}  ·  Dibuat {time.strftime('%d-%m-%Y %H:%M')}"
    head = ["Peringkat", "Nomor Peserta", "Nama", "Benar", "Salah", "Kosong", "Skor", "Nilai", "Catatan", "Berkas"] + [str(q) for q in qs]
    HR = 4
    for c, h in enumerate(head, 1):
        cell = ws.cell(HR, c, h); cell.font = bold; cell.fill = PatternFill("solid", fgColor="DDE7EE")
        cell.alignment = Alignment(horizontal="center")
    ws.cell(HR + 1, 3, "KUNCI JAWABAN").font = bold
    for j, q in enumerate(qs):
        c = ws.cell(HR + 1, 11 + j, key.get(q, "")); c.font = bold; c.alignment = Alignment(horizontal="center")
    green = PatternFill("solid", fgColor="D3F9D8"); red = PatternFill("solid", fgColor="FFE3E3"); grey = PatternFill("solid", fgColor="F1F3F5")
    for i, (r, g) in enumerate(rows):
        R = HR + 2 + i
        note = []
        if st.needs_review(r):
            note.append("perlu dicek")
        vals = [i + 1, r.get("nomor", ""), r.get("nama", ""), g["benar"], g["salah"], g["kosong"], g["skor"], g["nilai"],
                ", ".join(note), r.get("label", "")]
        for c, v in enumerate(vals, 1):
            ws.cell(R, c, v)
        a = st.answers(r)
        for j, q in enumerate(qs):
            v = a.get(q, "")
            cell = ws.cell(R, 11 + j, v or "-"); cell.alignment = Alignment(horizontal="center")
            if q in key:
                cell.fill = grey if not v else (green if v == key[q] else red)
    if rows:
        R = HR + 3 + len(rows)
        n = len(rows)
        ws.cell(R, 3, "Rata-rata").font = bold
        ws.cell(R, 8, f"=ROUND(AVERAGE(H{HR + 2}:H{HR + 1 + n}),2)").font = bold
        ws.cell(R + 1, 3, "Tertinggi").font = bold; ws.cell(R + 1, 8, f"=MAX(H{HR + 2}:H{HR + 1 + n})")
        ws.cell(R + 2, 3, "Terendah").font = bold; ws.cell(R + 2, 8, f"=MIN(H{HR + 2}:H{HR + 1 + n})")
    widths = [10, 15, 28, 7, 7, 8, 7, 8, 13, 22] + [4] * len(qs)
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = ws.cell(HR + 2, 4)

    # Per soal
    w2 = wb.create_sheet("Per Soal")
    labels = sorted({ch for q in qs for ch in (st.tpl.labels_for(q) if st.tpl else "ABCDE")})
    h2 = ["No. Soal", "Kunci", "Jumlah Benar", "% Benar", "Kosong"] + [f"Pilih {l}" for l in labels]
    for c, h in enumerate(h2, 1):
        cell = w2.cell(1, c, h); cell.font = bold; cell.fill = PatternFill("solid", fgColor="DDE7EE")
    for i, q in enumerate(qs):
        cnt = {l: 0 for l in labels}; b = k = 0
        for r, _ in rows:
            v = st.answers(r).get(q, "")
            if not v:
                k += 1
            elif v in cnt:
                cnt[v] += 1
            if v and v == key.get(q):
                b += 1
        pct = round(b / len(rows) * 100, 1) if rows else 0
        vals = [q, key.get(q, ""), b, pct, k] + [cnt[l] for l in labels]
        for c, v in enumerate(vals, 1):
            cell = w2.cell(2 + i, c, v)
            if c == 4 and rows:
                cell.fill = red if pct < 40 else (green if pct >= 75 else PatternFill())
    for c in range(1, len(h2) + 1):
        w2.column_dimensions[get_column_letter(c)].width = 13
    w2.freeze_panes = "B2"
    wb.save(fn)


# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1280, 820)
        self.store = ResultStore()
        self.tabs = QTabWidget()
        self.t_tpl = TemplateTab()
        self.t_grade = GradeTab(self.store)
        self.t_res = ResultsTab(self.store)
        self.tabs.addTab(self.t_tpl, "1. Template")
        self.tabs.addTab(self.t_grade, "2. Koreksi")
        self.tabs.addTab(self.t_res, "3. Hasil")
        self.setCentralWidget(self.tabs)
        self.t_tpl.templatesChanged.connect(self.t_grade.reload_templates)
        self.t_grade.started.connect(lambda: self.tabs.setCurrentWidget(self.t_res))
        self.t_grade.key.textChanged.connect(self.t_res.refresh)
        for w in (self.t_grade.pb, self.t_grade.ps, self.t_grade.pk):
            w.valueChanged.connect(self.t_res.refresh)
        self.store.grader = self.t_grade
        if self.t_grade.tpl_combo.count():
            self.tabs.setCurrentWidget(self.t_grade)

    def closeEvent(self, e):
        if self.t_tpl.dirty and QMessageBox.question(self, APP_NAME, "Template belum disimpan. Tetap keluar?") != QMessageBox.Yes:
            e.ignore(); return
        self.t_grade.save_settings(); self.store.save()
        if self.t_grade.worker and self.t_grade.worker.isRunning():
            self.t_grade.worker.stop(); self.t_grade.worker.wait(5000)
        e.accept()


def main():
    QApplication.setOrganizationName("LanaAqil")
    QApplication.setApplicationName(APP_NAME)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
