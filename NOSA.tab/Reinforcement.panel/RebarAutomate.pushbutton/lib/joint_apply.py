# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate - beam bars clashing with a column's bars where the beam enters it, resolved after the beams are
reinforced (user 2026-10-28, point 3.2: R1 applied automatically when it meets every check of
nosa_utils.joint_resolution; R2 only with compression proven by the model's forces, which no model carries yet, so
it stays R3; R3 flagged for manual review). Every application is logged: bar, rule, shift.
A shifted bar of a set leaves the set (its position excluded) and becomes a single bar of the same shape, mark and
length at its new place, so the set and its calling-up stay.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

FT = 304.8


def _text(el, name):
    p = el.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def _mark(el):
    from Autodesk.Revit import DB  # Lazy import
    try:
        return (el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString() or u'').strip()
    except Exception:  # nosa-lint: disable=NOSA006 - an element without a mark is named by its id
        return u''


def _dia(doc, r):
    return doc.GetElement(r.GetTypeId()).BarNominalDiameter * FT


def _lines(r, index=None):
    """[(a, b, position)] of the straight legs of a rebar's bars (of one position when index is given)."""
    from Autodesk.Revit import DB  # Lazy import
    from Autodesk.Revit.DB.Structure import MultiplanarOption
    out = []
    for i in ([index] if index is not None else range(r.NumberOfBarPositions)):
        try:
            if not r.DoesBarExistAtPosition(i):       # excluded, or a set's first/last bar left out
                continue
            cs = r.GetTransformedCenterlineCurves(False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves, i)
        except Exception:  # nosa-lint: disable=NOSA006 - a position Revit cannot give is left out
            continue
        for c in cs:
            if isinstance(c, DB.Line):
                out.append((c.GetEndPoint(0), c.GetEndPoint(1), i))
    return out


def _rebars_in(host):
    from Autodesk.Revit.DB.Structure import RebarHostData
    data = RebarHostData.GetRebarHostData(host)
    return list(data.GetRebarsInHost()) if data is not None else []


def _columns_near(doc, beam):
    from Autodesk.Revit import DB  # Lazy import
    bb = beam.get_BoundingBox(None)
    outline = DB.Outline(bb.Min - DB.XYZ(1.0, 1.0, 1.0), bb.Max + DB.XYZ(1.0, 1.0, 1.0))
    return list(DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
                .WhereElementIsNotElementType().WherePasses(DB.BoundingBoxIntersectsFilter(outline)))


