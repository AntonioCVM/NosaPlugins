# -*- coding: utf-8 -*-
"""Revit-free tests for the pure logic of the plugins that had none (MASTER_ROADMAP, 2026-10-02).

Modules load under tests_support.revit_stubs.permissive_imports, so .NET / Revit / pyRevit
imports resolve to inert stubs; each test feeds plain Python data or small fakes.
"""
import io
import json
import math
import os
import shutil
import sys
import tempfile
import unittest

_EXT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_LIB = os.path.join(_EXT, 'lib')
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from tests_support.revit_stubs import Namespace, load_module, permissive_imports  # noqa: E402

_TAB = os.path.join(_EXT, 'NOSA.tab')
_MODULES = {}


def _plugin(*parts):
    """Load NOSA.tab/<parts> once, with its folder on sys.path, under permissive stubs."""
    path = os.path.join(_TAB, *parts)
    if path not in _MODULES:
        folder = os.path.dirname(path)
        if folder not in sys.path:
            sys.path.insert(0, folder)
        name = 'tpl_' + '_'.join(p.split('.')[0] for p in parts[-3:])
        with permissive_imports():
            _MODULES[path] = load_module(name, path)
    return _MODULES[path]


class _XYZ(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X, self.Y, self.Z = x, y, z


def _tmp_csv(test, text, name='data.csv'):
    folder = tempfile.mkdtemp()
    test.addCleanup(shutil.rmtree, folder, True)
    path = os.path.join(folder, name)
    with io.open(path, 'w', encoding='utf-8-sig') as f:
        f.write(text)
    return path


def _tmp_path(test, name):
    folder = tempfile.mkdtemp()
    test.addCleanup(shutil.rmtree, folder, True)
    return os.path.join(folder, name)


def _read_raw(path):
    with io.open(path, 'rb') as f:
        return f.read()


def _assert_one_bom(test, path):
    raw = _read_raw(path)
    test.assertTrue(raw.startswith(b'\xef\xbb\xbf'), 'CSV must start with a UTF-8 BOM (Excel)')
    test.assertEqual(raw.count(b'\xef\xbb\xbf'), 1, 'exactly one BOM')
    return raw.decode('utf-8-sig')


# --------------------------------------------------------------------------- Structures

class CenterBeamToColumnTests(unittest.TestCase):
    """'Structures.panel/Elements.pulldown/CenterBeamToColumn.pushbutton'"""

    def setUp(self):
        self.m = _plugin('Structures.panel', 'Elements.pulldown', 'CenterBeamToColumn.pushbutton',
                         'lib', 'logic.py')

    def test_closest_column_and_its_plan_distance(self):
        centres = {'c1': _XYZ(10, 0, 0), 'c2': _XYZ(3, 4, 99), 'c3': None}
        original = self.m.get_element_center
        self.m.get_element_center = lambda col: centres[col]
        try:
            col, dist = self.m.find_closest_column(_XYZ(0, 0, 0), ['c1', 'c2', 'c3'])
        finally:
            self.m.get_element_center = original
        self.assertEqual(col, 'c2')
        self.assertAlmostEqual(dist, 5.0)      # plan distance: Z ignored

    def test_no_columns_gives_none(self):
        self.assertEqual(self.m.find_closest_column(_XYZ(), []), (None, float('inf')))


class WaffleSlabTests(unittest.TestCase):
    """'Structures.panel/Elements.pulldown/WaffleSlab.pushbutton'"""

    def setUp(self):
        self.m = _plugin('Structures.panel', 'Elements.pulldown', 'WaffleSlab.pushbutton', 'lib', 'logic.py')

    def test_typical_waffle_is_valid_without_warnings(self):
        ok, _msg, warnings = self.m.validate_parameters(800, 150, 300, 50)
        self.assertTrue(ok)
        self.assertEqual(warnings, [])

    def test_limits(self):
        self.assertFalse(self.m.validate_parameters(1600, 150, 300, 50)[0])     # spacing > 1500
        self.assertTrue(self.m.validate_parameters(1200, 150, 300, 50)[0])      # BS 8110 band, warned
        self.assertEqual(len(self.m.validate_parameters(1200, 150, 300, 50)[2]), 1)
        self.assertFalse(self.m.validate_parameters(800, 90, 300, 50)[0])       # rib < 100
        self.assertFalse(self.m.validate_parameters(800, 150, 200, 50)[0])      # depth < 250
        self.assertFalse(self.m.validate_parameters(800, 150, 300, 120)[0])     # topping > 100
        self.assertEqual(len(self.m.validate_parameters(800, 110, 300, 45)[2]), 2)

    def test_point_in_polygon(self):
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        self.assertTrue(self.m.point_in_polygon_xy(5, 5, square))
        self.assertFalse(self.m.point_in_polygon_xy(15, 5, square))
        l_shape = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
        self.assertFalse(self.m.point_in_polygon_xy(7, 7, l_shape))
        self.assertTrue(self.m.point_in_polygon_xy(2, 7, l_shape))
        self.assertTrue(self.m.point_in_polygon_xy(50, 50, []))                # no boundary: accept


class StructuralScheduleProTests(unittest.TestCase):
    """'Structures.panel/Quantities.pulldown/StructuralSchedulePro.pushbutton'"""

    def setUp(self):
        self.m = _plugin('Structures.panel', 'Quantities.pulldown', 'StructuralSchedulePro.pushbutton',
                         'lib', 'logic_schedule_pro.py')

    def test_subtotal_row_after_each_group(self):
        rows = [{'mark': 'B1', 'level': 'L1'}, {'mark': 'B2', 'level': 'L1'}, {'mark': 'B3', 'level': 'L2'}]
        out = self.m.subtotals(rows, 'level')
        self.assertEqual([r.get('is_subtotal', False) for r in out], [False, False, True, False, True])
        self.assertEqual(out[2]['etype'], u'Count: 2')
        self.assertEqual(out[4]['etype'], u'Count: 1')
        self.assertIs(self.m.subtotals(rows, 'unknown'), rows)

    def test_csv_export(self):
        path = _tmp_path(self, 'schedule.csv')
        self.m.export_csv([{'mark': u'B1', 'etype': u'300x600', 'level': u'L1', 'length_m': 6.0,
                            'material': u'C32/40', 'category': u'Beams', 'ep_Comments': u'Viñas'}],
                          path, u'Test', extra_params=['Comments'])
        lines = _assert_one_bom(self, path).splitlines()
        self.assertEqual(lines[3], u'Mark,Type,Level,Length (m),Material,Category,Comments')
        self.assertEqual(lines[4], u'B1,300x600,L1,6.0,C32/40,Beams,Viñas')

    def test_density_box(self):
        ui = _plugin('Structures.panel', 'Quantities.pulldown', 'StructuralSchedulePro.pushbutton', 'lib', 'ui.py')
        self.assertEqual(ui._parse_density(Namespace(Text=u' 2400 ')), 2400.0)
        self.assertEqual(ui._parse_density(Namespace(Text=u'-1')), 2500.0)
        self.assertEqual(ui._parse_density(Namespace(Text=u'abc'), 7850.0), 7850.0)


class StructuralQATests(unittest.TestCase):
    """'Structures.panel/QA.pulldown/StructuralQA.pushbutton'"""

    def setUp(self):
        self.m = _plugin('Structures.panel', 'QA.pulldown', 'StructuralQA.pushbutton', 'lib',
                         'logic_quantification_qa.py')

    def test_concrete_aggregated_by_category_material_level(self):
        rows = [{'category': 'Floors', 'material_name': 'C32', 'level': 'L1', 'volume_m3': 1.2345, 'area_m2': 10.0},
                {'category': 'Floors', 'material_name': 'C32', 'level': 'L1', 'volume_m3': 1.0, 'area_m2': 5.556},
                {'category': 'Walls', 'material_name': 'C32', 'level': 'L1', 'volume_m3': 2.0, 'area_m2': 1.0}]
        out = self.m.aggregate_concrete_v2(rows)
        self.assertEqual(len(out), 2)
        floors = [r for r in out if r['category'] == 'Floors'][0]
        self.assertEqual((floors['volume_m3'], floors['area_m2'], floors['count']), (2.234, 15.56, 2))

    def test_rebar_weight_from_linear_density(self):
        out = self.m.aggregate_rebar([{'level': 'L1', 'diam_mm': 16, 'length_m': 6.0},
                                      {'level': 'L1', 'diam_mm': 16, 'length_m': 4.0}])
        self.assertEqual(out[0]['count'], 2)
        self.assertAlmostEqual(out[0]['weight_kg'], 10.0 * math.pi / 4 * 0.016 ** 2 * 7850, delta=0.1)

    def test_qa_issues_missing_material_zero_volume_and_outlier(self):
        base = {'category': 'Floors', 'level': 'L1', 'has_material': True}
        rows = [dict(base, id=i, name='F%d' % i, volume_m3=1.0) for i in range(10)]
        rows.append(dict(base, id=98, name='Huge', volume_m3=40.0))
        rows.append(dict(base, id=99, name='NoMat', volume_m3=0.0, has_material=False))
        problems = {(i['id'], i['severity']) for i in self.m.check_qa_issues(rows)}
        self.assertIn((99, 'High'), problems)       # no material
        self.assertIn((99, 'Medium'), problems)     # zero volume
        self.assertIn((98, 'Medium'), problems)     # outlier
        self.assertEqual(len(problems), 3)


class StructuralQADrawingCheckerTests(unittest.TestCase):
    """'Structures.panel/QA.pulldown/StructuralQA.pushbutton' — drawing checker reuses Template Guard rules."""

    def test_template_guard_rules_come_from_view_template_manager(self):
        m = _plugin('Structures.panel', 'QA.pulldown', 'StructuralQA.pushbutton', 'lib', 'logic_drawing_checker.py')
        with permissive_imports():
            tg = m._templateguard_logic()
        self.assertIsNotNone(tg)
        self.assertIn('ViewTemplateManager.pushbutton', tg.__file__)
        for name in ('load_rules', 'check_wrong_scale', 'check_sheet_naming', 'check_viewport_overrides',
                     'check_crop_region', 'check_detail_level'):
            self.assertTrue(callable(getattr(tg, name)), name)


class ElementJoinTests(unittest.TestCase):
    """'Structures.panel/Elements.pulldown/ElementJoin.pushbutton'"""

    def setUp(self):
        self.m = _plugin('Structures.panel', 'Elements.pulldown', 'ElementJoin.pushbutton', 'lib', 'logic.py')
        self.saved = (self.m._CONFIGS_ROOT, self.m._CONFIG_FILE)
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        self.m._CONFIGS_ROOT = os.path.join(folder, 'cfg')
        self.m._CONFIG_FILE = os.path.join(folder, 'cfg', 'element_join.json')

    def tearDown(self):
        self.m._CONFIGS_ROOT, self.m._CONFIG_FILE = self.saved

    def test_default_priority_without_config(self):
        self.assertEqual(self.m.load_priority(), list(self.m.DEFAULT_PRIORITY))

    def test_saved_order_round_trips(self):
        custom = list(reversed(self.m.DEFAULT_PRIORITY))
        self.m.save_priority(custom)
        self.assertEqual(self.m.load_priority(), custom)

    def test_order_with_other_categories_is_ignored(self):
        self.m.save_priority(['Nonsense'])
        self.assertEqual(self.m.load_priority(), list(self.m.DEFAULT_PRIORITY))


class ElementCommentsHubTests(unittest.TestCase):
    """'Structures.panel/ElementCommentsHub.pushbutton'"""

    def test_category_key_from_builtin_category_value(self):
        m = _plugin('Structures.panel', 'ElementCommentsHub.pushbutton', 'lib', 'logic.py')
        values = dict((c[2], -2000000 - i) for i, c in enumerate(m.CATEGORY_CHOICES))
        original = m.DB
        m.DB = Namespace(BuiltInCategory=Namespace(**values))
        try:
            for key, _label, bic in m.CATEGORY_CHOICES:
                self.assertEqual(m._category_key_for_bic(values[bic]), key)
            self.assertIsNone(m._category_key_for_bic(-1))
        finally:
            m.DB = original
        self.assertEqual(len(set(m.CATEGORY_KEYS)), len(m.CATEGORY_KEYS))


class StructuralTypeManagerTests(unittest.TestCase):
    """'Structures.panel/Elements.pulldown/StructuralTypeManager.pushbutton'"""

    def test_csv_cell_quotes_only_when_needed(self):
        ui = _plugin('Structures.panel', 'Elements.pulldown', 'StructuralTypeManager.pushbutton', 'lib', 'ui.py')
        self.assertEqual(ui._csv_cell(u'C32/40'), u'C32/40')
        self.assertEqual(ui._csv_cell(u'a,b'), u'"a,b"')
        self.assertEqual(ui._csv_cell(u'say "hi"'), u'"say ""hi"""')
        self.assertEqual(ui._csv_cell(12.5), u'12.5')


class PourSequencePlannerTests(unittest.TestCase):
    """'Structures.panel/Elements.pulldown/PourSequencePlanner.pushbutton'"""

    def test_first_writable_text_parameter_is_the_pour_parameter(self):
        m = _plugin('Structures.panel', 'Elements.pulldown', 'PourSequencePlanner.pushbutton', 'lib', 'logic.py')
        original = m.DB
        m.DB = Namespace(StorageType=Namespace(String='S', Double='D'))
        names = list(m._POUR_PARAM_NAMES)
        params = {names[0]: Namespace(IsReadOnly=True, StorageType='S'),
                  names[1]: Namespace(IsReadOnly=False, StorageType='S')} if len(names) > 1 else \
                 {names[0]: Namespace(IsReadOnly=False, StorageType='S')}
        element = Namespace(LookupParameter=lambda n: params.get(n))
        try:
            found = m._find_pour_param(element)
            self.assertIs(found, params[names[1] if len(names) > 1 else names[0]])
            self.assertIsNone(m._find_pour_param(Namespace(LookupParameter=lambda n: None)))
        finally:
            m.DB = original


# --------------------------------------------------------------------------- Foundations

class PilecapLoadCheckerTests(unittest.TestCase):
    """'Foundations.panel/PileTools.pulldown/PilecapLoadChecker.pushbutton'"""

    def setUp(self):
        self.m = _plugin('Foundations.panel', 'PileTools.pulldown', 'PilecapLoadChecker.pushbutton', 'lib', 'logic.py')

    def test_load_semaphore_thresholds(self):
        self.assertEqual(self.m._load_semaphore(750, 500, 2), (0.75, u'OK'))
        self.assertEqual(self.m._load_semaphore(-900, 500, 2), (0.9, u'WARNING'))
        self.assertEqual(self.m._load_semaphore(1100, 500, 2), (1.1, u'FAIL'))
        self.assertEqual(self.m._load_semaphore(None, 500, 2)[0], None)
        self.assertEqual(self.m._load_semaphore(100, 500, 0)[0], None)

    def test_rules_file_only_overrides_known_keys(self):
        path = _tmp_path(self, 'rules.json')
        key = sorted(self.m._DEFAULT_RULES)[0]
        with io.open(path, 'w', encoding='utf-8') as f:
            f.write(json.dumps({key: 'custom', 'unknown': 1}))
        original = self.m._RULES_FILE
        self.m._RULES_FILE = path
        try:
            rules = self.m.load_rules()
        finally:
            self.m._RULES_FILE = original
        self.assertEqual(rules[key], 'custom')
        self.assertNotIn('unknown', rules)
        self.assertEqual(set(rules), set(self.m._DEFAULT_RULES))


class FootingDesignerTests(unittest.TestCase):
    """'Foundations.panel/FootingDesigner.pushbutton'"""

    def test_existing_footing_detected_within_tolerance(self):
        m = _plugin('Foundations.panel', 'FootingDesigner.pushbutton', 'lib', 'logic_pad_footings.py')
        tol = m._FOOTING_XY_TOL_FT
        self.assertTrue(m._has_footing_near(_XYZ(0, 0), [_XYZ(tol * 0.6, tol * 0.6)]))
        self.assertFalse(m._has_footing_near(_XYZ(0, 0), [_XYZ(tol, tol)]))
        self.assertFalse(m._has_footing_near(_XYZ(0, 0), []))


class SiteToolkitTests(unittest.TestCase):
    """'Foundations.panel/SiteToolkit.pushbutton'"""

    def test_number_format(self):
        ui = _plugin('Foundations.panel', 'SiteToolkit.pushbutton', 'lib', 'ui.py')
        self.assertEqual(ui._fmt(1234567.891, 2), u'1,234,567.89')
        self.assertEqual(ui._fmt(12.4), u'12')
        self.assertEqual(ui._fmt(None), u'—')


class SurveyExportTests(unittest.TestCase):
    """'Foundations.panel/Survey.pulldown/SurveyExport.pushbutton'"""

    def setUp(self):
        self.m = _plugin('Foundations.panel', 'Survey.pulldown', 'SurveyExport.pushbutton', 'lib',
                         'logic_cuadro_replanteo.py')

    def test_survey_csv_aliases_and_metres_to_mm(self):
        path = _tmp_csv(self, u'Ref,Easting,Northing,Elevation\nP1,100.5,200.25,3.1\nP2,bad,1,1\nP3,1,2,\n')
        pts = self.m.load_survey_csv(path)
        self.assertEqual([p['mark'] for p in pts], ['P1', 'P3'])     # unparsable row skipped
        self.assertEqual((pts[0]['sx'], pts[0]['sy'], pts[0]['sz']), (100500.0, 200250.0, 3100.0))
        self.assertIsNone(pts[1]['sz'])

    def test_survey_csv_needs_x_and_y(self):
        with self.assertRaises(ValueError):
            self.m.load_survey_csv(_tmp_csv(self, u'Mark,Z\nP1,1\n'))

    def test_compare_flags_tolerance_and_unmatched_points(self):
        model = [{'mark': 'P1', 'x_mm': 1000.0, 'y_mm': 0.0, 'z_mm': 0.0},
                 {'mark': 'p2', 'x_mm': 0.0, 'y_mm': 0.0, 'z_mm': None},
                 {'mark': 'P9', 'x_mm': 0.0, 'y_mm': 0.0, 'z_mm': 0.0}]
        survey = [{'mark': 'P1', 'sx': 1003.0, 'sy': 4.0, 'sz': 0.0},
                  {'mark': 'P2', 'sx': 30.0, 'sy': 40.0, 'sz': 5.0},
                  {'mark': 'P7', 'sx': 0.0, 'sy': 0.0, 'sz': 0.0}]
        out = dict((r['mark'], r) for r in self.m.compare_survey(model, survey, tolerance_mm=10.0))
        self.assertEqual(out['P1']['status'], u'OK (5mm)')
        self.assertEqual(out['p2']['d_total'], 50.0)                 # no model Z: horizontal only
        self.assertTrue(out['p2']['status'].startswith(u'OUT OF TOLERANCE'))
        self.assertEqual(out['P9']['status'], u'No survey point')
        self.assertEqual(out['P7']['status'], u'No model element')


# --------------------------------------------------------------------------- Documentation

class SheetGenTests(unittest.TestCase):
    """'Documentation.panel/Sheets.pulldown/SheetGen.pushbutton'"""

    def setUp(self):
        self.m = _plugin('Documentation.panel', 'Sheets.pulldown', 'SheetGen.pushbutton', 'lib', 'logic.py')

    def test_unique_copy_numbers_are_case_insensitive(self):
        taken = {u's-101-copy'}
        self.assertEqual(self.m.allocate_unique_sheet_number(taken, u'S-101'), u'S-101-COPY2')
        self.assertEqual(self.m.allocate_unique_sheet_number(taken, u'S-101'), u'S-101-COPY3')
        self.assertEqual(self.m.allocate_unique_sheet_number(taken, u''), u'SHEET-COPY')

    def test_sheet_csv_round_trip(self):
        path = _tmp_path(self, 'sheets.csv')
        self.m.export_csv_sheets([{'number': u'S-101', 'name': u'Planta baja — Viñas'}], path)
        _assert_one_bom(self, path)
        headers, rows = self.m.parse_csv_sheets(path)
        self.assertEqual(headers[:2], ['Number', 'Name'])
        self.assertEqual(rows[0]['Name'], u'Planta baja — Viñas')


class SheetHubTests(unittest.TestCase):
    """'Documentation.panel/Sheets.pulldown/SheetHub.pushbutton'"""

    def test_grid_header_maps_to_field_key(self):
        ui = _plugin('Documentation.panel', 'Sheets.pulldown', 'SheetHub.pushbutton', 'lib', 'ui.py')
        first = ui._FIELD_KEYS[0]
        self.assertEqual(ui._field_key_from_header(first + u' Project No'), first)
        self.assertEqual(ui._field_key_from_header(u'  ' + first + u'  '), first)
        self.assertEqual(ui._field_key_from_header(u'Sheet Name'), u'Sheet Name')


class IssueWorkflowHubTests(unittest.TestCase):
    """'Documentation.panel/Issue.pulldown/IssueWorkflowHub.pushbutton'"""

    def _m(self, name):
        return _plugin('Documentation.panel', 'Issue.pulldown', 'IssueWorkflowHub.pushbutton', 'lib', name)

    def test_snapshot_diff(self):
        m = self._m('logic_revision_package_diff.py')
        base = {'S1': {'name': 'A', 'rev': 'P1'}, 'S2': {'name': 'B', 'rev': 'P1'}, 'S3': {'name': 'C', 'rev': 'P1'}}
        cur = {'S1': {'name': 'A', 'rev': 'P2'}, 'S2': {'name': 'B', 'rev': 'P1'}, 'S4': {'name': 'D', 'rev': 'P1'}}
        changes = dict((d['number'], d['change']) for d in m.diff_snapshots(base, cur))
        self.assertEqual(changes, {'S1': u'Revised', 'S2': u'Unchanged', 'S3': u'Removed', 'S4': u'New Sheet'})

    def test_transmittal_lists_only_changes_with_one_bom(self):
        m = self._m('logic_revision_package_diff.py')
        diffs = m.diff_snapshots({'S1': {'name': u'Sección', 'rev': 'P1'}, 'S2': {'name': 'B', 'rev': 'P1'}},
                                 {'S1': {'name': u'Sección', 'rev': 'P2'}, 'S2': {'name': 'B', 'rev': 'P1'}})
        path = _tmp_path(self, 'transmittal.csv')
        m.export_transmittal_csv(diffs, path)
        lines = _assert_one_bom(self, path).splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith(u'S1,Sección,Revised,P1,P2'))

    def test_issue_log_rows_and_csv(self):
        m = self._m('logic_sheet_issue_manager.py')
        records = m.add_issue([], ['S1', 'S2'], 'P3', u'Muñoz Ltd', 'Pkg', '', 'AV')
        self.assertEqual([r['sheet'] for r in records], ['S1', 'S2'])
        path = _tmp_path(self, 'log.csv')
        m.export_csv(records, path)
        lines = _assert_one_bom(self, path).splitlines()
        self.assertEqual(lines[0], u'Date,Sheet,Revision,Recipient,Package,Notes,Issued By')
        self.assertIn(u'Muñoz Ltd', lines[1])

    def test_protocol_summary_counts(self):
        m = self._m('logic_protocol_checker.py')
        results = [Namespace(status=s) for s in ('green', 'green', 'amber', 'red')]
        self.assertEqual(m.summarise(results), {'total': 4, 'green': 2, 'amber': 1, 'red': 1})


