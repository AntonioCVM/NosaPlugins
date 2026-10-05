# -*- coding: utf-8 -*-
"""
Sections of the 0900 General notes that a project can leave out: hidden in the view (never deleted)
and the sections below them in the same column moved up to close the gap. The shifts applied are kept
in Project Information (NOSA_GN_Sections) so that showing a section again puts everything back.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import json
import re

STATE_PARAM = u'NOSA_GN_Sections'
COLUMN_TOLERANCE_MM = 25.0      # headings of one column
ITEM_LEFT_TOLERANCE_MM = 5.0    # an item may start this much left of its column's heading
_MM = 304.8

# (key, label, heading regex) — the bold headings of the 0900 drafting view (first line of the note)
SECTIONS = [
    (u'general', u'General notes', r'^general notes$'),
    (u'legend', u'Legend', r'^legend:?$'),
    (u'earthworks', u'Earthworks', r'^earthworks notes'),
    (u'steelwork', u'Structural steelwork', r'^structural steelwork'),
    (u'concrete', u'Concrete (with anchorage & lap table, bond diagram, beam sketches)', r'^concrete$'),
    (u'timber', u'Timber', r'^timber$'),
    (u'masonry', u'Masonry (with mortar table, wall ties, lintels, padstones, movement joints)', r'^masonry$'),
    (u'contractor_design', u'Contractor design elements', r'^contractor design elements list'),
    (u'barriers', u'Barriers and handrails, cladding (with NA.8 table and wind data)', r'^barriers and handrails'),
]
ALWAYS = (u'general', u'legend')       # never hidden


def heading_key(text, sections=None):
    """Section key whose heading regex matches the first line of a text note, else None (pure)."""
    first = (text or u'').strip().split(u'\r')[0].split(u'\n')[0].strip()
    for key, _label, pattern in (sections if sections is not None else SECTIONS):
        if re.match(pattern, first, re.IGNORECASE):
            return key
    return None


def columns(headings, tolerance=COLUMN_TOLERANCE_MM):
    """
    [[(key, x, top)]] headings grouped by column (x within tolerance), each column top to bottom (pure).
    headings: [(key, x_left_mm, top_mm)].
    """
    cols = []
    for h in sorted(headings, key=lambda h: h[1]):
        for col in cols:
            if abs(col[0][1] - h[1]) <= tolerance:
                col.append(h)
                break
        else:
            cols.append([h])
    return [sorted(c, key=lambda h: -h[2]) for c in sorted(cols, key=lambda c: c[0][1])]


def assign(headings, items, tolerance=COLUMN_TOLERANCE_MM):
    """
    {key: [item id]} (pure): an item belongs to the nearest heading above it in its column.
    items: [(id, x_left_mm, x_right_mm, y_mid_mm, ...)]; an item in no column or above every heading of
    its column is left out (title, sheet furniture).
    """
    cols = columns(headings, tolerance)
    out = dict((h[0], []) for h in headings)
    for item in items:
        item_id, x0, y = item[0], item[1], item[3]
        best = None
        for col in cols:
            cx = col[0][1]
            if cx - ITEM_LEFT_TOLERANCE_MM <= x0 and (best is None or cx > best[0][1]):
                best = col
        if best is None:
            continue
        above = [h for h in best if h[2] + 1.0 >= y]
        if above:
            out[above[-1][0]].append(item_id)
    return out


def shifts(headings, bottoms, hidden, gap_mm=0.0, tolerance=COLUMN_TOLERANCE_MM):
    """
    {key: dy_mm} upward shift of every visible section so that hidden ones leave no gap (pure).
    bottoms: {key: lowest y of the section's content}; a hidden section frees the space from its heading
    to the next heading in the column (or to its own bottom when it is the last one).
    """
    out = {}
    for col in columns(headings, tolerance):
        freed = 0.0
        for i, (key, _x, top) in enumerate(col):
            if key in hidden:
                nxt = col[i + 1][2] if i + 1 < len(col) else bottoms.get(key, top) - gap_mm
                freed += top - nxt
                out[key] = 0.0
            else:
                out[key] = freed
    return out


def load_state(text):
    """{'hidden': [keys], 'shift': {key: mm}, 'members': {key: [ids]}} from the stored JSON (pure, tolerant)."""
    try:
        data = json.loads(text or u'{}')
    except ValueError:
        data = {}
    return {u'hidden': list(data.get(u'hidden') or []),
            u'shift': dict((k, float(v)) for k, v in (data.get(u'shift') or {}).items()),
            u'members': dict((k, [int(i) for i in v]) for k, v in (data.get(u'members') or {}).items()),
            u'geometry': dict((k, [float(x) for x in v]) for k, v in (data.get(u'geometry') or {}).items())}


def dump_state(hidden, shift, members=None, geometry=None):
    """
    JSON kept in Project Information. members: ids of the sections moved or hidden (moved ones are away from
    the template layout; hidden ones are the elements NOSA hid). geometry: {key: [x, top, bottom]} at home for
    hidden sections, because Revit gives no box for a hidden element.
    """
    moved = dict((k, round(v, 3)) for k, v in shift.items() if v)
    keep = set(moved) | set(hidden)
    data = {u'hidden': sorted(hidden), u'shift': moved}
    if members:
        data[u'members'] = dict((k, sorted(v)) for k, v in members.items() if k in keep and v)
    if geometry:
        data[u'geometry'] = dict((k, [round(x, 3) for x in v]) for k, v in geometry.items() if k in hidden)
    return json.dumps(data, sort_keys=True)


def home_layout(headings, items, state):
    """
    (headings, items) back at the template layout (pure): undo the stored shift of every section and of
    the elements recorded as its members, so that sections are assigned on positions that do not overlap.
    """
    shift = state.get(u'shift') or {}
    owner = {}
    for key, ids in (state.get(u'members') or {}).items():
        for i in ids:
            owner[i] = key
    home_h = [(k, x, top - shift.get(k, 0.0)) for k, x, top in headings]
    home_i = []
    for item in items:
        dy = shift.get(owner.get(item[0]), 0.0)
        home_i.append(tuple([item[0], item[1], item[2], item[3] - dy] + [v - dy for v in item[4:]]))
    return home_h, home_i


# ── Revit side ──────────────────────────────────────────────────────────────────────────────────

def _layout(doc, view):
    """(headings [(key, x, top)], items [(id, x0, x1, y_mid, y_min)]) in mm, visible elements only."""
    from Autodesk.Revit import DB
    from nosa_utils.revit_helpers import get_id_value
    headings, items = [], []
    for el in DB.FilteredElementCollector(doc).OwnedByView(view.Id).WhereElementIsNotElementType():
        if el.Category is None or isinstance(el, DB.Sketch) or el.IsHidden(view):
            continue
        box = el.get_BoundingBox(view)
        if box is None:
            continue
        if isinstance(el, DB.TextNote):
            key = heading_key(el.Text)
            if key is not None:
                headings.append((key, box.Min.X * _MM, box.Max.Y * _MM))
        items.append((get_id_value(el.Id), box.Min.X * _MM, box.Max.X * _MM, (box.Min.Y + box.Max.Y) / 2.0 * _MM,
                      box.Min.Y * _MM))
    return headings, items


def read_state(doc):
    p = doc.ProjectInformation.LookupParameter(STATE_PARAM)
    return load_state(p.AsString() if p is not None else u'')


def sections_in_view(doc, view):
    """[(key, label, present)] of the sections a project may leave out, for the window."""
    headings, _items = _layout(doc, view)
    found = set(h[0] for h in headings) | set(read_state(doc)[u'geometry'])
    return [(key, label, key in found) for key, label, _p in SECTIONS if key not in ALWAYS]


def apply(doc, view, hidden):
    """
    Hide the sections in `hidden`, show the others and move the visible ones so no gap is left.
    Only what NOSA hid is shown again. Call inside a transaction. Returns (hidden count, moved count).
    """
    from Autodesk.Revit import DB
    from System.Collections.Generic import List
    from nosa_utils.revit_helpers import element_id_from_int
    hidden = [k for k in hidden if k not in ALWAYS]
    state = read_state(doc)
    was_hidden = dict((k, state[u'geometry'][k]) for k in state[u'hidden'] if k in state[u'geometry'])
    headings, items = _layout(doc, view)
    # back to the template layout first: undo the shifts applied last time, then assign
    home, home_items = home_layout(headings, items, state)
    home += [(k, g[0], g[1]) for k, g in was_hidden.items()]
    members = assign(home, home_items)
    by_id = dict((i[0], i) for i in home_items)
    bottoms, geometry = {}, {}
    for key, ids in members.items():
        if key in was_hidden:
            members[key] = list(state[u'members'].get(key, []))
            bottoms[key] = was_hidden[key][2]
            continue
        ys = [by_id[i][4] for i in ids]
        bottoms[key] = min(ys) if ys else 0.0
    for key, x, top in home:
        geometry[key] = [x, top, bottoms.get(key, top)]
    wanted = shifts(home, bottoms, set(hidden))
    moved = 0
    for key, ids in members.items():
        if not ids:
            continue
        ids_net = List[DB.ElementId]([element_id_from_int(i) for i in ids if doc.GetElement(element_id_from_int(i))])
        if not ids_net.Count:
            continue
        dy = wanted.get(key, 0.0) - state[u'shift'].get(key, 0.0)   # a hidden section goes home too
        if abs(dy) > 1e-6:
            DB.ElementTransformUtils.MoveElements(doc, ids_net, DB.XYZ(0, dy / _MM, 0))
            moved += 1
        if key in hidden and key not in was_hidden:
            view.HideElements(ids_net)
        elif key not in hidden and key in was_hidden:
            view.UnhideElements(ids_net)
    p = doc.ProjectInformation.LookupParameter(STATE_PARAM)
    if p is not None:
        p.Set(dump_state(hidden, wanted, members, geometry))
    return len(hidden), moved