def _others_near(doc, beam):
    """(a, b, dia, host id) of the slab and other beam bars around the beam (no links)."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    bb = beam.get_BoundingBox(None)
    outline = DB.Outline(bb.Min - DB.XYZ(1.0, 1.0, 1.0), bb.Max + DB.XYZ(1.0, 1.0, 1.0))
    out = []
    for cat in (DB.BuiltInCategory.OST_Floors, DB.BuiltInCategory.OST_StructuralFraming):
        for host in DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType() \
                .WherePasses(DB.BoundingBoxIntersectsFilter(outline)):
            if host.Id == beam.Id:
                continue
            for r in _rebars_in(host):
                if _text(r, u'NOSA_Rebar_Layer').startswith(u'stirrup'):
                    continue
                for a, b, _i in _lines(r):
                    out.append((a, b, _dia(doc, r), get_id_value(host.Id)))
    return out


def analyse(doc, beam, columns=None, others=None, crossing_check=True):
    """
    The proposals of one beam: [{'beam', 'beam_id', 'layer', 'mark', 'bar_id', 'position', 'y_mm', 'dia',
    'supports', 'rule', 'shift_mm', 'crank_mm', 'support', 'reason', 'checks', 'axis'}] ('axis': the beam's
    across direction, for applying a shift). The model's forces are not read (none carry them): no R2.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils import joint_resolution as jr
    from nosa_utils.revit_helpers import get_id_value
    curve = beam.Location.Curve
    if not isinstance(curve, DB.Line):
        return []
    o = curve.GetEndPoint(0)
    d = (curve.GetEndPoint(1) - o).Normalize()
    w = DB.XYZ(-d.Y, d.X, 0.0).Normalize()
    length = curve.Length * FT
    columns = _columns_near(doc, beam) if columns is None else columns
    others = _others_near(doc, beam) if others is None else others
    rebars = _rebars_in(beam)
    links = [r for r in rebars if _text(r, u'NOSA_Rebar_Layer').startswith(u'stirrup')]
    if not links:
        return []
    ys = [abs((p - o).DotProduct(w)) * FT for a, b, _i in _lines(links[0])[:8] for p in (a, b)]
    if not ys:
        return []
    cage = max(ys) - _dia(doc, links[0]) / 2.0
    supports = []
    for col in columns:
        bb = col.get_BoundingBox(None)
        cx, cy = (bb.Min.X + bb.Max.X) / 2.0, (bb.Min.Y + bb.Max.Y) / 2.0
        if bb.Min.Z > o.Z + 0.01 or bb.Max.Z < o.Z - 1.0:
            continue
        if abs((DB.XYZ(cx, cy, o.Z) - o).DotProduct(w)) * FT > (bb.Max.X - bb.Min.X) * FT / 2.0:
            continue
        along = sorted((DB.XYZ(x, y, o.Z) - o).DotProduct(d) * FT for x in (bb.Min.X, bb.Max.X)
                       for y in (bb.Min.Y, bb.Max.Y))
        if along[-1] < -50.0 or along[0] > length + 50.0:
            continue
        bars = []
        for r in _rebars_in(col):
            if _text(r, u'NOSA_Rebar_Layer') != u'vertical':
                continue
            for a, b, _i in _lines(r):
                if abs((b - a).Normalize().Z) > 0.99:
                    bars.append((a, b, _dia(doc, r)))
        supports.append((col, along[0], along[-1], bars))
    if not supports:
        return []
    supports.sort(key=lambda s: s[1])
    faces = [(s[1], s[2]) for s in supports]
    rows = []
    for layer_name in (u'top', u'bottom'):
        layer, z = [], []
        for r in rebars:
            if _text(r, u'NOSA_Rebar_Layer') != layer_name:
                continue
            for a, b, i in _lines(r):
                if abs((b - a).Normalize().DotProduct(d)) > 0.99:
                    layer.append((round((a - o).DotProduct(w) * FT, 1), _dia(doc, r), _text(r, u'NOSA_Rebar_Mark'),
                                  r, i))
                    z.append(a.Z * FT)
        uniq = {}
        for entry in layer:
            uniq.setdefault(round(entry[0]), entry)
        layer = sorted(uniq.values(), key=lambda e: e[0])
        if not layer:
            continue
        zl = sum(z) / len(z)
        sups = []
        for col, a, b, cbs in supports:
            cys = sorted(set(round((p - o).DotProduct(w) * FT, 1) for p, q, _d in cbs
                             if min(p.Z, q.Z) * FT < zl < max(p.Z, q.Z) * FT
                             and a - 1.0 <= (p - o).DotProduct(d) * FT <= b + 1.0))
            if not cys:
                continue                    # the column above, whose bars start at this level
            cdia = max([cd for _p, _q, cd in cbs] or [20.0])
            toward = -1.0 if (a + b) / 2.0 < length / 2.0 else 1.0
            face = b if toward < 0 else a
            span = [f for f in faces if f != (a, b)]
            sups.append({'name': _mark(col) or str(get_id_value(col.Id)), 'column_bars': cys, 'column_dia': cdia,
                         'forces': None, 'face_mm': face, 'toward': toward,
                         'span_mm': (face, (span[0][0] if toward < 0 else span[-1][1]) if span else face),
                         'zones_mm': []})
        if not sups:
            continue
        par = []
        for a3, b3, dd, hid in others:
            if abs((b3 - a3).Normalize().DotProduct(d)) < 0.99:
                continue
            # at the layer's level: further up or down it cannot meet a shifted bar whatever its y
            if abs((a3.Z + b3.Z) / 2.0 * FT - zl) >= jr.centre_gap_mm(dd, layer[0][1]) - 0.5:
                continue
            # along this beam's own span, not the next beam's bars of the same line lapping at the support
            s0, s1 = sorted(((a3 - o).DotProduct(d) * FT, (b3 - o).DotProduct(d) * FT))
            inner = (faces[0][1], faces[-1][0]) if len(faces) > 1 else (0.0, length)
            if min(s1, inner[1]) - max(s0, inner[0]) < 500.0:
                continue
            yy = (a3 - o).DotProduct(w) * FT
            if abs(yy) < cage + 60.0:
                par.append((round(yy, 1), dd))
        crossing = []
        for a3, b3, dd, hid in others:
            # another beam's bar across this one at its level inside a column: a shift moves the crossing, never
            # clears it (2026-10-28 test with 400 beams: +41 findings, none removed)
            if abs((b3 - a3).Normalize().DotProduct(d)) > 0.1 or abs(b3.Z - a3.Z) * FT > 1.0:
                continue
            if abs((a3.Z + b3.Z) / 2.0 * FT - zl) >= jr.centre_gap_mm(dd, layer[0][1]) - 0.5:
                continue
            at = ((a3 + b3) / 2.0 - o).DotProduct(d) * FT
            if any(a - 1.0 <= at <= b + 1.0 for _c, a, b, _bars in supports):
                crossing.append((round(at), dd, hid))
        for p in jr.propose([(e[0], e[1]) for e in layer], sups, cage, top=layer_name == u'top', parallel=par):
            y, dd, mk, rebar, index = layer[p['bar']]
            if p['rule'] == u'R1' and crossing and crossing_check:
                p = dict(p, rule=u'R3', checks=p['checks'] + [{
                    'check': u'no other beam\'s bars across it at its level in the joint (EC2 8.2(2))', 'ok': False,
                    'value': u'{} crossing bar(s)'.format(len(crossing)), 'limit': u'none'}],
                    reason=p['reason'] + u' - the shift would clear the column bars but not the crossing beam\'s '
                                         u'bars at the same level: manual review')
            rows.append({'beam': _mark(beam) or str(get_id_value(beam.Id)), 'beam_id': get_id_value(beam.Id),
                         'layer': layer_name, 'mark': mk, 'bar_id': get_id_value(rebar.Id), 'position': index,
                         'y_mm': y, 'dia': dd, 'supports': [s['name'] for s in sups], 'rule': p['rule'],
                         'shift_mm': p.get('shift_mm'), 'crank_mm': p.get('crank_mm'), 'support': p.get('support'),
                         'reason': p['reason'], 'checks': p['checks'], 'axis': w})
    return rows


