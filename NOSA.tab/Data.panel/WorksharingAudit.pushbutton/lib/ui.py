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
_wa_logic = load_module('wa_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class WA_Row(object):
    def __init__(self, d):
        self.Category        = d['category']
        self.ElemId           = d['id']
        self.ElemName         = d['name']
        self.Creator          = d['creator']
        self.Owner            = d['owner']
        self.LastChangedBy    = d['last_changed_by']
        self.Checkout         = d['checkout']
        self.Workset          = d['workset']
        self.OnDefault        = d['on_default_workset']
        self.OnDefaultStr     = u'Yes' if d['on_default_workset'] else u'No'


class WorksharingAuditWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'worksharing_audit')
        self.doc = doc

        self._all_rows = []
        self._rows = ObservableCollection[WA_Row]()
        self.GridResults.ItemsSource = self._rows

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        if not _wa_logic.is_workshared(doc):
            self.TxtSummary.Text = (u'This model is not workshared — there is no '
                                     u'ownership/editing history to audit.')
            self.BtnAudit.IsEnabled = False

    # ── audit ─────────────────────────────────────────────────────────────

    def Audit_Click(self, sender, args):
        self._run_audit()

    def _run_audit(self):
        # WorksharingUtils calls are per-element and only valid on the main
        # thread, so — like SharedParamManager's audit — this can't be
        # backgrounded; SetLoading just swaps in the overlay for the scan.
        self.SetLoading(True, u'Reading worksharing data…')
        try:
            active_view = self.doc.ActiveView
            scan_entire = self.ChkEntireModel.IsChecked == True
            result = _wa_logic.audit(self.doc, active_view=active_view,
                                      scan_entire_model=scan_entire)
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
            self.TxtSummary.Text = (
                u'{} element(s) scanned — {} currently checked out, '
                u'{} on the default workset.'.format(
                    result['scanned'], result['checked_out'], result['on_default']))
        self._apply_filter()

    # ── filters ───────────────────────────────────────────────────────────

    def Filter_Changed(self, sender, args):
        self._apply_filter()

    def _apply_filter(self):
        search           = (self.TxtSearch.Text or u'').strip().lower()
        only_checked_out = self.ChkOnlyCheckedOut.IsChecked == True
        only_default     = self.ChkOnlyDefaultWorkset.IsChecked == True

        self._rows.Clear()
        for d in self._all_rows:
            if search:
                haystack = u' '.join([d['category'], d['name'], d['owner'],
                                       d['creator']]).lower()
                if search not in haystack:
                    continue
            if only_checked_out and d['checkout'] == u'Not checked out':
                continue
            if only_default and not d['on_default_workset']:
                continue
            self._rows.Add(WA_Row(d))

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
                w.writerow(['Category', 'Id', 'Element', 'Workset', 'Creator',
                            'Last changed by', 'Checkout', 'On default workset'])
                for d in self._all_rows:
                    w.writerow([d['category'], d['id'], d['name'], d['workset'],
                                d['creator'], d['last_changed_by'], d['checkout'],
                                u'Yes' if d['on_default_workset'] else u'No'])
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    # ── shared ────────────────────────────────────────────────────────────

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
