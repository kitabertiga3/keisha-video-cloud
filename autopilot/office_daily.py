"""Autonomous daily Keisha content plan + guarded Buffer schedule.

Cloudflare Workers AI writes the script. GitHub Actions handles rendering separately.
There is no hidden fallback to fabricated AI or a second automatic Buffer retry.
"""
from __future__ import annotations

import argparse
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


def validate_plan(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError('Rencana bukan JSON object.')
    heads, bodies = data.get('headings'), data.get('bodies')
    if not isinstance(heads, list) or not isinstance(bodies, list) or len(heads) != 5 or len(bodies) != 5:
        raise ValueError('Naskah harus 5 judul dan 5 isi berbeda.')
    h = [clean_string(x, 68, f'heading {i}') for i, x in enumerate(heads, 1)]
    b = [clean_string(x, 145, f'body {i}') for i, x in enumerate(bodies, 1)]
    for i, scene in enumerate(b, 1):
        # Reject slogans masquerading as 40-60 second educational narration.
        if len(scene) < 75 or len(scene.split()) < 11:
            raise ValueError(f'body {i} terlalu singkat/umum; '
                             'minimal 75 karakter dan 11 kata dengan langkah atau contoh konkret.')
    if len(set(x.lower() for x in h)) != 5 or len(set(x.lower() for x in b)) != 5:
        raise ValueError('Naskah mengulang adegan.')
    cta = clean_string(data.get('cta'), 56, 'cta')
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
              "CTA mengajak lihat info di link profil. Tanpa karakter JSON di isi teks. "
              "Balas HANYA satu objek JSON valid (tanpa markdown/penjelasan) berisi: "
              "headings (5 string UNIK, masing-masing 15-55 karakter), "
              "bodies (5 string UNIK, masing-masing 95-135 karakter DAN minimal 15 kata), "
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
                 'Untuk bodies, setiap adegan wajib minimal 75 karakter dan 11 kata, '
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
    if not token or not chat:
        if not optional: raise RuntimeError('Token pelaporan Telegram belum tersedia.')
        return
    req = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendMessage',
        method='POST', data=urllib.parse.urlencode({'chat_id': chat, 'text': text[:3500]}).encode())
    try:
        with urllib.request.urlopen(req, timeout=20): pass
    except (urllib.error.URLError, TimeoutError):
        print('Peringatan: laporan Telegram tidak berhasil dikirim.', file=sys.stderr)


def schedule_all(plan: dict, video: Path, metadata: Path, run_id: int, result_path: Path) -> dict:
    # External writes only occur after every preflight passes.
    base = Path(__file__).resolve().parents[1] / 'Keisha_Video_Cloud_Starter_v1'
    sys.path.insert(0, str(base))
    import social_drafts as s
    m = s.validate_metadata(metadata)
    video_info = s.validate_video(video, m)
    if m['headings'] != plan['headings'] or m['bodies'] != plan['bodies']:
        raise ValueError('Metadata video tidak cocok dengan naskah AI yang disetujui.')
    if not os.getenv('BUFFER_API_KEY'):
        raise RuntimeError('BUFFER_API_KEY belum tersedia.')
    when = due_at(date.fromisoformat(plan['date']), plan['posting_time'])
    channels = s.get_channels(os.environ['BUFFER_API_KEY'])
    # Lock by deterministic calendar date, not GitHub run ID. Reruns will refuse to re-post.
    url = upload_daily_once(video, plan['date'])
    outcome = {'date': plan['date'], 'video': video_info, 'status': 'partial',
               'due_at_utc': when.isoformat(), 'cloudinary_url': url, 'posts': {}, 'errors': []}
    for service in ('tiktok','facebook','youtube'):
        q = ('mutation { createPost(input: {'
             f'text: {json.dumps(plan["captions"][service], ensure_ascii=False)}, '
             f'channelId: {json.dumps(channels[service])}, '
             'schedulingType: automatic, mode: customScheduled, '
             f'dueAt: {json.dumps(when.strftime("%Y-%m-%dT%H:%M:%S.000Z"))}, '
             f'assets: [{{video: {{url: {json.dumps(url)}}}}}]'
             '}) { ... on PostActionSuccess { post { id dueAt status } } '
             '... on MutationError { message } } }')
        try:
            o = s.graphql(os.environ['BUFFER_API_KEY'], q).get('createPost') or {}
            pid = (o.get('post') or {}).get('id')
            if not pid: raise RuntimeError(str(o.get('message','Buffer menolak jadwal'))[:180])
            outcome['posts'][service] = {'id': pid, 'state': (o.get('post') or {}).get('status')}
        except Exception as e:
            outcome['errors'].append({'platform':service,'error':type(e).__name__})
    outcome['status'] = 'scheduled' if len(outcome['posts']) == 3 else 'manual_review'
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


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('plan','schedule','report_failure'))
    p.add_argument('--plan',default='autopilot_plan.json')
    p.add_argument('--video',default='Keisha_Video_Cloud_Starter_v1/hasil/keisha-rcd-video.mp4')
    p.add_argument('--metadata',default='Keisha_Video_Cloud_Starter_v1/hasil/metadata.json')
    p.add_argument('--result',default='autopilot_result.json')
    args=p.parse_args()
    if args.action=='plan':
        today=datetime.now(WIB).date()
        plan=plan_for_day(today)
        Path(args.plan).write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'Rencana AI lengkap untuk {today}, tema: {plan["theme"]}, slot: {plan["posting_time"]} WIB.')
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
        telegram_report('⚠️ AI Office otomatis gagal pada satu tahap. Tidak ada percobaan posting ulang. Periksa GitHub Actions. Status kanal yang berhasil mungkin sudah terjadwal.')

if __name__=='__main__':
    main()