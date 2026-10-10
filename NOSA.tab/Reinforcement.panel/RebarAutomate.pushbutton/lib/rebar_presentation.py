# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — IStructE SMDSC 6.2.2 presentation of the bars in one view (T8.27), the rules in
nosa_utils.presentation and nosa_utils.callout_layout: each set lying in the view plane is drawn as one
typical bar (layers drawn over each other show different bars) with a Multi-Rebar Annotation as its indicator
line and the calling-up on its extension outside the member; under a beam elevation its link zones 'n/pitch'
over one total calling-up per mark; in sections and elevations a mark over every cut bar and one per set lying
in the view, in rows outside the member with pointers; 'Alt.' / 'Stg.'; a short 30 degree
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


def _line_style(doc, name=LINE_STYLE, pen=3):
    """A NOSA line style (a Lines subcategory), made on first use."""
    lines = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
    for sub in lines.SubCategories:
        if sub.Name == name:
            return sub.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
    try:
        sub = doc.Settings.Categories.NewSubcategory(lines, name)
        sub.SetLineWeight(pen, DB.GraphicsStyleType.Projection)
        return sub.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
    except Exception:
        return None


def _clear(doc, view, styles):
    """What an earlier run drew in this view: its notes, bar-end ticks and total lines."""
    gone = []
    for note in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.TextNote):
        if _OWN_NOTE.match((note.Text or u'').strip()):
            gone.append(note.Id)
    own = set(get_id_value(s.Id) for s in styles if s is not None)
    if own:
        for curve in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.CurveElement):
            try:
                if curve.LineStyle is not None and get_id_value(curve.LineStyle.Id) in own:
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
OUTSIDE_PAPER_MM = 6.0       # a calling-up past the member's edge
CUT_OUTSIDE_PAPER_MM = 2.0   # a cut bar's mark, no pointer, next to the member's face
CROP_MARGIN_PAPER_MM = 4.0   # the view's crop round its calling-up
ROW_PAPER_MM = 7.0           # between rows of indicator lines under a beam
ZONE_TAG = u'Full label - Dot'
POINTER_TAG = u'Mark only - Arrow'
CUT_TAG = u'Mark only - Dot'            # a mark over every bar a section cuts (SMDSC 6.2.3, user 2026-10-10)
ELEVATION_TAG = u'Full label - Arrow'   # main bars of an elevation: 'No centres' for beams and columns
SHORT_TAG = u'No centres - Dot'
TOTAL_STYLE = u'NOSA Total Lines'       # the line under a beam carrying a link mark's one calling-up
ELEVATION_KINDS = ('elevation', 'column_elevation')
CALLOUT_TAG = u'Callout - Dot'          # NOSA Rebar Tag 1.3.0
ZONE_QTY_TAG = u'Zone quantity - Dot'
CALLOUT_PARAM = u'NOSA_Rebar_Callout'
ZONE_QTY_PARAM = u'NOSA_Rebar_Zone_Qty'
MAX_TAG_TRIES = 6


def params_file():
    import os
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data',
                                        'shared_parameters', 'NOSA_Presentation.txt'))


def bind(doc):
    """NOSA_Rebar_Callout / NOSA_Rebar_Zone_Qty on Structural Rebar (idempotent). Outside a transaction."""
    from nosa_utils import shared_params
    return shared_params.ensure_bound(doc, ['OST_Rebar'], params_file())


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
    return (max(len(text), 2) * 0.75 + 0.5) * h, 1.3 * h, (0.0, 0.0)


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


