# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — IStructE SMDSC 4th ed. 6.2.2 presentation of the bars in one view (T8.27), the rules in
nosa_utils.presentation and nosa_utils.callout_layout: each set lying in the view plane is drawn as one
typical bar (layers drawn over each other show different bars) with a Multi-Rebar Annotation as its indicator
line and the calling-up on its extension outside the member; under a beam elevation its link zones '(n@pitch)'
over one total calling-up per mark; in sections and elevations a mark over every cut bar and one per set lying
in the view, in rows outside the member with pointers; 'ALT' / 'STG'; a short 30 degree
oblique at curtailed ends; bars detailed on another drawing dashed with 'SEE DRG' (see_drawing, once the
view is on its sheet). Re-running replaces the bars' own annotations in the view. In a transaction.
"""
import math
import re

from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS

from nosa_utils import presentation
from nosa_utils.revit_helpers import get_id_value

_MM_PER_FT = 304.8
LINE_STYLE = u'NOSA Bar Ends'
DRAWING_PARAM = u'NOSA_Rebar_Group'
_OWN_NOTE = re.compile(u'^(\\(\\d+\\)|Alt\\.|Stg\\.|ALT|STG|SEE DRG .*|\\d{1,2}|COLUMN STRIP|MIDDLE STRIP|CH \\d+|'
                       u'R \\d+|BEAM ON R \\d+ TO ITS CENTRELINE - CENTRE OFF THE PLAN|CENTRE|ρ = .*|P\\d+|CONFINEMENT ZONE|KICKER|'
                       u'(PILE|X \\(mm\\)|Y \\(mm\\)|DIA \\(mm\\)|CUT-OFF \\(m\\))[\\r\\n][\\s\\S]*)$')   # ... and section numbers
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
    main = _main_line(rebar, 0, view)
    if main is None:
        return None
    along = main.Direction
    last_main = (_main_line(rebar, n - 1, view) if n > 1 else main) or main
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
            try:
                if sub.GetLineWeight(DB.GraphicsStyleType.Projection) != pen:
                    sub.SetLineWeight(pen, DB.GraphicsStyleType.Projection)
            except Exception:
                pass
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
    for mask in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.FilledRegion):
        note = mask.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if note is not None and note.AsString() == STUB_NOTE:
            gone.append(mask.Id)
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


def _note(doc, view, point, text, type_id, centre=False):
    try:
        opts = DB.TextNoteOptions(type_id)
        opts.HorizontalAlignment = DB.HorizontalTextAlignment.Center if centre else DB.HorizontalTextAlignment.Left
        return DB.TextNote.Create(doc, view.Id, point, text, opts)
    except Exception:
        return None


GAP_PAPER_MM = 1.5           # between texts
OUTSIDE_PAPER_MM = 6.0       # a calling-up past the member's edge
COLUMN_OUTSIDE_PAPER_MM = 3.0   # a column elevation's calling-up beside the column
CUT_OUTSIDE_PAPER_MM = 2.0   # a cut bar's mark, no pointer, next to the member's face
FREE_GAP_PAPER_MM = 0.5      # between the marks of cut bars side by side
CROP_MARGIN_PAPER_MM = 4.0   # the view's crop round its calling-up
ROW_PAPER_MM = 7.0           # between rows of indicator lines under a beam
ZONE_TAG = u'Full label - Dot'
POINTER_TAG = u'Mark only - Arrow'
CUT_TAG = u'Mark only - Dot'            # a mark over every bar a section cuts (SMDSC 4th ed. 6.2.3, user 2026-10-10)
ELEVATION_TAG = u'Full label - Arrow'   # main bars of an elevation: 'No centres' for beams and columns
SHORT_TAG = u'No centres - Dot'
SPACER_TAG = u'No centres - Arrow'      # '4H25-01 SPACERS': the count of the set, no centres (SMDSC 4th ed. MD B1)
TOTAL_STYLE = u'NOSA Total Lines'       # the line under a beam carrying a link mark's one calling-up
ELEVATION_KINDS = ('elevation', 'column_elevation')
# link zones called up level beside the member: a column's elevation, a base's starter links (user 2026-10-17)
LEVEL_ZONE_KINDS = ('column_elevation', 'footing_section')
PER_SET_KINDS = ('column_elevation',)   # one mark per cut set; sections mark every cut bar (user 2026-10-12)
CALLOUT_TAG = u'Callout - Dot'          # NOSA Rebar Tag 1.3.0
ZONE_QTY_TAG = u'Zone quantity - Dot'
CALLOUT_PARAM = u'NOSA_Rebar_Callout'
ZONE_QTY_PARAM = u'NOSA_Rebar_Zone_Qty'
LINK_RUN_GAP_MM = 1000.0     # zones of one mark further apart get their own total line under a beam
NOTE_PARAM = u'NOSA_Rebar_Note'          # L-BARS, U-BARS, LINKS ... after the calling-up
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


def _main_line(rebar, i, view=None):
    """
    The longest straight leg of bar i; for a bar of arcs only (T8.58 curved beams) a short line along its tangent,
    where a section cuts it (view given and not a plan) or at its middle.
    """
    curves = _centreline(rebar, i)
    lines = [c for c in curves if isinstance(c, DB.Line)]
    arcs = [c for c in curves if isinstance(c, DB.Arc)]
    line = max(lines, key=lambda c: c.Length) if lines else None
    arc = max(arcs, key=lambda c: c.Length) if arcs else None
    if arc is None or line is not None and line.Length >= arc.Length:
        return line                          # bends are short arcs: a straight leg is the bar's main line
    at = (arc.GetEndParameter(0) + arc.GetEndParameter(1)) / 2.0
    if view is not None and not _is_plan(view):
        try:
            at = arc.Project(view.Origin).Parameter
        except Exception:
            pass
    frame = arc.ComputeDerivatives(at, False)
    tangent = frame.BasisX.Normalize()
    half = min(arc.Length / 4.0, 50.0 / _MM_PER_FT)
    return DB.Line.CreateBound(frame.Origin - tangent.Multiply(half), frame.Origin + tangent.Multiply(half))


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


def _corners(element):
    """Model corners of a member's own concrete: its largest solid (a pile cap's piles left out), else its box."""
    best = None
    try:
        stack = list(element.get_Geometry(DB.Options()) or [])
    except Exception:
        stack = []
    while stack:
        g = stack.pop()
        if isinstance(g, DB.GeometryInstance):
            stack.extend(g.GetInstanceGeometry())
        elif isinstance(g, DB.Solid) and g.Volume > 0 and (best is None or g.Volume > best.Volume):
            best = g
    bb = best.GetBoundingBox() if best is not None else element.get_BoundingBox(None)
    if bb is None:
        return []
    t = bb.Transform if best is not None else DB.Transform.Identity
    return [t.OfPoint(DB.XYZ(x, y, z)) for x in (bb.Min.X, bb.Max.X) for y in (bb.Min.Y, bb.Max.Y)
            for z in (bb.Min.Z, bb.Max.Z)]


def _largest_solid(element):
    best = None
    try:
        stack = list(element.get_Geometry(DB.Options()) or [])
    except Exception:
        stack = []
    while stack:
        g = stack.pop()
        if isinstance(g, DB.GeometryInstance):
            stack.extend(g.GetInstanceGeometry())
        elif isinstance(g, DB.Solid) and g.Volume > 0 and (best is None or g.Volume > best.Volume):
            best = g
    return best


def _cut_outline(view, elements):
    """Box (view mm) of the members where the view's cut plane goes through them, None when it misses them."""
    try:
        crop = view.CropBox
        t = crop.Transform
        normal = t.BasisZ
        origin = t.OfPoint(DB.XYZ(0.0, 0.0, crop.Max.Z))
    except Exception:
        return None
    pts = []
    for e in elements:
        solid = _largest_solid(e)
        if solid is None:
            continue
        for edge in solid.Edges:
            try:
                ps = list(edge.Tessellate())
            except Exception:
                continue
            for p, q in zip(ps, ps[1:]):
                a, b = (p - origin).DotProduct(normal), (q - origin).DotProduct(normal)
                if a == b or a * b > 0:
                    continue
                f = a / (a - b)
                pts.append(_xy(view, p + (q - p).Multiply(f)))
    if len(pts) < 3:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _outline(view, elements):
    """Box (view mm) round the members."""
    pts = [_xy(view, c) for e in elements for c in _corners(e)]
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _size(view, tag, text=None):
    """
    (width, height across the view, offset of the text centre from the head) of a tag's text in view mm. From its
    text at the drawing's lettering size, not Revit's box: the NOSA Rebar Tag labels are boxes far wider than
    their text (some 50 mm on paper, measured 2026-10-10) and a Multi-Rebar Annotation's tag does not give its
    text; the text of every NOSA tag is centred on its head.
    """
    return _estimate(view, tag, text)


def _estimate(view, tag, text=None):
    """(width, height, offset) of a tag's text at the drawing's lettering size (Century Gothic, 2.5 mm)."""
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    if text is None:
        try:
            text = tag.TagText or u''
        except Exception:
            text = u''
    h = TEXT_PAPER_MM * scale
    w, t = (max(len(text), 2) * 0.58 + 0.2) * h, 1.3 * h     # Century Gothic: 0.57 h a character, measured
    try:
        if tag.TagOrientation == DB.TagOrientation.Vertical:
            return t, w, (0.0, 0.0)
    except Exception:
        pass
    return w, t, (0.0, 0.0)


def _zone_text(doc, d):
    """The calling-up an indicator line's tag writes (a Multi-Rebar Annotation's tag does not say), for its size."""
    rebar = d['rebar']
    try:
        dia = doc.GetElement(rebar.GetTypeId()).BarNominalDiameter * _MM_PER_FT
    except Exception:
        dia = 16.0
    return u'{}H{:.0f}-{}-{:.0f} B1 {}'.format(d['count'], dia, d['mark'], d.get('spacing') or 0.0,
                                              _text(rebar, NOTE_PARAM)).strip()


def _view_grids(view):
    """
    The grids a view shows. A plan shows them all, those its crop still leaves out too: the crop is the member's
    while the calling-ups are laid out, then grows round them (2026-10-18: grid C, past the slab, was missed).
    """
    if isinstance(view, DB.ViewPlan):
        return list(DB.FilteredElementCollector(view.Document).OfClass(DB.Grid))
    return list(DB.FilteredElementCollector(view.Document, view.Id).OfClass(DB.Grid))


def _grid_curves(grid, view):
    """
    A grid's lines in the view, at the model's extents: a new view's own are cut to its crop, which is still the
    member's when the calling-ups are laid out (2026-10-18: grid C, past the slab, was not there yet).
    """
    for extent in (DB.DatumExtentType.Model, DB.DatumExtentType.ViewSpecific):
        try:
            curves = list(grid.GetCurvesInView(extent, view))
            if curves:
                return curves
        except Exception:
            continue
    try:
        return [grid.Curve]
    except Exception:
        return []


def _grid_boxes(view, pad):
    """
    The upright grid lines the view draws as thin boxes, view mm: the side columns of texts keep off them (a level
    one would push a column the whole width of the view away).
    """
    out = []
    for g in _view_grids(view):
        curves = _grid_curves(g, view)
        for c in curves:
            a, b = _xy(view, c.GetEndPoint(0)), _xy(view, c.GetEndPoint(1))
            if abs(a[0] - b[0]) < 1.0:
                out.append((a[0] - pad, min(a[1], b[1]), a[0] + pad, max(a[1], b[1])))
    return out


def _grid_blocks(view):
    """The grid lines the view draws, as rows of marks meet them: {'top'/'bottom': [x], 'left'/'right': [y]}."""
    out = {'top': [], 'bottom': [], 'left': [], 'right': []}
    for g in _view_grids(view):
        curves = _grid_curves(g, view)
        for c in curves:
            a, b = _xy(view, c.GetEndPoint(0)), _xy(view, c.GetEndPoint(1))
            if abs(a[0] - b[0]) < 1.0:
                out['top'].append(a[0])
                out['bottom'].append(a[0])
            elif abs(a[1] - b[1]) < 1.0:
                out['left'].append(a[1])
                out['right'].append(a[1])
    return out


def _on_line(seg, c, vertical, tol=1.0):
    """A segment lying on the line at c (the bar the dimension measures)."""
    (p, q) = seg
    return abs(p[0] - c) < tol and abs(q[0] - c) < tol if vertical else abs(p[1] - c) < tol and abs(q[1] - c) < tol


def _drawn_lines(doc, view):
    """The detail lines and the dimension lines (indicator lines included) the view draws, view mm."""
    out = []
    for e in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.CurveElement):
        if getattr(e, 'ViewSpecific', False):
            try:
                c = e.GeometryCurve
                out.append((_xy(view, c.GetEndPoint(0)), _xy(view, c.GetEndPoint(1))))
            except Exception:
                continue
    for d in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.Dimension):
        try:
            direction = d.Curve.Direction
            segs = [(s.Origin, s.Value) for s in d.Segments] if d.NumberOfSegments else [(d.Origin, d.Value)]
        except Exception:
            continue
        for origin, value in segs:
            if origin is None or value is None:
                continue
            half = direction.Multiply(value / 2.0)
            out.append((_xy(view, origin - half), _xy(view, origin + half)))
    return out


def _seen_bars(view):
    """The straight bits of the bars drawn in the view, view mm: what a calling-up's line must not run along."""
    out = []
    doc = view.Document
    for r in DB.FilteredElementCollector(doc, view.Id).OfClass(DBS.Rebar):
        try:
            count = r.NumberOfBarPositions
        except Exception:
            count = 1
        for i in range(count):
            try:
                if r.IsBarHidden(view, i):
                    continue
                curves = r.GetTransformedCenterlineCurves(False, False, False,
                                                          DBS.MultiplanarOption.IncludeOnlyPlanarCurves, i)
            except Exception:
                continue
            for c in curves:
                if isinstance(c, DB.Line):
                    a, b = _xy(view, c.GetEndPoint(0)), _xy(view, c.GetEndPoint(1))
                    if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1.0:
                        out.append((a, b))
    return out


def _text_box(view, tag):
    """A tag's text as Revit writes it, view mm: its box less the part run on to the bar it tags."""
    from nosa_utils import annotation_audit
    bb = tag.get_BoundingBox(view)
    if bb is None:
        return None
    pts = [_xy(view, DB.XYZ(x, y, z)) for x in (bb.Min.X, bb.Max.X) for y in (bb.Min.Y, bb.Max.Y)
           for z in (bb.Min.Z, bb.Max.Z)]
    box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    return annotation_audit.centred_box(_xy(view, tag.TagHeadPosition), box)


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
    """A plan of bars; a member section drawn as a plan (a column's, looking down) is a section."""
    return isinstance(view, DB.ViewPlan) and u' - Section ' not in (view.Name or u'')


def _cut_depth(view):
    """Depth along the view direction of the plane the view cuts at (a plan's cut plane, a section's origin)."""
    if isinstance(view, DB.ViewPlan):
        try:
            rng = view.GetViewRange()
            level = view.Document.GetElement(rng.GetLevelId(DB.PlanViewPlane.CutPlane))
            return level.Elevation + rng.GetOffset(DB.PlanViewPlane.CutPlane)
        except Exception:
            pass
    return view.Origin.DotProduct(view.ViewDirection)


