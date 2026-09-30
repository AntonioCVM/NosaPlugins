# -*- coding: utf-8 -*-
import io, csv, os, sys, imp
import System.Windows
from System.Collections.ObjectModel import ObservableCollection

from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.revit_helpers import element_id_from_int

_here = os.path.dirname(os.path.abspath(__file__))
_tg_logic = imp.load_source('vtm_tg_logic', os.path.join(_here, 'logic_template_guard.py'))
_ct_logic_mod = imp.load_source('vtm_ct_logic', os.path.join(_here, 'logic_copy_templates.py'))

run_all_checks    = _tg_logic.run_all_checks
CopyTemplateLogic = _ct_logic_mod.CopyTemplateLogic


class _IssueRow(object):
    def __init__(self, d):
        self.Key      = d.get('key', '')
        self.Label    = d.get('label', '')
        self.Severity = d.get('severity', '')
        self.Sheet    = d.get('sheet', u'—')
        self.ViewName = d.get('view', '')
        self.ViewType = d.get('type', '')
        self.Detail   = d.get('detail', '')
        self.Id       = d.get('id')


class _ViewItem(object):
    def __init__(self, element):
        self.Element   = element
        self.Name      = element.Name
        self.IsChecked = False


class ViewTemplateManagerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'view_template_manager')
        self.doc = doc

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._tg_init()
        self._ct_init()
        self._co_init()

    # ──────────────────────────────────────────────────────────────────
    # TAB 1: TEMPLATE GUARD
    # ──────────────────────────────────────────────────────────────────

    def _tg_init(self):
        self._tg_rows     = ObservableCollection[_IssueRow]()
        self._tg_all_rows = []
        self._tg_data     = None
        self._tg_sheet_ids = self._tg_collect_sheet_view_ids()
        self.TG_GridResults.ItemsSource = self._tg_rows

    def _tg_collect_sheet_view_ids(self):
        ids = set()
        try:
            for s in (DB.FilteredElementCollector(self.doc)
                      .OfClass(DB.ViewSheet).ToElements()):
                for vpid in s.GetAllViewports():
                    try:
                        vp  = self.doc.GetElement(vpid)
                        ids.add(get_id_value(vp.ViewId))
                    except Exception:
                        pass
        except Exception:
            pass
        return ids

    def _tg_active_checks(self):
        m = {
            'no_template':     self.TG_ChkNoTemplate,
            'wrong_scale':     self.TG_ChkWrongScale,
            'sheet_naming':    self.TG_ChkSheetNaming,
            'manual_overrides':self.TG_ChkOverrides,
            'crop_missing':    self.TG_ChkCrop,
            'wrong_detail_level': self.TG_ChkDetailLevel,
        }
        return {k for k, cb in m.items() if cb.IsChecked == True}

    def _tg_active_sevs(self):
        s = set()
        if self.TG_ChkHigh.IsChecked   == True: s.add('High')
        if self.TG_ChkMedium.IsChecked == True: s.add('Medium')
        if self.TG_ChkLow.IsChecked    == True: s.add('Low')
        return s

    def _tg_apply_filter(self):
        sevs        = self._tg_active_sevs()
        search      = (self.TG_TxtSearch.Text or u'').lower()
        only_sheets = self.TG_ChkOnlySheets.IsChecked == True
        self._tg_rows.Clear()
        high = med = low = 0
        for r in self._tg_all_rows:
            if r.Severity not in sevs:
                continue
            if search and search not in r.ViewName.lower() \
                      and search not in r.Sheet.lower() \
                      and search not in r.Detail.lower():
                continue
            if only_sheets and r.Id is not None \
                           and r.Id not in self._tg_sheet_ids:
                continue
            self._tg_rows.Add(r)
            if r.Severity == 'High':   high += 1
            elif r.Severity == 'Medium': med += 1
            else: low += 1
        self.TG_TxtHigh.Text   = u'{} High'.format(high)
        self.TG_TxtMedium.Text = u'{} Medium'.format(med)
        self.TG_TxtLow.Text    = u'{} Low'.format(low)
        total = self._tg_data['total'] if self._tg_data else 0
        self.TG_TxtTotal.Text  = u'{} total issues'.format(total)

    def TG_Run_Click(self, sender, args):
        self.SetLoading(True, u'Checking views & sheets...')
        self._tg_rows.Clear(); self._tg_all_rows = []
        self.TG_BtnExport.IsEnabled = False
        try:
            self._tg_data = run_all_checks(self.doc, self._tg_active_checks())
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error: {}'.format(e)); return
        self._tg_all_rows = [_IssueRow(d) for d in self._tg_data['issues']]
        self._tg_apply_filter()
        self.SetLoading(False)
        self.TG_BtnExport.IsEnabled = True

    def TG_Search_Changed(self, sender, args):
        self._tg_apply_filter()

    def TG_Grid_SelectionChanged(self, sender, args):
        self.TG_BtnSelect.IsEnabled = self.TG_GridResults.SelectedItem is not None

    def TG_Select_Click(self, sender, args):
        row = self.TG_GridResults.SelectedItem
        if not row or row.Id is None: return
        try:
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([element_id_from_int(row.Id)])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert(u'Could not select: {}'.format(e))

    def TG_EditRules_Click(self, sender, args):
        rules = os.path.join(_here, '..', 'TemplateGuard.nobutton', 'lib', 'rules.json')
        rules = os.path.normpath(rules)
        try:
            import subprocess
            subprocess.Popen(['notepad.exe', rules])
        except Exception:
            forms.alert(u'Rules file:\n{}'.format(rules))

    def TG_Export_Click(self, sender, args):
        if not self._tg_data: return
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Severity','Rule','Sheet','View','Type','Detail'])
                for r in self._tg_rows:
                    w.writerow([r.Severity, r.Label, r.Sheet, r.ViewName, r.ViewType, r.Detail])
            forms.alert(u'Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export failed: {}'.format(e))

    # ──────────────────────────────────────────────────────────────────
    # TAB 2: APPLY TEMPLATE
    # ──────────────────────────────────────────────────────────────────

    def _ct_init(self):
        self._ct_logic    = CopyTemplateLogic(self.doc)
        self._ct_all_views = []

        templates = self._ct_logic.get_all_templates()
        self.CT_ComboTemplates.ItemsSource = templates
        if templates:
            self.CT_ComboTemplates.SelectedIndex = 0
            self._ct_show_info(templates[0])

        raw = self._ct_logic.get_all_non_template_views()
        self._ct_all_views = [_ViewItem(v) for v in raw]
        self.CT_ListViews.ItemsSource = list(self._ct_all_views)

        self.CT_ComboTemplates.SelectionChanged += self._ct_combo_changed
        self.CT_TxtFilter.TextChanged += self.CT_Filter_Changed

    def _ct_show_info(self, tmpl):
        if not tmpl: return
        try:
            info = self._ct_logic.get_template_info(tmpl)
            self.CT_TxtScale.Text   = u'Scale: {}'.format(info.get('scale', '—'))
            self.CT_TxtFilters.Text = u'Filters: {}'.format(len(info.get('filters', [])))
            self.CT_PanelInfo.Visibility = System.Windows.Visibility.Visible
        except Exception:
            pass

    def _ct_combo_changed(self, sender, args):
        self._ct_show_info(self.CT_ComboTemplates.SelectedItem)

    def CT_Filter_Changed(self, sender, args):
        text = (self.CT_TxtFilter.Text or u'').lower()
        visible = [v for v in self._ct_all_views
                   if not text or text in v.Name.lower()]
        self.CT_ListViews.ItemsSource = visible

    def CT_CheckAll_Checked(self, sender, args):
        for v in list(self.CT_ListViews.ItemsSource or []):
            v.IsChecked = True
        self.CT_ListViews.Items.Refresh()

    def CT_CheckAll_Unchecked(self, sender, args):
        for v in list(self.CT_ListViews.ItemsSource or []):
            v.IsChecked = False
        self.CT_ListViews.Items.Refresh()

    def CT_Apply_Click(self, sender, args):
        tmpl = self.CT_ComboTemplates.SelectedItem
        if not tmpl:
            forms.alert(u'Please select a source template.')
            return
        targets = [v for v in (self.CT_ListViews.ItemsSource or []) if v.IsChecked]
        if not targets:
            forms.alert(u'Please select at least one target view.')
            return
        self.CT_Overlay.Visibility = System.Windows.Visibility.Visible
        count = 0
        with revit.Transaction(u'NOSA — Apply View Template'):
            for vi in targets:
                ok, _ = self._ct_logic.copy_template_to_view(tmpl, vi.Element)
                if ok: count += 1
        self.CT_Overlay.Visibility = System.Windows.Visibility.Collapsed
        forms.alert(u"Applied '{}' to {} views.".format(tmpl.Name, count))

    # ──────────────────────────────────────────────────────────────────
    # TAB 3: COPY OVERRIDES
    # ──────────────────────────────────────────────────────────────────

    def _co_init(self):
        raw = self._ct_logic.get_all_non_template_views()
        self.CO_ComboSource.ItemsSource = raw
        if raw:
            self.CO_ComboSource.SelectedIndex = 0
        self._co_all_views = [_ViewItem(v) for v in raw]
        self.CO_ListViews.ItemsSource = list(self._co_all_views)
        self.CO_TxtFilter.TextChanged += self.CO_Filter_Changed

    def CO_Filter_Changed(self, sender, args):
        text = (self.CO_TxtFilter.Text or u'').lower()
        visible = [v for v in self._co_all_views
                   if not text or text in v.Name.lower()]
        self.CO_ListViews.ItemsSource = visible

    def CO_CheckAll_Checked(self, sender, args):
        for v in list(self.CO_ListViews.ItemsSource or []):
            v.IsChecked = True
        self.CO_ListViews.Items.Refresh()

    def CO_CheckAll_Unchecked(self, sender, args):
        for v in list(self.CO_ListViews.ItemsSource or []):
            v.IsChecked = False
        self.CO_ListViews.Items.Refresh()

    def CO_Copy_Click(self, sender, args):
        src = self.CO_ComboSource.SelectedItem
        if not src:
            forms.alert(u'Please select a source view.')
            return
        targets = [v for v in (self.CO_ListViews.ItemsSource or [])
                   if v.IsChecked and v.Element.Id != src.Id]
        if not targets:
            forms.alert(u'Please select at least one target view.')
            return
        self.CO_Overlay.Visibility = System.Windows.Visibility.Visible
        count = 0
        with revit.Transaction(u'NOSA — Copy View Overrides'):
            for vi in targets:
                ok, _ = self._ct_logic.copy_overrides_to_view(src, vi.Element)
                if ok: count += 1
        self.CO_Overlay.Visibility = System.Windows.Visibility.Collapsed
        forms.alert(u'Copied overrides to {} views.'.format(count))

    # ──────────────────────────────────────────────────────────────────
    # Shared
    # ──────────────────────────────────────────────────────────────────

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
