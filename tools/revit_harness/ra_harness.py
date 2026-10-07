# -*- coding: utf-8 -*-
"""
Headless RebarAutomate run, executed inside Revit through pyRevit's
IronPython engine (see run_ra.cs). Drives the plugin's real
Generate -> Select -> Apply path with the values last saved in the
window; only PickObjects and forms.alert are replaced.

Scope variables set by the launcher:
    doc        DB.Document
    MODE       'footings_floors' | 'columns' | 'beams' | 'walls' | 'stairs'
    IDS        list of element ids (int)
    CONTROLS   JSON {control name: bool | text} applied to the window first
    OVERRIDES  JSON string merged over the values read from the window
    EXT_ROOT   NOSA.extension folder to load the plugin from
    PYREVIT    pyRevit-Master folder
    ROLLBACK   optional bool: run inside a TransactionGroup and roll it back; Revit errors roll their
               transaction back instead of opening a dialog, and the new rebars per host are listed
    OUT        optional path: RESULT is also written there (runs longer than the 60 s call)
Result: RESULT (unicode).
"""
import sys
import os
import json
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)

from io import StringIO
_out = StringIO()
_old_stdout = sys.stdout
sys.stdout = _out
_log = []
_failures = []
try:
    _rollback = bool(ROLLBACK)
except NameError:
    _rollback = False


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
                ops.SetClearAfterRollback(True)
                self._rvtxn.SetFailureHandlingOptions(ops)
    revit.Transaction = Guarded
    return revit, original


