# -*- coding: utf-8 -*-
# type: ignore
# pyright: reportMissingImports=false, reportUndefinedVariable=false
# pylint: disable=import-error,no-name-in-module,undefined-variable
__title__ = "Sheet Export Hub"
__author__ = "NOSA"
__version__ = "1.0.0"
__doc__ = """Batch export sheets/views to PDF + DWG + DXF with configurable
columns (NOSA Protocols preset + custom presets), inline/batch sheet
parameter editing, live validation status, naming preview and a
pre-export confirmation dialog.

Independent tool alongside Export Sheets Pro — does not replace it.
"""

import sys, os, traceback

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)
_ext_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)

def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
    except (ImportError, AttributeError):
        from nosa_utils.bootstrap import load_module
        m = load_module(n, p); sys.modules[n] = m; return m

from pyrevit import revit
from nosa_utils.logging import Logger
from nosa_utils.base_window import launch_nosa_window
ui_module = _lm('sheetexporthub_ui_local', os.path.join(lib_path, 'ui.py'))
SheetExportHubWindow = ui_module.SheetExportHubWindow

logger = Logger()

def main():
    doc = revit.doc
    if not doc:
        logger.warning("No active document.")
        return

    try:
        launch_nosa_window(SheetExportHubWindow, doc)
        logger.info("Sheet Export Hub closed.")
    except Exception as e:
        logger.critical("Critical error running Sheet Export Hub", e)
        print("Error Critical: {}".format(e))
        print(traceback.format_exc())

if __name__ == '__main__':
    main()
