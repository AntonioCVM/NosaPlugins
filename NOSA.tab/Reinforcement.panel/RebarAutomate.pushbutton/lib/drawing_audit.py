# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — audit of the reinforcement drawings' annotations: every label, text, dimension, grid, bar,
detail line and leader of the views on the RC sheets, in paper mm, checked with nosa_utils.annotation_audit.
Read-only. Categories as the user's brief (2026-10-18): A1 band out of line, A3 overlap, A4 crossing lines,
A5 label turned, A6 band off its member at an odd distance, A7 out of the view's frame or the sheet,
A8 a label not printing its bar's mark (2026-10-24).
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from Autodesk.Revit import DB  # noqa: E402

_MM_PER_FT = 304.8
LABEL_SHRINK_MM = 0.3          # a tag's box has a little air round its text
BAND_TOL_MM = 1.0             # a band: near edges this close (rows of marks one over another are bands apart)
SPREAD_TOL_MM = 0.5
OFF_TOL_MM = 0.5
CUT_BAR_MM = 0.5               # a bar seen end on: a dot this size (paper)
SECTION_STYLE = u'NOSA Section Marks'


def _id(eid):
    from nosa_utils.revit_helpers import get_id_value
    return get_id_value(eid)


def _name(el):
    from nosa_utils.revit_helpers import element_name
    try:
        return element_name(el)
    except Exception:
        return u''


class _Frame(object):
    """View coordinates in paper mm."""

    def __init__(self, view):
        self.r, self.u = view.RightDirection, view.UpDirection
        self.k = _MM_PER_FT / max(1, view.Scale)

    def xy(self, p):
        return (p.DotProduct(self.r) * self.k, p.DotProduct(self.u) * self.k)

    def box(self, bb):
        if bb is None:
            return None
        pts = [self.xy(DB.XYZ(x, y, z))
               for x in (bb.Min.X, bb.Max.X) for y in (bb.Min.Y, bb.Max.Y) for z in (bb.Min.Z, bb.Max.Z)]
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _elements(doc, view, cls):
    try:
        return list(DB.FilteredElementCollector(doc, view.Id).OfClass(cls))
    except Exception:
        return []


def _union(boxes):
    boxes = [b for b in boxes if b is not None]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _tagged(tag):
    try:
        return [_id(i) for i in tag.GetTaggedLocalElementIds()]
    except Exception:
        try:
            return [_id(tag.TaggedLocalElementId)]
        except Exception:
            return []


def _tag_box(tag, view, f):
    """
    A tag's text box: Revit's box runs on to the bar it tags (leader or not, measured 2026-10-18) but the NOSA
    tags' text is centred on the head, so the shorter half each way from the head is the text's.
    """
    from nosa_utils import annotation_audit as aa
    b = f.box(tag.get_BoundingBox(view))
    if b is None:
        return None
    return aa.centred_box(f.xy(tag.TagHeadPosition), b)


def _note_box(doc, note, f):
    """
    A text note's text, paper mm: from its insertion point, alignment and lettering size - Revit's box of a note
    is padded far round its text (a 2 mm figure measured 7.4 mm high, 2026-10-18).
    """
    try:
        size = doc.GetElement(note.GetTypeId()).get_Parameter(DB.BuiltInParameter.TEXT_SIZE).AsDouble() * _MM_PER_FT
        text = (note.Text or u'').strip()
        rows = text.split(u'\r')
        w = max(len(r) for r in rows) * 0.62 * size
        h = (len(rows) * 1.25 - 0.25) * size
        align = note.HorizontalAlignment
        shift = w / 2.0 if align == DB.HorizontalTextAlignment.Center else             w if align == DB.HorizontalTextAlignment.Right else 0.0
        top = f.xy(note.Coord)
        u = f.xy(note.BaseDirection)
        n = (u[0] ** 2 + u[1] ** 2) ** 0.5 or 1.0
        u = (u[0] / n, u[1] / n)
        v = (-u[1], u[0])                    # up the text
        corners = []
        for a in (-shift, w - shift):
            for b in (-0.2 * size, -h - 0.2 * size):
                corners.append((top[0] + u[0] * a + v[0] * b, top[1] + u[1] * a + v[1] * b))
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        return (min(xs), min(ys), max(xs), max(ys))
    except Exception:
        return None


