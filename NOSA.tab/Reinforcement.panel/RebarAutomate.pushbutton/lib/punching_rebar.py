# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — punching shear stud rails round the columns under a slab (EC2 6.4, UK NA; the
layout rules in nosa_utils.punching). VEd and beta come from each column's NOSA_Punching_VEd /
NOSA_Punching_Beta, else from the window. Rails ("Shear Stud Rail") sit on the bottom cover, the
studs ("Shear Stud") on them with their heads at the top cover.
"""
import math
import os

from Autodesk.Revit import DB

from nosa_utils import punching
from nosa_utils.revit_helpers import get_id_value

_MM_PER_FT = 304.8
RAIL_FAMILY = u'Shear Stud Rail'
STUD_FAMILY = u'Shear Stud'
VED_PARAM = u'NOSA_Punching_VEd'
BETA_PARAM = u'NOSA_Punching_Beta'
DEFAULT_RHO = 0.005


def params_file():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data',
                                        'shared_parameters', 'NOSA_Punching.txt'))


def bind(doc):
    """NOSA_Punching_VEd / NOSA_Punching_Beta on Structural Columns (idempotent). Outside a transaction."""
    from nosa_utils import shared_params
    return shared_params.ensure_bound(doc, ['OST_StructuralColumns'], params_file())


def _symbol(doc, family, name=None):
    for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol):
        try:
            if s.FamilyName == family and (name is None or DB.Element.Name.GetValue(s) == name):
                return s
        except Exception:
            continue
    return None


def _number(element, name):
    p = element.LookupParameter(name)
    if p is None or not p.HasValue or p.StorageType != DB.StorageType.Double:
        return None
    v = p.AsDouble()
    return v if v > 0 else None


def _set(element, name, value):
    p = element.LookupParameter(name)
    if p is not None and not p.IsReadOnly:
        p.Set(value)


def slab_outline_mm(doc, slab, footing_rebar):
    """Outer loop of the slab's soffit in plan, mm, and the soffit z, mm."""
    engine = footing_rebar._ensure_engine()
    topo = footing_rebar._ensure_topology()
    face = footing_rebar.get_footing_bottom_face(engine.CoverGeometryManager(doc, slab))
    if face is None:
        return None, None
    outer, _holes, _n = topo.classify_loops(topo.extract_loops_mm(face.face))
    return outer, face.origin.Z * _MM_PER_FT


def columns_under(doc, slab, outline_mm):
    """Structural columns meeting the slab (their plan centre inside its outline)."""
    box = slab.get_BoundingBox(None)
    pad = 50.0 / _MM_PER_FT
    flt = DB.BoundingBoxIntersectsFilter(DB.Outline(box.Min - DB.XYZ(0, 0, pad), box.Max + DB.XYZ(0, 0, pad)))
    out = []
    for col in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StructuralColumns) \
            .WhereElementIsNotElementType().WherePasses(flt):
        loc = getattr(col, 'Location', None)
        if not isinstance(loc, DB.LocationPoint):
            continue
        p = loc.Point
        if punching.point_in_polygon(p.X * _MM_PER_FT, p.Y * _MM_PER_FT, outline_mm):
            out.append(col)
    return out


def column_frame(doc, col, column_rebar):
    """(centre XYZ, unit x along the width, column dict for nosa_utils.punching) or None."""
    geo = column_rebar.detect_column_geometry(doc, col)
    if not geo:
        return None
    try:
        hand = DB.XYZ(col.HandOrientation.X, col.HandOrientation.Y, 0.0).Normalize()
    except Exception:
        hand = DB.XYZ.BasisX
    if geo.get('shape') == 'circle':
        section = {'d': geo['diameter_mm']}
    else:
        section = {'c1': geo['width_mm'], 'c2': geo['depth_mm']}
    return col.Location.Point, hand, section


def effective_depth_and_rho(h_mm, top_cover_mm, values):
    """(d, rho_l, note) from the top mat in the window; rho_l = 0.5 % assumed without one."""
    if values.get('include_top_mat'):
        dx, dy, s = values['top_dia_x'], values['top_dia_y'], values['top_spacing']
        d = h_mm - top_cover_mm - (dx + dy) / 2.0
        rx = math.pi * dx ** 2 / 4.0 / (s * d)
        ry = math.pi * dy ** 2 / 4.0 / (s * d)
        return d, math.sqrt(rx * ry), None
    dia = max(values.get('dia_x') or 12.0, values.get('dia_y') or 12.0)
    d = h_mm - top_cover_mm - dia
    return d, DEFAULT_RHO, (u'no top mat given: d = {:.0f} mm and rho_l = 0.5 % assumed for the punching check; '
                            u'tick Include Top Mat for the real values.'.format(d))


