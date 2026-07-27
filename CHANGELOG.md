# NOSA pyRevit Extension — Changelog

---

## v5.8.1 — 2026-07-06  (Hardening — user-reported bugs + full static sweep)

### Fixes (user-reported)
- **Issue Gate crashed on open**: `LetterSpacing="1"` in its XAML is a UWP
  property that does not exist in WPF — the window never loaded since the
  attribute was introduced. Removed; swept every other XAML for invalid
  properties (none found).
- **Drawing Protocol Checker**: "Sheet Namer logic not found" — its resolver
  still looked in the Issue pulldown after SheetNamer moved to Sheets in
  v5.7. Now checks Sheets.pulldown first, Issue as fallback.
- **View Manager — Templates**: template list now includes EVERY view
  template in the project (any view type, labelled with its type) instead of
  a type-filtered subset; Apply works on all listed views (with confirmation)
  when no rows are highlighted; clear message when the project has no
  templates at all.
- **View Manager — Rename**: "New name" column is directly editable
  (double-click and type), tracked via CellEditEnding like Sheet Gen.
- **View Manager — Detail number**: new "No." column (viewport detail
  number) next to "Sheet" in the Duplicate, Rename and Templates grids;
  sheet map now reads viewports so both come from one pass.

### Static hardening sweep (all 80 XAML + all plugin .py)
- Cross-reference audit of every plugin moved/renamed in v5.7–5.8: one
  broken reference found (Drawing Protocol Checker, above) — all sibling
  loaders are otherwise suffix- and location-tolerant.
- XML validation of all 80 XAML files: RebarManager.nobutton had two
  missing-space attribute defects (`"Binding=`, `"Width=`) making its XAML
  unparseable — fixed.
- Python `ast` parse of every plugin file: clean.
- XAML event-handler audit: every `Click`/`TextChanged`/etc. handler declared
  in XAML now verified to exist in its `ui.py` — no orphans.

---

## v5.8.0 — 2026-07-06  (DiRoots parity + consolidation + icon set)

### Sheet Gen v4.0 — full DiRoots SheetGen parity
- **Configurable parameter columns**: "Columns…" button on the Edit tab lets you
  pick ANY writable sheet text parameter as an editable grid column (persisted).
- **Place Views window** (button on Create sidebar), three tabs:
  · Place Views — one new sheet per unplaced view (title block + number pattern),
    or a row/column grid of views on an existing sheet.
  · Legends — place the same legend on many sheets at a fixed U,V position.
  · Placeholders — bulk-create placeholder sheets; convert selected placeholders
    to real sheets (number/name preserved, title block added).

### View Manager v2.0
- **Properties tab**: bulk scale / detail level / discipline (template-controlled
  properties skipped safely).
- **Create tab**: 3D view per level (section-boxed per storey) and batch drafting
  view creation.
- **Preview**: PNG snapshot of the highlighted view (ImageExportOptions) opened
  in the default viewer.

### Consolidation (no functionality lost — logic kept as providers)
- **ViewHub → hidden**: superseded by View Manager (same rename/template/clean
  capabilities plus create/duplicate).
- **GA Auto-Dimension → hidden**: paper-scale offset logic ported into
  AnnotationHub's embedded copy first (single source again).
- **Annotation pulldown retitled**: AnnotationHub → "Auto Dimensions" (v1.1),
  AnnotationSuite → "Tags & Symbols". Full window merge deferred — the two tab
  systems differ and a blind splice risked both tools.
- **BulkParameterEditor / ParameterInspector nobuttons DELETED** after diff:
  ParameterHub's embedded copies are identical or newer (compat ensure_text).
- **LinkManager absorbs LinkChangeMonitor**: new "Snapshot Baseline" and
  "Check Changes" buttons (levels/grids/element-count comparison per RVT link);
  LinkChangeMonitor hidden.
- **Text pulldown dissolved**: TextTools moved into Annotations pulldown
  (self-contained, no path changes needed); Documentation panel is one pulldown
  lighter.
- **DrawingChecker absorbs Template Guard**: its five rule checks (scales,
  sheet naming, manual overrides, crop regions, detail level) now run inside
  DrawingChecker's Run All via cross-panel logic loading.

