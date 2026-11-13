# -*- coding: utf-8 -*-
"""
Preview drawings as lists of simple shapes in real millimetres (x right,
y up), drawn by ui.RebarAutomateWindow._draw_shapes. Pure Python — no
Revit, no WPF — so it runs under the plain test runner.

Each shape is a dict with a 'kind':
    'concrete'  x0, y0, x1, y1                 element outline (orange)
    'outline'   points [(x, y), ...]           element outline as a polygon (orange)
    'ground'    x0, y0, x1, y1                 foundation / supporting concrete (grey)
    'bar'       points [(x, y), ...], dia_mm, role    reinforcement centreline
    'dot'       x, y, dia_mm, role, hollow     bar seen end-on
    'text'      x, y, text, anchor ('l' | 'r' | 'c')
    'level'     y, x0, x1, text                dashed reference line
Roles: 'main', 'link', 'ubar', 'starter', 'dowel', 'ghost'.

Detailing follows the IStructE Standard Method of Detailing Structural
Concrete and EC2 as applied by the generators (T2.19, 2026-09-30):
starters and dowels are L bars with the foot outwards (min 450 mm) and
lap above a kicker; slab edge U-bars have legs of at least 2h.
"""
import math

MIN_STARTER_FOOT_MM = 450.0


def _bar(points, dia, role='main'):
    return {'kind': 'bar', 'points': list(points), 'dia_mm': dia, 'role': role}


def _dot(x, y, dia, role='main', hollow=False):
    return {'kind': 'dot', 'x': x, 'y': y, 'dia_mm': dia, 'role': role, 'hollow': hollow}


def _text(x, y, text, anchor='l'):
    return {'kind': 'text', 'x': x, 'y': y, 'text': text, 'anchor': anchor}


def _spaced(lo, hi, spacing):
    """Evenly spaced positions from lo to hi, no gap wider than spacing."""
    if hi <= lo or spacing <= 0:
        return [(lo + hi) / 2.0]
    n = int(math.ceil((hi - lo) / spacing)) + 1
    step = (hi - lo) / float(n - 1)
    return [lo + i * step for i in range(n)]


def _foot_mm(dia):
    return max(MIN_STARTER_FOOT_MM, 12.0 * dia)


