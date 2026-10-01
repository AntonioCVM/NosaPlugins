# /check-plugin — Validate a NOSA plugin against all conventions

Audits a single plugin directory and reports every violation found.

## Usage

```
/check-plugin <path-or-plugin-name>
```

Examples:
- `/check-plugin CreatePilecapType`
- `/check-plugin Structures.panel/QA.pulldown/ClashReport.pushbutton`

## What to check

Locate the plugin directory under `NOSA.tab/`. Then check every item below.
Report PASS ✓ or FAIL ✗ for each, with the exact file and line number for failures.

---

### A. File structure
- [ ] `script.py` exists
- [ ] `icon.png` exists and is 32×32 px
- [ ] `lib/ui.py` exists
- [ ] `lib/logic.py` exists
- [ ] `lib/ui.xaml` exists
- [ ] `lib/__init__.py` exists (may be empty)

### B. script.py
- [ ] Has `__title__`, `__version__`, `__doc__`, `__author__` metadata
- [ ] `__author__` is `"NOSA Engineering"`
- [ ] Uses `nosa_utils.bootstrap.load_module(...)` to load ui.py (not `imp.load_source` nor `nosa_utils.loader`)
- [ ] sys.path depth is correct:
  - pushbutton (no pulldown): 3 `..` levels to reach lib/
  - pulldown/pushbutton: 4 `..` levels to reach lib/

### C. Import rules
- [ ] No `from pyrevit import DB` anywhere (use `from Autodesk.Revit import DB`)
- [ ] No `from pyrevit import DB, revit` (split: DB from Autodesk, revit from pyrevit)
- [ ] No `from pyrevit import DB, forms` (same split rule)
- [ ] `from Autodesk.Revit import DB` present in logic.py

### D. Module-level Revit API usage
- [ ] No `DB.BuiltInCategory.*` at module level (must be inside functions)
- [ ] No `DB.FilteredElementCollector(...)` at module level
- [ ] No `DB.ElementId(...)` at module level

### E. sys.path depth in lib/*.py
- [ ] pushbutton/lib/*.py: uses 4 `..` to reach extension lib/
- [ ] pulldown/pushbutton/lib/*.py: uses 5 `..` to reach extension lib/
- [ ] Guard: `if _lib not in sys.path: sys.path.insert(0, _lib)`

### F. NOSAWindow
- [ ] ui.py imports `NOSAWindow` from `nosa_utils.base_window`
- [ ] Main window class inherits `NOSAWindow`
- [ ] `NOSAWindow.__init__(self, xaml_path, 'plugin_key')` called
- [ ] `plugin_key` is a unique snake_case string

### G. XAML
- [ ] Window has `FontFamily="Century Gothic"`
- [ ] All 5 colour resources present: `BgColor`, `PanelColor`, `TextColor`, `AccentColor`, `BorderColor`
- [ ] `AccentColor` default is `#FF5F00`
- [ ] No `{Binding type}` — rename to `{Binding etype}`
- [ ] No `{Binding _*}` — underscore-prefixed bindings fail silently in WPF
- [ ] Loading overlay (`LoadingPanel`, `ProcessBar`, `TxtStatus`) present
- [ ] `ChkDarkMode` CheckBox present with `Click="Theme_Toggled"`

### H. British English
Scan all `.py` and `.xaml` files for Spanish UI strings.
Flag any of these patterns found outside comments:
- Common Spanish words in string literals: `Cancelar`, `Aceptar`, `Pilote`, `Encepado`,
  `Guardar`, `Cargar`, `Error`, `Advertencia`, `Seleccionar`, `Generar`, `Exportar`,
  `Armado`, `Forjado`, `Vigas`, `Pilares`, `Cimentación`, `Distancia`, `Longitud`
- Any string with accented characters (á, é, í, ó, ú, ñ, ü) in UI text

### I. Transactions
- [ ] Every model-modifying function wraps changes in `DB.Transaction`
- [ ] Transaction name follows pattern: `u"NOSA — Action Name"`

### J. Unit conversions
- [ ] Uses `_MM_TO_FT = 1.0 / 304.8` (not hardcoded `0.00328`)
- [ ] No raw hardcoded conversion factors without named constant

---

## Output format

```
=== check-plugin: ClashReport ===
Path: Structures.panel/QA.pulldown/ClashReport.pushbutton

File structure
  ✓ script.py
  ✓ icon.png (32×32)
  ✓ lib/ui.py
  ✓ lib/logic.py
  ✓ lib/ui.xaml
  ✗ lib/__init__.py — MISSING

Import rules
  ✗ lib/logic.py:2 — `from pyrevit import DB` → must be `from Autodesk.Revit import DB`
  ✓ No module-level BuiltInCategory usage

XAML
  ✓ All 5 colour resources present
  ✗ lib/ui.xaml:47 — `{Binding _is_match}` → underscore prefix, WPF binding will silently fail

British English
  ✓ No Spanish strings detected

Summary: 3 issues found
Fix: lib/__init__.py (create empty), lib/logic.py:2 (import), lib/ui.xaml:47 (binding name)
```

If zero issues: `✓ Plugin passes all NOSA conventions.`
