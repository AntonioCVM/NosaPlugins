# -*- coding: utf-8 -*-
"""
T8.57 scripted reinforcement test model: in the unsaved test project only, one rolled-back group builds every
typology and shape the plugin claims (rectangular and circular columns; straight, inclined and curved beams over
columns; rectangular slab with an opening, L-shaped slab, slab with a curved edge; straight wall with an opening,
curved wall; pad foundation, pile cap), reinforces each through RebarAutomate's real path (ra_harness.py, one
element at a time so a failure is pinned to its case) and reports what each case made and every Revit error.
Run in each Revit version before a merge (extends T8.2). Scope: doc, EXT_ROOT, PYREVIT, OUT. Result: RESULT.
"""
import io
import os
import time

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS

if doc.PathName or doc.Title != u'Project1':
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
    c = doc.Create.NewFamilyInstance(xyz(x, y), sym, ground, DBS.StructuralType.Column)
    c.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(first.Id)
    return c


def build():
    """{case: [element ids]} of the model."""
    cases = []
    rect = symbol(DB.BuiltInCategory.OST_StructuralColumns, u'Concrete Rectangular', u'450x600mm')
    rect_sq = symbol(DB.BuiltInCategory.OST_StructuralColumns, u'Concrete Square', u'450x450mm')
    round_ = symbol(DB.BuiltInCategory.OST_StructuralColumns, u'Concrete Round', u'450mm Ø')
    beam = symbol(DB.BuiltInCategory.OST_StructuralFraming, u'RC Beam', u'300x600mm')
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
    t.Commit()
    return cases, [c1.Id, c2.Id, c3.Id]


_log = []
group = DB.TransactionGroup(doc, u'NOSA T8.57 regression model')
group.Start()
try:
    started = time.time()
    cases, support_ids = build()
    harness = os.path.join(EXT_ROOT, 'tools', 'revit_harness', 'ra_harness.py')
    for mode, label, ids in cases:
        scope = {'doc': doc, 'MODE': mode, 'IDS': [el.Value if hasattr(el, 'Value') else el.IntegerValue for el in ids],
                 'CONTROLS': u'{}', 'OVERRIDES': u'{}', 'EXT_ROOT': EXT_ROOT, 'PYREVIT': PYREVIT,
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
