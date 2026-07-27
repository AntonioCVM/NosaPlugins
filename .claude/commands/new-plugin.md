# /new-plugin — Scaffold a new NOSA pyRevit plugin

Creates a complete, convention-compliant NOSA plugin from scratch.

## Usage

```
/new-plugin <PluginName> <Panel> [pulldown]
```

Examples:
- `/new-plugin GridManager Structures Elements`  → `Structures.panel/Elements.pulldown/GridManager.pushbutton/`
- `/new-plugin IFCExporterPro Data`              → `Data.panel/IFCExporterPro.pushbutton/`

## What to create

Given the plugin name, panel, and optional pulldown, scaffold ALL of the following:

### 1. Directory structure

```
NOSA.tab/
  <Panel>.panel/
    [<Pulldown>.pulldown/]       ← only if pulldown arg given
      <PluginName>.pushbutton/
        script.py
        icon.png                 ← create a 32×32 orange placeholder PNG using PIL
        lib/
          __init__.py            ← empty
          ui.py
          logic.py
          ui.xaml
```

### 2. script.py

```python
# -*- coding: utf-8 -*-
__title__   = "<Plugin>\nName"
__version__ = "1.0"
__doc__     = "<PluginName> v1.0 — <one line description>."
__author__  = "NOSA Engineering"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), <correct_depth>, 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

_ui = imp.load_source('<pluginname>_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit
win = _ui.<PluginName>Window(revit.doc)
win.ShowDialog()
```

Path depth rules (from script.py to lib/):
- pushbutton (no pulldown): `'..', '..', '..', 'lib'`  (3 levels)
- pulldown/pushbutton:       `'..', '..', '..', '..', 'lib'`  (4 levels)

### 3. lib/logic.py

```python
# -*- coding: utf-8 -*-
from Autodesk.Revit import DB   # ← ALWAYS Autodesk direct, never pyrevit import DB
import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), <correct_depth>, 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

# All DB.BuiltInCategory.* usage MUST be inside functions, never at module level


def get_elements(doc):
    """Collect relevant elements from the model."""
    return list(
        DB.FilteredElementCollector(doc)
          .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
          .WhereElementIsNotElementType()
          .ToElements()
    )
```

Path depth rules (from lib/*.py to lib/):
- pushbutton/lib/*.py:          `'..', '..', '..', '..', 'lib'`  (4 levels)
- pulldown/pushbutton/lib/*.py: `'..', '..', '..', '..', '..', 'lib'`  (5 levels)

### 4. lib/ui.py

```python
# -*- coding: utf-8 -*-
import os, sys, imp
from pyrevit import forms

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), <correct_depth>, 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
_logic = imp.load_source('<pluginname>_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))


class <PluginName>Window(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, '<plugin_key>')
        self.doc = doc

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

    def Run_Click(self, sender, args):
        self.SetLoading(True, 'Processing...')
        try:
            results = _logic.get_elements(self.doc)
            forms.alert(u'Found {} elements.'.format(len(results)))
        except Exception as e:
            forms.alert(u'Error: {}'.format(e))
        finally:
            self.SetLoading(False)

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
```

### 5. lib/ui.xaml

```xml
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="<Plugin Name>" Height="500" Width="700"
        WindowStartupLocation="CenterScreen"
        Background="{DynamicResource BgColor}" FontFamily="Century Gothic">
    <Window.Resources>
        <SolidColorBrush x:Key="BgColor"     Color="#FAFAFA"/>
        <SolidColorBrush x:Key="PanelColor"  Color="#FFFFFF"/>
        <SolidColorBrush x:Key="TextColor"   Color="#333333"/>
        <SolidColorBrush x:Key="AccentColor" Color="#FF5F00"/>
        <SolidColorBrush x:Key="BorderColor" Color="#E0E0E0"/>
    </Window.Resources>
    <Grid Margin="20">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="1*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>

        <TextBlock Grid.Row="0" Text="<PLUGIN NAME>" FontSize="16" FontWeight="Bold"
                   Foreground="{DynamicResource AccentColor}" Margin="0,0,0,16"/>

        <TextBlock Grid.Row="1" Text="Plugin content goes here."
                   Foreground="{DynamicResource TextColor}"/>

        <StackPanel Grid.Row="2" Orientation="Horizontal"
                    HorizontalAlignment="Right" Margin="0,16,0,0">
            <CheckBox Name="ChkDarkMode" Content="Dark Mode"
                      Click="Theme_Toggled" Margin="0,0,16,0"
                      Foreground="{DynamicResource TextColor}"/>
            <Button Content="RUN" Click="Run_Click" Width="100" Height="32"
                    Background="{DynamicResource AccentColor}" Foreground="White"
                    FontWeight="Bold" BorderThickness="0"/>
        </StackPanel>

        <!-- Loading overlay -->
        <Grid Name="LoadingPanel" Grid.RowSpan="3" Visibility="Collapsed"
              Background="#CCFAFAFA">
            <Border Background="White" CornerRadius="6" Padding="24,16"
                    HorizontalAlignment="Center" VerticalAlignment="Center">
                <StackPanel HorizontalAlignment="Center">
                    <TextBlock Text="Processing..." HorizontalAlignment="Center" FontSize="13"/>
                    <ProgressBar Name="ProcessBar" Width="200" Height="10"
                                 IsIndeterminate="True"
                                 Foreground="{DynamicResource AccentColor}" Margin="0,8,0,0"/>
                    <TextBlock Name="TxtStatus" HorizontalAlignment="Center"
                               FontSize="11" Opacity="0.6" Margin="0,8,0,0"/>
                </StackPanel>
            </Border>
        </Grid>
    </Grid>
</Window>
```

### 6. icon.png

Generate a 32×32 NOSA-style icon using PIL:
```python
from PIL import Image, ImageDraw
img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
# Draw something relevant to the plugin in #FF5F00 orange
d.rectangle([4, 4, 28, 28], outline=(255, 95, 0, 255), width=2)
img.save('icon.png')
```

## Checklist before finishing

- [ ] All user-facing strings in British English
- [ ] `from Autodesk.Revit import DB` (not pyrevit)
- [ ] Correct sys.path depth for panel/pulldown level
- [ ] NOSAWindow inherited, plugin_key set
- [ ] XAML has all 5 colour resources
- [ ] Loading overlay present in XAML
- [ ] icon.png created (32×32)
- [ ] __init__.py in lib/ (empty)