def mat_section_shapes(width_mm, thickness_mm, cover_mm, dia_x, dia_y, spacing_mm,
                       include_top=False, top_cover_mm=None, top_dia_x=None, top_dia_y=None,
                       top_spacing_mm=None, ubars=False, ubar_dia=None, is_floor=False,
                       bottom_hooks=False, top_hooks=False, dowels=False, dowel_dia=None,
                       dowel_splice_mm=600.0, kicker_mm=75.0, column_width_mm=400.0,
                       side=False, side_dia=None, side_spacing_mm=None):
    """Section through a footing or slab, cut along X: X bars in plane, Y bars end-on."""
    w, t, c = float(width_mm), float(thickness_mm), float(cover_mm)
    half = w / 2.0
    shapes = [{'kind': 'concrete', 'x0': -half, 'y0': 0.0, 'x1': half, 'y1': t}]
    b1 = c + dia_x / 2.0
    b2 = c + dia_x + dia_y / 2.0
    x_lo, x_hi = -half + c + dia_x / 2.0, half - c - dia_x / 2.0
    bottom = [(x_lo, b1), (x_hi, b1)]
    if bottom_hooks:
        leg_top = t - (top_cover_mm or c)
        bottom = [(x_lo, leg_top)] + bottom + [(x_hi, leg_top)]
    shapes.append(_bar(bottom, dia_x))
    for x in _spaced(-half + c + dia_y / 2.0, half - c - dia_y / 2.0, spacing_mm):
        shapes.append(_dot(x, b2, dia_y))
    labels = [(b1, u'B1  H{:g} @ {:g}'.format(dia_x, spacing_mm)),
              (b2, u'B2  H{:g} @ {:g}'.format(dia_y, spacing_mm))]
    t1 = t2 = None
    if include_top and top_cover_mm and top_dia_x and top_dia_y:
        tc = float(top_cover_mm)
        t1 = t - tc - top_dia_x / 2.0
        t2 = t - tc - top_dia_x - top_dia_y / 2.0
        top = [(x_lo, t1), (x_hi, t1)]
        if top_hooks:
            top = [(x_lo, c)] + top + [(x_hi, c)]
        shapes.append(_bar(top, top_dia_x))
        for x in _spaced(-half + c + top_dia_y / 2.0, half - c - top_dia_y / 2.0,
                         top_spacing_mm or spacing_mm):
            shapes.append(_dot(x, t2, top_dia_y))
        labels += [(t1, u'T1  H{:g} @ {:g}'.format(top_dia_x, top_spacing_mm or spacing_mm)),
                   (t2, u'T2  H{:g} @ {:g}'.format(top_dia_y, top_spacing_mm or spacing_mm))]
        if ubars and ubar_dia:
            leg = 40.0 * ubar_dia
            if is_floor:
                leg = max(leg, 2.0 * t)
            leg = min(leg, w / 2.0 - c)
            back = half - c - ubar_dia / 2.0
            for edge in (-1.0, 1.0):   # not 'side': that name is the side-bar flag
                xb = edge * back
                xl = xb - edge * leg
                # legs drawn just inside their mat bar: in reality they lie beside it
                lap = (dia_x + ubar_dia) / 2.0
                shapes.append(_bar([(xl, t1 - lap), (xb, t1 - lap), (xb, b1 + lap), (xl, b1 + lap)],
                                   ubar_dia, 'ubar'))
            labels.append((t / 2.0, u'U-bars H{:g} @ {:g}, leg {:.0f}{}'.format(
                ubar_dia, spacing_mm, leg, u' (2h)' if is_floor and leg >= 2.0 * t - 1 else u'')))
    if side and side_dia and side_spacing_mm and not is_floor:
        # footing_rebar.build_side_rebar_set: a closed perimeter loop inset cover + d/2, repeated
        # upwards between the mats — its side legs cut end-on, the X leg in plane
        x_side = half - c - side_dia / 2.0
        bottom_limit = c + dia_x + dia_y + side_dia / 2.0
        if t1 is not None:
            top_limit = t - float(top_cover_mm) - top_dia_x - top_dia_y - side_dia / 2.0
        else:
            top_limit = t - c - side_dia / 2.0
        levels = _spaced(bottom_limit, top_limit, float(side_spacing_mm))
        for y in levels:
            shapes.append(_bar([(-x_side, y), (x_side, y)], side_dia, 'link'))
            for sign in (-1.0, 1.0):
                shapes.append(_dot(sign * x_side, y, side_dia, 'link'))
        labels.append(((bottom_limit + top_limit) / 2.0, u'Side bars H{:g} @ {:g} ({} levels)'.format(
            side_dia, side_spacing_mm, len(levels))))
    if dowels and dowel_dia:
        mat_top = c + dia_x + dia_y
        lap_top = t + kicker_mm + dowel_splice_mm
        col_half = column_width_mm / 2.0
        shapes.append({'kind': 'ghost_column', 'x0': -col_half, 'y0': t + kicker_mm,
                       'x1': col_half, 'y1': lap_top + 200.0})
        if kicker_mm > 0:
            shapes.append({'kind': 'concrete', 'x0': -col_half, 'y0': t, 'x1': col_half,
                           'y1': t + kicker_mm})
        x_bar = col_half - c - 10.0 - dowel_dia / 2.0
        foot = _foot_mm(dowel_dia)
        for sign in (1.0, -1.0):
            x = sign * (x_bar - dowel_dia)
            corner_y = mat_top + dowel_dia / 2.0
            tip = sign * min(abs(x) + foot, half - c)
            shapes.append(_bar([(tip, corner_y), (x, corner_y), (x, lap_top)], dowel_dia, 'dowel'))
        labels.append((lap_top, u'Dowels H{:g}, lap {:g} above {:g} kicker'.format(
            dowel_dia, dowel_splice_mm, kicker_mm)))
    for y, text in labels:
        shapes.append(_text(half + 60.0, y, text))
    shapes.append(_text(-half, -60.0, u'cover {:g}'.format(c)))
    return shapes


