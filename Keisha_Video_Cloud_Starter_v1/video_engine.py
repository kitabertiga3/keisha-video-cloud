"""Original, text-only MP4 cards for Ruang Cuan Digital (no unlicensed TTS)."""
from pathlib import Path
import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 720, 1280
NAVY = (10, 23, 45)
GOLD = (255, 205, 87)
WHITE = (246, 248, 252)
MUTED = (186, 204, 224)
LOGO = Path(__file__).parent / 'assets' / 'rcd_logo.png'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def font(px, bold=False):
    paths = [BOLD if bold else FONT, 'C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf']
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, px)
    return ImageFont.load_default()


def fit_lines(draw, words, max_width, max_lines, initial=55, min_size=26, bold=True):
    for size in range(initial, min_size - 1, -2):
        f = font(size, bold)
        lines, current = [], ''
        for word in words.split():
            candidate = (current + ' ' + word).strip()
            if draw.textbbox((0, 0), candidate, font=f)[2] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if len(lines) <= max_lines and all(draw.textbbox((0, 0), x, font=f)[2] <= max_width for x in lines):
            return lines, f
    raise ValueError('Teks terlalu panjang untuk tampilan video. Perpendek kalimat.')


def draw_lines(draw, lines, f, x, y, color, gap=1.26):
    size = getattr(f, 'size', 28)
    for line in lines:
        draw.text((x, y), line, fill=color, font=f)
        y += int(size * gap)
    return y


def card(path, index, heading, body, cta):
    # Solid+subtle bands: memory-friendly and readable as vertical phone content.
    im = Image.new('RGB', (WIDTH, HEIGHT), NAVY)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, WIDTH, 14), fill=GOLD)
    d.polygon([(0, 1010), (720, 840), (720, 1280), (0, 1280)], fill=(18, 44, 80))
    d.rounded_rectangle((42, 194, 678, 910), radius=34, fill=(23, 46, 79), outline=(74, 100, 132), width=2)
    if LOGO.exists():
        with Image.open(LOGO) as logo:
            logo = logo.convert('RGB').resize((98, 98), Image.Resampling.LANCZOS)
            im.paste(logo, (42, 40))
    d.text((155, 51), 'RUANG CUAN', fill=WHITE, font=font(25, True))
    d.text((155, 92), 'D I G I T A L', fill=GOLD, font=font(15, True))
    d.text((62, 220), f'BAGIAN {index:02}/05', fill=GOLD, font=font(25, True))
    heading_lines, heading_font = fit_lines(d, heading, 562, 4, initial=54, min_size=30)
    y = draw_lines(d, heading_lines, heading_font, 62, 305, WHITE, gap=1.22)
    y += 40
    d.line((62, y, 615, y), fill=GOLD, width=4)
    y += 36
    body_lines, body_font = fit_lines(d, body, 562, 9, initial=35, min_size=26, bold=False)
    bottom = draw_lines(d, body_lines, body_font, 62, y, MUTED, gap=1.35)
    if bottom > 886:
        raise ValueError('Isi slide terlalu panjang. Ringkas teksnya.')
    d.rounded_rectangle((42, 962, 678, 1053), radius=26, fill=GOLD)
    cta_lines, cta_font = fit_lines(d, cta, 566, 2, initial=28, min_size=22)
    total_cta_height = len(cta_lines) * int(cta_font.size * 1.16)
    draw_lines(d, cta_lines, cta_font, 68, 1006 - total_cta_height // 2, NAVY, gap=1.16)
    d.text((42, 1134), 'lynk.id/dirgakhaa', font=font(30, True), fill=GOLD)
    d.text((42, 1190), 'Konten edukasi | Tautan affiliate', font=font(19), fill=MUTED)
    im.save(path, optimize=True)


def build_video(folder, headings, bodies, cta):
    """Generate a 20-second silent vertical H.264 MP4 with 5 original cards."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    images = []
    for i in range(5):
        path = folder / f'card-{i + 1}.png'
        card(path, i + 1, headings[i], bodies[i], cta)
        images.append(path)
    playlist = folder / 'slides.ffconcat'
    with playlist.open('w', encoding='utf-8') as f:
        f.write('ffconcat version 1.0\n')
        for p in images:
            f.write(f"file '{p.name}'\nduration 4\n")
        f.write(f"file '{images[-1].name}'\n")
    video = folder / 'keisha-rcd-video.mp4'
    subprocess.run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-safe', '0', '-f', 'concat', '-i', str(playlist),
        '-vf', 'fps=15,format=yuv420p', '-t', '20', '-an', '-c:v', 'libx264',
        '-threads', '1', '-preset', 'ultrafast', '-crf', '27', '-movflags', '+faststart', str(video),
    ], check=True, timeout=240, cwd=str(folder))
    if not video.exists() or video.stat().st_size < 5000:
        raise RuntimeError('FFmpeg tidak menghasilkan MP4 yang valid')
    return video
