# -*- coding: utf-8 -*-
import imp
import os, sys
import System.Windows
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('projsetup_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class ProjectSetupWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'project_setup')
        self.doc = doc
        self._prefill()
        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    def _prefill(self):
        """Fill project info fields with current values."""
        try:
            info = _logic.get_project_info(self.doc)
            self.TxtName.Text    = info.get('name', '')
            self.TxtNumber.Text  = info.get('number', '')
            self.TxtClient.Text  = info.get('client', '')
            self.TxtAddress.Text = info.get('address', '')
            self.TxtStatus.Text  = info.get('status', '')
        except Exception:
            pass

    def Configure_Click(self, sender, args):
        results = []

        # Step 1 — Project Info
        if self.ChkProjectInfo.IsChecked == True:
            try:
                info = {
                    'name':    self.TxtName.Text.strip(),
                    'number':  self.TxtNumber.Text.strip(),
                    'client':  self.TxtClient.Text.strip(),
                    'address': self.TxtAddress.Text.strip(),
                    'status':  self.TxtStatus.Text.strip(),
                    'code':    self.TxtCode.Text.strip(),
                }
                _logic.set_project_info(self.doc, info)
                results.append(u'✓ Project information updated.')
            except Exception as e:
                results.append(u'✗ Project info failed: {}'.format(e))

        # Step 2 — Worksets
        if self.ChkWorksets.IsChecked == True:
            try:
                n, err = _logic.create_worksets(self.doc)
                if err:
                    results.append(u'⚠ Worksets: {}'.format(err))
                else:
                    results.append(u'✓ {} workset(s) created.'.format(n))
            except Exception as e:
                results.append(u'✗ Worksets failed: {}'.format(e))

        # Step 3 — Levels
        if self.ChkLevels.IsChecked == True:
            try:
                n, msg = _logic.create_standard_levels(self.doc)
                if msg:
                    results.append(u'⚠ Levels: {}'.format(msg))
                else:
                    results.append(u'✓ {} standard level(s) created.'.format(n))
            except Exception as e:
                results.append(u'✗ Levels failed: {}'.format(e))

        # Step 4 — Sheets
        if self.ChkSheets.IsChecked == True:
            try:
                _logic.create_cover_sheet(self.doc)
                results.append(u'✓ Cover sheet created (00-00).')
            except Exception as e:
                results.append(u'⚠ Cover sheet: {}'.format(e))
            try:
                _logic.create_drawing_index(self.doc)
                results.append(u'✓ Drawing index sheet created (00-01).')
            except Exception as e:
                results.append(u'⚠ Drawing index: {}'.format(e))

        if results:
            forms.alert(u'Project Setup Complete:\n\n{}'.format(u'\n'.join(results)),
                        title=u'Project Setup Wizard')
        else:
            forms.alert(u'No steps were selected.', title=u'Project Setup Wizard')

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
