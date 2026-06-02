# -*- coding: utf-8 -*-
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
import System.Windows

EXTENSION_VERSION = "3.0.0"
EXTENSION_DATE    = "May 2026"


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
    def __init__(self, panel, name):
        self.Panel = panel
        self.Name  = name


class NOSADashboardWindow(NOSAWindow):

    _PANELS_ORDER = ['NOSA.Panel', 'Piling.panel', 'Structures.panel',
                     'Views.panel', 'Print.Panel', 'Text.panel', 'Data.panel']

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
        }

        self._populate()
        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    # ------------------------------------------------------------------
    # Data gathering
    # ------------------------------------------------------------------

    def _nosa_tab(self):
        return os.path.join(self._root, 'NOSA.tab')

    def _get_panels_info(self):
        tab = self._nosa_tab()
        result = []
        for d in sorted(os.listdir(tab)):
            panel_path = os.path.join(tab, d)
            if not os.path.isdir(panel_path):
                continue
            buttons = [x for x in os.listdir(panel_path)
                       if x.endswith('.pushbutton') and
                       os.path.isdir(os.path.join(panel_path, x))]
            if buttons:
                label = d.replace('.panel', '').replace('.Panel', '')
                result.append((label, len(buttons)))
        return result

    def _get_all_plugins(self):
        tab = self._nosa_tab()
        result = []
        for d in sorted(os.listdir(tab)):
            panel_path = os.path.join(tab, d)
            if not os.path.isdir(panel_path):
                continue
            label = d.replace('.panel', '').replace('.Panel', '')
            for b in sorted(os.listdir(panel_path)):
                if b.endswith('.pushbutton') and os.path.isdir(os.path.join(panel_path, b)):
                    name = b.replace('.pushbutton', '')
                    result.append(PluginItem(label, name))
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
        return rows

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

        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
