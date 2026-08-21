# -*- coding: utf-8 -*-
import imp
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('linkmanager_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))

_lcm = None


def _lcm_logic():
    """Lazy-load LinkChangeMonitor logic (lives under Structures/Coordination)."""
    global _lcm
    if _lcm is None:
        ext_root = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..', '..'))
        for suffix in ('nobutton', 'pushbutton'):
            path = os.path.join(ext_root, 'NOSA.tab', 'Structures.panel',
                                'Coordination.pulldown',
                                'LinkChangeMonitor.{}'.format(suffix),
                                'lib', 'logic.py')
            if os.path.isfile(path):
                _lcm = imp.load_source('linkmanager_lcm_logic', path)
                break
        if _lcm is None:
            raise ImportError(u'LinkChangeMonitor logic not found.')
    return _lcm


class _LinkRow(object):
    def __init__(self, rec):
        self.LinkName = rec['name']
        self.Kind     = rec['kind']
        self.Status   = rec['status']
        self.LinkPath = rec['path']
        self._rec     = rec


class LinkManagerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'link_manager')
        self.doc = doc
        self._data = []

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._load()

    def _load(self):
        self._data = _logic.collect_all(self.doc)
        self._rows = [_LinkRow(r) for r in self._data]
        self._apply_search()
        rvt     = sum(1 for r in self._data if r['kind'] == u'RVT Link')
        cad     = sum(1 for r in self._data if u'CAD' in r['kind'])
        missing = sum(1 for r in self._data if r['status'] == u'Missing')
        try:
            self.TxtSummary.Text = u'{} RVT · {} CAD · {} missing'.format(rvt, cad, missing)
        except Exception:
            pass
        try:
            self.TxtStatus.Text = u'{} links found.'.format(len(self._data))
        except Exception:
            pass

    def _apply_search(self):
        try:
            text = (self.TxtSearch.Text or u'').strip().lower()
        except Exception:
            text = u''
        rows = getattr(self, '_rows', [])
        if text:
            rows = [r for r in rows
                    if text in r.LinkName.lower()
                    or text in r.Kind.lower()
                    or text in r.Status.lower()
                    or text in r.LinkPath.lower()]
        self.GridLinks.ItemsSource = rows

    def Search_Changed(self, sender, args):
        self._apply_search()

    def _selected_rows(self):
        return list(self.GridLinks.SelectedItems)

    def Reload_Click(self, sender, args):
        rows = self._selected_rows()
        if not rows:
            self.TxtStatus.Text = u'Select links to reload.'
            return
        self.SetLoading(True, u'Reloading…')
        ok = fail = 0
        try:
            for row in rows:
                if row._rec['kind'] != u'RVT Link':
                    continue
                try:
                    _logic.reload_link(self.doc, row._rec['element'])
                    ok += 1
                except Exception as ex:
                    fail += 1
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Reloaded {}. Failed: {}.'.format(ok, fail)
        self._load()

    def Unload_Click(self, sender, args):
        rows = self._selected_rows()
        if not rows:
            self.TxtStatus.Text = u'Select links to unload.'
            return
        self.SetLoading(True, u'Unloading…')
        ok = fail = 0
        try:
            for row in rows:
                if row._rec['kind'] != u'RVT Link':
                    continue
                try:
                    _logic.unload_link(self.doc, row._rec['element'])
                    ok += 1
                except Exception as ex:
                    fail += 1
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Unloaded {}. Failed: {}.'.format(ok, fail)
        self._load()

    def Remove_Click(self, sender, args):
        rows = self._selected_rows()
        if not rows:
            self.TxtStatus.Text = u'Select links to remove.'
            return
        try:
            from pyrevit import forms as _forms
            if not _forms.alert(
                    u'Remove {} link(s) from the model?'.format(len(rows)),
                    title=u'Confirm Remove', yes=True, no=True):
                return
        except Exception:
            pass
        ok = fail = 0
        self.SetLoading(True, u'Removing…')
        try:
            for row in rows:
                try:
                    _logic.remove_link(self.doc, row._rec['id'])
                    ok += 1
                except Exception:
                    fail += 1
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Removed {}. Failed: {}.'.format(ok, fail)
        self._load()

    def ReloadAllMissing_Click(self, sender, args):
        missing = [r for r in self._data if r['status'] == u'Missing' and r['kind'] == u'RVT Link']
        if not missing:
            self.TxtStatus.Text = u'No missing RVT links found.'
            return
        ok = fail = 0
        self.SetLoading(True, u'Reloading missing links…')
        try:
            for rec in missing:
                try:
                    _logic.reload_link(self.doc, rec['element'])
                    ok += 1
                except Exception:
                    fail += 1
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Reload attempted on {} missing links. OK: {}  Failed: {}.'.format(
            len(missing), ok, fail)
        self._load()

    def Refresh_Click(self, sender, args):
        self._load()

    def Snapshot_Click(self, sender, args):
        try:
            lcm = _lcm_logic()
            links = lcm.get_links(self.doc)
        except Exception as e:
            self.TxtStatus.Text = u'Change monitor unavailable: {}'.format(e)
            return
        if not links:
            self.TxtStatus.Text = u'No loaded RVT link instances to snapshot.'
            return
        self.SetLoading(True, u'Taking snapshots…')
        ok = fail = 0
        try:
            for link in links:
                try:
                    lcm.take_snapshot(self.doc, link)
                    ok += 1
                except Exception:
                    fail += 1
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = (u'Baseline snapshot saved for {} link(s). '
                               u'Failed: {}.'.format(ok, fail))

    def Changes_Click(self, sender, args):
        try:
            lcm = _lcm_logic()
            links = lcm.get_links(self.doc)
        except Exception as e:
            self.TxtStatus.Text = u'Change monitor unavailable: {}'.format(e)
            return
        if not links:
            self.TxtStatus.Text = u'No loaded RVT link instances to compare.'
            return
        self.SetLoading(True, u'Comparing against snapshots…')
        lines = []
        total = 0
        try:
            for link in links:
                try:
                    name = link.Name
                except Exception:
                    name = u'(link)'
                try:
                    changes = lcm.compare_link(self.doc, link)
                except Exception as e:
                    changes = [type('X', (object,), {
                        'category': u'Error', 'detail': u'{}'.format(e),
                        'severity': 'red'})()]
                lines.append(u'')
                lines.append(u'=== {} — {} change(s) ==='.format(name, len(changes)))
                for c in changes:
                    total += 1
                    lines.append(u'  [{}] {}: {}'.format(
                        c.severity.upper(), c.category, c.detail))
        finally:
            self.SetLoading(False)

        from pyrevit import forms as _forms
        report = u'\n'.join(lines).strip()
        if len(lines) <= 28:
            _forms.alert(report or u'No changes detected.',
                         title=u'Link Changes')
        else:
            import tempfile, io as _io, datetime as _dt
            path = os.path.join(
                tempfile.gettempdir(),
                'nosa_link_changes_{}.txt'.format(_dt.datetime.now().strftime('%H%M%S')))
            with _io.open(path, 'w', encoding='utf-8-sig') as f:
                f.write(report)
            try:
                os.startfile(path)
            except Exception:
                _forms.alert(u'Report saved to:\n{}'.format(path),
                             title=u'Link Changes')
        self.TxtStatus.Text = u'{} change(s) across {} link(s).'.format(total, len(links))

    def Close_Click(self, sender, args):
        self.Close()
