"""Regression tests for the brief cleanup that prevents leaked voice/music fields."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render_studio import clean_plain_video_topic


class CleanTopicTests(unittest.TestCase):
    def test_user_reported_leak(self):
        raw = "3 kesalahan pemula saat memulai bisnis digital, , , musik: tenang"
        self.assertEqual(clean_plain_video_topic(raw),
                         "3 kesalahan pemula saat memulai bisnis digital")

    def test_multiple_inline_settings(self):
        raw = "3 kesalahan pemula, gaya: otomatis, suara: natural, musik: tenang"
        self.assertEqual(clean_plain_video_topic(raw), "3 kesalahan pemula")

    def test_comma_cleanup(self):
        self.assertEqual(clean_plain_video_topic("A, , , B"), "A, B")

    def test_json_stays_intact(self):
        source = '{"headings":["A"],"bodies":["B"],"cta":"C"}'
        self.assertEqual(clean_plain_video_topic(source), source)

    def test_multiline_storyboard_stays_intact(self):
        source = "1. Judul | Isi adegan\n2. Judul lain | Isi lain"
        self.assertEqual(clean_plain_video_topic(source), source)

    def test_plain_text_without_settings(self):
        source = "Tips memilih produk digital untuk pemula"
        self.assertEqual(clean_plain_video_topic(source), source)


if __name__ == "__main__":
    unittest.main()