class ViewManagerTests(unittest.TestCase):
    """'Documentation.panel/Views.pulldown/ViewManager.pushbutton'"""

    def test_unique_names_case_insensitive(self):
        m = _plugin('Documentation.panel', 'Views.pulldown', 'ViewManager.pushbutton', 'lib', 'logic.py')
        taken = {u'level 1'}
        self.assertEqual(m._unique_name(u'Level 1', taken), u'Level 1 (2)')
        self.assertEqual(m._unique_name(u'Level 1', taken), u'Level 1 (3)')
        self.assertEqual(m._unique_name(u'Roof', taken), u'Roof')
        self.assertIn(u'roof', taken)


class ViewOverridesTests(unittest.TestCase):
    """'Documentation.panel/Views.pulldown/ViewOverrides.pushbutton'"""

    def test_colours_assigned_in_sorted_order_and_cycle(self):
        m = _plugin('Documentation.panel', 'Views.pulldown', 'ViewOverrides.pushbutton', 'lib',
                    'logic_colour_by_param.py')
        palette = list(m._PALETTE)
        values = [u'v{:02d}'.format(i) for i in range(len(palette) + 1)]
        colours = m.assign_colors(reversed(values))
        self.assertEqual(colours[u'v00'], palette[0])
        self.assertEqual(colours[values[-1]], palette[0])          # wraps around
        self.assertEqual(m.assign_colors([]), {})


