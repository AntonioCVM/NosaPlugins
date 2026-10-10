# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — continuous nibs and half joints of beams (IStructE SMDSC 6.9). Revit side: reads the
NOSA "RC Beam - Nib" / "RC Beam - Half Joint" parameters and turns the section-frame layouts of
nosa_utils.nibs into model lines.
"""
from Autodesk.Revit import DB

_MM_PER_FT = 304.8


def _value_mm(host, name):
    for el in (host, getattr(host, 'Symbol', None)):
        if el is None:
            continue
        p = el.LookupParameter(name)
        if p is not None and p.HasValue and p.StorageType == DB.StorageType.Double:
            return p.AsDouble() * _MM_PER_FT
    return None


def _flag(host, name):
    for el in (host, getattr(host, 'Symbol', None)):
        if el is None:
            continue
        p = el.LookupParameter(name)
        if p is not None and p.HasValue and p.StorageType == DB.StorageType.Integer:
            return p.AsInteger() == 1
    return False


def nib_sides(host):
    """(projection, depth, [+1 left, -1 right]) of an 'RC Beam - Nib', else None."""
    proj, depth = _value_mm(host, u'Nib Projection'), _value_mm(host, u'Nib Depth')
    if not proj or not depth:
        return None
    sides = [s for s, name in ((1.0, u'Nib Left'), (-1.0, u'Nib Right')) if _flag(host, name)]
    return (proj, depth, sides) if sides else None


def half_joint_params(host):
    """(length, notch height) of an 'RC Beam - Half Joint', else None."""
    length, depth = _value_mm(host, u'Half Joint Length'), _value_mm(host, u'Half Joint Depth')
    return (length, depth) if length and depth else None


def section_mm(host):
    """(b, h) from the type."""
    return _value_mm(host, u'b'), _value_mm(host, u'h')


def _points(host):
    def solids(items):
        for obj in items or []:
            if isinstance(obj, DB.GeometryInstance):
                for sub in solids(obj.GetInstanceGeometry()):
                    yield sub
            elif isinstance(obj, DB.Solid) and obj.Volume > 0.0:
                yield obj
    return [p for s in solids(host.get_Geometry(DB.Options())) for e in s.Edges for p in e.Tessellate()]


def frame(host):
    """
    The beam's section frame: {'o' (soffit at the start of its geometry), 'ex' (along), 'ey' (left), 'length',
    'axis_offset' (axis start from the geometry start, mm)}.
    """
    curve = host.Location.Curve
    p0 = curve.GetEndPoint(0)
    ex = (curve.GetEndPoint(1) - p0).Normalize()
    ex = DB.XYZ(ex.X, ex.Y, 0.0).Normalize()
    ey = DB.XYZ.BasisZ.CrossProduct(ex)
    pts = _points(host)
    xs = [(p - p0).DotProduct(ex) for p in pts]
    soffit = min(p.Z for p in pts)
    lo, hi = min(xs), max(xs)
    o = p0 + ex.Multiply(lo)
    return {'o': DB.XYZ(o.X, o.Y, soffit), 'ex': ex, 'ey': ey, 'length': (hi - lo) * _MM_PER_FT,
            'axis_offset': -lo * _MM_PER_FT}


def world(fr, x, y, z):
    return fr['o'] + fr['ex'].Multiply(x / _MM_PER_FT) + fr['ey'].Multiply(y / _MM_PER_FT) \
        + DB.XYZ.BasisZ.Multiply(z / _MM_PER_FT)


def polyline(fr, pts, closed=False):
    """Model lines through (x, y, z) section-frame points."""
    w = [world(fr, *p) for p in pts]
    if closed:
        w.append(w[0])
    return [DB.Line.CreateBound(a, b) for a, b in zip(w[:-1], w[1:]) if a.DistanceTo(b) > 1e-4]


def section_loop(fr, x, corners):
    """A closed link in the section at x through (y, z) corners."""
    return polyline(fr, [(x, y, z) for y, z in corners], closed=True)


def mirror_x(fr, pts):
    """The same layout at the far end of the beam."""
    return [(fr['length'] - x, -y, z) for x, y, z in pts]
