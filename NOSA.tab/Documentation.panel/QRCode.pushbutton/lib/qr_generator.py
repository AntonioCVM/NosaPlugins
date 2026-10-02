# -*- coding: utf-8 -*-
"""
NOSA styled QR code generator.

Runtime routing
---------------
CPython 3   – uses qrcode + Pillow directly (auto-installed via pip).
IronPython  – locates pyRevit's CPython3 engine, spawns it as a subprocess
              to run _qr_subprocess.py, and returns the resulting PNG path.

Public API
----------
generate_nosa_qr(url, size_mm=24, dpi=300)
    CPython3   → PIL.Image (RGBA)
    IronPython → str  (temp PNG file path – caller deletes when done)
"""

import os
import sys
import math
from nosa_utils.telemetry import log_swallowed
_LOG = u'qrcode'

_ORANGE = (255, 95, 0, 255)
_BLACK  = (0,   0,  0, 255)
_WHITE  = (255, 255, 255, 255)
_TRANSP = (0,   0,  0,  0)

# pyRevit truncates sys.version to just '2.7.12' — check the major version
# In pyRevit: IronPython == Python 2.x,  CPython == Python 3.x
_IS_IRONPYTHON = sys.version_info[0] < 3


# ---------------------------------------------------------------------------
# Path helpers – locate pyRevit's CPython3 engine
# ---------------------------------------------------------------------------

def _get_engines_dir():
    """
    Navigate from IronPython's sys.prefix to the pyRevit engines directory.

    sys.prefix in pyRevit/IronPython looks like:
        ...\\pyRevit-Master\\bin\\netcore\\engines\\IPY2712PR\\pyRevitLabs.IronPython.dll
    Two os.path.dirname calls give us the engines\\ folder.
    """
    prefix = getattr(sys, 'prefix', '') or ''
    if not prefix:
        return None
    engines = os.path.dirname(os.path.dirname(prefix))
    return engines if os.path.isdir(engines) else None


def _find_cpython3_exe():
    """Return the first usable CPython 3 python.exe, searching several locations."""
    import glob
    import subprocess as sp

    candidates = []

    # 1. pyRevit engines directory  (CPY38, CPY310, CPY311, CPY312 …)
    engines = _get_engines_dir()
    if engines:
        for cpy_dir in sorted(glob.glob(os.path.join(engines, 'CPY*')), reverse=True):
            for name in ('python.exe', 'python3.exe'):
                p = os.path.join(cpy_dir, name)
                if os.path.isfile(p):
                    candidates.append(p)

    # 2. Common fixed paths
    appdata = os.environ.get('APPDATA', '')
    localappdata = os.environ.get('LOCALAPPDATA', '')
    for base in [
        os.path.join(appdata, 'Programs', 'Python'),
        os.path.join(localappdata, 'Programs', 'Python'),
        'C:\\Python312', 'C:\\Python311', 'C:\\Python310',
        'C:\\Python39', 'C:\\Python38',
        'C:\\Program Files\\Python312', 'C:\\Program Files\\Python311',
    ]:
        for name in ('python.exe', 'python3.exe'):
            p = os.path.join(base, name)
            if os.path.isfile(p):
                candidates.append(p)

    # 3. Glob for Python3xx in common install roots
    for pattern in [
        os.path.join(appdata, 'Programs', 'Python', 'Python3*', 'python.exe'),
        os.path.join(localappdata, 'Programs', 'Python', 'Python3*', 'python.exe'),
    ]:
        candidates += sorted(glob.glob(pattern), reverse=True)

    # 4. System PATH  (use 'where' command, safe in IronPython subprocess)
    try:
        out_fd, out_tmp = _tmp_file('.txt')
        ret = sp.call(['where', 'python'], stdout=out_fd, stderr=out_fd)
        os.close(out_fd)
        if ret == 0:
            with open(out_tmp, 'r') as f:
                for line in f:
                    p = line.strip()
                    if os.path.isfile(p) and 'python' in os.path.basename(p).lower():
                        candidates.append(p)
        os.unlink(out_tmp)
    except Exception:
        log_swallowed(_LOG, u'_find_cpython3_exe')

    # Return first candidate that really is Python 3
    for p in candidates:
        try:
            out_fd, out_tmp = _tmp_file('.txt')
            ret = sp.call([p, '--version'], stdout=out_fd, stderr=out_fd)
            os.close(out_fd)
            with open(out_tmp, 'r') as f:
                ver_str = f.read()
            os.unlink(out_tmp)
            if ret == 0 and 'Python 3' in ver_str:
                return p
        except Exception:
            log_swallowed(_LOG, u'_find_cpython3_exe')

    return None


