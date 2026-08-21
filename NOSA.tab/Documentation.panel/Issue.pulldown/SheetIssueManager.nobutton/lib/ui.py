# -*- coding: utf-8 -*-
import imp
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('sheetissuemanager_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))

_SEARCH_PLACEHOLDER = u'Search issues…'


class _IssueRow(object):
    def __init__(self, rec):
        self.Date      = rec.get('date', u'')
        self.Sheet     = rec.get('sheet', u'')
        self.Revision  = rec.get('revision', u'')
        self.Package   = rec.get('package', u'')
        self.Recipient = rec.get('recipient', u'')
        self.IssuedBy  = rec.get('issued_by', u'')
        self.Notes     = rec.get('notes', u'')


class _SheetItem(object):
    def __init__(self, sheet):
        self.sheet = sheet
        self.Display = u'{} — {}'.format(sheet.SheetNumber, sheet.Name)


class SheetIssueManagerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'sheet_issue_manager')
        self.doc = doc
        self._records = _logic.load_log()
        self._filter = u''

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self.TxtSearch.Text = _SEARCH_PLACEHOLDER
        self._load_sheets()
        self._refresh_grid()
        self._update_status()

    def _load_sheets(self):
        try:
            sheets = _logic.collect_sheets(self.doc)
            self.LstSheets.Items.Clear()
            for s in sheets:
                self.LstSheets.Items.Add(_SheetItem(s))
        except Exception as ex:
            self.TxtStatus.Text = u'Could not load sheets: {}'.format(ex)

    def _refresh_grid(self):
        flt = self._filter.lower().strip()
        rows = []
        for rec in self._records:
            if flt and not any(flt in str(v).lower() for v in rec.values()):
                continue
            rows.append(_IssueRow(rec))
        self.GridLog.ItemsSource = rows
        total = len(self._records)
        shown = len(rows)
        self.TxtTotal.Text = (
            u'{} issues'.format(total) if not flt
            else u'{} / {} shown'.format(shown, total))

    def _update_status(self):
        self.TxtStatus.Text = u'{} issue records on file.'.format(len(self._records))

    def _save(self):
        _logic.save_log(self._records)

    # ── Events ──────────────────────────────────────────────────────────────

    def Search_GotFocus(self, sender, args):
        if self.TxtSearch.Text == _SEARCH_PLACEHOLDER:
            self.TxtSearch.Text = u''

    def Search_LostFocus(self, sender, args):
        if not self.TxtSearch.Text.strip():
            self.TxtSearch.Text = _SEARCH_PLACEHOLDER
            self._filter = u''
            self._refresh_grid()

    def Search_Changed(self, sender, args):
        txt = self.TxtSearch.Text
        if txt == _SEARCH_PLACEHOLDER:
            self._filter = u''
        else:
            self._filter = txt
        self._refresh_grid()

    def LogIssue_Click(self, sender, args):
        selected = list(self.LstSheets.SelectedItems)
        if not selected:
            self.TxtFormStatus.Text = u'Select at least one sheet from the list.'
            return
        package   = self.TxtPackage.Text.strip()
        recipient = self.TxtRecipient.Text.strip()
        if not package or not recipient:
            self.TxtFormStatus.Text = u'Package / issue code and recipient are required.'
            return

        revision = self.TxtRevision.Text.strip()
        issued_by = self.TxtIssuedBy.Text.strip()
        notes     = self.TxtNotes.Text.strip()

        sheet_numbers = []
        for item in selected:
            s = item.sheet
            rev = revision or _logic.sheet_revision(s)
            sheet_numbers.append(u'{} (Rev {})'.format(s.SheetNumber, rev) if rev
                                 else s.SheetNumber)

        self._records = _logic.add_issue(
            self._records, sheet_numbers, revision, recipient, package, notes, issued_by)
        self._save()

        count = len(sheet_numbers)
        self.TxtFormStatus.Text = u'Logged {} sheet{} to "{}".'.format(
            count, u's' if count != 1 else u'', package)
        self.TxtPackage.Text   = u''
        self.TxtRecipient.Text = u''
        self.TxtRevision.Text  = u''
        self.TxtNotes.Text     = u''

        self._refresh_grid()
        self._update_status()

    def DeleteSelected_Click(self, sender, args):
        selected_rows = list(self.GridLog.SelectedItems)
        if not selected_rows:
            self.TxtStatus.Text = u'Select rows to delete.'
            return

        flt = self._filter.lower().strip()
        filtered_records = [
            rec for rec in self._records
            if not flt or any(flt in str(v).lower() for v in rec.values())
        ]

        selected_keys = set()
        for row in selected_rows:
            key = (row.Date, row.Sheet, row.Package, row.Recipient)
            selected_keys.add(key)

        indices_to_delete = set()
        for i, rec in enumerate(self._records):
            key = (rec.get('date', u''), rec.get('sheet', u''),
                   rec.get('package', u''), rec.get('recipient', u''))
            if key in selected_keys:
                indices_to_delete.add(i)

        self._records = _logic.delete_records(self._records, indices_to_delete)
        self._save()
        self._refresh_grid()
        self._update_status()
        self.TxtStatus.Text = u'Deleted {} record{}.'.format(
            len(indices_to_delete), u's' if len(indices_to_delete) != 1 else u'')

    def ExportCsv_Click(self, sender, args):
        try:
            from pyrevit import forms as _forms
            path = _forms.save_file(
                file_ext=u'csv',
                default_name=u'sheet_issues.csv',
                title=u'Export issue log as CSV')
            if not path:
                return
            _logic.export_csv(self._records, path)
            self.TxtStatus.Text = u'Exported {} records to {}'.format(
                len(self._records), os.path.basename(path))
        except Exception as ex:
            self.TxtStatus.Text = u'Export failed: {}'.format(ex)

    def Refresh_Click(self, sender, args):
        self._records = _logic.load_log()
        self._refresh_grid()
        self._update_status()

    def Close_Click(self, sender, args):
        self.Close()
