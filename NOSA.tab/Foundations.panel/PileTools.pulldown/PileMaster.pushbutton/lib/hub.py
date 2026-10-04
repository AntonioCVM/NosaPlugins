# -*- coding: utf-8 -*-
"""Piling tools and survey: coordinate export, pile numbering, sheet layout and element layout survey tables."""
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



def _pile_master():
    # Pile Master's ui imports its logic modules by these names
    for name, f in (('pilemaster_logic_coords_local', 'logic_coords.py'),
                    ('pilemaster_logic_numbering_local', 'logic_numbering.py'),
                    ('pilemaster_logic_sheets_local', 'logic_sheets.py')):
        sys.modules[name] = load_module(name, os.path.join(_HERE, f))
    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    return load_module('pilemaster_ui_local', os.path.join(_HERE, 'ui.py')).PileMasterWindow()


def _survey(doc):
    def make():
        win = _tool('survey', 'surveyexport_ui', 'SurveyExportWindow', doc)()
        # pile setting-out lives in the Pile Master tab: keep only the element layout survey
        import System
        win.BtnModePile.Visibility = System.Windows.Visibility.Collapsed
        return win
    return make


def tools(doc, uidoc):
    return [
        (u'Pile Master', _pile_master),
        (u'Survey', _survey(doc)),
    ]
