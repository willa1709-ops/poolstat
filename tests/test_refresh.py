import copy
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts import update_data
from scripts.check_links import validate_refresh


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / 'pools.json'
        self.original = Path('data/pools.json').read_bytes()
        self.output.write_bytes(self.original)
        self.config = json.loads(Path('config/pools.json').read_text())
        self.mocks = self.enterContext(ExitStack())
        self.mocks.enter_context(patch.object(update_data, 'fetch_text', return_value='Official pool programme'))
        self.feed = self.mocks.enter_context(patch.object(update_data, 'parse_lane_feed', side_effect=self.lane_feed))
        self.mocks.enter_context(patch.object(update_data, 'parse_mb_official_lane_feed', side_effect=self.lane_feed))

    @staticmethod
    def lane_feed(url, count, fetched_at):
        return {
            'source': 'test', 'source_url': url, 'fetched_at': fetched_at,
            'days': {fetched_at[:10]: [{'from': '06:00', 'to': '24:00', 'free': count, 'known_lanes': count}]},
        }

    def generate(self):
        update_data.main(self.output)
        return json.loads(self.output.read_text())

    def assert_original_preserved(self):
        self.assertEqual(self.output.read_bytes(), self.original)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_complete_refresh_and_calendar_without_lane_feed(self):
        payload = self.generate()
        validate_refresh(self.config, payload)
        active = [p for p in payload['pools'] if p.get('status') != 'reconstruction']
        self.assertEqual(len(active), 6)
        self.assertTrue(all(p['source_fetch_ok'] for p in active))
        self.assertIsNone(active[0]['lane_availability'])
        self.assertEqual(sum(bool(p['lane_availability']) for p in active), 5)

    def test_partial_official_fetch_preserves_previous_snapshot(self):
        def fetch(url):
            return None if 'bazenhloubetin.eu' in url else 'Official programme'
        with patch.object(update_data, 'fetch_text', side_effect=fetch):
            with self.assertRaisesRegex(ValueError, 'praha-hloubetin: official source'):
                self.generate()
        self.assert_original_preserved()

    def test_missing_required_lane_feed_preserves_previous_snapshot(self):
        self.feed.side_effect = None
        self.feed.return_value = None
        with self.assertRaisesRegex(ValueError, 'lane feed is unavailable'):
            self.generate()
        self.assert_original_preserved()

    def test_invalid_lane_count_preserves_previous_snapshot(self):
        def invalid_feed(url, count, fetched_at):
            result = self.lane_feed(url, count, fetched_at)
            result['days'][fetched_at[:10]][0]['free'] = count + 1
            return result
        self.feed.side_effect = invalid_feed
        with self.assertRaisesRegex(ValueError, 'invalid lane count'):
            self.generate()
        self.assert_original_preserved()

    def test_atomic_replace_failure_preserves_previous_snapshot(self):
        with patch.object(update_data.os, 'replace', side_effect=OSError('Disk error')):
            with self.assertRaisesRegex(OSError, 'Disk error'):
                self.generate()
        self.assert_original_preserved()

    def test_invalid_config_is_rejected_before_fetching(self):
        bad_config = Path(self.directory.name) / 'bad-config.json'
        config = copy.deepcopy(self.config)
        config[0]['source_url'] = 'http://invalid.example'
        bad_config.write_text(json.dumps(config))
        with patch.object(update_data, 'CONFIG', bad_config), patch.object(update_data, 'fetch_text') as fetch:
            with self.assertRaises(ValueError):
                self.generate()
            fetch.assert_not_called()
        self.assertEqual(self.output.read_bytes(), self.original)

    def test_lane_dates_intervals_and_provenance(self):
        payload = self.generate()
        original = payload['pools'][1]['lane_availability']
        mutations = [
            {'days': {}},
            {'source_url': 'https://other.example/'},
            {'days': {payload['pools'][1]['date']: [{'from': '22:00', 'to': '06:00', 'free': 0, 'known_lanes': 8}]}},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                payload['pools'][1]['lane_availability'] = {**original, **mutation}
                with self.assertRaises(ValueError):
                    validate_refresh(self.config, payload)

    def test_stale_snapshot_is_rejected(self):
        payload = self.generate()
        payload['generated_at'] = '2020-01-01T06:00:00+01:00'
        with self.assertRaisesRegex(ValueError, 'not fresh'):
            validate_refresh(self.config, payload)
