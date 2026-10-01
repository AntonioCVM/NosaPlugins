# -*- coding: utf-8 -*-
import os
import sys
import csv
import datetime

import System.Windows
import System.Windows.Media as WM
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List
from Autodesk.Revit import DB

from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import element_id_from_int

_here = os.path.dirname(os.path.abspath(__file__))
from nosa_utils.bootstrap import load_module
from nosa_utils.telemetry import log_swallowed
_LOG = u'IssueWorkflowHub'
_pc_logic  = load_module('iwh_pc_logic',  os.path.join(_here, 'logic_protocol_checker.py'))
_ig_logic  = load_module('iwh_ig_logic',  os.path.join(_here, 'logic_issue_gate.py'))
_rpd_logic = load_module('iwh_rpd_logic', os.path.join(_here, 'logic_revision_package_diff.py'))
_rt_logic  = load_module('iwh_rt_logic',  os.path.join(_here, 'logic_revision_tracker.py'))
_sim_logic = load_module('iwh_sim_logic', os.path.join(_here, 'logic_sheet_issue_manager.py'))

_SEARCH_PLACEHOLDER = u'Search issues…'

_IG_CHECK_DEFS = [
    ('protocol',   u'Sheet Protocol'),
    ('revisions',  u'Revision Completeness'),
    ('titleblock', u'Title Block Parameters'),
    ('duplicates', u'Duplicate Sheet Numbers'),
]
_IG_SUFFIXES = {
    'protocol':   'Protocol',
    'revisions':  'Revisions',
    'titleblock': 'Titleblock',
    'duplicates': 'Duplicates',
}
_IG_STATUS_ICONS = {
    'pass':    u'✓',
    'warn':    u'⚠',
    'fail':    u'✗',
    'error':   u'!',
    'pending': u'○',
}
_IG_STATUS_LABELS = {
    'pass':    u'Pass',
    'warn':    u'Warning',
    'fail':    u'Fail',
    'error':   u'Error',
    'pending': u'Not checked',
}


def _ig_make_brush(status):
    if status == 'pass':   return WM.SolidColorBrush(WM.Color.FromRgb(39,  174, 96))
    if status == 'warn':   return WM.SolidColorBrush(WM.Color.FromRgb(243, 156, 18))
    if status == 'fail':   return WM.SolidColorBrush(WM.Color.FromRgb(231, 76,  60))
    if status == 'error':  return WM.SolidColorBrush(WM.Color.FromRgb(120, 120, 120))
    return WM.SolidColorBrush(WM.Color.FromRgb(200, 200, 200))


_RPD_CHANGE_COLORS = {
    u'New Sheet': u'#1A7F37',
    u'Revised':   u'#0550AE',
    u'Removed':   u'#CF222E',
    u'Unchanged': u'#6E7781',
}


# ══════════════════════════════════════════════════════════════════════════
# Row / item classes
# ══════════════════════════════════════════════════════════════════════════

class PCResultRow(object):
    def __init__(self, result):
        self.sheet_number = result.sheet_number
        self.sheet_name = result.sheet_name
        self.status = result.status.upper()
        self.issue_count = len(result.issues)
        self.issues_text = u'; '.join(result.issues)


class IGDetailRow(object):
    def __init__(self, item):
        self.SheetNumber = item.get('number', u'')
        self.SheetName   = item.get('name', u'')
        self.Severity    = item.get('severity', u'')
        self.Issue       = item.get('issue', u'')


class RPDDiffRow(object):
    def __init__(self, r):
        self.SheetNumber = r.get('number', u'')
        self.SheetName   = r.get('name', u'')
        self.Change      = r.get('change', u'')
        self.OldRev      = r.get('old_rev', u'')
        self.NewRev      = r.get('new_rev', u'')
        self.NewDate     = r.get('new_date', u'')


class RTRevisionItem(object):
    """Wraps a DB.Revision for DataGrid binding."""
    def __init__(self, rev):
        self.Rev         = rev
        self.RevId       = rev.Id
        self.Sequence    = rev.SequenceNumber
        self.Description = rev.Description or u''
        self.Date        = rev.RevisionDate  or u''
        self.IsIssued    = rev.Issued
        self.Status      = u'ISSUED' if rev.Issued else u'Open'
        self.IssuedBy    = rev.IssuedBy or u''
        self.IssuedTo    = rev.IssuedTo or u''


class RTSheetRevItem(object):
    """Wraps a ViewSheet + has-revision flag for DataGrid binding."""
    def __init__(self, sheet, has_rev):
        self.SheetId         = sheet.Id
        self.Number          = sheet.SheetNumber or u''
        self.Name            = sheet.Name        or u''
        self.HasRevision     = has_rev
        self.HasRevisionText = u'✅' if has_rev else u'—'
        prefix = u''
        for ch in self.Number:
            if ch.isalpha():
                prefix += ch
            else:
                break
        self.Discipline = prefix or u'—'


class RTCboRevItem(object):
    """Simple label wrapper for the revision ComboBox in the Sheets sub-tab."""
    def __init__(self, rev_item):
        self.RevItem = rev_item
        self.Label   = u'{} — {}'.format(rev_item.Sequence, rev_item.Description)

    def __str__(self):
        return self.Label


