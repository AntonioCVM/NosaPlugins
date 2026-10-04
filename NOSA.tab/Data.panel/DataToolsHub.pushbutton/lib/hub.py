# -*- coding: utf-8 -*-
"""Excel sync, workset health, model cleanup, link manager, type renamer, shared parameter audit and worksharing audit in one hub."""
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
        (u'Data Tools', _tool('', 'datatoolshub_ui', 'DataToolsHubWindow', doc)),
        (u'Shared Parameters', _tool('shared_params', 'sharedparammanager_ui', 'SharedParamManagerWindow', doc)),
        (u'Worksharing Audit', _tool('worksharing', 'worksharingaudit_ui', 'WorksharingAuditWindow', doc)),
    ]
