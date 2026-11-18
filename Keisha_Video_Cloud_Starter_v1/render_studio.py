"""Ruang Cuan Digital | Keisha Studio v3.1.
Original text-vector compositions with synchronized continuous ElevenLabs Nilasari narration.
Requires licensed ElevenLabs API for promotional/commercial use. No robotic voice fallback.
"""
from __future__ import annotations

import base64
import difflib
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


NILASARI_VOICE_ID = 'NPDHDOOQCSyifTJZOe6J'  # Verified ElevenLabs Voice Library: Nilasari


def narration_for_scene(heading, body, cta=''):
    """Narration speaks exactly the on-screen heading, body and optional CTA."""
    parts = [heading.rstrip(' .!?'), body.rstrip(' .!?')]
    if cta:
        parts.append(cta.rstrip(' .!?'))
    return '. '.join(x for x in parts if x) + '.'


def _align_index(original, produced, pos):
    """Translate a narration character index to ElevenLabs alignment characters."""
    if original == produced:
        return pos
    blocks = difflib.SequenceMatcher(a=original, b=produced, autojunk=False).get_matching_blocks()
    for block in blocks:
        if block.a <= pos < block.a + block.size:
            return block.b + pos - block.a
        if block.a > pos:
            break
    earlier = [b for b in blocks if b.a + b.size <= pos]
    return min(len(produced) - 1, (earlier[-1].b + earlier[-1].size) if earlier else 0)


