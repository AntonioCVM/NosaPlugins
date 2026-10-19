# -*- coding: utf-8 -*-
import datetime
import io
import json
import os
import re
import shutil
import sys
import tempfile
import traceback

import System
import System.Diagnostics
import System.Windows
import System.Windows.Controls
import System.Windows.Interop
from System import Array, Byte, TimeSpan
from System.IO import MemoryStream
from System.Collections.ObjectModel import ObservableCollection
from System.Windows import Thickness, FontWeights, Visibility, CornerRadius
from System.Windows.Controls import TreeViewItem, StackPanel, TextBlock, Orientation, Border, ContextMenu, MenuItem
from System.Windows.Input import Key, Keyboard, ModifierKeys
from System.Windows.Media import SolidColorBrush, Color
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
from System.Windows.Threading import DispatcherTimer, DispatcherPriority
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent
from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.bootstrap import load_module
from nosa_utils.export_io import ask_save_path, write_csv
from nosa_utils.telemetry import log_error, log_swallowed

_here = os.path.dirname(os.path.abspath(__file__))
_reader = load_module('clashviewer_reader', os.path.join(_here, 'clash_reader.py'))
_locator = load_module('clashviewer_locator', os.path.join(_here, 'clash_locator.py'))
_view = load_module('clashviewer_view', os.path.join(_here, 'clash_view.py'))
_review = load_module('clashviewer_review', os.path.join(_here, 'review_store.py'))
_check = load_module('clashviewer_check', os.path.join(_here, 'clash_check.py'))
_report = load_module('clashviewer_report', os.path.join(_here, 'report_html.py'))

_LOG = u'ClashViewer.ui'
_TITLE = u'NOSA — Clash Viewer'

_STATUS_RGB = {
    u'New': (0xFF, 0x5F, 0x00),
    u'Active': (0xD3, 0x2F, 0x2F),
    u'Reviewed': (0x19, 0x76, 0xD2),
    u'Approved': (0x2E, 0xAA, 0x4A),
    u'Resolved': (0x9E, 0x9E, 0x9E),
}
_GREEN, _RED, _AMBER, _GREY = (0x2E, 0xAA, 0x4A), (0xD3, 0x2F, 0x2F), (0xC7, 0x77, 0x00), (0x80, 0x80, 0x80)
_STATE_RGB = {
    _locator.FOUND_HOST: _GREEN, _locator.FOUND_LINK: _GREEN,
    _locator.NOT_FOUND: _RED,
    _locator.UNLOADED: _AMBER, _locator.MISMATCH: _AMBER,
    _locator.NOT_IN_REVIT: _GREY, _locator.NO_DATA: _GREY,
}
_ALL_TESTS = u'All tests'
_ALL_PEOPLE = u'Everyone'
_ALL_CATEGORIES = u'All categories'
_ALL_MODELS = u'All models'
_REVIEW_ALL, _REVIEW_OPEN, _REVIEW_DONE = u'All', u'Open', u'Done'
_UNASSIGNED = u'(unassigned)'


def _json_text(value):
    """JSON-safe text: IronPython 2.7 returns non-ASCII paths (a profile with an accent) json cannot encode."""
    try:
        json.dumps(value)
        return value
    except UnicodeDecodeError:
        return value.encode('utf-8')


def _brush(rgb):
    return SolidColorBrush(Color.FromRgb(rgb[0], rgb[1], rgb[2]))


def _text(text, bold=False, size=12.0, opacity=1.0, rgb=None, margin_right=6):
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = size
    tb.Opacity = opacity
    tb.Margin = Thickness(0, 0, margin_right, 0)
    tb.VerticalAlignment = System.Windows.VerticalAlignment.Center
    if bold:
        tb.FontWeight = FontWeights.SemiBold
    if rgb is not None:
        tb.Foreground = _brush(rgb)
    else:
        tb.SetResourceReference(TextBlock.ForegroundProperty, 'TextColor')
    return tb


def _tint(rgb, alpha):
    return SolidColorBrush(Color.FromArgb(alpha, rgb[0], rgb[1], rgb[2]))


def _tint_box(panel):
    box = Border()
    box.CornerRadius = CornerRadius(3)
    box.Padding = Thickness(4, 1, 6, 1)
    box.Child = panel
    return box


def _row(*children):
    panel = StackPanel()
    panel.Orientation = Orientation.Horizontal
    for child in children:
        panel.Children.Add(child)
    return panel


def _bitmap(data):
    stream = MemoryStream(Array[Byte](bytearray(data)))
    image = BitmapImage()
    image.BeginInit()
    image.CacheOption = BitmapCacheOption.OnLoad
    image.StreamSource = stream
    image.EndInit()
    image.Freeze()
    return image


def _item_category(item):
    return item.category or item.acad_class


def _item_model(item):
    return item.model_base


def _float(text, default):
    try:
        return float(text.replace(u',', u'.'))
    except (ValueError, AttributeError):
        return default


def _percent(value):
    try:
        return u'%.1f%%' % (float(value) * 100.0)
    except ValueError:
        return value


class _SummaryRow(object):
    def __init__(self, test, total, new, active, reviewed, approved, resolved, closed):
        self.Test = test
        self.Total = total
        self.New = new
        self.Active = active
        self.Reviewed = reviewed
        self.Approved = approved
        self.Resolved = resolved
        self.Closed = closed


