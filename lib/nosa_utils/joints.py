# -*- coding: utf-8 -*-
"""
nosa_utils.joints — coordination of bars where members meet (T8.49, IStructE SMDSC 4.2.1 / 4.2.2, 5.2.5), no
Revit: anchorage legs in one column nested so they do not coincide, a slab's top mat over a beam's top bars, a
main beam's top bars over a secondary's, beam bars passing between a column's bars.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

from nosa_utils import rebar_qa


def leg_step_mm(outer_dia_mm, inner_dia_mm, aggregate_mm=rebar_qa.AGGREGATE_MM):
    """
    Centre to centre of two anchorage legs side by side in a column, the outer one nearer its far face: the
    real bar sizes plus the minimum clear gap (SMDSC 5.2.5), up to the next 5 mm.
    """
    need = rebar_qa.REAL_DIA * (outer_dia_mm + inner_dia_mm) / 2.0 + rebar_qa.min_clear_mm(
        max(outer_dia_mm, inner_dia_mm), aggregate_mm)
    return 5.0 * math.ceil(need / 5.0 - 1e-9)


def nested_leg_insets_mm(top_dia_mm, bottom_dia_mm, support_dia_mm=None):
    """
    How far inside the top bars' legs the other legs of a beam end stand in its column (SMDSC MB1: the top bars
    outermost, the support bars inside them, the bottom bars inside both): {'support': mm, 'bottom': mm}.
    """
    if support_dia_mm:
        s = leg_step_mm(top_dia_mm, support_dia_mm)
        return {'support': s, 'bottom': s + leg_step_mm(support_dia_mm, bottom_dia_mm)}
    return {'support': 0.0, 'bottom': leg_step_mm(top_dia_mm, bottom_dia_mm)}


def slab_on_beam_drop_mm(slab_top_cover_mm, slab_top_dias_mm, beam_top_cover_mm):
    """
    How much lower a beam's links and top bars go under a slab flush with its top (SMDSC 4.2.2): the slab's top
    mat keeps its cover and the beam's links start under both of its layers.
    """
    return max(0.0, float(slab_top_cover_mm) + sum(slab_top_dias_mm) - float(beam_top_cover_mm))


def secondary_drop_mm(primary_top_dia_mm):
    """A secondary beam's top bars pass under the main beam's top bars (SMDSC 4.2.1): lower by their size."""
    return float(primary_top_dia_mm or 0.0)


def bars_between(column_bars_mm, beam_bars_mm, column_dia_mm, beam_dia_mm,
                 aggregate_mm=rebar_qa.AGGREGATE_MM):
    """
    Beam bars (positions across the column face, mm) that do not pass clear between the column's vertical bars
    there (SMDSC 4.2.1): [(beam bar position, nearest column bar, clear gap)].
    """
    need = rebar_qa.min_clear_mm(max(column_dia_mm, beam_dia_mm), aggregate_mm)
    out = []
    for b in beam_bars_mm:
        if not column_bars_mm:
            break
        c = min(column_bars_mm, key=lambda x: abs(x - b))
        clear = abs(c - b) - rebar_qa.REAL_DIA * (column_dia_mm + beam_dia_mm) / 2.0
        if clear < need - 0.5:
            out.append((b, c, clear))
    return out
