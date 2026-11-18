"""Ruang Cuan Digital | Keisha Studio v3.4.
Narasi Piper gratis + musik instrumental ORIGINAL, adaptif, pelan dan ducking.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import urllib.error
import urllib.request

from PIL import Image, ImageDraw, ImageFont
from render_custom import parse_script, clip_words
from music_engine import choose_mood, generate_music

ROOT = Path(__file__).resolve().parent
OUT = (ROOT / 'hasil').resolve()
LOGO = ROOT / 'assets' / 'rcd_logo.png'
W, H = 720, 1280
STYLES = ('majalah', 'neon', 'poster', 'kartu', 'minimal', 'diagonal')
MOTIFS = ('ide', 'buku', 'ponsel', 'grafik', 'target', 'cek', 'bintang', 'hadiah', 'komunitas', 'roket')
ACCENTS = ('#FEC854', '#57DAD0', '#FA8B70', '#7C72E9', '#8FCB89', '#F1B4E5')


def valid_accent(value, fallback):
    if isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        return tuple(int(value[x:x+2], 16) for x in (1, 3, 5))
    return fallback


def script_visuals(raw):
    """Read the optional Narska art direction without changing the old parser."""
    try:
        raw = os.environ.get('VIDEO_VISUALS', '').strip() or raw
        obj = json.loads(raw)
        if not isinstance(obj, (dict, list)):
            return []
        visuals = obj if isinstance(obj, list) else obj.get('visuals', [])
        return visuals if isinstance(visuals, list) else []
    except (ValueError, TypeError):
        return []


def storyboard(raw, style, seed):
    """Return five explicit scene designs; automatic mode varies EACH slide."""
    proposed = script_visuals(raw)
    ordered = list(STYLES)
    random.Random(seed).shuffle(ordered)
    results = []
    for n in range(5):
        info = proposed[n] if n < len(proposed) and isinstance(proposed[n], dict) else {}
        picked_style = ordered[n] if style == 'otomatis' else style
        if style == 'otomatis' and info.get('style') in STYLES:
            # Narska can select a unique scene style; resolve duplicates to keep variation.
            candidate = info['style']
            if candidate not in [x['style'] for x in results]:
                picked_style = candidate
            elif picked_style in [x['style'] for x in results]:
                picked_style = next(s for s in STYLES if s not in [x['style'] for x in results])
        elif style == 'otomatis' and picked_style in [x['style'] for x in results]:
            picked_style = next(s for s in STYLES if s not in [x['style'] for x in results])
        motif = str(info.get('motif', '')).lower().strip()
        if motif not in MOTIFS:
            motif = MOTIFS[(seed + n*3) % len(MOTIFS)]
        accent = info.get('accent')
        if not isinstance(accent, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', accent):
            accent = ACCENTS[(seed + n) % len(ACCENTS)]
        results.append({'style':picked_style, 'motif':motif, 'accent':accent})
    return results


def draw_motif(draw, kind, color, bg, n):
    """Simple, original vector visuals drawn on each slide (no external assets)."""
    cx,cy=581,177
    draw.rounded_rectangle((cx-66,cy-66,cx+65,cy+65),radius=28,fill=bg,outline=color,width=4)
    def line(points,width=7): draw.line(points,fill=color,width=width,joint='curve')
    if kind == 'buku':
        draw.polygon([(cx-42,cy-29),(cx-2,cy-22),(cx-2,cy+33),(cx-42,cy+24)],outline=color)
        line([(cx-42,cy-29),(cx-42,cy+24),(cx-2,cy+33),(cx+1,cy-22),(cx+42,cy-29),(cx+42,cy+24),(cx+1,cy+33)],5)
    elif kind == 'ponsel':
        draw.rounded_rectangle((cx-25,cy-44,cx+25,cy+45),radius=10,outline=color,width=7)
        line([(cx-12,cy+31),(cx+12,cy+31)],5)
    elif kind == 'grafik':
        line([(cx-44,cy+31),(cx-16,cy+5),(cx+9,cy+16),(cx+41,cy-28)],9)
        line([(cx+18,cy-29),(cx+41,cy-28),(cx+40,cy-5)],6)
    elif kind == 'target':
        for r in (43,27,10): draw.ellipse((cx-r,cy-r,cx+r,cy+r),outline=color,width=5)
    elif kind == 'cek':
        draw.rounded_rectangle((cx-39,cy-33,cx+40,cy+34),radius=13,outline=color,width=6)
        line([(cx-23,cy),(cx-6,cy+17),(cx+27,cy-19)],8)
    elif kind == 'bintang':
        pts=[]
        for k in range(10):
            a=-math.pi/2+k*math.pi/5;r=43 if k%2==0 else 19
            pts.append((cx+int(math.cos(a)*r),cy+int(math.sin(a)*r)))
        draw.polygon(pts,outline=color);line(pts+[pts[0]],4)
    elif kind == 'hadiah':
        draw.rectangle((cx-37,cy-8,cx+37,cy+36),outline=color,width=6)
        draw.rectangle((cx-44,cy-24,cx+44,cy-7),outline=color,width=6)
        line([(cx,cy-24),(cx,cy+36)],6)
        draw.ellipse((cx-26,cy-45,cx-1,cy-23),outline=color,width=5)
        draw.ellipse((cx+1,cy-45,cx+26,cy-23),outline=color,width=5)
    elif kind == 'komunitas':
        for x,y,r in ((cx-22,cy-22,13),(cx+22,cy-22,13),(cx,cy+11,16)):
            draw.ellipse((x-r,y-r,x+r,y+r),outline=color,width=5)
        line([(cx-37,cy+27),(cx-37,cy+40),(cx+37,cy+40),(cx+37,cy+27)],5)
    elif kind == 'roket':
        draw.ellipse((cx-17,cy-39,cx+24,cy+24),outline=color,width=6)
        draw.ellipse((cx-6,cy-18,cx+12,cy),outline=color,width=4)
        line([(cx-24,cy+36),(cx-13,cy+19),(cx+20,cy+31)],6)
    else:  # ide
        draw.ellipse((cx-29,cy-40,cx+29,cy+18),outline=color,width=7)
        line([(cx-15,cy+21),(cx+15,cy+21)],7)
        line([(cx-13,cy+35),(cx+13,cy+35)],7)
    draw.text((cx-44,cy+72),f'IDE {n:02}',font=font(16,True),fill=color)

FONT_DIR = Path('/usr/share/fonts/truetype/dejavu')


def ff(*args, timeout=180):
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', *map(str, args)], check=True, timeout=timeout)


def duration(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
                            check=True, capture_output=True, text=True, timeout=12)
    return float(result.stdout.strip())


def font(size, bold=False):
    preferred = FONT_DIR / ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')
    if preferred.is_file():
        return ImageFont.truetype(str(preferred), size)
    return ImageFont.truetype('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf', size)


def wrap(draw, text, width, maxlines, maxsize, minsize=20, bold=False):
    text = re.sub(r'\s+', ' ', str(text)).strip()
    for size in range(maxsize, minsize-1, -2):
        f = font(size, bold)
        lines, line = [], ''
        for word in text.split():
            candidate = (line + ' ' + word).strip()
            if draw.textbbox((0, 0), candidate, font=f)[2] <= width:
                line = candidate
            else:
                if line: lines.append(line)
                line = word
        if line: lines.append(line)
        if len(lines) <= maxlines and all(draw.textbbox((0, 0), t, font=f)[2] <= width for t in lines):
            return lines, f
    # Guard against long unbroken words; shrink instead of crashing the production run.
    f = font(minsize, bold)
    words = []
    for word in text.split():
        if draw.textbbox((0, 0), word, font=f)[2] > width:
            word = word[:max(8, int(len(word)*width/max(1, draw.textbbox((0,0),word,font=f)[2])))]
        words.append(word)
    lines = []
    for word in words:
        if not lines or draw.textbbox((0, 0), lines[-1]+' '+word, font=f)[2] > width:
            lines.append(word)
        else:
            lines[-1] += ' '+word
    return lines[:maxlines], f


def multiline(d, words, f, x, y, fill, spacing=1.23):
    lineh = int(f.size * spacing)
    for text in words:
        d.text((x, y), text, font=f, fill=fill, stroke_width=0)
        y += lineh
    return y


def make_gradient(c1, c2):
    im = Image.new('RGB', (W, H), c1)
    d = ImageDraw.Draw(im)
    for y in range(0, H, 4):
        f = y / (H-1)
        rgb = tuple(int(a*(1-f)+b*f) for a,b in zip(c1,c2))
        d.rectangle((0,y,W,min(y+4,H)),fill=rgb)
    return im


def badge_logo(im, dark=False):
    d = ImageDraw.Draw(im)
    fg = (14,27,50) if dark else (248,248,249)
    accent = (255,188,64)
    if LOGO.exists():
        with Image.open(LOGO) as logo:
            logo = logo.convert('RGB').resize((64,64),Image.Resampling.LANCZOS)
            im.paste(logo,(49,48))
    else:
        d.rounded_rectangle((48,48,112,112),radius=13,fill=accent)
        d.text((57,68),'RCD',font=font(19,True),fill=(14,27,50))
    d.text((126,60),'RUANG CUAN',font=font(23,True),fill=fg)
    d.text((128,93),'DIGITAL',font=font(17),fill=accent if not dark else (172,103,12))


def make_card(path, i, heading, body, cta, style, seed, motif="ide", accent_hex="#FEC854"):
    rng = random.Random(seed + i*173)
    navy=(10,24,47); white=(248,248,247); gold=valid_accent(accent_hex, (254,200,84))
    if style=='majalah':
        im=make_gradient((246,240,226),(229,221,205))
        d=ImageDraw.Draw(im)
        d.rectangle((0,0,W,23), fill=(20,31,46))
        d.rectangle((0,215,W,222), fill=(10,24,47))
        d.rectangle((0,1054,W,H), fill=(20,31,46))
        d.text((54,253),f'EDISI • {i:02}/05',font=font(22,True),fill=(142,93,48))
        title_y,body_y=320,695
        title_color, body_color=navy,(68,72,77)
        bodypanel=False; dark=True
    elif style=='neon':
        im=make_gradient((17,12,50),(10,50,66))
        d=ImageDraw.Draw(im)
        for j in range(4):
            x=rng.randrange(-140,630); y=rng.randrange(120,1020); r=rng.randrange(90,250)
            d.ellipse((x,y,x+r,y+r),outline=(50,160,166),width=3)
        d.rounded_rectangle((34,245,686,997),radius=37,fill=(18,30,69),outline=(75,230,218),width=5)
        d.rounded_rectangle((50,1052,670,1133),radius=28,fill=(62,213,201))
        d.text((61,280),f'CREATIVE STORY / {i:02}',font=font(22,True),fill=(80,232,209))
        title_y,body_y=359,666
        title_color,body_color=white,(207,223,233)
        bodypanel=True; dark=False
    elif style=='poster':
        im=make_gradient((241,113,89),(196,56,72))
        d=ImageDraw.Draw(im)
        d.polygon([(0,330),(W,170),(W,720),(0,886)],fill=(19,35,66))
        d.ellipse((510,45,810,345),fill=(255,200,84))
        d.rounded_rectangle((38,713,682,1040),radius=29,fill=(255,233,200))
        d.text((50,303),f'{i:02}. IDE CEPAT',font=font(26,True),fill=gold)
        title_y,body_y=393,776
        title_color,body_color=white,(37,34,42)
        bodypanel=True; dark=False
    elif style=='kartu':
        im=make_gradient((9,34,44),(24,80,83))
        d=ImageDraw.Draw(im)
        for k in range(5):
            x=35+k*137
            d.rounded_rectangle((x,188,x+98,208),radius=8,fill=gold if k==i-1 else (52,99,104))
        d.rounded_rectangle((40,267,680,1058),radius=38,fill=(250,245,228))
        d.rounded_rectangle((64,291,654,353),radius=20,fill=(244,191,71))
        d.text((86,309),f'TIPS NOMOR {i}',font=font(22,True),fill=navy)
        title_y,body_y=395,726
        title_color,body_color=navy,(59,66,67)
        bodypanel=True; dark=False
    elif style=='minimal':
        im=make_gradient((246,248,244),(227,237,230))
        d=ImageDraw.Draw(im)
        d.rectangle((0,0,19,H),fill=(31,139,124))
        d.ellipse((535,190,820,475),fill=(200,224,204))
        d.rectangle((50,295,125,306),fill=(31,139,124))
        d.text((54,323),f'SLIDE {i} / 5',font=font(25,True),fill=(33,136,120))
        title_y,body_y=418,778
        title_color,body_color=navy,(63,82,87)
        bodypanel=False; dark=True
    else: # diagonal
        im=make_gradient((21,34,75),(31,50,105))
        d=ImageDraw.Draw(im)
        d.polygon([(0,280),(W,80),(W,515),(0,725)],fill=(234,196,95))
        d.polygon([(0,1033),(W,827),(W,H),(0,H)],fill=(17,33,59))
        d.rounded_rectangle((43,690,678,1063),radius=30,fill=(245,241,227))
        d.text((53,289),f'IDE {i:02} / 05',font=font(25,True),fill=navy)
        title_y,body_y=390,746
        title_color,body_color=navy,(39,57,69)
        bodypanel=True; dark=False

    # A topic-specific vector illustration provides visual variety beyond typography.
    motif_fg = navy if style in ('majalah', 'poster', 'minimal', 'kartu', 'diagonal') else (89,226,221)
    motif_bg = (255,248,228) if style in ('majalah', 'minimal', 'kartu') else (23,38,75)
    if style == 'poster': motif_bg = (255,221,160)
    if style == 'diagonal': motif_bg = (239,205,115)
    draw_motif(ImageDraw.Draw(im),motif,motif_fg,motif_bg,i)
    # Heading and body both stay inside the safe text area.
    d=ImageDraw.Draw(im)
    max_heading_height=(body_y-title_y-60)
    heading_lines, heading_font=wrap(d,heading,592,4,55,29,True)
    if len(heading_lines)*heading_font.size*1.2>max_heading_height:
        heading_lines, heading_font=wrap(d,heading,592,5,42,25,True)
    end_title=multiline(d,heading_lines,heading_font,63,title_y,title_color,1.18)
    # Body panel and placement differ by design, avoid collisions.
    if style in ('majalah','minimal'):
        d.line((63,body_y-37,642,body_y-37),fill=(212,159,73) if style=='majalah' else (31,139,124),width=5)
    elif style=='neon':
        d.line((64,body_y-35,643,body_y-35),fill=(75,230,218),width=4)
    body_lines, body_font=wrap(d,body,580,7,33,22)
    if len(body_lines)*body_font.size*1.32>215:
        body_lines,body_font=wrap(d,body,580,8,28,21)
    multiline(d,body_lines,body_font,66,body_y,body_color,1.3)
    # Footer intentionally does not overlap any of the main body text.
    if style in ('majalah',):
        footer_fg=(255,255,255);footer_bg=(20,31,46)
    elif style in ('minimal',):
        footer_fg=navy;footer_bg=(226,236,229)
    elif style in ('kartu','poster','diagonal'):
        footer_fg=gold if style=='diagonal' else navy
        footer_bg=(19,33,62) if style=='diagonal' else (255,225,178)
    else:
        footer_fg=navy;footer_bg=(62,213,201)
    d.rounded_rectangle((40,1086,680,1155),radius=17,fill=footer_bg)
    cta_lines,cta_font=wrap(d,cta,595,2,22,17,True)
    multiline(d,cta_lines,cta_font,58,1098,footer_fg,1.19)
    d.text((48,1180),'lynk.id/dirgakhaa   •   Tautan afiliasi',font=font(19,True),fill=navy if style=='minimal' else white)
    badge_logo(im,dark=dark)
    im.save(path,optimize=True)


# Model suara Indonesia Piper (sekali diunduh, bisa digunakan offline tanpa kuota TTS).
PIPER_MODEL_NAME = 'id_ID-news_tts-medium.onnx'
PIPER_MODEL_DIR = ROOT / '.piper_models'
PIPER_BASE_URL = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID/news_tts/medium/'
PIPER_ONNX_MD5 = '17de01db7ac654655436b6e509893c72'
PIPER_CONFIG_MD5 = 'c023cfa031cc9ed4cf5dd8d2ef1e48ed'


def narration_for_scene(heading, body, cta=''):
    parts = [str(heading).rstrip(' .!?'), str(body).rstrip(' .!?')]
    if cta:
        parts.append(str(cta).rstrip(' .!?'))
    return '. '.join(x for x in parts if x) + '.'


def _valid_md5(path, expected):
    if not path.is_file():
        return False
    digest = hashlib.md5()  # Integrity check against upstream model catalog; not a security signature.
    with path.open('rb') as f:
        for block in iter(lambda: f.read(2 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest() == expected


def ensure_piper_model():
    '''Fetch the open model if absent. No voice API calls during TTS inference.'''
    directory = Path(os.environ.get('PIPER_MODEL_DIR', str(PIPER_MODEL_DIR)))
    directory.mkdir(parents=True, exist_ok=True)
    model = directory / PIPER_MODEL_NAME
    for name, checksum in ((PIPER_MODEL_NAME, PIPER_ONNX_MD5),
                           (PIPER_MODEL_NAME + '.json', PIPER_CONFIG_MD5)):
        target = directory / name
        if _valid_md5(target, checksum):
            continue
        tmp = directory / (name + '.download')
        try:
            req = urllib.request.Request(PIPER_BASE_URL + name,
                headers={'User-Agent': 'KeishaStudio/3.3 (Piper Voice Setup)'})
            with urllib.request.urlopen(req, timeout=120) as response, tmp.open('wb') as f:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk: break
                    f.write(chunk)
            if not _valid_md5(tmp, checksum):
                raise RuntimeError('Checksum model Piper tidak sesuai katalog resmi')
            tmp.replace(target)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise RuntimeError('Gagal mengunduh model gratis Piper. Periksa jaringan Github Actions / Hugging Face: '
                               + type(exc).__name__) from exc
    return model


def piper_audio(narration, output):
    '''One offline synthesis invocation, producing a continuous WAV.'''
    model = ensure_piper_model()
    if not shutil.which('piper'):
        raise RuntimeError('Piper belum diinstal. Periksa langkah Install Piper pada workflow.')
    try:
        run = subprocess.run([
            'piper', '--model', str(model), '--output_file', str(output),
            '--length_scale', '1.10',  # Gaya B: tempo sedikit lebih lembut (bukan Nilasari asli).
            '--noise_scale', '0.48', '--noise_w', '0.55',
            '--sentence_silence', '0.14',
        ], input=narration + '\n', text=True, capture_output=True, timeout=210)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Piper tidak selesai: ' + type(exc).__name__) from exc
    if run.returncode:
        raise RuntimeError('Piper gagal menyintesis narasi: ' + (run.stderr or run.stdout)[-900:])
    if not output.is_file() or output.stat().st_size < 4000:
        raise RuntimeError('File WAV Piper kosong / tidak valid.')
    audio_length = duration(output)
    if audio_length < 2:
        raise RuntimeError('Narasi Piper terlalu singkat; periksa model dan naskah.')
    return audio_length


def approximate_cuts(sentences, audio_length):
    '''Offline Piper lacks alignment; keep full uninterrupted audio and use rough timing.'''
    if len(sentences) != 5:
        raise ValueError('Butuh lima adegan')
    # Weighted syllable-ish proxy avoids overly fast slides for long Indonesian words.
    weights = [max(10.0, sum(0.6 + (1.15 if ch.lower() in 'aiueo' else 0.35)
                                   for ch in text if ch.isalpha()) + 4.0)
               for text in sentences]
    total = sum(weights)
    cuts = [0.0]
    cumulative = 0.0
    for x in weights[:-1]:
        cumulative += x
        cuts.append(audio_length * cumulative / total)
    return cuts


def create():
    raw = os.environ.get('VIDEO_NASKAH', '').strip()
    if not raw:
        raise ValueError('Naskah tidak boleh kosong')
    headings, bodies, cta = parse_script(raw)
    if os.environ.get('VIDEO_CTA', '').strip():
        cta = clip_words(os.environ['VIDEO_CTA'], 56)
    seedstr = os.environ.get('GITHUB_RUN_ID', '') or str(os.environ.get('VIDEO_SEED', ''))
    if not seedstr:
        seedstr = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]
    seed = int(hashlib.sha256(seedstr.encode('utf-8')).hexdigest()[:12], 16)
    style = os.environ.get('VIDEO_STYLE', 'otomatis').lower().strip()
    style = 'otomatis' if style in ('otomatis', 'auto', '') else style
    if style not in STYLES + ('otomatis',):
        raise ValueError('Gaya tersedia: ' + ', '.join(STYLES))
    voice = os.environ.get('VIDEO_VOICE', 'piper').lower().strip()
    if voice in ('otomatis', 'natural', 'sintetis', 'nilasari', 'gratis', 'perempuan', ''):
        voice = 'piper'  # Legacy Telegram commands use the free voice automatically.
    if voice not in ('piper', 'mati'):
        raise ValueError('Suara tersedia: piper (gratis) atau mati')

    music_request = os.environ.get('VIDEO_MUSIC', 'otomatis').strip().lower()
    music_mood = choose_mood(raw, music_request)
    music_volume = float(os.environ.get('VIDEO_MUSIC_VOLUME', '0.20'))
    if not (0.05 <= music_volume <= 0.30):
        raise ValueError('VIDEO_MUSIC_VOLUME harus antara 0.05 dan 0.30')

    art = storyboard(raw, style, seed)
    OUT.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, (head, body) in enumerate(zip(headings, bodies), 1):
        card = OUT / f'studio-slide-{i}.png'
        make_card(card, i, head, body, cta, art[i-1]['style'], seed,
                  art[i-1]['motif'], art[i-1]['accent'])
        clips.append(card)

    audio = OUT / 'keisha-suara-gratis.wav'
    if voice == 'mati':
        cuts = [4.0 * n for n in range(5)]
        speech_duration = 20.0
    else:
        sentences = [narration_for_scene(h, b, cta if i == 4 else '')
                     for i, (h, b) in enumerate(zip(headings, bodies))]
        narration = ' '.join(sentences)  # Satu tuturan panjang, bukan klip per slide.
        speech_duration = piper_audio(narration, audio)
        cuts = approximate_cuts(sentences, speech_duration)

    video_length = speech_duration + (0.40 if voice != 'mati' else 0)
    boundaries = cuts + [video_length]
    durations = [b-a for a,b in zip(boundaries, boundaries[1:])]
    timeline = OUT / 'studio-frames.ffconcat'
    with timeline.open('w', encoding='utf-8') as handle:
        handle.write('ffconcat version 1.0\n')
        for image_path, seconds in zip(clips, durations):
            handle.write(f"file '{image_path.name}'\nduration {seconds:.6f}\n")
        handle.write(f"file '{clips[-1].name}'\n")
    silent = OUT / 'studio-silent.mp4'
    ff('-safe','0','-f','concat','-i',timeline, '-vf','fps=15,format=yuv420p',
       '-t',f'{video_length:.3f}','-an','-c:v','libx264','-threads','1',
       '-preset','ultrafast','-crf','27',silent,timeout=240)
    video = OUT / 'keisha-rcd-video.mp4'
    soundtrack_path = OUT / 'keisha-musik-original.wav'
    music_info = None
    if music_mood != 'mati':
        music_info = generate_music(soundtrack_path, video_length, music_mood,
                                    seed_text=raw)

    if voice == 'mati' and music_mood == 'mati':
        shutil.copyfile(silent, video)
    elif voice == 'mati':
        # Music-only video is allowed, but metadata clearly states no narration.
        ff('-i',silent,'-i',soundtrack_path,'-map','0:v:0', '-map','1:a:0',
           '-c:v','copy','-c:a','aac','-b:a','160k',
           '-af',f'volume={music_volume},alimiter=limit=0.88',
           '-t',f'{video_length:.3f}','-movflags','+faststart',video)
    elif music_mood == 'mati':
        ff('-i',silent,'-i',audio,'-map','0:v:0','-map','1:a:0',
           '-c:v','copy','-c:a','aac','-b:a','160k','-ar','44100',
           '-af','highpass=f=70,lowpass=f=10500,acompressor=threshold=-20dB:ratio=2:attack=30:release=300,loudnorm=I=-17:TP=-2:LRA=10,apad=pad_dur=0.40',
           '-t',f'{video_length:.3f}', '-movflags','+faststart',video)
    else:
        # Keep the music low under the narrator. Sidechain compression reduces the
        # original instrumental track whenever the narrator speaks; no abrupt cuts.
        fadeout_start=max(0.0,video_length-.85)
        filter_graph=(
            '[1:a]highpass=f=70,lowpass=f=10500,'
            'acompressor=threshold=-20dB:ratio=2:attack=30:release=300,'
            'loudnorm=I=-17:TP=-2:LRA=10,'
            f'apad=pad_dur=0.40,atrim=duration={video_length:.4f},'
            'aresample=44100,aformat=channel_layouts=stereo,asplit=2[voice][trigger];'
            f'[2:a]aresample=44100,aformat=channel_layouts=stereo,'
            f'atrim=duration={video_length:.4f},'
            f'volume={music_volume:.3f},afade=t=in:st=0:d=0.40,'
            f'afade=t=out:st={fadeout_start:.4f}:d=0.85[bed];'
            '[bed][trigger]sidechaincompress=threshold=0.042:ratio=4.5:'
            'attack=40:release=400[ducked];'
            '[voice][ducked]amix=inputs=2:duration=longest:'
            'dropout_transition=0:normalize=0,alimiter=limit=0.88[finalaudio]'
        )
        ff('-i',silent,'-i',audio,'-i',soundtrack_path,
           '-filter_complex',filter_graph,'-map','0:v:0','-map','[finalaudio]',
           '-c:v','copy','-c:a','aac','-b:a','160k', '-ar','44100',
           '-t',f'{video_length:.3f}','-movflags','+faststart',video,timeout=230)
    if not video.is_file() or video.stat().st_size < 5000:
        raise RuntimeError('MP4 hasil rendering tidak valid')
    verify = subprocess.run(['ffprobe','-v','error','-select_streams','a:0',
            '-show_entries','stream=codec_name','-of',
            'default=noprint_wrappers=1:nokey=1', str(video)],
            check=True,capture_output=True,text=True,timeout=15)
    has_audio = bool(verify.stdout.strip())
    if voice != 'mati' and not has_audio:
        raise RuntimeError('MP4 kehilangan audio. Tidak dikirim ke Telegram.')
    info = {'version':'3.4','style':style,'scene_styles':[x['style'] for x in art],
            'visuals':art,'voice':voice,'voice_style':'B-lembut (Piper offline, B referensi karakter)',
            'audio_verified':has_audio,'narration_verified':has_audio and voice!='mati',
            'music_enabled':music_mood!='mati','music_mood':music_mood,
            'music_volume':music_volume if music_info else 0,
            'music_source':'original_programmatic_instrumental' if music_info else None,
            'music_info':music_info,
            'duration':round(duration(video),1),
            'headings':headings,'bodies':bodies,'cta':cta,
            'narration_continuous':voice!='mati',
            'audio_timing_exact':False,
            'scene_start_seconds':[round(v,3) for v in cuts],
            'voice_id':'id_ID-news_tts-medium' if voice!='mati' else None,
            'scene_timing':'estimated_offline' if voice!='mati' else 'fixed_silent',
            'tts_cloud_requests':0}
    (OUT/'metadata.json').write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                    encoding='utf-8')
    print('KEISHA STUDIO V3.4 MUSIK ORIGINAL GRATIS:', video, '| voice:', voice,
          '| one continuous audio:', info['narration_continuous'],
          '| audio verified:', has_audio, '| duration:', info['duration'])


if __name__=='__main__':
    create()
