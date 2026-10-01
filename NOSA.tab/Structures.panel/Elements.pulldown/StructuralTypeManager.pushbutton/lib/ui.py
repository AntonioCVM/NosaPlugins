# -*- coding: utf-8 -*-
import os
import sys
import codecs

import System.Windows

_lib = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms

try:
    unicode
except NameError:
    unicode = str  # CPython 3 compat

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value as _gid
from nosa_utils import diroots_tools_log as _trace

from nosa_utils.bootstrap import load_module
_logic = load_module(
    'struct_type_mgr_logic',
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


class TypeParamRow(object):

    def __init__(self, el_type, pname, pname_aux=None):
        self._et = el_type
        self.ParamName = pname
        try:
            self.TypeId = unicode(_gid(el_type.Id))
        except Exception:
            self.TypeId = unicode(str(el_type.Id))
        try:
            self.FamType = _logic.type_family_type_label(el_type)
        except Exception:
            self.FamType = u''
        p = None
        try:
            p = _logic.lookup_param_named(el_type, pname)
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
                p2 = _logic.lookup_param_named(el_type, pname_aux)
                if p2:
                    self.AuxVal = _logic._param_value_display(p2)
            except Exception:
                pass


class StructuralTypeManagerWindow(NOSAWindow):

    _PRESET_KEY = u'struct_param_presets'
    _SCOPE_LABELS = (
        u'All parameters',
        u'Built-in only',
        u'Shared only',
        u'Other / family',
    )

    _CAT_ITEMS = (
        ('OST_StructuralColumns', u'Structural columns'),
        ('OST_StructuralFraming', u'Structural framing'),
        ('OST_StructuralFoundation', u'Structural foundations'),
        ('OST_StructuralBrace', u'Structural brace'),
        ('OST_StructuralConnections', u'Structural connections'),
        ('OST_Rebar', u'Rebar (bar types)'),
        ('OST_Floors', u'Floor types'),
        ('OST_StructuralWalls', u'Structural wall types'),
        ('OST_Walls', u'Wall types (all)'),
        ('OST_GenericModel', u'Generic model types'),
    )

    def __init__(self, doc, uidoc=None):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'structural_type_manager')
        self.doc = doc
        self._uidoc = uidoc
        self._rows = ObservableCollection[TypeParamRow]()
        self._types = []
        self._raw_param_specs = []
        self._preset_loading = False

        self.GridMain.ItemsSource = self._rows
        self.TxtStatusHint.Text = (
            u'Type-family bulk edit mirrors Data › Bulk Parameter (instances).\n'
            u'Double values honour display units→internal conversions.')

        for c, t in self._CAT_ITEMS:
            self.ComboCategory.Items.Add(_CatPick(c, t))
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
        self.ChkDarkMode.IsChecked = cfg.get(u'dark_mode', self.dark_mode)
        self._reload_presets_combo()

    def _set_loading(self, on, msg=u''):
        try:
            self.LoadingPanel.Visibility = (
                System.Windows.Visibility.Visible if on
                else System.Windows.Visibility.Collapsed)
            self.TxtLoadingMsg.Text = msg
        except Exception:
            pass

    def _tb(self, ctrl):
        try:
            return unicode(ctrl.Text or u'').strip()
        except Exception:
            return u''

    # --- presets ---
    def _reload_presets_combo(self):
        self._preset_loading = True
        try:
            cfg = self.LoadConfig()
            lst = cfg.get(self._PRESET_KEY, []) or []
            self.ComboPresetPick.Items.Clear()
            self.ComboPresetPick.Items.Add(u'— load preset —')
            for row in lst:
                nm = row.get(u'name')
                if nm:
                    self.ComboPresetPick.Items.Add(nm)
            self.ComboPresetPick.SelectedIndex = 0
        finally:
            self._preset_loading = False

    def _gather_preset(self, pname, cat_item):
        return {
            u'name': pname,
            u'category_code': getattr(cat_item, 'Code', u'') if cat_item else u'',
            u'fam_filter': self._tb(self.TxtFamFilter),
            u'type_filter': self._tb(self.TxtTypeFilter),
            u'txt_param_filter': self._tb(self.TxtParamFilter),
            u'scope_index': int(self.ComboParamScope.SelectedIndex),
            u'restrict_selection': self.ChkRestrictSelection.IsChecked == True,
            u'exclude_non_modifiable': self.ChkExcludeNonModifiable.IsChecked == True,
            u'only_open_worksets': self.ChkOpenWorksetsOnly.IsChecked == True,
            u'writable_discover_only': self.ChkWritableOnlyDiscover.IsChecked == True,
            u'writable_apply_hide': self.ChkWritableApply.IsChecked == True,
            u'dry_run_preview': self.ChkDryRunPreview.IsChecked == True,
            u'param_primary': self._primary_param_pick() or u'',
            u'param_aux': self._aux_param_pick_text() or u'',
        }

    def PresetSave_Click(self, sender, args):
        nm = self._tb(self.TxtPresetSaveName)
        if not nm:
            forms.alert(u'Enter preset name.')
            return
        payload = self._gather_preset(nm, self.ComboCategory.SelectedItem)
        cfg = self.LoadConfig()
        lst = cfg.get(self._PRESET_KEY, []) or []
        lst = [x for x in lst if unicode(x.get(u'name', u'')) != nm]
        lst.append(payload)
        cfg[self._PRESET_KEY] = sorted(lst, key=lambda z: unicode(z.get(u'name', u'')))
        self.SaveConfig(cfg)
        forms.alert(u'Saved preset "{}".'.format(nm))
        self._reload_presets_combo()

    def PresetLoad_Changed(self, sender, args):
        if self._preset_loading or self.ComboPresetPick.SelectedIndex <= 0:
            return
        name = unicode(self.ComboPresetPick.SelectedItem)
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
            cc = hit.get(u'category_code')
            if cc:
                for idx in range(self.ComboCategory.Items.Count):
                    pk = self.ComboCategory.Items[idx]
                    if getattr(pk, 'Code', None) == cc:
                        self.ComboCategory.SelectedIndex = idx
                        break
            self.TxtFamFilter.Text = hit.get(u'fam_filter', u'') or u''
            self.TxtTypeFilter.Text = hit.get(u'type_filter', u'') or u''
            self.TxtParamFilter.Text = hit.get(u'txt_param_filter', u'') or u''
            try:
                self.ComboParamScope.SelectedIndex = min(
                    int(hit.get(u'scope_index', 0)),
                    max(0, self.ComboParamScope.Items.Count - 1))
            except Exception:
                pass
            self.ChkRestrictSelection.IsChecked = bool(hit.get(u'restrict_selection'))
            self.ChkExcludeNonModifiable.IsChecked = bool(hit.get(u'exclude_non_modifiable'))
            self.ChkOpenWorksetsOnly.IsChecked = bool(hit.get(u'only_open_worksets'))
            self.ChkWritableOnlyDiscover.IsChecked = bool(hit.get(u'writable_discover_only'))
            self.ChkWritableApply.IsChecked = bool(hit.get(u'writable_apply_hide', True))
            self.ChkDryRunPreview.IsChecked = bool(hit.get(u'dry_run_preview', True))
        finally:
            self._preset_loading = False
        self.Scan_Click(None, None)
        _sel_combo_text(self.ComboParam, unicode(hit.get(u'param_primary', u'')))
        aux = unicode(hit.get(u'param_aux', u'')).strip()
        if aux:
            _sel_combo_text(self.ComboParamAux, aux)
        else:
            self.ComboParamAux.SelectedIndex = 0
        pk = self._primary_param_pick()
        if pk and self._types:
            self._rebuild(pk, self._aux_param_pick())

    # --- scopes ---
    def _scope_ok(self, kind):
        lbl = unicode(self.ComboParamScope.SelectedItem or u'').lower()
        if u'built-in' in lbl:
            return kind == u'built_in'
        if u'shared' in lbl:
            return kind == u'shared'
        if u'other' in lbl or u'family' in lbl:
            return kind == u'other'
        return True

    def _names_after_filters(self):
        q = self._tb(self.TxtParamFilter).lower()
        combo = []
        for spec in self._raw_param_specs or []:
            n = spec[u'name']
            k = spec.get(u'kind', u'other')
            if not self._scope_ok(k):
                continue
            if q and q not in n.lower():
                continue
            combo.append(n)
        return sorted(combo, key=lambda z: z.lower())

    def _refresh_lists(self):
        names = self._names_after_filters()
        keep_primary = self._primary_param_pick()
        keep_aux = self._aux_param_pick_text()

        self.ComboParam.Items.Clear()
        for nm in names:
            self.ComboParam.Items.Add(nm)
        _sel_combo_text(self.ComboParam, keep_primary)
        try:
            if self.ComboParam.Items.Count and self.ComboParam.SelectedIndex < 0:
                self.ComboParam.SelectedIndex = 0
        except Exception:
            pass

        self.ComboParamAux.Items.Clear()
        self.ComboParamAux.Items.Add(u'— none —')
        for nm in names:
            self.ComboParamAux.Items.Add(nm)
        if keep_aux:
            _sel_combo_text(self.ComboParamAux, keep_aux)
        else:
            self.ComboParamAux.SelectedIndex = 0

    def ParamFilter_TextChanged(self, sender, args):
        if self._preset_loading or not self._types:
            return
        self._refresh_lists()

    def ParamScope_Changed(self, sender, args):
        if self._preset_loading or not self._types:
            return
        self._refresh_lists()

    def Scan_Click(self, sender, args):
        if self._preset_loading:
            return
        ci = self.ComboCategory.SelectedItem
        if not ci:
            forms.alert(u'Pick category.')
            return
        elems, hint = _logic.gather_element_types(
            self.doc, ci.Code,
            self.TxtFamFilter.Text, self.TxtTypeFilter.Text,
            uidoc=self._uidoc,
            restrict_selection=self.ChkRestrictSelection.IsChecked == True,
            exclude_non_modifiable=self.ChkExcludeNonModifiable.IsChecked == True,
            only_open_worksets=self.ChkOpenWorksetsOnly.IsChecked == True)
        self._types = elems
        if not elems:
            forms.alert(u'No matching types.')
            self.TxtRowCount.Text = u'0 types'
            self._types = []
            self._raw_param_specs = []
            self._rows.Clear()
            self.ComboParam.Items.Clear()
            self.ComboParamAux.Items.Clear()
            self.ComboParamAux.Items.Add(u'— none —')
            try:
                self.ComboParamAux.SelectedIndex = 0
            except Exception:
                pass
            return
        self.TxtRowCount.Text = u'{} {}'.format(len(elems), hint or u'')

        wd = self.ChkWritableOnlyDiscover.IsChecked == True
        self._raw_param_specs = _logic.discover_param_specs(
            elems, writable_only=wd)
        self._refresh_lists()
        p1 = self._primary_param_pick()
        aux = self._aux_param_pick()
        if p1:
            self._rebuild(p1, aux)
        else:
            self._rows.Clear()

    def _primary_param_pick(self):
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

    def _aux_param_pick_text(self):
        try:
            it = self.ComboParamAux.SelectedItem
            return unicode(it or u'').strip()
        except Exception:
            return u''

    def _aux_param_pick(self):
        if self.ComboParamAux.SelectedIndex <= 0:
            return None
        s = self._aux_param_pick_text()
        if not s or s == u'— none —':
            return None
        return s

    def Param_SelectionChanged(self, sender, args):
        if not self._types or self._preset_loading:
            return
        p = self._primary_param_pick()
        if p:
            self._rebuild(p, self._aux_param_pick())

    def AuxParam_SelectionChanged(self, sender, args):
        if not self._types or self._preset_loading:
            return
        p = self._primary_param_pick()
        if p:
            self._rebuild(p, self._aux_param_pick())

    def _rebuild(self, pname, aux_nm=None):
        hide_ro = self.ChkWritableApply.IsChecked == True
        self._set_loading(True, u'Building grid…')
        try:
            self._rows.Clear()
            for et in self._types:
                row = TypeParamRow(et, pname, aux_nm)
                if hide_ro and row.ParamRef and row.ParamRef.IsReadOnly:
                    continue
                self._rows.Add(row)
            try:
                self.GridMain.Items.Refresh()
            except Exception:
                pass
        finally:
            self._set_loading(False)

    def Grid_Main_BeginningEdit(self, sender, args):
        row = getattr(args.Row, 'Item', None)
        if isinstance(row, TypeParamRow) and not row.CanEdit:
            args.Cancel = True

    def FillAll_Click(self, sender, args):
        val = unicode(self.TxtApplyAll.Text or '')
        for rw in self._rows:
            if isinstance(rw, TypeParamRow) and rw.CanEdit:
                rw.NewVal = val
        try:
            self.GridMain.Items.Refresh()
        except Exception:
            pass

    def Duplicate_Click(self, sender, args):
        chose = []
        try:
            for o in self.GridMain.SelectedItems:
                if isinstance(o, TypeParamRow):
                    chose.append(o)
        except Exception:
            pass
        if len(chose) != 1:
            forms.alert(u'Select single row.')
            return
        row = chose[0]
        nn = self._tb(self.TxtDupTypeName)
        if not nn:
            forms.alert(u'Provide new duplicate name.')
            return
        dup, err = _logic.duplicate_type(self.doc, row._et, nn)
        if err:
            _trace.log_event(u'struct_types', u'duplicate_fail', unicode(err))
            forms.alert(u'Duplicate error: {}'.format(err))
            return
        forms.alert(u'Duplicated. New Type Id {}.'.format(_gid(dup.Id)))
        self.Scan_Click(None, None)

    def Apply_Click(self, sender, args):
        pn = self._primary_param_pick()
        if not pn:
            forms.alert(u'Pick primary parameter.')
            return
        if self._rows.Count <= 0:
            forms.alert(u'SCAN first.')
            return
        tup = []
        for rw in self._rows:
            if not isinstance(rw, TypeParamRow):
                continue
            p = rw.ParamRef or _logic.lookup_param_named(rw._et, pn)
            if not p or (self.ChkWritableApply.IsChecked == True and p.IsReadOnly):
                continue
            try:
                if _logic.param_edit_is_unchanged(p, rw.NewVal):
                    continue
            except Exception:
                if unicode(rw.NewVal).strip() == unicode(rw.CurrentVal).strip():
                    continue
            tup.append((p, rw.NewVal))
        if not tup:
            forms.alert(u'No pending edits.')
            return
        if self.ChkDryRunPreview.IsChecked == True:
            lines = _logic.preview_apply_strings(tup)
            block = u'Dry-run — {} cell(s).\n{}'.format(len(tup), u'-' * 28)
            block += u'\n' + u'\n'.join(lines[:18])
            if not forms.alert(block + u'\n\nApply?', yes=True, no=True):
                return
        elif not forms.alert(u'Confirm {} edits?'.format(len(tup)), yes=True, no=True):
            return
        self._set_loading(True, u'Applying…')
        try:
            ok, fail, skip = _logic.apply_batch(self.doc, tup)
        except Exception as ex:
            _trace.log_event(u'struct_types', u'apply_exc', unicode(ex))
            forms.alert(u'Apply failed: {}'.format(ex))
            return
        finally:
            self._set_loading(False)
        if fail or skip:
            _trace.log_event(
                u'struct_types',
                u'apply_partial',
                u'ok={} fail={} skip={}'.format(ok, fail, skip))
        forms.alert(u'OK {} / Fail {} / Skip {}'.format(ok, fail, skip))
        self._rebuild(pn, self._aux_param_pick())

    def Export_Click(self, sender, args):
        if not self._rows.Count:
            forms.alert(u'Nothing to export — scan first.')
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        p1 = self._primary_param_pick() or u'Param'
        ax = self._aux_param_pick() or u''
        head = [u'Family : Type', u'TypeId']
        if ax:
            head.append(u'Aux ' + ax)
        head.extend([p1 + u' current', p1 + u' new'])
        body = [_csv_line(head)]
        for rw in self._rows:
            if not isinstance(rw, TypeParamRow):
                continue
            pieces = [rw.FamType, rw.TypeId]
            if ax:
                pieces.append(rw.AuxVal)
            pieces.extend([rw.CurrentVal, rw.NewVal])
            body.append(_csv_line(pieces))
        try:
            with codecs.open(path, 'w', encoding='utf-8-sig') as f:
                f.write(u'\r\n'.join(body))
        except Exception as ex:
            forms.alert(u'CSV export failed: {}'.format(ex))
            return
        forms.alert(path, title=u'CSV')
