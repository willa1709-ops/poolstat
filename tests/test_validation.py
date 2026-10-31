import copy
import json
import unittest
import tempfile
from unittest.mock import patch
from scripts import update_data
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.check_links import validate_config, validate_payload
from scripts.update_data import detect_exception

CONFIG = json.loads(Path('config/pools.json').read_text())

class ValidationTests(unittest.TestCase):
    def test_config(self):
        validate_config(CONFIG)

    def test_bad_config(self):
        for patch in ({'source_url': None}, {'source_url': 'https://bad host/'},
                      {'lane_feed_url': 'http://bad'}, {'check_urls': ['http://bad']},
                      {'updates_url': None, 'updates_label': 'News'}):
            with self.subTest(patch=patch):
                pools = copy.deepcopy(CONFIG)
                pools[0].update(patch)
                with self.assertRaises(ValueError):
                    validate_config(pools)

    def test_payload(self):
        validate_payload(CONFIG, {'pools': CONFIG})
        pools = copy.deepcopy(CONFIG)
        pools[0]['lane_source_url'] = None
        with self.assertRaises(ValueError):
            validate_payload(CONFIG, {'pools': pools})
        with self.assertRaises(ValueError):
            validate_payload(CONFIG, {'pools': CONFIG[:-1]})

    def test_jicin_range(self):
        text = 'V termínu 28. - 30. 10. 2026 bude Aqua centrum otevřeno 10.00 - 21.00 hod. Ranní plavání a aquaerobik v tyto dny není.'
        for day in (28, 29, 30):
            result = detect_exception({}, text, datetime(2026, 10, day, tzinfo=ZoneInfo('Europe/Prague')))
            self.assertEqual(result, {'kind': 'hours', 'intervals': [['10:00', '21:00']]})
        self.assertIsNone(detect_exception({}, text, datetime(2026, 10, 31)))

    def test_failed_fetch_does_not_create_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'pools.json'
            with patch.object(update_data, 'OUT', output), patch.object(update_data, 'fetch_text', return_value=None), patch.object(update_data, 'fetch_html', return_value=None):
                with self.assertRaisesRegex(ValueError, 'official source could not be fetched'):
                    update_data.main()
            self.assertFalse(output.exists())

    def test_ambiguous_notice(self):
        result = detect_exception({}, 'Dne 30. 10. 2026 změna provozu, ověřte telefonicky.', datetime(2026, 10, 30))
        self.assertEqual(result['kind'], 'warning')

    def test_old_closure_does_not_override_hours(self):
        text = 'Dne 30. 10. 2026 otevřeno 10:00–21:00. Dne 3. 10. 2026 uzavřeno.'
        self.assertEqual(detect_exception({}, text, datetime(2026, 10, 30))['kind'], 'hours')

if __name__ == '__main__':
    unittest.main()