### Lazy loading (verified)
All hubs (ModelHealthHub, RebarHub, SheetHub, ParameterHub, AnnotationHub)
already defer data collection to explicit Run buttons — no changes required.

### Icon set
Letter tiles replaced with drawn glyphs (GDI+, transparent, NOSA palette):
NOSA Dashboard (orange hexagon + dark N, per the recovered NOSA logo),
Wall Footings (wall on strip), Pad Footings (stepped pad + column),
Cover Compliance (section + rebar + dashed cover), View Dependency Explorer
(node graph), View Manager (cascading frames), Sheets pulldown (folded sheet).

Requires a full Revit restart (folders renamed/moved).

---

## v5.7.0 — 2026-07-06  (Sheet Gen + View Manager + ribbon reorganisation)

### Sheet Gen v3.0 (DiRoots SheetGen equivalent)
`SheetComposer.nobutton` promoted, renamed and extended as
`Documentation/Sheets/SheetGen.pushbutton`:
- All existing capability kept: edit-sheets grid, create/clone rows, sidebar
  clone ×N, duplicate with viewports and duplicated model views, renumber
  (prefix/start/step/suffix/pad), CSV import (create/update/both) and export.
- NEW: Excel import (`parse_xlsx_sheets`) — same round-trip modes as CSV.
- NEW: Excel export (`export_xlsx_sheets`) — NOSA-styled header, frozen top
  row, auto column widths; re-import the same file to update sheets.

### View Manager v1.0 (DiRoots-style view management suite)
New `Documentation/Views/ViewManager.pushbutton`, five tabs:
- **Create** — plan views from ticked levels × view family type, `{level}`
  name pattern, optional template and scale applied on creation.
- **Duplicate** — batch duplicate (plain / with detailing / as dependent),
  N copies, `{name}`/`{n}` rename pattern, `CanViewBeDuplicated` guard.
- **Rename** — find & replace, prefix/suffix, case transform with live
  preview (reuses ViewBatchManager logic — single source of truth).
- **Templates** — bulk assign or remove view templates.
- **Clean** — lists views not placed on any sheet; delete selected.

### Ribbon reorganisation
- New **Sheets pulldown** in Documentation: SheetHub + SheetGen (with
  SheetNamer/DrawingIndex logic modules moved alongside — SheetHub sibling
  resolution intact, `SheetComposer` reference updated to `SheetGen`).
- Issue pulldown reordered by workflow: IssueGate → Protocol Checker →
  Revision Tracker → Revision Package Diff → Sheet Issue Manager → Export.
- Panel order fixed via bundle.yaml: **tab** (NOSA → Foundations → Structures
  → Documentation → Data), **Foundations** (PileMaster → PileTools → Wall →
  Pad → Survey), **Structures** (Elements → Coordination → QA → Quantities),
  **Data** (ParameterHub → DataTools → ProjectSetup → ModelCleanup),
  **Documentation** (Sheets → Views → Annotations → Issue → Text → QRCode).
- Views pulldown: ViewManager first, then hubs and single-purpose tools.

Requires a full Revit restart (folder-level ribbon changes).

---

## v5.6.0 — 2026-07-06  (UX overhaul — all plugins)

### Core (`nosa_utils`)
- **`base_window.py`**: resizable windows now remember their size per plugin
  (restored on open, clamped to screen). New `SetProgress(current, total, msg)` —
  determinate ProcessBar with dispatcher pump so long loops repaint the UI.
- **`export_io.py`**: added dialog-based `save_csv` / `save_text` / `ask_save_path`
  with a single remembered output folder shared by all plugins.
- **`version.txt`** (new, extension root): single source of truth for the extension
  version. Dashboard reads it — no more hardcoded stale version strings.

### Dashboard
- New **Error Log** tab: tails `NOSA_Configs/logs/nosa_errors.log` with error count,
  Refresh, Open Folder and Clear Log. Silent plugin failures are now visible.
- Health panel: new **Git** row (last commit hash + date, 3 s timeout).
- Version/date now sourced from `version.txt`.