def _leader(tag, f):
    """A tag's leader as segments (head, elbow, end)."""
    if not getattr(tag, 'HasLeader', False):
        return []
    out = []
    try:
        refs = list(tag.GetTaggedReferences())
    except Exception:
        refs = []
    head = f.xy(tag.TagHeadPosition)
    for ref in refs:
        try:
            end = f.xy(tag.GetLeaderEnd(ref))
        except Exception:
            continue
        pts = [head]
        try:
            if tag.HasLeaderElbow(ref):
                pts.append(f.xy(tag.GetLeaderElbow(ref)))
        except Exception:
            pass
        pts.append(end)
        out.extend(zip(pts, pts[1:]))
    return out


def _dimension(doc, dim, f, view):
    """A dimension's lines and its texts' boxes (approximate: text size x characters)."""
    lines, texts = [], []
    try:
        curve = dim.Curve
        direction = curve.Direction
    except Exception:
        return lines, texts
    try:
        size = dim.DimensionType.get_Parameter(DB.BuiltInParameter.TEXT_SIZE).AsDouble() * _MM_PER_FT
    except Exception:
        size = 2.5
    d2 = f.xy(direction)
    n = (d2[0] ** 2 + d2[1] ** 2) ** 0.5 or 1.0
    d2 = (d2[0] / n, d2[1] / n)
    segs = []
    try:
        if dim.NumberOfSegments:
            for s in dim.Segments:
                segs.append((s.Origin, s.Value, getattr(s, 'TextPosition', None), s.ValueString))
        else:
            segs.append((dim.Origin, dim.Value, getattr(dim, 'TextPosition', None), dim.ValueString))
    except Exception:
        return lines, texts                     # ordinate, spot and formula dimensions: no plain line
    for origin, value, text_at, text in segs:
        if origin is None or value is None:
            continue
        c = f.xy(origin)
        half = value * f.k / 2.0
        lines.append(((c[0] - d2[0] * half, c[1] - d2[1] * half), (c[0] + d2[0] * half, c[1] + d2[1] * half)))
        if text_at is not None and text:
            t = f.xy(text_at)
            w, h = 0.75 * size * len(text) / 2.0, size / 2.0
            if abs(d2[0]) >= abs(d2[1]):
                texts.append((t[0] - w, t[1] - h, t[0] + w, t[1] + h))
            else:
                texts.append((t[0] - h, t[1] - w, t[0] + h, t[1] + w))
    return lines, texts


def _bars(doc, view, f):
    """Bars seen in the view: centreline segments, and dots for bars seen end on."""
    from Autodesk.Revit.DB.Structure import Rebar, MultiplanarOption
    segs, dots = [], []
    from rebar_presentation import shown_positions
    depth = _depth_range(view)
    for r in _elements(doc, view, Rebar):
        for i in shown_positions(r, view):
            try:
                curves = r.GetTransformedCenterlineCurves(False, False, False,
                                                          MultiplanarOption.IncludeOnlyPlanarCurves, i)
            except Exception:
                continue
            for c in curves:
                try:
                    model = list(c.Tessellate())
                except Exception:
                    continue
                pts = [f.xy(p) for p in model]
                for k, (p, q) in enumerate(zip(pts, pts[1:])):
                    if depth is not None:
                        # a section draws what lies within its depth: a curved wall's other bars and the run of
                        # its horizontal arcs beyond the cut are not drawn (2026-10-24, W2 section 2-2)
                        za, zb = depth[0].OfPoint(model[k]).Z, depth[0].OfPoint(model[k + 1]).Z
                        if max(za, zb) < depth[1] - 1e-3 or min(za, zb) > depth[2] + 1e-3:
                            continue
                        if abs(zb - za) > 1e-9:
                            # only the part within the depth
                            t0 = min(max((depth[1] - za) / (zb - za), 0.0), 1.0)
                            t1 = min(max((depth[2] - za) / (zb - za), 0.0), 1.0)
                            t0, t1 = min(t0, t1), max(t0, t1)
                            a3, b3 = model[k], model[k + 1]
                            p = f.xy(a3 + (b3 - a3).Multiply(t0))
                            q = f.xy(a3 + (b3 - a3).Multiply(t1))
                    if abs(p[0] - q[0]) + abs(p[1] - q[1]) < CUT_BAR_MM:
                        dots.append((p[0] - CUT_BAR_MM, p[1] - CUT_BAR_MM, p[0] + CUT_BAR_MM, p[1] + CUT_BAR_MM))
                    else:
                        segs.append((r, (p, q)))
    return segs, dots


