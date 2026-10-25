# -*- coding: utf-8 -*-
"""
T8.57 scripted reinforcement test model: in the unsaved test project only, one rolled-back group builds every
typology and shape the plugin claims (rectangular and circular columns; straight, inclined and curved beams over
columns; rectangular slab with an opening, L-shaped slab, slab with a curved edge; straight wall with an opening,
curved wall; pad foundation, pile cap), reinforces each through RebarAutomate's real path (ra_harness.py, one
element at a time so a failure is pinned to its case) and reports what each case made and every Revit error.
Run in each Revit version before a merge (extends T8.2). Scope: doc, EXT_ROOT, PYREVIT, OUT, ONLY (optional: case labels to run), FULL (optional: each case's whole
harness report). Result: RESULT.
"""
import io
import math
import os
import time

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS

import re
if doc.PathName or not re.match(u'^Project[0-9]+$', doc.Title):      # a new, never saved project only
    raise RuntimeError(u'not the unsaved test project: ' + doc.Title)

_MM = 304.8
X0 = 400000.0                      # far from anything in the test project


def f(mm):
    return mm / _MM


def xyz(x, y, z=0.0):
    return DB.XYZ(f(X0 + x), f(y), f(z))


def symbol(category, family, name=None):
    for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(category):
        if s.FamilyName == family and (name is None or DB.Element.Name.GetValue(s) == name):
            if not s.IsActive:
                s.Activate()
            return s
    raise RuntimeError(u'no {} {}'.format(family, name or u''))


levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
ground, first = levels[0], levels[1]
H = (first.Elevation - ground.Elevation) * _MM


def loop(points, arcs=()):
    """CurveLoop through points (x, y mm); arcs: {index: (x, y) mid point} turns that edge into an arc."""
    cl = DB.CurveLoop()
    arcs = dict(arcs)
    for i in range(len(points)):
        a, b = points[i], points[(i + 1) % len(points)]
        if i in arcs:
            cl.Append(DB.Arc.Create(xyz(*a), xyz(*b), xyz(*arcs[i])))
        else:
            cl.Append(DB.Line.CreateBound(xyz(*a), xyz(*b)))
    return cl


def floor(loops, level=None):
    ftype = [t for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType)
             if DB.Element.Name.GetValue(t).startswith(u'300mm RC')][0]
    from System.Collections.Generic import List
    cls = List[DB.CurveLoop]()
    for cl in loops:
        cls.Add(cl)
    fl = DB.Floor.Create(doc, cls, ftype.Id, (level or first).Id)
    fl.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL).Set(1)
    return fl


def column(x, y, sym):
    if not sym.IsActive:
        sym.Activate()
    c = doc.Create.NewFamilyInstance(xyz(x, y), sym, ground, DBS.StructuralType.Column)
    c.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(first.Id)
    return c


FAMILIES = os.path.join(os.environ.get('LOCALAPPDATA', u''), u'Temp', u'nosa_t858')


def test_family(name):
    """
    A test family (make_test_families.py made it once and saved it): loaded, never made here - creating family
    documents from the harness killed Revit 2026 (2026-10-25). None when it has not been made.
    """
    path = os.path.join(FAMILIES, name + u'.rfa')
    if not os.path.exists(path):
        return None
    t = DB.Transaction(doc, u'NOSA test family')
    t.Start()
    loaded = doc.LoadFamily(path)
    t.Commit()
    fam = loaded[1] if isinstance(loaded, tuple) else None
    if fam is None:
        fam = [x for x in DB.FilteredElementCollector(doc).OfClass(DB.Family) if x.Name == name][0]
    return doc.GetElement(list(fam.GetFamilySymbolIds())[0])