class ViewTemplateManagerTests(unittest.TestCase):
    """'Documentation.panel/Views.pulldown/ViewTemplateManager.pushbutton'"""

    def test_sheet_naming_rule(self):
        m = _plugin('Documentation.panel', 'Views.pulldown', 'ViewTemplateManager.pushbutton', 'lib',
                    'logic_template_guard.py')
        sheets = [Namespace(SheetNumber=u'S-101', Name=u'General Arrangement', Id=1),
                  Namespace(SheetNumber=u'x1', Name=u'GA', Id=2)]
        saved = (m._collect_sheets, m.get_id_value)
        m._collect_sheets, m.get_id_value = (lambda doc: sheets), (lambda eid: eid)
        try:
            issues = m.check_sheet_naming(None, {'sheet_number_pattern': r'^[A-Z]-\d{3}$',
                                                 'sheet_name_min_length': 4})
        finally:
            m._collect_sheets, m.get_id_value = saved
        self.assertEqual([i['id'] for i in issues], [2])
        self.assertIn(u'does not match pattern', issues[0]['detail'])
        self.assertIn(u'Name too short', issues[0]['detail'])


class ViewUtilitiesTests(unittest.TestCase):
    """'Documentation.panel/Views.pulldown/ViewUtilities.pushbutton'"""

    def test_title_alignment_modes(self):
        m = _plugin('Documentation.panel', 'Views.pulldown', 'ViewUtilities.pushbutton', 'lib',
                    'logic_align_view_titles.py')
        original = m.DB
        m.DB = Namespace(XYZ=_XYZ)
        logic = m.__dict__[[k for k, v in m.__dict__.items()
                            if isinstance(v, type) and hasattr(v, 'calculate_aligned_offset')][0]]
        aligner = logic.__new__(logic)
        ref = Namespace(GetBoxCenter=lambda: _XYZ(1.0, 1.0))
        target = Namespace(GetBoxCenter=lambda: _XYZ(5.0, 2.0), LabelOffset=_XYZ(0.3, -0.4),
                           GetBoxOutline=lambda: Namespace(MinimumPoint=_XYZ(4.0, 1.0),
                                                           MaximumPoint=_XYZ(6.0, 3.0)))
        offset = _XYZ(-0.5, -0.6, 0.0)
        try:
            same = aligner.calculate_aligned_offset(offset, ref, target, 'Same as Reference', True)
            left = aligner.calculate_aligned_offset(offset, ref, target, 'Left', False)
        finally:
            m.DB = original
        self.assertEqual((same.X, round(same.Y, 6)), (0.5 - 5.0, round(0.4 - 2.0, 6)))
        self.assertEqual((left.X, left.Y), (-1.0, -0.4))