def _viewer_heads(doc, view, f):
    """The heads and tails of the section marks drawn in the view (their ends: the line between them may be crossed)."""
    out = []
    try:
        viewers = DB.FilteredElementCollector(doc, view.Id).OfCategory(DB.BuiltInCategory.OST_Viewers) \
            .WhereElementIsNotElementType().ToElements()
    except Exception:
        return out
    size = 6.0
    for v in viewers:
        b = f.box(v.get_BoundingBox(view))
        if b is None:
            continue
        horizontal = (b[2] - b[0]) >= (b[3] - b[1])
        if min(b[2] - b[0], b[3] - b[1]) > 3.0 * size:
            # a mark on the skew (a curved beam's sections): its heads at the corners of its box, not a strip
            # the box's height (2026-10-24, B2: CH 1000 flagged on the strip)
            for x in (b[0], b[2] - size):
                for y in (b[1], b[3] - size):
                    out.append((x, y, x + size, y + size))
        elif horizontal:
            out.append((b[0], b[1], b[0] + size, b[3]))
            out.append((b[2] - size, b[1], b[2], b[3]))
        else:
            out.append((b[0], b[1], b[2], b[1] + size))
            out.append((b[0], b[3] - size, b[2], b[3]))
    return out


def _members(doc, view, f):
    from Autodesk.Revit.DB.Structure import Rebar
    hosts = {}
    for r in _elements(doc, view, Rebar):
        try:
            h = doc.GetElement(r.GetHostId())
        except Exception:
            h = None
        if h is not None:
            hosts[_id(h.Id)] = h
    boxes = []
    for h in hosts.values():
        b = f.box(h.get_BoundingBox(None))
        if b is not None:
            boxes.append(b)
    return boxes


def _crop(view, f):
    """The frame annotations are cut at: the crop and its annotation offsets, None when nothing cuts them."""
    if not view.CropBoxActive:
        return None
    try:
        p = view.get_Parameter(DB.BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
        if p is None or p.AsInteger() != 1:
            return None
    except Exception:
        return None
    cb = view.CropBox
    t = cb.Transform
    pts = [f.xy(t.OfPoint(DB.XYZ(x, y, cb.Min.Z))) for x in (cb.Min.X, cb.Max.X) for y in (cb.Min.Y, cb.Max.Y)]
    box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    try:
        m = view.GetCropRegionShapeManager()
        k = f.k
        return (box[0] - m.LeftAnnotationCropOffset * k, box[1] - m.BottomAnnotationCropOffset * k,
                box[2] + m.RightAnnotationCropOffset * k, box[3] + m.TopAnnotationCropOffset * k)
    except Exception:
        return box


def _masks(doc, view, f):
    """Boxes (paper mm) of the masking regions drawn in the view."""
    out = []
    for r in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.FilledRegion):
        try:
            if r.IsMasking:
                b = f.box(r.get_BoundingBox(view))
                if b is not None:
                    out.append(b)
        except Exception:
            continue
    return out


