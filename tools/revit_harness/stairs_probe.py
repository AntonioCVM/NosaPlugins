# -*- coding: utf-8 -*-
"""T7.8 probe: build a dog-leg cast-in-place stair, reinforce it, check every bar vertex lies in the
concrete; everything rolled back. Scope: doc, EXT_ROOT, PYREVIT, STAIRS_ID (0 = build one). Result: RESULT."""
import sys
import os
import traceback
import __builtin__

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
_out = []
_FT = 304.8


class _Quiet(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, accessor):
        for f in accessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                accessor.DeleteWarning(f)
        return DB.FailureProcessingResult.Continue


def build_stairs():
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
    from nosa_utils.revit_helpers import element_name
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
    try:
        shape = SHAPE
    except NameError:
        shape = 'U'
    if shape == 'L':
        r2 = DBA.StairsRun.CreateStraightRun(doc, sid, DB.Line.CreateBound(DB.XYZ(10, 2, z), DB.XYZ(10, 10, z)),
                                             DBA.StairsRunJustification.Center)
    else:
        r2 = DBA.StairsRun.CreateStraightRun(doc, sid, DB.Line.CreateBound(DB.XYZ(8, 5, z), DB.XYZ(0, 5, z)),
                                             DBA.StairsRunJustification.Center)
    DBA.StairsLanding.CreateAutomaticLanding(doc, r1.Id, r2.Id)
    t.Commit()
    scope.Commit(_Quiet())
    return doc.GetElement(sid)


def solids_of(stairs):
    out = []
    for g in stairs.get_Geometry(DB.Options()):
        if isinstance(g, DB.Solid) and g.Volume > 0:
            out.append(g)
    return out


def inside(solids, p):
    line = DB.Line.CreateBound(p - DB.XYZ(0, 0, 1.0 / _FT), p + DB.XYZ(0, 0, 1.0 / _FT))
    opts = DB.SolidCurveIntersectionOptions()
    opts.ResultType = DB.SolidCurveIntersectionMode.CurveSegmentsInside
    for s in solids:
        if s.IntersectWithCurve(line, opts).SegmentCount > 0:
            return True
    return False


group = None
try:
    if u'template' not in doc.Title and u'Project1' not in doc.Title and u'Rebar test' not in doc.Title:
        raise RuntimeError(u'not a test model: ' + doc.Title)
    from nosa_utils.bootstrap import load_module
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
    if lib not in sys.path:
        sys.path.insert(0, lib)
    re_engine = load_module('re_engine', os.path.join(lib, 'rebar_engine.py'))
    stair_rebar = load_module('stair_rebar', os.path.join(lib, 'stair_rebar.py'))
    stair_host = load_module('stair_host', os.path.join(lib, 'stair_host.py'))

    group = DB.TransactionGroup(doc, u'NOSA test - stairs')
    group.Start()
    stairs = build_stairs()
    data = stair_host.read_stairs(doc, stairs)
    _out.append(u'warnings: {}'.format(data['warnings']))
    for r in data['runs']:
        _out.append(u'run L {:.0f} slope {:.4f} soffit_z0 {:.0f} pitch_z0 {:.0f} v {:.0f}..{:.0f} lower {} {:.0f}/{:.0f} far {:.0f} upper {} {:.0f} far {:.0f}'.format(
            r['length'], r['slope'], r['soffit_z0'], r['pitch_z0'], r['v_min'], r['v_max'],
            r['lower']['kind'], r['lower']['top'], r['lower']['bottom'], r['lower']['s_far'],
            r['upper']['kind'], r['upper']['top'], r['upper']['s_far']))
    for l in data['landings']:
        _out.append(u'landing s {:.0f}..{:.0f} v {:.0f}..{:.0f} top {:.0f} bottom {:.0f} strips {} parallel {}'.format(
            l['s_min'], l['s_max'], l['v_min'], l['v_max'], l['top'], l['bottom'], l['strips'], l['parallel']))

    cover = 40.0
    wrapper = re_engine.RebarWrapper(doc)
    bar_types = {12.0: re_engine.get_bar_type_by_diameter(doc, 12.0),
                 8.0: re_engine.get_bar_type_by_diameter(doc, 8.0)}
    jobs = []
    for r in data['runs']:
        for st in stair_rebar.build_flight(r, cover, 12.0, 200.0, 8.0, 200.0, anchorage=480.0):
            jobs.append((r['frame'], st))
    for l in data['landings']:
        for st in stair_rebar.build_landing(l, cover, 12.0, 8.0, 200.0, 200.0, l['strips'], l['parallel']):
            jobs.append((l['frame'], st))
    solids = []
    for eid in list(stairs.GetStairsRuns()) + list(stairs.GetStairsLandings()):
        solids.extend(stair_host._solids(doc.GetElement(eid)))
    probe = DB.XYZ(1000 / _FT, 0, 300 / _FT)
    _out.append(u'solids {} volumes {} inside(1000,0,300) {}'.format(
        len(solids), [round(x.Volume * 0.0283168, 3) for x in solids], inside(solids, probe)))
    created = failed = outside = 0
    positions = {}
    for frame, st in jobs:
        rebar = stair_host.create_set(wrapper, stairs, frame, st, bar_types[st['dia']])
        if rebar is None:
            failed += 1
            _out.append(u'FAIL {}: {}'.format(st['label'], wrapper.last_error))
            continue
        created += 1
        bad = []
        n = rebar.NumberOfBarPositions
        accessor = rebar.GetShapeDrivenAccessor()

        def bar_curves(i):
            xf = accessor.GetBarPositionTransform(i)
            return [c.CreateTransformed(xf) for c in rebar.GetCenterlineCurves(
                False, False, False, DB.Structure.MultiplanarOption.IncludeOnlyPlanarCurves, i)]
        for i in range(n):
            for c in bar_curves(i):
                for p in (c.GetEndPoint(0), c.GetEndPoint(1), c.Evaluate(0.5, True)):
                    if not inside(solids, p):
                        bad.append(p)
        if st['axis'] == 'v':
            positions[st['label'] + str(id(frame))] = sorted(
                round(frame.local(bar_curves(i)[0].GetEndPoint(0))[1]) for i in range(n))
        if bad:
            outside += 1
            p = bad[0]
            _out.append(u'OUTSIDE {} ({} bars): {} point(s), first ({:.0f}, {:.0f}, {:.0f})'.format(
                st['label'], n, len(bad), p.X * _FT, p.Y * _FT, p.Z * _FT))
        else:
            _out.append(u'ok {} — {} bar(s)'.format(st['label'], n))
    for key in sorted(positions):
        _out.append(u'v {}: {}'.format(key.split('<')[0][:40], positions[key]))
    _out.append(u'created {} failed {} sets with points outside {}'.format(created, failed, outside))
    group.RollBack()
    group = None
except Exception:
    _out.append(traceback.format_exc())
finally:
    if group is not None and group.HasStarted():
        group.RollBack()
RESULT = u'\n'.join(_out)
