"""Regression tests for Buffer delivery verification (no external calls)."""
import unittest
from unittest.mock import Mock
from autopilot.office_daily import summarize_buffer_publication


class PublicationVerificationTests(unittest.TestCase):
    def setUp(self):
        self.posts = {p: {'id': p + '_buffer_123'} for p in
                      ('tiktok', 'facebook', 'youtube')}

    def test_all_sent_is_buffer_confirmation_not_platform_proof(self):
        def reader(post_id):
            return {'id': post_id, 'status': 'sent'}
        result = summarize_buffer_publication({'posts': self.posts}, reader)
        self.assertTrue(result['buffer_all_sent'])
        self.assertFalse(result['platform_publication_verified'])
        self.assertFalse(result['requires_manual_review'])

    def test_scheduled_or_error_requires_review_without_retry(self):
        statuses = {'tiktok_buffer_123': 'sent',
                    'facebook_buffer_123': 'scheduled',
                    'youtube_buffer_123': 'error'}
        reader = Mock(side_effect=lambda x: {'id': x, 'status': statuses[x]})
        result = summarize_buffer_publication({'posts': self.posts}, reader)
        self.assertFalse(result['buffer_all_sent'])
        self.assertTrue(result['requires_manual_review'])
        self.assertEqual(result['channels']['facebook'], 'scheduled')
        self.assertEqual(reader.call_count, 3)

    def test_missing_id_does_not_query_or_claim_success(self):
        partial = {'posts': {'facebook': self.posts['facebook']}}
        reader = Mock(return_value={'status': 'sent'})
        result = summarize_buffer_publication(partial, reader)
        self.assertEqual(result['channels']['tiktok'], 'missing_receipt_id')
        self.assertEqual(result['channels']['youtube'], 'missing_receipt_id')
        self.assertFalse(result['buffer_all_sent'])
        reader.assert_called_once_with('facebook_buffer_123')

    def test_wrong_id_or_request_error_fails_closed(self):
        def reader(post_id):
            if post_id.startswith('facebook'):
                raise RuntimeError('API not available')
            return {'id': 'wrong_id', 'status': 'sent'}
        result = summarize_buffer_publication({'posts': self.posts}, reader)
        self.assertEqual(result['channels']['facebook'], 'unverified')
        self.assertEqual(result['channels']['tiktok'], 'unverified')
        self.assertFalse(result['buffer_all_sent'])


if __name__ == '__main__':
    unittest.main()
