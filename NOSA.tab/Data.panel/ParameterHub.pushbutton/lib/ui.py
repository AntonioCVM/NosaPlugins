# -*- coding: utf-8 -*-
import imp, io, os, sys, csv, codecs
import System.Windows
from System.Collections.ObjectModel import ObservableCollection

from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value as _gid
from nosa_utils.compat import ensure_text
from nosa_utils.telemetry import log_error

try:
    from nosa_utils import diroots_tools_log as _trace
except ImportError:
    class _trace(object):
        @staticmethod
        def log_event(*a, **kw):
            pass

_here      = os.path.dirname(os.path.abspath(__file__))
_pi_logic  = imp.load_source('ph_pi_logic',  os.path.join(_here, 'logic_param_inspector.py'))
_be_logic  = imp.load_source('ph_be_logic',  os.path.join(_here, 'logic_bulk_param_editor.py'))

_PI_SEARCH_PH = u'Search parameters...'


# ── ParameterInspector row ────────────────────────────────────────────────────

class _PIRow(object):
    def __init__(self, row_data, element_count):
        self.Name    = row_data['name']
        self.Group   = row_data['group']
        self.Storage = row_data['storage']
        self.RW      = u'R' if row_data['readonly'] else u'RW'
        self.HasDiff = not row_data['consistent'] and element_count > 1
        self._params = row_data['params']
        self._readonly = row_data['readonly']
        values = row_data['values']
        if element_count <= 1:
            self.ValueStr = values[0] if values else u''
        else:
            unique = list(dict.fromkeys(v for v in values if v is not None))
            if len(unique) == 1:
                self.ValueStr = unique[0]
            else:
                self.ValueStr = u' | '.join(str(v) for v in unique[:4])
                if len(unique) > 4:
                    self.ValueStr += u' ...'


# ── BulkParameterEditor helpers ───────────────────────────────────────────────

class _CatPick(object):
    def __init__(self, code, title):
        self.Code  = code
        self.Title = title


class _BERow(object):
    def __init__(self, elem, pname, pname_aux=None):
        self._el = elem
        self.ParamName = pname
        self.AuxLabel  = pname_aux or u''
        try:
            self.ElemId = ensure_text(_gid(elem.Id))
        except Exception:
            self.ElemId = ensure_text(str(elem.Id))
        try:
            self.FamType = _be_logic._fam_type_label(elem)
        except Exception:
            self.FamType = u''
        try:
            self.InstName = _be_logic._display_name(elem)
        except Exception:
            self.InstName = u''
        p = None
        try:
            p = _be_logic.lookup_param_named(elem, pname)
        except Exception:
            pass
        self.ParamRef   = p
        self.CurrentVal = u''
        if p:
            try:
                self.CurrentVal = _be_logic._param_value_display(p)
            except Exception:
                pass
        self.NewVal  = self.CurrentVal
        self.CanEdit = p is not None and (not p.IsReadOnly)
        self.AuxVal  = u''
        if pname_aux:
            try:
                p2 = _be_logic.lookup_param_named(elem, pname_aux)
                if p2:
                    self.AuxVal = _be_logic._param_value_display(p2)
            except Exception:
                pass


def _sel_combo_text(cmb, txt):
    if not txt:
        return
    t = ensure_text(txt).strip()
    if not t:
        return
    try:
        for i in range(cmb.Items.Count):
            if ensure_text(cmb.Items[i]).strip().lower() == t.lower():
                cmb.SelectedIndex = i
                return
        cmb.Text = t
    except Exception:
        try:
            cmb.Text = t
        except Exception:
            pass


def _csv_cell(v):
    s = ensure_text(v)
    if u'"' in s or u',' in s or u'\n' in s or u'\r' in s:
        return u'"' + s.replace(u'"', u'""') + u'"'
    return s


def _csv_line(fields):
    return u','.join(_csv_cell(f) for f in fields)


# ── Merged window ─────────────────────────────────────────────────────────────

