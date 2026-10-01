# -*- coding: utf-8 -*-
import os
import sys

from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

_logic = None


def _get_logic():
    global _logic
    if _logic is None:
        from nosa_utils.bootstrap import load_module
        _logic = load_module(
            'linkchangemonitor_logic',
            os.path.join(os.path.dirname(__file__), 'logic.py'))
    return _logic


from nosa_utils.base_window import NOSAWindow


class LinkItem(object):
    def __init__(self, link, link_doc):
        self.Link = link
        self.Label = u'{} — {}'.format(link.Name, link_doc.Title)


class ChangeRow(object):
    def __init__(self, item):
        self.category = item.category
        self.detail = item.detail
        self.severity = item.severity.upper()


class LinkChangeMonitorWindow(NOSAWindow):

    def __init__(self, doc):
        try:
            xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
            NOSAWindow.__init__(self, xaml, 'link_change_monitor')
            self.doc = doc
            self._links = []
            self._changes = ObservableCollection[ChangeRow]()
            self.GridChanges.ItemsSource = self._changes
            self._load_links()
            cfg = self.LoadConfig()
            self.ApplyTheme(cfg.get('dark_mode', False))
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
        except Exception as e:
            self._init_ok = False
            forms.alert(u'Link Change Monitor init error:\n{}'.format(e), title=u'Error')
            raise

    def _load_links(self):
        self.CboLink.Items.Clear()
        self._links = _get_logic().get_links(self.doc)
        for link, link_doc in self._links:
            self.CboLink.Items.Add(LinkItem(link, link_doc))
        if self.CboLink.Items.Count:
            self.CboLink.SelectedIndex = 0

    def _selected_link(self):
        item = self.CboLink.SelectedItem
        return item.Link if item else None

    def Snapshot_Click(self, sender, args):
        link = self._selected_link()
        if link is None:
            forms.alert(u'No linked model selected.')
            return
        self.SetLoading(True, u'Taking snapshot…')
        try:
            path, payload = _get_logic().take_snapshot(self.doc, link)
            self.TxtStatusLine.Text = u'Snapshot saved for "{}".'.format(payload['doc_title'])
        except Exception as e:
            forms.alert(u'Error:\n{}'.format(e))
        finally:
            self.SetLoading(False)

    def Compare_Click(self, sender, args):
        link = self._selected_link()
        if link is None:
            forms.alert(u'No linked model selected.')
            return
        self.SetLoading(True, u'Comparing…')
        try:
            changes = _get_logic().compare_link(self.doc, link)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error:\n{}'.format(e))
            return
        self.SetLoading(False)
        self._changes.Clear()
        for c in changes:
            self._changes.Add(ChangeRow(c))
        issues = sum(1 for c in changes if c.severity != 'green')
        self.TxtStatusLine.Text = u'{} change(s) detected.'.format(issues)

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
