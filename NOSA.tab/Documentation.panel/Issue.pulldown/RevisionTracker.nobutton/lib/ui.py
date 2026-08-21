# -*- coding: utf-8 -*-
import imp
from Autodesk.Revit import DB
import os, sys, csv, datetime
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List
from pyrevit import forms, revit
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('revtrack_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


# ─────────────────────────────────────────────────────────────────────────────
# Data item classes
# ─────────────────────────────────────────────────────────────────────────────

class RevisionItem(object):
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


class SheetRevItem(object):
    """Wraps a ViewSheet + has-revision flag for DataGrid binding."""
    def __init__(self, sheet, has_rev):
        self.SheetId         = sheet.Id
        self.Number          = sheet.SheetNumber or u''
        self.Name            = sheet.Name        or u''
        self.HasRevision     = has_rev
        self.HasRevisionText = u'✅' if has_rev else u'—'
        # Derive discipline from sheet number prefix (letters before first digit/dash)
        prefix = u''
        for ch in self.Number:
            if ch.isalpha():
                prefix += ch
            else:
                break
        self.Discipline = prefix or u'—'


class CboRevItem(object):
    """Simple label wrapper for the revision ComboBox in Tab 2."""
    def __init__(self, rev_item):
        self.RevItem = rev_item
        self.Label   = u'{} — {}'.format(rev_item.Sequence, rev_item.Description)

    def __str__(self):
        return self.Label


class SnapItem(object):
    def __init__(self, d):
        self.File  = d['file']
        self.Label = d['label']
        self.Ts    = d['ts']
        self.Count = d['count']

    def __str__(self):
        return u'{} ({} elem.)'.format(self.Label, self.Count)


class DeltaRow(object):
    def __init__(self, change_type, entry, detail=u''):
        self.ChangeType = change_type
        self.Category   = entry.get('category', u'')
        self.Name       = entry.get('name', u'') or entry.get('type', u'')
        self.Id         = entry.get('id', u'')
        self.Detail     = detail


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

class RevisionTrackerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'revision_tracker')
        self.doc          = doc
        self._current_tab = 0

        # Tab 0 state
        self._rev_items  = ObservableCollection[RevisionItem]()
        self.GridRevisions.ItemsSource = self._rev_items

        # Tab 1 state
        self._sheet_items = ObservableCollection[SheetRevItem]()
        self.GridSheets.ItemsSource = self._sheet_items
        self._cbo_rev_items = ObservableCollection[CboRevItem]()
        self.CboRevision.ItemsSource = self._cbo_rev_items

        # Tab 2 state
        self._delta_rows = ObservableCollection[DeltaRow]()
        self.GridDelta.ItemsSource = self._delta_rows
        self._snap_data  = None

        # Tab 3 state — Auto-rules
        self._auto_rules = []  # list of {'prefix': str, 'revision_desc': str}

        # Default date in create form
        self.TxtNewDate.Text = datetime.date.today().strftime('%d/%m/%Y')

        self._load_revisions()
        self._refresh_snapshots()
        self._load_auto_rules_to_ui()

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    # ── navigation ─────────────────────────────────────────────────────────

    def NavBtn_Click(self, sender, args):
        name = sender.Name
        tab_map = {
            'BtnTabRevisions': 0,
            'BtnTabSheets':    1,
            'BtnTabHistory':   2,
            'BtnTabAutoRules': 3,
        }
        self._current_tab = tab_map.get(name, 0)
        Vis = System.Windows.Visibility
        self.TabRevisions.Visibility  = Vis.Visible if self._current_tab == 0 else Vis.Collapsed
        self.TabSheets.Visibility     = Vis.Visible if self._current_tab == 1 else Vis.Collapsed
        self.TabHistory.Visibility    = Vis.Visible if self._current_tab == 2 else Vis.Collapsed
        self.TabAutoRules.Visibility  = Vis.Visible if self._current_tab == 3 else Vis.Collapsed

        self.BtnTabRevisions.Tag  = 'Selected' if self._current_tab == 0 else None
        self.BtnTabSheets.Tag     = 'Selected' if self._current_tab == 1 else None
        self.BtnTabHistory.Tag    = 'Selected' if self._current_tab == 2 else None
        self.BtnTabAutoRules.Tag  = 'Selected' if self._current_tab == 3 else None

        if self._current_tab == 1:
            self._load_sheets_for_selected_revision()

    # ── Tab 0: Revisiones ──────────────────────────────────────────────────

    def _load_revisions(self):
        self._rev_items.Clear()
        self._cbo_rev_items.Clear()
        revs = _logic.get_all_revisions(self.doc)
        for r in revs:
            item = RevisionItem(r)
            self._rev_items.Add(item)
            self._cbo_rev_items.Add(CboRevItem(item))
        self.TxtRevCount.Text = u'({} revisions)'.format(len(revs))
        if self._cbo_rev_items:
            self.CboRevision.SelectedIndex = 0

    def RevisionGrid_SelectionChanged(self, sender, args):
        item = self.GridRevisions.SelectedItem
        has  = item is not None
        self.BtnIssueRev.IsEnabled   = has and not item.IsIssued
        self.BtnUnissueRev.IsEnabled = has and item.IsIssued
        self.BtnDeleteRev.IsEnabled  = has and not item.IsIssued
        self.TxtRevActionStatus.Text = u''

    def CreateRev_Click(self, sender, args):
        desc = (self.TxtNewDesc.Text or u'').strip()
        if not desc:
            forms.alert(u'Enter a description for the revision.')
            return
        date      = (self.TxtNewDate.Text     or u'').strip()
        issued_by = (self.TxtNewIssuedBy.Text or u'').strip()
        issued_to = (self.TxtNewIssuedTo.Text or u'').strip()
        try:
            _logic.create_revision(self.doc, desc, date, issued_by, issued_to)
            self._load_revisions()
            self.TxtNewDesc.Text = u''
            self.TxtRevActionStatus.Text = u'✅ Revision created.'
        except Exception as e:
            forms.alert(u'Could not create revision:\n{}'.format(e))

    def IssueRev_Click(self, sender, args):
        item = self.GridRevisions.SelectedItem
        if not item:
            return
        try:
            _logic.set_issued(self.doc, item.Rev, True)
            self._load_revisions()
            self.TxtRevActionStatus.Text = u'✅ Revision issued.'
        except Exception as e:
            forms.alert(u'Could not issue revision:\n{}'.format(e))

    def UnissueRev_Click(self, sender, args):
        item = self.GridRevisions.SelectedItem
        if not item:
            return
        try:
            _logic.set_issued(self.doc, item.Rev, False)
            self._load_revisions()
            self.TxtRevActionStatus.Text = u'↩ Revision reopened.'
        except Exception as e:
            forms.alert(u'Could not reopen revision:\n{}'.format(e))

    def DeleteRev_Click(self, sender, args):
        item = self.GridRevisions.SelectedItem
        if not item:
            return
        if not forms.alert(
            u'Delete revision "{}"?\nIf revision clouds are attached, '
            u'Revit will reject the operation.'.format(item.Description),
            yes=True, no=True
        ):
            return
        try:
            _logic.delete_revision(self.doc, item.Rev)
            self._load_revisions()
            self.TxtRevActionStatus.Text = u'🗑 Revision deleted.'
        except Exception as e:
            forms.alert(u'Could not delete revision:\n{}'.format(e))

    # ── Tab 1: Hojas ────────────────────────────────────────────────────────

    def CboRevision_Changed(self, sender, args):
        self._load_sheets_for_selected_revision()

    def _load_sheets_for_selected_revision(self):
        cbo_item = self.CboRevision.SelectedItem
        if cbo_item is None:
            return
        rev_id = cbo_item.RevItem.RevId
        self.SetLoading(True, u'Loading sheets…')
        try:
            pairs = _logic.get_sheets_with_status(self.doc, rev_id)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error loading sheets:\n{}'.format(e))
            return
        self.SetLoading(False)
        self._sheet_items.Clear()
        for sheet, has in pairs:
            self._sheet_items.Add(SheetRevItem(sheet, has))
        assigned = sum(1 for s in self._sheet_items if s.HasRevision)
        self.TxtSheetStatus.Text = u'{} / {} sheets with this revision'.format(
            assigned, len(pairs))
        has_rev = cbo_item.RevItem is not None
        self.BtnAddToSel.IsEnabled      = has_rev
        self.BtnRemoveFromSel.IsEnabled = has_rev
        self.BtnAutoAssign.IsEnabled    = has_rev

    def AddToSelected_Click(self, sender, args):
        cbo_item = self.CboRevision.SelectedItem
        if cbo_item is None:
            return
        selected = list(self.GridSheets.SelectedItems)
        if not selected:
            forms.alert(u'Select sheets in the table (Ctrl+Click for multiple).')
            return
        rev_id    = cbo_item.RevItem.RevId
        sheet_ids = [s.SheetId for s in selected]
        try:
            count = _logic.add_revision_to_sheets(self.doc, rev_id, sheet_ids)
            self._load_sheets_for_selected_revision()
            self.TxtSheetStatus.Text = u'✅ Revision added to {} sheet(s).'.format(count)
        except Exception as e:
            forms.alert(u'Error:\n{}'.format(e))

    def RemoveFromSelected_Click(self, sender, args):
        cbo_item = self.CboRevision.SelectedItem
        if cbo_item is None:
            return
        selected = list(self.GridSheets.SelectedItems)
        if not selected:
            forms.alert(u'Select sheets in the table.')
            return
        rev_id    = cbo_item.RevItem.RevId
        sheet_ids = [s.SheetId for s in selected]
        try:
            count = _logic.remove_revision_from_sheets(self.doc, rev_id, sheet_ids)
            self._load_sheets_for_selected_revision()
            self.TxtSheetStatus.Text = u'↩ Revision removed from {} sheet(s).'.format(count)
        except Exception as e:
            forms.alert(u'Error:\n{}'.format(e))

    def AutoAssign_Click(self, sender, args):
        cbo_item = self.CboRevision.SelectedItem
        if cbo_item is None:
            return
        prefix = (self.TxtPrefix.Text or u'').strip()
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
            added, already = _logic.auto_assign_by_prefix(self.doc, rev_id, prefix)
            self._load_sheets_for_selected_revision()
            self.TxtSheetStatus.Text = (
                u'✅ Added to {} sheet(s). {} already had it.'.format(added, already))
        except Exception as e:
            forms.alert(u'Error:\n{}'.format(e))

    # ── Tab 2: Historial ────────────────────────────────────────────────────

    def _refresh_snapshots(self):
        self.ListSnapshots.Items.Clear()
        for s in _logic.list_snapshots():
            self.ListSnapshots.Items.Add(SnapItem(s))

    def Snapshot_SelectionChanged(self, sender, args):
        has = self.ListSnapshots.SelectedItem is not None
        self.BtnCompare.IsEnabled    = has
        self.BtnDeleteSnap.IsEnabled = has

    def TakeSnapshot_Click(self, sender, args):
        label = forms.ask_for_string(
            prompt=u'Snapshot label (e.g. Rev-C, IFC-2026):',
            title=u'New Snapshot')
        if label is None:
            return
        self.SetLoading(True, u'Taking snapshot…')
        try:
            _, lbl, n = _logic.take_snapshot(self.doc, label.strip() or None)
            self._refresh_snapshots()
            forms.alert(u'Snapshot saved: {}\n{} elements captured.'.format(lbl, n))
        except Exception as e:
            forms.alert(u'Error: {}'.format(e))
        finally:
            self.SetLoading(False)

    def Compare_Click(self, sender, args):
        item = self.ListSnapshots.SelectedItem
        if not item:
            return
        self.SetLoading(True, u'Comparing…')
        self._delta_rows.Clear()
        self.BtnExportDelta.IsEnabled = False
        try:
            snap         = _logic.load_snapshot(item.File)
            self._snap_data = _logic.compare(self.doc, snap)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error: {}'.format(e))
            return

        s = self._snap_data['summary']
        self.TxtAdded.Text   = u'{} Added'.format(s['added'])
        self.TxtRemoved.Text = u'{} Removed'.format(s['removed'])
        self.TxtChanged.Text = u'{} Changed'.format(s['changed'])
        self.TxtSnapInfo.Text = u'vs: {}'.format(item.Label)

        for r in self._snap_data['added']:
            self._delta_rows.Add(DeltaRow(u'ADDED', r))
        for r in self._snap_data['removed']:
            self._delta_rows.Add(DeltaRow(u'REMOVED', r))
        for r in self._snap_data['changed']:
            params = u', '.join(r['diff_params'])
            loc    = u'position moved' if r['location_changed'] else u''
            detail = u' | '.join(x for x in [params, loc] if x)
            self._delta_rows.Add(DeltaRow(u'CHANGED', r['current'], detail))

        self.SetLoading(False)
        self.BtnExportDelta.IsEnabled = True

    def DeleteSnap_Click(self, sender, args):
        item = self.ListSnapshots.SelectedItem
        if not item:
            return
        _logic.delete_snapshot(item.File)
        self._refresh_snapshots()

    def DeltaGrid_SelectionChanged(self, sender, args):
        self.BtnSelect.IsEnabled = self.GridDelta.SelectedItem is not None

    def Select_Click(self, sender, args):
        row = self.GridDelta.SelectedItem
        if not row or not row.Id:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(int(row.Id))])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert(u'Could not select: {}'.format(e))

    def ExportDelta_Click(self, sender, args):
        if not self._snap_data:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            import io
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow([u'Change', u'Category', u'Name', u'ID', u'Detail'])
                for r in self._delta_rows:
                    w.writerow([r.ChangeType, r.Category, r.Name, r.Id, r.Detail])
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error exporting: {}'.format(e))

    # ── Tab 3: Auto-assignment Rules ────────────────────────────────────────

    def _load_auto_rules_to_ui(self):
        title = self.doc.Title or ''
        self._auto_rules = list(_logic.load_auto_rules(title))
        self._refresh_rules_grid()

    def _refresh_rules_grid(self):
        self.LstRules.Items.Clear()
        for rule in self._auto_rules:
            self.LstRules.Items.Add(
                u'{prefix}  →  {revision_desc}'.format(**rule))

    def AddRule_Click(self, sender, args):
        prefix   = (self.TxtRulePrefix.Text or '').strip()
        rev_desc = (self.TxtRuleRevDesc.Text or '').strip()
        if not prefix:
            forms.alert(u'Enter a sheet number prefix (e.g. S, C, E).')
            return
        if not rev_desc:
            forms.alert(u'Enter a revision description (or the start of one).')
            return
        # Avoid duplicates
        for r in self._auto_rules:
            if r['prefix'].lower() == prefix.lower():
                forms.alert(u'A rule for prefix "{}" already exists. Remove it first.'.format(prefix))
                return
        self._auto_rules.append({'prefix': prefix, 'revision_desc': rev_desc})
        self.TxtRulePrefix.Text  = ''
        self.TxtRuleRevDesc.Text = ''
        self._refresh_rules_grid()

    def RemoveRule_Click(self, sender, args):
        idx = self.LstRules.SelectedIndex
        if idx < 0 or idx >= len(self._auto_rules):
            return
        del self._auto_rules[idx]
        self._refresh_rules_grid()

    def SaveRules_Click_AutoRules(self, sender, args):
        title = self.doc.Title or ''
        if _logic.save_auto_rules(self._auto_rules, title):
            forms.alert(u'{} rules saved.'.format(len(self._auto_rules)))
        else:
            forms.alert(u'Could not save rules — check folder permissions.')

    def ApplyRules_Click(self, sender, args):
        if not self._auto_rules:
            forms.alert(u'No rules defined. Add at least one rule first.')
            return
        try:
            report = _logic.apply_auto_rules(self.doc, self._auto_rules)
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

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)





