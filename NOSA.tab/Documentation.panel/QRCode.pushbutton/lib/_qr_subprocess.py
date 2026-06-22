#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NOSA QR Code generator – CPython3 subprocess bridge.

Called by qr_generator.py from IronPython:
    python _qr_subprocess.py <url_file> <output_png> [size_mm] [dpi]

url_file  : path to a UTF-8 text file containing the URL/content to encode
output_png: destination PNG path
size_mm   : output size in millimetres (default 24)
dpi       : resolution (default 300)
"""

import sys
import os
import subprocess
import math

# ---------------------------------------------------------------------------
# Dependency bootstrap
# ---------------------------------------------------------------------------

def _ensure():
    try:
        import qrcode        # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', 'qrcode', 'Pillow', '--quiet']
        )

_ensure()

import qrcode
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Rendering constants
# ---------------------------------------------------------------------------

_ORANGE = (255, 95, 0, 255)
_BLACK  = (0,   0,  0, 255)
_WHITE  = (255, 255, 255, 255)
_TRANSP = (0,   0,  0,  0)


def _rounded_rect(draw, x0, y0, x1, y1, radius, fill):
    r = int(radius)
    draw.rectangle([x0 + r, y0,      x1 - r, y1],      fill=fill)
    draw.rectangle([x0,     y0 + r,  x1,     y1 - r],  fill=fill)
    draw.ellipse(  [x0,      y0,      x0 + 2*r, y0 + 2*r], fill=fill)
    draw.ellipse(  [x1 - 2*r, y0,    x1,       y0 + 2*r], fill=fill)
    draw.ellipse(  [x0,      y1 - 2*r, x0 + 2*r, y1],     fill=fill)
    draw.ellipse(  [x1 - 2*r, y1 - 2*r, x1,     y1],      fill=fill)


_LOGO_PATH = os.path.join(os.path.dirname(__file__), 'nosa_logo.png')


def _paste_logo(img, cx, cy, logo_d):
    """Paste the NOSA logo PNG centred at (cx, cy). Falls back to vector."""
    sz = max(4, int(round(logo_d * 0.88)))
    if os.path.isfile(_LOGO_PATH):
        try:
            logo = Image.open(_LOGO_PATH).convert('RGBA')
            logo = logo.resize((sz, sz), Image.LANCZOS)
            px = int(round(cx - sz / 2))
            py = int(round(cy - sz / 2))
            img.paste(logo, (px, py), logo.split()[3])
            return
        except Exception:
            pass
    # Vector fallback
    draw = ImageDraw.Draw(img)
    _nosa_logo_vector(draw, cx, cy, logo_d)


def _nosa_logo_vector(draw, cx, cy, size):
    r = size * 0.5
    pts = [
        (cx + r * math.cos(math.radians(30 + i * 60)),
         cy + r * math.sin(math.radians(30 + i * 60)))
        for i in range(6)
    ]
    draw.polygon(pts, fill=_ORANGE)
    nw, nh, bar = size * 0.28, size * 0.28, size * 0.085
    x0, y0 = cx - nw, cy - nh
    x1, y1 = cx + nw, cy + nh
    draw.rectangle([x0,       y0, x0 + bar, y1], fill=_WHITE)
    draw.rectangle([x1 - bar, y0, x1,       y1], fill=_WHITE)
    draw.polygon([(x0, y0), (x0 + bar, y0), (x1, y1), (x1 - bar, y1)], fill=_WHITE)


def generate(url, size_mm, dpi):
    """
    No outer frame design: QR content fills the full canvas.
    2× supersampling + LANCZOS downsample for smooth edges.
    """
    render_dpi = dpi * 2
    px  = max(480, int(round(size_mm / 25.4 * render_dpi)))
    pad = max(8, px // 40)
    qr_sz = px - 2 * pad

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1, border=0,
    )
    qr.add_data(url)
    qr.make(fit=True)

    matrix = qr.modules
    n      = qr.modules_count
    mod    = qr_sz / float(n)
    qr_x   = pad
    qr_y   = pad

    img  = Image.new('RGBA', (px, px), _WHITE)
    draw = ImageDraw.Draw(img)

    _finders = [
        (0,     0,     6,     6    ),
        (0,     n - 7, 6,     n - 1),
        (n - 7, 0,     n - 1, 6    ),
    ]

    def _in_finder(row, col):
        for r0, c0, r1, c1 in _finders:
            if r0 <= row <= r1 and c0 <= col <= c1:
                return True
        return False

    r_dot = mod * 0.42
    for row in range(n):
        for col in range(n):
            if matrix[row][col] and not _in_finder(row, col):
                cx = qr_x + (col + 0.5) * mod
                cy = qr_y + (row + 0.5) * mod
                draw.ellipse([cx - r_dot, cy - r_dot, cx + r_dot, cy + r_dot], fill=_BLACK)

    r_out, r_sep, r_in = mod * 3.3, mod * 2.5, mod * 1.5
    for er, ec in [(3, 3), (3, n - 4), (n - 4, 3)]:
        cx = qr_x + (ec + 0.5) * mod
        cy = qr_y + (er + 0.5) * mod
        draw.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], fill=_ORANGE)
        draw.ellipse([cx - r_sep, cy - r_sep, cx + r_sep, cy + r_sep], fill=_WHITE)
        draw.ellipse([cx - r_in,  cy - r_in,  cx + r_in,  cy + r_in],  fill=_BLACK)

    logo_d  = mod * 7.0
    logo_cx = logo_cy = px / 2.0
    bg_r    = logo_d * 0.56
    draw.ellipse([logo_cx - bg_r, logo_cy - bg_r, logo_cx + bg_r, logo_cy + bg_r], fill=_WHITE)
    _paste_logo(img, logo_cx, logo_cy, logo_d)

    target_px = max(240, int(round(size_mm / 25.4 * dpi)))
    img = img.resize((target_px, target_px), Image.LANCZOS)
    return img


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: _qr_subprocess.py <url_file> <output_png> [size_mm] [dpi]')
        print('   or: _qr_subprocess.py <url_file> --matrix-json <output_json>')
        sys.exit(1)

    url_file = sys.argv[1]

    try:
        with open(url_file, 'r', encoding='utf-8') as f:
            url = f.read().strip()
    except TypeError:
        with open(url_file, 'r') as f:
            url = f.read().strip()

    # ── Matrix-only mode ────────────────────────────────────────────────
    if len(sys.argv) >= 4 and sys.argv[2] == '--matrix-json':
        json_out = sys.argv[3]
        try:
            import json
            qr = qrcode.QRCode(
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=1, border=0,
            )
            qr.add_data(url)
            qr.make(fit=True)
            data = {
                'matrix': [[bool(cell) for cell in row] for row in qr.modules],
                'n': qr.modules_count,
            }
            with open(json_out, 'w') as f:
                json.dump(data, f)
            sys.exit(0)
        except Exception as e:
            print('ERROR: {}'.format(e), file=sys.stderr)
            sys.exit(1)

    # ── PNG generation mode (default) ───────────────────────────────────
    output_png = sys.argv[2]
    size_mm    = float(sys.argv[3]) if len(sys.argv) > 3 else 24
    dpi        = int(sys.argv[4])   if len(sys.argv) > 4 else 1200

    try:
        img = generate(url, size_mm, dpi)
        img.save(output_png, dpi=(dpi, dpi))
        sys.exit(0)
    except Exception as e:
        print('ERROR: {}'.format(e), file=sys.stderr)
        sys.exit(1)
