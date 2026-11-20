"""Keisha social drafts: validate MP4, upload Cloudinary, save Buffer drafts ONLY."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

PLATFORMS = ("tiktok", "facebook", "youtube")
SUSPICIOUS = re.compile(r'[\[\]{}]|"(?:headings|bodies|cta)"\s*:|\b(?:gaya|suara|musik)\s*:|\b(?:gaya\s+otomatis|suara\s+natural|musik\s+tenang|musik\s+otomatis)\b', re.I)

def validate_metadata(path):
    m = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(m, dict) or not m.get("audio_verified") or not m.get("narration_verified"):
        raise ValueError("Metadata atau narasi tidak lolos pemeriksaan.")
    if m.get("voice") in (None, "", "mati"):
        raise ValueError("Video tanpa suara tidak boleh diunggah.")
    for field in ("headings", "bodies"):
        items = m.get(field)
        if not isinstance(items, list) or len(items) != 5:
            raise ValueError("Naskah harus berisi lima adegan.")
        for i, item in enumerate(items, 1):
            if not isinstance(item, str) or not item.strip() or SUSPICIOUS.search(item):
                raise ValueError(f"Teks slide {i} mengandung tanda JSON atau pengaturan produksi.")
    if not isinstance(m.get("cta"), str) or SUSPICIOUS.search(m["cta"]):
        raise ValueError("CTA mengandung format tak layak tayang.")
    return m

def validate_video(path, m):
    if not path.is_file() or not (5000 < path.stat().st_size < 90 * 1024 * 1024):
        raise ValueError("MP4 tidak ditemukan atau berukuran tidak wajar.")
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    data = json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30).stdout)
    videos = [x for x in data.get("streams", []) if x.get("codec_type") == "video"]
    audios = [x for x in data.get("streams", []) if x.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) != 1:
        raise ValueError("Video harus memiliki satu video stream dan satu audio stream.")
    v, a = videos[0], audios[0]
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    seconds = float(data.get("format", {}).get("duration", 0))
    if w * 16 != h * 9 or w < 360 or v.get("codec_name") != "h264" or a.get("codec_name") != "aac":
        raise ValueError("MP4 harus vertikal 9:16, H.264 dan AAC.")
    if not (3 <= seconds <= 175) or abs(float(m.get("duration", seconds)) - seconds) > 3:
        raise ValueError("Durasi MP4 tidak sesuai metadata atau terlalu panjang.")
    return {"width": w, "height": h, "seconds": round(seconds, 2)}

def caption(m):
    title = m["headings"][0].strip().rstrip(".,!?")
    return (title + "\n\nPelajari langkah-langkahnya, lalu cek informasi Ebook Cuan dari Rumah di link profil.\n\n"
            "Tautan affiliate: kami dapat menerima komisi dari pembelian yang memenuhi syarat.\n"
            "#BisnisDigital #BelajarAffiliate #RuangCuanDigital")

def graphql(token, query):
    req = urllib.request.Request("https://api.buffer.com",
        data=json.dumps({"query": query}, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json",
                 "User-Agent": "KeishaDrafts/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Buffer HTTP {error.code}; periksa izin API.") from None
    if result.get("errors"):
        raise RuntimeError("Buffer menolak query: " +
            "; ".join(str(x.get("message", "error"))[:110] for x in result["errors"][:2]))
    return result.get("data") or {}

def get_channels(token):
    account = graphql(token, "query { account { organizations { id } } }")
    orgs = (account.get("account") or {}).get("organizations") or []
    channels = {}
    for org in orgs:
        q = f'query {{ channels(input: {{ organizationId: {json.dumps(org["id"])} }}) {{ id name service }} }}'
        for item in graphql(token, q).get("channels") or []:
            service = str(item.get("service", "")).lower()
            if service in PLATFORMS and service not in channels:
                channels[service] = item["id"]
    missing = set(PLATFORMS) - set(channels)
    if missing:
        raise RuntimeError("Buffer belum memiliki channel: " + ", ".join(sorted(missing)))
    return channels

def upload(video, run_id):
    import cloudinary
    import cloudinary.api
    import cloudinary.uploader
    fields = ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    missing = [f for f in fields if not os.getenv(f)]
    if missing:
        raise RuntimeError("Secret Cloudinary belum tersedia: " + ", ".join(missing))
    cloudinary.config(cloud_name=os.environ[fields[0]], api_key=os.environ[fields[1]],
                      api_secret=os.environ[fields[2]], secure=True)
    # Prevent replaying the same run and accidentally creating more Buffer drafts.
    identifier = f"keisha-drafts/run-{run_id}"
    try:
        cloudinary.api.resource(identifier, resource_type="video")
    except cloudinary.api.NotFound:
        pass
    else:
        raise RuntimeError("Run ini sudah pernah diunggah. Jangan buat draf ganda.")
    r = cloudinary.uploader.upload(str(video), resource_type="video",
        folder="keisha-drafts", public_id=f"run-{run_id}", unique_filename=False, overwrite=False)
    url = str(r.get("secure_url", ""))
    if not url.startswith("https://res.cloudinary.com/") or "/video/upload/" not in url:
        raise RuntimeError("Cloudinary tidak mengembalikan URL MP4 publik yang benar.")
    return url

def save_draft(token, channel_id, url, text):
    # saveToDraft: true guarantees no scheduling or publication via this mutation.
    q = ("mutation { createPost(input: {"
         f"text: {json.dumps(text, ensure_ascii=False)}, "
         f"channelId: {json.dumps(channel_id)}, schedulingType: automatic, "
         "mode: addToQueue, saveToDraft: true, "
         f"assets: [{{video: {{url: {json.dumps(url)}}}}}]"
         "}) { ... on PostActionSuccess { post { id status } } ... on MutationError { message } } }")
    result = graphql(token, q).get("createPost") or {}
    post = result.get("post") or {}
    post_id = post.get("id")
    if not post_id:
        raise RuntimeError("Tidak berhasil menyimpan draf Buffer: " + str(result.get("message", "unknown"))[:160])
    if str(post.get("status", "")).lower() != "draft":
        raise RuntimeError("Buffer tidak mengonfirmasi status draft. Periksa akun, jangan ulang otomatis.")
    return post_id

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("inspect", "create_drafts"), default="inspect")
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--metadata", type=Path, required=True)
    p.add_argument("--output", type=Path, default=Path("draft_result.json"))
    a = p.parse_args()
    if a.run_id <= 0:
        raise ValueError("Run ID tidak valid.")
    m = validate_metadata(a.metadata)
    summary = validate_video(a.video, m)
    outcome = {"run_id": a.run_id, "mode": a.mode, "validated_video": summary, "published": False}
    print("Video lolos pemeriksaan:", summary)
    if a.mode == "create_drafts":
        token = os.getenv("BUFFER_API_KEY", "")
        if not token:
            raise RuntimeError("BUFFER_API_KEY belum tersedia.")
        channels = get_channels(token)  # Check before uploading publicly to Cloudinary.
        url = upload(a.video, a.run_id)
        outcome["cloudinary_url"] = url
        outcome["buffer_drafts"] = {}
        for service in PLATFORMS:
            try:
                outcome["buffer_drafts"][service] = save_draft(token, channels[service], url, caption(m))
                print("Draf tersimpan untuk", service)
            except Exception as err:
                outcome.setdefault("errors", []).append(f"{service}: {type(err).__name__}: {str(err)[:120]}")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(outcome, indent=2, ensure_ascii=False), encoding="utf-8")
    if outcome.get("errors"):
        raise RuntimeError("Ada draf yang gagal; periksa hasil JSON. Jangan ulang otomatis.")
    print("SELESAI: tidak ada publikasi atau posting terjadwal.")

if __name__ == "__main__":
    main()
