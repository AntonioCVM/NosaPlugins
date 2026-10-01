# -*- coding: utf-8 -*-
import io, csv, os, sys

from pyrevit import forms
from System.Collections.ObjectModel import ObservableCollection

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

from nosa_utils.bootstrap import load_module
_spm_logic = load_module('spm_logic', os.path.join(os.path.dirname(__file__), 'logic_shared_param.py'))


class SPM_Row(object):
    def __init__(self, d):
        self.ParamName  = d['name']
        self.Guid       = d['guid']
        self.Group      = d['group']
        self.DataType   = d['data_type']
        self.BoundStr   = u'Yes' if d['bound'] else u'No'
        self.Status     = d['status']
        self.Categories = d.get('categories', u'')


class SharedParamManagerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'shared_param_manager')
        self.doc = doc
        self.app = doc.Application

        self._all_rows = []
        self._rows = ObservableCollection[SPM_Row]()
        self.GridResults.ItemsSource = self._rows

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._refresh_file_label()
        self._run_audit()

    # ── shared parameter file ────────────────────────────────────────────

    def _refresh_file_label(self):
        path = _spm_logic.get_shared_parameter_file_path(self.app)
        self.TxtFilePath.Text = path if path else u'(no shared parameter file set)'

    def LoadFile_Click(self, sender, args):
        path = forms.pick_file(file_ext='txt')
        if not path:
            return
        try:
            _spm_logic.set_shared_parameter_file(self.app, path)
        except Exception as e:
            forms.alert(u'Could not load shared parameter file:\n{}'.format(e))
            return
        self._refresh_file_label()
        self._run_audit()

    # ── audit ─────────────────────────────────────────────────────────────

    def Audit_Click(self, sender, args):
        self._run_audit()

    def _run_audit(self):
        # The Revit API is single-threaded — doc.ParameterBindings and
        # OpenSharedParameterFile() must run on the main thread, so this
        # can't be handed off to a background Task the way a generic WPF
        # app would. SetLoading swaps in the shared overlay for the
        # duration instead; the audit itself only iterates definitions
        # and bindings (no model geometry scan), so it stays well under a
        # second even on large parameter files.
        self.SetLoading(True, u'Reading shared parameter file…')
        try:
            result = _spm_logic.audit(self.app, self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Audit failed:\n{}'.format(e))
            return
        self.SetLoading(False)

        if result['error']:
            self._all_rows = []
            self.TxtSummary.Text = result['error']
        else:
            self._all_rows = result['rows']
            total = len(self._all_rows)
            bound = sum(1 for r in self._all_rows if r['bound'])
            self.TxtSummary.Text = (
                u'{} definition(s) — {} bound, {} not bound, '
                u'{} orphaned binding(s), {} GUID conflict(s).'.format(
                    total, bound, total - bound,
                    result['orphans'] - result['conflicts'], result['conflicts']))
        self._apply_filter()

    # ── filters ───────────────────────────────────────────────────────────

    def Filter_Changed(self, sender, args):
        self._apply_filter()

    def _apply_filter(self):
        search      = (self.TxtSearch.Text or u'').strip().lower()
        only_issues = self.ChkOnlyIssues.IsChecked == True
        self._rows.Clear()
        for d in self._all_rows:
            if search and search not in d['name'].lower():
                continue
            if only_issues and d['status'] == u'Bound':
                continue
            self._rows.Add(SPM_Row(d))

    # ── export ────────────────────────────────────────────────────────────

    def Export_Click(self, sender, args):
        if not self._all_rows:
            forms.alert(u'Nothing to export — run an audit first.')
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Name', 'GUID', 'Group', 'Data Type', 'Bound', 'Status', 'Categories'])
                for d in self._all_rows:
                    w.writerow([d['name'], d['guid'], d['group'], d['data_type'],
                                u'Yes' if d['bound'] else u'No', d['status'],
                                d.get('categories', u'')])
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    # ── shared ────────────────────────────────────────────────────────────

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
