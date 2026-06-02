# NOSA Extension - Technical Changelog

Date: 2026-04-17
Scope: release-ready stabilization and UX consistency

## Added

- New command: `Views.panel/HalftoneSelection.pushbutton/script.py`
  - Apply/remove halftone on current view selection.
  - Safety confirmation when operating on large selections.
- New icon assets for the new command:
  - `Views.panel/HalftoneSelection.pushbutton/icon.svg`
  - `Views.panel/HalftoneSelection.pushbutton/icon.dark.svg`

## Updated

- `Print.Panel/ExportSheets.pushbutton/lib/ui.py`
  - Extended session persistence:
    - active tab
    - dark mode
    - formats
    - search text
    - output folder
    - naming profile
    - sheets/views mode
  - Enhanced selection UX:
    - `Shift + click` range checking
    - `Check Selected Rows`
    - `Invert Checks`
    - `Select Range...` (e.g. `A101-A110`, `101-110`)
- `Print.Panel/ExportSheets.pushbutton/lib/ui.xaml`
  - Added selection action buttons.
  - Enabled extended row selection.
  - Set `Century Gothic` font.

- `Structures.panel/CenterBeamToColumn.pushbutton/script.py`
  - Added support for ground beams (foundation + curve location).
  - Preview/results now differentiate beams, ground beams, and pilecaps.
  - Updated script metadata to `v3.1`.

- `Structures.panel/CenterBeamToColumn.pushbutton/config.json`
  - Added `include_ground_beams`.

- `Structures.panel/WaffleSlab.pushbutton/script.py`
  - Improved config read/write error reporting.
  - Persist user input defaults for subsequent runs.
  - Added explicit cancel handling for selection actions.
  - Updated output/copy text consistency.
  - Updated script metadata to `v2.1`.

- Theme and visual consistency (shared `ThemeManager`)
  - `Views.panel/TagAll.pushbutton/lib/ui.py`
  - `Views.panel/AlignViewTitles.pushbutton/lib/ui.py`
  - `Views.panel/CopyViewTemplates.pushbutton/lib/ui.py`
  - `Views.panel/DimensionWalls.pushbutton/lib/ui.py`
  - `Structures.panel/ClashReport.pushbutton/lib/ui.py`

- Typography consistency (`Century Gothic`) in key WPF windows
  - `Piling.panel/PileMaster.pushbutton/lib/ui.xaml`
  - `Print.Panel/ExportSheets.pushbutton/lib/ui.xaml`
  - `Views.panel/DimensionWalls.pushbutton/lib/ui.xaml`
  - `Views.panel/CopyViewTemplates.pushbutton/lib/ui.xaml`
  - `Views.panel/TagAll.pushbutton/lib/ui.xaml`
  - `Views.panel/AlignViewTitles.pushbutton/lib/ui.xaml`
  - `Structures.panel/ClashReport.pushbutton/lib/ui.xaml`

## Refactored

- Replaced hardcoded absolute `sys.path` extension imports with relative extension-root resolution in multiple scripts:
  - `Piling.panel/AddPileToPilecap.pushbutton/script.py`
  - `Piling.panel/CreatePilecapType.pushbutton/script.py`
  - `Views.panel/ExportScheduleToExcel.pushbutton/script.py`
  - `NOSA.Panel/NOSA.pushbutton/script.py`
  - `Text.panel/BatchRename.pushbutton/script.py`
  - `Text.panel/MinusToMayus.pushbutton/script.py`
  - `Text.panel/MayusToMinus.pushbutton/script.py`
  - `Structures.panel/CenterBeamToColumn.pushbutton/script.py`

## Hardening

- Exception handling cleanup in critical scripts:
  - `Piling.panel/AddPileToPilecap.pushbutton/script.py`
    - Removed silent bare `except:` blocks and replaced with explicit exception handling.
  - Additional guardrails in UI handlers (`AlignViewTitles`, `TagAll`, etc.) to reduce hidden failures.

## Notes

- Python CLI execution checks are not available in this environment (no local `python` command).
- Lint checks on edited files passed during implementation.
