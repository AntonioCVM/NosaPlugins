# -*- coding: utf-8 -*-
"""
Four-storey building, end to end, in a new never-saved project only: pad foundations, columns, beams and slabs on
a 2 x 2 bay grid (6 m), a roof slab, a core wall each storey and a dog-leg concrete stair; then every RebarAutomate
command in construction order (bases, columns, beams, slabs, walls, stairs) through the real window path
(ra_harness.py), the drawings (ra_create_views.py), the documentation audit (ra_doc_audit.py) and a PDF of every
RC sheet. Scope: doc, EXT_ROOT, PYREVIT, OUT, OUTDIR; optional ONLY (kinds to reinforce, e.g. ['stairs']),
DRAWINGS (False: reinforcement only), DETAIL (ra_harness's), STOREYS, GRID, PROFILE (True: the drawing
modules' functions timed, the slowest listed). Result: RESULT (also written to OUT).
"""
import io
import json
import os
import re
import time

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Architecture as DBA
from Autodesk.Revit.DB import Structure as DBS
from System.Collections.Generic import List

if doc.PathName or not re.match(u'^Project[0-9]+$', doc.Title):      # a new, never saved project only
    raise RuntimeError(u'not the unsaved test project: ' + doc.Title)

_MM = 304.8
X0 = 400000.0
BAY = 6000.0
STOREYS = globals().get('STOREYS') or 4
GRID = globals().get('GRID') or 3            # grid lines each way (3: 2 x 2 bays)
ONLY = globals().get('ONLY') or None
DRAWINGS = globals().get('DRAWINGS', True)
PROFILE = globals().get('PROFILE', False)
QA = globals().get('QA', True)
DRAWING_QA = globals().get('DRAWING_QA', True)
ON_UI = globals().get('ON_UI')                       # callable(ui) run on the modules each reinforcement loads
PROBE = globals().get('PROBE')                       # a script run on the reinforced building (scope: doc, ids, _log, _mem)      # False: the drawings' buildability grade left out (measuring)
_TIMES = {}


def _profiled(modules):
    """Every function of the modules timed (inclusive, calls counted) into _TIMES."""
    import types

    def wrap(mod, name, fn):
        key = u'{}.{}'.format(mod.__name__, name)

        def timed(*a, **k):
            t0 = time.time()
            try:
                return fn(*a, **k)
            finally:
                entry = _TIMES.setdefault(key, [0.0, 0])
                entry[0] += time.time() - t0
                entry[1] += 1
        return timed
    for mod in modules:
        for name, fn in list(vars(mod).items()):
            if isinstance(fn, types.FunctionType) and fn.__module__ == mod.__name__:
                setattr(mod, name, wrap(mod, name, fn))


def f(mm):
    return mm / _MM


def xyz(x, y, z=0.0):
    return DB.XYZ(f(X0 + x), f(y), f(z))


def name_of(e):
    return DB.Element.Name.GetValue(e)


def symbol(category, family, name=None):
    for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(category):
        if s.FamilyName == family and (name is None or name_of(s) == name):
            if not s.IsActive:
                s.Activate()
            return s
    raise RuntimeError(u'no {} {}'.format(family, name or u''))


class _Quiet(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, accessor):
        for fm in accessor.GetFailureMessages():
            if fm.GetSeverity() == DB.FailureSeverity.Warning:
                accessor.DeleteWarning(fm)
        return DB.FailureProcessingResult.Continue


def _quiet(t):
    ops = t.GetFailureHandlingOptions()
    ops.SetFailuresPreprocessor(_Quiet())
    t.SetFailureHandlingOptions(ops)


def levels_and_plans():
    existing = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
    ground = existing[0]
    storey = (existing[1].Elevation - ground.Elevation) * _MM if len(existing) > 1 else 3500.0
    plan_type = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                 if v.ViewFamily == DB.ViewFamily.StructuralPlan][0]
    out = [ground]
    for k in range(1, STOREYS + 1):
        z = ground.Elevation + f(storey * k)
        lv = [l for l in existing if abs(l.Elevation - z) < f(1.0)]
        if lv:
            out.append(lv[0])
            continue
        new = DB.Level.Create(doc, z)
        new.Name = u'Roof' if k == STOREYS else u'Level {}'.format(k)
        DB.ViewPlan.Create(doc, plan_type.Id, new.Id)
        out.append(new)
    return out, storey


