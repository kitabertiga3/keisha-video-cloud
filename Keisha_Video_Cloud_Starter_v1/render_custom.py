"""Render a new original text storyboard supplied from Telegram/GitHub.
No default storyboards: each run requires a real brief/script input.
"""
import json
import os
import re
from server import validate
from video_engine import build_video

BODY_LIMIT = 145
HEADING_LIMIT = 78


def clip_words(value, limit):
    value = re.sub(r'\s+', ' ', str(value)).strip(' -:;|')
    if len(value) <= limit:
        return value
    cut = value[:limit].rsplit(' ', 1)[0].rstrip('.,;: -')
    return cut if cut else value[:limit]


def clean_text(value):
    return re.sub(r'^(?:isi|narasi|body|teks|caption)\s*:\s*', '', value.strip(), flags=re.I).strip()


def make_heading(value):
    words = re.findall(r'\S+', value)
    return clip_words(' '.join(words[:7]).upper().strip('.,:;!?'), HEADING_LIMIT)


def content_from_topic(topic, title=None):
    """Plain-text fallback when cloud AI is unavailable; no unsupported claims."""
    topic = re.sub(r'^(?:tentang|mengenai|topiknya)\s+', '', topic.strip(), flags=re.I)
    topic = clip_words(topic, 92).strip(' .,;:')
    name = title or topic
    return (
        [clip_words(t, HEADING_LIMIT) for t in [
            name.upper(), 'MULAI DARI TUJUAN', 'PERIKSA INFORMASINYA', 'BUAT LANGKAH PRAKTIS', 'SIMPULKAN & LANJUTKAN'
        ]],
        [clip_words(t, BODY_LIMIT) for t in [
            f'Kenali dulu topik ini: {topic}. Tentukan informasi apa yang paling kamu butuhkan.',
            f'Sebelum bertindak, tentukan tujuanmu saat mempelajari {topic}.',
            'Cari sumber yang jelas, bandingkan informasi, dan hindari janji hasil instan.',
            f'Buat daftar langkah kecil yang sesuai dengan kebutuhanmu tentang {topic}.',
            'Simpan hal penting, cek lagi faktanya, lalu mulai dari langkah yang paling masuk akal.'
        ]]
    )


def parse_script(raw):
    raw = raw.strip()
    if not raw or len(raw) > 4000:
        raise ValueError('Naskah kosong atau terlalu panjang (maks 4000 karakter)')

    # Cloudflare AI may send structured JSON. This is the preferred format.
    if raw.startswith('{'):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and 'headings' in obj and 'bodies' in obj:
            heads = [clip_words(x, HEADING_LIMIT) for x in obj['headings']]
            bodies = [clip_words(x, BODY_LIMIT) for x in obj['bodies']]
            cta = clip_words(obj.get('cta') or 'Cek detail ebook di link bio', 56)
            return validate({'headings': heads, 'bodies': bodies, 'cta': cta})

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    title, cta = None, 'Cek detail ebook di link bio'
    scenes = {}
    current = None
    leftovers = []
    scene_re = re.compile(r'^(?:(?:slide|bagian|scene|adegan)\s*)?([1-5])\s*[.):\-]\s*(.*)$', re.I)
    for line in lines:
        if re.match(r'^CTA\s*:', line, flags=re.I):
            cta = clip_words(line.split(':', 1)[1], 56) or cta
            continue
        if re.match(r'^(?:judul|topik|tema)\s*:', line, flags=re.I):
            title = line.split(':', 1)[1].strip()
            continue
        match = scene_re.match(line)
        if match:
            current = int(match.group(1))
            content = match.group(2).strip()
            if '|' in content:
                heading, body = content.split('|', 1)
                scenes[current] = [heading.strip(), body.strip()]
            elif ' — ' in content:
                heading, body = content.split(' — ', 1)
                scenes[current] = [heading.strip(), body.strip()]
            else:
                scenes[current] = [content, '']
            continue
        if current is not None:
            scenes[current][1] = (scenes[current][1] + ' ' + clean_text(line)).strip()
        else:
            leftovers.append(line)

    if all(i in scenes for i in range(1, 6)):
        heads, bodies = [], []
        for i in range(1, 6):
            heading, body = scenes[i]
            if not body:
                # If user supplies numbered sentences, turn each sentence into slide content.
                body = heading
                heading = make_heading(heading)
            heads.append(clip_words(heading or make_heading(body), HEADING_LIMIT))
            bodies.append(clip_words(body, BODY_LIMIT))
        return validate({'headings': heads, 'bodies': bodies, 'cta': cta})

    # Full unnumbered script from a colleague: each sentence becomes a segment.
    remaining = ' '.join(leftovers or lines)
    remaining = re.sub(r'^(?:tolong\s+)?(?:tentang|mengenai|topik)\s+', '', remaining, flags=re.I)
    sentences = [clean_text(s) for s in re.split(r'(?<=[.!?])\s+|\s*;\s*', remaining) if s.strip()]
    if len(sentences) >= 5:
        groups = [[] for _ in range(5)]
        # Keep story order, balanced in contiguous groups (rather than round-robin).
        for k, sentence in enumerate(sentences):
            groups[min(4, (k * 5) // len(sentences))].append(sentence)
        # Small lists of 5-9 can leave empty groups; fill from preceding groups.
        if not all(groups):
            groups = [[sentences[i]] for i in range(5)]
        heads = [clip_words(title if i == 0 and title else make_heading(group[0]), HEADING_LIMIT)
                 for i, group in enumerate(groups)]
        bodies = [clip_words(' '.join(group), BODY_LIMIT) for group in groups]
        return validate({'headings': heads, 'bodies': bodies, 'cta': cta})

    # A topic or short creative direction becomes a visibly different draft.
    topic = title or ' '.join(leftovers or lines)
    heads, bodies = content_from_topic(topic, title)
    return validate({'headings': heads, 'bodies': bodies, 'cta': cta})


def main():
    raw = os.environ.get('VIDEO_NASKAH', '').strip()
    if not raw:
        raise SystemExit('ERROR: Isi naskah/topik dulu. Video default tidak diulang.')
    headings, bodies, cta = parse_script(raw)
    override = os.environ.get('VIDEO_CTA', '').strip()
    if override:
        cta = clip_words(override, 56)
    # Re-validate lengths and format so a long external script fails clearly.
    headings, bodies, cta = validate({'headings': headings, 'bodies': bodies, 'cta': cta})
    path = build_video('hasil', headings, bodies, cta)
    print('MP4 khusus berhasil dibuat:', path, '| slide 1:', headings[0])


if __name__ == '__main__':
    main()
