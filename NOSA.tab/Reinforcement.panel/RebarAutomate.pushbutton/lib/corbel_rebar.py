# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — column corbels (IStructE SMDSC 6.9, Model Detail MCB1). Revit side.

Corbels are read from the column instance's own geometry: every solid beside the shaft, standing
out of one of its four faces, is a corbel. That serves the NOSA corbel column families (one level
or several) and any other family built the same way. The bars come from nosa_utils.corbels.
"""
from Autodesk.Revit import DB

_MM_PER_FT = 304.8


def _solids(items):
    for obj in items or []:
        if isinstance(obj, DB.GeometryInstance):
            for sub in _solids(obj.GetInstanceGeometry()):
                yield sub
        elif isinstance(obj, DB.Solid) and obj.Volume > 0.0:
            yield obj


def _points(solid):
    return [p for edge in solid.Edges for p in edge.Tessellate()]


def find_corbels(host, cover_mm):
    """
    ({'base', 'top', 'u0', 'u1', 'v0', 'v1'}, [corbel]) of a column instance, or (None, []) without
    one. Each corbel: frame (origin on the column face at the corbel's centre line, o out of the face,
    a along it), top, projection, width, depth_face, depth_tip, cover, column depth / half_along.
    """
    solids = [(s, _points(s)) for s in _solids(host.get_Geometry(DB.Options()))]
    solids = [(s, p) for s, p in solids if p]
    if len(solids) < 2:
        return None, []
    try:
        u = DB.XYZ(host.HandOrientation.X, host.HandOrientation.Y, 0.0).Normalize()
    except Exception:
        u = DB.XYZ.BasisX
    v = DB.XYZ.BasisZ.CrossProduct(u)
    shaft, shaft_pts = max(solids, key=lambda sp: max(q.Z for q in sp[1]) - min(q.Z for q in sp[1]))
    origin = DB.XYZ(shaft_pts[0].X, shaft_pts[0].Y, 0.0)

    def uv(p):
        d = DB.XYZ(p.X, p.Y, 0.0) - origin
        return d.DotProduct(u) * _MM_PER_FT, d.DotProduct(v) * _MM_PER_FT

    su = [uv(p) for p in shaft_pts]
    col = {'u0': min(a for a, _b in su), 'u1': max(a for a, _b in su),
           'v0': min(b for _a, b in su), 'v1': max(b for _a, b in su),
           'base': min(p.Z for p in shaft_pts) * _MM_PER_FT, 'top': max(p.Z for p in shaft_pts) * _MM_PER_FT}
    cu, cv = (col['u0'] + col['u1']) / 2.0, (col['v0'] + col['v1']) / 2.0
    corbels = []
    for solid, pts in solids:
        if solid is shaft:
            continue
        loc = [uv(p) for p in pts]
        us, vs = [a for a, _b in loc], [b for _a, b in loc]
        tol = 2.0
        if min(us) >= col['u1'] - tol:
            side, o_dir, face, along, a_dir, depth, half = 'u+', u, col['u1'], vs, v, col['u1'] - col['u0'], (col['v1'] - col['v0']) / 2.0
        elif max(us) <= col['u0'] + tol:
            side, o_dir, face, along, a_dir, depth, half = 'u-', u.Negate(), -col['u0'], vs, v.Negate(), col['u1'] - col['u0'], (col['v1'] - col['v0']) / 2.0
        elif min(vs) >= col['v1'] - tol:
            side, o_dir, face, along, a_dir, depth, half = 'v+', v, col['v1'], us, u.Negate(), col['v1'] - col['v0'], (col['u1'] - col['u0']) / 2.0
        elif max(vs) <= col['v0'] + tol:
            side, o_dir, face, along, a_dir, depth, half = 'v-', v.Negate(), -col['v0'], us, u, col['v1'] - col['v0'], (col['u1'] - col['u0']) / 2.0
        else:
            continue                                          # not standing out of one face
        sign_a = 1.0 if side in ('u+', 'v-') else -1.0
        o_vals = [(us[i] if side[0] == 'u' else vs[i]) * (1.0 if side[1] == '+' else -1.0) - face
                  for i in range(len(pts))]
        a_vals = [(along[i] - (cv if side[0] == 'u' else cu)) * sign_a for i in range(len(pts))]
        z_vals = [p.Z * _MM_PER_FT for p in pts]
        projection = max(o_vals)
        at_face = [z for o, z in zip(o_vals, z_vals) if o < tol]
        at_tip = [z for o, z in zip(o_vals, z_vals) if o > projection - tol]
        if projection < 50.0 or not at_face or not at_tip:
            continue
        a_mid = (max(a_vals) + min(a_vals)) / 2.0
        plan = {'u+': (col['u1'], cv + a_mid), 'u-': (col['u0'], cv - a_mid),
                'v+': (cu - a_mid, col['v1']), 'v-': (cu + a_mid, col['v0'])}[side]
        frame_origin = origin + u.Multiply(plan[0] / _MM_PER_FT) + v.Multiply(plan[1] / _MM_PER_FT)
        corbels.append({
            'side': side, 'origin': DB.XYZ(frame_origin.X, frame_origin.Y, 0.0), 'o': o_dir, 'a': a_dir,
            'top': max(z_vals), 'projection': projection, 'width': max(a_vals) - min(a_vals),
            'depth_face': max(at_face) - min(at_face), 'depth_tip': max(at_tip) - min(at_tip),
            'cover': cover_mm, 'column_depth': depth, 'half_along': half})
    corbels.sort(key=lambda c: (c['side'], -c['top']))
    return col, corbels


def to_world(corbel, polyline):
    """Model lines of one (o, a, z) polyline, mm, in the corbel's frame."""
    pts = [corbel['origin'] + corbel['o'].Multiply(o / _MM_PER_FT) + corbel['a'].Multiply(a / _MM_PER_FT)
           + DB.XYZ(0.0, 0.0, z / _MM_PER_FT) for o, a, z in polyline]
    return [DB.Line.CreateBound(p, q) for p, q in zip(pts[:-1], pts[1:]) if p.DistanceTo(q) > 1e-3]
