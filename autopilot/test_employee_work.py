"""Safety tests for AI Office team board, no Telegram bot impersonation."""
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import employee_work as work

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
                "facebook":"Kamu bisa mulai dari pertanyaan sederhana, cek link profil. Tautan afiliasi.",
                "youtube":"Belajar mulai dari nol, cek link profil. Tautan afiliasi."
            },
            "posting_time":"19:00",
            "reason":"Perkiraan waktu audiens tersedia selepas kerja."
        }

    def test_has_13_correct_job_titles_and_no_faked_completion(self):
        from unittest.mock import patch
        p=self.plan()
        with patch.object(work,"normalize_saved_plan",return_value=p):
            board=work.prepare_board(p,ask_ai=False)
        self.assertEqual(len(board["roles"]),13)
        self.assertEqual(board["roles"]["raka"]["title"],"YouTube Shorts Specialist")
        self.assertEqual(board["roles"]["rina"]["title"],"HRD")
        self.assertEqual(board["roles"]["bima"]["title"],"CEO")
        self.assertEqual(board["roles"]["keisha"]["status"],"assigned")
        self.assertFalse(board["publication_confirmed"])
        self.assertFalse(board["live_office_synced"])
        self.assertEqual(board["verified_channels"],{})

    def test_finish_only_records_real_buffer_post_ids_and_audio_qc(self):
        p=self.plan()
        with patch.object(work,"normalize_saved_plan",return_value=p):
            board=work.prepare_board(p,ask_ai=False)
        result={"date":p["date"],"status":"manual_review",
                "video":{"fps":30,"width":720,"height":1280},
                "posts":{"youtube":{"id":"y123","status":"scheduled"},
                         "facebook":{"id":"f123","status":"scheduled"}},
                "errors":[{"platform":"tiktok","detail":"provider error"}]}
        final=work.finish_board(board,result)
        self.assertEqual(final["stage"],"manual_review")
        self.assertEqual(final["roles"]["citra"]["status"],"pending_manual_review")
        self.assertEqual(final["roles"]["raka"]["status"],"scheduled_by_buffer")
        self.assertEqual(final["roles"]["keisha"]["status"],"video_qc_recorded")
        self.assertFalse(final["publication_confirmed"])
        self.assertFalse(final["live_office_synced"])

    def test_independent_role_review_requests_are_scoped(self):
        p=self.plan()
        with patch.object(work,"ai_request",return_value=json.dumps({
            "prioritas":"Periksa pesan video",
            "risiko":"Jangan menjanjikan penghasilan",
            "saran":"Perjelas tindakan konkret"})) as request:
            for role in ("bima","bagas"):
                output=work.review_as_role(role,p)
                self.assertEqual(output["status"],"advice_available")
        self.assertEqual(request.call_count,2)
        first=request.call_args_list[0].args[0]
        self.assertIn("Bima",first[0]["content"])
        self.assertNotIn("Saya sudah posting",first[0]["content"])

    def test_integration_only_before_and_after_existing_schedule(self):
        workflow=Path(__file__).resolve().parents[1]/".github/workflows/keisha_autopilot.yml"
        raw=workflow.read_text(encoding="utf-8")
        self.assertIn("employee_work.py prepare",raw)
        self.assertIn("employee_work.py finish",raw)
        self.assertIn("autopilot_team.json",raw)
        self.assertIn("RUN_MODE == 'schedule' || env.RUN_MODE == 'go_live'",raw)
        self.assertNotIn("TELEGRAM_BIMA_TOKEN",raw)
