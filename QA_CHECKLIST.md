# NOSA Extension v3.0.0 — Transversal QA Checklist

Run before every release. Test on **at least one real project model**.

---

## Smoke tests (open without crashing)

| Plugin | Open OK | No import error | Closes OK |
|--------|:-------:|:---------------:|:---------:|
| HealthScore | ☐ | ☐ | ☐ |
| TemplateGuard | ☐ | ☐ | ☐ |
| WarningsTriage | ☐ | ☐ | ☐ |
| QuantificationQA | ☐ | ☐ | ☐ |
| RebarCoverage | ☐ | ☐ | ☐ |
| LevelNavigator | ☐ | ☐ | ☐ |
| AnnotationBatch | ☐ | ☐ | ☐ |
| ExportSheets Pro | ☐ | ☐ | ☐ |
| ClashReport | ☐ | ☐ | ☐ |
| TagAll | ☐ | ☐ | ☐ |
| PileMaster | ☐ | ☐ | ☐ |
| WaffleSlab | ☐ | ☐ | ☐ |

---

## Functional tests

### HealthScore
- [ ] Run with all checks ON → score shown (0–100)
- [ ] Score bar changes colour (green / orange / red)
- [ ] "Select in Model" selects elements
- [ ] Export CSV saves file with all columns

### TemplateGuard
- [ ] "No template" check finds real issues in model
- [ ] Severity filter (High/Medium/Low) works
- [ ] Search box filters table
- [ ] "Edit Rules" opens `rules.json` in Notepad
- [ ] Export CSV saves file

### WarningsTriage
- [ ] Loads all model warnings
- [ ] High/Medium/Low correctly classified
- [ ] Action panel shows on row selection
- [ ] "Ignore" hides row (re-shown with toggle)
- [ ] "Select in Model" works

### QuantificationQA
- [ ] Quantities tab shows volumes per level/category
- [ ] Rebar tab shows bars and lengths
- [ ] QA tab shows missing material issues
- [ ] Tab switching works
- [ ] Export CSV has all three sections

### RebarCoverage
- [ ] Coverage % shown correctly
- [ ] Category summary table populated
- [ ] Missing elements list populated
- [ ] "Select in Model" selects correct elements

### LevelNavigator
- [ ] List shows all levels with elevation
- [ ] Selecting a level activates its view

### AnnotationBatch
- [ ] Tag tab: places column tags in selected views
- [ ] Grid Bubbles tab: shows/hides bubbles
- [ ] Result panel shows Created/Skipped/Failed

### ExportSheets Pro (regressions)
- [ ] Last profile selected on open
- [ ] Last folder shown on open
- [ ] "Force Black" → PDF lines are black/greyscale
- [ ] Pre-export check warns for temp-isolated views
- [ ] DWG Force Black uses IndexColors
- [ ] Active tab persisted between sessions
- [ ] Sheet Sets expander: Save set → appears in dropdown
- [ ] Sheet Sets expander: Load set → checkboxes update correctly
- [ ] Sheet Sets expander: Delete set → removed from dropdown

### ClashReport
- [ ] Severity and Volume columns shown
- [ ] Row colours match severity
- [ ] HTML export opens in browser with summary table
- [ ] "Isolate Selected" works

### TagAll
- [ ] Level filter shows levels and filters list
- [ ] Progress bar advances per view
- [ ] Result shows Tagged/Skipped/Failed

### PileMaster
- [ ] Opens without `ValueError: Attempted relative import`
- [ ] Coordinate tab works
- [ ] Numbering tab works

---

## Visual consistency

- [ ] All new windows use Century Gothic font
- [ ] All new windows respond to Dark Mode toggle
- [ ] `AccentColor` (#FF5F00) correct throughout
- [ ] NOSA Dashboard lists all 8 new plugins

---

## Regression — no previously working features broken

- [ ] ExportSheets PDF export (colour mode) still works
- [ ] ExportSheets DWG export still works
- [ ] WaffleSlab creates floor with voids
- [ ] AddPileToPilecap places piles
- [ ] DimensionWalls creates dimensions

---

_Mark ☑ when verified. Sign off: ________________________  Date: ___________  Version: v3.0.0_
