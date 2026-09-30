# NOSA pyRevit Extension — Claude Code Instructions

This file is loaded automatically at the start of every Claude Code session.
It encodes all project conventions so they never need to be repeated.

---

## 1. Language — CRITICAL

ALL user-facing text MUST be in **British English**.
This includes: button labels, window titles, column headers, error messages,
tooltips, combo-box items, TextBlock/TextBox placeholder text, form alerts.

**Spanish text anywhere in the UI is always a bug.**
Comments in code may be in English or Spanish. Variable names must be English.

Correct → `Edge clearance (mm):`  `Arm A — length (piles):`  `Cancel`
Wrong   → `Distancia de borde:`   `Longitud del brazo A:`    `Cancelar`

---

## 2. Import Rules — CRITICAL (multi-Revit safety)

When two Revit versions run simultaneously, `from pyrevit import DB` triggers
pyRevit's full `__init__.py` which reads `pyRevit_config.ini`.
If another instance holds the lock → `IOError: [Errno 32]` crash.

**Rule: always import DB directly from Autodesk:**

```python
# ✓ CORRECT — bypasses pyRevit config chain
from Autodesk.Revit import DB

# ✗ WRONG — triggers pyRevit init → IOError on multi-Revit
from pyrevit import DB
```

`forms`, `revit`, `script` still come from pyrevit — they're only used inside
functions/methods (not at module level), so they don't trigger the init chain
at import time when a button is clicked.

### IronPython 2.7 / CPython 3 compatibility

`unicode()` is a built-in in IronPython 2.7 but does not exist in CPython 3.
Add this shim at the top of any file that calls `unicode()`:

```python
try:
    unicode
except NameError:
    unicode = str  # CPython 3 compat
```

For future CPython 3 migration, use `nosa_utils.bootstrap` instead of `imp`:

```python
# Preferred future pattern (works on both runtimes)
from nosa_utils.bootstrap import load_module
_ui = load_module('myplugin_ui', os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))
```

Current code still uses `imp.load_source` directly — both work in IronPython 2.7.
Only `nosa_utils/bootstrap.py` needs changing when migrating to CPython 3.

---

## 3. Plugin Structure

Every plugin lives at exactly one of these two depths:

```
NOSA.tab/
  Panel.panel/
    Plugin.pushbutton/          ← pushbutton (depth 0)
      script.py
      icon.png                  ← 96×96 RGBA PNG, transparent bg, #FF5F00
      lib/
        ui.py
        logic.py
        ui.xaml

    Pulldown.pulldown/          ← pulldown (adds one depth level)
      icon.png                  ← pulldown icon, also 96×96
      Plugin.pushbutton/
        script.py
        icon.png
        lib/
          ui.py
          logic.py
          ui.xaml
```

### sys.path to shared lib

Depths are counted from `os.path.dirname(__file__)` to `NOSA.extension`, then `lib`.

```
script.py depths (pushbutton is 1 dir deep from panel):
  Direct pushbutton:          3 × '..'   (pushbutton → panel → NOSA.tab → extension)
  Pulldown pushbutton:        4 × '..'   (pushbutton → pulldown → panel → NOSA.tab → extension)

lib/ui.py or lib/logic.py (one level deeper than script.py):
  Direct pushbutton/lib/:     4 × '..'
  Pulldown pushbutton/lib/:   5 × '..'
```

Always guard with `if _lib not in sys.path: sys.path.insert(0, _lib)`.

### script.py standard header

All plugins use `launch_nosa_window` — NOT the bare `imp.load_source` + `ShowDialog()` pattern.

```python
# -*- coding: utf-8 -*-
__title__   = "Plugin\nName"
__version__ = "1.0"
__doc__     = "One-line description."
__author__  = "A. Viñas"

import os, sys, imp

# Direct pushbutton: 3×'..'  |  Pulldown pushbutton: 4×'..'
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

_ui = imp.load_source('pluginname_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit
win = _ui.MyWindow(revit.doc)
win.ShowDialog()
```

Use `imp.load_source` — not `nosa_utils.loader.load_local_module` which can fail silently.

---

## 4. NOSAWindow Base Class

