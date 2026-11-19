from datetime import date, datetime, timezone
from unittest import TestCase
import office_daily as m

class Tests(TestCase):
    def plan(self):
        return {
          'headings': [f'{i} Belajar Langkah Kecil' for i in range(5)],
          'bodies': [f'Langkah {i}: pilih satu pertanyaan penonton pemula, lalu jelaskan contoh tindakan yang sederhana dan realistis.' for i in range(5)],
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

    def test_workers_ai_legacy_response(self):
        self.assertEqual(m.extract_ai_text({'success': True, 'result': {'response': 'halo'}}), 'halo')

    def test_workers_ai_new_chat_completion_response(self):
        sample = {'success': True, 'result': {'choices': [
            {'message': {'role': 'assistant', 'content': '{"headings":[]}'}}]}}
        self.assertEqual(m.extract_ai_text(sample), '{"headings":[]}')

    def test_workers_ai_text_segments(self):
        sample = {'success': True, 'result': {'choices': [
            {'message': {'content': [{'type': 'text', 'text': 'bagian 1'},
                                      {'type': 'text', 'text': ' bagian 2'}]}}]}}
        self.assertEqual(m.extract_ai_text(sample), 'bagian 1 bagian 2')

    def test_workers_ai_empty_response_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'bentuk hasil'):
            m.extract_ai_text({'success': True, 'result': {'choices': []}})

    def test_ai_request_uses_supported_model_without_live_api(self):
        import io
        import json
        from unittest.mock import patch
        reply = {'success': True, 'result': {'choices': [
            {'message': {'content': 'contoh teks'}}]}}
        env = {'CLOUDFLARE_AI_API_TOKEN': 'test-only',
               'CLOUDFLARE_ACCOUNT_ID': 'a'*32}
        with patch.dict('os.environ', env):
            with patch.object(m.urllib.request, 'urlopen',
                              return_value=io.BytesIO(json.dumps(reply).encode())) as mock:
                actual = m.ai_request([{'role': 'user', 'content': 'tes'}])
        self.assertEqual(actual, 'contoh teks')
        req = mock.call_args.args[0]
        self.assertIn('/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast', req.full_url)
        self.assertEqual(json.loads(req.data)['stream'], False)
        self.assertEqual(json.loads(req.data)['response_format'], {'type': 'json_object'})
        self.assertEqual(json.loads(req.data)['max_tokens'], 3000)


    def test_plan_retries_overlong_heading_then_accepts_valid_response(self):
        import json
        from unittest.mock import patch
        bad = self.plan()
        bad['headings'][0] = 'Judul panjang untuk konten ' + 'tentang audiens ' * 7
        good = self.plan()
        with patch.object(m, 'ai_request',
                          side_effect=[json.dumps(bad), json.dumps(good)]) as ai:
            result = m.plan_for_day(date(2026, 11, 20))
        self.assertEqual(result['headings'], good['headings'])
        self.assertEqual(ai.call_count, 2)
        self.assertIn('heading 1', ai.call_args.args[0][-1]['content'])
        self.assertEqual(result['date'], '2026-11-20')

    def test_plan_retries_forbidden_format_then_accepts_valid_response(self):
        import json
        from unittest.mock import patch
        bad = self.plan()
        bad['headings'][0] = 'Judul untuk pemula [ubah sesuai tema]'
        with patch.object(m, 'ai_request',
                          side_effect=[json.dumps(bad), json.dumps(self.plan())]) as ai:
            result = m.plan_for_day(date(2026, 11, 20))
        self.assertEqual(result['posting_time'], '19:00')
        self.assertEqual(ai.call_count, 2)

    def test_plan_stops_after_three_invalid_replies_without_fallback(self):
        import json
        from unittest.mock import patch
        bad = self.plan()
        bad['headings'][0] = 'x'
        with patch.object(m, 'ai_request', return_value=json.dumps(bad)) as ai:
            with self.assertRaisesRegex(RuntimeError, 'tiga percobaan'):
                m.plan_for_day(date(2026, 11, 20))
        self.assertEqual(ai.call_count, 3)


    def test_workers_ai_json_object_result(self):
        import json
        obj = self.plan()
        response = {'success': True, 'result': {'response': obj}}
        self.assertEqual(json.loads(m.extract_ai_text(response)), obj)

    def test_workers_ai_empty_chat_content_has_safe_diagnostic(self):
        reply = {'success': True, 'result': {'choices': [{
            'finish_reason': 'length',
            'message': {'content': '', 'reasoning': 'private-not-for-logs'}}]}}
        with self.assertRaises(m.AIEmptyResponseError) as ctx:
            m.extract_ai_text(reply)
        self.assertIn('finish_reason=length', str(ctx.exception))
        self.assertNotIn('private-not-for-logs', str(ctx.exception))

    def test_plan_retries_empty_ai_response_once_then_succeeds(self):
        import json
        from unittest.mock import patch
        with patch.object(m, 'ai_request', side_effect=[
            m.AIEmptyResponseError('empty model output'),
            json.dumps(self.plan())]) as ai:
            plan = m.plan_for_day(date(2026, 11, 20))
        self.assertEqual(ai.call_count, 2)
        self.assertEqual(plan['posting_time'], '19:00')

    def test_plan_aborts_after_three_empty_ai_responses(self):
        from unittest.mock import patch
        with patch.object(m, 'ai_request',
                          side_effect=m.AIEmptyResponseError('empty model output')) as ai:
            with self.assertRaisesRegex(RuntimeError, 'tiga percobaan'):
                m.plan_for_day(date(2026, 11, 20))
        self.assertEqual(ai.call_count, 3)

    def test_plan_does_not_retry_ai_api_errors(self):
        from unittest.mock import patch
        with patch.object(m, 'ai_request', side_effect=RuntimeError('HTTP 401')) as ai:
            with self.assertRaisesRegex(RuntimeError, 'HTTP 401'):
                m.plan_for_day(date(2026, 11, 20))
        self.assertEqual(ai.call_count, 1)

    def test_string_validation_reports_length_without_model_content(self):
        very_long = 'teks-rahasia-' * 8
        with self.assertRaises(ValueError) as ctx:
            m.clean_string(very_long, 68, 'heading 1')
        self.assertIn('heading 1', str(ctx.exception))
        self.assertIn('karakter', str(ctx.exception))
        self.assertNotIn('teks-rahasia', str(ctx.exception))

    def test_caption_missing_link_is_completed_once(self):
        data = self.plan()
        data['captions'] = {
            p: 'Ini cara mengevaluasi ide konten untuk pemula secara realistis'
            for p in ('tiktok', 'facebook', 'youtube')
        }
        plan = m.validate_plan(data)
        for caption in plan['captions'].values():
            self.assertIn('lynk.id/dirgakhaa', caption)
            self.assertIn('Tautan afiliasi.', caption)
            self.assertEqual(caption.count('lynk.id/dirgakhaa'), 1)
            self.assertEqual(caption.count('Tautan afiliasi.'), 1)

    def test_caption_existing_link_and_disclosure_not_duplicated(self):
        text = 'Pelajari materinya lewat lynk.id/dirgakhaa. Tautan afiliasi.'
        self.assertEqual(m.complete_caption(text, 'youtube'), text)

    def test_caption_without_link_only_adds_missing_link(self):
        text = 'Baca penjelasan singkat ini, tautan afiliasi tersedia.'
        actual = m.complete_caption(text, 'tiktok')
        self.assertIn('lynk.id/dirgakhaa', actual)
        self.assertEqual(actual.lower().count('afiliasi'), 1)

    def test_caption_rejects_unapproved_external_link(self):
        with self.assertRaisesRegex(ValueError, 'bukan link profil resmi'):
            m.complete_caption('Cek info di https://contoh.com/promo', 'facebook')

    def test_caption_rejects_empty_or_nontext(self):
        for value in ('', None, {}, 5):
            with self.assertRaises(ValueError):
                m.complete_caption(value, 'tiktok')

    def test_plan_missing_link_succeeds_on_single_ai_request(self):
        import json
        from unittest.mock import patch
        data = self.plan()
        data['captions'] = {
            p: 'Konten singkat yang membantu pemula memahami strategi konten'
            for p in ('tiktok', 'facebook', 'youtube')
        }
        with patch.object(m, 'ai_request', return_value=json.dumps(data)) as ai:
            result = m.plan_for_day(date(2026, 11, 20))
        self.assertEqual(ai.call_count, 1)
        self.assertTrue(all('lynk.id/dirgakhaa' in text
                            for text in result['captions'].values()))

    def test_caption_does_not_truncate_long_text(self):
        data = self.plan()
        data['captions']['youtube'] = 'Edukasi strategi konten yang berguna. ' * 10
        with self.assertRaisesRegex(ValueError, 'youtube: panjang'):
            m.validate_plan(data)



    def test_scene_149_chars_from_live_failure_now_valid(self):
        data = self.plan()
        base = ('Mulai dengan mencatat satu masalah penonton, lalu tampilkan contoh '
                'perubahan judul yang lebih jelas supaya penonton tahu langkah praktis.')
        scene = base.ljust(149, '!')
        self.assertEqual(len(scene), 149)
        data['bodies'][2] = scene
        self.assertEqual(m.validate_plan(data)['bodies'][2], scene)

    def test_scene_220_char_limit_accepted_without_truncation(self):
        data = self.plan()
        base = ('Coba pilih satu masalah penonton yang nyata, lalu tunjukkan dua contoh '
                'judul berbeda dan jelaskan kenapa salah satunya lebih mudah dipahami. ')
        scene = (base * 3)[:220]
        self.assertEqual(len(scene), 220)
        data['bodies'][2] = scene
        self.assertEqual(m.validate_plan(data)['bodies'][2], scene)

    def test_scene_221_char_limit_still_rejected(self):
        data = self.plan()
        base = ('Coba pilih satu masalah penonton yang nyata, lalu tunjukkan dua contoh '
                'judul berbeda dan jelaskan kenapa salah satunya lebih mudah dipahami. ')
        scene = (base * 3)[:221]
        self.assertEqual(len(scene), 221)
        data['bodies'][2] = scene
        with self.assertRaisesRegex(ValueError, r'body 3: panjang 221 karakter; wajib 10-220'):
            m.validate_plan(data)

    def test_reject_real_short_scene_from_previous_ai_plan(self):
        bad = self.plan()
        bad['bodies'] = [
            'Konten harus menarik',
            'Adegan vertikal lebih menarik',
            'Konten bermanfaat sangat penting',
            'Visual lebih berdampak',
            'Konten harus disusun rapi'
        ]
        with self.assertRaisesRegex(ValueError, 'body 1 terlalu singkat'):
            m.validate_plan(bad)

    def test_reject_padded_scene_without_useful_word_count(self):
        bad = self.plan()
        bad['bodies'][2] = 'konten ' * 12
        with self.assertRaisesRegex(ValueError, 'body 3 terlalu singkat'):
            m.validate_plan(bad)

    def test_plan_revises_short_scene_using_previous_draft(self):
        import json
        from unittest.mock import patch
        bad = self.plan()
        bad['bodies'][0] = 'Konten harus menarik'
        good = self.plan()
        with patch.object(m, 'ai_request',
                          side_effect=[json.dumps(bad), json.dumps(good)]) as ai:
            result = m.plan_for_day(date(2026, 11, 20))
        self.assertEqual(ai.call_count, 2)
        self.assertEqual(result['bodies'], good['bodies'])
        revised_messages = ai.call_args.args[0]
        self.assertEqual(revised_messages[-2]['role'], 'assistant')
        self.assertIn('Konten harus menarik', revised_messages[-2]['content'])
        self.assertIn('body 1', revised_messages[-1]['content'])

    def test_render_workflow_is_preview_only(self):
        from pathlib import Path
        workflow = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'keisha_autopilot.yml'
        text = workflow.read_text(encoding='utf-8')
        self.assertIn('          - render', text)
        self.assertIn('actions/download-artifact@v4', text)
        self.assertIn("run-id: ${{ inputs.source_plan_run_id }}", text)
        self.assertIn("if: ${{ env.RUN_MODE == 'render' || env.RUN_MODE == 'schedule' }}", text)
        self.assertIn("name: QC video MP4 dan audio (tidak mengunggah)", text)
        self.assertIn("if: ${{ env.RUN_MODE == 'schedule' }}", text)
        self.assertNotIn("if: ${{ env.RUN_MODE == 'render' }}\n        run: |\n          python autopilot/office_daily.py schedule", text)
        start = text.index('      - name: Pastikan video valid lalu jadwalkan SATU ke tiap channel')
        end = text.index('      - name: Laporkan kegagalan satu kali tanpa retry posting',start)
        self.assertIn("if: ${{ env.RUN_MODE == 'schedule' }}", text[start:end])
        self.assertNotIn('RUN_MODE == \'render\'', text[start:end])

    def test_cannot_invent_ai(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'CLOUDFLARE_AI_API_TOKEN':'','CLOUDFLARE_ACCOUNT_ID':''}):
            with self.assertRaises(RuntimeError): m.ai_request([{'role':'user','content':'x'}])