class _Bridge(IExternalEventHandler):
    """Runs requests from the modeless window inside Revit's API context (ExternalEvent)."""

    def __init__(self):
        self._queue = []
        self._event = None

    def attach(self):
        self._event = ExternalEvent.Create(self)

    def detach(self):
        try:
            if self._event is not None:
                self._event.Dispose()
        except Exception:
            log_swallowed(_LOG, u'_Bridge.detach')
        self._event = None

    def request(self, kind, func, done):
        self._queue.append((kind, func, done))
        self._event.Raise()

    def GetName(self):
        return u'NOSA Clash Viewer'

    def Execute(self, uiapp):
        pending, self._queue = self._queue, []
        latest = {}
        for index, (kind, _, _) in enumerate(pending):
            if kind in (u'locate', u'show'):
                latest[kind] = index              # only the newest locate / show request matters
        for index, (kind, func, done) in enumerate(pending):
            if kind in latest and latest[kind] != index:
                continue
            result, error = None, None
            try:
                result = func(uiapp)
            except Exception as ex:
                error = ex
                log_error(u'ClashViewer', u'%s request failed: %s' % (kind, ex), traceback.format_exc())
            try:
                done(result, error)
            except Exception as ex:
                log_error(u'ClashViewer', u'%s callback failed: %s' % (kind, ex), traceback.format_exc())


