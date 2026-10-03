# -*- coding: utf-8 -*-
"""Revit-free tests for the most used plugins (MASTER_ROADMAP T6.3).

SheetExportHub naming · PileMaster coordinates · QRCode rendering · MaterialManager ·
CreatePilecapType (AddPileToPilecap is covered by test_pilecap_utils).
"""
import io
import os
import sys
import tempfile
import types
import unittest

_EXT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_LIB = os.path.join(_EXT, 'lib')
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from tests_support import revit_stubs  # noqa: E402


class _XYZ(object):
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z


DB, _ = revit_stubs.install_revit_stubs(db_attrs={'XYZ': _XYZ})


def _any_name(name):
    if name.startswith('__'):
        raise AttributeError(name)
    stub = type(name, (object,), {})
    setattr(DB, name, stub)
    return stub


DB.__getattr__ = _any_name   # other DB names are only touched inside functions
revit_stubs.install_system_stubs(full_tree=True)
for _name in ('System.Drawing',):
    sys.modules.setdefault(_name, types.ModuleType(_name))
sys.modules['System.Drawing'].Color = object
_pyrevit = sys.modules.setdefault('pyrevit', types.ModuleType('pyrevit'))
_pyrevit.revit = types.SimpleNamespace(doc=None)

from nosa_utils.bootstrap import load_module  # noqa: E402

_TAB = os.path.join(_EXT, 'NOSA.tab')


def _plugin(*parts):
    path = os.path.join(_TAB, *parts)
    folder = os.path.dirname(path)
    if folder not in sys.path:
        sys.path.insert(0, folder)
    return load_module('t63_' + '_'.join(p.split('.')[0] for p in parts[-3:]), path)


cap = _plugin('Foundations.panel', 'PileTools.pulldown', 'CreatePilecapType.pushbutton', 'lib', 'logic.py')
mat = _plugin('Structures.panel', 'Quantities.pulldown', 'MaterialManager.pushbutton', 'lib', 'logic.py')
coords = _plugin('Foundations.panel', 'PileTools.pulldown', 'PileMaster.pushbutton', 'lib', 'logic_coords.py')
qr = _plugin('Documentation.panel', 'QRCode.pushbutton', 'lib', 'qr_generator.py')
naming = _plugin('Documentation.panel', 'SheetExportHub.pushbutton', 'lib', 'naming.py')


class CreatePilecapTypeTests(unittest.TestCase):

    def test_rectangular_cap_size_is_spacing_grid_plus_two_edge_clearances(self):
        self.assertEqual(cap.calc_dimensions(3, 2, 1200, 500), (3400.0, 2200.0))
        self.assertEqual(cap.calc_dimensions(1, 1, 1200, 500), (1000.0, 1000.0))

    def test_pile_families_are_told_apart_from_footings_and_caps(self):
        self.assertTrue(cap._is_pile_candidate_foundation(u'Pile-Steel Pipe Circular', u'500mm Diameter'))
        self.assertTrue(cap._is_pile_candidate_foundation(u'Bored Pile', u''))
        self.assertFalse(cap._is_pile_candidate_foundation(u'Pile Cap-4 Pile', u'2000 x 2000'))
        self.assertFalse(cap._is_pile_candidate_foundation(u'RC Pad foundation', u'1500x1500x500'))

    def test_irregular_shapes_have_the_expected_pile_counts(self):
        self.assertEqual(len(cap.get_irregular_cells('L', 4, 3)), 6)        # 4 + 3 - shared corner
        self.assertEqual(len(cap.get_irregular_cells('U', 4, 3)), 8)        # base 4 + 2 arms of 2
        self.assertEqual(len(cap.get_irregular_cells('Plus', 5, 5)), 9)
        with self.assertRaises(ValueError):
            cap.get_irregular_cells('Q', 3, 3)

    def test_irregular_shapes_are_connected(self):
        for shape in ('L', 'T', 'Plus', 'Z', 'U'):
            cells = set(cap.get_irregular_cells(shape, 4, 4, 1, 1))
            seen, todo = set(), [next(iter(cells))]
            while todo:
                c = todo.pop()
                if c in seen:
                    continue
                seen.add(c)
                todo += [n for n in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1))
                         if n in cells]
            self.assertEqual(seen, cells, shape)

    def test_single_pile_cap_polygon_is_a_square_two_clearances_wide(self):
        poly = cap.compute_cap_polygon([(0, 0)], 1200, 500)
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        self.assertEqual(len(poly), 4)
        self.assertAlmostEqual(max(xs) - min(xs), 1000.0)
        self.assertAlmostEqual(max(ys) - min(ys), 1000.0)

    def test_collinear_vertices_are_dropped(self):
        square = [(0, 0), (1, 0), (2, 0), (2, 2), (0, 2)]
        self.assertEqual(cap._remove_collinear(square), [(0, 0), (2, 0), (2, 2), (0, 2)])


