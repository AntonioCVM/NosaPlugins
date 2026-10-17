# -*- coding: utf-8 -*-
"""
nosa_utils.typical_details — NOSA's own typical details (T9.21, user decision 2026-10-17: drawn by NOSA after the
SMDSC 4th edition model details, not copied from them), one legend each so a drawing can carry the ones its case
needs, each citing the model detail and clauses it follows. Sketches are model mm at SCALE.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

SCALE = 20
PREFIX = u'NOSA TD '
_FT = 304.8


def _u(x0, y0, w, h):
    """A U-bar opening right: its back at x0, legs w long, h apart."""
    return ('poly', ((x0 + w, y0), (x0, y0), (x0, y0 + h), (x0 + w, y0 + h)))


# kind: 'rect' (x0, y0, x1, y1) concrete | 'poly' ((x, y), ...) bar | 'dots' (x0, y, x1, step) cut bars |
# 'text' (x, y, text) | 'thin' ((x, y), ...) a thin line (dimension / leader)
DETAILS = (
    (u'S1', u'SLAB TOP BARS AT AN INTERNAL SUPPORT', u'SMDSC 4th ed. MD S1', (
        ('rect', (0.0, 0.0, 2400.0, 250.0)), ('rect', (1050.0, -600.0, 1350.0, 0.0)),
        ('poly', ((40.0, 210.0), (2360.0, 210.0))),
        ('poly', ((450.0, 170.0), (1950.0, 170.0))),
        ('poly', ((40.0, 40.0), (2360.0, 40.0))),
        ('thin', ((1350.0, 330.0), (1950.0, 330.0))), ('text', (1400.0, 420.0, u'50 %: 0.3 l or l_bd')),
        ('thin', ((1350.0, 290.0), (1700.0, 290.0))), ('text', (1400.0, 560.0, u'100 %: 0.15 l or l_bd')),
        ('text', (0.0, -750.0, u'l = clear span; the greater of the two governs')),
        ('text', (0.0, -850.0, u'Bottom bars: 40 % into the support, lapped')),
        ('text', (0.0, -950.0, u'Distribution bars to the MD S1 table')),
    )),
    (u'S3', u'SLAB FREE EDGE', u'SMDSC 4th ed. MD S3', (
        ('rect', (0.0, 0.0, 1600.0, 250.0)),
        ('poly', ((0.0, 210.0), (1560.0, 210.0))), ('poly', ((0.0, 40.0), (1560.0, 40.0))),
        _u(1000.0, 60.0, 560.0, 130.0),
        ('text', (0.0, -150.0, u'U-bars the size of the bottom bars, one beside')),
        ('text', (0.0, -250.0, u'each bar, legs lapped with the mats')),
        ('text', (0.0, -350.0, u'50 % of the span steel continues to the support')),
    )),
    (u'OP1', u'SLAB OPENING TRIMMING', u'SMDSC 4th ed. MD OP1 / 6.2.2', (
        ('rect', (600.0, 500.0, 1400.0, 1100.0)),
        ('poly', ((100.0, 420.0), (1900.0, 420.0))), ('poly', ((100.0, 1180.0), (1900.0, 1180.0))),
        ('poly', ((520.0, 0.0), (520.0, 1600.0))), ('poly', ((1480.0, 0.0), (1480.0, 1600.0))),
        ('poly', ((300.0, 200.0), (700.0, 600.0))), ('poly', ((1700.0, 200.0), (1300.0, 600.0))),
        ('poly', ((300.0, 1400.0), (700.0, 1000.0))), ('poly', ((1700.0, 1400.0), (1300.0, 1000.0))),
        ('text', (700.0, 830.0, u'OPENING')),
        ('text', (0.0, -150.0, u'Trimmers of the area cut, half each side,')),
        ('text', (0.0, -250.0, u'45 dia. past the opening, clear of the mat')),
        ('text', (0.0, -350.0, u'Openings 500-1000 in slabs over 250:')),
        ('text', (0.0, -450.0, u'diagonals top and bottom')),
    )),
    (u'W4', u'WALL OPENING', u'SMDSC 4th ed. MD W4', (
        ('rect', (500.0, 400.0, 1300.0, 1200.0)),
        ('poly', ((100.0, 340.0), (1700.0, 340.0))), ('poly', ((100.0, 1260.0), (1700.0, 1260.0))),
        ('poly', ((440.0, 0.0), (440.0, 1600.0))), ('poly', ((1360.0, 0.0), (1360.0, 1600.0))),
        ('text', (650.0, 830.0, u'OPENING')),
        ('text', (0.0, -150.0, u'Trimmers one size up from the verticals,')),
        ('text', (0.0, -250.0, u'tension anchorage past the opening')),
        ('text', (0.0, -350.0, u'U-bars the size of the horizontals, round it,')),
        ('text', (0.0, -450.0, u'enclosing the trimmers; wall 175 min.')),
    )),
    (u'C1', u'COLUMN STARTERS AND KICKER', u'SMDSC 4th ed. MD C1 / MF1', (
        ('rect', (0.0, 0.0, 1800.0, 700.0)), ('rect', (650.0, 700.0, 1150.0, 775.0)),
        ('poly', ((700.0, 1500.0), (700.0, 75.0), (400.0, 75.0))),
        ('poly', ((1100.0, 1500.0), (1100.0, 75.0), (1400.0, 75.0))),
        ('poly', ((650.0, 300.0), (1150.0, 300.0))), ('poly', ((650.0, 500.0), (1150.0, 500.0))),
        ('text', (1250.0, 760.0, u'KICKER 75 (150 below ground)')),
        ('text', (1250.0, 1250.0, u'Projection: lap + kicker + 150')),
        ('text', (0.0, -150.0, u'Starter links H10-300, 3 min., in the base')),
        ('text', (0.0, -250.0, u'Starters fixed to a template before the pour')),
    )),
    (u'PC1', u'PILE CAP', u'SMDSC 4th ed. MD PC1 / 6.7', (
        ('rect', (0.0, 0.0, 2000.0, 900.0)),
        ('rect', (250.0, -600.0, 750.0, 0.0)), ('rect', (1250.0, -600.0, 1750.0, 0.0)),
        _u(100.0, 175.0, 1800.0, 625.0),
        ('poly', ((100.0, 175.0), (100.0, 800.0))),
        ('text', (0.0, -750.0, u'Bars over the piles, 100 cover above the pile heads')),
        ('text', (0.0, -850.0, u'Lacers round the U-bar legs; piles cut off')),
        ('text', (0.0, -950.0, u'75 into the cap (see the pile table)')),
    )),
)


def by_key():
    return dict((key, (title, md, sketch)) for key, title, md, sketch in DETAILS)


def view_name(key):
    title, md, _s = by_key()[key]
    return u'{}{} - {}'.format(PREFIX, key, title)


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


def draw(doc, view, key, text_type_id, bar_style=None, thin_style=None):
    """Draw detail `key` into an empty legend view, its title and model detail reference over it."""
    import math
    from Autodesk.Revit import DB  # Lazy import
    title, md, sketch = by_key()[key]
    view.Scale = SCALE
    top = max([p[1] for kind, d in sketch if kind in ('poly', 'thin') for p in d] +
              [d[3] for kind, d in sketch if kind == 'rect'] + [d[1] + 60.0 for kind, d in sketch if kind == 'text']
              + [0.0])
    if bar_style is None:
        bar_style = wide_lines(doc)

    def line(a, b, style):
        c = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_xyz(*a), _xyz(*b)))
        if style is not None:
            c.LineStyle = style
    for kind, d in sketch:
        if kind == 'rect':
            x0, y0, x1, y1 = d
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
            for a, b in zip(pts, pts[1:]):
                line(a, b, None)
        elif kind in ('poly', 'thin'):
            for a, b in zip(d, d[1:]):
                line(a, b, bar_style if kind == 'poly' else thin_style)
        elif kind == 'dots':
            x0, y, x1, step = d
            n = int(round((x1 - x0) / step))
            for k in range(n + 1):
                doc.Create.NewDetailCurve(view, DB.Arc.Create(_xyz(x0 + k * step, y), 8.0 / _FT, 0.0,
                                                              2.0 * math.pi, DB.XYZ.BasisX, DB.XYZ.BasisY))
        elif kind == 'text':
            x, y, text = d
            DB.TextNote.Create(doc, view.Id, _xyz(x, y), text, text_type_id)
    DB.TextNote.Create(doc, view.Id, _xyz(0.0, top + 350.0), u'TYPICAL DETAIL {} - {}'.format(key, title),
                       text_type_id)
    DB.TextNote.Create(doc, view.Id, _xyz(0.0, top + 220.0), u'After {} - NOSA detail, confirm with design'.format(md),
                       text_type_id)
