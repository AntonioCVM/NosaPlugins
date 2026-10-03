# -*- coding: utf-8 -*-
"""
T7.2 end-to-end: 4 columns and 3 beams in a line, RebarAutomate's real Beams GENERATE with
"Continuous beam" ticked (selection faked, alerts captured), report the bars by layer and their
reach along the line, then roll EVERYTHING back. Revit errors roll their transaction back
instead of opening a dialog (harness only). Scope: doc, EXT_ROOT, PYREVIT, CONTROLS. Result: RESULT.
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
            try:
                if not DB.JoinGeometryUtils.AreElementsJoined(doc, c, bm):
                    DB.JoinGeometryUtils.JoinGeometry(doc, c, bm)
                if not DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, c, bm):
                    DB.JoinGeometryUtils.SwitchJoinOrder(doc, c, bm)
            except Exception:
                pass  # nosa-lint: disable=NOSA006 - not touching: nothing to join
    t.Commit()
    return columns, beams


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