def _shift(doc, rebar, index, w, delta_mm):
    """The bar at this position moved delta_mm across the beam; a set keeps its other bars. Returns the moved id."""
    from Autodesk.Revit import DB  # Lazy import
    move = w.Multiply(delta_mm / FT)
    if rebar.NumberOfBarPositions <= 1:
        DB.ElementTransformUtils.MoveElement(doc, rebar.Id, move)
        return rebar.Id
    before = _lines(rebar, index)[0][0]
    new_id = list(DB.ElementTransformUtils.CopyElement(doc, rebar.Id, DB.XYZ.Zero))[0]
    rebar.SetBarIncluded(False, index)
    new = doc.GetElement(new_id)
    new.GetShapeDrivenAccessor().SetLayoutAsSingle()
    doc.Regenerate()
    at = _lines(new, 0)[0][0]
    DB.ElementTransformUtils.MoveElement(doc, new_id, (before - at) + move)
    return new_id


def resolve(doc, beams, errors, log=None, created=None, crossing_check=True):
    """
    Point 3.2 after the beams are reinforced (in a transaction): R1 shifts applied, R2/R3 reported for manual review.
    errors: the run's messages (one per application and per joint left to review). log: a list the rows go to.
    created: the run's new rebars, a set's shifted bar added. Returns {'R1': applied, 'R3': flagged, 'failed': n}.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    counts = {'R1': 0, 'R3': 0, 'failed': 0}
    for beam in beams:
        try:
            rows = analyse(doc, beam, crossing_check=crossing_check)
        except Exception as e:
            errors.append(u'Beam {}: beam/column joint check failed ({}).'.format(get_id_value(beam.Id), e))
            continue
        for row in rows:
            where = u'Beam {} {} bar {} (y = {:.0f} mm) at {}'.format(
                row['beam'], row['layer'], row['mark'], row['y_mm'], u', '.join(row['supports']))
            if row['rule'] == u'R1':
                rebar = _by_id(doc, row['bar_id'])
                try:
                    with DB.SubTransaction(doc) as st:
                        st.Start()
                        moved = _shift(doc, rebar, row['position'], row['axis'], row['shift_mm'])
                        st.Commit()
                    row['moved_id'] = get_id_value(moved)
                    if created is not None and moved != rebar.Id:
                        created.append(doc.GetElement(moved))
                    row['status'] = u'applied'
                    counts['R1'] += 1
                    errors.append(u'{}: shifted {:+.0f} mm clear of the column bars (R1, SMDSC P2: |shift| <= '
                                  u's/2 and 50 mm, every check met).'.format(where, row['shift_mm']))
                except Exception as e:
                    row['status'] = u'failed'
                    counts['failed'] += 1
                    errors.append(u'{}: R1 shift of {:+.0f} mm not applied ({}); review by hand.'.format(
                        where, row['shift_mm'], e))
            else:
                row['status'] = u'manual review'
                counts['R3'] += 1
                why = row['reason'].split(u' - ', 1)[1] if u' - ' in row['reason'] else u'review by hand'
                errors.append(u'{}: clashes with the column bars (R3): {}.'.format(where, why.rstrip(u'.')))
            if log is not None:
                log.append(dict((k, v) for k, v in row.items() if k != 'axis'))
    return counts


def _by_id(doc, value):
    from nosa_utils.revit_helpers import element_id_from_int
    return doc.GetElement(element_id_from_int(value))
