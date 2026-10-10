# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — IStructE SMDSC 6.2.2 presentation of the bars in one view (T8.27), the rules in
nosa_utils.presentation and nosa_utils.callout_layout: each set lying in the view plane is drawn as one
typical bar (layers drawn over each other show different bars) with a Multi-Rebar Annotation as its indicator
line and the calling-up on its extension outside the member (under a beam in its elevation); the marks of
bars in sections and elevations in rows outside the member with pointers; 'Alt.' / 'Stg.'; a short 30 degree
oblique at curtailed ends; bars detailed on another drawing dashed with 'SEE DRG' (see_drawing, once the
view is on its sheet). Re-running replaces the bars' own annotations in the view. In a transaction.
"""
import re

from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS

from nosa_utils import presentation
from nosa_utils.revit_helpers import get_id_value

_MM_PER_FT = 304.8
LINE_STYLE = u'NOSA Bar Ends'
DRAWING_PARAM = u'NOSA_Rebar_Group'
_OWN_NOTE = re.compile(u'^(\\(\\d+\\)|Alt\\.|Stg\\.|SEE DRG .*)$')
TEXT_PAPER_MM = 2.5


def _xy(view, p):
    return (p.DotProduct(view.RightDirection) * _MM_PER_FT, p.DotProduct(view.UpDirection) * _MM_PER_FT)


def _point(view, xy, like):
    """Model point at view coordinates xy (mm), in the plane of `like`."""
    depth = like.DotProduct(view.ViewDirection)
    return (view.RightDirection.Multiply(xy[0] / _MM_PER_FT) + view.UpDirection.Multiply(xy[1] / _MM_PER_FT)
            + view.ViewDirection.Multiply(depth))


def _text(element, name):
    p = element.LookupParameter(name)
    return (p.AsString() or u'') if p is not None and p.HasValue else u''


def mark_of(rebar):
    mark = _text(rebar, u'NOSA_Rebar_Mark')
    if not mark:
        p = rebar.get_Parameter(DB.BuiltInParameter.REBAR_ELEM_SCHEDULE_MARK)
        mark = (p.AsString() or u'') if p is not None else u''
    return mark


def _centreline(rebar, i):
    try:
        return [c for c in rebar.GetTransformedCenterlineCurves(
            False, False, False, DBS.MultiplanarOption.IncludeOnlyPlanarCurves, i)]
    except Exception:
        return []


def describe(view, rebar):
    """The set in the view frame (nosa_utils.presentation's dict) plus its 3D data, or None."""
    try:
        n = rebar.NumberOfBarPositions
    except Exception:
        return None
    first = _centreline(rebar, 0)
    lines = [c for c in first if isinstance(c, DB.Line)]
    if not lines:
        return None
    main = max(lines, key=lambda c: c.Length)
    along = main.Direction
    last = _centreline(rebar, n - 1) if n > 1 else first
    last_lines = [c for c in last if isinstance(c, DB.Line)]
    last_main = max(last_lines, key=lambda c: c.Length) if last_lines else main
    p0, p1 = _xy(view, main.Evaluate(0.5, True)), _xy(view, last_main.Evaluate(0.5, True))
    run = ((p1[0] - p0[0]), (p1[1] - p0[1]))
    length = (run[0] ** 2 + run[1] ** 2) ** 0.5
    bar2 = _xy(view, along)
    bar_len = (bar2[0] ** 2 + bar2[1] ** 2) ** 0.5 or 1.0
    return {'id': get_id_value(rebar.Id), 'mark': mark_of(rebar), 'count': n,
            'bar_dir': (bar2[0] / bar_len, bar2[1] / bar_len),
            'spread_dir': (run[0] / length, run[1] / length) if n > 1 and length > 1.0 else None,
            'first': p0, 'last': p1, 'spacing': length / (n - 1) if n > 1 else 0.0,
            'ends': (_xy(view, main.GetEndPoint(0)), _xy(view, main.GetEndPoint(1))),
            'chain': first, 'view_dot': abs(along.DotProduct(view.ViewDirection)), 'rebar': rebar}


def _line_style(doc):
    """The 'NOSA Bar Ends' line style (a Lines subcategory), made on first use."""
    lines = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
    for sub in lines.SubCategories:
        if sub.Name == LINE_STYLE:
            return sub.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
    try:
        sub = doc.Settings.Categories.NewSubcategory(lines, LINE_STYLE)
        sub.SetLineWeight(3, DB.GraphicsStyleType.Projection)
        return sub.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
    except Exception:
        return None


def _clear(doc, view, style):
    """What an earlier run drew in this view: its notes and bar-end ticks."""
    gone = []
    for note in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.TextNote):
        if _OWN_NOTE.match((note.Text or u'').strip()):
            gone.append(note.Id)
    if style is not None:
        for curve in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.CurveElement):
            try:
                if curve.LineStyle is not None and curve.LineStyle.Id == style.Id:
                    gone.append(curve.Id)
            except Exception:
                continue
    for eid in gone:
        try:
            doc.Delete(eid)
        except Exception:
            continue


