# -*- coding: utf-8 -*-
"""
"RC Ground Beam": line-based Structural Foundation family (user 2026-10-05) so tie beams land in the
foundation and concrete schedules. Width (centred, EQ) and Depth (down from the placement level) drive a
prism locked to the Left/Right ends; geometry material = Structural Material (Concrete - Generic).
Scope: doc, EXT_ROOT, PYREVIT, SAVE_TO (folder for the .rfa), LOAD (bool: load into doc). Result: RESULT.
"""
import os
import sys
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TEMPLATE = r'C:\ProgramData\Autodesk\RVT 2024\Family Templates\English\Metric Generic Model line based.rft'
NAME = u'RC Ground Beam'
TYPES = [(300, 450), (300, 600), (400, 600), (400, 800), (450, 900)]
MATERIAL = u'Concrete - Generic'
_MM = 1.0 / 304.8
_log = []


def _xyz(x, y, z):
    return DB.XYZ(x * _MM, y * _MM, z * _MM)


def build():
    app = doc.Application
    fd = app.NewFamilyDocument(TEMPLATE)
    try:
        planes = dict((rp.Name, rp) for rp in DB.FilteredElementCollector(fd).OfClass(DB.ReferencePlane))
        views = dict((v.Name + u'|' + u'{}'.format(v.ViewType), v) for v in DB.FilteredElementCollector(fd).OfClass(DB.View)
                     if not v.IsTemplate)
        plan = views[u'Ref. Level|FloorPlan']
        front = views[u'Front|Elevation']
        level = list(DB.FilteredElementCollector(fd).OfClass(DB.Level))[0]
        fm = fd.FamilyManager
        create = fd.FamilyCreate
        t = DB.Transaction(fd, u'NOSA ground beam')
        t.Start()
        fd.OwnerFamily.FamilyCategory = fd.Settings.Categories.get_Item(DB.BuiltInCategory.OST_StructuralFoundation)
        try:
            fd.OwnerFamily.get_Parameter(DB.BuiltInParameter.FAMILY_STRUCT_MATERIAL_TYPE).Set(
                int(DB.Structure.StructuralMaterialType.Concrete))
        except Exception as e:
            _log.append(u'material type: {}'.format(e))
        existing = dict((p.Definition.Name, p) for p in fm.Parameters)
        _log.append(u'built-in parameters now: {}'.format(sorted(n for n in existing if n in (
            u'Width', u'Length', u'Foundation Thickness', u'Thickness', u'Depth', u'Structural Material'))))

        def length_param(names, new_name):
            for n in names:
                p = existing.get(n)
                if p is not None and not p.IsReporting and not p.IsDeterminedByFormula:
                    if p.IsInstance:
                        fm.MakeType(p)
                    return p
            return fm.AddParameter(new_name, DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
        width = length_param([u'Width'], u'Beam Width')
        depth = length_param([u'Foundation Thickness', u'Depth'], u'Depth')
        fm.Set(width, 300 * _MM)
        fm.Set(depth, 600 * _MM)
        w, d, length = 300.0, 600.0, 1200.0
        side_a = create.NewReferencePlane(_xyz(-300, w / 2, 0), _xyz(1500, w / 2, 0), DB.XYZ.BasisZ, plan)
        side_a.Name = u'Side A'
        side_b = create.NewReferencePlane(_xyz(-300, -w / 2, 0), _xyz(1500, -w / 2, 0), DB.XYZ.BasisZ, plan)
        side_b.Name = u'Side B'
        bottom = create.NewReferencePlane(_xyz(-300, 0, -d), _xyz(1500, 0, -d), DB.XYZ.BasisY, front)
        bottom.Name = u'Bottom'
        fd.Regenerate()
        centre = planes[u'Center (Front/Back)']

        def refs(*items):
            ra = DB.ReferenceArray()
            for it in items:
                ra.Append(it)
            return ra
        dline = DB.Line.CreateBound(_xyz(600, -w, 0), _xyz(600, w, 0))
        dim_w = create.NewDimension(plan, dline, refs(side_a.GetReference(), side_b.GetReference()))
        dim_w.FamilyLabel = width
        dim_eq = create.NewDimension(plan, DB.Line.CreateBound(_xyz(300, -w, 0), _xyz(300, w, 0)),
                                     refs(side_a.GetReference(), centre.GetReference(), side_b.GetReference()))
        dim_eq.AreSegmentsEqual = True
        top_ref = level.GetPlaneReference()
        dim_d = create.NewDimension(front, DB.Line.CreateBound(_xyz(600, 0, 50), _xyz(600, 0, -d - 50)),
                                    refs(top_ref, bottom.GetReference()))
        dim_d.FamilyLabel = depth

        profile = DB.CurveArray()
        pts = [_xyz(0, -w / 2, 0), _xyz(0, w / 2, 0), _xyz(0, w / 2, -d), _xyz(0, -w / 2, -d)]
        for i in range(4):
            profile.Append(DB.Line.CreateBound(pts[i], pts[(i + 1) % 4]))
        arr = DB.CurveArrArray()
        arr.Append(profile)
        sketch = DB.SketchPlane.Create(fd, planes[u'Left'].Id)
        ext = create.NewExtrusion(True, arr, sketch, length * _MM)
        fd.Regenerate()

        opt = DB.Options()
        opt.ComputeReferences = True
        opt.IncludeNonVisibleObjects = True
        faces = {}
        for g in ext.get_Geometry(opt):
            if isinstance(g, DB.Solid):
                for f in g.Faces:
                    n = f.FaceNormal if isinstance(f, DB.PlanarFace) else None
                    if n is None:
                        continue
                    key = (round(n.X), round(n.Y), round(n.Z))
                    faces[key] = f.Reference
        pairs = [((1, 0, 0), planes[u'Right'].GetReference(), plan), ((-1, 0, 0), planes[u'Left'].GetReference(), plan),
                 ((0, 1, 0), side_a.GetReference(), plan), ((0, -1, 0), side_b.GetReference(), plan),
                 ((0, 0, 1), top_ref, front), ((0, 0, -1), bottom.GetReference(), front)]
        locked = 0
        for key, ref, view in pairs:
            if key not in faces:
                _log.append(u'no face {}'.format(key))
                continue
            try:
                al = create.NewAlignment(view, ref, faces[key])
                al.IsLocked = True
                locked += 1
            except Exception as e:
                _log.append(u'align {}: {}'.format(key, e))
        _log.append(u'faces locked: {}'.format(locked))
        for label, w_mm, d_mm in ((u'regen after locks', 300, 600), (u'flex 450x900', 450, 900), (u'back', 300, 600)):
            try:
                fm.Set(width, w_mm * _MM)
                fm.Set(depth, d_mm * _MM)
                fd.Regenerate()
                _log.append(label + u': ok')
            except Exception as e:
                _log.append(u'{}: {}'.format(label, e))
                raise

        mat = None
        for m in DB.FilteredElementCollector(fd).OfClass(DB.Material):
            if m.Name == MATERIAL:
                mat = m.Id
        if mat is None:
            mat = DB.Material.Create(fd, MATERIAL)
        smat = fm.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
        if smat is None:
            smat = fm.AddParameter(u'Structural Material', DB.GroupTypeId.Materials, DB.SpecTypeId.Reference.Material, True)
            _log.append(u'added Structural Material parameter')
        fm.Set(smat, mat)                    # a value first: associating to an empty material fails regeneration
        fd.Regenerate()
        try:
            fm.AssociateElementParameterToFamilyParameter(ext.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM), smat)
        except Exception as e:
            _log.append(u'material association: {} - geometry gets the material directly'.format(e))
            ext.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM).Set(mat)

        first = True
        for bw, bd in TYPES:
            tname = u'{}x{}mm'.format(bw, bd)
            if first and fm.CurrentType is not None:
                fm.RenameCurrentType(tname)
                first = False
            else:
                fm.NewType(tname)
            fm.Set(width, bw * _MM)
            fm.Set(depth, bd * _MM)
            fm.Set(smat, mat)
            fd.Regenerate()
        t.Commit()
        _log.append(u'types: {}'.format(fm.Types.Size))
        path = os.path.join(SAVE_TO, NAME + u'.rfa')
        opts = DB.SaveAsOptions()
        opts.OverwriteExistingFile = True
        fd.SaveAs(path, opts)
        _log.append(u'saved ' + path)
        if LOAD:
            class _Opts(DB.IFamilyLoadOptions):
                def OnFamilyFound(self, in_use, overwrite):
                    return True, True

                def OnSharedFamilyFound(self, fam, in_use, source, overwrite):
                    return True, DB.FamilySource.Family, True
            fam = fd.LoadFamily(doc, _Opts())
            _log.append(u'loaded into {}: {}'.format(doc.Title, fam.Name if fam else u'?'))
    except Exception:
        _log.append(traceback.format_exc())
        for tx_name in ('t',):
            tx = locals().get(tx_name)
            if tx is not None and tx.HasStarted() and not tx.HasEnded():
                tx.RollBack()
    finally:
        fd.Close(False)


try:
    build()
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
