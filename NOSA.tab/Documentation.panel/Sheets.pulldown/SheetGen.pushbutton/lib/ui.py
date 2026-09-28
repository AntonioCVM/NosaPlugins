# -*- coding: utf-8 -*-
import imp
import os, sys, re
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from System.Windows.Controls import DataGridTextColumn
from System.Windows.Data import Binding
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

try:
    unicode
except NameError:
    unicode = str
_logic    = imp.load_source('sheetcomposer_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))
_di_logic = imp.load_source('drawingindex_logic',
                 os.path.abspath(os.path.join(os.path.dirname(__file__),
                                              '..', '..', 'DrawingIndex.nobutton', 'lib', 'logic.py')))

# Column header → attr_name (for the Edit tab CellEditEnding handler)
_HEADER_TO_ATTR = {
    'Name':                         'SheetName',
    'Project No.':                  'ProjNum',
    'Originator':                   'Originator',
    'Func.':                        'FuncBreak',
    'Spatial':                      'SpatBreak',
    'Form':                         'FormId',
    'Disc.':                        'Discipline',
    'Doc No.':                      'DocNum',
    'Rev':                          'Revision',
    'Rev Date':                     'RevDate',
    'Rev Desc':                     'RevDesc',
    'Scale':                        'Scale',
    'Drawn By':                     'DrawnBy',
    'Checked By':                   'CheckedBy',
    'Approved By':                  'ApprovedBy',
    'Issue Date':                   'IssueDate',
}


def _safe_attr(header):
    """Convert a CSV column header to a safe Python attribute name."""
    s = re.sub(r'[^A-Za-z0-9_]', '_', header)
    if s and s[0].isdigit():
        s = '_' + s
    return s or '_col'


class EditSheetRow(object):
    """Existing sheet row for the Edit tab."""

    _param_map = {
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

    def __init__(self, i, data):
        self._element  = data['element']
        self.RowNum    = i
        self.Number    = data['number']
        self.SheetName = data['name']
        self.ProjNum    = data.get('Project Number', '')
        self.Originator = data.get('Originator', '')
        self.FuncBreak  = data.get('Functional Breakdown', '')
        self.SpatBreak  = data.get('Spatial Breakdown', '')
        self.FormId     = data.get('Form', '') or data.get('Form Identifier', '')
        self.Discipline = data.get('Discipline', '')
        self.DocNum     = data.get('Document Number', '')
        self.Revision   = data.get('Current Revision', '')
        self.RevDate    = data.get('Current Revision Date', '')
        self.RevDesc    = data.get('Current Revision Description', '')
        self.Scale      = data.get('Scale', '')
        self.DrawnBy    = data.get('Drawn By', '')
        self.CheckedBy  = data.get('Checked By', '')
        self.ApprovedBy = data.get('Approved By', '')
        self.IssueDate  = data.get('Sheet Issue Date', '')
        self.ViewCount  = data.get('view_count', 0)
        self.HasPending = False


class NewSheetRow(object):
    """New sheet row for the Create grid (Add Row / bulk add; CanUserAddRows disabled for IronPython)."""
    def __init__(self):
        self.Number     = ''
        self.SheetName  = ''
        self.ProjNum    = ''
        self.Originator = ''
        self.FuncBreak  = ''
        self.SpatBreak  = ''
        self.FormId     = ''
        self.Discipline = ''
        self.DocNum     = ''
        self.DrawnBy    = ''
        self.CheckedBy  = ''
        self.ApprovedBy = ''

    def to_dict(self):
        return {
            'number':                    self.Number,
            'name':                      self.SheetName,
            'Project Number':            self.ProjNum,
            'Originator':                self.Originator,
            'Functional Breakdown':      self.FuncBreak,
            'Spatial Breakdown':         self.SpatBreak,
            'Form':                      self.FormId,
            'Discipline':                self.Discipline,
            'Document Number':           self.DocNum,
            'Drawn By':                  self.DrawnBy,
            'Checked By':                self.CheckedBy,
            'Approved By':               self.ApprovedBy,
        }


class DiSheetRow(object):
    """Lightweight row for the Drawing Index tab."""
    def __init__(self, i, d):
        self.idx            = i
        self.number         = d.get('number', '')
        self.name           = d.get('name', '')
        self.revision       = d.get('revision', '')
        self.revision_date  = d.get('revision_date', '')
        self.revision_desc  = d.get('revision_desc', '')
        self.scale          = d.get('scale', '')
        self.drawn_by       = d.get('drawn_by', '')
        self.viewport_count = d.get('viewport_count', 0)


class TbItem(object):
    def __init__(self, mid, name):
        self.Id   = mid
        self.Name = name


class SourceSheetItem(object):
    def __init__(self, sheet):
        self._element = sheet
        self.Label    = u'{} — {}'.format(sheet.SheetNumber, sheet.Name)


class CsvRow(object):
    """Dynamic row for the Import CSV preview DataGrid."""
    def __init__(self, data, safe_keys):
        for orig_key, safe_key in safe_keys.items():
            setattr(self, safe_key, data.get(orig_key, ''))


class SheetComposerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'sheet_composer')
        self.doc = doc

        # ── Edit tab state ────────────────────────────────────────────────────
        self._all_edit_data = []
        self._edit_rows     = ObservableCollection[EditSheetRow]()
        self._pending       = {}  # {sheet_number: {'_element': el, attr_name: val}}
        self.GridEdit.ItemsSource = self._edit_rows

        # ── Create tab state ──────────────────────────────────────────────────
        self._new_rows = ObservableCollection[NewSheetRow]()
        self.GridCreate.ItemsSource = self._new_rows

        # ── Renumber tab state ────────────────────────────────────────────────
        self._renum_rows = ObservableCollection[EditSheetRow]()
        self.GridRenum.ItemsSource = self._renum_rows

        # ── Drawing Index tab state ───────────────────────────────────────────
        self._di_raw   = []      # all sheet dicts from DrawingIndex logic
        self._di_rows  = ObservableCollection[DiSheetRow]()
        self.GridDrawingIndex.ItemsSource = self._di_rows

        # ── Import tab state ──────────────────────────────────────────────────
        self._csv_path    = None
        self._csv_headers = []
        self._csv_rows    = []

        # ── Title block ComboBoxes ────────────────────────────────────────────
        tbs = _logic.get_titleblock_types(doc)
        tb_items = [TbItem(mid, n) for mid, n in tbs]
        self.CboTitleblockCreate.ItemsSource = tb_items
        self.CboTitleblockCreate.SelectedIndex = 0 if tbs else -1
        self.CboTitleblockImport.ItemsSource = tb_items
        self.CboTitleblockImport.SelectedIndex = 0 if tbs else -1

        self._load_all_sheets()
        self._ensure_create_placeholder_row()

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

        # ── Extra parameter columns (user-configurable, persisted) ────────────
        self._extra_cols        = []   # DataGridTextColumn refs added to GridEdit
        self._extra_header_attr = {}   # header → row attribute
        self._extra_attr_param  = {}   # row attribute → Revit parameter name
        self._extra_params = [p for p in cfg.get('extra_edit_params', []) if p]
        if self._extra_params:
            self._rebuild_extra_columns()
            self._apply_edit_filter()

        # Wired here, not in XAML: the initial tab selection fires during
        # LoadComponent, before the sidebar controls exist.
        self.TabMain.SelectionChanged += self.Tab_Changed
        self.Tab_Changed(self.TabMain, None)

    def _rebuild_extra_columns(self):
        for col in self._extra_cols:
            try:
                self.GridEdit.Columns.Remove(col)
            except Exception:
                pass
        self._extra_cols        = []
        self._extra_header_attr = {}
        self._extra_attr_param  = {}
        for pname in self._extra_params:
            attr = 'X_' + _safe_attr(pname)
            col = DataGridTextColumn()
            col.Header  = pname
            col.Binding = Binding(attr)
            col.Width   = System.Windows.Controls.DataGridLength(110)
            self.GridEdit.Columns.Add(col)
            self._extra_cols.append(col)
            self._extra_header_attr[pname] = attr
            self._extra_attr_param[attr]   = pname

    def EditColumns_Click(self, sender, args):
        try:
            names = _logic.get_sheet_param_names(self.doc)
        except Exception as e:
            forms.alert(u'Could not read sheet parameters: {}'.format(e))
            return
        if not names:
            forms.alert(u'No additional writable sheet parameters found.')
            return
        picked = forms.SelectFromList.show(
            names, multiselect=True,
            title=u'Extra parameter columns for the Edit grid',
            button_name=u'Set Columns')
        if picked is None:
            return
        self._extra_params = list(picked)
        cfg = self.LoadConfig()
        cfg['extra_edit_params'] = self._extra_params
        self.SaveConfig(cfg)
        self._rebuild_extra_columns()
        self._apply_edit_filter()

    # ── data loading ──────────────────────────────────────────────────────────

    def _load_all_sheets(self):
        """Full reload from Revit — call on init and after mutations."""
        self.SetLoading(True, 'Loading sheets...')
        try:
            self._all_edit_data = _logic.collect_editable_sheets(self.doc)

            # Populate renumber grid (unfiltered)
            self._renum_rows.Clear()
            for i, d in enumerate(self._all_edit_data, 1):
                self._renum_rows.Add(EditSheetRow(i, d))

            # Populate clone source ComboBox
            raw = _logic.get_all_sheets(self.doc)
            sources = [SourceSheetItem(r['sheet']) for r in raw]
            self.CboCloneSource.ItemsSource = sources
            if sources:
                self.CboCloneSource.SelectedIndex = 0

            self._apply_edit_filter()
        except Exception as e:
            forms.alert("Error loading sheets: {}".format(e))
        finally:
            self.SetLoading(False)

    def _ensure_create_placeholder_row(self):
        """Ensure at least one blank row exists on the Create grid."""
        try:
            if self._new_rows.Count == 0:
                self._new_rows.Add(NewSheetRow())
        except Exception:
            pass

    def EditGrid_SelectionChanged(self, sender, args):
        """Keeps bindings stable if no action on selection."""
        pass

    def DuplicateSelectedFromEdit_Click(self, sender, args):
        """Full clone (duplicate model views where applicable). Uses title block chosen in sidebar."""
        rows = []
        try:
            for o in self.GridEdit.SelectedItems:
                if isinstance(o, EditSheetRow):
                    rows.append(o)
        except Exception:
            pass
        if not rows:
            forms.alert(
                'Select one or more sheets in the Edit Sheets grid '
                '(use Ctrl / Shift-click).')
            return
        tb_item = self.CboTitleblockCreate.SelectedItem
        if not tb_item:
            forms.alert(
                'Select a title block in the sidebar '
                '("Title block", visible on Create / Clone sidebar).')
            return
        if not forms.alert(
                'Duplicate {} sheet(s)?\n'
                'New numbers: ORIG-COPY, ORIG-COPY2, ... '
                '(model views duplicated; legends/schedules reused).'.format(len(rows)),
                yes=True, no=True):
            return
        elems = [r._element for r in rows]
        self.SetLoading(True, 'Duplicating...')
        try:
            created, errors = _logic.duplicate_sheets_with_viewports(
                self.doc, elems, tb_item.Id)
        except Exception as e:
            self.SetLoading(False)
            forms.alert('Duplicate failed: {}'.format(e))
            return
        self.SetLoading(False)
        msg = 'Created: {}'.format(created)
        if errors:
            msg += '\n\nWarnings:\n' + '\n'.join(errors[:8])
        forms.alert(msg, title='Duplicate sheets')
        self._load_all_sheets()

    def SendSelectionToCreateGrid_Click(self, sender, args):
        """Pre-fill blank-layout sheet rows using parameters from selection (adjust numbers → Create Sheets)."""
        rows = []
        try:
            for o in self.GridEdit.SelectedItems:
                if isinstance(o, EditSheetRow):
                    rows.append(o)
        except Exception:
            pass
        if not rows:
            forms.alert(
                'Select one or more sheets in the Edit grid first.')
            return
        try:
            lowered = set(_logic._existing_sheet_numbers_lower(self.doc))
        except Exception:
            lowered = set()
        self._touch_create_placeholder_to_template()
        for er in sorted(rows, key=lambda r: r.Number or ''):
            nr = NewSheetRow()
            stem = (er.Number or u'SHEET').strip() or u'SHEET'
            nr.Number = _logic.allocate_unique_sheet_number(lowered, stem)
            nr.SheetName  = er.SheetName or u''
            nr.ProjNum    = er.ProjNum or u''
            nr.Originator = er.Originator or u''
            nr.FuncBreak  = er.FuncBreak or u''
            nr.SpatBreak  = er.SpatBreak or u''
            nr.FormId     = er.FormId or u''
            nr.Discipline = er.Discipline or u''
            nr.DocNum     = er.DocNum or u''
            nr.DrawnBy    = er.DrawnBy or u''
            nr.CheckedBy  = er.CheckedBy or u''
            nr.ApprovedBy = er.ApprovedBy or u''
            self._new_rows.Add(nr)
        self.TabMain.SelectedIndex = 1
        self.GridCreate.Items.Refresh()
        forms.alert(
            'Added {} row(s) to the Create / Clone tab. '
            'Review sheet numbers, then choose title block and CREATE SHEETS.'.format(len(rows)),
            title='Create from selection')

    def _touch_create_placeholder_to_template(self):
        """If Create grid only has one untouched blank row, clear it before appending."""
        try:
            if self._new_rows.Count != 1:
                return
            lone = self._new_rows[0]
            for attr in ('Number', 'SheetName', 'ProjNum', 'Originator', 'FuncBreak',
                         'SpatBreak', 'FormId', 'Discipline', 'DocNum', 'DrawnBy',
                         'CheckedBy', 'ApprovedBy'):
                v = getattr(lone, attr, None)
                if v is None:
                    continue
                try:
                    if unicode(v).strip():
                        return
                except Exception:
                    pass
            self._new_rows.Clear()
        except Exception:
            pass

    def BulkAddRows_Click(self, sender, args):
        try:
            n = int((self.TxtBulkRows.Text or '1').strip())
        except ValueError:
            forms.alert('Rows count must be a whole number.')
            return
        n = max(1, min(int(n), 200))
        for _ in range(n):
            self._new_rows.Add(NewSheetRow())

    def _apply_edit_filter(self):
        """Re-filter already-loaded data for the Edit tab."""
        filt = (self.TxtEditFilter.Text or '').strip().lower()
        self._edit_rows.Clear()
        i = 1
        for d in self._all_edit_data:
            if filt and filt not in d['number'].lower() and filt not in d['name'].lower():
                continue
            row = EditSheetRow(i, d)
            for pname, attr in getattr(self, '_extra_header_attr', {}).items():
                try:
                    setattr(row, attr, _logic._param_str(d['element'], pname))
                except Exception:
                    setattr(row, attr, u'')
            # Restore pending highlight
            if d['number'] in self._pending:
                row.HasPending = True
            self._edit_rows.Add(row)
            i += 1
        count = len(list(self._edit_rows))
        self.TxtSheetCount.Text = '{} sheets'.format(count)
        self.BtnExportEdit.IsEnabled = count > 0
        try:
            self.BtnExportEditXlsx.IsEnabled = count > 0
        except Exception:
            pass

    # ── tab switching ─────────────────────────────────────────────────────────

    def Tab_Changed(self, sender, args):
        try:
            idx = self.TabMain.SelectedIndex
            v   = System.Windows.Visibility
            panels = [self.SidebarEdit, self.SidebarCreate, self.SidebarImport,
                      self.SidebarDrawingIdx, self.SidebarRenum]
            for p in panels:
                p.Visibility = v.Collapsed
            if 0 <= idx < len(panels):
                panels[idx].Visibility = v.Visible
            # Tab 3 = Drawing Index (0-indexed)
            if idx == 3:
                self._populate_drawing_index()
        except Exception:
            pass

    # ── drawing index tab ─────────────────────────────────────────────────────

    def _populate_drawing_index(self, filter_text=''):
        """Load / refresh the Drawing Index grid."""
        try:
            if not self._di_raw:
                self._di_raw = _di_logic.collect_sheets(self.doc)
            filt = filter_text.lower().strip()
            self._di_rows.Clear()
            for i, d in enumerate(self._di_raw, 1):
                if filt and filt not in (d.get('number','') + ' ' + d.get('name','')).lower():
                    continue
                self._di_rows.Add(DiSheetRow(i, d))
            has_rows = self._di_rows.Count > 0
            self.BtnExportIdxCsv.IsEnabled  = has_rows
            self.BtnExportIdxHtml.IsEnabled = has_rows
        except Exception as e:
            forms.alert("Drawing Index error: {}".format(e))

    def DrawingFilter_Changed(self, sender, args):
        try:
            self._populate_drawing_index(self.TxtDiFilter.Text or '')
        except Exception:
            pass

    def ExportIdxCsv_Click(self, sender, args):
        if not self._di_raw:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _di_logic.export_csv(self._di_raw, path)
            forms.alert("Drawing Index exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export error:\n{}".format(e))

    def ExportIdxHtml_Click(self, sender, args):
        if not self._di_raw:
            return
        path = forms.save_file(file_ext='html')
        if not path:
            return
        try:
            proj = _di_logic.get_project_name(self.doc)
            _di_logic.export_html(self._di_raw, path, proj)
            forms.alert("Drawing Index (HTML) exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export error:\n{}".format(e))

    # ── edit tab ──────────────────────────────────────────────────────────────

    def EditFilter_Changed(self, sender, args):
        self._apply_edit_filter()

    def Edit_CellEditEnding(self, sender, args):
        try:
            row = args.Row.Item
            if not isinstance(row, EditSheetRow):
                return
            col = args.Column
            if not hasattr(col, 'Header') or not col.Header:
                return
            attr_name = _HEADER_TO_ATTR.get(str(col.Header))
            if attr_name is None:
                attr_name = getattr(self, '_extra_header_attr', {}).get(str(col.Header))
            if attr_name is None:
                return
            new_val = str(args.EditingElement.Text
                          if hasattr(args.EditingElement, 'Text') else '')
            snum = row.Number
            if snum not in self._pending:
                self._pending[snum] = {'_element': row._element}
            self._pending[snum][attr_name] = new_val
            setattr(row, attr_name, new_val)
            row.HasPending = True
            self.BtnApply.IsEnabled = True
            # Defer refresh so it runs AFTER the WPF edit transaction closes
            try:
                import System.Windows.Threading as _swt
                def _do_refresh():
                    try:
                        self.GridEdit.Items.Refresh()
                    except Exception:
                        pass
                self.GridEdit.Dispatcher.BeginInvoke(
                    _swt.DispatcherPriority.Background,
                    System.Action(_do_refresh))
            except Exception:
                pass
        except Exception as e:
            forms.alert("Could not track edit: {}".format(e))

    def Apply_Click(self, sender, args):
        if not self._pending:
            return
        # Build changes dict: {snum: {'_element': el, param_name: val}}
        changes = {}
        for snum, change_dict in self._pending.items():
            el = change_dict.get('_element')
            if el is None:
                continue
            param_changes = {'_element': el}
            for attr_name, val in change_dict.items():
                if attr_name == '_element':
                    continue
                pname = EditSheetRow._param_map.get(attr_name)
                if not pname:
                    pname = getattr(self, '_extra_attr_param', {}).get(attr_name)
                if pname:
                    param_changes[pname] = val
            changes[snum] = param_changes

        self.SetLoading(True, 'Applying changes...')
        try:
            ok, failed = _logic.update_sheets_batch(self.doc, changes)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Apply failed: {}".format(e))
            return
        self.SetLoading(False)
        self._pending.clear()
        for row in self._edit_rows:
            row.HasPending = False
        self.GridEdit.Items.Refresh()
        self.BtnApply.IsEnabled = False
        forms.alert("Applied: {}   Failed: {}".format(ok, failed))

    def ExportEdit_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _logic.export_csv_sheets(self._all_edit_data, path)
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))

    def ExportEditXlsx_Click(self, sender, args):
        path = forms.save_file(file_ext='xlsx')
        if not path:
            return
        try:
            _logic.export_xlsx_sheets(self._all_edit_data, path)
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))

    # ── create tab ────────────────────────────────────────────────────────────

    def OpenPlaceViews_Click(self, sender, args):
        try:
            _pv = imp.load_source('sheetgen_place_ui',
                                  os.path.join(os.path.dirname(__file__), 'ui_place.py'))
            win = _pv.PlaceViewsWindow(self.doc)
            win.ShowDialog()
            self._load_all_sheets()
        except Exception as e:
            forms.alert(u'Could not open Place Views: {}'.format(e))

    def AddRow_Click(self, sender, args):
        self._new_rows.Add(NewSheetRow())

    def RemoveRow_Click(self, sender, args):
        for row in list(self.GridCreate.SelectedItems):
            try:
                self._new_rows.Remove(row)
            except Exception:
                pass
        self._ensure_create_placeholder_row()

    def CreateSheets_Click(self, sender, args):
        rows = [
            r for r in self._new_rows
            if isinstance(r, NewSheetRow) and ((r.Number or '').strip())
        ]
        if not rows:
            forms.alert("Add at least one row with a sheet number.")
            return
        tb_item = self.CboTitleblockCreate.SelectedItem
        if not tb_item:
            forms.alert("Select a title block.")
            return
        if not forms.alert(
            "Create {} sheet(s)?".format(len(rows)), yes=True, no=True
        ):
            return
        data = [r.to_dict() for r in rows]
        self.SetLoading(True, "Creating sheets...")
        try:
            created, errors = _logic.create_sheets_from_data(self.doc, data, tb_item.Id)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Create failed: {}".format(e))
            return
        self.SetLoading(False)
        msg = "Created: {}".format(created)
        if errors:
            msg += "\nErrors:\n" + '\n'.join(errors[:5])
        forms.alert(msg, title="Create Sheets")
        self._new_rows.Clear()
        self._ensure_create_placeholder_row()
        self._load_all_sheets()

    def Clone_Click(self, sender, args):
        src_item = self.CboCloneSource.SelectedItem
        if not src_item:
            forms.alert("Select a source sheet.")
            return
        tb_item = self.CboTitleblockCreate.SelectedItem
        if not tb_item:
            forms.alert("Select a title block.")
            return
        try:
            count = int(self.TxtCloneCount.Text or '1')
            start = int(self.TxtCloneStart.Text or '1')
        except ValueError:
            forms.alert("Count and start number must be integers.")
            return
        source_el = src_item._element
        name_tmpl = self.TxtCloneName.Text or (source_el.Name + ' ({n})')
        if not forms.alert(
            "Clone '{} {}' {} time(s) starting at {}?".format(
                source_el.SheetNumber, source_el.Name, count, start),
            yes=True, no=True
        ):
            return
        self.SetLoading(True, "Cloning sheets...")
        try:
            created, errors = _logic.clone_sheets_batch(
                self.doc, source_el, count, start, name_tmpl, tb_item.Id)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Clone failed: {}".format(e))
            return
        self.SetLoading(False)
        msg = "Created: {}".format(created)
        if errors:
            msg += "\nErrors:\n" + '\n'.join(errors[:5])
        forms.alert(msg, title="Clone Sheets")
        self._load_all_sheets()

    # ── import tab ────────────────────────────────────────────────────────────

    def BrowseCSV_Click(self, sender, args):
        path = forms.pick_file(file_ext='csv')
        if not path:
            return
        self._load_import_file(path, _logic.parse_csv_sheets, u'CSV')

    def BrowseExcel_Click(self, sender, args):
        path = forms.pick_file(file_ext='xlsx')
        if not path:
            return
        self._load_import_file(path, _logic.parse_xlsx_sheets, u'Excel')

    def _load_import_file(self, path, parser, label):
        try:
            headers, rows = parser(path)
        except Exception as e:
            forms.alert(u"Could not read {}: {}".format(label, e))
            return
        self._csv_path    = path
        self._csv_headers = headers
        self._csv_rows    = rows
        self.TxtCsvPath.Text = path
        self.BtnImport.IsEnabled = True

        # Build safe key mapping
        safe_keys = {h: _safe_attr(h) for h in headers}

        # Populate dynamic DataGrid columns (max 20 for readability)
        self.GridImport.Columns.Clear()
        for header in headers[:20]:
            col = DataGridTextColumn()
            col.Header = header
            col.Binding = Binding(safe_keys[header])
            col.Width = System.Windows.Controls.DataGridLength(120)
            self.GridImport.Columns.Add(col)

        # Populate preview rows (max 500)
        csv_rows = ObservableCollection[CsvRow]()
        for r in rows[:500]:
            csv_rows.Add(CsvRow(r, safe_keys))
        self.GridImport.ItemsSource = csv_rows

    def Import_Click(self, sender, args):
        if not self._csv_rows:
            forms.alert("Browse a CSV file first.")
            return
        tb_item = self.CboTitleblockImport.SelectedItem
        if not tb_item:
            forms.alert("Select a title block (needed for creating new sheets).")
            return
        if self.RbUpdate.IsChecked:
            mode = 'update'
        elif self.RbBoth.IsChecked:
            mode = 'both'
        else:
            mode = 'create'
        if not forms.alert(
            "Import {} row(s) — mode: '{}'?".format(len(self._csv_rows), mode),
            yes=True, no=True
        ):
            return
        self.SetLoading(True, "Importing CSV...")
        try:
            created, updated, skipped = _logic.import_sheets_from_csv(
                self.doc, self._csv_rows, tb_item.Id, mode)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Import failed: {}".format(e))
            return
        self.SetLoading(False)
        forms.alert(
            "Created: {}  |  Updated: {}  |  Skipped: {}".format(created, updated, skipped),
            title="Import CSV"
        )
        self._load_all_sheets()

    # ── renumber tab ──────────────────────────────────────────────────────────

    def Renumber_Click(self, sender, args):
        selected = list(self.GridRenum.SelectedItems)
        if not selected:
            forms.alert("Select sheets to renumber (Ctrl/Shift-click).")
            return
        prefix = self.TxtRenumPrefix.Text or ''
        suffix = self.TxtRenumSuffix.Text or ''
        try:
            start = int(self.TxtRenumStart.Text or '1')
            step  = int(self.TxtRenumStep.Text  or '1')
            pad   = int(self.TxtRenumPad.Text   or '0')
        except ValueError:
            forms.alert("Start, step and pad must be integers.")
            return
        if not forms.alert(
            "Renumber {} sheet(s) — prefix='{}' suffix='{}' start={} step={}?".format(
                len(selected), prefix, suffix, start, step),
            yes=True, no=True
        ):
            return
        ids = [r._element.Id for r in selected]
        self.SetLoading(True, "Renumbering sheets...")
        try:
            ok, failed = _logic.renumber_sheets(self.doc, ids, prefix, start, step, suffix, pad)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Renumber failed: {}".format(e))
            return
        self.SetLoading(False)
        forms.alert("Renumbered: {}  |  Failed: {}".format(ok, failed), title="Renumber Sheets")
        self._load_all_sheets()

    # ── shared ────────────────────────────────────────────────────────────────

    def Refresh_Click(self, sender, args):
        if self._pending:
            if not forms.alert(
                "You have unsaved edits. Refresh and discard them?", yes=True, no=True
            ):
                return
            self._pending.clear()
            self.BtnApply.IsEnabled = False
        self._load_all_sheets()