def column_section_shapes(width_mm, depth_mm, cover_mm, bar_dia, positions, link_dia,
                          shape='rect', starters=False, starter_dia=None, link_spacing=None,
                          crossties=None):
    """Plan section of a column: verticals (positions from the generator's layout), link, starters lapped inside."""
    c = float(cover_mm)
    shapes = []
    if shape == 'circle':
        d = float(width_mm)
        n = 36
        shapes.append({'kind': 'circle', 'x': 0.0, 'y': 0.0, 'r': d / 2.0})
        r_link = d / 2.0 - c - link_dia / 2.0
        shapes.append(_bar([(r_link * math.cos(2 * math.pi * i / n), r_link * math.sin(2 * math.pi * i / n))
                            for i in range(n + 1)], link_dia, 'link'))
        depth_mm = width_mm
    else:
        hw, hd = width_mm / 2.0, depth_mm / 2.0
        shapes.append({'kind': 'concrete', 'x0': -hw, 'y0': -hd, 'x1': hw, 'y1': hd})
        lw, ld = hw - c - link_dia / 2.0, hd - c - link_dia / 2.0
        shapes.append(_bar([(-lw, -ld), (lw, -ld), (lw, ld), (-lw, ld), (-lw, -ld)], link_dia, 'link'))
    for x1, y1, x2, y2 in crossties or []:
        shapes.append(_bar([(x1, y1), (x2, y2)], link_dia, 'link'))
    max_x = max(abs(x) for x, _ in positions) if positions else 0.0
    max_y = max(abs(y) for _, y in positions) if positions else 0.0
    for x, y in positions:
        shapes.append(_dot(x, y, bar_dia))
        if starters and starter_dia:
            length = math.hypot(x, y) or 1.0
            if shape == 'circle':
                ix, iy = -x / length, -y / length
            else:
                ix = (-1.0 if x > 0 else 1.0) if abs(abs(x) - max_x) < 1.0 else 0.0
                iy = (-1.0 if y > 0 else 1.0) if abs(abs(y) - max_y) < 1.0 else 0.0
                norm = math.hypot(ix, iy) or 1.0
                ix, iy = ix / norm, iy / norm
            off = (bar_dia + starter_dia) / 2.0
            shapes.append(_dot(x + ix * off, y + iy * off, starter_dia, 'starter', hollow=True))
    right = (width_mm if shape == 'circle' else width_mm) / 2.0 + 60.0
    label = u'{} H{:g}   links H{:g}{}'.format(len(positions), bar_dia, link_dia,
                                              u' @ {:g}'.format(link_spacing) if link_spacing else u'')
    shapes.append(_text(right, depth_mm / 2.0 - 20.0, label))
    shapes.append(_text(right, depth_mm / 2.0 - 90.0, u'cover {:g}{}'.format(
        c, u'   + crossties' if crossties else u'')))
    if starters and starter_dia:
        shapes.append(_text(right, depth_mm / 2.0 - 160.0,
                            u'o  starters/dowels H{:g}, lapped inside'.format(starter_dia)))
    return shapes


