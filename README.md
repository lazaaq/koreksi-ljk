# Koreksi LJK

Aplikasi desktop (Windows & macOS) untuk mengoreksi LJK pilihan ganda dari hasil scanner, satu folder sekaligus.
Bisa dipakai untuk **LJK jenis apa pun** lewat template yang dibuat sekali dari scan LJK kosong.

## Unduh & pasang

Buka tab **Actions** (build terbaru) atau **Releases** di repo ini, lalu unduh sesuai komputer:

| Komputer | Berkas | Keterangan |
|---|---|---|
| Windows 10 / 11 (64-bit) | `Koreksi-LJK-Windows-10-11.zip` | Versi utama (Qt 6) |
| Windows 7 SP1 / 8 / 8.1 (64-bit) | `Koreksi-LJK-Windows-7-8-8.1.zip` | Versi lama (Qt 5, Python 3.8) |
| Windows 32-bit (7 / 8 / 10) | `Koreksi-LJK-Windows-32bit.zip` | Versi lama 32-bit |
| Mac Apple Silicon (M1–M4), macOS 11+ | `Koreksi-LJK-macOS-AppleSilicon.zip` | Versi utama |
| Mac Intel, macOS 11+ | `Koreksi-LJK-macOS-Intel.zip` | Versi utama |
| Mac Intel, macOS 10.13 – 10.15 | `Koreksi-LJK-macOS-Intel-lama.zip` | Versi lama (Qt 5) |

Versi macOS minimum dihitung otomatis oleh CI dari semua biner di dalam aplikasi
(`tools/macos_min_version.py`) dan ditulis ke `Info.plist`, jadi macOS yang terlalu lama
menampilkan pesan yang jelas, bukan crash. Setiap build juga dijalankan sekali di CI (`--selftest`)
sebelum diunggah.

Tidak didukung: Windows XP/Vista dan macOS 10.12 ke bawah (tidak ada Python/Qt modern yang
berjalan di sana). Untuk Windows 7, pastikan pembaruan Windows terpasang (terutama *KB2999226*,
Universal C Runtime). Build Windows 7/8 dan macOS 10.13–10.15 sudah lolos uji di CI, tetapi belum
dicoba di perangkat fisik dengan OS tersebut.

- **Windows:** ekstrak zip, buka folder `Koreksi LJK`, jalankan `Koreksi LJK.exe`.
  Pertama kali muncul *“Windows protected your PC”* → klik **More info → Run anyway**.
- **Mac:** ekstrak zip, pindahkan `Koreksi LJK.app` ke folder Applications.
  Pertama kali: **klik kanan → Open → Open**. Kalau muncul *“rusak/damaged”*, jalankan
  `xattr -cr "/Applications/Koreksi LJK.app"` di Terminal, lalu buka lagi.

Aplikasi berjalan offline sepenuhnya; scan LJK tidak dikirim ke mana pun.

## Cara pakai

1. **Template** (sekali per jenis LJK)
   Scan satu LJK **kosong** → *Template baru* → tarik kotak di sekeliling tiap kelompok bulatan soal
   (mis. soal 1–25) dan kelompok nomor peserta → periksa titik biru tepat di tengah bulatan → *Simpan*.
2. **Koreksi**
   Pilih template, isi kunci jawaban (ketik `ABCDE…`/`1.A 2.C…`, atau *Baca kunci dari scan LJK* yang diisi kunci),
   atur poin benar/salah/kosong, (opsional) daftar siswa `nomor, nama`, pilih folder scan → *Mulai koreksi*.
3. **Hasil**
   Lembar bertanda ⚠ perlu dicek (jawaban ganda, isian tipis, nomor peserta tak terbaca, dll).
   Klik untuk melihat gambar beranotasi, betulkan bila perlu, klik *Sudah dicek*. Lalu *Ekspor ke Excel*
   (sheet **Rekap** + **Per Soal**). Hasil juga tersimpan otomatis di `hasil_koreksi_ljk.json` dalam folder scan,
   jadi bisa dilanjutkan kapan saja (berkas baru saja yang dikoreksi).

### Tips scan

- 200–300 dpi, **grayscale**, format JPG/PNG/TIFF atau PDF (multi-halaman didukung).
- Matikan *auto-crop* / *auto-enhance* yang berlebihan bila hasilnya aneh. Miring sedikit dan terbalik 180° tidak masalah.
- Template harus dari LJK **yang sama persis** dengan yang dikoreksi (cetakan/versi berbeda → buat template baru).

## Cara kerja (ringkas)

`koreksi_ljk/omr.py` — inti pembacaan, terpisah dari tampilan:

1. Deteksi otomatis bulatan/oval pada LJK kosong; blok yang ditandai pengguna diubah menjadi grid posisi bulatan.
2. Tiap scan diselaraskan ke template (fitur ORB + RANSAC, diperhalus ECC) → tak perlu penanda sudut khusus.
3. Kegelapan tiap bulatan diukur relatif terhadap kertas di sekitarnya, **dikurangi kegelapan cetakan bulatan yang sama
   di template kosong**, lalu dibandingkan dengan ambang yang dihitung per lembar.
4. Jawaban ganda, tipis, atau bekas hapusan ditandai untuk dicek manusia, bukan ditebak diam-diam.

## Pengembangan

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                 # versi lama: requirements-legacy-dev.txt (Python 3.8)
python run.py                                        # jalankan aplikasi

python -m pytest tests -q                            # 97 unit test (inti + GUI offscreen)
python tests/make_synthetic.py tests/data            # buat LJK & scan sintetis
python tests/bench_accuracy.py                       # benchmark akurasi
python tests/bench_stress.py                         # pensil tipis / isian setengah / miring / 150 dpi
python tests/gui_smoke.py /tmp/shots                 # tangkapan layar GUI (offscreen)
```

| Berkas tes | Isi |
|---|---|
| `tests/test_io.py` | Format JPG/PNG/BMP/TIFF/WebP/GIF, PDF & TIFF multi-halaman, TIFF 16-bit, RGBA, nama berkas Unicode, berkas kosong/rusak/terlalu kecil, berkas tersembunyi macOS |
| `tests/test_key_grade.py` | Format kunci (berurutan, bernomor, huruf kecil, baris judul ikut ditempel), huruf di luar pilihan LJK, penilaian & poin minus |
| `tests/test_template.py` | Deteksi bulatan, tebakan baris/kolom, posisi grid vs cetakan, semua jenis blok, simpan/muat, template versi lama/baru |
| `tests/test_read.py` | Akurasi, rotasi 90°/180°/3.5°, 150–480 dpi, scan gelap, isian tipis/setengah tidak pernah salah diam-diam, lembar kosong, dokumen salah, aturan nomor peserta, blok nama & isian, LJK kosong dari scan terisi |
| `tests/test_app.py` | Editor template, impor/ekspor, dialog blok, status kunci, cache template, koreksi folder dengan berkas rusak, lanjutkan berkas baru, edit hasil, Excel, kompatibilitas Qt 5/6 |

CI (`.github/workflows/build.yml`) menjalankan semua tes di Linux, Windows 10/11, macOS Intel & Apple Silicon,
serta kombinasi pustaka versi lama (Python 3.8 + Qt 5, Windows 32/64-bit, macOS Intel). Setelah itu CI membuat
6 build dan mengujinya dengan `--selftest`. Push tag `v*` (mis. `v0.1.0`) untuk melampirkan build ke Releases.