def apply(doc, view, rebars, det, mra_type_id=None, hosts=None, cover_mm=40.0, kind=None, sections=()):
    """
    SMDSC 4th ed. 6.2.2 / 3.3 in `view` for `rebars` (det: the rebar_detailing module): typical bars, indicator lines
    with their calling-up outside the member, a mark over every bar a section or elevation cuts and one per set
    lying in it, in rows outside the member; under a beam elevation its link zones '(n@pitch)' over one total
    calling-up per mark; 'ALT' / 'STG', 30 degree ends. kind: the view_plan kind of the view.
    Replaces the rebars' own annotations in the view.
    Returns {'typical', 'mra', 'marks', 'notes', 'ticks', 'inside'}.
    """
    report = {'typical': 0, 'mra': 0, 'marks': 0, 'notes': 0, 'ticks': 0, 'inside': 0}
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    gap, outside, row = GAP_PAPER_MM * scale, OUTSIDE_PAPER_MM * scale, ROW_PAPER_MM * scale
    style = _line_style(doc)
    total_style = _line_style(doc, TOTAL_STYLE, 1)
    section_style = _line_style(doc, SECTION_STYLE, SECTION_PEN)
    _clear(doc, view, (style, total_style, section_style))
    # only the bars of the members detailed (user 2026-10-12: a beam elevation showed the column bars)
    _hide_foreign(doc, view, rebars, hosts or ())
    # only the bars the view really draws: inside its crop and depth (a curved beam's 34 loose links all passed
    # IsHidden and stretched every section's crop to the whole beam, 2026-10-11)
    drawn = set(get_id_value(i) for i in DB.FilteredElementCollector(doc, view.Id).OfClass(DBS.Rebar).ToElementIds())
    visible = [r for r in rebars if r is not None and r.IsValidObject and not r.IsHidden(view)
               and get_id_value(r.Id) in drawn]
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
    box = None
    if not _is_plan(view) and kind not in ELEVATION_KINDS:
        # a section: the member as its plane cuts it (2026-10-18, an inclined beam's box ran far past its section)
        box = _cut_outline(view, [m for m in members if m is not None])
    box = box or _clip_to_crop(view, _outline(view, [m for m in members if m is not None]))
    if box is None:
        return report
    _concrete_fills(doc, view, [m for m in members if m is not None], kind)
    clusters = _single_groups(doc, rebars)
    text_type = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
    tag_types = _tag_types(doc)
    mra_type = doc.GetElement(mra_type_id) if mra_type_id is not None else None
    plan = _is_plan(view)
    zones, pointers, cut = [], [], []
    for rebar in visible:
        d = describe(view, rebar)
        if d is None:
            continue
        if presentation.is_typical_bar_set(d['view_dot'], d['spread_dir'] is not None) and mra_type is not None \
                and _shape_driven(rebar):
            d['layer'] = _text(rebar, u'NOSA_Rebar_Layer')
            zones.append(d)
            continue
        if d['view_dot'] >= 0.5 and not plan:
            if (kind == 'column_elevation' and _is_links(rebar) and d['spread_dir'] is not None
                    and mra_type is not None and _shape_driven(rebar)):
                # a column's links seen side on: their Multi-Rebar Annotation with the full calling-up in every
                # elevation (user 2026-10-12), not a mark over each leg
                d['layer'] = _text(rebar, u'NOSA_Rebar_Layer')
                zones.append(d)
                continue
            cut.append(d)
            continue
        if d['view_dot'] < 0.5 and hosts is not None:
            report['ticks'] += _ticks(doc, view, d, hosts, cover_mm, scale, style)
        pointers.append(d)
    if hosts and kind in ELEVATION_KINDS:
        # another member's bars ending inside these (a base's starter links up a column) are shown, not marked
        # leg by leg: they are called up on their own drawing (user 2026-10-18, C3)
        own = set(get_id_value(h.Id) for h in hosts if h is not None)
        cut = [d for d in cut if get_id_value(d['rebar'].GetHostId()) in own]
    _notes(doc, visible)
    elevation = kind in ELEVATION_KINDS
    # every bar one weight (user 2026-10-18, from the KIHBIT drawings: bars of one size drew thick and thin; this
    # replaces T9.19's heavy verticals and light horizontals on wall elevations)
    report['styles'] = bar_weights(view, visible)
    beam_elevation = not plan and kind in (None, 'elevation') and any(
        m is not None and m.Category is not None and
        get_id_value(m.Category.Id) == int(DB.BuiltInCategory.OST_StructuralFraming) for m in members)
    placed = []
    if sections:
        # first, so every calling-up keeps clear of them
        report['sections'] = _section_refs(doc, view, sections, box, placed, scale, section_style, text_type)
    viewers = _viewer_boxes(doc, view) if plan else []
    placed.extend(viewers)                           # the section marks drawn on a plan (user 2026-10-12)
    if kind == 'footing_section':
        # the column cut above the base: its calling-up outside all cut concrete (user 2026-10-17, F10)
        placed.extend(_other_concrete(doc, view, hosts or members))
    if hosts and elevation:
        # the levels first: the calling-up keeps off them (user 2026-10-12)
        report['geometry'] = _geometry(doc, view, hosts, kind, box, placed, scale)
    # arrows at bar ends on beam elevations and sections only: a wall elevation's trimmers filled it with them
    ended = [d for d in pointers if (beam_elevation or kind in SIZE_KINDS) and _end_marked(view, d)]
    joint = None
    grids = []
    if beam_elevation:
        # SMDSC 4th ed. 6.2.3 beam elevation: the main bars' calling-up close to the beam's faces, the arrows to where
        # each bar stops beyond it (user 2026-10-12), then where they stop dimensioned from the supports (T9.3) and
        # the link zones under them, each mark's '(n@pitch)' zones over its one total calling-up
        _marks(doc, view, pointers, cut, det, tag_types, box, gap, outside, placed, report, 'beam', clusters=clusters)
        _end_marks(doc, view, ended, tag_types, box, gap, scale, placed, report)
        report['curtailment'] = _curtailment(doc, view, pointers, box, placed, scale, total_style)
        if not zones:
            # with links the supports go in their string (user 2026-10-17)
            report['supports'] = _support_limits(doc, view, box, placed, scale, total_style)
        made = _beam_links(doc, view, zones, mra_type, det, box, gap, outside, row, placed, report, total_style)
    else:
        # a column's bars called up close beside it (user 2026-10-12)
        near = COLUMN_OUTSIDE_PAPER_MM * scale if kind == 'column_elevation' else outside
        bars_x = [x for d in pointers for x in _vertical_x(d)] if kind in LEVEL_ZONE_KINDS else []
        panel = kind == 'elevation' and any(isinstance(m, DB.Wall) for m in members)
        column = kind == 'column_elevation'
        joint = {'gap': gap, 'text_type': text_type, 'relations': presentation.relations(zones)} \
            if (plan or panel or column) else None
        if column:
            # a column's calling-ups in one column on its right, clear of the levels on its left (user 2026-10-12),
            # each on a line leaving its bar or indicator line square (2026-10-18 audit: oblique leaders)
            joint['side'] = 'right'
        made = _zones(doc, view, zones, mra_type, det, box, gap, near, row, placed, report,
                      level=kind in LEVEL_ZONE_KINDS, avoid=bars_x, panel=panel, joint=joint)
        if plan or panel:
            # a group of loose bars drawn as a zone is: its middle bar, the one called up, and a line across them
            # (W2, 2026-10-18: every vertical of a curved wall was drawn, its marks bunched with no telling whose)
            report['typical_singles'] = _typical_singles(doc, view, rebars, clusters, total_style)
        if plan or panel or column:
            _pointers(doc, view, pointers, det, tag_types, box, gap, near if column else outside, placed, report,
                      clusters=clusters, joint=joint)
        if joint is not None:
            # the grid lines drawn: a column of texts stands clear of them (2026-10-18 audit, S1: on grid C)
            grids = _grid_boxes(view, gap / 2.0)
            _layout_joint(doc, view, joint, box, gap, outside, placed, report, total_style, keep_off=grids,
                          neighbours=_neighbours(doc, view, hosts or members) if plan else ())
        if plan:
            if hosts and kind == 'plan':
                _plan_dims(doc, view, hosts, zones, box, placed, scale, total_style, report)
                report['strips'] = _strips(doc, view, hosts, box, placed, scale, total_style, text_type)
                report['arc'] = _arc_setting_out(doc, view, hosts, box, scale, total_style, text_type)
                report['piles'] = _pile_table(doc, view, hosts, box, placed, scale, text_type)
        else:
            # a section: the bars lying in it are told by the arrows at their ends, not by another mark
            ends = set(d['id'] for d in ended)
            items = pointers if elevation else [d for d in pointers if d['id'] not in ends]
            if panel or column:
                items = []                           # its loose bars went with its zones (_layout_joint)
            if panel:
                cut = []        # bars a wall elevation sees end on are called up on its sections (W2, 2026-10-18)
            # a column's main bars on its right, clear of the levels on its left (user 2026-10-12)
            _marks(doc, view, items, cut, det, tag_types, box, gap, near, placed, report, elevation,
                   per_set=kind in PER_SET_KINDS, clusters=clusters,
                   side='right' if kind == 'column_elevation' else None)
            _end_marks(doc, view, ended, tag_types, box, gap, scale, placed, report)
            if kind == 'column_elevation':
                report['laps'] = _column_laps(doc, view, pointers + zones, box, placed, scale, total_style)
                report['confinement'] = _confinement(doc, view, zones, box, placed, scale, total_style)
                report['kicker'] = _kicker(doc, view, hosts or members, box, placed, scale, total_style)
            elif kind == 'footing_section':
                report['starters'] = _starter_dims(doc, view, visible, box, placed, scale, total_style)
    stacked = joint.get('stacked', set()) if joint is not None else set()
    for a, _b, label in presentation.relations(zones):
        bx = made.get(a)
        if bx is None or a in stacked:
            continue
        point = _point(view, ((bx[0] + bx[2]) / 2.0, bx[1] - gap - TEXT_PAPER_MM * scale), made_origin(zones, a))
        if _note(doc, view, point, label, text_type):
            report['notes'] += 1
    if hosts and not elevation:
        # SMDSC 4th ed. 3.13 / 3.14.3 (T9.4): the member's size and levels from its own faces, so they follow the model
        report['geometry'] = _geometry(doc, view, hosts, kind, box, placed, scale)
        if kind == 'member_section':
            # under the section's own dimensions (T9.18)
            report['ratio'] = _column_ratio(doc, view, hosts, visible, box, placed, scale, text_type)
    _fit_crop(view, [box] + [q for q in placed if q not in viewers and q not in grids], CROP_MARGIN_PAPER_MM * scale)
    if beam_elevation:
        # SMDSC 4th ed. Fig. 6.24: the columns as short stubs under the beam, so the link zones, their calling-up
        # and dimensions below read clear (a crop would hide the dimensions: Revit drops those whose references
        # it crops out)
        report['stubs'] = _column_stubs(doc, view, box, scale, style)
    return report


def _hide_foreign(doc, view, rebars, hosts=()):
    """Hide in the view the bars of other members than the ones it details, but those ending inside them."""
    from System.Collections.Generic import List
    own = set(get_id_value(r.Id) for r in rebars if r is not None and r.IsValidObject)
    ids = List[DB.ElementId]()
    for r in DB.FilteredElementCollector(doc, view.Id).OfClass(DBS.Rebar):
        if get_id_value(r.Id) not in own and r.CanBeHidden(view) and not (hosts and _ends_inside(r, hosts)):
            ids.Add(r.Id)
    if ids.Count:
        try:
            view.HideElements(ids)
        except Exception:
            pass


CONCRETE_CUT_RGB = (255, 192, 155)     # NOSA 'Concrete - Generic' cut colour, when a member has no material


CONCRETE_CATEGORIES = ('OST_Floors', 'OST_StructuralFoundation', 'OST_StructuralFraming', 'OST_StructuralColumns',
                       'OST_Walls')


def _solid_fill(doc):
    for fp in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement):
        if fp.GetFillPattern().IsSolidFill:
            return fp
    return None


def _concrete_fills(doc, view, members, kind):
    """
    The concrete a view cuts in the cut colour - its members and the others round them; what it sees keeps the
    template's grey (user 2026-10-18: keep the grey on plans and elevations).
    """
    if _is_plan(view):
        return
    _concrete_cut(doc, view, members + _concrete_near(doc, members))


def _concrete_near(doc, members, reach_mm=None):
    """The concrete members round the ones detailed (within reach), the members themselves left out."""
    own = set(get_id_value(m.Id) for m in members)
    boxes = [m.get_BoundingBox(None) for m in members]
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return []
    r = (reach_mm or NEIGHBOUR_REACH_MM) / _MM_PER_FT
    near = DB.BoundingBoxIntersectsFilter(DB.Outline(
        DB.XYZ(min(b.Min.X for b in boxes) - r, min(b.Min.Y for b in boxes) - r, min(b.Min.Z for b in boxes) - r),
        DB.XYZ(max(b.Max.X for b in boxes) + r, max(b.Max.Y for b in boxes) + r, max(b.Max.Z for b in boxes) + r)))
    out = []
    for name in CONCRETE_CATEGORIES:
        for e in DB.FilteredElementCollector(doc).OfCategory(getattr(DB.BuiltInCategory, name)) \
                .WhereElementIsNotElementType().WherePasses(near):
            if get_id_value(e.Id) not in own:
                out.append(e)
    return out


def _concrete_cut(doc, view, members):
    """
    The members cut solid in their material's cut colour (user 2026-10-12: slabs, walls and columns came out
    blank at Coarse, where Revit draws walls and floors with their type's coarse fill instead).
    """
    solid = _solid_fill(doc)
    if solid is None:
        return
    for m in members:
        rgb = None
        ids = []
        try:
            ids = list(m.GetMaterialIds(False))
        except Exception:
            ids = []
        if not ids and m.Category is not None and m.Category.Material is not None:
            ids = [m.Category.Material.Id]
        for mid in ids:
            mat = doc.GetElement(mid)
            colour = getattr(mat, 'CutForegroundPatternColor', None)
            if colour is not None and colour.IsValid:
                rgb = (colour.Red, colour.Green, colour.Blue)
                break
        rgb = rgb or CONCRETE_CUT_RGB
        try:
            ogs = view.GetElementOverrides(m.Id)
            ogs.SetCutForegroundPatternId(solid.Id)
            ogs.SetCutForegroundPatternColor(DB.Color(rgb[0], rgb[1], rgb[2]))
            ogs.SetCutForegroundPatternVisible(True)
            view.SetElementOverrides(m.Id, ogs)
        except Exception:
            continue


NEIGHBOUR_REACH_MM = 15000.0


def _neighbours(doc, view, hosts, reach=NEIGHBOUR_REACH_MM):
    """
    View boxes (mm) of the other members at a plan's members' level within reach of them: the plan shows them
    once its crop grows round the calling-ups, so the columns of texts keep off them (2026-10-18, Revit 2026).
    """
    own = set(get_id_value(h.Id) for h in hosts if h is not None)
    boxes = [h.get_BoundingBox(None) for h in hosts if h is not None]
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return []
    r = reach / _MM_PER_FT
    lo = DB.XYZ(min(b.Min.X for b in boxes) - r, min(b.Min.Y for b in boxes) - r, min(b.Min.Z for b in boxes))
    hi = DB.XYZ(max(b.Max.X for b in boxes) + r, max(b.Max.Y for b in boxes) + r, max(b.Max.Z for b in boxes))
    near = DB.BoundingBoxIntersectsFilter(DB.Outline(lo, hi))
    out = []
    for cat in (DB.BuiltInCategory.OST_Floors, DB.BuiltInCategory.OST_StructuralFoundation,
                DB.BuiltInCategory.OST_Walls, DB.BuiltInCategory.OST_StructuralColumns,
                DB.BuiltInCategory.OST_StructuralFraming):
        for e in DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().WherePasses(near):
            if get_id_value(e.Id) in own:
                continue
            b = _box_in_view(view, e.get_BoundingBox(None))
            if b is not None:
                out.append(b)
    return out


def _other_concrete(doc, view, hosts):
    """View boxes (mm) of the columns and walls a section draws besides its members, cut to the view's crop."""
    own = set(get_id_value(h.Id) for h in hosts if h is not None)
    crop = _clip_to_crop(view, (-1e9, -1e9, 1e9, 1e9))
    out = []
    for cat in (DB.BuiltInCategory.OST_StructuralColumns, DB.BuiltInCategory.OST_Walls):
        for e in DB.FilteredElementCollector(doc, view.Id).OfCategory(cat).WhereElementIsNotElementType():
            if get_id_value(e.Id) in own:
                continue
            bb = e.get_BoundingBox(None)
            if bb is None:
                continue
            pts = [_xy(view, DB.XYZ(x, y, z)) for x in (bb.Min.X, bb.Max.X) for y in (bb.Min.Y, bb.Max.Y)
                   for z in (bb.Min.Z, bb.Max.Z)]
            b = (max(crop[0], min(p[0] for p in pts)), max(crop[1], min(p[1] for p in pts)),
                 min(crop[2], max(p[0] for p in pts)), min(crop[3], max(p[1] for p in pts)))
            if b[0] < b[2] and b[1] < b[3]:
                out.append(b)
    return out