### Visual (all 71 windows)
- `FontFamily="Century Gothic"` → `"Century Gothic, Segoe UI"` — graceful fallback
  on machines without the corporate font.

### Search boxes added
- LinkManager (name/type/status/path), TypeRenamer (live filter over the preview),
  WorksetHealth (workset/owner), ScheduleImpact (schedule/sheets).
  StructuralTypeManager already had family/type filters — untouched.

### Select in Model added
- **CoverCompliance**: selected rows, or all failing bars if none highlighted.
- **ParameterDriftMonitor**: resolves drift keys (`Category:Mark` or `Category:id`)
  back to elements via new `resolve_key_elements()`.
- **IssueGate**: "Select Sheets" selects the sheets listed in the detail panel.
- **ScheduleImpact**: double-click a row opens the schedule view
  (`RequestViewChange`) — more useful than selection for schedules.
- DrawingChecker excluded: its results store names only; selection would require
  a logic refactor (deferred to avoid regression).

### New plugin — Pad Footings (Foundations)
- `PadFootings.pushbutton` v1.0: lists structural columns (level filter), flags
  columns that already have a foundation within 300 mm of their base, places the
  chosen point-based foundation family at each column base with
  `StructuralType.Footing`. Companion to Wall Footings.

### Workflow
- **ExportSheets**: after each successful export a plain-text transmittal note is
  written to the output folder (project, date, formats, sheet list with revisions).
- **ClashReport**: warns before runs exceeding ~2M element-pair comparisons.
- **ColourByParam** reactivated (`.nobutton` → `.pushbutton`, added to Views layout).
  SheetNamer and DrawingIndex stay hidden — SheetHub already embeds their logic.

---

## v5.5.0 — 2026-07-05  (AM3D-inspired robustness + Wall Footings)

Algorithm patterns adapted from the AM3D-DynamoToRevitAPI library (ideas, not code).

### A — `nosa_utils/solids.py` (new shared module)
Safe solid-geometry helpers: `get_element_solid` (union of bodies, else largest),
`intersection_volume` / `solids_intersect` / `safe_difference` (never raise, never
return None unexpectedly), `union_solids`, `total_volume` (geometric, parameter-free).
- **ClashReport**: `get_element_solid` no longer returns only the FIRST solid of
  multi-body elements (was losing geometry → missed clashes); now unions all bodies.
- **QuantificationQA**: `_volume_m3` falls back to geometric solid-volume sum when
  `HOST_VOLUME_COMPUTED` is missing or zero — silent 0 m³ rows eliminated.

### B — Wall Footings (new plugin, Foundations panel)
`WallFootings.pushbutton` v1.0 — batch-creates continuous wall foundations
(`WallFoundation.Create`) under selected structural walls. Level filter, footing
type selector, walls that already have a footing are flagged and skipped.
Requires a Revit restart to appear in the ribbon.

### C — GA Auto-Dimension reactivated + paper-constant spacing (v1.1)
- `GAAutoDimension.nobutton` → `.pushbutton`; added to `Annotations.pulldown/bundle.yaml`.
- Dimension line offset was fixed at 2 m model units regardless of scale. Now
  `offset = paper_mm × view.Scale` (default 8 mm on paper, editable in the UI and
  persisted with the on-grid tolerance in the plugin config).
- `script.py` normalised: `imp.load_source`, standard header, redundant usage
  tracking removed (handled by `launch_nosa_window`).

### D — Pilecap polygon validation (CreatePilecapType)
`validate_cap_polygon()` runs before any geometry is created for irregular caps:
point-in-polygon check per pile + minimum pile-to-edge distance ≥ clearance.
On failure nothing is created and the exact problem is reported. The live preview
shows a GEOMETRY WARNING in the same case. Verified standalone against rectangle,
line, L, T, single-pile and corrupt-polygon cases (6/6).

---

## v5.4.0 — 2026-07-02  (Runtime bug fixes)

### NOSA Dashboard — XAML crash fixed
- `<Grid BorderBrush="..." BorderThickness="...">` is not valid WPF — Grid does not support
  those properties; only `Border` does. The Protocol panel had 7 field rows using this
  pattern, causing the entire XAML to fail to load on startup.
