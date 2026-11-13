# -*- coding: utf-8 -*-
"""
Punching shear stud families for the template (user decision 2026-10-10: stud rails):
"Shear Stud" (point-based Generic Model: shaft of Stud Diameter, head 3 x the diameter and half of it
thick, Stud Height overall from its base) and "Shear Stud Rail" (line-based Generic Model: a flat bar
Rail Width x Rail Thickness under the line, plus the rail's stud data as instance parameters for the
schedules). Scope: doc, SAVE_TO (folder), LOAD (bool). Result: RESULT.
"""
import os
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

TEMPLATES = r'C:\ProgramData\Autodesk\RVT 2024\Family Templates\English'
_MM = 1.0 / 304.8
STUD_SIZES = (10, 12, 14, 16, 20, 25)
_log = []


def _xyz(x, y, z):
    return DB.XYZ(x * _MM, y * _MM, z * _MM)


def _refs(*items):
    ra = DB.ReferenceArray()
    for it in items:
        ra.Append(it)
    return ra


class _Opts(DB.IFamilyLoadOptions):
    def OnFamilyFound(self, in_use, overwrite):
        return True, True

    def OnSharedFamilyFound(self, fam, in_use, source, overwrite):
        return True, DB.FamilySource.Family, True


def _views(fd):
    return dict((v.Name + u'|' + u'{}'.format(v.ViewType), v) for v in DB.FilteredElementCollector(fd).OfClass(DB.View)
                if not v.IsTemplate)


def _circle_extrusion(fd, sketch, radius_mm, depth_mm):
    profile = DB.CurveArray()
    profile.Append(DB.Arc.Create(DB.XYZ.Zero, radius_mm * _MM, 0.0, 2.0 * 3.141592653589793, DB.XYZ.BasisX, DB.XYZ.BasisY))
    arr = DB.CurveArrArray()
    arr.Append(profile)
    return fd.FamilyCreate.NewExtrusion(True, arr, sketch, depth_mm * _MM)


def _label_radius(fd, plan, ext, param):
    curve = [c for ca in ext.Sketch.Profile for c in ca][0]
    ref = fd.GetElement(curve.Reference.ElementId).GeometryCurve.Reference
    dim = fd.FamilyCreate.NewRadialDimension(plan, ref, _xyz(0, 0, 0))
    dim.FamilyLabel = param


_OPEN = []


def _start(fd, name):
    t = DB.Transaction(fd, name)
    t.Start()
    _OPEN.append(t)
    return t


def _roll_back_open(fd):
    """Roll back a transaction a failed build left open, or the document will not close."""
    while _OPEN:
        t = _OPEN.pop()
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()


def _save_and_load(fd, name):
    path = os.path.join(SAVE_TO, name + u'.rfa')
    opts = DB.SaveAsOptions()
    opts.OverwriteExistingFile = True
    fd.SaveAs(path, opts)
    _log.append(u'saved ' + path)
    if LOAD:
        fam = fd.LoadFamily(doc, _Opts())
        _log.append(u'loaded {}'.format(fam.Name if fam else u'?'))


