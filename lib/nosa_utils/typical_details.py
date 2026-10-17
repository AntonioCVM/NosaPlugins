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
# 'fillpoly' ('cut' | 'seen', ((x, y), ...)) concrete of any outline |
# 'edge' ((x, y), ...) a real face of the concrete, thin - none where the member runs on (user 2026-10-17) |
# 'poly' ((x, y), ...) bar | 'dots' (x0, y0, x1, n[, dy]) bars cut: n along y0 from x0 to x1, or n up from y0 at
# dy when x0 == x1 | 'thin' ((x, y), ...) a thin line (leader) | 'text' (x, y, text)
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
        ('dots', (180.0, 215.0, 1820.0, 6)),
        ('dots', (140.0, 400.0, 140.0, 2, 200.0)), ('dots', (1860.0, 400.0, 1860.0, 2, 200.0)),
        ('text', (0.0, -750.0, u'U-bars over the piles, 100 cover above the pile heads;')),
        ('text', (0.0, -850.0, u'bars the other way above them; lacers round the legs')),
        ('text', (0.0, -950.0, u'Piles cut off 75 into the cap (see the piling drawing)')),
    )),
    (u'W1', u'WALL BASE, KICKER AND TOP', u'SMDSC 4th ed. MD W1', (
        ('fill', (u'cut', (0.0, 0.0, 1600.0, 500.0), [])), ('fill', (u'cut', (650.0, 500.0, 900.0, 575.0), [])),
        ('fill', (u'cut', (650.0, 575.0, 900.0, 1800.0), [])),
        ('edge', ((650.0, 500.0), (0.0, 500.0), (0.0, 0.0), (1600.0, 0.0), (1600.0, 500.0), (900.0, 500.0))),
        ('edge', ((650.0, 500.0), (650.0, 1800.0), (900.0, 1800.0), (900.0, 500.0))),
        ('thin', ((650.0, 575.0), (900.0, 575.0))),
        ('poly', ((700.0, 1150.0), (700.0, 75.0), (400.0, 75.0))),
        ('poly', ((850.0, 1150.0), (850.0, 75.0), (1150.0, 75.0))),
        ('poly', ((710.0, 900.0), (710.0, 1740.0))), ('poly', ((840.0, 900.0), (840.0, 1740.0))),
        ('poly', ((725.0, 1400.0), (725.0, 1725.0), (825.0, 1725.0), (825.0, 1400.0))),
        ('dots', (700.0, 1300.0, 700.0, 3, 200.0)), ('dots', (850.0, 1300.0, 850.0, 3, 200.0)),
        ('text', (1000.0, 600.0, u'KICKER 75 (150 below ground)')),
        ('text', (1000.0, 1000.0, u'Starters lapped above the kicker')),
        ('text', (1000.0, 1650.0, u'U-bar at a free top, legs the greater')),
        ('text', (1000.0, 1560.0, u'of 450 or 2 x the mat spacing')),
        ('text', (0.0, -150.0, u'Bars to Table 6.6 where the design gives none;')),
        ('text', (0.0, -250.0, u'horizontal bars outside the verticals')),
    )),
    (u'W2', u'WALL CORNER', u'SMDSC 4th ed. MD W2', (
        ('fillpoly', (u'cut', ((0.0, 0.0), (1600.0, 0.0), (1600.0, 250.0), (250.0, 250.0), (250.0, 1600.0),
                               (0.0, 1600.0)))),
        ('edge', ((1600.0, 0.0), (0.0, 0.0), (0.0, 1600.0))), ('edge', ((1600.0, 250.0), (250.0, 250.0),
                                                                       (250.0, 1600.0))),
        ('poly', ((1560.0, 45.0), (45.0, 45.0), (45.0, 1560.0))),
        ('poly', ((1560.0, 205.0), (205.0, 205.0), (205.0, 1560.0))),
        ('poly', ((700.0, 65.0), (65.0, 65.0), (65.0, 185.0), (700.0, 185.0))),
        ('poly', ((65.0, 700.0), (65.0, 65.0), (185.0, 65.0), (185.0, 700.0))),
        ('dots', (85.0, 85.0, 165.0, 2)), ('dots', (85.0, 165.0, 165.0, 2)),
        ('text', (500.0, 700.0, u'PLAN')),
        ('text', (0.0, -150.0, u'U-bars lapped with the horizontal bars round')),
        ('text', (0.0, -250.0, u'the corner; two bars in each loop up to 300 thick,')),
        ('text', (0.0, -350.0, u'four over 300; large opening moments: design')),
    )),
    (u'S2', u'SLAB RESTRAINED END SUPPORT', u'SMDSC 4th ed. MD S2', (
        ('fill', (u'cut', (0.0, 0.0, 2000.0, 250.0), [])), ('fill', (u'cut', (0.0, -800.0, 250.0, 0.0), [])),
        ('edge', ((2000.0, 250.0), (0.0, 250.0), (0.0, -800.0))), ('edge', ((250.0, -800.0), (250.0, 0.0),
                                                                        (2000.0, 0.0))),
        ('poly', ((1500.0, 210.0), (45.0, 210.0), (45.0, -500.0))),
        ('poly', ((2000.0, 40.0), (80.0, 40.0))),
        ('poly', ((900.0, 60.0), (65.0, 60.0), (65.0, 190.0), (900.0, 190.0))),
        ('text', (300.0, -300.0, u'Top bars bent down into the wall:')),
        ('text', (300.0, -400.0, u'a tension anchorage past the bend')),
        ('text', (0.0, -950.0, u'Top bars the greater of 0.3 x clear span or l_bd;')),
        ('text', (0.0, -1050.0, u'U-bars half the bottom steel at mid span;')),
        ('text', (0.0, -1150.0, u'wall starters detailed with the wall drawings')),
    )),
    (u'S4', u'CANTILEVER SLAB', u'SMDSC 4th ed. MD S4', (
        ('fill', (u'cut', (0.0, 0.0, 2600.0, 250.0), [])), ('fill', (u'cut', (1000.0, -600.0, 1300.0, 0.0), [])),
        ('edge', ((0.0, 250.0), (2600.0, 250.0), (2600.0, 0.0), (1300.0, 0.0), (1300.0, -600.0))),
        ('edge', ((0.0, 0.0), (1000.0, 0.0), (1000.0, -600.0))),
        ('poly', ((100.0, 210.0), (2560.0, 210.0), (2560.0, 120.0))),
        ('poly', ((550.0, 175.0), (2400.0, 175.0))),
        ('poly', ((0.0, 40.0), (2560.0, 40.0))),
        ('thin', ((1300.0, 320.0), (2600.0, 320.0))), ('text', (1700.0, 420.0, u'k')),
        ('text', (0.0, -750.0, u'Top: 100 % back the greater of 0.75 k or 0.15 l + d;')),
        ('text', (0.0, -850.0, u'60 % back the greater of 1.5 k or 0.3 l + d')),
        ('text', (0.0, -950.0, u'Bottom: at least 0.5 k into the cantilever')),
    )),
    (u'S6', u'PUNCHING SHEAR LINKS', u'SMDSC 4th ed. MD S6', (
        ('fill', (u'seen', (0.0, 0.0, 2000.0, 2000.0), [(800.0, 800.0, 1200.0, 1200.0)])),
        ('fill', (u'cut', (800.0, 800.0, 1200.0, 1200.0), [])),
        ('edge', ((800.0, 800.0), (1200.0, 800.0), (1200.0, 1200.0), (800.0, 1200.0), (800.0, 800.0))),
        ('thin', ((700.0, 700.0), (1300.0, 700.0), (1300.0, 1300.0), (700.0, 1300.0), (700.0, 700.0))),
        ('thin', ((550.0, 550.0), (1450.0, 550.0), (1450.0, 1450.0), (550.0, 1450.0), (550.0, 550.0))),
        ('thin', ((400.0, 400.0), (1600.0, 400.0), (1600.0, 1600.0), (400.0, 1600.0), (400.0, 400.0))),
        ('dots', (700.0, 700.0, 1300.0, 5)), ('dots', (700.0, 1300.0, 1300.0, 5)),
        ('dots', (550.0, 550.0, 1450.0, 7)), ('dots', (550.0, 1450.0, 1450.0, 7)),
        ('dots', (400.0, 400.0, 1600.0, 9)), ('dots', (400.0, 1600.0, 1600.0, 9)),
        ('text', (850.0, 1000.0, u'COLUMN')),
        ('text', (0.0, -150.0, u'First perimeter 0.3d to 0.5d from the column face,')),
        ('text', (0.0, -250.0, u'then at no more than 0.75d; links round each perimeter')),
        ('text', (0.0, -350.0, u'at 1.5d max. within 2d of the face, 2d max. beyond;')),
        ('text', (0.0, -450.0, u'H12 fixing bars where no main bar is present')),
    )),
    (u'ST1', u'STAIR WITH LANDINGS', u'SMDSC 4th ed. MD ST1', (
        ('fillpoly', (u'cut', ((0.0, 0.0), (800.0, 0.0), (1900.0, 1000.0), (2700.0, 1000.0), (2700.0, 1200.0),
                               (2000.0, 1200.0), (900.0, 200.0), (0.0, 200.0)))),
        ('edge', ((0.0, 0.0), (800.0, 0.0), (1900.0, 1000.0), (2700.0, 1000.0))),
        ('edge', ((0.0, 200.0), (900.0, 200.0), (2000.0, 1200.0), (2700.0, 1200.0))),
        ('poly', ((0.0, 40.0), (790.0, 40.0), (1890.0, 1040.0), (2700.0, 1040.0))),
        ('poly', ((0.0, 160.0), (1150.0, 160.0))),
        ('poly', ((1650.0, 1160.0), (2700.0, 1160.0))),
        ('text', (0.0, -150.0, u'Main bars continuous through the knees into the landings;')),
        ('text', (0.0, -250.0, u'top bars at the knees reach A, the greatest of 0.1 x span,')),
        ('text', (0.0, -350.0, u'a tension anchorage or 500; landing U-bars 50 % of the')),
        ('text', (0.0, -450.0, u'main bottom steel; distribution bars as MD S1')),
    )),
    (u'RW1', u'CANTILEVER RETAINING WALL', u'SMDSC 4th ed. MD RW1', (
        ('fill', (u'cut', (0.0, 0.0, 2400.0, 450.0), [])), ('fill', (u'cut', (900.0, 450.0, 1200.0, 600.0), [])),
        ('fill', (u'cut', (900.0, 600.0, 1200.0, 2600.0), [])),
        ('edge', ((900.0, 450.0), (0.0, 450.0), (0.0, 0.0), (2400.0, 0.0), (2400.0, 450.0), (1200.0, 450.0))),
        ('edge', ((900.0, 450.0), (900.0, 2600.0), (1200.0, 2600.0), (1200.0, 450.0))),
        ('thin', ((900.0, 600.0), (1200.0, 600.0))),
        ('poly', ((1125.0, 2540.0), (1125.0, 75.0), (2300.0, 75.0))),
        ('poly', ((975.0, 2540.0), (975.0, 75.0), (500.0, 75.0))),
        ('poly', ((100.0, 375.0), (2300.0, 375.0))),
        ('text', (1300.0, 1800.0, u'EARTH FACE: bars to design')),
        ('text', (0.0, 1800.0, u'EXPOSED FACE:')),
        ('text', (0.0, 1700.0, u'MD W1 table')),
        ('text', (1300.0, 700.0, u'KICKER 150')),
        ('text', (0.0, -150.0, u'c_nom 75 against soil, 50 on blinding, 40 to formed faces;')),
        ('text', (0.0, -250.0, u'large radius bends as the design asks')),
    )),
    (u'C4', u'COLUMN TOP DETAIL', u'SMDSC 4th ed. MD C4', (
        ('fill', (u'cut', (0.0, 1500.0, 2000.0, 1750.0), [])), ('fill', (u'cut', (750.0, 0.0, 1150.0, 1500.0), [])),
        ('edge', ((0.0, 1750.0), (2000.0, 1750.0))), ('edge', ((0.0, 1500.0), (750.0, 1500.0), (750.0, 0.0))),
        ('edge', ((2000.0, 1500.0), (1150.0, 1500.0), (1150.0, 0.0))),
        ('poly', ((800.0, 0.0), (800.0, 1690.0), (1300.0, 1690.0))),
        ('poly', ((1100.0, 0.0), (1100.0, 1690.0), (600.0, 1690.0))),
        ('poly', ((790.0, 1200.0), (1110.0, 1200.0))), ('poly', ((790.0, 1350.0), (1110.0, 1350.0))),
        ('poly', ((790.0, 1050.0), (1110.0, 1050.0))),
        ('text', (1250.0, 1250.0, u'Links at the lap: 12 dia., 0.6 x the')),
        ('text', (1250.0, 1150.0, u'lesser side or 240, 150 max., 3 min.')),
        ('text', (0.0, -150.0, u'Bars bent into the slab when it is at least 200 deep')),
        ('text', (0.0, -250.0, u'(H20), 250 (H25), 300 (H32); else Detail B of MD C4')),
    )),
    (u'B3', u'CANTILEVER BEAM', u'SMDSC 4th ed. MD B3', (
        ('fill', (u'cut', (0.0, 0.0, 3000.0, 600.0), [])), ('fill', (u'cut', (800.0, -700.0, 1200.0, 0.0), [])),
        ('edge', ((0.0, 600.0), (3000.0, 600.0), (3000.0, 0.0), (1200.0, 0.0), (1200.0, -700.0))),
        ('edge', ((0.0, 0.0), (800.0, 0.0), (800.0, -700.0))),
        ('poly', ((150.0, 545.0), (2950.0, 545.0), (2950.0, 300.0))),
        ('poly', ((450.0, 495.0), (2600.0, 495.0))),
        ('poly', ((0.0, 55.0), (2950.0, 55.0))),
        ('thin', ((1200.0, 680.0), (3000.0, 680.0))), ('text', (2000.0, 780.0, u'k')),
        ('text', (0.0, -850.0, u'Top: 100 % back the greater of 0.75 k or 0.15 l + 1.1 d;')),
        ('text', (0.0, -950.0, u'60 % back the greater of 1.5 k or 0.3 l + d;')),
        ('text', (0.0, -1050.0, u'links to the end of the cantilever')),
    )),
    (u'CB1', u'CORBEL', u'SMDSC 4th ed. MD CB1', (
        ('fillpoly', (u'cut', ((0.0, 0.0), (400.0, 0.0), (400.0, 900.0), (800.0, 1100.0), (800.0, 1400.0),
                               (400.0, 1400.0), (400.0, 2200.0), (0.0, 2200.0)))),
        ('edge', ((0.0, 0.0), (0.0, 2200.0))),
        ('edge', ((400.0, 0.0), (400.0, 900.0), (800.0, 1100.0), (800.0, 1400.0), (400.0, 1400.0),
                  (400.0, 2200.0))),
        ('poly', ((60.0, 900.0), (60.0, 1340.0), (740.0, 1340.0), (740.0, 1150.0))),
        ('poly', ((350.0, 1250.0), (700.0, 1250.0))), ('poly', ((350.0, 1170.0), (700.0, 1170.0))),
        ('poly', ((340.0, 0.0), (340.0, 2200.0))), ('poly', ((60.0, 0.0), (60.0, 2200.0))),
        ('text', (900.0, 1300.0, u'Main loop round the face,')),
        ('text', (900.0, 1200.0, u'its bend starting at the load')),
        ('text', (900.0, 1050.0, u'Horizontal links over 2/3 d')),
        ('text', (0.0, -150.0, u'a_v no more than 0.5 h; H16 max. without welds')),
        ('text', (0.0, -250.0, u'(MD CB2 with welded cross bars)')),
    )),
)


