"""Authenticated, single-job prototype for on-demand video rendering on Render."""
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from video_engine import build_video

ROOT = Path(__file__).parent
JOBS = {}
LOCK = threading.Lock()
MAX_AGE = 1800
DEFAULT_HEADINGS = [
    'JANGAN ASAL PILIH PRODUK DIGITAL!',
    'VIRAL BELUM TENTU COCOK',
    'SIAPA YANG MEMBUTUHKAN?',
    'MASALAH APA YANG MAU DIBANTU?',
    'RISET DULU SEBELUM PROMOSI',
]
DEFAULT_BODIES = [
    'Kalau baru mulai bisnis online, jangan memilih produk hanya karena tren.',
    'Produk yang sedang populer belum tentu cocok untuk setiap calon pembeli.',
    'Cari tahu target pembeli dan kebutuhan mereka, bukan menebak-nebak.',
    'Periksa informasi produk dan pastikan manfaatnya relevan dengan kebutuhan.',
    'Baca deskripsi dan aturan affiliate. Untuk referensi bacaan, cek ebook Cuan dari Rumah.',
]
DEFAULT_CTA = 'Lihat detail ebook di link bio'


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('Format data tidak valid')
    headings = data.get('headings', DEFAULT_HEADINGS)
    bodies = data.get('bodies', DEFAULT_BODIES)
    cta = data.get('cta', DEFAULT_CTA)
    if not isinstance(headings, list) or not isinstance(bodies, list) or len(headings) != 5 or len(bodies) != 5:
        raise ValueError('Harus ada tepat 5 judul dan 5 isi slide')
    for s in headings:
        if not isinstance(s, str) or not (1 <= len(s.strip()) <= 85) or '\n' in s:
            raise ValueError('Judul slide harus 1-85 karakter tanpa baris baru')
    for s in bodies:
        if not isinstance(s, str) or not (1 <= len(s.strip()) <= 155) or '\n' in s:
            raise ValueError('Isi slide harus 1-155 karakter tanpa baris baru')
    if not isinstance(cta, str) or not (1 <= len(cta.strip()) <= 60) or '\n' in cta:
        raise ValueError('CTA harus 1-60 karakter')
    return [s.strip() for s in headings], [s.strip() for s in bodies], cta.strip()


def cleanup():
    now = time.time()
    with LOCK:
        for job_id, job in list(JOBS.items()):
            if job['state'] != 'working' and now - job['created'] > MAX_AGE:
                del JOBS[job_id]
                job['temp'].cleanup()


def worker(job_id, headings, bodies, cta):
    job = JOBS[job_id]
    try:
        video = build_video(job['folder'], headings, bodies, cta)
        with LOCK:
            job.update(state='done', path=video)
    except Exception:
        with LOCK:
            job.update(state='error', error='Gagal membuat video. Cek log layanan atau ringkas teks lalu coba lagi.')


class Handler(BaseHTTPRequestHandler):
    server_version = 'KeishaCloud/1.0'

    def respond(self, code, data, content_type='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def auth(self):
        key = os.environ.get('KEISHA_API_KEY', '')
        if len(key) < 32:
            self.respond(503, {'error': 'KEISHA_API_KEY belum dikonfigurasi di Render (min 32 karakter)'})
            return False
        supplied = self.headers.get('Authorization', '')
        if not hmac.compare_digest(supplied, f'Bearer {key}'):
            self.respond(401, {'error': 'Kunci akses salah'})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            contents = (ROOT / 'index.html').read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(contents)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(contents)
            return
        if path == '/healthz':
            self.respond(200, {'ok': True, 'service': 'Keisha cloud demo', 'video': 'silent MP4', 'social_posting': False})
            return
        if not self.auth():
            return
        match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})(/video)?', path)
        if not match:
            self.respond(404, {'error': 'Endpoint tidak ditemukan'})
            return
        cleanup()
        job = JOBS.get(match.group(1))
        if not job:
            self.respond(404, {'error': 'Video tidak ditemukan atau sudah kedaluwarsa'})
            return
        if match.group(2) == '/video':
            if job['state'] != 'done':
                self.respond(409, {'error': 'Video belum siap'})
                return
            p = job['path']
            size = p.stat().st_size
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Content-Length', str(size))
            self.send_header('Content-Disposition', 'attachment; filename="keisha-rcd-video.mp4"')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            with p.open('rb') as f:
                while block := f.read(65536):
                    self.wfile.write(block)
            return
        self.respond(200, {'id': match.group(1), 'state': job['state'], 'error': job.get('error'), 'download': f"/api/jobs/{match.group(1)}/video" if job['state'] == 'done' else None})

    def do_POST(self):
        if urlsplit(self.path).path != '/api/render':
            self.respond(404, {'error': 'Endpoint tidak ditemukan'})
            return
        if not self.auth():
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 1 <= length <= 15000:
                raise ValueError('Ukuran permintaan tidak sesuai')
            payload = json.loads(self.rfile.read(length))
            headings, bodies, cta = validate(payload)
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            self.respond(400, {'error': str(exc)})
            return
        cleanup()
        with LOCK:
            if any(j['state'] == 'working' for j in JOBS.values()):
                self.respond(429, {'error': 'Satu video sedang diproduksi. Coba lagi setelah selesai.'})
                return
            folder = tempfile.TemporaryDirectory(prefix='keisha-')
            jid = secrets.token_hex(16)
            JOBS[jid] = {'created': time.time(), 'state': 'working', 'folder': folder.name, 'temp': folder}
        threading.Thread(target=worker, args=(jid, headings, bodies, cta), daemon=True).start()
        self.respond(202, {'id': jid, 'state': 'working'})


def main():
    port = int(os.environ.get('PORT', '10000'))
    print(f'Keisha Cloud listening on {port}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()


if __name__ == '__main__':
    main()
