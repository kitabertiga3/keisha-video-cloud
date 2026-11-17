# Keisha Video Cloud — Ruang Cuan Digital

Prototipe pembuat video MP4 faceless **20 detik, 5 slide, vertikal 720×1280, tanpa suara**, dijalankan di Render Web Service. Tidak ada akses media sosial, Lynk.id, Cloudflare ataupun token Telegram. Proyek ini menguji pembuatan MP4 tanpa PC lokal. **Belum otomatis membuat voice-over, mengirim ke grup Telegram, atau posting.**

## Langkah 1. Unggah ke GitHub

Di repository `kitabertiga3/keisha-video-cloud` (Public), pilih **Add file → Upload files**. Unggah **isi** folder ini (termasuk `Dockerfile`, `server.py`, `video_engine.py`, `index.html`, `requirements.txt`, dan folder `assets/rcd_logo.png`), lalu Commit. Jangan mengunggah ZIP mentah sebagai satu file. Jika `README.md` sudah ada, jangan pilih README baru saat upload; boleh biarkan README lama.

## Langkah 2. Render gratis tanpa konektor Git

1. Render → **New Web Service** → tab **Public Git Repository**.
2. URL repository: `https://github.com/kitabertiga3/keisha-video-cloud`.
3. Pilih branch `main` dan Runtime **Docker** (Dockerfile di root repository), region terdekat, Instance Type **Free** jika tersedia. Nama layanan mis. `keisha-video-cloud`.
4. Tambahkan Environment variable **KEISHA_API_KEY** dengan nilai acak **minimal 32 karakter** dari password manager. **Jangan kirim kunci tersebut kepada orang lain atau taruh di repository.**
5. Create Web Service / Deploy. Tunggu hingga statusnya Live. Jika Render meminta kartu, berhenti dan evaluasi opsi lain, jangan isi asal.
6. Buka URL `https://<nama-service>.onrender.com/`. Masukkan KEISHA_API_KEY dan tekan **Buat MP4 di Cloud**. Unduh MP4 ketika selesai.

**Catatan penting:** Untuk public Git repository, Render mungkin memerlukan **Manual Deploy** saat source berubah, bukan auto-deploy. Render Free dapat tidur setelah ~15 menit tanpa traffic, cold-start beberapa saat dan penyimpanannya sementara. Jika server restart saat video dibuat, pekerjaan dapat gagal. Jangan gunakan sebagai satu-satunya sumber penyimpanan hasil; perlu R2 di tahap lanjut.

## Konsep keamanan

- Semua route yang membuat/mengunduh video butuh kunci di Header `Authorization: Bearer ...`.
- Kunci tidak disimpan di GitHub dan tidak pernah dikirim di query URL.
- Maksimum satu render aktif. Tidak tersedia upload file. Batasi konten sendiri dan jangan mempublikasikan link service sembarangan.
- Mesin ini tidak terhubung ke sistem Cloudflare/D1/Telegram lama dan tidak mengubahnya.

## Uji offline (opsional)

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python server.py
```

Generator memerlukan `ffmpeg` dan `ffprobe` pada PATH; tersedia dari Dockerfile. Buka `http://localhost:10000/` dan set `KEISHA_API_KEY` di environment sebelum menjalankan server.