All WPF windows must inherit from `nosa_utils.base_window.NOSAWindow`.

```python
from nosa_utils.base_window import NOSAWindow

class MyWindow(NOSAWindow):
    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'my_plugin_key')
        self.doc = doc
```

**Available methods:**
- `self.LoadConfig()` → `dict`  (loads `NOSA_Configs/_key.json`)
- `self.SaveConfig(data)` → persists dict
- `self.ApplyTheme(dark_mode)` → applies NOSA colour scheme
- `self.SetLoading(bool, message)` → shows/hides `LoadingPanel` + `ProcessBar`
- `self.LogLine(msg)` → appends to optional `TxtLog` TextBox
- `self.Theme_Toggled(sender, args)` → wire to `ChkDarkMode.Click`

**XAML required resources** (must be in `Window.Resources`):
```xml
<SolidColorBrush x:Key="BgColor"     Color="#FAFAFA"/>
<SolidColorBrush x:Key="PanelColor"  Color="#FFFFFF"/>
<SolidColorBrush x:Key="TextColor"   Color="#333333"/>
<SolidColorBrush x:Key="AccentColor" Color="#FF5F00"/>
<SolidColorBrush x:Key="BorderColor" Color="#E0E0E0"/>
```

**XAML loading overlay pattern** (optional but standard):
```xml
<Grid Name="LoadingPanel" Visibility="Collapsed" Background="#CCFAFAFA">
    <Border Background="White" CornerRadius="6" Padding="24,16"
            HorizontalAlignment="Center" VerticalAlignment="Center">
        <StackPanel>
            <TextBlock Text="Processing..." HorizontalAlignment="Center" FontSize="13"/>
            <ProgressBar Name="ProcessBar" Width="200" Height="10"
                         IsIndeterminate="True"
                         Foreground="{DynamicResource AccentColor}"/>
            <TextBlock Name="TxtStatus" HorizontalAlignment="Center"
                       FontSize="11" Opacity="0.6" Margin="0,8,0,0"/>
        </StackPanel>
    </Border>
</Grid>
```

---

## 5. IronPython / WPF Gotchas

### WPF DataGrid binding

- Attribute names with underscore prefix (`_field`) **cannot be bound** in WPF
  DataGrid via `{Binding _field}`. Use plain names: `self.is_subtotal` not `self._is_subtotal`.
- `{Binding type}` conflicts with Python's built-in keyword when IronPython
  reflects on it. Rename to `etype` or similar.

### Module-level Revit API calls

`DB.BuiltInCategory.*` accessed at module import time (outside any function)
can fail in IronPython when the Revit context is not fully active.
**Always wrap in lazy functions or access inside `__init__` / methods.**

```python
# ✗ WRONG — module level
_COLS = DB.BuiltInCategory.OST_StructuralColumns

# ✓ CORRECT — inside function
def _get_cols(doc):
    return DB.FilteredElementCollector(doc) \
             .OfCategory(DB.BuiltInCategory.OST_StructuralColumns) \
             ...
```

### Floor creation (Revit 2024–2027 compatibility)

```python
try:
    # Revit 2022+
    floor = DB.Floor.Create(doc, loops, floor_type_id, level_id)
except Exception:
    # Revit 2021 and earlier fallback
    floor = doc.Create.NewFloor(curve_array, floor_type, level, True)
```

### FamilyInstance creation (structural elements)

```python
try:
    from Autodesk.Revit.DB.Structure import StructuralType
    inst = doc.Create.NewFamilyInstance(pt, symbol, level, StructuralType.Footing)
except Exception:
    inst = doc.Create.NewFamilyInstance(pt, symbol, level,
                                        DB.Structure.StructuralType.Footing)
```

---

## 6. Revit Version Compatibility

Target: **Revit 2024, 2025, 2026, 2027**.

- Use `try/except` around any API call that may differ between versions.
- Never use deprecated APIs without a fallback.
- `ElementId` from an int: `nosa_utils.revit_helpers.element_id_from_int(value)`.
  Never `DB.ElementId(int(x))`: in Revit 2026 IronPython it is ambiguous
  (`ElementId(BuiltInParameter|BuiltInCategory|Int64)`) and raises TypeError
  (lint rule NOSA010). Read ids back with `get_id_value(eid)`.
