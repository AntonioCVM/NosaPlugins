# -*- coding: utf-8 -*-
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
import System.Windows

_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
           'August', 'September', 'October', 'November', 'December']


def _read_version():
    """Read version from version.txt at extension root; date = file mtime."""
    ver, date = u'?', u''
    try:
        vfile = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..', 'version.txt'))
        with open(vfile, 'r') as f:
            ver = f.read().strip() or u'?'
        import datetime
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(vfile))
        date = u'{} {}'.format(_MONTHS[mt.month - 1], mt.year)
    except Exception:
        pass
    return ver, date


EXTENSION_VERSION, EXTENSION_DATE = _read_version()


class PanelItem(object):
    def __init__(self, name, count):
        self.Name     = name
        self.CountStr = '{} plugin{}'.format(count, 's' if count != 1 else '')


class EnvItem(object):
    def __init__(self, label, value):
        self.Label = label
        self.Value = value


class HealthItem(object):
    def __init__(self, ok, label, detail):
        self.Icon      = 'OK' if ok else 'X'
        self.IconColor = '#22AA44' if ok else '#CC3333'
        self.Label     = label
        self.Detail    = detail


class PluginItem(object):
    def __init__(self, panel, name, version=u''):
        self.Panel   = panel
        self.Name    = name
        self.Version = u'v{}'.format(version) if version else u''


class UsageItem(object):
    def __init__(self, rank, name, count):
        self.Rank  = str(rank)
        self.Name  = name
        self.Count = str(count)


