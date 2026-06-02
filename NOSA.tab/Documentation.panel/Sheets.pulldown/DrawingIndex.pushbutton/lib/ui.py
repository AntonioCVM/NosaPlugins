# -*- coding: utf-8 -*-
import os, sys, imp, json
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from System.Windows.Controls import CheckBox as _WPFCheckBox
from pyrevit import forms, revit, DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils import sheet_protocol as _sp
_logic = imp.load_source('drawingidx_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

from nosa_utils.base_window import NOSAWindow

_CONFIGS_ROOT = os.path.join(
    os.getenv('APPDATA', ''), 'pyRevit', 'Extensions',
    'NOSA.extension', 'NOSA_Configs'
)
_COL_ORDER_FILE = os.path.join(_CONFIGS_ROOT, 'drawing_index_columns.json')
_COL_VIS_FILE   = os.path.join(_CONFIGS_ROOT, 'drawing_index_col_vis.json')

# Short DataGrid headers → SheetRow attribute names (must match Sheet Composer)
_HEADER_TO_ATTR = {
    'Name':        'SheetName',
    'Project No.': 'ProjNum',
    'Originator':  'Originator',
    'Func.':       'FuncBreak',
    'Spatial':     'SpatBreak',
    'Form':        'FormId',
    'Disc.':       'Discipline',
    'Doc No.':     'DocNum',
    'Rev':         'Revision',
    'Rev Date':    'RevDate',
    'Rev Desc':    'RevDesc',
    'Scale':       'Scale',
    'Drawn By':    'DrawnBy',
    'Checked By':  'CheckedBy',
    'Approved By': 'ApprovedBy',
    'Issue Date':  'IssueDate',
}


class SheetRow(object):
    """Row bound to DataGrid — all NOSA protocol fields as direct attributes."""
    def __init__(self, i, s, proj_info=None):
        self._element  = s.get('element')
        self.RowNum    = i
        self.Number    = s['number']
        self.SheetName = s['name']
        self.HasPending = False
        pi = proj_info or {}
        self.ProjNum    = s.get('Project Number', '')    or pi.get('Project Number', '')
        self.Originator = s.get('Originator', '')        # only from sheet param "Originator"
        self.FuncBreak  = s.get('Functional Breakdown', '')
        self.SpatBreak  = s.get('Spatial Breakdown', '')
        self.FormId     = s.get('Form', '') or s.get('Form Identifier', '')
        self.Discipline = s.get('Discipline', '')
        self.DocNum     = s.get('Document Number', '')
        self.Revision   = s.get('Current Revision', '')  or s.get('revision', '')
        self.RevDate    = s.get('Current Revision Date', '') or s.get('revision_date', '')
        self.RevDesc    = s.get('Current Revision Description', '') or s.get('revision_desc', '')
        self.Scale      = s.get('Scale', '')
        self.DrawnBy    = s.get('Drawn By', '')
        self.CheckedBy  = s.get('Checked By', '')
        self.ApprovedBy = s.get('Approved By', '')
        self.IssueDate  = s.get('Sheet Issue Date', '')
        self.ViewCount  = s.get('viewport_count', 0)
        self._param_map = {
            'SheetName':  'Sheet Name',
            'ProjNum':    'Project Number',
            'Originator': 'Originator',
            'FuncBreak':  'Functional Breakdown',
            'SpatBreak':  'Spatial Breakdown',
            'FormId':     'Form',
            'Discipline': 'Discipline',
            'DocNum':     'Document Number',
            'Revision':   'Current Revision',
            'RevDate':    'Current Revision Date',
            'RevDesc':    'Current Revision Description',
            'Scale':      'Scale',
            'DrawnBy':    'Drawn By',
            'CheckedBy':  'Checked By',
            'ApprovedBy': 'Approved By',
            'IssueDate':  'Sheet Issue Date',
        }


class DrawingIndexWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'drawing_index')
        self.doc             = doc
        self._sheets         = []
        self._proj_info      = self._read_project_info()
        self._rows           = ObservableCollection[SheetRow]()
        self._pending_changes = {}  # {sheet_number: {attr_name: new_val}}
        self.GridSheets.ItemsSource = self._rows
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        self.Load_Click(None, None)
        self._load_col_order()
        self._col_checkboxes = []
        self._setup_col_checkboxes()

    # ── project info ─────────────────────────────────────────────────────────

    def _read_project_info(self):
        """Read ProjectInformation parameters into a dict. Originator NOT from CLIENT_NAME."""
        info = {}
        try:
            pi = self.doc.ProjectInformation
            if pi:
                for p in pi.Parameters:
                    try:
                        if p.Definition:
                            val = p.AsString() or p.AsValueString() or ''
                            if val:
                                info[p.Definition.Name] = val
                    except Exception:
                        pass
                # Only PROJECT_NUMBER from standard BIPs; Originator must come
                # from a shared parameter named "Originator" on the sheets themselves.
                try:
                    p = pi.get_Parameter(DB.BuiltInParameter.PROJECT_NUMBER)
                    if p and p.AsString():
                        info.setdefault('Project Number', p.AsString())
                except Exception:
                    pass
        except Exception:
            pass
        return info

    # ── column order persistence ──────────────────────────────────────────────

    def _save_col_order(self):
        try:
            if not os.path.exists(_CONFIGS_ROOT):
                os.makedirs(_CONFIGS_ROOT)
            order = [str(col.Header) for col in self.GridSheets.Columns]
            with open(_COL_ORDER_FILE, 'w') as f:
                json.dump(order, f)
            self._save_col_vis()
            forms.alert("Column layout saved.")
        except Exception as e:
            forms.alert("Could not save column layout: {}".format(e))

    def _load_col_order(self):
        try:
            if os.path.exists(_COL_ORDER_FILE):
                with open(_COL_ORDER_FILE, 'r') as f:
                    order = json.load(f)
                col_map = {str(col.Header): col for col in self.GridSheets.Columns}
                for new_idx, header in enumerate(order):
                    if header in col_map:
                        col = col_map[header]
                        old_idx = self.GridSheets.Columns.IndexOf(col)
                        if old_idx >= 0 and old_idx != new_idx:
                            self.GridSheets.Columns.Move(old_idx, new_idx)
        except Exception:
            pass

    # ── column visibility ─────────────────────────────────────────────────────

    def _load_col_vis(self):
        try:
            if os.path.exists(_COL_VIS_FILE):
                with open(_COL_VIS_FILE, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_col_vis(self):
        try:
            if not os.path.exists(_CONFIGS_ROOT):
                os.makedirs(_CONFIGS_ROOT)
            vis = {str(cb.Content): bool(cb.IsChecked) for cb in self._col_checkboxes}
            with open(_COL_VIS_FILE, 'w') as f:
                json.dump(vis, f)
        except Exception:
            pass

    def _make_col_toggle(self, col):
        v = System.Windows.Visibility
        def _toggle(sender, args):
            col.Visibility = v.Visible if sender.IsChecked else v.Collapsed
            self._save_col_vis()
        return _toggle

    def _setup_col_checkboxes(self):
        saved = self._load_col_vis()
        v = System.Windows.Visibility
        for col in self.GridSheets.Columns:
            header = str(col.Header or '')
            if not header or header in ('#', 'Views'):
                continue
            visible = saved.get(header, True)
            cb = _WPFCheckBox()
            cb.Content = header
            cb.IsChecked = visible
            cb.Margin = System.Windows.Thickness(0, 2, 0, 2)
            col.Visibility = v.Visible if visible else v.Collapsed
            cb.Click += self._make_col_toggle(col)
            self._col_checkboxes.append(cb)
            self.ColCheckboxPanel.Children.Add(cb)

    def ConfigCols_Click(self, sender, args):
        v = System.Windows.Visibility
        panel = self.ColCheckboxPanel
        panel.Visibility = (v.Collapsed if panel.Visibility == v.Visible else v.Visible)

    # ── filter / load ─────────────────────────────────────────────────────────

    def Filter_Changed(self, sender, args):
        self._apply_filter()

    def _apply_filter(self):
        text = self.TxtFilter.Text.strip() if hasattr(self, 'TxtFilter') else ''
        self._rows.Clear()
        self._sheets = _logic.collect_sheets(self.doc, text)
        for i, s in enumerate(self._sheets, 1):
            self._rows.Add(SheetRow(i, s, self._proj_info))
        self.TxtCount.Text = "{} sheets".format(len(self._sheets))
        self.BtnCsv.IsEnabled  = len(self._sheets) > 0
        self.BtnHtml.IsEnabled = len(self._sheets) > 0
        # Re-apply pending-change highlights
        for row in self._rows:
            if row.Number in self._pending_changes:
                row.HasPending = True
        self.GridSheets.Items.Refresh()

    def Load_Click(self, sender, args):
        self.SetLoading(True, 'Loading sheets...')
        try:
            self._apply_filter()
        except Exception as e:
            forms.alert("Error: {}".format(e))
        finally:
            self.SetLoading(False)

    # ── cell editing ──────────────────────────────────────────────────────────

    def Grid_CellEditEnding(self, sender, args):
        """Store edited value in _pending_changes; do NOT write to Revit yet."""
        try:
            row = args.Row.Item
            if not hasattr(row, '_element') or row._element is None:
                return
            col = args.Column
            if not hasattr(col, 'Header') or not col.Header:
                return
            hdr = str(col.Header)
            attr_name = _HEADER_TO_ATTR.get(hdr)
            if attr_name is None:
                attr_name = next(
                    (k for k, v in row._param_map.items()
                     if v == hdr or k == hdr), None
                )
            if attr_name is None:
                return
            new_val = str(args.EditingElement.Text
                          if hasattr(args.EditingElement, 'Text') else '')
            sheet_num = row.Number
            if sheet_num not in self._pending_changes:
                self._pending_changes[sheet_num] = {}
            self._pending_changes[sheet_num][attr_name] = new_val
            setattr(row, attr_name, new_val)
            row.HasPending = True
            self.BtnApply.IsEnabled = True
            try:
                import System.Windows.Threading as _swt
                def _do_refresh():
                    try:
                        self.GridSheets.Items.Refresh()
                    except Exception:
                        pass
                self.GridSheets.Dispatcher.BeginInvoke(
                    _swt.DispatcherPriority.Background,
                    System.Action(_do_refresh))
            except Exception:
                pass
        except Exception as e:
            forms.alert("Could not track edit: {}".format(e))

    # ── apply changes ─────────────────────────────────────────────────────────

    def Apply_Click(self, sender, args):
        """Write all pending changes to Revit in a single transaction."""
        if not self._pending_changes:
            return
        ok = fail = 0
        try:
            with revit.Transaction('NOSA — Apply drawing index edits'):
                for row in self._rows:
                    sheet_num = row.Number
                    if sheet_num not in self._pending_changes or row._element is None:
                        continue
                    el      = row._element
                    changes = self._pending_changes[sheet_num]
                    for attr_name, new_val in changes.items():
                        try:
                            param_name = row._param_map.get(attr_name, attr_name)
                            if param_name == 'Form' or attr_name == 'FormId':
                                okt, _f = _sp.write_form_value(self.doc, el, new_val)
                                if okt > 0:
                                    ok += 1
                                else:
                                    fail += 1
                                continue
                            p = el.LookupParameter(param_name)
                            if not p:
                                bip_map = {
                                    'Sheet Name': DB.BuiltInParameter.SHEET_NAME,
                                    'Drawn By':   DB.BuiltInParameter.SHEET_DRAWN_BY,
                                    'Checked By': DB.BuiltInParameter.SHEET_CHECKED_BY,
                                    'Scale':      DB.BuiltInParameter.VIEW_SCALE_PULLDOWN_METRIC,
                                }
                                if param_name in bip_map:
                                    p = el.get_Parameter(bip_map[param_name])
                            if p and not p.IsReadOnly:
                                p.Set(new_val)
                                ok += 1
                            else:
                                fail += 1
                        except Exception:
                            fail += 1
                    row.HasPending = False
            self._pending_changes.clear()
            self.GridSheets.Items.Refresh()
            self.BtnApply.IsEnabled = False
            forms.alert("Applied: {}   /   Failed: {}".format(ok, fail))
        except Exception as e:
            forms.alert("Apply failed: {}".format(e))

    # ── column order ──────────────────────────────────────────────────────────

    def SaveColOrder_Click(self, sender, args):
        self._save_col_order()

    # ── exports ───────────────────────────────────────────────────────────────

    def ExportCsv_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _logic.export_csv(self._sheets, path)
            forms.alert("CSV exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))

    def ExportHtml_Click(self, sender, args):
        path = forms.save_file(file_ext='html')
        if not path:
            return
        try:
            _logic.export_html(self._sheets, path, _logic.get_project_name(self.doc))
            import os as _os
            _os.startfile(path)
        except Exception as e:
            forms.alert("Export failed: {}".format(e))