def _note(doc, view, point, text, type_id):
    try:
        opts = DB.TextNoteOptions(type_id)
        opts.HorizontalAlignment = DB.HorizontalTextAlignment.Left
        return DB.TextNote.Create(doc, view.Id, point, text, opts)
    except Exception:
        return None


GAP_PAPER_MM = 1.5           # between texts
OUTSIDE_PAPER_MM = 4.0       # a calling-up past the member's edge
ROW_PAPER_MM = 7.0           # between rows of indicator lines under a beam
ZONE_TAG = u'Full label - Dot'
POINTER_TAG = u'Mark only - Arrow'
MAX_TAG_TRIES = 6


def _tag_types(doc):
    return dict((DB.Element.Name.GetValue(t), t.Id) for t in DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_RebarTags).WhereElementIsElementType())


def _own_annotations(doc, view, ids):
    """MRAs and tags of the given rebars in the view (the ones this run replaces)."""
    gone, mra_tags = [], set()

    def tagged(tag):
        try:
            return any(get_id_value(i) in ids for i in tag.GetTaggedLocalElementIds())
        except Exception:
            return False
    for mra in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.MultiReferenceAnnotation):
        tag = doc.GetElement(mra.TagId)
        dim = doc.GetElement(mra.DimensionId)
        refs = []
        try:
            refs = [get_id_value(r.ElementId) for r in dim.References] if dim is not None else []
        except Exception:
            refs = []
        if (tag is not None and tagged(tag)) or any(i in ids for i in refs):
            gone.append(mra.Id)
            if tag is not None:
                mra_tags.add(get_id_value(tag.Id))
    for tag in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag):
        if get_id_value(tag.Id) not in mra_tags and tagged(tag):
            gone.append(tag.Id)
    return gone


def _main_line(rebar, i):
    lines = [c for c in _centreline(rebar, i) if isinstance(c, DB.Line)]
    return max(lines, key=lambda c: c.Length) if lines else None


def _show_one(rebar, view, n, idx):
    """Only bar idx of the set shows in the view (Revit 'Select' presentation), else the middle one."""
    try:
        rebar.SetPresentationMode(view, DBS.RebarPresentationMode.Select)
        for i in range(n):
            rebar.SetBarHiddenStatus(view, i, i != idx)
        return idx
    except Exception:
        try:
            rebar.SetPresentationMode(view, DBS.RebarPresentationMode.Middle)
            return n // 2
        except Exception:
            return None


def _outline(view, elements):
    """Box (view mm) round the members."""
    xs, ys = [], []
    for e in elements:
        bb = e.get_BoundingBox(None)
        if bb is None:
            continue
        for x in (bb.Min.X, bb.Max.X):
            for y in (bb.Min.Y, bb.Max.Y):
                for z in (bb.Min.Z, bb.Max.Z):
                    p = _xy(view, DB.XYZ(x, y, z))
                    xs.append(p[0])
                    ys.append(p[1])
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _size(view, tag):
    """(width, height, offset of the box centre from the head) of a tag in view mm."""
    bb = tag.get_BoundingBox(view)
    if bb is None:
        return None
    a, b = _xy(view, bb.Min), _xy(view, bb.Max)
    x0, x1, y0, y1 = min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])
    head = _xy(view, tag.TagHeadPosition)
    return x1 - x0, y1 - y0, ((x0 + x1) / 2.0 - head[0], (y0 + y1) / 2.0 - head[1])


def _estimate(view, tag):
    """(width, height, offset) of a tag Revit gives no box for, from its text at the drawing's lettering size."""
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    try:
        text = tag.TagText or u''
    except Exception:
        text = u''
    h = TEXT_PAPER_MM * scale
    return (max(len(text), 2) * 0.75 + 0.5) * h, 1.6 * h, (0.0, 0.0)


