# -*- coding: utf-8 -*-
"""Checks for the 'done' marks store (no Revit needed)."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    'review_store', os.path.join(_HERE, '..', 'lib', 'review_store.py'))
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)


class ReviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.report = os.path.join(self.tmp, 'UWWTP-AA-00-BM-RP-00002.xlsm')
        self.local = os.path.join(self.tmp, 'local')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def store(self):
        return rs.ReviewStore.for_report(self.report, 'UWWTP-AA-00-BM-RP-00002', self.local)

    def test_sidecar_is_named_after_document_code_and_sits_next_to_report(self):
        self.assertEqual(os.path.basename(self.store().path), 'UWWTP-AA-00-BM-RP-00002.clashreview.json')
        self.assertEqual(os.path.dirname(self.store().path), self.tmp)

    def test_mark_and_unmark_round_trip(self):
        s = self.store()
        self.assertTrue(s.set_done(u'T|Clash1', True, u'AntonioCVi\xf1as'))
        again = self.store()
        self.assertTrue(again.is_done(u'T|Clash1'))
        self.assertEqual(again.info(u'T|Clash1')['by'], u'AntonioCVi\xf1as')
        self.assertEqual(again.done_count, 1)
        again.set_done(u'T|Clash1', False)
        self.assertFalse(self.store().is_done(u'T|Clash1'))

    def test_two_people_do_not_overwrite_each_other(self):
        a, b = self.store(), self.store()
        a.set_done(u'T|Clash1', True, u'ana')
        b.set_done(u'T|Clash2', True, u'bob')
        merged = self.store()
        self.assertTrue(merged.is_done(u'T|Clash1') and merged.is_done(u'T|Clash2'))

    def test_file_is_plain_ascii_json(self):
        s = self.store()
        s.set_done(u'T|Clash1', True, u'Jos\xe9')
        with open(s.path, 'rb') as fh:
            raw = fh.read()
        raw.decode('ascii')
        self.assertEqual(json.loads(raw.decode('ascii'))['done'][u'T|Clash1']['by'], u'Jos\xe9')

    def test_read_only_folder_falls_back_to_local_copy(self):
        s = rs.ReviewStore(os.path.join(self.tmp, 'missing_drive_file', 'x.json'),
                           os.path.join(self.local, 'x.json'))
        original = s._write
        calls = []

        def write(path):
            calls.append(path)
            if path == s.path:
                raise IOError('read-only')
            return original(path)

        s._write = write
        self.assertTrue(s.set_done(u'T|Clash1', True, u'ana'))
        self.assertIn(u'this computer', s.message)
        self.assertEqual(os.path.dirname(s.path), self.local)

    def test_corrupt_file_is_reported_not_fatal(self):
        s = self.store()
        with open(s.path, 'w') as fh:
            fh.write('{not json')
        again = self.store()
        self.assertEqual(again.done_count, 0)
        self.assertIn(u'could not be read', again.message)

    def test_notes_round_trip_and_clear(self):
        s = self.store()
        self.assertTrue(s.set_note(u'T|Clash1', u'  Beam moved 200 mm ñ v3 ', u'ana'))
        again = self.store()
        self.assertEqual(again.note(u'T|Clash1'), u'Beam moved 200 mm ñ v3')
        self.assertEqual(again.note_info(u'T|Clash1')['by'], u'ana')
        again.set_note(u'T|Clash1', u'   ')
        self.assertEqual(self.store().note(u'T|Clash1'), u'')

    def test_note_and_done_are_independent_and_merge(self):
        a, b = self.store(), self.store()
        a.set_note(u'T|Clash1', u'check with MEP', u'ana')
        b.set_done(u'T|Clash1', True, u'bob')
        merged = self.store()
        self.assertTrue(merged.is_done(u'T|Clash1'))
        self.assertEqual(merged.note(u'T|Clash1'), u'check with MEP')

    def test_version_1_files_still_load(self):
        s = self.store()
        with open(s.path, 'w') as fh:
            json.dump({'version': 1, 'done': {'T|Clash9': {'by': 'x', 'at': '2026-10-19 10:00'}}}, fh)
        old = self.store()
        self.assertTrue(old.is_done(u'T|Clash9'))
        self.assertEqual(old.note(u'T|Clash9'), u'')

    def test_set_many_marks_and_unmarks_with_one_file(self):
        s = self.store()
        self.assertTrue(s.set_many([u'T|C1', u'T|C2', u'T|C3'], True, u'ana'))
        again = self.store()
        self.assertEqual(again.done_count, 3)
        again.set_many([u'T|C1', u'T|C3'], False)
        self.assertEqual([k for k in (u'T|C1', u'T|C2', u'T|C3') if self.store().is_done(k)], [u'T|C2'])


if __name__ == '__main__':
    unittest.main()
