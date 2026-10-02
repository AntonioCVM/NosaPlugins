# -*- coding: utf-8 -*-
import os
import sys

from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

from nosa_utils.bootstrap import load_module
_logic = load_module('poursequence_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class PourSequencePlannerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'pour_sequence_planner')
        self.doc = doc
        self._load_levels()

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
        self.TxtPhase.Text = _logic._DEFAULT_PHASES[0]

    def _load_levels(self):
        self.CboLevel.Items.Clear()
        for lvl in _logic.get_levels(self.doc):
            self.CboLevel.Items.Add(lvl.Name)
        if self.CboLevel.Items.Count:
            self.CboLevel.SelectedIndex = 0

    def Assign_Click(self, sender, args):
        if self.CboLevel.SelectedIndex < 0:
            forms.alert(u'Select a level.')
            return
        phase = (self.TxtPhase.Text or u'').strip()
        if not phase:
            forms.alert(u'Enter a pour phase name.')
            return
        zone = (self.TxtZone.Text or u'').strip()
        lvl = _logic.get_levels(self.doc)[self.CboLevel.SelectedIndex]
        self.SetLoading(True, u'Assigning pour phase…')
        try:
            assigned, skipped = _logic.assign_pour_phase(self.doc, lvl.Id, phase, zone)
            self.TxtResult.Text = u'Assigned "{}" to {} elements ({} skipped).'.format(
                phase, assigned, skipped)
        except Exception as e:
            forms.alert(u'Error:\n{}'.format(e))
        finally:
            self.SetLoading(False)

    def Colour_Click(self, sender, args):
        view = revit.uidoc.ActiveView
        if view is None:
            forms.alert(u'Open a plan or 3D view to apply colour overrides.')
            return
        phases = [p.strip() for p in (self.TxtPhasesList.Text or u'').split(',') if p.strip()]
        if not phases:
            phases = list(_logic._DEFAULT_PHASES)
        self.SetLoading(True, u'Applying colours…')
        try:
            count = _logic.apply_phase_colours(self.doc, view, phases)
            self.TxtResult.Text = u'Applied colour overrides to {} elements in "{}".'.format(
                count, view.Name)
        except Exception as e:
            forms.alert(u'Error:\n{}'.format(e))
        finally:
            self.SetLoading(False)

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
