# -*- coding: utf-8 -*-
"""
T7.6 end-to-end: one long wall, RebarAutomate's real Walls GENERATE (selection faked, alerts
captured) with a short stock length so both meshes are spliced, report every Set (start, end, count,
spacing) and where the laps fall, then roll EVERYTHING back. Scope: doc, EXT_ROOT, PYREVIT, CONTROLS.
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


def build_wall():
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
    wall_types = [w for w in DB.FilteredElementCollector(doc).OfClass(DB.WallType)
                  if w.Kind == DB.WallKind.Basic and 200.0 <= w.Width * _FT <= 400.0]
    t = DB.Transaction(doc, 'NOSA test - wall')
    t.Start()
    try:
        curved = CURVED
    except NameError:
        curved = False
    if curved:
        import math
        r = 6000.0 / _FT
        line = DB.Arc.Create(DB.XYZ(r, 0, 0), DB.XYZ(r * math.cos(2.0944), r * math.sin(2.0944), 0),
                             DB.XYZ(r * math.cos(1.0472), r * math.sin(1.0472), 0))
    else:
        line = DB.Line.CreateBound(DB.XYZ(0, 0, 0), DB.XYZ(9000.0 / _FT, 0, 0))
    wall = DB.Wall.Create(doc, line, wall_types[0].Id, levels[0].Id, 3000.0 / _FT, 0.0, False, True)
    t.Commit()
    return wall


group = None
revit_mod, original_tx = None, None
try:
    if u'template' not in doc.Title and u'Project1' not in doc.Title and u'Rebar test' not in doc.Title:
        raise RuntimeError(u'not a test model: ' + doc.Title)
    from nosa_utils.bootstrap import load_module
    from nosa_utils import shared_params
    from Autodesk.Revit.DB.Structure import RebarHostData, MultiplanarOption
    revit_mod, original_tx = _guard_pyrevit_transactions()
    ra_lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
    ui = load_module('rebarautomate_ui', os.path.join(ra_lib, 'ui.py'))
    ui.forms.alert = lambda msg, *a, **k: _log.append(u'ALERT: ' + unicode(msg)) or True

    group = DB.TransactionGroup(doc, u'NOSA test - wall stagger')
    group.Start()
    wall = build_wall()
    _log.append(u'wall {:.0f} thick, valid host {}'.format(wall.Width * _FT, RebarHostData.IsValidHost(wall)))

    win = ui.RebarAutomateWindow(doc)
    win.Show = lambda: None
    win._is_loaded = True
    for name, value in json.loads(CONTROLS or '{}').items():
        control = getattr(win, name)
        if isinstance(value, bool):
            control.IsChecked = value
        else:
            control.Text = unicode(value)
    values = win._read_wall_inputs()

    class _Ref(object):
        def __init__(self, eid):
            self.ElementId = eid

    class _Selection(object):
        def PickObjects(self, *args):
            return [_Ref(wall.Id)]

    class _UIDoc(object):
        Document = doc
        Selection = _Selection()

    class _UIApp(object):
        ActiveUIDocument = _UIDoc()

    win._reinforcement_handler.pending = {'mode': 'walls', 'values': values}
    win._reinforcement_handler.Execute(_UIApp())
    _log.append(u'RESULT:\n' + unicode(win.TxtWallResult.Text or u''))

    for rebar in RebarHostData.GetRebarHostData(wall).GetRebarsInHost():
        layer = shared_params.read(rebar, u'NOSA_Rebar_Layer', u'?')
        firsts, lasts = [], []
        for i in range(rebar.NumberOfBarPositions):
            pts = []
            for c in rebar.GetTransformedCenterlineCurves(False, False, False,
                                                          MultiplanarOption.IncludeOnlyPlanarCurves, i):
                pts.extend([c.GetEndPoint(0), c.GetEndPoint(1)])
            firsts.append(pts[0])
            lasts.append(pts[-1])
        p0, p1 = firsts[0], lasts[0]
        if rebar.IsRebarFreeForm():
            radii = sorted(set(round((p.X * p.X + p.Y * p.Y) ** 0.5 * _FT) for p in firsts))
            _log.append(u'{}: FREEFORM n{} radii {} z {:.0f}..{:.0f}'.format(
                layer, rebar.NumberOfBarPositions, radii, min(p.Z for p in firsts) * _FT,
                max(p.Z for p in lasts) * _FT))
            continue
        q = firsts[-1]
        _log.append(u'{}: n{} bar0 ({:.0f},{:.0f},{:.0f})->({:.0f},{:.0f},{:.0f}) len {:.0f} | last bar at '
                    u'({:.0f},{:.0f},{:.0f})'.format(layer, rebar.NumberOfBarPositions, p0.X * _FT, p0.Y * _FT,
                                                     p0.Z * _FT, p1.X * _FT, p1.Y * _FT, p1.Z * _FT,
                                                     p0.DistanceTo(p1) * _FT, q.X * _FT, q.Y * _FT, q.Z * _FT))
    try:
        modify = MODIFY
    except NameError:
        modify = False
    if modify:
        # T7.7: split the horizontal sets to a shorter stock, show as solids, delete the host's bars
        from System.Collections.Generic import List
        from nosa_utils.revit_helpers import get_id_value
        horizontal = [r for r in RebarHostData.GetRebarHostData(wall).GetRebarsInHost()
                      if shared_params.read(r, u'NOSA_Rebar_Layer', u'') == u'horizontal']
        win.uidoc.Selection.SetElementIds(List[DB.ElementId]([r.Id for r in horizontal]))
        win.TxtModifyStockLength.Text = u'4000'
        win._split_selected()
        _log.append(u'SPLIT: ' + unicode(win.TxtDetailingStatus.Text))
        for rebar in RebarHostData.GetRebarHostData(wall).GetRebarsInHost():
            if shared_params.read(rebar, u'NOSA_Rebar_Layer', u'') != u'horizontal':
                continue
            pts = []
            for c in rebar.GetTransformedCenterlineCurves(False, False, False,
                                                          MultiplanarOption.IncludeOnlyPlanarCurves, 0):
                pts.extend([c.GetEndPoint(0), c.GetEndPoint(1)])
            last = list(rebar.GetTransformedCenterlineCurves(
                False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, rebar.NumberOfBarPositions - 1))
            _log.append(u'  split {} n{} x {:.0f}..{:.0f} y {:.0f} z {:.0f}..{:.0f} mark {}'.format(
                get_id_value(rebar.Id), rebar.NumberOfBarPositions, pts[0].X * _FT, pts[-1].X * _FT,
                pts[0].Y * _FT, pts[0].Z * _FT, last[0].GetEndPoint(0).Z * _FT,
                shared_params.read(rebar, u'NOSA_Rebar_Mark', u'?')))
        view3d = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.View3D) if not v.IsTemplate][0]
        rebar_modify = ui.rebar_modify
        bars = rebar_modify.host_rebars(doc, [wall])
        t = DB.Transaction(doc, 'NOSA test - solids')
        t.Start()
        state = [rebar_modify.toggle_solids(view3d, bars), rebar_modify.toggle_solids(view3d, bars)]
        t.Commit()
        _log.append(u'SOLIDS toggled in "{}": {}'.format(view3d.Name, state))
        win.uidoc.Selection.SetElementIds(List[DB.ElementId]([wall.Id]))
        win._delete_host_rebars()
        _log.append(u'DELETE: {} | left in host {}'.format(
            win.TxtDetailingStatus.Text, len(list(RebarHostData.GetRebarHostData(wall).GetRebarsInHost()))))

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
