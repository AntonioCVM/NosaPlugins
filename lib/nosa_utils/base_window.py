# -*- coding: utf-8 -*-
"""
NOSAWindow — Base WPF window class for all NOSA pyRevit plugins.

Provides:
  - NOSA theme (Century Gothic, #FF5F00 accent, light/dark)
  - Per-plugin config persistence (JSON)
  - Standard result reporting
  - Loading/progress helpers
  - Shared log panel helpers
"""
import os
import sys
import json

from pyrevit.forms import WPFWindow
import System.Windows

from nosa_utils.theme import ThemeManager
from nosa_utils.logging import Logger

logger = Logger()

_CONFIGS_ROOT = os.path.join(
    os.getenv('APPDATA', ''),
    'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs'
)


class NOSAWindow(WPFWindow):
    """
    Base class for all NOSA WPF windows.

    Subclass usage:
        class MyWindow(NOSAWindow):
            def __init__(self, doc):
                NOSAWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'ui.xaml'), 'my_plugin')
                self.doc = doc
                self.InitializeData()
    """

    def __init__(self, xaml_path, plugin_key):
        """
        Args:
            xaml_path  (str): Absolute path to ui.xaml.
            plugin_key (str): Short unique key used for config file name, e.g. 'health_score'.
        """
        WPFWindow.__init__(self, xaml_path)
        self._plugin_key = plugin_key
        self._config_file = os.path.join(_CONFIGS_ROOT, '_{}.json'.format(plugin_key))
        self._ensure_config_dir()

        self.dark_mode = ThemeManager.load_theme()
        self.ApplyTheme(self.dark_mode)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def ApplyTheme(self, dark_mode):
        self.dark_mode = dark_mode
        colors = ThemeManager.get_colors(dark_mode)
        try:
            self.Resources["BgColor"].Color     = colors['bg']
            self.Resources["PanelColor"].Color  = colors['panel']
            self.Resources["TextColor"].Color   = colors['text']
            self.Resources["AccentColor"].Color = colors['accent']
            self.Resources["BorderColor"].Color = colors['border']
        except Exception as e:
            logger.debug("NOSAWindow.ApplyTheme: {}".format(e))

    def Theme_Toggled(self, sender, args):
        """Wire CheckBox.Click="Theme_Toggled" in XAML for dark-mode toggle."""
        chk = sender
        new_mode = chk.IsChecked == True
        if new_mode != self.dark_mode:
            ThemeManager.save_theme(new_mode)
            self.ApplyTheme(new_mode)
            cfg = self.LoadConfig()
            cfg['dark_mode'] = new_mode
            self.SaveConfig(cfg)

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _ensure_config_dir(self):
        if not os.path.exists(_CONFIGS_ROOT):
            try:
                os.makedirs(_CONFIGS_ROOT)
            except (OSError, IOError) as e:
                logger.debug("NOSAWindow: could not create config dir: {}".format(e))

    def SaveConfig(self, data):
        """Persist dict to plugin config file."""
        try:
            with open(self._config_file, 'w') as f:
                json.dump(data, f, indent=2)
        except (OSError, IOError, TypeError) as e:
            logger.debug("NOSAWindow.SaveConfig ({}): {}".format(self._plugin_key, e))

    def LoadConfig(self):
        """Load plugin config dict; returns {} on any error."""
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.debug("NOSAWindow.LoadConfig ({}): {}".format(self._plugin_key, e))
        return {}

    # ------------------------------------------------------------------
    # Loading / progress
    # ------------------------------------------------------------------

    def SetLoading(self, is_loading, message="Processing..."):
        """
        Toggle a loading overlay named 'LoadingPanel' (Visibility) and an
        optional status label named 'TxtStatus'.  Both are optional — if the
        control doesn't exist the call is silently ignored.
        """
        vis = System.Windows.Visibility
        state = vis.Visible if is_loading else vis.Collapsed
        try:
            self.LoadingPanel.Visibility = state
        except Exception:
            pass
        try:
            self.ProcessBar.IsIndeterminate = is_loading
        except Exception:
            pass
        if message:
            try:
                self.TxtStatus.Text = message
            except Exception:
                pass

    def LogLine(self, msg):
        """Append a line to a TextBox named 'TxtLog' (optional)."""
        try:
            self.TxtLog.AppendText(msg + "\n")
            self.TxtLog.ScrollToEnd()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Standard result dialog
    # ------------------------------------------------------------------

    def ShowResult(self, created=0, skipped=0, failed=0, extra_lines=None):
        """
        Show a unified result message box.
        Pass extra_lines=['Note: ...'] for additional context.
        """
        from pyrevit import forms
        msg = "Created: {}\nSkipped: {}\nFailed:  {}".format(created, skipped, failed)
        if extra_lines:
            msg += "\n\n" + "\n".join(extra_lines)
        title = "Done" if failed == 0 else "Done (with errors)"
        forms.alert(msg, title=title)

    # ------------------------------------------------------------------
    # Sidebar tab switching (shared pattern)
    # ------------------------------------------------------------------

    def SwitchTab(self, btn_name, tabs_dict):
        """
        tabs_dict: {'BtnTabX': self.GridX, ...}
        Hides all grids, shows the selected one, updates Tag="Selected" on buttons.
        """
        vis = System.Windows.Visibility
        for name, grid in tabs_dict.items():
            grid.Visibility = vis.Collapsed
        if btn_name in tabs_dict:
            tabs_dict[btn_name].Visibility = vis.Visible
        for name in tabs_dict.keys():
            try:
                btn = getattr(self, name)
                btn.Tag = "Selected" if name == btn_name else ""
            except Exception:
                pass
