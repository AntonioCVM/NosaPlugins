# -*- coding: utf-8 -*-
import os
import sys
import codecs

import System.Windows

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms

from nosa_utils.loader import load_local_module as _lm
from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value as _gid
from nosa_utils import diroots_tools_log as _trace

_logic = _lm(
    'bulkparam_logic',
    os.path.join(os.path.dirname(__file__), 'logic.py'))


class _CatPick(object):
    def __init__(self, code, title):
        self.Code = code
        self.Title = title


def _csv_cell(v):
    s = unicode(v) if not isinstance(v, unicode) else v
    if u'"' in s or u',' in s or u'\n' in s or u'\r' in s:
        return u'"' + s.replace(u'"', u'""') + u'"'
    return s


def _csv_line(fields):
    return u','.join(_csv_cell(f) for f in fields)


class ElemParamRow(object):

    def __init__(self, elem, pname, pname_aux=None):
        self._el = elem
        self.ParamName = pname
        self.AuxLabel = pname_aux or u''
        try:
            self.ElemId = unicode(_gid(elem.Id))
        except Exception:
            self.ElemId = unicode(str(elem.Id))
        try:
            self.FamType = _logic._fam_type_label(elem)
        except Exception:
            self.FamType = u''
        try:
            self.InstName = _logic._display_name(elem)
        except Exception:
            self.InstName = u''
        p = None
        try:
            p = _logic.lookup_param_named(elem, pname)
        except Exception:
            pass
        self.ParamRef = p
        self.CurrentVal = u''
        if p:
            try:
                self.CurrentVal = _logic._param_value_display(p)
            except Exception:
                self.CurrentVal = u''
        self.NewVal = self.CurrentVal
        self.CanEdit = p is not None and (not p.IsReadOnly)

        self.AuxVal = u''
        if pname_aux:
            try:
                p2 = _logic.lookup_param_named(elem, pname_aux)
                if p2:
                    self.AuxVal = _logic._param_value_display(p2)
            except Exception:
                pass


