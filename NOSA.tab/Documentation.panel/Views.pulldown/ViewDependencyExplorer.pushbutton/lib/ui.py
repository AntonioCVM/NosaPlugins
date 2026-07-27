# -*- coding: utf-8 -*-
import imp
import os
import sys

from System.Collections.ObjectModel import ObservableCollection

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('viewdep_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))

_TYPE_ICONS = {
    'Template':      u'T',
    'Filter':        u'F',
    'Sheet':         u'S',
    'Revision':      u'R',
    'Dependent':     u'D',
}


class ViewItem(object):
    def __init__(self, d):
        self.ViewName = d.get('name', u'')
        self.ViewType = d.get('type', u'')
        self._id      = d.get('id', 0)

    @property
    def DisplayName(self):
        return u'[{}]  {}'.format(self.ViewType, self.ViewName)


class DepRow(object):
    def __init__(self, dep_type, name, detail):
        self.DepType = dep_type
        self.Name    = name
        self.Detail  = detail


class ViewDependencyWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'view_dependency_explorer')
        self.doc    = doc
        self._views = []
        self._rows  = ObservableCollection[object]()

        self.DepGrid.ItemsSource = self._rows

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

        self._load_views()

    def _load_views(self):
        self.ViewList.Items.Clear()
        self._views = _logic.get_all_views(self.doc)
        for vi in self._views:
            self.ViewList.Items.Add(
                u'[{}]  {}'.format(vi['type'], vi['name']))
        self.TxtResult.Text = u'{} views available.'.format(len(self._views))

    # ── handlers ──────────────────────────────────────────────────────────────

    def Analyse_Click(self, sender, args):
        idx = self.ViewList.SelectedIndex
        if idx < 0 or idx >= len(self._views):
            from pyrevit import forms
            forms.alert(u'Select a view first.', title=u'View Dependency Explorer')
            return
        vi = self._views[idx]
        self.SetLoading(True, u'Analysing dependencies…')
        try:
            data = _logic.analyse_view(self.doc, vi['id'])
        except Exception as e:
            self.SetLoading(False)
            from pyrevit import forms
            forms.alert(u'Error:\n{}'.format(e), title=u'View Dependency Explorer')
            return

        self._rows.Clear()

        # Template
        if data['template']:
            self._rows.Add(DepRow(u'Template', data['template']['name'],
                                  u'ID {}'.format(data['template']['id'])))
        else:
            self._rows.Add(DepRow(u'Template', u'(none — no template applied)', u''))

        # Filters
        for f in data['filters']:
            vis = u'Visible' if f['visible'] else u'Hidden'
            self._rows.Add(DepRow(u'Filter', f['name'], vis))
        if not data['filters']:
            self._rows.Add(DepRow(u'Filter', u'(no filters applied)', u''))

        # Sheets
        for sh in data['sheets']:
            self._rows.Add(DepRow(u'Sheet', u'{} — {}'.format(sh['number'], sh['name']), u''))
        if not data['sheets']:
            self._rows.Add(DepRow(u'Sheet', u'(not placed on any sheet)', u''))

        # Revisions
        for rv in data['revisions']:
            detail = u'{} · {}'.format(rv['date'], rv['sheet']) if rv['date'] else rv['sheet']
            self._rows.Add(DepRow(u'Revision', rv['description'] or rv['sequence'], detail))
        if not data['revisions']:
            self._rows.Add(DepRow(u'Revision', u'(no revisions found on hosting sheets)', u''))

        # Dependent views
        for dv in data['dependent_views']:
            self._rows.Add(DepRow(u'Dependent', dv['name'], u'ID {}'.format(dv['id'])))
        if not data['dependent_views']:
            self._rows.Add(DepRow(u'Dependent', u'(no dependent views)', u''))

        self.SetLoading(False)

        n_tmpl  = 1 if data['template'] else 0
        n_filt  = len(data['filters'])
        n_sheet = len(data['sheets'])
        n_rev   = len(data['revisions'])
        n_dep   = len(data['dependent_views'])
        self.TxtResult.Text = (
            u'{} — {} template · {} filter(s) · {} sheet(s) · '
            u'{} revision(s) · {} dependent view(s)'.format(
                vi['name'], n_tmpl, n_filt, n_sheet, n_rev, n_dep))

    def Close_Click(self, sender, args):
        self.SaveConfig({'dark_mode': bool(self.ChkDarkMode.IsChecked)})
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
