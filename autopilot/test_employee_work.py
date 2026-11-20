"""Regression tests: evidence-only role coordination, no fabricated human activity."""
import json
from pathlib import Path
from unittest import TestCase

from autopilot.team_ops import build_record, PLATFORMS

class TeamWorkTests(TestCase):
    def plan(self):
        return {
            "date":"2026-11-21","theme":"Belajar pelan-pelan",
            "headings":[f"Langkah ke {i}: belajar konten" for i in range(1,6)],
            "bodies":[
                f"Langkah {i} pilih satu pertanyaan pemula lalu jawab dengan contoh jelas dan berguna setiap hari."
                for i in range(1,6)],
            "cta":"Cek informasi di link profil",
            "captions":{
                "tiktok":"Cari ide bermanfaat, cek link profil. Tautan afiliasi.",
                "facebook":"Mulai dari pertanyaan sederhana, cek link profil. Tautan afiliasi.",
                "youtube":"Belajar mulai dari nol, cek link profil. Tautan afiliasi."
            },
            "posting_time":"19:00",
            "reason":"Perkiraan waktu audiens tersedia selepas kerja."
        }

    def test_all_13_roles_with_youtube_not_instagram(self):
        board=build_record(plan=self.plan())
        self.assertEqual(len(board["roles"]),13)
        self.assertIn("YouTube",board["roles"]["raka"])
        self.assertEqual(board["stage"],"planned")
        self.assertEqual(board["tasks"]["citra"]["status"],"awaiting_buffer")
        self.assertEqual(board["tasks"]["dita"]["status"],"awaiting_publication_metrics")
        self.assertIn("not individual bot conversations",board["claim_scope"])

    def test_metadata_and_qc_evidence_required(self):
        plan=self.plan()
        with self.assertRaisesRegex(ValueError,"Metadata dan naskah"):
            build_record(plan=plan,metadata={"headings":plan["headings"],"bodies":plan["bodies"],"cta":"other"})
        board=build_record(plan=plan,metadata={k:plan[k] for k in ("headings","bodies","cta")})
        self.assertEqual(board["stage"],"media_verified")
        self.assertEqual(board["tasks"]["keisha"]["status"],"video_rendered")
        self.assertEqual(board["tasks"]["bagas"]["status"],"media_metadata_checked")

    def test_partial_buffer_results_do_not_claim_completed(self):
        plan=self.plan();meta={k:plan[k] for k in ("headings","bodies","cta")}
        result={"date":plan["date"],"status":"manual_review",
                "posts":{"youtube":{"id":"youtube-123","status":"scheduled"},
                         "facebook":{"id":"facebook-123","status":"scheduled"}},
                "errors":[{"platform":"tiktok","detail":"provider error"}]}
        board=build_record(plan=plan,metadata=meta,post_result=result)
        self.assertEqual(board["stage"],"manual_review")
        self.assertEqual(board["tasks"]["citra"]["status"],"manual_review_required")
        self.assertEqual(board["tasks"]["raka"]["status"],"buffer_scheduled")
        self.assertEqual(board["tasks"]["rina"]["scheduled_channels"],2)

    def test_all_three_scheduled_still_not_claimed_published(self):
        plan=self.plan();meta={k:plan[k] for k in ("headings","bodies","cta")}
        result={"date":plan["date"],"status":"scheduled","errors":[],
                "posts":{platform:{"id":platform+"-id","status":"scheduled"}
                         for platform in PLATFORMS}}
        board=build_record(plan=plan,metadata=meta,post_result=result)
        self.assertEqual(board["stage"],"scheduled")
        self.assertEqual(board["tasks"]["rina"]["scheduled_channels"],3)
        self.assertEqual(board["tasks"]["bima"]["status"],"awaiting_publication_verification")

    def test_existing_workflow_stores_role_board_not_extra_post(self):
        raw=(Path(__file__).resolve().parents[1]/".github/workflows/keisha_autopilot.yml").read_text("utf-8")
        self.assertIn("python autopilot/team_ops.py planned",raw)
        self.assertIn("ai_office_team_status.json",raw)
        self.assertIn("from autopilot.team_ops import build_record",raw)
        self.assertIn("env.RUN_MODE == 'schedule' || env.RUN_MODE == 'go_live'",raw)
        self.assertNotIn("TELEGRAM_BIMA_TOKEN",raw)
