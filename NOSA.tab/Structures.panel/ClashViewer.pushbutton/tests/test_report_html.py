# -*- coding: utf-8 -*-
"""Revit-free checks of the HTML report builder and of the re-check helpers."""
import importlib.util
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, stubs=()):
    saved = {}
    for stub in stubs:
        saved[stub] = sys.modules.get(stub)
        sys.modules[stub] = types.ModuleType(stub)
    if 'Autodesk.Revit' in stubs:
        sys.modules['Autodesk'].Revit = sys.modules['Autodesk.Revit']
        sys.modules['Autodesk.Revit'].DB = sys.modules['Autodesk.Revit.DB']
    if 'nosa_utils.telemetry' in stubs:
        sys.modules['nosa_utils.telemetry'].log_swallowed = lambda *a, **k: None
    try:
        spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, '..', 'lib', name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for stub, old in saved.items():
            if old is None:
                sys.modules.pop(stub, None)
            else:
                sys.modules[stub] = old


report_html = _load('report_html')
check = _load('clash_check', ('Autodesk', 'Autodesk.Revit', 'Autodesk.Revit.DB', 'nosa_utils',
                              'nosa_utils.solids', 'nosa_utils.telemetry'))

_META = {'document_code': u'UWWTP-AA-00-BM-RP-00002', 'revision': u'P06', 'revision_date': u'2026-10-15',
         'generated': u'2026-10-19 12:30', 'user': u'AntonioCVi\xf1as', 'scope': u'3 clashes (filtered list)'}


def _entry(**kw):
    e = {'test': u'Piping_Vs_Structural', 'group': u'Slab Edges', 'name': u'Clash200', 'status': u'Active',
         'assigned': u'NE-Dionis David', 'point': u'x 1  y 2  z 3', 'before': b'\xff\xd8\xff\xe0abc',
         'after': b'\x89PNGdef', 'done': False,
         'items': [{'title': u'ITEM 1', 'info': [u'Pipe', u'Id 1'], 'state': u'Found', 'kind': u'ok'},
                   {'title': u'ITEM 2', 'info': [u'Slab Edge'], 'state': u'Not found', 'kind': u'bad'}]}
    e.update(kw)
    return e


class ReportTests(unittest.TestCase):
    def test_both_images_are_embedded_with_the_right_mime(self):
        html = report_html.build_report(_META, [_entry()])
        self.assertIn(u'data:image/jpeg;base64,', html)
        self.assertIn(u'data:image/png;base64,', html)
        self.assertNotIn(u'src="http', html)

    def test_missing_image_shows_a_placeholder(self):
        html = report_html.build_report(_META, [_entry(after=None)])
        self.assertIn(u'No image available', html)

    def test_user_text_is_escaped(self):
        html = report_html.build_report(_META, [_entry(note=u'<script>alert(1)</script> & "x"', name=u'<b>C</b>')])
        self.assertNotIn(u'<script>alert', html)
        self.assertIn(u'&lt;script&gt;', html)
        self.assertIn(u'&lt;b&gt;C&lt;/b&gt;', html)

    def test_summary_counts_done_open_and_checks(self):
        entries = [_entry(done=True, done_by=u'ana', done_at=u'2026-10-19 10:00', check_kind=u'cleared',
                          check_text=u'No longer clashing'),
                   _entry(name=u'Clash2', check_kind=u'still', check_text=u'Still clashing'),
                   _entry(name=u'Clash3')]
        html = report_html.build_report(_META, entries)
        self.assertIn(u'<b>3</b><span>Clashes in this report', html)
        self.assertIn(u'<b>1</b><span>Done', html)
        self.assertIn(u'<b>2</b><span>Open', html)
        self.assertIn(u'<b>1</b><span>No longer clashing', html)
        self.assertIn(u'Done · ana, 2026-10-19 10:00', html)
        self.assertIn(u'Geometry re-check: Still clashing', html)

    def test_joined_verdict_is_counted_and_shown_as_a_warning(self):
        html = report_html.build_report(_META, [_entry(check_kind=u'joined', check_text=u'Joined in Revit (Join Geometry)')])
        self.assertIn(u'Joined in Revit', html)
        self.assertIn(u'k-warn', html)

    def test_non_ascii_user_and_british_text(self):
        html = report_html.build_report(_META, [_entry()])
        self.assertIn(u'AntonioCVi\xf1as', html)
        self.assertIn(u'lang="en-GB"', html)


class CheckHelperTests(unittest.TestCase):
    def test_tolerance_parsing(self):
        self.assertEqual(check.tolerance_mm(u'1mm'), 1.0)
        self.assertEqual(check.tolerance_mm(u'5 mm'), 5.0)
        self.assertEqual(check.tolerance_mm(u'0,5mm'), 0.5)
        self.assertEqual(check.tolerance_mm(u''), 1.0)

    def test_apart_uses_the_tolerance(self):
        P = type('P', (), {})

        def pt(x, y, z):
            p = P()
            p.X, p.Y, p.Z = x, y, z
            return p
        a = (pt(0, 0, 0), pt(1, 1, 1))
        self.assertTrue(check._apart(a, (pt(2, 0, 0), pt(3, 1, 1)), 0.0))
        self.assertFalse(check._apart(a, (pt(1.05, 0, 0), pt(3, 1, 1)), 0.1))
        self.assertFalse(check._apart(a, (pt(0.5, 0.5, 0.5), pt(2, 2, 2)), 0.0))


if __name__ == '__main__':
    unittest.main()
