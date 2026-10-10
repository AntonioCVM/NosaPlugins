# -*- coding: utf-8 -*-
"""
Tag All engine (T7.4): tag every element of the chosen categories in a view, re-arrange the
existing tags of those categories, keep tags off each other and off columns, give a leader only
to a tag that ended away from its element, and undo crossing leaders (nosa_utils.label_layout).
One transaction per view, rolled back on a Revit error instead of a dialog.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os

from nosa_utils import tag_rules
from nosa_utils.label_layout import layout_tags

_FT = 304.8
_TAG_CATEGORY = {'columns': 'OST_StructuralColumnTags', 'piles': 'OST_StructuralColumnTags',
                 'framing': 'OST_StructuralFramingTags', 'walls': 'OST_WallTags',
                 'floors': 'OST_FloorTags', 'foundations': 'OST_StructuralFoundationTags',
                 'stair_landings': 'OST_StairsLandingTags', 'rebar': 'OST_RebarTags'}
_GEOMETRY = dict((c[0], c[3]) for c in tag_rules.CATEGORIES)
_ELEMENT_CATEGORY = dict((c[0], c[2]) for c in tag_rules.CATEGORIES)
_RA_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
_rebar_detailing = None
_rebar_presentation = None
MRA_PREFERENCE = (u'dots',)
MRA_MIN_SPREAD_MM = 10.0    # paper: narrower sets (bars across a beam) get an ordinary tag


def _bic(name):
    from Autodesk.Revit import DB  # Lazy import
    return getattr(DB.BuiltInCategory, name)


def _ra_detailing():
    global _rebar_detailing
    if _rebar_detailing is None:
        import sys
        from nosa_utils.bootstrap import load_module
        if _RA_LIB not in sys.path:
            sys.path.insert(0, _RA_LIB)
        _rebar_detailing = load_module('tagall_rebar_detailing', os.path.join(_RA_LIB, 'rebar_detailing.py'))
    return _rebar_detailing


def _ra_presentation():
    global _rebar_presentation
    if _rebar_presentation is None:
        from nosa_utils.bootstrap import load_module
        _ra_detailing()
        _rebar_presentation = load_module('tagall_rebar_presentation', os.path.join(_RA_LIB, 'rebar_presentation.py'))
    return _rebar_presentation


def present_rebar(doc, view, mra_type):
    """T8.27, IStructE SMDSC 6.2.2: the bars of the view as typical bars with indicator lines and notes."""
    from nosa_utils.revit_helpers import get_id_value
    rebars = elements(doc, view, 'rebar')
    if not rebars:
        return {}
    hosts, seen = [], set()
    for r in rebars:
        try:
            h = doc.GetElement(r.GetHostId())
        except Exception:
            h = None
        if h is not None and get_id_value(h.Id) not in seen:
            seen.add(get_id_value(h.Id))
            hosts.append(h)
    return _ra_presentation().apply(doc, view, rebars, _ra_detailing(),
                                    mra_type.Id if mra_type is not None else mra_type_id(doc), hosts=hosts)


def tag_types(doc, key):
    """[(name, id)] of the tag types loaded for a category, 'Family : Type'."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    out = []
    for symbol in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(_bic(_TAG_CATEGORY[key])):
        out.append((u'{} : {}'.format(symbol.FamilyName, element_name(symbol)), symbol.Id))
    return sorted(out)


def elements(doc, view, key):
    from Autodesk.Revit import DB  # Lazy import
    found = []
    try:
        collector = DB.FilteredElementCollector(doc, view.Id).OfCategory(
            _bic(_ELEMENT_CATEGORY[key])).WhereElementIsNotElementType()
    except Exception:
        return []
    for el in collector:
        if key in ('columns', 'piles'):
            family = getattr(getattr(el, 'Symbol', None), 'FamilyName', u'')
            if tag_rules.is_pile(family) != (key == 'piles'):
                continue
        found.append(el)
    return found


def _context(key, el, kind):
    """Context for tag_rules.pick_tag_type."""
    from Autodesk.Revit import DB  # Lazy import
    if key == 'rebar':
        return kind
    if key == 'framing' and kind == 'section':
        return 'section'
    if key == 'foundations':
        return 'slab' if isinstance(el, DB.Floor) else 'plan'
    if key in ('columns', 'framing'):
        try:
            return 'steel' if u'{}'.format(el.StructuralMaterialType).endswith(u'Steel') else 'concrete'
        except Exception:
            return 'concrete'
    return None


def default_type_id(doc, key, el, kind):
    types = tag_types(doc, key)
    if not types:
        return None
    return types[tag_rules.pick_tag_type([n for n, _i in types], key, _context(key, el, kind))][1]


