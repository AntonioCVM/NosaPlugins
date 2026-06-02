# NOSA Extension - Release Ready QA Checklist

Date: 2026-04-17

## 1) Print Panel - Export Sheets Pro

- [ ] Open `Print > Export Sheets Pro` and confirm UI loads in `Century Gothic`.
- [ ] Close and reopen tool; verify persisted values are restored:
  - [ ] output folder
  - [ ] naming profile
  - [ ] active tab
  - [ ] formats (PDF/DWG/DXF)
  - [ ] search text
  - [ ] sheets/views mode
  - [ ] dark mode
- [ ] In list, verify `Shift + click` checks a continuous range.
- [ ] Multi-select rows and click `Check Selected Rows`; verify all selected rows become checked.
- [ ] Click `Invert Checks`; verify checked state toggles.
- [ ] Use `Select Range...` with:
  - [ ] `A101-A110`
  - [ ] `101-110`
  - [ ] invalid input (`ABC`) shows validation message.
- [ ] Run export with at least one sheet and one format; confirm success log.

## 2) Views Panel - Halftone Selection

- [ ] Open `Views > Halftone Selection`.
- [ ] With no selection, verify validation alert appears.
- [ ] Select elements and run `Apply Halftone`; confirm overrides visible in active view.
- [ ] Run again with `Remove Halftone`; confirm rollback works.
- [ ] Select >20 elements and verify confirmation prompt appears.
- [ ] Confirm icon resources exist:
  - [ ] `Views.panel/HalftoneSelection.pushbutton/icon.svg`
  - [ ] `Views.panel/HalftoneSelection.pushbutton/icon.dark.svg`

## 3) Structures Panel - Align Element to Column

- [ ] Select beams + columns and run command.
- [ ] Select ground beams (foundation elements with curve) + columns and run command.
- [ ] Select pilecaps + columns and run command.
- [ ] Verify preview shows separate counts for:
  - [ ] Beams
  - [ ] Ground Beams
  - [ ] Pilecaps
- [ ] Verify final result dialog includes all three groups.
- [ ] Confirm config file includes `include_ground_beams: true`.

## 4) Waffle Slab

- [ ] Run tool and input parameters; close and reopen, verify defaults persisted.
- [ ] Cancel selection flow and verify graceful cancel message.
- [ ] Verify updated copy appears:
  - [ ] `Real Waffle Slab Creator v2.1`
  - [ ] `Calculating waffle void positions...`

## 5) Cross-Plugin Consistency

- [ ] Main WPF tools open in `Century Gothic`.
- [ ] Theme consistency: dark/light colors applied via shared `nosa_utils.theme.ThemeManager`.
- [ ] No hardcoded absolute user path remains for extension `lib` imports in updated scripts.

## 6) Smoke Test (minimum)

- [ ] Revit opens with extension enabled, no startup errors.
- [ ] Open each changed command once:
  - [ ] Export Sheets Pro
  - [ ] Halftone Selection
  - [ ] Align Element to Column
  - [ ] Waffle Slab
  - [ ] Add Pile to Pilecap
- [ ] No blocking exceptions in pyRevit output panel.
