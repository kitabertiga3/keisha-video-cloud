import tempfile
import unittest
from pathlib import Path
from server import validate
from video_engine import card, fit_lines
from PIL import Image, ImageDraw

class CloudTest(unittest.TestCase):
    def test_defaults(self):
        headings,bodies,cta = validate({})
        self.assertEqual(len(headings),5)
        self.assertEqual(len(bodies),5)
        self.assertTrue(cta)

    def test_reject_overlong(self):
        with self.assertRaises(ValueError): validate({'headings':['x'*100]*5})

    def test_reject_wrong_slide_count(self):
        with self.assertRaises(ValueError): validate({'bodies':['x']})

    def test_make_one_card(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'one.png'
            card(p,1,'Jangan Asal Pilih Produk Digital','Riset dulu sebelum memilih produk untuk promosi.','Baca detail di link bio')
            with Image.open(p) as im: self.assertEqual(im.size,(720,1280))

if __name__=='__main__': unittest.main()
