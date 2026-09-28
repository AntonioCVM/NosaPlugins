# -*- coding: utf-8 -*-
"""Revit-free tests for nosa_utils.usage key canonicalisation and migration."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from nosa_utils import usage  # noqa: E402

_EXT = os.path.dirname(_LIB)


class MigrationTests(unittest.TestCase):

    def test_folds_legacy_keys_into_canonical(self):
        data = {'export_sheets': 84, 'exportsheets': 20, 'sheet_export_hub': 67,
                'qrcode': 33, 'qr_code': 25, 'pilemaster': 40, 'pile_master': 25,
                'smartjoin_pro': 13, 'elementjoin': 14,
                'material_manager': 23, 'materialmanager': 26, 'rebar_automate': 72}
        out, changed = usage.migrate(copy.deepcopy(data))
        self.assertTrue(changed)
        self.assertEqual(out['sheet_export_hub'], 171)
        self.assertEqual(out['qr_code'], 58)
        self.assertEqual(out['pile_master'], 65)
        self.assertEqual(out['element_join'], 27)
        self.assertEqual(out['material_manager'], 49)
        self.assertEqual(out['rebar_automate'], 72)
        for old in ('export_sheets', 'exportsheets', 'qrcode', 'pilemaster',
                    'smartjoin_pro', 'elementjoin', 'materialmanager'):
            self.assertNotIn(old, out)
            self.assertEqual(out['_legacy_keys'][old], data[old])

    def test_total_is_preserved(self):
        data = {'exportsheets': 20, 'qrcode': 33, 'unknown_tool': 4, 'nosa': 15}
        out, _ = usage.migrate(copy.deepcopy(data))
        self.assertEqual(sum(usage._counts(out).values()), sum(data.values()))
        self.assertEqual(out['unknown_tool'], 4)

    def test_idempotent(self):
        once, _ = usage.migrate({'qrcode': 3, 'qr_code': 2})
        snapshot = copy.deepcopy(once)
        twice, changed = usage.migrate(once)
        self.assertFalse(changed)
        self.assertEqual(twice, snapshot)

    def test_legacy_key_reappearing_is_folded_again(self):
        data, _ = usage.migrate({'qrcode': 3})
        data['qrcode'] = 1  # written by an older build in another Revit
        data, changed = usage.migrate(data)
        self.assertTrue(changed)
        self.assertEqual(data['qr_code'], 4)
        self.assertEqual(data['_legacy_keys']['qrcode'], 4)

    def test_non_dict_input(self):
        self.assertEqual(usage.migrate([])[0], {})

    def test_alias_table_has_no_chains(self):
        for old, new in usage._KEY_ALIASES.items():
            self.assertNotIn(new, usage._KEY_ALIASES, '%s -> %s chains' % (old, new))
            self.assertNotEqual(old, new)


class KeyDerivationTests(unittest.TestCase):

    def test_snake_case(self):
        self.assertEqual(usage.to_snake_case('SheetExportHub'), 'sheet_export_hub')
        self.assertEqual(usage.to_snake_case('QRCode'), 'qr_code')
        self.assertEqual(usage.to_snake_case('IFCStructuralExportQA'),
                         'ifc_structural_export_qa')
        self.assertEqual(usage.to_snake_case('NOSA'), 'nosa')

    def test_bundle_key_from_path(self):
        p = os.path.join('x', 'NOSA.tab', 'Documentation.panel', 'Sheets.pulldown',
                         'SheetExportHub.pushbutton', 'lib', 'ui.py')
        self.assertEqual(usage.bundle_key_from_path(p), 'sheet_export_hub')
        p = os.path.join('x', 'Issue.pulldown', 'ExportSheets.nobutton', 'lib', 'ui.py')
        self.assertEqual(usage.bundle_key_from_path(p), 'sheet_export_hub')
        self.assertIsNone(usage.bundle_key_from_path(os.path.join('x', 'lib', 'a.py')))

    def test_every_active_pushbutton_has_a_non_alias_key(self):
        keys = set()
        for root, dirs, _ in os.walk(os.path.join(_EXT, 'NOSA.tab')):
            for d in dirs:
                if d.endswith('.pushbutton'):
                    key = usage.bundle_key_from_path(os.path.join(root, d, 'script.py'))
                    self.assertNotIn(key, usage._KEY_ALIASES)
                    keys.add(key)
        self.assertIn('sheet_export_hub', keys)
        self.assertIn('qr_code', keys)
        self.assertIn('pile_master', keys)

    def test_record_uses_canonical_key(self):
        tmp = tempfile.mkdtemp()
        orig = usage._CONFIGS_DIR, usage._USAGE_FILE
        try:
            usage._CONFIGS_DIR = tmp
            usage._USAGE_FILE = os.path.join(tmp, '_usage.json')
            with open(usage._USAGE_FILE, 'w') as f:
                json.dump({'pilemaster': 40, 'pile_master': 25}, f)
            usage.record('pilemaster')
            self.assertEqual(usage.get_all(), {'pile_master': 66})
            with open(usage._USAGE_FILE) as f:
                self.assertEqual(json.load(f)['_legacy_keys'], {'pilemaster': 40})
        finally:
            usage._CONFIGS_DIR, usage._USAGE_FILE = orig
            shutil.rmtree(tmp)


if __name__ == '__main__':
    unittest.main()