class ClashViewerWindow(NOSAWindow):

    def __init__(self, doc=None, *args):
        NOSAWindow.__init__(self, os.path.join(_here, 'ui.xaml'), 'clash_viewer')
        self._is_loaded = False
        self.report = None
        self.current = None
        self.located = None
        self._visible = []
        self._clash_items = {}
        self._group_items = {}
        self._view = _view.ClashView()
        self._store = None
        self._shown = 0
        self._busy = False
        self._cancel = False
        self._checks = {}
        cfg = self.LoadConfig()
        self._model_map = cfg.get('model_map', {})

        self._bridge = _Bridge()
        self._bridge.attach()
        self._set_owner()

        self.ChkDarkMode.IsChecked = bool(self.dark_mode)
        self._restore_options(cfg)
        self._fill_review(cfg.get('review'))
        self._search_timer = DispatcherTimer()
        self._search_timer.Interval = TimeSpan.FromMilliseconds(300)
        self._search_timer.Tick += self._search_tick

        self.TreeClashes.SelectedItemChanged += self._tree_selected
        self.TreeClashes.MouseDoubleClick += self._tree_double_click
        self.TreeClashes.PreviewMouseRightButtonDown += self._tree_right_click
        self.TreeClashes.ContextMenu = ContextMenu()
        self.TreeClashes.ContextMenuOpening += self._tree_menu_opening
        self.TxtNote.LostFocus += self._note_lost_focus
        self.TxtSearch.TextChanged += self._search_changed
        for cbo in (self.CboTest, self.CboAssigned, self.CboCategory, self.CboModel, self.CboReview):
            cbo.SelectionChanged += self._filter_changed
        for chk in self._status_checks().values():
            chk.Click += self._filter_changed
        self.PreviewKeyDown += self._key_down
        self.Loaded += self._on_loaded
        self.Closing += self._on_closing
        self.Closed += self._on_closed
        self._reset_detail()
        self._is_loaded = True
        self._last_cfg = cfg

    # ------------------------------------------------------------------ setup

    def handle_input_key(self, sender, args):
        """pyRevit's WPFWindow closes on Esc; this window must stay open."""
        return

    def _set_owner(self):
        try:
            helper = System.Windows.Interop.WindowInteropHelper(self)
            helper.Owner = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle
        except Exception:
            log_swallowed(_LOG, u'_set_owner')

    def _status_checks(self):
        return {u'New': self.ChkNew, u'Active': self.ChkActive, u'Reviewed': self.ChkReviewed,
                u'Approved': self.ChkApproved, u'Resolved': self.ChkResolved}

    def _restore_options(self, cfg):
        wanted = cfg.get('statuses', [u'New', u'Active', u'Reviewed'])
        for name, chk in self._status_checks().items():
            chk.IsChecked = name in wanted
        self.ChkIsolate.IsChecked = cfg.get('isolate', True)
        self.ChkPermanent.IsChecked = cfg.get('permanent', False)
        self.ChkDim.IsChecked = cfg.get('dim_rest', False)
        self.ChkKeepCam.IsChecked = cfg.get('keep_camera', False)
        self.TxtMargin.Text = u'%g' % cfg.get('margin_m', 1.0)
        self.TxtCrop.Text = u'%g' % cfg.get('crop_m', 0.0)
        self.TxtColour1.Text = cfg.get('colour1', _view.DEFAULT_COLOUR_1)
        self.TxtColour2.Text = cfg.get('colour2', _view.DEFAULT_COLOUR_2)

    def _save_options(self):
        cfg = self.LoadConfig()
        cfg.update({
            'last_file': _json_text(self.report.path) if self.report else cfg.get('last_file', u''),
            'statuses': [n for n, c in self._status_checks().items() if c.IsChecked],
            'test': self._combo_value(self.CboTest, _ALL_TESTS),
            'assigned': self._combo_value(self.CboAssigned, _ALL_PEOPLE),
            'category': self._combo_value(self.CboCategory, _ALL_CATEGORIES),
            'model': self._combo_value(self.CboModel, _ALL_MODELS),
            'review': self._combo_value(self.CboReview, _REVIEW_ALL),
            'isolate': bool(self.ChkIsolate.IsChecked),
            'permanent': bool(self.ChkPermanent.IsChecked),
            'dim_rest': bool(self.ChkDim.IsChecked),
            'keep_camera': bool(self.ChkKeepCam.IsChecked),
            'margin_m': _float(self.TxtMargin.Text, 1.0),
            'crop_m': _float(self.TxtCrop.Text, 0.0),
            'colour1': self.TxtColour1.Text,
            'colour2': self.TxtColour2.Text,
            'model_map': self._model_map,
        })
        self.SaveConfig(cfg)

    def _on_loaded(self, sender, args):
        last = self._last_cfg.get('last_file')
        if last and os.path.isfile(last):
            self._load_path(last)

    def _on_closing(self, sender, args):
        self._cancel = True
        try:
            self._commit_note()
            self._save_options()
        except Exception:
            log_swallowed(_LOG, u'_on_closing')

    def _on_closed(self, sender, args):
        self._search_timer.Stop()
        self._bridge.detach()

    # ------------------------------------------------------------- loading

    def _pump(self):
        try:
            self.Dispatcher.Invoke(System.Action(lambda: None), DispatcherPriority.Background)
        except Exception:
            log_swallowed(_LOG, u'_pump')

    def Load_Click(self, sender, args):
        from Microsoft.Win32 import OpenFileDialog
        dialog = OpenFileDialog()
        dialog.Title = u'Open clash report'
        dialog.Filter = u'Excel workbooks (*.xlsm;*.xlsx)|*.xlsm;*.xlsx|All files (*.*)|*.*'
        last = self.LoadConfig().get('last_file')
        if last and os.path.isdir(os.path.dirname(last)):
            dialog.InitialDirectory = os.path.dirname(last)
        if dialog.ShowDialog():
            self._load_path(dialog.FileName)

    def _load_path(self, path):
        self.SetLoading(True, u'Reading %s…' % os.path.basename(path))
        self._pump()
        try:
            report = _reader.load_report(path)
        except _reader.ClashReaderError as ex:
            self.SetLoading(False)
            forms.alert(u'%s' % ex, title=_TITLE)
            return
        except Exception as ex:
            self.SetLoading(False)
            log_error(u'ClashViewer', u'load failed: %s' % ex, traceback.format_exc())
            forms.alert(u'The report could not be read:\n%s' % ex, title=_TITLE)
            return
        self.SetLoading(False)
        self.report = report
        self.current = None
        self._store = _review.ReviewStore.for_report(
            report.path, report.document_code, os.path.dirname(self._config_file))
        self._reset_detail()
        bits = [report.document_code]
        if report.revision:
            bits.append(u'revision %s (%s)' % (report.revision, report.revision_date))
        bits.append(u'%d clashes' % report.total)
        bits.append(os.path.basename(report.path))
        self.TxtFileInfo.Text = u'  ·  '.join(bits)
        self.TxtInfo.Text = (u'Report loaded. ' + u'; '.join(report.warnings)) if report.warnings \
            else u'Report loaded.'
        self._fill_summary()
        self._fill_filters()
        self._rebuild_tree()
        cfg = self.LoadConfig()
        cfg['last_file'] = _json_text(path)
        self.SaveConfig(cfg)

    def _fill_summary(self):
        rows = ObservableCollection[object]()
        for rec in self.report.summary:
            name = rec.get(u'test name', u'')
            if not name:
                continue
            closed = _percent(rec.get(u'% closed', u''))
            rows.Add(_SummaryRow(name, rec.get(u'total clashes', u''), rec.get(u'new', u''),
                                 rec.get(u'active', u''), rec.get(u'reviewed', u''),
                                 rec.get(u'approved', u''), rec.get(u'resolved', u''), closed))
        if rows.Count == 0:
            for t in self.report.tests:
                c = t.counts()
                rows.Add(_SummaryRow(t.name, len(t.clashes), c.get(u'New', 0), c.get(u'Active', 0),
                                     c.get(u'Reviewed', 0), c.get(u'Approved', 0),
                                     c.get(u'Resolved', 0), u'%.1f%%' % (t.pct_closed * 100.0)))
        self.GridSummary.ItemsSource = rows

    # ------------------------------------------------------------- filters

    @staticmethod
    def _combo_value(cbo, default):
        return cbo.SelectedItem if cbo.SelectedItem is not None else default

    def _fill_combo(self, cbo, first, values, remembered):
        self._is_loaded = False
        cbo.Items.Clear()
        cbo.Items.Add(first)
        for v in sorted(values, key=lambda s: s.lower()):
            cbo.Items.Add(v)
        index = 0
        for i in range(cbo.Items.Count):
            if cbo.Items[i] == remembered:
                index = i
        cbo.SelectedIndex = index
        self._is_loaded = True

    def _fill_filters(self):
        cfg = self.LoadConfig()
        tests, people, cats, models = set(), set(), set(), set()
        for t in self.report.tests:
            tests.add(t.name)
            for c in t.clashes:
                people.update(c.assignees)
                if not c.assignees:
                    people.add(_UNASSIGNED)
                for item in c.items:
                    if _item_category(item):
                        cats.add(_item_category(item))
                    if _item_model(item):
                        models.add(_item_model(item))
        self._fill_combo(self.CboTest, _ALL_TESTS, tests, cfg.get('test'))
        self._fill_combo(self.CboAssigned, _ALL_PEOPLE, people, cfg.get('assigned'))
        self._fill_combo(self.CboCategory, _ALL_CATEGORIES, cats, cfg.get('category'))
        self._fill_combo(self.CboModel, _ALL_MODELS, models, cfg.get('model'))

    def _matches(self, clash, f):
        if clash.status not in f['statuses']:
            return False
        if f['assigned'] != _ALL_PEOPLE:
            mine = clash.assignees or [_UNASSIGNED]
            if f['assigned'] not in mine:
                return False
        if f['category'] != _ALL_CATEGORIES and \
                f['category'] not in [_item_category(i) for i in clash.items]:
            return False
        if f['model'] != _ALL_MODELS and f['model'] not in [_item_model(i) for i in clash.items]:
            return False
        if f['review'] != _REVIEW_ALL and self._store is not None:
            done = self._store.is_done(clash.key)
            if (f['review'] == _REVIEW_DONE) != done:
                return False
        if f['text']:
            hay = u' '.join([clash.name, clash.group, clash.assigned] + [
                u' '.join([i.category, i.family, i.element_id_raw, i.acad_tag, i.acad_class,
                           i.unique_id, i.pnp_guid]) for i in clash.items]).lower()
            if f['text'] not in hay:
                return False
        return True

    def _filter_state(self):
        return {
            'statuses': [n for n, c in self._status_checks().items() if c.IsChecked],
            'test': self._combo_value(self.CboTest, _ALL_TESTS),
            'assigned': self._combo_value(self.CboAssigned, _ALL_PEOPLE),
            'category': self._combo_value(self.CboCategory, _ALL_CATEGORIES),
            'model': self._combo_value(self.CboModel, _ALL_MODELS),
            'review': self._combo_value(self.CboReview, _REVIEW_ALL),
            'text': (self.TxtSearch.Text or u'').strip().lower(),
        }

    def _filter_changed(self, sender, args):
        if self._is_loaded and self.report is not None:
            self._rebuild_tree()

    def _search_changed(self, sender, args):
        self._search_timer.Stop()
        self._search_timer.Start()

    def _search_tick(self, sender, args):
        self._search_timer.Stop()
        self._filter_changed(None, None)

    # ----------------------------------------------------------------- tree

    def _rebuild_tree(self):
        previous = self.current
        f = self._filter_state()
        self._visible = []
        self._clash_items = {}
        self._group_items = {}
        self.TreeClashes.Items.Clear()
        shown = 0
        for test in self.report.tests:
            if f['test'] != _ALL_TESTS and f['test'] != test.name:
                continue
            groups = {}
            order = []
            for c in test.clashes:
                if self._matches(c, f):
                    if c.group not in groups:
                        groups[c.group] = []
                        order.append(c.group)
                    groups[c.group].append(c)
            if not order:
                continue
            count = sum(len(groups[g]) for g in order)
            shown += count
            t_item = TreeViewItem()
            t_item.Tag = (u'test', [c for g in order for c in groups[g]])
            t_item.Header = _row(
                _text(test.name, bold=True),
                _text(u'%d' % count, opacity=0.65),
                _text(u'· %s · %s' % (test.test_type or u'-', test.tolerance or u'-'), size=10.5, opacity=0.5))
            for gname in order:
                g_item = TreeViewItem()
                g_item.Header = _row(_text(gname), _text(u'(%d)' % len(groups[gname]), opacity=0.6))
                g_item.Tag = (u'group', groups[gname])
                g_item.Items.Add(self._placeholder())
                g_item.Expanded += self._group_expanded
                t_item.Items.Add(g_item)
                for c in groups[gname]:
                    self._group_items[c.key] = (t_item, g_item)
                    self._visible.append(c)
            self.TreeClashes.Items.Add(t_item)
        self._shown = shown
        self._update_count()
        if previous is not None and previous.key in self._group_items:
            self._select_in_tree(previous)

    @staticmethod
    def _placeholder():
        item = TreeViewItem()
        item.Header = u'…'
        item.Tag = u'placeholder'
        return item

    def _group_expanded(self, sender, args):
        self._build_group(sender)

    def _build_group(self, g_item):
        tag = g_item.Tag
        if not isinstance(tag, tuple) or g_item.Items.Count != 1 or g_item.Items[0].Tag != u'placeholder':
            return
        g_item.Items.Clear()
        for c in tag[1]:
            item = TreeViewItem()
            who = c.assignees[0] if c.assignees else u''
            item.Header = _tint_box(_row(
                _text(u'●', rgb=_STATUS_RGB.get(c.status, _GREY), size=9, margin_right=5),
                _text(c.name, bold=True),
                _text(c.status, size=10.5, opacity=0.6),
                _text(who, size=10.5, opacity=0.5),
                _text(u'✎', size=11, rgb=_AMBER, margin_right=0)))
            item.Tag = c
            self._style_leaf(item)
            g_item.Items.Add(item)
            self._clash_items[c.key] = item

    # ----------------------------------------------------------------- done

    @staticmethod
    def _user_name():
        return os.getenv('USERNAME') or u''

    def _fill_review(self, remembered):
        self.CboReview.Items.Clear()
        for label in (_REVIEW_ALL, _REVIEW_OPEN, _REVIEW_DONE):
            self.CboReview.Items.Add(label)
        self.CboReview.SelectedIndex = max(0, [_REVIEW_ALL, _REVIEW_OPEN, _REVIEW_DONE].index(remembered)
                                           if remembered in (_REVIEW_ALL, _REVIEW_OPEN, _REVIEW_DONE) else 0)

    def _style_leaf(self, item):
        """Green wash when done, red wash while open; the bullet keeps the Navisworks status."""
        clash = item.Tag
        done = self._store is not None and self._store.is_done(clash.key)
        has_note = self._store is not None and bool(self._store.note(clash.key))
        box = item.Header
        kids = box.Child.Children
        box.Background = _tint(_GREEN, 0x38) if done else _tint(_RED, 0x1C)
        kids[0].Text = u'✓' if done else u'●'
        kids[0].Foreground = _brush(_GREEN if done else _STATUS_RGB.get(clash.status, _GREY))
        base = (1.0, 0.6, 0.5)
        for offset in range(3):
            kids[1 + offset].Opacity = base[offset] * (0.6 if done else 1.0)
        kids[4].Visibility = Visibility.Visible if has_note else Visibility.Collapsed

    def _update_count(self):
        done_total = 0
        if self._store is not None:
            done_total = sum(1 for c in self.report.all_clashes() if self._store.is_done(c.key))
        self.TxtCount.Text = u'SHOWING %d OF %d CLASHES  ·  %d DONE' % (
            self._shown, self.report.total, done_total)

    def _refresh_done_ui(self, clash):
        has_store = self._store is not None
        done = has_store and self._store.is_done(clash.key)
        self.ChkMarkDone.IsEnabled = has_store
        self.ChkMarkDone.IsChecked = done
        info = self._store.info(clash.key) if done else None
        self.TxtDoneInfo.Text = (u'Marked by %s on %s' % (info.get('by') or u'?', info.get('at') or u'?')
                                 if info else u'')
        self.TxtNote.IsEnabled = has_store
        self.TxtNote.Text = self._store.note(clash.key) if has_store else u''
        note = self._store.note_info(clash.key) if has_store else None
        self.TxtNoteInfo.Text = (u'Note by %s on %s' % (note.get('by') or u'?', note.get('at') or u'?')
                                 if note and note.get('text') else u'')
        self.BtnRecheck.IsEnabled = True
        self._show_check(self._checks.get(clash.key))

    def _commit_note(self):
        """Save the note box for the current clash when its text changed."""
        if self._store is None or self.current is None:
            return
        text = (self.TxtNote.Text or u'').strip()
        if text == self._store.note(self.current.key):
            return
        self._store.set_note(self.current.key, text, self._user_name())
        item = self._clash_items.get(self.current.key)
        if item is not None:
            self._style_leaf(item)
        note = self._store.note_info(self.current.key)
        self.TxtNoteInfo.Text = (u'Note by %s on %s' % (note.get('by') or u'?', note.get('at') or u'?')
                                 if note and note.get('text') else u'')
        self.TxtInfo.Text = self._store.message or u'Note saved.'

    def _note_lost_focus(self, sender, args):
        self._commit_note()

    def _show_check(self, result):
        if result is None:
            self.TxtCheck.Text = u'Not checked yet'
            self.TxtCheck.Foreground = _brush(_GREY)
            return
        self.TxtCheck.Text = result.text
        self.TxtCheck.Foreground = _brush({_check.STILL: _RED, _check.CLEARED: _GREEN}.get(result.verdict, _AMBER))

    def Recheck_Click(self, sender, args):
        clash = self.current
        if clash is None:
            return
        tolerance = _check.tolerance_mm(clash.test.tolerance)
        self.TxtCheck.Text = u'Checking…'
        self.TxtCheck.Foreground = _brush(_GREY)

        def op(uiapp):
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None:
                raise RuntimeError(u'Open a Revit project first.')
            located = _locator.Locator(uidoc.Document, self._model_map).locate_clash(clash)
            return located, _check.recheck(located, tolerance)

        def done(result, err):
            if err is not None:
                self.TxtCheck.Text = u'Could not check: %s' % err
                self.TxtCheck.Foreground = _brush(_AMBER)
                return
            located, outcome = result
            self._checks[clash.key] = outcome
            if clash is self.current:
                self._apply_located(located)
                self._show_check(outcome)

        self._bridge.request(u'check', op, done)

    def _set_many(self, clashes, done):
        if self._store is None or not clashes:
            return
        word = u'done' if done else u'open'
        answer = forms.alert(u'Mark %d clashes as %s?' % (len(clashes), word), title=_TITLE, yes=True, no=True)
        if not answer:
            return
        self._store.set_many([c.key for c in clashes], done, self._user_name())
        for c in clashes:
            item = self._clash_items.get(c.key)
            if item is not None:
                self._style_leaf(item)
        if self.current is not None:
            self._refresh_done_ui(self.current)
        self._update_count()
        self.TxtInfo.Text = self._store.message or u'%d clashes marked as %s.' % (len(clashes), word)
        for g_item_pair in set(self._group_items.get(c.key) for c in clashes):
            if g_item_pair is not None:
                self._build_group(g_item_pair[1])
                for child in list(g_item_pair[1].Items):
                    if isinstance(child.Tag, _reader.Clash):
                        self._style_leaf(child)

    def _tree_right_click(self, sender, args):
        node = args.OriginalSource
        while node is not None and not isinstance(node, TreeViewItem):
            try:
                node = System.Windows.Media.VisualTreeHelper.GetParent(node)
            except Exception:
                log_swallowed(_LOG, u'_tree_right_click')
                node = None
        if node is not None:
            node.IsSelected = True
            node.Focus()

    def _tree_menu_opening(self, sender, args):
        menu = self.TreeClashes.ContextMenu
        menu.Items.Clear()
        selected = self.TreeClashes.SelectedItem
        tag = selected.Tag if selected is not None else None
        if self._store is None or tag is None:
            args.Handled = True
            return

        def add(text, handler):
            entry = MenuItem()
            entry.Header = text
            entry.Click += lambda s_, a_: handler()
            menu.Items.Add(entry)

        if isinstance(tag, _reader.Clash):
            done = self._store.is_done(tag.key)
            add(u'Go to clash', lambda: self._goto(tag))
            add(u'Reopen' if done else u'Mark as done', lambda: self._set_done(tag, not done))
            add(u'Edit note…', lambda: self.TxtNote.Focus())
        elif isinstance(tag, tuple) and tag[0] in (u'group', u'test'):
            clashes = tag[1]
            add(u'Mark all %d as done' % len(clashes), lambda: self._set_many(clashes, True))
            add(u'Reopen all %d' % len(clashes), lambda: self._set_many(clashes, False))
        else:
            args.Handled = True

    def MarkDone_Click(self, sender, args):
        if self.current is not None:
            self._set_done(self.current, bool(self.ChkMarkDone.IsChecked))

    def _set_done(self, clash, done):
        if self._store is None:
            return
        self._store.set_done(clash.key, done, self._user_name())
        state = self._store.is_done(clash.key)
        item = self._clash_items.get(clash.key)
        if item is not None:
            self._style_leaf(item)
        if clash is self.current:
            self._refresh_done_ui(clash)
        self._update_count()
        message = self._store.message or u'%s marked as %s.' % (clash.name, u'done' if state else u'open')
        if self._combo_value(self.CboReview, _REVIEW_ALL) != _REVIEW_ALL:
            message += u' The list updates when you change a filter.'
        self.TxtInfo.Text = message

    def _select_in_tree(self, clash):
        pair = self._group_items.get(clash.key)
        if pair is None:
            return
        t_item, g_item = pair
        t_item.IsExpanded = True
        self._build_group(g_item)
        g_item.IsExpanded = True
        item = self._clash_items.get(clash.key)
        if item is not None:
            item.IsSelected = True
            item.BringIntoView()

    def _tree_selected(self, sender, args):
        item = self.TreeClashes.SelectedItem
        if item is not None and isinstance(item.Tag, _reader.Clash):
            self._select_clash(item.Tag)

    def _tree_double_click(self, sender, args):
        item = self.TreeClashes.SelectedItem
        if item is not None and isinstance(item.Tag, _reader.Clash):
            self._goto(item.Tag)

    def _key_down(self, sender, args):
        ctrl = (Keyboard.Modifiers & ModifierKeys.Control) == ModifierKeys.Control
        if ctrl and args.Key == Key.Right:
            self.Next_Click(None, None)
            args.Handled = True
        elif ctrl and args.Key == Key.Left:
            self.Prev_Click(None, None)
            args.Handled = True
        elif ctrl and args.Key == Key.D and self.current is not None and self._store is not None:
            self._set_done(self.current, not self._store.is_done(self.current.key))
            args.Handled = True
        elif args.Key == Key.Return and self.current is not None \
                and not isinstance(args.OriginalSource, System.Windows.Controls.TextBox):
            self._goto(self.current)
            args.Handled = True

    # --------------------------------------------------------------- detail

    def _reset_detail(self):
        self.ImgClash.Source = None
        self.TxtNoImage.Visibility = Visibility.Visible
        self.TxtDetTitle.Text = u'Select a clash'
        self.TxtDetSub.Text = u''
        for tb in (self.TxtDetStatus, self.TxtDetAssigned, self.TxtDetDate, self.TxtDetPoint,
                   self.TxtItem1Info, self.TxtItem1State, self.TxtItem2Info, self.TxtItem2State,
                   self.TxtDetWarn):
            tb.Text = u''
        self.TxtItem1Head.Text = u'ITEM 1'
        self.TxtItem2Head.Text = u'ITEM 2'
        self.ChkMarkDone.IsEnabled = False
        self.ChkMarkDone.IsChecked = False
        self.TxtDoneInfo.Text = u''
        self.TxtNote.Text = u''
        self.TxtNote.IsEnabled = False
        self.TxtNoteInfo.Text = u''
        self.BtnRecheck.IsEnabled = False
        self._show_check(None)

    @staticmethod
    def _item_info(item):
        if item.is_empty:
            return u'No data in the report.'
        lines = []
        if item.is_plant:
            lines.append(u'AutoCAD Plant: %s' % u' · '.join(
                x for x in (item.acad_class, item.acad_size and u'size %s' % item.acad_size) if x))
            if item.acad_tag:
                lines.append(u'Tag: %s' % item.acad_tag)
            if item.pnp_guid:
                lines.append(u'PnPGuid: %s' % item.pnp_guid)
        else:
            lines.append(u'%s / %s' % (item.category or u'-', item.family or u'-'))
            if item.element_id_raw:
                lines.append(u'Element Id: %s' % item.element_id_raw)
            if item.unique_id:
                lines.append(u'UniqueId: %s' % item.unique_id)
        if item.model_base:
            lines.append(u'Model: %s' % item.model_base)
        return u'\n'.join(lines)

    def _select_clash(self, clash):
        self._commit_note()
        self.current = clash
        self.located = None
        self.TxtDetTitle.Text = clash.name
        self.TxtDetSub.Text = u'%s  ›  %s' % (clash.test.name, clash.group)
        self.TxtDetStatus.Text = u'● %s' % clash.status
        self.TxtDetStatus.Foreground = _brush(_STATUS_RGB.get(clash.status, _GREY))
        self.TxtDetAssigned.Text = u' & '.join(clash.assignees) or u'-'
        self.TxtDetDate.Text = clash.date_approved or u'-'
        pt = clash.point_mm
        self.TxtDetPoint.Text = u'x %.0f   y %.0f   z %.0f' % pt if pt else u'-'
        self.TxtItem1Head.Text = u'ITEM 1 — %s' % clash.item1.label
        self.TxtItem2Head.Text = u'ITEM 2 — %s' % clash.item2.label
        self.TxtItem1Info.Text = self._item_info(clash.item1)
        self.TxtItem2Info.Text = self._item_info(clash.item2)
        for tb in (self.TxtItem1State, self.TxtItem2State):
            tb.Text = u'Checking the model…'
            tb.Foreground = _brush(_GREY)
        self.TxtDetWarn.Text = u''
        self._refresh_done_ui(clash)
        try:
            data = self.report.get_image_bytes(clash)
            self.ImgClash.Source = _bitmap(data) if data else None
        except Exception:
            log_swallowed(_LOG, u'_select_clash.image')
            self.ImgClash.Source = None
        self.TxtNoImage.Visibility = Visibility.Collapsed if self.ImgClash.Source is not None \
            else Visibility.Visible
        self._bridge.request(u'locate', lambda uiapp: self._locate_op(uiapp, clash),
                             lambda result, err: self._located_done(clash, result, err))

    def _locate_op(self, uiapp, clash):
        uidoc = uiapp.ActiveUIDocument
        if uidoc is None:
            raise RuntimeError(u'Open a Revit project first.')
        return _locator.Locator(uidoc.Document, self._model_map).locate_clash(clash)

    def _located_done(self, clash, result, err):
        if clash is not self.current:
            return
        if err is not None or result is None:
            for tb in (self.TxtItem1State, self.TxtItem2State):
                tb.Text = u'Revit could not be queried (%s).' % (err,)
                tb.Foreground = _brush(_AMBER)
            return
        self._apply_located(result)

    def _apply_located(self, located):
        self.located = located
        for tb, li in ((self.TxtItem1State, located.first), (self.TxtItem2State, located.second)):
            tb.Text = li.text
            tb.Foreground = _brush(_STATE_RGB.get(li.status, _GREY))
        self.TxtDetWarn.Text = u'\n'.join(located.warnings)

    # -------------------------------------------------------------- actions

    def _options(self):
        opts = _view.ViewOptions()
        opts.isolate = bool(self.ChkIsolate.IsChecked)
        opts.permanent = bool(self.ChkPermanent.IsChecked)
        opts.dim_rest = bool(self.ChkDim.IsChecked)
        opts.keep_camera = bool(self.ChkKeepCam.IsChecked)
        opts.margin_mm = max(_float(self.TxtMargin.Text, 1.0), 0.0) * 1000.0
        opts.crop_radius_mm = max(_float(self.TxtCrop.Text, 0.0), 0.0) * 1000.0
        opts.colour1 = self.TxtColour1.Text
        opts.colour2 = self.TxtColour2.Text
        return opts

    def _goto(self, clash):
        opts = self._options()
        self.TxtInfo.Text = u'Going to %s…' % clash.name

        def op(uiapp):
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None:
                raise RuntimeError(u'Open a Revit project first.')
            located = _locator.Locator(uidoc.Document, self._model_map).locate_clash(clash)
            return located, self._view.show(uidoc, located, opts)

        def done(result, err):
            if err is not None:
                self.TxtInfo.Text = u'The clash could not be shown: %s' % err
                return
            located, message = result
            if clash is self.current:
                self._apply_located(located)
            self.TxtInfo.Text = message

        self._bridge.request(u'show', op, done)

    def Goto_Click(self, sender, args):
        if self.current is None:
            self.TxtInfo.Text = u'Select a clash first.'
            return
        self._goto(self.current)

    def _step(self, delta):
        if not self._visible:
            return
        try:
            index = self._visible.index(self.current) + delta
        except ValueError:
            index = 0 if delta > 0 else len(self._visible) - 1
        index = max(0, min(len(self._visible) - 1, index))
        clash = self._visible[index]
        self._select_in_tree(clash)
        self._goto(clash)

    def Next_Click(self, sender, args):
        self._step(1)

    def Prev_Click(self, sender, args):
        self._step(-1)

    def Reset_Click(self, sender, args):
        def op(uiapp):
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None:
                raise RuntimeError(u'Open a Revit project first.')
            return self._view.reset(uidoc)

        def done(result, err):
            self.TxtInfo.Text = result if err is None else u'The view could not be reset: %s' % err

        self._bridge.request(u'reset', op, done)

    def Export_Click(self, sender, args):
        if not self._visible:
            self.TxtInfo.Text = u'There is nothing to export: the list is empty.'
            return
        path = ask_save_path(u'clash_list', 'csv')
        if not path:
            return
        clashes = list(self._visible)
        self.TxtInfo.Text = u'Exporting %d clashes…' % len(clashes)

        def op(uiapp):
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None:
                raise RuntimeError(u'Open a Revit project first.')
            locator = _locator.Locator(uidoc.Document, self._model_map)
            headers = [u'Test', u'Group', u'Clash', u'Status', u'Assigned to', u'Date approved',
                       u'X (mm)', u'Y (mm)', u'Z (mm)', u'Located',
                       u'Item 1 model', u'Item 1 category', u'Item 1 family', u'Item 1 Element Id',
                       u'Item 1 tag', u'Item 1 state',
                       u'Item 2 model', u'Item 2 category', u'Item 2 family', u'Item 2 Element Id',
                       u'Item 2 tag', u'Item 2 state', u'Done', u'Done by', u'Done on', u'Note']
            rows = []
            for c in clashes:
                lc = locator.locate_clash(c)
                pt = c.point_mm or (u'', u'', u'')
                row = [c.test.name, c.group, c.name, c.status, c.assigned, c.date_approved,
                       pt[0], pt[1], pt[2], lc.state_text]
                for item, li in ((c.item1, lc.first), (c.item2, lc.second)):
                    row.extend([item.model_base, _item_category(item), item.family,
                                item.element_id_raw, item.acad_tag, li.text])
                mark = self._store.info(c.key) if self._store is not None else None
                row.extend([u'Yes' if mark else u'', mark.get('by', u'') if mark else u'',
                            mark.get('at', u'') if mark else u'',
                            self._store.note(c.key) if self._store is not None else u''])
                rows.append(row)
            write_csv(path, headers, rows)
            return len(rows)

        def done(result, err):
            if err is not None:
                self.TxtInfo.Text = u'The list could not be exported: %s' % err
            else:
                self.TxtInfo.Text = u'Exported %d clashes to %s' % (result, path)

        self._bridge.request(u'export', op, done)

    # --------------------------------------------------------------- report

    def CancelBusy_Click(self, sender, args):
        self._cancel = True
        self.TxtStatus.Text = u'Cancelling…'

    def _report_entry(self, clash, located, outcome, after):
        def item_dict(n, item, li):
            kind = {_locator.FOUND_HOST: u'ok', _locator.FOUND_LINK: u'ok', _locator.NOT_FOUND: u'bad',
                    _locator.UNLOADED: u'warn', _locator.MISMATCH: u'warn'}.get(li.status, u'none')
            return {u'title': u'ITEM %d — %s' % (n, item.label), u'info': self._item_info(item).split(u'\n'),
                    u'state': li.text, u'kind': kind}
        mark = self._store.info(clash.key) if self._store is not None else None
        note = self._store.note_info(clash.key) if self._store is not None else None
        pt = clash.point_mm
        return {
            u'test': clash.test.name, u'group': clash.group, u'name': clash.name, u'status': clash.status,
            u'assigned': u' & '.join(clash.assignees),
            u'point': (u'x %.0f  y %.0f  z %.0f mm' % pt) if pt else u'',
            u'before': self.report.get_image_bytes(clash), u'after': after,
            u'items': [item_dict(1, clash.item1, located.first), item_dict(2, clash.item2, located.second)],
            u'done': bool(mark), u'done_by': (mark or {}).get('by', u''), u'done_at': (mark or {}).get('at', u''),
            u'note': (note or {}).get('text', u''), u'note_by': (note or {}).get('by', u''),
            u'note_at': (note or {}).get('at', u''),
            u'check_kind': outcome.verdict if outcome is not None else u'',
            u'check_text': outcome.text if outcome is not None else u'',
        }

    def _report_op(self, uiapp, clashes, opts, meta, path):
        """Show, photograph and re-check every clash, then write the HTML; runs inside Revit's API context."""
        uidoc = uiapp.ActiveUIDocument
        if uidoc is None:
            raise RuntimeError(u'Open a Revit project first.')
        doc = uidoc.Document
        count = len(clashes)
        locator = _locator.Locator(doc, self._model_map)
        folder = tempfile.mkdtemp(prefix=u'nosa_clash_')
        entries = []
        try:
            for index, clash in enumerate(clashes):
                if self._cancel:
                    break
                self.SetProgress(index, count, u'Clash %d of %d: %s' % (index + 1, count, clash.name))
                located = locator.locate_clash(clash)
                after = None
                if self._view.region(located, opts) is not None:
                    self._view.show(uidoc, located, opts)
                    png = self._view.export_image(doc, folder)
                    if png:
                        with open(png, 'rb') as handle:
                            after = handle.read()
                outcome = _check.recheck(located, _check.tolerance_mm(clash.test.tolerance))
                self._checks[clash.key] = outcome
                entries.append(self._report_entry(clash, located, outcome, after))
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        if entries:
            meta[u'scope'] = u'%d of %d clashes in the current list' % (len(entries), count)
            with io.open(path, 'w', encoding='utf-8') as out:
                out.write(_report.build_report(meta, entries))
        return len(entries), self._cancel

    def Report_Click(self, sender, args):
        if self._busy:
            return
        if not self._visible:
            self.TxtInfo.Text = u'There is nothing to report: the list is empty.'
            return
        self._commit_note()
        clashes = list(self._visible)
        count = len(clashes)
        question = (u'Create the report for the %d clashes in the current list?\n\n'
                    u'Each clash is shown in the clash view, photographed from Revit and re-checked '
                    u'(about 2 seconds each, roughly %d min in total). You can cancel at any time and '
                    u'the model is not changed.' % (count, max(1, int(count * 2 / 60.0 + 0.5))))
        if not forms.alert(question, title=_TITLE, yes=True, no=True):
            return
        path = ask_save_path(u'clash_report', 'html')
        if not path:
            return
        opts = self._options()
        opts.quiet = True
        meta = {
            u'title': u'Clash report', u'document_code': self.report.document_code,
            u'revision': self.report.revision or u'-', u'revision_date': self.report.revision_date,
            u'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), u'user': self._user_name(),
            u'scope': u'%d clashes (current list)' % count,
        }
        self._busy, self._cancel = True, False
        self.BtnCancelBusy.Visibility = Visibility.Visible
        self.SetLoading(True, u'Preparing the report…')
        self._pump()

        def op(uiapp):
            return self._report_op(uiapp, clashes, opts, meta, path)

        def done(result, err):
            self._busy = False
            self.BtnCancelBusy.Visibility = Visibility.Collapsed
            self.SetLoading(False)
            if err is not None:
                self.TxtInfo.Text = u'The report could not be created: %s' % err
                return
            written, cancelled = result
            if not written:
                self.TxtInfo.Text = u'The report was cancelled before any clash was added.'
                return
            self.TxtInfo.Text = u'Report with %d clashes saved to %s%s' % (
                written, path, u' (cancelled early)' if cancelled else u'')
            try:
                os.startfile(path)
            except Exception:
                log_swallowed(_LOG, u'Report.open')

        self._bridge.request(u'report', op, done)