def _rect(element, view):
    """(xmin, ymin, xmax, ymax) of an element in the view plane, ft."""
    from Autodesk.Revit import DB  # Lazy import
    box = element.get_BoundingBox(view)
    if box is None:
        return None
    right, up = view.RightDirection, view.UpDirection
    xs, ys = [], []
    for x in (box.Min.X, box.Max.X):
        for y in (box.Min.Y, box.Max.Y):
            for z in (box.Min.Z, box.Max.Z):
                p = DB.XYZ(x, y, z)
                xs.append(p.DotProduct(right))
                ys.append(p.DotProduct(up))
    return (min(xs), min(ys), max(xs), max(ys))


def _tag_rect(tag, view, char_ratio=0.75):
    rect = _rect(tag, view)
    if rect is None:
        return None
    try:
        text = tag.TagText or u''
    except Exception:
        text = u''
    height = rect[3] - rect[1]
    width = max(rect[2] - rect[0], len(text) * char_ratio * height)
    cx = (rect[0] + rect[2]) / 2.0
    return (cx - width / 2.0, rect[1], cx + width / 2.0, rect[3])


def head_rects(doc, view, tags):
    """
    Head rectangles of tags (text included, leader excluded): Revit's box of a tag with a leader
    spans the leader too, so leaders are switched off for the measure and then restored.
    """
    states = []
    for tag in tags:
        try:
            states.append(tag.HasLeader)
            if tag.HasLeader:
                tag.HasLeader = False
        except Exception:
            states.append(None)
    doc.Regenerate()
    rects = [_tag_rect(tag, view) for tag in tags]
    for tag, state in zip(tags, states):
        if state:
            try:
                tag.HasLeader = True
            except Exception:
                continue
    doc.Regenerate()
    return rects


def _anchor(el, view, geometry):
    """The point (view plane) a tag annotates, and the element's own rectangle."""
    from Autodesk.Revit import DB  # Lazy import
    rect = _rect(el, view)
    if rect is None:
        return None, None
    if geometry == 'line':
        curve = getattr(getattr(el, 'Location', None), 'Curve', None)
        if curve is not None:
            p = curve.Evaluate(0.5, True)
            return (p.DotProduct(view.RightDirection), p.DotProduct(view.UpDirection)), rect
    return ((rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0), rect


def natural_rect(geometry, anchor, el_rect, tag_rect, gap):
    """Where a tag of this size naturally sits: beside a column's corner, over a beam, on a slab."""
    w, h = tag_rect[2] - tag_rect[0], tag_rect[3] - tag_rect[1]
    if geometry == 'point':
        x0, y0 = el_rect[2] + gap, el_rect[3] + gap
        return (x0, y0, x0 + w, y0 + h)
    if geometry == 'line':
        horizontal = (el_rect[2] - el_rect[0]) >= (el_rect[3] - el_rect[1])
        if horizontal:
            return (anchor[0] - w / 2.0, el_rect[3] + gap, anchor[0] + w / 2.0, el_rect[3] + gap + h)
        return (el_rect[2] + gap, anchor[1] - h / 2.0, el_rect[2] + gap + w, anchor[1] + h / 2.0)
    return (anchor[0] - w / 2.0, anchor[1] - h / 2.0, anchor[0] + w / 2.0, anchor[1] + h / 2.0)


def mra_type_id(doc, preferred=MRA_PREFERENCE):
    """Multi-Rebar Annotation type for Tag All in plans: the first whose name contains a preferred
    word, else the first loaded, else None."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    types = sorted(DB.FilteredElementCollector(doc).OfClass(DB.MultiReferenceAnnotationType),
                   key=element_name)
    if not types:
        return None
    names = [element_name(t) for t in types]
    return types[mra_pick(names, preferred)].Id


def mra_pick(names, preferred=MRA_PREFERENCE):
    """Index of the preferred MRA type name (pure): 'Zone label - Dots' before 'No dots'."""
    for wanted in preferred:
        for i, name in enumerate(names):
            low = (name or u'').lower()
            if wanted in low and u'no ' + wanted not in low:
                return i
    return 0


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def stack_out(rects, sides, obstacles, gap, max_steps=40):
    """
    (dx, dy) per MRA tag head (pure): each head is pushed away from its dimension line along its
    side (unit (x, y) in view coordinates), alternately to one side and the other a head at a time,
    until it clears the obstacles and the heads already placed. A rect of None stays put.
    """
    placed = [r for r in obstacles if r is not None]
    out = []
    for rect, side in zip(rects, sides):
        if rect is None:
            out.append((0.0, 0.0))
            continue
        step = abs(side[0]) * (rect[2] - rect[0] + gap) + abs(side[1]) * (rect[3] - rect[1] + gap)
        dx = dy = 0.0
        for i in range(max_steps + 1):
            k = (i + 1) // 2 * (1 if i % 2 else -1)
            dx, dy = side[0] * step * k, side[1] * step * k
            moved = (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)
            if not any(_overlap(moved, o) for o in placed):
                break
        placed.append((rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy))
        out.append((dx, dy))
    return out


def _mra_tagged(doc, view):
    """({element id: (MRA tag, MRA)}, {tag id}) of the rebar already carried by a Multi-Rebar Annotation."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    elements_, tags = {}, set()
    for mra in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.MultiReferenceAnnotation):
        tag = doc.GetElement(mra.TagId)
        if tag is None:
            continue
        tags.add(get_id_value(tag.Id))
        tagged = _tagged_id(tag)
        if tagged is not None:
            elements_[tagged] = (tag, mra)
    return elements_, tags