def column_elevation_shapes(width_mm, height_mm, cover_mm, bar_dia, link_dia, normal_spacing,
                            dense_spacing=None, dense_zone_mm=None, top_starters=False,
                            top_lap_mm=None, foundation_starters=False, starter_dia=None,
                            starter_splice_mm=600.0, kicker_mm=75.0, foundation_depth_mm=600.0,
                            floor_levels_mm=None):
    """Elevation of a column on its foundation: L starters (feet out), kicker, links, laps."""
    w, h, c = float(width_mm), float(height_mm), float(cover_mm)
    half = w / 2.0
    fd = float(foundation_depth_mm)
    fw = max(3.0 * w, w + 2.0 * _foot_mm(starter_dia or bar_dia) + 400.0)
    shapes = [{'kind': 'ground', 'x0': -fw / 2.0, 'y0': -fd, 'x1': fw / 2.0, 'y1': 0.0}]
    if kicker_mm > 0:
        shapes.append({'kind': 'concrete', 'x0': -half, 'y0': 0.0, 'x1': half, 'y1': kicker_mm})
    shapes.append({'kind': 'concrete', 'x0': -half, 'y0': kicker_mm, 'x1': half, 'y1': h})
    x_bar = half - c - link_dia - bar_dia / 2.0
    top = h + (top_lap_mm if top_starters and top_lap_mm else 0.0)
    for x in (-x_bar, x_bar):
        shapes.append(_bar([(x, kicker_mm + c), (x, top)], bar_dia))
    zone = dense_zone_mm or 0.0
    positions = []
    y = kicker_mm + 50.0
    while y < h - 50.0:
        positions.append(y)
        in_dense = dense_spacing and (y < kicker_mm + zone or y > h - zone)
        y += dense_spacing if in_dense else normal_spacing
    lx = half - c - link_dia / 2.0
    for y in positions:
        shapes.append(_bar([(-lx, y), (lx, y)], link_dia, 'link'))
    for level in floor_levels_mm or []:
        shapes.append({'kind': 'level', 'y': level, 'x0': -half - 150.0, 'x1': half + 150.0,
                       'text': u'floor'})
    if foundation_starters:
        sd = starter_dia or bar_dia
        mat_top = -fd + c + 2.0 * 16.0
        lap_top = kicker_mm + starter_splice_mm
        xs = x_bar - (bar_dia + sd) / 2.0
        for sign in (-1.0, 1.0):
            x = sign * xs
            tip = sign * (xs + _foot_mm(sd))
            shapes.append(_bar([(tip, mat_top + sd / 2.0), (x, mat_top + sd / 2.0), (x, lap_top)], sd, 'starter'))
        shapes.append(_text(fw / 2.0 + 60.0, lap_top,
                            u'Starters H{:g}, foot {:.0f} out, lap {:g} + kicker {:g}'.format(
                                sd, _foot_mm(sd), starter_splice_mm, kicker_mm)))
    shapes.append(_text(fw / 2.0 + 60.0, h * 0.6, u'Links H{:g} @ {:g}{}'.format(
        link_dia, normal_spacing, u' ({:g} at ends)'.format(dense_spacing) if dense_spacing else u'')))
    if top_starters and top_lap_mm:
        shapes.append(_text(fw / 2.0 + 60.0, top, u'Lap into storey above {:g}'.format(top_lap_mm)))
    shapes.append({'kind': 'level', 'y': 0.0, 'x0': -fw / 2.0, 'x1': fw / 2.0, 'text': u'foundation top'})
    return shapes


def beam_interior_ties(width_mm, height_mm, cover_mm, bar_dia, n_top, n_bottom, link_dia):
    """Interior links / crossties of a beam section, relative to its centre (column rule)."""
    from rebar_preview import _crosstie_lines_preview
    n_u = max(int(n_top or 0), int(n_bottom or 0))
    if n_u <= 2:
        return []
    bend_r = 2.0 * link_dia
    extra = 0.0 if bend_r <= bar_dia / 2.0 else bend_r - (bend_r - bar_dia / 2.0) / math.sqrt(2.0) - bar_dia / 2.0
    inset = cover_mm + link_dia + bar_dia / 2.0 + extra
    return _crosstie_lines_preview(width_mm / 2.0 - inset, height_mm / 2.0 - inset, n_u, 2, 'all',
                                   bar_dia, link_dia)


def beam_section_shapes(width_mm, height_mm, cover_mm, bar_dia, n_top, n_bottom, link_dia,
                        link_spacing=None, ties=None):
    """Cross-section of a beam: link, top and bottom rows seated in its corners (+ interior ties)."""
    w, h, c = float(width_mm), float(height_mm), float(cover_mm)
    hw = w / 2.0
    shapes = [{'kind': 'concrete', 'x0': -hw, 'y0': 0.0, 'x1': hw, 'y1': h}]
    lw = hw - c - link_dia / 2.0
    shapes.append(_bar([(-lw, c + link_dia / 2.0), (lw, c + link_dia / 2.0), (lw, h - c - link_dia / 2.0),
                        (-lw, h - c - link_dia / 2.0), (-lw, c + link_dia / 2.0)], link_dia, 'link'))
    for x1, y1, x2, y2 in ties or []:
        shapes.append(_bar([(x1, y1 + h / 2.0), (x2, y2 + h / 2.0)], link_dia, 'link'))
    bend_r = 2.0 * link_dia
    extra = 0.0 if bend_r <= bar_dia / 2.0 else bend_r - (bend_r - bar_dia / 2.0) / math.sqrt(2.0) - bar_dia / 2.0
    inset = c + link_dia + bar_dia / 2.0 + extra
    for n, y in ((n_top, h - inset), (n_bottom, inset)):
        n = max(1, int(n))
        xs = [0.0] if n == 1 else _spaced(-hw + inset, hw - inset, (w - 2 * inset) / (n - 1))
        for x in xs:
            shapes.append(_dot(x, y, bar_dia))
    shapes.append(_text(hw + 60.0, h - inset, u'Top {} H{:g}'.format(int(n_top), bar_dia)))
    shapes.append(_text(hw + 60.0, inset, u'Bottom {} H{:g}'.format(int(n_bottom), bar_dia)))
    shapes.append(_text(hw + 60.0, h / 2.0, u'Links H{:g}{}   cover {:g}'.format(
        link_dia, u' @ {:g}'.format(link_spacing) if link_spacing else u'', c)))
    return shapes


