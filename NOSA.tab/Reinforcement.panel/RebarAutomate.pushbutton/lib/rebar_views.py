# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Create Views in one click (T7.3).

For every reinforced element: the view set of its typology (user decision 2026-10-03), the NOSA
RC templates, a scale from view_plan, its bars shown unobscured and tagged without overlaps, and
an A1 QR sheet of its own numbered in the 4500 series (45xx RC details). Each element is built in one transaction
that rolls back on a Revit error instead of opening a dialog.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_FT = 304.8
SECTION_TEMPLATE = u'NOSA RC Section'
PLAN_TEMPLATE = u'NOSA RC PLAN'
TITLEBLOCK = u'NOSA_Titleblock_A1_QR'
_CATEGORIES = (('OST_StructuralColumns', 'column'), ('OST_StructuralFraming', 'beam'),
               ('OST_StructuralFoundation', 'foundation'), ('OST_Floors', 'floor'),
               ('OST_Walls', 'wall'), ('OST_Stairs', 'stairs'))
_TITLES = {'column': u'Column', 'beam': u'Beam', 'foundation': u'Foundation', 'floor': u'Slab',
           'wall': u'Wall', 'stairs': u'Stair'}


def _mm(feet):
    return feet * _FT


def _ft(mm):
    return mm / _FT


def host_kind(element):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    if element is None or element.Category is None:
        return None
    value = get_id_value(element.Category.Id)
    for name, kind in _CATEGORIES:
        if value == int(getattr(DB.BuiltInCategory, name)):
            return kind
    return None


def host_rebars(element):
    from Autodesk.Revit.DB.Structure import RebarHostData
    try:
        return list(RebarHostData.GetRebarHostData(element).GetRebarsInHost())
    except Exception:
        return []


def host_label(element):
    """
    The element's Mark, else its id: never its bars' BBS partition, which another member's Mark can read the same
    (2026-10-17: an unmarked column drawn as a second 'C1').
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    try:
        mark = (element.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString() or u'').strip()
        if mark:
            return mark
    except Exception:  # nosa-lint: disable=NOSA006 - no Mark parameter: the id applies
        pass
    return u'{}'.format(get_id_value(element.Id))


def _box(element, re_engine):
    box = None
    try:
        box = re_engine.get_isolated_solid_bbox(element)
    except Exception:
        box = None
    return box or element.get_BoundingBox(None)


def _extent(box, direction):
    """(min, max) of a bounding box along a direction, ft."""
    from Autodesk.Revit import DB  # Lazy import
    values = [DB.XYZ(x, y, z).DotProduct(direction) for x in (box.Min.X, box.Max.X)
              for y in (box.Min.Y, box.Max.Y) for z in (box.Min.Z, box.Max.Z)]
    return min(values), max(values)


STARTER_LAYERS = (u'dowel', u'starter_link')


def _starters_depth(host, origin, toward):
    """How far (mm) behind a section's plane at `origin`, looking along -`toward`, the starters of a base reach."""
    from Autodesk.Revit import DB  # Lazy import
    deepest = 0.0
    for r in host_rebars(host):
        p = r.LookupParameter(u'NOSA_Rebar_Layer')
        if p is None or (p.AsString() or u'').strip().lower() not in STARTER_LAYERS:
            continue
        bb = r.get_BoundingBox(None)
        if bb is None:
            continue
        for x in (bb.Min.X, bb.Max.X):
            for y in (bb.Min.Y, bb.Max.Y):
                deepest = max(deepest, -_mm((DB.XYZ(x, y, origin.Z) - origin).DotProduct(toward)))
    return deepest


def _section(title, kind, origin, right, up, half_w, half_h, near, far):
    return {'title': title, 'kind': kind, 'plan': False, 'origin': origin, 'right': right.Normalize(),
            'up': up.Normalize(), 'half_w': half_w, 'half_h': half_h, 'near': near, 'far': far,
            'size': (2.0 * half_w, 2.0 * half_h)}


def _plan(title, kind, level, box, cut_z, bottom_z, margin=500.0):
    return {'title': title, 'kind': kind, 'plan': True, 'level': level, 'box': box, 'cut_z': cut_z,
            'bottom_z': bottom_z, 'margin': margin,
            'size': (_mm(box.Max.X - box.Min.X) + 2 * margin, _mm(box.Max.Y - box.Min.Y) + 2 * margin)}


def _level_of(doc, element):
    from Autodesk.Revit import DB  # Lazy import
    for getter in (lambda: element.LevelId,
                   lambda: element.get_Parameter(DB.BuiltInParameter.STAIRS_BASE_LEVEL_PARAM).AsElementId(),
                   lambda: element.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).AsElementId()):
        try:
            level = doc.GetElement(getter())
            if isinstance(level, DB.Level):
                return level
        except Exception:
            continue
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
    return levels[0] if levels else None


def _local_axes(element):
    from Autodesk.Revit import DB  # Lazy import
    try:
        x = element.HandOrientation
        y = element.FacingOrientation
        if x.GetLength() > 0.5 and y.GetLength() > 0.5:
            return DB.XYZ(x.X, x.Y, 0).Normalize(), DB.XYZ(y.X, y.Y, 0).Normalize()
    except Exception:  # nosa-lint: disable=NOSA006 - not a family instance: global axes
        pass
    return DB.XYZ.BasisX, DB.XYZ.BasisY


LINK_LEAD_MM = 20.0          # a curved beam's section cut this far in front of the link it shows


def _arc_box(arc, width_mm, box):
    """
    Plan box of a curved beam from its arc, half its width either side (Revit's own box of an arc beam ran 6 m
    deep for a 2 m rise, user 2026-10-12: half the plan blank).
    """
    from Autodesk.Revit import DB  # Lazy import
    pts = []
    for p in arc.Tessellate():
        radial = DB.XYZ(p.X - arc.Center.X, p.Y - arc.Center.Y, 0.0).Normalize()
        for side in (-1.0, 1.0):
            pts.append(p + radial.Multiply(side * _ft(width_mm / 2.0)))
    if not pts:
        return box
    out = DB.BoundingBoxXYZ()
    out.Min = DB.XYZ(min(q.X for q in pts), min(q.Y for q in pts), box.Min.Z)
    out.Max = DB.XYZ(max(q.X for q in pts), max(q.Y for q in pts), box.Max.Z)
    return out


def _link_parameters(arc, rebars):
    """Normalised arc parameters of a curved beam's links (bars of layer 'stirrup'), from their centres."""
    from Autodesk.Revit import DB  # Lazy import
    out = []
    for r in rebars:
        p = r.LookupParameter(u'NOSA_Rebar_Layer')
        if p is None or not (p.AsString() or u'').startswith(u'stirrup'):
            continue
        for i in range(r.NumberOfBarPositions):
            try:
                curves = list(r.GetTransformedCenterlineCurves(
                    False, False, False, DB.Structure.MultiplanarOption.IncludeOnlyPlanarCurves, i))
                pts = [c.Evaluate(0.5, True) for c in curves]
                centre = DB.XYZ(sum(q.X for q in pts) / len(pts), sum(q.Y for q in pts) / len(pts), 0.0)
                flat = DB.XYZ(centre.X, centre.Y, arc.Center.Z)
                out.append(arc.ComputeNormalizedParameter(arc.Project(flat).Parameter))
            except Exception:
                continue
    return out


