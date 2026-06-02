# -*- coding: utf-8 -*-
import os, sys
import qrcode, qrcode.constants as QC
from PIL import Image, ImageDraw

_DIR  = os.path.dirname(os.path.abspath(__file__))
_LOGO = os.path.join(_DIR, 'nosa_logo.png')

_ORANGE = (255, 120, 0, 255)
_BLACK  = (0, 0, 0, 255)
_WHITE  = (255, 255, 255, 255)

DPI     = 300
SIZE_MM = 60


def render(url, ec_level):
    qr = qrcode.QRCode(version=None, error_correction=ec_level, box_size=10, border=0)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)

    px  = max(240, int(round(SIZE_MM / 25.4 * DPI * 2)))
    pad = max(8, px // 40)
    qr_sz = px - 2 * pad
    mod   = qr_sz / float(n)

    img  = Image.new('RGBA', (px, px), _WHITE)
    draw = ImageDraw.Draw(img)

    fp_cols = {(r, c)
               for r0, c0 in [(0, 0), (0, n - 7), (n - 7, 0)]
               for r in range(r0, r0 + 7)
               for c in range(c0, c0 + 7)}

    for r in range(n):
        for c in range(n):
            if (r, c) in fp_cols or not matrix[r][c]:
                continue
            cx = pad + (c + 0.5) * mod
            cy = pad + (r + 0.5) * mod
            rad = mod * 0.45
            draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=_BLACK)

    for r0, c0 in [(0, 0), (0, n - 7), (n - 7, 0)]:
        cx = pad + (c0 + 3.5) * mod
        cy = pad + (r0 + 3.5) * mod
        for radius, color in [(mod * 3.5, _ORANGE), (mod * 2.5, _WHITE), (mod * 1.5, _ORANGE)]:
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color)

    logo_size = int(qr_sz * 0.18)
    lx = (px - logo_size) // 2
    ly = (px - logo_size) // 2
    if os.path.exists(_LOGO):
        logo = Image.open(_LOGO).convert('RGBA').resize((logo_size, logo_size), Image.LANCZOS)
        img.paste(logo, (lx, ly), logo)

    target = max(240, int(round(SIZE_MM / 25.4 * DPI)))
    return img.resize((target, target), Image.LANCZOS), n


if __name__ == '__main__':
    url_full  = 'https://nosagi.sharepoint.com/:f:/g/IgBqtIX4u67zTJUi9aD2_HhVAZ6Dj51UzpRYwKqGON-Lanw?e=2EBKMi'
    url_clean = url_full.split('?')[0]

    cases = [
        ('M_full',  QC.ERROR_CORRECT_M, url_full,  'M + URL completa  ({} chars)'.format(len(url_full))),
        ('M_clean', QC.ERROR_CORRECT_M, url_clean, 'M + sin ?e=       ({} chars)'.format(len(url_clean))),
        ('L_full',  QC.ERROR_CORRECT_L, url_full,  'L + URL completa  ({} chars)'.format(len(url_full))),
        ('L_clean', QC.ERROR_CORRECT_L, url_clean, 'L + sin ?e=       ({} chars)'.format(len(url_clean))),
    ]

    for tag, ec, url, desc in cases:
        img, n = render(url, ec)
        out = os.path.join(_DIR, '_demo_{}.png'.format(tag))
        img.save(out)
        print('{} -> {}x{} modulos -> {}'.format(desc, n, n, out))
