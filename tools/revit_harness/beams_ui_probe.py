# -*- coding: utf-8 -*-
"""
T7.2 end-to-end: 4 columns and 3 beams in a line, RebarAutomate's real Beams GENERATE with
"Continuous beam" ticked (selection faked, alerts captured), report the bars by layer and their
reach along the line, then roll EVERYTHING back. Revit errors roll their transaction back
instead of opening a dialog (harness only). Scope: doc, EXT_ROOT, PYREVIT, CONTROLS, VIEWS (bool: also reinforce a column and run Create
Views on the line and the column). Result: RESULT.
"""
import sys
import os
import json
import traceback
import __builtin__

try:
    unicode
except NameError:
    unicode = str  # CPython 3 compat

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
for _asm in ('PresentationCore', 'PresentationFramework', 'WindowsBase', 'System.Xaml'):
    clr.AddReference(_asm)
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)

from io import StringIO
_console = StringIO()
_old_stdout = sys.stdout
sys.stdout = _console
_log = []
_FT = 304.8
_failures = []


class _RollbackOnError(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, accessor):
        accessor.DeleteAllWarnings()
        errors = [f for f in accessor.GetFailureMessages() if f.GetSeverity() != DB.FailureSeverity.Warning]
        if not errors:
            return DB.FailureProcessingResult.Continue
        _failures.append(u'; '.join(f.GetDescriptionText() for f in errors))
        return DB.FailureProcessingResult.ProceedWithRollBack


def _guard_pyrevit_transactions():
    from pyrevit import revit
    original = revit.Transaction

    class Guarded(original):
        def __init__(self, *args, **kwargs):
            original.__init__(self, *args, **kwargs)
            ops = getattr(self, '_fhndlr_ops', None)
            if ops is not None:
                ops.SetFailuresPreprocessor(_RollbackOnError())
                ops.SetForcedModalHandling(False)
                self._rvtxn.SetFailureHandlingOptions(ops)
    revit.Transaction = Guarded
    return revit, original


def build_line():
    from nosa_utils.revit_helpers import element_name
    from Autodesk.Revit.DB.Structure import StructuralType
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
    symbols = list(DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol))
    col = [s for s in symbols if s.FamilyName == 'Concrete Rectangular' and element_name(s) == '450x600mm'][0]
    beam = [s for s in symbols if s.FamilyName == 'RC Beam' and element_name(s) == '300x600mm'][0]
    t = DB.Transaction(doc, 'NOSA test - beam line')
    ops = t.GetFailureHandlingOptions()
    ops.SetFailuresPreprocessor(_RollbackOnError())
    ops.SetForcedModalHandling(False)
    t.SetFailureHandlingOptions(ops)
    t.Start()
    for s in (col, beam):
        if not s.IsActive:
            s.Activate()
    xs = [0.0, 6450.0, 12900.0, 19350.0]
    columns = []
    for x in xs:
        c = doc.Create.NewFamilyInstance(DB.XYZ(x / _FT, 0, 0), col, levels[0], StructuralType.Column)
        c.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(levels[1].Id)
        columns.append(c)
    top = levels[1].Elevation
    beams = []
    for a, b in zip(xs[:-1], xs[1:]):
        line = DB.Line.CreateBound(DB.XYZ(a / _FT, 0, top), DB.XYZ(b / _FT, 0, top))
        beams.append(doc.Create.NewFamilyInstance(line, beam, levels[1], StructuralType.Beam))
    doc.Regenerate()
    for c in columns:
        for bm in beams:
            cb, bb = c.get_BoundingBox(None), bm.get_BoundingBox(None)
            if (cb.Max.X < bb.Min.X - 1e-3 or bb.Max.X < cb.Min.X - 1e-3 or
                    cb.Max.Y < bb.Min.Y - 1e-3 or bb.Max.Y < cb.Min.Y - 1e-3):
                continue  # only touching pairs: joining apart elements warns in a dialog
            try:
                if not DB.JoinGeometryUtils.AreElementsJoined(doc, c, bm):
                    DB.JoinGeometryUtils.JoinGeometry(doc, c, bm)
                if not DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, c, bm):
                    DB.JoinGeometryUtils.SwitchJoinOrder(doc, c, bm)
            except Exception:  # nosa-lint: disable=NOSA006 - not touching: nothing to join
                pass
    t.Commit()
    return columns, beams


