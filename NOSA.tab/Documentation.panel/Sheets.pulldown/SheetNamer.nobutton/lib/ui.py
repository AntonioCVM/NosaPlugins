# -*- coding: utf-8 -*-
import os
import sys
import re

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.bootstrap import load_module
_logic = load_module('sheetnamer_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

from nosa_utils.base_window import NOSAWindow
from Autodesk.Revit import DB
from System.Collections.ObjectModel import ObservableCollection


class BulkSheetRow(object):
    _STATUS_COLOURS = {
        'ok':     '#E8F5E9',
        'change': '#FFF3E0',
        'error':  '#FFEBEE',
    }

    def __init__(self, sheet_dict, suggestion):
        self.Selected      = suggestion.get('status') == 'change'
        self._sheet_id     = sheet_dict['id']
        self.CurrentNumber = sheet_dict['number']
        self.SheetName     = sheet_dict['name']
        self.F1 = suggestion['f1']
        self.F3 = suggestion['f3']
        self.F4 = suggestion['f4']
        self.F5 = suggestion['f5']
        self.F6 = suggestion['f6']
        self.F7 = suggestion['f7']
        self.F8 = suggestion['f8']
        self.Status       = suggestion['status']
        self.StatusLabel  = suggestion['status_label']
        self.Message      = suggestion['message']
        self.RowBrush     = BulkSheetRow._STATUS_COLOURS.get(self.Status, '#FFFFFF')

    @property
    def NewNumber(self):
        try:
            return _logic.build_sheet_number(
                self.F1, self.F3, self.F4, self.F5, self.F6, self.F7, self.F8)
        except Exception:
            return u''

    def refresh_status(self, existing_numbers):
        errors = _logic.validate_fields(
            self.F1, self.F3, self.F4, self.F5, self.F6, self.F7, self.F8)
        new_num = self.NewNumber
        if errors:
            self.Status = 'error'
            self.StatusLabel = u'Error'
            self.Message = u'; '.join(errors)
        elif new_num != self.CurrentNumber:
            self.Status = 'change'
            self.StatusLabel = u'Suggested change'
            self.Message = u'Proposed number differs from current.'
        elif _logic.parse_nosa_number(self.CurrentNumber):
            self.Status = 'ok'
            self.StatusLabel = u'OK'
            self.Message = u'Compliant with NOSA v2.2.'
        else:
            self.Status = 'change'
            self.StatusLabel = u'Suggested change'
            self.Message = u'Current number is not NOSA format.'
        if existing_numbers and new_num in existing_numbers and new_num != self.CurrentNumber:
            self.Status = 'error'
            self.StatusLabel = u'Error'
            self.Message = u'Duplicate sheet number.'
        self.RowBrush = BulkSheetRow._STATUS_COLOURS.get(self.Status, '#FFFFFF')


class ParseSheetRow(object):
    def __init__(self, sheet_dict):
        self.Selected  = False
        self._sheet_id = sheet_dict['id']
        self.Original  = sheet_dict['number']
        self.SheetName = sheet_dict['name']
        # Parse
        parts = self.Original.split()
        self.F1 = parts[0] if len(parts) > 0 else ''
        self.F3 = parts[2] if len(parts) > 2 else ''
        self.F4 = parts[3] if len(parts) > 3 else ''
        self.F5 = parts[4] if len(parts) > 4 else ''
        self.F6 = parts[5] if len(parts) > 5 else ''
        self.F7 = parts[6] if len(parts) > 6 else ''
        self.F8 = parts[7] if len(parts) > 7 else ''

    @property
    def Generated(self):
        try:
            return _logic.build_sheet_number(
                self.F1, self.F3, self.F4, self.F5, self.F6, self.F7, self.F8)
        except Exception:
            return u''


class SheetNamerWindow(NOSAWindow):

    _NOSA_PATTERN = re.compile(r'^\d{5}\s+NOSA\s+\w{2}\s+\w{3}\s+\w\s+\w\s+\d{4}\s+\w+')

    def __init__(self, doc, uidoc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'sheet_namer')
        self.doc   = doc
        self.uidoc = uidoc
        self._bulk_rows  = ObservableCollection[BulkSheetRow]()
        self._parse_rows = ObservableCollection[ParseSheetRow]()
        self._bulk_preview_reviewed = False
        try:
            cfg = self.LoadConfig()
            self.ApplyTheme(cfg.get('dark_mode', False))
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
            self._populate_combos(cfg)
            self._update_preview()
            self._show_tab('Build')
        except Exception as e:
            from pyrevit import forms
            forms.alert(u'Sheet Namer init error:\n{}'.format(e), title='Error')

    # ------------------------------------------------------------------
    def _populate_combos(self, cfg):
        self.CmbF3.Items.Clear()
        for code, desc in _logic.F3_CODES:
            self.CmbF3.Items.Add(u'{} — {}'.format(code, desc))
        self.CmbF3.SelectedIndex = self._index_of_code(
            self.CmbF3, cfg.get('f3', 'GA'))

        self.CmbF4.Items.Clear()
        for code, desc in _logic.F4_PRESETS:
            self.CmbF4.Items.Add(u'{} — {}'.format(code, desc))
        self.CmbF4.Text = cfg.get('f4', 'ZZZ')

        self.CmbF5.Items.Clear()
        for code, desc in _logic.F5_CODES:
            self.CmbF5.Items.Add(u'{} — {}'.format(code, desc))
        self.CmbF5.SelectedIndex = self._index_of_code(
            self.CmbF5, cfg.get('f5', 'D'))

        self.CmbF6.Items.Clear()
        for code, desc in _logic.F6_CODES:
            self.CmbF6.Items.Add(u'{} — {}'.format(code, desc))
        self.CmbF6.SelectedIndex = self._index_of_code(
            self.CmbF6, cfg.get('f6', 'S'))

        self.CmbF8.Items.Clear()
        for rev in _logic.F8_STAGES:
            self.CmbF8.Items.Add(rev)
        self.CmbF8.Text = cfg.get('f8', 'P01')

        self.TxtF1.Text = cfg.get('f1', '')
        self.TxtF7.Text = cfg.get('f7', '2200')
        self.TxtF9.Text = u''

    @staticmethod
    def _index_of_code(cmb, code):
        for i in range(cmb.Items.Count):
            if str(cmb.Items[i]).startswith(code):
                return i
        return 0

    def _get_f_values(self):
        f1 = (self.TxtF1.Text or u'').strip()
        f3 = (str(self.CmbF3.SelectedItem) or u'').split(u' ')[0] if self.CmbF3.SelectedItem else u''
        raw_f4 = (self.CmbF4.Text or u'').strip()
        f4 = raw_f4.split(u' ')[0] if raw_f4 else u''
        f5 = (str(self.CmbF5.SelectedItem) or u'').split(u' ')[0] if self.CmbF5.SelectedItem else u''
        f6 = (str(self.CmbF6.SelectedItem) or u'').split(u' ')[0] if self.CmbF6.SelectedItem else u''
        f7 = (self.TxtF7.Text or u'').strip()
        raw_f8 = (self.CmbF8.Text or u'').strip()
        f8 = raw_f8.split(u' ')[0] if raw_f8 else u''
        f9 = (self.TxtF9.Text or u'').strip()
        return f1, f3, f4, f5, f6, f7, f8, f9

    def _update_preview(self):
        try:
            f1, f3, f4, f5, f6, f7, f8, f9 = self._get_f_values()
            errors = _logic.validate_fields(f1, f3, f4, f5, f6, f7, f8)
            if errors:
                self.TxtPreviewNumber.Text = u''
                self.TxtValidation.Text = u'  ·  '.join(errors)
            else:
                num = _logic.build_sheet_number(f1, f3, f4, f5, f6, f7, f8)
                existing = _logic.get_existing_numbers(self.doc)
                self.TxtPreviewNumber.Text = num
                warn = u'⚠ Duplicate: another sheet already has this number.' \
                       if num in existing else u''
                self.TxtValidation.Text = warn
            self.TxtPreviewName.Text = f9
        except Exception as e:
            self.TxtValidation.Text = str(e)

    def _get_target_sheets(self):
        sheets = _logic.get_all_sheets(self.doc)
        if self.RbActiveSheet.IsChecked:
            av = self.uidoc.ActiveView
            if av and isinstance(av, DB.ViewSheet):
                return [s for s in sheets if s['id'] == av.Id]
            return []
        if self.RbAllSheets.IsChecked:
            return sheets
        # Selected in bulk grid
        return [row._sheet_id for row in self._bulk_rows if row.Selected]

    def _apply(self, apply_number, apply_name):
        f1, f3, f4, f5, f6, f7, f8, f9 = self._get_f_values()
        errors = _logic.validate_fields(f1, f3, f4, f5, f6, f7, f8)
        if errors:
            self.LogLine(u'Validation: ' + u'; '.join(errors))
            return

        num = _logic.build_sheet_number(f1, f3, f4, f5, f6, f7, f8)
        targets = self._get_target_sheets()
        if not targets:
            self.LogLine(u'No target sheets found.')
            return

        ok = fail = 0
        with DB.Transaction(self.doc, u'NOSA — Sheet Namer') as t:
            t.Start()
            for s in targets:
                sid = s['id'] if isinstance(s, dict) else s
                sheet = self.doc.GetElement(sid)
                if sheet is None:
                    fail += 1
                    continue
                try:
                    if apply_number:
                        applied, _, _ = _logic.apply_nosa_to_sheet(
                            self.doc, sheet, f1, f3, f4, f5, f6, f7, f8,
                            new_number=num)
                        if not applied:
                            fail += 1
                            continue
                    if apply_name and f9:
                        sheet.Name = f9
                    ok += 1
                except Exception as e:
                    self.LogLine(u'  Error on sheet {}: {}'.format(
                        sheet.SheetNumber, e))
                    fail += 1
            t.Commit()

        self.LogLine(u'Applied to {} sheet(s). {} error(s).'.format(ok, fail))
        self._save_config(f1, f3, f4, f5, f6, f7, f8)

    def _save_config(self, f1, f3, f4, f5, f6, f7, f8):
        cfg = self.LoadConfig()
        cfg.update({'f1': f1, 'f3': f3, 'f4': f4, 'f5': f5,
                    'f6': f6, 'f7': f7, 'f8': f8,
                    'dark_mode': self.dark_mode})
        self.SaveConfig(cfg)

    # ------------------------------------------------------------------
    # Tab switching
    def _show_tab(self, tab):
        from System.Windows import Visibility
        tabs = {'Build': self.PanelBuild,
                'Bulk':  self.PanelBulk,
                'Parse': self.PanelParse}
        btns = {'Build': self.BtnTabBuild,
                'Bulk':  self.BtnTabBulk,
                'Parse': self.BtnTabParse}
        from System.Windows.Media import Brushes
        import System.Windows.Media as WM
        for k, p in tabs.items():
            p.Visibility = Visibility.Visible if k == tab else Visibility.Collapsed
        for k, b in btns.items():
            if k == tab:
                b.Background = WM.SolidColorBrush(WM.Color.FromRgb(255, 95, 0))
                b.Foreground = Brushes.White
            else:
                b.Background = Brushes.Transparent
                b.Foreground = WM.SolidColorBrush(WM.Color.FromRgb(51, 51, 51))

    # ------------------------------------------------------------------
    # Event handlers
    def Tab_Click(self, sender, args):
        tag = sender.Tag
        self._show_tab(str(tag))
        if str(tag) == 'Bulk':
            self._populate_bulk()
        elif str(tag) == 'Parse':
            self._populate_parse()

    def Field_Changed(self, sender, args):
        self._update_preview()

    def ApplyNumber_Click(self, sender, args):
        self._apply(apply_number=True, apply_name=False)

    def ApplyName_Click(self, sender, args):
        self._apply(apply_number=False, apply_name=True)

    def ApplyBoth_Click(self, sender, args):
        self._apply(apply_number=True, apply_name=True)

    def Suggest_Click(self, sender, args):
        av = self.uidoc.ActiveView
        if av is None or not isinstance(av, DB.ViewSheet):
            self.LogLine(u'Active view is not a sheet.')
            return
        sheet_name = av.Name or u''
        f3 = _logic.suggest_f3_from_views(self.doc, av) or _logic.suggest_f3_from_name(sheet_name)
        f4 = _logic.suggest_f4_from_level(self.doc, av)
        f7 = _logic.F7_HINTS.get(f3, '2200')
        # Set combos
        self.CmbF3.SelectedIndex = self._index_of_code(self.CmbF3, f3)
        self.CmbF4.Text = f4
        self.TxtF7.Text = f7
        self.TxtF9.Text = sheet_name
        self.LogLine(u'Suggested: F3={}, F4={}, F7={}'.format(f3, f4, f7))

    def _set_bulk_apply_enabled(self, enabled):
        try:
            self.BtnBulkApplyAll.IsEnabled = enabled
        except Exception:
            pass

    def BulkRefresh_Click(self, sender, args):
        self._populate_bulk()

    def BulkSuggest_Click(self, sender, args):
        self._populate_bulk()

    def BulkPreview_Click(self, sender, args):
        existing = _logic.get_existing_numbers(self.doc)
        ok = change = err = 0
        for row in self._bulk_rows:
            row.refresh_status(existing)
            if row.Status == 'ok':
                ok += 1
            elif row.Status == 'change':
                change += 1
            else:
                err += 1
        self.GridSheets.Items.Refresh()
        self._bulk_preview_reviewed = True
        self._set_bulk_apply_enabled(change > 0 and err == 0)
        self.TxtBulkStatus.Text = (
            u'Preview: {} OK, {} to change, {} errors. '
            u'Review coloured rows, then Apply selected.'.format(ok, change, err))

    def _populate_bulk(self):
        cfg = self.LoadConfig()
        self._bulk_rows.Clear()
        self._bulk_preview_reviewed = False
        self._set_bulk_apply_enabled(False)
        existing = _logic.get_existing_numbers(self.doc)
        for s in _logic.get_all_sheets(self.doc):
            sug = _logic.suggest_bulk_for_sheet(self.doc, s, cfg, existing)
            self._bulk_rows.Add(BulkSheetRow(s, sug))
        self.GridSheets.ItemsSource = self._bulk_rows
        self.TxtBulkStatus.Text = (
            u'{} sheets loaded — click Preview to review suggested changes.'.format(
                self._bulk_rows.Count))

    def BulkApplyAll_Click(self, sender, args):
        if not self._bulk_preview_reviewed:
            self.TxtBulkStatus.Text = u'Run Preview first to review suggested changes.'
            return
        rows = [r for r in self._bulk_rows if r.Selected and r.Status != 'error']
        if not rows:
            self.TxtBulkStatus.Text = u'No valid rows selected.'
            return
        self.SetLoading(True, u'Applying sheet numbers…')
        ok = fail = 0
        try:
            with DB.Transaction(self.doc, u'NOSA — Sheet Namer Bulk') as t:
                t.Start()
                for row in rows:
                    sheet = self.doc.GetElement(row._sheet_id)
                    if sheet is None:
                        fail += 1
                        continue
                    try:
                        nn = row.NewNumber
                        errors = _logic.validate_fields(
                            row.F1, row.F3, row.F4, row.F5, row.F6, row.F7, row.F8)
                        if not errors:
                            applied, _, _ = _logic.apply_nosa_to_sheet(
                                self.doc, sheet,
                                row.F1, row.F3, row.F4, row.F5, row.F6, row.F7, row.F8,
                                new_number=nn)
                            if applied:
                                ok += 1
                            else:
                                fail += 1
                        else:
                            fail += 1
                    except Exception:
                        fail += 1
                t.Commit()
        finally:
            self.SetLoading(False)
        self.TxtBulkStatus.Text = u'Applied: {} OK, {} errors.'.format(ok, fail)
        self._bulk_preview_reviewed = False
        self._set_bulk_apply_enabled(False)
        self._populate_bulk()

    def _populate_parse(self):
        self._parse_rows.Clear()
        for s in _logic.get_all_sheets(self.doc):
            if self._NOSA_PATTERN.match(s['number']):
                self._parse_rows.Add(ParseSheetRow(s))
        self.GridParse.ItemsSource = self._parse_rows
        self.TxtParseStatus.Text = u'{} NOSA-pattern sheets found'.format(
            self._parse_rows.Count)

    def ParseRefresh_Click(self, sender, args):
        self._populate_parse()

    def ParseApply_Click(self, sender, args):
        rows = [r for r in self._parse_rows if r.Selected]
        if not rows:
            self.TxtParseStatus.Text = u'No rows selected.'
            return
        ok = fail = 0
        with DB.Transaction(self.doc, u'NOSA — Sheet Namer Parse') as t:
            t.Start()
            for row in rows:
                sheet = self.doc.GetElement(row._sheet_id)
                if sheet is None:
                    fail += 1
                    continue
                try:
                    applied, _, _ = _logic.apply_nosa_to_sheet(
                        self.doc, sheet,
                        row.F1, row.F3, row.F4, row.F5, row.F6, row.F7, row.F8,
                        new_number=row.Generated)
                    if applied:
                        ok += 1
                    else:
                        fail += 1
                except Exception:
                    fail += 1
            t.Commit()
        self.TxtParseStatus.Text = u'Applied: {} OK, {} errors.'.format(ok, fail)

    def Close_Click(self, sender, args):
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