class AnnotationHubTests(unittest.TestCase):
    """'Documentation.panel/Annotations.pulldown/AnnotationHub.pushbutton'"""

    def setUp(self):
        self.m = _plugin('Documentation.panel', 'Annotations.pulldown', 'AnnotationHub.pushbutton', 'lib',
                         'logic_ga_auto_dim.py')

    def test_offset_constant_on_paper(self):
        at_50 = self.m.dim_offset_ft(Namespace(Scale=50), 8.0)
        at_100 = self.m.dim_offset_ft(Namespace(Scale=100), 8.0)
        self.assertAlmostEqual(at_50 * 304.8, 400.0)
        self.assertAlmostEqual(at_100, 2 * at_50)

    def test_nearest_grid_and_off_grid(self):
        original = self.m._grid_fixed_coord
        self.m._grid_fixed_coord = lambda g: g
        try:
            self.assertEqual(self.m._nearest_grid([0.0, 10.0, 20.0], 12.0), (10.0, 2.0))
            self.assertEqual(self.m._is_off_grid(_XYZ(10.05, 20.5), [20.0], [10.0], 0.1), (True, False))
        finally:
            self.m._grid_fixed_coord = original


class AnnotationSuiteTests(unittest.TestCase):
    """'Documentation.panel/Annotations.pulldown/AnnotationSuite.pushbutton'"""

    def test_sibling_tool_logic_is_found(self):
        ui = _plugin('Documentation.panel', 'Annotations.pulldown', 'AnnotationSuite.pushbutton', 'lib', 'ui.py')
        self.assertTrue(hasattr(ui._anno, '__file__'))
        self.assertTrue(hasattr(ui._gbb, '__file__'))
        with self.assertRaises(ImportError):
            ui._load_sibling_logic('NoSuchTool', 'nope')