VIEWER_HEAD_PAPER_MM = 9.0     # round a section mark's head on a plan: its bubble and arrow


def _viewer_boxes(doc, view):
    """
    View boxes (mm) of the section marks a plan draws, for the calling-up to keep off: each one's cut line and its
    two heads - not the box of its depth, which covered the member and drove every text far off it (user
    2026-10-17, F10 plan).
    """
    out = []
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    head = VIEWER_HEAD_PAPER_MM * scale
    sections = {}
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewSection):
        try:
            sections.setdefault(v.Name, v)
        except Exception:
            continue
    for viewer in DB.FilteredElementCollector(doc, view.Id).OfCategory(DB.BuiltInCategory.OST_Viewers):
        line = None
        section = sections.get(viewer.Name)
        if section is not None:
            try:
                crop = section.CropBox
                t = crop.Transform
                line = (_xy(view, t.OfPoint(DB.XYZ(crop.Min.X, 0.0, crop.Max.Z))),
                        _xy(view, t.OfPoint(DB.XYZ(crop.Max.X, 0.0, crop.Max.Z))))
            except Exception:
                line = None
        if line is not None and (abs(line[1][0] - line[0][0]) + abs(line[1][1] - line[0][1])) > 1.0:
            a, b = line
            out.append((min(a[0], b[0]) - head / 6.0, min(a[1], b[1]) - head / 6.0,
                        max(a[0], b[0]) + head / 6.0, max(a[1], b[1]) + head / 6.0))
            for p in (a, b):
                out.append((p[0] - head, p[1] - head, p[0] + head, p[1] + head))
            # and the heads where Revit draws them: the ends of the mark's own box (2026-10-18 audit: a text in
            # the column ran into head E, drawn past the crop's end)
            try:
                drawn = _box_in_view(view, viewer.get_BoundingBox(view))
            except Exception:
                drawn = None
            if drawn is not None:
                # along the line to the drawn ends only: across it the box is the section's depth
                if abs(b[0] - a[0]) >= abs(b[1] - a[1]):
                    y = (a[1] + b[1]) / 2.0
                    out.append((drawn[0], y - head, drawn[0] + 2.0 * head, y + head))
                    out.append((drawn[2] - 2.0 * head, y - head, drawn[2], y + head))
                else:
                    x = (a[0] + b[0]) / 2.0
                    out.append((x - head, drawn[1], x + head, drawn[1] + 2.0 * head))
                    out.append((x - head, drawn[3] - 2.0 * head, x + head, drawn[3]))
            continue
        try:
            bb = viewer.get_BoundingBox(view)
        except Exception:
            bb = None
        if bb is None:
            continue
        pts = [_xy(view, bb.Transform.OfPoint(DB.XYZ(x, y, z))) for x in (bb.Min.X, bb.Max.X)
               for y in (bb.Min.Y, bb.Max.Y) for z in (bb.Min.Z, bb.Max.Z)]
        out.append((min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)))
    return out


def _is_links(rebar):
    return _text(rebar, NOTE_PARAM).startswith(u'LINKS') or _text(rebar, u'NOSA_Rebar_Layer').startswith(u'stirrup')


TYPICAL_SINGLES_MIN = 3     # a group this large shows only its middle bar


def _typical_singles(doc, view, rebars, clusters, style):
    """
    Each group of loose single bars (clusters) shown as SMDSC shows a set: its middle bar - the one merge_singles
    calls up - and a line across the group from its first bar to its last; the others hidden in the view.
    Returns how many bars hidden.
    """
    from System.Collections.Generic import List
    by_id = dict((get_id_value(r.Id), r) for r in rebars if r is not None and r.IsValidObject)
    groups = {}
    for rid, (gid, size) in (clusters or {}).items():
        if size >= TYPICAL_SINGLES_MIN and rid in by_id:
            groups.setdefault(gid, []).append(by_id[rid])
    hide = List[DB.ElementId]()
    for bars in groups.values():
        placed_ = []
        for r in bars:
            line = _main_line(r, 0)
            if line is not None:
                placed_.append((_xy(view, line.Evaluate(0.5, True)), r, line))
        if len(placed_) < TYPICAL_SINGLES_MIN:
            continue
        placed_.sort(key=lambda e: (round(e[0][0], 3), round(e[0][1], 3)))
        lead = placed_[len(placed_) // 2][1]
        for _p, r, _l in placed_:
            if r.Id != lead.Id and r.CanBeHidden(view):
                hide.Add(r.Id)
        a, b = placed_[0][0], placed_[-1][0]
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) > 1.0:
            _draw_path(doc, view, [a, b], placed_[0][2].Evaluate(0.5, True), style)
    if hide.Count:
        try:
            view.HideElements(hide)
        except Exception:
            return 0
    return hide.Count


def _single_groups(doc, rebars):
    """{id: (group, size)} of the loose single bars of the members (presentation.single_clusters)."""
    bars = []
    for r in rebars:
        try:
            if r is None or not r.IsValidObject or r.NumberOfBarPositions != 1 or not mark_of(r):
                continue
        except Exception:
            continue
        line = _main_line(r, 0)
        if line is None:
            continue
        a, b = line.GetEndPoint(0), line.GetEndPoint(1)
        key = (mark_of(r), get_id_value(r.GetTypeId()), _text(r, u'NOSA_Rebar_Layer'), get_id_value(r.GetHostId()))
        bars.append((get_id_value(r.Id), key, (a.X * _MM_PER_FT, a.Y * _MM_PER_FT, a.Z * _MM_PER_FT),
                     (b.X * _MM_PER_FT, b.Y * _MM_PER_FT, b.Z * _MM_PER_FT)))
    return presentation.single_clusters(bars)


STUB_MM = 300.0              # column stub drawn under a beam elevation
STUB_NOTE = u'NOSA stub'     # Comments of the masking regions that cut the columns to stubs


SIZE_KINDS = ('member_section', 'wall_section', 'slab_section', 'footing_section')


def _face_refs(view, element):
    """[(normal, reference, a point on the face)] of the element's planar faces, with references for dimensions."""
    out = []
    opts = DB.Options()
    opts.ComputeReferences = True
    opts.View = view
    try:
        geometry = element.get_Geometry(opts)
    except Exception:
        return out
    # an uncut family instance (a column) keeps its faces in the symbol geometry: only those references can be
    # dimensioned, so they are read there and moved by the instance transform
    stack = [(g, DB.Transform.Identity) for g in geometry] if geometry is not None else []
    while stack:
        g, t = stack.pop()
        if isinstance(g, DB.GeometryInstance):
            stack.extend((s, t.Multiply(g.Transform)) for s in g.GetSymbolGeometry())
            continue
        if not isinstance(g, DB.Solid) or g.Volume <= 0:
            continue
        for face in g.Faces:
            if isinstance(face, DB.PlanarFace) and face.Reference is not None:
                out.append((t.OfVector(face.FaceNormal), face.Reference, t.OfPoint(face.Origin)))
    return out


def _extreme_pair(faces, direction, view):
    """The two faces facing -direction and +direction furthest apart (the member's two outer faces)."""
    lo = [(f[2].DotProduct(direction), f) for f in faces if f[0].DotProduct(direction) < -0.99]
    hi = [(f[2].DotProduct(direction), f) for f in faces if f[0].DotProduct(direction) > 0.99]
    if not lo or not hi:
        return None
    return min(lo, key=lambda e: e[0])[1], max(hi, key=lambda e: e[0])[1]


def _geometry(doc, view, hosts, kind, box, placed, scale):
    """
    Member sections: overall width under the section and depth beside it; slab and base sections: thickness
    at the left end; beam and column elevations: spot levels on the top (and a column's bottom) face.
    Laid out beyond what is already placed. Returns how many dimensions and levels.
    """
    made = 0
    gap = GAP_PAPER_MM * scale
    row = ROW_PAPER_MM * scale
    like = view.Origin
    mra_dims = set()
    for mra in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.MultiReferenceAnnotation):
        mra_dims.add(get_id_value(mra.DimensionId))
    for dim in list(DB.FilteredElementCollector(doc, view.Id).OfClass(DB.Dimension)):
        # an earlier pass's size dimensions and levels (the zone chains went with their witness ticks)
        if get_id_value(dim.Id) in mra_dims:
            continue
        refs = [dim.References.get_Item(i) for i in range(dim.References.Size)] if dim.References else []
        if isinstance(dim, DB.SpotDimension) or refs and all(r.ElementReferenceType ==
                                                              DB.ElementReferenceType.REFERENCE_TYPE_SURFACE
                                                              for r in refs):
            try:
                doc.Delete(dim.Id)
            except Exception:
                pass
    lo_y = min([box[1]] + [q[1] for q in placed])
    hi_x = max([box[2]] + [q[2] for q in placed])
    lo_x = min([box[0]] + [q[0] for q in placed])
    try:
        # only members this view draws: a coplanar face of the next span would give a dimension the view hides
        shown = set(get_id_value(i) for i in DB.FilteredElementCollector(doc, view.Id).ToElementIds())
    except Exception:
        shown = None
    faces = [f for h in hosts if shown is None or get_id_value(h.Id) in shown for f in _face_refs(view, h)]
    if kind in SIZE_KINDS:
        pairs = []
        if kind in ('member_section', 'wall_section'):
            pairs.append((view.RightDirection, 'below'))
        pairs.append((view.UpDirection, 'left' if kind in ('slab_section', 'footing_section') else 'right'))
        for direction, side in pairs:
            pair = _extreme_pair(faces, direction, view)
            if pair is None:
                continue
            refs = DB.ReferenceArray()
            refs.Append(pair[0][1])
            refs.Append(pair[1][1])
            if side == 'below':
                y = lo_y - row
                a, b = (box[0], y), (box[2], y)
                placed.append((box[0], y - row / 2.0, box[2], y + row / 2.0))
            else:
                if side == 'right' and hi_x - box[2] > box[0] - lo_x + row:
                    side = 'left'          # the side the calling-up leaves clearer (B12: a link's mark on the right)
                x = hi_x + row if side == 'right' else lo_x - row
                a, b = (x, box[1]), (x, box[3])
                placed.append((x - row / 2.0, box[1], x + row / 2.0, box[3]))
            try:
                doc.Create.NewDimension(view, DB.Line.CreateBound(_point(view, a, like), _point(view, b, like)), refs)
                made += 1
            except Exception:
                continue
    elif kind in ('elevation', 'column_elevation'):
        up = DB.XYZ.BasisZ
        tops = [f for f in faces if f[0].DotProduct(up) > 0.99]
        bottoms = [f for f in faces if f[0].DotProduct(up) < -0.99] if kind == 'column_elevation' else []
        for group, pick in ((tops, max), (bottoms, min)):
            if not group:
                continue
            face = pick(group, key=lambda f: f[2].Z)
            at = _xy(view, face[2])
            point = face[2]                          # on the face itself (the outline's end may lie in a column)
            # just past the member's own face: a leader out to the furthest calling-up would widen the crop over
            # the next element (column C2 came into C1's elevation)
            end = _point(view, (box[0] - 3.5 * row, at[1]), face[2])     # its figures clear of the member
            bend = _point(view, (box[0] - 1.0 * row, at[1]), face[2])
            try:
                spot = doc.Create.NewSpotElevation(view, face[1], point, bend, end, point, True)
                level_type = _level_type(doc, spot)
                if level_type is not None:
                    spot.ChangeTypeId(level_type)
                placed.append((box[0] - 5.0 * row, at[1] - row / 2.0, box[0], at[1] + row / 2.0))
                made += 1
            except Exception:
                continue
    return made


LEVEL_TYPE = u'NOSA RC level'
LEVEL_TEXT_FROM_SYMBOL_MM = 11.0      # the level's figures clear of its triangle (user 2026-10-12)


def _level_type(doc, spot):
    """The spot elevation type of the RC drawings: the default one with its text clear of the symbol."""
    found = None
    for t in DB.FilteredElementCollector(doc).OfClass(DB.SpotDimensionType):
        if DB.Element.Name.GetValue(t) == LEVEL_TYPE:
            found = t
    try:
        found = found or doc.GetElement(spot.GetTypeId()).Duplicate(LEVEL_TYPE)
        p = found.LookupParameter(u'Text Offset from Symbol')
        if p is not None and not p.IsReadOnly and abs(p.AsDouble() * _MM_PER_FT - LEVEL_TEXT_FROM_SYMBOL_MM) > 0.01:
            p.Set(LEVEL_TEXT_FROM_SYMBOL_MM / _MM_PER_FT)
        return found.Id
    except Exception:
        return found.Id if found is not None else None


def _column_stubs(doc, view, box, scale, style):
    """
    Each column under the beam in `box` cut off STUB_MM below its soffit: a masking region over the rest down to
    the crop and a break line across the stub. Returns how many.
    """
    try:
        crop_low = min(_xy(view, view.CropBox.Transform.OfPoint(DB.XYZ(x, y, view.CropBox.Max.Z)))[1]
                       for x in (view.CropBox.Min.X, view.CropBox.Max.X)
                       for y in (view.CropBox.Min.Y, view.CropBox.Max.Y))
        cols = DB.FilteredElementCollector(doc, view.Id).OfCategory(DB.BuiltInCategory.OST_StructuralColumns) \
            .WhereElementIsNotElementType().ToElements()
    except Exception:
        return 0
    from System.Collections.Generic import List
    invisible = None
    for sid in DB.FilledRegion.GetValidLineStyleIdsForFilledRegion(doc):
        style_el = doc.GetElement(sid)
        if style_el is not None and u'Invisible' in (style_el.Name or u''):
            invisible = sid                  # the mask's own outline must not show
            break
    like = view.Origin
    made = 0
    pad = 0.5 * scale
    cut = box[1] - STUB_MM
    for col in cols:
        o = _outline(view, [col])
        if o is None or not (o[1] < cut < o[3]):
            continue
        x0, x1, y0 = o[0] - pad, o[2] + pad, max(o[1], crop_low) - pad
        loop = DB.CurveLoop()
        pts = [(x0, y0), (x1, y0), (x1, cut), (x0, cut)]
        try:
            for i in range(4):
                loop.Append(DB.Line.CreateBound(_point(view, pts[i], like), _point(view, pts[(i + 1) % 4], like)))
            loops = List[DB.CurveLoop]()
            loops.Add(loop)
            mask = DB.FilledRegion.CreateMaskingRegion(doc, view.Id, loops)
            if invisible is not None:
                mask.SetLineStyleId(invisible)
            note = mask.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if note is not None and not note.IsReadOnly:
                note.Set(STUB_NOTE)
        except Exception:
            continue
        # break line: straight across with one zigzag in the middle
        m, z = (o[0] + o[2]) / 2.0, 1.5 * scale
        zig = [(o[0] - pad, cut), (m - z, cut), (m - z / 2.0, cut + z), (m + z / 2.0, cut - z), (m + z, cut),
               (o[2] + pad, cut)]
        for a, b in zip(zig, zig[1:]):
            try:
                curve = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_point(view, a, like),
                                                                            _point(view, b, like)))
                if style is not None:
                    curve.LineStyle = style
            except Exception:
                continue
        made += 1
    return made


def _crop_bottom(view, y):
    """Move the bottom of the view's crop to view height y (mm)."""
    try:
        crop = view.CropBox
        t = crop.Transform
        o = t.Origin.DotProduct(view.UpDirection) * _MM_PER_FT
        sy = 1.0 if t.BasisY.DotProduct(view.UpDirection) > 0 else -1.0
        value = sy * (y - o) / _MM_PER_FT
        if sy > 0 and value < crop.Max.Y:
            crop.Min = DB.XYZ(crop.Min.X, value, crop.Min.Z)
        elif sy < 0 and value > crop.Min.Y:
            crop.Max = DB.XYZ(crop.Max.X, value, crop.Max.Z)
        else:
            return
        view.CropBox = crop
    except Exception:
        pass


SECTION_STYLE = u'NOSA Section Marks'
SECTION_PEN = 3     # tick and arrow one weight (user 2026-10-18: the marks mixed thick and thin lines)
SECTION_TICK_PAPER_MM = 5.0


