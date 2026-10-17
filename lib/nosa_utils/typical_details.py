# -*- coding: utf-8 -*-
"""
nosa_utils.typical_details — the practice's own typical details (T9.21, user decision 2026-10-17: drawn after the
SMDSC 4th edition model details, not copied from them), one legend each so a drawing can carry the ones its case
needs, each citing the model detail and clauses it follows. Sketches are model mm at SCALE.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

SCALE = 20
PREFIX = u'TD '
OLD_PREFIX = u'NOSA TD '          # the legends' names before 2026-10-17: renamed in place
_FT = 304.8
# the template's filled region types: concrete cut by a section, and seen in plan or elevation (user 2026-10-17)
FILL_TYPES = {u'cut': u'NOSA concrete cut (light orange)',
              u'seen': u'NOSA concrete elevation/plan (Light grey) Opaque'}


def corner_bar(x, y, sx, sy, offset=150.0, half=400.0):
    """
    A corner diagonal of an opening at its corner (x, y), the opening lying towards (-sx, -sy): outside the
    opening, square to the corner's bisector, `offset` out from the corner, 2 x `half` long (SMDSC 4th ed. MD OP1).
    """
    r = 2.0 ** 0.5
    cx, cy = x + sx * offset / r, y + sy * offset / r
    dx, dy = sx * half / r, -sy * half / r
    return ('poly', ((cx - dx, cy - dy), (cx + dx, cy + dy)))


# kind: 'fill' ('cut' | 'seen', outer (x0, y0, x1, y1), [holes]) concrete, its boundary invisible |
# 'edge' ((x, y), ...) a real face of the concrete, thin - none where the member runs on (user 2026-10-17) |
# 'poly' ((x, y), ...) bar | 'thin' ((x, y), ...) a thin line (leader) | 'text' (x, y, text)
DETAILS = (
    (u'S1', u'SLAB TOP BARS AT AN INTERNAL SUPPORT', u'SMDSC 4th ed. MD S1', (
        ('fill', (u'cut', (0.0, 0.0, 2400.0, 250.0), [])), ('fill', (u'cut', (1050.0, -600.0, 1350.0, 0.0), [])),
        ('edge', ((0.0, 250.0), (2400.0, 250.0))), ('edge', ((0.0, 0.0), (1050.0, 0.0))),
        ('edge', ((1350.0, 0.0), (2400.0, 0.0))),
        ('edge', ((1050.0, 0.0), (1050.0, -600.0))), ('edge', ((1350.0, 0.0), (1350.0, -600.0))),
        ('poly', ((40.0, 210.0), (2360.0, 210.0))),
        ('poly', ((700.0, 175.0), (1700.0, 175.0))),
        ('poly', ((350.0, 140.0), (2050.0, 140.0))),
        ('poly', ((40.0, 40.0), (2360.0, 40.0))),
        ('thin', ((1350.0, 300.0), (1700.0, 300.0))), ('text', (1380.0, 410.0, u'100 %: 0.15 l or l_bd')),
        ('thin', ((1350.0, 520.0), (2050.0, 520.0))), ('text', (1380.0, 630.0, u'50 %: 0.3 l or l_bd')),
        ('thin', ((1350.0, 280.0), (1350.0, 540.0))),
        ('text', (0.0, -750.0, u'l = clear span, from the face of the support;')),
        ('text', (0.0, -850.0, u'the greater of the two governs')),
        ('text', (0.0, -950.0, u'Bottom bars: 40 % into the support, lapped')),
        ('text', (0.0, -1050.0, u'Distribution bars to the MD S1 table')),
    )),
    (u'S3', u'SLAB FREE EDGE', u'SMDSC 4th ed. MD S3', (
        ('fill', (u'cut', (0.0, 0.0, 1600.0, 250.0), [])),
        ('edge', ((0.0, 250.0), (1600.0, 250.0), (1600.0, 0.0), (0.0, 0.0))),
        ('poly', ((0.0, 210.0), (1530.0, 210.0))), ('poly', ((0.0, 40.0), (1530.0, 40.0))),
        ('poly', ((1000.0, 190.0), (1560.0, 190.0), (1560.0, 60.0), (1000.0, 60.0))),
        ('text', (0.0, -150.0, u'U-bars the size of the bottom bars, one beside')),
        ('text', (0.0, -250.0, u'each bar, their backs at the edge, legs lapped')),
        ('text', (0.0, -350.0, u'with the mats; 50 % of the span steel to the support')),
    )),
    (u'OP1', u'SLAB OPENING TRIMMING', u'SMDSC 4th ed. MD OP1 / 6.2.2.12', (
        ('fill', (u'seen', (0.0, 0.0, 2000.0, 1600.0), [(600.0, 500.0, 1400.0, 1100.0)])),
        ('edge', ((600.0, 500.0), (1400.0, 500.0), (1400.0, 1100.0), (600.0, 1100.0), (600.0, 500.0))),
        ('poly', ((100.0, 420.0), (1900.0, 420.0))), ('poly', ((100.0, 1180.0), (1900.0, 1180.0))),
        ('poly', ((520.0, 60.0), (520.0, 1540.0))), ('poly', ((1480.0, 60.0), (1480.0, 1540.0))),
        corner_bar(600.0, 500.0, -1.0, -1.0), corner_bar(1400.0, 500.0, 1.0, -1.0),
        corner_bar(600.0, 1100.0, -1.0, 1.0), corner_bar(1400.0, 1100.0, 1.0, 1.0),
        ('text', (700.0, 830.0, u'OPENING')),
        ('text', (0.0, -150.0, u'Trimmers of the area cut, half each side,')),
        ('text', (0.0, -250.0, u'l_bd (450 min.) past the opening, clear of the mat')),
        ('text', (0.0, -350.0, u'Openings 500-1000 in slabs over 250: corner')),
        ('text', (0.0, -450.0, u'diagonals top and bottom, outside the opening')),
    )),
    (u'W4', u'WALL OPENING', u'SMDSC 4th ed. MD W4', (
        ('fill', (u'seen', (0.0, 0.0, 1800.0, 1600.0), [(500.0, 400.0, 1300.0, 1200.0)])),
        ('edge', ((500.0, 400.0), (1300.0, 400.0), (1300.0, 1200.0), (500.0, 1200.0), (500.0, 400.0))),
        ('poly', ((100.0, 340.0), (1700.0, 340.0))), ('poly', ((100.0, 1260.0), (1700.0, 1260.0))),
        ('poly', ((440.0, 60.0), (440.0, 1540.0))), ('poly', ((1360.0, 60.0), (1360.0, 1540.0))),
        ('poly', ((470.0, 370.0), (1330.0, 370.0), (1330.0, 1230.0), (470.0, 1230.0), (470.0, 370.0))),
        ('text', (650.0, 830.0, u'OPENING')),
        ('text', (0.0, -150.0, u'Trimmers one size up from the verticals,')),
        ('text', (0.0, -250.0, u'tension anchorage past the opening')),
        ('text', (0.0, -350.0, u'U-bars the size of the horizontals, round it,')),
        ('text', (0.0, -450.0, u'enclosing the trimmers; wall 175 min.')),
    )),
    (u'C1', u'COLUMN STARTERS AND KICKER', u'SMDSC 4th ed. MD C1 / MD F1', (
        ('fill', (u'cut', (0.0, 0.0, 1800.0, 700.0), [])), ('fill', (u'cut', (650.0, 700.0, 1150.0, 775.0), [])),
        ('fill', (u'cut', (650.0, 775.0, 1150.0, 1500.0), [])),
        ('edge', ((650.0, 700.0), (0.0, 700.0), (0.0, 0.0), (1800.0, 0.0), (1800.0, 700.0), (1150.0, 700.0))),
        ('edge', ((650.0, 1500.0), (650.0, 700.0))), ('edge', ((1150.0, 1500.0), (1150.0, 700.0))),
        ('thin', ((650.0, 775.0), (1150.0, 775.0))),
        ('poly', ((700.0, 1500.0), (700.0, 75.0), (400.0, 75.0))),
        ('poly', ((1100.0, 1500.0), (1100.0, 75.0), (1400.0, 75.0))),
        ('poly', ((650.0, 300.0), (1150.0, 300.0))), ('poly', ((650.0, 500.0), (1150.0, 500.0))),
        ('text', (1250.0, 860.0, u'KICKER 75 (150 below ground)')),
        ('text', (1250.0, 1250.0, u'Projection: lap + kicker + 150')),
        ('text', (0.0, -150.0, u'Starter links H10-300, 3 min., in the base')),
        ('text', (0.0, -250.0, u'Starters fixed to a template before the pour')),
    )),
    (u'PC1', u'PILE CAP', u'SMDSC 4th ed. MD PC1 / 6.7', (
        ('fill', (u'cut', (0.0, 0.0, 2000.0, 900.0), [])),
        ('fill', (u'seen', (250.0, -600.0, 750.0, 0.0), [])), ('fill', (u'seen', (1250.0, -600.0, 1750.0, 0.0), [])),
        ('edge', ((0.0, 0.0), (2000.0, 0.0), (2000.0, 900.0), (0.0, 900.0), (0.0, 0.0))),
        ('edge', ((250.0, -600.0), (250.0, 0.0))), ('edge', ((750.0, -600.0), (750.0, 0.0))),
        ('edge', ((1250.0, -600.0), (1250.0, 0.0))), ('edge', ((1750.0, -600.0), (1750.0, 0.0))),
        ('poly', ((100.0, 800.0), (100.0, 175.0), (1900.0, 175.0), (1900.0, 800.0))),
        ('poly', ((140.0, 800.0), (140.0, 215.0), (1860.0, 215.0), (1860.0, 800.0))),
        ('text', (0.0, -750.0, u'Bars over the piles, 100 cover above the pile heads')),
        ('text', (0.0, -850.0, u'Lacers round the U-bar legs; piles cut off')),
        ('text', (0.0, -950.0, u'75 into the cap (see the pile table)')),
    )),
)


def by_key():
    return dict((key, (title, md, sketch)) for key, title, md, sketch in DETAILS)


def view_name(key, prefix=PREFIX):
    title, _md, _s = by_key()[key]
    return u'{}{} - {}'.format(prefix, key, title)


def needed(host_kinds, layers, piled=False):
    """
    The typical details a drawing calls for (T9.21): host_kinds ('floor', 'wall', 'foundation', ...) and the rebar
    layers on it. Keys in DETAILS order.
    """
    layers = set((l or u'').strip().lower() for l in layers)
    kinds = set(host_kinds)
    want = set()
    if 'floor' in kinds:
        if layers & set((u'top_x', u'top_y')):
            want.add(u'S1')
        if layers & set((u'end_ubar', u'corner_ubar')):
            want.add(u'S3')
        if any(l.startswith(u'trimmer_') or l.startswith(u'diagonal_') for l in layers):
            want.add(u'OP1')
    if 'wall' in kinds and layers & set((u'trimmer', u'opening_ubar')):
        want.add(u'W4')
    if layers & set((u'dowel', u'starter_link')):
        want.add(u'C1')
    if piled:
        want.add(u'PC1')
    return [key for key, _t, _m, _s in DETAILS if key in want]


def _xyz(x, y):
    from Autodesk.Revit import DB  # Lazy import
    return DB.XYZ(x / _FT, y / _FT, 0.0)


def wide_lines(doc):
    """Revit's 'Wide Lines' style: the bars of a detail drawn heavy over the thin concrete outline."""
    from Autodesk.Revit import DB  # Lazy import
    lines = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
    for sub in lines.SubCategories:
        if sub.Name in (u'<Wide Lines>', u'Wide Lines'):
            return sub.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
    return None


