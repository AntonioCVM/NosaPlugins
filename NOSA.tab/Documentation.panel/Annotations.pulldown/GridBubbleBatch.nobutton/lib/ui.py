# -*- coding: utf-8 -*-
import os
import sys

from Autodesk.Revit import DB
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

from nosa_utils.bootstrap import load_module
_logic = load_module('gridbubblebatch_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class ViewItem(object):
    def __init__(self, view):
        self.View = view
        self.Name = u'{} ({})'.format(view.Name, str(view.ViewType).split('.')[-1])
        self.IsChecked = False


class GridBubbleBatchWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'grid_bubble_batch')
        self.doc = doc
        self._items = ObservableCollection[ViewItem]()
        self.ListViews.ItemsSource = self._items
        self._load_views()

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    def _load_views(self):
        self._items.Clear()
        for v in _logic.get_plan_views(self.doc):
            self._items.Add(ViewItem(v))
        self.TxtViewCount.Text = u'{} plan views'.format(self._items.Count)

    def SelectAll_Click(self, sender, args):
        for item in self._items:
            item.IsChecked = True

    def ClearAll_Click(self, sender, args):
        for item in self._items:
            item.IsChecked = False

    def _selected_views(self):
        return [i.View for i in self._items if i.IsChecked]

    def Apply_Click(self, sender, args):
        views = self._selected_views()
        if not views:
            forms.alert(u'Select at least one plan view.')
            return

        if self.RbShow.IsChecked:
            action = 'show'
        elif self.RbHide.IsChecked:
            action = 'hide'
        else:
            action = 'standardise'

        both = self.ChkBothEnds.IsChecked == True
        self.SetLoading(True, u'Updating grid bubbles…')
        try:
            result = _logic.apply_bubble_action(self.doc, views, action, both)
            self.TxtStatusResult.Text = (
                u'Updated {} bubble ends across {} views ({} skipped, {} failed).'.format(
                    result['updated'], result['views'], result['skipped'], result['failed']))
        except Exception as e:
            forms.alert(u'Error:\n{}'.format(e))
        finally:
            self.SetLoading(False)

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
