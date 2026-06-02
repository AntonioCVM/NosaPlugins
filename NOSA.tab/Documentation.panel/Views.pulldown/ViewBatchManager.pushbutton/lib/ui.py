# -*- coding: utf-8 -*-
import os, sys
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit, DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.loader      import load_local_module as _lm
from nosa_utils.base_window import NOSAWindow
_logic = _lm('viewbatchmanager_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class ViewRow(object):
    def __init__(self, data, idx):
        self._view    = data['view']
        self.RowNum   = idx
        self.ViewType = data['type']
        self.Name     = data['name']
        self.Template = data['template']
        self.NewName  = data['name']
        self.HasChange = False


class TmplItem(object):
    def __init__(self, eid, name):
        self.Id   = eid
        self.Name = name


class ViewBatchManagerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'view_batch_manager')
        self.doc = doc

        self._all_data   = []
        self._rename_rows = ObservableCollection[ViewRow]()
        self._tmpl_rows   = ObservableCollection[ViewRow]()
        self.GridRename.ItemsSource   = self._rename_rows
        self.GridTemplate.ItemsSource = self._tmpl_rows

        # View templates for Apply Template tab
        tpls = _logic.get_view_templates(doc)
        self.CboTemplate.ItemsSource   = [TmplItem(eid, n) for eid, n in tpls]
        self.CboTemplate.SelectedIndex = 0 if tpls else -1

        self._load_views()

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    # ── data loading ──────────────────────────────────────────────────────────

    def _load_views(self, filter_text='', filter_text_t=''):
        self.SetLoading(True, 'Loading views...')
        try:
            self._all_data = _logic.collect_views(self.doc)
            self._refresh_rename(filter_text)
            self._refresh_template(filter_text_t)
        except Exception as e:
            forms.alert("Error loading views: {}".format(e))
        finally:
            self.SetLoading(False)

    def _refresh_rename(self, filter_text=''):
        txt = (filter_text or '').strip().lower()
        self._rename_rows.Clear()
        for i, d in enumerate(self._all_data, 1):
            if txt and txt not in d['name'].lower():
                continue
            self._rename_rows.Add(ViewRow(d, i))
        self.TxtViewCount.Text = '{} views'.format(len(list(self._rename_rows)))
        self._compute_preview()

    def _refresh_template(self, filter_text=''):
        txt = (filter_text or '').strip().lower()
        self._tmpl_rows.Clear()
        for i, d in enumerate(self._all_data, 1):
            if txt and txt not in d['name'].lower():
                continue
            self._tmpl_rows.Add(ViewRow(d, i))

    # ── tab switching ─────────────────────────────────────────────────────────

    def Tab_Changed(self, sender, args):
        try:
            idx = self.TabMain.SelectedIndex
            v   = System.Windows.Visibility
            self.SidebarRename.Visibility   = v.Visible   if idx == 0 else v.Collapsed
            self.SidebarTemplate.Visibility = v.Visible   if idx == 1 else v.Collapsed
        except Exception:
            pass

    # ── rename tab ────────────────────────────────────────────────────────────

    def Filter_Changed(self, sender, args):
        self._refresh_rename((self.TxtFilter.Text or '').strip())

    def Mode_Changed(self, sender, args):
        v = System.Windows.Visibility
        idx = self.CboMode.SelectedIndex
        self.PanelFindReplace.Visibility = v.Visible   if idx == 0 else v.Collapsed
        self.PanelPrefixSuffix.Visibility = v.Visible  if idx == 1 else v.Collapsed
        self.PanelCase.Visibility         = v.Visible  if idx == 2 else v.Collapsed
        self._compute_preview()

    def Preview_Changed(self, sender, args):
        self._compute_preview()

    def _get_rename_mode_params(self):
        idx = self.CboMode.SelectedIndex
        if idx == 0:
            return 'find_replace', {
                'find':           self.TxtFind.Text or '',
                'replace':        self.TxtReplace.Text or '',
                'case_sensitive': self.ChkCaseSensitive.IsChecked == True,
            }
        if idx == 1:
            return 'prefix_suffix', {
                'prefix': self.TxtPrefix.Text or '',
                'suffix': self.TxtSuffix.Text or '',
            }
        # idx == 2: case
        if self.RbUpper.IsChecked:    cm = 'upper'
        elif self.RbLower.IsChecked:  cm = 'lower'
        elif self.RbSentence.IsChecked: cm = 'sentence'
        else:                          cm = 'title'
        return 'case', {'case_mode': cm}

    def _compute_preview(self):
        try:
            mode, params = self._get_rename_mode_params()
            for row in self._rename_rows:
                new_name = _logic.compute_new_name(row.Name, mode, params)
                row.NewName   = new_name
                row.HasChange = (new_name != row.Name)
            self.GridRename.Items.Refresh()
        except Exception:
            pass

    def Rename_Click(self, sender, args):
        selected = list(self.GridRename.SelectedItems)
        if not selected:
            forms.alert("Select at least one view in the grid.")
            return
        mode, params = self._get_rename_mode_params()
        renames = []
        for row in selected:
            new_name = _logic.compute_new_name(row.Name, mode, params)
            if new_name and new_name != row.Name:
                renames.append((row._view.Id, new_name))
        if not renames:
            forms.alert("No names would change with the current settings.")
            return
        if not forms.alert(
            "Rename {} view(s)?".format(len(renames)), yes=True, no=True
        ):
            return
        self.SetLoading(True, "Renaming views...")
        try:
            ok, failed = _logic.rename_views(self.doc, renames)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Rename failed: {}".format(e))
            return
        self.SetLoading(False)
        forms.alert("Renamed: {}  |  Failed: {}".format(ok, failed), title="Rename Views")
        self._load_views(
            (self.TxtFilter.Text or '').strip(),
            (self.TxtFilterT.Text or '').strip(),
        )

    # ── template tab ──────────────────────────────────────────────────────────

    def FilterT_Changed(self, sender, args):
        self._refresh_template((self.TxtFilterT.Text or '').strip())

    def ApplyTemplate_Click(self, sender, args):
        selected = list(self.GridTemplate.SelectedItems)
        if not selected:
            forms.alert("Select at least one view.")
            return
        tmpl_item = self.CboTemplate.SelectedItem
        if not tmpl_item:
            forms.alert("Select a view template.")
            return
        if not forms.alert(
            "Apply '{}' to {} view(s)?".format(tmpl_item.Name, len(selected)),
            yes=True, no=True
        ):
            return
        ids = [r._view.Id for r in selected]
        self.SetLoading(True, "Applying template...")
        try:
            ok, failed = _logic.apply_view_template(self.doc, ids, tmpl_item.Id)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Apply failed: {}".format(e))
            return
        self.SetLoading(False)
        forms.alert("Applied: {}  |  Failed: {}".format(ok, failed), title="Apply Template")
        self._load_views(
            (self.TxtFilter.Text or '').strip(),
            (self.TxtFilterT.Text or '').strip(),
        )

    def RemoveTemplate_Click(self, sender, args):
        selected = list(self.GridTemplate.SelectedItems)
        if not selected:
            forms.alert("Select at least one view.")
            return
        if not forms.alert(
            "Remove view template from {} view(s)?".format(len(selected)),
            yes=True, no=True
        ):
            return
        ids = [r._view.Id for r in selected]
        self.SetLoading(True, "Removing templates...")
        try:
            ok, failed = _logic.apply_view_template(
                self.doc, ids, DB.ElementId.InvalidElementId)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Remove failed: {}".format(e))
            return
        self.SetLoading(False)
        forms.alert("Cleared: {}  |  Failed: {}".format(ok, failed), title="Remove Template")
        self._load_views(
            (self.TxtFilter.Text or '').strip(),
            (self.TxtFilterT.Text or '').strip(),
        )

    # ── shared ────────────────────────────────────────────────────────────────

    def Refresh_Click(self, sender, args):
        self._load_views(
            (self.TxtFilter.Text or '').strip(),
            (self.TxtFilterT.Text or '').strip(),
        )