def _move_head(view, tag, centre, offset):
    """Put the tag's text box centre at `centre` (view mm)."""
    head = (centre[0] - offset[0], centre[1] - offset[1])
    tag.TagHeadPosition = _point(view, head, tag.TagHeadPosition)


def _mra(doc, view, mra_type, rebar, origin, direction, head, leader):
    try:
        from System.Collections.Generic import List as NetList
        options = DB.MultiReferenceAnnotationOptions(mra_type)
        options.DimensionPlaneNormal = view.ViewDirection
        options.DimensionLineDirection = direction
        options.DimensionLineOrigin = origin
        options.TagHeadPosition = head
        try:
            options.TagHasLeader = leader
        except Exception:
            pass
        ids = NetList[DB.ElementId]()
        ids.Add(rebar.Id)
        options.SetElementsToDimension(ids)
        return DB.MultiReferenceAnnotation.Create(doc, view.Id, options)
    except Exception:
        return None


def _is_plan(view):
    return isinstance(view, DB.ViewPlan)


def apply(doc, view, rebars, det, mra_type_id=None, hosts=None, cover_mm=40.0):
    """
    SMDSC 6.2.2 / 3.3 in `view` for `rebars` (det: the rebar_detailing module): typical bars, indicator lines
    with their calling-up outside the member, marks of bars in sections and elevations in rows outside it,
    'Alt.' / 'Stg.', 30 degree ends. Replaces the rebars' own annotations in the view.
    Returns {'typical', 'mra', 'marks', 'notes', 'ticks', 'inside'}.
    """
    report = {'typical': 0, 'mra': 0, 'marks': 0, 'notes': 0, 'ticks': 0, 'inside': 0}
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    gap, outside, row = GAP_PAPER_MM * scale, OUTSIDE_PAPER_MM * scale, ROW_PAPER_MM * scale
    style = _line_style(doc)
    _clear(doc, view, style)
    visible = [r for r in rebars if r is not None and r.IsValidObject and not r.IsHidden(view)]
    ids = set(get_id_value(r.Id) for r in visible)
    for eid in _own_annotations(doc, view, ids):
        try:
            doc.Delete(eid)
        except Exception:
            continue
    try:
        p = view.get_Parameter(DB.BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
        if p is not None and not p.IsReadOnly:
            p.Set(0)                         # calling-up outside the member stays visible
    except Exception:
        pass
    members = hosts or [doc.GetElement(r.GetHostId()) for r in visible]
    box = _outline(view, [m for m in members if m is not None])
    if box is None:
        return report
    text_type = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
    tag_types = _tag_types(doc)
    mra_type = doc.GetElement(mra_type_id) if mra_type_id is not None else None
    zones, pointers = [], []
    for rebar in visible:
        d = describe(view, rebar)
        if d is None:
            continue
        if presentation.is_typical_bar_set(d['view_dot'], d['spread_dir'] is not None) and mra_type is not None:
            d['layer'] = _text(rebar, u'NOSA_Rebar_Layer')
            zones.append(d)
            continue
        if d['view_dot'] < 0.5 and hosts is not None:
            report['ticks'] += _ticks(doc, view, d, hosts, cover_mm, scale, style)
        pointers.append(d)
    beam_elevation = not _is_plan(view) and any(
        m is not None and m.Category is not None and
        get_id_value(m.Category.Id) == int(DB.BuiltInCategory.OST_StructuralFraming) for m in members)
    placed = []
    made = _zones(doc, view, zones, mra_type, det, box, gap, outside, row, beam_elevation, placed, report)
    _pointers(doc, view, pointers, det, tag_types, box, gap, outside, placed, report)
    for a, _b, label in presentation.relations(zones):
        bx = made.get(a)
        if bx is None:
            continue
        point = _point(view, ((bx[0] + bx[2]) / 2.0, bx[1] - gap - TEXT_PAPER_MM * scale), made_origin(zones, a))
        if _note(doc, view, point, label, text_type):
            report['notes'] += 1
    return report


def made_origin(zones, sid):
    for z in zones:
        if z['id'] == sid:
            return z['chain'][0].GetEndPoint(0) if z['chain'] else DB.XYZ.Zero
    return DB.XYZ.Zero


def _zones(doc, view, zones, mra_type, det, box, gap, outside, row, beam_elevation, placed, report):
    """Typical bar, indicator line and calling-up of every zone; {id: text box}."""
    slots = presentation.layer_slots(zones)
    pending = []
    rows_used = []
    for d in sorted(zones, key=lambda z: (slots.get(z['id'], 0.5), z['id'])):
        rebar, n = d['rebar'], d['count']
        frac = slots.get(d['id'], 0.5)
        idx = _show_one(rebar, view, n, int(round(frac * (n - 1))))
        if idx is None:
            continue
        report['typical'] += 1
        direction = det.set_direction_in_view(rebar, view, 1.0)
        shown, first, last = _main_line(rebar, idx), _main_line(rebar, 0), _main_line(rebar, n - 1)
        if direction is None or shown is None or first is None or last is None:
            continue
        junction = shown.Evaluate(frac, True)
        t = sorted((ln.Evaluate(0.5, True) - junction).DotProduct(direction) for ln in (first, last))
        a3, b3 = junction + direction.Multiply(t[0]), junction + direction.Multiply(t[1])
        origin = junction
        if beam_elevation:
            # under the beam: one row per overlapping run of zones (SMDSC MB1 elevations)
            xa, xb = sorted((_xy(view, a3)[0], _xy(view, b3)[0]))
            k = 0
            while any(r == k and not (xb + gap < r0 or xa - gap > r1) for r, r0, r1 in rows_used):
                k += 1
            rows_used.append((k, xa, xb))
            y = box[1] - outside - k * row
            origin = _point(view, (_xy(view, junction)[0], y), junction)
            a3 = _point(view, (_xy(view, a3)[0], y), junction)
            b3 = _point(view, (_xy(view, b3)[0], y), junction)
        mra = _mra(doc, view, mra_type, rebar, origin, direction, b3, False)
        if mra is None:
            continue
        report['mra'] += 1
        pending.append((d, mra, a3, b3))
    doc.Regenerate()
    made = {}
    for d, mra, a3, b3 in pending:
        tag = doc.GetElement(mra.TagId)
        if tag is None:
            continue
        a, b = _xy(view, a3), _xy(view, b3)
        vertical = abs(b[1] - a[1]) > abs(b[0] - a[0])
        if vertical and not beam_elevation:
            try:
                tag.TagOrientation = DB.TagOrientation.Vertical
            except Exception:
                pass
    doc.Regenerate()
    for d, mra, a3, b3 in pending:
        tag = doc.GetElement(mra.TagId)
        size = _size(view, tag) if tag is not None else None
        if size is None:
            continue
        w, h, offset = size
        a, b = _xy(view, a3), _xy(view, b3)
        if beam_elevation:
            centre = ((a[0] + b[0]) / 2.0, a[1] - gap - h / 2.0)
            bx = (centre[0] - w / 2.0, centre[1] - h / 2.0, centre[0] + w / 2.0, centre[1] + h / 2.0)
            placed.append(bx)
            _move_head(view, tag, centre, offset)
            made[d['id']] = bx
            continue
        vertical = abs(b[1] - a[1]) > abs(b[0] - a[0])
        length, height = (h, w) if vertical else (w, h)
        r = presentation_place(a, b, length, height, box, placed, gap, outside)
        _move_head(view, tag, r['centre'], offset)
        try:
            tag.HasLeader = bool(r['outside'])
        except Exception:
            pass
        if not r['outside']:
            report['inside'] += 1
        made[d['id']] = r['box']
    return made


def presentation_place(a, b, length, height, box, placed, gap, outside):
    from nosa_utils import callout_layout
    return callout_layout.place_inline({'a': a, 'b': b, 'length': length, 'height': height}, box, placed, gap,
                                       outside)


def _shown_bar(view, rebar, n):
    """
    The bar of a set the view draws: the middle one on plans; in sections and elevations the nearest one
    behind the cut plane (a bar in front of it is not drawn, nor is a tag on it).
    """
    if _is_plan(view) or n < 2:
        return n // 2
    cut = view.Origin.DotProduct(view.ViewDirection)
    depths = []
    for i in range(n):
        line = _main_line(rebar, i)
        if line is not None:
            depths.append((line.Evaluate(0.5, True).DotProduct(view.ViewDirection), i))
    behind = [(d, i) for d, i in depths if d <= cut + 1.0 / _MM_PER_FT]
    if behind:
        return max(behind)[1]
    return min(depths, key=lambda di: abs(di[0] - cut))[1] if depths else n // 2


def _anchor(view, d, fraction=0.5, index=None):
    """Point on the bar the mark points at: along the shown bar at `fraction` (a dot when the bars are cut)."""
    rebar = d['rebar']
    line = _main_line(rebar, d['count'] // 2 if index is None else index) or _main_line(rebar, 0)
    return line.Evaluate(fraction, True) if line is not None else None


def _visible(doc, view, element):
    return any(get_id_value(e) == get_id_value(element.Id) for e in
               DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag).ToElementIds())


def _tag_bar(doc, view, rebar, index, type_id):
    """
    (tag, bar index): a tag on one bar of the set (Revit 2024 will not tag a whole set), no leader yet. Revit
    draws such a tag only for some bars of a set, so the shown bar is tried first, then the end ones and the
    neighbours.
    """
    subs = list(rebar.GetSubelements())
    if not subs:
        return DB.IndependentTag.Create(doc, type_id, view.Id, DB.Reference(rebar), False,
                                        DB.TagOrientation.Horizontal, view.Origin), index
    order = []
    for i in [index, 0, len(subs) - 1] + sorted(range(len(subs)), key=lambda i: (abs(i - index), i)):
        if 0 <= i < len(subs) and i not in order:
            order.append(i)
    order = order[:MAX_TAG_TRIES]
    for i in order:
        line = _main_line(rebar, i) or _main_line(rebar, 0)
        point = line.Evaluate(0.5, True) if line is not None else view.Origin
        try:
            tag = DB.IndependentTag.Create(doc, type_id, view.Id, subs[i].GetReference(), False,
                                           DB.TagOrientation.Horizontal, point)
        except Exception:
            continue
        doc.Regenerate()
        if _visible(doc, view, tag):
            return tag, i
        doc.Delete(tag.Id)
    return None, index


def _pointer_fractions(items):
    """{id: fraction}: bars lying along each other in the view get their marks at different places."""
    flat = [d for d in items if d['view_dot'] < 0.5]
    groups = []
    for d in sorted(flat, key=lambda z: (_text(z['rebar'], u'NOSA_Rebar_Layer'), z['id'])):
        e = sorted(sum(p[i] * d['bar_dir'][i] for i in (0, 1)) for p in d['ends'])
        for g in groups:
            o = g[0]
            if abs(sum(o['bar_dir'][i] * d['bar_dir'][i] for i in (0, 1))) > 0.99:
                f = sorted(sum(p[i] * d['bar_dir'][i] for i in (0, 1)) for p in o['ends'])
                if e[0] < f[1] and f[0] < e[1]:
                    g.append(d)
                    break
        else:
            groups.append([d])
    out = {}
    for g in groups:
        for k, d in enumerate(g):
            out[d['id']] = (k + 1.0) / (len(g) + 1.0)
    return out


def _pointers(doc, view, items, det, tag_types, box, gap, outside, placed, report):
    """Marks of the bars that are not zones, in rows outside the member, each with a pointer to its bar."""
    from nosa_utils import callout_layout
    if not items:
        return
    kind = ZONE_TAG if _is_plan(view) else POINTER_TAG
    type_id = tag_types.get(kind) or det.tag_type_for_view(doc, view)
    fractions = _pointer_fractions(items)
    tags = []
    for d in items:
        index = _shown_bar(view, d['rebar'], d['count'])
        try:
            tag, index = _tag_bar(doc, view, d['rebar'], index, det._tag_type_for_bar(doc, d['rebar'], type_id))
        except Exception:
            continue
        anchor = _anchor(view, d, fractions.get(d['id'], 0.5), index)
        if tag is None or anchor is None:
            continue
        tags.append((d, tag, anchor))
    doc.Regenerate()
    layout = []
    sizes = {}
    for d, tag, anchor in tags:
        size = _size(view, tag) if tag is not None and tag.IsValidObject else None
        if size is None and tag is not None and tag.IsValidObject:
            size = _estimate(view, tag)
        if size is None:
            continue
        sizes[d['id']] = size
        layout.append({'id': d['id'], 'anchor': _xy(view, anchor), 'length': size[0], 'height': size[1]})
    if placed:
        box = (min([box[0]] + [b[0] for b in placed]), min([box[1]] + [b[1] for b in placed]),
               max([box[2]] + [b[2] for b in placed]), max([box[3]] + [b[3] for b in placed]))
    places = callout_layout.place_pointers(layout, box, gap, outside)
    for d, tag, anchor in tags:
        if d['id'] not in places:
            continue
        w, h, offset = sizes[d['id']]
        c = places[d['id']]['centre']
        _move_head(view, tag, c, offset)
        try:
            tag.HasLeader = True
            tag.LeaderEndCondition = DB.LeaderEndCondition.Free
            refs = list(tag.GetTaggedReferences())
            if refs:
                tag.SetLeaderEnd(refs[0], anchor)
        except Exception:
            pass
        placed.append((c[0] - w / 2.0, c[1] - h / 2.0, c[0] + w / 2.0, c[1] + h / 2.0))
        report['marks'] += 1


def see_drawing(doc, view, rebars):
    """Bars detailed on another drawing than the view's sheet: thick dashed, 'SEE DRG nnnn' (SMDSC 6.2.2)."""
    sheet = view.get_Parameter(DB.BuiltInParameter.VIEWPORT_SHEET_NUMBER)
    view_drawing = (sheet.AsString() or u'') if sheet is not None else u''
    if not view_drawing:
        return 0
    dash = DB.LinePatternElement.GetLinePatternElementByName(doc, u'Dash')
    text_type = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
    n = 0
    for rebar in rebars:
        if rebar is None or not rebar.IsValidObject or rebar.IsHidden(view):
            continue
        see = presentation.see_drawing(_text(rebar, DRAWING_PARAM), view_drawing)
        if not see:
            continue
        ogs = DB.OverrideGraphicSettings()
        if dash is not None:
            ogs.SetProjectionLinePatternId(dash.Id)
        view.SetElementOverrides(rebar.Id, ogs)
        line = _main_line(rebar, 0)
        if line is not None and _note(doc, view, line.Evaluate(0.5, True), see, text_type):
            n += 1
    return n


def _ticks(doc, view, d, hosts, cover_mm, scale, style):
    """Short 30 degree obliques at the curtailed straight ends of a bar seen along its length."""
    chain = d['chain']
    if not chain:
        return 0
    host = None
    for h in hosts:
        if get_id_value(h.Id) == get_id_value(d['rebar'].GetHostId()):
            host = h
    box = host.get_BoundingBox(None) if host is not None else None
    if box is None:
        return 0
    try:
        dia = d['rebar'].Document.GetElement(d['rebar'].GetTypeId()).BarModelDiameter * _MM_PER_FT
    except Exception:
        dia = 16.0
    made = 0
    lines = [c for c in chain if isinstance(c, DB.Line)]
    main = max(lines, key=lambda c: c.Length) if lines else None
    for curve, at_start in ((chain[0], True), (chain[-1], False)):
        if not isinstance(curve, DB.Line) or main is None or abs(curve.Direction.DotProduct(main.Direction)) < 0.99:
            continue                                    # a bend, hook or link leg there, not a curtailed end
        end = curve.GetEndPoint(0) if at_start else curve.GetEndPoint(1)
        out = curve.Direction.Negate() if at_start else curve.Direction
        corners = [DB.XYZ(x, y, z) for x in (box.Min.X, box.Max.X) for y in (box.Min.Y, box.Max.Y)
                   for z in (box.Min.Z, box.Max.Z)]
        proj = [c.DotProduct(curve.Direction) * _MM_PER_FT for c in corners]
        if not presentation.curtailed(end.DotProduct(curve.Direction) * _MM_PER_FT, min(proj), max(proj),
                                      cover_mm, dia):
            continue
        o2 = _xy(view, out)
        n = (o2[0] ** 2 + o2[1] ** 2) ** 0.5 or 1.0
        o2 = (o2[0] / n, o2[1] / n)
        side = (-o2[1], o2[0]) if o2[0] >= 0 else (o2[1], -o2[0])
        a, b = presentation.tick(_xy(view, end), o2, side, scale)
        try:
            line = DB.Line.CreateBound(_point(view, a, end), _point(view, b, end))
            curve_el = doc.Create.NewDetailCurve(view, line)
            if style is not None:
                curve_el.LineStyle = style
            made += 1
        except Exception:
            continue
    return made
