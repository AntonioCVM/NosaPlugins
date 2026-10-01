# -*- coding: utf-8 -*-
import os, sys, json

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from Autodesk.Revit import DB
from System.Collections.ObjectModel import ObservableCollection
import System.Windows
import System.Windows.Media as WM
from System.Windows.Media import Brushes
import System.Windows.Threading as _swt
from System.Windows import FontWeights

from nosa_utils.base_window import NOSAWindow
from nosa_utils import sheet_protocol as _sp
from nosa_utils.revit_helpers import coerce_element_id, get_id_value

_HERE      = os.path.dirname(__file__)
_SHEETS_DL = os.path.abspath(os.path.join(_HERE, '..', '..'))

_di_logic = None
_sn_logic = None
_sc_logic = None


def _resolve_hub_logic(plugin_base):
    for suffix in ('nobutton', 'pushbutton'):
        path = os.path.join(_SHEETS_DL, '{}.{}'.format(plugin_base, suffix), 'lib', 'logic.py')
        if os.path.isfile(path):
            return path
    raise IOError(u'Logic module not found for "{}" under Sheets pulldown.'.format(plugin_base))


def _hub_logics():
    global _di_logic, _sn_logic, _sc_logic
    if _di_logic is None:
        from nosa_utils.bootstrap import load_module
        _di_logic = load_module('sheethub_di_logic',
            _resolve_hub_logic('DrawingIndex'))
        _sn_logic = load_module('sheethub_sn_logic',
            _resolve_hub_logic('SheetNamer'))
        _sc_logic = load_module('sheethub_sc_logic',
            _resolve_hub_logic('SheetGen'))
    return _di_logic, _sn_logic, _sc_logic

ACCENT = WM.Color.FromRgb(255, 95, 0)
DARK   = WM.Color.FromRgb(51, 51, 51)

_STATUS_COLOURS = {
    'neutral':  '#F5F5F5',
    'ok':       '#E8F5E9',
    'match':    '#E8F5E9',
    'change':   '#FFF3E0',
    'field':    '#FFF3E0',
    'error':    '#FFEBEE',
    'approved': '#E3F2FD',
    'loaded':   '#FFFFFF',
}

_FIELD_KEYS = (u'F1', u'F2', u'F3', u'F4', u'F5', u'F6', u'F7', u'F8', u'F9')
_EDITABLE_FIELDS = frozenset(_FIELD_KEYS)
_FIELD_PARAM_LABELS = dict(_sp.NOSA_FIELD_DISPLAY_NAMES)

_CONFIGS_ROOT = os.path.join(
    os.getenv('APPDATA', ''),
    'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs')