def build():
    """{case: [element ids]} of the model."""
    cases = []
    rect = symbol(DB.BuiltInCategory.OST_StructuralColumns, u'Concrete Rectangular', u'450x600mm')
    rect_sq = symbol(DB.BuiltInCategory.OST_StructuralColumns, u'Concrete Square', u'450x450mm')
    round_ = symbol(DB.BuiltInCategory.OST_StructuralColumns, u'Concrete Round', u'450mm Ø')
    beam = symbol(DB.BuiltInCategory.OST_StructuralFraming, u'RC Beam', u'300x600mm')
    l_sym, t_sym = test_family(u'NOSA test L column'), test_family(u'NOSA test T column')
    haunch = test_family(u'NOSA test haunched beam')
    t = DB.Transaction(doc, u'NOSA T8.57 model')
    t.Start()
    c1, c2, c3 = column(0, 0, rect_sq), column(6000, 0, rect_sq), column(12000, 0, rect_sq)
    cases.append((u'columns', u'rectangular column 450x600', [column(0, 8000, rect).Id]))
    cases.append((u'columns', u'circular column 450', [column(6000, 8000, round_).Id]))
    z = H
    b1 = doc.Create.NewFamilyInstance(DB.Line.CreateBound(xyz(0, 0, z), xyz(6000, 0, z)), beam, first,
                                      DBS.StructuralType.Beam)
    b2 = doc.Create.NewFamilyInstance(DB.Line.CreateBound(xyz(6000, 0, z), xyz(12000, 0, z)), beam, first,
                                      DBS.StructuralType.Beam)
    cases.append((u'beams', u'continuous beam over three columns', [b1.Id, b2.Id]))
    b3 = doc.Create.NewFamilyInstance(DB.Line.CreateBound(xyz(0, -6000, z), xyz(6000, -6000, z + 600)), beam,
                                      first, DBS.StructuralType.Beam)
    cases.append((u'beams', u'inclined beam', [b3.Id]))
    b4 = doc.Create.NewFamilyInstance(DB.Arc.Create(xyz(0, -12000, z), xyz(6000, -12000, z),
                                                    xyz(3000, -10500, z)), beam, first, DBS.StructuralType.Beam)
    cases.append((u'beams', u'curved beam', [b4.Id]))
    slab = floor([loop([(20000, 0), (28000, 0), (28000, 6000), (20000, 6000)]),
                  loop([(23000, 2500), (23700, 2500), (23700, 3100), (23000, 3100)])])
    cases.append((u'footings_floors', u'slab with an opening', [slab.Id]))
    l_slab = floor([loop([(30000, 0), (38000, 0), (38000, 3000), (33000, 3000), (33000, 7000), (30000, 7000)])])
    cases.append((u'footings_floors', u'L-shaped slab', [l_slab.Id]))
    curved = floor([loop([(40000, 0), (46000, 0), (46000, 5000), (40000, 5000)], {1: (47000, 2500)})])
    cases.append((u'footings_floors', u'slab with a curved edge', [curved.Id]))
    wtype = [w for w in DB.FilteredElementCollector(doc).OfClass(DB.WallType)
             if DB.Element.Name.GetValue(w) == u'300mm RC Wall'][0]
    wall = DB.Wall.Create(doc, DB.Line.CreateBound(xyz(0, 20000), xyz(6000, 20000)), wtype.Id, ground.Id, f(H), 0.0,
                          False, True)
    doc.Regenerate()
    doc.Create.NewOpening(wall, xyz(2000, 20000, 800), xyz(3200, 20000, 2000))
    cases.append((u'walls', u'straight wall with an opening', [wall.Id]))
    arc_wall = DB.Wall.Create(doc, DB.Arc.Create(xyz(10000, 20000), xyz(16000, 20000), xyz(13000, 22000)), wtype.Id,
                              ground.Id, f(H), 0.0, False, True)
    cases.append((u'walls', u'curved wall', [arc_wall.Id]))
    pad = doc.Create.NewFamilyInstance(xyz(20000, 20000, -500), symbol(
        DB.BuiltInCategory.OST_StructuralFoundation, u'RC Pad foundation'), ground, DBS.StructuralType.Footing)
    cases.append((u'footings_floors', u'pad foundation', [pad.Id]))
    cap = doc.Create.NewFamilyInstance(xyz(26000, 20000, -900), symbol(
        DB.BuiltInCategory.OST_StructuralFoundation, u'Pile Cap-4 Pile', u'2000 x 2000 x 900mm'), ground,
        DBS.StructuralType.Footing)
    cases.append((u'footings_floors', u'pile cap, 4 piles', [cap.Id]))
    # T8.58 (2026-10-25): an L and a T column and a haunched beam (test families, make_test_families.py)
    if l_sym is not None:
        cases.append((u'columns', u'L column 600x600x250', [column(20000, 30000, l_sym).Id]))
    if t_sym is not None:
        cases.append((u'columns', u'T column 800x600x250', [column(24000, 30000, t_sym).Id]))
    if haunch is not None:
        if not haunch.IsActive:
            haunch.Activate()
        hb = doc.Create.NewFamilyInstance(DB.Line.CreateBound(xyz(28000, 30000, z), xyz(34000, 30000, z)), haunch,
                                          first, DBS.StructuralType.Beam)
        cases.append((u'beams', u'haunched beam 600/900', [hb.Id]))
    # T8.58 (2026-10-25): a column leaning 10 degrees and a slab sloping 10 %
    lean = math.tan(math.radians(10.0)) * H
    slanted = doc.Create.NewFamilyInstance(DB.Line.CreateBound(xyz(30000, 20000), xyz(30000 + lean, 20000, H)),
                                           rect_sq, ground, DBS.StructuralType.Column)
    cases.append((u'columns', u'inclined column 10 deg', [slanted.Id]))
    from System.Collections.Generic import List
    ftype = [x for x in DB.FilteredElementCollector(doc).OfClass(DB.FloorType)
             if DB.Element.Name.GetValue(x).startswith(u'300mm RC')][0]
    sloped_loops = List[DB.CurveLoop]()
    sloped_loops.Add(loop([(36000, 20000), (44000, 20000), (44000, 25000), (36000, 25000)]))
    sloped = DB.Floor.Create(doc, sloped_loops, ftype.Id, first.Id, True,
                             DB.Line.CreateBound(xyz(36000, 22500), xyz(44000, 22500)), 0.1)
    cases.append((u'footings_floors', u'inclined slab 10 %', [sloped.Id],
                  u'{"ChkIncludeTopMat": true, "ChkIncludePerimeterUBars": true}'))
    t.Commit()
    return cases, [c1.Id, c2.Id, c3.Id]