class TextToolsTests(unittest.TestCase):
    """'Documentation.panel/Annotations.pulldown/TextTools.pushbutton'"""

    def test_case_tools_and_spatial_order(self):
        ui = _plugin('Documentation.panel', 'Annotations.pulldown', 'TextTools.pushbutton', 'lib', 'ui.py')
        self.assertEqual(ui.text_utils.capitalise_sentences(u'first. second! third'),
                         u'First. Second! Third')
        centres = {'a': _XYZ(5, 0), 'b': _XYZ(0, 10), 'c': _XYZ(1, 0)}
        original = ui._geo.get_element_center
        ui._geo.get_element_center = lambda e: centres[e]
        try:
            self.assertEqual(ui._sort_spatially(['a', 'b', 'c']), ['b', 'c', 'a'])   # top-down, left-right
        finally:
            ui._geo.get_element_center = original


# --------------------------------------------------------------------------- Data / coordination

class DataToolsHubTests(unittest.TestCase):
    """'Data.panel/DataTools.pulldown/DataToolsHub.pushbutton'"""

    def _m(self, name):
        return _plugin('Data.panel', 'DataTools.pulldown', 'DataToolsHub.pushbutton', 'lib', name)

    def test_csv_load_and_preview(self):
        m = self._m('logic_excel_sync.py')
        headers, rows = m.load_file(_tmp_csv(self, u'Mark,Comments\nB1,Viñas\nB22,\n'))
        self.assertEqual(headers, ['Mark', 'Comments'])
        self.assertEqual(rows[0]['Comments'], u'Viñas')
        preview = m.format_preview(headers, rows, max_rows=1).splitlines()
        self.assertEqual(preview[1], u'| Mark | Comments |')
        self.assertEqual(preview[-1], u'  ... and 1 more rows')
        self.assertEqual(m.format_preview(headers, []), '(empty)')

    def test_type_rename_preview(self):
        m = self._m('logic_type_renamer.py')
        self.assertEqual(m.preview_rename([u'300x600'], 'find_replace', u'x', u' x ', u'', u''),
                         [(u'300x600', u'300 x 600')])
        self.assertEqual(m.preview_rename([u'B1'], 'prefix_suffix', u'', u'', u'RC-', u'-A'),
                         [(u'B1', u'RC-B1-A')])

    def test_link_status_labels(self):
        m = self._m('logic_link_manager.py')
        self.assertEqual(m._link_status_label('LinkedFileStatus.Loaded'), u'Loaded')
        self.assertEqual(m._link_status_label('LinkedFileStatus.NotFound'), u'Missing')
        self.assertEqual(m._link_status_label('Other'), u'Other')