def _section_refs(doc, view, sections, box, placed, scale, style, text_type):
    """
    Where each numbered section cuts the member, SMDSC 4th ed. Fig. 6.24: a short thick line just past each face,
    an arrow from its outer end the way the section looks (user 2026-10-12) and the section number at the arrow,
    across a long member (beam: above and below; column: left and right). Returns how many.
    """
    gap, tick = GAP_PAPER_MM * scale, SECTION_TICK_PAPER_MM * scale
    text = TEXT_PAPER_MM * scale
    arrow = SECTION_ARROW_PAPER_MM * scale
    tall = (box[3] - box[1]) > (box[2] - box[0])
    made = 0
    for origin, number, look in sections:
        a = _xy(view, origin)
        look2 = _xy(view, look)
        n = (look2[0] ** 2 + look2[1] ** 2) ** 0.5
        look2 = (look2[0] / n, look2[1] / n) if n > 1e-6 else None
        if tall:
            if not box[1] - gap < a[1] < box[3] + gap:
                continue
            ends = [((box[0] - gap - tick, a[1]), (box[0] - gap, a[1]), (box[0] - 2 * gap - tick - text, a[1])),
                    ((box[2] + gap, a[1]), (box[2] + gap + tick, a[1]), (box[2] + 2 * gap + tick, a[1]))]
        else:
            if not box[0] - gap < a[0] < box[2] + gap:
                continue
            ends = [((a[0], box[3] + gap), (a[0], box[3] + gap + tick), (a[0] - text / 2.0, box[3] + 2 * gap + tick + text)),
                    ((a[0], box[1] - gap - tick), (a[0], box[1] - gap), (a[0] - text / 2.0, box[1] - 2 * gap - tick))]
        for k, (p, q, at) in enumerate(ends):
            try:
                curve = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_point(view, p, origin),
                                                                            _point(view, q, origin)))
                if style is not None:
                    curve.LineStyle = style
            except Exception:
                continue
            outer = q if k == 0 and not tall or k == 1 and tall else p      # the tick's end away from the member
            extra = []
            if look2 is not None:
                tip = (outer[0] + look2[0] * arrow, outer[1] + look2[1] * arrow)
                head = 0.4 * arrow
                side = (-look2[1], look2[0])
                for seg in ((outer, tip), (tip, (tip[0] - look2[0] * head + side[0] * head * 0.5,
                                                 tip[1] - look2[1] * head + side[1] * head * 0.5)),
                            (tip, (tip[0] - look2[0] * head - side[0] * head * 0.5,
                                   tip[1] - look2[1] * head - side[1] * head * 0.5))):
                    try:
                        c = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_point(view, seg[0], origin),
                                                                                _point(view, seg[1], origin)))
                        if style is not None:
                            c.LineStyle = section_arrow_style(doc) or style
                    except Exception:
                        continue
                extra = [tip]
            _note(doc, view, _point(view, at, origin), number, text_type)
            xs = [p[0], q[0], at[0], at[0] + text] + [e[0] for e in extra]
            ys = [p[1], q[1], at[1], at[1] - text] + [e[1] for e in extra]
            placed.append((min(xs) - gap, min(ys) - gap, max(xs) + gap, max(ys) + gap))
        made += 1
    return made


SECTION_ARROW_PAPER_MM = 4.0


def section_arrow_style(doc):
    """A section mark's arrow: the tick's own style, so the whole mark is one weight (user 2026-10-18)."""
    return _line_style(doc, SECTION_STYLE, SECTION_PEN)


def _strip_note(text, note):
    """A tag's text without the bar note at its end (the label may carry NOSA_Rebar_Note already)."""
    text = (text or u'').strip()
    if note and text.endswith(note):
        text = text[:-len(note)].strip()
    return text


def _notes(doc, rebars):
    """
    NOSA_Rebar_Note of each set from its shape (user 2026-10-10): L-BARS, U-BARS, LINKS, LINKS IN 2s where two
    links of a host stand at each position; blank for straight bars.
    """
    shapes, links = {}, {}
    for r in rebars:
        try:
            code = DB.Element.Name.GetValue(doc.GetElement(r.GetShapeId()))
        except Exception:
            code = _text(r, u'NOSA_Rebar_Shape_Code')
        shapes[get_id_value(r.Id)] = code
        if presentation.bar_note(code) == u'LINKS':
            line = _main_line(r, 0)
            if line is not None:
                links.setdefault(get_id_value(r.GetHostId()), []).append((r, line.Evaluate(0.5, True)))
    twos = set()
    for sets in links.values():
        for i, (a, pa) in enumerate(sets):
            for b, pb in sets[i + 1:]:
                if a.NumberOfBarPositions == b.NumberOfBarPositions and _same_station(a, pa, b, pb):
                    twos.update((get_id_value(a.Id), get_id_value(b.Id)))
    for r in rebars:
        rid = get_id_value(r.Id)
        p = r.LookupParameter(NOTE_PARAM)
        if p is not None and not p.IsReadOnly:
            p.Set(presentation.bar_note(shapes.get(rid), rid in twos, _text(r, u'NOSA_Rebar_Layer')))


def _same_station(a, pa, b, pb, tol_mm=30.0):
    """Two link sets whose first links stand at the same place along the member (links in 2s)."""
    try:
        n = a.GetShapeDrivenAccessor().Normal
    except Exception:
        return False
    return abs((pa - pb).DotProduct(n)) * _MM_PER_FT <= tol_mm


def _free_ends(chain):
    """The ends of a bar's longest straight leg that are ends of the bar itself (not a bend into another leg)."""
    lines = [c for c in chain if isinstance(c, DB.Line)]
    if not lines:
        return None, []
    main = max(lines, key=lambda c: c.Length)
    tips = [chain[0].GetEndPoint(0), chain[-1].GetEndPoint(1)]
    if tips[0].DistanceTo(tips[1]) < 60.0 / _MM_PER_FT:
        return main, []                                   # a closed link
    return main, [p for p in (main.GetEndPoint(0), main.GetEndPoint(1))
                  if any(p.DistanceTo(t) < 1.0 / _MM_PER_FT for t in tips)]


def _end_marked(view, d):
    """A bar lying across the view (a beam's or a slab's) with a free end along it: that end gets its arrow."""
    if d['view_dot'] >= 0.5 or abs(d['bar_dir'][0]) < 0.9 or not d['chain']:
        return False
    return bool(_free_ends(d['chain'])[1])


END_ROWS = 6


def _end_marks(doc, view, items, tag_types, box, gap, scale, placed, report):
    """
    Where each bar lying in a section or elevation stops (user 2026-10-12, SMDSC 4th ed. Fig. 6.24): a short
    horizontal arrow beside the bar, its tip level with the end, the bar's mark at its tail; beside the outer face
    the bar is nearer, row after row until clear of what is already drawn. Closed links have no ends.
    """
    from nosa_utils import callout_layout
    type_id = tag_types.get(POINTER_TAG)
    if type_id is None:
        return
    mid = (box[1] + box[3]) / 2.0
    pending = []
    for d in items:
        rebar = d['rebar']
        index = _shown_bar(view, rebar, d['count'])
        main, free = _free_ends(_centreline(rebar, index) or d['chain'])
        if main is None or not free:
            continue
        a, b = _xy(view, main.GetEndPoint(0)), _xy(view, main.GetEndPoint(1))
        side = (0.0, 1.0) if (a[1] + b[1]) / 2.0 > mid else (0.0, -1.0)
        left = min(a[0], b[0])
        for e in [_xy(view, p) for p in free]:
            outward = (-1.0, 0.0) if abs(e[0] - left) < 1.0 else (1.0, 0.0)
            try:
                tag, _i = _tag_bar(doc, view, rebar, index, type_id)
            except Exception:
                tag = None
            if tag is None:
                continue
            w, h, offset = _estimate(view, tag)
            spot = None
            for k in range(END_ROWS):
                tip, c, bx = presentation.end_arrow(e, outward, side, w, h, scale, gap, row=k)
                lane = (min(bx[0], tip[0]), bx[1], max(bx[2], tip[0]), bx[3])
                if not any(callout_layout.overlap(lane, q, gap / 2.0) for q in placed):
                    spot = (tip, c, lane)
                    break
            if spot is None:
                doc.Delete(tag.Id)
                continue
            _move_head(view, tag, spot[1], offset)
            pending.append((tag, 'h', spot[0]))
            try:
                tag.HasLeader = True
                tag.LeaderEndCondition = DB.LeaderEndCondition.Free
                refs = list(tag.GetTaggedReferences())
                if refs:
                    tag.SetLeaderEnd(refs[0], _point(view, spot[0], main.GetEndPoint(0)))
            except Exception:
                pass
            placed.append(spot[2])
            report['marks'] += 1
    _line_up(doc, view, pending)


def _shape_driven(rebar):
    """A Rebar Set (a typical bar and an indicator line can show it); a FreeForm group cannot."""
    try:
        return rebar.IsRebarShapeDriven()
    except Exception:
        return True


def _clip_to_crop(view, box):
    """
    The member's outline cut to the view's crop in a section: a section across a curved beam would otherwise take
    the whole arc projected (6-9 m) as the member and lay the calling-up and the crop out to it (2026-10-11).
    """
    if box is None or _is_plan(view):
        return box
    try:
        if not view.CropBoxActive:
            return box
        crop = view.CropBox
        pts = [_xy(view, crop.Transform.OfPoint(DB.XYZ(x, y, crop.Max.Z)))
               for x in (crop.Min.X, crop.Max.X) for y in (crop.Min.Y, crop.Max.Y)]
        clipped = (max(box[0], min(p[0] for p in pts)), max(box[1], min(p[1] for p in pts)),
                   min(box[2], max(p[0] for p in pts)), min(box[3], max(p[1] for p in pts)))
        return clipped if clipped[0] < clipped[2] and clipped[1] < clipped[3] else box
    except Exception:
        return box


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


def _zones(doc, view, zones, mra_type, det, box, gap, outside, row, placed, report, level=False, avoid=(),
           panel=False, joint=None):
    """
    Typical bar, indicator line and calling-up of every zone; {id: text box}. level: every text horizontal. panel:
    a wall's elevation, laid out as a plan is (user 2026-10-18, W10: texts beside their zones, not round the wall).
    """
    from nosa_utils import callout_layout
    flat = _is_plan(view) or panel
    slots = presentation.layer_slots(zones)
    pending = []
    if flat:
        # a slab's openings: no calling-up in the hole (user 2026-10-18, S1 trimmers)
        seen = set()
        for z in zones:
            hid = get_id_value(z['rebar'].GetHostId())
            if hid in seen:
                continue
            seen.add(hid)
            host = doc.GetElement(z['rebar'].GetHostId())
            if host is not None:
                placed.extend(_openings(view, host))      # no text in a hole, whatever places it
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
        # the indicator line crosses the typical bar off its middle: through the middle it ran along the other
        # direction's typical bar (user 2026-10-12, PC10 plan)
        junction = shown.Evaluate(presentation.junction_fraction(frac) if flat else frac, True)
        if avoid and not flat:
            # the indicator line between the bars seen along it, not over one (user 2026-10-18, C1 elevation)
            ts = [k / 40.0 for k in range(4, 37)]
            xs = [_xy(view, shown.Evaluate(t, True))[0] for t in ts]
            best = presentation.clearest(xs, avoid)
            if best is not None:
                junction = shown.Evaluate(ts[best], True)
        t = sorted((ln.Evaluate(0.5, True) - junction).DotProduct(direction) for ln in (first, last))
        a3, b3 = junction + direction.Multiply(t[0]), junction + direction.Multiply(t[1])
        mra = _mra(doc, view, mra_type, rebar, junction, direction, b3, False)
        if mra is None:
            continue
        report['mra'] += 1
        if _no_real_pitch(rebar):
            # two layers of lacers laid out by a nominal 10000 pitch: '2H12-04 LINKS', no centres
            short = _tag_types(doc).get(SHORT_TAG)
            try:
                if short is not None:
                    doc.GetElement(mra.TagId).ChangeTypeId(short)
            except Exception:
                pass
        pending.append((d, mra, a3, b3, junction))
    doc.Regenerate()
    made, line_up = {}, []
    for d, mra, a3, b3, _o in pending:
        tag = doc.GetElement(mra.TagId)
        if tag is None:
            continue
        a, b = _xy(view, a3), _xy(view, b3)
        if abs(b[1] - a[1]) > abs(b[0] - a[0]) and not (flat or level):
            try:
                tag.TagOrientation = DB.TagOrientation.Vertical
            except Exception:
                pass
    doc.Regenerate()
    if flat or joint is not None:
        return _aligned_zones(doc, view, pending, joint if joint is not None else {'gap': gap})
    for d, mra, a3, b3, junction in pending:
        tag = doc.GetElement(mra.TagId)
        if tag is None:
            continue
        # each set its own calling-up with its own count, even when another set is identical (user 2026-10-12:
        # one total over both ends of a wall with '(15)' at each read wrong)
        w, h, offset = _size(view, tag, _full_label(doc, view, d, tag.GetTypeId()) or _zone_text(doc, d))
        a, b = _xy(view, a3), _xy(view, b3)
        line_vertical = abs(b[1] - a[1]) > abs(b[0] - a[0])
        # a plan's calling-up reads level, and a column elevation's link zones (user 2026-10-17: as the bars')
        vertical = line_vertical and not (flat or level)
        # the text's extent along its line and across it (its box in the view)
        length, height = (h, w) if line_vertical else (w, h)
        if level and line_vertical and _beside_column(view, tag, a, b, _xy(view, junction), junction, w, h, offset,
                                                      box, placed, gap, outside):
            report['beside'] = report.get('beside', 0) + 1
            made[d['id']] = placed[-1]
            continue
        r = presentation_place(a, b, length, height, box, placed, gap, outside)
        _move_head(view, tag, r['centre'], offset)
        try:
            tag.HasLeader = bool(r['outside'])
        except Exception:
            pass
        if r['outside']:
            if not _square_mra(view, tag, a, b, r, length, a3):
                # on its line's extension: the leader's attach point put on the line
                line_up.append((tag, 'v' if vertical else 'h', r['centre']))
        else:
            report['inside'] += 1
        made[d['id']] = r['box']
    _line_up(doc, view, line_up)
    return made


def _skew(a, b, lo_deg=20.0, hi_deg=70.0):
    """A bar neither level nor upright in the view: lo_deg to hi_deg off the level."""
    import math
    angle = math.degrees(math.atan2(abs(b[1] - a[1]), abs(b[0] - a[0])))
    return lo_deg < angle < hi_deg


def _vertical_x(d):
    """The view x (mm) of a bar seen along its length up the view, else nothing."""
    (ax, ay), (bx, by) = d['ends']
    return [(ax + bx) / 2.0] if abs(by - ay) > 3.0 * abs(bx - ax) else []


def _beside_column(view, tag, a, b, junction, like, w, h, offset, box, placed, gap, outside):
    """
    A column elevation's link zone called up level beside the column, at its typical link (user 2026-10-17: as the
    main bars' marks), a straight leader to the indicator line next to it. False when no room within 8 rows.
    """
    from nosa_utils import callout_layout
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    off = LEADER_OFF_BAR_PAPER_MM * scale
    up = 1.0 if b[1] >= a[1] else -1.0
    # two rows off the typical link first: the main bars' mark stands level with the middle of the column
    for k in (2, 3, -2, -3, 4, -4, 1, -1, 0, 5, -5, 6, -6, 7, -7, 8, -8):
        land_y = junction[1] + up * off + k * (h + gap)
        if not (min(a[1], b[1]) <= land_y <= max(a[1], b[1])):
            continue
        for sign, edge in ((1.0, box[2]), (-1.0, box[0])):
            cx = edge + sign * (outside + w / 2.0)
            bx = (cx - w / 2.0, land_y - h / 2.0, cx + w / 2.0, land_y + h / 2.0)
            if any(callout_layout.overlap(bx, q, gap) for q in placed):
                continue
            placed.append(bx)
            _move_head(view, tag, (cx, land_y), offset)
            try:
                tag.HasLeader = True
                refs = list(tag.GetTaggedReferences())
                if refs:
                    tag.LeaderEndCondition = DB.LeaderEndCondition.Free
                    tag.SetLeaderEnd(refs[0], _point(view, (junction[0], land_y), like))
                    tag.SetLeaderElbow(refs[0], _point(view, (cx - sign * w / 2.0, land_y), like))
            except Exception:
                pass
            return True
    return False


LEADER_OFF_BAR_PAPER_MM = 2.5      # a column elevation's link leader lands this far off the typical link


