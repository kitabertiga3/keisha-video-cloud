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
    # TikTok upload requires 23–60 fps. Check this BEFORE Cloudinary/Buffer writes.
    from fractions import Fraction
    try:
        fps = float(Fraction(str(v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1")))
    except (ValueError, ZeroDivisionError, OverflowError):
        fps = 0.0
    if not (23 <= fps <= 60):
        raise ValueError(f"FPS video {fps:g} di luar batas TikTok 23–60. Jangan unggah atau jadwalkan.")
    if not (3 <= seconds <= 175) or abs(float(m.get("duration", seconds)) - seconds) > 3:
        raise ValueError("Durasi MP4 tidak sesuai metadata atau terlalu panjang.")
    return {"width": w, "height": h, "seconds": round(seconds, 2), "fps": round(fps, 3)}

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

def draft_metadata(platform, title=""):
    """Required Buffer GraphQL per-platform fields, from official API schema."""
    if platform == "tiktok":
        return ""
    if platform == "facebook":
        return "metadata: {facebook: {type: reel}}, "
    if platform == "youtube":
        title = str(title).strip()
        if not title or len(title) > 100:
            raise ValueError("Judul YouTube wajib ada (1-100 karakter).")
        return ("metadata: {youtube: {title: " + json.dumps(title, ensure_ascii=False)
                + ', categoryId: "27", isAiGenerated: true, madeForKids: false, privacy: public}}, ')
    raise ValueError("Platform draf tidak dikenali.")


def save_draft(token, channel_id, url, text, *, platform="tiktok", title=""):
    # saveToDraft: true is required; never schedule or publish in draft mode.
    metadata = draft_metadata(platform, title)
    q = ("mutation { createPost(input: {"
         f"text: {json.dumps(text, ensure_ascii=False)}, "
         f"channelId: {json.dumps(channel_id)}, schedulingType: automatic, "
         "mode: addToQueue, saveToDraft: true, "
         + metadata +
         f"assets: [{{video: {{url: {json.dumps(url)}}}}}]"
         "}) { ... on PostActionSuccess { post { id status } } ... on MutationError { message } } }")
    result = graphql(token, q).get("createPost") or {}
    post = result.get("post") or {}
    post_id = post.get("id")
    if not post_id:
        raise RuntimeError("Buffer menolak draf " + platform + ": "
                           + str(result.get("message", "tanpa alasan spesifik"))[:250])
    if str(post.get("status", "")).lower() != "draft":
        raise RuntimeError("Buffer tidak mengonfirmasi status draft untuk " + platform +
                           ". Periksa akun, jangan ulang otomatis.")
    return post_id


def find_matching_posts(token, channel_id, caption_text, media_url, max_pages=30):
    """Read only: scan channel posts before any draft write; fail closed on incomplete scans."""
    orgs = (graphql(token, "query { account { organizations { id } } }")
            .get("account") or {}).get("organizations") or []
    if not orgs:
        raise RuntimeError("Buffer tidak mengembalikan organization untuk pemeriksaan draf.")
    matches = {}
    for org in orgs:
        after = None
        visited = set()
        for _ in range(max_pages):
            params = (f"first: 50, input: {{organizationId: {json.dumps(org['id'])}, "
                      f"filter: {{status: [draft, needs_approval, scheduled, sending, sent, error], "
                      f"channelIds: [{json.dumps(channel_id)}]}}}}")
            if after:
                params = "after: " + json.dumps(after) + ", " + params
            result = graphql(token, "query { posts(" + params + ") { edges { node { id text status channelId assets { source } } } pageInfo { hasNextPage endCursor } } }")
            posts = result.get("posts")
            if not isinstance(posts, dict):
                raise RuntimeError("Buffer tidak mengembalikan daftar posts; pemeriksaan duplikat dibatalkan.")
            for item in posts.get("edges") or []:
                post = (item or {}).get("node") or {}
                if str(post.get("channelId")) != str(channel_id):
                    continue
                same_text = bool(caption_text.strip()) and str(post.get("text") or "").strip() == caption_text.strip()
                same_media = any(media_url == (asset or {}).get("source") for asset in (post.get("assets") or []))
                if (same_text or same_media) and post.get("id"):
                    matches[post["id"]] = {"id": post["id"], "status": post.get("status")}
            page = posts.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            cursor = page.get("endCursor")
            if not cursor or cursor in visited:
                raise RuntimeError("Buffer pagination tidak konsisten; hentikan untuk mencegah draf ganda.")
            visited.add(cursor)
            after = cursor
        else:
            raise RuntimeError("Terlalu banyak halaman Buffer; pemeriksaan duplikat belum lengkap.")
    return list(matches.values())


def save_scheduled_post(token, channel_id, url, text, *, platform, title, due_at):
    """Schedule one future post using the metadata also required by drafts."""
    if not isinstance(due_at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.000Z", due_at):
        raise ValueError("Waktu jadwal wajib UTC ISO-8601.")
    metadata = draft_metadata(platform, title)
    q = ("mutation { createPost(input: {"
         f"text: {json.dumps(text, ensure_ascii=False)}, "
         f"channelId: {json.dumps(channel_id)}, "
         "schedulingType: automatic, mode: customScheduled, "
         f"dueAt: {json.dumps(due_at)}, "
         + metadata +
         f"assets: [{{video: {{url: {json.dumps(url)}}}}}]"
         "}) { ... on PostActionSuccess { post { id dueAt status } } "
         "... on MutationError { message } } }")
    outcome = graphql(token, q).get("createPost") or {}
    post = outcome.get("post") or {}
    if not post.get("id"):
        raise RuntimeError("Buffer menolak jadwal " + platform + ": "
                           + str(outcome.get("message","tidak ada alasan"))[:220])
    if str(post.get("status") or "").lower() != "scheduled":
        raise RuntimeError("Buffer tidak mengonfirmasi jadwal " + platform +
                           " (status=" + str(post.get("status"))[:30] + ").")
    return {"id":post["id"], "status":post["status"], "due_at":post.get("dueAt")}



def save_publish_now_post(token, channel_id, url, text, *, platform, title):
    """Submit one video for immediate Buffer delivery; never retry on ambiguity."""
    # No write if Buffer already has identical caption or this media on this channel.
    # Fail closed if the inventory cannot be read fully.
    prior = find_matching_posts(token, channel_id, text, url)
    if prior:
        raise RuntimeError("POTENSI DUPLIKAT "+platform+": Buffer sudah memiliki posting identik (ID "
                           + ",".join(str(x["id"]) for x in prior[:3]) + "). Jangan ulang.")
    metadata = draft_metadata(platform, title)
    q = ("mutation { createPost(input: {"
         f"text: {json.dumps(text, ensure_ascii=False)}, "
         f"channelId: {json.dumps(channel_id)}, "
         "schedulingType: automatic, mode: shareNow, "
         + metadata +
         f"assets: [{{video: {{url: {json.dumps(url)}}}}}]"
         "}) { ... on PostActionSuccess { post { id status } } "
         "... on MutationError { message } } }")
    result = graphql(token, q).get("createPost") or {}
    post = result.get("post") or {}
    if not post.get("id"):
        raise RuntimeError("Buffer menolak Publish Now " + platform + ": "
                           + str(result.get("message", "tanpa konfirmasi"))[:220])
    status = str(post.get("status") or "").lower()
    if status not in ("sent", "sending", "scheduled"):
        raise RuntimeError("Buffer status Publish Now belum pasti: " + status
                           + ". Jangan ulangi otomatis.")
    return {"id": post["id"], "status": status, "due_at": None}


def read_post_by_id(token, post_id):
    """Read the original Buffer post directly, regardless of rewritten asset URLs."""
    if not isinstance(post_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", post_id):
        raise ValueError("ID draf Buffer tidak valid.")
    q = ('query { post(input: {id: ' + json.dumps(post_id)
         + '}) { id status channelId createdAt assets { source } } }')
    try:
        post = graphql(token, q).get("post")
    except RuntimeError as exc:
        # Inaccessible/deleted post IDs are a diagnostic result, NOT retry permission.
        if "post not found for id:" in str(exc).lower():
            return {"id":post_id, "status":"not_found", "channel_id":None,
                    "reachable":False, "asset_count":0}
        raise
    if not isinstance(post, dict) or post.get("id") != post_id:
        return {"id":post_id, "status":"not_verified", "channel_id":None,
                "reachable":False, "asset_count":0}
    return {"id":post_id, "status":post.get("status"),
            "channel_id":post.get("channelId"), "created_at":post.get("createdAt"),
            "reachable":True, "asset_count":len(post.get("assets") or [])}


def summarize_channel_drafts(token, channel_id, audit_day, max_pages=15):
    """Read-only inventory of channel drafts created on the audit date."""
    orgs = ((graphql(token, "query { account { organizations { id } } }")
             .get("account") or {}).get("organizations") or [])
    if not orgs:
        raise RuntimeError("Tidak ada organization Buffer yang dapat diaudit.")
    candidates = {}
    scanned = 0
    for org in orgs:
        after = None
        seen = set()
        for _ in range(max_pages):
            query_args = ('first: 50, input: {organizationId: '
                          + json.dumps(org["id"])
                          + ', filter: {status: [draft], channelIds: ['
                          + json.dumps(channel_id) + ']}}')
            if after:
                query_args = 'after: ' + json.dumps(after) + ', ' + query_args
            data = graphql(token, 'query { posts(' + query_args
                           + ') { edges { node { id status channelId createdAt } } '
                           'pageInfo { hasNextPage endCursor } } }')
            result = data.get("posts")
            if not isinstance(result, dict):
                raise RuntimeError("Buffer tidak mengembalikan inventaris draf.")
            for edge in result.get("edges") or []:
                post = (edge or {}).get("node") or {}
                scanned += 1
                created = str(post.get("createdAt") or "")
                if (str(post.get("channelId")) == str(channel_id)
                        and created.startswith(audit_day) and post.get("id")):
                    candidates[post["id"]] = {"id":post["id"],
                                               "status":post.get("status"),
                                               "created_at":created}
            page = result.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                break
            cursor = page.get("endCursor")
            if not cursor or cursor in seen:
                raise RuntimeError("Pagination draf Buffer tidak konsisten.")
            seen.add(cursor)
            after = cursor
        else:
            raise RuntimeError("Inventaris draf Buffer terlalu panjang untuk diverifikasi.")
    return {"scanned":scanned,
            "created_on_audit_date":sorted(candidates.values(),
                 key=lambda p: p["created_at"], reverse=True)[:20]}


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