def _tag_all_check(columns, beams):
    """T7.4: Tag All on the created views and an RC plan; count overlapping tags and crossing leaders."""
    from nosa_utils import tag_rules, tag_engine
    from nosa_utils.label_layout import segments_cross
    from nosa_utils.revit_helpers import element_name
    out = []
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
    plan_vft = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                if v.ViewFamily == DB.ViewFamily.StructuralPlan][0]
    t = DB.Transaction(doc, 'NOSA test - plan')
    t.Start()
    plan = DB.ViewPlan.Create(doc, plan_vft.Id, levels[1].Id)
    plan.Name = u'Tag All test plan'
    for tpl in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if tpl.IsTemplate and element_name(tpl) == u'NOSA RC PLAN':
            plan.ViewTemplateId = tpl.Id
    t.Commit()
    views = [plan] + [v for v in DB.FilteredElementCollector(doc).OfClass(DB.View)
                      if not v.IsTemplate and (element_name(v).startswith(u'Beam ') or
                                               element_name(v).startswith(u'Column ')) and
                      tag_rules.view_kind(v.ViewType)]
    for view in views:
        template = doc.GetElement(view.ViewTemplateId)
        keys = tag_rules.recommend(view.ViewType, element_name(template) if template else u'', view.Name,
                                   rebar_visible=bool(tag_engine.elements(doc, view, 'rebar')))
        r = tag_engine.tag_view(doc, view, keys)
        try:
            image = IMAGE
        except NameError:
            image = None
        if image and view.Id == plan.Id:
            from System.Collections.Generic import List
            opts = DB.ImageExportOptions()
            opts.ExportRange = DB.ExportRange.SetOfViews
            opts.SetViewsAndSheets(List[DB.ElementId]([view.Id]))
            opts.FilePath = image
            opts.HLRandWFViewsFileType = DB.ImageFileType.PNG
            opts.ZoomType = DB.ZoomFitType.FitToPage
            opts.PixelSize = 2400
            doc.ExportImage(opts)
        tags = list(DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag))
        measure = DB.Transaction(doc, 'NOSA test - measure')
        measure.Start()
        rects = tag_engine.head_rects(doc, view, tags)
        measure.RollBack()
        overlaps = sum(1 for i in range(len(rects)) for j in range(i + 1, len(rects))
                       if rects[i] and rects[j] and rects[i][0] < rects[j][2] and rects[j][0] < rects[i][2]
                       and rects[i][1] < rects[j][3] and rects[j][1] < rects[i][3])
        segs = []
        for x in tags:
            if not x.HasLeader:
                continue
            el = doc.GetElement(list(x.GetTaggedLocalElementIds())[0])
            geometry = 'line' if isinstance(getattr(el, 'Location', None), DB.LocationCurve) else 'area'
            anchor, _r = tag_engine._anchor(el, view, geometry)
            head = x.TagHeadPosition
            segs.append((anchor, (head.DotProduct(view.RightDirection), head.DotProduct(view.UpDirection))))
        crossings = 0
        lead_tags = [x for x in tags if x.HasLeader]
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                if segs[i][0] and segs[j][0] and segments_cross(segs[i][0], segs[i][1], segs[j][0], segs[j][1]):
                    crossings += 1
                    measure = DB.Transaction(doc, 'NOSA test - measure pair')
                    measure.Start()
                    pair_rects = tag_engine.head_rects(doc, view, [lead_tags[i], lead_tags[j]])
                    measure.RollBack()
                    out.append(u'    rects: {}'.format([tuple(round(v, 2) for v in pr) if pr else None for pr in pair_rects]))
                    for k in (i, j):
                        x = lead_tags[k]
                        el = doc.GetElement(list(x.GetTaggedLocalElementIds())[0])
                        out.append(u'    cross: tag {} on {} {} anchor ({:.2f},{:.2f}) head ({:.2f},{:.2f})'.format(
                            x.Id.IntegerValue, el.Category.Name, el.Id.IntegerValue, segs[k][0][0], segs[k][0][1],
                            segs[k][1][0], segs[k][1][1]))
        out.append(u'  TAG ALL "{}" keys {} -> new {} mra {} moved {} leaders {} failed {} | tags {} overlaps {} '
                   u'crossings {} {}'.format(element_name(view), keys, r['created'], r['mra'], r['rearranged'], r['leaders'],
                                             r['failed'], len(tags), overlaps, crossings, r['errors'][:2]))
    return out