CONGESTED_SCALE = 10           # a congested section's own scale (SMDSC 4th ed. 4.2.1)
CONGESTED_CLEAR_MM = 300.0     # a congested station this close to a section already drawn is shown by it


def _clear_cut(solid, centre, right, other, lo, hi, olo, ohi):
    """The point a section across `right` goes through: nearest the middle where its line meets no opening."""
    from Autodesk.Revit import DB  # Lazy import
    import view_plan
    base = centre - other.Multiply(centre.DotProduct(other))
    for offset in view_plan.section_offsets(olo, ohi):
        point = base + other.Multiply(offset)
        if solid is None:
            return point
        a = point - right.Multiply(point.DotProduct(right) - lo + 1.0)
        b = point + right.Multiply(hi - point.DotProduct(right) + 1.0)
        try:
            hits = solid.IntersectWithCurve(DB.Line.CreateBound(a, b), DB.SolidCurveIntersectionOptions())
            if hits.SegmentCount == 1:
                return point
        except Exception:
            return point
    return centre


def view_specs(doc, hosts, re_engine, beam_rebar=None, stair_host=None):
    """The view set of one element (or one line of beam spans), in view_plan's kinds."""
    from Autodesk.Revit import DB  # Lazy import
    host = hosts[0]
    kind = host_kind(host)
    z_axis = DB.XYZ.BasisZ
    specs = []
    if kind == 'column':
        box = _box(host, re_engine)
        x, y = _local_axes(host)
        if x.CrossProduct(y).Z < 0:
            y = y.Negate()
        centre = (box.Min + box.Max).Multiply(0.5)
        wx = _mm(_extent(box, x)[1] - _extent(box, x)[0])
        wy = _mm(_extent(box, y)[1] - _extent(box, y)[0])
        height = _mm(box.Max.Z - box.Min.Z)
        # drawn as a plan cut through the column looking down (SMDSC): Revit leaves a column out of a horizontal
        # section (user 2026-10-12: no concrete in C1's section)
        spec = _section(u'Section', 'member_section', centre, x, y, wx / 2 + 150, wy / 2 + 150, 0.0, 60.0)
        spec.update({'as_plan': True, 'level': _level_of(doc, host), 'box': box, 'cut_z': _mm(centre.Z),
                     'bottom_z': _mm(centre.Z) - 60.0, 'margin': 150.0})
        specs.append(spec)
        # the whole column in the view's depth, cut by neither plane: both elevations drawn alike (user 2026-10-12:
        # B came out shaded and A blank)
        specs.append(_section(u'Elevation A', 'column_elevation', centre, x, z_axis, wx / 2 + 300,
                              height / 2 + 700, wy / 2 + 60, wy / 2 + 60))
        specs.append(_section(u'Elevation B', 'column_elevation', centre, y, z_axis, wy / 2 + 300,
                              height / 2 + 700, wx / 2 + 60, wx / 2 + 60))
    elif kind == 'beam' and beam_rebar.get_beam_arc(host) is not None:
        # T8.58 curved beam: no plane holds it, so a plan of it (its arc bars) and radial sections
        arc = beam_rebar.get_beam_arc(host)
        # Revit's own box: the solid's edge ends miss the bulge of the arc (24 of 34 links fell outside the plan)
        box = host.get_BoundingBox(None) or _box(host, re_engine)
        z_mid = (box.Min.Z + box.Max.Z) / 2.0
        depth = _mm(box.Max.Z - box.Min.Z)
        width = _mm(host.Symbol.LookupParameter(u'b').AsDouble()) if host.Symbol.LookupParameter(u'b') else 300.0
        top = _mm(box.Max.Z)
        plan = _plan(u'Plan', 'plan', _level_of(doc, host), _arc_box(arc, width, box), top + 200.0,
                     _mm(box.Min.Z) - 200.0)
        plan['medium'] = True      # at Coarse Revit draws a beam in plan as its stick line only (user 2026-10-12)
        specs.append(plan)
        links = _link_parameters(arc, host_rebars(host))
        for letter, t in ((u'1', 0.5), (u'2', 0.12)):
            if links:
                # through a link, so the section shows one (user 2026-10-12: 5-5 and 6-6 fell between them)
                t = min(links, key=lambda u: abs(u - t))
            p = arc.Evaluate(t, True)
            tangent = arc.ComputeDerivatives(t, True).BasisX.Normalize()
            across = DB.XYZ(-tangent.Y, tangent.X, 0.0).Normalize()
            p = p + across.CrossProduct(z_axis).Normalize().Multiply(_ft(LINK_LEAD_MM))
            spec = _section(u'Section {0}-{0}'.format(letter), 'member_section', DB.XYZ(p.X, p.Y, z_mid), across,
                            z_axis, width / 2 + 150, depth / 2 + 150, 0.0, 60.0)
            spec['letter'] = letter              # its mark, named, on the plan
            specs.append(spec)
    elif kind == 'beam':
        axes = [beam_rebar._clamp_axis_to_bbox(beam_rebar.get_beam_axis(h), h) for h in hosts]
        d = axes[0].Direction.Normalize()
        w = z_axis.CrossProduct(d).Normalize()
        origin = axes[0].GetEndPoint(0)
        params = [(a.GetEndPoint(i) - origin).DotProduct(d) for a in axes for i in (0, 1)]
        boxes = [_box(h, re_engine) for h in hosts]
        z0 = min(b.Min.Z for b in boxes)
        z1 = max(b.Max.Z for b in boxes)
        lo, hi = min(params), max(params)
        width = _mm(_extent(boxes[0], w)[1] - _extent(boxes[0], w)[0])
        mid = origin + d.Multiply((lo + hi) / 2.0)
        mid = DB.XYZ(mid.X, mid.Y, (z0 + z1) / 2.0)
        depth = _mm(z1 - z0)
        specs.append(_section(u'Elevation', 'elevation', mid, d, z_axis, _mm(hi - lo) / 2 + 600,
                              depth / 2 + 300, 1.0, width / 2 + 60))
        for n, axis in enumerate(axes):
            label = u'' if len(axes) == 1 else u' span {}'.format(n + 1)
            centre = axis.Evaluate(0.5, True)
            centre = DB.XYZ(centre.X, centre.Y, (z0 + z1) / 2.0)
            specs.append(_section(u'Section mid{}'.format(label), 'member_section', centre, w, z_axis,
                                  width / 2 + 150, depth / 2 + 150, 0.0, 60.0))
            near = min(_ft(500.0), axis.Length / 4.0)
            at_support = axis.GetEndPoint(0) + axis.Direction.Multiply(near)
            at_support = DB.XYZ(at_support.X, at_support.Y, (z0 + z1) / 2.0)
            specs.append(_section(u'Section support{}'.format(label), 'member_section', at_support, w,
                                  z_axis, width / 2 + 150, depth / 2 + 150, 0.0, 60.0))
        # T9.8 (SMDSC 4th ed. 4.2.1): where the bars congest a section, a section of its own at 1:10
        from nosa_utils import rebar_qa
        taken = [sp['origin'] for sp in specs if not sp['plan']]
        for h in hosts:
            for (x, y, _z), issues in rebar_qa.congested_stations(doc, h):
                at = DB.XYZ(x, y, (z0 + z1) / 2.0)
                if any(_mm(DB.XYZ(at.X - o.X, at.Y - o.Y, 0.0).GetLength()) < CONGESTED_CLEAR_MM for o in taken):
                    continue
                spec = _section(u'Section congested', 'member_section', at, w, z_axis, width / 2 + 150,
                                depth / 2 + 150, 0.0, 60.0)
                spec['scale'], spec['congested'] = CONGESTED_SCALE, issues
                specs.append(spec)
                taken.append(at)
    elif kind in ('foundation', 'floor'):
        box = _box(host, re_engine)
        x, y = _local_axes(host) if kind == 'foundation' else (DB.XYZ.BasisX, DB.XYZ.BasisY)
        centre = (box.Min + box.Max).Multiply(0.5)
        level = _level_of(doc, host)
        section_kind = 'footing_section' if kind == 'foundation' else 'slab_section'
        faces = set(rebar_face(r, box) for r in host_rebars(host)) if kind == 'floor' else set()
        if len(faces) > 1:
            # a slab with bars in both faces: one plan each (SMDSC 4th ed. 6.2.4, user 2026-10-10: one plan of both
            # mats is hard to read)
            for face, title in ((u'bottom', u'Bottom reinforcement'), (u'top', u'Top reinforcement')):
                spec = _plan(title, 'plan', level, box, _mm(box.Max.Z) + 200.0, _mm(box.Min.Z) - 200.0)
                spec['face'] = face
                specs.append(spec)
        else:
            specs.append(_plan(u'Plan', 'plan', level, box, _mm(box.Max.Z) + 200.0, _mm(box.Min.Z) - 200.0))
        thick = _mm(box.Max.Z - box.Min.Z)
        solid = None
        try:
            solid = re_engine.get_host_solid(host)
        except Exception:
            solid = None
        # their marks look up the plan and to its left (user 2026-10-12)
        for letter, right, other in ((u'A', x.Negate(), y), (u'B', y.Negate(), x)):
            # user 2026-10-11: two real sections (60 mm deep, SMDSC 4th ed. 3.17), not views of the whole slab, through
            # it clear of openings, their marks named A / B on the plans
            lo, hi = _extent(box, right)
            olo, ohi = _extent(box, other)
            origin = _clear_cut(solid, centre, right, other, lo, hi, olo, ohi)
            far = 60.0
            if kind == 'foundation':
                # deep enough for the far row of starters and their links: 60 mm left them all out, the calling-up
                # naming bars the section did not draw (user 2026-10-17, F10)
                far = max(far, _starters_depth(host, origin, right.CrossProduct(z_axis).Normalize()) + 60.0)
            spec = _section(u'Section {0}-{0}'.format(letter), section_kind, origin, right, z_axis,
                            _mm(hi - lo) / 2 + 300, thick / 2 + 300, 0.0, far)
            spec['letter'] = letter
            specs.append(spec)
    elif kind == 'wall':
        box = _box(host, re_engine)
        line = host.Location.Curve
        d = line.Direction.Normalize()
        n = z_axis.CrossProduct(d).Normalize()
        centre = line.Evaluate(0.5, True)
        centre = DB.XYZ(centre.X, centre.Y, (box.Min.Z + box.Max.Z) / 2.0)
        height = _mm(box.Max.Z - box.Min.Z)
        thick = _mm(host.Width)
        specs.append(_section(u'Elevation', 'elevation', centre, d, z_axis, _mm(line.Length) / 2 + 300,
                              height / 2 + 700, 1.0, thick / 2 + 60))
        solid = None
        try:
            solid = re_engine.get_host_solid(host)
        except Exception:
            solid = None
        # through the wall clear of its openings (user 2026-10-11: the section fell in the opening)
        dlo, dhi = _extent(box, d)
        cut = _clear_cut(solid, centre, z_axis, d, box.Min.Z, box.Max.Z, dlo, dhi)
        specs.append(_section(u'Section', 'wall_section', DB.XYZ(cut.X, cut.Y, centre.Z), n, z_axis,
                              thick / 2 + 300, height / 2 + 700, 0.0, 60.0))
    elif kind == 'stairs':
        data = stair_host.read_stairs(doc, host)
        box = _box(host, re_engine) if host.get_BoundingBox(None) is not None else None
        for i, run in enumerate(data['runs']):
            frame = run['frame']
            s_lo = run['lower']['s_far'] if run['lower']['kind'] == 'landing' else 0.0
            s_hi = run['upper']['s_far'] if run['upper']['kind'] == 'landing' else run['length']
            v_mid = (run['v_min'] + run['v_max']) / 2.0
            z_lo = run['lower']['bottom'] - 300.0
            z_hi = run['upper']['top']
            origin = frame.xyz((s_lo + s_hi) / 2.0, v_mid, (z_lo + z_hi) / 2.0)
            right = frame.u
            specs.append(_section(u'Flight {} section'.format(i + 1), 'stair_section', origin, right,
                                  z_axis, (s_hi - s_lo) / 2 + 400, (z_hi - z_lo) / 2 + 400, 1.0,
                                  (run['v_max'] - run['v_min']) / 2 + 60))
        if box is not None:
            specs.append(_plan(u'Plan', 'stair_plan', _level_of(doc, host), box,
                               _mm(box.Max.Z) + 200.0, _mm(box.Min.Z) - 200.0, margin=400.0))
    number = 1
    for spec in specs:
        # SMDSC 4th ed. 3.18 / 4th ed. Fig. 6.24 (user 2026-10-11): member sections numbered 1-1, 2-2 ... on the drawing,
        # each referenced on the elevation it cuts
        if not spec['plan'] and spec['kind'] in ('member_section', 'wall_section') and not spec.get('letter'):
            spec['letter'] = u'{}'.format(number)
            spec['title'] = u'Section {0}-{0}'.format(number)
            number += 1
    return specs


