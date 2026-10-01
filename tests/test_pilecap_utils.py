# -*- coding: utf-8 -*-
"""Revit-free tests for nosa_utils.pilecap_utils and the pile tools that use it (T5.5)."""
import math
import os
import random
import sys
import unittest

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from tests_support import revit_stubs  # noqa: E402

class _Eid(revit_stubs.FakeElementId):
    @property
    def Value(self):
        return self._value


DB, _ = revit_stubs.install_revit_stubs(
    db_attrs={'ElementId': revit_stubs.namespace(InvalidElementId=_Eid(-1))})


def _any_name(name):
    if name.startswith('__'):
        raise AttributeError(name)
    stub = type(name, (object,), {})
    setattr(DB, name, stub)
    return stub


DB.__getattr__ = _any_name  # other DB names are only touched inside functions


class _GenericList(object):
    def __getitem__(self, item_type):  # List[T](items)
        return list


revit_stubs.install_system_stubs().List = _GenericList()

from nosa_utils import pilecap_utils as pu  # noqa: E402

_EXT = os.path.dirname(_LIB)
_CAP_LOGIC = os.path.join(_EXT, 'NOSA.tab', 'Foundations.panel', 'PileTools.pulldown',
                          'CreatePilecapType.pushbutton', 'lib', 'logic.py')


# ── Reference copies of the implementations that were replaced ───────────────

def _old_addpile_point_in_polygon(x, y, polygon):
    if len(polygon) < 3:
        return False
    n = len(polygon)
    inside = False
    xinters = None
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def _old_addpile_edge_distance(x, y, polygon):
    if len(polygon) < 2:
        return float('inf')
    min_dist = float('inf')
    n = len(polygon)
    for i in range(n):
        p1x, p1y = polygon[i]
        p2x, p2y = polygon[(i + 1) % n]
        dx = p2x - p1x
        dy = p2y - p1y
        len_sq = dx * dx + dy * dy
        if len_sq == 0:
            dist = math.sqrt((x - p1x) ** 2 + (y - p1y) ** 2)
        else:
            t = max(0, min(1, ((x - p1x) * dx + (y - p1y) * dy) / len_sq))
            dist = math.sqrt((x - (p1x + t * dx)) ** 2 + (y - (p1y + t * dy)) ** 2)
        min_dist = min(min_dist, dist)
    return min_dist


