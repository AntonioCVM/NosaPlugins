# -*- coding: utf-8 -*-
"""
nosa_utils.fit — will the bars fit? IStructE SMDSC 5.2-5.3 (BS 8666), for every concrete element.

Bars are checked at their actual size (+10 %, SMDSC 5.3 examples), clear gaps at least
max(phi, dg + 5, 20) (SMDSC 5.2 / EC2 8.2), and links between two concrete faces lose the
"closed" detailing deduction of SMDSC Table 5.5. Pure Python: no Revit API.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

ACTUAL_SIZE_FACTOR = 1.10        # deformations: an H16 may measure 18 mm
DEFAULT_AGGREGATE_MM = 20.0
MIN_PITCH_MM = 75.0              # SMDSC 6.2 (slabs): recommended minimum pitch of bars
MIN_PITCH_AT_LAPS_MM = 100.0


def actual_size_mm(bar_dia_mm):
    return ACTUAL_SIZE_FACTOR * bar_dia_mm


def min_clear_mm(bar_dia_mm, aggregate_mm=DEFAULT_AGGREGATE_MM):
    """Minimum clear distance between bars: max(phi, dg + 5, 20)."""
    return max(bar_dia_mm, aggregate_mm + 5.0, 20.0)


def closed_deduction_mm(distance_between_faces_mm, bent=True):
    """SMDSC Table 5.5: links and bent bars 10 / 15 / 20 mm up to 1 / 2 / over 2 m; straight bars 40 mm."""
    if not bent:
        return 40.0
    if distance_between_faces_mm <= 1000.0:
        return 10.0
    if distance_between_faces_mm <= 2000.0:
        return 15.0
    return 20.0


def space_inside_links_mm(width_mm, cover_mm, link_dia_mm):
    """Clear width inside the links of a member: cover and actual link size each side, less Table 5.5."""
    return (width_mm - 2.0 * (cover_mm + actual_size_mm(link_dia_mm))
            - closed_deduction_mm(width_mm, bent=True))


def bars_fit(space_mm, n_bars, bar_dia_mm, aggregate_mm=DEFAULT_AGGREGATE_MM):
    """
    (fits, clear gap mm) for n_bars of bar_dia_mm side by side in space_mm, at their actual size.
    One bar always fits if it is not wider than the space.
    """
    if n_bars <= 0:
        return True, space_mm
    used = n_bars * actual_size_mm(bar_dia_mm)
    if n_bars == 1:
        return used <= space_mm + 1e-6, space_mm - used
    gap = (space_mm - used) / (n_bars - 1)
    return gap >= min_clear_mm(bar_dia_mm, aggregate_mm) - 1e-6, gap


def max_bars_in(space_mm, bar_dia_mm, aggregate_mm=DEFAULT_AGGREGATE_MM):
    """Most bars of bar_dia_mm that fit side by side in space_mm."""
    size = actual_size_mm(bar_dia_mm)
    if space_mm < size:
        return 0
    return 1 + int((space_mm - size + 1e-6) // (size + min_clear_mm(bar_dia_mm, aggregate_mm)))


def mesh_spacing_notes(spacing_mm, bar_dia_mm, aggregate_mm=DEFAULT_AGGREGATE_MM, label=u'bars'):
    """Notes when a mesh pitch leaves too small a clear gap or is under the SMDSC minimum pitch."""
    # floats: IronPython 2 rejects '{:.0f}' for an int (the tabs' diameters are ints)
    spacing_mm, bar_dia_mm = float(spacing_mm), float(bar_dia_mm)
    notes = []
    clear = spacing_mm - actual_size_mm(bar_dia_mm)
    need = min_clear_mm(bar_dia_mm, aggregate_mm)
    if clear < need - 1e-6:
        notes.append(u'{} H{:.0f} at {:.0f} mm leave {:.0f} mm clear, under the {:.0f} mm minimum '
                     u'(SMDSC 5.2).'.format(label, bar_dia_mm, spacing_mm, clear, need))
    if spacing_mm < MIN_PITCH_MM - 1e-6:
        notes.append(u'{} at {:.0f} mm are under the {:.0f} mm minimum pitch (100 mm where lapped, '
                     u'SMDSC 6.2).'.format(label, spacing_mm, MIN_PITCH_MM))
    elif spacing_mm < MIN_PITCH_AT_LAPS_MM - 1e-6:
        notes.append(u'{} at {:.0f} mm: keep laps staggered, a lapped zone needs a {:.0f} mm pitch '
                     u'(SMDSC 6.2).'.format(label, spacing_mm, MIN_PITCH_AT_LAPS_MM))
    return notes


def layer_notes(width_mm, cover_mm, link_dia_mm, n_bars, bar_dia_mm, aggregate_mm=DEFAULT_AGGREGATE_MM,
                label=u'bars'):
    """Notes when n_bars of a layer do not fit inside the links of a member width_mm wide."""
    width_mm, cover_mm, link_dia_mm, bar_dia_mm = float(width_mm), float(cover_mm), float(link_dia_mm), float(bar_dia_mm)
    space = space_inside_links_mm(width_mm, cover_mm, link_dia_mm)
    fits, gap = bars_fit(space, n_bars, bar_dia_mm, aggregate_mm)
    if fits:
        return []
    return [u'{} {}H{:.0f} do not fit in one layer of a {:.0f} mm member: {:.0f} mm inside the links '
            u'(SMDSC Table 5.5, bars at +10 %), {:.0f} mm clear between bars against {:.0f} mm; at most '
            u'{} per layer.'.format(label, n_bars, bar_dia_mm, width_mm, space, gap,
                                    min_clear_mm(bar_dia_mm, aggregate_mm),
                                    max_bars_in(space, bar_dia_mm, aggregate_mm))]