def build():
    sq = symbol(DB.BuiltInCategory.OST_StructuralColumns, u'Concrete Square', u'450x450mm')
    beam = symbol(DB.BuiltInCategory.OST_StructuralFraming, u'RC Beam', u'300x600mm')
    pad = symbol(DB.BuiltInCategory.OST_StructuralFoundation, u'RC Pad foundation')
    ftype = [x for x in DB.FilteredElementCollector(doc).OfClass(DB.FloorType)
             if name_of(x).startswith(u'300mm RC')][0]
    wtype = [w for w in DB.FilteredElementCollector(doc).OfClass(DB.WallType) if name_of(w) == u'300mm RC Wall'][0]
    t = DB.Transaction(doc, u'NOSA building test - frame')
    t.Start()
    _quiet(t)
    lv, storey = levels_and_plans()
    grid = [i * BAY for i in range(GRID)]
    ids = {'bases': [], 'columns': [], 'beams': [], 'slabs': [], 'walls': []}
    for x in grid:
        for y in grid:
            ids['bases'].append(doc.Create.NewFamilyInstance(xyz(x, y, -500), pad, lv[0],
                                                             DBS.StructuralType.Footing).Id)
            for k in range(STOREYS):
                c = doc.Create.NewFamilyInstance(xyz(x, y, lv[k].Elevation * _MM), sq, lv[k], DBS.StructuralType.Column)
                c.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(lv[k + 1].Id)
                ids['columns'].append(c.Id)
    for k in range(1, STOREYS + 1):
        z = lv[k].Elevation * _MM
        for a in grid:
            for b0, b1 in zip(grid, grid[1:]):
                for p, q in ((xyz(b0, a, z), xyz(b1, a, z)), (xyz(a, b0, z), xyz(a, b1, z))):
                    ids['beams'].append(doc.Create.NewFamilyInstance(DB.Line.CreateBound(p, q), beam, lv[k],
                                                                     DBS.StructuralType.Beam).Id)
        cl = DB.CurveLoop()
        edge = grid[-1] + 225 if len(grid) > 1 else 1500
        pts = [(-225, -225), (edge, -225), (edge, edge), (-225, edge)]
        for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
            cl.Append(DB.Line.CreateBound(xyz(ax, ay, z), xyz(bx, by, z)))
        fl = DB.Floor.Create(doc, List[DB.CurveLoop]([cl]), ftype.Id, lv[k].Id)
        fl.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL).Set(1)
        ids['slabs'].append(fl.Id)
        w = DB.Wall.Create(doc, DB.Line.CreateBound(xyz(-3000, 0, z - storey), xyz(-3000, 6000, z - storey)),
                           wtype.Id, lv[k - 1].Id, f(storey), 0.0, False, True)
        ids['walls'].append(w.Id)
    t.Commit()
    ids['stairs'] = []
    try:
        cip = [s for s in DB.FilteredElementCollector(doc).OfClass(DBA.StairsType) if name_of(s) == u'Concrete Stair'][0]
        scope = DB.StairsEditScope(doc, u'NOSA building test - stair')
        sid = scope.Start(lv[0].Id, lv[1].Id)
        ts = DB.Transaction(doc, u'NOSA building test - stair runs')
        ts.Start()
        doc.GetElement(sid).ChangeTypeId(cip.Id)
        r1 = DBA.StairsRun.CreateStraightRun(doc, sid, DB.Line.CreateBound(xyz(16000, 0), xyz(16000 + 2438.4, 0)),
                                             DBA.StairsRunJustification.Center)
        zt = r1.TopElevation
        r2 = DBA.StairsRun.CreateStraightRun(
            doc, sid, DB.Line.CreateBound(DB.XYZ(f(X0 + 16000 + 2438.4), f(1524), zt), DB.XYZ(f(X0 + 16000), f(1524), zt)),
            DBA.StairsRunJustification.Center)
        DBA.StairsLanding.CreateAutomaticLanding(doc, r1.Id, r2.Id)
        ts.Commit()
        scope.Commit(_Quiet())
        ids['stairs'].append(sid)
    except Exception as e:
        _log.append(u'stair not built: {}'.format(e))
    return ids


