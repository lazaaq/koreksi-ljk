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
    QAbstractItemView, QSizePolicy, QScrollArea, QFrame,
)

from . import omr
from . import theme as T
from .theme import Card, button, label, set_role, page_header
from .guide import GuideDialog
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

    def __init__(self, draw_enabled=False, placeholder: str = ""):
        super().__init__()
        self.placeholder = placeholder
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor("#F1F5F9"))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.draw_enabled = draw_enabled
        self._origin = None
        self._band = None
        self._pan = None
        self.pix_item: QGraphicsPixmapItem | None = None
        self.set_image(None)

    def set_image(self, img: np.ndarray | None, keep_view=False):
        tr = self.transform() if keep_view else None
        h0 = self.horizontalScrollBar().value(); v0 = self.verticalScrollBar().value()
        self.scene().clear(); self._band = None
        if img is None:
            self.pix_item = None
            if self.placeholder:
                t = self.scene().addText(self.placeholder)
                f = QFont(); f.setPixelSize(15); t.setFont(f); t.setDefaultTextColor(QColor(T.MUTED))
                self.scene().setSceneRect(t.boundingRect().adjusted(-40, -40, 40, 40))
                self.resetTransform()
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
        self.kind = QComboBox(); self.kind.addItems(["Jawaban soal", "Nomor peserta (angka)", "Nama peserta (huruf A–Z)",
                                                     "Isian lain (mis. ruang, no HP) — tidak dinilai"])
        self.title = QLineEdit(); self.title.setPlaceholderText("mis. Ruang, No HP, Kode paket")
        self.charset = QComboBox(); self.charset.addItems(["Angka 0–9", "Huruf A–Z"])
        self.charset.currentIndexChanged.connect(lambda: self._update())
        self.rows = QSpinBox(); self.rows.setRange(1, 200); self.rows.setValue(max(rows, 1))
        self.cols = QSpinBox(); self.cols.setRange(1, 200); self.cols.setValue(max(cols, 1))
        self.orient = QComboBox()
        self.orient.addItems(["Tiap BARIS = 1 soal (pilihan A–E ke samping)",
                              "Tiap KOLOM = 1 soal (pilihan A–E ke bawah)"])
        self.start = QSpinBox(); self.start.setRange(1, 999); self.start.setValue(next_start)
        self.labels = QLineEdit()
        for sb in (self.rows, self.cols, self.start):
            sb.setButtonSymbols(QSpinBox.NoButtons); sb.findChild(QLineEdit).setTextMargins(8, 0, 0, 0)
        self.info = label("", "info", wrap=True)
        self.setMinimumWidth(580)
        lay.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lay.setSpacing(12); lay.setContentsMargins(24, 22, 24, 20)
        lay.addRow("Jenis blok", self.kind)
        lay.addRow("Nama isian", self.title)
        lay.addRow("Isinya berupa", self.charset)
        lay.addRow("Jumlah baris bulatan", self.rows)
        lay.addRow("Jumlah kolom bulatan", self.cols)
        lay.addRow("Susunan", self.orient)
        lay.addRow("Nomor soal pertama", self.start)
        lay.addRow("Label pilihan", self.labels)
        lay.addRow(self.info)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Tambah blok"); bb.button(QDialogButtonBox.Ok).setProperty("kind", "primary")
        bb.button(QDialogButtonBox.Cancel).setText("Batal")
        T.clickable(self)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addRow(bb)
        for w in (self.kind, self.orient):
            w.currentIndexChanged.connect(self._update)
        self.title.textChanged.connect(self._update)
        for w in (self.rows, self.cols):
            w.valueChanged.connect(self._update)
        # tebakan susunan: lebih banyak baris daripada kolom → tiap baris = 1 soal
        self.orient.setCurrentIndex(0 if rows >= cols else 1)
        self._update()

    def _update(self):
        kind = self.kind.currentIndex()
        nomor = kind >= 1
        isian = kind == 3
        form = self.layout()
        for w in (self.title, self.charset):
            form.setRowVisible(w, isian)
        huruf = (kind == 2) or (isian and self.charset.currentIndex() == 1)
        if huruf:
            self.orient.setItemText(0, "Tiap BARIS = 1 huruf (A–Z ke samping)")
            self.orient.setItemText(1, "Tiap KOLOM = 1 huruf (A–Z ke bawah)")
        elif nomor:
            self.orient.setItemText(0, "Tiap BARIS = 1 digit (angka 0–9 ke samping)")
            self.orient.setItemText(1, "Tiap KOLOM = 1 digit (angka 0–9 ke bawah)")
        else:
            self.orient.setItemText(0, "Tiap BARIS = 1 soal (pilihan A–E ke samping)")
            self.orient.setItemText(1, "Tiap KOLOM = 1 soal (pilihan A–E ke bawah)")
        self.start.setEnabled(not nomor)
        along_rows = self.orient.currentIndex() == 0
        n_ch = self.cols.value() if along_rows else self.rows.value()
        n_it = self.rows.value() if along_rows else self.cols.value()
        self.labels.setText(omr.ALPHABET[:n_ch] if huruf else (omr.DIGITS[:n_ch] if nomor else omr.LETTERS[:n_ch]))
        if isian:
            self.info.setText(f"{self.title.text().strip() or 'Isian'}: {n_it} kolom × {n_ch} pilihan · tidak dinilai")
        elif kind == 2:
            self.info.setText(f"Nama sampai {n_it} huruf, tiap huruf {n_ch} pilihan.")
        elif nomor:
            self.info.setText(f"{n_it} digit nomor peserta, tiap digit {n_ch} pilihan.")
        else:
            self.info.setText(f"Soal {self.start.value()}–{self.start.value() + n_it - 1}, "
                              f"masing-masing {n_ch} pilihan.")

    def values(self):
        return dict(kind=["soal", "nomor", "nama", "isian"][self.kind.currentIndex()], title=self.title.text().strip(),
                    rows=self.rows.value(), cols=self.cols.value(),
                    items_along="rows" if self.orient.currentIndex() == 0 else "cols",
                    start=self.start.value(), labels=self.labels.text().strip())