_PLURAL = {'column': u'Columns', 'beam': u'Beams', 'foundation': u'Foundations', 'floor': u'Slabs',
           'wall': u'Walls', 'stairs': u'Stairs'}


def _continue_labels(doc, created, group, kind, label):
    """Section numbers and letters carried on across one drawing (1-1 ... then 5-5; A, B, then C, D)."""
    from Autodesk.Revit import DB  # Lazy import
    numbers = [e for e in created if e[1].get('letter', u'').isdigit()]
    letters = [e for e in created if e[1].get('letter') and not e[1]['letter'].isdigit()]
    for view, spec, _s in numbers:
        spec['letter'] = u'{}'.format(int(spec['letter']) + group['numbers'])
        spec['title'] = u'Section {0}-{0}'.format(spec['letter'])
    for view, spec, _s in letters:
        spec['letter'] = _letter(ord(spec['letter'][0]) - ord(u'A') + group['letters'])
        spec['title'] = u'Section {0}-{0}'.format(spec['letter'])
    group['numbers'] += len(numbers)
    group['letters'] += len(letters)
    for view, spec, _s in created:
        try:
            if (view, spec, _s) in numbers + letters:
                view.Name = _unique_view_name(doc, u'{} {} - {}'.format(_TITLES.get(kind, u''), label,
                                                                        spec['title']))
            # every title says whose view it is ('B1-B3 Elevation'), one member on the drawing too ('W10
            # Elevation', 2026-10-17: a lone wall's read only 'Elevation')
            view.get_Parameter(DB.BuiltInParameter.VIEW_DESCRIPTION).Set(u'{} {}'.format(label, spec['title']))
        except Exception:
            continue