def _host_solids(host):
    opts = DB.Options()
    opts.ComputeReferences = False
    out = []
    for g in host.get_Geometry(opts):
        items = g.GetInstanceGeometry() if isinstance(g, DB.GeometryInstance) else [g]
        out.extend(x for x in items if isinstance(x, DB.Solid) and x.Volume > 1e-6)
    return out


def _link_tilt(host, hd):
    """How far a column's or beam's links lean off square to its axis (degrees), None without links or axis."""
    loc = host.Location
    axis = loc.Curve if isinstance(loc, DB.LocationCurve) else None
    if axis is None or not isinstance(axis, DB.Line):
        return None
    a = axis.Direction
    worst = None
    for r in hd.GetRebarsInHost():
        layer = r.LookupParameter(u'NOSA_Rebar_Layer')
        if layer is None or (layer.AsString() or u'') not in (u'stirrup', u'link'):
            continue
        curves = [c for c in r.GetCenterlineCurves(False, False, False, DBS.MultiplanarOption.IncludeOnlyPlanarCurves, 0)
                  if isinstance(c, DB.Line)]
        if len(curves) < 2:
            continue
        n = curves[0].Direction.CrossProduct(curves[1].Direction)
        if n.GetLength() < 1e-6:
            continue
        ang = math.degrees(math.acos(min(1.0, abs(n.Normalize().DotProduct(a)))))
        worst = ang if worst is None else max(worst, ang)
    return worst


