# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — reads a cast-in-place Revit Stairs for stair_rebar and maps its local
(s, v, z) frames back to model coordinates (T7.8). The bars are hosted on the Stairs element:
in Revit 2024 its runs and landings are not valid rebar hosts on their own.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
_EXT_LIB = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)

_FT = 304.8
_LEVEL_TOL_MM = 5.0
_TOUCH_TOL_MM = 100.0


class Frame(object):
    """Flight frame: origin at the first riser on the walking line, s along it, v to its left."""

    def __init__(self, origin, direction):
        from Autodesk.Revit import DB  # Lazy import
        self.origin = DB.XYZ(origin.X, origin.Y, 0.0)
        self.u = DB.XYZ(direction.X, direction.Y, 0.0).Normalize()
        self.v = DB.XYZ.BasisZ.CrossProduct(self.u)

    def local(self, point):
        d = point - self.origin
        return d.DotProduct(self.u) * _FT, d.DotProduct(self.v) * _FT

    def xyz(self, s, v, z):
        from Autodesk.Revit import DB  # Lazy import
        return DB.XYZ(self.origin.X + (self.u.X * s + self.v.X * v) / _FT,
                      self.origin.Y + (self.u.Y * s + self.v.Y * v) / _FT,
                      z / _FT)

    def vector(self, ds, dv, dz):
        from Autodesk.Revit import DB  # Lazy import
        return DB.XYZ(self.u.X * ds + self.v.X * dv, self.u.Y * ds + self.v.Y * dv, dz).Normalize()


def is_cast_in_place(stairs):
    from Autodesk.Revit.DB.Structure import RebarHostData
    try:
        return RebarHostData.IsValidHost(stairs)
    except Exception:
        return False


def _solids(element):
    from Autodesk.Revit import DB  # Lazy import
    out = []
    for g in element.get_Geometry(DB.Options()):
        if isinstance(g, DB.Solid) and g.Volume > 0:
            out.append(g)
        elif isinstance(g, DB.GeometryInstance):
            out.extend(x for x in g.GetInstanceGeometry() if isinstance(x, DB.Solid) and x.Volume > 0)
    return out


def _soffit_z0(run_element, frame):
    """Level (mm) of the flight soffit plane under the first riser, from the run's own solid."""
    from Autodesk.Revit import DB  # Lazy import
    best = None
    for solid in _solids(run_element):
        for face in solid.Faces:
            if not isinstance(face, DB.PlanarFace):
                continue
            n = face.FaceNormal
            if n.Z > -0.1 or n.Z < -0.999:
                continue
            if n.X * frame.u.X + n.Y * frame.u.Y < 0.05:      # the soffit leans towards the walking line
                continue
            if best is None or face.Area > best.Area:
                best = face
    if best is None:
        return None
    n, o = best.FaceNormal, best.Origin
    x0, y0 = frame.origin.X, frame.origin.Y
    return (o.Z - (n.X * (x0 - o.X) + n.Y * (y0 - o.Y)) / n.Z) * _FT


def _footprint_box(curves, frame):
    s_vals, v_vals = [], []
    for curve in curves:
        for i in (0, 1):
            s, v = frame.local(curve.GetEndPoint(i))
            s_vals.append(s)
            v_vals.append(v)
    return min(s_vals), max(s_vals), min(v_vals), max(v_vals)


