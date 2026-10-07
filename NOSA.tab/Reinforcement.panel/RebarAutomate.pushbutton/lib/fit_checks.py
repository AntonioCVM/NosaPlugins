# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — T8.47 fitting checks for every element type (IStructE SMDSC 5.2/5.3).

Meshes (slabs, foundations, walls) from the tab's own values; beams and columns per member from
its section. The rules themselves live in nosa_utils.fit; this only knows the tabs' value names.
Pure Python: no Revit API.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import math

from nosa_utils import fit


def _unique(notes):
    out = []
    for n in notes:
        if n not in out:
            out.append(n)
    return out


def mesh_notes(mode, values):
    """Clear gap and pitch of every mesh direction the tab is about to lay."""
    v = values or {}
    pairs = []
    if mode == 'walls':
        pairs = [(u'Wall verticals', v.get('vert_dia'), v.get('vert_spacing')),
                 (u'Wall horizontals', v.get('horiz_dia'), v.get('horiz_spacing'))]
    elif mode == 'footings_floors':
        pairs = [(u'Bottom mat X', v.get('dia_x'), v.get('spacing')),
                 (u'Bottom mat Y', v.get('dia_y'), v.get('spacing'))]
        if v.get('include_top_mat'):
            pairs += [(u'Top mat X', v.get('top_dia_x'), v.get('top_spacing')),
                      (u'Top mat Y', v.get('top_dia_y'), v.get('top_spacing'))]
    notes = []
    for label, dia, spacing in pairs:
        if dia and spacing:
            notes.extend(fit.mesh_spacing_notes(float(spacing), float(dia), label=label))
    return _unique(notes)


def beam_notes(width_mm, cover_mm, link_dia_mm, bar_dia_mm, n_top, n_bottom, label=u'Beam'):
    """Top and bottom layers of a beam inside its links."""
    notes = []
    for name, n in ((u'top', n_top), (u'bottom', n_bottom)):
        notes.extend(fit.layer_notes(width_mm, cover_mm, link_dia_mm, int(n or 0), bar_dia_mm,
                                     label=u'{} {}'.format(label, name)))
    return notes


def column_notes(geometry, cover_mm, link_dia_mm, bar_dia_mm, bar_count, per_face, label=u'Column'):
    """
    The bars of a column inside its links: per face for a rectangle (per_face: (n_u, n_v) bars on
    the width and depth faces, corners included), round the perimeter for a circle.
    """
    if not geometry:
        return []
    cover_mm, link_dia_mm, bar_dia_mm = float(cover_mm), float(link_dia_mm), float(bar_dia_mm)
    if geometry.get('shape') == 'circle':
        inside = geometry['diameter_mm'] - 2.0 * (cover_mm + fit.actual_size_mm(link_dia_mm))
        ring = math.pi * max(inside - fit.actual_size_mm(bar_dia_mm), 0.0)
        need = bar_count * (fit.actual_size_mm(bar_dia_mm) + fit.min_clear_mm(bar_dia_mm))
        if ring + 1e-6 < need:
            return [u'{}: {}H{:.0f} do not fit round a {:.0f} mm column inside its links (SMDSC 5.2/5.3).'
                    .format(label, bar_count, bar_dia_mm, geometry['diameter_mm'])]
        return []
    n_u, n_v = per_face
    notes = fit.layer_notes(geometry['width_mm'], cover_mm, link_dia_mm, n_u, bar_dia_mm,
                            label=u'{} face'.format(label))
    notes += fit.layer_notes(geometry['depth_mm'], cover_mm, link_dia_mm, n_v, bar_dia_mm,
                             label=u'{} face'.format(label))
    return _unique(notes)