def inside_report(ids):
    """The worst share of a bar's length inside its host's concrete, per host (T8.58: bars of sloping members)."""
    lines = []
    for eid in ids:
        host = doc.GetElement(eid)
        hd = DBS.RebarHostData.GetRebarHostData(host)
        if hd is None:
            continue
        solids = _host_solids(host)
        worst, where = 1.0, u''
        for r in hd.GetRebarsInHost():
            n = r.NumberOfBarPositions
            for i in sorted(set([0, n // 2, n - 1])):
                try:
                    curves = r.GetTransformedCenterlineCurves(False, False, False,
                                                              DBS.MultiplanarOption.IncludeOnlyPlanarCurves, i)
                except Exception:
                    continue
                total = inside = 0.0
                for c in curves:
                    total += c.Length
                    for so in solids:
                        res = so.IntersectWithCurve(c, DB.SolidCurveIntersectionOptions())
                        inside += sum(res.GetCurveSegment(k).Length for k in range(res.SegmentCount))
                share = inside / total if total > 0 else 1.0
                if share < worst:
                    worst, where = share, u'{} bar {}'.format(r.LookupParameter(u'NOSA_Rebar_Layer').AsString()
                                                              if r.LookupParameter(u'NOSA_Rebar_Layer') else u'', i)
        lines.append(u'    host {}: worst bar {:.0%} inside the concrete ({})'.format(
            eid.Value if hasattr(eid, 'Value') else eid.IntegerValue, worst, where))
        tilt = _link_tilt(host, hd)
        if tilt is not None:
            lines.append(u'    host {}: links {:.1f} deg off square to the member axis'.format(
                eid.Value if hasattr(eid, 'Value') else eid.IntegerValue, tilt))
    return lines


_log = []
group = DB.TransactionGroup(doc, u'NOSA T8.57 regression model')
group.Start()
try:
    started = time.time()
    cases, support_ids = build()
    harness = os.path.join(EXT_ROOT, 'tools', 'revit_harness', 'ra_harness.py')
    for case in cases:
        mode, label, ids = case[:3]
        controls = case[3] if len(case) > 3 else u'{}'
        if 'ONLY' in globals() and ONLY and label not in ONLY:
            continue
        scope = {'doc': doc, 'MODE': mode, 'IDS': [el.Value if hasattr(el, 'Value') else el.IntegerValue for el in ids],
                 'CONTROLS': controls, 'OVERRIDES': u'{}', 'EXT_ROOT': EXT_ROOT, 'PYREVIT': PYREVIT,
                 'ROLLBACK': True, 'ASSIMILATE': True, '__name__': '__nosa_case__'}
        t0 = time.time()
        try:
            execfile(harness, scope)
            text = scope.get('RESULT', u'')
        except Exception as e:
            text = u'EXCEPTION {}'.format(e)
        made = [l for l in text.split(u'\n') if u'created' in l][:1]
        bad = [l for l in text.split(u'\n') if u'REVIT ERROR' in l or u'EXCEPTION' in l or u'ALERT' in l]
        _log.append(u'{} [{}]: {} {:.1f} s{}'.format(label, mode, made[0] if made else u'nothing made',
                                                    time.time() - t0, u'' if not bad else u'\n    ' + u'\n    '.join(
                                                        b[:300] for b in bad)))
        try:
            _log.extend(inside_report(ids))
        except Exception as e:
            _log.append(u'    inside check failed: {}'.format(e))
        if 'FULL' in globals() and FULL:
            _log.append(text)
    _log.append(u'total {:.0f} s'.format(time.time() - started))
except Exception:
    import traceback
    _log.append(traceback.format_exc())
finally:
    group.RollBack()

RESULT = u'Revit {}\n'.format(doc.Application.VersionNumber) + u'\n'.join(_log)
try:
    with io.open(OUT, 'w', encoding='utf-8') as fh:
        fh.write(RESULT)
except NameError:  # nosa-lint: disable=NOSA006 - OUT not given
    pass
