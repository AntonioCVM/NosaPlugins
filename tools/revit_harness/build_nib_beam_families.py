# -*- coding: utf-8 -*-
"""
Beam families for IStructE SMDSC 6.9 (user decision 2026-10-10), both copies of the template's "RC Beam":
"RC Beam - Nib" (a continuous nib flush with the soffit on either side: Nib Left / Nib Right, Nib
Projection, Nib Depth) and "RC Beam - Half Joint" (a half joint at both ends: Half Joint Length, Half
Joint Depth = the notch from the soffit). Scope: doc, SAVE_TO (folder), LOAD (bool), WHICH ('nib', 'half',
'both'). Result: RESULT.
"""
import os
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

_MM = 1.0 / 304.8
_log = []
_OPEN = []


class _Opts(DB.IFamilyLoadOptions):
    def OnFamilyFound(self, in_use, overwrite):
        return True, True

    def OnSharedFamilyFound(self, fam, in_use, source, overwrite):
        return True, DB.FamilySource.Family, True


def _xyz(x, y, z):
    return DB.XYZ(x * _MM, y * _MM, z * _MM)


def _refs(*items):
    ra = DB.ReferenceArray()
    for it in items:
        ra.Append(it)
    return ra


def _start(fd, name):
    t = DB.Transaction(fd, name)
    t.Start()
    _OPEN.append(t)
    return t


def _roll_back_open():
    while _OPEN:
        t = _OPEN.pop()
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()


def _source(fd):
    """The RC Beam copy's planes, views, sweep and parameters."""
    planes = list(DB.FilteredElementCollector(fd).OfClass(DB.ReferencePlane))

    def plane(normal, coord, value):
        for rp in planes:
            n = rp.Normal
            if abs(abs(getattr(n, normal)) - 1.0) < 1e-6 and abs(getattr(rp.BubbleEnd, coord) - value * _MM) < 1.0 * _MM:
                return rp
        raise Exception(u'no reference plane {} = {}'.format(coord, value))
    sweep = list(DB.FilteredElementCollector(fd).OfClass(DB.Sweep))[0]
    bb = sweep.get_BoundingBox(None)
    views = dict((v.Name + u'|' + u'{}'.format(v.ViewType), v) for v in DB.FilteredElementCollector(fd).OfClass(DB.View)
                 if not v.IsTemplate)
    fm = fd.FamilyManager
    b = fm.get_Parameter(u'b').Formula  # noqa: F841 - only proves the parameter exists
    x0, x1 = bb.Min.X / _MM, bb.Max.X / _MM
    return {'sweep': sweep, 'x0': x0, 'x1': x1, 'end0': plane('X', 'X', x0), 'end1': plane('X', 'X', x1),
            'side_pos': plane('Y', 'Y', 150.0), 'side_neg': plane('Y', 'Y', -150.0),
            'bottom': [rp for rp in planes if rp.Name == u'Bottom'][0],
            'plan': views[u'Ref. Level|FloorPlan'], 'front': views[u'Front|Elevation'],
            'left': views[u'Left|Elevation'], 'fm': fm,
            'material': fm.get_Parameter(u'Structural Material')}


def _base_type(fd):
    """Back to the 300x600mm type: the sketches below are drawn at its sizes."""
    fm = fd.FamilyManager
    fm.CurrentType = [ft for ft in fm.Types if ft.Name == u'300x600mm'][0]
    fd.Regenerate()


def _new_plane(fd, name, a, b, cut, view):
    rp = fd.FamilyCreate.NewReferencePlane(a, b, cut, view)
    rp.Name = name
    return rp


def _sketch_ref(fd, curve):
    return fd.GetElement(curve.Reference.ElementId).GeometryCurve.Reference


def _align(fd, view, plane_ref, other_ref):
    a = fd.FamilyCreate.NewAlignment(view, plane_ref, other_ref)
    a.IsLocked = True


def _faces(element):
    opt = DB.Options()
    opt.ComputeReferences = True
    opt.IncludeNonVisibleObjects = True
    out = {}
    for g in element.get_Geometry(opt):
        if isinstance(g, DB.Solid):
            for f in g.Faces:
                if isinstance(f, DB.PlanarFace):
                    n = f.FaceNormal
                    out[(int(round(n.X)), int(round(n.Y)), int(round(n.Z)))] = f.Reference
    return out


