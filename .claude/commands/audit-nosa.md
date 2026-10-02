# /audit-nosa — Full audit of all NOSA plugins

Scans every plugin in the extension and produces a prioritised report of all violations.

## What to do

1. Find every `.pushbutton` directory under `NOSA.tab/` (including those inside `.pulldown/`)
2. Run the full `/check-plugin` checklist on each one
3. Aggregate results into a prioritised report

## Checks to run across ALL plugins simultaneously

### Critical (break at runtime)
- `from pyrevit import DB` at module level → IOError on multi-Revit
- `DB.BuiltInCategory.*` at module level → fails before Revit context active
- `{Binding type}` in XAML → Python keyword collision
- `{Binding _*}` in XAML → silent WPF binding failure
- Wrong sys.path depth (e.g. 4 `..` in a pulldown that needs 5)
- `nosa_utils.loader.load_local_module` (can fail silently) or bare `imp.load_source` → use `nosa_utils.bootstrap.load_module`

### High (break visually or functionally)
- Spanish UI strings in TextBlock/TextBox/Button content
- Missing `lib/__init__.py`
- Missing `icon.png` or wrong size
- Window class does not inherit `NOSAWindow`
- Missing 5 colour resources in XAML
- No `LoadingPanel` in XAML (if plugin does async work)

### Medium (convention violations)
- `__author__` is not `"NOSA Engineering"`
- `plugin_key` not set or not unique
- Transaction name not matching `"NOSA — ..."` pattern
- Hardcoded unit conversion factor without named constant

### Low (style / hygiene)
- Missing `lib/__init__.py` (empty is fine, but should exist)
- `__doc__` is empty or missing
- Commented-out code blocks > 5 lines

## Output format

Print a table sorted by severity then plugin name:

```
NOSA Extension Audit — <date>
Total plugins: 50

CRITICAL (must fix before next release)
┌─────────────────────────────────────────────────────────────────────────┐
│ Plugin              │ File          │ Line │ Issue                      │
├─────────────────────────────────────────────────────────────────────────┤
│ ClashReport         │ lib/logic.py  │  2   │ `from pyrevit import DB`   │
│ GAAutoDimension     │ lib/logic.py  │ 14   │ Module-level BuiltInCat    │
│ ...                                                                      │
└─────────────────────────────────────────────────────────────────────────┘

HIGH
┌─────────────────────────────────────────────────────────────────────────┐
│ Plugin              │ File          │ Line │ Issue                      │
├─────────────────────────────────────────────────────────────────────────┤
│ ExcelSync           │ lib/ui.xaml   │ 34   │ Spanish text "Cancelar"    │
│ ...                                                                      │
└─────────────────────────────────────────────────────────────────────────┘

MEDIUM / LOW  (list only, no table)
...

CLEAN PLUGINS (0 issues): PileMaster, CreatePilecapType, NOSA Dashboard, ...

Summary
  Critical: X   High: Y   Medium: Z   Low: W
  Estimated fix time: ~N hours
```

## After the report

For each Critical issue, offer to fix it immediately.
Group fixes where possible (e.g. mass-replace all `from pyrevit import DB`
across all files in one operation rather than file by file).