_BE_CAT_ITEMS = (
    ('OST_StructuralColumns',            u'Structural Columns'),
    ('OST_StructuralFraming',            u'Structural Framing'),
    ('OST_StructuralFoundation',         u'Structural Foundations'),
    ('OST_StructuralBrace',              u'Structural Brace'),
    ('OST_StructuralConnections',        u'Structural Connections'),
    ('OST_Rebar',                        u'Rebar'),
    ('OST_Floors',                       u'Floors'),
    ('OST_Walls',                        u'Walls'),
    ('OST_StructuralSteel',              u'Structural Steel'),
    ('OST_StructuralFabricAreas',        u'Fabric Areas'),
    ('OST_StructuralFabricReinforcement',u'Fabric Reinforcement'),
    ('OST_GenericModel',                 u'Generic Models'),
)

_BE_SCOPE_LABELS = (
    u'All parameters',
    u'Built-in only',
    u'Shared only',
    u'Other / family',
)

_BE_PRESET_KEY = u'bulk_param_presets'


class ParameterHubWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'parameter_hub')
        self.doc = doc

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._pi_init(cfg)
        self._be_init(cfg)

    # ══════════════════════════════════════════════════════════════════
    # TAB 1: PARAMETER INSPECTOR
    # ══════════════════════════════════════════════════════════════════

    def _pi_init(self, cfg):
        self._pi_elements    = []
        self._pi_all_rows    = []
        self._pi_rows        = ObservableCollection[_PIRow]()
        self._pi_search_on   = False
        self.PI_GridParams.ItemsSource = self._pi_rows
        self.PI_ChkDarkMode_state = cfg.get('dark_mode', False)

    def PI_Load_Click(self, sender, args):
        sel = revit.get_selection()
        elements = list(sel.elements) if hasattr(sel, 'elements') else list(sel)
        if not elements:
            forms.alert(u'No elements selected. Select elements in Revit first.')
            return
        self._pi_elements = elements
        self.PI_TxtElementCount.Text = u'{} element(s)'.format(len(elements))
        self.SetLoading(True, u'Reading parameters...')
        try:
            self._pi_all_rows = _pi_logic.collect_params(self.doc, elements)
        except Exception as e:
            import traceback
            log_error(u'ParameterHub/Inspect', str(e), traceback.format_exc())
            self.SetLoading(False)
            forms.alert(u'Error collecting parameters: {}'.format(e))
            return
        self._pi_apply_filters()
        self.SetLoading(False)
        self.PI_BtnExport.IsEnabled   = True
        self.PI_BtnCopyFrom.IsEnabled = len(elements) > 1

    def PI_Filter_Changed(self, sender, args):
        self._pi_apply_filters()

    def _pi_apply_filters(self):
        show_builtin  = self.PI_ChkShowBuiltin.IsChecked  == True
        show_shared   = self.PI_ChkShowShared.IsChecked   == True
        show_project  = self.PI_ChkShowProject.IsChecked  == True
        only_diffs    = self.PI_ChkOnlyDiffs.IsChecked    == True
        only_writable = self.PI_ChkOnlyWritable.IsChecked == True
        search_text   = (self.PI_TxtSearch.Text or u'').strip().lower()
        if search_text == _PI_SEARCH_PH.lower():
            search_text = u''

        visible = []
        for rd in self._pi_all_rows:
            if rd['builtin'] and not show_builtin:   continue
            if rd['shared'] and not show_shared:     continue
            if not rd['builtin'] and not rd['shared'] and not show_project: continue
            if only_diffs and rd['consistent']:       continue
            if only_writable and rd['readonly']:      continue
            if search_text and search_text not in rd['name'].lower(): continue
            visible.append(rd)

        n = len(self._pi_elements)
        self._pi_rows.Clear()
        diffs = 0
        for rd in visible:
            row = _PIRow(rd, n)
            if row.HasDiff:
                diffs += 1
            self._pi_rows.Add(row)
        self.PI_TxtTotalParams.Text = u'{} params'.format(len(visible))
        self.PI_TxtDiffParams.Text  = u'{} diffs'.format(diffs)

    def PI_Search_GotFocus(self, sender, args):
        if self.PI_TxtSearch.Text == _PI_SEARCH_PH:
            self.PI_TxtSearch.Text       = u''
            self.PI_TxtSearch.Foreground = System.Windows.Media.Brushes.Black
            self._pi_search_on           = True

    def PI_Search_LostFocus(self, sender, args):
        if not self.PI_TxtSearch.Text.strip():
            self.PI_TxtSearch.Text       = _PI_SEARCH_PH
            self.PI_TxtSearch.Foreground = System.Windows.Media.Brushes.Gray
            self._pi_search_on           = False

    def PI_Search_Changed(self, sender, args):
        if self._pi_search_on or self.PI_TxtSearch.Text != _PI_SEARCH_PH:
            self._pi_apply_filters()

    def PI_Grid_SelectionChanged(self, sender, args):
        row = self.PI_GridParams.SelectedItem
        self.PI_BtnApply.IsEnabled = (
            row is not None and not row._readonly and bool(self._pi_elements))

    def PI_Apply_Click(self, sender, args):
        row = self.PI_GridParams.SelectedItem
        if row is None or row._readonly:
            return
        new_val = self.PI_TxtNewValue.Text
        params  = [p for p in row._params if p is not None]
        if not params:
            forms.alert(u'No editable parameters found for this row.')
            return
        ok, fail = _pi_logic.set_param_value(self.doc, params, new_val)
        forms.alert(u'Set: {}  |  Failed: {}'.format(ok, fail), title=u'Bulk Edit')
        self.PI_Load_Click(None, None)

    def PI_CopyFrom_Click(self, sender, args):
        if len(self._pi_elements) < 2:
            return
        source  = self._pi_elements[0]
        targets = self._pi_elements[1:]
        name    = getattr(source, 'Name', str(source.Id))
        if not forms.alert(
            u'Copy all writable parameters from:\n{}\n\nTo {} elements?'.format(
                name, len(targets)),
            yes=True, no=True
        ):
            return
        copied, skipped = _pi_logic.copy_params_from_source(self.doc, source, targets)
        forms.alert(u'Copied: {}  |  Skipped: {}'.format(copied, skipped))
        self.PI_Load_Click(None, None)

    def PI_Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                header = ['Group', 'Parameter', 'Type', 'R/W', 'Consistent?']
                for i in range(len(self._pi_elements)):
                    header.append('Element {}'.format(i + 1))
                w.writerow(header)
                for rd in self._pi_all_rows:
                    w.writerow([
                        rd['group'], rd['name'], rd['storage'],
                        'R' if rd['readonly'] else 'RW',
                        'Yes' if rd['consistent'] else 'No',
                    ] + rd['values'])
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # TAB 2: BULK PARAMETER EDITOR
    # ══════════════════════════════════════════════════════════════════

    def _be_init(self, cfg):
        self._be_rows          = ObservableCollection[_BERow]()
        self._be_elements      = []
        self._be_raw_specs     = []
        self._be_preset_loading = False

        self.BE_GridMain.ItemsSource = self._be_rows
        self.BE_TxtStatusHint.Text = (
            u'SCAN gathers instances after category & filters.\n'
            u'Numerical values use Revit display units on APPLY.')

        for code, ttl in _BE_CAT_ITEMS:
            self.BE_ComboCategory.Items.Add(_CatPick(code, ttl))
        try:
            self.BE_ComboCategory.SelectedIndex = 1
        except Exception:
            pass

        self.BE_ComboParamScope.Items.Clear()
        for s in _BE_SCOPE_LABELS:
            self.BE_ComboParamScope.Items.Add(s)
        try:
            self.BE_ComboParamScope.SelectedIndex = 0
        except Exception:
            pass

        self.BE_ComboParamAux.Items.Clear()
        self.BE_ComboParamAux.Items.Add(u'— none —')
        try:
            self.BE_ComboParamAux.SelectedIndex = 0
        except Exception:
            pass

        self._be_reload_presets()

    def _be_set_loading(self, on, msg=u''):
        try:
            self.BE_LoadingPanel.Visibility = (
                System.Windows.Visibility.Visible if on
                else System.Windows.Visibility.Collapsed)
            self.BE_TxtLoadingMsg.Text = msg
        except Exception:
            pass

    def _be_tb(self, ctrl):
        try:
            return ensure_text(ctrl.Text or u'').strip()
        except Exception:
            return u''

    def _be_reload_presets(self):
        self._be_preset_loading = True
        try:
            cfg = self.LoadConfig()
            lst = cfg.get(_BE_PRESET_KEY, []) or []
            self.BE_ComboPresetPick.Items.Clear()
            self.BE_ComboPresetPick.Items.Add(u'— load preset —')
            for row in lst:
                nm = row.get(u'name')
                if nm:
                    self.BE_ComboPresetPick.Items.Add(nm)
            self.BE_ComboPresetPick.SelectedIndex = 0
        finally:
            self._be_preset_loading = False

    def BE_PresetSave_Click(self, sender, args):
        try:
            name = ensure_text(self.BE_TxtPresetSaveName.Text or u'').strip()
        except Exception:
            name = u''
        if not name:
            forms.alert(u'Enter a preset name.')
            return
        ci     = self.BE_ComboCategory.SelectedItem
        preset = self._be_gather_preset(name, ci)
        cfg    = self.LoadConfig()
        arr    = cfg.get(_BE_PRESET_KEY, []) or []
        arr    = [x for x in arr if x.get(u'name') != name]
        arr.append(preset)
        cfg[_BE_PRESET_KEY] = sorted(arr, key=lambda z: ensure_text(z.get(u'name', u'')))
        self.SaveConfig(cfg)
        forms.alert(u'Saved "{}".'.format(name), title=u'Presets')
        self._be_reload_presets()

    def _be_gather_preset(self, preset_name, category_item):
        code  = getattr(category_item, 'Code', u'') if category_item else u''
        p1    = self._be_current_param()
        p_aux = None
        try:
            if self.BE_ComboParamAux.SelectedIndex > 0:
                p_aux = ensure_text(self.BE_ComboParamAux.SelectedItem)
        except Exception:
            pass
        return {
            u'name':                  preset_name,
            u'category_code':         code,
            u'fam_filter':            self._be_tb(self.BE_TxtFamFilter),
            u'type_filter':           self._be_tb(self.BE_TxtTypeFilter),
            u'txt_param_filter':      self._be_tb(self.BE_TxtParamFilter),
            u'scope_index':           max(0, self.BE_ComboParamScope.SelectedIndex),
            u'restrict_selection':    self.BE_ChkRestrictSelection.IsChecked == True,
            u'exclude_non_modifiable':self.BE_ChkExcludeNonModifiable.IsChecked == True,
            u'only_open_worksets':    self.BE_ChkOpenWorksetsOnly.IsChecked == True,
            u'writable_discover_only':self.BE_ChkWritableOnlyDiscover.IsChecked == True,
            u'writable_apply_hide':   self.BE_ChkWritableApply.IsChecked == True,
            u'dry_run_preview':       self.BE_ChkDryRunPreview.IsChecked == True,
            u'param_primary':         p1 or u'',
            u'param_aux':             p_aux or u'',
        }

    def BE_PresetLoad_Changed(self, sender, args):
        if self._be_preset_loading:
            return
        try:
            if self.BE_ComboPresetPick.SelectedIndex <= 0:
                return
            name = ensure_text(self.BE_ComboPresetPick.SelectedItem)
        except Exception:
            return
        cfg = self.LoadConfig()
        hit = None
        for row in cfg.get(_BE_PRESET_KEY, []) or []:
            if ensure_text(row.get(u'name', u'')) == name:
                hit = row; break
        if not hit:
            return
        self._be_preset_loading = True
        try:
            code = hit.get(u'category_code')
            if code:
                for i in range(self.BE_ComboCategory.Items.Count):
                    try:
                        if self.BE_ComboCategory.Items[i].Code == code:
                            self.BE_ComboCategory.SelectedIndex = i; break
                    except Exception:
                        pass
            self.BE_TxtFamFilter.Text  = hit.get(u'fam_filter',  u'') or u''
            self.BE_TxtTypeFilter.Text = hit.get(u'type_filter', u'') or u''
            self.BE_TxtParamFilter.Text = hit.get(u'txt_param_filter', u'') or u''
            try:
                ix = int(hit.get(u'scope_index', 0))
                self.BE_ComboParamScope.SelectedIndex = min(
                    ix, self.BE_ComboParamScope.Items.Count - 1)
            except Exception:
                pass
            self.BE_ChkRestrictSelection.IsChecked     = bool(hit.get(u'restrict_selection'))
            self.BE_ChkExcludeNonModifiable.IsChecked  = bool(hit.get(u'exclude_non_modifiable'))
            self.BE_ChkOpenWorksetsOnly.IsChecked       = bool(hit.get(u'only_open_worksets'))
            self.BE_ChkWritableOnlyDiscover.IsChecked   = bool(hit.get(u'writable_discover_only'))
            self.BE_ChkWritableApply.IsChecked          = bool(hit.get(u'writable_apply_hide', True))
            self.BE_ChkDryRunPreview.IsChecked          = bool(hit.get(u'dry_run_preview', True))
        finally:
            self._be_preset_loading = False
        self.BE_Scan_Click(None, None)
        try:
            _sel_combo_text(self.BE_ComboParam,    ensure_text(hit.get(u'param_primary', u'')).strip())
            _sel_combo_text(self.BE_ComboParamAux, ensure_text(hit.get(u'param_aux',     u'')).strip())
        except Exception:
            pass
        pname = self._be_current_param()
        aux   = self._be_current_aux()
        if pname and self._be_elements:
            self._be_rebuild_grid(pname, aux)

    def BE_Category_Changed(self, sender, args):
        pass

    def BE_ParamFilter_TextChanged(self, sender, args):
        if self._be_preset_loading:
            return
        if self._be_elements:
            self._be_refresh_param_lists()

    def BE_ParamScope_Changed(self, sender, args):
        if self._be_preset_loading:
            return
        if self._be_elements:
            self._be_refresh_param_lists()

    def _be_scope_accepts_kind(self, kind):
        sel = ensure_text(self.BE_ComboParamScope.SelectedItem or u'').strip().lower()
        if u'built-in' in sel: return kind == u'built_in'
        if u'shared'   in sel: return kind == u'shared'
        if u'other'    in sel or u'family' in sel: return kind == u'other'
        return True

    def _be_names_pass_filter(self):
        filt  = self._be_tb(self.BE_TxtParamFilter).lower()
        combo = []
        for row in self._be_raw_specs or []:
            name = row[u'name']
            kind = row.get(u'kind', u'other')
            if not self._be_scope_accepts_kind(kind): continue
            if filt and filt not in name.lower(): continue
            combo.append(name)
        combo.sort(key=lambda z: z.lower())
        return combo

    def _be_refresh_param_lists(self):
        names      = self._be_names_pass_filter()
        keep_main  = self._be_current_param()
        keep_aux   = self._be_current_aux()
        self.BE_ComboParam.Items.Clear()
        for n in names:
            self.BE_ComboParam.Items.Add(n)
        _sel_combo_text(self.BE_ComboParam, keep_main)
        if self.BE_ComboParam.Items.Count > 0 and self.BE_ComboParam.SelectedIndex < 0:
            try:
                self.BE_ComboParam.SelectedIndex = 0
            except Exception:
                pass
        self.BE_ComboParamAux.Items.Clear()
        self.BE_ComboParamAux.Items.Add(u'— none —')
        for n in names:
            self.BE_ComboParamAux.Items.Add(n)
        if keep_aux:
            _sel_combo_text(self.BE_ComboParamAux, keep_aux)
        else:
            try:
                self.BE_ComboParamAux.SelectedIndex = 0
            except Exception:
                pass

    def BE_Scan_Click(self, sender, args):
        if self._be_preset_loading:
            return
        ci = self.BE_ComboCategory.SelectedItem
        if ci is None:
            forms.alert(u'Choose category first.')
            return
        elems, hint = _be_logic.gather_instances(
            self.doc, ci.Code,
            self.BE_TxtFamFilter.Text, self.BE_TxtTypeFilter.Text,
            uidoc=revit.uidoc,
            restrict_selection=self.BE_ChkRestrictSelection.IsChecked == True,
            exclude_non_modifiable=self.BE_ChkExcludeNonModifiable.IsChecked == True,
            only_open_worksets=self.BE_ChkOpenWorksetsOnly.IsChecked == True)
        self._be_elements = elems
        if not elems:
            forms.alert(u'No elements matched — adjust filters.')
            self.BE_TxtRowCount.Text = u'0 instances'
            self._be_rows.Clear()
            self.BE_ComboParam.Items.Clear()
            self.BE_ComboParamAux.Items.Clear()
            self.BE_ComboParamAux.Items.Add(u'— none —')
            return
        self.BE_TxtRowCount.Text = u'{} {}'.format(len(elems), hint or u'instances').strip()
        writable = self.BE_ChkWritableOnlyDiscover.IsChecked == True
        self._be_raw_specs = _be_logic.discover_param_specs(elems, writable_only=writable)
        self._be_refresh_param_lists()
        pname = self._be_current_param()
        aux   = self._be_current_aux()
        if pname:
            self._be_rebuild_grid(pname, aux)
        else:
            self._be_rows.Clear()

    def _be_current_param(self):
        try:
            it = self.BE_ComboParam.SelectedItem
            if it is not None:
                return ensure_text(it).strip()
        except Exception:
            pass
        try:
            return ensure_text(self.BE_ComboParam.Text or u'').strip()
        except Exception:
            return u''

    def _be_current_aux(self):
        try:
            if self.BE_ComboParamAux.SelectedIndex == 0:
                return None
        except Exception:
            pass
        try:
            it = self.BE_ComboParamAux.SelectedItem
            if it is None:
                return None
            s = ensure_text(it).strip()
            return None if not s or s == u'— none —' else s
        except Exception:
            return None

    def BE_Param_SelectionChanged(self, sender, args):
        if not self._be_elements or self._be_preset_loading:
            return
        pname = self._be_current_param()
        if pname:
            self._be_rebuild_grid(pname, self._be_current_aux())

    def BE_AuxParam_SelectionChanged(self, sender, args):
        if not self._be_elements or self._be_preset_loading:
            return
        pname = self._be_current_param()
        if pname:
            self._be_rebuild_grid(pname, self._be_current_aux())

    def _be_rebuild_grid(self, pname, pname_aux=None):
        skip_ro = self.BE_ChkWritableApply.IsChecked == True
        self._be_set_loading(True, u'Building grid…')
        try:
            self._be_rows.Clear()
            for el in self._be_elements:
                row = _BERow(el, pname, pname_aux)
                if skip_ro and row.ParamRef and row.ParamRef.IsReadOnly:
                    continue
                self._be_rows.Add(row)
            try:
                self.BE_GridMain.Items.Refresh()
            except Exception:
                pass
        finally:
            self._be_set_loading(False)

    def BE_Grid_Main_BeginningEdit(self, sender, args):
        try:
            row = args.Row.Item
            if isinstance(row, _BERow) and not row.CanEdit:
                args.Cancel = True
        except Exception:
            pass

    def BE_FillAll_Click(self, sender, args):
        val = self._be_tb(self.BE_TxtApplyAll)
        for row in self._be_rows:
            if isinstance(row, _BERow) and row.CanEdit:
                row.NewVal = val
        try:
            self.BE_GridMain.Items.Refresh()
        except Exception:
            pass

    def BE_Apply_Click(self, sender, args):
        pname = self._be_current_param()
        if not pname:
            forms.alert(u'Pick or enter a primary parameter.')
            return
        if self._be_rows.Count <= 0:
            forms.alert(u'Run SCAN first.')
            return
        tuples = []
        for row in self._be_rows:
            if not isinstance(row, _BERow):
                continue
            try:
                p = _be_logic.lookup_param_named(row._el, pname)
            except Exception:
                p = row.ParamRef
            if not p:
                continue
            if self.BE_ChkWritableApply.IsChecked == True and p.IsReadOnly:
                continue
            try:
                if _be_logic.param_edit_is_unchanged(p, row.NewVal):
                    continue
            except Exception:
                try:
                    if ensure_text(row.NewVal).strip() == ensure_text(row.CurrentVal).strip():
                        continue
                except Exception:
                    pass
            tuples.append((p, row.NewVal))
        if not tuples:
            forms.alert(u'Nothing to apply.')
            return
        if self.BE_ChkDryRunPreview.IsChecked == True:
            lines = _be_logic.preview_apply_strings(tuples)
            hdr  = u'Dry-run — {} write(s).\n{}'.format(len(tuples), u'-' * 32)
            body = hdr + u'\n' + u'\n'.join(lines[:18])
            if len(lines) > 18:
                body += u'\n… truncated.'
            if not forms.alert(body + u'\n\nApply these writes?', yes=True, no=True):
                return
        else:
            if not forms.alert(u'Apply {} parameter write(s)?'.format(len(tuples)),
                               yes=True, no=True):
                return
        self._be_set_loading(True, u'Applying…')
        try:
            ok, fail, sk = _be_logic.apply_batch(self.doc, tuples)
        except Exception as e:
            import traceback
            log_error(u'ParameterHub/BulkEdit', str(e), traceback.format_exc())
            _trace.log_event(u'bulk_param', u'apply_exception', ensure_text(e))
            forms.alert(u'Apply failed:\n{}'.format(e))
            return
        finally:
            self._be_set_loading(False)
        try:
            if fail or sk:
                _trace.log_event(u'bulk_param', u'apply_result',
                                 u'ok={} fail={} skip={}'.format(ok, fail, sk))
        except Exception:
            pass
        forms.alert(u'OK {}\nFail {}\nSkip {}'.format(ok, fail, sk),
                    title=u'Parameter Hub — Bulk Editor')
        if pname:
            self._be_rebuild_grid(pname, self._be_current_aux())

    def BE_Export_Click(self, sender, args):
        if self._be_rows.Count <= 0:
            forms.alert(u'Nothing to export — scan first.')
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        pname      = self._be_current_param() or u'Parameter'
        paux_name  = self._be_current_aux() or u''
        head = [u'Family : Type', u'Name', u'ElemId']
        if paux_name:
            head.append(u'Aux ' + paux_name)
        head.extend([pname + u' current', pname + u' new'])
        lines = [_csv_line(head)]
        for row in self._be_rows:
            if not isinstance(row, _BERow):
                continue
            row_vals = [row.FamType, row.InstName, row.ElemId]
            if paux_name:
                row_vals.append(row.AuxVal)
            row_vals.extend([row.CurrentVal, row.NewVal])
            lines.append(_csv_line(row_vals))
        try:
            with codecs.open(path, 'w', encoding='utf-8-sig') as f:
                f.write(u'\r\n'.join(lines))
        except Exception as ex:
            import traceback
            log_error(u'ParameterHub/Export', str(ex), traceback.format_exc())
            forms.alert(u'CSV failed: {}'.format(ex))
            return
        forms.alert(path, title=u'Exported')

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