def _lock_profile(fd, view, ext, pairs):
    """Lock each sketch line of ext to the plane it lies on: pairs [(test(line) -> bool, plane)]."""
    locked = 0
    for c in [c for ca in ext.Sketch.Profile for c in ca]:
        for test, rp in pairs:
            if test(c):
                try:
                    _align(fd, view, rp.GetReference(), _sketch_ref(fd, c))
                    locked += 1
                except Exception as e:
                    _log.append(u'lock to {} at {} -> {} failed: {}'.format(
                        rp.Name, [round(v / _MM) for v in (c.GetEndPoint(0).X, c.GetEndPoint(0).Y, c.GetEndPoint(0).Z)],
                        [round(v / _MM) for v in (c.GetEndPoint(1).X, c.GetEndPoint(1).Y, c.GetEndPoint(1).Z)],
                        u'{}'.format(e).split(u'\n')[0]))
                break
    return locked


def _box(ext):
    bb = ext.get_BoundingBox(None)
    return (bb.Min.X / _MM, bb.Max.X / _MM, bb.Min.Y / _MM, bb.Max.Y / _MM, bb.Min.Z / _MM, bb.Max.Z / _MM)


def _fix_direction(fd, ext, x0, x1):
    """Extrude from x0 towards x1 whichever way the sketch plane's normal points."""
    lo, hi = _box(ext)[0:2]
    if abs(lo - x0) > 1.0 or abs(hi - x1) > 1.0:
        ext.EndOffset = -ext.EndOffset
        fd.Regenerate()


