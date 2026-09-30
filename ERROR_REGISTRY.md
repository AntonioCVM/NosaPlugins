# NOSA Extension — Error Registry

> All known runtime errors, their causes and fixes.  
> Add new entries to `lib/nosa_utils/known_errors.json`.  
> Error logs are written to `%APPDATA%\pyRevit\Extensions\NOSA.extension\Logs\nosa_errors_YYYYMMDD.log`

---

## How to use

From any plugin:
```python
from nosa_utils.error_registry import ErrorRegistry
reg = ErrorRegistry()

try:
    ...
except Exception as e:
    hint = reg.log_error("MyPlugin", e, context="during export")
    if hint:
        forms.alert("Known error detected:\n\n" + hint)
```

---

## Known errors catalogue

| ID | Plugin | Severity | Symptom | Cause | Fix |
|----|--------|----------|---------|-------|-----|
| ERR001 | * | CRITICAL | `Attempted relative import in non-package` | IronPython resolves wrong `ui.py` from another plugin | Use `imp.load_source()` with unique module name in `script.py` |
| ERR002 | * | CRITICAL | `has no attribute 'tabs'` | `ApplyLoadedConfig()` called before `self.tabs` is initialized | Move `self.tabs = {...}` before any `LoadLastConfig` / `ApplyLoadedConfig` call |
| ERR003 | ExportSheets | WARNING | `PDF export returned False` | Sheet has no views, or view has temporary hide/isolate active | Use pre-export check in Formats tab; check view state before export |
| ERR004 | ExportSheets | WARNING | `No se detectó PDF creado` | Revit I/O race condition — file written but not yet visible | Increase `time.sleep()` in `export_sheet_pdf()` or add retry |
| ERR005 | ClashReport | WARNING | `BooleanOperationsUtils` exception | Invalid element geometry for boolean intersection | Already handled — `intersect_volume()` returns 0.0 and skips pair |
| ERR006 | WaffleSlab | ERROR | `Boundary curves do not form a valid planar loop` | Non-planar or unclosed boundary selection | Use "Rectangular area" mode, or ensure all lines are co-planar and close |
| ERR007 | TagAll | INFO | `IndependentTag.Create` fails per element | Element not visible in view / no valid reference | Counted as "Failed" — check view detail level and element visibility |
| ERR008 | PileMaster | CRITICAL | `ValueError: Attempted relative import` | Same as ERR001, specific to `logic_*.py` relative imports | `script.py` pre-loads with `imp.load_source`; reload pyRevit after changes |
| ERR009 | RebarCoverage | WARNING | `GetDependentElements` unavailable | Some Revit API versions / element types | Fallback collector already in place — no crash |
| ERR010 | * | WARNING | `DynamicResource BgColor` key not found | `ApplyTheme` called before `WPFWindow.__init__` | Always call `WPFWindow.__init__` (or `NOSAWindow.__init__`) first |
| ERR011 | TemplateGuard | WARNING | `GetCategoryOverrides` exception | Internal/empty categories raise on override query | Already in `try/except` — count may be slightly low |
| ERR012 | QuantificationQA | INFO | `HOST_VOLUME_COMPUTED` = 0 | Parameter not available for some framing types | Element flagged as "Zero volume" in QA tab — expected behaviour |
| ERR013 | SheetExportHub | ERROR | ExportManager import fails | SheetExportHub `lib/` not importable — path or folder issue | Ensure `Documentation.panel/Sheets.pulldown/SheetExportHub.pushbutton/lib` exists |
| ERR014 | * | WARNING | `ShowElements` fails | Elements in different view type / view not open | Already in `try/except` — selection still applied |
| ERR015 | LevelNavigator | ERROR | Cannot set `ActiveView` | Selected view is not openable / wrong type | LevelNavigator only shows FloorPlan views; check view is not closed |

---

## Adding a new entry

Edit `lib/nosa_utils/known_errors.json`:
```json
[
  {
    "id": "ERR016",
    "plugin": "MyPlugin",
    "match": "keyword that appears in the exception message",
    "severity": "ERROR",
    "cause": "What causes this.",
    "fix": "How to fix it.",
    "docs": "Optional reference"
  }
]
```
The `plugin` field accepts `"*"` for any plugin.

---

## Log file location

`%APPDATA%\pyRevit\Extensions\NOSA.extension\Logs\nosa_errors_YYYYMMDD.log`

One file per day. Entries include timestamp, plugin name, traceback, and known-error ID if matched.