- Fix: each affected Grid wrapped in `<Border BorderBrush="..." BorderThickness="...">`.
  Two error dialogs (one from `NOSAWindow.__init__`, one from `launch_nosa_window`) now gone.

### LinkManager — "Name" initialisation error fixed
- DataGrid `{Binding Name}` is ambiguous in IronPython/WPF because `Name` is a reserved
  `FrameworkElement` property. Renamed `_LinkRow.Name` → `_LinkRow.LinkName` and
  `_LinkRow.Path` → `_LinkRow.LinkPath`; updated XAML bindings accordingly.
- Added `try/except` guards around `TxtSummary.Text` and `TxtStatus.Text` assignments
  in `_load()`.

### AnnotationBatch — removed from ribbon (logic preserved)
- `AnnotationBatch.pushbutton` renamed to `AnnotationBatch.nobutton`. The plugin is no
  longer visible in the ribbon because `AnnotationSuite` provides the same functionality
  in a unified 3-tab interface (Tags / Grid Bubbles / Spot Elevations) and already loads
  AnnotationBatch's `logic.py` directly via `_load_sibling_logic`.

### ExportSheets — pre-flight check removed
- The IssueGate pre-flight block in `script.py` was removed at user request. Export now
  launches directly without running IssueGate checks.

---

## v5.3.0 — 2026-07-02  (Sprint 3 — ribbon clean-up)

### B3 — Dead `.nobutton` folders removed from `Data.panel`

Five `.nobutton` folders were confirmed as exact duplicates of active pushbuttons
inside `DataTools.pulldown` and `ProjectSetup.stack`. Deleted:

- `Data.panel/ExcelSync.nobutton` (identical to `DataTools.pulldown/ExcelSync.pushbutton`)
- `Data.panel/WorksetHealth.nobutton` (identical to `DataTools.pulldown/WorksetHealth.pushbutton`)
- `Data.panel/TypeRenamer.nobutton` (identical to `DataTools.pulldown/TypeRenamer.pushbutton`)
- `Data.panel/LinkManager.nobutton` (identical to `ProjectSetup.stack/LinkManager.pushbutton`)
- `Data.panel/ProjectSetupWizard.nobutton` (identical to `ProjectSetup.stack/ProjectSetupWizard.pushbutton`)

The only diff between each pair was the sys.path depth (3×`..` at panel root vs 4×`..`
inside pulldown/stack) — both correct for their respective locations. No unique logic lost.

`BulkParameterEditor.nobutton` and `ParameterInspector.nobutton` were NOT touched —
diff against their pushbutton counterparts still pending.

---

## v5.2.0 — 2026-07-02  (Sprint 2-3 — product coherence + onboarding)

### RebarCoverage consolidation
- **`Elements.pulldown/RebarCoverage.pushbutton`**: title corrected to "Missing Rebar" (it detects
  structural elements with no rebar assigned — not EC2 cover). `__doc__` updated to match.
- **`Coordination.pulldown/CoverCompliance.pushbutton`** (was `RebarCoverage.nobutton`): folder
  renamed from `.nobutton` to `.pushbutton`; title/doc/module name updated to "Cover Compliance";
  icon generated (orange "C"); added to `Coordination.pulldown/bundle.yaml`. Now visible in ribbon.

### B2 — bundle.yaml for PileTools and Survey
- Created `Foundations.panel/PileTools.pulldown/bundle.yaml` (AddPileToPilecap → CreatePilecapType
  → PilecapLoadChecker). Previously order was undefined/alphabetical.
- Created `Foundations.panel/Survey.pulldown/bundle.yaml` (CuadroReplanteo → PileSurveyExport).

### A3 — `@transaction` decorator
- Added `transaction(name)` decorator to `lib/nosa_utils/transactions.py`. Wraps any
  `NOSAWindow` method that edits the Revit model — `doc` resolved from `self.doc`. Existing
  `nosa_transaction()` context manager is unchanged and still the recommended pattern for
  complex write operations.

