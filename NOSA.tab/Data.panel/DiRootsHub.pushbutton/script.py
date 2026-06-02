# -*- coding: utf-8 -*-
__title__ = "DiRoots\n Hub"
__version__ = '1.0'
__doc__ = """Unified launcher for NOSA bulk instance + type editors."""
__author__ = 'NOSA Engineering'

import os
import sys
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)


def _load_ui():
    try:
        import importlib.util as iu
        spec = iu.spec_from_file_location(u'diroots_hub_ui', os.path.join(lib_path, u'ui.py'))
        mod = iu.module_from_spec(spec)
        sys.modules[u'diroots_hub_ui'] = mod
        spec.loader.exec_module(mod)
        return mod
    except (ImportError, AttributeError):
        import imp
        return imp.load_source(u'diroots_hub_ui', os.path.join(lib_path, u'ui.py'))


_ui = _load_ui()
DiRootsHubWindow = _ui.DiRootsHubWindow


if __name__ == '__main__':
    DiRootsHubWindow(revit.doc, getattr(revit, 'uidoc', None)).ShowDialog()