def apply(doc, view, rebars, det, mra_type_id=None, hosts=None, cover_mm=40.0, kind=None):
    """
    SMDSC 6.2.2 / 3.3 in `view` for `rebars` (det: the rebar_detailing module): typical bars, indicator lines
    with their calling-up outside the member, a mark over every bar a section or elevation cuts and one per set
    lying in it, in rows outside the member; under a beam elevation its link zones 'n/pitch' over one total
    calling-up per mark; 'Alt.' / 'Stg.', 30 degree ends. kind: the view_plan kind of the view.
    Replaces the rebars' own annotations in the view.
    Returns {'typical', 'mra', 'marks', 'notes', 'ticks', 'inside'}.
    """
    report = {'typical': 0, 'mra': 0, 'marks': 0, 'notes': 0, 'ticks': 0, 'inside': 0}
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    gap, outside, row = GAP_PAPER_MM * scale, OUTSIDE_PAPER_MM * scale, ROW_PAPER_MM * scale
    style = _line_style(doc)
    total_style = _line_style(doc, TOTAL_STYLE, 1)
    _clear(doc, view, (style, total_style))
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
    plan = _is_plan(view)
    zones, pointers, cut = [], [], []
    for rebar in visible:
        d = describe(view, rebar)
        if d is None:
            continue
        if presentation.is_typical_bar_set(d['view_dot'], d['spread_dir'] is not None) and mra_type is not None:
            d['layer'] = _text(rebar, u'NOSA_Rebar_Layer')
            zones.append(d)
            continue
        if d['view_dot'] >= 0.5 and not plan:
            cut.append(d)
            continue
        if d['view_dot'] < 0.5 and hosts is not None:
            report['ticks'] += _ticks(doc, view, d, hosts, cover_mm, scale, style)
        pointers.append(d)
    elevation = kind in ELEVATION_KINDS
    beam_elevation = not plan and kind in (None, 'elevation') and any(
        m is not None and m.Category is not None and
        get_id_value(m.Category.Id) == int(DB.BuiltInCategory.OST_StructuralFraming) for m in members)
    placed = []
    if beam_elevation:
        # SMDSC 6.2.3 beam elevation: the main bars' calling-up turned up the sheet just past the beam's faces,
        # then the link zones under them, each mark's 'n/pitch' zones over its one total calling-up
        _marks(doc, view, pointers, cut, det, tag_types, box, gap, outside, placed, report, 'beam')
        made = _beam_links(doc, view, zones, mra_type, det, box, gap, outside, row, placed, report, total_style)
    else:
        made = _zones(doc, view, zones, mra_type, det, box, gap, outside, row, placed, report)
        if plan:
            _pointers(doc, view, pointers, det, tag_types, box, gap, outside, placed, report)
        else:
            _marks(doc, view, pointers, cut, det, tag_types, box, gap, outside, placed, report, elevation)
    for a, _b, label in presentation.relations(zones):
        bx = made.get(a)
        if bx is None:
            continue
        point = _point(view, ((bx[0] + bx[2]) / 2.0, bx[1] - gap - TEXT_PAPER_MM * scale), made_origin(zones, a))
        if _note(doc, view, point, label, text_type):
            report['notes'] += 1
    _fit_crop(view, [box] + placed, CROP_MARGIN_PAPER_MM * scale)
    return report


def _fit_crop(view, boxes, margin):
    """Widen the view's crop to take every calling-up in, so no crop line runs through a text."""
    try:
        crop = view.CropBox
        t = crop.Transform
        o = (t.Origin.DotProduct(view.RightDirection) * _MM_PER_FT, t.Origin.DotProduct(view.UpDirection) * _MM_PER_FT)
        sx = 1.0 if t.BasisX.DotProduct(view.RightDirection) > 0 else -1.0
        sy = 1.0 if t.BasisY.DotProduct(view.UpDirection) > 0 else -1.0
        xs = [sx * (x - o[0]) for b in boxes for x in (b[0] - margin, b[2] + margin)]
        ys = [sy * (y - o[1]) for b in boxes for y in (b[1] - margin, b[3] + margin)]
        lo = DB.XYZ(min(crop.Min.X, min(xs) / _MM_PER_FT), min(crop.Min.Y, min(ys) / _MM_PER_FT), crop.Min.Z)
        hi = DB.XYZ(max(crop.Max.X, max(xs) / _MM_PER_FT), max(crop.Max.Y, max(ys) / _MM_PER_FT), crop.Max.Z)
        if lo.IsAlmostEqualTo(crop.Min) and hi.IsAlmostEqualTo(crop.Max):
            return
        crop.Min, crop.Max = lo, hi
        view.CropBox = crop
    except Exception:
        pass


def made_origin(zones, sid):
    for z in zones:
        if z['id'] == sid:
            return z['chain'][0].GetEndPoint(0) if z['chain'] else DB.XYZ.Zero
    return DB.XYZ.Zero


def _thin(a, b, half):
    """Box round the segment a-b, `half` either side."""
    return (min(a[0], b[0]) - half, min(a[1], b[1]) - half, max(a[0], b[0]) + half, max(a[1], b[1]) + half)