def _spans_member(seg, member, share=0.85):
    """A line (paper mm) running across most of the member's box its way: level across its width, upright its height."""
    if member is None:
        return False
    (a, b) = seg
    if abs(b[0] - a[0]) >= abs(b[1] - a[1]):
        return abs(b[0] - a[0]) >= share * (member[2] - member[0])
    return abs(b[1] - a[1]) >= share * (member[3] - member[1])


def _depth_range(view):
    """(inverse crop transform, min z, max z) of a section's crop box: the depth it draws; None for other views."""
    try:
        if not isinstance(view, DB.ViewSection) or not view.CropBoxActive:
            return None
        cb = view.CropBox
        return cb.Transform.Inverse, cb.Min.Z, cb.Max.Z
    except Exception:
        return None


def _model_crop(view, f):
    """The model crop of a view, paper mm (without the annotation offsets); None when it is not cropped."""
    try:
        if not view.CropBoxActive:
            return None
        cb = view.CropBox
        t = cb.Transform
        pts = [f.xy(t.OfPoint(DB.XYZ(x, y, cb.Min.Z))) for x in (cb.Min.X, cb.Max.X) for y in (cb.Min.Y, cb.Max.Y)]
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    except Exception:
        return None


def _kind(view):
    name = _name(view).lower()
    if u'section' in name:
        return u'section'
    if u'elevation' in name:
        return u'elevation'
    return u'plan'


def _check_mark(doc, tag, issue):
    """A8: the label prints its bar's mark (and varying range) as the BBS lists it."""
    import review
    from Autodesk.Revit.DB.Structure import Rebar
    from nosa_utils.revit_helpers import element_id_from_int
    for rid in _tagged(tag):
        rebar = doc.GetElement(element_id_from_int(rid))
        if not isinstance(rebar, Rebar):
            continue
        mark = rebar.LookupParameter(u'NOSA_Rebar_Mark')
        suffix = rebar.LookupParameter(u'NOSA_Rebar_Mark_Suffix')
        try:
            text = tag.TagText
        except Exception:
            continue
        printed = review.callout_mismatch(text, mark.AsString() if mark is not None else u'',
                                          (suffix.AsString() or u'') if suffix is not None else u'')
        if printed:
            issue(u'A8', u'T{}'.format(_id(tag.Id)), u'', u'prints {} for bar {} marked {}{}'.format(
                printed, rid, mark.AsString(), suffix.AsString() if suffix is not None else u''))
        return


