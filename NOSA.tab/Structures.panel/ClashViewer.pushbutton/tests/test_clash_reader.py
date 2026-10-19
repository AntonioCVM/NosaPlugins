# -*- coding: utf-8 -*-
"""Parser checks for clash_reader: a synthetic workbook (always) and the real report (if present).

Run:  python -m unittest discover -s tests          (from the pushbutton folder)
Set NOSA_CLASH_REPORT to the .xlsm path to test another copy of the report.
"""
import importlib.util
import io
import os
import tempfile
import unittest
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    'clash_reader', os.path.join(_HERE, '..', 'lib', 'clash_reader.py'))
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)

REAL_REPORT = os.environ.get('NOSA_CLASH_REPORT') or os.path.join(
    os.path.expanduser('~'), 'NOSA', 'NOSA - Shared Data', '1. Projects', '23112 - WWTP',
    '2. Incoming', 'Contractor - ACCIONA', '261015 - Clash repports XML',
    'UWWTP-AA-00-BM-RP-00002.xlsm')

_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def _cell(ref, value):
    if value is None:
        return ''
    if isinstance(value, (int, float)):
        return '<c r="%s"><v>%s</v></c>' % (ref, value)
    value = value.replace('&', '&amp;').replace('<', '&lt;')
    return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, value)


def _sheet(rows):
    out = []
    for r, cells in sorted(rows.items()):
        body = ''.join(_cell('%s%d' % (col, r), v) for col, v in cells.items())
        out.append('<row r="%d">%s</row>' % (r, body))
    return ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="%s"><sheetData>%s'
            '</sheetData></worksheet>' % (_MAIN, ''.join(out)))


def _clash_sheet(title, clashes):
    rows = {
        4: {'A': title, 'C': 'Tolerance', 'D': 'Clashes', 'E': 'New', 'F': 'Active',
            'G': 'Reviewed', 'H': 'Approved', 'I': 'Resolved', 'J': 'Type', 'K': 'Status'},
        5: {'C': '1mm', 'D': len(clashes), 'E': 1, 'F': 1, 'G': 0, 'H': 0, 'I': 0,
            'J': 'Hard', 'K': 'Old'},
        7: {'M': 'Item 1', 'V': 'Item 2'},
        8: {'A': 'Image', 'C': 'Clash Group', 'E': 'Clash Name', 'G': 'Status',
            'H': 'Assigned To', 'I': 'Date Approved', 'J': 'Clash Point',
            'M': 'Path', 'N': 'Element Category', 'O': 'Element Family', 'P': 'Element Id',
            'Q': 'Element Properties UniqueId', 'R': 'AutoCAD Class', 'T': 'AutoCAD Tag',
            'V': 'Path', 'W': 'Element Category', 'Y': 'Element Id',
            'Z': 'Element Properties UniqueId'},
    }
    r = 9
    seen = set()
    for c in clashes:
        if c['group'] not in seen:
            seen.add(c['group'])
            rows[r] = {'E': c['group'], 'G': c['status'], 'M': c['p1']}   # group header row
            r += 1
        rows[r] = {'C': c['group'], 'E': c['name'], 'G': c['status'], 'H': c.get('who'),
                   'I': c.get('date'), 'J': c.get('point'), 'M': c['p1'], 'N': c.get('cat1'),
                   'P': c.get('id1'), 'R': c.get('cls'), 'T': c.get('tag'),
                   'V': c['p2'], 'W': 'Walls', 'Y': c.get('id2'), 'Z': c.get('uid2')}
        r += 1
    return _sheet(rows)


def _build_workbook(path):
    sheets = [
        ('sign', _sheet({18: {'B': 'P02', 'C': 46290}, 19: {'B': 'P03', 'C': 46294},
                         52: {'C': 'UWWTP-', 'D': 'AA-', 'E': '00-', 'F': 'BM-',
                              'G': 'RP-', 'H': '00002'}})),
        ('Clash Summary', _sheet({1: {'A': 'Test Name', 'B': 'Total Clashes'},
                                  2: {'A': 'T_One', 'B': 2}})),
        ('T_One', _clash_sheet('T_One_Full_Name', [
            {'group': 'Walls', 'name': 'Clash1', 'status': 'New', 'who': 'AA-Ana & NE-Bob',
             'date': u'2026/9/14\xa0 10:44', 'point': 'x:288581488, y:3999342951, z:3280',
             'p1': 'UWWTP-AA-10-EM-MD-00001.nwc', 'cls': 'Pipe', 'tag': '10 GTA001',
             'p2': 'UWWTP-GA-10-AR-MD-00001.nwc', 'id2': '1292445',
             'uid2': 'f2a703f7-6ed8-4d73-905b-4847fbf9dd60-0013b89d'},
            {'group': 'Beams', 'name': 'Clash2', 'status': 'Active',
             'p1': 'UWWTP-NE-10-ST-MD-00001.nwc', 'cat1': 'Floors', 'id1': 1010447.0,
             'p2': 'UWWTP-NE-10-ST-MD-00001.nwc', 'id2': 77},
        ])),
        ('Not_A_Test', _sheet({1: {'A': 'hello'}})),
    ]
    with zipfile.ZipFile(path, 'w') as z:
        sh = ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d" xmlns:r="%s"/>'
                     % (n, i + 1, i + 1, _REL) for i, (n, _) in enumerate(sheets))
        z.writestr('xl/workbook.xml',
                   '<workbook xmlns="%s"><sheets>%s</sheets></workbook>' % (_MAIN, sh))
        rels = ''.join('<Relationship Id="rId%d" Type="x/worksheet" Target="worksheets/sheet%d.xml"/>'
                       % (i + 1, i + 1) for i in range(len(sheets)))
        z.writestr('xl/_rels/workbook.xml.rels',
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '%s</Relationships>' % rels)
        for i, (_, xml) in enumerate(sheets):
            z.writestr('xl/worksheets/sheet%d.xml' % (i + 1), xml)


class SyntheticReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.path = os.path.join(cls.tmp, 'UWWTP-AA-00-BM-RP-00002.xlsx')
        _build_workbook(cls.path)
        cls.report = cr.load_report(cls.path)

    def test_only_clash_sheets_are_tests(self):
        self.assertEqual([t.sheet_name for t in self.report.tests], ['T_One'])

    def test_full_name_comes_from_a4(self):
        self.assertEqual(self.report.tests[0].name, 'T_One_Full_Name')

    def test_group_rows_are_not_clashes(self):
        test = self.report.tests[0]
        self.assertEqual(len(test.clashes), 2)
        self.assertEqual(list(test.groups), ['Walls', 'Beams'])

    def test_counts_and_header_values(self):
        test = self.report.tests[0]
        self.assertEqual(test.tolerance, '1mm')
        self.assertEqual(test.test_type, 'Hard')
        self.assertEqual(test.declared['Total'], 2)
        self.assertEqual(test.counts()['New'], 1)
        self.assertEqual(test.warnings, [])

    def test_clash_fields(self):
        c = self.report.tests[0].clashes[0]
        self.assertEqual(c.name, 'Clash1')
        self.assertEqual(c.assignees, ['AA-Ana', 'NE-Bob'])
        self.assertEqual(c.date_approved, '2026-09-14 10:44')
        self.assertEqual(c.point_mm, (288581488.0, 3999342951.0, 3280.0))

    def test_items_split_by_block(self):
        c = self.report.tests[0].clashes[0]
        self.assertTrue(c.item1.is_plant)
        self.assertFalse(c.item1.is_revit)
        self.assertEqual((c.item1.acad_class, c.item1.acad_tag), ('Pipe', '10 GTA001'))
        self.assertEqual(c.item1.discipline, 'EM')
        self.assertEqual(c.item2.element_id, 1292445)
        self.assertEqual(c.item2.unique_id, 'f2a703f7-6ed8-4d73-905b-4847fbf9dd60-0013b89d')
        self.assertEqual(c.item2.discipline, 'AR')
        self.assertEqual(c.item2.author, 'GA')

    def test_numeric_element_id_cell(self):
        c = self.report.tests[0].clashes[1]
        self.assertEqual(c.item1.element_id, 1010447)
        self.assertEqual(c.item1.model_base, 'UWWTP-NE-10-ST-MD-00001')

    def test_cover_revision_and_code(self):
        self.assertEqual(self.report.revision, 'P03')
        self.assertEqual(self.report.revision_date, '2026-09-29')
        self.assertEqual(self.report.document_code, 'UWWTP-AA-00-BM-RP-00002')

    def test_summary_rows(self):
        self.assertEqual(self.report.summary[0]['test name'], 'T_One')

    def test_not_a_workbook(self):
        bad = os.path.join(self.tmp, 'bad.xlsm')
        with open(bad, 'wb') as fh:
            fh.write(b'not a zip')
        with self.assertRaises(cr.ClashReaderError):
            cr.load_report(bad)

    def test_no_image_is_fine(self):
        self.assertIsNone(self.report.get_image_bytes(self.report.tests[0].clashes[0]))


@unittest.skipUnless(os.path.isfile(REAL_REPORT), 'real report not available')
class RealReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = cr.load_report(REAL_REPORT)

    def test_six_tests_detected(self):
        self.assertEqual(len(self.report.tests), 6)

    def test_totals(self):
        totals = [len(t.clashes) for t in self.report.tests]
        self.assertEqual(totals, [34, 19, 15, 99, 302, 532])
        self.assertEqual(self.report.total, 1001)

    def test_no_declared_mismatch(self):
        self.assertEqual(self.report.warnings, [])

    def test_group_rows_not_counted(self):
        for t in self.report.tests:
            self.assertTrue(all(c.name.lower().startswith('clash') for c in t.clashes))
            self.assertEqual(len(set(c.name for c in t.clashes)), len(t.clashes))
            self.assertTrue(set(t.groups) >= set(c.group for c in t.clashes))

    def test_full_names_not_truncated(self):
        names = [t.name for t in self.report.tests]
        self.assertIn('Mechanical_Vs_Structural Concrete', names)

    def test_clash_point(self):
        c = self.report.tests[0].clashes[0]
        self.assertEqual(c.point_mm, (288581488.0, 3999342951.0, 3280.0))

    def test_cover(self):
        self.assertEqual(self.report.revision, 'P06')
        self.assertEqual(self.report.revision_date, '2026-10-15')
        self.assertEqual(self.report.document_code, 'UWWTP-AA-00-BM-RP-00002')

    def test_summary_matches(self):
        self.assertEqual(self.report.summary[-1]['total clashes'], '1001')

    def test_every_clash_has_an_image(self):
        missing = [c.key for c in self.report.all_clashes() if not c.image_member]
        self.assertEqual(missing, [])
        data = self.report.get_image_bytes(self.report.tests[0].clashes[0])
        self.assertTrue(data[:2] == b'\xff\xd8' or data[:4] == b'\x89PNG')

    def test_revit_and_plant_items(self):
        c = self.report.tests[0].clashes[0]
        self.assertTrue(c.item1.is_plant and not c.item1.is_revit)
        self.assertTrue(c.item2.is_revit and c.item2.element_id == 1292445)


if __name__ == '__main__':
    unittest.main()