def _letter(index):
    """A ... Z, then AA, AB ... (SMDSC 4th ed. 3.19 omits I and O)."""
    alphabet = [c for c in u'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if c not in u'IO']
    out = u''
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, len(alphabet))
        out = alphabet[rem] + out
    return out


def build_drawings(doc, groups, re_engine, rebar_detailing, view_plan, sheet_numbers, beam_rebar=None,
                   stair_host=None, tag=True):
    """
    T9.7 (user 2026-10-11): the elements of one kind on one drawing, as a consultancy draws them: all their
    views laid out together on shared A1 sheets, marks 01 upwards across the drawing and its sections
    numbered on. groups: [[host, ...]] (one element or one beam line each). Returns one report.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    report = {'views': [], 'sheets': [], 'tags': 0, 'errors': []}
    assign_marks(doc, [h for g in groups for h in g], view_plan, report)
    kinds = []
    placed = []
    for g in groups:
        k = host_kind(g[0])
        if k not in kinds:
            kinds.append(k)
    for kind in kinds:
        batch = [g for g in groups if host_kind(g[0]) == kind]
        rebars = [r for g in batch for h in g for r in host_rebars(h)]
        if rebars:
            t = DB.Transaction(doc, u'NOSA — Marks of the {} drawing'.format(_PLURAL.get(kind, kind)))
            t.Start()
            import rebar_marking
            rebar_marking.renumber_drawing(doc, [r.Id for r in rebars])      # SMDSC 4th ed. 4.5.1: one drawing
            from nosa_utils import rule_flags
            rule_flags.stamp(rebars)                                           # T9.15: bars added by a rule
            t.Commit()
        group = {'pending': [], 'retag': {}, 'hosts': [], 'rebars': [], 'numbers': 0, 'letters': 0,
                 'members': len(batch)}
        for g in batch:
            r = build_element_views(doc, g, re_engine, rebar_detailing, view_plan, sheet_numbers,
                                    beam_rebar=beam_rebar, stair_host=stair_host, tag=tag, sheet_group=group)
            report['views'].extend(r['views'])
            report['tags'] += r['tags']
            report['errors'].extend(r['errors'])
        valid = [e for e in group['pending'] if e[0].IsValidObject]
        if valid:
            report['sheets'].extend(_place_group(doc, kind, valid, group, view_plan, sheet_numbers, report))
            own = set(get_id_value(r.Id) for r in group['rebars'])
            placed.extend((v, sp, s, own, list(group['hosts'])) for v, sp, s in valid)
    # the section marks of the drawings made after a view, out of its elevations and sections (2026-10-17: F10's
    # section head sat on C3's confinement and kicker dimensions)
    # ... and the bars of the other members drawn (user 2026-10-17): hidden, but for those ending in its members
    if placed:
        import rebar_presentation
        t = DB.Transaction(doc, u'NOSA — Other members\' bars and section marks')
        t.Start()
        for v, sp, _s, own, hosts in placed:
            if not v.IsValidObject:
                continue
            if sp.get('as_plan') or not sp.get('plan'):
                _hide_viewers(doc, v)
            rebar_presentation.foreign_bars(doc, v, own, hosts)
        t.Commit()
    return report


def assign_marks(doc, hosts, view_plan, report):
    """
    The members drawn without a Mark get the next free one of their kind (C4, B13, S21, PC2...; user 2026-10-17:
    SMDSC 3.19 - every member referenced), each one reported to be checked against the GA. In a transaction.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    import rebar_presentation

    def mark_of(e):
        p = e.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
        return ((p.AsString() or u'').strip() if p is not None else u''), p
    bare = [h for h in hosts if h is not None and not mark_of(h)[0] and mark_of(h)[1] is not None
            and not mark_of(h)[1].IsReadOnly]
    if not bare:
        return 0
    t = DB.Transaction(doc, u'NOSA — Marks of unmarked members')
    t.Start()
    for h in bare:
        kind = host_kind(h)
        if kind == 'foundation' and rebar_presentation._piles_under(doc, h):
            kind = 'pile_cap'
        taken = [mark_of(e)[0] for e in DB.FilteredElementCollector(doc).OfCategoryId(h.Category.Id)
                 .WhereElementIsNotElementType()]
        mark = view_plan.next_mark(view_plan.MARK_PREFIX.get(kind, u'M'), taken)
        mark_of(h)[1].Set(mark)
        report['errors'].append(u'{} {} had no Mark: given {} - check it against the GA drawings.'.format(
            _TITLES.get(host_kind(h), u'Member'), get_id_value(h.Id), mark))
    t.Commit()
    return len(bare)


def _titleblock(doc):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    found = None
    for symbol in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(
            DB.BuiltInCategory.OST_TitleBlocks):
        if found is None or element_name(symbol) == TITLEBLOCK:
            found = symbol
            if element_name(symbol) == TITLEBLOCK:
                break
    return found


def _place_group(doc, kind, created, group, view_plan, sheet_numbers, report):
    """The views of one drawing on its A1 sheets, with the legends, its notes and the drawing stamped."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    import rc_legends
    titleblock = _titleblock(doc)
    if titleblock is None:
        report['errors'].append(u'No title block in this project: views left off the sheets.')
        return []
    t = DB.Transaction(doc, u'NOSA — {} drawing'.format(_PLURAL.get(kind, kind)))
    guard = _rollback_on_error()
    options = t.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(guard)
    options.SetClearAfterRollback(True)
    options.SetForcedModalHandling(False)
    t.SetFailureHandlingOptions(options)
    t.Start()
    try:
        legends = rc_legends.ensure(doc)
        for view, spec, _scale in created:
            if spec.get('as_plan'):
                _hide_viewers(doc, view)     # the marks of the views of the members built after this one

        def retag(view):
            fn = group['retag'].get(get_id_value(view.Id))
            if fn is not None:
                fn(view)
        # a drawing of several members goes on to a second sheet rather than below the SMDSC reading scales
        sheets = _place_on_sheets(doc, created, titleblock, sheet_numbers, view_plan,
                                  u'{} reinforcement'.format(_PLURAL.get(kind, kind)), retag=retag, legends=legends,
                                  coarsen=False)
        if sheets:
            import bar_schedules
            bar_schedules.stamp_drawing(doc, group['rebars'], sheets[0], force=True)
            grade = _buildability(doc, group['hosts'], report)
            td_sheet, typical = _typical(doc, group['hosts'], group['rebars'], titleblock, sheet_numbers)
            for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
                if sheet.SheetNumber in sheets:
                    report['errors'].extend(rc_legends.sheet_notes(doc, sheet, group['hosts'], group['rebars'],
                                                                   grade, typical, td_sheet))
        if t.Commit() != DB.TransactionStatus.Committed or guard.errors:
            report['errors'].append(u'{} drawing: rolled back by Revit — {}'.format(
                _PLURAL.get(kind, kind), u'; '.join(guard.errors)))
            return []
        return sheets
    except Exception as e:
        t.RollBack()
        report['errors'].append(u'{} drawing: {}'.format(_PLURAL.get(kind, kind), e))
        return []


def _buildability(doc, hosts, report):
    """T9.12: (score, grade, errors, warnings) of a drawing's members from the reinforcement QA, or None."""
    from nosa_utils import rebar_qa
    try:
        findings = rebar_qa.audit(doc, [h.Id for h in hosts])
    except Exception as e:
        report['errors'].append(u'buildability check not run: {}'.format(e))
        return None
    report['buildability'] = [(f.Host, f.Check, f.Severity, f.Issue) for f in findings]
    return rebar_qa.buildability(findings)


