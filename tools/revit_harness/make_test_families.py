# -*- coding: utf-8 -*-
"""
T8.58 test families, made ONCE in a Revit instance that holds no user work and saved as .rfa in OUTDIR, so the
harnesses only load them (Application.NewFamilyDocument killed Revit 2026 when driven repeatedly, 2026-10-25):
an L and a T concrete column and a haunched concrete beam. Scope: doc, OUTDIR. Result: RESULT.
"""
import glob
import os

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS

_MM = 304.8


def f(mm):
    return mm / _MM


def _template(name):
    year = doc.Application.VersionNumber
    found = glob.glob(u'C:/ProgramData/Autodesk/RVT {}/Family Templates/*/{}'.format(year, name))
    if not found:
        raise RuntimeError(u'no {} for Revit {}'.format(name, year))
    return found[0]


def _make(template, path, draw):
    if os.path.exists(path):
        return u'kept ' + os.path.basename(path)
    fam = doc.Application.NewFamilyDocument(_template(template))
    t = DB.Transaction(fam, u'NOSA test family')
    try:
        t.Start()
        draw(fam)
        fam.OwnerFamily.get_Parameter(DB.BuiltInParameter.FAMILY_STRUCT_MATERIAL_TYPE).Set(
            int(DBS.StructuralMaterialType.Concrete))
        t.Commit()
        opts = DB.SaveAsOptions()
        opts.OverwriteExistingFile = True
        fam.SaveAs(path, opts)
    finally:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        fam.Close(False)
    return u'made ' + os.path.basename(path)


def _extrusion(fam, outline, plane, depth_mm):
    arr = DB.CurveArray()
    for a, b in zip(outline, outline[1:] + outline[:1]):
        arr.Append(DB.Line.CreateBound(a, b))
    profile = DB.CurveArrArray()
    profile.Append(arr)
    fam.FamilyCreate.NewExtrusion(True, profile, DB.SketchPlane.Create(fam, plane), f(depth_mm))


def _column(outline_mm):
    def draw(fam):
        pts = [DB.XYZ(f(x), f(y), 0.0) for x, y in outline_mm]
        _extrusion(fam, pts, DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisZ, DB.XYZ.Zero), 3000.0)
    return draw


def _haunched_beam(fam):
    # side elevation in the beam's XZ plane: 600 deep, 900 at each end over 1000 mm, 6000 long, 300 wide
    pts = [(0, 0), (6000, 0), (6000, -900), (5000, -600), (1000, -600), (0, -900)]
    plane = DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisY, DB.XYZ(0.0, f(-150.0), 0.0))
    _extrusion(fam, [DB.XYZ(f(x), f(-150.0), f(z)) for x, z in pts], plane, 300.0)


_log = []
if not os.path.isdir(OUTDIR):
    os.makedirs(OUTDIR)
_log.append(_make(u'Metric Structural Column.rft', os.path.join(OUTDIR, u'NOSA test L column.rfa'),
                  _column([(-300, -300), (300, -300), (300, -50), (-50, -50), (-50, 300), (-300, 300)])))
_log.append(_make(u'Metric Structural Column.rft', os.path.join(OUTDIR, u'NOSA test T column.rfa'),
                  _column([(-400, 50), (-125, 50), (-125, -300), (125, -300), (125, 50), (400, 50), (400, 300),
                           (-400, 300)])))
_log.append(_make(u'Metric Structural Framing - Beams and Braces.rft',
                  os.path.join(OUTDIR, u'NOSA test haunched beam.rfa'), _haunched_beam))
RESULT = u'\n'.join(_log)