def place(doc, slab, values, bottom_cover_mm, top_cover_mm, fck, footing_rebar, column_rebar, errors):
    """Check every column under the slab and place its stud rails. In a transaction. Returns the rails placed."""
    sid = get_id_value(slab.Id)
    rail_sym = _symbol(doc, RAIL_FAMILY)
    stud_sym = _symbol(doc, STUD_FAMILY, u'{:.0f}mm'.format(values['stud_dia']))
    if rail_sym is None or stud_sym is None:
        errors.append(u'Floor {}: the "{}" / "{}" ({:.0f}mm) families are not loaded — punching studs '
                      u'skipped.'.format(sid, RAIL_FAMILY, STUD_FAMILY, values['stud_dia']))
        return 0
    outline, soffit = slab_outline_mm(doc, slab, footing_rebar)
    if outline is None:
        errors.append(u'Floor {}: no soffit found — punching studs skipped.'.format(sid))
        return 0
    box = slab.get_BoundingBox(None)
    h_mm = box.Max.Z * _MM_PER_FT - soffit
    d, rho, note = effective_depth_and_rho(h_mm, top_cover_mm, values)
    if note:
        errors.append(u'Floor {}: {}'.format(sid, note))
    rail_t = (_number(rail_sym, u'Rail Thickness') or 6.0 / _MM_PER_FT) * _MM_PER_FT
    stud_h = punching.stud_height_mm(h_mm, top_cover_mm, bottom_cover_mm, rail_t)
    z_rail = soffit + bottom_cover_mm + rail_t
    level = doc.GetElement(slab.LevelId)
    for sym in (rail_sym, stud_sym):
        if not sym.IsActive:
            sym.Activate()
    placed = 0
    columns = columns_under(doc, slab, outline)
    if not columns:
        errors.append(u'Floor {}: no columns under it — no punching check.'.format(sid))
    for col in columns:
        cid = get_id_value(col.Id)
        ved = _number(col, VED_PARAM)
        beta = _number(col, BETA_PARAM)
        ved = ved if ved else values.get('punch_ved')
        beta = beta if beta else values.get('punch_beta') or 1.15
        if not ved:
            errors.append(u'Column {}: no VEd ({} empty, none in the window) — punching not checked.'.format(
                cid, VED_PARAM))
            continue
        frame = column_frame(doc, col, column_rebar)
        if frame is None:
            errors.append(u'Column {}: section not read — punching not checked.'.format(cid))
            continue
        centre, ux, section = frame
        uy = DB.XYZ.BasisZ.CrossProduct(ux)
        cx, cy = centre.X * _MM_PER_FT, centre.Y * _MM_PER_FT
        local = [((x - cx) * ux.X + (y - cy) * ux.Y, (x - cx) * uy.X + (y - cy) * uy.Y) for x, y in outline]
        r = punching.design(ved, beta, section, d, rho, fck, values['stud_dia'], polygon=local)
        label = u'Column {} (VEd {:.0f} kN, beta {:.2f})'.format(cid, ved, beta)
        errors.extend(u'{}: {}'.format(label, n) for n in r['notes'])
        if not r['needed'] or not r['ok']:
            continue

        def world(p):
            return DB.XYZ((cx + p[0] * ux.X + p[1] * uy.X) / _MM_PER_FT,
                          (cy + p[0] * ux.Y + p[1] * uy.Y) / _MM_PER_FT, z_rail / _MM_PER_FT)
        studs = 0
        for rail in r['rails']:
            a, b = world(rail['start']), world(rail['end'])
            inst = doc.Create.NewFamilyInstance(DB.Line.CreateBound(a, b), rail_sym, level,
                                                DB.Structure.StructuralType.NonStructural)
            _offset(inst, level, z_rail)
            _set(inst, u'Number of Studs', len(rail['studs']))
            _set(inst, u'Stud Diameter', values['stud_dia'] / _MM_PER_FT)
            _set(inst, u'Stud Height', stud_h / _MM_PER_FT)
            _set(inst, u'Stud Spacing', r['sr'] / _MM_PER_FT)
            _set(inst, u'First Stud From Column', r['perimeters'][0] / _MM_PER_FT)
            for p in rail['studs']:
                stud = doc.Create.NewFamilyInstance(world(p), stud_sym, level, DB.Structure.StructuralType.NonStructural)
                _offset(stud, level, z_rail)
                _set(stud, u'Stud Height', stud_h / _MM_PER_FT)
                studs += 1
            placed += 1
        errors.append(u'{}: vEd {:.2f} > vRd,c {:.2f} N/mm2 at u1; Asw {:.0f} mm2 per perimeter = {} H{:.0f} studs; '
                      u'{} perimeters at {:.0f} + {:.0f} mm (u_out {:.0f} mm from the face); {} rails, {} studs '
                      u'{:.0f} mm high (EC2 6.4, SMDSC).'.format(
                          label, r['v_ed1'], r['v_rd_c'], r['asw_mm2'], r['studs_per_perimeter'],
                          float(values['stud_dia']), len(r['perimeters']), r['perimeters'][0], r['sr'], r['a_out'],
                          len(r['rails']), studs, stud_h))
    return placed


def _offset(inst, level, z_mm):
    """Lift a level-hosted instance to z (mm, absolute)."""
    p = inst.get_Parameter(DB.BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM)
    if p is not None and not p.IsReadOnly:
        p.Set(z_mm / _MM_PER_FT - level.Elevation)
