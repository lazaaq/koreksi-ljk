"""Panduan dalam aplikasi (pop-up), supaya layar utama tetap ringkas."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QTabWidget, QTextBrowser, QVBoxLayout

from . import theme as T

CSS = f"""
<style>
 body {{ font-size: 14px; color: {T.TEXT}; line-height: 150%; }}
 h3 {{ font-size: 16px; margin: 16px 0 6px 0; }}
 ol, ul {{ margin-top: 4px; margin-left: -18px; }}
 li {{ margin-bottom: 6px; }}
 .tip {{ color: {T.MUTED}; }}
 kbd {{ background: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 4px; padding: 1px 5px; }}
</style>
"""

TEMPLATE = CSS + """
<h3>Template dari LJK kosong</h3>
<ol>
 <li>Scan satu LJK yang <b>belum diisi</b>.</li>
 <li>Klik <b>Template dari LJK Kosong</b> dan pilih hasil scannya.</li>
</ol>
<h3>Template tanpa LJK kosong</h3>
<ol>
 <li>Klik <b>Template Tanpa LJK Kosong</b>.</li>
 <li>Pilih folder berisi minimal <b>5 scan terisi</b>. Isian siswa dihapus otomatis, cetakan LJK disimpan.</li>
</ol>
<h3>Menandai bulatan</h3>
<ol>
 <li><b>Tarik kotak</b> (klik kiri) di sekeliling satu kelompok bulatan, mis. soal 1–10.</li>
 <li>Pilih jenis blok:
  <ul>
   <li><b>Jawaban soal</b> — isi nomor soal pertama.</li>
   <li><b>Nomor peserta</b> — angka 0–9.</li>
   <li><b>Nama peserta</b> — huruf A–Z.</li>
   <li><b>Isian lain</b> — mis. Ruang, No HP. Dibaca, tidak dinilai.</li>
  </ul></li>
 <li>Cek jumlah baris/kolom dan <b>Susunan</b>: tiap baris atau tiap kolom = 1 soal/digit.</li>
 <li>Ulangi untuk kelompok lain. Satu kolom soal = satu kotak.</li>
 <li>Pastikan <b>titik di tengah tiap bulatan</b>, beri nama, lalu <b>Simpan</b>.</li>
</ol>
<h3>Kontrol</h3>
<ul>
 <li><kbd>Klik kiri + tarik</kbd> buat kotak &nbsp;·&nbsp; <kbd>Roda mouse</kbd> zoom &nbsp;·&nbsp; <kbd>Klik kanan + tarik</kbd> geser</li>
 <li>Blok salah? Pilih di daftar bawah → <b>Hapus blok</b>, lalu tarik ulang.</li>
 <li><b>Ekspor</b> menghasilkan berkas <i>.ljktemplate</i>; buka di laptop lain dengan <b>Impor</b>.</li>
</ul>
"""

KOREKSI = CSS + """
<h3>1 · Template &amp; kunci</h3>
<ul>
 <li>Pilih template sesuai LJK yang dikoreksi.</li>
 <li>Kunci bisa diketik berurutan <kbd>ABCDA…</kbd> atau per nomor <kbd>1.A 2.C …</kbd>.</li>
 <li><b>Baca dari scan</b>: isi satu LJK dengan kunci, scan, lalu pilih berkasnya.</li>
 <li>Soal tanpa kunci tidak dinilai.</li>
</ul>
<h3>Poin</h3>
<ul>
 <li>Nilai = skor ÷ (jumlah soal × poin benar) × 100.</li>
 <li>Sistem minus: isi poin salah, mis. <kbd>-1</kbd>.</li>
</ul>
<h3>2 · Daftar siswa (opsional)</h3>
<ul>
 <li>Satu baris per siswa: <kbd>nomor, nama</kbd>.</li>
 <li>Nama terisi otomatis dari nomor peserta di LJK. Bisa impor dari Excel/CSV (kolom A nomor, kolom B nama).</li>
</ul>
<h3>3 · Folder scan</h3>
<ul>
 <li>Semua JPG, PNG, TIFF, GIF, dan PDF di folder dikoreksi sekaligus.</li>
 <li>Scan 200–300 dpi, grayscale. Miring sedikit atau terbalik tidak masalah.</li>
 <li>Folder yang pernah dikoreksi bisa <b>dilanjutkan</b> (hanya berkas baru) atau <b>dikoreksi ulang</b>.</li>
</ul>
"""

HASIL = CSS + """
<h3>Status</h3>
<ul>
 <li><b style="color:#16A34A">OK</b> — terbaca jelas.</li>
 <li><b style="color:#D97706">Perlu dicek</b> — jawaban ganda, isian tipis/bekas hapusan, atau nomor peserta tidak lengkap.
 Alasannya tampil di kotak kuning.</li>
</ul>
<h3>Membetulkan</h3>
<ol>
 <li>Klik baris, zoom gambar untuk melihat bulatan yang ditandai.</li>
 <li>Ubah <b>Nomor</b>, <b>Nama</b>, atau <b>Jawaban</b>. Di kolom jawaban: <kbd>-</kbd> = kosong, <kbd>*</kbd> = ganda.</li>
 <li>Klik <b>Sudah dicek</b> — lanjut otomatis ke lembar berikutnya.</li>
</ol>
<h3>Warna di gambar</h3>
<ul>
 <li><b style="color:#16A34A">Hijau</b> benar · <b style="color:#DC2626">Merah</b> salah · <b style="color:#2563EB">Biru</b> kunci seharusnya ·
 <b style="color:#D97706">Oranye</b> kosong/ganda/ragu · <b style="color:#9333EA">Ungu</b> nomor, nama &amp; isian</li>
</ul>
<h3>Simpan &amp; ekspor</h3>
<ul>
 <li>Hasil tersimpan otomatis di folder scan (<i>hasil_koreksi_ljk.json</i>).</li>
 <li><b>Ekspor Excel</b>: sheet <b>Rekap</b> (peringkat, isian, jawaban berwarna) dan <b>Per Soal</b> (% benar, pilihan terbanyak).</li>
</ul>
"""


class GuideDialog(QDialog):
    def __init__(self, parent=None, page: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Panduan")
        self.resize(620, 640)
        lay = QVBoxLayout(self); lay.setContentsMargins(20, 16, 20, 16); lay.setSpacing(12)
        tabs = QTabWidget()
        for title, html in (("Template", TEMPLATE), ("Koreksi", KOREKSI), ("Hasil", HASIL)):
            tb = QTextBrowser(); tb.setHtml(html); tb.setOpenExternalLinks(True)
            tb.setStyleSheet("QTextBrowser { border: none; padding: 4px 8px; background: white; }")
            tabs.addTab(tb, title)
        tabs.setCurrentIndex(page)
        tabs.tabBar().setCursor(Qt.PointingHandCursor)
        lay.addWidget(tabs, 1)
        row = QHBoxLayout(); row.addStretch()
        row.addWidget(T.button("Tutup", "primary", slot=self.accept))
        lay.addLayout(row)
