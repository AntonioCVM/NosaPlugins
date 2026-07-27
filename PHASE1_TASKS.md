# NOSA Extension — Phase 1 Task List
> Generated: 2026-05-08 | Version target: 3.0.0 (shipped as 3.1.0)

---

## BLOQUE 0 — Fundamentos

- [x] **B0.1** Create `lib/nosa_utils/base_window.py` — NOSAWindow base class with ApplyTheme, SaveConfig, LoadConfig, ShowResult, SetLoading, LogLine
- [x] **B0.2a** `icon.svg` + `icon.dark.svg` — HealthScore
- [x] **B0.2b** `icon.svg` + `icon.dark.svg` — TemplateGuard
- [x] **B0.2c** `icon.svg` + `icon.dark.svg` — WarningsTriage
- [x] **B0.2d** `icon.svg` + `icon.dark.svg` — QuantificationQA
- [x] **B0.3** Create folder structure for 4 new plugins (pushbutton dirs + lib/)

---

## BLOQUE 1 — Structural Model Health Score

- [x] **B1.1** `logic.py` — check_elements_without_material, check_elements_without_analytical, check_orphan_foundations, check_elements_with_warnings, check_parameter_completeness, check_level_offsets, calculate_score
- [x] **B1.2** `ui.py` + `ui.xaml` — sidebar category filters, score gauge, results table, Export CSV, Select in Model, dark mode, config persistence
- [x] **B1.3** `script.py` — imp.load_source entrypoint, __title__, __doc__, __version__
- [ ] **B1.4** QA — smoke test empty model, smoke test real model, score reproducible ×3 runs *(requires Revit)*

---

## BLOQUE 2 — Template Compliance Guard

- [x] **B2.1** `logic.py` — check_views_without_template, check_wrong_scale, check_sheet_naming, check_viewport_overrides, check_crop_region, check_detail_level, load_rules_from_config
- [x] **B2.2** `ui.py` + `ui.xaml` — rule toggles sidebar, results table, severity filter, Select in Model, Export Report, Edit Rules button
- [x] **B2.3** `rules.json` — base config: allowed scales, sheet naming patterns, detail level rules
- [x] **B2.4** `script.py`
- [ ] QA (false positive rate < 5%) *(requires Revit)*

---

## BLOQUE 3 — Structural Warnings Triage

- [x] **B3.1** `logic.py` — get_all_warnings, classify_by_severity, group_by_element_pair, get_affected_elements, suggest_action, load_warning_rules
- [x] **B3.2** `ui.py` + `ui.xaml` — severity filter sidebar, triage table with row colours, counter header, Select in Model, Export Report, Ignore Selected
- [x] **B3.3** `warning_rules.json` — mapping common structural warnings → severity + suggested action
- [x] **B3.4** `script.py`
- [ ] QA *(requires Revit)*

---

## BLOQUE 4 — Concrete & Steel Quantification QA

- [x] **B4.1** `logic.py` — collect_concrete_elements, extract_volume_and_area, collect_rebar_elements, check_elements_without_material, check_volume_outliers, calculate_rebar_ratio, group_by_level_and_category
- [x] **B4.2** `ui.py` + `ui.xaml` — category + level filter sidebar, Quantities tab, QA Issues tab, totals/subtotals by level, Export CSV per category
- [x] **B4.3** `script.py`
- [ ] QA (validate against manual takeoff) *(requires Revit)*

---

## BLOQUE 5 — Mejoras plugins existentes

- [x] **B5.1** ExportSheets — Force Black toggle, pre-export temp-override check
- [x] **B5.2** ClashReport — severity column (intersection volume), HTML export, category-pair summary table
- [x] **B5.3** TagAll — view filter by level/type, real per-view progress
- [x] **B5.4** PileMaster — relative imports replaced with imp.load_source; migrated to NOSAWindow
- [x] **B5.5** All plugins — imp.load_source for ui.py, SaveConfig/LoadConfig present; 0 `from pyrevit import DB` violations, 0 `{Binding type}` conflicts, 100% NOSAWindow (50/50 plugins)

---

## BLOQUE 6 — Nuevas ideas (implementadas)

- [x] **B6.A** Structural Level Navigator — `Documentation.panel\Views.pulldown\LevelNavigator.pushbutton` — lists levels + elevation, activates structural plan view on double-click
- [x] **B6.B** Rebar Coverage Checker — `Structures.panel\Elements.pulldown\RebarCoverage.pushbutton` (implemented in Phase 1)
- [x] **B6.C** Sheet Set Quick Exporter — integrated into ExportSheets Pro (Sheet Sets expander: save / load / delete named sets + 1-click export)
- [x] **B6.D** Structural Annotation Batch — `Documentation.panel\Annotations.pulldown\AnnotationBatch.pushbutton` (implemented in Phase 1)

---

## BLOQUE 7 — Release Fase 1

- [x] **B7.1** Changelogs for 4 new plugins — v3.0.0 in CHANGELOG.md; convention hardening in v3.1.0
- [x] **B7.2** Update NOSA Dashboard — Dashboard scans plugins dynamically; all new plugins auto-listed
- [x] **B7.3** Transversal QA checklist — QA_CHECKLIST.md updated to v3.1.0 with convention compliance section
- [x] **B7.4** Bump extension version → v3.1.0 (set in NOSA Dashboard ui.py)

---

## Execution order
```
B0 → B1 → B5.4 → B2 → B3 → B4 → B5.1-B5.5 → B6 → B7  ✅ COMPLETE
```

> Remaining open items: QA smoke tests (B1.4, B2.4, B3.4, B4.4) require Revit — run against QA_CHECKLIST.md.
