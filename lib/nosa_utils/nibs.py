# -*- coding: utf-8 -*-
"""
Continuous nibs (IStructE SMDSC 6.9, Model Details MN1/MN2) and beam half joints (SMDSC 6.9, EC2 Annex J)
laid out in the beam's own section frame, no Revit: x along the beam from the end of its geometry, y
across it from the centre (+ towards the nib), z up from the soffit; mm.
"""
import math

MIN_NIB_DEPTH_MM = 140.0          # MN2
MAX_LINK_DIA_MM = 12.0            # MN1
MAX_UBAR_DIA_MM = 16.0            # MN2
MAX_UBAR_PITCH_MM = 250.0         # MN2
NIB_OVERLAP_MM = 60.0             # MN1: nib steel against the supported member's steel
HANGER_LINKS = 4                  # half joint: hanger links next to the re-entrant corner ...
HANGER_PITCH_MM = 75.0            # ... at this pitch
STEP_MM = 25.0


def _floor_step(x, step=STEP_MM):
    return step * math.floor(x / step + 1e-9)


def mandrel_mm(dia_mm):
    """BS 8666 / SMDSC Table B1 mandrel: 4 d up to 16, 7 d above."""
    return (4.0 if dia_mm <= 16.0 else 7.0) * dia_mm


def nib_mode(nib_depth_mm, cover_mm, link_dia_mm):
    """
    ('MN1' | 'MN2', notes): closed links (MN1) where the nib leaves room for two bends of the link inside
    its covers, horizontal U-bars (MN2) where it is shallower.
    """
    notes = []
    if nib_depth_mm < MIN_NIB_DEPTH_MM:
        notes.append(u'nib {:.0f} mm deep: SMDSC MN2 asks for at least 140.'.format(nib_depth_mm))
    inside = nib_depth_mm - 2.0 * cover_mm - link_dia_mm
    mode = 'MN1' if inside >= 2.0 * mandrel_mm(link_dia_mm) else 'MN2'
    return mode, notes


def nib_pitch_mm(nib_depth_mm, concentrated=False):
    """Pitch of the nib's main bars (SMDSC 6.9.2): 3h <= 400, or 2h <= 250 under concentrated loads."""
    return _floor_step(min(2.0 * nib_depth_mm, 250.0) if concentrated else min(3.0 * nib_depth_mm, 400.0))


def secondary_pitch_mm(nib_depth_mm, concentrated=False):
    """Pitch of the nib's secondary bars: 3.5h <= 450, or 3h <= 400 under concentrated loads."""
    return _floor_step(min(3.0 * nib_depth_mm, 400.0) if concentrated else min(3.5 * nib_depth_mm, 450.0))


def positions_mm(lo, hi, pitch):
    """Even positions from lo to hi at no more than pitch."""
    if hi - lo < 1.0:
        return [(lo + hi) / 2.0]
    n = int(math.ceil((hi - lo) / pitch - 1e-9)) + 1
    return [lo + (hi - lo) * k / (n - 1) for k in range(n)]


def mn1_link(b_mm, projection_mm, nib_depth_mm, cover_mm, link_dia_mm):
    """MN1 closed link in the section, [(y, z)] corners: across web and nib, the nib's depth."""
    c = cover_mm + link_dia_mm / 2.0
    y0, y1 = -b_mm / 2.0 + c, b_mm / 2.0 + projection_mm - c
    z0, z1 = c, nib_depth_mm - c
    return [(y0, z0), (y1, z0), (y1, z1), (y0, z1)]


def nib_bar_positions(b_mm, projection_mm, nib_depth_mm, cover_mm, link_dia_mm, bar_dia_mm):
    """(y, z) of the nib's longitudinal bars inside its MN1 links: the outer corners, more across a wide nib."""
    c = cover_mm + link_dia_mm + bar_dia_mm / 2.0
    y_out = b_mm / 2.0 + projection_mm - c
    y_in = b_mm / 2.0 + c
    pitch = secondary_pitch_mm(nib_depth_mm)
    ys = positions_mm(y_in, y_out, pitch) if y_out - y_in > pitch else [y_out]
    return [(y, z) for y in ys for z in (c, nib_depth_mm - c)]


def u_gap_mm(dia_mm):
    """Centre-to-centre gap of a U-bar's legs: the mandrel and a straight between the two bends."""
    return max(mandrel_mm(dia_mm) + 3.0 * dia_mm, 60.0)