def by_key():
    return dict((key, (title, md, sketch)) for key, title, md, sketch in DETAILS)


def view_name(key, prefix=PREFIX):
    title, _md, _s = by_key()[key]
    return u'{}{} - {}'.format(prefix, key, title)


def needed(host_kinds, layers, piled=False, flags=()):
    """
    The typical details a drawing calls for (T9.21): host_kinds ('floor', 'wall', 'foundation', ...), the rebar
    layers on it and flags ('column_top': a column with none above). Keys in DETAILS order. The others (S2, S4,
    S6, RW1, B3) stay in the template's library for the detailer to place.
    """
    layers = set((l or u'').strip().lower() for l in layers)
    kinds = set(host_kinds)
    want = set()
    if 'wall' in kinds:
        want.add(u'W1')
        if u'corner_ubar' in layers:
            want.add(u'W2')
    if 'stairs' in kinds:
        want.add(u'ST1')
    if layers & set((u'corbel_compression', u'corbel')):
        want.add(u'CB1')
    if 'column' in kinds and u'column_top' in flags:
        want.add(u'C4')
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


DOT_R_MM = 10.0       # a bar cut, drawn as a filled dot at SCALE


def dot_points(d):
    """The centres of a 'dots' item (x0, y0, x1, n[, dy])."""
    x0, y0, x1, n = d[0], d[1], d[2], int(d[3])
    dy = d[4] if len(d) > 4 else 0.0
    if abs(x1 - x0) < 1e-6 and dy:
        return [(x0, y0 + k * dy) for k in range(n)]
    if n < 2:
        return [((x0 + x1) / 2.0, y0)]
    return [(x0 + k * (x1 - x0) / (n - 1), y0) for k in range(n)]