### D2 — DMU health check in Dashboard
- Health panel now reports two extra rows: `DMU — logic file` (checks `logic_dmu.py` exists
  at `Foundations.panel`) and `DMU — live coords` (reads `live_coords.json` and shows whether
  pile live coordinates are active).

### D3 — Get Started panel in Dashboard
- New sidebar item **Get Started** added to NOSA Dashboard with three workflow cards:
  Issue (IssueGate → SheetHub → RevisionTracker → ExportSheets),
  Foundations (PileMaster → AddPileToPilecap → PileSurveyExport),
  Model QA (ModelHealthHub → HealthScore → QuantificationQA).

### D4 — Version per plugin in Dashboard
- `PluginItem` now exposes a `Version` field populated by reading `__version__` from each
  `script.py` at startup. Shown as a third right-aligned column in the Plugins tab.

---

## v5.1.0 — 2026-07-02  (Sprint 1 — reliability & quick wins)

### Bug fixes
- **DMU `logic_dmu.py`**: `_LIB_DIR` was still pointing to the deleted `Piling.panel` path.
  Fixed to `Foundations.panel`. Added `_IMPORT_WARNED` flag so a failed `logic_coords`
  import is logged once via `log_error` instead of silently swallowed on every pile move.
- **ExportSheets pre-flight**: `except Exception: pass` replaced with `log_error` so any
  failure of the IssueGate check is written to the NOSA error log while still being
  non-blocking (export proceeds).
- **`config_manager.py`**: `DEFAULT_CONFIG_DIR` was writing to `%APPDATA%/pyRevit/NOSA_Configs`
  instead of the correct `…/Extensions/NOSA.extension/NOSA_Configs`. Unified with
  `base_window._CONFIGS_ROOT`.
- **`RebarCoverage.pushbutton` (Elements)**: script used `importlib.util` with `imp` fallback
  (violates CLAUDE.md §3) and only added the local `lib/` to `sys.path`, making
  `nosa_utils` import order-dependent. Fixed: `imp.load_source`, correct 4×`..` extension
  lib path, title updated to "Cover Compliance" for clarity.
- **Dashboard `_PANELS_ORDER`**: still listed `'Piling'` after panel was renamed to
  `Foundations`. Updated.

### Infrastructure
- **A1 — Telemetry in `launch_nosa_window`**: `usage.record(plugin_key)` is now called after
  every successful `ShowDialog()`. One change covers all ~88 plugins that use
  `launch_nosa_window` — no per-plugin changes needed.

### Audit findings that were false positives
- **Fix #5 (Sheets.pulldown)**: does not exist; DrawingIndex is already a `.nobutton`
  inside `Issue.pulldown`. Nothing to delete.