UNDERLINE_LIFT_PAPER_MM = 0.6      # a calling-up's text stands this far above the line under it
STACK_GAP_PAPER_MM = 1.0           # between the lines of a stacked calling-up (ALT / STG)


def _draw_path(doc, view, path, like, style):
    """The detail lines from an indicator line (or a bar) to the far end of its calling-up's underline."""
    for p0, p1 in zip(path, path[1:]):
        if abs(p1[0] - p0[0]) + abs(p1[1] - p0[1]) < 1.0:
            continue
        try:
            curve = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_point(view, p0, like), _point(view, p1, like)))
            if style is not None:
                curve.LineStyle = style
        except Exception:
            continue


def _aligned_zones(doc, view, pending, joint):
    """
    The zones of a plan or a wall elevation, kept for one layout with the plan's loose bars (_layout_joint): Arup's
    detailing manual (R. Whittle, 1.5.1) and the SMDSC 4th ed. working drawings. Returns the {id: text box} filled
    when that layout runs.
    """
    for d, mra, a3, b3, junction in pending:
        tag = doc.GetElement(mra.TagId)
        if tag is None:
            continue
        w, h, offset = _size(view, tag, _full_label(doc, view, d, tag.GetTypeId()) or _zone_text(doc, d))
        # an upright indicator line is left a text's height off its typical bar: on the bar, the line read as it
        joint.setdefault('items', []).append((d['id'], {
            'a': _xy(view, a3), 'b': _xy(view, b3), 'length': w, 'height': h, 'side': joint.get('side'),
            'at': _xy(view, junction)[1] + h + joint.get('gap', 0.0)}, tag, offset, junction, True))
    return joint.setdefault('made', {})


def _layout_joint(doc, view, joint, box, gap, outside, placed, report, style, keep_off=(), neighbours=()):
    """
    Every calling-up of a plan or a wall elevation, its zones' and its loose bars', in one layout (user 2026-10-18:
    which bar each text is for must be plain): every text level on a line under it, the line leaving the zone's
    indicator line or the bar and running level out to one column each side of the member; no two lines cross.
    The lines are detail lines; the calling-ups have no leader of their own.
    """
    from nosa_utils import callout_layout
    entries = joint.get('items', [])
    if not entries:
        return
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    inner = STACK_GAP_PAPER_MM * scale
    word_h = TEXT_PAPER_MM * scale
    # two related zones (ALT / STG) called up together, one over the other with the word between, on one line
    by_key = dict((e[0], e) for e in entries if e[5])
    stacks, under = {}, set()
    for a, b, label in joint.get('relations', ()):
        if a in by_key and b in by_key and a not in under and b not in under and a not in stacks and b not in stacks:
            stacks[a] = (b, label)
            under.add(b)
    items = {}
    for e in entries:
        if e[0] in under:
            continue
        it = dict(e[1])
        if e[0] in stacks:
            other = by_key[stacks[e[0]][0]][1]
            it['length'] = max(it['length'], other['length'])
            it['height'] = it['height'] + word_h + other['height'] + 2.0 * inner
        items[e[0]] = it
    out = callout_layout.align_rows(items, box, gap, outside, list(placed) + list(keep_off),
                                    lift=UNDERLINE_LIFT_PAPER_MM * scale,
                                    obstacles=_seen_bars(view), neighbours=neighbours)
    made = joint.setdefault('made', {})
    joint['stacked'] = set()
    drawn = []
    for key, item, tag, offset, like, zone in entries:
        r = out.get(key)
        if r is None:
            continue
        lines = [(key, tag, offset, item)]
        if key in stacks:
            b = by_key[stacks[key][0]]
            centres = callout_layout.stack(r['box'], r['side'], [(item['length'], item['height']),
                                                                 (0.0, word_h), (b[1]['length'], b[1]['height'])],
                                           inner)
            # the word centred under the upper calling-up, as the manual's stacked calling-ups
            word = _note(doc, view, _point(view, (centres[0][0], centres[1][1] + 0.75 * word_h), like),
                         stacks[key][1], joint.get('text_type'), centre=True)
            if word is not None:
                report['notes'] = report.get('notes', 0) + 1
            joint['stacked'].update([key, b[0]])
            lines = [(key, tag, offset, dict(item, centre=centres[0])),
                     (b[0], b[2], b[3], dict(b[1], centre=centres[2]))]
        else:
            lines = [(key, tag, offset, dict(item, centre=r['centre']))]
        for k, t, off, it in lines:
            _move_head(view, t, it['centre'], off)
            try:
                t.HasLeader = False
            except Exception:
                pass
            if zone:
                made[k] = r['box']
                report['aligned'] = report.get('aligned', 0) + 1
            else:
                report['marks'] = report.get('marks', 0) + 1
        drawn.append((r, like, [t for _k, t, _o, _i in lines]))
    # the texts measured as Revit writes them: each set flush with its column's edge, its line as long as the text
    # (2026-10-18 audit: estimated widths left a column's texts up to 2.7 mm out of line)
    doc.Regenerate()
    for r, like, tags_ in drawn:
        sign = 1.0 if r['side'] == 'right' else -1.0
        near = r['box'][0] if r['side'] == 'right' else r['box'][2]
        reach = 0.0
        for t in tags_:
            real = _text_box(view, t)
            if real is None:
                continue
            edge = real[0] if r['side'] == 'right' else real[2]
            shift = near - edge
            if abs(shift) > 1e-3:
                head = _xy(view, t.TagHeadPosition)
                t.TagHeadPosition = _point(view, (head[0] + shift, head[1]), t.TagHeadPosition)
            reach = max(reach, real[2] - real[0])
        path = list(r['path'])
        if reach > 0.0:
            far = path[-1]
            path[-1] = (near + sign * reach, far[1])
            r['box'] = (min(near, path[-1][0]), r['box'][1], max(near, path[-1][0]), r['box'][3])
        _draw_path(doc, view, path, like, style)
        placed.append(r['box'])


def _square_mra(view, tag, a, b, r, length, like):
    """An indicator line's calling-up set beside its line's extension: the leader runs on along the line, then at 90
    degrees to the text (user 2026-10-12: no oblique leaders)."""
    end = b if r['end'] == 'b' else a
    other = a if r['end'] == 'b' else b
    u = (end[0] - other[0], end[1] - other[1])
    n = (u[0] ** 2 + u[1] ** 2) ** 0.5 or 1.0
    u = (u[0] / n, u[1] / n)
    c = r['centre']
    along = (c[0] - end[0]) * u[0] + (c[1] - end[1]) * u[1]
    across = abs(-(c[0] - end[0]) * u[1] + (c[1] - end[1]) * u[0])
    if across < 1.0:
        return False
    t = max(0.0, along - length / 2.0)
    elbow = (end[0] + u[0] * t, end[1] + u[1] * t)
    try:
        refs = list(tag.GetTaggedReferences())
        if refs:
            tag.SetLeaderElbow(refs[0], _point(view, elbow, like))
    except Exception:
        pass
    return True


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


def _supports_x(doc, view, box):
    """View x ranges (mm) of the columns the beam in `box` frames into, from the left."""
    out = []
    try:
        cols = DB.FilteredElementCollector(doc, view.Id).OfCategory(DB.BuiltInCategory.OST_StructuralColumns) \
            .WhereElementIsNotElementType().ToElements()
    except Exception:
        return out
    for col in cols:
        o = _outline(view, [col])
        if o is not None and o[1] < box[3] and o[3] > box[1]:
            out.append((o[0], o[2]))
    return sorted(out)


def _dimension_chain(doc, view, xs, y, like, scale, style, vertical=False):
    """
    A dimension string along the view x through the points xs at height y (mm) — along the view y at x = y when
    vertical: one short witness tick per point (a detail line the dimension refers to) and Revit's own dimension,
    so the figures stay true to the model (SMDSC 4th ed. 3.13: to faces and setting-out points, clear of the detail, read
    from the bottom).
    """
    def at(t, c):
        return _point(view, (c, t) if vertical else (t, c), like)
    xs = sorted(set(round(x, 1) for x in xs))
    if len(xs) < 2:
        return None
    tick = 1.0 * scale
    refs = DB.ReferenceArray()
    for x in xs:
        try:
            curve = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(at(x, y - tick), at(x, y + tick)))
            if style is not None:
                curve.LineStyle = style
            refs.Append(curve.GeometryCurve.Reference)
        except Exception:
            continue
    if refs.Size < 2:
        return None
    try:
        return doc.Create.NewDimension(view, DB.Line.CreateBound(at(xs[0], y), at(xs[-1], y)), refs)
    except Exception:
        return None


def _curtailment(doc, view, items, box, placed, scale, style):
    """
    Dimension strings above a beam elevation for its top bars and below it for its bottom bars: each end stopping
    in a span from the face of the nearest support, each lap with 'LAP' under it. Returns how many.
    """
    supports = _supports_x(doc, view, box)
    mid = (box[1] + box[3]) / 2.0
    bars = []
    for d in items:
        (ax, ay), (bx, by) = d['ends']
        bars.append((min(ax, bx), max(ax, bx), u'top' if (ay + by) / 2.0 > mid else u'bottom'))
    dims = presentation.curtailment_dims(bars, supports)
    if not dims:
        return 0
    gap, row = GAP_PAPER_MM * scale, ROW_PAPER_MM * scale
    like = view.Origin
    rows = {u'top': [], u'bottom': []}
    made = 0
    for kind, a, b, layer in sorted(dims, key=lambda d: (d[3], d[1])):
        k = 0
        while any(r == k and not (b + gap < r0 or a - gap > r1) for r, r0, r1 in rows[layer]):
            k += 1
        rows[layer].append((k, a, b))
        if layer == u'top':
            y = max([box[3]] + [q[3] for q in placed if q[0] < b and q[2] > a]) + gap + row * (0.6 + k)
        else:
            y = min([box[1]] + [q[1] for q in placed if q[0] < b and q[2] > a]) - gap - row * (0.6 + k)
        dim = _dimension_chain(doc, view, [a, b], y, like, scale, style)
        if dim is None:
            continue
        if kind == 'lap':
            try:
                dim.Below = LAP_TEXT
            except Exception:
                pass
        placed.append((a, y - row / 2.0, b, y + row / 2.0))
        made += 1
    return made


def _support_limits(doc, view, box, placed, scale, style):
    """
    T9.17 under a beam elevation: one dimension string through the faces of its supports, SUPPORT under each
    support and the clear spans between their faces (SMDSC 4th ed. MD B1: curtailment is read from the faces).
    Returns 1 when drawn.
    """
    supports = [s for s in _supports_x(doc, view, box) if s[1] > box[0] - 1.0 and s[0] < box[2] + 1.0]
    xs, labels = presentation.support_chain(supports)
    if not xs:
        return 0
    row = ROW_PAPER_MM * scale
    y = min([box[1]] + [q[1] for q in placed if q[0] < xs[-1] and q[2] > xs[0]]) - row
    dim = _dimension_chain(doc, view, xs, y, view.Origin, scale, style)
    if dim is None:
        return 0
    try:
        segments = list(dim.Segments) if dim.NumberOfSegments > 1 else [dim]
        for seg, label in zip(segments, labels):
            if label:
                seg.Below = label
    except Exception:
        pass
    placed.append((xs[0], y - row / 2.0, xs[-1], y + row / 2.0))
    return 1


LAP_TEXT = u'LAP ZONE'
EDGE_TOL_MM = 100.0       # a bar stopping this close to a slab edge or an opening is anchored there, not curtailed


def _openings(view, host):
    """View boxes (mm) of the openings through a slab, base or wall: the inner loops of the face the view sees."""
    out = []
    opts = DB.Options()
    try:
        geometry = host.get_Geometry(opts)
    except Exception:
        return out
    stack = list(geometry) if geometry is not None else []
    faces = []
    while stack:
        g = stack.pop()
        if isinstance(g, DB.GeometryInstance):
            stack.extend(g.GetInstanceGeometry())
        elif isinstance(g, DB.Solid) and g.Volume > 0:
            # the face the view looks at: a slab's top on a plan, a wall's face on its elevation
            faces.extend(f for f in g.Faces if isinstance(f, DB.PlanarFace) and
                         abs(f.FaceNormal.DotProduct(view.ViewDirection)) > 0.99)
    if not faces:
        return out
    top = max(faces, key=lambda f: f.Area)
    loops = []
    for loop in top.EdgeLoops:
        pts = [_xy(view, e.AsCurve().GetEndPoint(0)) for e in loop]
        if pts:
            loops.append((min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts),
                          max(p[1] for p in pts)))
    if len(loops) < 2:
        return out
    outer = max(loops, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    return [b for b in loops if b is not outer]


OPENING_RULE_LAYERS = (u'trimmer', u'diagonal', u'opening_ubar')


def _plan_dims(doc, view, hosts, zones, box, placed, scale, style, report):
    """
    T9.2 on a slab or base plan (SMDSC 4th ed. 3.13, 4th ed. Fig. 6.24): each opening set out from the edges, a string
    under the plan and one beside it; each bar of a zone stopping short of an edge or an opening dimensioned from
    that face, along its typical bar. Returns how many dimensions.
    """
    from nosa_utils import callout_layout
    gap, row = GAP_PAPER_MM * scale, ROW_PAPER_MM * scale
    like = view.Origin
    holes = [o for h in hosts for o in _openings(view, h)]
    made = 0
    lines = None
    if holes:
        y = min([box[1]] + [q[1] for q in placed if q[0] < box[2] and q[2] > box[0]]) - row
        if _dimension_chain(doc, view, [box[0], box[2]] + [x for o in holes for x in (o[0], o[2])], y, like, scale,
                            style) is not None:
            placed.append((box[0], y - row / 2.0, box[2], y + row / 2.0))
            made += 1
        x = max([box[2]] + [q[2] for q in placed if q[1] < box[3] and q[3] > box[1]]) + row
        if _dimension_chain(doc, view, [box[1], box[3]] + [v for o in holes for v in (o[1], o[3])], x, like, scale,
                            style, vertical=True) is not None:
            placed.append((x - row / 2.0, box[1], x + row / 2.0, box[3]))
            made += 1
    for d in zones:
        if (d.get('layer') or u'').lower().startswith(OPENING_RULE_LAYERS):
            continue                      # trimmers and diagonals: their reach is MD OP1's, not a dimension each
        rebar = d['rebar']
        line, free = _free_ends(_centreline(rebar, _shown_bar(view, rebar, d['count'])))
        if line is None or not free:
            continue                      # a U-bar's or a link's legs end at bends, not in the span
        a, b = _xy(view, line.GetEndPoint(0)), _xy(view, line.GetEndPoint(1))
        vertical = abs(b[1] - a[1]) > abs(b[0] - a[0])
        k, c = (1, a[0]) if vertical else (0, a[1])
        lo, hi = (box[1], box[3]) if vertical else (box[0], box[2])
        near = [(o[k], o[k + 2]) for o in holes if o[1 - k] - 1000.0 < c < o[3 - k] + 1000.0]
        supports = [(lo - 1e6, lo), (hi, hi + 1e6)] + near
        ends = [(_xy(view, f)[k],) * 2 + (u'',) for f in free]
        for kind, t0, t1, _layer in presentation.curtailment_dims(ends, supports, tol=EDGE_TOL_MM):
            if kind != 'cut':
                continue
            if lines is None:
                lines = _seen_bars(view) + _drawn_lines(doc, view)
            # beside its bar, clear of the zones' lines, the calling-ups' and the texts (S2, Revit 2026: on them)
            steps = [1.5, -1.5, 3.0, -3.0, 4.5, -4.5, 6.0, -6.0]
            at = callout_layout.clear_offset(min(t0, t1), max(t0, t1), c, vertical, [k * gap for k in steps],
                                             placed, [s for s in lines if not _on_line(s, c, vertical)],
                                             0.8 * TEXT_PAPER_MM * scale)
            if _dimension_chain(doc, view, [t0, t1], at, like, scale, style, vertical=vertical) is not None:
                made += 1
                half = 0.8 * TEXT_PAPER_MM * scale
                placed.append((at - half, min(t0, t1), at + half, max(t0, t1)) if vertical else
                              (min(t0, t1), at - half, max(t0, t1), at + half))
    report['dims'] = report.get('dims', 0) + made
    return made


ARC_NOTE = u'BEAM ON R {:.0f} TO ITS CENTRELINE - CENTRE OFF THE PLAN'
RADIUS_AT = 0.64     # where along a curved beam its radius is drawn: off its sections (0.5, 0.12) and stations


def _arc_setting_out(doc, view, hosts, box, scale, style, text_type):
    """
    T9.17 on a curved beam's plan (SMDSC 4th ed. 3.13: set out from a centre): its radius written along a line from its
    axis towards the centre, the centre crossed and labelled when it falls on the plan, and stations across the
    beam with their chainage from its start, inside the curve. Returns how many texts.
    """
    import beam_rebar
    from nosa_utils import presentation
    made = 0
    tick, text_h = 3.0 * scale, TEXT_PAPER_MM * scale

    def line(a, b, like):
        try:
            c = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_point(view, a, like), _point(view, b, like)))
            if style is not None:
                c.LineStyle = style
        except Exception:
            pass

    def note(xy, text, like, angle=0.0):
        try:
            opts = DB.TextNoteOptions(text_type)
            opts.HorizontalAlignment = DB.HorizontalTextAlignment.Center
            opts.Rotation = angle
            return DB.TextNote.Create(doc, view.Id, _point(view, xy, like), text, opts) is not None
        except Exception:
            return False

    for host in hosts:
        try:
            arc = beam_rebar.get_beam_arc(host)
        except Exception:
            arc = None
        if arc is None:
            continue
        like = arc.Evaluate(RADIUS_AT, True)      # clear of the sections at mid span and near the start
        centre = _xy(view, arc.Center)
        radius = arc.Radius * _MM_PER_FT
        mid = _xy(view, like)
        to_c = (centre[0] - mid[0], centre[1] - mid[1])
        n = (to_c[0] ** 2 + to_c[1] ** 2) ** 0.5 or 1.0
        u = (to_c[0] / n, to_c[1] / n)
        on_plan = box[0] <= centre[0] <= box[2] and box[1] <= centre[1] <= box[3]
        if on_plan:
            line(mid, centre, like)
            line((centre[0] - tick, centre[1]), (centre[0] + tick, centre[1]), like)
            line((centre[0], centre[1] - tick), (centre[0], centre[1] + tick), like)
            made += note((centre[0], centre[1] - tick - text_h), u'CENTRE', like)
            made += note(((mid[0] + centre[0]) / 2.0, (mid[1] + centre[1]) / 2.0 + text_h),
                         u'R {:.0f}'.format(radius), like)
        else:
            # the inside of the curve is full of stations and section marks: a note under the plan
            made += note(((box[0] + box[2]) / 2.0, box[1] - 4.0 * ROW_PAPER_MM * scale),
                         ARC_NOTE.format(radius), like)
        length = arc.Length * _MM_PER_FT
        for ch in presentation.arc_stations(length):
            p = arc.Evaluate(ch / length, True)
            q = _xy(view, p)
            out = (q[0] - centre[0], q[1] - centre[1])
            m = (out[0] ** 2 + out[1] ** 2) ** 0.5 or 1.0
            o = (out[0] / m, out[1] / m)
            half_w = 300.0
            try:
                half_w = host.Symbol.LookupParameter(u'b').AsDouble() * _MM_PER_FT / 2.0
            except Exception:
                pass
            a = (q[0] - o[0] * (half_w + tick), q[1] - o[1] * (half_w + tick))
            b = (q[0] + o[0] * (half_w + tick), q[1] + o[1] * (half_w + tick))
            line(a, b, like)
            t_angle = math.atan2(o[1], o[0])
            if t_angle > math.pi / 2.0 or t_angle < -math.pi / 2.0:
                t_angle += math.pi
            at = (a[0] - o[0] * 3.0 * text_h, a[1] - o[1] * 3.0 * text_h)     # inside: the calling-up is outside
            made += note(at, presentation.chainage_text(ch), like, t_angle)
    return made


