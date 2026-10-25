# -*- coding: utf-8 -*-
"""
Four-storey building, end to end, in a new never-saved project only: pad foundations, columns, beams and slabs on
a 2 x 2 bay grid (6 m), a roof slab, a core wall each storey and a dog-leg concrete stair; then every RebarAutomate
command in construction order (bases, columns, beams, slabs, walls, stairs) through the real window path
(ra_harness.py), the drawings (ra_create_views.py), the documentation audit (ra_doc_audit.py) and a PDF of every
RC sheet. Scope: doc, EXT_ROOT, PYREVIT, OUT, OUTDIR; optional ONLY (kinds to reinforce, e.g. ['stairs']),
DRAWINGS (False: reinforcement only), DETAIL (ra_harness's), STOREYS. Result: RESULT (also written to OUT).
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
ONLY = globals().get('ONLY') or None
DRAWINGS = globals().get('DRAWINGS', True)


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
    grid = [i * BAY for i in range(3)]
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
        pts = [(-225, -225), (12225, -225), (12225, 12225), (-225, 12225)]
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
             'DETAIL': globals().get('DETAIL', False), '__name__': '__nosa_case__'}
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


_log = []
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
        text, secs = run(mode, ids[kind], controls)
        n, bars = rebar_count(ids[kind])
        issues = [l for l in text.split(u'\n') if l.strip() and not l.startswith(u'host ') and
                  u'RESULT' not in l and u'processed' not in l and u'created' not in l]
        _log.append(u'== {} ({} elements): {} rebar elements, {} bars, {:.0f} s'.format(kind, len(ids[kind]), n, bars,
                                                                                    secs))
        _log.extend(u'    ' + l[:400] for l in issues[:60])
    if DRAWINGS:
        scope = {'doc': doc, 'EXT_ROOT': EXT_ROOT, 'PYREVIT': PYREVIT, 'CLEAR': False, 'MODE': 'regenerate',
                 '__name__': '__nosa_views__'}
        t0 = time.time()
        try:
            execfile(os.path.join(EXT_ROOT, 'tools', 'revit_harness', 'ra_create_views.py'), scope)
            _log.append(u'== drawings {:.0f} s\n{}'.format(time.time() - t0, scope.get('RESULT', u'')))
        except Exception as e:
            _log.append(u'== drawings EXCEPTION {}'.format(e))
        if not os.path.isdir(OUTDIR):
            os.makedirs(OUTDIR)
        scope = {'doc': doc, 'OUTDIR': OUTDIR, '__name__': '__nosa_audit__'}
        try:
            execfile(os.path.join(EXT_ROOT, 'tools', 'revit_harness', 'ra_doc_audit.py'), scope)
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
                doc.Export(pdf_dir, List[DB.ElementId]([s.Id]), opts)
            except Exception as e:
                _log.append(u'pdf {} failed: {}'.format(s.SheetNumber, e))
        _log.append(u'== pdf: {} sheet(s) to {}'.format(len(sheets), pdf_dir))
    _log.append(u'total {:.0f} s'.format(time.time() - started))
except Exception:
    import traceback
    _log.append(traceback.format_exc())
finally:
    group.RollBack()

RESULT = u'Revit {}\n'.format(doc.Application.VersionNumber) + u'\n'.join(_log)
with io.open(OUT, 'w', encoding='utf-8') as fh:
    fh.write(RESULT)
