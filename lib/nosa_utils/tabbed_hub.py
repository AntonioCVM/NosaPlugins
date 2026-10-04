# -*- coding: utf-8 -*-
"""
One ribbon button, several existing NOSA tools as tabs (T8.6–T8.11 merges).

Each tool window is built (never shown) the first time its tab is opened; its content moves into
the tab together with its own resources, so its buttons, bindings and theme keep working on the
original window object. Close / Hide / Show of a tool act on the hub.
"""
import os

from nosa_utils.base_window import NOSAWindow
from nosa_utils.telemetry import log_swallowed

_LOG = u'nosa_utils.tabbed_hub'
_XAML = os.path.join(os.path.dirname(__file__), 'tabbed_hub.xaml')
_THEME_KEYS = ('BgColor', 'PanelColor', 'TextColor', 'AccentColor', 'BorderColor')


class TabbedHub(NOSAWindow):
    """tools: [(tab header, factory)] — factory() returns the tool's NOSAWindow (not shown)."""

    def __init__(self, title, plugin_key, tools):
        NOSAWindow.__init__(self, _XAML, plugin_key)
        from System.Windows.Controls import TabItem
        self.Title = title
        self._factories = []
        self._tools = {}
        self._contents = []
        self._is_loaded = False
        for header, factory in tools:
            item = TabItem()
            item.Header = header
            self.HubTabs.Items.Add(item)
            self._factories.append(factory)
        self.HubTabs.SelectionChanged += self._tab_changed
        self._is_loaded = True
        self.HubTabs.SelectedIndex = 0
        self._build(0)

    def _tab_changed(self, sender, args):
        if not self._is_loaded or args.OriginalSource is not self.HubTabs:
            return
        self._build(self.HubTabs.SelectedIndex)

    def tool(self, index):
        """The tool window behind tab `index` (built on demand)."""
        self._build(index)
        return self._tools.get(index)

    def _build(self, index):
        if index < 0 or index in self._tools:
            return
        tool = self._factories[index]()
        content = tool.Content
        tool.Content = None
        own = tool.Resources
        for key in list(own.Keys):
            try:
                if key in _THEME_KEYS:
                    continue                    # set below from the hub's theme
                value = own[key]
                if content.Resources.Contains(key):
                    content.Resources[key] = value
                else:
                    content.Resources.Add(key, value)
            except Exception:
                log_swallowed(_LOG, u'_build')
        for name in ('Close', 'Hide', 'Show', 'ApplyTheme'):
            setattr(tool, name, getattr(self, name))
        self.HubTabs.Items[index].Content = content
        self._contents.append(content)
        self._paint(content.Resources, self.dark_mode)
        self._tools[index] = tool
        for prop in ('Width', 'Height'):
            try:
                setattr(self, prop, max(getattr(self, prop), getattr(tool, prop) + 24))
            except Exception:
                log_swallowed(_LOG, u'_build')

    def ApplyTheme(self, dark_mode):
        """Hub and every open tab follow one theme (a tool's own toggle calls this too)."""
        self.dark_mode = dark_mode
        self._paint(self.Resources, dark_mode)
        for content in getattr(self, '_contents', []):
            self._paint(content.Resources, dark_mode)

    @staticmethod
    def _paint(resources, dark_mode):
        """Fresh brushes per dictionary: a brush shared by two dictionaries gets frozen by WPF."""
        from System.Windows.Media import SolidColorBrush, Color as MediaColor
        from nosa_utils.theme import ThemeManager
        colors = ThemeManager.get_colors(dark_mode)
        for key, name in zip(_THEME_KEYS, ('bg', 'panel', 'text', 'accent', 'border')):
            c = colors[name]
            brush = SolidColorBrush(MediaColor.FromArgb(c.A, c.R, c.G, c.B))
            try:
                if resources.Contains(key):
                    resources[key] = brush
                else:
                    resources.Add(key, brush)
            except Exception:
                log_swallowed(_LOG, u'_paint')