def audit_view(doc, view, sheet_number):
    """Inventory and incidents of one view. Returns {'rows': [...], 'issues': [...], 'metrics': {...}}."""
    from nosa_utils import annotation_audit as aa
    from Autodesk.Revit.DB.Structure import Rebar
    f = _Frame(view)
    vname = _name(view)
    rows, issues = [], []

    def issue(cat, element, family, problem):
        issues.append({'sheet': sheet_number, 'view': vname, 'category': cat, 'element': element,
                       'family': family, 'problem': problem})

    # MRAs: their tag and indicator line belong together
    group = {}
    for m in _elements(doc, view, DB.MultiReferenceAnnotation):
        group[_id(m.TagId)] = _id(m.Id)
        group[_id(m.DimensionId)] = _id(m.Id)
    labels, label_info = {}, {}
    leaders = {}
    for tag in _elements(doc, view, DB.IndependentTag):
        _check_mark(doc, tag, issue)
        b = _tag_box(tag, view, f)
        if b is None:
            continue
        key = u'T{}'.format(_id(tag.Id))
        labels[key] = aa.shrink(b, LABEL_SHRINK_MM)
        ttype = doc.GetElement(tag.GetTypeId())
        fam = u'{} : {}'.format(getattr(getattr(ttype, 'Family', None), 'Name', u'') if ttype else u'', _name(ttype))
        kind = u'distribution (MRA)' if _id(tag.Id) in group else u'simple'
        label_info[key] = {'family': fam, 'kind': kind, 'tagged': _tagged(tag), 'group': group.get(_id(tag.Id))}
        rows.append({'sheet': sheet_number, 'view': vname, 'kind': kind, 'family': fam,
                     'element': u', '.join(str(i) for i in _tagged(tag)), 'id': _id(tag.Id)})
        try:
            if tag.TagOrientation != DB.TagOrientation.Horizontal:
                issue(u'A5', _id(tag.Id), fam, u'label turned ({})'.format(tag.TagOrientation))
        except Exception:
            pass
        for i, s in enumerate(_leader(tag, f)):
            leaders[u'{}-L{}'.format(key, i)] = s
    for note in _elements(doc, view, DB.TextNote):
        b = _note_box(doc, note, f) or f.box(note.get_BoundingBox(view))
        if b is None:
            continue
        key = u'N{}'.format(_id(note.Id))
        labels[key] = b
        label_info[key] = {'family': u'Text note : ' + _name(doc.GetElement(note.GetTypeId())), 'kind': u'text',
                           'turned': abs(f.xy(note.BaseDirection)[0]) < 0.99 * f.k,
                           'tagged': [], 'group': None}
        rows.append({'sheet': sheet_number, 'view': vname, 'kind': u'text', 'family': label_info[key]['family'],
                     'element': note.Text.strip()[:40], 'id': _id(note.Id)})
    dim_lines, dim_texts = {}, {}
    for d in _elements(doc, view, DB.Dimension):
        if isinstance(d, DB.SpotDimension):
            continue
        lines, texts = _dimension(doc, d, f, view)
        for i, s in enumerate(lines):
            dim_lines[u'D{}-{}'.format(_id(d.Id), i)] = (s, group.get(_id(d.Id)))
        for i, b in enumerate(texts):
            dim_texts[u'D{}-{}'.format(_id(d.Id), i)] = b
    detail = {}
    for c in _elements(doc, view, DB.CurveElement):
        if not getattr(c, 'ViewSpecific', False):
            continue
        try:
            if c.LineStyle is not None and c.LineStyle.Name == SECTION_STYLE:
                continue                 # the plugin's own section marks: their number stands at the arrow
        except Exception:
            pass
        try:
            pts = [f.xy(p) for p in c.GeometryCurve.Tessellate()]
        except Exception:
            continue
        for i, (p, q) in enumerate(zip(pts, pts[1:])):
            detail[u'C{}-{}'.format(_id(c.Id), i)] = (p, q)
    grids = {}
    for g in _elements(doc, view, DB.Grid):
        try:
            for i, c in enumerate(g.GetCurvesInView(DB.DatumExtentType.ViewSpecific, view)):
                grids[u'G{}-{}'.format(_name(g), i)] = (f.xy(c.GetEndPoint(0)), f.xy(c.GetEndPoint(1)))
        except Exception:
            continue
    bar_segs, bar_dots = _bars(doc, view, f)
    # only what the view draws: a bar under a masking region is hidden by it (a column cut to a stub under a beam
    # elevation, 2026-10-24 B3-B4)
    masks = _masks(doc, view, f)
    if masks:
        bar_segs = [(r, seg) for r, seg in bar_segs
                    if not any(all(m[0] <= q[0] <= m[2] and m[1] <= q[1] <= m[3] for q in seg) for m in masks)]
        bar_dots = [d for d in bar_dots
                    if not any(m[0] <= d[0] and d[2] <= m[2] and m[1] <= d[1] and d[3] <= m[3] for m in masks)]
    # ... and a bar outside its crop is not drawn (a curved wall's other verticals, 2026-10-24)
    seen_box = _model_crop(view, f)
    if seen_box is not None:
        bar_segs = [(r, seg) for r, seg in bar_segs if aa.segment_hits_box(seg, seen_box)
                    or all(seen_box[0] <= q[0] <= seen_box[2] and seen_box[1] <= q[1] <= seen_box[3] for q in seg)]
        bar_dots = [d for d in bar_dots if aa.area_overlap(d, seen_box)]
    viewers = _viewer_heads(doc, view, f)
    members = _members(doc, view, f)
    member = _union(members)
    crop = _crop(view, f)

    same = lambda a, b: (label_info[a]['group'] is not None and label_info[a]['group'] == label_info[b]['group'])
    for a, b in aa.overlapping_pairs(labels, same=same):
        issue(u'A3', a, label_info[a]['family'], u'label over label {}'.format(b))
    for key, box in labels.items():
        mine = label_info[key]['group']
        for dk, (seg, owner) in dim_lines.items():
            if owner is not None and owner == mine:
                continue
            if aa.segment_hits_box(seg, box):
                issue(u'A3', key, label_info[key]['family'],
                      u'label over {} {}'.format(u'indicator line' if owner else u'dimension line', dk))
                break
        for dk, tb in dim_texts.items():
            if aa.area_overlap(box, tb):
                issue(u'A3', key, label_info[key]['family'], u'label over dimension text {}'.format(dk))
                break
        for gk, seg in grids.items():
            if aa.segment_hits_box(seg, box):
                issue(u'A3', key, label_info[key]['family'], u'label over grid line {}'.format(gk))
                break
        tagged = set(label_info[key]['tagged'])
        for r, seg in bar_segs:
            if aa.segment_hits_box(seg, box):
                issue(u'A3', key, label_info[key]['family'],
                      u'label over bar {}{}'.format(_id(r.Id), u' (its own)' if _id(r.Id) in tagged else u''))
                break
        else:
            for dot in bar_dots:
                if aa.area_overlap(box, dot):
                    issue(u'A3', key, label_info[key]['family'], u'label over a cut bar')
                    break
        for ck, seg in detail.items():
            if label_info[key].get('turned'):
                break                        # a turned note's box is square to the sheet: too coarse for lines
            if aa.segment_hits_box(seg, box) and not aa.underlines(seg, box):
                issue(u'A3', key, label_info[key]['family'], u'label crossed by detail line {}'.format(ck))
                break
        for lk, seg in leaders.items():
            # another tag's pointer through this text (2026-10-24 audit, m2: a link's pointer through the '01')
            if not lk.startswith(key + u'-') and aa.segment_hits_box(seg, aa.shrink(box, LABEL_SHRINK_MM)) \
                    and not aa.underlines(seg, box):
                issue(u'A3', key, label_info[key]['family'], u'label crossed by the leader {}'.format(lk))
                break
        for vb in viewers:
            if aa.area_overlap(box, vb):
                issue(u'A3', key, label_info[key]['family'], u'label over a section mark')
                break
        if crop is not None and aa.outside(box, crop, tol=0.1):
            issue(u'A7', key, label_info[key]['family'], u'label outside the view\'s crop')
    callout = aa.callout_lines(detail, list(labels.values()))
    lines_ = dict([(k, v) for k, v in detail.items() if k in callout] + list(leaders.items()))
    for a, b in aa.crossing_pairs(lines_, same=lambda a, b: a.split(u'-')[0] == b.split(u'-')[0]):
        issue(u'A4', a, u'line', u'crosses {}'.format(b))
    for ck in callout:
        for gk, gseg in dim_lines.items():
            if aa.cross(detail[ck], gseg[0]):
                issue(u'A4', ck, u'line', u'crosses dimension {}'.format(gk))
                break
    whole = {}                                      # each dimension's full line: its segments end to end
    for gk, gseg in dim_lines.items():
        did = gk.rsplit(u'-', 1)[0]
        whole.setdefault(did, []).extend(gseg[0])
    for did, pts in whole.items():
        far = max(((a, b) for a in pts for b in pts), key=lambda ab: (ab[0][0] - ab[1][0]) ** 2 + (ab[0][1] - ab[1][1]) ** 2)
        whole[did] = far
    for lk, seg in leaders.items():
        for gk, gseg in dim_lines.items():
            if aa.cross(seg, gseg[0]):
                if _spans_member(whole.get(gk.rsplit(u'-', 1)[0], gseg[0]), member):
                    # an indicator line across the whole member: every calling-up out to that side crosses it
                    issue(u'A4i', lk, u'leader', u'crosses dimension {} across the whole member'.format(gk))
                else:
                    issue(u'A4', lk, u'leader', u'crosses dimension {}'.format(gk))
                break
    bands = []
    if member is not None:
        outer = dict((k, b) for k, b in labels.items() if label_info[k]['kind'] != u'text')
        bands = aa.bands(outer, member, BAND_TOL_MM)
        for band in bands:
            if len(band['keys']) > 1 and band['spread'] > SPREAD_TOL_MM:
                issue(u'A1', u', '.join(band['keys']), u'band',
                      u'{} band out of line by {:.1f} mm'.format(band['side'], band['spread']))
    metrics = {'sheet': sheet_number, 'view': vname, 'kind': _kind(view), 'scale': view.Scale,
               'labels': len(labels), 'bands': [{'side': b['side'], 'n': len(b['keys']), 'off': round(b['off'], 1),
                                                 'spread': round(b['spread'], 2)} for b in bands]}
    return {'rows': rows, 'issues': issues, 'metrics': metrics}