class ParameterHubTests(unittest.TestCase):
    """'Data.panel/ParameterHub.pushbutton'"""

    def test_csv_cell(self):
        ui = _plugin('Data.panel', 'ParameterHub.pushbutton', 'lib', 'ui.py')
        self.assertEqual(ui._csv_cell(u'plain'), u'plain')
        self.assertEqual(ui._csv_cell(u'line\nbreak'), u'"line\nbreak"')
        self.assertEqual(ui._csv_cell(u'5" bar'), u'"5"" bar"')


class SharedParamManagerTests(unittest.TestCase):
    """'Data.panel/SharedParamManager.pushbutton'"""

    def test_definitions_read_across_groups(self):
        m = _plugin('Data.panel', 'SharedParamManager.pushbutton', 'lib', 'logic_shared_param.py')
        defs = Namespace(Groups=[
            Namespace(Name=u'Rebar', Definitions=[Namespace(Name=u'NOSA_Rebar_Mark', GUID=u'g-1')]),
            Namespace(Name=u'General', Definitions=[Namespace(Name=u'NOSA_Drawn_By', GUID=u'g-2')])])
        out = m.read_file_definitions(defs)
        self.assertEqual([(d['name'], d['group'], d['guid']) for d in out],
                         [(u'NOSA_Rebar_Mark', u'Rebar', u'g-1'), (u'NOSA_Drawn_By', u'General', u'g-2')])
        self.assertEqual(m.read_file_definitions(None), [])