def _number_in_reading_order(doc, created, kind, label):
    """
    The numbered sections renumbered 1, 2 ... in the order a reader meets them on the elevation they cut
    (left to right on a beam, top down on a column; Revit may draw an elevation looking either way along the
    member), renamed to match and put in that order for the sheet.
    """
    from Autodesk.Revit import DB  # Lazy import
    elevations = [v for v, sp, _s in created if not sp['plan'] and sp['kind'] in ('elevation', 'column_elevation')]
    numbered = [(v, sp, sc) for v, sp, sc in created if sp.get('letter') and sp['kind'] in ('member_section',
                                                                                           'wall_section')]
    if not elevations or len(numbered) < 2:
        return created
    right = elevations[0].RightDirection
    column = any(sp['kind'] == 'column_elevation' for _v, sp, _s in created)
    order = sorted(numbered, key=lambda e: -e[1]['origin'].Z if column else e[1]['origin'].DotProduct(right))
    for n, (view, spec, _scale) in enumerate(order, 1):
        spec['letter'] = u'{}'.format(n)
        spec['title'] = u'Section {0}-{0}'.format(n)
        try:
            view.Name = u'{} - {}'.format(view.Name.split(u' - ')[0], u'tmp {}'.format(n))
        except Exception:
            pass
    for view, spec, _scale in order:
        try:
            view.Name = _unique_view_name(doc, u'{} {} - {}'.format(_TITLES.get(kind, u''), label, spec['title']))
            view.get_Parameter(DB.BuiltInParameter.VIEW_DESCRIPTION).Set(spec['title'])
        except Exception:
            continue
    rest = [e for e in created if e not in numbered]
    return rest + order


def section_refs(created, view, spec):
    """[(origin, number, the way it looks)] of the numbered member sections an elevation should reference."""
    if spec['plan'] or spec['kind'] not in ('elevation', 'column_elevation'):
        return []
    return [(sp['origin'], sp['letter'], v.ViewDirection.Negate()) for v, sp, _s in created
            if sp.get('letter') and sp['kind'] in ('member_section', 'wall_section') and v.IsValidObject]