def read_stairs(doc, stairs):
    """{'runs': [...], 'landings': [...], 'warnings': [...]} in stair_rebar's terms (mm)."""
    from Autodesk.Revit import DB  # Lazy import
    warnings = []
    riser = stairs.ActualRiserHeight * _FT
    tread = stairs.ActualTreadDepth * _FT
    runs, landings = [], []
    landing_data = []
    for lid in stairs.GetStairsLandings():
        landing = doc.GetElement(lid)
        try:
            thickness = doc.GetElement(landing.GetTypeId()).Thickness * _FT
        except Exception:
            thickness = 150.0
        landing_data.append({'element': landing, 'top_rel': landing.BaseElevation * _FT,
                             'thickness': thickness, 'curves': list(landing.GetFootprintBoundary())})

    run_elements = [doc.GetElement(rid) for rid in stairs.GetStairsRuns()]
    path_z = None
    for run_el in run_elements:
        path = list(run_el.GetStairsPath())
        if len(path) != 1 or not isinstance(path[0], DB.Line):
            warnings.append(u'Run {}: only straight runs are reinforced (winders / curved runs '
                            u'skipped).'.format(run_el.Id))
            continue
        start, end = path[0].GetEndPoint(0), path[0].GetEndPoint(1)
        path_z = start.Z * _FT if path_z is None else path_z
        frame = Frame(start, end - start)
        length = start.DistanceTo(end) * _FT
        base = path_z + run_el.BaseElevation * _FT
        top = path_z + run_el.TopElevation * _FT
        soffit = _soffit_z0(run_el, frame)
        if soffit is None:
            warnings.append(u'Run {}: no sloping soffit found — is the run monolithic?'.format(run_el.Id))
            continue
        _s0, _s1, v_min, v_max = _footprint_box(list(run_el.GetFootprintBoundary()), frame)
        run = {'element': run_el, 'frame': frame, 'length': length,
               'slope': riser / tread,
               'soffit_z0': soffit, 'pitch_z0': base, 'v_min': v_min, 'v_max': v_max,
               'risers': run_el.ActualRisersNumber, 'riser': riser, 'tread': tread,
               'lower': {'kind': 'floor', 'top': base, 'bottom': base, 's_far': 0.0},
               'upper': {'kind': 'floor', 'top': top, 'bottom': None, 's_far': length}}
        for data in landing_data:
            top_abs = path_z + data['top_rel']
            s_min, s_max, lv_min, lv_max = _footprint_box(data['curves'], frame)
            overlaps = lv_max > v_min + 1.0 and lv_min < v_max - 1.0
            if not overlaps:
                continue
            end = {'kind': 'landing', 'top': top_abs, 'bottom': top_abs - data['thickness'],
                   'element': data['element']}
            if abs(top_abs - top) < _LEVEL_TOL_MM and s_min <= length + _TOUCH_TOL_MM and s_max > length:
                end['s_far'] = s_max
                run['upper'] = end
            elif abs(top_abs - base) < _LEVEL_TOL_MM and s_max >= -_TOUCH_TOL_MM and s_min < 0.0:
                end['s_far'] = s_min
                run['lower'] = end
        runs.append(run)

    for data in landing_data:
        attached = [r for r in runs if r['upper'].get('element') is data['element'] or
                    r['lower'].get('element') is data['element']]
        if not attached:
            warnings.append(u'Landing {}: no straight flight attached — not reinforced.'.format(
                data['element'].Id))
            continue
        frame = attached[0]['frame']
        s_min, s_max, v_min, v_max = _footprint_box(data['curves'], frame)
        top_abs = path_z + data['top_rel']
        # the flights meet the landing along one side: start its own bars where the last of them ends
        frame_run = attached[0]
        upper_side = frame_run['upper'].get('element') is data['element']
        for r in attached:
            if abs(abs(r['frame'].u.DotProduct(frame.u)) - 1.0) > 1e-3:
                continue        # a perpendicular flight (L / quarter landing) joins along a side
            path = list(r['element'].GetStairsPath())[0]
            joint = path.GetEndPoint(1) if r['upper'].get('element') is data['element'] else path.GetEndPoint(0)
            s_joint, _v = frame.local(joint)
            if upper_side:
                s_min = max(s_min, s_joint)
            else:
                s_max = min(s_max, s_joint)
        strips, parallel = [], True
        for r in attached:
            if abs(abs(r['frame'].u.DotProduct(frame.u)) - 1.0) > 1e-3:
                parallel = False
                continue
            _a, _b, rv_min, rv_max = _footprint_box(list(r['element'].GetFootprintBoundary()), frame)
            strips.append((rv_min, rv_max))
        landings.append({'element': data['element'], 'frame': frame, 's_min': s_min, 's_max': s_max,
                         'v_min': v_min, 'v_max': v_max, 'top': top_abs,
                         'bottom': top_abs - data['thickness'], 'strips': strips,
                         'parallel': parallel})
    return {'runs': runs, 'landings': landings, 'warnings': warnings}


def set_curves(frame, bar_set):
    """Model curves and set normal for one stair_rebar set."""
    from Autodesk.Revit import DB  # Lazy import
    if bar_set['axis'] == 'v':
        v = bar_set['first']
        pts = [frame.xyz(s, v, z) for s, z in bar_set['points']]
        curves = [DB.Line.CreateBound(a, b) for a, b in zip(pts[:-1], pts[1:])]
        return curves, frame.v
    if bar_set['axis'] == 's':
        s = bar_set['first']
        pts = [frame.xyz(s, v, z) for v, z in bar_set['points_vz']]
        return [DB.Line.CreateBound(a, b) for a, b in zip(pts[:-1], pts[1:])], frame.u
    (s, z), = bar_set['points']
    v0, v1 = bar_set['v_range']
    curves = [DB.Line.CreateBound(frame.xyz(s, v0, z), frame.xyz(s, v1, z))]
    ds, dz = bar_set['direction']
    return curves, frame.vector(ds, 0.0, dz)



