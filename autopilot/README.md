# AI Office Autopilot (opsional, default MATI)

**Status:** fitur dijalankan secara manual lebih dulu. Jadwal harian hanya aktif setelah GitHub repository variable `AUTOPILOT_ENABLED` diset ke `true` oleh pemilik.

Jadwal 08.17 WIB: AI Cloudflare menyusun script -> Keisha merender 5 adegan bersuara Pocket TTS dan musik -> cek audio/metadata dan teks -> Cloudinary -> Buffer menjadwalkan satu video per channel TikTok, Facebook Page, YouTube Shorts untuk pukul 18.30/19.00/20.00 WIB sesuai saran AI.

Peran dalam workflow: Naya (riset), Nadia (strategi), Fajar (naskah), Keisha (produksi), Bagas (QC), Citra (TikTok), Arga (Facebook), Raka (YouTube Shorts), Rina (koordinasi). **Peran di sini adalah pembagian tanggung jawab dalam rangkaian pemanggilan AI dan program GitHub, belum percakapan terpisah dari 13 akun bot Telegram.** Bot Cloudflare lama masih perlu pembaruan terpisah untuk mengubah label Instagram milik Raka.

**Secret tambahan yang diperlukan** untuk mode `plan` atau `schedule`:

- `CLOUDFLARE_ACCOUNT_ID` — Account ID Cloudflare, bukan API key, disimpan di GitHub Actions Secrets.
- `CLOUDFLARE_AI_API_TOKEN` — token terbatas hanya izin Account > Workers AI > Read. Jangan gunakan token Global API Key.

Gunakan juga secret lama: `BUFFER_API_KEY`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `TELEGRAM_KEISHA_TOKEN`, `TELEGRAM_CHAT_ID`.

Cara uji: Actions -> `Keisha - AI Office Autopilot Harian (AMAN)` -> Run workflow -> `check` (tidak ada API/MP4/post). Setelah ada dua secret AI, jalankan `plan` (membuat rencana AI saja). Hanya setelah lulus dan konten diperiksa, pilih `schedule` untuk uji end-to-end, yang **benar-benar menjadwalkan** publikasi. Aktifkan jadwal harian dengan Actions variable `AUTOPILOT_ENABLED=true` setelah uji posting terverifikasi.

**Anti-spam:** hanya satu pelaporan Telegram pada akhir jadwal dan paling banyak satu pesan kegagalan. Cloudinary menyimpan video dengan ID tanggal; bila ID itu sudah ada, ulangan workflow tidak memposting kedua kali. Kegagalan parsial tidak diulang otomatis; tinjau `autopilot_result.json`.

**Batasan penting:** ini tidak memeriksa analytics real-time, tidak membuktikan video telah benar-benar terbit; Buffer hanya mengonfirmasi terjadwal. GitHub schedule bisa terlambat. Harga dan promosi ditulis tanpa menjanjikan penghasilan. Tidak gratis tanpa batas: Cloudflare AI, GitHub Actions, Cloudinary, dan Buffer memiliki kuota atau batas paket.