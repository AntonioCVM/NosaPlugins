# NOSA pyRevit Extension — Changelog

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
