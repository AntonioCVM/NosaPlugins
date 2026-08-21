# -*- coding: utf-8 -*-
import imp
import os
import sys

from System.Collections.ObjectModel import ObservableCollection

from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value

_logic = imp.load_source('scheduleimpact_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))


class ImpactRow(object):
    def __init__(self, r):
        self.ScheduleName = r.get('schedule_name', u'')
        self.FieldCount   = u'{}'.format(r.get('field_count', 0))
        self.SheetCount   = u'{}'.format(r.get('sheet_count', 0))
        self.Sheets       = u', '.join(
            u'{} — {}'.format(s[0], s[1]) for s in r.get('sheets', []))
        self.ScheduleId   = r.get('schedule_id', 0)


class CatItem(object):
    def __init__(self, name, cat):
        self.Name     = name
        self._cat     = cat

    @property
    def CategoryId(self):
        try:
            return get_id_value(self._cat.Id)
        except Exception:
            return -1


class ScheduleImpactWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'schedule_impact')
        self.doc   = doc
        self._rows = ObservableCollection[object]()
        self._cats = []

        self.ImpactGrid.ItemsSource = self._rows

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

        self._load_categories()

    def _load_categories(self):
        self.CboCategory.Items.Clear()
        self._cats = _logic.get_schedulable_categories(self.doc)
        for name, cat in self._cats:
            self.CboCategory.Items.Add(name)
        if self._cats:
            self.CboCategory.SelectedIndex = 0
        self.TxtResult.Text = u'{} schedulable categories found.'.format(len(self._cats))

    # ── handlers ──────────────────────────────────────────────────────────────

    def Analyse_Click(self, sender, args):
        idx = self.CboCategory.SelectedIndex
        if idx < 0 or idx >= len(self._cats):
            forms.alert(u'Select a category first.', title=u'Schedule Impact')
            return
        _, cat = self._cats[idx]
        self.SetLoading(True, u'Analysing schedules…')
        try:
            records = _logic.analyse(self.doc, get_id_value(cat.Id))
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error:\n{}'.format(e), title=u'Schedule Impact')
            return
        self._all_rows = [ImpactRow(r) for r in records]
        self._apply_search()
        self.SetLoading(False)
        total_sheets = sum(r.get('sheet_count', 0) for r in records)
        self.TxtResult.Text = u'{} schedule{} found, placed on {} sheet{}.'.format(
            len(records), u's' if len(records) != 1 else u'',
            total_sheets, u's' if total_sheets != 1 else u'')

    def _apply_search(self):
        try:
            text = (self.TxtSearch.Text or u'').strip().lower()
        except Exception:
            text = u''
        self._rows.Clear()
        for row in getattr(self, '_all_rows', []):
            if text and text not in row.ScheduleName.lower() \
                    and text not in row.Sheets.lower():
                continue
            self._rows.Add(row)

    def Search_Changed(self, sender, args):
        self._apply_search()

    def ExportCsv_Click(self, sender, args):
        rows = list(self._rows)
        if not rows:
            forms.alert(u'Run an analysis first.', title=u'Schedule Impact')
            return
        try:
            from nosa_utils.export_io import save_csv
            path = save_csv(
                [u'Schedule', u'Fields', u'Sheet count', u'Sheets'],
                [[r.ScheduleName, r.FieldCount, r.SheetCount, r.Sheets] for r in rows],
                default_name=u'schedule_impact')
            if path:
                self.TxtResult.Text = u'Exported to: {}'.format(path)
        except Exception as e:
            forms.alert(u'Export failed:\n{}'.format(e), title=u'Schedule Impact')

    def Grid_DoubleClick(self, sender, args):
        row = self.ImpactGrid.SelectedItem
        if row is None or not getattr(row, 'ScheduleId', 0):
            return
        try:
            from pyrevit import revit
            from nosa_utils.revit_helpers import element_id_from_int
            view = self.doc.GetElement(element_id_from_int(row.ScheduleId))
            if view is not None:
                revit.uidoc.RequestViewChange(view)
                self.TxtResult.Text = u'Opening schedule "{}"…'.format(row.ScheduleName)
        except Exception as e:
            self.TxtResult.Text = u'Could not open schedule: {}'.format(e)

    def Close_Click(self, sender, args):
        self.SaveConfig({'dark_mode': bool(self.ChkDarkMode.IsChecked)})
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