def rebar_face(rebar, box):
    """'top' or 'bottom': the face of the host (its box) a set's first bar lies nearer."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils import presentation
    try:
        curves = [c for c in rebar.GetTransformedCenterlineCurves(
            False, False, False, DB.Structure.MultiplanarOption.IncludeOnlyPlanarCurves, 0)]
        z = sum(c.Evaluate(0.5, True).Z for c in curves) / float(len(curves))
    except Exception:  # nosa-lint: disable=NOSA006 - no centreline: drawn with the bottom bars
        return u'bottom'
    return presentation.face(z, box.Min.Z, box.Max.Z)


def _show_face(doc, view, rebars, hosts, face):
    """Hide in a slab plan the bars of the other face."""
    from Autodesk.Revit import DB  # Lazy import
    from System.Collections.Generic import List
    boxes = dict((h.Id.ToString(), h.get_BoundingBox(None)) for h in hosts)
    other = List[DB.ElementId]()
    for rebar in rebars:
        box = boxes.get(rebar.GetHostId().ToString())
        if box is not None and rebar_face(rebar, box) != face:
            other.Add(rebar.Id)
    if other.Count:
        view.HideElements(other)


def _view_family_type(doc, family):
    from Autodesk.Revit import DB  # Lazy import
    for vft in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
        if vft.ViewFamily == family:
            return vft
    return None


def _template(doc, name):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if view.IsTemplate and element_name(view) == name:
            return view
    return None


def _create_section(doc, vft, spec):
    from Autodesk.Revit import DB  # Lazy import
    transform = DB.Transform.Identity
    transform.Origin = spec['origin']
    transform.BasisX = spec['right']
    transform.BasisY = spec['up']
    transform.BasisZ = spec['right'].CrossProduct(spec['up']).Normalize()
    box = DB.BoundingBoxXYZ()
    box.Transform = transform
    box.Min = DB.XYZ(-_ft(spec['half_w']), -_ft(spec['half_h']), -_ft(spec['far']))
    box.Max = DB.XYZ(_ft(spec['half_w']), _ft(spec['half_h']), _ft(spec['near']))
    if vft.ViewFamily == DB.ViewFamily.Section:
        return DB.ViewSection.CreateSection(doc, vft.Id, box)
    return DB.ViewSection.CreateDetail(doc, vft.Id, box)


def _create_plan(doc, vft, spec):
    from Autodesk.Revit import DB  # Lazy import
    level = spec['level']
    view = DB.ViewPlan.Create(doc, vft.Id, level.Id)
    rng = view.GetViewRange()
    level_mm = _mm(level.Elevation)
    cut = spec['cut_z'] - level_mm
    bottom = spec['bottom_z'] - level_mm
    for plane, offset in ((DB.PlanViewPlane.TopClipPlane, cut + 100.0), (DB.PlanViewPlane.CutPlane, cut),
                          (DB.PlanViewPlane.BottomClipPlane, bottom),
                          (DB.PlanViewPlane.ViewDepthPlane, bottom)):
        rng.SetLevelId(plane, level.Id)
        rng.SetOffset(plane, _ft(offset))
    view.SetViewRange(rng)
    box = spec['box']
    crop = DB.BoundingBoxXYZ()
    margin = _ft(spec['margin'])
    crop.Min = DB.XYZ(box.Min.X - margin, box.Min.Y - margin, box.Min.Z)
    crop.Max = DB.XYZ(box.Max.X + margin, box.Max.Y + margin, box.Max.Z)
    view.CropBoxActive = True
    view.CropBox = crop
    return view


def _unique_view_name(doc, wanted):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    taken = set(element_name(v) for v in DB.FilteredElementCollector(doc).OfClass(DB.View))
    name, n = wanted, 2
    while name in taken:
        name = u'{} ({})'.format(wanted, n)
        n += 1
    return name


def _hide_datums(doc, view):
    """A member section shows the member only: the grids and levels crossing it are hidden in it."""
    from Autodesk.Revit import DB  # Lazy import
    from System.Collections.Generic import List
    ids = List[DB.ElementId]()
    for cls in (DB.Grid, DB.Level):
        for e in DB.FilteredElementCollector(doc).OfClass(cls):
            if e.CanBeHidden(view):
                ids.Add(e.Id)
    if ids.Count:
        try:
            view.HideElements(ids)
        except Exception:
            from nosa_utils.telemetry import log_swallowed
            log_swallowed(u'rebarautomate', u'hide datums')


def _hide_viewers(doc, view):
    """The section marks of the other views crossing a member section drawn as a plan."""
    from Autodesk.Revit import DB  # Lazy import
    from System.Collections.Generic import List
    from nosa_utils.revit_helpers import get_id_value
    viewers = set((int(DB.BuiltInCategory.OST_Viewers), int(DB.BuiltInCategory.OST_Views)))
    for e in DB.FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType():
        try:
            if e.Category is None or get_id_value(e.Category.Id) not in viewers or e.Id == view.Id \
                    or not e.CanBeHidden(view):
                continue
            ids = List[DB.ElementId]()
            ids.Add(e.Id)
            view.HideElements(ids)
        except Exception:
            continue


def hide_section_marks(view):
    """
    No section marks in the elevations and sections of a member (user brief 2026-10-10: Revit puts their
    heads at the ends of the section's crop, right on the calling-up under a beam); each section is told by
    its title. On the RC template when it controls the annotation visibility, else on the view.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    doc = view.Document
    cat = DB.ElementId(DB.BuiltInCategory.OST_Sections)
    target = view
    template = doc.GetElement(view.ViewTemplateId) if view.ViewTemplateId != DB.ElementId.InvalidElementId else None
    if template is not None:
        free = set(get_id_value(i) for i in template.GetNonControlledTemplateParameterIds())
        if int(DB.BuiltInParameter.VIS_GRAPHICS_ANNOTATION) not in free:
            target = template
    try:
        if not target.GetCategoryHidden(cat):
            target.SetCategoryHidden(cat, True)
        return True
    except Exception:
        from nosa_utils.telemetry import log_swallowed
        log_swallowed(u'rebarautomate', u'hide_section_marks')
        return False


def ensure_coarse(view):
    """
    Detail level Coarse (user decision 2026-10-10, replacing Fine of 2026-10-06): a bar is one thick line
    and a cut bar a filled dot to scale (IStructE SMDSC 4th ed. 3.10), legible on A1 and reduced to A3. When the
    view template controls the detail level, the RC template itself is set; otherwise the view. In a
    transaction; True when it is Coarse.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    doc = view.Document
    template = doc.GetElement(view.ViewTemplateId) if view.ViewTemplateId != DB.ElementId.InvalidElementId else None
    target = view
    if template is not None:
        free = set(get_id_value(i) for i in template.GetNonControlledTemplateParameterIds())
        if int(DB.BuiltInParameter.VIEW_DETAIL_LEVEL) not in free:
            target = template
    try:
        if target.DetailLevel != DB.ViewDetailLevel.Coarse:
            target.DetailLevel = DB.ViewDetailLevel.Coarse
        return True
    except Exception:
        from nosa_utils.telemetry import log_swallowed
        log_swallowed(u'rebarautomate', u'ensure_coarse')
        return False


def _apply_template_and_scale(view, template, scale):
    from Autodesk.Revit import DB  # Lazy import
    if template is not None:
        view.ViewTemplateId = template.Id
    try:
        view.Scale = scale
    except Exception:
        # this template fixes the scale: copy its settings instead of linking it
        view.ViewTemplateId = DB.ElementId.InvalidElementId
        if template is not None:
            view.ApplyViewTemplateParameters(template)
        view.Scale = scale
    ensure_coarse(view)


def _show_framing(doc, view):
    """
    The beam itself in a curved beam's plan (user 2026-10-12): the RC plan template hides the framing subcategories
    (Primary, Secondary ...) so slab plans show no beams; this view shows them, not their stick symbols.
    """
    from Autodesk.Revit import DB  # Lazy import
    cat = DB.Category.GetCategory(doc, DB.BuiltInCategory.OST_StructuralFraming)
    for sub in cat.SubCategories:
        if sub.Name in (u'Stick Symbols', u'Location Lines', u'Hidden Faces'):
            continue
        try:
            if view.GetCategoryHidden(sub.Id):
                view.SetCategoryHidden(sub.Id, False)
        except Exception:
            continue


def _detach_template(view, template):
    """The view keeps its template's settings but no longer follows it (its own detail level)."""
    from Autodesk.Revit import DB  # Lazy import
    view.ViewTemplateId = DB.ElementId.InvalidElementId
    if template is not None:
        view.ApplyViewTemplateParameters(template)


def _rollback_on_error():
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


def _column_above(doc, column):
    """True when another column stands on this one (its base within 100 mm of this top, over its plan)."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    bb = column.get_BoundingBox(None)
    if bb is None:
        return False
    tol = 100.0 / _FT
    for c in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StructuralColumns)             .WhereElementIsNotElementType():
        if get_id_value(c.Id) == get_id_value(column.Id):
            continue
        b = c.get_BoundingBox(None)
        if b is not None and abs(b.Min.Z - bb.Max.Z) < tol and b.Min.X < bb.Max.X and b.Max.X > bb.Min.X                 and b.Min.Y < bb.Max.Y and b.Max.Y > bb.Min.Y:
            return True
    return False


def _typical(doc, hosts, rebars, titleblock, sheet_numbers=None):
    """
    T9.21: the typical details these members call for (their kinds, the bar layers on them, piles under a cap),
    placed on the typical details drawing - made, when missing, with the next of the numbers reserved for this run
    (sheet_numbers; 2026-10-17: it took a free number the walls drawing then found in use). (its number,
    [(key, model detail)]).
    """
    import rc_legends
    import rebar_presentation
    from nosa_utils import typical_details
    layers = set()
    for r in rebars:
        p = r.LookupParameter(u'NOSA_Rebar_Layer')
        if p is not None and p.AsString():
            layers.add(p.AsString())
    piled = any(host_kind(h) == 'foundation' and rebar_presentation._piles_under(doc, h) for h in hosts)
    flags = [u'column_top'] if any(host_kind(h) == 'column' and not _column_above(doc, h) for h in hosts) else []
    keys = typical_details.needed([host_kind(h) for h in hosts], layers, piled, flags)
    try:
        return rc_legends.typical_details(doc, keys, titleblock, number=(
            (lambda: sheet_numbers.pop(0)) if sheet_numbers else None))
    except Exception:
        from nosa_utils.telemetry import log_swallowed
        log_swallowed(u'rebarautomate', u'typical details')
        return u'', []


def _new_sheet(doc, titleblock, number, name):
    from Autodesk.Revit import DB  # Lazy import
    sheet = DB.ViewSheet.Create(doc, titleblock.Id)
    sheet.SheetNumber = number
    sheet.Name = name
    return sheet


def _title_on_sheet(view):
    from Autodesk.Revit import DB  # Lazy import
    try:
        return view.get_Parameter(DB.BuiltInParameter.VIEW_DESCRIPTION).AsString() or u''
    except Exception:
        return u''


def _streams(created):
    """
    The views of a drawing in reading order (user 2026-10-12): each member's plans and elevations (A before B), then
    its sections in number order, left to right; a drawing of several columns puts all the elevations on one line,
    level with each other, and all the sections on the next.
    """
    def order(e):
        letter = e[1].get('letter') or u''
        return (0, int(letter), u'') if letter.isdigit() else (1, len(letter), letter)

    def main_key(e):
        return (not e[1]['plan'], e[1]['title'])
    indexed = list(enumerate(created))
    sections = [e for e in indexed if not e[1][1]['plan'] and e[1][1].get('letter')]
    mains = [e for e in indexed if e not in sections]
    members = []
    for _i, (_v, sp, _s) in indexed:
        if sp.get('member') not in members:
            members.append(sp.get('member'))
    if any(e[1][1]['kind'] == 'column_elevation' for e in indexed) and len(members) > 1:
        lines = [(mains, []), ([], sections)]
    else:
        lines = [([e for e in mains if e[1][1].get('member') == m], [e for e in sections if e[1][1].get('member') == m])
                 for m in members]
    streams = []
    for main, secs in lines:
        stream = sorted(main, key=lambda e: (e[1][1].get('member') or u'', main_key(e[1]))) + \
            sorted(secs, key=lambda e: order(e[1]))
        if stream:
            streams.append([i for i, _e in stream])
    return streams


DATUM_Z_FT = 0.0     # the model level every elevation of a drawing is lined up on


def _datum_depth(port, view):
    """Paper depth (mm) of the model datum below the top of an elevation's viewport, or None."""
    from Autodesk.Revit import DB  # Lazy import
    try:
        t = port.GetProjectionToSheetTransform()
        local = view.CropBox.Transform.Inverse.OfPoint(DB.XYZ(view.Origin.X, view.Origin.Y, DATUM_Z_FT))
        y = t.OfPoint(local.Divide(view.Scale)).Y
        return _mm(port.GetBoxOutline().MaximumPoint.Y - y)
    except Exception:
        return None


def _place_on_sheets(doc, created, titleblock, sheet_numbers, view_plan, name, retag=None, legends=(),
                     coarsen=True):
    """
    Two passes: drop every view on the first sheet, read its real viewport size (tags and the
    view title included), then pack them. One sheet per element (user brief): while the views
    need a second sheet, the largest section or elevation that can (then plan) goes to its next coarser
    scale (tags re-laid out by `retag`); only then does a view move to another sheet. Every sheet gets the legends
    (layer notation, reinforcement notes) in the corner of the drawing area kept for them
    (IStructE SMDSC 4th ed. 3.7, 4.2.1).
    """
    from Autodesk.Revit import DB  # Lazy import
    sheets = [_new_sheet(doc, titleblock, sheet_numbers.pop(0), name)]
    ports = [DB.Viewport.Create(doc, sheets[0].Id, view.Id, DB.XYZ(_ft(400.0), _ft(300.0), 0.0))
             for view, _spec, _scale in created]
    doc.Regenerate()

    def _size(port):
        from nosa_utils.revit_helpers import element_name
        box = port.GetBoxOutline()
        view = doc.GetElement(port.ViewId)
        title = view_plan.title_width_mm(element_name(view) if view is not None else u'', _title_on_sheet(view))
        return (max(_mm(box.MaximumPoint.X - box.MinimumPoint.X), title),
                _mm(box.MaximumPoint.Y - box.MinimumPoint.Y))
    sizes = [_size(port) for port in ports]
    reserved = ()
    if legends:
        import rc_legends
        reserved = (rc_legends.LEGEND_BOX,)
    streams = _streams(created)
    anchors = dict((i, _datum_depth(ports[i], created[i][0])) for i in range(len(created))
                   if created[i][1]['kind'] in ('elevation', 'column_elevation'))

    def place():
        rows = view_plan.layout_rows([[(sizes[i][0], sizes[i][1], anchors.get(i)) for i in st] for st in streams],
                                     reserved=reserved)
        out = [None] * len(created)
        for i, r in zip([i for st in streams for i in st], rows):
            out[i] = r
        return out
    placement = place()
    stuck = set()
    for _attempt in range(12 if coarsen else 0):
        if max(p[0] for p in placement) == 0:
            break
        candidates = [i for i, (view, spec, _s) in enumerate(created)
                      if i not in stuck and view_plan.coarser_scale(spec['kind'], view.Scale)]
        if not candidates:
            break
        # the sections and elevations give way before the plans, which carry most of the calling-up
        i = max(candidates, key=lambda k: (created[k][1].get('plan') is not True, sizes[k][0] * sizes[k][1]))
        view, spec = created[i][0], created[i][1]
        try:
            view.Scale = view_plan.coarser_scale(spec['kind'], view.Scale)
        except Exception:  # nosa-lint: disable=NOSA006 - its template fixes the scale: leave it
            stuck.add(i)
            continue
        if retag is not None:
            retag(view)
        doc.Regenerate()
        sizes[i] = _size(ports[i])
        if i in anchors:
            anchors[i] = _datum_depth(ports[i], view)
        placement = place()
    for i, (sheet_index, cx, cy) in enumerate(placement):
        while sheet_index >= len(sheets):
            sheets.append(_new_sheet(doc, titleblock, sheet_numbers.pop(0),
                                     u'{} ({})'.format(name, len(sheets) + 1)))
        centre = DB.XYZ(_ft(cx), _ft(cy), 0.0)
        if sheet_index == 0:
            ports[i].SetBoxCenter(centre)
        else:
            view_id = ports[i].ViewId
            doc.Delete(ports[i].Id)
            ports[i] = DB.Viewport.Create(doc, sheets[sheet_index].Id, view_id, centre)
    for i, port in enumerate(ports):
        # Revit numbers the viewports of a sheet 1, 2 ... itself: clear of the section numbers first
        try:
            port.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER).Set(u'tmp{}'.format(i + 1))
        except Exception:
            pass
    for i, (port, (_view, spec, _scale)) in enumerate(zip(ports, created)):
        if not spec.get('letter'):
            # out of the way of the section numbers 1, 2 ... (detail numbers are unique on a sheet)
            try:
                port.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER).Set(u'V{}'.format(i + 1))
            except Exception:
                pass
    for port, (_view, spec, _scale) in zip(ports, created):
        if spec.get('letter'):
            # the section's mark on the plans reads A / B, its title Section A-A (SMDSC 4th ed. 3.17)
            try:
                port.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER).Set(spec['letter'])
            except Exception:
                from nosa_utils.telemetry import log_swallowed
                log_swallowed(u'rebarautomate', u'section letter')
    if legends:
        import rc_legends
        for sheet in sheets:
            rc_legends.place(doc, sheet, legends)
    return [s.SheetNumber for s in sheets]