class MaterialManagerTests(unittest.TestCase):

    def test_levenshtein_distance(self):
        self.assertEqual(mat._lev(u'concrete', u'concrete'), 0)
        self.assertEqual(mat._lev(u'concrete', u'concret'), 1)
        self.assertEqual(mat._lev(u'c40', u'a very different name'), 99)   # length gap shortcut

    def test_near_duplicates_are_flagged_in_pairs(self):
        rows = [{'name': u'Concrete - RC32/40'}, {'name': u'Concrete - RC32/40 '},
                {'name': u'Steel S355'}]
        self.assertEqual(mat.find_near_duplicates(rows),
                         {u'Concrete - RC32/40', u'Concrete - RC32/40 '})

    def test_csv_export_has_one_bom_and_a_header(self):
        path = os.path.join(tempfile.mkdtemp(), 'materials.csv')
        mat.export_csv([{'name': u'Concrete', 'class': u'Concrete', 'category': u'Structural',
                         'use_count': 3, 'is_unused': False},
                        {'name': u'Old', 'class': u'Generic', 'category': u'',
                         'use_count': 0, 'is_unused': True}], path)
        with io.open(path, 'rb') as f:
            raw = f.read()
        self.assertEqual(raw.count(b'\xef\xbb\xbf'), 1)
        lines = raw.decode('utf-8-sig').splitlines()
        self.assertEqual(lines[0], u'Name,Class,Category,Use Count,Status')
        self.assertEqual(lines[2], u'Old,Generic,,0,Unused')


class PileMasterCoordinateTests(unittest.TestCase):

    def test_grouped_decimals(self):
        fmt = coords.CoordinateLogic._format_grouped_decimals
        self.assertEqual(fmt(1234567.2544), u'1,234,567.254')
        self.assertEqual(fmt(12.5, 1), u'12.5')

    def test_reporting_point_without_transform_is_the_model_point(self):
        logic = coords.CoordinateLogic.__new__(coords.CoordinateLogic)
        p = _XYZ(1.0, 2.0, 3.0)
        self.assertIs(logic.compute_reporting_point(p, 'coordination', None), p)

    def test_coordination_mode_uses_the_shared_transform(self):
        logic = coords.CoordinateLogic.__new__(coords.CoordinateLogic)
        shift = types.SimpleNamespace(OfPoint=lambda q: _XYZ(q.X + 100, q.Y + 200, q.Z))
        out = logic.compute_reporting_point(_XYZ(1.0, 2.0, 3.0), 'coordination', shift)
        self.assertEqual((out.X, out.Y, out.Z), (101.0, 202.0, 3.0))


class QRCodeTests(unittest.TestCase):

    def test_render_has_the_target_size_and_orange_finders(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest('Pillow not installed')
        n = 21
        matrix = [[(r + c) % 2 == 0 for c in range(n)] for r in range(n)]
        img = qr._render_pil(matrix, n, 24, 300)
        self.assertEqual(img.size, (283, 283))          # 24 mm at 300 dpi
        # the top-left finder ring (between 2.5 and 3.3 modules from its centre) is NOSA orange
        render_px = max(480, int(round(24 / 25.4 * 600)))
        pad = max(8, render_px // 40)
        module = (render_px - 2 * pad) / float(n)
        scale = 283.0 / render_px
        centre = (pad + 3.5 * module) * scale
        r, g, b, _a = img.getpixel((int(centre + 2.9 * module * scale), int(centre)))
        self.assertTrue(r > 200 and 60 < g < 160 and b < 80, (r, g, b))


class SheetExportNamingTests(unittest.TestCase):

    def test_template_order_can_be_edited(self):
        b = naming.NamingBuilder()
        for p in (u'Sheet Number', u'Sheet Name', u'Revision'):
            b.add_parameter(p)
        b.add_parameter(u'Sheet Name')                      # no duplicates
        b.move_up(u'Revision')
        b.move_down(u'Sheet Number')
        self.assertEqual(b.template, [u'Revision', u'Sheet Number', u'Sheet Name'])
        b.remove_parameter(u'Revision')
        self.assertEqual(b.template, [u'Sheet Number', u'Sheet Name'])

    def test_template_items_carry_functions_and_regex(self):
        b = naming.NamingBuilder()
        self.assertEqual(b._parse_template_item(u'Sheet Name|function:upper'),
                         (u'Sheet Name', 'function', u'upper'))
        self.assertEqual(b._parse_template_item(u'Sheet Name|regex:\\s+:_'),
                         (u'Sheet Name', 'regex', (u'\\s+', u'_')))
        self.assertEqual(b._parse_template_item(u'Revision'), (u'Revision', None, None))

    def test_functions_and_regex_transform_values(self):
        b = naming.NamingBuilder()
        self.assertEqual(b._apply_function(u'general arrangement', 'upper'), u'GENERAL ARRANGEMENT')
        self.assertEqual(b._apply_function(u'a b', 'replace_space'), u'a_b')
        self.assertEqual(b._apply_function(u'x' * 40, 'truncate_30'), u'x' * 30)
        self.assertEqual(b._apply_regex(u'GA  Plan', r'\s+', u'_'), u'GA_Plan')
        self.assertEqual(b._apply_regex(u'', r'\s', u'_'), u'')


if __name__ == '__main__':
    unittest.main()
