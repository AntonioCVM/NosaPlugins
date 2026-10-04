# -*- coding: utf-8 -*-
__title__ = "QR\nCode"
__version__ = '1.2'
__doc__ = """Generate branded NOSA QR codes and place them in titleblock families.

Creates 24 x 24 mm PNG images at 1200 dpi with 2x supersampling:
circular data modules, orange finder eyes, NOSA logo in centre.
Error correction level M (15 %) + automatic URL cleaning for optimal density.

After generating, click "Place in Titleblocks" to update every unique
titleblock family in the project – all sheets refresh automatically."""
__author__  = "A. Viñas"

import os
import sys

from pyrevit import revit

_lib = os.path.join(os.path.dirname(__file__), 'lib')
_ext_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)

from nosa_utils.base_window import launch_nosa_window
from nosa_utils.bootstrap import load_module
_ui = load_module('qrcode_ui', os.path.join(_lib, 'ui.py'))

_doc   = getattr(revit, 'doc',   None)
_uidoc = getattr(revit, 'uidoc', None)
launch_nosa_window(_ui.QRCodeWindow, _doc, _uidoc)

try:
    import nosa_utils.usage as _ut
    _ut.record('qrcode')
except Exception:  # nosa-lint: disable=NOSA006 - usage stats must never break the tool
    pass
