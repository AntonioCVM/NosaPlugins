# -*- coding: utf-8 -*-
"""
Schedules review: place one element of every concrete and steel kind in the open template, read what every
schedule lists, then roll everything back. Scope: doc, EXT_ROOT, PYREVIT, OUT (file), SCHEDULES (optional
list of names), SETMAT (bool: set the instance Structural Material first). Result: RESULT.
"""
import io
import os
import sys
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import StructuralType

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_MM = 1.0 / 304.8
_lines = []


def _symbol(family, type_name=None):
    from nosa_utils.revit_helpers import element_name
    for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol):
        if s.FamilyName == family and (type_name is None or element_name(s) == type_name):
            if not s.IsActive:
                s.Activate()
            return s
    raise RuntimeError(u'no type {} : {}'.format(family, type_name))


def _type(cls, name):
    from nosa_utils.revit_helpers import element_name
    for t in DB.FilteredElementCollector(doc).OfClass(cls):
        if element_name(t) == name:
            return t
    raise RuntimeError(u'no {} {}'.format(cls.__name__, name))


def _pt(x, y, z=0.0):
    return DB.XYZ(x * _MM, y * _MM, z * _MM)


def build():
    from nosa_utils.revit_helpers import element_name
    level = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)[1]
    made = []

    def note(el, label):
        mat = el.LookupParameter(u'Structural Material')
        m = doc.GetElement(mat.AsElementId()) if mat is not None and mat.HasValue else None
        made.append(u'{} -> {} | structural material {}'.format(label, el.Id, element_name(m) if m else u'-'))
        return el

    x = 0.0
    for wt in (u'225mm RC Wall', u'300mm RC Wall'):
        note(DB.Wall.Create(doc, DB.Line.CreateBound(_pt(x, 0), _pt(x + 4000, 0)), _type(DB.WallType, wt).Id,
                            level.Id, 3000 * _MM, 0, False, True), u'wall ' + wt)
        x += 6000
    wall = DB.Wall.Create(doc, DB.Line.CreateBound(_pt(0, -8000), _pt(4000, -8000)),
                          _type(DB.WallType, u'225mm RC Wall').Id, level.Id, 3000 * _MM, 0, False, True)
    try:
        note(DB.WallFoundation.Create(doc, _type(DB.WallFoundationType, u'1200x600mm deep').Id, wall.Id),
             u'wall foundation 1200x600')
    except Exception as e:
        made.append(u'wall foundation: {}'.format(e))

    def loop(x0, y0, w, h):
        cl = DB.CurveLoop()
        pts = [_pt(x0, y0), _pt(x0 + w, y0), _pt(x0 + w, y0 + h), _pt(x0, y0 + h)]
        for i in range(4):
            cl.Append(DB.Line.CreateBound(pts[i], pts[(i + 1) % 4]))
        from System.Collections.Generic import List
        return List[DB.CurveLoop]([cl])
    for ft, y in ((u'300mm RC Floor', 5000), (u'160mm ComFlor 70', 12000), (u'800mm', 19000)):
        try:
            note(DB.Floor.Create(doc, loop(0, y, 4000, 4000), _type(DB.FloorType, ft).Id, level.Id), u'floor ' + ft)
        except Exception as e:
            made.append(u'floor {}: {}'.format(ft, e))

    def place(family, type_name, xx, yy, kind):
        try:
            sym = _symbol(family, type_name)
            return note(doc.Create.NewFamilyInstance(_pt(xx, yy), sym, level, kind), u'{} : {}'.format(family, type_name))
        except Exception as e:
            made.append(u'{} {}: {}'.format(family, type_name, e))

    def beam(family, type_name, yy):
        try:
            sym = _symbol(family, type_name)
            line = DB.Line.CreateBound(_pt(30000, yy, level.Elevation / _MM), _pt(36000, yy, level.Elevation / _MM))
            return note(doc.Create.NewFamilyInstance(line, sym, level, StructuralType.Beam),
                        u'beam {} : {}'.format(family, type_name))
        except Exception as e:
            made.append(u'beam {} {}: {}'.format(family, type_name, e))

    for i, (fam, typ) in enumerate(((u'Concrete Rectangular', None), (u'Concrete Round', None),
                                    (u'UKC-UK Columns-Column', None), (u'HEB Column', None),
                                    (u'SHS-Square Hollow Sections-Column', None),
                                    (u'CHS-Circular Hollow Sections-Column', None))):
        place(fam, typ, 20000, i * 3000, StructuralType.Column)
    for i, (fam, typ) in enumerate(((u'RC Beam', u'400x800mm'), (u'RC Beam', u'300x600mm'),
                                    (u'UKB-UK Beams', None), (u'HEA', None),
                                    (u'RHS-Rectangular Hollow Sections', None),
                                    (u'CHS-Circular Hollow Sections', None), (u'UKPFC-Parallel Flange Channels', None))):
        beam(fam, typ, i * 3000)
    for i, (fam, typ) in enumerate(((u'RC Pad foundation', None), (u'Pile Cap-4 Pile', None),
                                    (u'Pile Square piling', None), (u'Pile-Steel Pipe Circular', None))):
        place(fam, typ, 45000, i * 6000, StructuralType.Footing)
    return made


