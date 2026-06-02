# NOSA Extension — Phase 1 Task List
> Generated: 2026-05-08 | Version target: 3.0.0

---

## BLOQUE 0 — Fundamentos

- [ ] **B0.1** Create `lib/nosa_utils/base_window.py` — NOSAWindow base class with ApplyTheme, SaveConfig, LoadConfig, ShowResult, SetLoading, LogLine
- [ ] **B0.2a** `icon.svg` + `icon.dark.svg` — HealthScore (shield + score bar + check)
- [ ] **B0.2b** `icon.svg` + `icon.dark.svg` — TemplateGuard (sheet + lock + tick)
- [ ] **B0.2c** `icon.svg` + `icon.dark.svg` — WarningsTriage (triangle + funnel)
- [ ] **B0.2d** `icon.svg` + `icon.dark.svg` — QuantificationQA (cube + bar + sigma)
- [ ] **B0.3** Create folder structure for 4 new plugins (pushbutton dirs + lib/)

---

## BLOQUE 1 — Structural Model Health Score

- [ ] **B1.1** `logic.py` — check_elements_without_material, check_elements_without_analytical, check_orphan_foundations, check_elements_with_warnings, check_parameter_completeness, check_level_offsets, calculate_score
- [ ] **B1.2** `ui.py` + `ui.xaml` — sidebar category filters, score gauge, results table (Check | Issues | Severity | Points lost), Export CSV, Select in Model, dark mode, config persistence
- [ ] **B1.3** `script.py` — imp.load_source entrypoint, __title__, __doc__, __version__
- [ ] **B1.4** QA — smoke test empty model, smoke test real model, score reproducible x3 runs

---

## BLOQUE 2 — Template Compliance Guard

- [ ] **B2.1** `logic.py` — check_views_without_template, check_wrong_scale, check_sheet_naming, check_viewport_overrides, check_crop_region, check_detail_level, load_rules_from_config
- [ ] **B2.2** `ui.py` + `ui.xaml` — rule toggles sidebar, results table (Sheet | View | Rule | Severity | Detail), severity filter, Select in Model, Export Report, Edit Rules button
- [ ] **B2.3** `rules.json` — base config: allowed scales, sheet naming patterns, detail level rules
- [ ] **B2.4** `script.py` + QA (false positive rate < 5%)

---

## BLOQUE 3 — Structural Warnings Triage

- [ ] **B3.1** `logic.py` — get_all_warnings, classify_by_severity (Critical/Medium/Info), group_by_element_pair, get_affected_elements, suggest_action, load_warning_rules
- [ ] **B3.2** `ui.py` + `ui.xaml` — severity filter sidebar, triage table with row colors (red/orange/grey), counter header (X Critical · Y Medium · Z Info), Select in Model, Export Report, Ignore Selected
- [ ] **B3.3** `warning_rules.json` — mapping common structural warnings → severity + suggested action
- [ ] **B3.4** `script.py` + QA

---

## BLOQUE 4 — Concrete & Steel Quantification QA

- [ ] **B4.1** `logic.py` — collect_concrete_elements, extract_volume_and_area, collect_rebar_elements, check_elements_without_material, check_volume_outliers, calculate_rebar_ratio, group_by_level_and_category
- [ ] **B4.2** `ui.py` + `ui.xaml` — category + level filter sidebar, Quantities tab (Category | Level | Volume | Area | Count), QA Issues tab (Element | Problem | Severity), totals/subtotals by level, Export CSV per category
- [ ] **B4.3** `script.py` + QA (validate against manual takeoff)

---

## BLOQUE 5 — Mejoras plugins existentes

- [ ] **B5.1** ExportSheets — Force Black toggle, pre-export temp-override check, fix intermittent blue titleblock (ColorDepth = BlackLine when force-black mode)
- [ ] **B5.2** ClashReport — severity column (intersection volume), HTML export with Isolate links, category-pair summary table
- [ ] **B5.3** TagAll — view filter by level/type, real per-view progress
- [ ] **B5.4** PileMaster — fix `from .logic_x import` relative imports → imp.load_source or proper __init__.py package
- [ ] **B5.5** All plugins — verify imp.load_source for ui.py, SaveConfig/LoadConfig present, unified result format (Created: X | Skipped: Y | Failed: Z)

---

## BLOQUE 6 — Nuevas ideas (planificación)

- [ ] **B6.A** PLAN: Structural Level Navigator (Views.panel) — activate structural plan view by level in 1 click
- [ ] **B6.B** PLAN: Rebar Coverage Checker (Structures.panel) — detect structural elements with no rebar assigned
- [ ] **B6.C** PLAN: Sheet Set Quick Exporter (Print.panel) — save named sheet sets + 1-click export
- [ ] **B6.D** PLAN: Structural Annotation Batch (Views.panel) — batch dims/marks/levels by configurable rules

---

## BLOQUE 7 — Release Fase 1

- [ ] **B7.1** Changelogs for 4 new plugins
- [ ] **B7.2** Update NOSA Dashboard (script.py) with new apps listed
- [ ] **B7.3** Transversal QA checklist — smoke test × 9 plugins (4 new + 5 improved)
- [ ] **B7.4** Bump extension version → v3.0.0

---

## Execution order
```
B0 → B1 → B5.4 → B2 → B3 → B4 → B5.1-B5.5 → B6 (plan only) → B7
```