def nilasari_audio_with_timing(narration, scene_offsets, output):
    """Generate ONE continuous voiceover; use ElevenLabs character timing for cuts.

    No per-slide TTS splicing, no eSpeak fallback. This preserves prosody and
    fixes staccato/awkward breaks caused by joining five independent speech clips.
    """
    api = os.environ.get('ELEVENLABS_API_KEY', '').strip()
    commercial_ok = os.environ.get('ELEVENLABS_COMMERCIAL_OK', '').lower() in ('true', '1', 'yes')
    if not api or not commercial_ok:
        raise RuntimeError(
            'Suara Nilasari BELUM AKTIF. Tambahkan GitHub Actions secret '
            'ELEVENLABS_API_KEY dari akun ElevenLabs berlisensi komersial dan '
            'ELEVENLABS_COMMERCIAL_OK=true. Video dibatalkan, tanpa fallback robot.'
        )
    payload = json.dumps({
        'text': narration,
        'model_id': 'eleven_multilingual_v2',
        'voice_settings': {'stability': 0.5, 'similarity_boost': 0.8, 'style': 0.12,
                           'use_speaker_boost': True},
    }, ensure_ascii=False).encode('utf-8')
    url = (f'https://api.elevenlabs.io/v1/text-to-speech/{NILASARI_VOICE_ID}'
           '/with-timestamps?output_format=mp3_44100_128')
    request = urllib.request.Request(url, data=payload, method='POST', headers={
        'xi-api-key': api, 'Content-Type': 'application/json', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=130) as response:
            content = response.read(15_000_000)
        data = json.loads(content)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            message = 'API key tidak valid atau tidak berhak mengakses suara Nilasari.'
        elif error.code in (400, 404, 422):
            message = 'Voice Nilasari belum tersedia di akun. Tambahkan Nilasari dari ElevenLabs Voice Library.'
        elif error.code == 429:
            message = 'Kuota atau batas permintaan ElevenLabs habis.'
        else:
            message = f'ElevenLabs HTTP {error.code}.'
        raise RuntimeError(message + ' Video tidak dibuat dengan suara robot.') from None
    except (OSError, ValueError, TimeoutError) as error:
        raise RuntimeError(f'Gagal meminta suara Nilasari: {type(error).__name__}. '
                           'Periksa koneksi ElevenLabs; video belum dibuat.') from None
    try:
        mp3 = base64.b64decode(data['audio_base64'], validate=True)
        chars = data['alignment']['characters']
        times = data['alignment']['character_start_times_seconds']
        ends = data['alignment']['character_end_times_seconds']
        if len(chars) < 10 or len(chars) != len(times) or len(chars) != len(ends):
            raise ValueError('alignment tidak valid')
        returned_text = ''.join(chars)
        similarity = difflib.SequenceMatcher(a=narration, b=returned_text,
                                               autojunk=False).ratio()
        if similarity < 0.75:
            raise ValueError('naskah dan timing tidak sesuai')
        output.write_bytes(mp3)
        if len(mp3) < 1000:
            raise ValueError('file audio terlalu kecil')
        audio_length = duration(output)
        if audio_length < 1:
            raise ValueError('durasi audio tidak valid')
        cuts = [0.0]
        for pos in scene_offsets[1:]:
            idx = _align_index(narration, returned_text, pos)
            cuts.append(float(times[max(0, min(len(times)-1, idx))]))
        if len(cuts) != 5 or any(b-a < .4 for a,b in zip(cuts, cuts[1:])):
            raise ValueError('batas slide tidak valid')
        if cuts[-1] >= audio_length - .4:
            raise ValueError('audio tidak cocok dengan lima adegan')
        return cuts, audio_length
    except (ValueError, KeyError, TypeError, UnicodeError) as error:
        output.unlink(missing_ok=True)
        raise RuntimeError(f'Suara Nilasari diterima tapi timing bermasalah: {error}. '
                           'Video dibatalkan agar tidak salah sinkron.') from None


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
    voice = os.environ.get('VIDEO_VOICE', 'nilasari').lower().strip()
    if voice in ('otomatis', 'natural', 'sintetis', ''):
        voice = 'nilasari'  # Old commands never silently select the robotic voice.
    if voice not in ('nilasari', 'mati'):
        raise ValueError('Suara tersedia: nilasari atau mati')

    art = storyboard(raw, style, seed)
    OUT.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, (head, body) in enumerate(zip(headings, bodies), 1):
        card = OUT / f'studio-slide-{i}.png'
        make_card(card, i, head, body, cta, art[i-1]['style'], seed,
                  art[i-1]['motif'], art[i-1]['accent'])
        clips.append(card)

    mp3 = OUT / 'keisha-nilasari.mp3'
    if voice == 'mati':
        cuts = [4.0 * n for n in range(5)]
        speech_duration = 20.0
    else:
        sentences = [narration_for_scene(h, b, cta if i == 4 else '')
                     for i, (h, b) in enumerate(zip(headings, bodies))]
        narration = '\n\n'.join(sentences)
        offsets = []
        pos = 0
        for i, sentence in enumerate(sentences):
            offsets.append(pos)
            pos += len(sentence) + (2 if i != 4 else 0)
        cuts, speech_duration = nilasari_audio_with_timing(narration, offsets, mp3)

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
    if voice == 'mati':
        shutil.copyfile(silent, video)
    else:
        # Encode one AAC track from a continuous MP3. No independent WAV stitching.
        ff('-i',silent,'-i',mp3,'-map','0:v:0','-map','1:a:0',
           '-c:v','copy','-c:a','aac','-b:a','160k','-ar','44100',
           '-af','apad=pad_dur=0.40','-t',f'{video_length:.3f}',
           '-movflags','+faststart',video)
    if not video.is_file() or video.stat().st_size < 5000:
        raise RuntimeError('MP4 hasil rendering tidak valid')
    verify = subprocess.run(['ffprobe','-v','error','-select_streams','a:0',
            '-show_entries','stream=codec_name','-of',
            'default=noprint_wrappers=1:nokey=1', str(video)],
            check=True,capture_output=True,text=True,timeout=15)
    has_audio = bool(verify.stdout.strip())
    if voice != 'mati' and not has_audio:
        raise RuntimeError('MP4 kehilangan audio. Tidak dikirim ke Telegram.')
    info = {'version':'3.2','style':style,'scene_styles':[x['style'] for x in art],
            'visuals':art,'voice':voice,'audio_verified':has_audio,
            'duration':round(duration(video),1),
            'headings':headings,'bodies':bodies,'cta':cta,
            'narration_continuous':voice!='mati',
            'scene_start_seconds':[round(v,3) for v in cuts],
            'voice_id':NILASARI_VOICE_ID if voice!='mati' else None}
    (OUT/'metadata.json').write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                    encoding='utf-8')
    print('KEISHA STUDIO V3.2:', video, '| voice:', voice,
          '| synchronized:', info['narration_continuous'],
          '| audio verified:', has_audio, '| duration:', info['duration'])


if __name__=='__main__':
    create()
