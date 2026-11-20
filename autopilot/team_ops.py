"""Evidence-based AI Affiliate Office task handoffs.

This documents real workflow results, not fabricated conversations by Telegram bots.
No external writes or posting; reporting belongs to existing Keisha workflow.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

DIVISIONS = {
    "bima": "CEO / operasi dan kebijakan",
    "rina": "HRD / koordinasi staf",
    "naya": "riset topik (hipotesis, bukan data live)",
    "nadia": "strategi konten",
    "fajar": "naskah",
    "keisha": "video dan suara",
    "bagas": "QC media",
    "citra": "TikTok",
    "arga": "Facebook",
    "raka": "YouTube Shorts",
    "dimas": "kepatuhan produk afiliasi",
    "dita": "analitik hanya jika metrik tersedia",
    "reza": "keamanan dan koneksi API",
}
PLATFORMS = {"tiktok": "citra", "facebook": "arga", "youtube": "raka"}
ROUTE = "AI AFFILIATE OFFICE | HQ"
STATES = ("planned", "media_verified", "scheduled", "manual_review")


def _read(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("Dokumen sumber harus objek JSON")
    return obj


def build_record(*, plan: dict, metadata: dict | None = None,
                 post_result: dict | None = None) -> dict:
    day = plan.get("date")
    if not isinstance(day, str):
        raise ValueError("Tanggal naskah belum tersedia")
    datetime.strptime(day, "%Y-%m-%d")
    headings = plan.get("headings")
    if not isinstance(headings, list) or len(headings) != 5 or not all(
        isinstance(x, str) and x.strip() for x in headings
    ):
        raise ValueError("Naskah lima adegan belum disetujui")
    slots = plan.get("captions")
    if not isinstance(slots, dict) or any(
        not isinstance(slots.get(p), str) or not slots[p].strip() for p in PLATFORMS
    ):
        raise ValueError("Caption tiga platform belum tersedia")
    tasks = {
        "bima": {"status": "coordinating_workflow"},
        "rina": {"status": "awaiting_verified_report"},
        "naya": {"status": "topic_selected", "evidence": plan.get("theme", "")},
        "nadia": {"status": "content_plan_ready", "evidence": day},
        "fajar": {"status": "script_ready", "evidence": "5 scenes"},
        "dimas": {"status": "affiliate_disclosure_requires_qc"},
        "keisha": {"status": "awaiting_video"},
        "bagas": {"status": "awaiting_media_qc"},
        "citra": {"status": "awaiting_buffer"},
        "arga": {"status": "awaiting_buffer"},
        "raka": {"status": "awaiting_buffer"},
        "dita": {"status": "awaiting_publication_metrics"},
        "reza": {"status": "connections_checked_by_preflight_only"},
    }
    stage = "planned"
    if metadata is not None:
        for name in ("headings", "bodies", "cta"):
            if metadata.get(name) != plan.get(name):
                raise ValueError("Metadata dan naskah tidak cocok: " + name)
        tasks["keisha"] = {"status": "video_rendered", "evidence": "metadata matches plan"}
        tasks["bagas"] = {"status": "media_metadata_checked",
                          "evidence": "frame rate/audio QC run separately in workflow"}
        stage = "media_verified"
    if post_result is not None:
        if metadata is None:
            raise ValueError("Jadwal tidak boleh dicatat sebelum QC media")
        if post_result.get("date") != day:
            raise ValueError("Tanggal hasil Buffer berbeda")
        scheduled = post_result.get("posts") or {}
        for platform, owner in PLATFORMS.items():
            post = scheduled.get(platform)
            if isinstance(post, dict) and post.get("status") == "scheduled" and post.get("id"):
                tasks[owner] = {"status": "buffer_scheduled", "post_id": post["id"]}
            else:
                tasks[owner] = {"status": "manual_review_required"}
        complete = (post_result.get("status") == "scheduled"
                    and not post_result.get("errors")
                    and all(tasks[owner]["status"] == "buffer_scheduled"
                            for owner in PLATFORMS.values()))
        stage = "scheduled" if complete else "manual_review"
        tasks["rina"] = {"status": "schedule_report_available",
                         "scheduled_channels": sum(
                             tasks[x]["status"] == "buffer_scheduled"
                             for x in PLATFORMS.values())}
        tasks["bima"] = {"status": "awaiting_publication_verification"}
    return {"office": ROUTE, "date": day, "stage": stage,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "roles": DIVISIONS, "tasks": tasks,
            "claim_scope": "GitHub workflow evidence, not individual bot conversations"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=STATES)
    parser.add_argument("--plan", default="autopilot_plan.json")
    parser.add_argument("--metadata", default="Keisha_Video_Cloud_Starter_v1/hasil/metadata.json")
    parser.add_argument("--result", default="autopilot_result.json")
    parser.add_argument("--output", default="ai_office_team_status.json")
    args = parser.parse_args()
    plan = _read(Path(args.plan))
    meta = _read(Path(args.metadata)) if args.stage != "planned" else None
    result = _read(Path(args.result)) if args.stage in ("scheduled", "manual_review") else None
    record = build_record(plan=plan, metadata=meta, post_result=result)
    if args.stage != record["stage"]:
        # Never claim completion when the underlying evidence does not match.
        raise RuntimeError("Status tidak cocok: requested=" + args.stage +
                           " actual=" + record["stage"])
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print("AI Office team evidence saved: " + record["stage"])


if __name__ == "__main__":
    main()
