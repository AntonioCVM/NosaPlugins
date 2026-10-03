# -*- coding: utf-8 -*-
"""
T7.8 end-to-end: build a dog-leg cast-in-place stair, run RebarAutomate's real Stairs GENERATE
(selection faked, alerts captured), report what was stamped, then roll EVERYTHING back (the
shared-parameter binding included). Scope: doc, EXT_ROOT, PYREVIT, CONTROLS (JSON), SUPPORT (floor type name under the start, or '').
Result: RESULT.
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
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Architecture as DBA
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


class _Quiet(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, accessor):
        for f in accessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                accessor.DeleteWarning(f)
        return DB.FailureProcessingResult.Continue


def comments(element):
    return element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).AsString() or u''


def build_stairs():
    from nosa_utils.revit_helpers import element_name
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
    cip = [t for t in DB.FilteredElementCollector(doc).OfClass(DBA.StairsType)
           if element_name(t) == 'Concrete Stair'][0]
    scope = DB.StairsEditScope(doc, 's')
    sid = scope.Start(levels[0].Id, levels[1].Id)
    t = DB.Transaction(doc, 'NOSA test - runs')
    t.Start()
    doc.GetElement(sid).ChangeTypeId(cip.Id)
    r1 = DBA.StairsRun.CreateStraightRun(doc, sid, DB.Line.CreateBound(DB.XYZ(0, 0, 0), DB.XYZ(8, 0, 0)),
                                         DBA.StairsRunJustification.Center)
    z = r1.TopElevation
    r2 = DBA.StairsRun.CreateStraightRun(doc, sid, DB.Line.CreateBound(DB.XYZ(8, 5, z), DB.XYZ(0, 5, z)),
                                         DBA.StairsRunJustification.Center)
    DBA.StairsLanding.CreateAutomaticLanding(doc, r1.Id, r2.Id)
    t.Commit()
    scope.Commit(_Quiet())
    return doc.GetElement(sid)


def build_support(type_name):
    """A foundation slab / floor of that type under the stair start, top at the base level."""
    from nosa_utils.revit_helpers import element_name
    from System.Collections.Generic import List
    level = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)[0]
    ftype = [t for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType) if element_name(t) == type_name][0]
    pts = [DB.XYZ(-1500 / _FT, -1000 / _FT, 0), DB.XYZ(1500 / _FT, -1000 / _FT, 0),
           DB.XYZ(1500 / _FT, 1000 / _FT, 0), DB.XYZ(-1500 / _FT, 1000 / _FT, 0)]
    loop = DB.CurveLoop()
    for a, b in zip(pts, pts[1:] + pts[:1]):
        loop.Append(DB.Line.CreateBound(a, b))
    t = DB.Transaction(doc, 'NOSA test - support')
    t.Start()
    floor = DB.Floor.Create(doc, List[DB.CurveLoop]([loop]), ftype.Id, level.Id)
    param = floor.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
    if param is not None and not param.IsReadOnly:
        param.Set(1)
    t.Commit()
    return floor


def solids_of(element):
    out = []
    for g in element.get_Geometry(DB.Options()):
        if isinstance(g, DB.Solid) and g.Volume > 0:
            out.append(g)
        elif isinstance(g, DB.GeometryInstance):
            out.extend(x for x in g.GetInstanceGeometry() if isinstance(x, DB.Solid) and x.Volume > 0)
    return out


def inside(solids, p):
    line = DB.Line.CreateBound(p - DB.XYZ(0, 0, 1.0 / _FT), p + DB.XYZ(0, 0, 1.0 / _FT))
    opts = DB.SolidCurveIntersectionOptions()
    opts.ResultType = DB.SolidCurveIntersectionMode.CurveSegmentsInside
    return any(s.IntersectWithCurve(line, opts).SegmentCount > 0 for s in solids)


_FT = 304.8
_failures = []


def _on_failures(sender, args):
    """Never let a Revit error dialog block the session: roll that transaction back and log it."""
    accessor = args.GetFailuresAccessor()
    errors = [f for f in accessor.GetFailureMessages() if f.GetSeverity() != DB.FailureSeverity.Warning]
    accessor.DeleteAllWarnings()
    if errors:
        _failures.append(u'{}: {}'.format(accessor.GetTransactionName(),
                                         u'; '.join(f.GetDescriptionText() for f in errors)))
        args.SetProcessingResult(DB.FailureProcessingResult.ProceedWithRollBack)


doc.Application.FailuresProcessing += _on_failures
group = None
try:
    if u'template' not in doc.Title and u'Project1' not in doc.Title and u'Rebar test' not in doc.Title:
        raise RuntimeError(u'not a test model: ' + doc.Title)
    from nosa_utils.bootstrap import load_module
    from nosa_utils import shared_params
    from nosa_utils.revit_helpers import get_id_value
    ra_lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
    ui = load_module('rebarautomate_ui', os.path.join(ra_lib, 'ui.py'))
    ui.forms.alert = lambda msg, *a, **k: _log.append(u'ALERT: ' + unicode(msg)) or True

    group = DB.TransactionGroup(doc, u'NOSA test - stairs end to end')
    group.Start()
    stairs = build_stairs()
    support = build_support(SUPPORT) if SUPPORT else None

    win = ui.RebarAutomateWindow(doc)
    win.Show = lambda: None
    win._is_loaded = True
    for name, value in json.loads(CONTROLS or '{}').items():
        control = getattr(win, name)
        if isinstance(value, bool):
            control.IsChecked = value
        else:
            control.Text = unicode(value)
    win._update_stair_preview()
    _log.append(u'preview children: {}  note: {}'.format(
        win.StairSectionCanvas.Children.Count, win.TxtStairPreviewNote.Text))
    values = win._read_stair_inputs()

    class _Ref(object):
        def __init__(self, eid):
            self.ElementId = eid

    class _Selection(object):
        def PickObjects(self, *args):
            return [_Ref(stairs.Id)]

    class _UIDoc(object):
        Document = doc
        Selection = _Selection()

    class _UIApp(object):
        ActiveUIDocument = _UIDoc()

    win._reinforcement_handler.pending = {'mode': 'stairs', 'values': values}
    win._reinforcement_handler.Execute(_UIApp())
    _log.append(u'RESULT:\n' + unicode(win.TxtStairResult.Text or u''))

    from Autodesk.Revit.DB.Structure import RebarHostData, MultiplanarOption
    rows = {}
    solids = []
    for eid in list(stairs.GetStairsRuns()) + list(stairs.GetStairsLandings()):
        solids.extend(solids_of(doc.GetElement(eid)))
    rebars = list(RebarHostData.GetRebarHostData(stairs).GetRebarsInHost())
    if support is not None:
        solids.extend(solids_of(support))
        rebars += list(RebarHostData.GetRebarHostData(support).GetRebarsInHost())
    for rebar in rebars:
        accessor = rebar.GetShapeDrivenAccessor()
        bad = 0
        for i in range(rebar.NumberOfBarPositions):
            xf = accessor.GetBarPositionTransform(i)
            for c in rebar.GetCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, i):
                c = c.CreateTransformed(xf)
                for p in (c.GetEndPoint(0), c.GetEndPoint(1), c.Evaluate(0.5, True)):
                    if not inside(solids, p):
                        bad += 1
        if bad:
            _log.append(u'OUTSIDE {} ({}): {} point(s)'.format(
                shared_params.read(rebar, u'NOSA_Rebar_Layer', u'?'), comments(rebar), bad))
        key = (shared_params.read(rebar, u'NOSA_Rebar_Layer', u'?'),
               comments(rebar),
               shared_params.read(rebar, u'NOSA_Rebar_Shape_Code', u'?'))
        rows.setdefault(key, []).append(u'{}x{}'.format(
            shared_params.read(rebar, u'NOSA_Rebar_Mark', u'?'), rebar.Quantity))
    for key in sorted(rows):
        _log.append(u'layer {} | loc {} | shape {} | marks {}'.format(key[0], key[1], key[2], rows[key]))
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
    sys.stdout = _old_stdout
    doc.Application.FailuresProcessing -= _on_failures
    _log.extend(u'FAILURE ' + f for f in _failures)

RESULT = u'\n'.join(_log) + u'\n--- console ---\n' + _console.getvalue()[-3000:]
