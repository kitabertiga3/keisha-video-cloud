from datetime import date, datetime, timezone
from unittest import TestCase
import office_daily as m

class Tests(TestCase):
    def plan(self):
        return {
          'headings': [f'{i} Belajar Langkah Kecil' for i in range(5)],
          'bodies': [f'Langkah {i} penting untuk memahami kebutuhan penonton pemula' for i in range(5)],
          'cta': 'Cek detail produk di link profil',
          'captions': {x:'Lihat info produk digital melalui link profil. Tautan afiliasi. #Belajar' for x in ('tiktok','facebook','youtube')},
          'posting_time':'19:00', 'reason':'Jam hipotesis audiens sering membuka aplikasi malam hari'
        }
    def test_plan_valid(self):
        self.assertEqual(m.validate_plan(self.plan())['posting_time'],'19:00')
    def test_reject_bracket_and_settings(self):
        for v in ('Musik: tenang','],[',', , ,'):
            data=self.plan();data['headings'][0]=v
            with self.assertRaises(ValueError):m.validate_plan(data)
    def test_reject_duplicates(self):
        data=self.plan();data['headings'][1]=data['headings'][0]
        with self.assertRaises(ValueError):m.validate_plan(data)
    def test_bad_time(self):
        data=self.plan();data['posting_time']='03:00'
        with self.assertRaises(ValueError):m.validate_plan(data)
    def test_schedule_future(self):
        when=m.due_at(date(2026,11,20),'19:00',now=datetime(2026,11,20,0,0,tzinfo=timezone.utc))
        self.assertEqual(when.isoformat(),'2026-11-20T12:00:00+00:00')
    def test_schedule_refuses_late(self):
        with self.assertRaises(ValueError):
            m.due_at(date(2026,11,20),'19:00',now=datetime(2026,11,20,11,30,tzinfo=timezone.utc))
    def test_cannot_invent_ai(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'CLOUDFLARE_AI_API_TOKEN':'','CLOUDFLARE_ACCOUNT_ID':''}):
            with self.assertRaises(RuntimeError): m.ai_request([{'role':'user','content':'x'}])