def _rollback_on_error():
    """A failures preprocessor that rolls the transaction back on any error (never a dialog)."""
    from Autodesk.Revit import DB  # Lazy import

    class RollbackOnError(DB.IFailuresPreprocessor):
        def __init__(self):
            self.errors = []

        def PreprocessFailures(self, accessor):
            accessor.DeleteAllWarnings()
            errors = [f for f in accessor.GetFailureMessages()
                      if f.GetSeverity() != DB.FailureSeverity.Warning]
            if not errors:
                return DB.FailureProcessingResult.Continue
            self.errors.extend(f.GetDescriptionText() for f in errors)
            return DB.FailureProcessingResult.ProceedWithRollBack
    return RollbackOnError()


def create_set(wrapper, host, frame, bar_set, bar_type):
    """
    One stair_rebar set as one Revit Rebar (a set when it holds several bars); None on failure.
    Runs in its own transaction that rolls back on a Revit error ("Can't solve Rebar Shape"),
    so a bad shape is reported in wrapper.last_error instead of stopping Revit with a dialog.
    """
    from Autodesk.Revit import DB  # Lazy import
    curves, normal = set_curves(frame, bar_set)
    name = u'NOSA — Create {}'.format(bar_set['label'])
    count = bar_set.get('count')
    doc = host.Document
    guard = _rollback_on_error()
    t = DB.Transaction(doc, name)
    options = t.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(guard)
    options.SetClearAfterRollback(True)
    options.SetForcedModalHandling(False)
    t.SetFailureHandlingOptions(options)
    t.Start()
    try:
        if count is not None and count >= 2:
            rebar = wrapper.create_rebar_set_fixed_number(host, curves, bar_type, count, bar_set['array'],
                                                          normal=normal, transaction_name=name)
        elif count is None and bar_set['array'] >= bar_set['spacing']:
            rebar = wrapper.create_rebar_set(host, curves, bar_type, bar_set['spacing'], bar_set['array'],
                                             normal=normal, transaction_name=name)
        else:
            rebar = wrapper.create_from_curves(host, curves, bar_type, normal=normal, transaction_name=name)
    except Exception as e:
        t.RollBack()
        wrapper.last_error = u'{}'.format(e)
        return None
    if t.Commit() != DB.TransactionStatus.Committed or guard.errors:
        wrapper.last_error = u'; '.join(guard.errors) or u'rolled back by Revit'
        return None
    return rebar


def host_cover_mm(stairs, default_mm):
    """The stair's own Rebar Cover (one common cover for a monolithic stair)."""
    from Autodesk.Revit.DB.Structure import RebarHostData
    try:
        cover_type = RebarHostData.GetRebarHostData(stairs).GetCommonCoverType()
        if cover_type is not None:
            return cover_type.CoverDistance * _FT
    except Exception:  # nosa-lint: disable=NOSA006 - no cover type: the normative default applies
        pass
    return default_mm


_EDGES = ('s_min', 's_max', 'v_min', 'v_max')


def _nearest_edge(landing, s, v):
    gaps = {'s_min': abs(s - landing['s_min']), 's_max': abs(s - landing['s_max']),
            'v_min': abs(v - landing['v_min']), 'v_max': abs(v - landing['v_max'])}
    return min(gaps, key=gaps.get)


def apply_landing_ubars(data, u_dia, cover, main_dia):
    """
    Mark every landing edge no flight arrives at, and whose U-bar can be bent, for U-bars
    (landing['u_edges']) and tell each flight whose bars stop at such an edge to stop straight
    inside the U (end['u_dia']). Returns the notes on edges left without U-bars.
    """
    import stair_rebar
    notes = []
    for landing in data['landings']:
        frame = landing['frame']
        occupied = set()
        for run in data['runs']:
            for end_name, joint_s in (('upper', run['length']), ('lower', 0.0)):
                end = run[end_name]
                if end.get('element') is not landing['element']:
                    continue
                mid_v = (run['v_min'] + run['v_max']) / 2.0
                s, v = frame.local(run['frame'].xyz(joint_s, mid_v, 0.0))
                occupied.add(_nearest_edge(landing, s, v))
        free = [e for e in _EDGES if e not in occupied]
        fits, why = stair_rebar.feasible_u_edges(landing['top'] - landing['bottom'], cover, main_dia,
                                                 u_dia, free)
        notes.extend(why)
        landing['u_edges'] = tuple(e for e in _EDGES if e in fits)
        for run in data['runs']:
            for end_name in ('upper', 'lower'):
                end = run[end_name]
                if end.get('element') is not landing['element']:
                    continue
                mid_v = (run['v_min'] + run['v_max']) / 2.0
                s, v = frame.local(run['frame'].xyz(end['s_far'], mid_v, 0.0))
                if _nearest_edge(landing, s, v) in landing['u_edges']:
                    end['u_dia'] = u_dia
    return notes