class NOSADashboardWindow(NOSAWindow):

    _PANELS_ORDER = ['NOSA', 'Foundations', 'Structures', 'Documentation', 'Data']

    def __init__(self):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'nosa_dashboard')

        self._root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

        self._panels = {
            'BtnOverview':    self.PanelOverview,
            'BtnEnvironment': self.PanelEnvironment,
            'BtnHealth':      self.PanelHealth,
            'BtnPlugins':     self.PanelPlugins,
            'BtnAbout':       self.PanelAbout,
            'BtnUsage':       self.PanelUsage,
            'BtnProtocol':    self.PanelProtocol,
            'BtnStart':       self.PanelStart,
            'BtnErrors':      self.PanelErrors,
        }

        self._populate()
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    # ------------------------------------------------------------------
    # Data gathering
    # ------------------------------------------------------------------

    def _nosa_tab(self):
        return os.path.join(self._root, 'NOSA.tab')

    @staticmethod
    def _count_recursive(path):
        """Count all .pushbutton directories inside a panel/pulldown path."""
        count = 0
        try:
            for item in os.listdir(path):
                full = os.path.join(path, item)
                if not os.path.isdir(full):
                    continue
                if item.endswith('.pushbutton'):
                    count += 1
                elif item.endswith('.pulldown'):
                    count += NOSADashboardWindow._count_recursive(full)
        except Exception:
            pass
        return count

    @staticmethod
    def _collect_plugins(path, panel_label, result):
        """Recursively collect PluginItem entries from panel/pulldown path."""
        try:
            for item in sorted(os.listdir(path)):
                full = os.path.join(path, item)
                if not os.path.isdir(full):
                    continue
                if item.endswith('.pushbutton'):
                    name = item.replace('.pushbutton', '')
                    version = u''
                    _script = os.path.join(full, 'script.py')
                    if os.path.isfile(_script):
                        try:
                            with open(_script, 'r') as _sf:
                                for _ln in _sf:
                                    _ln = _ln.strip()
                                    if _ln.startswith('__version__'):
                                        version = _ln.split('=', 1)[1].strip().strip('"\'')
                                        break
                        except Exception:
                            pass
                    result.append(PluginItem(panel_label, name, version))
                elif item.endswith('.pulldown'):
                    sub = item.replace('.pulldown', '')
                    NOSADashboardWindow._collect_plugins(
                        full, u'{} / {}'.format(panel_label, sub), result)
        except Exception:
            pass

    def _get_panels_info(self):
        tab = self._nosa_tab()
        result = []
        for d in sorted(os.listdir(tab)):
            panel_path = os.path.join(tab, d)
            if not os.path.isdir(panel_path):
                continue
            if not (d.endswith('.panel') or d.endswith('.Panel')):
                continue
            count = self._count_recursive(panel_path)
            if count > 0:
                label = d.replace('.panel', '').replace('.Panel', '')
                result.append((label, count))
        order_map = {n: i for i, n in enumerate(self._PANELS_ORDER)}
        result.sort(key=lambda p: order_map.get(p[0], 999))
        return result

    def _scan_bad_db_imports(self):
        """Find plugin files using `from pyrevit import DB` (multi-Revit crash risk)."""
        hits = []
        tab = self._nosa_tab()
        for dirpath, _, files in os.walk(tab):
            for fn in files:
                if not fn.endswith('.py'):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, 'r') as f:
                        for i, line in enumerate(f, 1):
                            s = line.strip()
                            if s == 'from pyrevit import DB' or s.startswith('from pyrevit import DB,'):
                                rel = os.path.relpath(path, self._root).replace('\\', '/')
                                hits.append('{}:{}'.format(rel, i))
                except Exception:
                    pass
        return hits

    def _get_all_plugins(self):
        tab = self._nosa_tab()
        result = []
        for d in sorted(os.listdir(tab)):
            panel_path = os.path.join(tab, d)
            if not os.path.isdir(panel_path):
                continue
            if not (d.endswith('.panel') or d.endswith('.Panel')):
                continue
            label = d.replace('.panel', '').replace('.Panel', '')
            self._collect_plugins(panel_path, label, result)
        return result

    def _get_lib_modules(self):
        lib_utils = os.path.join(self._root, 'lib', 'nosa_utils')
        if not os.path.exists(lib_utils):
            return []
        return sorted(f.replace('.py', '') for f in os.listdir(lib_utils)
                      if f.endswith('.py') and not f.startswith('__'))

    def _health_checks(self):
        root = self._root
        rows = []
        rows.append(('Extension folder',
                     os.path.isdir(root), root))
        rows.append(('Shared library',
                     os.path.isdir(os.path.join(root, 'lib')), 'lib/'))
        rows.append(('nosa_utils package',
                     os.path.isfile(os.path.join(root, 'lib', 'nosa_utils', '__init__.py')),
                     'lib/nosa_utils/__init__.py'))
        ok_imp = False
        imp_detail = ''
        try:
            import nosa_utils  # noqa
            ok_imp = True
            imp_detail = 'imported OK'
        except Exception as e:
            imp_detail = str(e)
        rows.append(('nosa_utils import', ok_imp, imp_detail))
        rows.append(('Theme module',
                     os.path.isfile(os.path.join(root, 'lib', 'nosa_utils', 'theme.py')),
                     'lib/nosa_utils/theme.py'))
        rows.append(('Base window',
                     os.path.isfile(os.path.join(root, 'lib', 'nosa_utils', 'base_window.py')),
                     'lib/nosa_utils/base_window.py'))
        bad_db = self._scan_bad_db_imports()
        rows.append(('No pyrevit DB imports',
                     len(bad_db) == 0,
                     'None found' if not bad_db else '; '.join(bad_db[:5]) +
                     (' (+{} more)'.format(len(bad_db) - 5) if len(bad_db) > 5 else '')))

        # DMU checks (D2)
        _dmu_file = os.path.join(self._root, 'NOSA.tab', 'Foundations.panel',
                                  'PileMaster.pushbutton', 'lib', 'logic_dmu.py')
        rows.append(('DMU — logic file',
                     os.path.isfile(_dmu_file),
                     'Foundations/PileMaster/lib/logic_dmu.py'))
        _dmu_active = False
        _dmu_detail = 'live_coords.json not found (open PileMaster first)'
        try:
            import json as _json
            _cfg = os.path.join(os.getenv('APPDATA', ''),
                                'pyRevit', 'Extensions', 'NOSA.extension',
                                'NOSA_Configs', 'live_coords.json')
            if os.path.exists(_cfg):
                with open(_cfg, 'r') as _f:
                    _dmu_active = _json.load(_f).get('active', False)
                _dmu_detail = 'active={} (live_coords.json)'.format(_dmu_active)
        except Exception:
            _dmu_detail = 'error reading live_coords.json'
        rows.append(('DMU — live coords',
                     True,  # not a failure if inactive; just informational
                     _dmu_detail))

        # Git status (informational)
        rows.append(('Git', True, self._git_info()))
        return rows

    def _git_info(self):
        if not os.path.isdir(os.path.join(self._root, '.git')):
            return u'not a git repository'
        try:
            from System.Diagnostics import Process, ProcessStartInfo
            psi = ProcessStartInfo()
            psi.FileName  = 'git'
            psi.Arguments = '-C "{}" log -1 "--format=%h (%cd)" --date=short'.format(self._root)
            psi.UseShellExecute = False
            psi.RedirectStandardOutput = True
            psi.CreateNoWindow = True
            p = Process.Start(psi)
            if not p.WaitForExit(3000):
                try:
                    p.Kill()
                except Exception:
                    pass
                return u'git timed out'
            out = p.StandardOutput.ReadToEnd().strip()
            return u'last commit: {}'.format(out) if out else u'git returned nothing'
        except Exception as e:
            return u'git unavailable ({})'.format(e)

    def _revit_version(self):
        try:
            from pyrevit import HOST_APP
            v = HOST_APP.app.VersionNumber
            return str(v) if v else 'Unknown'
        except Exception:
            return 'Unknown'

    def _pyrevit_version(self):
        try:
            import pyrevit
            return getattr(pyrevit, '__version__', 'Unknown')
        except Exception:
            return 'Unknown'

    # ------------------------------------------------------------------
    # Populate
    # ------------------------------------------------------------------

    def _populate(self):
        tab = self._nosa_tab()
        panels = self._get_panels_info()
        total_plugins = sum(c for _, c in panels)
        modules = self._get_lib_modules()

        self.TxtVersion.Text  = 'v{}'.format(EXTENSION_VERSION)
        self.TxtBundleDate.Text = 'Bundle date: {}  ·  {} panels  ·  {} plugins'.format(
            EXTENSION_DATE, len(panels), total_plugins)
        self.TxtPluginCount.Text = str(total_plugins)
        self.TxtPanelCount.Text  = str(len(panels))
        self.TxtModuleCount.Text = str(len(modules))

        from System.Collections.ObjectModel import ObservableCollection
        panel_items = ObservableCollection[PanelItem]()
        for name, cnt in panels:
            panel_items.Add(PanelItem(name, cnt))
        self.ListPanels.ItemsSource = panel_items

        env_items = ObservableCollection[EnvItem]()
        env_items.Add(EnvItem('Extension version', EXTENSION_VERSION))
        env_items.Add(EnvItem('Bundle date',       EXTENSION_DATE))
        env_items.Add(EnvItem('Revit',             self._revit_version()))
        env_items.Add(EnvItem('pyRevit',           self._pyrevit_version()))
        env_items.Add(EnvItem('Python',            sys.version.split()[0]))
        env_items.Add(EnvItem('Extension root',    self._root))
        env_items.Add(EnvItem('Library path',      os.path.join(self._root, 'lib')))
        self.ListEnv.ItemsSource = env_items

        health_items = ObservableCollection[HealthItem]()
        for name, ok, detail in self._health_checks():
            health_items.Add(HealthItem(ok, name, detail))
        self.ListHealth.ItemsSource = health_items

        plugin_items = ObservableCollection[PluginItem]()
        for pi in self._get_all_plugins():
            plugin_items.Add(pi)
        self.ListAllPlugins.ItemsSource = plugin_items

    # ------------------------------------------------------------------
    # Usage
    # ------------------------------------------------------------------

    def _populate_usage(self):
        try:
            from nosa_utils import usage as _usage
            top = _usage.get_top(25)
        except Exception:
            top = []

        from System.Collections.ObjectModel import ObservableCollection
        items = ObservableCollection[UsageItem]()
        if top:
            for i, (key, count) in enumerate(top, 1):
                items.Add(UsageItem(i, key, count))
        self.ListUsage.ItemsSource = items

    def RefreshUsage_Click(self, sender, args):
        self._populate_usage()

    # ------------------------------------------------------------------
    # Error log
    # ------------------------------------------------------------------

    def _log_path(self):
        try:
            from nosa_utils.telemetry import get_log_path
            return get_log_path()
        except Exception:
            return os.path.join(os.getenv('APPDATA', ''),
                                'pyRevit', 'Extensions', 'NOSA.extension',
                                'NOSA_Configs', 'logs', 'nosa_errors.log')

    def _populate_errors(self, tail=200):
        path = self._log_path()
        if not os.path.isfile(path):
            self.TxtErrorLog.Text = u'No errors logged. The log file will appear at:\n{}'.format(path)
            self.TxtErrorCount.Text = u''
            return
        try:
            with open(path, 'r') as f:
                lines = f.readlines()
            n_errors = sum(1 for ln in lines if 'ERROR:' in ln)
            shown = lines[-tail:]
            self.TxtErrorLog.Text = u''.join(shown) or u'Log file is empty.'
            self.TxtErrorCount.Text = u'{} error entries · showing last {} lines · {}'.format(
                n_errors, min(tail, len(lines)), path)
            try:
                self.TxtErrorLog.ScrollToEnd()
            except Exception:
                pass
        except Exception as e:
            self.TxtErrorLog.Text = u'Could not read log: {}'.format(e)
            self.TxtErrorCount.Text = u''

    def RefreshErrors_Click(self, sender, args):
        self._populate_errors()

    def ClearErrors_Click(self, sender, args):
        try:
            from pyrevit import forms
            if not forms.alert(u'Clear the NOSA error log? This cannot be undone.',
                               yes=True, no=True):
                return
        except Exception:
            return
        try:
            path = self._log_path()
            if os.path.isfile(path):
                with open(path, 'w') as f:
                    f.write('')
            self._populate_errors()
        except Exception as e:
            try:
                from pyrevit import forms
                forms.alert(u'Could not clear log: {}'.format(e))
            except Exception:
                pass

    def OpenLogFolder_Click(self, sender, args):
        try:
            import subprocess
            folder = os.path.dirname(self._log_path())
            if os.path.isdir(folder):
                subprocess.Popen('explorer "{}"'.format(folder))
        except Exception:
            pass

    def ResetUsage_Click(self, sender, args):
        try:
            from pyrevit import forms
            if not forms.alert(u'Reset all usage counts? This cannot be undone.',
                               yes=True, no=True):
                return
            from nosa_utils import usage as _usage
            _usage.reset()
            self._populate_usage()
        except Exception as e:
            try:
                from pyrevit import forms
                forms.alert(u'Reset error: {}'.format(e))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def Nav_Click(self, sender, args):
        vis = System.Windows.Visibility
        for btn_name, panel in self._panels.items():
            panel.Visibility = vis.Collapsed
            try:
                getattr(self, btn_name).Tag = ''
            except Exception:
                pass
        clicked = sender.Name
        if clicked in self._panels:
            self._panels[clicked].Visibility = vis.Visible
            sender.Tag = 'Active'
            if clicked == 'BtnUsage':
                self._populate_usage()
            elif clicked == 'BtnErrors':
                self._populate_errors()

        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