def build_nib(fd):
    s = _source(fd)
    fm = s['fm']
    t = _start(fd, u'NOSA nib beam')
    proj = fm.AddParameter(u'Nib Projection', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
    depth = fm.AddParameter(u'Nib Depth', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
    left = fm.AddParameter(u'Nib Left', DB.GroupTypeId.Geometry, DB.SpecTypeId.Boolean.YesNo, False)
    right = fm.AddParameter(u'Nib Right', DB.GroupTypeId.Geometry, DB.SpecTypeId.Boolean.YesNo, False)
    fm.SetDescription(proj, u'How far the nib stands out of the beam side')
    fm.SetDescription(depth, u'Nib depth from the beam soffit (SMDSC MN2: not less than 140)')
    for ft in fm.Types:
        fm.CurrentType = ft
        fm.Set(proj, 150 * _MM)
        fm.Set(depth, 250 * _MM)
        fm.Set(left, 1)
        fm.Set(right, 0)
    _base_type(fd)
    x0, x1 = s['x0'], s['x1']
    left_view = s['left']
    planes = {}
    for name, y in ((u'Nib Left Edge', 300.0), (u'Nib Right Edge', -300.0)):
        planes[name] = _new_plane(fd, name, _xyz(0, y, -700), _xyz(0, y, 700), DB.XYZ.BasisX, left_view)
    top = _new_plane(fd, u'Nib Top', _xyz(0, -700, -50), _xyz(0, 700, -50), DB.XYZ.BasisX, left_view)
    fd.Regenerate()
    create = fd.FamilyCreate
    create.NewDimension(left_view, DB.Line.CreateBound(_xyz(x0, 0, -500), _xyz(x0, 400, -500)),
                        _refs(s['side_pos'].GetReference(), planes[u'Nib Left Edge'].GetReference())).FamilyLabel = proj
    create.NewDimension(left_view, DB.Line.CreateBound(_xyz(x0, -400, -500), _xyz(x0, 0, -500)),
                        _refs(planes[u'Nib Right Edge'].GetReference(), s['side_neg'].GetReference())).FamilyLabel = proj
    create.NewDimension(left_view, DB.Line.CreateBound(_xyz(x0, 500, -300), _xyz(x0, 500, -50)),
                        _refs(s['bottom'].GetReference(), top.GetReference())).FamilyLabel = depth
    sketch = DB.SketchPlane.Create(fd, s['end0'].Id)
    made = []
    for name, side, edge, flag in ((u'left', s['side_pos'], planes[u'Nib Left Edge'], left),
                                   (u'right', s['side_neg'], planes[u'Nib Right Edge'], right)):
        y_in, y_out = side.BubbleEnd.Y / _MM, edge.BubbleEnd.Y / _MM
        pts = [_xyz(x0, y_in, -300), _xyz(x0, y_out, -300), _xyz(x0, y_out, -50), _xyz(x0, y_in, -50)]
        loop = DB.CurveArray()
        for i in range(4):
            loop.Append(DB.Line.CreateBound(pts[i], pts[(i + 1) % 4]))
        arr = DB.CurveArrArray()
        arr.Append(loop)
        ext = create.NewExtrusion(True, arr, sketch, (x1 - x0) * _MM)
        fd.Regenerate()
        _fix_direction(fd, ext, x0, x1)

        def at_y(v):
            return lambda c: abs(c.GetEndPoint(0).Y - v * _MM) < 1e-4 and abs(c.GetEndPoint(1).Y - v * _MM) < 1e-4

        def at_z(v):
            return lambda c: abs(c.GetEndPoint(0).Z - v * _MM) < 1e-4 and abs(c.GetEndPoint(1).Z - v * _MM) < 1e-4
        n = _lock_profile(fd, left_view, ext, [(at_y(y_in), side), (at_y(y_out), edge),
                                               (at_z(-300), s['bottom']), (at_z(-50), top)])
        faces = _faces(ext)
        ends = 0
        for key, rp in (((-1, 0, 0), s['end0'] if x0 < x1 else s['end1']), ((1, 0, 0), s['end1'])):
            if key in faces:
                _align(fd, s['plan'], rp.GetReference(), faces[key])
                ends += 1
        fm.AssociateElementParameterToFamilyParameter(ext.get_Parameter(DB.BuiltInParameter.IS_VISIBLE_PARAM), flag)
        if s['material'] is not None:
            fm.AssociateElementParameterToFamilyParameter(ext.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM),
                                                          s['material'])
        _log.append(u'nib {}: profile locks {}, end locks {}, box {}'.format(name, n, ends, [round(v) for v in _box(ext)]))
        made.append(ext)
    fd.Regenerate()
    t.Commit()
    _flex(fd, made, [(u'b', 400), (u'h', 800), (u'Nib Projection', 200), (u'Nib Depth', 300)])
    return made


def build_half(fd):
    s = _source(fd)
    fm = s['fm']
    t = _start(fd, u'NOSA half joint beam')
    length = fm.AddParameter(u'Half Joint Length', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
    depth = fm.AddParameter(u'Half Joint Depth', DB.GroupTypeId.Geometry, DB.SpecTypeId.Length, False)
    fm.SetDescription(length, u'Length of the notch at each end of the beam')
    fm.SetDescription(depth, u'Height of the notch from the soffit (the nib is the rest of the depth)')
    for ft in fm.Types:
        fm.CurrentType = ft
        fm.Set(length, 300 * _MM)
        fm.Set(depth, 300 * _MM)
    _base_type(fd)
    x0, x1 = s['x0'], s['x1']
    front, plan, create = s['front'], s['plan'], fd.FamilyCreate
    p_start = _new_plane(fd, u'Half Joint Start', _xyz(x0 + 300, -700, 0), _xyz(x0 + 300, 700, 0), DB.XYZ.BasisZ, plan)
    p_end = _new_plane(fd, u'Half Joint End', _xyz(x1 - 300, -700, 0), _xyz(x1 - 300, 700, 0), DB.XYZ.BasisZ, plan)
    p_top = _new_plane(fd, u'Half Joint Top', _xyz(-2000, 0, 0), _xyz(2000, 0, 0), DB.XYZ.BasisY, front)
    fd.Regenerate()
    create.NewDimension(plan, DB.Line.CreateBound(_xyz(x0, 500, 0), _xyz(x0 + 300, 500, 0)),
                        _refs(s['end0'].GetReference(), p_start.GetReference())).FamilyLabel = length
    create.NewDimension(plan, DB.Line.CreateBound(_xyz(x1 - 300, 500, 0), _xyz(x1, 500, 0)),
                        _refs(p_end.GetReference(), s['end1'].GetReference())).FamilyLabel = length
    create.NewDimension(front, DB.Line.CreateBound(_xyz(x1 + 100, 0, -300), _xyz(x1 + 100, 0, 0)),
                        _refs(s['bottom'].GetReference(), p_top.GetReference())).FamilyLabel = depth
    centre = [rp for rp in DB.FilteredElementCollector(fd).OfClass(DB.ReferencePlane) if rp.Name == u'Center (Front/Back)'][0]
    sketch = DB.SketchPlane.Create(fd, centre.Id)
    voids = []
    for name, xa, xb, end_plane, joint_plane in ((u'start', x0, x0 + 300, s['end0'], p_start),
                                                 (u'end', x1 - 300, x1, s['end1'], p_end)):
        pts = [_xyz(xa, 0, -2000), _xyz(xb, 0, -2000), _xyz(xb, 0, 0), _xyz(xa, 0, 0)]     # well below any soffit
        loop = DB.CurveArray()
        for i in range(4):
            loop.Append(DB.Line.CreateBound(pts[i], pts[(i + 1) % 4]))
        arr = DB.CurveArrArray()
        arr.Append(loop)
        void = create.NewExtrusion(False, arr, sketch, 1000 * _MM)
        void.StartOffset = -1000 * _MM
        fd.Regenerate()

        def at_x(v):
            return lambda c: abs(c.GetEndPoint(0).X - v * _MM) < 1e-4 and abs(c.GetEndPoint(1).X - v * _MM) < 1e-4

        def at_z(v):
            return lambda c: abs(c.GetEndPoint(0).Z - v * _MM) < 1e-4 and abs(c.GetEndPoint(1).Z - v * _MM) < 1e-4
        outer = xa if name == u'start' else xb
        inner = xb if name == u'start' else xa
        n = _lock_profile(fd, front, void, [(at_x(outer), end_plane), (at_x(inner), joint_plane), (at_z(0), p_top)])
        _log.append(u'half joint {}: profile locks {}'.format(name, n))
        voids.append(void)
    every = DB.CombinableElementArray()               # one combination: the voids cut the beam body
    every.Append(s['sweep'])
    for void in voids:
        every.Append(void)
    fd.CombineElements(every)
    fd.Regenerate()
    t.Commit()
    _flex(fd, [s['sweep']], [(u'b', 400), (u'h', 800), (u'Half Joint Length', 400), (u'Half Joint Depth', 350)])
    return voids


def _flex(fd, elements, changes):
    fm = fd.FamilyManager
    t = _start(fd, u'flex')
    for name, mm in changes:
        fm.Set(fm.get_Parameter(name), mm * _MM)
    fd.Regenerate()
    for e in elements:
        _log.append(u'flex {}: {}'.format(e.Id.IntegerValue, [round(v) for v in _box(e)]))
    if elements and isinstance(elements[0], DB.Sweep):
        solids = [g for g in elements[0].get_Geometry(DB.Options()) if isinstance(g, DB.Solid)]
        _log.append(u'flex sweep volume {:.3f} m3, faces {}'.format(
            sum(x.Volume for x in solids) * 0.0283168, sum(x.Faces.Size for x in solids)))
    t.RollBack()
    _OPEN.remove(t)


def make(name, builder):
    src = [f for f in DB.FilteredElementCollector(doc).OfClass(DB.Family) if f.Name == u'RC Beam'][0]
    fd = doc.EditFamily(src)
    try:
        builder(fd)
        path = os.path.join(SAVE_TO, name + u'.rfa')
        opts = DB.SaveAsOptions()
        opts.OverwriteExistingFile = True
        fd.SaveAs(path, opts)
        _log.append(u'saved ' + path)
        if LOAD:
            fam = fd.LoadFamily(doc, _Opts())
            _log.append(u'loaded {}'.format(fam.Name if fam else u'?'))
    except Exception:
        _log.append(traceback.format_exc())
        _roll_back_open()
    finally:
        fd.Close(False)


try:
    which = WHICH
except NameError:
    which = u'both'
if which in (u'nib', u'both'):
    make(u'RC Beam - Nib', build_nib)
if which in (u'half', u'both'):
    make(u'RC Beam - Half Joint', build_half)
RESULT = u'\n'.join(_log)