def mn2_ubar(b_mm, projection_mm, nib_depth_mm, cover_mm, dia_mm, anchorage_mm, x_mm):
    """
    MN2 horizontal U-bar at x: the loop at the nib face, both legs into the beam a tension anchorage past
    the nib's inner face (no further than the far side cover). ([(x, y, z)], short_by_mm).
    """
    gap = u_gap_mm(dia_mm)
    z = nib_depth_mm / 2.0
    y_out = b_mm / 2.0 + projection_mm - cover_mm - dia_mm / 2.0
    want = b_mm / 2.0 - anchorage_mm
    y_in = max(want, -b_mm / 2.0 + cover_mm + dia_mm / 2.0)
    x = x_mm
    pts = [(x - gap / 2.0, y_in, z), (x - gap / 2.0, y_out, z), (x + gap / 2.0, y_out, z), (x + gap / 2.0, y_in, z)]
    return pts, max(y_in - want, 0.0)


def mn2_lacer(b_mm, projection_mm, nib_depth_mm, cover_mm, dia_mm):
    """(y, z) of the MN2 lacer bar, inside the U loops at the nib face."""
    gap = u_gap_mm(dia_mm)
    return (b_mm / 2.0 + projection_mm - cover_mm - dia_mm - gap / 2.0, nib_depth_mm / 2.0)


def half_joint(length_mm, notch_mm, h_mm, b_mm, cover_mm, link_dia_mm, ubar_dia_mm, anchorage_mm):
    """
    Half joint at the start of a beam (the end mirrors it): notch length_mm long and notch_mm high from
    the soffit, the nib above it. Returns {'hangers': [x], 'ubars': [[(x, y, z)]], 'nib_links': [x],
    'nib_link': [(y, z)] corners, 'bottom_stop_mm': where the full-depth bottom bars end, 'notes'}.
    """
    notes = []
    nib_h = h_mm - notch_mm
    face = length_mm                                    # the re-entrant face, from the beam's end
    c = cover_mm + link_dia_mm / 2.0
    hangers = [face + c + k * HANGER_PITCH_MM for k in range(HANGER_LINKS)]
    # horizontal U-bars low in the nib: the loop round the nib end, the legs anchored past the hangers
    z = notch_mm + cover_mm + link_dia_mm + ubar_dia_mm / 2.0
    y = b_mm / 2.0 - cover_mm - link_dia_mm - ubar_dia_mm / 2.0
    x_end = cover_mm + ubar_dia_mm / 2.0
    x_in = hangers[-1] + anchorage_mm
    ubars = []
    for k in range(2):
        zk = z + k * max(2.0 * ubar_dia_mm, ubar_dia_mm + 25.0)
        if zk > h_mm - cover_mm - link_dia_mm - ubar_dia_mm / 2.0:
            break
        ubars.append([(x_in, -y, zk), (x_end, -y, zk), (x_end, y, zk), (x_in, y, zk)])
    if ubar_dia_mm > MAX_UBAR_DIA_MM:
        notes.append(u'half joint U-bars H{:.0f}: SMDSC 6.9 prefers 16 or less (larger ones are usually welded, '
                     u'MCB2).'.format(ubar_dia_mm))
    nib_links = positions_mm(cover_mm + link_dia_mm / 2.0 + 25.0, face - c, 100.0) if face - 2.0 * c > 25.0 else []
    nib_link = [(-b_mm / 2.0 + c, notch_mm + c), (b_mm / 2.0 - c, notch_mm + c),
                (b_mm / 2.0 - c, h_mm - c), (-b_mm / 2.0 + c, h_mm - c)]
    if nib_h < 2.0 * mandrel_mm(link_dia_mm) + 2.0 * cover_mm:
        notes.append(u'half joint nib only {:.0f} mm deep: no room for closed links in it.'.format(nib_h))
        nib_links = []
    notes.append(u'half joint: {} hanger links at {:.0f} next to the re-entrant corner, {} horizontal U-bar(s) '
                 u'H{:.0f} anchored {:.0f} past them; the designer must confirm the areas (EC2 Annex J, SMDSC '
                 u'6.9).'.format(HANGER_LINKS, HANGER_PITCH_MM, len(ubars), ubar_dia_mm, anchorage_mm))
    return {'hangers': hangers, 'ubars': ubars, 'nib_links': nib_links, 'nib_link': nib_link,
            'bottom_stop_mm': face + cover_mm, 'notes': notes}
