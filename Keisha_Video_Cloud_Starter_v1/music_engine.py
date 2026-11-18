"""Original, deterministic background music for Keisha vertical videos.

Composed/synthesized directly by this project. No samples, copyrighted tracks,
cloud services, paid API keys, or third-party instrument libraries required.
"""
from __future__ import annotations
import hashlib
import math
from pathlib import Path
import wave
import numpy as np

SAMPLE_RATE = 22050
MOODS = ('tenang', 'ceria', 'inspiratif', 'fokus', 'dramatis')
THEMES = {
    'tenang':      dict(bpm=78, root=50, minor=False, steps=(0, 7, 9, 5), busy=0.38),
    'ceria':       dict(bpm=112,root=48, minor=False, steps=(0, 5, 9, 7), busy=0.86),
    'inspiratif':  dict(bpm=98, root=55, minor=False, steps=(0, 7, 9, 5), busy=0.72),
    'fokus':       dict(bpm=87, root=45, minor=True,  steps=(0, 8, 3, 10),busy=0.34),
    'dramatis':    dict(bpm=82, root=52, minor=True,  steps=(0, 10, 8, 7),busy=0.55),
}
# Longer phrase matches take priority. These are not exhaustive topic classifiers.
TRIGGERS = (
    ('dramatis', ('penipuan','waspada','bahaya','risiko besar','kecemasan','masalah serius','kerugian')),
    ('ceria', ('lucu','ceria','seru','fun','anak','hiburan','hadiah','rayakan','komedi')),
    ('tenang', ('tenang','healing','rileks','meditasi','tidur','merenung','santai','syukur')),
    ('fokus', ('tutorial','cara menggunakan','langkah-langkah','tutorial','panduan teknis','analisis','riset')),
    ('inspiratif', ('motivasi','semangat','sukses','bisnis','berjualan','jualan','ebook','affiliate','tips','produktif')),
)

def choose_mood(topic: str, requested: str='otomatis') -> str:
    request=(requested or 'otomatis').strip().lower()
    if request in MOODS: return request
    if request in ('mati','off','none','tanpa'): return 'mati'
    if request not in ('','otomatis','auto'):
        raise ValueError('Pilihan musik: otomatis, ' + ', '.join(MOODS) + ', mati')
    s=(topic or '').lower()
    for mood, phrases in TRIGGERS:
        if any(p in s for p in phrases): return mood
    return 'inspiratif'

def midi_hz(midi:float)->float:
    return 440 * 2**((midi-69)/12)

def generate_music(path: str | Path, seconds: float, mood: str,
                   seed_text: str='') -> dict:
    if mood not in THEMES: raise ValueError('Mood musik tidak dikenal: '+str(mood))
    if not (2 <= seconds <= 600): raise ValueError('Durasi musik di luar batas aman (2..600 detik)')
    cfg = THEMES[mood]
    n=int(math.ceil(seconds*SAMPLE_RATE))
    buffer=np.zeros(n,dtype=np.float32)
    seed=int(hashlib.sha256((mood+'|'+seed_text).encode()).hexdigest()[:14],16)
    rng=np.random.default_rng(seed)
    beat=60/cfg['bpm']; bar=beat*4
    bars=int(math.ceil(seconds/bar))

    def add(midi, at, d, amp=0.1, kind='pad'):
        start=max(0,int(at*SAMPLE_RATE)); length=min(n-start,int(d*SAMPLE_RATE))
        if length<=0: return
        t=np.arange(length,dtype=np.float32)/SAMPLE_RATE
        freq=midi_hz(midi)
        phase=(2*np.pi*freq*t)
        if kind=='pad':
            wavev=(np.sin(phase)+.17*np.sin(2*phase+.15)+.07*np.sin(3*phase))*np.cos(2*np.pi*.18*t)**2*.055 + np.sin(phase)*.88
            attack=np.minimum(1,t/.23)
            release=np.minimum(1,(d-t)/.45)
            env=np.maximum(0,attack*release)
        elif kind=='bell':
            wavev=np.sin(phase)+.20*np.sin(2*phase)+.08*np.sin(4*phase)
            env=(1-np.exp(-t*60))*np.exp(-t*2.7)
        elif kind=='bass':
            wavev=np.sin(phase)+.13*np.sin(2*phase)
            env=(1-np.exp(-t*24))*np.exp(-t*2.2)
        else:
            wavev=np.sin(phase)
            env=(1-np.exp(-t*40))*np.exp(-t*3.5)
        buffer[start:start+length]+=(wavev*env*amp).astype(np.float32)

    def hat(at,amp):
        length=min(n-int(at*SAMPLE_RATE), int(.065*SAMPLE_RATE)); start=int(at*SAMPLE_RATE)
        if start<0 or length<1: return
        t=np.arange(length,dtype=np.float32)/SAMPLE_RATE
        noise=rng.normal(0,1,length).astype(np.float32)
        # Noise transient is softly filtered by differencing and a quick decay.
        noise[1:]-=noise[:-1]*.7
        buffer[start:start+length]+=(noise*np.exp(-t*85)*amp).astype(np.float32)

    major=(0,4,7,11);minor=(0,3,7,10)
    for b in range(bars):
        start=b*bar
        degree=cfg['steps'][b%len(cfg['steps'])]
        notes=(minor if cfg['minor'] else major)
        root=cfg['root']+degree
        for chord_interval in notes[:3]:
            add(root+chord_interval+12, start, bar+.12, amp=.070, kind='pad')
        # A sparse, original arpeggiated motif: deliberately stays below narration.
        for beat_idx in range(4):
            bt=start+beat_idx*beat
            if bt>=seconds: break
            if beat_idx in (0,2): add(root-12,bt,beat*.92,amp=.095,kind='bass')
            if (beat_idx%2==0 or cfg['busy']>.65) and rng.random()<cfg['busy']+.22:
                index=(beat_idx+b)%3
                add(root+notes[index]+24, bt+(.035 if beat_idx%2 else 0),beat*.68,amp=.025,kind='bell')
            if beat_idx in (1,3) and cfg['busy']>.40: hat(bt,.009 if mood!='ceria' else .013)
            if cfg['busy']>.70 and beat_idx in (0,2): hat(bt,.006)

    # No sampled tracks; music is rendered deterministically from original synth signals.
    # Keep moderate headroom so the voice/music mixer has room for a limiter.
    peak=float(np.max(np.abs(buffer))) or 1.0
    buffer*=.58/peak
    fade=min(.45,seconds*.08)
    fade_n=int(fade*SAMPLE_RATE)
    buffer[:fade_n]*=np.linspace(0,1,fade_n,dtype=np.float32)
    end_n=int(min(.90, seconds*.12)*SAMPLE_RATE)
    buffer[-end_n:]*=np.linspace(1,0,end_n,dtype=np.float32)
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    pcm=np.asarray(np.clip(buffer,-1,1)*32767,dtype='<i2')
    with wave.open(str(target),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(SAMPLE_RATE);wav.writeframes(pcm.tobytes())
    return {'mood':mood,'bpm':cfg['bpm'],'duration':round(seconds,2),'original_composition':True,'peak':round(float(np.max(np.abs(buffer))),4)}