def wall_section_shapes(thickness_mm, height_mm, cover_mm, vert_dia, vert_spacing, horiz_dia,
                        horiz_spacing, both_faces=True, vert_outer=True, top_ubar=False,
                        straight_extension=False, extension_mm=None, foundation_starters=False,
                        starter_dia=None, starter_splice_mm=600.0, kicker_mm=75.0,
                        footing_width_mm=None, footing_depth_mm=400.0):
    """Vertical cut through a wall on its strip footing."""
    t, h, c = float(thickness_mm), float(height_mm), float(cover_mm)
    ht = t / 2.0
    fw = float(footing_width_mm or max(3.0 * t, t + 2.0 * _foot_mm(starter_dia or vert_dia)))
    fd = float(footing_depth_mm)
    shapes = [{'kind': 'ground', 'x0': -fw / 2.0, 'y0': -fd, 'x1': fw / 2.0, 'y1': 0.0}]
    if kicker_mm > 0:
        shapes.append({'kind': 'concrete', 'x0': -ht, 'y0': 0.0, 'x1': ht, 'y1': kicker_mm})
    shapes.append({'kind': 'concrete', 'x0': -ht, 'y0': kicker_mm, 'x1': ht, 'y1': h})
    if vert_outer:
        xv = ht - c - vert_dia / 2.0
        xh = ht - c - vert_dia - horiz_dia / 2.0
    else:
        xh = ht - c - horiz_dia / 2.0
        xv = ht - c - horiz_dia - vert_dia / 2.0
    faces = (-1.0, 1.0) if both_faces else (1.0,)
    bottom = -fd + c if straight_extension else kicker_mm + c
    for s in faces:
        shapes.append(_bar([(s * xv, bottom), (s * xv, h - c)], vert_dia))
        for y in _spaced(kicker_mm + 50.0, h - c - horiz_dia, horiz_spacing):
            shapes.append(_dot(s * xh, y, horiz_dia))
    if top_ubar and both_faces:
        shapes.append(_bar([(-xv, h - c - 400.0), (-xv, h - c), (xv, h - c), (xv, h - c - 400.0)],
                           vert_dia, 'ubar'))
    if foundation_starters and not straight_extension:
        sd = starter_dia or vert_dia
        mat_top = -fd + c + 32.0
        lap_top = kicker_mm + starter_splice_mm
        xs = xv - (vert_dia + sd) / 2.0
        for s in faces:
            tip = s * min(xs + _foot_mm(sd), fw / 2.0 - c)
            shapes.append(_bar([(tip, mat_top + sd / 2.0), (s * xs, mat_top + sd / 2.0),
                                (s * xs, lap_top)], sd, 'starter'))
        shapes.append(_text(fw / 2.0 + 40.0, lap_top, u'Starters H{:g}: foot out, lap {:g}'.format(
            sd, starter_splice_mm)))
        shapes.append(_text(fw / 2.0 + 40.0, lap_top - 150.0, u'above {:g} kicker'.format(kicker_mm)))
    shapes.append(_text(fw / 2.0 + 40.0, h * 0.8, u'V H{:g} @ {:g}{}'.format(
        vert_dia, vert_spacing, u' EF' if both_faces else u'')))
    shapes.append(_text(fw / 2.0 + 40.0, h * 0.8 - 150.0, u'H H{:g} @ {:g}'.format(horiz_dia, horiz_spacing)))
    shapes.append(_text(fw / 2.0 + 40.0, h * 0.8 - 300.0, u'cover {:g}'.format(c)))
    if straight_extension:
        shapes.append(_text(fw / 2.0 + 40.0, -fd / 2.0, u'Verticals down to foundation bottom'))
    return shapes