group = None
revit_mod, original_tx = None, None
try:
    from nosa_utils.bootstrap import load_module
    from nosa_utils import shared_params
    from nosa_utils.revit_helpers import element_id_from_int, get_id_value
    from Autodesk.Revit.DB.Structure import RebarHostData
    ra_lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel',
                          'RebarAutomate.pushbutton', 'lib')
    ui = load_module('rebarautomate_ui', os.path.join(ra_lib, 'ui.py'))

    def _alert(msg, *args, **kwargs):
        _log.append(u'ALERT: ' + unicode(msg))
        return True
    ui.forms.alert = _alert

    # never annotate from the harness: a tag can raise a modal dialog (2026-09-30)
    ui.rebar_detailing.create_rebar_tags = lambda *a, **k: ([], [])
    ui.rebar_detailing.resolve_tag_overlaps = lambda *a, **k: None

    try:
        _trace_pins = DETAIL == 3
    except NameError:
        _trace_pins = False
    if _trace_pins:
        _pin = ui.re_engine.pin_rebar_to_host_faces

        def _describe(rebar, host):
            mgr = rebar.GetRebarConstraintsManager()
            rows = []
            for h in mgr.GetAllHandles():
                c = mgr.GetCurrentConstraintOnHandle(h)
                cands = []
                for cand in mgr.GetConstraintCandidatesForHandle(h, host.Id):
                    try:
                        cands.append(u'{}:{}:{:.0f}'.format(cand.GetConstraintType(), get_id_value(
                            cand.GetTargetHostFaceReference().ElementId), cand.GetDistanceToTargetHostFace() * 304.8))
                    except Exception:
                        cands.append(u'{}'.format(cand.GetConstraintType()))
                rows.append(u'{}={} [{}]'.format(h.GetHandleType(), c.GetConstraintType() if c else None, u' '.join(cands)))
            return u'; '.join(rows)

        def _traced(doc_, rebar, host, inset_mm, *a, **k):
            _log.append(u'PIN {} inset {:.1f} BEFORE {}'.format(get_id_value(rebar.Id), inset_mm, _describe(rebar, host)))
            n = _pin(doc_, rebar, host, inset_mm, *a, **k)
            _log.append(u'PIN {} -> {} AFTER {}'.format(get_id_value(rebar.Id), n, _describe(rebar, host)))
            return n
        ui.re_engine.pin_rebar_to_host_faces = _traced

    def _record(name, method):
        def wrapped(self, *args, **kwargs):
            result = method(self, *args, **kwargs)
            if self.last_error:     # failures the plugin may recover from silently (set -> bar by bar)
                _log.append(u'WRAPPER {} [{}] -> {}: {}'.format(name, kwargs.get('transaction_name', u''),
                                                                u'ok' if result is not None else u'None',
                                                                self.last_error))
                if result is None and len(args) > 1:
                    try:
                        for c in args[1]:
                            p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
                            _log.append(u'    ({:.0f},{:.0f},{:.0f}) -> ({:.0f},{:.0f},{:.0f})'.format(
                                p0.X * 304.8, p0.Y * 304.8, p0.Z * 304.8, p1.X * 304.8, p1.Y * 304.8, p1.Z * 304.8))
                        _log.append(u'    args {} kwargs {}'.format(args[3:], dict((k, v) for k, v in kwargs.items()
                                                                          if k != 'transaction_name')))
                    except Exception as e:
                        _log.append(u'    (curves not readable: {})'.format(e))
            return result
        return wrapped
    for _name in ('create_from_curves', 'create_rebar_set', 'create_rebar_set_fixed_number',
                  'create_freeform_group', 'create_from_shape', 'create_lapped_circle_set'):
        _m = getattr(ui.re_engine.RebarWrapper, _name, None)
        if _m is not None and not getattr(_m, '_nosa_recorded', False):
            _w = _record(_name, _m)
            _w._nosa_recorded = True
            setattr(ui.re_engine.RebarWrapper, _name, _w)

    def _host_rebars(eid):
        hd = RebarHostData.GetRebarHostData(doc.GetElement(element_id_from_int(eid)))
        return list(hd.GetRebarsInHost()) if hd is not None else []

    before = dict((i, set(get_id_value(r.Id) for r in _host_rebars(i))) for i in IDS)
    if _rollback:
        if u'template' not in doc.Title and u'Project' not in doc.Title and u'Rebar test' not in doc.Title:
            raise RuntimeError(u'not a test model: ' + doc.Title)
        revit_mod, original_tx = _guard_pyrevit_transactions()
        group = DB.TransactionGroup(doc, u'NOSA test - RebarAutomate')
        group.Start()
        try:
            pre_delete = list(PRE_DELETE)
        except NameError:
            pre_delete = []
        if pre_delete:     # e.g. rebars of an earlier run, rolled back with the rest
            t = DB.Transaction(doc, u'NOSA test - clear')
            t.Start()
            for i in pre_delete:
                doc.Delete(element_id_from_int(i))
            t.Commit()

    win = ui.RebarAutomateWindow(doc)
    win.Show = lambda: None
    win._is_loaded = True
    for name, value in json.loads(CONTROLS or '{}').items():
        control = getattr(win, name)
        if isinstance(value, bool):
            control.IsChecked = value
        else:
            control.Text = unicode(value)
    readers = {'footings_floors': win._read_inputs, 'columns': win._read_column_inputs,
               'beams': win._read_beam_inputs, 'walls': win._read_wall_inputs,
               'stairs': win._read_stair_inputs}
    values = readers[MODE]()
    if values is None:
        raise ValueError(u'window inputs rejected')
    values.update(json.loads(OVERRIDES or '{}'))

    class _Ref(object):
        def __init__(self, eid):
            self.ElementId = element_id_from_int(eid)

    class _Selection(object):
        def PickObjects(self, *args):
            return [_Ref(i) for i in IDS]

    class _UIDoc(object):
        Document = doc
        Selection = _Selection()

    class _UIApp(object):
        ActiveUIDocument = _UIDoc()

    win._reinforcement_handler.pending = {'mode': MODE, 'values': values}
    win._reinforcement_handler.Execute(_UIApp())
    result_box = {'footings_floors': 'TxtResult', 'columns': 'TxtColumnResult',
                  'beams': 'TxtBeamResult', 'walls': 'TxtWallResult', 'stairs': 'TxtStairResult'}[MODE]
    _log.append(u'RESULT:\n' + unicode(getattr(win, result_box).Text or u''))
    for i in IDS:
        layers = {}
        for r in _host_rebars(i):
            if get_id_value(r.Id) not in before[i]:
                layer = shared_params.read(r, u'NOSA_Rebar_Layer', u'?')
                layers[layer] = layers.get(layer, 0) + 1
                try:
                    detail = DETAIL
                except NameError:
                    detail = False
                if detail:
                    from Autodesk.Revit.DB.Structure import MultiplanarOption
                    pts = []
                    for k in range(r.NumberOfBarPositions):
                        for c in r.GetTransformedCenterlineCurves(False, False, False,
                                                                  MultiplanarOption.IncludeOnlyPlanarCurves, k):
                            pts.extend([c.GetEndPoint(0), c.GetEndPoint(1)])
                    if detail == 2:
                        mgr = r.GetRebarConstraintsManager()
                        for h in mgr.GetAllHandles():
                            c = mgr.GetCurrentConstraintOnHandle(h)
                            target = u''
                            try:
                                target = get_id_value(c.GetTargetHostFaceReference().ElementId)
                            except Exception:  # nosa-lint: disable=NOSA006 - no host face: left blank
                                pass
                            try:
                                dist = u'{:.1f}'.format(c.GetDistanceToTargetHostFace() * 304.8)
                            except Exception:
                                dist = u''
                            _log.append(u'    {} -> {} {} {}'.format(h.GetHandleType(), c.GetConstraintType() if c else None,
                                                                    target, dist))
                    try:
                        kind = u'freeform' if r.IsRebarFreeForm() else u'{}'.format(r.DistributionType)
                    except Exception:
                        kind = u'?'
                    try:
                        from nosa_utils.revit_helpers import element_name
                        kind += u' shape ' + element_name(doc.GetElement(r.GetShapeId()))
                    except Exception:
                        kind += u' multi-shape'
                    mark = u'{}{}'.format(
                        r.get_Parameter(DB.BuiltInParameter.REBAR_ELEM_SCHEDULE_MARK).AsString() or u'',  # nosa-lint: disable=NOSA002 - harness script, runs inside Revit
                        shared_params.read(r, u'NOSA_Rebar_Mark_Suffix', u'') or u'')
                    _log.append(u'  {} [{}] {} n{} x {:.0f}..{:.0f} y {:.0f}..{:.0f} z {:.0f}..{:.0f}'.format(
                        layer, kind, mark, r.NumberOfBarPositions, *[f(getattr(p, ax) for p in pts) * 304.8
                                                                for ax in ('X', 'Y', 'Z') for f in (min, max)]))
        _log.append(u'host {}: new rebars by layer {}'.format(i, sorted(layers.items())))
    try:
        bbs = BBS
    except NameError:
        bbs = None
    if bbs:     # the template's BBS as it reads now (before the rollback)
        view = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule) if v.Name == bbs][0]
        body = view.GetTableData().GetSectionData(DB.SectionType.Body)
        for row in range(body.NumberOfRows):
            _log.append(u'BBS ' + u'|'.join(u' '.join(view.GetCellText(DB.SectionType.Body, row, col).split())
                                             for col in range(body.NumberOfColumns)))
    try:
        win.Close()
    except Exception as e:
        _log.append(u'close: {}'.format(e))
except Exception:
    import traceback
    _log.append(u'EXCEPTION:\n' + unicode(traceback.format_exc()))
finally:
    if group is not None and group.HasStarted():
        group.RollBack()
        _log.append(u'rolled back')
    if revit_mod is not None:
        revit_mod.Transaction = original_tx
    sys.stdout = _old_stdout
    _log.extend(u'REVIT ERROR (rolled back): ' + f for f in _failures)

RESULT = u'\n'.join(_log) + u'\n--- console ---\n' + _out.getvalue()[-4000:]
try:
    import io as _io
    with _io.open(OUT, 'w', encoding='utf-8') as _fh:
        _fh.write(RESULT)
except NameError:  # nosa-lint: disable=NOSA006 - OUT not given
    pass
