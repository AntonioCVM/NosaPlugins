# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — draw a shape sketch to a PNG in pure Python (T7.5): anti-aliased thick
lines, a 5x7 bitmap font for the dimension letters, zlib PNG encoding with a 300 dpi pHYs chunk.
No .NET drawing: System.Drawing from IronPython crashed Revit 2024 (stack overflow, 2026-10-03).
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import math
import struct
import zlib

# 5x7 glyphs, rows top to bottom, '#' = ink (dimension letters and what labels may contain)
_FONT = dict(zip(u'ABCDEFRGH, ', (
    (' ### ', '#   #', '#   #', '#####', '#   #', '#   #', '#   #'),
    ('#### ', '#   #', '#   #', '#### ', '#   #', '#   #', '#### '),
    (' ####', '#    ', '#    ', '#    ', '#    ', '#    ', ' ####'),
    ('#### ', '#   #', '#   #', '#   #', '#   #', '#   #', '#### '),
    ('#####', '#    ', '#    ', '#### ', '#    ', '#    ', '#####'),
    ('#####', '#    ', '#    ', '#### ', '#    ', '#    ', '#    '),
    ('#### ', '#   #', '#   #', '#### ', '# #  ', '#  # ', '#   #'),
    (' ####', '#    ', '#    ', '# ###', '#   #', '#   #', ' ### '),
    ('#   #', '#   #', '#   #', '#####', '#   #', '#   #', '#   #'),
    ('     ', '     ', '     ', '     ', '  ## ', '  ## ', ' #   '),
    ('     ',) * 7,
)))


class Canvas(object):
    """Grey-scale canvas, 255 = white paper, 0 = ink."""

    def __init__(self, width, height):
        self.width, self.height = int(width), int(height)
        self.rows = [bytearray([255] * self.width) for _ in range(self.height)]

    def ink(self, x, y, coverage):
        if 0 <= x < self.width and 0 <= y < self.height and coverage > 0:
            value = int(round(255 * (1.0 - min(coverage, 1.0))))
            row = self.rows[y]
            if value < row[x]:
                row[x] = value

    def line(self, a, b, width):
        """Thick segment with round ends, edge anti-aliased over one pixel."""
        half = width / 2.0
        x0, x1 = int(math.floor(min(a[0], b[0]) - half - 1)), int(math.ceil(max(a[0], b[0]) + half + 1))
        y0, y1 = int(math.floor(min(a[1], b[1]) - half - 1)), int(math.ceil(max(a[1], b[1]) + half + 1))
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        reach = half + 1.5
        for y in range(max(y0, 0), min(y1, self.height - 1) + 1):
            py = y + 0.5
            if abs(dy) > 1e-9:                  # only the band of this row the bar can touch
                t0, t1 = sorted(((py - reach - a[1]) / dy, (py + reach - a[1]) / dy))
                t0, t1 = max(t0, 0.0), min(t1, 1.0)
                if t0 > t1:
                    t0 = t1 = 0.0 if py < min(a[1], b[1]) else 1.0
                xa, xb = sorted((a[0] + t0 * dx, a[0] + t1 * dx))
                lo, hi = int(math.floor(xa - reach)), int(math.ceil(xb + reach))
            else:
                lo, hi = x0, x1
            for x in range(max(lo, x0, 0), min(hi, x1, self.width - 1) + 1):
                px = x + 0.5
                t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / length2))
                d = math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))
                self.ink(x, y, half + 0.5 - d)

    def polyline(self, points, width):
        for a, b in zip(points[:-1], points[1:]):
            self.line(a, b, width)

    def text(self, text, cx, cy, size):
        """Text centred on (cx, cy); size = glyph height in pixels."""
        cell = max(1, int(round(size / 7.0)))
        glyphs = [_FONT.get(ch.upper(), _FONT[' ']) for ch in text]
        total_w = len(glyphs) * 6 * cell - cell
        left = int(round(cx - total_w / 2.0))
        top = int(round(cy - 7 * cell / 2.0))
        for n, glyph in enumerate(glyphs):
            gx = left + n * 6 * cell
            for r, pattern in enumerate(glyph):
                for c, mark in enumerate(pattern):
                    if mark != ' ':
                        for yy in range(top + r * cell, top + (r + 1) * cell):
                            for xx in range(gx + c * cell, gx + (c + 1) * cell):
                                self.ink(xx, yy, 1.0)

    def png(self, dpi=300):
        """PNG bytes, 8-bit grey-scale, with the print resolution."""
        raw = b''.join(b'\x00' + bytes(row) for row in self.rows)

        def chunk(kind, data):
            body = kind + data
            return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
        per_metre = int(round(dpi / 0.0254))
        return (b'\x89PNG\r\n\x1a\n' +
                chunk(b'IHDR', struct.pack('>IIBBBBB', self.width, self.height, 8, 0, 0, 0, 0)) +
                chunk(b'pHYs', struct.pack('>IIB', per_metre, per_metre, 1)) +
                chunk(b'IDAT', zlib.compress(raw, 9)) +
                chunk(b'IEND', b''))


def draw_sketch(pixel_lines, labels, width, height, line_width=5.0, letter_size=26):
    canvas = Canvas(width, height)
    for line in pixel_lines:
        if len(line) >= 2:
            canvas.polyline(line, line_width)
    for text, x, y in labels:
        canvas.text(text, x, y, letter_size)
    return canvas
