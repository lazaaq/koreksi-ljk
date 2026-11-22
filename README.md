# Koreksi LJK

Aplikasi desktop (Windows & macOS) untuk mengoreksi LJK pilihan ganda dari hasil scanner, satu folder sekaligus.
Bisa dipakai untuk **LJK jenis apa pun** lewat template yang dibuat sekali dari scan LJK kosong.

## Unduh & pasang

Buka tab **Actions** (build terbaru) atau **Releases** di repo ini, lalu unduh:

| Laptop | Berkas |
|---|---|
| Windows | `Koreksi-LJK-Windows.zip` |
| Mac Apple Silicon (M1/M2/M3/M4) | `Koreksi-LJK-macOS-AppleSilicon.zip` |
| Mac Intel | `Koreksi-LJK-macOS-Intel.zip` |

- **Windows:** ekstrak zip, buka folder `Koreksi LJK`, jalankan `Koreksi LJK.exe`.
  Pertama kali muncul *“Windows protected your PC”* → klik **More info → Run anyway**.
- **Mac:** ekstrak zip, pindahkan `Koreksi LJK.app` ke folder Applications.
  Pertama kali: **klik kanan → Open → Open**. Kalau tetap ditolak, buka *System Settings → Privacy & Security* lalu klik **Open Anyway**.

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
pip install -r requirements-dev.txt
python run.py                                        # jalankan aplikasi

python tests/make_synthetic.py tests/data            # buat LJK & scan sintetis
python tests/test_accuracy.py                        # uji akurasi
python tests/test_stress.py                          # uji pensil tipis / miring / 150 dpi
python tests/gui_smoke.py /tmp/shots                 # uji GUI + tangkapan layar (offscreen)
```

Build `.exe`/`.app` dibuat otomatis oleh GitHub Actions (`.github/workflows/build.yml`) setiap push ke `main`;
push tag `v*` (mis. `v0.1.0`) untuk melampirkannya ke halaman Releases.
