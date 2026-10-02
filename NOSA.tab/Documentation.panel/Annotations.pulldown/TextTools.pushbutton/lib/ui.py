# -*- coding: utf-8 -*-
import re, os, sys
import System.Windows
from System.Collections.ObjectModel import ObservableCollection

from Autodesk.Revit import DB
from pyrevit import forms, revit
from nosa_utils.telemetry import log_swallowed
_LOG = u'texttools'

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

try:
    from nosa_utils import text_utils
except ImportError:
    class text_utils(object):
        @staticmethod
        def to_uppercase(s):  return s.upper()
        @staticmethod
        def to_lowercase(s):  return s.lower()
        @staticmethod
        def capitalise_sentences(s):
            import re as _r
            return _r.sub(r'(^|[.!?]\s+)([a-z])',
                          lambda m: m.group(1) + m.group(2).upper(), s)
        @staticmethod
        def to_title_case(s):  return s.title()

try:
    from nosa_utils import geometry as _geo
    def _sort_spatially(elems):
        def _loc(e):
            try:
                c = _geo.get_element_center(e)
                if c:
                    return (-c.Y, c.X)
            except Exception:
                log_swallowed(_LOG, u'_loc')
            return (0, 0)
        return sorted(elems, key=_loc)
except ImportError:
    def _sort_spatially(elems):
        return elems


class _PreviewRow(object):
    def __init__(self, display_name, old_val, new_val):
        self.DisplayName = display_name
        self.OldValue    = old_val
        self.NewValue    = new_val
        self.IsChange    = (old_val != new_val)


class TextToolsWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'text_tools')
        self.doc = doc

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._br_rows = ObservableCollection[_PreviewRow]()
        self._cc_rows = ObservableCollection[_PreviewRow]()
        self._br_changes = []
        self._cc_changes = []
        self.BR_GridPreview.ItemsSource = self._br_rows
        self.CC_GridPreview.ItemsSource = self._cc_rows

        self._br_init()
        self._cc_init()

    # ══════════════════════════════════════════════════════════════════
    # TAB 1: BATCH RENAME
    # ══════════════════════════════════════════════════════════════════

    def _br_init(self):
        cats = self._br_get_cats()
        if cats:
            self.BR_CboCategory.ItemsSource = cats
            self.BR_CboCategory.SelectedIndex = 0

    def _br_get_cats(self):
        cats = []
        try:
            for cat in self.doc.Settings.Categories:
                try:
                    if cat.CategoryType != DB.CategoryType.Model:
                        continue
                    col = (DB.FilteredElementCollector(self.doc)
                           .OfCategoryId(cat.Id)
                           .WhereElementIsNotElementType())
                    if col.GetElementCount() > 0:
                        cats.append(cat)
                except Exception:
                    log_swallowed(_LOG, u'TextToolsWindow._br_get_cats')
        except Exception:
            log_swallowed(_LOG, u'TextToolsWindow._br_get_cats')
        return sorted(cats, key=lambda c: c.Name)

    def BR_Mode_Changed(self, sender, args):
        V = System.Windows.Visibility.Visible
        C = System.Windows.Visibility.Collapsed
        self.BR_PanelFindReplace.Visibility  = V if self.BR_RbFindReplace.IsChecked  == True else C
        self.BR_PanelPrefixSuffix.Visibility = V if self.BR_RbPrefixSuffix.IsChecked == True else C
        self.BR_PanelSequential.Visibility   = V if self.BR_RbSequential.IsChecked   == True else C

    def BR_Source_Changed(self, sender, args):
        self.BR_CboCategory.IsEnabled = (self.BR_RbCategory.IsChecked == True)

    def _br_get_elements(self):
        if self.BR_RbSelection.IsChecked == True:
            sel = revit.get_selection()
            elems = list(sel.elements) if hasattr(sel, 'elements') else list(sel)
            if not elems:
                forms.alert(u'No elements selected.')
                return []
            return elems
        else:
            cat = self.BR_CboCategory.SelectedItem
            if cat is None:
                forms.alert(u'Select a category.')
                return []
            return list(
                DB.FilteredElementCollector(self.doc)
                .OfCategoryId(cat.Id)
                .WhereElementIsNotElementType()
                .ToElements()
            )

    def _br_get_param_value(self, elem):
        bip = (DB.BuiltInParameter.ALL_MODEL_MARK
               if self.BR_RbMark.IsChecked == True
               else DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        p = elem.get_Parameter(bip)
        return p.AsString() or u'' if p else u''

    def _br_set_param_value(self, elem, val):
        bip = (DB.BuiltInParameter.ALL_MODEL_MARK
               if self.BR_RbMark.IsChecked == True
               else DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        p = elem.get_Parameter(bip)
        if p and not p.IsReadOnly:
            p.Set(val)
            return True
        return False

    def _br_element_label(self, elem):
        try:
            if hasattr(elem, 'Symbol') and elem.Symbol:
                return u'{} : {}'.format(
                    elem.Symbol.Family.Name if elem.Symbol.Family else u'',
                    elem.Name)
            return elem.Name if hasattr(elem, 'Name') else u'Elem {}'.format(elem.Id)
        except Exception:
            return u'Elem {}'.format(elem.Id)

    def _br_compute_changes(self, elements):
        changes = []
        if self.BR_RbFindReplace.IsChecked == True:
            find    = self.BR_TxtFind.Text or u''
            replace = self.BR_TxtReplace.Text or u''
            use_re  = self.BR_ChkRegex.IsChecked == True
            for elem in elements:
                old = self._br_get_param_value(elem)
                try:
                    new = re.sub(find, replace, old) if use_re else old.replace(find, replace)
                except Exception:
                    new = old
                changes.append((elem, old, new))

        elif self.BR_RbPrefixSuffix.IsChecked == True:
            prefix = self.BR_TxtPrefix.Text or u''
            suffix = self.BR_TxtSuffix.Text or u''
            for elem in elements:
                old = self._br_get_param_value(elem)
                new = prefix + old + suffix
                changes.append((elem, old, new))

        else:
            pattern   = self.BR_TxtPattern.Text or u'ELEM-###'
            start_str = self.BR_TxtStartNum.Text or u'1'
            try:
                start = int(start_str)
            except Exception:
                start = 1
            sorted_elems = _sort_spatially(elements)
            hash_count   = pattern.count('#')
            counter      = start
            for elem in sorted_elems:
                old     = self._br_get_param_value(elem)
                num_str = str(counter).zfill(hash_count)
                new     = pattern.replace('#' * hash_count, num_str)
                while '#' in new:
                    new = new.replace('#', str(counter), 1)
                changes.append((elem, old, new))
                counter += 1

        return changes

    def BR_Preview_Click(self, sender, args):
        elements = self._br_get_elements()
        if not elements:
            return
        self._br_changes = self._br_compute_changes(elements)
        self._br_rows.Clear()
        n_change = 0
        for elem, old, new in self._br_changes[:200]:
            row = _PreviewRow(self._br_element_label(elem), old, new)
            if row.IsChange:
                n_change += 1
            self._br_rows.Add(row)
        if len(self._br_changes) > 200:
            extra = len(self._br_changes) - 200
            self._br_rows.Add(_PreviewRow(u'… {} more not shown'.format(extra), u'', u''))
        actual_changes = sum(1 for _, o, n in self._br_changes if o != n)
        self.BR_TxtPillTotal.Text   = u'{} elements'.format(len(elements))
        self.BR_TxtPillChanges.Text = u'{} changes'.format(actual_changes)
        self.BR_TxtStatus.Text      = u'{} elements scanned, {} will change.'.format(
            len(elements), actual_changes)
        self.BR_BtnApply.IsEnabled  = actual_changes > 0

    def BR_Apply_Click(self, sender, args):
        actual = [(e, o, n) for e, o, n in self._br_changes if o != n]
        if not actual:
            forms.alert(u'Nothing to apply.')
            return
        param_lbl = u'Mark' if self.BR_RbMark.IsChecked == True else u'Comments'
        if not forms.alert(
            u'Apply {} rename(s) to {} parameter?'.format(len(actual), param_lbl),
            yes=True, no=True
        ):
            return
        ok = fail = 0
        with DB.Transaction(self.doc, u'NOSA — Batch Rename') as t:
            t.Start()
            for elem, _, new_val in actual:
                try:
                    if self._br_set_param_value(elem, new_val):
                        ok += 1
                    else:
                        fail += 1
                except Exception:
                    fail += 1
            t.Commit()
        self.BR_TxtStatus.Text     = u'Done. Renamed: {}  |  Failed: {}'.format(ok, fail)
        self.BR_BtnApply.IsEnabled = False
        forms.alert(u'Renamed: {}\nFailed: {}'.format(ok, fail), title=u'Batch Rename')

    # ══════════════════════════════════════════════════════════════════
    # TAB 2: CASE CONVERTER
    # ══════════════════════════════════════════════════════════════════

    def _cc_init(self):
        pass

    def CC_Target_Changed(self, sender, args):
        V = System.Windows.Visibility.Visible
        C = System.Windows.Visibility.Collapsed
        self.CC_PanelParam.Visibility = V if self.CC_RbParam.IsChecked == True else C

    def _cc_transform(self, text):
        if self.CC_RbUpper.IsChecked    == True: return text_utils.to_uppercase(text)
        if self.CC_RbLower.IsChecked    == True: return text_utils.to_lowercase(text)
        if self.CC_RbSentence.IsChecked == True: return text_utils.capitalise_sentences(text)
        return text_utils.to_title_case(text)

    def _cc_get_elements(self):
        if self.CC_RbScopeSelection.IsChecked == True:
            sel = revit.get_selection()
            return list(sel.elements) if hasattr(sel, 'elements') else list(sel)
        elif self.CC_RbScopeView.IsChecked == True:
            try:
                return list(
                    DB.FilteredElementCollector(self.doc, self.doc.ActiveView.Id)
                    .WhereElementIsNotElementType().ToElements()
                )
            except Exception:
                return []
        else:
            return list(
                DB.FilteredElementCollector(self.doc)
                .WhereElementIsNotElementType().ToElements()
            )

    def _cc_get_targets(self, elements):
        if self.CC_RbTextNotes.IsChecked == True:
            return [(e, None) for e in elements if isinstance(e, DB.TextNote)]
        else:
            pname = (self.CC_TxtParamName.Text or u'').strip()
            if not pname:
                forms.alert(u'Enter a parameter name.')
                return []
            result = []
            for e in elements:
                try:
                    p = e.LookupParameter(pname)
                    if p and p.StorageType == DB.StorageType.String and not p.IsReadOnly:
                        result.append((e, p))
                except Exception:
                    log_swallowed(_LOG, u'TextToolsWindow._cc_get_targets')
            return result

    def _cc_get_text(self, elem, param):
        if param is None:
            return elem.Text or u''
        return param.AsString() or u''

    def _cc_set_text(self, elem, param, val):
        if param is None:
            elem.Text = val
        else:
            param.Set(val)

    def CC_Preview_Click(self, sender, args):
        elements = self._cc_get_elements()
        if not elements:
            self.CC_TxtStatus.Text = u'No elements in scope.'
            return
        targets = self._cc_get_targets(elements)
        if not targets:
            self.CC_TxtStatus.Text = u'No matching elements found.'
            self.CC_BtnApply.IsEnabled = False
            return
        self._cc_changes = []
        self._cc_rows.Clear()
        n_change = 0
        for elem, param in targets:
            old = self._cc_get_text(elem, param)
            new = self._cc_transform(old)
            self._cc_changes.append((elem, param, old, new))
            if len(self._cc_rows) < 200:
                row = _PreviewRow(u'', old, new)
                row.IsChange = (old != new)
                self._cc_rows.Add(row)
            if old != new:
                n_change += 1
        actual = sum(1 for _, _, o, n in self._cc_changes if o != n)
        self.CC_TxtPillTotal.Text   = u'{} found'.format(len(targets))
        self.CC_TxtPillChanges.Text = u'{} changes'.format(actual)
        self.CC_TxtStatus.Text      = u'{} targets scanned, {} will change.'.format(
            len(targets), actual)
        self.CC_BtnApply.IsEnabled  = actual > 0

    def CC_Apply_Click(self, sender, args):
        actual = [(e, p, o, n) for e, p, o, n in self._cc_changes if o != n]
        if not actual:
            forms.alert(u'Nothing to apply.')
            return
        if len(actual) > 10:
            if not forms.alert(
                u'Apply case conversion to {} elements?'.format(len(actual)),
                yes=True, no=True
            ):
                return
        changed = 0
        with DB.Transaction(self.doc, u'NOSA — Case Converter') as t:
            t.Start()
            for elem, param, _, new_val in actual:
                try:
                    self._cc_set_text(elem, param, new_val)
                    changed += 1
                except Exception:
                    log_swallowed(_LOG, u'TextToolsWindow.CC_Apply_Click')
            t.Commit()
        self.CC_TxtStatus.Text     = u'Done. Changed: {}  |  Unchanged: {}'.format(
            changed, len(self._cc_changes) - changed)
        self.CC_BtnApply.IsEnabled = False
        forms.alert(u'Changed: {}'.format(changed), title=u'Case Converter')

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