def typical_stair_flight():
    """A 10-riser 176.5 / 280 flight on a floor, 150 mm landing at the top (Revit 'Concrete Stair')."""
    return {'length': 2520.0, 'slope': 176.5 / 280.0, 'soffit_z0': -193.0, 'pitch_z0': 0.0,
            'v_min': -500.0, 'v_max': 500.0, 'risers': 10, 'riser': 176.5, 'tread': 280.0,
            'lower': {'kind': 'floor', 'top': 0.0, 'bottom': 0.0, 's_far': 0.0},
            'upper': {'kind': 'landing', 'top': 1765.0, 'bottom': 1615.0, 's_far': 3520.0}}


def stair_section_shapes(run, cover, main_dia, main_spacing, top_dia, top_spacing, dist_dia,
                         dist_spacing, anchorage, slab_anchor=True, ubar_dia=None, starter_dia=None,
                         starter_mode='cast', starter_lap=600.0, support_depth=500.0, a_mm=None):
    """Longitudinal section of one flight (stair_rebar geometry): bars in plane, distribution end-on."""
    import copy
    import stair_rebar
    run = copy.deepcopy(run)
    shapes = [{'kind': 'outline', 'points': stair_rebar.section_profile(run)}]
    if ubar_dia and run['upper']['kind'] == 'landing':
        run['upper']['u_dia'] = ubar_dia
        up = run['upper']
        landing = {'s_min': run['length'], 's_max': up['s_far'], 'v_min': run['v_min'],
                   'v_max': run['v_max'], 'top': up['top'], 'bottom': up['bottom']}
        for st in stair_rebar.build_landing(landing, cover, main_dia, dist_dia, dist_spacing,
                                            main_spacing, [(run['v_min'], run['v_max'])], True,
                                            u_dia=ubar_dia, u_edges=('s_max',)):
            if st['layer'] == u'stair_landing_ubar':
                shapes.append(_bar(st['points'], ubar_dia, 'ubar'))
    starters = None
    if starter_dia and run['lower']['kind'] == 'floor':
        base = run['lower']['bottom']
        if starter_mode == 'cast':
            support = {'mode': 'cast', 'foot_z': base - support_depth + cover + 2.0 * main_dia + starter_dia / 2.0}
            depth = support_depth
        else:
            support = {'mode': 'post', 'embed': max(anchorage, 10.0 * starter_dia)}
            depth = support['embed'] + 150.0
        starters = {'dia': starter_dia, 'lap': starter_lap, 'support': support}
        shapes.append({'kind': 'ground', 'x0': -400.0, 'y0': base - depth, 'x1': 900.0, 'y1': base})
    sets = stair_rebar.build_flight(run, cover, main_dia, main_spacing, dist_dia, dist_spacing,
                                    anchorage, top_dia=top_dia, top_spacing=top_spacing,
                                    slab_anchor=slab_anchor, starters=starters, a_mm=a_mm)
    labels = []
    for st in sets:
        if st['axis'] == 'v':
            pts = st['points']
            role = {'stair_knee': 'ubar', 'stair_starter': 'starter'}.get(st['layer'], 'main')
            shapes.append(_bar(pts, st['dia'], role))
        else:
            (s0, z0), = st['points']
            ds, dz = st['direction']
            for d in _spaced(0.0, st['array'], st['spacing']):
                shapes.append(_dot(s0 + ds * d, z0 + dz * d, st['dia'], 'link'))
    top_z = run['upper']['top']
    labels.append((top_z, u'T  H{:g} @ {:g} (top, over the upper knee)'.format(top_dia, top_spacing)))
    labels.append((top_z - 400.0, u'B  H{:g} @ {:g} (bottom, crossed at the upper knee)'.format(
        main_dia, main_spacing)))
    labels.append((top_z - 800.0, u'Knee bars (brown) anchored across re-entrant corners'))
    labels.append((top_z - 1200.0, u'Distribution H{:g} @ {:g}, both faces'.format(dist_dia, dist_spacing)))
    x_max = max(p[0] for p in shapes[0]['points'])
    for y, text in labels:
        shapes.append(_text(x_max, y, text))
    return shapes