def _fill_type(doc, kind):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name
    for frt in DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType):
        if element_name(frt) == FILL_TYPES[kind]:
            return frt
    return None


def _loop(x0, y0, x1, y1):
    from Autodesk.Revit import DB  # Lazy import
    loop = DB.CurveLoop()
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    for a, b in zip(pts, pts[1:]):
        loop.Append(DB.Line.CreateBound(_xyz(*a), _xyz(*b)))
    return loop


def draw(doc, view, key, text_type_id, bar_style=None, thin_style=None):
    """Draw detail `key` into an empty legend view: concrete in its material colour, bars heavy, title over it."""
    from Autodesk.Revit import DB  # Lazy import
    from System.Collections.Generic import List
    title, md, sketch = by_key()[key]
    view.Scale = SCALE
    top = max([p[1] for kind, d in sketch if kind in ('poly', 'thin', 'edge') for p in d] +
              [d[1][3] for kind, d in sketch if kind == 'fill'] + [d[1] + 60.0 for kind, d in sketch if kind == 'text']
              + [0.0])
    invisible = [g for g in DB.FilteredElementCollector(doc).OfClass(DB.GraphicsStyle)
                 if g.Name == u'<Invisible lines>']
    if bar_style is None:
        bar_style = wide_lines(doc)

    def line(a, b, style):
        c = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_xyz(*a), _xyz(*b)))
        if style is not None:
            c.LineStyle = style
    for kind, d in sketch:            # the concrete first, under the lines
        if kind != 'fill':
            continue
        fill_kind, outer, holes = d
        frt = _fill_type(doc, fill_kind)
        if frt is None:
            continue
        loops = List[DB.CurveLoop]()
        loops.Add(_loop(*outer))
        for h in holes:
            loops.Add(_loop(*h))
        try:
            region = DB.FilledRegion.Create(doc, frt.Id, view.Id, loops)
            if invisible:
                region.SetLineStyleId(invisible[0].Id)     # the real faces are drawn as 'edge' lines
        except Exception:
            continue
    for kind, d in sketch:
        if kind in ('poly', 'thin', 'edge'):
            for a, b in zip(d, d[1:]):
                line(a, b, bar_style if kind == 'poly' else thin_style)
        elif kind == 'text':
            x, y, text = d
            DB.TextNote.Create(doc, view.Id, _xyz(x, y), text, text_type_id)
    DB.TextNote.Create(doc, view.Id, _xyz(0.0, top + 350.0), u'TYPICAL DETAIL {} - {}'.format(key, title),
                       text_type_id)
    DB.TextNote.Create(doc, view.Id, _xyz(0.0, top + 220.0), u'After {} - confirm with design'.format(md),
                       text_type_id)