def _tmp_file(suffix=''):
    """Create a temp file and return (fd, path)."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=suffix, prefix='nosa_qr_tmp_')
    return fd, path


def _diagnose():
    return (
        'sys.executable = {}\n'
        'sys.prefix     = {}\n'
        'sys.version    = {}\n'
        'engines dir    = {}'
    ).format(
        getattr(sys, 'executable', 'N/A'),
        getattr(sys, 'prefix',     'N/A'),
        sys.version.split()[0],
        _get_engines_dir() or 'not found',
    )


# ---------------------------------------------------------------------------
# CPython3 direct path  (qrcode + Pillow)
# ---------------------------------------------------------------------------

def _deps_present():
    """Check whether qrcode + Pillow are importable, without installing anything."""
    try:
        import qrcode       # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def _ensure_deps(confirm=None):
    """
    Import or auto-install qrcode + Pillow. Returns (ok, err_msg).

    confirm: optional no-arg callable returning True/False. Called before
    actually installing anything (never before a plain import that already
    succeeds). If it returns False, installation is skipped and (False, ...)
    is returned instead of silently running pip.
    """
    if _deps_present():
        return True, None

    if confirm is not None and not confirm():
        return False, u'Installation of qrcode/Pillow was declined by the user.'

    # Try pip internal API first (no subprocess needed)
    try:
        from pip._internal.cli.main import main as _pip
        _pip(['install', '--quiet', 'qrcode', 'Pillow'])
        import qrcode       # noqa: F401
        from PIL import Image  # noqa: F401
        return True, None
    except Exception:
        log_swallowed(_LOG, u'_ensure_deps')

    # Fallback: subprocess with a valid Python exe
    py = _find_valid_cpython_exe()
    if py:
        try:
            import subprocess
            subprocess.call([py, '-m', 'pip', 'install', '--quiet', 'qrcode', 'Pillow'])
            import qrcode       # noqa: F401
            from PIL import Image  # noqa: F401
            return True, None
        except Exception as e:
            return False, str(e)

    return False, 'Auto-install failed.\n' + _diagnose()


def _find_valid_cpython_exe():
    """Find any usable python.exe (not Revit.exe, not None)."""
    exe = getattr(sys, 'executable', None)
    if exe and isinstance(exe, str) and os.path.isfile(exe):
        if 'python' in os.path.basename(exe).lower():
            return exe

    prefix = getattr(sys, 'prefix', '') or ''
    for name in ('python.exe', 'python3.exe'):
        p = os.path.join(prefix, name)
        if os.path.isfile(p):
            return p

    return _find_cpython3_exe()


def _rounded_rect(draw, x0, y0, x1, y1, radius, fill):
    """Filled rounded rectangle, compatible with all Pillow versions."""
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
    from PIL import Image as _PILImg
    sz = max(4, int(round(logo_d * 0.88)))
    if os.path.isfile(_LOGO_PATH):
        try:
            logo = _PILImg.open(_LOGO_PATH).convert('RGBA')
            logo = logo.resize((sz, sz), _PILImg.LANCZOS)
            px = int(round(cx - sz / 2))
            py = int(round(cy - sz / 2))
            img.paste(logo, (px, py), logo.split()[3])
            return
        except Exception:
            log_swallowed(_LOG, u'_paste_logo')
    # Vector fallback
    from PIL import ImageDraw as _IDraw
    draw = _IDraw.Draw(img)
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


def _render_pil(matrix, n, size_mm, dpi):
    """
    Render QR matrix to a high-quality PIL RGBA image.

    Design: no outer orange frame – the QR content fills the full canvas
    with a small white margin, making each module larger and therefore
    sharper.  Finder patterns keep the NOSA orange style.

    Uses 2× supersampling: renders at double resolution then downscales
    with LANCZOS to eliminate pixelation on all circles and ellipses.
    """
    from PIL import Image, ImageDraw

    # Render at 2× target resolution for smooth anti-aliasing
    render_dpi = dpi * 2
    px  = max(480, int(round(size_mm / 25.4 * render_dpi)))
    # Small white margin only – no frame border
    pad = max(8, px // 40)
    qr_sz = px - 2 * pad
    mod   = qr_sz / float(n)
    qr_x  = pad
    qr_y  = pad

    # White opaque background (QR codes need high contrast)
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

    # Circular data modules
    r_dot = mod * 0.42
    for row in range(n):
        for col in range(n):
            if matrix[row][col] and not _in_finder(row, col):
                cx = qr_x + (col + 0.5) * mod
                cy = qr_y + (row + 0.5) * mod
                draw.ellipse([cx - r_dot, cy - r_dot, cx + r_dot, cy + r_dot], fill=_BLACK)

    # Orange finder pattern rings
    r_out, r_sep, r_in = mod * 3.3, mod * 2.5, mod * 1.5
    for er, ec in [(3, 3), (3, n - 4), (n - 4, 3)]:
        cx = qr_x + (ec + 0.5) * mod
        cy = qr_y + (er + 0.5) * mod
        draw.ellipse([cx - r_out, cy - r_out, cx + r_out, cy + r_out], fill=_ORANGE)
        draw.ellipse([cx - r_sep, cy - r_sep, cx + r_sep, cy + r_sep], fill=_WHITE)
        draw.ellipse([cx - r_in,  cy - r_in,  cx + r_in,  cy + r_in],  fill=_BLACK)

    # NOSA logo centred
    logo_d  = mod * 7.0
    logo_cx = logo_cy = px / 2.0
    bg_r    = logo_d * 0.56
    draw.ellipse([logo_cx - bg_r, logo_cy - bg_r, logo_cx + bg_r, logo_cy + bg_r], fill=_WHITE)
    _paste_logo(img, logo_cx, logo_cy, logo_d)

    # Downsample to final target resolution – LANCZOS is the best quality filter
    target_px = max(240, int(round(size_mm / 25.4 * dpi)))
    img = img.resize((target_px, target_px), Image.LANCZOS)
    return img


def _generate_cpython(url, size_mm, dpi, confirm=None):
    """Generate QR code using qrcode + Pillow (CPython3 only)."""
    ok, err = _ensure_deps(confirm=confirm)
    if not ok:
        raise ImportError(err)

    import qrcode
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1, border=0,
    )
    qr.add_data(url)
    qr.make(fit=True)

    return _render_pil(qr.modules, qr.modules_count, size_mm, dpi)


# ---------------------------------------------------------------------------
# IronPython bridge path  (spawn CPython3 subprocess)
# ---------------------------------------------------------------------------

def _cpython_deps_present(cpy_exe):
    """Check (no install) whether qrcode + Pillow are importable in cpy_exe."""
    import subprocess as sp
    try:
        with open(os.devnull, 'wb') as _devnull:
            ret = sp.call([cpy_exe, '-c', 'import qrcode, PIL'],
                          stdout=_devnull, stderr=_devnull)
        return ret == 0
    except Exception:
        return False


def _generate_ironpython(url, size_mm, dpi, confirm=None):
    """
    IronPython path: find CPython3 in pyRevit engines, spawn _qr_subprocess.py,
    return temp PNG file path.

    confirm: optional no-arg callable returning True/False, asked before the
    subprocess is allowed to auto-install qrcode/Pillow (the subprocess itself
    always installs unconditionally if missing, so the check must happen here).
    """
    import subprocess as sp
    import tempfile

    cpy_exe = _find_cpython3_exe()
    if not cpy_exe:
        raise RuntimeError(
            'Python 3 not found. Please install Python 3 from python.org\n'
            'or enable the CPython3 engine in pyRevit Settings.\n\n'
            + _diagnose()
        )

    if confirm is not None and not _cpython_deps_present(cpy_exe):
        if not confirm():
            raise RuntimeError(
                u'Installation of qrcode/Pillow was declined by the user.'
            )

    fd, tmp = tempfile.mkstemp(suffix='.png', prefix='nosa_qr_')
    os.close(fd)

    bridge = os.path.join(os.path.dirname(__file__), '_qr_subprocess.py')

    # Write URL to a temp file to avoid any shell-quoting issues with Unicode
    fd2, url_file = tempfile.mkstemp(suffix='.txt', prefix='nosa_qr_url_')
    try:
        os.write(fd2, url.encode('utf-8'))
    except Exception:
        os.write(fd2, url)
    os.close(fd2)

    try:
        ret = sp.call([cpy_exe, bridge, url_file, tmp, str(size_mm), str(dpi)])
    finally:
        try:
            os.unlink(url_file)
        except Exception:
            log_swallowed(_LOG, u'_generate_ironpython')

    if ret != 0:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise RuntimeError(
            'QR subprocess exited with code {}.\n'
            'CPython3: {}\n'
            'Bridge:   {}'.format(ret, cpy_exe, bridge)
        )

    return tmp   # caller loads this PNG and deletes it when done


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_nosa_qr(url, size_mm=24, dpi=1200, confirm=None):
    """
    Generate a branded NOSA QR code.

    confirm: optional no-arg callable returning True/False, used to ask the
    user before qrcode/Pillow are auto-installed via pip (only asked if the
    packages are actually missing). If omitted, installation proceeds without
    asking (previous behaviour), so headless/non-interactive callers are
    unaffected.

    Returns
    -------
    CPython3   : PIL.Image (RGBA, 24×24 mm at 600 dpi, 2× supersampled)
    IronPython : str  (absolute path to a temp PNG file – caller deletes it)

    Raises
    ------
    ImportError / RuntimeError on failure.
    """
    if _IS_IRONPYTHON:
        return _generate_ironpython(url, size_mm, dpi, confirm=confirm)
    return _generate_cpython(url, size_mm, dpi, confirm=confirm)


# ---------------------------------------------------------------------------
# Matrix-only API  (used by vector / FilledRegion mode)
# ---------------------------------------------------------------------------

def _generate_matrix_cpython(url):
    """Return (matrix, n) using qrcode directly (CPython3)."""
    ok, err = _ensure_deps()
    if not ok:
        raise ImportError(err)
    import qrcode
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1, border=0,
    )
    qr.add_data(url)
    qr.make(fit=True)
    matrix = [[bool(cell) for cell in row] for row in qr.modules]
    return matrix, qr.modules_count


def _generate_matrix_ironpython(url):
    """Return (matrix, n) by spawning the CPython3 subprocess in --matrix-json mode."""
    import subprocess as sp
    import tempfile
    import json as _json

    cpy_exe = _find_cpython3_exe()
    if not cpy_exe:
        raise RuntimeError(
            u'Python 3 no encontrado para generación de matriz QR.\n' + _diagnose()
        )

    fd, json_out = tempfile.mkstemp(suffix='.json', prefix='nosa_qrmat_')
    os.close(fd)
    fd2, url_file = tempfile.mkstemp(suffix='.txt', prefix='nosa_qr_url_')
    try:
        os.write(fd2, url.encode('utf-8'))
    except Exception:
        os.write(fd2, url)
    os.close(fd2)

    bridge = os.path.join(os.path.dirname(__file__), '_qr_subprocess.py')
    try:
        ret = sp.call([cpy_exe, bridge, url_file, '--matrix-json', json_out])
    finally:
        try:
            os.unlink(url_file)
        except Exception:
            log_swallowed(_LOG, u'_generate_matrix_ironpython')

    if ret != 0:
        try:
            os.unlink(json_out)
        except Exception:
            log_swallowed(_LOG, u'_generate_matrix_ironpython')
        raise RuntimeError(u'QR matrix subprocess failed with code {}'.format(ret))

    try:
        with open(json_out, 'r') as f:
            data = _json.load(f)
        return data['matrix'], data['n']
    finally:
        try:
            os.unlink(json_out)
        except Exception:
            log_swallowed(_LOG, u'_generate_matrix_ironpython')


def generate_nosa_qr_matrix(url):
    """
    Return (matrix, n) — the raw QR boolean matrix and module count.

    matrix : list[list[bool]]  — row 0 is the TOP of the QR code
    n      : int               — modules per side

    Used by vector (FilledRegion) placement mode.
    """
    if _IS_IRONPYTHON:
        return _generate_matrix_ironpython(url)
    return _generate_matrix_cpython(url)
