"""Optional, locally-run natural-sounding Indonesian voice (CC-BY-4.0 model, CC0 prompt).
No ElevenLabs API, no per-character credits. Requires pocket-tts package and model download.
Uses independently licensed CC0 Common Voice example. Does NOT clone Nilasari.
"""
from __future__ import annotations
import math
import os
from pathlib import Path
import subprocess
import urllib.request
import wave
import numpy as np

CONFIG='hf://anak10thn/pocket-tts-indonesian/indonesian_6l.yaml@17257664e384561c957b02ac92edd1a24807f0e5'
REFERENCE='https://huggingface.co/anak10thn/pocket-tts-indonesian/resolve/main/voices/common_voice_id_19961910.mp3'

def natural_audio(text: str, output: Path) -> float:
    from pocket_tts import TTSModel
    directory = output.parent / 'pocket-voice'
    directory.mkdir(parents=True, exist_ok=True)
    src = directory / 'cc0_indonesian_reference.mp3'
    dst = directory / 'cc0_indonesian_reference.wav'
    if not src.exists() or src.stat().st_size < 10000:
        req = urllib.request.Request(REFERENCE, headers={'User-Agent':'KeishaStudio-v3.5'})
        with urllib.request.urlopen(req, timeout=90) as response:
            data=response.read(500000)
        if len(data)<10000 or len(data)>450000:
            raise RuntimeError('Reference CC0 tidak dapat diunduh dengan benar')
        src.write_bytes(data)
    if not dst.exists() or dst.stat().st_size < 10000:
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(src),
                        '-ar','48000','-ac','1','-c:a','pcm_s16le',str(dst)],
                       check=True,timeout=45)
    model=TTSModel.load_model(config=CONFIG, eos_threshold=-6.0)
    state=model.get_state_for_audio_prompt(str(dst))
    with __import__('torch').inference_mode():
        result=model.generate_audio(state,text)
    samples=result.detach().cpu().float().numpy().reshape(-1)
    if not len(samples) or not np.isfinite(samples).all():
        raise RuntimeError('Pocket TTS menghasilkan audio kosong/tidak valid')
    rate=int(model.sample_rate)
    seconds=len(samples)/rate
    if not (2.0<=seconds<=180.0):
        raise RuntimeError(f'Durasi Pocket TTS tidak wajar: {seconds:.1f} detik')
    # Avoid clipping without unnatural pitch shifts / fake voice transformation.
    pcm=(np.clip(samples,-0.98,0.98)*32767).astype('<i2')
    with wave.open(str(output),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate);f.writeframes(pcm.tobytes())
    return seconds
