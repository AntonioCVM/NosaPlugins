# -*- coding: utf-8 -*-
__title__ = "QR\nCode"
__version__ = '1.2'
__doc__ = """Generate branded NOSA QR codes and place them in titleblock families.

Creates 24 x 24 mm PNG images at 1200 dpi with 2x supersampling:
circular data modules, orange finder eyes, NOSA logo in centre.
Error correction level M (15 %) + automatic URL cleaning for optimal density.

After generating, click "Place in Titleblocks" to update every unique
titleblock family in the project – all sheets refresh automatically."""
__author__ = 'NOSA Engineering'

import os
import sys

from pyrevit import revit

_lib = os.path.join(os.path.dirname(__file__), 'lib')
if _lib not in sys.path:
    sys.path.insert(0, _lib)


def _load_ui():
    try:
        import importlib.util as iu
        spec = iu.spec_from_file_location('qrcode_ui', os.path.join(_lib, 'ui.py'))
        mod = iu.module_from_spec(spec)
        sys.modules['qrcode_ui'] = mod
        spec.loader.exec_module(mod)
        return mod
    except (ImportError, AttributeError):
        import imp
        return imp.load_source('qrcode_ui', os.path.join(_lib, 'ui.py'))


_ui = _load_ui()
QRCodeWindow = _ui.QRCodeWindow

if __name__ == '__main__':
    _doc   = getattr(revit, 'doc',   None)
    _uidoc = getattr(revit, 'uidoc', None)
    QRCodeWindow(_doc, _uidoc).ShowDialog()