def build_stud():
    fd = doc.Application.NewFamilyDocument(os.path.join(TEMPLATES, u'Metric Generic Model.rft'))
    try:
        fm = fd.FamilyManager
        plan = _views(fd)[u'Ref. Level|FloorPlan']
        level = list(DB.FilteredElementCollector(fd).OfClass(DB.Level))[0]
        t = _start(fd, u'NOSA shear stud')
        dia = fm.AddParameter(u'Stud Diameter', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
        r_shaft = fm.AddParameter(u'Stud Radius', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
        r_head = fm.AddParameter(u'Head Radius', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
        head_t = fm.AddParameter(u'Head Thickness', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
        height = fm.AddParameter(u'Stud Height', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, True)
        shaft_l = fm.AddParameter(u'Shaft Length', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, True)
        if fm.CurrentType is None:
            fm.NewType(u'{}mm'.format(STUD_SIZES[0]))
        fm.Set(dia, 10 * _MM)
        fm.Set(height, 194 * _MM)
        fm.SetFormula(r_shaft, u'Stud Diameter / 2')
        fm.SetFormula(r_head, u'Stud Diameter * 1.5')
        fm.SetFormula(head_t, u'Stud Diameter / 2')
        fm.SetFormula(shaft_l, u'Stud Height - Head Thickness')
        for p, text in ((dia, u'Shank diameter of the headed stud'),
                        (height, u'Overall height from the rail to the top of the head'),
                        (head_t, u'Head 3 x the shank diameter, half of it thick')):
            fm.SetDescription(p, text)
        sketch = DB.SketchPlane.Create(fd, level.Id)
        shaft = _circle_extrusion(fd, sketch, 5.0, 189.0)
        head = _circle_extrusion(fd, sketch, 15.0, 194.0)
        head.StartOffset = 189.0 * _MM
        fd.Regenerate()
        _label_radius(fd, plan, shaft, r_shaft)
        _label_radius(fd, plan, head, r_head)
        fm.AssociateElementParameterToFamilyParameter(shaft.get_Parameter(DB.BuiltInParameter.EXTRUSION_END_PARAM), shaft_l)
        fm.AssociateElementParameterToFamilyParameter(head.get_Parameter(DB.BuiltInParameter.EXTRUSION_START_PARAM), shaft_l)
        fm.AssociateElementParameterToFamilyParameter(head.get_Parameter(DB.BuiltInParameter.EXTRUSION_END_PARAM), height)
        fd.Regenerate()
        for d in STUD_SIZES:
            name = u'{}mm'.format(d)
            have = [ft for ft in fm.Types if ft.Name == name]
            if have:
                fm.CurrentType = have[0]
            else:
                fm.NewType(name)
            fm.Set(dia, d * _MM)
            fd.Regenerate()
        t.Commit()
        for d in (25, 10):                              # flex check
            t2 = _start(fd, u'flex')
            fm.CurrentType = [ft for ft in fm.Types if ft.Name == u'{}mm'.format(d)][0]
            fm.Set(height, 250 * _MM)
            fd.Regenerate()
            bb = head.get_BoundingBox(None)
            _log.append(u'flex {}mm: head x {:.1f}..{:.1f} z {:.1f}..{:.1f}'.format(
                d, bb.Min.X / _MM, bb.Max.X / _MM, bb.Min.Z / _MM, bb.Max.Z / _MM))
            t2.RollBack()
        _save_and_load(fd, u'Shear Stud')
    except Exception:
        _log.append(traceback.format_exc())
        _roll_back_open(fd)
    finally:
        fd.Close(False)


def build_rail():
    fd = doc.Application.NewFamilyDocument(os.path.join(TEMPLATES, u'Metric Generic Model line based.rft'))
    try:
        fm = fd.FamilyManager
        create = fd.FamilyCreate
        planes = dict((rp.Name, rp) for rp in DB.FilteredElementCollector(fd).OfClass(DB.ReferencePlane))
        views = _views(fd)
        plan, front = views[u'Ref. Level|FloorPlan'], views[u'Front|Elevation']
        level = list(DB.FilteredElementCollector(fd).OfClass(DB.Level))[0]
        t = _start(fd, u'NOSA shear stud rail')
        width = fm.AddParameter(u'Rail Width', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
        thick = fm.AddParameter(u'Rail Thickness', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
        fm.Set(width, 30 * _MM)
        fm.Set(thick, 6 * _MM)
        info = [(u'Number of Studs', DB.SpecTypeId.Int.Integer, u'Studs on this rail'),
                (u'Stud Diameter', DB.SpecTypeId.Length, u'Shank diameter of the studs'),
                (u'Stud Height', DB.SpecTypeId.Length, u'Overall stud height above the rail'),
                (u'Stud Spacing', DB.SpecTypeId.Length, u'Stud pitch along the rail (0.75 d)'),
                (u'First Stud From Column', DB.SpecTypeId.Length, u'First stud from the column face (0.5 d)')]
        for name, spec, text in info:
            p = fm.AddParameter(name, DB.GroupTypeId.Data, spec, True)
            fm.SetDescription(p, text)
        w, th = 30.0, 6.0
        side_a = create.NewReferencePlane(_xyz(-300, w / 2, 0), _xyz(1500, w / 2, 0), DB.XYZ.BasisZ, plan)
        side_a.Name = u'Side A'
        side_b = create.NewReferencePlane(_xyz(-300, -w / 2, 0), _xyz(1500, -w / 2, 0), DB.XYZ.BasisZ, plan)
        side_b.Name = u'Side B'
        bottom = create.NewReferencePlane(_xyz(-300, 0, -th), _xyz(1500, 0, -th), DB.XYZ.BasisY, front)
        bottom.Name = u'Bottom'
        fd.Regenerate()
        centre = planes[u'Center (Front/Back)']
        create.NewDimension(plan, DB.Line.CreateBound(_xyz(600, -w, 0), _xyz(600, w, 0)),
                            _refs(side_a.GetReference(), side_b.GetReference())).FamilyLabel = width
        create.NewDimension(plan, DB.Line.CreateBound(_xyz(300, -w, 0), _xyz(300, w, 0)),
                            _refs(side_a.GetReference(), centre.GetReference(), side_b.GetReference())).AreSegmentsEqual = True
        top_ref = level.GetPlaneReference()
        create.NewDimension(front, DB.Line.CreateBound(_xyz(600, 0, 20), _xyz(600, 0, -th - 20)),
                            _refs(top_ref, bottom.GetReference())).FamilyLabel = thick
        profile = DB.CurveArray()
        pts = [_xyz(0, -w / 2, 0), _xyz(0, w / 2, 0), _xyz(0, w / 2, -th), _xyz(0, -w / 2, -th)]
        for i in range(4):
            profile.Append(DB.Line.CreateBound(pts[i], pts[(i + 1) % 4]))
        arr = DB.CurveArrArray()
        arr.Append(profile)
        ext = create.NewExtrusion(True, arr, DB.SketchPlane.Create(fd, planes[u'Left'].Id), 1200 * _MM)
        fd.Regenerate()
        opt = DB.Options()
        opt.ComputeReferences = True
        opt.IncludeNonVisibleObjects = True
        faces = {}
        for g in ext.get_Geometry(opt):
            if isinstance(g, DB.Solid):
                for f in g.Faces:
                    if isinstance(f, DB.PlanarFace):
                        n = f.FaceNormal
                        faces[(round(n.X), round(n.Y), round(n.Z))] = f.Reference
        locked = 0
        for key, ref, view in (((1, 0, 0), planes[u'Right'].GetReference(), plan),
                               ((-1, 0, 0), planes[u'Left'].GetReference(), plan),
                               ((0, 1, 0), side_a.GetReference(), plan), ((0, -1, 0), side_b.GetReference(), plan),
                               ((0, 0, 1), top_ref, front), ((0, 0, -1), bottom.GetReference(), front)):
            try:
                create.NewAlignment(view, ref, faces[key]).IsLocked = True
                locked += 1
            except Exception as e:
                _log.append(u'align {}: {}'.format(key, e))
        _log.append(u'rail faces locked: {}'.format(locked))
        if fm.CurrentType is not None:
            fm.RenameCurrentType(u'30x6mm')
        t.Commit()
        _save_and_load(fd, u'Shear Stud Rail')
    except Exception:
        _log.append(traceback.format_exc())
        _roll_back_open(fd)
    finally:
        fd.Close(False)


for _build in (build_stud, build_rail):
    try:
        _build()
    except Exception:
        _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