class ProjectSetupWizardTests(unittest.TestCase):
    """'Data.panel/ProjectSetupWizard.pushbutton'"""

    def test_project_information_dict(self):
        m = _plugin('Data.panel', 'ProjectSetupWizard.pushbutton', 'lib', 'logic.py')
        doc = Namespace(ProjectInformation=Namespace(Name=u'UWWTP', Number=u'1234', ClientName=None,
                                                     Address=u'Gibraltar', Status=u'Stage 4'))
        self.assertEqual(m.get_project_info(doc), {'name': u'UWWTP', 'number': u'1234', 'client': '',
                                                   'address': u'Gibraltar', 'status': u'Stage 4'})
        self.assertAlmostEqual(m._ft(304.8), 1.0)


class WorksharingAuditTests(unittest.TestCase):
    """'Data.panel/WorksharingAudit.pushbutton'"""

    def test_checkout_labels(self):
        m = _plugin('Data.panel', 'WorksharingAudit.pushbutton', 'lib', 'logic.py')
        for raw, label in m._CHECKOUT_LABELS.items():
            self.assertEqual(m._checkout_label(raw), label)
        self.assertEqual(m._checkout_label('Unexpected'), u'Unexpected')


class ModelHealthHubTests(unittest.TestCase):
    """'Structures.panel/Coordination.pulldown/ModelHealthHub.pushbutton'"""

    def _m(self, name):
        return _plugin('Structures.panel', 'Coordination.pulldown', 'ModelHealthHub.pushbutton', 'lib', name)

    def test_health_score(self):
        m = self._m('logic_health_score.py')
        self.assertEqual(m.calculate_score({}), 100.0)
        worst = dict((k, 10 ** 6) for k in m._WEIGHTS)
        self.assertAlmostEqual(m.calculate_score(worst), 0.0)
        key = sorted(m._WEIGHTS)[0]
        partial = m.calculate_score({key: 10 ** 6})
        self.assertAlmostEqual(100.0 - partial, 100.0 * m._WEIGHTS[key] / float(sum(m._WEIGHTS.values())))

    def test_parameter_drift_and_csv(self):
        m = self._m('logic_parameter_drift.py')
        diffs = m.compare_snapshots({'B1': {'Mark': u'B1', 'Comments': u'x'}},
                                    {'B1': {'Mark': u'B1-A', 'Level': u'L1'}})
        self.assertEqual([(d['param'], d['change']) for d in diffs],
                         [('Comments', u'Removed'), ('Level', u'Added'), ('Mark', u'Modified')])
        path = _tmp_path(self, 'drift.csv')
        m.export_diffs_csv(diffs, path)
        lines = _assert_one_bom(self, path).splitlines()
        self.assertEqual(lines[0], u'Element,Parameter,Change,Baseline Value,Current Value')
        self.assertEqual(len(lines), 4)

    def test_warning_triage(self):
        m = self._m('logic_warnings_triage.py')
        rules = {'rules': [{'keyword': 'Overlap', 'severity': 'High', 'action': 'Fix it'}],
                 'default_severity': 'Low', 'default_action': 'Review'}
        self.assertEqual(m._classify(u'Highlighted floors overlap.', rules), ('High', 'Fix it'))
        self.assertEqual(m._classify(None, rules), ('Low', 'Review'))
        keyword, action = sorted(m.FIXABLE_KEYWORDS.items())[0]
        self.assertEqual(m._detect_fix_type(u'xx ' + keyword.upper() + u' yy'), action)
        self.assertIsNone(m.get_fixable_description(u'nothing to fix'))

    def test_calc_csv_columns_by_alias(self):
        m = self._m('logic_model_sync.py')
        header = u','.join([m._ID_ALIASES[0], m._LENGTH_ALIASES[0], m._SECTION_ALIASES[0]])
        rows = m.parse_calc_csv(_tmp_csv(self, header + u'\nB1,"6,5",300x600\n,1,x\n'))
        self.assertEqual(rows, [{'mark': u'B1', 'section': u'300x600', 'length_m': 6.5, 'level': u''}])
        with self.assertRaises(ValueError):
            m.parse_calc_csv(_tmp_csv(self, u'foo,bar\n1,2\n'))

    def test_reaction_envelope_takes_max_axial(self):
        m = self._m('logic_foundation_loads.py')
        env = m._envelope([{'N': 100, 'Mx': 5}, {'N': -300, 'Mx': 1}, {'N': 200, 'Mx': 9}])
        self.assertEqual((env['N'], env['Mx']), (-300, 1))
        self.assertIsNone(m._envelope([])['N'])


