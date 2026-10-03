# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — BS 8666 shape sketches for the bar bending schedule (T7.5). Pure, no Revit.

User decisions 2026-10-03: the BS 8666 sketch of each shape with its dimension letters (A, B, C…),
in the Revit BBS schedule (the RebarShape image) and in the Excel export. The geometry is Revit's
own shape-browser sketch; this module fits it in an image and places the letters.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import math

WIDTH, HEIGHT, MARGIN = 360, 180, 34        # pixels (300 dpi: 30 x 15 mm on paper)
LABEL_OFFSET = 6           # clear gap between the bar and its letter


def _bounds(polylines):
    xs = [p[0] for line in polylines for p in line]
    ys = [p[1] for line in polylines for p in line]
    return min(xs), min(ys), max(xs), max(ys)


def fit(polylines, width=WIDTH, height=HEIGHT, margin=MARGIN):
    """
    Map model (x, y) polylines to image pixels (y down), uniform scale, centred.
    Returns (pixel polylines, transform function).
    """
    x0, y0, x1, y1 = _bounds(polylines)
    span_x, span_y = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)
    if x1 - x0 < 1e-6:
        scale = (height - 2 * margin) / span_y
    if y1 - y0 < 1e-6:
        scale = (width - 2 * margin) / span_x
    ox = (width - (x1 - x0) * scale) / 2.0
    oy = (height - (y1 - y0) * scale) / 2.0

    def to_px(p):
        return (ox + (p[0] - x0) * scale, height - (oy + (p[1] - y0) * scale))
    return [[to_px(p) for p in line] for line in polylines], to_px


def _midpoint(line):
    """Point halfway along a polyline, and the direction of the piece it lies on."""
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(line[:-1], line[1:])]
    total = sum(lengths)
    if total <= 0:
        return line[0], (1.0, 0.0)
    walk = total / 2.0
    for (a, b), length in zip(zip(line[:-1], line[1:]), lengths):
        if walk <= length and length > 0:
            t = walk / length
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), ((b[0] - a[0]) / length,
                                                                          (b[1] - a[1]) / length)
        walk -= length
    return line[-1], (1.0, 0.0)


def label_positions(pixel_lines, labels, offset=LABEL_OFFSET, char_w=24.0, char_h=28.0, line_w=5.0):
    """
    Where each segment's letter goes: beside the middle of its segment, on the side away from
    the sketch's centre, clear of the bar by `offset` whatever the segment's slope (the text box's
    reach along the normal is added). labels: one text (or '') per polyline. Returns [(text, x, y)].
    """
    pts = [p for line in pixel_lines for p in line]
    cx = sum(p[0] for p in pts) / float(len(pts))
    cy = sum(p[1] for p in pts) / float(len(pts))
    out = []
    for line, text in zip(pixel_lines, labels):
        if not text:
            continue
        (mx, my), (dx, dy) = _midpoint(line)
        nx, ny = -dy, dx
        if (mx - cx) * nx + (my - cy) * ny < 0:
            nx, ny = -nx, -ny
        if abs(nx) < 1e-9 and abs(ny) < 1e-9:
            nx, ny = 0.0, -1.0
        half_w = (len(text) * char_w - char_w / 6.0) / 2.0
        reach = abs(nx) * half_w + abs(ny) * char_h / 2.0
        distance = offset + reach + line_w / 2.0
        out.append((text, mx + nx * distance, my + ny * distance))
    return out


def tessellate_arc(start, end, centre, steps=24):
    """Points of the shorter-or-given arc from start to end around centre (2D)."""
    a0 = math.atan2(start[1] - centre[1], start[0] - centre[0])
    a1 = math.atan2(end[1] - centre[1], end[0] - centre[0])
    r = math.hypot(start[0] - centre[0], start[1] - centre[1])
    sweep = a1 - a0
    while sweep <= -math.pi:
        sweep += 2 * math.pi
    while sweep > math.pi:
        sweep -= 2 * math.pi
    return [(centre[0] + r * math.cos(a0 + sweep * i / float(steps)),
             centre[1] + r * math.sin(a0 + sweep * i / float(steps))) for i in range(steps + 1)]