def _old_cap_point_in_polygon(px, py, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and \
           (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


_SHAPES = {
    'square': [(0, 0), (10, 0), (10, 10), (0, 10)],
    'L': [(0, 0), (30, 0), (30, 10), (10, 10), (10, 30), (0, 30)],
    'U': [(0, 0), (30, 0), (30, 30), (20, 30), (20, 10), (10, 10), (10, 30), (0, 30)],
    'rotated': [(0, 0), (7.07, 7.07), (0, 14.14), (-7.07, 7.07)],
    'triangle_cw': [(0, 0), (5, 12), (13, 1)],
    'with_duplicate_vertex': [(0, 0), (10, 0), (10, 0), (10, 10), (0, 10)],
}


def _on_outline(x, y, poly, tol=1e-9):
    return pu.distance_to_polygon_edge(x, y, poly) < tol


class PolygonTests(unittest.TestCase):

    def test_matches_old_implementations_off_the_outline(self):
        rnd = random.Random(20260930)
        for name, poly in _SHAPES.items():
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]
            for _ in range(3000):
                x = rnd.uniform(min(xs) - 5, max(xs) + 5)
                y = rnd.uniform(min(ys) - 5, max(ys) + 5)
                if _on_outline(x, y, poly):
                    continue
                expected = _old_cap_point_in_polygon(x, y, poly)
                self.assertEqual(pu.point_in_polygon(x, y, poly), expected, (name, x, y))
                self.assertEqual(_old_addpile_point_in_polygon(x, y, poly), expected, (name, x, y))
                self.assertAlmostEqual(pu.distance_to_polygon_edge(x, y, poly),
                                       _old_addpile_edge_distance(x, y, poly), places=9)

    def test_grid_points_through_vertex_heights(self):
        # Rays passing exactly through vertices are the classic ray-cast trap.
        poly = _SHAPES['U']
        for x in [i * 2.5 + 0.3 for i in range(-2, 14)]:
            for y in [0.0, 10.0, 30.0, 5.0, 20.0]:
                if _on_outline(x, y, poly):
                    continue
                self.assertEqual(pu.point_in_polygon(x, y, poly),
                                 _old_addpile_point_in_polygon(x, y, poly), (x, y))

    def test_degenerate_polygons(self):
        self.assertFalse(pu.point_in_polygon(0, 0, []))
        self.assertFalse(pu.point_in_polygon(0, 0, [(0, 0), (1, 1)]))
        self.assertEqual(pu.distance_to_polygon_edge(0, 0, [(1, 1)]), float('inf'))
        self.assertAlmostEqual(pu.distance_to_segment(3, 4, 0, 0, 0, 0), 5.0)

    def test_distance_values(self):
        sq = _SHAPES['square']
        self.assertAlmostEqual(pu.distance_to_polygon_edge(5, 5, sq), 5.0)
        self.assertAlmostEqual(pu.distance_to_polygon_edge(2, 7, sq), 2.0)
        self.assertAlmostEqual(pu.distance_to_polygon_edge(13, 14, sq), 5.0)


# ── Model Group round-trip ───────────────────────────────────────────────────

class _Group(object):
    def __init__(self, members):
        self.members = members
        self.ungrouped = False

    def GetMemberIds(self):
        return list(self.members)

    def GetTypeId(self):
        return 'type'

    def UngroupMembers(self):
        self.ungrouped = True


class _BadGroup(_Group):
    def UngroupMembers(self):
        raise RuntimeError('locked')


class _El(object):
    def __init__(self, gid):
        self.GroupId = gid


class _Create(object):
    def __init__(self, fail=False):
        self.made = []
        self.fail = fail

    def NewGroup(self, ids):
        if self.fail:
            raise RuntimeError('nope')
        self.made.append(list(ids))


class _Doc(object):
    def __init__(self, groups, fail=False):
        self.groups = groups
        self.Create = _Create(fail)

    def GetElement(self, gid):
        return self.groups.get(gid)


class _Out(object):
    def __init__(self):
        self.lines = []

    def print_md(self, text):
        self.lines.append(text)


class GroupRoundTripTests(unittest.TestCase):

    def setUp(self):
        self.g1, self.g2 = _Eid(10), _Eid(20)
        self.invalid = DB.ElementId.InvalidElementId
        self.doc = _Doc({self.g1: _Group([1, 2, 3]), self.g2: _Group([4, 5])})

    def test_each_group_ungrouped_once_and_restored(self):
        els = [_El(self.g1), _El(self.g1), _El(self.invalid), _El(self.g2)]
        restore = pu.ungroup_targets(self.doc, els)
        self.assertEqual(restore, [('type', [1, 2, 3]), ('type', [4, 5])])
        self.assertTrue(all(g.ungrouped for g in self.doc.groups.values()))
        self.assertEqual(pu.regroup_restore(self.doc, restore), 2)
        self.assertEqual(self.doc.Create.made, [[1, 2, 3], [4, 5]])

    def test_failures_are_skipped_and_reported_only_with_output(self):
        doc = _Doc({self.g1: _BadGroup([1]), self.g2: _Group([4, 5])})
        self.assertEqual(pu.ungroup_targets(doc, [_El(self.g1), _El(self.g2)]),
                         [('type', [4, 5])])
        out = _Out()
        doc = _Doc({self.g1: _BadGroup([1])}, fail=True)
        self.assertEqual(pu.ungroup_targets(doc, [_El(self.g1)], out), [])
        self.assertEqual(pu.regroup_restore(doc, [('type', [1])], out), 0)
        self.assertEqual(len(out.lines), 2)
        self.assertIn('could not ungroup', out.lines[0])
        self.assertIn('could not regroup', out.lines[1])

    def test_missing_group_element_is_ignored(self):
        doc = _Doc({})
        self.assertEqual(pu.ungroup_targets(doc, [_El(self.g1)]), [])


# ── CreatePilecapType: cap outline validation still accepts its own caps ─────

class CreatePilecapTypeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.logic = revit_stubs.load_module('createpilecaptype_logic_test', _CAP_LOGIC)

    def test_every_irregular_shape_validates(self):
        logic = self.logic
        for shape in ('L', 'T', 'Plus', 'Z', 'U'):
            for a, b, c, d in [(3, 3, 1, 1), (4, 3, 2, 1), (5, 4, 1, 2)]:
                cells = logic.get_irregular_cells(shape, a, b, c, d)
                poly = logic.compute_cap_polygon(cells, 1500.0, 450.0)
                offsets = logic.pile_offsets_mm(cells, 1500.0)
                ok, problems = logic.validate_cap_polygon(poly, offsets, 450.0)
                self.assertTrue(ok, (shape, a, b, c, d, problems))

    def test_validation_rejects_pile_outside_or_too_close(self):
        poly = [(-1000.0, -1000.0), (1000.0, -1000.0), (1000.0, 1000.0), (-1000.0, 1000.0)]
        ok, problems = self.logic.validate_cap_polygon(poly, [(0.0, 0.0), (1500.0, 0.0)], 450.0)
        self.assertFalse(ok)
        self.assertIn('outside', problems[0])
        ok, problems = self.logic.validate_cap_polygon(poly, [(800.0, 0.0)], 450.0)
        self.assertFalse(ok)
        self.assertIn('edge distance 200 mm', problems[0])


if __name__ == '__main__':
    unittest.main()