STRIP_MIN_COLUMNS = 2     # a flat slab: the slab stands on this many columns and on no wall or beam


def _strips(doc, view, hosts, box, placed, scale, style, text_type):
    """
    T9.16 on a flat slab plan (SMDSC 4th ed. 6.2.2.9 / Fig. 6.4 / MD S5): the column and middle strips of each
    direction, their limits as thin lines across the slab and each band labelled COLUMN STRIP / MIDDLE STRIP
    outside it (under the plan for the bands across X, left of it, turned, for those across Y). Returns how many
    labels.
    """
    import floor_rebar
    from nosa_utils import mesh_rules
    made = 0
    for host in hosts:
        if not isinstance(host, DB.Floor):
            continue
        bb = host.get_BoundingBox(None)
        if bb is None:
            continue
        bounds = (bb.Min.X * _MM_PER_FT, bb.Max.X * _MM_PER_FT, bb.Min.Y * _MM_PER_FT, bb.Max.Y * _MM_PER_FT)
        sup_x, sup_y = floor_rebar._slab_supports_mm(doc, DB, bounds, bb.Min.Z)
        cols = floor_rebar._slab_columns_mm(doc, DB, bounds, bb.Min.Z)
        if sup_x or sup_y or len(cols) < STRIP_MIN_COLUMNS:
            continue
        at = [_xy(view, DB.XYZ(c[0] / _MM_PER_FT, c[1] / _MM_PER_FT, bb.Min.Z)) for c in cols]
        xs = floor_rebar._merge_lines([p[0] for p in at])
        ys = floor_rebar._merge_lines([p[1] for p in at])
        spans = [b - a for line in (xs, ys) for a, b in zip(line, line[1:])]
        short = min(spans) if spans else min(box[2] - box[0], box[3] - box[1])
        like = bb.Min
        gap, row = GAP_PAPER_MM * scale, ROW_PAPER_MM * scale
        text_h = TEXT_PAPER_MM * scale
        y = min([box[1]] + [q[1] for q in placed if q[0] < box[2] and q[2] > box[0]]) - row
        x = min([box[0]] + [q[0] for q in placed if q[1] < box[3] and q[3] > box[1]]) - row
        for across_x, lines, lo, hi in ((True, xs, box[0], box[2]), (False, ys, box[1], box[3])):
            bands = mesh_rules.strip_bands_mm(lo, hi, lines, short)
            if len(bands) < 2:
                continue
            for a, b, label in bands:
                if a > lo + 1.0:
                    p, q = ((a, box[1]), (a, box[3])) if across_x else ((box[0], a), (box[2], a))
                    try:
                        curve = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_point(view, p, like),
                                                                                    _point(view, q, like)))
                        if style is not None:
                            curve.LineStyle = style
                    except Exception:
                        pass
                width = len(label) * text_h * 0.8
                if b - a < width + gap:
                    continue                      # too narrow to be labelled at this scale
                try:
                    opts = DB.TextNoteOptions(text_type)
                    opts.HorizontalAlignment = DB.HorizontalTextAlignment.Center
                    if across_x:
                        point = _point(view, ((a + b) / 2.0, y), like)
                    else:
                        opts.Rotation = math.pi / 2.0
                        point = _point(view, (x, (a + b) / 2.0), like)
                    if DB.TextNote.Create(doc, view.Id, point, label, opts) is not None:
                        made += 1
                except Exception:
                    continue
            if across_x:
                placed.append((box[0], y - text_h, box[2], y + gap))
            else:
                placed.append((x - text_h, box[1], x + gap, box[3]))
    return made


BAR_PEN = 3     # every bar in every RC view: one weight, cut or seen (measured 2026-10-18 in Revit 2026: left to
                # the category, bars of one size drew in two weights; pen 3 prints alike at 1:25 and 1:50)


def bar_weights(view, rebars):
    """Every bar drawn at BAR_PEN, seen or cut, keeping any line pattern already given (SEE DRG dashes)."""
    n = 0
    for r in rebars:
        try:
            ogs = view.GetElementOverrides(r.Id)
            ogs.SetProjectionLineWeight(BAR_PEN)
            ogs.SetCutLineWeight(BAR_PEN)
            view.SetElementOverrides(r.Id, ogs)
            n += 1
        except Exception:
            continue
    return n


def _is_column(host):
    return host is not None and host.Category is not None and \
        get_id_value(host.Category.Id) == int(DB.BuiltInCategory.OST_StructuralColumns)


def _right_of(box, placed, row):
    return max([box[2]] + [q[2] for q in placed if q[1] < box[3] and q[3] > box[1]]) + row


def _confinement(doc, view, zones, box, placed, scale, style):
    """
    T9.18 on a column elevation: each link zone closer than the general pitch (ends of the lift, laps; EC2
    9.5.3(4), SMDSC 4th ed. MD C1) dimensioned beside the column, CONFINEMENT ZONE under it. Returns how many.
    """
    from nosa_utils import presentation
    links = []
    for d in zones:
        if d.get('spread_dir') is None or abs(d['spread_dir'][1]) < 0.9:
            continue                                  # links stepping up the column
        lo, hi = sorted((d['first'][1], d['last'][1]))
        links.append((lo, hi, d.get('spacing') or 0.0))
    row = ROW_PAPER_MM * scale
    x = _right_of(box, placed, row)
    made = 0
    for lo, hi in presentation.confinement_zones(links):
        dim = _dimension_chain(doc, view, [lo, hi], x, view.Origin, scale, style, vertical=True)
        if dim is None:
            continue
        # read level beside the string: along it the words outran a zone of 720 at 1:50 (2026-10-17)
        _side_note(doc, view, x, (lo + hi) / 2.0, presentation.CONFINEMENT_TEXT, scale)
        placed.append((x - row / 2.0, lo, x + row / 2.0, hi))
        made += 1
    return made


def _side_note(doc, view, x, y, text, scale):
    """A level note just right of a vertical dimension string at x, centred on y (view mm)."""
    try:
        type_id = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
        opts = DB.TextNoteOptions(type_id)
        opts.HorizontalAlignment = DB.HorizontalTextAlignment.Left
        at = _point(view, (x + 2.0 * GAP_PAPER_MM * scale, y + TEXT_PAPER_MM * scale / 2.0), view.Origin)
        return DB.TextNote.Create(doc, view.Id, at, text, opts)
    except Exception:
        return None


def _kicker(doc, view, hosts, box, placed, scale, style):
    """
    T9.18 on the elevation of a column standing on a base: its kicker dimensioned at its foot, KICKER under it -
    75 mm, 150 mm below ground (SMDSC 4th ed. 6.7.3, MD C1). Returns 1 when drawn.
    """
    from nosa_utils import presentation, wall_rules
    cols = [h for h in hosts if _is_column(h)]
    if not cols:
        return 0
    bb = cols[0].get_BoundingBox(None)
    if bb is None:
        return 0
    base = bb.Min.Z
    on_base = False
    for f in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StructuralFoundation) \
            .WhereElementIsNotElementType():
        fb = f.get_BoundingBox(None)
        if fb is not None and abs(fb.Max.Z - base) < 0.2 and fb.Min.X < bb.Max.X and fb.Max.X > bb.Min.X \
                and fb.Min.Y < bb.Max.Y and fb.Max.Y > bb.Min.Y:
            on_base = True
            break
    if not on_base:
        return 0
    ground = 0.0
    for level in DB.FilteredElementCollector(doc).OfClass(DB.Level):
        if level.Name.lower().startswith(u'ground'):
            ground = level.Elevation
            break
    kicker = wall_rules.KICKER_BELOW_GROUND_MM if base < ground - 50.0 / _MM_PER_FT else wall_rules.KICKER_MM
    foot = _xy(view, DB.XYZ(0.0, 0.0, base))[1] if abs(view.UpDirection.Z) > 0.99 else None
    if foot is None:
        return 0
    row = ROW_PAPER_MM * scale
    x = _right_of(box, placed, row)
    dim = _dimension_chain(doc, view, [foot, foot + kicker], x, view.Origin, scale, style, vertical=True)
    if dim is None:
        return 0
    _side_note(doc, view, x, foot + kicker / 2.0, presentation.KICKER_TEXT, scale)
    placed.append((x - row / 2.0, foot, x + row / 2.0, foot + kicker))
    return 1


def _piles_under(doc, cap):
    """Piles under a pile cap: foundations centred in its plan whose tops sit inside it. [(x, y, dia, top z)] mm."""
    bb = cap.get_BoundingBox(None)
    if bb is None:
        return []
    out = []
    for f in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StructuralFoundation) \
            .WhereElementIsNotElementType():
        if get_id_value(f.Id) == get_id_value(cap.Id):
            continue
        fb = f.get_BoundingBox(None)
        if fb is None:
            continue
        cx, cy = (fb.Min.X + fb.Max.X) / 2.0, (fb.Min.Y + fb.Max.Y) / 2.0
        if bb.Min.X < cx < bb.Max.X and bb.Min.Y < cy < bb.Max.Y and fb.Max.Z < bb.Max.Z - 0.01 and \
                fb.Max.Z > bb.Max.Z - 3000.0 / _MM_PER_FT:
            out.append((cx * _MM_PER_FT, cy * _MM_PER_FT, (fb.Max.X - fb.Min.X) * _MM_PER_FT, fb.Max.Z * _MM_PER_FT))
    return out


def _pile_table(doc, view, hosts, box, placed, scale, text_type):
    """
    T9.20 on a pile cap plan: each pile labelled P1.. at its centre, the numbers of the piling drawing, which sets
    them out (user 2026-10-17: no table of positions here). Returns how many piles.
    """
    from nosa_utils import presentation
    made = 0
    text_h = TEXT_PAPER_MM * scale
    for cap in hosts:
        if cap is None or cap.Category is None or \
                get_id_value(cap.Category.Id) != int(DB.BuiltInCategory.OST_StructuralFoundation):
            continue
        piles = _piles_under(doc, cap)
        if not piles:
            continue
        bb = cap.get_BoundingBox(None)
        origin = ((bb.Min.X + bb.Max.X) / 2.0 * _MM_PER_FT, (bb.Min.Y + bb.Max.Y) / 2.0 * _MM_PER_FT)
        rows = presentation.pile_table(piles, origin)
        like = bb.Max
        for label, (x, y), _cells in rows:
            at = _xy(view, DB.XYZ(x / _MM_PER_FT, y / _MM_PER_FT, bb.Max.Z))
            _note(doc, view, _point(view, (at[0] + text_h, at[1] + 2.0 * text_h), like), label,
                  doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType) if text_type is None else text_type)
        made += len(rows)
    return made


def _starter_dims(doc, view, rebars, box, placed, scale, style):
    """
    T9.20 on a base section: the starter bars (dowels) dimensioned beside it - the cover under their feet, their
    embedment and their projection above the base (SMDSC 4th ed. MD F1 / 6.7.3). Returns 1 when drawn.
    """
    from nosa_utils import presentation
    tops, feet, mat = [], [], []
    for r in rebars:
        layer = _text(r, u'NOSA_Rebar_Layer').strip().lower()
        if layer.startswith(u'bottom'):
            # the underside of the bottom mat: the real cover is to it, not to the starters' feet on it
            try:
                radius = doc.GetElement(r.GetTypeId()).BarModelDiameter * _MM_PER_FT / 2.0
                for i in sorted(set((0, r.NumberOfBarPositions - 1))):
                    for c in _centreline(r, i) or []:
                        mat.extend(_xy(view, c.GetEndPoint(k))[1] - radius for k in (0, 1))
            except Exception:
                pass
            continue
        if layer != u'dowel':
            continue
        try:
            n = r.NumberOfBarPositions
            for i in sorted(set((0, n - 1))):
                for c in _centreline(r, i) or []:
                    for k in (0, 1):
                        y = _xy(view, c.GetEndPoint(k))[1]
                        tops.append(y)
                        feet.append(y)
        except Exception:
            continue
    if not tops:
        return 0
    xs, labels = presentation.starter_chain(box[1], min(feet), box[3], max(tops), min(mat) if mat else None)
    if not xs:
        return 0
    row = ROW_PAPER_MM * scale
    x = max([box[2]] + [q[2] for q in placed if q[1] < xs[-1] and q[3] > xs[0]]) + row
    dim = _dimension_chain(doc, view, xs, x, view.Origin, scale, style, vertical=True)
    if dim is None:
        return 0
    try:
        for seg, label in zip(list(dim.Segments), labels):
            if label:
                seg.Below = label
    except Exception:
        pass
    placed.append((x - row / 2.0, xs[0], x + row / 2.0, xs[-1]))
    return 1


