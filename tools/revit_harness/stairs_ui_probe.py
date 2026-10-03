# -*- coding: utf-8 -*-
"""
T7.8 end-to-end: build a dog-leg cast-in-place stair, run RebarAutomate's real Stairs GENERATE
(selection faked, alerts captured), report what was stamped, then roll EVERYTHING back (the
shared-parameter binding included). Scope: doc, EXT_ROOT, PYREVIT, CONTROLS (JSON). Result: RESULT.
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

    from Autodesk.Revit.DB.Structure import RebarHostData
    rows = {}
    for rebar in RebarHostData.GetRebarHostData(stairs).GetRebarsInHost():
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

RESULT = u'\n'.join(_log) + u'\n--- console ---\n' + _console.getvalue()[-3000:]
