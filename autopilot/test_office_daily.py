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
        self.assertIn("if: ${{ env.RUN_MODE == 'render' || env.RUN_MODE == 'drafts' || env.RUN_MODE == 'schedule' || env.RUN_MODE == 'publish_now' || env.RUN_MODE == 'go_live' || env.RUN_MODE == 'ceo_live_test' }}", text)
        self.assertIn("name: QC video MP4 dan audio (tidak mengunggah)", text)
        self.assertIn("if: ${{ env.RUN_MODE == 'schedule' || env.RUN_MODE == 'go_live' }}", text)
        self.assertNotIn("if: ${{ env.RUN_MODE == 'render' }}\n        run: |\n          python autopilot/office_daily.py schedule", text)
        start = text.index('      - name: Pastikan video valid lalu jadwalkan SATU ke tiap channel')
        end = text.index('      - name: Laporkan kegagalan satu kali tanpa retry posting',start)
        self.assertIn("if: ${{ env.RUN_MODE == 'schedule' || env.RUN_MODE == 'go_live' }}", text[start:end])
        self.assertNotIn('RUN_MODE == \'render\'', text[start:end])

    def test_render_prepares_ffmpeg_before_voice_and_video(self):
        from pathlib import Path
        workflow = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'keisha_autopilot.yml'
        content = workflow.read_text(encoding='utf-8')
        prepare = content.index('      - name: Siapkan FFmpeg dan FFprobe untuk suara serta MP4')
        install = content.index('      - name: Siapkan suara dan musik gratis untuk Keisha')
        render = content.index('      - name: Render MP4 menggunakan mesin Keisha yang sekarang')
        self.assertLess(prepare, install)
        self.assertLess(install, render)
        step = content[prepare:install]
        self.assertIn("if: ${{ env.RUN_MODE == 'render' || env.RUN_MODE == 'drafts' || env.RUN_MODE == 'schedule' || env.RUN_MODE == 'publish_now' || env.RUN_MODE == 'go_live' || env.RUN_MODE == 'ceo_live_test' }}", step)
        self.assertIn('apt-get install -y ffmpeg', step)
        self.assertIn("shutil.which('ffmpeg')", step)
        self.assertIn("shutil.which('ffprobe')", step)
        self.assertNotIn('BUFFER_API_KEY', step)
        self.assertNotIn('CLOUDINARY_API_SECRET', step)

    def test_video_url_is_removed_but_caption_keeps_official_link(self):
        data = self.plan()
        data['bodies'][4] = ('Sekarang saatnya untuk memulai. Lihat info di link profil '
                             'lynk.id/dirgakhaa untuk memulai perubahan yang sederhana dan realistis.')
        data['cta'] = 'Lihat di link profil lynk.id/dirgakhaa'
        result = m.validate_plan(data)
        self.assertNotIn('lynk.id', str(result['bodies']) + result['cta'])
        self.assertIn('link bio', result['bodies'][4])
        self.assertIn('link bio', result['cta'])
        self.assertTrue(all('lynk.id/dirgakhaa' in v for v in result['captions'].values()))

    def test_link_normalization_is_idempotent(self):
        s = 'Lihat info di link profil https://lynk.id/dirgakhaa untuk belajar.'
        once = m.normalize_video_copy(s)
        self.assertEqual(once, m.normalize_video_copy(once))
        self.assertNotIn('lynk.id', once)
        self.assertIn('link bio', once)

    def test_rendered_footer_and_spoken_text_do_not_expose_url(self):
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / 'Keisha_Video_Cloud_Starter_v1' / 'render_studio.py'
        render = path.read_text(encoding='utf-8')
        self.assertIn("'Info produk: cek link bio   •   Tautan afiliasi'", render)
        self.assertIn('safe_spoken_copy(title)', render)
        self.assertIn('safe_spoken_copy(body)', render)
        self.assertIn('safe_spoken_copy(cta)', render)
        self.assertNotIn("'lynk.id/dirgakhaa   •   Tautan afiliasi'", render)

    def test_old_artifact_is_normalized_by_render_workflow(self):
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'keisha_autopilot.yml'
        workflow = path.read_text(encoding='utf-8')
        self.assertIn('normalize_saved_plan(json.loads(', workflow)
        self.assertIn('path.write_text(json.dumps(plan, ensure_ascii=False, indent=2)', workflow)

    def test_preflight_requires_cloudinary_config_before_buffer_calls(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'BUFFER_API_KEY':'test','CLOUDINARY_CLOUD_NAME':'',
                'CLOUDINARY_API_KEY':'','CLOUDINARY_API_SECRET':''}):
            with self.assertRaisesRegex(RuntimeError, 'CLOUDINARY'):
                m.preflight_connections()

    def test_preflight_calls_read_only_channel_discovery(self):
        from unittest.mock import patch
        env = {'BUFFER_API_KEY':'test','CLOUDINARY_CLOUD_NAME':'test',
               'CLOUDINARY_API_KEY':'test','CLOUDINARY_API_SECRET':'test',
               'TELEGRAM_KEISHA_TOKEN':'test','TELEGRAM_CHAT_ID':'-1234'}
        with patch.dict('os.environ', env):
            with patch('Keisha_Video_Cloud_Starter_v1.social_drafts.get_channels',
                       return_value={'tiktok':'a','facebook':'b','youtube':'c'}) as channels:
                out=m.preflight_connections()
        self.assertEqual(out['buffer_channels'], ['facebook','tiktok','youtube'])
        self.assertTrue(out['ready_to_test_drafts'])
        self.assertTrue(out['telegram_reporting_config_present'])
        channels.assert_called_once_with('test')

    def test_workflow_preflight_does_not_generate_or_schedule(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] /
                '.github' / 'workflows' / 'keisha_autopilot.yml').read_text(encoding='utf-8')
        self.assertIn('          - preflight', text)
        self.assertIn("if: ${{ env.RUN_MODE == 'preflight' || env.RUN_MODE == 'drafts' || env.RUN_MODE == 'go_live' || env.RUN_MODE == 'schedule' || env.RUN_MODE == 'publish_now' || env.RUN_MODE == 'recover_tiktok' || env.RUN_MODE == 'ceo_live_test' }}", text)
        self.assertIn("if: ${{ env.RUN_MODE == 'schedule' || env.RUN_MODE == 'go_live' }}", text)
        self.assertIn("if: ${{ env.RUN_MODE == 'plan' || env.RUN_MODE == 'schedule' || env.RUN_MODE == 'publish_now' || env.RUN_MODE == 'go_live' || ((env.RUN_MODE == 'render' || env.RUN_MODE == 'drafts') && inputs.source_plan_run_id == '') || env.RUN_MODE == 'ceo_live_test' }}", text)


    def test_existing_daily_media_never_creates_duplicate_buffer_posts(self):
        import json
        import sys
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        plan = self.plan()
        plan['date'] = '2026-11-20'
        meta = {key:plan[key] for key in ('headings','bodies','cta')}
        with TemporaryDirectory() as directory:
            output = Path(directory) / 'schedule_result.json'
            with patch.dict(sys.modules, {'social_drafts': social}), \
                 patch.object(social, 'validate_metadata', return_value=meta), \
                 patch.object(social, 'validate_video', return_value={'seconds': 34}), \
                 patch.object(social, 'get_channels', return_value={'tiktok':'a','facebook':'b','youtube':'c'}), \
                 patch.object(social, 'find_matching_posts', return_value=[]), \
                 patch.object(social, 'save_scheduled_post') as scheduled, \
                 patch.object(m, 'upload_daily_once', side_effect=RuntimeError('KUNCI ANTI-SPAM: daily media exists')), \
                 patch.object(m, 'due_at', return_value=datetime(2026,11,20,12,tzinfo=timezone.utc)), \
                 patch.dict('os.environ', {'BUFFER_API_KEY':'test'}):
                receipt=m.schedule_all(plan,Path(directory)/'video.mp4',Path(directory)/'meta.json',24,output)
            self.assertEqual(receipt['date'],plan['date'])
            self.assertEqual(receipt['status'],'manual_review')
            self.assertEqual(receipt['posts'],{})
            self.assertTrue(receipt['errors'])
            self.assertEqual(json.loads(output.read_text())['status'],'manual_review')
            scheduled.assert_not_called()

    def test_workflow_has_same_day_receipt_guard_and_separate_preflight_receipt(self):
        from pathlib import Path
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/keisha_autopilot.yml').read_text()
        self.assertIn('keisha-autopilot-receipts/',workflow)
        self.assertIn('TZ=Asia/Jakarta date +%F',workflow)
        self.assertIn('preflight --result autopilot_preflight.json',workflow)
        self.assertIn("result.get('date') != plan.get('date')",workflow)

    def test_buffer_draft_requires_explicit_draft_confirmation(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as s
        with patch.object(s, 'graphql', return_value={'createPost':{
                'post': {'id': 'draft-123', 'status': 'draft'}}}) as call:
            pid = s.save_draft('token', 'channel', 'https://res.cloudinary.com/video/upload/x.mp4',
                               'Cek link bio. Tautan afiliasi.')
        self.assertEqual(pid, 'draft-123')
        query = call.call_args.args[1]
        self.assertIn('saveToDraft: true', query)
        self.assertIn('post { id status }', query)
        self.assertNotIn('customScheduled', query)
        with patch.object(s, 'graphql', return_value={'createPost':{
                'post': {'id': 'post-1', 'status': 'scheduled'}}}):
            with self.assertRaisesRegex(RuntimeError, 'tidak mengonfirmasi status draft'):
                s.save_draft('token', 'channel', 'https://res.cloudinary.com/video/upload/x.mp4',
                             'Cek link bio.')

    def test_drafts_all_uses_platform_captions_and_daily_id(self):
        from unittest.mock import patch
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as s
        plan = self.plan()
        plan['date'] = '2026-11-20'
        normalized = m.normalize_saved_plan(plan)
        meta = {'headings': normalized['headings'], 'bodies': normalized['bodies'],
                'cta': normalized['cta']}
        with TemporaryDirectory() as d:
            resultpath = Path(d) / 'result.json'
            with patch.object(s, 'validate_metadata', return_value=meta), \
                 patch.object(s, 'validate_video', return_value={'seconds':33}), \
                 patch.object(s, 'get_channels', return_value={
                    'tiktok':'a','facebook':'b','youtube':'c'}), \
                 patch.object(s, 'upload', return_value='https://res.cloudinary.com/demo/video/upload/x.mp4') as up, \
                 patch.object(s, 'save_draft', side_effect=['x','y','z']) as drafts, \
                 patch.dict('os.environ', {'BUFFER_API_KEY':'test'}):
                result = m.drafts_all(normalized, Path(d)/'video.mp4', Path(d)/'meta.json', resultpath)
                self.assertEqual(result['status'],'drafts_created')
                self.assertEqual(len(result['drafts']),3)
                self.assertFalse(result['scheduled'])
                self.assertFalse(result['published'])
                self.assertTrue(resultpath.exists())
                up.assert_called_once()
                self.assertEqual(up.call_args.args[1], 20261120)
                captions = [c.args[3] for c in drafts.call_args_list]
                self.assertEqual(captions, [normalized['captions'][p]
                    for p in ('tiktok','facebook','youtube')])

    def test_workflow_drafts_mode_is_separate_from_autopublish(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] /
                '.github' / 'workflows' / 'keisha_autopilot.yml').read_text(encoding='utf-8')
        self.assertIn('          - drafts', text)
        self.assertIn("if: ${{ env.RUN_MODE == 'drafts' }}", text)
        self.assertIn('python autopilot/office_daily.py drafts', text)
        pub = text.index('      - name: Pastikan video valid lalu jadwalkan SATU ke tiap channel')
        end = text.index('      - name: Laporkan kegagalan satu kali tanpa retry posting', pub)
        self.assertIn("if: ${{ env.RUN_MODE == 'schedule' || env.RUN_MODE == 'go_live' }}", text[pub:end])
        self.assertNotIn("env.RUN_MODE == 'drafts'", text[pub:end])


    def test_facebook_reel_and_youtube_required_metadata(self):
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        self.assertIn('metadata: {facebook: {type: reel}}',
                      social.draft_metadata('facebook'))
        yt = social.draft_metadata('youtube', 'Judul Keisha yang Edukatif')
        self.assertIn('categoryId: "27"', yt)
        self.assertIn('title: "Judul Keisha yang Edukatif"', yt)
        self.assertIn('isAiGenerated: true', yt)
        self.assertEqual(social.draft_metadata('tiktok'), '')
        with self.assertRaisesRegex(ValueError, 'Judul YouTube'):
            social.draft_metadata('youtube', '')

    def test_buffer_query_includes_platform_metadata_and_save_to_draft(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        for platform in ('facebook', 'youtube'):
            with self.subTest(platform=platform):
                with patch.object(social, 'graphql', return_value={
                    'createPost': {'post': {'id': 'p1', 'status':'draft'}}}) as query:
                    social.save_draft('token','channel','https://res.cloudinary.com/x/video/upload/a.mp4',
                                      'Tautan afiliasi', platform=platform, title='Video edukasi')
                sent = query.call_args.args[1]
                self.assertIn('saveToDraft: true', sent)
                self.assertIn('metadata: {' + platform + ':', sent)
                self.assertNotIn('customScheduled', sent)
                self.assertNotIn('publishPostNow', sent)

    def test_draft_audit_is_read_only_and_skips_existing_tiktok(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        plan = self.plan()
        plan['date'] = '2026-11-20'
        plan = m.normalize_saved_plan(plan)
        previous = {'date':'2026-11-20','mode':'drafts',
           'cloudinary_url':'https://res.cloudinary.com/x/video/upload/v1/keisha-drafts/run-20261120.mp4',
           'drafts':{'tiktok':{'id':'already-saved'}}}
        with patch.object(social,'get_channels', return_value={
                    'tiktok':'t','facebook':'f','youtube':'y'}), \
             patch.object(social,'find_matching_posts', side_effect=[[], []]) as scan, \
             patch.object(social,'save_draft') as send, \
             patch.dict('os.environ', {'BUFFER_API_KEY':'token'}):
            output=m.reconcile_failed_drafts(plan, previous)
        self.assertEqual(output['tiktok']['id'],'already-saved')
        self.assertEqual(output['channels']['facebook']['action'],'missing')
        self.assertEqual(scan.call_count, 2)
        send.assert_not_called()

    def test_recovery_skips_existing_draft_and_only_creates_missing_youtube(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        plan = self.plan()
        plan['date']='2026-11-20'
        plan=m.normalize_saved_plan(plan)
        previous={'date':'2026-11-20','mode':'drafts',
            'cloudinary_url':'https://res.cloudinary.com/x/video/upload/v1/keisha-drafts/run-20261120.mp4',
            'drafts':{'tiktok':{'id':'original-tiktok'}}}
        with patch.object(social,'get_channels', return_value={
                    'tiktok':'t','facebook':'f','youtube':'y'}), \
             patch.object(social,'find_matching_posts',side_effect=[
                [{'id':'existing-facebook','status':'draft'}],[]]), \
             patch.object(social,'save_draft',return_value='new-youtube') as send, \
             patch.dict('os.environ', {'BUFFER_API_KEY':'token'}):
            output=m.reconcile_failed_drafts(plan,previous,create_missing=True)
        self.assertEqual(send.call_count,1)
        self.assertEqual(send.call_args.kwargs['platform'],'youtube')
        self.assertEqual(output['channels']['facebook']['action'],'existing')
        self.assertEqual(output['channels']['youtube']['id'],'new-youtube')
        self.assertEqual(output['tiktok']['action'],'untouched')

    def test_buffer_scan_paginates_and_detects_existing_media(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        url = 'https://res.cloudinary.com/x/video/upload/v1/keisha-drafts/run-20261120.mp4'
        responses = [
            {'account':{'organizations':[{'id':'org'}]}},
            {'posts':{'edges':[], 'pageInfo':{'hasNextPage':True,'endCursor':'next'}}},
            {'posts':{'edges':[{'node':{'id':'found','text':'different','status':'draft',
                  'channelId':'channel','assets':[{'source':url}]}}],
                      'pageInfo':{'hasNextPage':False,'endCursor':'last'}}},
        ]
        with patch.object(social,'graphql',side_effect=responses) as req:
            found=social.find_matching_posts('token','channel','caption',url)
        self.assertEqual([x['id'] for x in found],['found'])
        self.assertIn('after: "next"',req.call_args.args[1])

    def test_recovery_stops_if_buffer_scan_fails_before_write(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        plan = self.plan()
        plan['date']='2026-11-20'
        plan=m.normalize_saved_plan(plan)
        previous={'date':'2026-11-20','mode':'drafts',
            'cloudinary_url':'https://res.cloudinary.com/x/video/upload/v1/keisha-drafts/run-20261120.mp4',
            'drafts':{'tiktok':{'id':'original-tiktok'}}}
        with patch.object(social,'get_channels',return_value={
                    'tiktok':'t','facebook':'f','youtube':'y'}), \
             patch.object(social,'find_matching_posts',side_effect=RuntimeError('scope tidak cukup')), \
             patch.object(social,'save_draft') as send, \
             patch.dict('os.environ', {'BUFFER_API_KEY':'token'}):
            with self.assertRaisesRegex(RuntimeError,'scope tidak cukup'):
                m.reconcile_failed_drafts(plan,previous,create_missing=True)
        send.assert_not_called()



    def test_known_tiktok_post_lookup_is_read_only(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        with patch.object(social, 'graphql', return_value={
                'post': {'id':'known12345','status':'draft','channelId':'tiktok',
                         'createdAt':'2026-11-20T01:02:00Z','assets':[{'source':'changed'}]}}) as query:
            result = social.read_post_by_id('token', 'known12345')
        self.assertEqual(result['status'], 'draft')
        self.assertEqual(result['channel_id'], 'tiktok')
        self.assertIn('post(input: {id: "known12345"})', query.call_args.args[1])
        self.assertNotIn('mutation', query.call_args.args[1])

    def test_inventory_reads_only_drafts_for_selected_day(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        responses = [
            {'account': {'organizations': [{'id': 'org'}]}},
            {'posts': {'edges': [
                {'node': {'id':'today', 'status':'draft', 'channelId':'channel',
                          'createdAt':'2026-11-20T01:20:00Z'}},
                {'node': {'id':'old', 'status':'draft', 'channelId':'channel',
                          'createdAt':'2026-11-19T01:20:00Z'}}],
                'pageInfo': {'hasNextPage': False}}}
        ]
        with patch.object(social, 'graphql', side_effect=responses) as query:
            result = social.summarize_channel_drafts('token', 'channel', '2026-11-20')
        self.assertEqual(result['scanned'], 2)
        self.assertEqual([p['id'] for p in result['created_on_audit_date']], ['today'])
        self.assertIn('status: [draft]', query.call_args.args[1])
        self.assertNotIn('mutation', query.call_args.args[1])

    def test_audit_checks_known_tiktok_id_without_creating_drafts(self):
        import sys, types
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        cloud = types.ModuleType('cloudinary')
        api = types.ModuleType('cloudinary.api')
        cloud.config = lambda **kw: None
        api.resource = lambda *args, **kw: {
            'public_id':'keisha-drafts/run-20261120',
            'secure_url':'https://res.cloudinary.com/demo/video/upload/v1/keisha-drafts/run-20261120.mp4'}
        cloud.api = api
        with patch.dict(sys.modules, {'cloudinary': cloud, 'cloudinary.api': api}), \
             patch.object(social, 'get_channels', return_value={
                 'tiktok':'t','facebook':'f','youtube':'y'}), \
             patch.object(social, 'find_matching_posts', return_value=[]), \
             patch.object(social, 'summarize_channel_drafts', return_value={
                 'scanned':2, 'created_on_audit_date':[]}), \
             patch.object(social, 'read_post_by_id', return_value={
                 'id':'tik12345','status':'draft','channel_id':'t','asset_count':1}), \
             patch.object(social, 'save_draft') as save, \
             patch.object(social, 'upload') as upload, \
             patch.dict('os.environ', {'BUFFER_API_KEY':'token',
                  'CLOUDINARY_CLOUD_NAME':'demo','CLOUDINARY_API_KEY':'a',
                  'CLOUDINARY_API_SECRET':'b'}):
            result = m.audit_live_drafts('2026-11-20', 'tik12345')
        self.assertEqual(result['channels']['tiktok']['status'], 'confirmed_by_post_id')
        self.assertEqual(result['known_tiktok_draft']['status'], 'draft')
        save.assert_not_called()
        upload.assert_not_called()

    def test_workflow_known_id_only_for_audit(self):
        from pathlib import Path
        yml = (Path(__file__).resolve().parents[1] / '.github' /
               'workflows' / 'keisha_autopilot.yml').read_text(encoding='utf-8')
        self.assertIn('known_tiktok_draft_id:', yml)
        self.assertIn('--known-tiktok-draft-id "', yml)
        self.assertIn('audit_drafts', yml)


    def test_stale_buffer_id_becomes_nonfatal_audit_result(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        with patch.object(social, 'graphql', side_effect=RuntimeError(
                 'Buffer menolak query: Post not found for id: badpost123')):
            post = social.read_post_by_id('token', 'badpost123')
        self.assertEqual(post['status'], 'not_found')
        self.assertFalse(post['reachable'])

    def test_scheduled_post_has_platform_metadata_and_expected_status(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        for platform in ('tiktok', 'facebook', 'youtube'):
            with self.subTest(platform=platform):
                with patch.object(social, 'graphql', return_value={
                        'createPost': {'post': {'id':'p123', 'status':'scheduled',
                                               'dueAt':'2026-11-21T12:00:00.000Z'}}}) as g:
                    post = social.save_scheduled_post('token','channel',
                        'https://res.cloudinary.com/demo/video/upload/x.mp4',
                        'Cek link bio, tautan afiliasi.', platform=platform,
                        title='Video edukasi', due_at='2026-11-21T12:00:00.000Z')
                self.assertEqual(post['status'],'scheduled')
                query = g.call_args.args[1]
                self.assertIn('mode: customScheduled',query)
                self.assertNotIn('saveToDraft: true',query)
                if platform!='tiktok':
                    self.assertIn('metadata: {' + platform + ':', query)

    def test_scheduled_post_does_not_accept_draft_status(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        with patch.object(social, 'graphql', return_value={
                'createPost': {'post': {'id':'p123', 'status':'draft'}}}):
            with self.assertRaisesRegex(RuntimeError, 'tidak mengonfirmasi jadwal'):
                social.save_scheduled_post('token','channel',
                    'https://res.cloudinary.com/demo/video/upload/x.mp4',
                    'Caption', platform='facebook', title='Video edukasi',
                    due_at='2026-11-21T12:00:00.000Z')

    def test_live_audit_with_missing_known_id_still_finishes_without_writes(self):
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        import sys, types
        cloud=types.ModuleType('cloudinary')
        api=types.ModuleType('cloudinary.api')
        cloud.config=lambda **kwargs: None
        api.resource=lambda *a, **kw: {
          'public_id':'keisha-drafts/run-20261120',
          'secure_url':'https://res.cloudinary.com/demo/video/upload/v1/keisha-drafts/run-20261120.mp4'}
        cloud.api=api
        with patch.dict(sys.modules,{'cloudinary':cloud,'cloudinary.api':api}), \
             patch.object(social,'get_channels',return_value={
                'tiktok':'t','facebook':'f','youtube':'y'}), \
             patch.object(social,'find_matching_posts',return_value=[]), \
             patch.object(social,'summarize_channel_drafts',return_value={
                'scanned':0,'created_on_audit_date':[]}), \
             patch.object(social,'read_post_by_id',return_value={
                'id':'badpost123','status':'not_found','reachable':False,'channel_id':None}), \
             patch.object(social,'save_draft') as save, \
             patch.object(social,'upload') as upload, \
             patch.dict('os.environ', {'BUFFER_API_KEY':'token',
                'CLOUDINARY_CLOUD_NAME':'demo','CLOUDINARY_API_KEY':'key',
                'CLOUDINARY_API_SECRET':'secret'}):
            result=m.audit_live_drafts('2026-11-20','badpost123')
        self.assertEqual(result['status'],'complete_read_only')
        self.assertEqual(result['channels']['tiktok']['known_id_status'],'not_found')
        save.assert_not_called()
        upload.assert_not_called()


    def test_go_live_receipt_requires_three_confirmed_posts(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import json
        from unittest.mock import patch
        with TemporaryDirectory() as d:
            result=Path(d)/'result.json'
            payload={'date':'2026-11-20','status':'scheduled','errors':[],
                'posts':{p:{'id':p+'-post-id','status':'scheduled'}
                         for p in ('tiktok','facebook','youtube')},
                'due_at_utc':'2026-11-20T12:00:00+00:00'}
            result.write_text(json.dumps(payload))
            with patch.object(m,'datetime') as clock:
                clock.now.return_value.date.return_value=date(2026,11,20)
                receipt=m.validated_schedule_receipt(result)
            self.assertFalse(receipt['published'])
            self.assertEqual(set(receipt['posts']),{'tiktok','facebook','youtube'})
            del payload['posts']['facebook']
            result.write_text(json.dumps(payload))
            with patch.object(m,'datetime') as clock:
                clock.now.return_value.date.return_value=date(2026,11,20)
                with self.assertRaisesRegex(RuntimeError,'3/3'):
                    m.validated_schedule_receipt(result)

    def test_go_live_activation_only_after_verified_receipt(self):
        from unittest.mock import patch
        from pathlib import Path
        verified={'date':'2026-11-20','posts':{},'status':'scheduled'}
        with patch.object(m,'validated_schedule_receipt',return_value=verified), \
             patch.object(m,'_github_put_new_file') as write, \
             patch.object(m,'telegram_report') as report:
            m.activate_daily_autopilot(Path('unused.json'))
        write.assert_called_once()
        self.assertEqual(write.call_args.args[0],m.AUTOPILOT_FLAG)
        self.assertTrue(write.call_args.args[1]['enabled'])
        report.assert_called_once()
        with patch.object(m,'validated_schedule_receipt',
                 side_effect=RuntimeError('not complete')), \
             patch.object(m,'_github_put_new_file') as write:
            with self.assertRaises(RuntimeError):
                m.activate_daily_autopilot(Path('unused.json'))
        write.assert_not_called()

    def test_headquarters_reporting_preflight_checks_chat_and_token(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'RUN_MODE':'go_live',
             'TELEGRAM_KEISHA_TOKEN':'bot-test',
             'TELEGRAM_CHAT_ID':'-old-group'}):
            with self.assertRaisesRegex(RuntimeError, 'AI AFFILIATE OFFICE'):
                m.check_reporting_ready()
        with patch.dict('os.environ', {'RUN_MODE':'go_live',
             'TELEGRAM_KEISHA_TOKEN':'bot-test',
             'TELEGRAM_CHAT_ID':m.HEADQUARTERS_CHAT_ID}):
            with patch('pathlib.Path.is_file',return_value=False):
                m.check_reporting_ready()

    def test_one_click_workflow_is_gated_and_has_report_receipt(self):
        from pathlib import Path
        w=(Path(__file__).resolve().parents[1]/'.github'/
           'workflows'/'keisha_autopilot.yml').read_text(encoding='utf-8')
        self.assertIn('          - go_live',w)
        self.assertIn('    needs: guard',w)
        self.assertIn("needs.guard.outputs.allowed == 'true'",w)
        self.assertIn('keisha-autopilot.enabled.json',w)
        self.assertIn('python autopilot/office_daily.py check_reporting',w)
        self.assertIn('python autopilot/office_daily.py record',w)
        self.assertIn('python autopilot/office_daily.py activate',w)
        self.assertIn('RUN_MODE == ',w)

    def test_daily_verification_does_not_publish(self):
        from pathlib import Path
        v=(Path(__file__).resolve().parents[1]/'.github'/
           'workflows'/'keisha_verify.yml').read_text(encoding='utf-8')
        self.assertIn('python autopilot/office_daily.py verify',v)
        self.assertNotIn(' office_daily.py schedule',v)
        self.assertNotIn(' office_daily.py drafts',v)
        self.assertIn('keisha-autopilot.enabled.json',v)
        self.assertIn('Keisha-Publication-Verification',v)


    def test_recovery_requires_matching_partial_source_without_writes(self):
        import tempfile, json
        from pathlib import Path
        from unittest.mock import patch
        from Keisha_Video_Cloud_Starter_v1 import social_drafts as social
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            day=m.datetime.now(m.WIB).date().isoformat()
            p=self.plan();p['date']=day
            (root/'plan.json').write_text(json.dumps(p))
            (root/'prior.json').write_text(json.dumps({
                'date':day,'status':'manual_review','posts':{'facebook':{'id':'abc'}}}))
            with patch.object(social,'save_scheduled_post') as send:
                with self.assertRaisesRegex(RuntimeError,'parsial 2/3'):
                    m.recover_tiktok_run21(root/'plan.json',root/'prior.json',
                        root/'video.mp4',root/'meta.json',root/'out.json')
            send.assert_not_called()

    def test_recovery_source_does_not_call_schedule_all(self):
        import inspect
        source=inspect.getsource(m.recover_tiktok_run21)
        self.assertIn("channels['tiktok']", source)
        self.assertIn("fps=30,format=yuv420p", source)
        self.assertIn("sd.find_matching_posts", source)
        self.assertNotIn("schedule_all(", source)
        self.assertNotIn("for service in ('tiktok','facebook','youtube'):", source)

    def test_recovery_workflow_uses_old_artifact_without_rendering(self):
        from pathlib import Path
        yaml=(Path(__file__).resolve().parents[1]/'.github'/
              'workflows'/'keisha_autopilot.yml').read_text('utf-8')
        self.assertIn('          - recover_tiktok',yaml)
        self.assertIn('python autopilot/office_daily.py prepare_recovery',yaml)
        self.assertIn('autopilot/recovery/2026-11-20-run21.json',yaml)
        self.assertNotIn('run-id: ${{ inputs.failed_schedule_run_id }}',yaml)
        self.assertIn('python autopilot/office_daily.py recover_tiktok',yaml)

    def test_manifest_restores_original_without_github_artifact(self):
        import hashlib, io, json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);video=b'dummy immutable source MP4'
            source='https://res.cloudinary.com/test/video/upload/v1/keisha-autopilot/original.mp4'
            plan=self.plan();plan['date']='2026-11-20'
            metadata={'headings':plan['headings'],'bodies':plan['bodies'],'cta':plan['cta']}
            manifest={'video_url':source,'source_sha256':hashlib.sha256(video).hexdigest(),
                      'source_bytes':len(video),'plan':plan,
                      'previous_result':{'date':plan['date'],'cloudinary_url':source},
                      'metadata':metadata}
            path=home/'source.json';path.write_text(json.dumps(manifest))
            response=io.BytesIO(video)
            response.status=200
            with patch.object(m.urllib.request,'urlopen',return_value=response):
                answer=m.prepare_recovery_from_manifest(path,home/'run21')
            self.assertEqual(answer['sha256'],manifest['source_sha256'])
            self.assertEqual((home/'run21'/'Keisha_Video_Cloud_Starter_v1'/
                 'hasil'/'keisha-rcd-video.mp4').read_bytes(),video)
            self.assertEqual(json.loads((home/'run21'/'autopilot_plan.json').read_text())['date'],
                 '2026-11-20')

    def test_manifest_rejects_mismatched_video_before_scheduling(self):
        import io, hashlib, json, tempfile
        from pathlib import Path
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            plan=self.plan();plan['date']='2026-11-20'
            url='https://res.cloudinary.com/test/video/upload/v1/demo.mp4'
            payload={'video_url':url,'source_sha256':hashlib.sha256(b'original').hexdigest(),
                'source_bytes':len(b'original'),'plan':plan,
                'previous_result':{'date':plan['date'],'cloudinary_url':url},
                'metadata':{'headings':plan['headings'],
                            'bodies':plan['bodies'],'cta':plan['cta']}}
            path=home/'source.json';path.write_text(json.dumps(payload))
            response=io.BytesIO(b'not the original');response.status=200
            with patch.object(m.urllib.request,'urlopen',return_value=response):
                with self.assertRaisesRegex(RuntimeError,'tidak identik'):
                    m.prepare_recovery_from_manifest(path,home/'run21')
            self.assertFalse((home/'run21'/'Keisha_Video_Cloud_Starter_v1'/
                 'hasil'/'keisha-rcd-video.mp4').exists())

    def test_cannot_invent_ai(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'CLOUDFLARE_AI_API_TOKEN':'','CLOUDFLARE_ACCOUNT_ID':''}):
            with self.assertRaises(RuntimeError): m.ai_request([{'role':'user','content':'x'}])