- Names of element types (FamilySymbol, RebarShape, RebarBarType, *Type): use
  `nosa_utils.revit_helpers.element_name(el)`, never `el.Name` / `getattr(el, 'Name')`
  — `.Name` raises `AttributeError: Name` on some types in IronPython (Revit 2026)
  and pythonnet (lint rule NOSA011).
- `Element.GetTypeId()` → returns ElementId; `doc.GetElement(id)` to resolve.
- Avoid `FilteredElementCollector(...).ToElementIds()` in tight loops — prefer
  `.ToElements()` to avoid repeated `doc.GetElement()` calls.

---

## 7. Design Standards

### NOSA Visual Identity
- **Accent colour:** `#FF5F00` (NOSA orange)
- **Font:** Century Gothic (fallback: Segoe UI)
- **Icon size:** 96 × 96 px, RGBA PNG, transparent background (pyRevit scales it to the
  32/16 px ribbon sizes and it stays sharp on HiDPI). Keep an `icon.svg` master next to it.
- **Dark mode:** toggled per-plugin via `ChkDarkMode`, persisted in config JSON

### Code style
- No module-level comments describing *what* the code does — use clear names
- No multi-paragraph docstrings — one short line max
- No trailing "summary" comments — the diff shows the change
- No Spanish text in code (variable names, comments in UI-related code)
- Prefer `u'...'` string literals for all user-facing strings (IronPython 2 unicode safety)

### Transactions
Always wrap Revit model changes in a named transaction:
```python
with DB.Transaction(doc, u"NOSA — Action Name") as t:
    t.Start()
    # ... model changes ...
    t.Commit()
```

### Unit conversions
```python
_MM_TO_FT = 1.0 / 304.8
_FT_TO_MM = 304.8
# Internal Revit API always uses decimal feet
```

---

## 8. Shared Library (lib/nosa_utils/)

| Module | Purpose |
|---|---|
| `base_window.py` | `NOSAWindow` WPF base class |
| `theme.py` | `ThemeManager` — load/save/apply dark/light theme |
| `logging.py` | `Logger` — debug logging wrapper |
| `revit_helpers.py` | `get_id_value(eid)` and other Revit utility functions |
| `text_utils.py` | Case conversion helpers |

---

## 9. Config / State Files

- Plugin configs: `%APPDATA%\pyRevit\Extensions\NOSA.extension\NOSA_Configs\_key.json`
- Theme: persisted by `ThemeManager` (shared across all plugins)
- Usage stats: `NOSA_Configs\_usage.json` (plugin launch counts)
- Last-used values: each plugin saves its own JSON via `SaveConfig` / `LoadConfig`

---

## 10. Known Issues / History

- **SchedulePro "Generate does nothing"** (fixed Sprint 5): was caused by 4 compounding bugs:
  module-level `_CATEGORY_MAP`, `{Binding type}`, `{Binding _is_subtotal}`,
  and `nosa_utils.loader` failing silently. Fixed in logic.py + ui.py + ui.xaml.

- **Irregular pilecap edge clearance** (fixed Sprint 5): old algorithm expanded from
  cell walls adding `clearance + spacing/2`. Fixed with doubled-coordinate system:
  `eff = clearance_mm - spacing_mm / 2.0`.

- **pyRevit ribbon cache**: structural changes (new/deleted folders) require a full
  **Revit restart** — `pyRevit Reload` only refreshes scripts, not ribbon layout.

- **Multi-Revit IOError**: `from pyrevit import DB` at module level triggers
  pyRevit config read which crashes if another Revit holds the lock.
  Fixed by using `from Autodesk.Revit import DB` everywhere.

---

## 11. Slash Commands (in .claude/commands/)

| Command | Purpose |
|---|---|
| `/new-plugin` | Scaffold a new NOSA plugin with correct structure |
| `/check-plugin` | Validate a plugin against all NOSA conventions |
| `/audit-nosa` | Full audit of all 50+ plugins — find Spanish text, bad imports, missing files |
