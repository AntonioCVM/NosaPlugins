# -*- coding: utf-8 -*-
"""Revit-free tests for the view / view-template helpers in nosa_utils.collectors."""
import os
import sys
import unittest

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from tests_support import revit_stubs  # noqa: E402


class FakeId(object):
    def __init__(self, value):
        self.Value = value

    def __eq__(self, other):
        return isinstance(other, FakeId) and other.Value == self.Value

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.Value)


INVALID = FakeId(-1)
VT = revit_stubs.namespace(FloorPlan='FloorPlan', Section='Section',
                           Legend='Legend', DrawingSheet='DrawingSheet')


class View(object):
    def __init__(self, vid, name, view_type, is_template=False, template=None):
        self.Id = FakeId(vid)
        self.Name = name
        self.ViewType = view_type
        self.IsTemplate = is_template
        self.ViewTemplateId = template.Id if template is not None else INVALID


class BrokenView(View):
    @property
    def IsTemplate(self):
        raise RuntimeError('element deleted')

    @IsTemplate.setter
    def IsTemplate(self, value):
        pass


class ViewSheet(View):
    def __init__(self, vid, viewport_ids=(), placed=None):
        View.__init__(self, vid, 'S%d' % vid, VT.DrawingSheet)
        self._viewports = [FakeId(x) for x in viewport_ids]
        self._placed = placed

    def GetAllViewports(self):
        return list(self._viewports)

    def GetAllPlacedViews(self):
        if self._placed is None:
            raise RuntimeError('not supported')
        return [FakeId(x) for x in self._placed]


class Viewport(object):
    def __init__(self, vid, view_id):
        self.Id = FakeId(vid)
        self.ViewId = FakeId(view_id)


ELEMENTS = []


class FakeCollector(object):
    def __init__(self, doc):
        self._cls = None

    def OfClass(self, cls):
        self._cls = cls
        return self

    def ToElements(self):
        return [e for e in ELEMENTS if isinstance(e, self._cls)]


class FakeDoc(object):
    def GetElement(self, eid):
        for e in ELEMENTS:
            if e.Id == eid:
                return e
        return None


DB, _ = revit_stubs.install_revit_stubs(db_attrs=dict(
    FilteredElementCollector=FakeCollector,
    View=View,
    ViewSheet=ViewSheet,
    ViewType=VT,
    ElementId=revit_stubs.namespace(InvalidElementId=INVALID),
    Transaction=object,
    BuiltInParameter=object,
    StorageType=object,
))

collectors = revit_stubs.load_module(
    'nosa_utils_collectors_under_test',
    os.path.join(_LIB, 'nosa_utils', 'collectors.py'))

DOC = FakeDoc()
TPL_PLAN = View(10, 'Plan Template', VT.FloorPlan, is_template=True)
TPL_UNUSED = View(11, 'Unused Template', VT.Section, is_template=True)
PLAN_A = View(20, 'Level 1', VT.FloorPlan, template=TPL_PLAN)
PLAN_B = View(21, 'Level 2', VT.FloorPlan)
SECTION = View(22, 'Section 1', VT.Section)
LEGEND = View(23, 'Legend', VT.Legend)
BROKEN = BrokenView(24, 'Broken', VT.FloorPlan)
SHEET_1 = ViewSheet(30, viewport_ids=[40, 41, 99], placed=[20, 23])
SHEET_2 = ViewSheet(31, viewport_ids=[42], placed=None)
VP_A = Viewport(40, 20)
VP_LEG = Viewport(41, 23)
VP_SEC = Viewport(42, 22)

ALL = [TPL_PLAN, TPL_UNUSED, PLAN_A, PLAN_B, SECTION, LEGEND, BROKEN,
       SHEET_1, SHEET_2, VP_A, VP_LEG, VP_SEC]


class CollectorTests(unittest.TestCase):

    def setUp(self):
        ELEMENTS[:] = ALL

    def test_collect_views_excludes_templates_and_broken_views(self):
        views = collectors.collect_views(DOC)
        self.assertEqual(views, [PLAN_A, PLAN_B, SECTION, LEGEND, SHEET_1, SHEET_2])

    def test_collect_views_can_keep_templates(self):
        views = collectors.collect_views(DOC, exclude_templates=False)
        self.assertIn(TPL_PLAN, views)
        self.assertIn(TPL_UNUSED, views)

    def test_collect_views_exclude_types(self):
        views = collectors.collect_views(DOC, exclude_types=(VT.Legend, VT.DrawingSheet))
        self.assertEqual(views, [PLAN_A, PLAN_B, SECTION])

    def test_collect_views_include_types(self):
        self.assertEqual(collectors.collect_views(DOC, include_types=(VT.FloorPlan,)),
                         [PLAN_A, PLAN_B])
        self.assertEqual(collectors.collect_views(DOC, include_types=()), [])

    def test_collect_views_keeps_collector_order(self):
        ELEMENTS[:] = [SECTION, PLAN_B, PLAN_A]
        self.assertEqual(collectors.collect_views(DOC), [SECTION, PLAN_B, PLAN_A])

    def test_collect_view_templates(self):
        self.assertEqual(collectors.collect_view_templates(DOC), [TPL_PLAN, TPL_UNUSED])

    def test_template_id_of_and_has_view_template(self):
        self.assertEqual(collectors.template_id_of(PLAN_A), TPL_PLAN.Id)
        self.assertIsNone(collectors.template_id_of(PLAN_B))
        self.assertTrue(collectors.has_view_template(PLAN_A))
        self.assertFalse(collectors.has_view_template(PLAN_B))

    def test_template_id_of_none_id(self):
        view = View(50, 'x', VT.FloorPlan)
        view.ViewTemplateId = None
        self.assertIsNone(collectors.template_id_of(view))

    def test_used_view_template_ids(self):
        self.assertEqual(collectors.used_view_template_ids(DOC), {10})

    def test_apply_view_template(self):
        view = View(51, 'New plan', VT.FloorPlan)
        self.assertTrue(collectors.apply_view_template(view, TPL_PLAN.Id))
        self.assertEqual(view.ViewTemplateId, TPL_PLAN.Id)

    def test_apply_view_template_ignores_missing_id(self):
        view = View(52, 'New plan', VT.FloorPlan, template=TPL_PLAN)
        self.assertFalse(collectors.apply_view_template(view, None))
        self.assertFalse(collectors.apply_view_template(view, INVALID))
        self.assertEqual(view.ViewTemplateId, TPL_PLAN.Id)

    def test_placed_view_ids_via_viewports_skips_missing_viewports(self):
        self.assertEqual(collectors.placed_view_ids(DOC), {20, 23, 22})

    def test_placed_view_ids_all_placed_skips_failing_sheets(self):
        self.assertEqual(collectors.placed_view_ids(DOC, all_placed=True), {20, 23})


if __name__ == '__main__':
    unittest.main()