def _zones(doc, view, zones, mra_type, det, box, gap, outside, row, placed, report):
    """Typical bar, indicator line and calling-up of every zone; {id: text box}."""
    slots = presentation.layer_slots(zones)
    pending = []
    lines = {}
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
        mra = _mra(doc, view, mra_type, rebar, junction, direction, b3, False)
        if mra is None:
            continue
        report['mra'] += 1
        pending.append((d, mra, a3, b3, junction))
        # what a zone's '(n)' must keep off: the other indicator lines and typical bars
        lines[d['id']] = [_thin(_xy(view, a3), _xy(view, b3), gap / 3.0),
                          _thin(_xy(view, shown.GetEndPoint(0)), _xy(view, shown.GetEndPoint(1)), gap / 3.0)]
    doc.Regenerate()
    made = {}
    for d, mra, a3, b3, _o in pending:
        tag = doc.GetElement(mra.TagId)
        if tag is None:
            continue
        a, b = _xy(view, a3), _xy(view, b3)
        if abs(b[1] - a[1]) > abs(b[0] - a[0]):
            try:
                tag.TagOrientation = DB.TagOrientation.Vertical
            except Exception:
                pass
    doc.Regenerate()
    qty, callouts = _strict_zones(doc, view, pending)
    doc.Regenerate()
    for d, mra, a3, b3, origin in pending:
        tag = doc.GetElement(mra.TagId)
        size = _size(view, tag) if tag is not None else None
        if size is None:
            continue
        w, h, offset = size
        a, b = _xy(view, a3), _xy(view, b3)
        if d['id'] in qty:
            # SMDSC 6.2.2: the zone's own number in brackets on its own indicator line, clear of the others
            others = [q for k, boxes in lines.items() if k != d['id'] for q in boxes]
            centre = _qty_spot(a, b, _xy(view, origin), w, h, gap, placed + others)
            bx = (centre[0] - w / 2.0, centre[1] - h / 2.0, centre[0] + w / 2.0, centre[1] + h / 2.0)
            placed.append(bx)
            _move_head(view, tag, centre, offset)
            try:
                tag.HasLeader = False
            except Exception:
                pass
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
    for d, tag, a3, b3 in callouts:
        size = (_size(view, tag) or _estimate(view, tag)) if tag.IsValidObject else None
        if size is None:
            continue
        w, h, offset = size
        a, b = _xy(view, a3), _xy(view, b3)
        vertical = abs(b[1] - a[1]) > abs(b[0] - a[0])
        if vertical:
            try:
                tag.TagOrientation = DB.TagOrientation.Vertical
                doc.Regenerate()
                w, h, offset = _size(view, tag) or _estimate(view, tag)
            except Exception:
                pass
        length, height = (h, w) if vertical else (w, h)
        r = presentation_place(a, b, length, height, box, placed, gap, outside)
        _move_head(view, tag, r['centre'], offset)
        try:
            tag.HasLeader = True
            tag.LeaderEndCondition = DB.LeaderEndCondition.Free
            refs = list(tag.GetTaggedReferences())
            if refs:
                tag.SetLeaderEnd(refs[0], b3 if r['end'] == 'b' else a3)
        except Exception:
            pass
        report['callouts'] = report.get('callouts', 0) + 1
    return made


def _set(rebar, name, value):
    p = rebar.LookupParameter(name)
    if p is None or p.IsReadOnly:
        return False
    p.Set(value)
    return True


def _total_line(doc, view, x0, x1, y, like, scale, style):
    """The line a link mark's one calling-up stands on: from its first zone to its last, 45 degree end ticks."""
    tick = 1.0 * scale
    segments = [((x0, y), (x1, y)), ((x0 - tick, y - tick), (x0 + tick, y + tick)),
                ((x1 - tick, y - tick), (x1 + tick, y + tick))]
    for a, b in segments:
        try:
            curve = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_point(view, a, like), _point(view, b, like)))
            if style is not None:
                curve.LineStyle = style
        except Exception:
            continue