def read(names):
    out = []
    for s in sorted(DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule), key=lambda x: x.Name):
        if s.IsTitleblockRevisionSchedule or s.IsTemplate or (names and s.Name not in names):
            continue
        body = s.GetTableData().GetSectionData(DB.SectionType.Body)
        out.append(u'=== {} ({} rows)'.format(s.Name, body.NumberOfRows))
        for r in range(body.NumberOfRows):
            cells = [s.GetCellText(DB.SectionType.Body, r, c) for c in range(body.NumberOfColumns)]
            if any(c.strip() for c in cells):
                out.append(u'  | ' + u' | '.join(cells))
    return out


group = None
try:
    group = DB.TransactionGroup(doc, u'NOSA test - schedules')
    group.Start()
    t = DB.Transaction(doc, u'NOSA test - elements')
    from nosa_utils import transactions as nosa_tx
    collector = nosa_tx.FailureCollector()
    nosa_tx._install(t, collector)
    t.Start()
    _lines.extend(build())
    try:
        set_mat = SETMAT
    except NameError:
        set_mat = False
    if set_mat:       # what the schedules show once the instance Structural Material is set
        from nosa_utils.revit_helpers import element_name
        mats = dict((element_name(m), m.Id) for m in DB.FilteredElementCollector(doc).OfClass(DB.Material))
        for el in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().OfClass(DB.FamilyInstance):
            fam = el.Symbol.FamilyName
            p = el.LookupParameter(u'Structural Material')
            if p is None or p.IsReadOnly:
                continue
            if fam in (u'Concrete Rectangular', u'RC Pad foundation', u'Pile Cap-4 Pile', u'Pile Square piling'):
                p.Set(mats[u'Concrete - RC32/40'])
            elif fam in (u'UKB-UK Beams', u'UKC-UK Columns-Column'):
                p.Set(mats[u'Structural Steel - S355'])
        _lines.append(u'structural materials set on the test instances')
    t.Commit()
    if collector.errors:
        _lines.append(u'REVIT ERRORS: ' + u' | '.join(collector.errors))
    try:
        names = list(SCHEDULES)
    except NameError:
        names = []
    _lines.extend(read(names))
except Exception:
    _lines.append(traceback.format_exc())
finally:
    if group is not None and group.HasStarted() and not group.HasEnded():
        group.RollBack()
        _lines.append(u'rolled back')
with io.open(OUT, 'w', encoding='utf-8') as fh:
    fh.write(u'\n'.join(_lines))
RESULT = u'{} lines'.format(len(_lines))