def _mra_side(doc, mra, tag):
    """Side an existing MRA head sits on: from its dimension line towards the head."""
    try:
        line = doc.GetElement(mra.DimensionId).Curve
        run = tag.TagHeadPosition - line.Origin
        away = run - line.Direction.Multiply(run.DotProduct(line.Direction))
        return away.Normalize() if away.GetLength() > 1e-6 else None
    except Exception:
        return None


def _stack_mra_heads(doc, view, stacked, items, keys, gap):
    """Push the MRA heads clear of each other, the elements' outlines and the other tags."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    right, up = view.RightDirection, view.UpDirection
    moving = set(get_id_value(t.Id) for t, _s in stacked) | set(get_id_value(it[0].Id) for it in items)
    others = [tag for tag in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag)
              if get_id_value(tag.Id) not in moving]
    obstacles = head_rects(doc, view, others)
    for key in ('columns', 'piles'):
        if key in keys:
            obstacles.extend(_rect(el, view) for el in elements(doc, view, key))
    sides = []
    for tag, side in stacked:
        if side is None:
            sides.append((0.0, 0.0))
            continue
        x, y = side.DotProduct(right), side.DotProduct(up)
        n = (x * x + y * y) ** 0.5 or 1.0
        sides.append((x / n, y / n))
    rects = head_rects(doc, view, [t for t, _s in stacked])
    moved = 0
    for (tag, _side), (dx, dy) in zip(stacked, stack_out(rects, sides, obstacles, gap)):
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            tag.TagHeadPosition = tag.TagHeadPosition + right.Multiply(dx) + up.Multiply(dy)
            moved += 1
    doc.Regenerate()
    return moved


def _tagged_id(tag):
    from nosa_utils.revit_helpers import get_id_value
    try:
        ids = list(tag.GetTaggedLocalElementIds())
        if ids:
            return get_id_value(ids[0])
    except Exception:  # nosa-lint: disable=NOSA006 - older API: the single-id property below
        pass
    try:
        return get_id_value(tag.TaggedLocalElementId)
    except Exception:
        return None


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


def tag_view(doc, view, keys, type_ids=None, rearrange=True, gap_paper_mm=1.5, leader_after=1.5):
    """
    Tag `keys` (tag_rules.KEYS) in one view. type_ids: {key: tag type id} overrides the NOSA
    preference ('rebar_mra' for the Multi-Rebar Annotation type). In plans every rebar set gets one
    MRA (T8.15); single bars and sets seen end-on get a tag.
    Returns {'created', 'mra', 'rearranged', 'leaders', 'failed', 'errors'}.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    report = {'created': 0, 'mra': 0, 'rearranged': 0, 'leaders': 0, 'failed': 0, 'errors': []}
    kind = tag_rules.view_kind(view.ViewType)
    if kind is None:
        return report
    type_ids = type_ids or {}
    guard = _rollback_on_error()
    t = DB.Transaction(doc, u'NOSA — Tag All ({})'.format(view.Name))
    options = t.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(guard)
    options.SetClearAfterRollback(True)
    options.SetForcedModalHandling(False)
    t.SetFailureHandlingOptions(options)
    t.Start()
    try:
        mra_elements, mra_tags = _mra_tagged(doc, view) if kind == 'plan' else ({}, set())
        mra_type = None
        if kind == 'plan' and 'rebar' in keys:
            mra_type = doc.GetElement(type_ids.get('rebar_mra') or mra_type_id(doc) or DB.ElementId.InvalidElementId)
        existing = {}
        for tag in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag):
            if get_id_value(tag.Id) in mra_tags:
                continue
            tagged = _tagged_id(tag)
            if tagged is not None:
                existing.setdefault(tagged, []).append(tag)
        items = []          # (tag, element, geometry)
        stacked = []        # (MRA tag, side the head moves to)
        for key in keys:
            geometry = _GEOMETRY[key]
            for el in elements(doc, view, key):
                eid = get_id_value(el.Id)
                if eid in mra_elements:
                    if rearrange:
                        mra_tag, mra = mra_elements[eid]
                        stacked.append((mra_tag, _mra_side(doc, mra, mra_tag)))
                    continue
                if eid in existing:
                    if rearrange:
                        items.extend((tag, el, geometry) for tag in existing[eid])
                    continue
                type_id = type_ids.get(key) or default_type_id(doc, key, el, kind)
                if type_id is None:
                    continue
                if key == 'rebar' and mra_type is not None:
                    det = _ra_detailing()
                    scale = max(1, int(view.Scale))
                    direction = det.set_direction_in_view(el, view, MRA_MIN_SPREAD_MM * scale)
                    if direction is not None:
                        mra = det.create_multi_rebar_annotation(doc, view, [el], mra_type, 6.0 * scale,
                                                                tag_has_leader=True, direction=direction)
                        if mra is not None:
                            report['mra'] += 1
                            mra_tag = doc.GetElement(mra.TagId)
                            if mra_tag is not None:
                                stacked.append((mra_tag, view.ViewDirection.CrossProduct(direction)))
                            continue
                try:
                    if key == 'rebar':
                        tag = _ra_detailing().create_rebar_tag(doc, view, el, (0.0, 0.0, 0.0), None, type_id, False)
                    else:
                        anchor, _r = _anchor(el, view, geometry)
                        if anchor is None:
                            continue
                        point = view.RightDirection.Multiply(anchor[0]) + view.UpDirection.Multiply(anchor[1]) + \
                            view.ViewDirection.Multiply(view.Origin.DotProduct(view.ViewDirection))
                        tag = DB.IndependentTag.Create(doc, type_id, view.Id, DB.Reference(el), False,
                                                       DB.TagOrientation.Horizontal, point)
                    items.append((tag, el, geometry))
                    report['created'] += 1
                except Exception as e:
                    report['failed'] += 1
                    if len(report['errors']) < 5:
                        report['errors'].append(u'{} {}: {}'.format(key, eid, e))
        doc.Regenerate()
        items = [it for it in items if it[0] is not None and it[0].IsValidObject]
        scale = max(1, int(view.Scale)) if hasattr(view, 'Scale') else 50
        gap = gap_paper_mm * scale / _FT
        if stacked:
            report['rearranged'] += _stack_mra_heads(doc, view, stacked, items, keys, gap)
        moving = set(get_id_value(it[0].Id) for it in items)
        fixed = [tag for tag in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.IndependentTag)
                 if get_id_value(tag.Id) not in moving]
        obstacles = [r for r in head_rects(doc, view, fixed) if r is not None]
        for tag, _el, _g in items:
            try:
                tag.HasLeader = False           # placed afresh; the layout decides the leader
            except Exception:
                continue
        item_rects = head_rects(doc, view, [it[0] for it in items])
        for key in ('columns', 'piles'):
            for el in elements(doc, view, key):
                rect = _rect(el, view)
                if rect is not None:
                    obstacles.append(rect)
        anchors, naturals, current, kept = [], [], [], []
        for (tag, el, geometry), rect in zip(items, item_rects):
            anchor, el_rect = _anchor(el, view, geometry if geometry != 'rebar' else 'area')
            if anchor is None or rect is None:
                continue
            if geometry == 'rebar':
                natural = rect                        # create_rebar_tag already chose its spot
            else:
                natural = natural_rect(geometry, anchor, el_rect, rect, gap)
            anchors.append(anchor)
            naturals.append(natural)
            current.append(rect)
            kept.append(tag)
        right, up = view.RightDirection, view.UpDirection
        for tag, rect, natural, (dx, dy, leader) in zip(kept, current, naturals,
                                                         layout_tags(anchors, naturals, obstacles, gap,
                                                                     leader_after)):
            mx = (natural[0] + natural[2]) / 2.0 + dx - (rect[0] + rect[2]) / 2.0
            my = (natural[1] + natural[3]) / 2.0 + dy - (rect[1] + rect[3]) / 2.0
            if abs(mx) > 1e-9 or abs(my) > 1e-9:
                tag.TagHeadPosition = tag.TagHeadPosition + right.Multiply(mx) + up.Multiply(my)
                report['rearranged'] += 1
            try:
                tag.HasLeader = bool(leader)
            except Exception:
                continue
            if leader:
                report['leaders'] += 1
        if 'rebar' in keys:
            present = present_rebar(doc, view, mra_type)
            report['mra'] += present.get('mra', 0) if kind != 'plan' else 0
    except Exception as e:
        t.RollBack()
        report['errors'].append(u'{}: {}'.format(view.Name, e))
        return report
    if t.Commit() != DB.TransactionStatus.Committed or guard.errors:
        report['errors'].append(u'{}: rolled back by Revit — {}'.format(view.Name, u'; '.join(guard.errors)))
        report['created'] = report['mra'] = report['rearranged'] = report['leaders'] = 0
    return report