def _dot(doc, view, x, y):
    import math
    from Autodesk.Revit import DB  # Lazy import
    from System.Collections.Generic import List
    frt = None
    for t in DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType):
        pat = doc.GetElement(t.ForegroundPatternId)
        c = t.ForegroundPatternColor
        try:
            if pat is not None and pat.GetFillPattern().IsSolidFill and c.Red + c.Green + c.Blue == 0:
                frt = t
                break
        except Exception:
            continue
    c0, r = _xyz(x, y), DOT_R_MM / _FT
    if frt is None:
        doc.Create.NewDetailCurve(view, DB.Arc.Create(c0, r, 0.0, 2.0 * math.pi, DB.XYZ.BasisX, DB.XYZ.BasisY))
        return
    loop = DB.CurveLoop()
    loop.Append(DB.Arc.Create(c0, r, 0.0, math.pi, DB.XYZ.BasisX, DB.XYZ.BasisY))
    loop.Append(DB.Arc.Create(c0, r, math.pi, 2.0 * math.pi, DB.XYZ.BasisX, DB.XYZ.BasisY))
    loops = List[DB.CurveLoop]()
    loops.Add(loop)
    DB.FilledRegion.Create(doc, frt.Id, view.Id, loops)


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
              + [p[1] for kind, d in sketch if kind == 'fillpoly' for p in d[1]] + [0.0])
    invisible = [g for g in DB.FilteredElementCollector(doc).OfClass(DB.GraphicsStyle)
                 if g.Name == u'<Invisible lines>']
    if bar_style is None:
        bar_style = wide_lines(doc)

    def line(a, b, style):
        c = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(_xyz(*a), _xyz(*b)))
        if style is not None:
            c.LineStyle = style
    for kind, d in sketch:            # the concrete first, under the lines
        if kind not in ('fill', 'fillpoly'):
            continue
        frt = _fill_type(doc, d[0])
        if frt is None:
            continue
        loops = List[DB.CurveLoop]()
        if kind == 'fill':
            loops.Add(_loop(*d[1]))
            for h in d[2]:
                loops.Add(_loop(*h))
        else:
            loop = DB.CurveLoop()
            pts = list(d[1]) + [d[1][0]]
            for a, b in zip(pts, pts[1:]):
                loop.Append(DB.Line.CreateBound(_xyz(*a), _xyz(*b)))
            loops.Add(loop)
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
        elif kind == 'dots':
            for x, y in dot_points(d):
                _dot(doc, view, x, y)
        elif kind == 'text':
            x, y, text = d
            DB.TextNote.Create(doc, view.Id, _xyz(x, y), text, text_type_id)
    DB.TextNote.Create(doc, view.Id, _xyz(0.0, top + 350.0), u'TYPICAL DETAIL {} - {}'.format(key, title),
                       text_type_id)
    DB.TextNote.Create(doc, view.Id, _xyz(0.0, top + 220.0), u'After {} - confirm with design'.format(md),
                       text_type_id)