# --------------------------------------------------------------------------- Hubs / dashboard

class RebarHubTests(unittest.TestCase):
    """'Structures.panel/Quantities.pulldown/RebarHub.pushbutton'"""

    def test_hub_finds_its_three_tool_logics(self):
        ui = _plugin('Structures.panel', 'Quantities.pulldown', 'RebarHub.pushbutton', 'lib', 'ui.py')
        for name in ('_bs_logic', '_sched_logic', '_aud_logic'):
            self.assertTrue(os.path.isfile(getattr(ui, name).__file__), name)

    def test_bs8666_groups_by_partition_and_mark(self):
        ui = _plugin('Structures.panel', 'Quantities.pulldown', 'RebarHub.pushbutton', 'lib', 'ui.py')
        bar = dict(diameter=16, diameter_label=u'H16', shape=u'00', shape_desc=u'Straight',
                   length_mm=3000.0, total_len_m=6.0, mass_kg=9.47, level=u'L1', host=u'Floor')
        bars = [dict(bar, mark=u'01', partition=u'F1', quantity=2),
                dict(bar, mark=u'01', partition=u'F1', quantity=3),
                dict(bar, mark=u'01', partition=u'F2', quantity=1, diameter=12)]
        groups = ui._bs_logic.group_by_mark(bars)
        self.assertEqual(sorted(g['mark'] for g in groups.values()), [u'F1 / 01', u'F2 / 01'])
        self.assertEqual(groups[(u'F1', u'01')]['quantity'], 5)
        self.assertEqual(ui._bs_logic.detect_duplicate_marks(bars), {})   # same mark, other partition
        self.assertEqual(ui.BsSchedRow(groups[(u'F2', u'01')]).MassKg, u'9.47')

    def test_bar_mass_per_metre(self):
        from nosa_utils.rebar_read import mass_per_m
        self.assertEqual(mass_per_m(16), 1.579)
        self.assertAlmostEqual(mass_per_m(14), 7850 * math.pi * 0.007 ** 2, places=6)


class NOSADashboardTests(unittest.TestCase):
    """'NOSA.Panel/NOSA.pushbutton'"""

    def test_plugin_inventory_walks_pulldowns(self):
        ui = _plugin('NOSA.Panel', 'NOSA.pushbutton', 'lib', 'ui.py')
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        for rel, version in (('A.pushbutton', '1.2'), ('P.pulldown/B.pushbutton', '2.0'),
                             ('P.pulldown/C.pushbutton', None)):
            os.makedirs(os.path.join(root, rel))
            if version:
                with io.open(os.path.join(root, rel, 'script.py'), 'w', encoding='utf-8') as f:
                    f.write(u'__title__ = "x"\n__version__ = "%s"\n' % version)
        os.makedirs(os.path.join(root, 'Ignored.nobutton'))
        win = ui.NOSADashboardWindow
        self.assertEqual(win._count_recursive(root), 3)
        found = []
        win._collect_plugins(root, u'Panel', found)
        self.assertEqual([(p.Name if hasattr(p, 'Name') else p.name) for p in found], ['A', 'B', 'C'])

    def test_version_file_is_read(self):
        ui = _plugin('NOSA.Panel', 'NOSA.pushbutton', 'lib', 'ui.py')
        version, _date = ui._read_version()
        self.assertTrue(version)


if __name__ == '__main__':
    unittest.main()
