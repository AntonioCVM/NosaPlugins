# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — plan geometry of curved (arc) walls in plain numbers (T7.9): angles of the
radial vertical bars, horizontal arcs cut to stock length with laps, angles beside a bar.
Angles in radians, measured like Revit (counter-clockwise from +X); lengths in mm.
"""
from __future__ import division
import math


def evenly_spaced(length_mm, spacing_mm, end_clear_mm):
    """Positions exactly spacing_mm apart, centred between the end clearances."""
    lo, hi = end_clear_mm, length_mm - end_clear_mm
    span = hi - lo
    if span <= 0 or spacing_mm <= 0:
        return []
    gaps = int(math.floor(span / spacing_mm + 1e-9))
    if gaps == 0:
        return [lo + span / 2.0]
    start = lo + (span - gaps * spacing_mm) / 2.0
    return [start + k * spacing_mm for k in range(gaps + 1)]


def bar_angles(start_angle, sweep, radius_mm, spacing_mm, end_clear_mm):
    """Angles of bars spaced spacing_mm along the arc of radius_mm (sweep signed: + is CCW)."""
    sign = 1.0 if sweep >= 0 else -1.0
    length = radius_mm * abs(sweep)
    return [start_angle + sign * s / radius_mm for s in evenly_spaced(length, spacing_mm, end_clear_mm)]


def split_arc(a0, a1, radius_mm, stock_mm, lap_mm, first_mm=None):
    """
    [(b0, b1)] angle pieces of the arc a0 -> a1 at radius_mm: stock-length bars lapping lap_mm,
    the first one first_mm long when given (staggered row), the last one the remainder.
    """
    length = radius_mm * abs(a1 - a0)
    if length <= stock_mm + 1e-6:
        return [(a0, a1)]
    first = first_mm if first_mm is not None and lap_mm < first_mm < stock_mm else stock_mm
    if length <= first + 1e-6:
        first = stock_mm
    advance = stock_mm - lap_mm
    sign = 1.0 if a1 >= a0 else -1.0
    pieces = []
    start, end = 0.0, first
    while True:
        if end >= length - 1e-6:
            pieces.append((start, length))
            break
        pieces.append((start, end))
        start = end - lap_mm
        end = start + stock_mm
        if advance <= 0:
            break
    return [(a0 + sign * s / radius_mm, a0 + sign * e / radius_mm) for s, e in pieces]


def point(center, radius_mm, angle):
    return (center[0] + radius_mm * math.cos(angle), center[1] + radius_mm * math.sin(angle))


def arc_length_mm(radius_mm, a0, a1):
    return radius_mm * abs(a1 - a0)
