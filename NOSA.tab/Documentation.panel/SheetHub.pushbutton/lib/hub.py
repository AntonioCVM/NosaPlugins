# -*- coding: utf-8 -*-
"""Sheet creation, NOSA protocol editing, view placement and sheet duplication in one hub."""
import os
import sys

from nosa_utils.bootstrap import load_module

_HERE = os.path.dirname(__file__)


def _tool(sub, module_name, cls_name, *args):
    def make():
        lib = os.path.join(_HERE, sub) if sub else _HERE
        if lib not in sys.path:
            sys.path.insert(0, lib)
        mod = load_module(module_name, os.path.join(lib, 'ui.py'))
        return getattr(mod, cls_name)(*args)
    return make


def tools(doc, uidoc):
    return [
        (u'Sheets & Protocol', _tool('sheet_hub', 'sheethub_ui', 'SheetHubWindow', doc, uidoc)),
        (u'Sheet Gen', _tool('sheet_gen', 'sheetgen_ui', 'SheetComposerWindow', doc)),
    ]
