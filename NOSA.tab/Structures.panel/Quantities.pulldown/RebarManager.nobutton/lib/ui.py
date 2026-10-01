# -*- coding: utf-8 -*-
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.bootstrap import load_module
_logic = load_module('rebarmanager_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))

from nosa_utils.base_window import NOSAWindow
from Autodesk.Revit import DB
from pyrevit import forms
from System.Collections.ObjectModel import ObservableCollection
import System.Windows


class ScheduleRow(object):
    def __init__(self, g):
        self.Mark       = g['mark']
        self.DiamLabel  = g['diameter_label']
        self.Quantity   = str(g['quantity'])
        self.Shape      = g['shape']
        self.ShapeDesc  = g['shape_desc']
        self.TotalLenM  = u'{:.2f}'.format(g['total_len_m'])
        self.MassKg     = u'{:.2f}'.format(g['mass_kg'])
        self.Levels     = g['levels']
        self.Hosts      = g['hosts']


class MarkRow(object):
    def __init__(self, g, dupe_marks):
        self.Selected    = False
        self.Mark        = g['mark']
        self.Diameter    = str(g['diameter'])
        self.Quantity    = str(g['quantity'])
        self.Shape       = g['shape']
        self.Levels      = g['levels']
        self.DupeWarning = u'⚠ DUPE' if g['mark'] in dupe_marks else u''


class RebarManagerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'rebar_manager')
        self.doc = doc

        self._bars        = []
        self._groups      = {}
        self._dupe_marks  = {}
        self._sched_rows  = ObservableCollection[ScheduleRow]()
        self._mark_rows   = ObservableCollection[MarkRow]()
        self.GridSchedule.ItemsSource = self._sched_rows
        self.GridMarks.ItemsSource    = self._mark_rows

        try:
            cfg = self.LoadConfig()
            self.ApplyTheme(cfg.get('dark_mode', False))
            self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)
            self.TxtProjectNo.Text = cfg.get('project_no', u'')
            self.TxtRevision.Text  = cfg.get('revision', u'P01')
            self._show_tab('Schedule')
        except Exception as e:
            from pyrevit import forms
            forms.alert(u'Rebar Manager init error:\n{}'.format(e), title='Error')

    # ------------------------------------------------------------------
    def _load_bars(self):
        self.SetLoading(True, u'Collecting rebar...')
        try:
            self._bars   = _logic.collect_rebar(self.doc)
            self._groups = _logic.group_by_mark(self._bars)
        finally:
            self.SetLoading(False)

    def _populate_schedule(self):
        self._sched_rows.Clear()
        for g in sorted(self._groups.values(), key=lambda x: x['mark']):
            self._sched_rows.Add(ScheduleRow(g))
        total_mass = sum(g['mass_kg'] for g in self._groups.values())
        self.TxtScheduleStatus.Text = (
            u'{} bar marks  ·  {} bars total  ·  {:.2f} kg total steel'.format(
                len(self._groups),
                sum(g['quantity'] for g in self._groups.values()),
                total_mass))

    def _populate_marks(self):
        self._dupe_marks = _logic.detect_duplicate_marks(self._bars)
        self._mark_rows.Clear()
        for g in sorted(self._groups.values(), key=lambda x: x['mark']):
            self._mark_rows.Add(MarkRow(g, self._dupe_marks))
        if self._dupe_marks:
            self.PanelDuplicates.Visibility = System.Windows.Visibility.Visible
            msgs = [u'⚠ Bar mark "{}" has multiple diameters: {}'.format(
                        m, u', '.join(u'Ø{}mm'.format(d) for d in sorted(ds)))
                    for m, ds in sorted(self._dupe_marks.items())]
            self.TxtDuplicates.Text = u'\n'.join(msgs)
        else:
            self.PanelDuplicates.Visibility = System.Windows.Visibility.Collapsed
        self.TxtMarksStatus.Text = u'{} unique marks · {} duplicate conflicts'.format(
            len(self._groups), len(self._dupe_marks))

    # ------------------------------------------------------------------
    def _show_tab(self, tab):
        from System.Windows import Visibility
        import System.Windows.Media as WM
        from System.Windows.Media import Brushes
        panels = {'Schedule': self.PanelSchedule, 'Marks': self.PanelMarks}
        btns   = {'Schedule': self.BtnTabSchedule, 'Marks': self.BtnTabMarks}
        for k, p in panels.items():
            p.Visibility = Visibility.Visible if k == tab else Visibility.Collapsed
        for k, b in btns.items():
            if k == tab:
                b.Background = WM.SolidColorBrush(WM.Color.FromRgb(255, 95, 0))
                b.Foreground = Brushes.White
            else:
                b.Background = Brushes.Transparent
                b.Foreground = WM.SolidColorBrush(WM.Color.FromRgb(51, 51, 51))

    # ------------------------------------------------------------------
    # Event handlers
    def Tab_Click(self, sender, args):
        tag = str(sender.Tag)
        self._show_tab(tag)

    def Load_Click(self, sender, args):
        try:
            self._load_bars()
            self._populate_schedule()
            self.LogLine(u'Loaded {} rebar elements.'.format(len(self._bars)))
            if not self._bars:
                self.LogLine(u'No rebar found — check model has rebar elements.')
        except Exception as e:
            self.LogLine(u'Error loading rebar: {}'.format(e))

    def ExportExcel_Click(self, sender, args):
        if not self._groups:
            self.LogLine(u'Load rebar first.')
            return
        path = forms.save_file(
            file_ext='xlsx',
            default_name=u'{} NOSA RC ZZZ L S 5500 {} RC Schedule'.format(
                self.TxtProjectNo.Text or u'00000',
                self.TxtRevision.Text  or u'P01'))
        if not path:
            return
        self.SetLoading(True, u'Exporting Excel...')
        try:
            ok, err = _logic.export_bs8666_excel(
                self._groups, path,
                self.TxtProjectNo.Text or u'',
                self.TxtRevision.Text  or u'P01')
            if ok:
                self.LogLine(u'Exported: {}'.format(path))
                cfg = self.LoadConfig()
                cfg.update({'project_no': self.TxtProjectNo.Text,
                            'revision':   self.TxtRevision.Text})
                self.SaveConfig(cfg)
            else:
                self.LogLine(u'Export error: {}'.format(err))
        finally:
            self.SetLoading(False)

    def LoadMarks_Click(self, sender, args):
        self._load_bars()
        self._populate_marks()
        self.LogLine(u'Refreshed: {} bars.'.format(len(self._bars)))

    def DetectDupes_Click(self, sender, args):
        if not self._bars:
            self._load_bars()
        self._populate_marks()

    def Renumber_Click(self, sender, args):
        selected_marks = set(r.Mark for r in self._mark_rows if r.Selected)
        if not selected_marks:
            self.LogLine(u'Select bar marks to renumber.')
            return
        prefix = self.TxtMarkPrefix.Text or u'S'
        try:
            start = int(self.TxtMarkStart.Text or u'1')
        except Exception:
            start = 1
        # Filter bars for selected marks only
        bars_sel = [b for b in self._bars if b['mark'] in selected_marks]
        with DB.Transaction(self.doc, u'NOSA — Rebar Renumber') as t:
            t.Start()
            changed, mapping = _logic.renumber_marks(self.doc, bars_sel, prefix, start)
            t.Commit()
        self.LogLine(u'Renumbered {} bars. New marks: {}'.format(
            changed,
            u', '.join(u'{}→{}'.format(k, v) for k, v in sorted(mapping.items())[:5])))
        self._load_bars()
        self._populate_marks()

    def Close_Click(self, sender, args):
        self.Close()

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