class RTSnapItem(object):
    def __init__(self, d):
        self.File  = d['file']
        self.Label = d['label']
        self.Ts    = d['ts']
        self.Count = d['count']

    def __str__(self):
        return u'{} ({} elem.)'.format(self.Label, self.Count)


class RTDeltaRow(object):
    def __init__(self, change_type, entry, detail=u''):
        self.ChangeType = change_type
        self.Category   = entry.get('category', u'')
        self.Name       = entry.get('name', u'') or entry.get('type', u'')
        self.Id         = entry.get('id', u'')
        self.Detail     = detail


class SIMIssueRow(object):
    def __init__(self, rec):
        self.Date      = rec.get('date', u'')
        self.Sheet     = rec.get('sheet', u'')
        self.Revision  = rec.get('revision', u'')
        self.Package   = rec.get('package', u'')
        self.Recipient = rec.get('recipient', u'')
        self.IssuedBy  = rec.get('issued_by', u'')
        self.Notes     = rec.get('notes', u'')


class SIMSheetItem(object):
    def __init__(self, sheet):
        self.sheet = sheet
        self.Display = u'{} — {}'.format(sheet.SheetNumber, sheet.Name)


# ══════════════════════════════════════════════════════════════════════════
# Main window
# ══════════════════════════════════════════════════════════════════════════

class IssueWorkflowHubWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'issue_workflow_hub')
        # SelectionChanged wired in code after LoadComponent, never in XAML (NOSA106)
        self.RT_CboRevision.SelectionChanged += self.RT_CboRevision_Changed
        self.RT_ListSnapshots.SelectionChanged += self.RT_Snapshot_SelectionChanged
        self.doc = doc
        self.proceed_to_export = False

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        # PC state
        self._pc_rows = ObservableCollection[PCResultRow]()
        self.PC_GridResults.ItemsSource = self._pc_rows

        # IG state
        self._ig_results     = {}
        self._ig_detail_rows = ObservableCollection[object]()
        self.IG_DetailGrid.ItemsSource = self._ig_detail_rows
        self._ig_reset_cards()
        self.IG_BtnExport.IsEnabled = False

        # RPD state
        self._rpd_rows  = ObservableCollection[object]()
        self._rpd_diffs = []
        self.RPD_DiffGrid.ItemsSource = self._rpd_rows
        self._rpd_baseline    = cfg.get('rpd_baseline', {})
        self._rpd_baseline_ts = cfg.get('rpd_baseline_ts', u'')
        self._rpd_refresh_baseline_label()

        # RT state
        self._rt_current_tab = 0
        self._rt_rev_items  = ObservableCollection[RTRevisionItem]()
        self.RT_GridRevisions.ItemsSource = self._rt_rev_items
        self._rt_sheet_items = ObservableCollection[RTSheetRevItem]()
        self.RT_GridSheets.ItemsSource = self._rt_sheet_items
        self._rt_cbo_rev_items = ObservableCollection[RTCboRevItem]()
        self.RT_CboRevision.ItemsSource = self._rt_cbo_rev_items
        self._rt_delta_rows = ObservableCollection[RTDeltaRow]()
        self.RT_GridDelta.ItemsSource = self._rt_delta_rows
        self._rt_snap_data  = None
        self._rt_auto_rules = []
        self.RT_TxtNewDate.Text = datetime.date.today().strftime('%d/%m/%Y')
        self._rt_load_revisions()
        self._rt_refresh_snapshots()
        self._rt_load_auto_rules_to_ui()

        # SIM state
        self._sim_records = _sim_logic.load_log()
        self._sim_filter  = u''
        self.SIM_TxtSearch.Text = _SEARCH_PLACEHOLDER
        self._sim_load_sheets()
        self._sim_refresh_grid()
        self._sim_update_status()

        # Outer nav — default to the first step of the workflow
        self._mode = 'protocol'
        self._update_mode_panels()

        # Run the protocol check immediately, matching the original
        # DrawingProtocolChecker's own behaviour of checking on open.
        self._pc_run_checks()

    # ══════════════════════════════════════════════════════════════════
    # Outer sidebar navigation
    # ══════════════════════════════════════════════════════════════════

    def NavBtn_Click(self, sender, args):
        name = sender.Name
        mode_map = {
            'BtnNavProtocol':  'protocol',
            'BtnNavGate':      'gate',
            'BtnNavRevisions': 'revisions',
            'BtnNavDiff':      'diff',
            'BtnNavIssueLog':  'issuelog',
        }
        self._mode = mode_map.get(name, 'protocol')
        self._update_mode_panels()

    def _update_mode_panels(self):
        V = System.Windows.Visibility.Visible
        C = System.Windows.Visibility.Collapsed
        m = self._mode
        self.PanelProtocol.Visibility  = V if m == 'protocol'  else C
        self.PanelGate.Visibility      = V if m == 'gate'      else C
        self.PanelRevisions.Visibility = V if m == 'revisions' else C
        self.PanelDiff.Visibility      = V if m == 'diff'      else C
        self.PanelIssueLog.Visibility  = V if m == 'issuelog'  else C

        self.BtnNavProtocol.Tag  = u'Selected' if m == 'protocol'  else None
        self.BtnNavGate.Tag      = u'Selected' if m == 'gate'      else None
        self.BtnNavRevisions.Tag = u'Selected' if m == 'revisions' else None
        self.BtnNavDiff.Tag      = u'Selected' if m == 'diff'      else None
        self.BtnNavIssueLog.Tag  = u'Selected' if m == 'issuelog'  else None

    # ══════════════════════════════════════════════════════════════════
    # STEP 1: PROTOCOL CHECK  (ex. DrawingProtocolChecker)
    # ══════════════════════════════════════════════════════════════════

    def _pc_run_checks(self):
        self.SetLoading(True, u'Checking sheets…')
        try:
            results = _pc_logic.run_protocol_checks(self.doc)
            summary = _pc_logic.summarise(results)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error running checks:\n{}'.format(e))
            return
        self.SetLoading(False)

        self._pc_rows.Clear()
        for r in results:
            if r.status != 'green':
                self._pc_rows.Add(PCResultRow(r))

        self.PC_TxtSummary.Text = (
            u'{} sheets — {} compliant, {} warnings, {} errors'.format(
                summary['total'], summary['green'], summary['amber'], summary['red']))

        if summary['red'] == 0 and summary['amber'] == 0:
            self.PC_TxtBanner.Text = u'All sheets comply with NOSA v2.2.'
            self.PC_TxtBanner.Foreground = System.Windows.Media.Brushes.ForestGreen
        elif summary['red'] > 0:
            self.PC_TxtBanner.Text = u'Protocol errors found — review before issue.'
            self.PC_TxtBanner.Foreground = System.Windows.Media.Brushes.Firebrick
        else:
            self.PC_TxtBanner.Text = u'Warnings only — review suggested fields.'
            self.PC_TxtBanner.Foreground = System.Windows.Media.Brushes.DarkOrange

    def PC_Refresh_Click(self, sender, args):
        self._pc_run_checks()

    # ══════════════════════════════════════════════════════════════════
    # STEP 2: ISSUE GATE
    # ══════════════════════════════════════════════════════════════════

    def _ig_reset_cards(self):
        pending_brush = _ig_make_brush('pending')
        for key, _ in _IG_CHECK_DEFS:
            suffix = _IG_SUFFIXES[key]
            getattr(self, 'IG_CardAccent' + suffix).BorderBrush = pending_brush
            getattr(self, 'IG_TxtIcon'    + suffix).Text        = u'○'
            getattr(self, 'IG_TxtIcon'    + suffix).Foreground  = pending_brush
            getattr(self, 'IG_TxtStatus'  + suffix).Text        = u'Not checked'
            getattr(self, 'IG_TxtStatus'  + suffix).Foreground  = pending_brush
            getattr(self, 'IG_TxtCount'   + suffix).Text        = u''

    def _ig_update_card(self, key, result):
        suffix = _IG_SUFFIXES[key]
        st     = result.get('status', 'pending')
        cnt    = result.get('count', 0)
        err    = result.get('error', u'')
        brush  = _ig_make_brush(st)

        getattr(self, 'IG_CardAccent' + suffix).BorderBrush = brush

        icon_el = getattr(self, 'IG_TxtIcon' + suffix)
        icon_el.Text       = _IG_STATUS_ICONS.get(st, u'○')
        icon_el.Foreground = brush

        status_el = getattr(self, 'IG_TxtStatus' + suffix)
        status_el.Text       = err if err else _IG_STATUS_LABELS.get(st, st)
        status_el.Foreground = brush

        count_el = getattr(self, 'IG_TxtCount' + suffix)
        if err:
            count_el.Text = u''
        elif cnt > 0:
            count_el.Text = u'{} issue{}'.format(cnt, u's' if cnt != 1 else u'')
        else:
            count_el.Text = u'No issues' if st == 'pass' else u''

    def _ig_show_details(self, key):
        self._ig_detail_rows.Clear()
        result = self._ig_results.get(key, {})
        label  = dict(_IG_CHECK_DEFS).get(key, key)
        cnt    = result.get('count', 0)
        err    = result.get('error', u'')

        for item in result.get('items', []):
            self._ig_detail_rows.Add(IGDetailRow(item))

        if err:
            self.IG_TxtDetailTitle.Text = u'{} — Error: {}'.format(label, err)
        elif cnt == 0:
            self.IG_TxtDetailTitle.Text = u'{} — No issues found'.format(label)
        else:
            self.IG_TxtDetailTitle.Text = u'{} — {} issue{}'.format(
                label, cnt, u's' if cnt != 1 else u'')

    def _ig_update_status_bar(self):
        if not self._ig_results:
            self.IG_TxtGateStatus.Text  = u'Run checks to validate the model before issue.'
            self.IG_BtnExport.IsEnabled = False
            return
        statuses = [r.get('status') for r in self._ig_results.values()]
        if 'fail' in statuses:
            self.IG_TxtGateStatus.Text  = u'FAIL — Critical issues found. Resolve before issuing.'
            self.IG_BtnExport.IsEnabled = False
        elif 'error' in statuses:
            self.IG_TxtGateStatus.Text  = u'ERROR — One or more checks could not run.'
            self.IG_BtnExport.IsEnabled = False
        elif 'warn' in statuses:
            self.IG_TxtGateStatus.Text  = u'WARN — Non-critical items need attention. Proceed with caution.'
            self.IG_BtnExport.IsEnabled = True
        else:
            self.IG_TxtGateStatus.Text  = u'PASS — All checks passed. Ready to export.'
            self.IG_BtnExport.IsEnabled = True

    def IG_RunChecks_Click(self, sender, args):
        self.SetLoading(True, u'Running pre-flight checks…')
        try:
            self._ig_results = _ig_logic.run_all(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error running checks:\n{}'.format(e), title=u'Issue Gate')
            return

        for key, _ in _IG_CHECK_DEFS:
            self._ig_update_card(key, self._ig_results.get(key, {'status': 'error', 'count': 0, 'items': []}))

        self._ig_update_status_bar()
        self.SetLoading(False)

        for key, _ in _IG_CHECK_DEFS:
            r = self._ig_results.get(key, {})
            if r.get('count', 0) > 0:
                self._ig_show_details(key)
                return
        self._ig_show_details('protocol')

    def IG_Card_Click(self, sender, args):
        key = str(sender.Tag) if sender.Tag else None
        if key:
            self._ig_show_details(key)

    def IG_SelectSheets_Click(self, sender, args):
        rows = list(self.IG_DetailGrid.SelectedItems or [])
        if not rows:
            rows = list(self._ig_detail_rows)
        numbers = set(r.SheetNumber for r in rows if r.SheetNumber)
        if not numbers:
            self.IG_TxtGateStatus.Text = u'No sheets to select — run checks first.'
            return
        try:
            ids = List[DB.ElementId]()
            for sheet in (DB.FilteredElementCollector(self.doc)
                          .OfClass(DB.ViewSheet).ToElements()):
                try:
                    if sheet.SheetNumber in numbers:
                        ids.Add(sheet.Id)
                except Exception:
                    log_swallowed(_LOG, u'IssueWorkflowHubWindow.IG_SelectSheets_Click')
            revit.uidoc.Selection.SetElementIds(ids)
            self.IG_TxtGateStatus.Text = u'Selected {} sheet(s) in the model.'.format(ids.Count)
        except Exception as e:
            self.IG_TxtGateStatus.Text = u'Selection failed: {}'.format(e)

    def IG_Export_Click(self, sender, args):
        self._save_shared_config()
        self.proceed_to_export = True
        self.Close()

    def IG_Close_Click(self, sender, args):
        self._save_shared_config()
        self.Close()

    # ══════════════════════════════════════════════════════════════════
    # STEP 3: REVISIONS  (ex. RevisionTracker)
    # ══════════════════════════════════════════════════════════════════

    def RT_NavBtn_Click(self, sender, args):
        name = sender.Name
        tab_map = {
            'RT_BtnTabRevisions': 0,
            'RT_BtnTabSheets':    1,
            'RT_BtnTabHistory':   2,
            'RT_BtnTabAutoRules': 3,
        }
        self._rt_current_tab = tab_map.get(name, 0)
        Vis = System.Windows.Visibility
        self.RT_TabRevisions.Visibility  = Vis.Visible if self._rt_current_tab == 0 else Vis.Collapsed
        self.RT_TabSheets.Visibility     = Vis.Visible if self._rt_current_tab == 1 else Vis.Collapsed
        self.RT_TabHistory.Visibility    = Vis.Visible if self._rt_current_tab == 2 else Vis.Collapsed
        self.RT_TabAutoRules.Visibility  = Vis.Visible if self._rt_current_tab == 3 else Vis.Collapsed

        self.RT_BtnTabRevisions.Tag  = 'Selected' if self._rt_current_tab == 0 else None
        self.RT_BtnTabSheets.Tag     = 'Selected' if self._rt_current_tab == 1 else None
        self.RT_BtnTabHistory.Tag    = 'Selected' if self._rt_current_tab == 2 else None
        self.RT_BtnTabAutoRules.Tag  = 'Selected' if self._rt_current_tab == 3 else None

        if self._rt_current_tab == 1:
            self._rt_load_sheets_for_selected_revision()

    # -- Sub-tab 0: Revisions --

    def _rt_load_revisions(self):
        self._rt_rev_items.Clear()
        self._rt_cbo_rev_items.Clear()
        revs = _rt_logic.get_all_revisions(self.doc)
        for r in revs:
            item = RTRevisionItem(r)
            self._rt_rev_items.Add(item)
            self._rt_cbo_rev_items.Add(RTCboRevItem(item))
        self.RT_TxtRevCount.Text = u'({} revisions)'.format(len(revs))
        if self._rt_cbo_rev_items:
            self.RT_CboRevision.SelectedIndex = 0

    def RT_RevisionGrid_SelectionChanged(self, sender, args):
        item = self.RT_GridRevisions.SelectedItem
        has  = item is not None
        self.RT_BtnIssueRev.IsEnabled   = has and not item.IsIssued
        self.RT_BtnUnissueRev.IsEnabled = has and item.IsIssued
        self.RT_BtnDeleteRev.IsEnabled  = has and not item.IsIssued
        self.RT_TxtRevActionStatus.Text = u''

    def RT_CreateRev_Click(self, sender, args):
        desc = (self.RT_TxtNewDesc.Text or u'').strip()
        if not desc:
            forms.alert(u'Enter a description for the revision.')
            return
        date      = (self.RT_TxtNewDate.Text     or u'').strip()
        issued_by = (self.RT_TxtNewIssuedBy.Text or u'').strip()
        issued_to = (self.RT_TxtNewIssuedTo.Text or u'').strip()
        try:
            _rt_logic.create_revision(self.doc, desc, date, issued_by, issued_to)
            self._rt_load_revisions()
            self.RT_TxtNewDesc.Text = u''
            self.RT_TxtRevActionStatus.Text = u'✅ Revision created.'
        except Exception as e:
            forms.alert(u'Could not create revision:\n{}'.format(e))

    def RT_IssueRev_Click(self, sender, args):
        item = self.RT_GridRevisions.SelectedItem
        if not item:
            return
        try:
            _rt_logic.set_issued(self.doc, item.Rev, True)
            self._rt_load_revisions()
            self.RT_TxtRevActionStatus.Text = u'✅ Revision issued.'
        except Exception as e:
            forms.alert(u'Could not issue revision:\n{}'.format(e))

    def RT_UnissueRev_Click(self, sender, args):
        item = self.RT_GridRevisions.SelectedItem
        if not item:
            return
        try:
            _rt_logic.set_issued(self.doc, item.Rev, False)
            self._rt_load_revisions()
            self.RT_TxtRevActionStatus.Text = u'↩ Revision reopened.'
        except Exception as e:
            forms.alert(u'Could not reopen revision:\n{}'.format(e))

    def RT_DeleteRev_Click(self, sender, args):
        item = self.RT_GridRevisions.SelectedItem
        if not item:
            return
        if not forms.alert(
            u'Delete revision "{}"?\nIf revision clouds are attached, '
            u'Revit will reject the operation.'.format(item.Description),
            yes=True, no=True
        ):
            return
        try:
            _rt_logic.delete_revision(self.doc, item.Rev)
            self._rt_load_revisions()
            self.RT_TxtRevActionStatus.Text = u'🗑 Revision deleted.'
        except Exception as e:
            forms.alert(u'Could not delete revision:\n{}'.format(e))

    # -- Sub-tab 1: Sheets --

    def RT_CboRevision_Changed(self, sender, args):
        self._rt_load_sheets_for_selected_revision()

    def _rt_load_sheets_for_selected_revision(self):
        cbo_item = self.RT_CboRevision.SelectedItem
        if cbo_item is None:
            return
        rev_id = cbo_item.RevItem.RevId
        self.SetLoading(True, u'Loading sheets…')
        try:
            pairs = _rt_logic.get_sheets_with_status(self.doc, rev_id)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error loading sheets:\n{}'.format(e))
            return
        self.SetLoading(False)
        self._rt_sheet_items.Clear()
        for sheet, has in pairs:
            self._rt_sheet_items.Add(RTSheetRevItem(sheet, has))
        assigned = sum(1 for s in self._rt_sheet_items if s.HasRevision)
        self.RT_TxtSheetStatus.Text = u'{} / {} sheets with this revision'.format(
            assigned, len(pairs))
        has_rev = cbo_item.RevItem is not None
        self.RT_BtnAddToSel.IsEnabled      = has_rev
        self.RT_BtnRemoveFromSel.IsEnabled = has_rev
        self.RT_BtnAutoAssign.IsEnabled    = has_rev

    def RT_AddToSelected_Click(self, sender, args):
        cbo_item = self.RT_CboRevision.SelectedItem
        if cbo_item is None:
            return
        selected = list(self.RT_GridSheets.SelectedItems)
        if not selected:
            forms.alert(u'Select sheets in the table (Ctrl+Click for multiple).')
            return
        rev_id    = cbo_item.RevItem.RevId
        sheet_ids = [s.SheetId for s in selected]
        try:
            count = _rt_logic.add_revision_to_sheets(self.doc, rev_id, sheet_ids)
            self._rt_load_sheets_for_selected_revision()
            self.RT_TxtSheetStatus.Text = u'✅ Revision added to {} sheet(s).'.format(count)
        except Exception as e:
            forms.alert(u'Error:\n{}'.format(e))

    def RT_RemoveFromSelected_Click(self, sender, args):
        cbo_item = self.RT_CboRevision.SelectedItem
        if cbo_item is None:
            return
        selected = list(self.RT_GridSheets.SelectedItems)
        if not selected:
            forms.alert(u'Select sheets in the table.')
            return
        rev_id    = cbo_item.RevItem.RevId
        sheet_ids = [s.SheetId for s in selected]
        try:
            count = _rt_logic.remove_revision_from_sheets(self.doc, rev_id, sheet_ids)
            self._rt_load_sheets_for_selected_revision()
            self.RT_TxtSheetStatus.Text = u'↩ Revision removed from {} sheet(s).'.format(count)
        except Exception as e:
            forms.alert(u'Error:\n{}'.format(e))

    def RT_AutoAssign_Click(self, sender, args):
        cbo_item = self.RT_CboRevision.SelectedItem
        if cbo_item is None:
            return
        prefix = (self.RT_TxtPrefix.Text or u'').strip()
        if not prefix:
            forms.alert(u'Enter a prefix (e.g. "S" for structural sheets).')
            return
        rev_id = cbo_item.RevItem.RevId
        if not forms.alert(
            u'Add revision "{}" to all sheets whose number starts with "{}"?'.format(
                cbo_item.RevItem.Description, prefix),
            yes=True, no=True
        ):
            return
        try:
            added, already = _rt_logic.auto_assign_by_prefix(self.doc, rev_id, prefix)
            self._rt_load_sheets_for_selected_revision()
            self.RT_TxtSheetStatus.Text = (
                u'✅ Added to {} sheet(s). {} already had it.'.format(added, already))
        except Exception as e:
            forms.alert(u'Error:\n{}'.format(e))

    # -- Sub-tab 2: History (snapshot diff) --

    def _rt_refresh_snapshots(self):
        self.RT_ListSnapshots.Items.Clear()
        for s in _rt_logic.list_snapshots():
            self.RT_ListSnapshots.Items.Add(RTSnapItem(s))

    def RT_Snapshot_SelectionChanged(self, sender, args):
        has = self.RT_ListSnapshots.SelectedItem is not None
        self.RT_BtnCompare.IsEnabled    = has
        self.RT_BtnDeleteSnap.IsEnabled = has

    def RT_TakeSnapshot_Click(self, sender, args):
        label = forms.ask_for_string(
            prompt=u'Snapshot label (e.g. Rev-C, IFC-2026):',
            title=u'New Snapshot')
        if label is None:
            return
        self.SetLoading(True, u'Taking snapshot…')
        try:
            _, lbl, n = _rt_logic.take_snapshot(self.doc, label.strip() or None)
            self._rt_refresh_snapshots()
            forms.alert(u'Snapshot saved: {}\n{} elements captured.'.format(lbl, n))
        except Exception as e:
            forms.alert(u'Error: {}'.format(e))
        finally:
            self.SetLoading(False)

    def RT_Compare_Click(self, sender, args):
        item = self.RT_ListSnapshots.SelectedItem
        if not item:
            return
        self.SetLoading(True, u'Comparing…')
        self._rt_delta_rows.Clear()
        self.RT_BtnExportDelta.IsEnabled = False
        try:
            snap             = _rt_logic.load_snapshot(item.File)
            self._rt_snap_data = _rt_logic.compare(self.doc, snap)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error: {}'.format(e))
            return

        s = self._rt_snap_data['summary']
        self.RT_TxtAdded.Text   = u'{} Added'.format(s['added'])
        self.RT_TxtRemoved.Text = u'{} Removed'.format(s['removed'])
        self.RT_TxtChanged.Text = u'{} Changed'.format(s['changed'])
        self.RT_TxtSnapInfo.Text = u'vs: {}'.format(item.Label)

        for r in self._rt_snap_data['added']:
            self._rt_delta_rows.Add(RTDeltaRow(u'ADDED', r))
        for r in self._rt_snap_data['removed']:
            self._rt_delta_rows.Add(RTDeltaRow(u'REMOVED', r))
        for r in self._rt_snap_data['changed']:
            params = u', '.join(r['diff_params'])
            loc    = u'position moved' if r['location_changed'] else u''
            detail = u' | '.join(x for x in [params, loc] if x)
            self._rt_delta_rows.Add(RTDeltaRow(u'CHANGED', r['current'], detail))

        self.SetLoading(False)
        self.RT_BtnExportDelta.IsEnabled = True

    def RT_DeleteSnap_Click(self, sender, args):
        item = self.RT_ListSnapshots.SelectedItem
        if not item:
            return
        _rt_logic.delete_snapshot(item.File)
        self._rt_refresh_snapshots()

    def RT_DeltaGrid_SelectionChanged(self, sender, args):
        self.RT_BtnSelect.IsEnabled = self.RT_GridDelta.SelectedItem is not None

    def RT_Select_Click(self, sender, args):
        row = self.RT_GridDelta.SelectedItem
        if not row or not row.Id:
            return
        try:
            ids = List[DB.ElementId]([element_id_from_int(row.Id)])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert(u'Could not select: {}'.format(e))

    def RT_ExportDelta_Click(self, sender, args):
        if not self._rt_snap_data:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            import io
            with io.open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
                w = csv.writer(f)
                w.writerow([u'Change', u'Category', u'Name', u'ID', u'Detail'])
                for r in self._rt_delta_rows:
                    w.writerow([r.ChangeType, r.Category, r.Name, r.Id, r.Detail])
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error exporting: {}'.format(e))

    # -- Sub-tab 3: Auto-assignment rules --

    def _rt_load_auto_rules_to_ui(self):
        title = self.doc.Title or ''
        self._rt_auto_rules = list(_rt_logic.load_auto_rules(title))
        self._rt_refresh_rules_grid()

    def _rt_refresh_rules_grid(self):
        self.RT_LstRules.Items.Clear()
        for rule in self._rt_auto_rules:
            self.RT_LstRules.Items.Add(
                u'{prefix}  →  {revision_desc}'.format(**rule))

    def RT_AddRule_Click(self, sender, args):
        prefix   = (self.RT_TxtRulePrefix.Text or '').strip()
        rev_desc = (self.RT_TxtRuleRevDesc.Text or '').strip()
        if not prefix:
            forms.alert(u'Enter a sheet number prefix (e.g. S, C, E).')
            return
        if not rev_desc:
            forms.alert(u'Enter a revision description (or the start of one).')
            return
        for r in self._rt_auto_rules:
            if r['prefix'].lower() == prefix.lower():
                forms.alert(u'A rule for prefix "{}" already exists. Remove it first.'.format(prefix))
                return
        self._rt_auto_rules.append({'prefix': prefix, 'revision_desc': rev_desc})
        self.RT_TxtRulePrefix.Text  = ''
        self.RT_TxtRuleRevDesc.Text = ''
        self._rt_refresh_rules_grid()

    def RT_RemoveRule_Click(self, sender, args):
        idx = self.RT_LstRules.SelectedIndex
        if idx < 0 or idx >= len(self._rt_auto_rules):
            return
        del self._rt_auto_rules[idx]
        self._rt_refresh_rules_grid()

    def RT_SaveRules_Click_AutoRules(self, sender, args):
        title = self.doc.Title or ''
        if _rt_logic.save_auto_rules(self._rt_auto_rules, title):
            forms.alert(u'{} rules saved.'.format(len(self._rt_auto_rules)))
        else:
            forms.alert(u'Could not save rules — check folder permissions.')

    def RT_ApplyRules_Click(self, sender, args):
        if not self._rt_auto_rules:
            forms.alert(u'No rules defined. Add at least one rule first.')
            return
        try:
            report = _rt_logic.apply_auto_rules(self.doc, self._rt_auto_rules)
        except Exception as e:
            forms.alert(u'Error: {}'.format(e))
            return
        lines = [u'Auto-assignment results:\n']
        for r in report:
            if r['error']:
                lines.append(u'  ✗ prefix "{prefix}": {error}'.format(**r))
            else:
                lines.append(u'  ✓ prefix "{prefix}" → "{revision_desc}": '
                             u'{assigned} assigned, {skipped} already set'.format(**r))
        forms.alert(u'\n'.join(lines))

    # ══════════════════════════════════════════════════════════════════
    # STEP 4: REVISION PACKAGE DIFF
    # ══════════════════════════════════════════════════════════════════

    def _rpd_refresh_baseline_label(self):
        if self._rpd_baseline:
            self.RPD_TxtBaselineInfo.Text = u'Baseline: {} — {} sheets'.format(
                self._rpd_baseline_ts or u'saved', len(self._rpd_baseline))
        else:
            self.RPD_TxtBaselineInfo.Text = u'No baseline saved. Click "Save Baseline" first.'

    def RPD_SaveBaseline_Click(self, sender, args):
        self.SetLoading(True, u'Capturing revision state…')
        try:
            self._rpd_baseline = _rpd_logic.snapshot_revisions(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error:\n{}'.format(e), title=u'Revision Package Diff')
            return
        self._rpd_baseline_ts = datetime.datetime.now().strftime(u'%Y-%m-%d %H:%M')
        self._save_shared_config()
        self.SetLoading(False)
        self._rpd_refresh_baseline_label()
        self._rpd_rows.Clear()
        self._rpd_diffs = []
        self.RPD_TxtResult.Text = u'Baseline saved — {} sheets.'.format(len(self._rpd_baseline))

    def RPD_Compare_Click(self, sender, args):
        if not self._rpd_baseline:
            forms.alert(u'Save a baseline first.', title=u'Revision Package Diff')
            return
        self.SetLoading(True, u'Comparing revisions…')
        try:
            current         = _rpd_logic.snapshot_revisions(self.doc)
            self._rpd_diffs = _rpd_logic.diff_snapshots(self._rpd_baseline, current)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error:\n{}'.format(e), title=u'Revision Package Diff')
            return
        self._rpd_rows.Clear()
        for r in self._rpd_diffs:
            self._rpd_rows.Add(RPDDiffRow(r))
        self.SetLoading(False)

        changed = [r for r in self._rpd_diffs if r['change'] != u'Unchanged']
        self.RPD_TxtResult.Text = u'{} sheet{} changed since baseline ({} new, {} revised, {} removed).'.format(
            len(changed), u's' if len(changed) != 1 else u'',
            sum(1 for r in changed if r['change'] == u'New Sheet'),
            sum(1 for r in changed if r['change'] == u'Revised'),
            sum(1 for r in changed if r['change'] == u'Removed'),
        )
        self.RPD_BtnExport.IsEnabled = len(changed) > 0

    def RPD_ShowAll_Checked(self, sender, args):
        self._rpd_rows.Clear()
        for r in self._rpd_diffs:
            self._rpd_rows.Add(RPDDiffRow(r))

    def RPD_ShowAll_Unchecked(self, sender, args):
        self._rpd_rows.Clear()
        for r in self._rpd_diffs:
            if r.get('change') != u'Unchanged':
                self._rpd_rows.Add(RPDDiffRow(r))

    def RPD_Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv', title=u'Save Transmittal List')
        if not path:
            return
        try:
            _rpd_logic.export_transmittal_csv(self._rpd_diffs, path)
            self.RPD_TxtResult.Text = u'Transmittal exported to {}'.format(os.path.basename(path))
        except Exception as e:
            forms.alert(u'Export failed:\n{}'.format(e), title=u'Revision Package Diff')

    def RPD_Close_Click(self, sender, args):
        self._save_shared_config()
        self.Close()

    # ══════════════════════════════════════════════════════════════════
    # STEP 5: ISSUE LOG  (ex. SheetIssueManager)
    # ══════════════════════════════════════════════════════════════════

    def _sim_load_sheets(self):
        try:
            sheets = _sim_logic.collect_sheets(self.doc)
            self.SIM_LstSheets.Items.Clear()
            for s in sheets:
                self.SIM_LstSheets.Items.Add(SIMSheetItem(s))
        except Exception as ex:
            self.SIM_TxtStatus.Text = u'Could not load sheets: {}'.format(ex)

    def _sim_refresh_grid(self):
        flt = self._sim_filter.lower().strip()
        rows = []
        for rec in self._sim_records:
            if flt and not any(flt in str(v).lower() for v in rec.values()):
                continue
            rows.append(SIMIssueRow(rec))
        self.SIM_GridLog.ItemsSource = rows
        total = len(self._sim_records)
        shown = len(rows)
        self.SIM_TxtTotal.Text = (
            u'{} issues'.format(total) if not flt
            else u'{} / {} shown'.format(shown, total))

    def _sim_update_status(self):
        self.SIM_TxtStatus.Text = u'{} issue records on file.'.format(len(self._sim_records))

    def _sim_save(self):
        _sim_logic.save_log(self._sim_records)

    def SIM_Search_GotFocus(self, sender, args):
        if self.SIM_TxtSearch.Text == _SEARCH_PLACEHOLDER:
            self.SIM_TxtSearch.Text = u''

    def SIM_Search_LostFocus(self, sender, args):
        if not self.SIM_TxtSearch.Text.strip():
            self.SIM_TxtSearch.Text = _SEARCH_PLACEHOLDER
            self._sim_filter = u''
            self._sim_refresh_grid()

    def SIM_Search_Changed(self, sender, args):
        txt = self.SIM_TxtSearch.Text
        if txt == _SEARCH_PLACEHOLDER:
            self._sim_filter = u''
        else:
            self._sim_filter = txt
        self._sim_refresh_grid()

    def SIM_LogIssue_Click(self, sender, args):
        selected = list(self.SIM_LstSheets.SelectedItems)
        if not selected:
            self.SIM_TxtFormStatus.Text = u'Select at least one sheet from the list.'
            return
        package   = self.SIM_TxtPackage.Text.strip()
        recipient = self.SIM_TxtRecipient.Text.strip()
        if not package or not recipient:
            self.SIM_TxtFormStatus.Text = u'Package / issue code and recipient are required.'
            return

        revision  = self.SIM_TxtRevision.Text.strip()
        issued_by = self.SIM_TxtIssuedBy.Text.strip()
        notes     = self.SIM_TxtNotes.Text.strip()

        sheet_numbers = []
        for item in selected:
            s = item.sheet
            rev = revision or _sim_logic.sheet_revision(s)
            sheet_numbers.append(u'{} (Rev {})'.format(s.SheetNumber, rev) if rev
                                 else s.SheetNumber)

        self._sim_records = _sim_logic.add_issue(
            self._sim_records, sheet_numbers, revision, recipient, package, notes, issued_by)
        self._sim_save()

        count = len(sheet_numbers)
        self.SIM_TxtFormStatus.Text = u'Logged {} sheet{} to "{}".'.format(
            count, u's' if count != 1 else u'', package)
        self.SIM_TxtPackage.Text   = u''
        self.SIM_TxtRecipient.Text = u''
        self.SIM_TxtRevision.Text  = u''
        self.SIM_TxtNotes.Text     = u''

        self._sim_refresh_grid()
        self._sim_update_status()

    def SIM_DeleteSelected_Click(self, sender, args):
        selected_rows = list(self.SIM_GridLog.SelectedItems)
        if not selected_rows:
            self.SIM_TxtStatus.Text = u'Select rows to delete.'
            return

        flt = self._sim_filter.lower().strip()
        filtered_records = [
            rec for rec in self._sim_records
            if not flt or any(flt in str(v).lower() for v in rec.values())
        ]

        selected_keys = set()
        for row in selected_rows:
            key = (row.Date, row.Sheet, row.Package, row.Recipient)
            selected_keys.add(key)

        indices_to_delete = set()
        for i, rec in enumerate(self._sim_records):
            key = (rec.get('date', u''), rec.get('sheet', u''),
                   rec.get('package', u''), rec.get('recipient', u''))
            if key in selected_keys:
                indices_to_delete.add(i)

        self._sim_records = _sim_logic.delete_records(self._sim_records, indices_to_delete)
        self._sim_save()
        self._sim_refresh_grid()
        self._sim_update_status()
        self.SIM_TxtStatus.Text = u'Deleted {} record{}.'.format(
            len(indices_to_delete), u's' if len(indices_to_delete) != 1 else u'')

    def SIM_ExportCsv_Click(self, sender, args):
        try:
            path = forms.save_file(
                file_ext=u'csv',
                default_name=u'sheet_issues.csv',
                title=u'Export issue log as CSV')
            if not path:
                return
            _sim_logic.export_csv(self._sim_records, path)
            self.SIM_TxtStatus.Text = u'Exported {} records to {}'.format(
                len(self._sim_records), os.path.basename(path))
        except Exception as ex:
            self.SIM_TxtStatus.Text = u'Export failed: {}'.format(ex)

    def SIM_Refresh_Click(self, sender, args):
        self._sim_records = _sim_logic.load_log()
        self._sim_refresh_grid()
        self._sim_update_status()

    def SIM_Close_Click(self, sender, args):
        self.Close()

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def _save_shared_config(self):
        self.SaveConfig({
            'dark_mode':     bool(self.ChkDarkMode.IsChecked),
            'rpd_baseline':    self._rpd_baseline,
            'rpd_baseline_ts': self._rpd_baseline_ts,
        })

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        self._save_shared_config()