# =============================================================================
# Tab 1: Template
# =============================================================================
class TemplateTab(QWidget):
    templatesChanged = Signal()
    COLORS = {"soal": QColor(T.PRIMARY), "nomor": QColor(T.PURPLE), "nama": QColor("#0891B2"), "isian": QColor("#EA580C")}

    def __init__(self):
        super().__init__()
        self.tpl: omr.Template | None = None
        self.tpl_dir: Path | None = None
        self.bubbles = []
        self.dirty = False

        # panel kiri: daftar template + panduan
        side = Card("Template")
        self.list = QListWidget(); self.list.currentItemChanged.connect(self._open_selected)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.list.setWordWrap(True)
        side.lay.addWidget(self.list, 1)
        side.lay.addWidget(button("Template dari LJK Kosong", "primary", slot=self.new_template))
        side.lay.addWidget(button("Template Tanpa LJK Kosong", slot=self.new_from_filled))
        io = QHBoxLayout(); io.setSpacing(8)
        io.addWidget(button("Impor", slot=self.import_template)); io.addWidget(button("Ekspor", slot=self.export_template))
        io.addWidget(button("Hapus", "danger", slot=self.delete_template))
        side.lay.addLayout(io)
        side.setFixedWidth(300)

        # panel kanan: editor
        editor = Card()
        top = QHBoxLayout(); top.setSpacing(10)
        self.name = QLineEdit(); self.name.setPlaceholderText("Nama template")
        self.name.textChanged.connect(lambda: self._set_dirty())
        top.addWidget(self.name, 1)
        self.b_fit = button("Paskan"); top.addWidget(self.b_fit)
        self.b_save = button("Simpan", "primary", slot=self.save)
        top.addWidget(self.b_save)
        editor.lay.addLayout(top)
        self.view = ImageView(draw_enabled=True, placeholder="Pilih atau buat template")
        self.view.rectDrawn.connect(self.add_block)
        self.b_fit.clicked.connect(self.view.fit)
        body = QHBoxLayout(); body.setSpacing(16)
        bcol = QVBoxLayout(); bcol.setSpacing(8)
        bcol.addWidget(label("Blok", "label"))
        self.blocks = QListWidget(); self.blocks.setWordWrap(True)
        self.blocks.currentRowChanged.connect(self._highlight_block)
        self._rect_items = []
        self.blocks.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        bcol.addWidget(self.blocks, 1)
        self.status = label("", "hint", wrap=True); bcol.addWidget(self.status)
        bcol.addWidget(button("Hapus blok", "danger", slot=self.remove_block))
        bw = QWidget(); bw.setLayout(bcol); bw.setFixedWidth(250)
        bcol.setContentsMargins(0, 0, 0, 0)
        body.addWidget(bw); body.addWidget(self.view, 1)
        editor.lay.addLayout(body, 1)

        lay = QHBoxLayout(self); lay.setContentsMargins(24, 20, 24, 24); lay.setSpacing(20)
        lay.addWidget(side); lay.addWidget(editor, 1)
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
        self.status.setText(f"{len(self.bubbles)} bulatan terdeteksi · tarik kotak untuk menandai")

    def _start_new(self, img, name):
        self.tpl = omr.Template(name=name, ref_path="")
        self.tpl.set_ref(img)
        self.tpl_dir = None
        self.bubbles = omr.detect_bubbles(self.tpl.ref())
        self.name.blockSignals(True); self.name.setText(self.tpl.name); self.name.blockSignals(False)
        self.list.blockSignals(True); self.list.clearSelection(); self.list.setCurrentItem(None); self.list.blockSignals(False)
        self._enable(True); self.redraw(fit=True); self._set_dirty(True)
        self.status.setText(f"{len(self.bubbles)} bulatan terdeteksi · tarik kotak untuk menandai")

    def new_from_filled(self):
        if not self._confirm_discard():
            return
        d = QFileDialog.getExistingDirectory(self, "Pilih folder berisi scan LJK TERISI (min. 5 lembar)")
        if not d:
            return
        files = omr.list_sheets(d)[:30]
        if len(files) < 5:
            QMessageBox.warning(self, APP_NAME, "Butuh minimal 5 scan di folder itu."); return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            imgs = [omr.load_pages(f)[0][1] for f in files]
            blank = omr.build_blank(imgs, progress=lambda i, n: (self.status.setText(f"Menyusun LJK kosong… {i}/{n}"),
                                                                 QApplication.processEvents()))
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP_NAME, f"Gagal: {e}"); return
        QApplication.restoreOverrideCursor()
        self._start_new(blank, Path(d).name)
        self.status.setText(f"Disusun dari {len(imgs)} scan · {len(self.bubbles)} bulatan · tarik kotak untuk menandai")

    def export_template(self):
        if not self.tpl_dir:
            QMessageBox.information(self, APP_NAME, "Pilih atau simpan template dulu."); return
        fn, _ = QFileDialog.getSaveFileName(self, "Ekspor template", str(Path.home() / f"{safe_name(self.tpl.name)}.ljktemplate"),
                                            "Template LJK (*.ljktemplate)")
        if not fn:
            return
        import zipfile
        with zipfile.ZipFile(fn, "w", zipfile.ZIP_DEFLATED) as z:
            for f in ("template.json", "ref.png"):
                z.write(self.tpl_dir / f, f)
        QMessageBox.information(self, APP_NAME, f"Template diekspor:\n{fn}\n\nKirim berkas ini ke laptop lain lalu pilih “Impor…”.")

    def import_template(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Impor template", "", "Template LJK (*.ljktemplate *.zip)")
        if fn:
            self.import_file(fn)

    def import_file(self, fn) -> Path | None:
        import zipfile
        try:
            with zipfile.ZipFile(fn) as z:
                names = set(z.namelist())
                if not {"template.json", "ref.png"} <= names:
                    raise ValueError("bukan berkas template Koreksi LJK")
                name = json.loads(z.read("template.json").decode("utf-8"))["name"]
                d = templates_dir() / f"{safe_name(name)}_{int(time.time())}"
                d.mkdir(parents=True)
                for f in ("template.json", "ref.png"):
                    (d / f).write_bytes(z.read(f))
        except Exception as e:
            QMessageBox.warning(self, APP_NAME, f"Gagal mengimpor: {e}"); return None
        self.reload_list(select=str(d)); self.templatesChanged.emit()
        it = self.list.currentItem()
        if it:
            self._open_selected(it, None)
        return d

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
        if v["kind"] == "isian" and not v["title"]:
            QMessageBox.warning(self, APP_NAME, "Isi dulu nama isiannya, mis. “Ruang”."); return
        if v["kind"] == "isian" and any(b.kind == "isian" and b.title.lower() == v["title"].lower() for b in self.tpl.blocks):
            QMessageBox.warning(self, APP_NAME, f"Isian “{v['title']}” sudah ada. Pakai nama lain."); return
        b = omr.fit_block(self.bubbles, rect, v["rows"], v["cols"], v["kind"], v["items_along"], v["start"],
                          v["labels"] or None, title=v["title"])
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
        self.blocks.blockSignals(True); self.blocks.clear(); self.blocks.blockSignals(False)
        self._rect_items = []
        for b in self.tpl.blocks:
            col = self.COLORS[b.kind]
            p = QPen(col, 2); p.setCosmetic(True)
            fill = QColor(col); fill.setAlpha(28)
            self._rect_items.append((sc.addRect(QRectF(*b.rect), p, QBrush(fill)), col))
            dot = QBrush(col); rx, ry = b.radius
            for row in b.centers:
                for (x, y) in row:
                    e = sc.addEllipse(x - rx, y - ry, 2 * rx, 2 * ry, p)
                    sc.addEllipse(x - 2.5, y - 2.5, 5, 5, QPen(Qt.NoPen), dot)
            if b.kind == "soal":
                txt = f"Soal {b.start}–{b.start + b.n_items - 1}  ({b.n_choices} pilihan: {b.labels})"
            elif b.kind == "nama":
                txt = f"Nama peserta  ({b.n_items} huruf)"
            elif b.kind == "isian":
                txt = f"{b.title}  ({b.n_items} kolom, tidak dinilai)"
            else:
                txt = f"Nomor peserta  ({b.n_items} digit)"
            t = sc.addSimpleText(txt.split("  ")[0]); t.setBrush(col)
            f = QFont(); f.setPointSize(16); f.setBold(True); t.setFont(f)
            t.setPos(b.rect[0], b.rect[1] - 28)
            self.blocks.addItem(txt)
        qs = self.tpl.question_numbers()
        has_id = any(b.kind == "nomor" for b in self.tpl.blocks)
        has_nm = any(b.kind == "nama" for b in self.tpl.blocks)
        self.status.setText(f"{len(qs)} soal" + (" · nomor ✓" if has_id else "") + (" · nama ✓" if has_nm else "") +
                            "".join(f" · {b.title} ✓" for b in self.tpl.blocks if b.kind == "isian"))

    def _highlight_block(self, row):
        for i, (it, col) in enumerate(self._rect_items):
            p = QPen(col, 5 if i == row else 2); p.setCosmetic(True)
            f = QColor(col); f.setAlpha(70 if i == row else 28)
            it.setPen(p); it.setBrush(QBrush(f))
        if 0 <= row < len(self._rect_items):
            self.view.ensureVisible(self._rect_items[row][0], 40, 40)

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
        self.status.setText("Tersimpan ✓")


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

        mono = QFont("Menlo" if sys.platform == "darwin" else "Consolas"); mono.setStyleHint(QFont.Monospace)
        mono.setPixelSize(15)

        # 1. template & kunci
        c1 = Card("Template & kunci", step=1)
        self.tpl_combo = QComboBox(); self.tpl_combo.currentIndexChanged.connect(self._tpl_changed)
        c1.lay.addWidget(self.tpl_combo)
        c1.lay.addSpacing(4)
        kh = QHBoxLayout(); kh.addWidget(label("Kunci jawaban", "label")); kh.addStretch()
        kh.addWidget(button("Baca dari scan", "ghost", slot=self.key_from_scan))
        c1.lay.addLayout(kh)
        self.key = QPlainTextEdit()
        self.key.setPlaceholderText("ABCDA …  atau  1.A 2.C …")
        self.key.textChanged.connect(self._key_changed)
        self.key.setFont(mono); self.key.setFixedHeight(110)
        c1.lay.addWidget(self.key)
        self.key_info = label("", "hint", wrap=True); c1.lay.addWidget(self.key_info)
        c1.lay.addSpacing(4)
        c1.lay.addWidget(label("Poin", "label"))
        self.pb = QDoubleSpinBox(); self.ps = QDoubleSpinBox(); self.pk = QDoubleSpinBox()
        pts = QHBoxLayout(); pts.setSpacing(16)
        for lab, w, v in (("Benar", self.pb, 1), ("Salah", self.ps, 0), ("Kosong", self.pk, 0)):
            w.setRange(-100, 100); w.setDecimals(2); w.setSingleStep(0.25); w.setValue(v); w.setFixedWidth(110)
            w.setButtonSymbols(QDoubleSpinBox.NoButtons)
            w.findChild(QLineEdit).setTextMargins(8, 0, 0, 0)
            col = QVBoxLayout(); col.setSpacing(4); col.addWidget(label(lab, "hint")); col.addWidget(w)
            pts.addLayout(col)
        pts.addStretch()
        c1.lay.addLayout(pts)

        # 2. siswa
        c2 = Card("Daftar siswa (opsional)", step=2)
        self.students = QPlainTextEdit()
        self.students.setPlaceholderText("nomor, nama")
        self.students.setFixedHeight(100)
        c2.lay.addWidget(self.students)
        c2.lay.addWidget(button("Impor Excel / CSV", slot=self.import_students), 0, Qt.AlignLeft)

        # 3. folder
        c3 = Card("Folder scan", step=3)
        h3 = QHBoxLayout(); h3.setSpacing(10)
        self.folder = QLineEdit(); self.folder.setPlaceholderText("Pilih folder")
        h3.addWidget(self.folder, 1); h3.addWidget(button("Pilih", slot=self.pick_folder))
        c3.lay.addLayout(h3)

        self.b_go = button("Mulai koreksi", "primary", "lg", slot=self.start)
        self.prog = QProgressBar(); self.prog.setVisible(False); self.prog.setFixedHeight(10)
        self.log = label("", None, wrap=True)

        col = QWidget(); col.setMaximumWidth(860)
        v = QVBoxLayout(col); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(16)
        for w in (c1, c2, c3):
            v.addWidget(w)
        go = QHBoxLayout(); go.addWidget(self.b_go); go.addStretch(); v.addLayout(go)
        v.addWidget(self.prog); v.addWidget(self.log); v.addStretch()
        inner = QWidget(); inner.setObjectName("Page")
        hl = QHBoxLayout(inner); hl.setContentsMargins(24, 24, 24, 32); hl.addStretch(); hl.addWidget(col, 10); hl.addStretch()
        sa = QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(inner)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.addWidget(sa)

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
            self.key_info.setText("Belum ada template"); set_role(self.key_info, "error")
            return
        qs = tpl.question_numbers(); k = self.key_dict()
        miss = [q for q in qs if q not in k]
        if not k:
            self.key_info.setText(f"{len(qs)} soal"); set_role(self.key_info, "hint")
        elif miss:
            self.key_info.setText(f"{len(k)} dari {len(qs)} soal dinilai")
            set_role(self.key_info, "hint")
        else:
            self.key_info.setText(f"✓  {len(k)} soal"); set_role(self.key_info, "ok")

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
        self.b_go.setText("Hentikan"); self.t0 = time.time()
        self.started.emit()
        self.worker.start()

    def _progress(self, n, total, label):
        self.prog.setMaximum(total); self.prog.setValue(n)
        self.log.setText(f"Mengoreksi {n} dari {total}  ·  {label}"); set_role(self.log, "hint")

    def _done(self):
        self.b_go.setText("Mulai koreksi"); self.prog.setVisible(False)
        rs = self.store.results
        rv = sum(1 for r in rs if self.store.needs_review(r))
        self.log.setText(f"Selesai: {len(rs)} lembar dalam {time.time() - self.t0:.0f} detik. "
                         f"{rv} lembar perlu dicek — lihat tab “Hasil”.")
        set_role(self.log, "ok")
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
        if not d.get("nama") and d.get("nama_lembar"):
            d["nama"] = d["nama_lembar"].title()
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
        return bool(r.get("error") or self.relevant_flags(r) or r.get("nomor_flag"))

    def relevant_flags(self, r: dict) -> dict[int, str]:
        """Tanda yang perlu dicek — soal di luar kunci (tidak dinilai) diabaikan."""
        key = self.key()
        fl = {int(k): v for k, v in r.get("flags", {}).items()}
        return {q: v for q, v in fl.items() if q == 0 or not key or q in key}

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
    COLS = ["Status", "Nomor", "Nama", "Benar", "Salah", "Kosong", "Nilai"]
    NUM_COLS = (3, 4, 5, 6)

    def __init__(self, store: ResultStore):
        super().__init__()
        self.store = store
        store.added.connect(lambda i: self.refresh())
        store.changed.connect(self.refresh)

        # ---- kiri: daftar lembar
        lc = Card()
        th = QHBoxLayout(); th.addWidget(label("Hasil koreksi", "cardTitle")); th.addStretch()
        self.summary = label("", "hint"); th.addWidget(self.summary)
        lc.lay.addLayout(th)
        self.only = QCheckBox("Hanya yang perlu dicek"); self.only.toggled.connect(self.refresh)
        lc.lay.addWidget(self.only)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setAlternatingRowColors(True); self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.NoFocus)
        hh = self.table.horizontalHeader(); hh.setHighlightSections(False)
        hh.setSectionResizeMode(QHeaderView.Fixed); hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for c, wdt in ((0, 108), (1, 74), (3, 62), (4, 58), (5, 70), (6, 70)):
            self.table.setColumnWidth(c, wdt)
        hh.setMinimumSectionSize(56)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self.show_selected)
        lc.lay.addWidget(self.table, 1)
        bot = QHBoxLayout(); bot.setSpacing(10)
        bot.addWidget(button("Buka hasil lama", slot=self.open_previous)); bot.addStretch()
        self.b_x = button("Ekspor ke Excel", "primary", slot=self.export); bot.addWidget(self.b_x)
        lc.lay.addLayout(bot)

        # ---- kanan: detail lembar
        rc = Card()
        hb = QHBoxLayout(); hb.setSpacing(12)
        sc = QVBoxLayout(); sc.setSpacing(0)
        self.fname = label("Nilai", "hint"); sc.addWidget(self.fname); self.score = label("–", "bigScore"); sc.addWidget(self.score)
        hb.addLayout(sc)
        self.chip_b = label("", "chipOk"); self.chip_s = label("", "chipBad"); self.chip_k = label("", "chipWarn")
        for c in (self.chip_b, self.chip_s, self.chip_k):
            hb.addWidget(c, 0, Qt.AlignBottom)
        hb.addStretch()
        self.b_ok = button("✓  Sudah dicek", "primary", slot=self.mark_checked)
        hb.addWidget(self.b_ok, 0, Qt.AlignBottom)
        rc.lay.addLayout(hb)
        form = QGridLayout(); form.setHorizontalSpacing(12); form.setVerticalSpacing(6)
        self.f_nomor = QLineEdit(); self.f_nama = QLineEdit(); self.f_ans = QLineEdit()
        mono = QFont("Menlo" if sys.platform == "darwin" else "Consolas"); mono.setStyleHint(QFont.Monospace); mono.setPixelSize(15)
        self.f_ans.setFont(mono)
        form.addWidget(label("Nomor peserta", "label"), 0, 0); form.addWidget(label("Nama", "label"), 0, 1)
        form.addWidget(self.f_nomor, 1, 0); form.addWidget(self.f_nama, 1, 1)
        form.setColumnStretch(0, 1); form.setColumnStretch(1, 2)
        form.addWidget(label("Jawaban  ( - kosong · * ganda )", "label"), 2, 0, 1, 2)
        form.addWidget(self.f_ans, 3, 0, 1, 2)
        rc.lay.addLayout(form)
        self.extra = label("", "hint", wrap=True); self.extra.setVisible(False)
        rc.lay.addWidget(self.extra)
        self.flags = label("", "warn", wrap=True); self.flags.setVisible(False)
        rc.lay.addWidget(self.flags)
        self.view = ImageView(draw_enabled=False, placeholder="Pilih lembar di tabel")
        rc.lay.addWidget(self.view, 1)
        leg = QLabel(f"<span style='color:{T.SUCCESS}'>●</span> benar &nbsp;&nbsp; <span style='color:{T.DANGER}'>●</span> salah &nbsp;&nbsp; "
                     f"<span style='color:{T.PRIMARY}'>●</span> kunci &nbsp;&nbsp; <span style='color:{T.WARNING}'>●</span> cek &nbsp;&nbsp; "
                     f"<span style='color:{T.PURPLE}'>●</span> identitas")
        leg.setProperty("role", "hint"); rc.lay.addWidget(leg)
        for w in (self.f_nomor, self.f_nama, self.f_ans):
            w.editingFinished.connect(self.save_edit)

        sp = QSplitter(); sp.addWidget(lc); sp.addWidget(rc); sp.setSizes([760, 560]); sp.setStretchFactor(0, 4); sp.setStretchFactor(1, 3); sp.setHandleWidth(20)
        sp.setStyleSheet("QSplitter::handle { background: transparent; }")
        lay = QVBoxLayout(self); lay.setContentsMargins(24, 20, 24, 24); lay.addWidget(sp)
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
            vals = ["Perlu dicek" if rv else "OK", r.get("nomor", ""), r.get("nama", "") or "—",
                    g and g["benar"], g and g["salah"], g and g["kosong"], g and g["nilai"]]
            for c, v in enumerate(vals):
                it = QTableWidgetItem()
                if isinstance(v, (int, float)) and v is not None and not isinstance(v, bool):
                    it.setData(Qt.DisplayRole, v)
                else:
                    it.setText("" if v in (None, False) else str(v))
                it.setData(Qt.UserRole, i)
                if c in self.NUM_COLS:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 0:
                    it.setForeground(QColor(T.WARNING if rv else T.SUCCESS))
                    f = it.font(); f.setBold(True); it.setFont(f)
                it.setToolTip(r.get("label", ""))
                if c == 6 and g:
                    f = it.font(); f.setBold(True); it.setFont(f)
                self.table.setItem(row, c, it)
            if g:
                nil.append(g["nilai"])
        self.table.setSortingEnabled(True)
        n = len(st.results); rv = sum(st.needs_review(r) for r in st.results)
        self.summary.setText(f"{n} lembar  ·  {rv} perlu dicek" + (f"  ·  rata-rata {sum(nil) / len(nil):.1f}" if nil else ""))
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
        self.fname.setText(f"Nilai  ·  {r.get('label', '')}")
        fx = r.get("fields") or {}
        self.extra.setText("   ·   ".join(f"<b>{k}:</b> {v or '—'}" for k, v in fx.items()))
        self.extra.setVisible(bool(fx))
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
        parts = []; role = "warn"
        if r.get("error"):
            parts.append(f"<b>{r['error']}</b>"); role = "error"
        fl = self.store.relevant_flags(r)
        if 0 in fl:
            parts.append(f"<b>{fl.pop(0)}</b>")
        if fl:
            parts.append("<b>Perlu dicek:</b> " + ", ".join(f"no. {q} ({v})" for q, v in sorted(fl.items())))
        if r.get("nomor_flag"):
            parts.append(f"<b>{r['nomor_flag'][0].upper() + r['nomor_flag'][1:]}</b>")
        if r.get("checked"):
            parts = ["✓  Sudah dicek"]; role = "ok"
        self.flags.setText("<br>".join(parts)); set_role(self.flags, role); self.flags.setVisible(bool(parts))
        g = self.store.grade(r) if not r.get("error") else None
        self.score.setText(f"{g['nilai']:g}" if g else "–")
        for chip, txt in ((self.chip_b, g and f"Benar {g['benar']}"), (self.chip_s, g and f"Salah {g['salah']}"),
                          (self.chip_k, g and f"Kosong {g['kosong']}")):
            chip.setText(txt or ""); chip.setVisible(bool(g))

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
    extra = [b.title or f"Isian {i + 1}" for i, b in enumerate(st.tpl.blocks) if b.kind == "isian"] if st.tpl else []
    for r, _ in rows:
        for k in (r.get("fields") or {}):
            if k not in extra:
                extra.append(k)
    head = ["Peringkat", "Nomor Peserta", "Nama"] + extra + ["Benar", "Salah", "Kosong", "Skor", "Nilai", "Catatan", "Berkas"] + [str(q) for q in qs]
    E = len(extra)
    HR = 4
    for c, h in enumerate(head, 1):
        cell = ws.cell(HR, c, h); cell.font = bold; cell.fill = PatternFill("solid", fgColor="DDE7EE")
        cell.alignment = Alignment(horizontal="center")
    ws.cell(HR + 1, 3, "KUNCI JAWABAN").font = bold
    for j, q in enumerate(qs):
        c = ws.cell(HR + 1, 11 + E + j, key.get(q, "")); c.font = bold; c.alignment = Alignment(horizontal="center")
    green = PatternFill("solid", fgColor="D3F9D8"); red = PatternFill("solid", fgColor="FFE3E3"); grey = PatternFill("solid", fgColor="F1F3F5")
    for i, (r, g) in enumerate(rows):
        R = HR + 2 + i
        note = []
        if st.needs_review(r):
            note.append("perlu dicek")
        fx = r.get("fields") or {}
        vals = [i + 1, r.get("nomor", ""), r.get("nama", "")] + [fx.get(k, "") for k in extra] + [
                g["benar"], g["salah"], g["kosong"], g["skor"], g["nilai"], ", ".join(note), r.get("label", "")]
        for c, v in enumerate(vals, 1):
            ws.cell(R, c, v)
        a = st.answers(r)
        for j, q in enumerate(qs):
            v = a.get(q, "")
            cell = ws.cell(R, 11 + E + j, v or "-"); cell.alignment = Alignment(horizontal="center")
            if q in key:
                cell.fill = grey if not v else (green if v == key[q] else red)
    if rows:
        R = HR + 3 + len(rows)
        n = len(rows)
        ws.cell(R, 3, "Rata-rata").font = bold
        NC = 8 + E; L = get_column_letter(NC)
        ws.cell(R, NC, f"=ROUND(AVERAGE({L}{HR + 2}:{L}{HR + 1 + n}),2)").font = bold
        ws.cell(R + 1, 3, "Tertinggi").font = bold; ws.cell(R + 1, NC, f"=MAX({L}{HR + 2}:{L}{HR + 1 + n})")
        ws.cell(R + 2, 3, "Terendah").font = bold; ws.cell(R + 2, NC, f"=MIN({L}{HR + 2}:{L}{HR + 1 + n})")
    widths = [10, 15, 28] + [max(10, len(k) + 4) for k in extra] + [7, 7, 8, 7, 8, 13, 22] + [4] * len(qs)
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
        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True)
        self.t_tpl = TemplateTab()
        self.t_grade = GradeTab(self.store)
        self.t_res = ResultsTab(self.store)
        self.tabs.addTab(self.t_tpl, "1  Template")
        self.tabs.addTab(self.t_grade, "2  Koreksi")
        self.tabs.addTab(self.t_res, "3  Hasil")
        header = QWidget(); header.setObjectName("Header")
        hl = QHBoxLayout(header); hl.setContentsMargins(24, 16, 24, 6)
        logo = QLabel("✓"); logo.setFixedSize(36, 36); logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(f"background:{T.PRIMARY};color:white;border-radius:10px;font-size:20px;font-weight:800;")
        hl.addWidget(logo); hl.addSpacing(10)
        tl = QVBoxLayout(); tl.setSpacing(0)
        tl.addWidget(label(APP_NAME, "appTitle"))
        hl.addLayout(tl); hl.addStretch()
        hl.addWidget(label(f"v{__version__}", "hint")); hl.addSpacing(8)
        hl.addWidget(button("?  Panduan", slot=lambda: GuideDialog(self, self.tabs.currentIndex()).exec()))
        central = QWidget(); central.setObjectName("Page")
        cl = QVBoxLayout(central); cl.setContentsMargins(0, 0, 0, 0); cl.setSpacing(0)
        cl.addWidget(header); cl.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.t_tpl.templatesChanged.connect(self.t_grade.reload_templates)
        self.t_grade.started.connect(lambda: self.tabs.setCurrentWidget(self.t_res))
        self.t_grade.key.textChanged.connect(self.t_res.refresh)
        for w in (self.t_grade.pb, self.t_grade.ps, self.t_grade.pk):
            w.valueChanged.connect(self.t_res.refresh)
        self.store.grader = self.t_grade
        if self.t_grade.tpl_combo.count():
            self.tabs.setCurrentWidget(self.t_grade)
        T.clickable(self)

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
    T.apply(app)
    w = MainWindow(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