def _column_ratio(doc, view, hosts, rebars, box, placed, scale, text_type):
    """T9.18 under a column's section: its steel ratio and vertical bars (EC2 9.5.2). Returns 1 when written."""
    from nosa_utils import presentation
    cols = [h for h in hosts if _is_column(h)]
    if not cols:
        return 0
    host = cols[0]
    bb = host.get_BoundingBox(None)
    try:
        solids = [g for g in host.get_Geometry(DB.Options()) if isinstance(g, DB.Solid) and g.Volume > 0]
        if not solids:
            inst = [g for g in host.get_Geometry(DB.Options()) if isinstance(g, DB.GeometryInstance)]
            solids = [g for i in inst for g in i.GetInstanceGeometry() if isinstance(g, DB.Solid) and g.Volume > 0]
        height = bb.Max.Z - bb.Min.Z
        area = sum(s.Volume for s in solids) / height * _MM_PER_FT ** 2 if height > 0 else 0.0
    except Exception:
        area = 0.0
    bars = []
    hid = get_id_value(host.Id)
    for r in rebars:
        try:
            if get_id_value(r.GetHostId()) != hid:
                continue
            line = _main_line(r, 0)
            if line is None or abs(line.Direction.Z) < 0.9:
                continue
            bars.append((r.NumberOfBarPositions, doc.GetElement(r.GetTypeId()).BarModelDiameter * _MM_PER_FT))
        except Exception:
            continue
    bars = [(n, round(d)) for n, d in bars]
    text = presentation.steel_ratio_text(bars, area)
    if not text:
        return 0
    row = ROW_PAPER_MM * scale
    y = min([box[1]] + [q[1] for q in placed if q[0] < box[2] and q[2] > box[0]]) - 2.0 * row
    try:
        opts = DB.TextNoteOptions(text_type)
        opts.HorizontalAlignment = DB.HorizontalTextAlignment.Center
        DB.TextNote.Create(doc, view.Id, _point(view, ((box[0] + box[2]) / 2.0, y), view.Origin), text, opts)
    except Exception:
        return 0
    placed.append((box[0], y - row, box[2], y))
    return 1


def _column_laps(doc, view, items, box, placed, scale, style):
    """
    T9.3 on a column elevation: the bars running on past the column's ends (starters, laps into the next lift)
    dimensioned from its face, and bars of one layer overlapping, each reading LAP ZONE; beside the column.
    """
    row = ROW_PAPER_MM * scale
    like = view.Origin
    bars = []
    for d in items:
        (ax, ay), (bx, by) = d['ends']
        if abs(by - ay) > abs(bx - ax):
            bars.append((min(ay, by), max(ay, by), _text(d['rebar'], u'NOSA_Rebar_Layer')))
    made = 0
    x = max([box[2]] + [q[2] for q in placed if q[1] < box[3] and q[3] > box[1]]) + row
    for _kind, t0, t1, _layer in presentation.curtailment_dims(bars, [(box[1], box[3])], tol=EDGE_TOL_MM):
        dim = _dimension_chain(doc, view, [t0, t1], x, like, scale, style, vertical=True)
        if dim is None:
            continue
        try:
            dim.Below = LAP_TEXT
        except Exception:
            pass
        placed.append((x - row / 2.0, t0, x + row / 2.0, t1))
        made += 1
    return made


