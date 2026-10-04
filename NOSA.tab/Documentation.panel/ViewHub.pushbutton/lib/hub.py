# -*- coding: utf-8 -*-
"""View management, overrides and filters, view templates and view utilities in one hub."""
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
        (u'Views', _tool('view_manager', 'viewmanager_ui', 'ViewManagerWindow', doc)),
        (u'Overrides & Filters', _tool('view_overrides', 'viewoverrides_ui', 'ViewOverridesWindow', doc)),
        (u'View Templates', _tool('view_templates', 'vtm_ui', 'ViewTemplateManagerWindow', doc)),
        (u'Utilities', _tool('view_utilities', 'viewutilities_ui', 'ViewUtilitiesWindow', doc, uidoc)),
    ]
