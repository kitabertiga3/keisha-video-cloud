"""Pure offline tests; no Buffer or Cloudinary write requests."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import social_drafts as module


class SocialDraftsTests(unittest.TestCase):
    def metadata(self):
        return {
            "audio_verified": True, "narration_verified": True, "voice": "natural",
            "duration": 35.2,
            "headings": ["Judul baik"] * 5, "bodies": ["Isi edukatif"] * 5,
            "cta": "Cek informasi ebook melalui link profil",
        }

    def test_metadata_accepts_clean_script(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "metadata.json"
            p.write_text(json.dumps(self.metadata()), encoding="utf-8")
            self.assertEqual(len(module.validate_metadata(p)["headings"]), 5)

    def test_metadata_rejects_json_artifacts(self):
        for suspicious in ('"],', 'gaya: otomatis', 'suara natural', '{"headings":'):
            with self.subTest(suspicious=suspicious), tempfile.TemporaryDirectory() as d:
                data = self.metadata()
                data["bodies"][2] = suspicious
                p = Path(d) / "metadata.json"
                p.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    module.validate_metadata(p)

    def test_video_rejects_invalid_dimensions(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mp4"
            p.write_bytes(b"0" * 20000)
            ffprobe = {"streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 720, "height": 720},
                {"codec_type": "audio", "codec_name": "aac"}],
                "format": {"duration": "35.2"}}
            fake = subprocess.CompletedProcess([], 0, stdout=json.dumps(ffprobe), stderr="")
            with patch.object(module.subprocess, "run", return_value=fake):
                with self.assertRaises(ValueError):
                    module.validate_video(p, self.metadata())

    def test_video_requires_at_least_23_fps_before_upload(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.mp4"
            p.write_bytes(b"0" * 20000)
            data = {"streams": [
                {"codec_type":"video", "codec_name":"h264","width":720,
                 "height":1280,"avg_frame_rate":"15/1"},
                {"codec_type":"audio","codec_name":"aac"}],
                "format":{"duration":"35.2"}}
            with patch.object(module.subprocess,"run", return_value=subprocess.CompletedProcess(
                        [],0,stdout=json.dumps(data),stderr="")):
                with self.assertRaisesRegex(ValueError,"FPS"):
                    module.validate_video(p,self.metadata())
            data['streams'][0]['avg_frame_rate']="30/1"
            with patch.object(module.subprocess,"run", return_value=subprocess.CompletedProcess(
                        [],0,stdout=json.dumps(data),stderr="")):
                validated=module.validate_video(p,self.metadata())
            self.assertEqual(validated['fps'],30)

    def test_render_encoder_defaults_to_30fps(self):
        render=(Path(__file__).resolve().parents[1]/'render_studio.py').read_text(encoding='utf-8')
        self.assertIn("'fps=30,format=yuv420p'",render)
        self.assertNotIn("'fps=15,format=yuv420p'",render)

    def test_draft_mutation_cannot_publish(self):
        observed = []
        def fake_graphql(token, query):
            observed.append(query)
            return {"createPost": {"post": {"id": "draft-123", "status": "draft"}}}
        with patch.object(module, "graphql", side_effect=fake_graphql):
            result = module.save_draft("fake", "channel-id", "https://res.cloudinary.com/x/video/upload/v1/a.mp4", "Test")
        self.assertEqual(result, "draft-123")
        self.assertIn("saveToDraft: true", observed[0])
        self.assertIn("assets:", observed[0])
        self.assertNotIn("shareNow", observed[0])


if __name__ == "__main__":
    unittest.main()