def _beam_links(doc, view, zones, mra_type, det, box, gap, outside, row, placed, report, style):
    """
    Link zones under a beam elevation (SMDSC 6.2.3, fig. 'Beam on grid 1/A-B'): every zone of a mark on one
    line, its indicator line labelled 'n/pitch' ('Zone quantity' tag, NOSA_Rebar_Zone_Qty), and under them one
    line from the mark's first zone to its last carrying its one calling-up ('43H8-06 LINKS', 'Callout' tag,
    NOSA_Rebar_Callout). Marks whose zones overlap take further rows. {id: text box}.
    """
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    types = _tag_types(doc)
    qty_type, callout_type, short_type = types.get(ZONE_QTY_TAG), types.get(CALLOUT_TAG), types.get(SHORT_TAG)
    text_h = TEXT_PAPER_MM * scale * 1.3
    top = min([box[1]] + [q[1] for q in placed]) - outside
    groups = {}
    for d in zones:
        groups.setdefault((d['mark'], get_id_value(d['rebar'].GetTypeId())), []).append(d)
    spans = []
    for key, group in groups.items():
        xs = [x for d in group for x in (d['first'][0], d['last'][0])]
        spans.append([min(xs), max(xs), key, group])
    rows_used = []
    made = {}
    for x0, x1, key, group in sorted(spans, key=lambda s: (s[0], s[1])):
        k = 0
        while any(r == k and not (x1 + gap < r0 or x0 - gap > r1) for r, r0, r1 in rows_used):
            k += 1
        rows_used.append((k, x0, x1))
        y_zone = top - gap - text_h - k * 2 * row
        y_total = y_zone - row
        pending = []
        for d in sorted(group, key=lambda z: z['first'][0]):
            rebar, n = d['rebar'], d['count']
            idx = _show_one(rebar, view, n, n // 2)
            direction = det.set_direction_in_view(rebar, view, 1.0)
            first, last = _main_line(rebar, 0), _main_line(rebar, n - 1)
            if idx is None or direction is None or first is None or last is None:
                continue
            report['typical'] += 1
            like = first.Evaluate(0.5, True)
            a, b = sorted((_xy(view, first.Evaluate(0.5, True))[0], _xy(view, last.Evaluate(0.5, True))[0]))
            origin = _point(view, ((a + b) / 2.0, y_zone), like)
            mra = _mra(doc, view, mra_type, rebar, origin, direction, origin, False)
            if mra is None:
                continue
            report['mra'] += 1
            pending.append((d, mra, a, b))
        if not pending:
            continue
        links = any(_text(d['rebar'], u'NOSA_Rebar_Layer').startswith(u'stirrup') for d, _m, _a, _b in pending)
        main = max(pending, key=lambda e: (e[0]['count'], -e[0]['id']))[0]
        callout = presentation.total_callout(_full_label(doc, view, main, short_type),
                                             sum(e[0]['count'] for e in pending), links)
        for d, mra, a, b in pending:
            ok = _set(d['rebar'], ZONE_QTY_PARAM, presentation.zone_quantity(d['count'], d['spacing']))
            _set(d['rebar'], CALLOUT_PARAM, callout)
            tag = doc.GetElement(mra.TagId)
            if tag is not None and ok and qty_type is not None:
                try:
                    tag.ChangeTypeId(qty_type)
                except Exception:
                    pass
        doc.Regenerate()
        for d, mra, a, b in pending:
            tag = doc.GetElement(mra.TagId)
            size = _size(view, tag) if tag is not None else None
            if size is None:
                continue
            w, h, offset = size
            centre = ((a + b) / 2.0, y_zone + gap / 2.0 + h / 2.0)
            _move_head(view, tag, centre, offset)
            try:
                tag.HasLeader = False
            except Exception:
                pass
            bx = (centre[0] - w / 2.0, centre[1] - h / 2.0, centre[0] + w / 2.0, centre[1] + h / 2.0)
            placed.append(bx)
            placed.append((a, y_zone - gap, b, y_zone + gap))
            made[d['id']] = bx
        lo, hi = min(e[2] for e in pending), max(e[3] for e in pending)
        _total_line(doc, view, lo, hi, y_total, _main_line(main['rebar'], 0).Evaluate(0.5, True), scale, style)
        placed.append((lo, y_total - gap, hi, y_total + gap))
        if callout_type is None or not callout:
            continue
        tag, _i = _tag_bar(doc, view, main['rebar'], _shown_bar(view, main['rebar'], main['count']), callout_type)
        if tag is None:
            continue
        doc.Regenerate()
        w, h, offset = _size(view, tag) or _estimate(view, tag)
        centre = ((lo + hi) / 2.0, y_total + gap / 2.0 + h / 2.0)
        _move_head(view, tag, centre, offset)
        try:
            tag.HasLeader = False
        except Exception:
            pass
        placed.append((centre[0] - w / 2.0, centre[1] - h / 2.0, centre[0] + w / 2.0, centre[1] + h / 2.0))
        report['callouts'] = report.get('callouts', 0) + 1
    return made


def _full_label(doc, view, d, type_id):
    """The full calling-up of a set as its tag writes it (a Multi-Rebar Annotation's tag does not give it)."""
    if type_id is None:
        return u''
    tag, _i = _tag_bar(doc, view, d['rebar'], _shown_bar(view, d['rebar'], d['count']), type_id)
    if tag is None:
        return u''
    try:
        return (tag.TagText or u'').strip()
    finally:
        doc.Delete(tag.Id)


def _qty_spot(a, b, j, w, h, gap, placed):
    """
    Centre of a zone's '(n)' on its indicator line: beside the line, at the typical bar or slid along the line
    (either side) to the first place clear of what is already drawn; at the typical bar when none is.
    """
    from nosa_utils import callout_layout
    run = (b[0] - a[0], b[1] - a[1])
    n = (run[0] ** 2 + run[1] ** 2) ** 0.5 or 1.0
    u = (run[0] / n, run[1] / n)
    up = (-u[1], u[0]) if u[0] >= 0 else (u[1], -u[0])
    horizontal = abs(u[0]) >= abs(u[1])
    lift = (h if horizontal else w) / 2.0 + gap / 2.0
    along = (w if horizontal else h) + gap
    t0 = (j[0] - a[0]) * u[0] + (j[1] - a[1]) * u[1]
    first = None
    for k in range(0, 9):
        for sign in ((1,) if k == 0 else (1, -1)):
            t = t0 + sign * k * along
            if t < 0.0 or t > n:
                continue
            for side in (1.0, -1.0):
                c = (a[0] + u[0] * t + up[0] * lift * side, a[1] + u[1] * t + up[1] * lift * side)
                bx = (c[0] - w / 2.0, c[1] - h / 2.0, c[0] + w / 2.0, c[1] + h / 2.0)
                if first is None:
                    first = c
                if not any(callout_layout.overlap(bx, q, gap / 2.0) for q in placed):
                    return c
    return first


def _strict_zones(doc, view, pending):
    """
    SMDSC 4.2.1 / 6.2.2 for a mark drawn in several zones of the view: the number written once, in one
    calling-up with the total ('Callout - Dot' tag, NOSA_Rebar_Callout), and each zone's own number in
    brackets on its indicator line ('Zone quantity - Dot' tag, NOSA_Rebar_Zone_Qty). Needs the NOSA Rebar
    Tag 1.3.0 types and the parameters bound; else every zone keeps its full calling-up.
    Returns ({zone id}, [(representative zone, callout tag, a3, b3)]).
    """
    types = _tag_types(doc)
    zone_type, callout_type = types.get(ZONE_QTY_TAG), types.get(CALLOUT_TAG)
    if zone_type is None or callout_type is None:
        return set(), []
    groups = {}
    for entry in pending:
        d = entry[0]
        key = (d['mark'], get_id_value(d['rebar'].GetTypeId()), round(d.get('spacing') or 0.0))   # one pitch, one zone
        if d['mark']:
            groups.setdefault(key, []).append(entry)
    qty, callouts = set(), []
    for entries in groups.values():
        if len(entries) < 2:
            continue
        rebars = [e[0]['rebar'] for e in entries]
        if any(r.LookupParameter(CALLOUT_PARAM) is None or r.LookupParameter(ZONE_QTY_PARAM) is None for r in rebars):
            continue
        main = max(entries, key=lambda e: (e[0]['count'], -e[0]['id']))
        text = _full_label(doc, view, main[0], types.get(ZONE_TAG))
        if not text[:1].isdigit():
            continue
        callout = re.sub(u'^\\d+', u'{}'.format(sum(e[0]['count'] for e in entries)), text)
        callout = re.sub(u'\\d+\\.\\d+', lambda m: u'{:.0f}'.format(float(m.group(0))), callout)   # 150.0, 194.5
        for e in entries:
            e[0]['rebar'].LookupParameter(CALLOUT_PARAM).Set(callout)
            e[0]['rebar'].LookupParameter(ZONE_QTY_PARAM).Set(u'({})'.format(e[0]['count']))
        changed = []
        for e in entries:
            tag = doc.GetElement(e[1].TagId)
            try:
                tag.ChangeTypeId(zone_type)
                changed.append(e)
            except Exception:
                continue
        if len(changed) != len(entries):
            continue
        d = main[0]
        tag, _i = _tag_bar(doc, view, d['rebar'], _shown_bar(view, d['rebar'], d['count']), callout_type)
        if tag is None:
            continue
        qty.update(e[0]['id'] for e in entries)
        callouts.append((d, tag, main[2], main[3]))
    return qty, callouts


def presentation_place(a, b, length, height, box, placed, gap, outside):
    from nosa_utils import callout_layout
    return callout_layout.place_inline({'a': a, 'b': b, 'length': length, 'height': height}, box, placed, gap,
                                       outside)


def _shown_bar(view, rebar, n):
    """
    The bar of a set the view draws: the middle one on plans; in sections and elevations the nearest one
    behind the cut plane (a bar in front of it is not drawn, nor is a tag on it).
    """
    for i in range(n):                  # a typical bar: the one bar the view shows
        try:
            if rebar.GetPresentationMode(view) == DBS.RebarPresentationMode.Select and not rebar.IsBarHidden(view, i):
                return i
        except Exception:
            break
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


def _clear_anchor(view, d, fraction, index, box, placed, gap):
    """
    The anchor of a bar's mark, slid along the bar (in the view plane) until the pointer, run straight out to
    the row beyond the member, crosses no text already placed; the first candidate when none is clear.
    """
    from nosa_utils import callout_layout
    first = _anchor(view, d, fraction, index)
    if first is None or d['view_dot'] >= 0.5:
        return first
    texts = [q for q in placed if (q[3] - q[1]) > 3.0 * gap and (q[2] - q[0]) > 3.0 * gap]
    for f in [fraction] + [x / 20.0 for x in (10, 6, 14, 4, 16, 8, 12, 3, 17, 5, 15)]:
        p = _anchor(view, d, f, index)
        a = _xy(view, p)
        side = callout_layout.side_of(a, box)
        far = {'top': (a[0], box[3] + 1e6), 'bottom': (a[0], box[1] - 1e6),
               'right': (box[2] + 1e6, a[1]), 'left': (box[0] - 1e6, a[1])}[side]
        lane = (min(a[0], far[0]) - gap, min(a[1], far[1]) - gap, max(a[0], far[0]) + gap, max(a[1], far[1]) + gap)
        if not any(callout_layout.overlap(lane, q) for q in texts):
            return p
    return first


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
        anchor = _clear_anchor(view, d, fractions.get(d['id'], 0.5), index, box, placed, gap)
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


def _crop_frame(view):
    """(inverse transform, min, max) of the view's crop box, or None when it does not crop."""
    try:
        if not view.CropBoxActive:
            return None
        crop = view.CropBox
        return crop.Transform.Inverse, crop.Min, crop.Max
    except Exception:
        return None


def _cut_bars(view, d, frame):
    """[(bar index, reference, point on it)] of the bars of a set cut by the view, inside its crop and depth."""
    rebar = d['rebar']
    try:
        subs = list(rebar.GetSubelements())
    except Exception:
        subs = []
    out = []
    for i in range(d['count']):
        try:
            if rebar.IsBarHidden(view, i):
                continue
        except Exception:
            pass
        line = _main_line(rebar, i)
        if line is None:
            continue
        if frame is not None:
            inv, lo, hi = frame
            p, q = inv.OfPoint(line.GetEndPoint(0)), inv.OfPoint(line.GetEndPoint(1))
            m = inv.OfPoint(line.Evaluate(0.5, True))
            if not (lo.X <= m.X <= hi.X and lo.Y <= m.Y <= hi.Y) or max(p.Z, q.Z) < lo.Z or min(p.Z, q.Z) > hi.Z:
                continue
        ref = subs[i].GetReference() if len(subs) == d['count'] else DB.Reference(rebar)
        out.append((i, ref, line.Evaluate(0.5, True)))
    return out


def _marks(doc, view, items, cut, det, tag_types, box, gap, outside, placed, report, mode):
    """
    Bar marks of a section or elevation (SMDSC 6.2.3, 6.4.4, user 2026-10-10): its own mark over every bar the
    view cuts ('Mark only - Dot', one per bar, no pointer: it stands just past the face in line with its bar,
    rows split when the bars are close), one mark per set lying in the view plane (in an elevation its
    calling-up without centres, 'Full label - Arrow'), all in rows beyond the member's nearest face, their near
    ends lined up, turned up the sheet when a row is too tight for them side by side, each pointing straight at
    its bar. mode: 'beam' (beam elevation: rows above and below only, texts always turned), True (another
    elevation), False (a section).
    """
    from nosa_utils import callout_layout
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    entries = []
    base = tag_types.get(ELEVATION_TAG if mode else POINTER_TAG) or det.tag_type_for_view(doc, view)
    fractions = _pointer_fractions(items)
    for d in items:
        index = _shown_bar(view, d['rebar'], d['count'])
        try:
            tag, index = _tag_bar(doc, view, d['rebar'], index, det._tag_type_for_bar(doc, d['rebar'], base))
        except Exception:
            continue
        anchor = _clear_anchor(view, d, fractions.get(d['id'], 0.5), index, box, placed, gap)
        if tag is not None and anchor is not None:
            entries.append((d['id'], tag, anchor))
    cut_type = tag_types.get(CUT_TAG) or base
    frame = _crop_frame(view)
    for d in cut:
        for i, ref, point in _cut_bars(view, d, frame):
            try:
                tag = DB.IndependentTag.Create(doc, cut_type, view.Id, ref, False, DB.TagOrientation.Horizontal,
                                               point)
            except Exception:
                continue
            entries.append(((d['id'], i), tag, point))
    if not entries:
        return
    doc.Regenerate()
    member = box
    if placed:
        box = (min([box[0]] + [b[0] for b in placed]), min([box[1]] + [b[1] for b in placed]),
               max([box[2]] + [b[2] for b in placed]), max([box[3]] + [b[3] for b in placed]))
    third = (member[3] - member[1]) / 3.0
    layout = []
    for key, tag, anchor in entries:
        w, h, _o = _estimate(view, tag)
        a = _xy(view, anchor)
        if mode == 'beam' or (isinstance(key, tuple) and not member[1] + third < a[1] < member[3] - third):
            # cut bars of a top or bottom layer, and all the bars of a beam elevation: above or below it
            side = 'top' if a[1] > (member[1] + member[3]) / 2.0 else 'bottom'
        else:
            side = callout_layout.side_of(a, member)
        item = {'id': key, 'anchor': a, 'length': w, 'height': h, 'side': side}
        if isinstance(key, tuple):
            # a cut bar's mark stands next to the member over its bar, no pointer (SMDSC 6.2.3 sections)
            item['free'], item['outside'] = True, CUT_OUTSIDE_PAPER_MM * scale
        layout.append(item)
    for side in ('top', 'bottom'):
        row = [it for it in layout if it['side'] == side]
        if row and (mode == 'beam' or callout_layout.crowded([it['anchor'][0] for it in row],
                                                            max(it['length'] for it in row), gap)):
            for it in row:
                it['vertical'] = True
    for it, (key, tag, anchor) in zip(layout, entries):
        if it.get('vertical'):
            try:
                tag.TagOrientation = DB.TagOrientation.Vertical
            except Exception:
                it['vertical'] = False
    doc.Regenerate()
    offsets = {}
    for it, (key, tag, anchor) in zip(layout, entries):
        size = _size(view, tag) if tag.IsValidObject else None
        offsets[key] = (0.0, 0.0)
        if size is not None:
            w, h, offsets[key] = size
            it['length'], it['height'] = (h, w) if it.get('vertical') else (w, h)
    places = callout_layout.place_pointers(layout, box, gap, outside)
    for key, tag, anchor in entries:
        if key not in places or not tag.IsValidObject:
            continue
        _move_head(view, tag, places[key]['centre'], offsets[key])
        if isinstance(key, tuple):
            try:
                tag.HasLeader = False
            except Exception:
                pass
            placed.append(places[key]['box'])
            report['marks'] += 1
            continue
        try:
            tag.HasLeader = True
            tag.LeaderEndCondition = DB.LeaderEndCondition.Free
            refs = list(tag.GetTaggedReferences())
            if refs:
                tag.SetLeaderEnd(refs[0], anchor)
        except Exception:
            pass
        placed.append(places[key]['box'])
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
