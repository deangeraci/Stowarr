import sys
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from movie_approvals import candidates, eligible_completion, provider_matches, read_live_item


class MovieProposalTests(unittest.TestCase):
    def test_removed_item_is_skipped(self):
        client = Mock()
        client.request.return_value.status_code = 404
        self.assertIsNone(read_live_item(client, 'user', 'old-item'))
        client.request.return_value.json.assert_not_called()

    def test_other_api_errors_are_not_skipped(self):
        client = Mock()
        client.request.return_value.status_code = 503
        client.request.return_value.raise_for_status.side_effect = RuntimeError('unavailable')
        with self.assertRaises(RuntimeError):
            read_live_item(client, 'user', 'item')

    movie = dict(id=15, title='Movie', year=2012, tmdbId=123,
                 movieFile=dict(id=99, size=20*1073741824))
    release = dict(title='Movie 1080p BluRay x265 10bit', size=6*1073741824,
                   seeders=40, infoHash='a'*40, indexerId=1,
                   quality={'quality':{'name':'Bluray-1080p'}},
                   rejections=['Existing file meets cutoff: Bluray-2160p'])

    def test_snapshot_pins_real_ids_and_filters(self):
        found = candidates(self.movie, [self.release], {})
        self.assertEqual(found[0][1]['source_file_id'], '99')
        self.assertEqual(found[0][1]['release_id'], 'a'*40)
        self.assertNotIn('downloadUrl', found[0][1])

    def test_rejection_missing_hash_and_bad_formats_fail(self):
        for change in [dict(rejections=['Not enough seeders']), dict(infoHash=''),
                       dict(seeders=0), dict(title='Movie 1080p REMUX x265'),
                       dict(title='Movie 1080p x264'), dict(size=9*1073741824)]:
            with self.subTest(change=change):
                self.assertEqual(candidates(self.movie, [dict(self.release, **change)], {}), [])

    def test_configured_size_and_savings_apply(self):
        self.assertEqual(candidates(self.movie, [self.release], {'approvals':{'maximum_candidate_gib':5}}), [])
        self.assertEqual(candidates(self.movie, [self.release], {'optimization':{'minimum_resolution':2160}}), [])

    def test_grace_is_recomputed_and_uncertain_state_blocks(self):
        now = datetime(2026, 10, 5, tzinfo=timezone.utc)
        row = ('complete','high','2026-09-01T00:00:00+00:00')
        self.assertTrue(eligible_completion(row, True, 30, now))
        self.assertFalse(eligible_completion(row, True, 60, now))
        self.assertFalse(eligible_completion(row, False, 30, now))
        self.assertFalse(eligible_completion(('complete','partial',row[2]), True, 30, now))
        self.assertFalse(eligible_completion(('complete','high','2026-09-01'), True, 30, now))

    def test_provider_identity_is_required(self):
        self.assertTrue(provider_matches({'ProviderIds':{'Tmdb':'123'}}, self.movie))
        self.assertFalse(provider_matches({'Name':'Movie','ProviderIds':{'Tmdb':'456'}}, self.movie))