def audit_sheet(doc, sheet):
    """The sheet's own checks: viewports overlapping one another or outside the title block (A7)."""
    from nosa_utils import annotation_audit as aa
    issues = []
    boxes = {}
    for vp in DB.FilteredElementCollector(doc, sheet.Id).OfClass(DB.Viewport):
        o = vp.GetBoxOutline()
        boxes[_name(doc.GetElement(vp.ViewId))] = (o.MinimumPoint.X * _MM_PER_FT, o.MinimumPoint.Y * _MM_PER_FT,
                                                   o.MaximumPoint.X * _MM_PER_FT, o.MaximumPoint.Y * _MM_PER_FT)
    for a, b in aa.overlapping_pairs(boxes, tol=0.5):
        issues.append({'sheet': sheet.SheetNumber, 'view': a, 'category': u'A3', 'element': a, 'family': u'viewport',
                       'problem': u'viewport over viewport {}'.format(b)})
    tbs = list(DB.FilteredElementCollector(doc, sheet.Id).OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
               .WhereElementIsNotElementType())
    if tbs:
        bb = tbs[0].get_BoundingBox(sheet)
        frame = (bb.Min.X * _MM_PER_FT, bb.Min.Y * _MM_PER_FT, bb.Max.X * _MM_PER_FT, bb.Max.Y * _MM_PER_FT)
        for name, box in boxes.items():
            if aa.outside(box, frame, tol=0.5):
                issues.append({'sheet': sheet.SheetNumber, 'view': name, 'category': u'A7', 'element': name,
                               'family': u'viewport', 'problem': u'viewport outside the title block'})
    return issues


def audit(doc, prefix=u'45'):
    """Every RC drawing (sheet number starting with prefix): its views (legends left out) and the sheet."""
    out = {'rows': [], 'issues': [], 'metrics': []}
    sheets = sorted((s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)
                     if s.SheetNumber.startswith(prefix)), key=lambda s: s.SheetNumber)
    for sheet in sheets:
        out['issues'].extend(audit_sheet(doc, sheet))
        for vid in sheet.GetAllPlacedViews():
            view = doc.GetElement(vid)
            if view is None or view.ViewType in (DB.ViewType.Legend, DB.ViewType.Schedule):
                continue
            r = audit_view(doc, view, sheet.SheetNumber)
            out['rows'].extend(r['rows'])
            out['issues'].extend(r['issues'])
            out['metrics'].append(r['metrics'])
    return out
