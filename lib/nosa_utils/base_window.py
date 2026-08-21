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


def launch_nosa_window(window_class, *args, **kwargs):
    """
    Instantiate a NOSAWindow subclass and show it.
    Surfaces init / ShowDialog failures via forms.alert (avoids blank AzureAD window).
    """
    from pyrevit import forms
    name = getattr(window_class, '__name__', 'NOSA plugin')
    win = None
    try:
        win = window_class(*args, **kwargs)
    except TypeError as e:
        msg = unicode(e)
        if u'2 given' in msg and (u'3 arguments' in msg or u'3 argument' in msg):
            try:
                from pyrevit import revit
                uidoc = getattr(revit, 'uidoc', None)
                if uidoc is not None:
                    win = window_class(*(args + (uidoc,)), **kwargs)
                else:
                    raise
            except Exception:
                forms.alert(
                    u'{} failed to initialise:\n{}'.format(name, e),
                    title=u'NOSA — Window Error')
                return None
        else:
            forms.alert(
                u'{} failed to initialise:\n{}'.format(name, e),
                title=u'NOSA — Window Error')
            return None
    except Exception as e:
        forms.alert(
            u'{} failed to initialise:\n{}'.format(name, e),
            title=u'NOSA — Window Error')
        return None
    if not getattr(win, '_init_ok', True):
        try:
            win.Close()
        except Exception:
            pass
        return None
    try:
        win.ShowDialog()
    except Exception as e:
        forms.alert(
            u'{} error while open:\n{}'.format(name, e),
            title=u'NOSA — Window Error')
        return win
    try:
        from nosa_utils import usage as _usage
        _key = getattr(win, '_plugin_key', None) or name
        _usage.record(_key)
    except Exception:
        pass
    return win


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
        self._init_ok = False
        self._plugin_key = plugin_key
        try:
            WPFWindow.__init__(self, xaml_path)
            self._merge_shared_theme()
            self._config_file = os.path.join(_CONFIGS_ROOT, '_{}.json'.format(plugin_key))
            self._ensure_config_dir()
            self.dark_mode = ThemeManager.load_theme()
            self.ApplyTheme(self.dark_mode)
            self._restore_window_size()
            self._init_ok = True
        except Exception as e:
            self._init_ok = False
            from pyrevit import forms
            forms.alert(
                u'{} — XAML / window load failed:\n{}'.format(plugin_key, e),
                title=u'NOSA — Window Error')
            raise

    # ------------------------------------------------------------------
    # Shared visual style (NosaTheme.xaml)
    # ------------------------------------------------------------------

    def _merge_shared_theme(self):
        """
        Merge lib/nosa_utils/NosaTheme.xaml into this window's own
        Resources, so every NOSAWindow-based plugin picks up the shared
        button/DataGrid/checkbox/etc. styling without having to paste the
        style block into each plugin's own ui.xaml.

        WPF resolves a resource key by checking the window's own Resources
        first and only falling back to MergedDictionaries — so a plugin
        that already defines its own Style for the same TargetType/key
        keeps that local one untouched; this only fills gaps.

        Deliberately swallows every error here rather than letting it
        propagate: a plugin must still open normally (with whatever
        styling it already had) if the shared theme file is missing,
        moved, or fails to parse for any reason. Never let a shared
        cosmetic resource take down an actual working tool.
        """
        try:
            theme_path = os.path.join(os.path.dirname(__file__), 'NosaTheme.xaml')
            if not os.path.exists(theme_path):
                return
            import clr
            clr.AddReference('PresentationFramework')
            from System.Windows.Markup import XamlReader
            from System.IO import FileStream, FileMode, FileAccess
            stream = FileStream(theme_path, FileMode.Open, FileAccess.Read)
            try:
                shared_dict = XamlReader.Load(stream)
            finally:
                stream.Close()
            self.Resources.MergedDictionaries.Add(shared_dict)
            self._apply_shared_control_styles(shared_dict)
            # Second pass after the window is actually shown: some plugins
            # populate ListBox/DataGrid items (which generate their own
            # ComboBox/CheckBox instances from a DataTemplate) only after
            # __init__ runs, so those didn't exist yet for the first walk
            # above. Re-running once Loaded fires catches those too, and
            # is cheap insurance against the first pass ever missing
            # anything for whatever reason.
            self._nosa_shared_dict = shared_dict
            self.Loaded += self._reapply_shared_control_styles_on_load
        except Exception as e:
            logger.debug("NOSAWindow: could not merge shared theme ({}): {}".format(
                self._plugin_key, e))

    def _reapply_shared_control_styles_on_load(self, sender, args):
        try:
            self._apply_shared_control_styles(self._nosa_shared_dict)
        except Exception as e:
            logger.debug("NOSAWindow: reapply on Loaded failed ({}): {}".format(
                self._plugin_key, e))

    def _apply_shared_control_styles(self, shared_dict):
        """
        Belt-and-braces on top of the MergedDictionaries.Add() above.
        WPF is supposed to resolve implicit (TargetType-only) styles
        dynamically even for elements created before the merge, but that
        wasn't reliably reaching Button in practice across plugins here —
        so this walks the window's logical tree and explicitly assigns
        the shared style to any Button / TextBox / ComboBox / CheckBox /
        RadioButton / DataGrid that doesn't already have its own local
        Style set.

        Only ever touches the Style property, and only when the element
        has no local Style value of its own (ReadLocalValue == Unset) —
        a plugin's own explicit Style="{StaticResource ...}" on a specific
        button is left completely alone. Style changes rendering only:
        Click handlers, bindings, IsChecked, Content — everything that
        makes a control actually DO something — live on separate
        properties this never reads or writes.
        """
        try:
            from System.Windows.Controls import Button, TextBox, ComboBox, CheckBox, RadioButton, DataGrid
            from System.Windows import LogicalTreeHelper, DependencyObject, FrameworkElement, DependencyProperty

            target_types = [Button, TextBox, ComboBox, CheckBox, RadioButton, DataGrid]
            styles = []
            for t in target_types:
                try:
                    s = shared_dict[t]
                except Exception:
                    s = None
                if s is not None:
                    styles.append((t, s))
            if not styles:
                return

            def visit(node):
                for t, style in styles:
                    if isinstance(node, t):
                        try:
                            if node.ReadLocalValue(FrameworkElement.StyleProperty) == DependencyProperty.UnsetValue:
                                node.Style = style
                        except Exception:
                            pass
                        break
                if isinstance(node, DependencyObject):
                    try:
                        for child in LogicalTreeHelper.GetChildren(node):
                            if child is not None:
                                visit(child)
                    except Exception:
                        pass

            visit(self)
        except Exception as e:
            logger.debug("NOSAWindow: could not apply shared control styles ({}): {}".format(
                self._plugin_key, e))

    # ------------------------------------------------------------------
    # Window size persistence (resizable windows only)
    # ------------------------------------------------------------------

    def _is_resizable(self):
        try:
            return str(self.ResizeMode) in ('CanResize', 'CanResizeWithGrip')
        except Exception:
            return False

    def _restore_window_size(self):
        if not self._is_resizable():
            return
        try:
            cfg = self.LoadConfig()
            w = float(cfg.get('win_w', 0))
            h = float(cfg.get('win_h', 0))
            if w >= 400 and h >= 300:
                sw = System.Windows.SystemParameters.PrimaryScreenWidth
                sh = System.Windows.SystemParameters.PrimaryScreenHeight
                self.Width  = min(w, sw)
                self.Height = min(h, sh)
        except Exception:
            pass
        try:
            self.Closing += self._nosa_save_window_size
        except Exception:
            pass

    def _nosa_save_window_size(self, sender, args):
        if not self._is_resizable():
            return
        try:
            cfg = self.LoadConfig()
            cfg['win_w'] = float(self.ActualWidth)
            cfg['win_h'] = float(self.ActualHeight)
            self.SaveConfig(cfg)
        except Exception:
            pass

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

    def SetProgress(self, current, total, message=None):
        """
        Determinate progress on 'ProcessBar' (0..total) with optional status
        text on 'TxtStatus'. Pumps the WPF dispatcher so the bar repaints
        during long loops. Both controls are optional — silently ignored
        if absent. Call SetLoading(False) when done to reset.
        """
        try:
            self.ProcessBar.IsIndeterminate = False
            self.ProcessBar.Minimum = 0
            self.ProcessBar.Maximum = max(1, int(total))
            self.ProcessBar.Value   = min(int(current), int(total))
        except Exception:
            pass
        if message:
            try:
                self.TxtStatus.Text = message
            except Exception:
                pass
        try:
            import System
            from System.Windows.Threading import DispatcherPriority
            self.Dispatcher.Invoke(System.Action(lambda: None),
                                   DispatcherPriority.Background)
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