def ints(eids):
    return [e.Value if hasattr(e, 'Value') else e.IntegerValue for e in eids]


def run(mode, eids, controls):
    scope = {'doc': doc, 'MODE': mode, 'IDS': ints(eids), 'CONTROLS': json.dumps(controls), 'OVERRIDES': u'{}',
             'EXT_ROOT': EXT_ROOT, 'PYREVIT': PYREVIT, 'ROLLBACK': True, 'ASSIMILATE': True,
             'DETAIL': globals().get('DETAIL', False), 'ON_UI': ON_UI, '__name__': '__nosa_case__'}
    t0 = time.time()
    try:
        execfile(os.path.join(EXT_ROOT, 'tools', 'revit_harness', 'ra_harness.py'), scope)
        text = scope.get('RESULT', u'')
    except Exception as e:
        text = u'EXCEPTION {}'.format(e)
    return text, time.time() - t0


def rebar_count(eids):
    n = bars = 0
    for eid in eids:
        hd = DBS.RebarHostData.GetRebarHostData(doc.GetElement(eid))
        if hd is None:
            continue
        for r in hd.GetRebarsInHost():
            n += 1
            bars += r.Quantity
    return n, bars


def _mem():
    """(private GB, working set GB) of this Revit process."""
    for name in ('System.Diagnostics.Process', 'System'):         # .NET 8 (Revit 2025+) / Framework
        try:
            clr.AddReference(name)
        except Exception:
            continue
    from System.Diagnostics import Process
    p = Process.GetCurrentProcess()
    p.Refresh()
    return p.PrivateMemorySize64 / 1073741824.0, p.WorkingSet64 / 1073741824.0


LIVE_PHASES = set()   # phases whose every call is written to OUT.progress as it starts and ends


def _progress(line):
    try:
        with io.open(OUT + u'.progress', 'a', encoding='utf-8') as fh:
            fh.write(u'{} {}\n'.format(time.strftime('%H:%M:%S'), line))
    except Exception:
        pass


MEMORY = []          # [(phase, start private, end private, end working set, seconds, calls)]
_PHASES = {}


def _phase(name, fn):
    """fn wrapped: the memory before and after every call added up under name."""
    def wrapped(*a, **k):
        p0, _w0 = _mem()
        t0 = time.time()
        live = name in LIVE_PHASES
        if live:
            _progress(u'   > {} ({:.2f} GB)'.format(name, p0))
        try:
            return fn(*a, **k)
        finally:
            p1, w1 = _mem()
            if live:
                _progress(u'   < {} ({:.2f} GB, {:+.2f}, {:.0f} s)'.format(name, p1, p1 - p0, time.time() - t0))
            entry = _PHASES.setdefault(name, [p0, p1, w1, 0.0, 0, 0.0])
            entry[1], entry[2] = p1, w1
            entry[3] += time.time() - t0
            entry[4] += 1
            entry[5] += p1 - p0
    return wrapped


class _Log(list):
    """The report, each line also appended at once to OUT.progress (a run that dies still says how far it got)."""

    def append(self, line):
        list.append(self, line)
        try:
            with io.open(OUT + u'.progress', 'a', encoding='utf-8') as fh:
                fh.write(u'{} {:5.2f}GB {}\n'.format(time.strftime('%H:%M:%S'), _mem()[0],
                                                       line.split(u'\n')[0][:200]))
        except Exception:
            pass