def wall_at_landing_edge(doc, landing, edge, reach_mm=100.0):
    """The wall a landing edge ('s_max', 'v_min', 'v_max') is built against, or None."""
    from Autodesk.Revit import DB  # Lazy import
    mid_s = (landing['s_min'] + landing['s_max']) / 2.0
    mid_v = (landing['v_min'] + landing['v_max']) / 2.0
    s, v = {'s_max': (landing['s_max'] + reach_mm, mid_v), 'v_min': (mid_s, landing['v_min'] - reach_mm),
            'v_max': (mid_s, landing['v_max'] + reach_mm)}[edge]
    p = landing['frame'].xyz(s, v, (landing['top'] + landing['bottom']) / 2.0)
    for wall in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Walls) \
            .WhereElementIsNotElementType():
        box = wall.get_BoundingBox(None)
        if box is None or not (box.Min.X <= p.X <= box.Max.X and box.Min.Y <= p.Y <= box.Max.Y
                               and box.Min.Z <= p.Z <= box.Max.Z):
            continue
        try:
            curve = wall.Location.Curve
            if curve.Distance(DB.XYZ(p.X, p.Y, curve.GetEndPoint(0).Z)) <= wall.Width / 2.0 + 1e-3:
                return wall
        except Exception:
            continue
    return None


def find_support_below(doc, x_ft, y_ft, base_z_ft, search_depth_ft=10.0, tol_ft=0.01):
    """Foundation, floor or beam right under a point whose top is at or just below base_z_ft."""
    from Autodesk.Revit import DB  # Lazy import
    best, best_top = None, None
    for cat in (DB.BuiltInCategory.OST_StructuralFoundation, DB.BuiltInCategory.OST_Floors,
                DB.BuiltInCategory.OST_StructuralFraming):
        for elem in DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType():
            box = elem.get_BoundingBox(None)
            if box is None:
                continue
            if not (box.Min.X - tol_ft <= x_ft <= box.Max.X + tol_ft and
                    box.Min.Y - tol_ft <= y_ft <= box.Max.Y + tol_ft):
                continue
            top = box.Max.Z
            if top > base_z_ft + tol_ft or top < base_z_ft - search_depth_ft:
                continue
            if best is None or top > best_top:
                best, best_top = elem, top
    return best


def starter_support(doc, re_engine, run, cover_mm, starter_dia_mm, mode, embed_mm=None,
                    support_cover_mm=None):
    """
    {'support': {...} for stair_rebar.starter_bars, 'host': element or None, 'embedded_mm',
     'source'} for a flight that starts on a support, or None when a cast-in starter finds
    nothing below. Post-installed starters stay hosted on the stair.
    """
    if mode != 'cast':
        return {'support': {'mode': 'post', 'embed': embed_mm}, 'host': None,
                'embedded_mm': embed_mm, 'source': 'post'}
    base = run['lower']['bottom']
    mid_v = (run['v_min'] + run['v_max']) / 2.0
    s_knee = (base + cover_mm - run['soffit_z0']) / run['slope']
    point = run['frame'].xyz(s_knee, mid_v, base)
    support = find_support_below(doc, point.X, point.Y, base / _FT)
    if support is None:
        return None
    box = re_engine.get_isolated_solid_bbox(support) or support.get_BoundingBox(None)
    cover = support_cover_mm if support_cover_mm is not None else         re_engine.get_native_cover_mm(doc, support, u'Bottom', cover_mm)
    mat_top_ft, source = re_engine.starter_foot_z(doc, support, box, cover, starter_dia_mm)
    foot_z = mat_top_ft * _FT + starter_dia_mm / 2.0          # the foot lies ON the mat
    return {'support': {'mode': 'cast', 'foot_z': foot_z}, 'host': support,
            'embedded_mm': base - foot_z, 'source': source}