- **B4 (Issue pulldown order)**: `bundle.yaml` was already in the proposed order.
- **B5 (missing icons)**: 5 of the 7 reported buttons already had `icon.png`; the
  "SVG-only" five also have `icon.png`. Only two were genuinely missing:
  `ViewDependencyExplorer` and `NOSA Dashboard` — both generated (32×32, #FF5F00, white letter).

---

## v5.0.0 — 2026-07-02  (Phase 3 — competitive plugins + technical debt closure)

### Block 8 — Issue workflow
- **Issue pulldown** (renamed from Sheets): ribbon now groups all issue-related tools under a single `Issue` pulldown.
- **Issue Gate** (new, v1.0): pre-export validation gate — runs four checks (Drawing Protocol, Current Revision, Titleblock fields, Duplicate sheet numbers), shows colour-coded pass/warn/fail cards, chains directly to Export Sheets Pro on approval.
- **ExportSheets** (v4.2): now runs IssueGate pre-flight checks automatically on launch; warns if FAILs are found, with option to proceed or cancel.

### Block 9 — QA normalisation
All six QA scripts normalised to `imp.load_source` pattern (removed `importlib.util` shim):
DrawingChecker, ClashReport, AnalyticalHealthCheck, ConnectionChecker, FoundationLoadExtractor, FamilyAudit.

### Block 10 — Competitive plugins (Phase 1)
| Plugin | Panel | Description |
|--------|-------|-------------|
| **Parameter Drift Monitor** | Structures / Coordination | Snapshot shared parameters at baseline, compare current model state against it. Detects added, removed, and modified values. Import from Excel; export diff to CSV. Trend chart for historical drift. |
| **Schedule Impact** | Structures / QA | Select a Revit category to see all schedules that reference it, the number of fields each uses, and which sheets each schedule is placed on. Helps assess impact before renaming families or changing categories. |
| **Revision Package Diff** | Documentation / Issue | Snapshot all sheet revision states; compare baseline vs. current to produce a transmittal list of New/Revised/Removed/Unchanged sheets. Exports to CSV. |

### Block 11 — Competitive plugins (Phase 2)
| Feature | Plugin | Description |
|---------|--------|-------------|
| **Protocol tab** | NOSA Dashboard | New sidebar tab documenting the full NOSA drawing naming convention (F1–F8 fields), issue stages (P/C/I/PC series), and issue process flow. |
| **View Dependency Explorer** (new, v1.0) | Documentation / Views | Select any view to see its template, all applied filters (with visibility state), every sheet it is placed on, all revisions on those sheets, and all dependent views. |
| **Jump to View** | ModelHealthHub / WarningsTriage | New button in the WarningsTriage tab: finds the first 3D or floor-plan view that contains the affected elements and activates it in Revit, then selects the elements. |

### Block 12 — Technical debt closure
- **`unicode()` compat shim**: added `try: unicode / except NameError: unicode = str` to five files that still called `unicode()` — StructuralTypeManager (ui+logic), BulkParameterEditor (ui+logic), SheetComposer ui. No behaviour change in IronPython 2.7; future CPython 3 migration will not require per-file changes.
- **`from pyrevit import DB` audit**: zero remaining module-level occurrences across the codebase (the two hits in the Dashboard audit code are string literals inside a scanner function, not actual imports).
- **`nosa_utils.bootstrap`**: CPython 3-compatible module loader (`load_module`, `ensure_lib`, `load_local`) was present from Block 1 and unchanged. Documented in CLAUDE.md §2 as the preferred future pattern.
- **CLAUDE.md**: updated to document bootstrap shim and unicode compat pattern.

---

## v4.0.0 — 2026-06-29  (Phase 2 — new plugins + quality sweep)

### Quality sweep (Block 0)

- **`__author__`**: mass-updated to `"A. Viñas"` across all 51 scripts.
- **XAML colour resources**: `BgColor` / `PanelColor` (and `TextColor` / `BorderColor` for ModelSyncChecker) added to 11 plugins that were missing them — dark-mode toggle now works correctly in all plugins.
- **RevisionTracker**: `"prefijo"` → `"prefix"` (last remaining Spanish UI string).

### New plugins — Block 1

#### Documentation / Sheets pulldown
| Plugin | Version | Description |
|--------|---------|-------------|
| **Sheet Namer** | 1.0 | Implements NOSA File Naming Protocol v2.2 (9 fields, exact character lengths). Three modes: Constructor (field-by-field dropdowns with live preview), Bulk Editor (DataGrid for all sheets), Parser (decompose existing numbers → correct → reapply). Auto-suggests F3/F4/F7 from active sheet name and associated level. Validates exact field lengths and warns on duplicate numbers. |

### New plugins — Block 2–4

#### Documentation / Views pulldown
| Plugin | Version | Description |
|--------|---------|-------------|
| **Colour by Parameter** | 1.0 | Select any category and instance parameter → assigns a 16-colour palette to each unique value → applies solid-fill graphic overrides in the active view. Clear button resets overrides. Inspired by DiRoots OneFilter, free alternative focused on structural workflows. |
| **Bay Sections** | 1.0 | Select grid pairs (A + B) → auto-generates longitudinal and transverse section views between them. Configurable name prefix, depth offset, and section view type. Equivalent to DiRoots QuickViews but grid-driven rather than room-driven. |

#### Structures / QA pulldown
| Plugin | Version | Description |
|--------|---------|-------------|
| **Section Boxer** | 1.0 | One-click 3D section box around the current selection. Prompts for offset (mm), creates a new isometric 3D view named after the selection, and activates it. No WPF window — runs directly from the button. |

#### Structures / Quantities pulldown
| Plugin | Version | Description |
|--------|---------|-------------|
| **Rebar Manager** | 1.0 | Two-tab plugin. **BS 8666 Schedule tab**: collects all rebar in the model, groups by bar mark, exports to formatted Excel with NOSA header (orange column headers, alternating rows, totals row). Filename auto-generated following NOSA protocol. **Bar Mark Manager tab**: detects duplicate marks (same mark + different diameter = likely drawing error), supports batch renumbering with configurable prefix and start number. |

### Plugin consolidation
To avoid ribbon clutter, 8 new concepts were merged into 5 plugins:
- Pile Schedule Generator → new **Schedule tab in PileMaster** (next session)
- Rebar Schedule (BS 8666) + Bar Mark Manager → **Rebar Manager** (single plugin, 2 tabs)
- Excel Table Importer → new **Import Table tab in ExcelSync** (next session)
- Section Box Creator → simple **Section Boxer** script (no WPF)
- Colour by Parameter, Bay Sections, Sheet Namer → standalone plugins

---

## v3.2.0 — 2026-06-29  (Block 6 — new utility plugins)

### New plugins

#### Documentation / Views pulldown
| Plugin | Version | Description |
|--------|---------|-------------|
| **Level Navigator** | 1.0 | Lists all project levels with elevation (m). Shows the associated floor-plan view (preferring structural discipline). Double-click or Activate button to switch Revit active view. Levels without a view are shown at reduced opacity. |

---

## v3.1.0 — 2026-06-29  (Convention hardening & NOSAWindow rollout)

### NOSAWindow migration (7 plugins)

All remaining plugins that used `pyrevit.forms.WPFWindow` or `wpf.LoadComponent`
have been migrated to `NOSAWindow`. Every plugin in the extension now inherits from
`NOSAWindow`, giving them unified theme management, config persistence, and loading overlay.

| Plugin | Change |
|--------|--------|
| DimensionWalls | `WPFWindow` → `NOSAWindow`; removed custom `ApplyTheme` / `Theme_Toggled` |
| AlignViewTitles | `WPFWindow` → `NOSAWindow` |
| CopyViewTemplates | `WPFWindow` → `NOSAWindow` |
| TagAll | `WPFWindow` → `NOSAWindow` |
| QRCode | `WPFWindow` → `NOSAWindow`; custom JSON config replaced with `LoadConfig`/`SaveConfig` |
| ExportSheets Pro | `WPFWindow` → `NOSAWindow`; kept `ApplyTheme` override for `ChkDarkMode` sync |
| PileMaster | `wpf.LoadComponent` approach → `NOSAWindow`; removed module-level pyrevit imports |

### Import fixes — `from pyrevit import DB` eliminated

Inline `from pyrevit import DB` inside methods triggers pyRevit's config chain and can
crash when two Revit instances run simultaneously. All occurrences replaced with
module-level `from Autodesk.Revit import DB` across 10 files: AnnotationBatch, HealthScore,
TemplateGuard, WarningsTriage, QuantificationQA, PilecapLoadChecker, ConnectionChecker,
ElementJoin, RebarCoverage, FamilyAudit.

### Bug fixes

- **AnnotationBatch**: `__import__('pyrevit').DB.FilteredElementCollector` inside a method
  replaced with the already-imported `DB` — hidden lazy import that bypassed the module-level rule.
- **PilecapLoadChecker**: `{Binding Type}` in DataGrid XAML caused a silent WPF binding failure
  (Python keyword conflict). Renamed `CapRow.Type` → `CapRow.Etype` and updated XAML binding.

### UI text

- **RevisionTracker**: 5 Spanish strings corrected to British English —
  `+ CREAR REVISIÓN` → `+ CREATE REVISION`, column headers `Nº Plano / Revisión / Disciplina / Prefijo`
  → `Sheet No. / Revision / Discipline / Prefix`, section title → `Sheet Revision Assignment`.

---

## v3.0.0 — 2026-05-08  (Phase 1 release)

### New plugins

#### Structures panel
| Plugin | Version | Description |
|--------|---------|-------------|
| **Health Score** | 1.0 | Structural model audit: weighted score 0-100 across 6 checks (material, analytical, orphan foundations, warnings, Mark parameter, level offsets). CSV export + select in model. |
| **Warnings Triage** | 1.0 | Classifies all Revit warnings by structural severity (High/Medium/Low). Colour-coded table, suggested action per warning, ignore/select workflow. |
| **Quantification QA** | 1.0 | Extracts concrete volumes & rebar quantities per level/category. QA tab detects missing materials, zero volumes and statistical outliers. CSV export with all tabs. |
| **Rebar Coverage** | 1.0 | Detects structural elements without rebar. Coverage gauge, category summary, and list of missing elements with Select in Model. |

#### Views panel
| Plugin | Version | Description |
|--------|---------|-------------|
| **Template Guard** | 1.0 | Checks views/sheets against NOSA standards: no template, non-standard scale, sheet naming, manual overrides, missing crop, wrong detail level. Configurable via `rules.json`. |
| **Level Navigator** | 1.0 | Lists all project levels with elevation and linked structural plan views. One-click activation. |
| **Annotation Batch** | 1.0 | Batch-applies structural tags (columns, framing, foundations) and grid bubble visibility to multiple views simultaneously. |

#### Print panel
| Plugin | Version | Description |
|--------|---------|-------------|
| **Sheet Set Exporter** | 1.0 | Save named groups of sheets and export them in one click (PDF/DWG). Last output folder persisted. Integrates with ExportSheets engine. |

---

### Improvements to existing plugins

#### ExportSheets Pro (v4.3)
- Added **Force Black** colour mode toggle (Formats tab): forces PDF to `BlackLine` depth and DWG to `IndexColors` for documentation-quality black output.
- Added **Pre-export check**: warns when selected views have temporary Hide/Isolate or overrides active — the most likely cause of unexpected colour in exports.
- Config persistence fix: last naming profile and output folder now reliably restored on open.
- Import collision fix: `ui.py` loaded via `imp.load_source` with unique module name.

#### ClashReport (v2.1)
- **Severity column**: High / Medium / Low based on intersection volume (m³).
- **Volume column**: actual intersection volume displayed per clash.
- **Row colour coding**: red for High, orange for Medium.
- **HTML export redesigned**: includes category-pair summary table and NOSA styling.

#### TagAll (v3.2)
- **Level filter**: ComboBox to filter target views by level (complementary to text search).
- **Real per-view progress**: `TxtStatus` shows current view and `ProgressBar` advances incrementally.
- **Unified result**: `Tagged / Skipped / Failed` counts.

#### PileMaster (v2.1)
- **Relative import fix**: `from .logic_x import` replaced with `imp.load_source` preloading in `script.py`. Eliminates `ValueError: Attempted relative import in non-package` in IronPython.

---

### Shared library additions
| Module | Change |
|--------|--------|
| `lib/nosa_utils/base_window.py` | New — `NOSAWindow` base class: `ApplyTheme`, `SaveConfig`, `LoadConfig`, `SetLoading`, `LogLine`, `ShowResult`, `SwitchTab`. All new Phase 1 plugins inherit from it. |

---

## v2.2.0 — 2026-04-18  (Sprint 2-3 hardening)

- All `except:` bare clauses replaced with `except Exception:` across `NOSA.tab` and `lib/`.
- `ClashReport`: broad-phase X-sweep + solid cache (performance improvement).
- `WaffleSlab`: point-in-polygon filter for void placement + two separate transactions (main slab / compression slab).
- `NOSA Dashboard` redesigned as operational dashboard with environment info and health checks.

---

## v2.1.0 — 2026-04-17  (Phase 0 hardening)

- `TagAll`: indentation fix in `try/except`, level filter ComboBox added.
- `DimensionWalls`: duplicate `create_arc_dimensions` removed.
- P0 fixes: `import os` in 4 scripts, DXF export decoupled from DWG branch.
- `base_window.py` introduced (stub).
