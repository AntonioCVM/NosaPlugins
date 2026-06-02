# -*- coding: utf-8 -*-
# type: ignore
# pyright: reportMissingImports=false, reportUndefinedVariable=false
# pylint: disable=import-error,no-name-in-module,undefined-variable
__title__ = "Export Sheets Pro"
__author__ = "Export Sheets Pro - Optimized Edition"
__version__ = "4.2 (Compatible with NOSA v2.1)"
__doc__ = """Sistema optimizado de exportacion PDF/DWG/DXF
VERSIÓN v4.2 - OPTIMIZED PROFESSIONAL EDITION:

MEJORAS v4.2:
✓ Modular Architecture: Clean code separation
✓ Single UI Class (lib/ui.py)
✓ Improved Responsiveness
✓ Corporate Branding (NOSA)
✓ Internationalization (English/Spanish)
"""

import sys, os, traceback

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
    except (ImportError, AttributeError):
        import imp; m = imp.load_source(n, p); sys.modules[n] = m; return m

from pyrevit import revit, script
from nosa_utils.logging import Logger
ui_module = _lm('exportsheets_ui_local', os.path.join(lib_path, 'ui.py'))
ExportSheetsProForm = ui_module.ExportSheetsProForm

# Logging
logger = Logger()

def main():
    doc = revit.doc
    if not doc:
        logger.warning("No active document.")
        return
        
    try:
        # logger.info("Starting Export Sheets Pro v4.2...")
        form = ExportSheetsProForm(doc)
        form.ShowDialog()
        logger.info("Export Sheets Pro closed.")
        
    except Exception as e:
        logger.critical("Critical error running Export Sheets Pro", e)
        print("Error Critical: {}".format(e))
        print(traceback.format_exc())

if __name__ == '__main__':
    main()