def _beam_links(doc, view, zones, mra_type, det, box, gap, outside, row, placed, report, style):
    """
    Link zones under a beam elevation (SMDSC 4th ed. 6.2.3, fig. 'Beam on grid 1/A-B'): every zone of a mark on one
    line, its indicator line labelled '(n@pitch)' ('Zone quantity' tag, NOSA_Rebar_Zone_Qty), and under them one
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
        groups.setdefault((d['mark'], get_id_value(d['rebar'].GetTypeId()), _text(d['rebar'], u'NOSA_Rebar_Layer')),
                          []).append(d)
    spans = []
    for key, group in groups.items():
        # a mark's zones next to each other share one total line; the same mark again further along (an
        # identical beam beyond another span) gets its own (user 2026-10-10)
        run, runs = [], []
        for d in sorted(group, key=lambda z: min(z['first'][0], z['last'][0])):
            reach = max(max(z['first'][0], z['last'][0]) for z in run) if run else None
            if run and min(d['first'][0], d['last'][0]) - reach > LINK_RUN_GAP_MM:
                runs.append(run)
                run = []
            run.append(d)
        runs.append(run)
        for run in runs:
            xs = [x for d in run for x in (d['first'][0], d['last'][0])]
            spans.append([min(xs), max(xs), key, run])
    rows_used = []
    made = {}
    supports = _supports_x(doc, view, box)
    for x0, x1, key, group in sorted(spans, key=lambda s: (s[0], s[1])):
        k = 0
        while any(r == k and not (x1 + gap < r0 or x0 - gap > r1) for r, r0, r1 in rows_used):
            k += 1
        rows_used.append((k, x0, x1))
        y_zone = top - gap - text_h - k * 3 * row
        y_total = y_zone - row
        y_dims = y_total - row
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
        main = max(pending, key=lambda e: (e[0]['count'], -e[0]['id']))[0]
        note = _text(main['rebar'], NOTE_PARAM) or (u'LINKS' if _text(main['rebar'], u'NOSA_Rebar_Layer')
                                                       .startswith(u'stirrup') else u'')
        callout = presentation.total_callout(_strip_note(_full_label(doc, view, main, short_type), note),
                                             sum(e[0]['count'] for e in pending), note)
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
            if tag is None:
                continue
            size = _size(view, tag, _text(d['rebar'], ZONE_QTY_PARAM))
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
        like = _main_line(main['rebar'], 0).Evaluate(0.5, True)
        _total_line(doc, view, lo, hi, y_total, like, scale, style)
        placed.append((lo, y_total - gap, hi, y_total + gap))
        # SMDSC 4th ed. Fig. 6.24 / 3.13: every zone dimensioned from the faces of the supports, SUPPORT under each -
        # one string for both (user 2026-10-17: the beam drawing in less room)
        faces = supports if supports is not None else []
        points, labels = presentation.links_chain([(e[2], e[3]) for e in pending], faces)
        dim = _dimension_chain(doc, view, points, y_dims, like, scale, style)
        if dim is not None:
            report['dims'] = report.get('dims', 0) + 1
            placed.append((min(points), y_dims - row / 2.0, max(points), y_dims + row / 2.0))
            try:
                segments = list(dim.Segments) if dim.NumberOfSegments > 1 else [dim]
                for seg, label in zip(segments, labels):
                    if label:
                        seg.Below = label
            except Exception:
                pass
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
        return (tag.TagText or u'').strip().rstrip(u'-').strip()   # an empty spacing leaves its '-' in TagText
    finally:
        doc.Delete(tag.Id)


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
    cut = _cut_depth(view)
    depths = []
    for i in range(n):
        line = _main_line(rebar, i)
        if line is not None:
            depths.append((line.Evaluate(0.5, True).DotProduct(view.ViewDirection), i))
    behind = [(d, i) for d, i in depths if d <= cut + 1.0 / _MM_PER_FT]
    if behind:
        return max(behind)[1]
    return min(depths, key=lambda di: abs(di[0] - cut))[1] if depths else n // 2


def _arc_of(rebar, index):
    """The bar's arc when it is a bar of arcs only (a curved beam's), else None."""
    curves = _centreline(rebar, index or 0)
    lines = [c for c in curves if isinstance(c, DB.Line)]
    arcs = [c for c in curves if isinstance(c, DB.Arc)]
    if not arcs:
        return None
    arc = max(arcs, key=lambda c: c.Length)
    return arc if not lines or max(c.Length for c in lines) < arc.Length else None


def _anchor(view, d, fraction=0.5, index=None):
    """Point on the bar the mark points at: along the shown bar at `fraction` (a dot when the bars are cut)."""
    rebar = d['rebar']
    i = d['count'] // 2 if index is None else index
    arc = _arc_of(rebar, i)
    if arc is not None:
        return arc.Evaluate(fraction, True)        # along a curved bar, not its short tangent
    line = _main_line(rebar, i) or _main_line(rebar, 0)
    return line.Evaluate(fraction, True) if line is not None else None


def _segment(view, d, index):
    """(a, b) view mm of the straight leg a mark's pointer lands on, or None."""
    line = _main_line(d['rebar'], d['count'] // 2 if index is None else index, view)
    if line is None or _arc_of(d['rebar'], index) is not None:
        return None
    return _xy(view, line.GetEndPoint(0)), _xy(view, line.GetEndPoint(1))


def _square_leader(view, tag, centre, side, segment, anchor):
    """
    A pointer at 90 degrees (user 2026-10-12): straight across the row to the bar where the bar crosses that line
    (the anchor slid along it), else a right-angled elbow. side: the row's side of the member. Returns the leader
    axis ('v' / 'h') the text's attach point is then lined up on.
    """
    vertical = side in ('top', 'bottom')
    refs = list(tag.GetTaggedReferences())
    if not refs:
        return None
    if segment is not None:
        (ax, ay), (bx, by) = segment
        t = None
        if vertical and abs(bx - ax) > 1.0:
            t = (centre[0] - ax) / (bx - ax)
        elif not vertical and abs(by - ay) > 1.0:
            t = (centre[1] - ay) / (by - ay)
        if t is not None and 0.03 <= t <= 0.97:
            p = (ax + t * (bx - ax), ay + t * (by - ay))
            tag.SetLeaderEnd(refs[0], _point(view, p, anchor))
            return ('v' if vertical else 'h'), p
    a = _xy(view, anchor)
    if abs((a[0] - centre[0]) if vertical else (a[1] - centre[1])) < 1.0:
        return ('v' if vertical else 'h'), a
    try:
        elbow = (centre[0], a[1]) if vertical else (a[0], centre[1])
        tag.SetLeaderElbow(refs[0], _point(view, elbow, anchor))
        return ('v' if vertical else 'h'), elbow
    except Exception:
        return None


LEADER_ATTACH_PAPER_MM = 0.48     # a NOSA tag's leader leaves its text this far above the tag head (measured)


def _line_up(doc, view, pending):
    """
    Revit hangs a tag's leader on the middle of its text, LEADER_ATTACH_PAPER_MM off its head (the arrows at bar ends
    leaned, more at 1:25 than at 1:50, user 2026-10-12): each tag moved so that point lies on its leader's straight
    run. pending: [(tag, axis 'v' | 'h', point on the run)].
    """
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    off = LEADER_ATTACH_PAPER_MM * scale
    for tag, axis, at in pending:
        try:
            head = _xy(view, tag.TagHeadPosition)
            turned = tag.TagOrientation == DB.TagOrientation.Vertical
            if axis == 'h' and not turned:
                head = (head[0], at[1] - off)
            elif axis == 'v' and turned:
                head = (at[0] + off, head[1])
            else:
                continue
            tag.TagHeadPosition = _point(view, head, tag.TagHeadPosition)
        except Exception:
            continue


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
    try:
        free_form = not rebar.IsRebarShapeDriven()
    except Exception:
        free_form = False
    if free_form:
        # a FreeForm group (curved beam bars, T8.58): a tag on one bar reads 1, on the element its Quantity
        try:
            line = _main_line(rebar, index or 0, view)
            tag = DB.IndependentTag.Create(doc, type_id, view.Id, DB.Reference(rebar), False,
                                           DB.TagOrientation.Horizontal,
                                           line.Evaluate(0.5, True) if line is not None else view.Origin)
            doc.Regenerate()
            if _visible(doc, view, tag):
                return tag, index
            doc.Delete(tag.Id)
        except Exception:
            pass
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


def merge_singles(doc, items, clusters=None):
    """
    Loose single bars of one mark in a view: one calling-up per group of them on the member (clusters, from
    _single_groups: the eight bars of a round column read '8H20-01' though an elevation shows five, user
    2026-10-12), on the group's middle bar shown ('total'); the other bars of the group get no mark of their own.
    """
    clusters = clusters or {}
    groups, out = {}, []
    for d in items:
        try:
            free_form = d['count'] > 1 and not d['rebar'].IsRebarShapeDriven()
        except Exception:
            free_form = False
        if free_form:
            # a FreeForm group's tag reads 1 bar: its calling-up written out with the count
            out.append(dict(d, total=d['count']))
        elif d['count'] == 1 and d.get('mark') and d['id'] in clusters:
            groups.setdefault(clusters[d['id']][0], []).append(d)
        else:
            out.append(d)
    for gid, members in groups.items():
        size = clusters[members[0]['id']][1]
        members.sort(key=lambda d: (round(d['first'][0], 3), round(d['first'][1], 3)))
        lead = members[len(members) // 2]
        out.append(dict(lead, total=size) if size > 1 else lead)
    return out


def _single_type(doc, d, tag_types, fallback):
    """The tag type of a merged loose bar: its calling-up with the total, or its mark alone."""
    if d.get('total'):
        try:
            dia = doc.GetElement(d['rebar'].GetTypeId()).BarNominalDiameter * _MM_PER_FT
        except Exception:
            dia = 0.0
        text = presentation.total_callout(u'1H{:.0f}-{}{}'.format(dia, d['mark'],
                                                                 _text(d['rebar'], u'NOSA_Rebar_Mark_Suffix')),
                                          d['total'], _text(d['rebar'], NOTE_PARAM))
        _set(d['rebar'], CALLOUT_PARAM, text)
        return tag_types.get(CALLOUT_TAG) or fallback
    if _no_real_pitch(d['rebar']):
        if fallback == tag_types.get(ZONE_TAG):
            return tag_types.get(SHORT_TAG) or fallback
        if fallback == tag_types.get(ELEVATION_TAG):
            return tag_types.get(SPACER_TAG) or fallback        # 'No centres - Arrow'
    return fallback


def _no_real_pitch(rebar):
    """
    A set laid out by a nominal maximum spacing longer than its own spread (a pile cap's two layers of lacers:
    10000 over 776 mm): its centres mean nothing, so it is called up without them (2H12-03 LINKS).
    """
    try:
        accessor = rebar.GetShapeDrivenAccessor()
        return rebar.NumberOfBarPositions > 1 and rebar.MaxSpacing > accessor.ArrayLength + 1e-6
    except Exception:
        return False


def _pointers(doc, view, items, det, tag_types, box, gap, outside, placed, report, clusters=None, joint=None):
    """Marks of the bars that are not zones, in rows outside the member, each with a pointer to its bar."""
    from nosa_utils import callout_layout
    if not items:
        return
    items = merge_singles(doc, items, clusters)
    kind = ZONE_TAG if (_is_plan(view) or joint is not None) else POINTER_TAG
    type_id = tag_types.get(kind) or det.tag_type_for_view(doc, view)
    fractions = _pointer_fractions(items)
    tags, indices = [], {}
    for d in items:
        index = _shown_bar(view, d['rebar'], d['count'])
        try:
            tag, index = _tag_bar(doc, view, d['rebar'], index, _single_type(
                doc, d, tag_types, det._tag_type_for_bar(doc, d['rebar'], type_id)))
        except Exception:
            continue
        anchor = _clear_anchor(view, d, fractions.get(d['id'], 0.5), index, box, placed, gap)
        if tag is None or anchor is None:
            continue
        tags.append((d, tag, anchor))
        indices[d['id']] = index
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
    straight = [(d, tag, anchor) for d, tag, anchor in tags
                if d['id'] in sizes and d.get('ends') and _arc_of(d['rebar'], indices.get(d['id'])) is None]
    if straight and joint is not None:
        # a plan's or a wall elevation's loose bars called up as its zones are, in the same columns (Arup manual
        # 1.5.1); a bar on the skew (an opening's diagonals) by a level line leaving the bar where it is marked
        for d, tag, anchor in straight:
            a, b = d['ends']
            if _skew(a, b):
                a = b = _xy(view, anchor)
            joint.setdefault('items', []).append((('bar', d['id']), {
                'a': a, 'b': b, 'length': sizes[d['id']][0], 'height': sizes[d['id']][1], 'side': joint.get('side'),
                'at': _xy(view, anchor)[1]}, tag, sizes[d['id']][2], anchor, False))
        done = set(d['id'] for d, _t, _a in straight)
        tags = [t for t in tags if t[0]['id'] not in done]
        layout = [it for it in layout if it['id'] not in done]
        if not tags:
            return
    if placed:
        box = (min([box[0]] + [b[0] for b in placed]), min([box[1]] + [b[1] for b in placed]),
               max([box[2]] + [b[2] for b in placed]), max([box[3]] + [b[3] for b in placed]))
    arcs = dict((d['id'], _arc_of(d['rebar'], indices.get(d['id']))) for d, _t, _a in tags)
    curved = [a for a in arcs.values() if a is not None]
    if curved:
        # a curved member's plan: every mark radially just outside it, its links' too
        arcs = dict((k, a or curved[0]) for k, a in arcs.items())
    places = callout_layout.place_pointers([it for it in layout if arcs.get(it['id']) is None], box, gap, outside)
    along = 0.0
    for i, (d, tag, anchor) in enumerate(tags):
        arc = arcs.get(d['id'])
        if arc is not None and d['id'] in sizes:
            # a curved beam's bar: its mark just outside the arc, square to it (user 2026-10-12: they stood far off);
            # the next ones slid along the arc a mark's width each, side by side, not stacked over one point where
            # one's pointer crossed the other's text (B12, 2026-10-17)
            w, h, _o = sizes[d['id']]
            if along:
                try:
                    hit = arc.Project(anchor)
                    if hit is not None:
                        raw = hit.Parameter - along / (arc.Radius * _MM_PER_FT)
                        lo, hi = arc.GetEndParameter(0), arc.GetEndParameter(1)
                        if lo <= raw <= hi:
                            anchor = arc.Evaluate(raw, False)
                            tags[i] = (d, tag, anchor)
                except Exception:
                    pass
            along += w + 2.0 * gap
            a = _xy(view, anchor)
            c0 = _xy(view, arc.Center)
            n = (a[0] - c0[0], a[1] - c0[1])
            ln = (n[0] ** 2 + n[1] ** 2) ** 0.5 or 1.0
            n = (n[0] / ln, n[1] / ln)
            reach = abs(n[0]) * w / 2.0 + abs(n[1]) * h / 2.0
            for k in range(12):
                dist = 4.0 * gap + reach + k * (h + gap)
                c = (a[0] + n[0] * dist, a[1] + n[1] * dist)
                bx = (c[0] - w / 2.0, c[1] - h / 2.0, c[0] + w / 2.0, c[1] + h / 2.0)
                if not any(callout_layout.overlap(bx, q, gap / 2.0) for q in placed):
                    break
            places[d['id']] = {'centre': c, 'side': None, 'box': bx, 'taken': True}
            placed.append(bx)          # the next curved bar's mark keeps clear of this one (B12, 2026-10-17)
    pending = []
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
            side = places[d['id']].get('side')
            if side:
                squared = _square_leader(view, tag, c, side, _segment(view, d, indices.get(d['id'])), anchor)
                if squared:
                    pending.append((tag, squared[0], squared[1]))
        except Exception:
            pass
        if not places[d['id']].get('taken'):
            placed.append((c[0] - w / 2.0, c[1] - h / 2.0, c[0] + w / 2.0, c[1] + h / 2.0))
        report['marks'] += 1
    _line_up(doc, view, pending)


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
        line = _main_line(rebar, i, view)
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


def _marks(doc, view, items, cut, det, tag_types, box, gap, outside, placed, report, mode, per_set=False,
           clusters=None, side=None):
    """
    Bar marks of a section or elevation (SMDSC 4th ed. 6.2.3, 6.4.4, user 2026-10-10): its own mark over every bar the
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
    items = merge_singles(doc, items, clusters)
    fractions = _pointer_fractions(items)
    bars = {}
    ahead = list(placed)
    if not mode and not per_set:
        # a section's cut bars' marks stand past the faces, placed after the pointers: a pointer run where one of
        # them goes crossed it (user 2026-10-17, W10 and C2 3-3) - their lanes kept clear when choosing anchors
        frame0 = _crop_frame(view)
        half = TEXT_PAPER_MM * scale
        tall = (box[3] - box[1]) > 3.0 * (box[2] - box[0])
        for d in cut:
            for _i, _ref, point in _cut_bars(view, d, frame0):
                p = _xy(view, point)
                if tall:
                    ahead.append((box[0] - 1e6, p[1] - half, box[2] + 1e6, p[1] + half))
                    continue
                s = callout_layout.side_of(p, box)
                ahead.append({'top': (p[0] - 2 * half, p[1], p[0] + 2 * half, box[3] + 1e6),
                              'bottom': (p[0] - 2 * half, box[1] - 1e6, p[0] + 2 * half, p[1]),
                              'left': (box[0] - 1e6, p[1] - half, p[0], p[1] + half),
                              'right': (p[0], p[1] - half, box[2] + 1e6, p[1] + half)}[s])
    for d in items:
        index = _shown_bar(view, d['rebar'], d['count'])
        # a section marks loose bars as it marks sets, mark only (2026-10-18: W2's verticals read '39H12-03', W1's '03')
        typed = d if mode else dict((k, v) for k, v in d.items() if k != 'total')
        try:
            tag, index = _tag_bar(doc, view, d['rebar'], index, _single_type(
                doc, typed, tag_types, det._tag_type_for_bar(doc, d['rebar'], base)))
        except Exception:
            continue
        anchor = _clear_anchor(view, d, fractions.get(d['id'], 0.5), index, box, ahead, gap)
        if tag is not None and anchor is not None:
            entries.append((d['id'], tag, anchor))
            bars[d['id']] = (d, index)
    cut_type = tag_types.get(CUT_TAG) or base
    frame = _crop_frame(view)
    if mode is True:
        # an elevation cuts loose links one by one (a circular column's ties): one calling-up with their total
        # instead of a mark over every cut leg (user 2026-10-11)
        groups, kept = {}, []
        for d in cut:
            if d['count'] == 1 and d.get('mark'):
                groups.setdefault((d['mark'], get_id_value(d['rebar'].GetTypeId())), []).append(d)
            else:
                kept.append(d)
        for members in groups.values():
            if len(members) < 3:
                kept.extend(members)
                continue
            members.sort(key=lambda d: (round(d['first'][1], 3), round(d['first'][0], 3)))
            lead = dict(members[len(members) // 2], total=len(members))
            bars = _cut_bars(view, lead, frame)
            if not bars:
                continue
            i, ref, point = bars[0]
            try:
                tag = DB.IndependentTag.Create(doc, _single_type(doc, lead, tag_types, cut_type), view.Id, ref, True,
                                               DB.TagOrientation.Horizontal, point)
                entries.append((lead['id'], tag, point))
            except Exception:
                pass
        cut = kept
    for d in cut:
        bars = _cut_bars(view, d, frame)
        if per_set and len(bars) > 1:
            # a slab or base section cuts tens of bars of a set: its mark once, pointing at its middle bar
            i, ref, point = bars[len(bars) // 2]
            try:
                tag = DB.IndependentTag.Create(doc, tag_types.get(POINTER_TAG) or cut_type, view.Id, ref, True,
                                               DB.TagOrientation.Horizontal, point)
                entries.append((d['id'], tag, point))
            except Exception:
                pass
            continue
        for i, ref, point in bars:
            try:
                tag = DB.IndependentTag.Create(doc, cut_type, view.Id, ref, False, DB.TagOrientation.Horizontal,
                                               point)
            except Exception:
                continue
            entries.append(((d['id'], i), tag, point))
        if _text(d['rebar'], u'NOSA_Rebar_Layer') == u'spacer' and bars:
            # SMDSC 4th ed. MD B1 (user 2026-10-11): each spacer keeps its mark, and the set gets one calling-up
            # '4H25-01 SPACERS' pointing at the first
            try:
                i, ref, point = bars[0]
                tag = DB.IndependentTag.Create(doc, tag_types.get(SPACER_TAG) or base, view.Id, ref, True,
                                               DB.TagOrientation.Horizontal, point)
                entries.append((d['id'], tag, point))
            except Exception:
                pass
    if not entries:
        return
    doc.Regenerate()
    member = box
    if placed:
        box = (min([box[0]] + [b[0] for b in placed]), min([box[1]] + [b[1] for b in placed]),
               max([box[2]] + [b[2] for b in placed]), max([box[3]] + [b[3] for b in placed]))
    third = (member[3] - member[1]) / 3.0
    forced = side
    tall = (member[3] - member[1]) > 3.0 * (member[2] - member[0])
    layout = []
    for key, tag, anchor in entries:
        w, h, _o = _estimate(view, tag)
        a = _xy(view, anchor)
        if isinstance(key, tuple) and tall:
            # a wall's section: each cut bar's mark beside its face, in line with it (user 2026-10-12)
            side = 'left' if a[0] < (member[0] + member[2]) / 2.0 else 'right'
        elif mode == 'beam' or (isinstance(key, tuple) and not member[1] + third < a[1] < member[3] - third):
            # cut bars of a top or bottom layer, and all the bars of a beam elevation: above or below it
            side = 'top' if a[1] > (member[1] + member[3]) / 2.0 else 'bottom'
        else:
            side = forced or callout_layout.side_of(a, member)
        item = {'id': key, 'anchor': a, 'length': w, 'height': h, 'side': side}
        if isinstance(key, tuple):
            # a cut bar's mark stands next to the member over its bar, no pointer (SMDSC 4th ed. 6.2.3 sections)
            item['free'], item['outside'] = True, CUT_OUTSIDE_PAPER_MM * scale
        layout.append(item)
    for side in ('top', 'bottom'):
        row = [it for it in layout if it['side'] == side and not it.get('free')]
        if row and mode and callout_layout.crowded([it['anchor'][0] for it in row],
                                                   max(it['length'] for it in row), gap):
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
    edges = None
    if forced:
        # one side only (a column's right): its row starts past what is drawn level with the texts, not past the
        # whole view's (the section marks beside the column pushed the calling-up out, user 2026-10-12)
        ys = [it['anchor'][1] for it in layout if it['side'] == forced and not it.get('free')]
        if ys:
            lo_y, hi_y = min(ys) - 3.0 * gap, max(ys) + 3.0 * gap
            near = [q for q in placed if q[1] < hi_y and q[3] > lo_y]
            if forced == 'right':
                edges = {'right': max([member[2]] + [q[2] for q in near if q[0] >= member[2] - 1.0])}
            elif forced == 'left':
                edges = {'left': min([member[0]] + [q[0] for q in near if q[2] <= member[0] + 1.0])}
    places = callout_layout.place_pointers(layout, box, gap, outside, edges=edges,
                                           free_gap=FREE_GAP_PAPER_MM * scale, blocks=_grid_blocks(view))
    pending = []
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
            if key in bars:
                d, index = bars[key]
                squared = _square_leader(view, tag, places[key]['centre'], places[key].get('side'),
                                         _segment(view, d, index), anchor)
                if squared:
                    pending.append((tag, squared[0], squared[1]))
        except Exception:
            pass
        placed.append(places[key]['box'])
        report['marks'] += 1
    _line_up(doc, view, pending)


def see_drawing(doc, view, rebars, hosts=()):
    """
    Bars detailed on another drawing than the view's sheet: thick dashed, 'SEE DRG nnnn' (SMDSC 4th ed. 6.2.2), the
    note level outside the member on a line leaving the bar (2026-10-18 audit: it stood over the column's bars).
    """
    sheet = view.get_Parameter(DB.BuiltInParameter.VIEWPORT_SHEET_NUMBER)
    view_drawing = (sheet.AsString() or u'') if sheet is not None else u''
    if not view_drawing:
        return 0
    dash = DB.LinePatternElement.GetLinePatternElementByName(doc, u'Dash')
    text_type = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)
    n, noted = 0, set()
    for rebar in rebars:
        if rebar is None or not rebar.IsValidObject or rebar.IsHidden(view):
            continue
        see = presentation.see_drawing(_text(rebar, DRAWING_PARAM), view_drawing)
        if not see:
            continue
        ogs = DB.OverrideGraphicSettings()
        if dash is not None:
            ogs.SetProjectionLinePatternId(dash.Id)
        ogs.SetProjectionLineWeight(BAR_PEN)
        ogs.SetCutLineWeight(BAR_PEN)
        view.SetElementOverrides(rebar.Id, ogs)
        if see in noted:
            continue            # one note a drawing: eight starters up a column wrote it eight times over (2026-10-18)
        line = _main_line(rebar, 0)
        if line is not None and _see_note(doc, view, line, see, text_type, hosts):
            noted.add(see)
            n += 1
    return n


def _see_note(doc, view, line, text, text_type, hosts):
    """'SEE DRG nnnn' beside the member, clear of what is written, on a level line from the bar."""
    scale = max(1, int(getattr(view, 'Scale', 50) or 50))
    boxes = [_box_in_view(view, h.get_BoundingBox(None)) for h in hosts if h is not None]
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return _note(doc, view, line.Evaluate(0.5, True), text, text_type)
    member = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    taken = _written(doc, view)
    h = TEXT_PAPER_MM * scale
    w = (len(text) * 0.62 + 0.4) * h
    lift, gap = UNDERLINE_LIFT_PAPER_MM * scale, GAP_PAPER_MM * scale
    out = OUTSIDE_PAPER_MM * scale
    for t in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
        p = _xy(view, line.Evaluate(t, True))
        if not (member[1] <= p[1] <= member[3]):
            continue
        right = member[2] - p[0] <= p[0] - member[0]
        x0 = member[2] + out if right else member[0] - out - w
        bx = (x0, p[1] + lift, x0 + w, p[1] + lift + h)
        if any(_hit(bx, q, gap) for q in taken):
            continue
        note = _note(doc, view, _point(view, (x0, p[1] + lift + 1.2 * h), line.GetEndPoint(0)), text, text_type)
        if note is None:
            return None
        far = x0 + w if right else x0
        _draw_path(doc, view, [p, (far, p[1])], line.GetEndPoint(0), _line_style(doc, TOTAL_STYLE, 1))
        return note
    return None


def _hit(a, b, gap):
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


def _box_in_view(view, bb):
    if bb is None:
        return None
    pts = [_xy(view, DB.XYZ(x, y, z)) for x in (bb.Min.X, bb.Max.X) for y in (bb.Min.Y, bb.Max.Y)
           for z in (bb.Min.Z, bb.Max.Z)]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _written(doc, view):
    """The texts already in the view (tags as they write, notes), view mm."""
    out = []
    for tag in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag):
        b = _text_box(view, tag)
        if b is not None:
            out.append(b)
    for note in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.TextNote):
        b = _box_in_view(view, note.get_BoundingBox(view))
        if b is not None:
            out.append(b)
    return out


END_INSIDE_TOL_MM = 5.0


def _ends_inside(rebar, hosts):
    """True when a bar of the set ends inside one of the hosts (a starter, an anchorage), not when it only passes."""
    boxes = [h.get_BoundingBox(None) for h in hosts if h is not None]
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return False
    tol = END_INSIDE_TOL_MM / _MM_PER_FT
    try:
        n = rebar.NumberOfBarPositions
    except Exception:
        return False
    for i in sorted(set((0, n - 1))):
        chain = _centreline(rebar, i)
        if not chain:
            continue
        for p in (chain[0].GetEndPoint(0), chain[-1].GetEndPoint(1)):
            for b in boxes:
                if b.Min.X + tol < p.X < b.Max.X - tol and b.Min.Y + tol < p.Y < b.Max.Y - tol and \
                        b.Min.Z + tol < p.Z < b.Max.Z - tol:
                    return True
    return False


def foreign_bars(doc, view, own_ids, hosts):
    """
    The bars of other members a drawing's view shows (user 2026-10-17): hidden, except those ending inside its
    members - starters, anchorages - drawn thick dashed with 'SEE DRG nnnn' (SMDSC 4th ed. 6.2.2). Returns
    (hidden, kept).
    """
    from System.Collections.Generic import List
    hide, keep = List[DB.ElementId](), []
    for r in DB.FilteredElementCollector(doc, view.Id).OfClass(DBS.Rebar):
        if get_id_value(r.Id) in own_ids or not r.CanBeHidden(view):
            continue
        if _ends_inside(r, hosts):
            keep.append(r)
        else:
            hide.Add(r.Id)
    if hide.Count:
        try:
            view.HideElements(hide)
        except Exception:
            pass
    return hide.Count, see_drawing(doc, view, keep, hosts)


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