group = None
revit_mod, original_tx = None, None
try:
    if u'template' not in doc.Title and u'Project1' not in doc.Title and u'Rebar test' not in doc.Title:
        raise RuntimeError(u'not a test model: ' + doc.Title)
    from nosa_utils.bootstrap import load_module
    from nosa_utils import shared_params
    from nosa_utils.revit_helpers import get_id_value
    from Autodesk.Revit.DB.Structure import RebarHostData
    revit_mod, original_tx = _guard_pyrevit_transactions()
    ra_lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
    ui = load_module('rebarautomate_ui', os.path.join(ra_lib, 'ui.py'))
    ui.forms.alert = lambda msg, *a, **k: _log.append(u'ALERT: ' + unicode(msg)) or True

    group = DB.TransactionGroup(doc, u'NOSA test - continuous beam')
    group.Start()
    columns, beams = build_line()
    _log.append(u'valid hosts: {}'.format([RebarHostData.IsValidHost(b) for b in beams]))

    win = ui.RebarAutomateWindow(doc)
    win.Show = lambda: None
    win._is_loaded = True
    for name, value in json.loads(CONTROLS or '{}').items():
        control = getattr(win, name)
        if isinstance(value, bool):
            control.IsChecked = value
        else:
            control.Text = unicode(value)
    values = win._read_beam_inputs()
    _log.append(u'values: {}'.format(dict((k, values[k]) for k in sorted(values))))

    class _Ref(object):
        def __init__(self, eid):
            self.ElementId = eid

    class _Selection(object):
        def PickObjects(self, *args):
            return [_Ref(b.Id) for b in beams]

    class _UIDoc(object):
        Document = doc
        Selection = _Selection()

    class _UIApp(object):
        ActiveUIDocument = _UIDoc()

    win._reinforcement_handler.pending = {'mode': 'beams', 'values': values}
    win._reinforcement_handler.Execute(_UIApp())
    _log.append(u'RESULT:\n' + unicode(win.TxtBeamResult.Text or u''))

    if VIEWS:
        from System.Collections.Generic import List
        col_values = win._read_column_inputs()
        win._reinforcement_handler.pending = {'mode': 'columns', 'values': col_values}

        class _ColSel(object):
            def PickObjects(self, *args):
                return [_Ref(columns[1].Id)]
        _UIDoc.Selection = _ColSel()
        win._reinforcement_handler.Execute(_UIApp())
        _log.append(u'columns: ' + unicode(win.TxtColumnResult.Text or u'').replace(u'\n', u' | '))
        win.uidoc.Selection.SetElementIds(List[DB.ElementId]([b.Id for b in beams] + [columns[1].Id]))
        win._create_views()
        _log.append(u'CREATE VIEWS: ' + unicode(win.TxtDetailingStatus.Text))
        from nosa_utils.revit_helpers import element_name
        for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
            if v.IsTemplate or not (element_name(v).startswith(u'Beam ') or element_name(v).startswith(u'Column ')):
                continue
            tpl = doc.GetElement(v.ViewTemplateId)
            n_tags = DB.FilteredElementCollector(doc, v.Id).OfCategory(
                DB.BuiltInCategory.OST_RebarTags).GetElementCount()  # nosa-lint: disable=NOSA002 - runs in Revit at call time
            _log.append(u'  view "{}" | 1:{} | template {} | tags {}'.format(
                element_name(v), v.Scale, element_name(tpl) if tpl else u'-', n_tags))
        for sh in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
            if sh.SheetNumber in (u'4002', u'4003', u'4004'):
                boxes = []
                for vid in sh.GetAllViewports():
                    o = doc.GetElement(vid).GetBoxOutline()
                    boxes.append(u'({:.0f},{:.0f})-({:.0f},{:.0f})'.format(o.MinimumPoint.X * _FT, o.MinimumPoint.Y * _FT,
                                                                          o.MaximumPoint.X * _FT, o.MaximumPoint.Y * _FT))
                _log.append(u'  sheet {} "{}" viewports {}'.format(sh.SheetNumber, sh.Name, u' '.join(boxes)))

        try:
            tag_all = TAGALL
        except NameError:
            tag_all = False
        if tag_all:
            _log.extend(_tag_all_check(columns, beams))

    from Autodesk.Revit.DB.Structure import MultiplanarOption
    rows = {}
    for bm in beams:
        for rebar in RebarHostData.GetRebarHostData(bm).GetRebarsInHost():
            layer = shared_params.read(rebar, u'NOSA_Rebar_Layer', u'?')
            xs, zs = [], []
            for i in range(rebar.NumberOfBarPositions):
                for c in rebar.GetTransformedCenterlineCurves(False, False, False,
                                                              MultiplanarOption.IncludeOnlyPlanarCurves, i):
                    for p in (c.GetEndPoint(0), c.GetEndPoint(1)):
                        xs.append(p.X * _FT)
                        zs.append(p.Z * _FT)
            rows.setdefault(layer, []).append(u'host {} n{} x {:.0f}..{:.0f} z {:.0f}..{:.0f}'.format(
                get_id_value(bm.Id), rebar.NumberOfBarPositions, min(xs), max(xs), min(zs), max(zs)))
    for layer in sorted(rows):
        if layer == u'stirrup':
            _log.append(u'{}: {} sets'.format(layer, len(rows[layer])))
            continue
        for row in rows[layer]:
            _log.append(u'{}: {}'.format(layer, row))
    try:
        win.Close()
    except Exception as e:
        _log.append(u'close: {}'.format(e))
    group.RollBack()
    group = None
    _log.append(u'rolled back')
except Exception:
    _log.append(u'EXCEPTION:\n' + unicode(traceback.format_exc()))
finally:
    if group is not None and group.HasStarted():
        group.RollBack()
        _log.append(u'rolled back (after error)')
    if revit_mod is not None:
        revit_mod.Transaction = original_tx
    sys.stdout = _old_stdout
    _log.extend(u'REVIT ERROR (rolled back): ' + f for f in _failures)

RESULT = u'\n'.join(_log) + u'\n--- console ---\n' + _console.getvalue()[-2500:]
