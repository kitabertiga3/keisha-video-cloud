"""Autonomous daily Keisha content plan + guarded Buffer schedule.

Cloudflare Workers AI writes the script. GitHub Actions handles rendering separately.
There is no hidden fallback to fabricated AI or a second automatic Buffer retry.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
from datetime import datetime, date, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

WIB = ZoneInfo('Asia/Jakarta')
SLOTS = ('18:30', '19:00', '20:00')
TOPICS = (
    'Memilih target audiens sebelum membuat konten',
    'Bedakan edukasi, promosi, dan testimoni dalam affiliate',
    'Mengenali masalah audiens sebelum menyebut produk',
    'Cara menulis hook jujur untuk video singkat',
    'Menghindari klaim penghasilan instan di konten',
    'Menyusun jadwal ide konten untuk pemula',
    'Mengukur hasil konten tanpa terpaku pada views',
    'Cara menyeleksi produk digital secara kritis',
    'Tiga pertanyaan sebelum mempromosikan ebook',
    'Membuat satu ide menjadi video 45 detik',
    'CTA yang memberi pilihan alih-alih mendesak pembeli',
    'Mengapa konten sederhana sering lebih jelas',
    'Cara menjaga konsistensi tanpa spam',
    'Perbaiki konten dari pertanyaan penonton',
    'Pahami bahwa affiliate tidak menjamin penghasilan',
    'Konten bermanfaat yang membuat orang ingin menyimpan video',
    'Membangun kepercayaan tanpa angka palsu',
    'Memilih topik konten berdasarkan kebutuhan pemula',
    'Membedakan fitur produk dan manfaat terverifikasi',
    'Mendesain adegan tanpa menjejalkan banyak tulisan',
    'Membuat riset ringan dari pengalaman belajar sendiri',
    'Cara menguji tiga pilihan judul video',
    'Memilih satu media sosial dulu ketika belajar',
    'Cara menyusun checklist konten sebelum publikasi',
    'Mengenali target video edukasi vs promosi',
    'Pentingnya transparansi tautan affiliate',
    'Membuat caption TikTok yang tidak berlebihan',
    'Membuat judul YouTube Shorts yang jelas',
    'Mendaur ulang topik dengan sudut pandang baru',
    'Cara mengevaluasi konten mingguan secara realistis',
)
BAD = re.compile(r'[\[\]{}]|"(?:headings|bodies|cta)"\s*:|\b(?:gaya|suara|musik)\s*:|(?:,\s*){2,}', re.I)


def day_topic(day: date) -> str:
    return TOPICS[(day.toordinal() - 1) % len(TOPICS)]


def extract_ai_text(value: dict) -> str:
    """Read both legacy Workers AI and current chat-completion response shapes.

    Never manufacture a script when the provider returns no text.
    """
    if not isinstance(value, dict) or value.get('success') is not True:
        raise RuntimeError('Workers AI mengembalikan status gagal.')
    result = value.get('result')
    if isinstance(result, str) and result.strip():
        return result.strip()
    if isinstance(result, dict):
        for key in ('response', 'output_text', 'text'):
            text = result.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
            # JSON Mode can return a parsed response object instead of a string.
            if isinstance(text, dict) and text:
                return json.dumps(text, ensure_ascii=False)
        # Current Workers AI chat-completion models return result.choices[].message.content.
        choices = result.get('choices', [])
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                msg = choice.get('message') or {}
                if not isinstance(msg, dict):
                    continue
                text = msg.get('content')
                if isinstance(text, str) and text.strip():
                    return text.strip()
                if isinstance(text, list):
                    pieces = [item.get('text', '') for item in text
                              if isinstance(item, dict) and item.get('type') == 'text'
                              and isinstance(item.get('text'), str)]
                    if ''.join(pieces).strip():
                        return ''.join(pieces).strip()
        keys = ','.join(sorted(str(k) for k in result.keys()))
    else:
        keys = type(result).__name__
    # Include only structural metadata, never generated text or credentials.
    first = (result.get('choices') or [None])[0] if isinstance(result, dict) else None
    finish = first.get('finish_reason') if isinstance(first, dict) else None
    raise AIEmptyResponseError('Workers AI tidak mengembalikan teks naskah; '
                               'bentuk hasil: ' + keys + '; finish_reason=' + str(finish))


class AIEmptyResponseError(RuntimeError):
    """Provider returned HTTP 200 but no usable final text."""


def ai_request(messages: list[dict]) -> str:
    token = os.environ.get('CLOUDFLARE_AI_API_TOKEN', '').strip()
    account = os.environ.get('CLOUDFLARE_ACCOUNT_ID', '').strip()
    if not token or not re.fullmatch(r'[a-fA-F0-9]{32}', account):
        raise RuntimeError('Perlu CLOUDFLARE_AI_API_TOKEN dan CLOUDFLARE_ACCOUNT_ID di GitHub Secrets.')
    # Use an active non-reasoning model supporting Cloudflare Workers AI JSON Mode.
    # Gemma 4 sometimes returns HTTP 200 with empty choices[].message.content.
    # This changes only GitHub Keisha planning, not the Cloudflare Telegram Worker.
    model = '@cf/meta/llama-3.3-70b-instruct-fp8-fast'
    endpoint = f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}'
    payload = {'messages': messages, 'max_tokens': 3000,
               'response_format': {'type': 'json_object'},
               'temperature': 0.35, 'stream': False}
    req = urllib.request.Request(endpoint, method='POST',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=110) as response:
            value = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Workers AI gagal HTTP {exc.code} (model={model}); '
                           'cek model/izin/kuota. Tidak melakukan posting.') from None
    except urllib.error.URLError:
        raise RuntimeError('Workers AI tidak dapat dihubungi.') from None
    return extract_ai_text(value)


def parse_json_reply(text: str) -> dict:
    raw = text.strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw, flags=re.I).strip()
    start = raw.find('{')
    if start < 0:
        raise ValueError('AI tidak mengirim JSON.')
    data, pos = json.JSONDecoder().raw_decode(raw[start:])
    if raw[start + pos:].strip():
        raise ValueError('AI menambahkan teks di belakang JSON.')
    if not isinstance(data, dict):
        raise ValueError('Naskah bukan objek JSON.')
    return data


def clean_string(v: object, limit: int, field: str) -> str:
    if not isinstance(v, str):
        raise ValueError(f'{field} harus berupa teks.')
    v = ' '.join(v.split()).strip()
    if not 10 <= len(v) <= limit:
        # Give useful diagnostics without leaking the model's unreviewed text.
        raise ValueError(f'{field}: panjang {len(v)} karakter; wajib 10-{limit}.')
    if BAD.search(v):
        raise ValueError(f'{field}: mengandung tanda kurung siku/kurawal atau format terlarang.')
    return v


OFFICIAL_AFFILIATE_LINK = 'lynk.id/dirgakhaa'
AFFILIATE_DISCLOSURE = 'Tautan afiliasi.'
OTHER_LINK = re.compile(r'(?i)(?:https?://|www\.)[^\s]+|\b[\w-]+\.(?:com|id|net|org|co)/[^\s]+')


def complete_caption(value: object, platform: str) -> str:
    """Append the verified profile URL and affiliate disclosure, not invented sales claims.

    This is deterministic caption metadata, not a fabricated AI script. Reject
    unexpected external links rather than publishing a potentially wrong URL.
    """
    if not isinstance(value, str):
        raise ValueError(f'{platform}: caption harus berupa teks.')
    caption = ' '.join(value.split()).strip()
    if not caption:
        raise ValueError(f'{platform}: caption kosong.')
    for match in OTHER_LINK.finditer(caption):
        if OFFICIAL_AFFILIATE_LINK not in match.group(0).lower():
            raise ValueError(f'{platform}: caption mengandung tautan yang bukan link profil resmi.')
    if OFFICIAL_AFFILIATE_LINK not in caption.lower():
        caption += ' Cek info: ' + OFFICIAL_AFFILIATE_LINK + '.'
    if not re.search(r'\b(?:afiliasi|affiliate)\b', caption, re.I):
        caption += ' ' + AFFILIATE_DISCLOSURE
    return caption


# Tautan asli hanya untuk caption. Video/voice cukup arahkan ke bio.
_VIDEO_AFFILIATE_RE = re.compile(
    r'(?i)(?:(?:link|tautan)\s+(?:di\s+)?(?:profil|bio)\s*[:\-]?\s*)?'
    r'(?:https?://)?(?:www\.)?lynk\.id/dirgakhaa/?'
)


def normalize_video_copy(value: object) -> object:
    """Perbaikan editorial aman: jangan membacakan URL atau menaruhnya di slide.

    Link afiliasi yang benar tetap disimpan dalam captions terpisah.
    """
    if not isinstance(value, str):
        return value
    text = _VIDEO_AFFILIATE_RE.sub('link bio', value)
    text = re.sub(r'(?i)\b(?:link|tautan)\s+(?:di\s+)?profil\b', 'link bio', text)
    text = re.sub(r'(?i)\blink\s+di\s+bio\b', 'link bio', text)
    text = re.sub(r'\s+([.,;:!?])', r'\1', ' '.join(text.split()))
    return text.strip()


def normalize_saved_plan(data: dict) -> dict:
    validated = validate_plan(data)
    return {**data, **validated}


def validate_plan(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError('Rencana bukan JSON object.')
    heads, bodies = data.get('headings'), data.get('bodies')
    if not isinstance(heads, list) or not isinstance(bodies, list) or len(heads) != 5 or len(bodies) != 5:
        raise ValueError('Naskah harus 5 judul dan 5 isi berbeda.')
    h = [clean_string(normalize_video_copy(x), 68, f'heading {i}') for i, x in enumerate(heads, 1)]
    # Toleransi panjang aman untuk teks yang masih dibungkus oleh render_studio.wrap.
    # Prompt tetap meminta naskah singkat; jangan menolak scene yang hanya lewat 4 karakter.
    b = [clean_string(normalize_video_copy(x), 220, f'body {i}') for i, x in enumerate(bodies, 1)]
    for i, scene in enumerate(b, 1):
        # Reject slogans masquerading as 40-60 second educational narration.
        if (len(scene) < 75 or len(scene.split()) < 11 or
                len(set(re.findall(r'\w+', scene.lower()))) < 7):
            raise ValueError(f'body {i} terlalu singkat/umum; '
                             'minimal 75 karakter dan 11 kata dengan langkah atau contoh konkret.')
    if any(OTHER_LINK.search(x) for x in [*h, *b]):
        raise ValueError('Naskah video mengandung URL lain yang belum disetujui.')
    if len(set(x.lower() for x in h)) != 5 or len(set(x.lower() for x in b)) != 5:
        raise ValueError('Naskah mengulang adegan.')
    cta = clean_string(normalize_video_copy(data.get('cta')), 56, 'cta')
    if OTHER_LINK.search(cta):
        raise ValueError('CTA video mengandung URL lain yang belum disetujui.')
    captions = data.get('captions')
    if not isinstance(captions, dict):
        raise ValueError('Caption tiap platform tidak ada.')
    c = {
        p: clean_string(complete_caption(captions.get(p), p),
                        620 if p != 'youtube' else 320, p)
        for p in ('tiktok', 'facebook', 'youtube')
    }
    if any(OFFICIAL_AFFILIATE_LINK not in v.lower() for v in c.values()):
        raise ValueError('Caption harus mencantumkan tautan profil resmi.')
    hhmm = data.get('posting_time')
    if hhmm not in SLOTS:
        raise ValueError('Jam posting harus salah satu slot yang disetujui.')
    reason = clean_string(data.get('reason'), 200, 'alasan')
    return {'headings': h, 'bodies': b, 'cta': cta, 'captions': c,
            'posting_time': hhmm, 'reason': reason}


def plan_for_day(today: date) -> dict:
    focus = day_topic(today)
    system = ("Kamu adalah tim editorial Ruang Cuan Digital: Naya (riset), Nadia (strategi), "
              "Fajar (naskah), Citra (TikTok), Raka (YouTube Shorts), Arga (Facebook), "
              "Bagas (QC), Rina (koordinasi). Gunakan penilaian kritis, bukan mengaku "
              "punya data insight real-time. Tuliskan konten Indonesia natural 5 adegan vertikal, "
              "bermanfaat, 40-60 detik, kalimat singkat. Produk hanya diketahui: "
              "Ebook Cuan dari Rumah Rp149.000, tautan profil lynk.id/dirgakhaa; "
              "JANGAN mengarang isi ebook, testimoni, diskon, hasil, atau keuntungan. "
              "Dilarang janjikan cuan. Caption berbeda per platform, transparan affiliate. "
              "Di judul, adegan, dan CTA hanya katakan 'cek link bio'; JANGAN "
              "tulis atau eja alamat lynk.id dalam narasi atau teks video. "
              "Alamat lynk.id/dirgakhaa hanya boleh di captions. "
              "Tanpa karakter JSON di isi teks. "
              "Balas HANYA satu objek JSON valid (tanpa markdown/penjelasan) berisi: "
              "headings (5 string UNIK, masing-masing 15-55 karakter), "
              "bodies (5 string UNIK, target 100-160 karakter dan minimal 15 kata; " 
              "batas maksimum kelonggaran 220 karakter per adegan), "
              "WAJIB isi 5 adegan berurutan: adegan 1 masalah/hook spesifik, "
              "adegan 2 penyebab yang dapat dijelaskan, adegan 3 contoh tindakan pertama, "
              "adegan 4 contoh tindakan kedua, adegan 5 langkah praktis penutup. "
              "Setiap isi adegan harus menjelaskan sesuatu yang bisa langsung dipraktikkan, "
              "bukan slogan. JANGAN tulis 'Konten harus menarik', 'Visual lebih berdampak', "
              "'Konten bermanfaat sangat penting', atau kalimat generik sejenis. "
              "cta (string 15-45 karakter), "
              "captions (objek tiktok, facebook, youtube; tiap caption 40-250 karakter "
              "dan HARUS menyebut link profil atau profil), "
              "posting_time (PERSIS salah satu 18:30, 19:00, 20:00), "
              "reason (string 20-150 karakter). "
              "Jangan pakai kurung siku/kurawal di DALAM nilai teks, label Gaya:/Suara:/Musik:, "
              "atau koma berturut-turut. "
              "Pilih jam berdasarkan HIPOTESIS audiens, bukan klaim analytics real-time. "
              "Jangan memakai kutipan di teks video.")
    question = f'Tanggal: {today.isoformat()}. Tema unik hari ini: {focus}. Buat rencana konten lengkap.'
    messages = [{'role':'system','content':system},{'role':'user','content':question}]
    # The AI can occasionally produce overlong headings or invalid JSON.
    # Regenerate at most twice; never silently truncate, fabricate, or publish bad content.
    for attempt in range(1, 4):
        answer = ''
        try:
            answer = ai_request(messages)
            plan = validate_plan(parse_json_reply(answer))
        except (ValueError, AIEmptyResponseError) as exc:
            reason = str(exc)
            print(f'Rencana AI belum lolos QC (percobaan {attempt}/3): {reason}', file=sys.stderr)
            if attempt == 3:
                raise RuntimeError('Naskah AI gagal validasi setelah tiga percobaan: '
                                   + reason + '. Tidak ada video/posting yang dijalankan.') from None
            messages = [
                {'role':'system','content':system},
                {'role':'user','content':question},
                {'role':'assistant','content':answer[:7000] if isinstance(answer, str) else ''},
                {'role':'user','content':'Draf di atas ditolak QC: ' + reason +
                 '. TULIS ULANG objek JSON yang sama, perbaiki kolom bermasalah. '
                 'Untuk bodies, setiap adegan wajib 75-220 karakter dan 11 kata, '
                 'berisi tips/contoh konkret sesuai tema dan tidak generik. '
                 'Jaga semua fakta/tautan tetap akurat. Hanya kirim JSON valid.'},
            ]
            continue
        plan['date'] = today.isoformat()
        plan['theme'] = focus
        return plan
    raise RuntimeError('Validasi naskah tidak selesai.')


def due_at(today: date, hhmm: str, now: datetime | None = None) -> datetime:
    if hhmm not in SLOTS:
        raise ValueError('Slot posting tidak dikenal')
    hour, minute = map(int, hhmm.split(':'))
    due = datetime(today.year, today.month, today.day, hour, minute, tzinfo=WIB)
    if now is None:
        now = datetime.now(WIB)
    if due < now.astimezone(WIB) + timedelta(minutes=45):
        raise ValueError('Slot posting sudah terlalu dekat/terlewat. Jangan memposting terlambat atau mengulang.')
    return due.astimezone(timezone.utc)


def telegram_report(text: str, *, optional: bool = True) -> None:
    token = os.getenv('TELEGRAM_KEISHA_TOKEN', '').strip()
    chat = os.getenv('TELEGRAM_CHAT_ID', '').strip()
    if chat and chat != HEADQUARTERS_CHAT_ID:
        print('Peringatan: Telegram destination bukan AI AFFILIATE OFFICE | HQ. Tidak mengirim ke grup lain.', file=sys.stderr)
        return
    if not token or not chat:
        if not optional: raise RuntimeError('Token pelaporan Telegram belum tersedia.')
        return
    req = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendMessage',
        method='POST', data=urllib.parse.urlencode({'chat_id': chat, 'text': text[:3500]}).encode())
    try:
        with urllib.request.urlopen(req, timeout=20): pass
    except (urllib.error.URLError, TimeoutError):
        print('Peringatan: laporan Telegram tidak berhasil dikirim.', file=sys.stderr)


def schedule_all(plan: dict, video: Path, metadata: Path, run_id: int, result_path: Path, *, publish_now: bool = False) -> dict:
    # External writes only occur after every preflight passes.
    base = Path(__file__).resolve().parents[1] / 'Keisha_Video_Cloud_Starter_v1'
    sys.path.insert(0, str(base))
    import social_drafts as s
    m = s.validate_metadata(metadata)
    video_info = s.validate_video(video, m)
    if (m['headings'] != plan['headings'] or m['bodies'] != plan['bodies']
            or m['cta'] != plan['cta']):
        raise ValueError('Metadata video tidak cocok dengan naskah AI yang disetujui.')
    if not os.getenv('BUFFER_API_KEY'):
        raise RuntimeError('BUFFER_API_KEY belum tersedia.')
    when = None if publish_now else due_at(date.fromisoformat(plan['date']), plan['posting_time'])
    channels = s.get_channels(os.environ['BUFFER_API_KEY'])
    # A pre-existing Cloudinary object may already have been sent to Buffer in
    # another run. Never re-upload/re-schedule on an ambiguous partial result.
    # Persist a same-date failure receipt for audit and team_ops instead.
    try:
        url = upload_daily_once(video, plan['date'])
    except RuntimeError as exc:
        if 'KUNCI ANTI-SPAM' not in str(exc):
            raise
        outcome = {'date': plan['date'], 'video': video_info,
                   'status': 'manual_review', 'published': False,
                   'due_at_utc': when.isoformat() if when else None, 'posts': {},
                   'errors': [{'platform': 'all',
                               'error': 'ExistingDailyMedia',
                               'detail': 'Media already exists in Cloudinary. Verify Buffer and the daily receipt manually; no new posting attempted.'}]}
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(outcome, indent=2, ensure_ascii=False),
                               encoding='utf-8')
        return outcome
    outcome = {'date': plan['date'], 'video': video_info, 'status': 'partial', 'mode': 'publish_now' if publish_now else 'schedule',
               'due_at_utc': when.isoformat() if when else None, 'cloudinary_url': url, 'posts': {}, 'errors': []}
    for service in ('tiktok','facebook','youtube'):
        try:
            if publish_now:
                post = s.save_publish_now_post(
                    os.environ['BUFFER_API_KEY'], channels[service], url,
                    plan['captions'][service], platform=service,
                    title=plan['headings'][0])
            else:
                post = s.save_scheduled_post(
                    os.environ['BUFFER_API_KEY'], channels[service], url,
                    plan['captions'][service], platform=service,
                    title=plan['headings'][0],
                    due_at=when.strftime('%Y-%m-%dT%H:%M:%S.000Z'))
            outcome['posts'][service] = post
        except Exception as exc:
            outcome['errors'].append({'platform':service, 'error':type(exc).__name__,
                                      'detail':str(exc)[:220]})
        finally:
            # Durable partial record before any subsequent platform mutation.
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(json.dumps(outcome, indent=2, ensure_ascii=False),
                                   encoding='utf-8')
    outcome['status'] = ('submitted' if publish_now else 'scheduled') if len(outcome['posts']) == 3 and not outcome['errors'] else 'manual_review'
    result_path.parent.mkdir(parents=True,exist_ok=True)
    result_path.write_text(json.dumps(outcome,indent=2,ensure_ascii=False),encoding='utf-8')
    return outcome


def upload_daily_once(video: Path, day: str) -> str:
    import cloudinary
    import cloudinary.api
    import cloudinary.uploader
    fields = ('CLOUDINARY_CLOUD_NAME','CLOUDINARY_API_KEY','CLOUDINARY_API_SECRET')
    if any(not os.getenv(x) for x in fields):
        raise RuntimeError('Cloudinary Secrets belum tersedia.')
    cloudinary.config(cloud_name=os.environ[fields[0]],api_key=os.environ[fields[1]],
                      api_secret=os.environ[fields[2]],secure=True)
    public_id = 'keisha-autopilot/' + day
    try:
        cloudinary.api.resource(public_id, resource_type='video')
    except cloudinary.api.NotFound:
        pass
    else:
        raise RuntimeError('KUNCI ANTI-SPAM: video tanggal ini sudah pernah diunggah. Dilarang membuat posting kedua.')
    uploaded = cloudinary.uploader.upload(str(video), resource_type='video',folder='keisha-autopilot',
                                          public_id=day, overwrite=False,unique_filename=False)
    url = uploaded.get('secure_url','')
    if not url.startswith('https://res.cloudinary.com/') or '/video/upload/' not in url:
        raise RuntimeError('Cloudinary gagal memberi URL video publik yang sesuai.')
    return url


def drafts_all(plan: dict, video: Path, metadata: Path, result_path: Path) -> dict:
    """Store up to 3 Buffer drafts, never schedule or publish.

    Use one deterministic Cloudinary resource per calendar date as a guard
    against accidentally duplicating a partly completed run. When something
    fails after upload, do not retry automatically: inspect Buffer manually.
    """
    base = Path(__file__).resolve().parents[1]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    from Keisha_Video_Cloud_Starter_v1 import social_drafts as s

    checked = normalize_saved_plan(plan)
    if any(plan.get(key) != checked[key] for key in ('headings','bodies','cta','captions')):
        raise ValueError('Rencana belum dinormalisasi; jangan unggah video lama yang berisi URL.')
    day = date.fromisoformat(plan['date'])
    metadata_data = s.validate_metadata(metadata)
    verified_video = s.validate_video(video, metadata_data)
    if (metadata_data['headings'] != checked['headings']
            or metadata_data['bodies'] != checked['bodies']
            or metadata_data['cta'] != checked['cta']):
        raise ValueError('Metadata video tidak cocok dengan naskah AI. Upload dibatalkan.')

    token = os.environ.get('BUFFER_API_KEY','').strip()
    if not token:
        raise RuntimeError('BUFFER_API_KEY belum tersedia; draf tidak dibuat.')
    channels = s.get_channels(token)
    if set(channels) != {'tiktok','facebook','youtube'}:
        raise RuntimeError('Tiga channel Buffer belum lengkap; draf tidak dibuat.')

    # Identitas harian, bukan GitHub Run ID; rerun hari yang sama tak buat draf ulang.
    daily_id = int(day.strftime('%Y%m%d'))
    output = {'date': day.isoformat(), 'status': 'pending', 'mode': 'drafts',
              'published': False, 'scheduled': False, 'video': verified_video,
              'drafts': {}, 'errors': []}
    def persist() -> None:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')

    # Only this step uploads the verified MP4 to public Cloudinary media hosting.
    url = s.upload(video, daily_id)
    output['cloudinary_url'] = url
    persist()
    for platform in ('tiktok', 'facebook', 'youtube'):
        try:
            pid = s.save_draft(token, channels[platform], url, checked['captions'][platform],
                               platform=platform, title=checked['headings'][0])
            output['drafts'][platform] = {'id': pid, 'status': 'draft'}
        except Exception as err:
            output['errors'].append({'platform': platform, 'error': type(err).__name__,
                                     'detail': str(err)[:240]})
        finally:
            persist()

    output['status'] = 'drafts_created' if len(output['drafts']) == 3 else 'manual_review'
    persist()
    if output['errors']:
        raise RuntimeError('Sebagian draf gagal; lihat artifact. '
                           'Jangan ulangi workflow otomatis agar draf tidak ganda.')
    return output


def reconcile_failed_drafts(plan: dict, previous_result: dict, *, create_missing: bool = False) -> dict:
    """Inspect failed Facebook/YouTube drafts from the original job without media upload.

    Recovery only after a complete duplicate scan. TikTok is never written.
    Running an audit does not call Buffer createPost.
    """
    base = Path(__file__).resolve().parents[1]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    from Keisha_Video_Cloud_Starter_v1 import social_drafts as s

    checked = normalize_saved_plan(plan)
    if previous_result.get('date') != checked.get('date'):
        raise ValueError('Tanggal rencana dan laporan sebelumnya berbeda.')
    if previous_result.get('mode') != 'drafts':
        raise ValueError('Laporan sumber bukan mode drafts.')
    url = str(previous_result.get('cloudinary_url') or '')
    if not (url.startswith('https://res.cloudinary.com/') and '/video/upload/' in url
            and '/keisha-drafts/run-' in url):
        raise ValueError('Tautan video Cloudinary dari hasil sebelumnya tidak valid.')
    if not (previous_result.get('drafts', {}).get('tiktok', {}).get('id')):
        raise ValueError('Tidak ada ID draf TikTok; hentikan untuk mencegah duplikat.')
    token = os.getenv('BUFFER_API_KEY', '').strip()
    if not token:
        raise RuntimeError('BUFFER_API_KEY tidak tersedia.')
    channels = s.get_channels(token)
    if not all(p in channels for p in ('tiktok', 'facebook', 'youtube')):
        raise RuntimeError('Channel Buffer tidak lengkap.')

    outcome = {'date': checked['date'], 'mode': 'recover_drafts' if create_missing else 'audit_drafts',
               'published': False, 'scheduled': False, 'tiktok': {
                   'id': previous_result['drafts']['tiktok']['id'],
                   'action': 'untouched'}, 'channels': {}, 'errors': []}
    # Complete BOTH scans before creating any post; unknown responses fail closed.
    for platform in ('facebook', 'youtube'):
        matches = s.find_matching_posts(token, channels[platform], checked['captions'][platform], url)
        outcome['channels'][platform] = {'matches': matches,
                                          'action': 'existing' if matches else 'missing'}
    if not create_missing:
        return outcome
    for platform in ('facebook', 'youtube'):
        if outcome['channels'][platform]['matches']:
            continue
        try:
            pid = s.save_draft(token, channels[platform], url, checked['captions'][platform],
                               platform=platform, title=checked['headings'][0])
            outcome['channels'][platform]['action'] = 'created'
            outcome['channels'][platform]['id'] = pid
        except Exception as err:
            outcome['channels'][platform]['action'] = 'manual_review'
            outcome['errors'].append({'platform': platform, 'detail': str(err)[:250]})
    if outcome['errors']:
        outcome['status'] = 'manual_review'
    else:
        outcome['status'] = 'reconciled'
    return outcome


def audit_live_drafts(audit_date: str, known_tiktok_draft_id: str = '') -> dict:
    """Read-only audit from Cloudinary and Buffer. Never requires a GitHub artifact."""
    base = Path(__file__).resolve().parents[1]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    from Keisha_Video_Cloud_Starter_v1 import social_drafts as s
    import cloudinary
    import cloudinary.api

    day = date.fromisoformat(audit_date)
    if audit_date != day.isoformat():
        raise ValueError('Format audit date harus YYYY-MM-DD.')
    fields = ('CLOUDINARY_CLOUD_NAME','CLOUDINARY_API_KEY','CLOUDINARY_API_SECRET')
    missing = [k for k in fields + ('BUFFER_API_KEY',) if not os.getenv(k, '').strip()]
    if missing:
        raise RuntimeError('Konfigurasi audit tidak tersedia: ' + ', '.join(missing))
    cloudinary.config(cloud_name=os.environ[fields[0]], api_key=os.environ[fields[1]],
                      api_secret=os.environ[fields[2]], secure=True)
    identifier = 'keisha-drafts/run-' + day.strftime('%Y%m%d')
    media = cloudinary.api.resource(identifier, resource_type='video')
    url = str(media.get('secure_url') or '')
    if (media.get('public_id') != identifier
            or not url.startswith('https://res.cloudinary.com/')
            or '/video/upload/' not in url):
        raise RuntimeError('Cloudinary tidak mengembalikan video sumber yang diharapkan.')

    token = os.environ['BUFFER_API_KEY']
    channels = s.get_channels(token)
    required = ('tiktok','facebook','youtube')
    if not all(platform in channels for platform in required):
        raise RuntimeError('Channel Buffer belum lengkap.')
    output = {'mode':'audit_drafts', 'date':day.isoformat(),
              'cloudinary_public_id': identifier, 'cloudinary_url':url,
              'published':False, 'scheduled':False, 'writes_performed':False,
              'channels':{}}
    for platform in required:
        matches = s.find_matching_posts(token, channels[platform], '', url)
        inventory = s.summarize_channel_drafts(token, channels[platform], day.isoformat())
        output['channels'][platform] = {
            'matches_by_original_url': matches,
            'draft_inventory': inventory,
            'status': ('matched_url' if matches else
                       'draft_candidates_found' if inventory['created_on_audit_date']
                       else 'not_verified')}
    if known_tiktok_draft_id:
        post = s.read_post_by_id(token, known_tiktok_draft_id)
        output['known_tiktok_draft'] = post
        if post.get('reachable', True):
            if str(post.get('channel_id')) != str(channels['tiktok']):
                raise RuntimeError('ID draf lama ternyata milik channel lain.')
            output['channels']['tiktok']['status'] = 'confirmed_by_post_id'
        else:
            # Record missing ID, never assume permission to create a replacement.
            output['channels']['tiktok']['known_id_status'] = post['status']
    output['status'] = 'complete_read_only'
    return output


def preflight_connections() -> dict:
    """Read-only checks before any real posting is enabled.

    No media uploads, Telegram messages, Buffer mutations or scheduled posts.
    """
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from Keisha_Video_Cloud_Starter_v1.social_drafts import get_channels
    required = ('BUFFER_API_KEY', 'CLOUDINARY_CLOUD_NAME',
                'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET')
    missing = [key for key in required if not os.environ.get(key, '').strip()]
    result = {'buffer_channels': [], 'cloudinary_config_present': not any(
        key.startswith('CLOUDINARY_') for key in missing),
        'telegram_reporting_config_present': bool(
            os.getenv('TELEGRAM_KEISHA_TOKEN') and os.getenv('TELEGRAM_CHAT_ID')),
        'ready_to_test_drafts': False}
    if missing:
        raise RuntimeError('Preflight gagal: Secret belum tersedia: ' + ', '.join(missing)
                           + '. Tidak ada upload atau posting.')
    channels = get_channels(os.environ['BUFFER_API_KEY'])
    result['buffer_channels'] = sorted(channels.keys())
    result['ready_to_test_drafts'] = len(channels) == 3
    if not result['ready_to_test_drafts']:
        raise RuntimeError('Preflight gagal: tiga channel Buffer belum lengkap.')
    return result


AUTOPILOT_FLAG = '.github/keisha-autopilot.enabled.json'
AUTOPILOT_RECEIPT_DIR = '.github/keisha-autopilot-receipts'
HEADQUARTERS_CHAT_ID = '-5540202723'


def _github_put_new_file(repo_path: str, data: dict) -> None:
    """Write a small receipt through Actions' scoped GitHub token.

    Refuses to overwrite any existing state; workflows never blindly repeat
    publication after an ambiguous API response.
    """
    token = os.getenv('GITHUB_TOKEN', '').strip()
    repo = os.getenv('GITHUB_REPOSITORY', '')
    if not token or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise RuntimeError('GitHub token/repository tidak tersedia untuk menyimpan status.')
    api = 'https://api.github.com/repos/' + repo + '/contents/' + repo_path
    encoded = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode()).decode()
    body = json.dumps({'message': 'Keisha autopilot: save verified status ' + data.get('date', ''),
                       'content': encoded, 'branch':'main'}).encode()
    req = urllib.request.Request(api, data=body, method='PUT',
        headers={'Authorization': 'Bearer ' + token,
                 'Accept': 'application/vnd.github+json',
                 'User-Agent':'KeishaAutopilot/1.0',
                 'X-GitHub-Api-Version':'2022-11-28',
                 'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        raise RuntimeError('Tidak bisa menyimpan status GitHub (HTTP '
                           + str(exc.code) + '). Jangan ulang posting.') from None
    if status not in (200, 201):
        raise RuntimeError('GitHub tidak mengonfirmasi penyimpanan status.')


def validated_schedule_receipt(path: Path) -> dict:
    result = json.loads(path.read_text(encoding='utf-8'))
    posts = result.get('posts') or {}
    if result.get('status') != 'scheduled' or set(posts) != {'tiktok','facebook','youtube'}:
        raise RuntimeError('Posting belum lengkap 3/3; autopilot tidak boleh diaktifkan.')
    if result.get('errors'):
        raise RuntimeError('Masih ada kesalahan channel; autopilot tetap mati.')
    for service, post in posts.items():
        if not isinstance(post.get('id'), str) or not post['id'].strip():
            raise RuntimeError('ID Buffer hilang pada ' + service)
        if post.get('status') != 'scheduled':
            raise RuntimeError('Buffer belum mengonfirmasi jadwal ' + service)
    expected = datetime.now(WIB).date().isoformat()
    if result.get('date') != expected:
        raise RuntimeError('Tanggal jadwal bukan hari ini. Pencatatan dibatalkan.')
    return {'date':expected,'posts':posts,'due_at_utc':result.get('due_at_utc'),
            'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'status':'scheduled','published':False}


def record_scheduled_receipt(path: Path) -> dict:
    receipt = validated_schedule_receipt(path)
    _github_put_new_file(AUTOPILOT_RECEIPT_DIR + '/' + receipt['date'] + '.json', receipt)
    print('Receipt Buffer 3/3 tersimpan ke repo, tanpa mengulang publikasi.')
    return receipt


def activate_daily_autopilot(path: Path) -> None:
    receipt = validated_schedule_receipt(path)
    # Only after 3/3 posts are accepted AND receipt is committed.
    _github_put_new_file(AUTOPILOT_FLAG,
        {'enabled':True,'date':receipt['date'],
         'first_receipt':AUTOPILOT_RECEIPT_DIR+'/'+receipt['date']+'.json'})
    telegram_report('✅ Keisha Autopilot harian aktif, Bos! Hari ini 3/3 channel '
                    'sudah dijadwalkan Buffer. Besok sistem buat video dan jadwal sendiri. '
                    'Posting belum sama dengan terbit; nanti status dikonfirmasi lagi.')


def summarize_buffer_publication(receipt: dict, reader) -> dict:
    """Read-only verification of each exact Buffer post ID from today's receipt.

    Buffer's 'sent' means delivered by Buffer, not proven live on the destination
    platform. Unknown/missing IDs must never be reported as published.
    """
    expected = ('tiktok', 'facebook', 'youtube')
    posts = receipt.get('posts')
    if not isinstance(posts, dict):
        posts = {}
    statuses = {}
    details = {}
    for platform in expected:
        old = posts.get(platform)
        post_id = old.get('id') if isinstance(old, dict) else None
        if not isinstance(post_id, str) or not post_id.strip():
            statuses[platform] = 'missing_receipt_id'
            details[platform] = {'status': 'missing_receipt_id', 'post_id': None}
            continue
        try:
            current = reader(post_id)
            if not isinstance(current, dict) or current.get('id') != post_id:
                status = 'unverified'
            else:
                status = str(current.get('status') or 'unknown').strip().lower()
            if status not in ('sent', 'scheduled', 'sending', 'error',
                              'draft', 'needs_approval', 'not_found', 'unverified'):
                status = 'unknown'
        except Exception:
            status = 'unverified'
        statuses[platform] = status
        details[platform] = {'status': status, 'post_id': post_id}
    all_sent = all(statuses[p] == 'sent' for p in expected)
    return {'channels': statuses, 'posts': details,
            'buffer_all_sent': all_sent,
            'platform_publication_verified': False,
            'requires_manual_review': not all_sent}


def verify_daily_publication() -> dict:
    """Check Buffer IDs and report truthful delivery status; never post again."""
    base = Path(__file__).resolve().parents[1]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    from Keisha_Video_Cloud_Starter_v1 import social_drafts as s
    day = datetime.now(WIB).date().isoformat()
    path = Path(AUTOPILOT_RECEIPT_DIR) / (day + '.json')
    if not path.is_file():
        telegram_report('⚠️ Keisha: bukti jadwal ' + day + ' belum ditemukan di GitHub. '
                        'Cek GitHub Actions; tidak ada posting ulang.')
        return {'date': day, 'status': 'no_receipt',
                'buffer_all_sent': False, 'platform_publication_verified': False}
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if receipt.get('date') != day:
        raise RuntimeError('Tanggal receipt verifikasi tidak cocok; tidak mengklaim posting berhasil.')
    token = os.getenv('BUFFER_API_KEY', '').strip()
    if not token:
        raise RuntimeError('Token Buffer tidak tersedia saat verifikasi.')
    report = summarize_buffer_publication(
        receipt, lambda post_id: s.read_post_by_id(token, post_id))
    statuses = report['channels']
    message = ('📊 Audit pengiriman Keisha ' + day + ' (BACA SAJA):\n'
               + '\n'.join(p.title() + ': ' + statuses[p]
                           for p in ('tiktok', 'facebook', 'youtube'))
               + ('\n✅ Buffer mengonfirmasi status sent untuk 3/3. '
                  if report['buffer_all_sent'] else
                  '\n⚠️ Ada status belum sent/tidak terverifikasi; periksa Buffer dan akun tujuan. ')
               + 'Sent hanya berarti Buffer mengonfirmasi pengiriman, '
                 'BUKAN bukti video terlihat publik di platform. '
                 'Tidak ada percobaan posting ulang otomatis.')
    telegram_report(message)
    result = {'date': day, 'status': 'buffer_sent' if report['buffer_all_sent']
              else 'needs_review'}
    result.update(report)
    return result

def prepare_recovery_from_manifest(manifest_path: Path, out_dir: Path) -> dict:
    """Restore Run #21 from checked-in metadata and exact original Cloudinary MP4.

    No GitHub Actions artifact needed; this operation is read-only. The original
    media must match the SHA-256 of the previously downloaded Run #21 artifact,
    preventing wrong or transformed videos from being scheduled.
    """
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source = manifest.get('video_url')
    if not isinstance(source,str) or not re.fullmatch(
        r'https://res\.cloudinary\.com/[A-Za-z0-9_-]+/video/upload/[A-Za-z0-9_./-]+\.mp4', source):
        raise RuntimeError('Recovery: tautan video sumber bukan URL Cloudinary MP4 yang diizinkan.')
    expected = manifest.get('source_sha256','').lower()
    if not re.fullmatch(r'[0-9a-f]{64}',expected):
        raise RuntimeError('Recovery: checksum video sumber tidak tersedia.')
    if source != manifest.get('previous_result',{}).get('cloudinary_url'):
        raise RuntimeError('Recovery: URL tidak cocok dengan laporan Run #21.')
    required = ('plan','previous_result','metadata')
    if any(not isinstance(manifest.get(x),dict) for x in required):
        raise RuntimeError('Recovery: metadata Run #21 tidak lengkap.')
    if manifest['plan'].get('date') != manifest['previous_result'].get('date'):
        raise RuntimeError('Recovery: tanggal laporan dan naskah tidak cocok.')
    meta=manifest['metadata']
    if any(meta.get(k) != manifest['plan'].get(k) for k in ('headings','bodies','cta')):
        raise RuntimeError('Recovery: metadata dan naskah Run #21 berbeda.')
    out_dir.mkdir(parents=True,exist_ok=True)
    movie=out_dir/'Keisha_Video_Cloud_Starter_v1'/'hasil'/'keisha-rcd-video.mp4'
    movie.parent.mkdir(parents=True,exist_ok=True)
    temp=movie.with_suffix('.mp4.part')
    digest=hashlib.sha256()
    total=0
    try:
        request=urllib.request.Request(source,headers={'User-Agent':'KeishaRecovery/1.0'})
        with urllib.request.urlopen(request,timeout=60) as response, temp.open('wb') as stream:
            if response.status != 200:
                raise RuntimeError('Recovery: server video tidak mengembalikan HTTP 200.')
            while True:
                block=response.read(65536)
                if not block:
                    break
                total+=len(block)
                if total>90*1024*1024:
                    raise RuntimeError('Recovery: file lebih besar dari batas aman.')
                digest.update(block)
                stream.write(block)
        if total != manifest['source_bytes'] or digest.hexdigest()!=expected:
            raise RuntimeError('Recovery: video Cloudinary tidak identik dengan Run #21. '
                               'Pemulihan dihentikan sebelum posting.')
        temp.replace(movie)
    finally:
        temp.unlink(missing_ok=True)
    files={
        'autopilot_plan.json':manifest['plan'],
        'autopilot_result.json':manifest['previous_result'],
        'Keisha_Video_Cloud_Starter_v1/hasil/metadata.json':meta,
    }
    for relative, data in files.items():
        destination=out_dir/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps(data,indent=2,ensure_ascii=False),
                               encoding='utf-8')
    print('Sumber Run #21 dipulihkan, checksum MP4 sesuai. '
          'Tidak ada unggahan atau jadwal Buffer baru.')
    return {'video_path':str(movie),'sha256':expected,'bytes':total}


def recover_tiktok_run21(plan_path: Path, prior_result_path: Path,
                         video_path: Path, metadata_path: Path,
                         result_path: Path) -> dict:
    """Recover the one missing TikTok slot of Run #21. Never touch FB/YouTube.

    Fail closed if any prior scheduled post is not verifiable, TikTok might
    already be scheduled, Cloudinary recovery asset already exists, or date
    differs. No automatic retries of a partially successful request.
    """
    import subprocess
    base = Path(__file__).resolve().parents[1] / 'Keisha_Video_Cloud_Starter_v1'
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    import social_drafts as sd

    day = datetime.now(WIB).date()
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    prior = json.loads(prior_result_path.read_text(encoding='utf-8'))
    checked = normalize_saved_plan(plan)
    if plan.get('date') != day.isoformat() or prior.get('date') != day.isoformat():
        raise RuntimeError('Tanggal Run #21 bukan hari ini. Pemulihan tidak boleh dijalankan.')
    if prior.get('status') != 'manual_review' or set(prior.get('posts',{})) != {'facebook','youtube'}:
        raise RuntimeError('Laporan sumber bukan kegagalan parsial 2/3 yang diharapkan.')
    if not any(x.get('platform') == 'tiktok' and
               'frame rate' in str(x.get('detail','')).lower()
               for x in prior.get('errors',[])):
        raise RuntimeError('Error sumber tidak sesuai dengan masalah FPS TikTok.')
    for platform in ('facebook','youtube'):
        if prior['posts'][platform].get('status') != 'scheduled':
            raise RuntimeError('Status jadwal terdahulu bukan scheduled pada ' + platform)
    if Path(AUTOPILOT_FLAG).is_file():
        raise RuntimeError('Autopilot sudah aktif; pemulihan manual dibatalkan.')

    # Ensure future slot and known original content before making any write.
    slot = due_at(day, plan['posting_time'])
    metadata = sd.validate_metadata(metadata_path)
    if (metadata['headings'] != checked['headings'] or
            metadata['bodies'] != checked['bodies'] or
            metadata['cta'] != checked['cta']):
        raise RuntimeError('Metadata MP4 berbeda dari naskah Run #21.')
    if not video_path.is_file():
        raise RuntimeError('MP4 sumber Run #21 tidak tersedia.')
    token = os.environ.get('BUFFER_API_KEY','').strip()
    channels = sd.get_channels(token)
    for platform in ('facebook','youtube'):
        post = sd.read_post_by_id(token, prior['posts'][platform]['id'])
        if not post.get('reachable') or post.get('status') not in ('scheduled','sent'):
            raise RuntimeError('Jadwal lama ' + platform + ' tidak dapat diverifikasi.')
        if str(post.get('channel_id')) != str(channels[platform]):
            raise RuntimeError('ID jadwal lama tidak cocok dengan channel ' + platform)
    previous_url = str(prior.get('cloudinary_url') or '')
    if not previous_url.startswith('https://res.cloudinary.com/'):
        raise RuntimeError('URL video Run #21 tidak valid.')

    existing = sd.find_matching_posts(token, channels['tiktok'],
                                      checked['captions']['tiktok'], previous_url)
    if existing:
        raise RuntimeError('TikTok mungkin sudah punya post yang sama. Tidak mengirim ulang.')

    # Re-encode ONLY the pre-existing MP4, preserving the existing narration.
    converted = result_path.parent / 'keisha-run21-tiktok-30fps.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y',
                    '-i',str(video_path),'-vf','fps=30,format=yuv420p',
                    '-c:v','libx264','-preset','veryfast','-crf','24',
                    '-c:a','copy','-movflags','+faststart',str(converted)],
                    check=True,timeout=240)
    info = sd.validate_video(converted,metadata)
    if info['fps'] < 29 or info['fps'] > 31:
        raise RuntimeError('QC video 30 FPS tidak lolos.')

    import cloudinary
    import cloudinary.api
    import cloudinary.uploader
    required = ('CLOUDINARY_CLOUD_NAME','CLOUDINARY_API_KEY','CLOUDINARY_API_SECRET')
    if any(not os.getenv(k) for k in required):
        raise RuntimeError('Cloudinary credentials tidak lengkap.')
    cloudinary.config(cloud_name=os.environ[required[0]],
                      api_key=os.environ[required[1]],
                      api_secret=os.environ[required[2]],secure=True)
    asset_id = 'keisha-autopilot/' + day.isoformat() + '-tiktok-30fps'
    try:
        cloudinary.api.resource(asset_id, resource_type='video')
    except cloudinary.api.NotFound:
        pass
    else:
        raise RuntimeError('Video pemulihan sudah ada di Cloudinary. STOP untuk mencegah duplikat.')

    output = {'date':day.isoformat(),'mode':'recover_tiktok','status':'pending',
              'video':info,'posts':dict(prior['posts']),'errors':[],
              'recovered_from_run_id':44657550853,
              'due_at_utc':slot.isoformat(),'published':False}
    result_path.parent.mkdir(parents=True,exist_ok=True)
    result_path.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding='utf-8')
    upload = cloudinary.uploader.upload(str(converted),resource_type='video',
                         folder='keisha-autopilot',
                         public_id=day.isoformat()+'-tiktok-30fps',
                         overwrite=False,unique_filename=False)
    url = upload.get('secure_url','')
    if not url.startswith('https://res.cloudinary.com/') or '/video/upload/' not in url:
        raise RuntimeError('Cloudinary belum mengonfirmasi MP4 pemulihan. Jangan ulang.')
    output['recovery_url'] = url
    result_path.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding='utf-8')
    try:
        post = sd.save_scheduled_post(token,channels['tiktok'],url,
                        checked['captions']['tiktok'],platform='tiktok',
                        title=checked['headings'][0],
                        due_at=slot.strftime('%Y-%m-%dT%H:%M:%S.000Z'))
        output['posts']['tiktok'] = post
        output['status']='scheduled'
    except Exception as exc:
        output['status']='manual_review'
        output['errors'].append({'platform':'tiktok','error':type(exc).__name__,
                                 'detail':str(exc)[:250]})
    finally:
        result_path.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding='utf-8')
    if output['errors']:
        raise RuntimeError('TikTok recovery gagal; cek artifact, JANGAN ulang otomatis.')
    telegram_report('✅ Keisha: TikTok sudah dijadwalkan untuk ' +plan['posting_time']+
                    ' WIB dengan MP4 30 FPS. Facebook & YouTube tidak disentuh. '
                    'Ini status antrean, belum konfirmasi tayang.')
    return output


def check_reporting_ready() -> None:
    """Fail before rendering or publishing if HQ notification cannot be routed."""
    if not os.getenv('TELEGRAM_KEISHA_TOKEN', '').strip():
        raise RuntimeError('TELEGRAM_KEISHA_TOKEN belum terpasang. Posting dibatalkan.')
    if os.getenv('TELEGRAM_CHAT_ID', '').strip() != HEADQUARTERS_CHAT_ID:
        raise RuntimeError('TELEGRAM_CHAT_ID wajib menunjuk grup AI AFFILIATE OFFICE | HQ. '
                           'Posting dibatalkan agar laporan tidak salah grup.')
    if (os.getenv('RUN_MODE') == 'go_live'
            and Path(AUTOPILOT_FLAG).is_file()):
        raise RuntimeError('Autopilot harian sudah aktif. Jangan jalankan go_live dua kali.')
    print('Pelaporan HQ siap. Tidak ada pesan Telegram yang dikirim pada tahap ini.')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('plan','preflight','drafts','audit_drafts','recover_drafts','schedule','record','activate','verify','check_reporting','prepare_recovery','recover_tiktok','report_failure'))
    p.add_argument('--plan',default='autopilot_plan.json')
    p.add_argument('--video',default='Keisha_Video_Cloud_Starter_v1/hasil/keisha-rcd-video.mp4')
    p.add_argument('--metadata',default='Keisha_Video_Cloud_Starter_v1/hasil/metadata.json')
    p.add_argument('--result',default='autopilot_result.json')
    p.add_argument('--previous-result',default='previous_autopilot_result.json')
    p.add_argument('--recovery-manifest',default='autopilot/recovery/2026-11-20-run21.json')
    p.add_argument('--recovery-dir',default='run21')
    p.add_argument('--audit-date',default='2026-11-20')
    p.add_argument('--known-tiktok-draft-id',default='')
    args=p.parse_args()
    if args.action=='plan':
        today=datetime.now(WIB).date()
        plan=plan_for_day(today)
        Path(args.plan).write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'Rencana AI lengkap untuk {today}, tema: {plan["theme"]}, slot: {plan["posting_time"]} WIB.')
    elif args.action=='preflight':
        status=preflight_connections()
        Path(args.result).write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
        print('PRE-FLIGHT BACA SAJA: tiga channel Buffer tersedia; '
              'Cloudinary credentials ada. Tidak ada posting atau upload.')
    elif args.action=='drafts':
        plan=json.loads(Path(args.plan).read_text(encoding='utf-8'))
        result=drafts_all(plan, Path(args.video), Path(args.metadata), Path(args.result))
        print('Berhasil menyiapkan', len(result['drafts']), 'DRAF di Buffer. '
              'Tidak ada jadwal atau posting yang dibuat.')
    elif args.action=='audit_drafts':
        try:
            result=audit_live_drafts(args.audit_date, args.known_tiktok_draft_id)
        except Exception as exc:
            result={'mode':'audit_drafts','date':args.audit_date,'status':'blocked',
                    'writes_performed':False,'detail':str(exc)[:300]}
            Path(args.result).write_text(json.dumps(result,ensure_ascii=False,indent=2),
                                         encoding='utf-8')
            raise
        Path(args.result).write_text(json.dumps(result,ensure_ascii=False,indent=2),
                                     encoding='utf-8')
        print('Audit langsung dari Cloudinary dan Buffer selesai: ',
              ', '.join(k+':'+v['status'] for k,v in result['channels'].items()),
              '; tidak ada posting, upload, atau pembuatan draf.')
    elif args.action=='recover_drafts':
        raise RuntimeError('Pemulihan draf masih dinonaktifkan sampai audit langsung'
                           ' Buffer selesai dan sudah diperiksa.')
    elif args.action=='prepare_recovery':
        prepare_recovery_from_manifest(Path(args.recovery_manifest),Path(args.recovery_dir))
    elif args.action=='recover_tiktok':
        recover_tiktok_run21(Path(args.plan),Path(args.previous_result),
                             Path(args.video),Path(args.metadata),Path(args.result))
    elif args.action=='check_reporting':
        check_reporting_ready()
    elif args.action in ('record','activate','verify'):
        if args.action=='record':
            record_scheduled_receipt(Path(args.result))
        elif args.action=='activate':
            activate_daily_autopilot(Path(args.result))
        else:
            status=verify_daily_publication()
            Path(args.result).write_text(json.dumps(status,ensure_ascii=False,indent=2),
                                         encoding='utf-8')
    elif args.action=='schedule':
        plan=json.loads(Path(args.plan).read_text(encoding='utf-8'))
        if plan.get('date')!=datetime.now(WIB).date().isoformat():
            raise RuntimeError('Naskah bukan untuk hari ini. Tidak dijadwalkan.')
        result=schedule_all(plan,Path(args.video),Path(args.metadata),int(os.environ.get('GITHUB_RUN_ID','0')),Path(args.result))
        telegram_report('📋 Laporan AI Office ' + plan['date'] + '\n'
          'Naya/Nadia/Fajar: Naskah disusun.\nKeisha/Bagas: MP4 diperiksa.\n'
          'Citra (TikTok), Arga (Facebook), Raka (YouTube): '+str(len(result['posts']))+'/3 jadwal tersimpan.\n'
          'Jam rencana: '+plan['posting_time']+' WIB.\n'
          'STATUS: '+('TERJADWAL di Buffer, BELUM terbukti terbit.' if result['status']=='scheduled' else 'PERLU PERBAIKAN MANUAL; JANGAN ULANGI OTOMATIS.' ))
        if result['errors']:
            raise RuntimeError('Ada channel gagal. Periksa artifact hasil, jangan tekan ulang schedule.')
    else:
        # After partial scheduling, main() already sent a channel-specific alert.
        receipt_path=Path(args.result)
        if receipt_path.exists():
            try:
                prev=json.loads(receipt_path.read_text(encoding='utf-8'))
                if prev.get('status') in ('manual_review','scheduled'):
                    return
            except (ValueError, OSError):
                pass
        telegram_report('⚠️ Keisha Autopilot berhenti sebelum selesai. '
                        'Cek GitHub Actions; sistem TIDAK mengulang posting otomatis.')

if __name__=='__main__':
    main()