def build_element_views(doc, hosts, re_engine, rebar_detailing, view_plan, sheet_numbers,
                        beam_rebar=None, stair_host=None, place_on_sheets=True, tag=True, sheet_group=None):
    """
    Views (and sheets) of one element / beam line. sheet_numbers: a list the next numbers are
    popped from. Returns {'views': [names], 'sheets': [numbers], 'tags': n, 'errors': [...]}.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name, get_id_value
    kind = host_kind(hosts[0])
    label = host_label(hosts[0]) if len(hosts) == 1 else u'{}-{}'.format(host_label(hosts[0]),
                                                                         host_label(hosts[-1]))
    report = {'views': [], 'sheets': [], 'tags': 0, 'errors': []}
    specs = view_specs(doc, hosts, re_engine, beam_rebar, stair_host)
    if not specs:
        report['errors'].append(u'{} {}: nothing to draw.'.format(_TITLES.get(kind, u'Element'), label))
        return report
    detail_vft = _view_family_type(doc, DB.ViewFamily.Detail)
    # a lettered section shows its mark, named on the sheet, in the plans (user 2026-10-11)
    section_vft = _view_family_type(doc, DB.ViewFamily.Section) or detail_vft
    plan_vft = _view_family_type(doc, DB.ViewFamily.StructuralPlan) or \
        _view_family_type(doc, DB.ViewFamily.FloorPlan)
    section_template = _template(doc, SECTION_TEMPLATE)
    plan_template = _template(doc, PLAN_TEMPLATE)
    titleblock = None
    for symbol in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(
            DB.BuiltInCategory.OST_TitleBlocks):
        if titleblock is None or element_name(symbol) == TITLEBLOCK:
            titleblock = symbol
            if element_name(symbol) == TITLEBLOCK:
                break
    rebars = [r for h in hosts for r in host_rebars(h)]

    if tag and rebars:
        try:
            import rebar_presentation
            rebar_presentation.bind(doc)       # the one-calling-up-per-mark parameters (SMDSC 4th ed. 4.2.1)
        except Exception as e:
            report['errors'].append(u'presentation parameters not bound: {}'.format(e))
    guard = _rollback_on_error()
    t = DB.Transaction(doc, u'NOSA — Create Views {} {}'.format(_TITLES.get(kind, u''), label))
    options = t.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(guard)
    options.SetClearAfterRollback(True)
    options.SetForcedModalHandling(False)
    t.SetFailureHandlingOptions(options)
    t.Start()
    created = []
    scales = [spec.get('scale') or view_plan.choose_scale('footing_section' if kind == 'foundation' else spec['kind'],
                                                          spec['size'][0], spec['size'][1]) for spec in specs]
    if kind == 'foundation':
        scales = [max(scales)] * len(scales)      # plan and sections at one scale (user 2026-10-12)
    try:
        for spec, scale in zip(specs, scales):
            spec['member'] = label
            if spec['plan'] or spec.get('as_plan'):
                if plan_vft is None or spec['level'] is None:
                    report['errors'].append(u'{}: no plan view type or level.'.format(spec['title']))
                    continue
                view = _create_plan(doc, plan_vft, spec)
                _apply_template_and_scale(view, plan_template, scale)
                if spec.get('medium'):
                    _detach_template(view, plan_template)
                    view.DetailLevel = DB.ViewDetailLevel.Medium
                    _show_framing(doc, view)
                if spec.get('as_plan'):
                    _hide_datums(doc, view)
                if spec.get('face'):
                    _show_face(doc, view, rebars, hosts, spec['face'])
            else:
                if detail_vft is None:
                    report['errors'].append(u'No detail view type in this project.')
                    break
                view = _create_section(doc, section_vft if spec.get('letter') else detail_vft, spec)
                _apply_template_and_scale(view, section_template, scale)
                hide_section_marks(view)
                if spec['kind'] in ('member_section', 'wall_section'):
                    _hide_datums(doc, view)
            view.Name = _unique_view_name(doc, u'{} {} - {}'.format(_TITLES.get(kind, u''), label,
                                                                     spec['title']))
            try:
                # the drawing names the member: each view's title on it is just its own (user 2026-10-11)
                view.get_Parameter(DB.BuiltInParameter.VIEW_DESCRIPTION).Set(spec['title'])
            except Exception:
                from nosa_utils.telemetry import log_swallowed
                log_swallowed(u'rebarautomate', u'title on sheet')
            for rebar in rebars:
                try:
                    rebar.SetUnobscuredInView(view, True)
                except Exception:
                    continue
            created.append((view, spec, scale))
        doc.Regenerate()
        for view, spec, _scale in created:
            if spec.get('as_plan'):
                _hide_viewers(doc, view)
        created = _number_in_reading_order(doc, created, kind, label)
        if sheet_group is not None:
            _continue_labels(doc, created, sheet_group, kind, label)
        if rebars and place_on_sheets and sheet_group is None:
            # SMDSC 4th ed. 4.5.1: these members make one new drawing, so their marks run 01 upwards across it —
            # before the calling-up, whose callout texts carry the marks
            import rebar_marking
            report['marks'] = rebar_marking.renumber_drawing(doc, [r.Id for r in rebars]).get('total_positions', 0)
        doc.Regenerate()
        if tag and rebars:
            # T8.27, SMDSC 4th ed. 6.2.2 / 3.3: typical bars, indicator lines and marks laid out outside the members,
            # before the sheets so each viewport takes its calling-up in
            import rebar_presentation
            from nosa_utils import tag_engine
            mra_type_id = tag_engine.mra_type_id(doc)
            for view, spec, _scale in created:
                rebar_presentation.apply(doc, view, rebars, rebar_detailing, mra_type_id, hosts=hosts,
                                         kind=spec['kind'], sections=section_refs(created, view, spec))
        if sheet_group is not None and tag and rebars:
            # T9.7: the views wait for the drawing of their kind; their calling-up is redone there at a coarser
            # scale when the sheet needs it
            def regroup(view, created=created, rebars=rebars, hosts=hosts, mra_type_id=mra_type_id):
                sp = dict((get_id_value(v.Id), x) for v, x, _s in created).get(get_id_value(view.Id)) or \
                    {'plan': False, 'kind': None}
                rebar_presentation.apply(doc, view, rebars, rebar_detailing, mra_type_id, hosts=hosts,
                                         kind=sp.get('kind'), sections=section_refs(created, view, sp))
            for v, _sp, _sc in created:
                sheet_group['retag'][get_id_value(v.Id)] = regroup
        if sheet_group is not None:
            sheet_group['pending'].extend(created)
            sheet_group['hosts'].extend(hosts)
            sheet_group['rebars'].extend(rebars)
        if place_on_sheets and created and titleblock is not None and sheet_group is None:
            import rc_legends
            legends = rc_legends.ensure(doc)
            retag = None
            if tag and rebars:
                specs_of = dict((get_id_value(v.Id), sp) for v, sp, _sc in created)

                def retag(view):
                    # a view taken to a coarser scale to fit the sheet: its calling-up laid out again at it
                    sp = specs_of.get(get_id_value(view.Id)) or {'plan': False, 'kind': None}
                    rebar_presentation.apply(doc, view, rebars, rebar_detailing, mra_type_id, hosts=hosts,
                                             kind=sp.get('kind'), sections=section_refs(created, view, sp))
            report['sheets'] = _place_on_sheets(doc, created, titleblock, sheet_numbers, view_plan,
                                                u'{} {} reinforcement'.format(_TITLES.get(kind, u''), label),
                                                retag=retag, legends=legends)
            if report['sheets']:
                # SMDSC 4th ed. 4.5.1: the member's bar schedules belong to the drawing it is detailed on
                import bar_schedules
                bar_schedules.stamp_drawing(doc, rebars, report['sheets'][0])
                # SMDSC 4th ed. 3.7 (T9.6): each drawing's notes from what is on it
                td_sheet, typical = _typical(doc, hosts, rebars, titleblock, sheet_numbers)
                for sheet in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
                    if sheet.SheetNumber in report['sheets']:
                        report['errors'].extend(rc_legends.sheet_notes(doc, sheet, hosts, rebars,
                                                                       typical=typical, typical_drawing=td_sheet))
        if tag and rebars and sheet_group is None:
            # T8.27, SMDSC 4th ed. 6.2.2: bars detailed on another drawing, once the views are on their sheets
            own = set(get_id_value(r.Id) for r in rebars)
            for view, _spec, _scale in created:
                rebar_presentation.foreign_bars(doc, view, own, hosts)
    except Exception as e:
        t.RollBack()
        report['errors'].append(u'{} {}: {}'.format(_TITLES.get(kind, u''), label, e))
        report['views'], report['sheets'], report['tags'] = [], [], 0
        return report
    if t.Commit() != DB.TransactionStatus.Committed or guard.errors:
        report['errors'].append(u'{} {}: rolled back by Revit — {}'.format(
            _TITLES.get(kind, u''), label, u'; '.join(guard.errors)))
        report['views'], report['sheets'], report['tags'] = [], [], 0
        return report
    report['views'] = [element_name(v) for v, _s, _sc in created]
    # Revit drops the tags of bars hidden in a view when the transaction commits: count what stays
    report['tags'] = sum(DB.FilteredElementCollector(doc, v.Id).OfCategory(
        DB.BuiltInCategory.OST_RebarTags).GetElementCount() for v, _s, _sc in created)
    return report
