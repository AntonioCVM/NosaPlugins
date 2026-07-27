# -*- coding: utf-8 -*-
import imp
import os
import sys

import System.Windows
from System.Collections.ObjectModel import ObservableCollection

from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_VIS = System.Windows.Visibility.Visible
_COL = System.Windows.Visibility.Collapsed


def _load_sibling_logic(name, module_name):
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    for suffix in ('nobutton', 'pushbutton'):
        path = os.path.join(base, '{}.{}'.format(name, suffix), 'lib', 'logic.py')
        if os.path.exists(path):
            return imp.load_source(module_name, path)
    raise ImportError('Cannot find logic for: ' + name)


_vbm  = _load_sibling_logic('ViewBatchManager', 'viewhub_vbm')
_vorg = _load_sibling_logic('ViewOrganiser',    'viewhub_vorg')


class ViewRow(object):
    def __init__(self, data, idx):
        self._view     = data['view']
        self.RowNum    = idx
        self.ViewType  = data['type']
        self.Name      = data['name']
        self.Template  = data['template']
        self.NewName   = data['name']
        self.HasChange = False


class TmplItem(object):
    def __init__(self, eid, name):
        self.Id   = eid
        self.Name = name


class OrgViewRow(object):
    def __init__(self, rec, new_name=u''):
        self.Name    = rec['name']
        self.NewName = new_name if new_name != rec['name'] else u''
        self.Vtype   = rec['vtype']
        self.Level   = rec['level'] or u'—'
        self.Placed  = u'Yes' if rec['placed'] else u'No'
        self._rec    = rec


class ViewHubWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'view_hub')
        self.doc = doc
        self._all_data     = []
        self._org_views    = []
        self._org_filtered = []

        self._rename_rows = ObservableCollection[ViewRow]()
        self._tmpl_rows   = ObservableCollection[ViewRow]()
        self.GridRename.ItemsSource   = self._rename_rows
        self.GridTemplate.ItemsSource = self._tmpl_rows

        try:
            self.CboMode.SelectedIndex = 0

            tpls = _vbm.get_view_templates(doc)
            tmpl_items = ObservableCollection[TmplItem]()
            for eid, n in tpls:
                tmpl_items.Add(TmplItem(eid, n))
            self.CboTemplate.ItemsSource   = tmpl_items
            self.CboTemplate.SelectedIndex = 0 if tpls else -1

            for label in _vorg.view_type_labels():
                self.OrgCboViewType.Items.Add(label)
            self.OrgCboViewType.SelectedIndex = self.OrgCboViewType.Items.Count - 1

            self.OrgRbFindReplace.IsChecked    = True
            self.OrgPnlFindReplace.Visibility  = _VIS
            self.OrgPnlPrefixSuffix.Visibility = _COL

            self._load_views()

            cfg = self.LoadConfig()
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        except Exception as e:
            forms.alert(u'View Hub init error:\n{}'.format(e), title=u'Error')

    # ── data loading ──────────────────────────────────────────────────────────

    def _load_views(self, filter_txt=u'', filter_txt_t=u''):
        self.SetLoading(True, u'Loading views...')
        try:
            self._all_data = _vbm.collect_views(self.doc)
            self._refresh_rename(filter_txt)
            self._refresh_template(filter_txt_t)
            self._org_views = _vorg.collect_views(self.doc)
            self._org_apply_filter()
        except Exception as e:
            forms.alert(u'Error loading views: {}'.format(e))
        finally:
            self.SetLoading(False)

    def _refresh_rename(self, filter_txt=u''):
        txt = (filter_txt or u'').strip().lower()
        self._rename_rows.Clear()
        for i, d in enumerate(self._all_data, 1):
            if txt and txt not in d['name'].lower():
                continue
            self._rename_rows.Add(ViewRow(d, i))
        self.TxtViewCount.Text = u'{} views'.format(len(list(self._rename_rows)))
        self._compute_preview()

    def _refresh_template(self, filter_txt=u''):
        txt = (filter_txt or u'').strip().lower()
        self._tmpl_rows.Clear()
        for i, d in enumerate(self._all_data, 1):
            if txt and txt not in d['name'].lower():
                continue
            self._tmpl_rows.Add(ViewRow(d, i))

    # ── tab 0: rename ─────────────────────────────────────────────────────────

    def Filter_Changed(self, sender, args):
        self._refresh_rename((self.TxtFilter.Text or u'').strip())

    def Mode_Changed(self, sender, args):
        idx = self.CboMode.SelectedIndex
        self.PanelFindReplace.Visibility  = _VIS if idx == 0 else _COL
        self.PanelPrefixSuffix.Visibility = _VIS if idx == 1 else _COL
        self.PanelCase.Visibility         = _VIS if idx == 2 else _COL
        self._compute_preview()

    def Preview_Changed(self, sender, args):
        self._compute_preview()

    def _get_rename_params(self):
        idx = self.CboMode.SelectedIndex
        if idx == 0:
            return u'find_replace', {
                'find':           self.TxtFind.Text or u'',
                'replace':        self.TxtReplace.Text or u'',
                'case_sensitive': self.ChkCaseSensitive.IsChecked == True,
            }
        if idx == 1:
            return u'prefix_suffix', {
                'prefix': self.TxtPrefix.Text or u'',
                'suffix': self.TxtSuffix.Text or u'',
            }
        if self.RbUpper.IsChecked:      cm = u'upper'
        elif self.RbLower.IsChecked:    cm = u'lower'
        elif self.RbSentence.IsChecked: cm = u'sentence'
        else:                           cm = u'title'
        return u'case', {'case_mode': cm}

    def _compute_preview(self):
        try:
            mode, params = self._get_rename_params()
            for row in self._rename_rows:
                new_name = _vbm.compute_new_name(row.Name, mode, params)
                row.NewName   = new_name
                row.HasChange = (new_name != row.Name)
            self.GridRename.Items.Refresh()
        except Exception:
            pass

    def Rename_Click(self, sender, args):
        selected = list(self.GridRename.SelectedItems)
        if not selected:
            forms.alert(u'Select at least one view in the grid.')
            return
        mode, params = self._get_rename_params()
        renames = []
        for row in selected:
            new_name = _vbm.compute_new_name(row.Name, mode, params)
            if new_name and new_name != row.Name:
                renames.append((row._view.Id, new_name))
        if not renames:
            forms.alert(u'No names would change with the current settings.')
            return
        if not forms.alert(u'Rename {} view(s)?'.format(len(renames)), yes=True, no=True):
            return
        self.SetLoading(True, u'Renaming views...')
        try:
            ok, failed = _vbm.rename_views(self.doc, renames)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Rename failed: {}'.format(e))
            return
        self.SetLoading(False)
        forms.alert(u'Renamed: {}  |  Failed: {}'.format(ok, failed), title=u'Rename Views')
        self._load_views((self.TxtFilter.Text or u'').strip(),
                         (self.TxtFilterT.Text or u'').strip())

    # ── tab 1: templates ──────────────────────────────────────────────────────

    def FilterT_Changed(self, sender, args):
        self._refresh_template((self.TxtFilterT.Text or u'').strip())

    def ApplyTemplate_Click(self, sender, args):
        selected = list(self.GridTemplate.SelectedItems)
        if not selected:
            forms.alert(u'Select at least one view.')
            return
        tmpl_item = self.CboTemplate.SelectedItem
        if not tmpl_item:
            forms.alert(u'Select a view template.')
            return
        if not forms.alert(u"Apply '{}' to {} view(s)?".format(tmpl_item.Name, len(selected)),
                           yes=True, no=True):
            return
        ids = [r._view.Id for r in selected]
        self.SetLoading(True, u'Applying template...')
        try:
            ok, failed = _vbm.apply_view_template(self.doc, ids, tmpl_item.Id)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Apply failed: {}'.format(e))
            return
        self.SetLoading(False)
        forms.alert(u'Applied: {}  |  Failed: {}'.format(ok, failed), title=u'Apply Template')
        self._load_views((self.TxtFilter.Text or u'').strip(),
                         (self.TxtFilterT.Text or u'').strip())

    def RemoveTemplate_Click(self, sender, args):
        selected = list(self.GridTemplate.SelectedItems)
        if not selected:
            forms.alert(u'Select at least one view.')
            return
        if not forms.alert(u'Remove view template from {} view(s)?'.format(len(selected)),
                           yes=True, no=True):
            return
        from Autodesk.Revit import DB
        ids = [r._view.Id for r in selected]
        self.SetLoading(True, u'Removing templates...')
        try:
            ok, failed = _vbm.apply_view_template(self.doc, ids, DB.ElementId.InvalidElementId)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Remove failed: {}'.format(e))
            return
        self.SetLoading(False)
        forms.alert(u'Cleared: {}  |  Failed: {}'.format(ok, failed), title=u'Remove Template')
        self._load_views((self.TxtFilter.Text or u'').strip(),
                         (self.TxtFilterT.Text or u'').strip())

    # ── tab 2: organise ───────────────────────────────────────────────────────

    def _org_apply_filter(self):
        vtype         = self.OrgCboViewType.SelectedItem or u'All types'
        unplaced_only = bool(self.OrgChkUnplacedOnly.IsChecked)
        self._org_filtered = [v for v in self._org_views
                              if (vtype == u'All types' or v['vtype'] == vtype)
                              and (not unplaced_only or not v['placed'])]
        self._org_rebuild_preview()

    def _org_rebuild_preview(self):
        mode    = u'find_replace' if self.OrgRbFindReplace.IsChecked else u'prefix_suffix'
        find    = self.OrgTxtFind.Text
        replace = self.OrgTxtReplace.Text
        prefix  = self.OrgTxtPrefix.Text
        suffix  = self.OrgTxtSuffix.Text

        pairs = _vorg.preview_rename(
            [v['name'] for v in self._org_filtered],
            mode, find, replace, prefix, suffix)

        rows = [OrgViewRow(self._org_filtered[i], new) for i, (old, new) in enumerate(pairs)]
        self.OrgGridViews.ItemsSource = rows

        placed   = sum(1 for v in self._org_filtered if v['placed'])
        unplaced = len(self._org_filtered) - placed
        self.OrgTxtSummary.Text = u'{} views  ·  {} placed  ·  {} unplaced'.format(
            len(self._org_views), placed, unplaced)
        self.OrgTxtStatus.Text = u'Showing {} views.'.format(len(self._org_filtered))

    def Org_ViewType_Changed(self, sender, args):
        self._org_apply_filter()

    def Org_Filter_Changed(self, sender, args):
        self._org_apply_filter()

    def Org_Mode_Changed(self, sender, args):
        is_fr = bool(self.OrgRbFindReplace.IsChecked)
        self.OrgPnlFindReplace.Visibility  = _VIS if is_fr else _COL
        self.OrgPnlPrefixSuffix.Visibility = _COL if is_fr else _VIS
        self._org_rebuild_preview()

    def Org_Rule_Changed(self, sender, args):
        self._org_rebuild_preview()

    def Org_Grid_SelectionChanged(self, sender, args):
        n = self.OrgGridViews.SelectedItems.Count
        self.OrgTxtStatus.Text = (
            u'{} view{} selected.'.format(n, u's' if n != 1 else u'')
            if n else u'Showing {} views.'.format(len(self._org_filtered)))

    def Org_SelectAll_Click(self, sender, args):
        self.OrgGridViews.SelectAll()

    def Org_RenameSelected_Click(self, sender, args):
        selected = list(self.OrgGridViews.SelectedItems)
        if not selected:
            self.OrgTxtStatus.Text = u'Select views to rename.'
            return
        pairs = [(row._rec['element'], row.NewName)
                 for row in selected if row.NewName and row.NewName != row.Name]
        if not pairs:
            self.OrgTxtStatus.Text = u'No name changes detected — check rename settings.'
            return
        self.SetLoading(True, u'Renaming views...')
        try:
            renamed, failed, errors = _vorg.rename_views(self.doc, pairs)
        finally:
            self.SetLoading(False)
        msg = u'Renamed {}. Failed: {}.'.format(renamed, failed)
        if errors:
            msg += u'  ' + u'; '.join(errors[:3])
        self.OrgTxtStatus.Text = msg
        self._org_views = _vorg.collect_views(self.doc)
        self._org_apply_filter()

    def Org_DeleteSelected_Click(self, sender, args):
        selected = list(self.OrgGridViews.SelectedItems)
        if not selected:
            self.OrgTxtStatus.Text = u'Select views to delete.'
            return
        try:
            if not forms.alert(u'Delete {} view(s)?'.format(len(selected)),
                               title=u'Confirm Delete', yes=True, no=True):
                return
        except Exception:
            pass
        ids = [row._rec['id'] for row in selected]
        self.SetLoading(True, u'Deleting views...')
        try:
            deleted, failed = _vorg.delete_views(self.doc, ids)
        finally:
            self.SetLoading(False)
        self.OrgTxtStatus.Text = u'Deleted {}. Failed: {}.'.format(deleted, failed)
        self._org_views = _vorg.collect_views(self.doc)
        self._org_apply_filter()

    def Org_DeleteUnplaced_Click(self, sender, args):
        unplaced = [v for v in self._org_views if not v['placed']]
        if not unplaced:
            self.OrgTxtStatus.Text = u'No unplaced views found.'
            return
        try:
            if not forms.alert(u'Delete {} unplaced view(s)?'.format(len(unplaced)),
                               title=u'Confirm Delete', yes=True, no=True):
                return
        except Exception:
            pass
        ids = [v['id'] for v in unplaced]
        self.SetLoading(True, u'Deleting unplaced views...')
        try:
            deleted, failed = _vorg.delete_views(self.doc, ids)
        finally:
            self.SetLoading(False)
        self.OrgTxtStatus.Text = u'Deleted {} unplaced views. Failed: {}.'.format(deleted, failed)
        self._org_views = _vorg.collect_views(self.doc)
        self._org_apply_filter()

    # ── shared ────────────────────────────────────────────────────────────────

    def Refresh_Click(self, sender, args):
        self._load_views((self.TxtFilter.Text or u'').strip(),
                         (self.TxtFilterT.Text or u'').strip())