def _hex_brush(hex_color):
    try:
        h = (hex_color or u'#FFFFFF').lstrip(u'#')
        return WM.SolidColorBrush(WM.Color.FromRgb(
            int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
    except Exception:
        return Brushes.White


def _field_key_from_header(header):
    """Map grid column header text to F-field key (e.g. 'F1 Project No' -> 'F1')."""
    hdr = (header or u'').strip()
    for fk in _FIELD_KEYS:
        if hdr == fk or hdr.startswith(fk + u' '):
            return fk
    return hdr


def _norm_val(val):
    return (val or u'').strip().upper()


class UnifiedSheetRow(object):
    def __init__(self, sheet_dict, load_data):
        self._element        = sheet_dict.get('element')
        raw_id = sheet_dict.get('id')
        if raw_id is None and self._element is not None:
            raw_id = self._element.Id
        self._sheet_id       = get_id_value(raw_id) if raw_id is not None else None
        self.Selected        = False
        self.Approved        = False
        self.CurrentNumber   = (
            load_data.get('current_display')
            or sheet_dict.get('nosa_display')
            or sheet_dict.get('number')
            or u'')
        self._current_fields = dict(load_data.get('current_fields') or {})
        self._suggested_fields = None
        self._sources        = {}
        self._has_suggestions = False
        self.F1 = load_data.get('f1', u'')
        self.F2 = load_data.get('f2', _sp.NOSA_ORIGINATOR)
        self.F3 = load_data.get('f3', u'')
        self.F4 = load_data.get('f4', u'')
        self.F5 = load_data.get('f5', u'')
        self.F6 = load_data.get('f6', u'')
        self.F7 = load_data.get('f7', u'')
        self.F8 = load_data.get('f8', u'')
        self.F9 = load_data.get('f9', sheet_dict.get('name', u''))
        self.Package = (
            sheet_dict.get('package', u'')
            or sheet_dict.get('Package', u'')
            or u'')
        self._current_package = self.Package
        self.Status          = load_data.get('status', 'loaded')
        self.StatusLabel     = load_data.get('status_label', u'Loaded')
        self.Message         = load_data.get('message', u'')
        self._field_errors   = {}
        self._field_warnings = {}
        self.RowBrush        = _hex_brush(_STATUS_COLOURS.get('loaded', '#FFFFFF'))
        self._update_field_ui()
        self._update_proposed_ui()

    def _fields_dict(self):
        return {fk.lower(): getattr(self, fk, u'') for fk in _FIELD_KEYS}

    def apply_suggestion(self, suggestion):
        self._current_fields = dict(suggestion.get('current_fields') or self._current_fields)
        self._suggested_fields = dict(
            suggestion.get('suggested_fields') or {
                u'f1': suggestion.get('f1', u''),
                u'f2': suggestion.get('f2', _sp.NOSA_ORIGINATOR),
                u'f3': suggestion.get('f3', u''),
                u'f4': suggestion.get('f4', u''),
                u'f5': suggestion.get('f5', u''),
                u'f6': suggestion.get('f6', u''),
                u'f7': suggestion.get('f7', u''),
                u'f8': suggestion.get('f8', u''),
                u'f9': suggestion.get('f9', u''),
            })
        self._sources = dict(suggestion.get('sources') or {})
        self.F1 = suggestion['f1']
        self.F2 = suggestion.get('f2', _sp.NOSA_ORIGINATOR)
        self.F3 = suggestion['f3']
        self.F4 = suggestion['f4']
        self.F5 = suggestion['f5']
        self.F6 = suggestion['f6']
        self.F7 = suggestion['f7']
        self.F8 = suggestion['f8']
        self.F9 = suggestion.get('f9', self.F9)
        self._has_suggestions = True
        self.Approved = False

    def revert_to_current(self):
        if not self._current_fields:
            return
        for fk in _FIELD_KEYS:
            setattr(self, fk, self._current_fields.get(fk.lower(), u''))
        self.Approved = False
        self._field_errors = {}
        self._field_warnings = {}

    def revert_to_suggested(self):
        if not self._suggested_fields:
            return
        for fk in _FIELD_KEYS:
            low = fk.lower()
            if low in self._suggested_fields:
                setattr(self, fk, self._suggested_fields[low])
        self.Approved = False
        self._field_errors = {}
        self._field_warnings = {}

    def set_apply_warnings(self, failed_fkeys, results=None):
        """Mark grid cells orange when Revit write failed for a field."""
        self._field_warnings = {}
        labels = dict(_sp.NOSA_FIELD_DISPLAY_NAMES)
        for fk in failed_fkeys:
            low = fk.lower() if hasattr(fk, 'lower') else fk
            host = u''
            info = u''
            if results and low in results:
                host = results[low].get(u'host', u'')
                info = results[low].get(u'info', u'')
            disp = labels.get(low, low.upper())
            msg = u'Not written to Revit'
            if info:
                msg = info
            elif host:
                msg = u'Not written — tried {}'.format(host)
            self._field_warnings[low] = msg

    def has_field_changes(self):
        for fk in _FIELD_KEYS:
            low = fk.lower()
            if _norm_val(self._current_fields.get(low, u'')) != _norm_val(getattr(self, fk, u'')):
                return True
        if _norm_val(self.Package) != _norm_val(self._current_package):
            return True
        return False

    def grid_field_values(self):
        """Current F-field values shown in the grid (source of truth for Apply)."""
        vals = {fk.lower(): getattr(self, fk, u'') or u'' for fk in _FIELD_KEYS}
        vals[u'package'] = self.Package or u''
        return vals

    def _update_field_ui(self):
        for fk in _FIELD_KEYS:
            low = fk.lower()
            cur = self._current_fields.get(low, u'')
            val = getattr(self, fk, u'')
            err = self._field_errors.get(low)
            warn = self._field_warnings.get(low)
            if err:
                colour = _STATUS_COLOURS['error']
            elif warn:
                colour = _STATUS_COLOURS['field']
            elif self.Approved and self._has_suggestions:
                colour = _STATUS_COLOURS['approved']
            elif not self._has_suggestions:
                if _norm_val(cur) != _norm_val(val):
                    colour = _STATUS_COLOURS['change']
                else:
                    colour = _STATUS_COLOURS['neutral']
            elif _norm_val(cur) == _norm_val(val):
                colour = _STATUS_COLOURS['match']
            else:
                colour = _STATUS_COLOURS['change']
            setattr(self, fk + u'Brush', _hex_brush(colour))
            src = self._sources.get(low, u'')
            if self._has_suggestions:
                tip = u'Current: {} \u2192 Suggested: {}'.format(cur or u'(empty)', val or u'(empty)')
                if src:
                    tip += u' (source: {})'.format(src)
            else:
                tip = u'Current: {}'.format(val or u'(empty)')
            if err:
                tip += u'\nError: {}'.format(err)
            if warn:
                tip += u'\nWarning: {}'.format(warn)
            setattr(self, fk + u'Tip', tip)

    def _update_proposed_ui(self):
        prop = self.ProposedNumber
        if not self._has_suggestions:
            self.ProposedNumberBrush = _hex_brush(_STATUS_COLOURS['neutral'])
            self.ProposedNumberWeight = FontWeights.Normal
        elif prop and _norm_val(prop) != _norm_val(self.CurrentNumber):
            self.ProposedNumberBrush = _hex_brush(_STATUS_COLOURS['change'])
            self.ProposedNumberWeight = FontWeights.Bold
        else:
            self.ProposedNumberBrush = _hex_brush(_STATUS_COLOURS['match'])
            self.ProposedNumberWeight = FontWeights.Normal

    @property
    def ProposedNumber(self):
        try:
            return _sp.build_nosa_number(
                self.F1, self.F3, self.F4, self.F5, self.F6, self.F7, self.F8)
        except Exception:
            return u''

    def refresh_status(self, existing_numbers, proposed_in_grid=None):
        _, sn, _ = _hub_logics()
        errors = sn.validate_fields(
            self.F1, self.F3, self.F4, self.F5, self.F6, self.F7, self.F8)
        self._field_errors = {}
        if errors:
            for msg in errors:
                for fk, label in (
                    (u'f1', u'F1'), (u'f3', u'F3'), (u'f4', u'F4'),
                    (u'f5', u'F5'), (u'f6', u'F6'), (u'f7', u'F7'), (u'f8', u'F8')):
                    if label in msg:
                        self._field_errors[fk] = msg
        new_num = self.ProposedNumber
        if errors:
            self.Status = 'error'
            self.StatusLabel = u'Error'
            self.Message = u'; '.join(errors)
            self.RowBrush = _hex_brush(_STATUS_COLOURS['error'])
        elif self.has_field_changes():
            self.Status = 'change'
            self.StatusLabel = u'To review'
            self.Message = u'Fields differ from current Revit values.'
            self.RowBrush = _hex_brush(_STATUS_COLOURS['change'])
        elif self.Approved and self._has_suggestions:
            self.Status = 'approved'
            self.StatusLabel = u'\u2713 Approved'
            self.Message = u'Ready to apply to Revit.'
            self.RowBrush = _hex_brush(_STATUS_COLOURS['approved'])
        elif not self._has_suggestions:
            self.Status = 'loaded'
            self.StatusLabel = u'Loaded'
            self.Message = u'Current values from Revit.'
            self.RowBrush = _hex_brush(_STATUS_COLOURS['loaded'])
        elif new_num and new_num != self.CurrentNumber:
            self.Status = 'change'
            self.StatusLabel = u'To review'
            self.Message = u'Proposed number differs from current.'
            self.RowBrush = _hex_brush(_STATUS_COLOURS['change'])
        else:
            self.Status = 'ok'
            self.StatusLabel = u'OK'
            self.Message = u'No changes needed.'
            self.RowBrush = _hex_brush(_STATUS_COLOURS['ok'])
        dup_msg = None
        if self.F7 and existing_numbers:
            current_f7 = (self._current_fields or {}).get(u'f7', u'')
            if self.F7 in existing_numbers and self.F7 != current_f7:
                dup_msg = u'Duplicate: another sheet already uses this document number.'
        if proposed_in_grid and new_num:
            others = proposed_in_grid.get(new_num, [])
            if len(others) > 1 or (len(others) == 1 and others[0] is not self):
                dup_msg = u'Duplicate: another row has this proposed number.'
        if dup_msg:
            self.Status = 'error'
            self.StatusLabel = u'Error'
            self.Message = dup_msg
            self.RowBrush = _hex_brush(_STATUS_COLOURS['error'])
        self._update_field_ui()
        self._update_proposed_ui()


class SheetHubWindow(NOSAWindow):

    def __init__(self, doc, uidoc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'sheet_hub')
        self.doc   = doc
        self.uidoc = uidoc

        self._sheets_data           = []
        self._all_sheet_rows        = []
        self._sheets_suggested      = False
        self._package_filter        = u''
        self._sheets_rows           = ObservableCollection[UnifiedSheetRow]()
        self.SheetsGrid.ItemsSource = self._sheets_rows
        self.SheetsGrid.SelectionChanged += self.SheetsGrid_Interaction
        self.SheetsGrid.CurrentCellChanged += self.SheetsGrid_Interaction
        self._init_sheets_context_menu()

        try:
            _hub_logics()
            cfg = self.LoadConfig()
            self.ApplyTheme(cfg.get('dark_mode', False))
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
            self.ChkAllowRenumber.IsChecked = cfg.get('allow_renumber', False)
            self._sn_populate_combos(cfg)
            self._sn_update_preview()
        except Exception as e:
            from pyrevit import forms
            forms.alert(u'Sheet Hub init error:\n{}'.format(e), title=u'Error')
            raise

        self.Loaded += self._on_window_loaded

    def _on_window_loaded(self, sender, args):
        try:
            self.SetLoading(True, u'Loading sheets...')
            txt = self.TxtSheetsFilter.Text.strip() if hasattr(self, 'TxtSheetsFilter') else u''
            self._sheets_load(txt)
        except Exception as e:
            from pyrevit import forms
            forms.alert(u'Sheet Hub load error:\n{}'.format(e), title=u'Error')
        finally:
            self.SetLoading(False)

    def _get_sheet_element(self, sheet_id):
        if sheet_id is None:
            return None
        return self.doc.GetElement(coerce_element_id(sheet_id))

    def _write_sheet_package(self, sheet, value):
        if sheet is None:
            return False
        from nosa_utils.param_element_ops import set_param_from_string
        for el in _sp.iter_write_hosts(self.doc, sheet):
            try:
                p = el.LookupParameter('Package')
                if p and set_param_from_string(p, value or u''):
                    return True
            except Exception:
                pass
        return False

    def _populate_package_combos(self):
        if not hasattr(self, 'CmbPackageFilter'):
            return
        di, _, _ = _hub_logics()
        packages = di.get_unique_packages(self.doc)
        sel = self._package_filter
        self.CmbPackageFilter.Items.Clear()
        self.CmbPackageFilter.Items.Add(u'All packages')
        for pkg in packages:
            self.CmbPackageFilter.Items.Add(pkg)
        if sel and sel in packages:
            self.CmbPackageFilter.SelectedItem = sel
        else:
            self.CmbPackageFilter.SelectedIndex = 0
            self._package_filter = u''
        self.CmbBulkPackage.Items.Clear()
        for pkg in packages:
            self.CmbBulkPackage.Items.Add(pkg)

    def PackageFilter_Changed(self, sender, args):
        item = self.CmbPackageFilter.SelectedItem
        if item is None or str(item) == u'All packages':
            self._package_filter = u''
        else:
            self._package_filter = str(item).strip()
        self._rebind_sheets_grid()

    def _row_passes_package_filter(self, row):
        if not self._package_filter:
            return True
        return (row.Package or u'').strip() == self._package_filter

    # ══ UNIFIED SHEETS TAB ════════════════════════════════════════════════════

    def _merge_namer_config(self, cfg):
        """Merge sheet_namer.json defaults into hub config (hub values win)."""
        merged = dict(cfg)
        namer_path = os.path.join(_CONFIGS_ROOT, '_sheet_namer.json')
        try:
            if os.path.isfile(namer_path):
                with open(namer_path, 'r') as f:
                    namer = json.load(f)
                for key in (u'f1', u'f3', u'f4', u'f5', u'f6', u'f7', u'f8'):
                    if key not in merged or not merged.get(key):
                        merged[key] = namer.get(key, merged.get(key, u''))
        except Exception:
            pass
        return merged

    def _init_sheets_context_menu(self):
        from System.Windows.Controls import MenuItem
        cm = System.Windows.Controls.ContextMenu()
        mi_cur = MenuItem(Header=u'Revert row to current Revit values')
        mi_cur.Click += self.SheetsRevertCurrent_Click
        mi_sug = MenuItem(Header=u'Revert row to protocol suggestion')
        mi_sug.Click += self.SheetsRevertSuggested_Click
        cm.Items.Add(mi_cur)
        cm.Items.Add(mi_sug)
        self.SheetsGrid.ContextMenu = cm

    def _proposed_number_index(self, rows):
        idx = {}
        for row in rows:
            num = row.ProposedNumber
            if not num:
                continue
            idx.setdefault(num, []).append(row)
        return idx

    def _sheets_refresh_status(self):
        _, sn, _ = _hub_logics()
        existing = sn.get_existing_numbers(self.doc)
        proposed_idx = self._proposed_number_index(self._all_sheet_rows)
        review = approved = err = ok = 0
        for row in self._all_sheet_rows:
            row.refresh_status(existing, proposed_idx)
            if row.Status == 'error':
                err += 1
            elif row.Status == 'approved':
                approved += 1
            elif row.Status == 'change':
                review += 1
            elif row.Status == 'ok':
                ok += 1
        self.SheetsGrid.Items.Refresh()
        self._update_sheets_toolbar()
        return review, approved, err, ok

    def _row_passes_changes_filter(self, row):
        if not hasattr(self, 'ChkChangesOnly') or not self.ChkChangesOnly.IsChecked:
            return True
        if not self._sheets_suggested:
            return True
        return row.has_field_changes() or (
            row.ProposedNumber and row.ProposedNumber != row.CurrentNumber)

    def _rebind_sheets_grid(self):
        self._sheets_rows.Clear()
        for row in self._all_sheet_rows:
            if self._row_passes_changes_filter(row) and self._row_passes_package_filter(row):
                self._sheets_rows.Add(row)
        self.SheetsGrid.Items.Refresh()

    def _selected_row_count(self):
        return sum(1 for r in self._all_sheet_rows if r.Selected)

    def _update_duplicate_panel(self):
        Vis = System.Windows.Visibility
        if hasattr(self, 'PanelDuplicate'):
            n = self._selected_row_count()
            self.PanelDuplicate.Visibility = Vis.Visible if n > 0 else Vis.Collapsed
            if hasattr(self, 'BtnSheetsDuplicate'):
                self.BtnSheetsDuplicate.IsEnabled = n > 0

    def _row_apply_ready(self, row):
        return row.Selected and row.has_field_changes()

    def _update_sheets_toolbar(self):
        has = len(self._all_sheet_rows) > 0
        self.BtnSheetsCsv.IsEnabled = has
        self.BtnSheetsHtml.IsEnabled = has
        self.BtnSheetsSuggest.IsEnabled = has
        apply_ready = any(self._row_apply_ready(r) for r in self._all_sheet_rows)
        self.BtnSheetsApply.IsEnabled = apply_ready and has
        approve_ready = self._sheets_suggested and any(
            r.Selected and r.Status not in ('error', 'approved') for r in self._all_sheet_rows)
        if hasattr(self, 'BtnSheetsApprove'):
            self.BtnSheetsApprove.IsEnabled = approve_ready
        if hasattr(self, 'BtnSheetsApproveAll'):
            self.BtnSheetsApproveAll.IsEnabled = self._sheets_suggested and any(
                r.Status == 'change' for r in self._all_sheet_rows)
        self._update_duplicate_panel()

    def _update_sheets_status_text(self, review, approved, err, ok=0):
        count = len(self._all_sheet_rows)
        if not self._sheets_suggested:
            self.TxtSheetsStatus.Text = u'Loaded {} sheets from Revit.'.format(count)
            return
        parts = []
        if review:
            parts.append(u'{} to review'.format(review))
        if approved:
            parts.append(u'{} approved'.format(approved))
        if err:
            parts.append(u'{} errors'.format(err))
        if ok and not review:
            parts.append(u'{} unchanged'.format(ok))
        self.TxtSheetsStatus.Text = u', '.join(parts) if parts else u'{} sheets loaded.'.format(count)

    def _sheet_dict_for_row(self, row):
        for s in self._sheets_data:
            sid = get_id_value(s.get('id'))
            if sid == row._sheet_id:
                return s
        return {
            'id': row._sheet_id,
            'number': row.CurrentNumber,
            'name': row.F9,
            'package': row.Package,
            'element': row._element or self._get_sheet_element(row._sheet_id),
        }

    def _sheets_load(self, filter_text=u''):
        di, sn, _ = _hub_logics()
        cfg = self._merge_namer_config(self.LoadConfig())
        self._all_sheet_rows = []
        self._sheets_rows.Clear()
        self._sheets_suggested = False
        self.BtnSheetsApply.IsEnabled = False
        if hasattr(self, 'BtnSheetsApprove'):
            self.BtnSheetsApprove.IsEnabled = False
        if hasattr(self, 'BtnSheetsApproveAll'):
            self.BtnSheetsApproveAll.IsEnabled = False
        self._sheets_data = di.collect_sheets(self.doc, filter_text)
        for s in self._sheets_data:
            cur = sn.read_current_for_sheet(self.doc, s, cfg)
            row = UnifiedSheetRow(s, cur)
            self._all_sheet_rows.append(row)
        self._rebind_sheets_grid()
        self._populate_package_combos()
        review, approved, err, ok = self._sheets_refresh_status()
        self._update_sheets_status_text(review, approved, err, ok)

    def SheetsFilter_Changed(self, sender, args):
        txt = self.TxtSheetsFilter.Text.strip() if hasattr(self, 'TxtSheetsFilter') else u''
        self._sheets_load(txt)

    def SheetsGrid_Interaction(self, sender, args):
        self._update_sheets_toolbar()

    def SheetRowSelected_Click(self, sender, args):
        self._update_sheets_toolbar()

    def SheetsLoad_Click(self, sender, args):
        self.SetLoading(True, u'Loading sheets from Revit…')
        try:
            txt = self.TxtSheetsFilter.Text.strip()
            self._sheets_load(txt)
        except Exception as e:
            from pyrevit import forms
            forms.alert(u'Error: {}'.format(e))
        finally:
            self.SetLoading(False)

    def _read_sheet_package(self, sheet):
        if sheet is None:
            return u''
        try:
            p = sheet.LookupParameter('Package')
            if p:
                return (p.AsString() or p.AsValueString() or u'').strip()
        except Exception:
            pass
        return u''

    def _refresh_row_from_revit(self, row, cfg):
        _, sn, _ = _hub_logics()
        sheet = row._element or self._get_sheet_element(row._sheet_id)
        s = self._sheet_dict_for_row(row)
        if sheet is not None:
            s['package'] = self._read_sheet_package(sheet)
            s['element'] = sheet
            row._element = sheet
        cur = sn.read_current_for_sheet(self.doc, s, cfg)
        row.CurrentNumber = (
            cur.get('current_display') or row.CurrentNumber or u'')
        row._current_fields = dict(cur.get('current_fields') or {})
        row._current_package = row.Package = (
            s.get('package', u'') or s.get('Package', u'') or row.Package or u'')
        for fk in _FIELD_KEYS:
            setattr(row, fk, cur.get(fk.lower(), getattr(row, fk, u'')))
        row._has_suggestions = False
        row.Approved = False
        row._suggested_fields = None
        row._sources = {}

    def _run_protocol_suggest(self):
        _, sn, _ = _hub_logics()
        cfg = self._merge_namer_config(self.LoadConfig())
        existing = sn.get_existing_numbers(self.doc)
        allow_renumber = bool(self.ChkAllowRenumber.IsChecked)
        suggestions = []
        for row in self._all_sheet_rows:
            s = self._sheet_dict_for_row(row)
            sug = sn.suggest_bulk_for_sheet(self.doc, s, cfg, existing)
            suggestions.append((row, sug))
        if allow_renumber:
            sn.assign_f7_sequences(self.doc, [s for _, s in suggestions], cfg)
        for row, sug in suggestions:
            if not allow_renumber:
                # Numbering locked — never propose a new F7, so the grid
                # never shows a "change" for a field Apply will skip anyway.
                sug[u'f7'] = row._current_fields.get(u'f7', u'') or sug.get(u'f7', u'')
            row.apply_suggestion(sug)
        self._sheets_suggested = True
        review, approved, err, ok = self._sheets_refresh_status()
        self._rebind_sheets_grid()
        self._update_sheets_status_text(review, approved, err, ok)
        return review, approved, err, ok

    def SheetsSuggest_Click(self, sender, args):
        if not self._all_sheet_rows:
            self.TxtSheetsStatus.Text = u'Load sheets first.'
            return
        self.SetLoading(True, u'Suggesting from NOSA protocol…')
        try:
            review, approved, err, ok = self._run_protocol_suggest()
            self.LogLine(u'[Sheets] Protocol suggestions applied to {} rows.'.format(
                len(self._all_sheet_rows)))
        except Exception as e:
            from pyrevit import forms
            forms.alert(u'Suggest failed: {}'.format(e))
        finally:
            self.SetLoading(False)

    def SheetsApprove_Click(self, sender, args):
        if not self._sheets_suggested:
            self.TxtSheetsStatus.Text = u'Run Suggest from Protocol first.'
            return
        n = 0
        for row in self._all_sheet_rows:
            if row.Selected and row.Status not in ('error', 'approved'):
                row.Approved = True
                n += 1
        review, approved, err, ok = self._sheets_refresh_status()
        self._update_sheets_status_text(review, approved, err, ok)
        self.SheetsGrid.Items.Refresh()
        self.LogLine(u'[Sheets] Approved {} row(s).'.format(n))

    def SheetsApproveAll_Click(self, sender, args):
        if not self._sheets_suggested:
            self.TxtSheetsStatus.Text = u'Run Suggest from Protocol first.'
            return
        n = 0
        for row in self._all_sheet_rows:
            if row.Status == 'change':
                row.Selected = True
                row.Approved = True
                n += 1
        review, approved, err, ok = self._sheets_refresh_status()
        self._rebind_sheets_grid()
        self._update_sheets_status_text(review, approved, err, ok)
        self.LogLine(u'[Sheets] Approved all rows with changes ({}).'.format(n))

    def ChangesOnly_Changed(self, sender, args):
        self._rebind_sheets_grid()

    def AllowRenumber_Changed(self, sender, args):
        cfg = self.LoadConfig()
        cfg['allow_renumber'] = bool(self.ChkAllowRenumber.IsChecked)
        self.SaveConfig(cfg)

    def SheetsRevertCurrent_Click(self, sender, args):
        row = self.SheetsGrid.SelectedItem
        if row is None:
            return
        row.revert_to_current()
        review, approved, err, ok = self._sheets_refresh_status()
        self._update_sheets_status_text(review, approved, err, ok)
        self.SheetsGrid.Items.Refresh()

    def SheetsRevertSuggested_Click(self, sender, args):
        row = self.SheetsGrid.SelectedItem
        if row is None or not row._suggested_fields:
            return
        row.revert_to_suggested()
        review, approved, err, ok = self._sheets_refresh_status()
        self._update_sheets_status_text(review, approved, err, ok)
        self.SheetsGrid.Items.Refresh()

    def SheetsGrid_CellEditEnding(self, sender, args):
        try:
            hdr = str(args.Column.Header or u'')
            fk = _field_key_from_header(hdr)
            row = args.Row.Item
            new_val = str(args.EditingElement.Text
                          if hasattr(args.EditingElement, 'Text') else u'').strip()
            if hdr == u'Package':
                row.Package = new_val
                row.Approved = False
            elif fk in _EDITABLE_FIELDS:
                setattr(row, fk, new_val)
                row._sources[fk.lower()] = u'Manual edit'
                row.Approved = False
            else:
                return
        except Exception:
            pass
        def _refresh():
            try:
                review, approved, err, ok = self._sheets_refresh_status()
                self._update_sheets_status_text(review, approved, err, ok)
                self.SheetsGrid.Items.Refresh()
            except Exception:
                pass
        self.SheetsGrid.Dispatcher.BeginInvoke(
            _swt.DispatcherPriority.Background,
            System.Action(_refresh))

    def SheetsApply_Click(self, sender, args):
        from pyrevit import forms
        _, sn, _ = _hub_logics()
        cfg = self._merge_namer_config(self.LoadConfig())
        rows = [r for r in self._all_sheet_rows if self._row_apply_ready(r)]
        if not rows:
            self.TxtSheetsStatus.Text = (
                u'No rows ready — tick rows with edited values, then apply.')
            return
        allow_renumber = bool(self.ChkAllowRenumber.IsChecked)
        ok = fail = warn_sheets = 0
        self.SetLoading(True, u'Applying changes to Revit…')
        try:
            with DB.Transaction(self.doc, u'NOSA — Sheet Hub Apply') as t:
                t.Start()
                for row in rows:
                    sheet = row._element or self._get_sheet_element(row._sheet_id)
                    label = row.F9 or row.CurrentNumber or str(row._sheet_id)
                    row._field_warnings = {}
                    if sheet is None:
                        fail += 1
                        self.LogLine(u'[Sheets] FAIL {} — sheet not found.'.format(label))
                        continue
                    vals = row.grid_field_values()
                    f1, f3, f4 = vals[u'f1'], vals[u'f3'], vals[u'f4']
                    f5, f6, f7, f8 = vals[u'f5'], vals[u'f6'], vals[u'f7'], vals[u'f8']
                    f9 = vals[u'f9']
                    pkg = vals[u'package']
                    errors = sn.validate_fields(f1, f3, f4, f5, f6, f7, f8)
                    if errors:
                        fail += 1
                        self.LogLine(u'[Sheets] FAIL {} — {}.'.format(
                            label, u'; '.join(errors)))
                        continue
                    try:
                        applied, results, warnings = sn.apply_nosa_to_sheet(
                            self.doc, sheet, f1, f3, f4, f5, f6, f7, f8,
                            new_name=f9 or None, debug=True,
                            allow_renumber=allow_renumber)
                        f7_res = (results or {}).get(u'f7') or {}
                        if (not allow_renumber and f7_res.get(u'skipped')
                                and _norm_val(f7) != _norm_val(row._current_fields.get(u'f7', u''))):
                            self.LogLine(
                                u'[Sheets]   F7 Document Number — locked, not applied '
                                u'(tick "Allow sheet number changes" to renumber).')
                        for fkey, res in (results or {}).items():
                            disp = _sp.NOSA_FIELD_DISPLAY_NAMES.get(fkey, fkey.upper())
                            if res.get(u'ok') and res.get(u'readonly') and res.get(u'info'):
                                self.LogLine(u'[Sheets]   {} — {}'.format(
                                    disp, res[u'info']))
                            elif res.get(u'ok') and res.get(u'host'):
                                self.LogLine(u'[Sheets]   {} → {} on {}'.format(
                                    disp, getattr(row, fkey.upper(), u''),
                                    res[u'host']))
                            debug_params = res.get(u'debug_params')
                            if debug_params:
                                self.LogLine(u'[Sheets]   {} title block params: {}'.format(
                                    disp, u', '.join(debug_params)))
                        if warnings:
                            warn_sheets += 1
                            row.set_apply_warnings(warnings, results)
                            names = u', '.join(
                                _FIELD_PARAM_LABELS.get(w, w) for w in warnings)
                            self.LogLine(u'[Sheets] WARN {} — not written: {}.'.format(
                                label, names or u', '.join(warnings)))
                        if not applied:
                            fail += 1
                            self.LogLine(u'[Sheets] FAIL {} — parameters not written.'.format(
                                label))
                            continue
                        pkg_changed = _norm_val(pkg) != _norm_val(row._current_package)
                        if pkg_changed:
                            if not self._write_sheet_package(sheet, pkg):
                                self.LogLine(
                                    u'[Sheets] WARN {} — NOSA fields OK, Package not written.'.format(
                                        label))
                        ok += 1
                        self.LogLine(u'[Sheets] OK {}{}.'.format(
                            label,
                            u', Package updated' if pkg_changed else u''))
                    except Exception as ex:
                        fail += 1
                        self.LogLine(u'[Sheets] FAIL {} — {}.'.format(label, ex))
                t.Commit()
            try:
                self.doc.Regenerate()
            except Exception:
                pass
        finally:
            self.SetLoading(False)
        for row in rows:
            if row.Selected:
                try:
                    self._refresh_row_from_revit(row, cfg)
                except Exception:
                    pass
        review, approved, err, ok_count = self._sheets_refresh_status()
        self._update_sheets_status_text(review, approved, err, ok_count)
        self.SheetsGrid.Items.Refresh()
        summary = u'Applied {} sheet(s), {} error(s)'.format(ok, fail)
        if warn_sheets:
            summary += u', {} warning(s)'.format(warn_sheets)
        self.TxtSheetsStatus.Text = summary + u'.'
        self.LogLine(u'[Sheets] Apply complete: {}.'.format(summary))
        if ok or warn_sheets:
            forms.alert(summary, title=u'Sheet Hub — Apply')

    def SheetsExportCsv_Click(self, sender, args):
        from pyrevit import forms
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            di, _, _ = _hub_logics()
            di.export_csv(self._sheets_data, path)
            forms.alert(u'CSV exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    def SheetsExportHtml_Click(self, sender, args):
        from pyrevit import forms
        path = forms.save_file(file_ext='html')
        if not path:
            return
        try:
            di, _, _ = _hub_logics()
            di.export_html(self._sheets_data, path, di.get_project_name(self.doc))
            import os as _os
            _os.startfile(path)
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    # ══ QUICK APPLY (active sheet only) ═══════════════════════════════════════

    def _sn_populate_combos(self, cfg):
        _, sn, _ = _hub_logics()
        self.SnCmbF3.Items.Clear()
        for code, desc in sn.F3_CODES:
            self.SnCmbF3.Items.Add(u'{} — {}'.format(code, desc))
        self.SnCmbF3.SelectedIndex = self._index_of_code(self.SnCmbF3, cfg.get('f3', u'GA'))

        self.SnCmbF4.Items.Clear()
        for code, desc in sn.F4_PRESETS:
            self.SnCmbF4.Items.Add(u'{} — {}'.format(code, desc))
        self.SnCmbF4.Text = cfg.get('f4', u'ZZZ')

        self.SnCmbF5.Items.Clear()
        for code, desc in sn.F5_CODES:
            self.SnCmbF5.Items.Add(u'{} — {}'.format(code, desc))
        self.SnCmbF5.SelectedIndex = self._index_of_code(self.SnCmbF5, cfg.get('f5', u'D'))

        self.SnCmbF6.Items.Clear()
        for code, desc in sn.F6_CODES:
            self.SnCmbF6.Items.Add(u'{} — {}'.format(code, desc))
        self.SnCmbF6.SelectedIndex = self._index_of_code(self.SnCmbF6, cfg.get('f6', u'S'))

        self.SnCmbF8.Items.Clear()
        for rev in sn.F8_STAGES:
            self.SnCmbF8.Items.Add(rev)
        self.SnCmbF8.Text = cfg.get('f8', u'P01')

        self.SnTxtF1.Text = cfg.get('f1', u'')
        self.SnTxtF7.Text = cfg.get('f7', u'2200')
        self.SnTxtF9.Text = u''

    @staticmethod
    def _index_of_code(cmb, code):
        for i in range(cmb.Items.Count):
            if str(cmb.Items[i]).startswith(code):
                return i
        return 0

    def _sn_get_fvals(self):
        f1 = (self.SnTxtF1.Text or u'').strip()
        f3 = str(self.SnCmbF3.SelectedItem or u'').split(u' ')[0]
        raw_f4 = (self.SnCmbF4.Text or u'').strip()
        f4 = raw_f4.split(u' ')[0] if raw_f4 else u''
        f5 = str(self.SnCmbF5.SelectedItem or u'').split(u' ')[0]
        f6 = str(self.SnCmbF6.SelectedItem or u'').split(u' ')[0]
        f7 = (self.SnTxtF7.Text or u'').strip()
        raw_f8 = (self.SnCmbF8.Text or u'').strip()
        f8 = raw_f8.split(u' ')[0] if raw_f8 else u''
        f9 = (self.SnTxtF9.Text or u'').strip()
        return f1, f3, f4, f5, f6, f7, f8, f9

    def _sn_update_preview(self):
        try:
            _, sn, _ = _hub_logics()
            f1, f3, f4, f5, f6, f7, f8, f9 = self._sn_get_fvals()
            errors = sn.validate_fields(f1, f3, f4, f5, f6, f7, f8)
            if errors:
                self.SnTxtPreview.Text    = u''
                self.SnTxtValidation.Text = u'  ·  '.join(errors)
            else:
                num = sn.build_sheet_number(f1, f3, f4, f5, f6, f7, f8)
                existing = sn.get_existing_numbers(self.doc)
                self.SnTxtPreview.Text = num
                warn = u'⚠ Duplicate: another sheet already has this number.' \
                       if num in existing else u''
                self.SnTxtValidation.Text = warn
        except Exception as e:
            self.SnTxtValidation.Text = str(e)

    def SnFieldChanged(self, sender, args):
        self._sn_update_preview()

    def SnApply_Click(self, sender, args):
        _, sn, _ = _hub_logics()
        f1, f3, f4, f5, f6, f7, f8, f9 = self._sn_get_fvals()
        errors = sn.validate_fields(f1, f3, f4, f5, f6, f7, f8)
        if errors:
            self.LogLine(u'[Quick] Validation: ' + u'; '.join(errors))
            return
        num  = sn.build_sheet_number(f1, f3, f4, f5, f6, f7, f8)
        mode = str(sender.Tag)
        av   = self.uidoc.ActiveView
        if av is None or not isinstance(av, DB.ViewSheet):
            self.LogLine(u'[Quick] Active view is not a sheet.')
            return
        fail = 0
        with DB.Transaction(self.doc, u'NOSA — Sheet Hub Quick Apply') as t:
            t.Start()
            try:
                if mode in ('number', 'both'):
                    applied, _, _ = sn.apply_nosa_to_sheet(
                        self.doc, av, f1, f3, f4, f5, f6, f7, f8, debug=True,
                        allow_renumber=bool(self.ChkAllowRenumber.IsChecked))
                    if not applied:
                        fail = 1
                if mode in ('name', 'both') and f9:
                    av.Name = f9
            except Exception as e:
                self.LogLine(u'[Quick] Error: {}'.format(e))
                fail = 1
            t.Commit()
        self.LogLine(u'[Quick] Applied to active sheet. {} error(s).'.format(fail))
        cfg = self.LoadConfig()
        cfg.update({'f1': f1, 'f3': f3, 'f4': f4, 'f5': f5, 'f6': f6,
                    'f7': f7, 'f8': f8, 'dark_mode': self.dark_mode})
        self.SaveConfig(cfg)
        txt = self.TxtSheetsFilter.Text.strip() if hasattr(self, 'TxtSheetsFilter') else u''
        self._sheets_load(txt)

    def SnSuggest_Click(self, sender, args):
        _, sn, _ = _hub_logics()
        av = self.uidoc.ActiveView
        if av is None or not isinstance(av, DB.ViewSheet):
            self.LogLine(u'[Quick] Active view is not a sheet.')
            return
        cfg = self.LoadConfig()
        sug = sn.suggest_bulk_for_sheet(
            self.doc,
            {'id': get_id_value(av.Id), 'number': av.SheetNumber, 'name': av.Name, 'element': av},
            cfg)
        self.SnTxtF1.Text = sug['f1']
        self.SnCmbF3.SelectedIndex = self._index_of_code(self.SnCmbF3, sug['f3'])
        self.SnCmbF4.Text = sug['f4']
        self.SnCmbF5.SelectedIndex = self._index_of_code(self.SnCmbF5, sug['f5'])
        self.SnCmbF6.SelectedIndex = self._index_of_code(self.SnCmbF6, sug['f6'])
        if bool(self.ChkAllowRenumber.IsChecked):
            self.SnTxtF7.Text = sug['f7']
        self.SnCmbF8.Text = sug['f8']
        self.SnTxtF9.Text = sug.get('f9', av.Name or u'')
        self._sn_update_preview()
        self.LogLine(u'[Quick] Suggested from active sheet.')

    # ══ DUPLICATE (unified Sheets tab) ════════════════════════════════════════

    def SheetsDupCountPreset_Click(self, sender, args):
        self.TxtSheetsDupCount.Text = str(sender.Tag)

    def SheetsSetPackage_Click(self, sender, args):
        pkg = (self.CmbBulkPackage.Text or u'').strip()
        if not pkg:
            self.TxtSheetsStatus.Text = u'Enter or select a package value.'
            return
        n = 0
        for row in self._all_sheet_rows:
            if row.Selected:
                row.Package = pkg
                row.Approved = False
                n += 1
        if not n:
            self.TxtSheetsStatus.Text = u'Tick rows to set package.'
            return
        self.SheetsGrid.Items.Refresh()
        self._update_sheets_toolbar()
        self.TxtSheetsStatus.Text = u'Set package on {} row(s) — tick and apply.'.format(n)
        self.LogLine(u'[Sheets] Package set on {} row(s): {}'.format(n, pkg))

    def _dup_titleblock_id(self):
        av = self.uidoc.ActiveView
        tb_id = DB.ElementId.InvalidElementId
        if av and isinstance(av, DB.ViewSheet):
            try:
                tb_inst = DB.FilteredElementCollector(self.doc, av.Id) \
                             .OfCategory(DB.BuiltInCategory.OST_TitleBlocks) \
                             .WhereElementIsNotElementType() \
                             .FirstElement()
                if tb_inst is not None:
                    tb_id = tb_inst.GetTypeId()
            except Exception:
                pass
        if tb_id == DB.ElementId.InvalidElementId:
            _, _, sc = _hub_logics()
            types = sc.get_titleblock_types(self.doc)
            if types:
                tb_id = types[0][0]
        return tb_id

    def SheetsDuplicate_Click(self, sender, args):
        from pyrevit import forms
        sources = []
        for row in self._all_sheet_rows:
            if row.Selected:
                el = row._element or self._get_sheet_element(row._sheet_id)
                if el is not None:
                    sources.append(el)
        if not sources:
            self.TxtSheetsStatus.Text = u'Tick source sheet row(s) to duplicate.'
            return
        try:
            count = int(self.TxtSheetsDupCount.Text.strip() or u'1')
            if count < 1:
                count = 1
        except Exception:
            count = 1
        copy_vp = bool(self.ChkSheetsDupViewports.IsChecked)
        copy_pkg = bool(self.ChkDupInheritPackage.IsChecked)
        tb_id = self._dup_titleblock_id()
        if tb_id == DB.ElementId.InvalidElementId:
            forms.alert(u'No title block type found.')
            return
        _, _, sc = _hub_logics()
        self.SetLoading(True, u'Duplicating sheets…')
        try:
            created, errors = sc.duplicate_sheets_nosa_incremental(
                self.doc, sources, count, tb_id,
                copy_viewports=copy_vp, copy_package=copy_pkg)
            self.LogLine(u'[Sheets] Duplicated {} sheet(s). {} error(s).'.format(
                created, len(errors)))
            if errors:
                self.LogLine(u'  ' + u'; '.join(errors[:5]))
            txt = self.TxtSheetsFilter.Text.strip() if hasattr(self, 'TxtSheetsFilter') else u''
            self._sheets_load(txt)
            if created and self._all_sheet_rows:
                self._run_protocol_suggest()
            self.TxtSheetsStatus.Text = (
                u'Created {} sheet(s). Edit fields, tick rows, then apply.'.format(created))
        except Exception as e:
            forms.alert(u'Duplicate failed: {}'.format(e))
        finally:
            self.SetLoading(False)

    # ── Shared ────────────────────────────────────────────────────────────────

    def Close_Click(self, sender, args):
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
