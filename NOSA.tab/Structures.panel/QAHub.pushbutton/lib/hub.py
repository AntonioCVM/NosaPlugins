# -*- coding: utf-8 -*-
"""Structural QA and model health in one hub: clashes, drawing checks, family audit, IFC, rebar coverage, quantities, health score, warnings and BIM sync."""
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
        (u'Structural QA', _tool('structural_qa', 'structuralqa_ui', 'StructuralQAWindow', doc)),
        (u'Model Health', _tool('model_health', 'modelhealthhub_ui', 'ModelHealthHubWindow', doc)),
    ]