class BulkParameterEditorWindow(NOSAWindow):

    _PRESET_KEY = u'bulk_param_presets'
    _SCOPE_LABELS = (
        u'All parameters',
        u'Built-in only',
        u'Shared only',
        u'Other / family',
    )

    _CAT_ITEMS = (
        ('OST_StructuralColumns', u'Default — Structural Columns'),
        ('OST_StructuralFraming', u'Default — Structural Framing'),
        ('OST_StructuralFoundation', u'Default — Structural Foundations'),
        ('OST_StructuralBrace', u'Default — Structural Brace'),
        ('OST_StructuralConnections', u'Default — Structural Connections'),
        ('OST_Rebar', u'Default — Rebar'),
        ('OST_Floors', u'Default — Floors'),
        ('OST_Walls', u'Default — Walls'),
        ('OST_StructuralSteel', u'Default — Structural Steel'),
        ('OST_StructuralFabricAreas', u'Default — Fabric Areas'),
        ('OST_StructuralFabricReinforcement', u'Default — Fabric Reinforcement'),
        ('OST_GenericModel', u'Default — Generic Models'),
    )

    def __init__(self, doc, uidoc=None):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'bulk_parameter_editor')
        self.doc = doc
        self._uidoc = uidoc
        self._rows = ObservableCollection[ElemParamRow]()
        self._elements = []
        self._raw_param_specs = []
        self._preset_loading = False

        self.GridMain.ItemsSource = self._rows
        self.TxtStatusHint.Text = (
            u'SCAN gathers instances after category & filters.\n'
            u'Numerical LENGTH-like values use Revit display units→internal '
            u'storage on APPLY.\n'
            u'Type parameters remain in Structures › Structural Types.')

        for code, ttl in self._CAT_ITEMS:
            self.ComboCategory.Items.Add(_CatPick(code, ttl))
        try:
            self.ComboCategory.SelectedIndex = 1
        except Exception:
            pass

        self.ComboParamScope.Items.Clear()
        for s in self._SCOPE_LABELS:
            self.ComboParamScope.Items.Add(s)
        try:
            self.ComboParamScope.SelectedIndex = 0
        except Exception:
            pass

        self.ComboParamAux.Items.Clear()
        self.ComboParamAux.Items.Add(u'— none —')
        try:
            self.ComboParamAux.SelectedIndex = 0
        except Exception:
            pass

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        self._reload_presets_combo()

    # ── presets ────────────────────────────────────────────────────────

    def _reload_presets_combo(self):
        self._preset_loading = True
        try:
            cfg = self.LoadConfig()
            lst = cfg.get(self._PRESET_KEY, []) or []
            self.ComboPresetPick.Items.Clear()
            self.ComboPresetPick.Items.Add(u'— load preset —')
            for row in lst:
                try:
                    nm = row.get(u'name')
                    if nm:
                        self.ComboPresetPick.Items.Add(nm)
                except Exception:
                    pass
            self.ComboPresetPick.SelectedIndex = 0
        finally:
            self._preset_loading = False

    def PresetSave_Click(self, sender, args):
        try:
            name = unicode(self.TxtPresetSaveName.Text or u'').strip()
        except Exception:
            name = u''
        if not name:
            forms.alert(u'Enter a preset name.')
            return
        ci = self.ComboCategory.SelectedItem
        preset = self._gather_preset_payload(name, ci)
        cfg = self.LoadConfig()
        arr = cfg.get(self._PRESET_KEY, []) or []
        arr = [x for x in arr if x.get(u'name') != name]
        arr.append(preset)
        cfg[self._PRESET_KEY] = sorted(arr, key=lambda z: unicode(z.get(u'name', u'')))
        self.SaveConfig(cfg)
        forms.alert(u'Saved "{}".'.format(name), title=u'Presets')
        self._reload_presets_combo()
        try:
            for i in range(self.ComboPresetPick.Items.Count):
                try:
                    if unicode(self.ComboPresetPick.Items[i]) == name:
                        self.ComboPresetPick.SelectedIndex = i
                        break
                except Exception:
                    pass
        except Exception:
            pass

    def _gather_preset_payload(self, preset_name, category_item):
        code = getattr(category_item, 'Code', u'') if category_item else u''
        p1 = self._current_param_pick()
        paux = None
        try:
            ix = self.ComboParamAux.SelectedIndex
            if ix > 0:
                paux = unicode(self.ComboParamAux.SelectedItem)
        except Exception:
            paux = None
        return {
            u'name': preset_name,
            u'category_code': code,
            u'fam_filter': self._tb(self.TxtFamFilter),
            u'type_filter': self._tb(self.TxtTypeFilter),
            u'txt_param_filter': self._tb(getattr(self, 'TxtParamFilter', None)),
            u'scope_index': max(0, self.ComboParamScope.SelectedIndex),
            u'restrict_selection': self.ChkRestrictSelection.IsChecked == True,
            u'exclude_non_modifiable': self.ChkExcludeNonModifiable.IsChecked == True,
            u'only_open_worksets': self.ChkOpenWorksetsOnly.IsChecked == True,
            u'writable_discover_only': self.ChkWritableOnlyDiscover.IsChecked == True,
            u'writable_apply_hide': self.ChkWritableApply.IsChecked == True,
            u'dry_run_preview': self.ChkDryRunPreview.IsChecked == True,
            u'param_primary': p1 or u'',
            u'param_aux': paux or u'',
        }

    def _tb(self, ctrl):
        try:
            return unicode(ctrl.Text or u'').strip()
        except Exception:
            return u''

    def PresetLoad_Changed(self, sender, args):
        if self._preset_loading:
            return
        try:
            if self.ComboPresetPick.SelectedIndex <= 0:
                return
            name = unicode(self.ComboPresetPick.SelectedItem)
        except Exception:
            return
        cfg = self.LoadConfig()
        hit = None
        for row in cfg.get(self._PRESET_KEY, []) or []:
            if unicode(row.get(u'name', u'')) == name:
                hit = row
                break
        if not hit:
            return
        self._preset_loading = True
        try:
            code = hit.get(u'category_code')
            if code:
                for i in range(self.ComboCategory.Items.Count):
                    pick = self.ComboCategory.Items[i]
                    try:
                        if pick.Code == code:
                            self.ComboCategory.SelectedIndex = i
                            break
                    except Exception:
                        pass
            self.TxtFamFilter.Text = hit.get(u'fam_filter', u'') or u''
            self.TxtTypeFilter.Text = hit.get(u'type_filter', u'') or u''
            pf = getattr(self, 'TxtParamFilter', None)
            if pf is not None:
                pf.Text = hit.get(u'txt_param_filter', u'') or u''
            try:
                ix = int(hit.get(u'scope_index', 0))
                self.ComboParamScope.SelectedIndex = min(ix, self.ComboParamScope.Items.Count - 1)
            except Exception:
                pass
            self.ChkRestrictSelection.IsChecked = bool(hit.get(u'restrict_selection'))
            self.ChkExcludeNonModifiable.IsChecked = bool(hit.get(u'exclude_non_modifiable'))
            self.ChkOpenWorksetsOnly.IsChecked = bool(hit.get(u'only_open_worksets'))
            try:
                self.ChkWritableOnlyDiscover.IsChecked = bool(hit.get(u'writable_discover_only'))
                self.ChkWritableApply.IsChecked = bool(hit.get(u'writable_apply_hide', True))
                self.ChkDryRunPreview.IsChecked = bool(hit.get(u'dry_run_preview', True))
            except Exception:
                pass
        finally:
            self._preset_loading = False
        self.Scan_Click(None, None)
        try:
            p_main = unicode(hit.get(u'param_primary', u'')).strip()
            _sel_combo_text(self.ComboParam, p_main)
            p_ax = unicode(hit.get(u'param_aux', u'')).strip()
            _sel_combo_text(self.ComboParamAux, p_ax)
        except Exception:
            pass
        pname = self._current_param_pick()
        aux = self._current_aux_param()
        if pname and self._elements:
            self._rebuild_grid(pname, aux)

    # ── scan / combos ────────────────────────────────────────────────────

    def _set_loading(self, on, msg=u''):
        try:
            self.LoadingPanel.Visibility = (
                System.Windows.Visibility.Visible if on
                else System.Windows.Visibility.Collapsed)
            self.TxtLoadingMsg.Text = msg
        except Exception:
            pass

    def Category_Changed(self, sender, args):
        pass

    def ParamFilter_TextChanged(self, sender, args):
        if self._preset_loading:
            return
        if self._elements:
            self._refresh_param_lists()

    def ParamScope_Changed(self, sender, args):
        if self._preset_loading:
            return
        if self._elements:
            self._refresh_param_lists()

    def _scope_accepts_kind(self, kind):
        sel = unicode(self.ComboParamScope.SelectedItem or u'').strip().lower()
        if u'built-in' in sel:
            return kind == u'built_in'
        if u'shared' in sel:
            return kind == u'shared'
        if u'other' in sel or u'family' in sel:
            return kind == u'other'
        return True

    def _names_pass_filter(self):
        filt = self._tb(getattr(self, 'TxtParamFilter', None)).lower()
        combo = []
        seen = set()
        for row in self._raw_param_specs or []:
            name = row[u'name']
            kind = row.get(u'kind', u'other')
            if not self._scope_accepts_kind(kind):
                continue
            if filt and filt not in name.lower():
                continue
            seen.add(name)
            combo.append(name)
        combo.sort(key=lambda z: z.lower())
        return combo

    def _refresh_param_lists(self):
        names = self._names_pass_filter()
        keep_main = self._current_param_pick()
        keep_aux = self._current_aux_param()

        self.ComboParam.Items.Clear()
        for name in names:
            self.ComboParam.Items.Add(name)
        _sel_combo_text(self.ComboParam, keep_main)
        try:
            if self.ComboParam.Items.Count > 0 and self.ComboParam.SelectedIndex < 0:
                self.ComboParam.SelectedIndex = 0
        except Exception:
            pass

        self.ComboParamAux.Items.Clear()
        self.ComboParamAux.Items.Add(u'— none —')
        for name in names:
            self.ComboParamAux.Items.Add(name)
        if keep_aux:
            _sel_combo_text(self.ComboParamAux, keep_aux)
        else:
            try:
                self.ComboParamAux.SelectedIndex = 0
            except Exception:
                pass

    def Scan_Click(self, sender, args):
        if self._preset_loading:
            return
        ci = self.ComboCategory.SelectedItem
        if ci is None:
            forms.alert(u'Choose category first.')
            return
        elems, hint = _logic.gather_instances(
            self.doc, ci.Code,
            self.TxtFamFilter.Text, self.TxtTypeFilter.Text,
            uidoc=self._uidoc,
            restrict_selection=self.ChkRestrictSelection.IsChecked == True,
            exclude_non_modifiable=self.ChkExcludeNonModifiable.IsChecked == True,
            only_open_worksets=self.ChkOpenWorksetsOnly.IsChecked == True)
        self._elements = elems
        if not elems:
            forms.alert(u'No elements matched — adjust filters.')
            self.TxtRowCount.Text = u'0 instances'
            self._rows.Clear()
            self.ComboParam.Items.Clear()
            try:
                self.ComboParamAux.Items.Clear()
                self.ComboParamAux.Items.Add(u'— none —')
            except Exception:
                pass
            return
        self.TxtRowCount.Text = u'{} {}'.format(len(elems), hint or u'instances').strip()

        writable = self.ChkWritableOnlyDiscover.IsChecked == True
        self._raw_param_specs = _logic.discover_param_specs(
            elems, writable_only=writable)
        self._refresh_param_lists()

        pname = self._current_param_pick()
        aux = self._current_aux_param()
        if pname:
            self._rebuild_grid(pname, aux)
        else:
            self._rows.Clear()

    def _current_param_pick(self):
        try:
            it = self.ComboParam.SelectedItem
            if it is not None:
                return unicode(it).strip()
        except Exception:
            pass
        try:
            return unicode(self.ComboParam.Text or u'').strip()
        except Exception:
            return unicode(str(self.ComboParam.Text or '')).strip()

    def _current_aux_param(self):
        try:
            if getattr(self.ComboParamAux, 'SelectedIndex', None) == 0:
                return None
        except Exception:
            pass
        try:
            it = self.ComboParamAux.SelectedItem
            if it is None:
                return None
            s = unicode(it).strip()
            if not s or s == u'— none —':
                return None
            return s
        except Exception:
            return None

    def Param_SelectionChanged(self, sender, args):
        if not self._elements or self._preset_loading:
            return
        pname = self._current_param_pick()
        if pname:
            self._rebuild_grid(pname, self._current_aux_param())

    def AuxParam_SelectionChanged(self, sender, args):
        if not self._elements or self._preset_loading:
            return
        pname = self._current_param_pick()
        if pname:
            self._rebuild_grid(pname, self._current_aux_param())

    def _rebuild_grid(self, pname, pname_aux=None):
        skip_ro = self.ChkWritableApply.IsChecked == True
        self._set_loading(True, u'Building grid…')
        try:
            self._rows.Clear()
            for el in self._elements:
                row = ElemParamRow(el, pname, pname_aux)
                if skip_ro and row.ParamRef and row.ParamRef.IsReadOnly:
                    continue
                self._rows.Add(row)
            try:
                self.GridMain.Items.Refresh()
            except Exception:
                pass
        finally:
            self._set_loading(False)

    def Grid_Main_BeginningEdit(self, sender, args):
        try:
            row = args.Row.Item
            if isinstance(row, ElemParamRow) and not row.CanEdit:
                args.Cancel = True
        except Exception:
            pass

    def FillAll_Click(self, sender, args):
        val = getattr(self.TxtApplyAll, 'Text', '') or ''
        try:
            val = unicode(val)
        except Exception:
            val = unicode(str(val))
        for row in self._rows:
            if isinstance(row, ElemParamRow) and row.CanEdit:
                row.NewVal = val
        try:
            self.GridMain.Items.Refresh()
        except Exception:
            pass

    def Apply_Click(self, sender, args):
        pname = self._current_param_pick()
        if not pname:
            forms.alert(u'Pick or enter a primary parameter.')
            return
        if self._rows.Count <= 0:
            forms.alert(u'Run SCAN first.')
            return
        tuples = []
        for row in self._rows:
            if not isinstance(row, ElemParamRow):
                continue
            try:
                p = _logic.lookup_param_named(row._el, pname)
            except Exception:
                p = row.ParamRef
            if not p:
                continue
            if self.ChkWritableApply.IsChecked == True and p.IsReadOnly:
                continue
            try:
                if _logic.param_edit_is_unchanged(p, row.NewVal):
                    continue
            except Exception:
                try:
                    if unicode(row.NewVal).strip() == unicode(row.CurrentVal).strip():
                        continue
                except Exception:
                    pass
            tuples.append((p, row.NewVal))
        if not tuples:
            forms.alert(u'Nothing to apply.')
            return
        if self.ChkDryRunPreview.IsChecked == True:
            lines = _logic.preview_apply_strings(tuples)
            hdr = u'Dry-run — {} writable cell change(s).\n{}'.format(len(tuples), u'-' * 32)
            body = hdr + u'\n' + u'\n'.join(lines[:18])
            if len(lines) > 18:
                body += u'\n… truncated — see CSV export for full grids.'
            if not forms.alert(body + u'\n\nApply these writes?', yes=True, no=True):
                return
        else:
            if not forms.alert(u'Apply {} parameter write(s)?'.format(len(tuples)), yes=True, no=True):
                return
        self._set_loading(True, u'Applying…')
        try:
            ok, fail, sk = _logic.apply_batch(self.doc, tuples)
        except Exception as e:
            _trace.log_event(u'bulk_param', u'apply_exception', unicode(e))
            forms.alert(u'Apply failed:\n{}'.format(e))
            return
        finally:
            self._set_loading(False)
        try:
            if fail or sk:
                _trace.log_event(
                    u'bulk_param',
                    u'apply_result',
                    u'ok={} fail={} skip={}'.format(ok, fail, sk))
        except Exception:
            pass
        forms.alert(
            u'OK {}\nFail {}\nSkip {}'.format(ok, fail, sk),
            title=u'Bulk Parameter Editor')
        if pname:
            self._rebuild_grid(pname, self._current_aux_param())

    def Export_Click(self, sender, args):
        if self._rows.Count <= 0:
            forms.alert(u'Nothing to export — scan.')
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        pname = self._current_param_pick() or u'Parameter'
        paux_name = self._current_aux_param() or u''
        head = [u'Family : Type', u'Name', u'ElemId']
        if paux_name:
            head.append(u'Aux ' + paux_name)
        head.extend([pname + u' current', pname + u' new'])
        lines = [_csv_line(head)]
        for row in self._rows:
            if not isinstance(row, ElemParamRow):
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
            forms.alert(u'CSV failed: {}'.format(ex))
            return
        forms.alert(path, title=u'Exported')


def _sel_combo_text(cmb, txt):
    if not txt:
        return
    t = unicode(txt).strip()
    if not t:
        return
    try:
        for i in range(cmb.Items.Count):
            if unicode(cmb.Items[i]).strip().lower() == t.lower():
                cmb.SelectedIndex = i
                return
        cmb.Text = t
    except Exception:
        try:
            cmb.Text = t
        except Exception:
            pass