_log = _Log()
started = time.time()
group = DB.TransactionGroup(doc, u'NOSA building test')
group.Start()
try:
    ids = build()
    _log.append(u'built {}'.format(u', '.join(u'{} {}'.format(len(v), k) for k, v in sorted(ids.items()))))
    steps = [('bases', 'footings_floors', {u'ChkIncludeDowels': True}),
             ('columns', 'columns', {u'ChkColFoundationStarters': True}),
             ('beams', 'beams', {}),
             ('slabs', 'footings_floors', {u'ChkIncludeTopMat': True, u'ChkAlternateBottom': True,
                                           u'ChkStaggerLaps': True, u'ChkIncludePerimeterUBars': True}),
             ('walls', 'walls', {}),
             ('stairs', 'stairs', {})]
    for kind, mode, controls in steps:
        if not ids[kind] or (ONLY and kind not in ONLY):
            continue
        _log.append(u'-- start {}'.format(kind))
        text, secs = _phase(u'reinforce ' + kind, run)(mode, ids[kind], controls)
        n, bars = rebar_count(ids[kind])
        issues = [l for l in text.split(u'\n') if l.strip() and not l.startswith(u'host ') and
                  u'RESULT' not in l and u'processed' not in l and u'created' not in l]
        _log.append(u'== {} ({} elements): {} rebar elements, {} bars, {:.0f} s'.format(kind, len(ids[kind]), n, bars,
                                                                                    secs))
        _log.extend(u'    ' + l[:400] for l in issues[:60])
    if PROBE:
        probe_scope = {'doc': doc, 'ids': ids, '_log': _log, '_mem': _mem, 'EXT_ROOT': EXT_ROOT, 'OUT': OUT,
                       '__name__': '__nosa_probe__'}
        try:
            execfile(PROBE, probe_scope)
        except Exception:
            import traceback
            _log.append(u'== PROBE EXCEPTION ' + traceback.format_exc())
    try:
        if not QA:
            raise StopIteration
        from nosa_utils import rebar_qa
        _log.append(u'-- start QA')
        t0 = time.time()
        found = _phase(u'QA rebar_qa.audit (whole building)', rebar_qa.audit)(doc, [i for k in ('bases', 'columns', 'beams', 'slabs', 'walls', 'stairs')
                                     for i in ids[k]])
        groups = {}
        for fd in found:
            key = (fd.Severity, fd.Check, re.sub(u'[0-9]+', u'n', fd.Issue or u'')[:150])
            groups.setdefault(key, []).append(fd)
        _log.append(u'== QA: {} finding(s) in {:.0f} s'.format(len(found), time.time() - t0))
        for (sev, check, issue), fds in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:30]:
            _log.append(u'    {:4d} {} | {} | {} | e.g. {} {}'.format(len(fds), sev, check, issue, fds[0].Host,
                                                                   fds[0].Mark))
    except StopIteration:
        pass
    except Exception as e:
        _log.append(u'== QA EXCEPTION {}'.format(e))
    if DRAWINGS and PROFILE:
        import sys
        ra_lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
        if ra_lib not in sys.path:
            sys.path.insert(0, ra_lib)
        import rebar_views, rebar_presentation, view_plan, rc_legends, bar_schedules, drawing_audit
        from nosa_utils import callout_layout, presentation
        _profiled([rebar_views, rebar_presentation, view_plan, rc_legends, bar_schedules, drawing_audit,
                   callout_layout, presentation])
    if DRAWINGS:
        import sys
        ra_lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
        if ra_lib not in sys.path:
            sys.path.insert(0, ra_lib)
        def on_modules(_rv):
            # the rebar_views module ui has just loaded (it loads its own copy, so wrap that one)
            for _name, _label in (('build_element_views', u'views + annotation (build_element_views)'),
                                  ('_place_group', u'sheets + viewports + notes (_place_group)'),
                                  ('_buildability', u'QA per drawing (_buildability)'),
                                  ('issue_schedules', u'BBS (issue_schedules)'),
                                  ('review_drawings', u'drawing review (review_drawings)')):
                setattr(_rv, _name, _phase(_label, getattr(_rv, _name)))
            if not DRAWING_QA:
                _rv._buildability = lambda *a, **k: None
        import rebar_presentation as _rp
        _rp.apply = _phase(u'annotation (rebar_presentation.apply)', _rp.apply)
        from nosa_utils import rebar_qa as _qa
        _qa.congested_stations = _phase(u'congested stations (rebar_qa)', _qa.congested_stations)
        _qa.audit = _phase(u'rebar_qa.audit (in drawings)', _qa.audit)
        LIVE_PHASES.update([u'views + annotation (build_element_views)', u'sheets + viewports + notes (_place_group)',
                            u'BBS (issue_schedules)', u'drawing review (review_drawings)',
                            u'rebar_qa.audit (in drawings)'])
        _log.append(u'-- start drawings')
        scope = {'doc': doc, 'EXT_ROOT': EXT_ROOT, 'PYREVIT': PYREVIT, 'CLEAR': False, 'MODE': 'regenerate',
                 'ON_MODULES': on_modules, '__name__': '__nosa_views__'}
        t0 = time.time()
        try:
            _phase(u'drawings, all (Create Views)', execfile)(
                os.path.join(EXT_ROOT, 'tools', 'revit_harness', 'ra_create_views.py'), scope)
            _log.append(u'== drawings {:.0f} s\n{}'.format(time.time() - t0, scope.get('RESULT', u'')))
        except Exception as e:
            _log.append(u'== drawings EXCEPTION {}'.format(e))
        if not os.path.isdir(OUTDIR):
            os.makedirs(OUTDIR)
        scope = {'doc': doc, 'OUTDIR': OUTDIR, '__name__': '__nosa_audit__'}
        try:
            _phase(u'documentation audit + BBS CSV', execfile)(
                os.path.join(EXT_ROOT, 'tools', 'revit_harness', 'ra_doc_audit.py'), scope)
            _log.append(u'== audit ' + scope.get('RESULT', u''))
        except Exception as e:
            _log.append(u'== audit EXCEPTION {}'.format(e))
        sheets = [s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)
                  if s.SheetNumber[:1] == u'4' or s.SheetNumber[:2] == u'55']
        pdf_dir = os.path.join(OUTDIR, u'pdf')
        if not os.path.isdir(pdf_dir):
            os.makedirs(pdf_dir)
        for s in sheets:
            try:
                opts = DB.PDFExportOptions()
                opts.FileName = u'{} - {}'.format(s.SheetNumber, re.sub(u'[\\\\/:*?"<>|]', u'_', s.Name))
                _phase(u'PDF export', doc.Export)(pdf_dir, List[DB.ElementId]([s.Id]), opts)
            except Exception as e:
                _log.append(u'pdf {} failed: {}'.format(s.SheetNumber, e))
        _log.append(u'== pdf: {} sheet(s) to {}'.format(len(sheets), pdf_dir))
    if _TIMES:
        _log.append(u'== slowest functions (inclusive s, calls)')
        for key, (secs, calls) in sorted(_TIMES.items(), key=lambda kv: -kv[1][0])[:40]:
            _log.append(u'    {:8.1f} {:7d}  {}'.format(secs, calls, key))
    _log.append(u'== memory by phase (GB private: first start, last end, sum of increases; working set at end)')
    for name, (p0, p1, w1, secs, calls, grown) in sorted(_PHASES.items(), key=lambda kv: kv[1][0]):
        _log.append(u'    {:<48} start {:6.2f} end {:6.2f} grown {:+6.2f} ws {:6.2f}  {:7.0f} s  {:4d} call(s)'.format(
            name, p0, p1, grown, w1, secs, calls))
    _log.append(u'total {:.0f} s'.format(time.time() - started))
except Exception:
    import traceback
    _log.append(traceback.format_exc())
finally:
    group.RollBack()

RESULT = u'Revit {}\n'.format(doc.Application.VersionNumber) + u'\n'.join(_log)
with io.open(OUT, 'w', encoding='utf-8') as fh:
    fh.write(RESULT)
