# Mapa de carpetas `.nobutton` (T5.2)

Generado 2026-09-28 sobre `develop` @ `121d93b`. pyRevit no registra carpetas `.nobutton` en la cinta;
solo se ejecutan si un pushbutton activo, `lib/` o `startup.py` las carga por ruta.

**Método.** Para cada carpeta se buscó su nombre base como literal de ruta (`'Name'`, `Name.nobutton`,
`Name.pushbutton`, `Name.{}` usado con `for suffix in ('nobutton', 'pushbutton')`) en todos los `.py`,
`.yaml`, `.xaml` y `.json` del repo, excluyendo la propia carpeta. Se revisaron además los enumeradores
de directorios (`NOSA.pushbutton` solo cuenta `.pushbutton`; `startup.py`, `hooks/` y `bundle.yaml` no
citan ninguna). Una referencia que solo proviene de otra `.nobutton` muerta no cuenta (cierre transitivo).

**Resultado.** Hay **57** carpetas (no 58), **29639 LOC** Python en total: **12 usadas** (9469 LOC),
**44 muertas** (19659 LOC) y 1 dudosa/excluida (`ClashReport`). Todas las muertas tienen copia de su lógica
dentro de un hub activo (`logic_*.py`), así que borrarlas no quita funcionalidad.

| Carpeta (bajo `NOSA.tab/`) | LOC | Quién la usa (fichero:línea) | Veredicto |
|---|---|---|---|
| `Data.panel/DataTools.pulldown/ExcelSync.nobutton` | 755 | sin referencias; absorbida en `DataToolsHub/lib/logic_excel_sync.py` | muerta |
| `Data.panel/DataTools.pulldown/TypeRenamer.nobutton` | 249 | sin referencias; absorbida en `DataToolsHub/lib/logic_type_renamer.py` | muerta |
| `Data.panel/DataTools.pulldown/WorksetHealth.nobutton` | 244 | sin referencias; absorbida en `DataToolsHub/lib/logic_workset_health.py` | muerta |
| `Data.panel/ModelCleanup.nobutton` | 663 | sin referencias; absorbida en `DataToolsHub/lib/logic_model_cleanup.py` | muerta |
| `Data.panel/ProjectSetup.stack/LinkManager.nobutton` | 399 | sin referencias; absorbida en `DataToolsHub/lib/logic_link_manager.py` | muerta |
| `Documentation.panel/Annotations.pulldown/AnnotationBatch.nobutton` | 421 | AnnotationSuite.pushbutton/lib/ui.py:32 (`_load_sibling_logic`) | **usada** |
| `Documentation.panel/Annotations.pulldown/BatchRename.nobutton` | 340 | sin referencias; absorbida en `TextTools.pushbutton` | muerta |
| `Documentation.panel/Annotations.pulldown/CaseConverter.nobutton` | 183 | sin referencias; absorbida en `TextTools.pushbutton` | muerta |
| `Documentation.panel/Annotations.pulldown/DimensionWalls.nobutton` | 478 | sin referencias; absorbida en `AnnotationHub/lib/logic_dim_walls.py` | muerta |
| `Documentation.panel/Annotations.pulldown/GAAutoDimension.nobutton` | 1061 | sin referencias; absorbida en `AnnotationHub/lib/logic_ga_auto_dim.py` | muerta |
| `Documentation.panel/Annotations.pulldown/GridBubbleBatch.nobutton` | 195 | AnnotationSuite.pushbutton/lib/ui.py:33 (`_load_sibling_logic`) | **usada** |
| `Documentation.panel/Issue.pulldown/DrawingProtocolChecker.nobutton` | 236 | IssueWorkflowHub.pushbutton/lib/logic_issue_gate.py:20 (sufijo dinámico) | **usada** |
| `Documentation.panel/Issue.pulldown/ExportSheets.nobutton` | 2992 | IssueWorkflowHub.pushbutton/script.py:32 (encadena Export tras Issue Gate; carga `lib/ui.py`) | **usada** |
| `Documentation.panel/Issue.pulldown/IssueGate.nobutton` | 402 | sin referencias; absorbida en `IssueWorkflowHub/lib/logic_issue_gate.py` | muerta |
| `Documentation.panel/Issue.pulldown/RevisionPackageDiff.nobutton` | 278 | sin referencias; absorbida en `IssueWorkflowHub/lib/logic_revision_package_diff.py` | muerta |
| `Documentation.panel/Issue.pulldown/RevisionTracker.nobutton` | 929 | sin referencias; absorbida en `IssueWorkflowHub/lib/logic_revision_tracker.py` | muerta |
| `Documentation.panel/Issue.pulldown/SheetIssueManager.nobutton` | 305 | sin referencias; absorbida en `IssueWorkflowHub/lib/logic_sheet_issue_manager.py` | muerta |
| `Documentation.panel/Sheets.pulldown/DrawingIndex.nobutton` | 618 | SheetGen.pushbutton/lib/ui.py:23; SheetHub.pushbutton/lib/ui.py:41 | **usada** |
| `Documentation.panel/Sheets.pulldown/SheetNamer.nobutton` | 1488 | SheetHub.pushbutton/lib/ui.py:43; IssueWorkflowHub.pushbutton/lib/logic_protocol_checker.py:26 | **usada** |
| `Documentation.panel/Views.pulldown/AlignViewTitles.nobutton` | 398 | sin referencias; absorbida en `ViewUtilities/lib/logic_align_view_titles.py` | muerta |
| `Documentation.panel/Views.pulldown/BaySections.nobutton` | 364 | sin referencias; absorbida en `ViewUtilities/lib/logic_bay_sections.py` | muerta |
| `Documentation.panel/Views.pulldown/ColourByParam.nobutton` | 325 | sin referencias; absorbida en `ViewOverrides/lib/logic_colour_by_param.py` | muerta |
| `Documentation.panel/Views.pulldown/CopyViewTemplates.nobutton` | 364 | sin referencias; absorbida en `ViewTemplateManager/lib/logic_copy_templates.py` | muerta |
| `Documentation.panel/Views.pulldown/HalftoneSelection.nobutton` | 84 | sin referencias; absorbida en `ViewUtilities/lib/logic_halftone_selection.py` | muerta |
| `Documentation.panel/Views.pulldown/LevelNavigator.nobutton` | 187 | sin referencias; absorbida en `ViewUtilities/lib/logic_level_navigator.py` (nombre citado solo como metadato en `error_registry.py`) | muerta |
| `Documentation.panel/Views.pulldown/SectionBoxer.nobutton` | 100 | sin referencias; absorbida en `ViewUtilities/lib/logic_section_boxer.py` | muerta |
| `Documentation.panel/Views.pulldown/TemplateGuard.nobutton` | 528 | ViewTemplateManager.pushbutton/lib/ui.py:161 (`rules.json`); StructuralQA.pushbutton/lib/logic_drawing_checker.py:223 | **usada** |
| `Documentation.panel/Views.pulldown/ViewBatchManager.nobutton` | 443 | ViewManager.pushbutton/lib/ui.py:29 (`_load_sibling_logic`) | **usada** |
| `Documentation.panel/Views.pulldown/ViewDependencyExplorer.nobutton` | 338 | sin referencias; absorbida en `ViewUtilities/lib/logic_view_dependency_explorer.py` | muerta |
| `Documentation.panel/Views.pulldown/ViewFilterBatch.nobutton` | 591 | sin referencias; absorbida en `ViewOverrides/lib/logic_view_filter_batch.py` | muerta |
| `Documentation.panel/Views.pulldown/ViewHub.nobutton` | 400 | sin referencias; absorbida en `ViewManager.pushbutton (hub sucesor)` | muerta |
| `Documentation.panel/Views.pulldown/ViewOrganiser.nobutton` | 329 | solo `ViewHub.nobutton/lib/ui.py:31` (muerta); copia en `ViewManager.pushbutton (rename/delete)` | muerta |
| `Foundations.panel/PadFootings.nobutton` | 365 | sin referencias; absorbida en `FootingDesigner/lib/logic_pad_footings.py` | muerta |
| `Foundations.panel/Survey.pulldown/CuadroReplanteo.nobutton` | 841 | sin referencias; absorbida en `SurveyExport/lib/logic_cuadro_replanteo.py` | muerta |
| `Foundations.panel/Survey.pulldown/PileSurveyExport.nobutton` | 555 | sin referencias; absorbida en `SurveyExport/lib/logic_pile_survey_export.py` | muerta |
| `Foundations.panel/WallFootings.nobutton` | 334 | sin referencias; absorbida en `FootingDesigner/lib/logic_wall_footings.py` | muerta |
| `Structures.panel/Coordination.pulldown/AnalyticalHealthCheck.nobutton` | 514 | sin referencias; absorbida en `ModelHealthHub/lib/logic_analytical_health.py` | muerta |
| `Structures.panel/Coordination.pulldown/ConnectionChecker.nobutton` | 456 | sin referencias; absorbida en `ModelHealthHub/lib/logic_connection_checker.py` | muerta |
| `Structures.panel/Coordination.pulldown/CoverCompliance.nobutton` | 308 | sin referencias; absorbida en `ModelHealthHub/lib/logic_cover_compliance.py` | muerta |
| `Structures.panel/Coordination.pulldown/FoundationLoadExtractor.nobutton` | 424 | sin referencias; absorbida en `ModelHealthHub/lib/logic_foundation_loads.py` | muerta |
| `Structures.panel/Coordination.pulldown/HealthScore.nobutton` | 1149 | sin referencias; absorbida en `ModelHealthHub/lib/logic_health_score.py` (nombre citado solo como metadato en `error_registry.py`) | muerta |
| `Structures.panel/Coordination.pulldown/LevelGridSync.nobutton` | 316 | sin referencias; absorbida en `ModelHealthHub/lib/logic_level_grid_sync.py` | muerta |
| `Structures.panel/Coordination.pulldown/LinkChangeMonitor.nobutton` | 343 | DataToolsHub.pushbutton/lib/ui.py:64 (sufijo dinámico) | **usada** |
| `Structures.panel/Coordination.pulldown/ModelSyncChecker.nobutton` | 401 | sin referencias; absorbida en `ModelHealthHub/lib/logic_model_sync.py` | muerta |
| `Structures.panel/Coordination.pulldown/ParameterDriftMonitor.nobutton` | 417 | sin referencias; absorbida en `ModelHealthHub/lib/logic_parameter_drift.py` | muerta |
| `Structures.panel/Coordination.pulldown/WarningsTriage.nobutton` | 432 | sin referencias; absorbida en `ModelHealthHub/lib/logic_warnings_triage.py` | muerta |
| `Structures.panel/Elements.pulldown/RebarCoverage.nobutton` | 297 | sin referencias; absorbida en `StructuralQA/lib/logic_rebar_coverage.py` | muerta |
| `Structures.panel/QA.pulldown/ClashReport.nobutton` | 511 | sin referencias de carga (solo metadatos en `lib/nosa_utils/error_registry.py`); copia en StructuralQA/lib/logic_clash_report.py | dudosa — excluida (T3.4 en curso) |
| `Structures.panel/QA.pulldown/DrawingChecker.nobutton` | 451 | sin referencias; absorbida en `StructuralQA/lib/logic_drawing_checker.py` | muerta |
| `Structures.panel/QA.pulldown/FamilyAudit.nobutton` | 435 | sin referencias; absorbida en `StructuralQA/lib/logic_family_audit.py` | muerta |
| `Structures.panel/QA.pulldown/IFCStructuralExportQA.nobutton` | 274 | sin referencias; absorbida en `StructuralQA/lib/logic_ifc_export_qa.py` | muerta |
| `Structures.panel/QA.pulldown/ScheduleImpact.nobutton` | 277 | sin referencias; absorbida en `StructuralQA/lib/logic_schedule_impact.py` | muerta |
| `Structures.panel/Quantities.pulldown/QuantificationQA.nobutton` | 799 | sin referencias; absorbida en `StructuralQA/lib/logic_quantification_qa.py` (nombre citado solo como metadato en `error_registry.py`) | muerta |
| `Structures.panel/Quantities.pulldown/RebarAuditor.nobutton` | 697 | RebarHub.pushbutton/lib/ui.py:28 | **usada** |
| `Structures.panel/Quantities.pulldown/RebarManager.nobutton` | 560 | RebarHub.pushbutton/lib/ui.py:24 | **usada** |
| `Structures.panel/Quantities.pulldown/RebarSchedule.nobutton` | 948 | RebarHub.pushbutton/lib/ui.py:26 | **usada** |
| `Structures.panel/Quantities.pulldown/StructuralBOM.nobutton` | 848 | sin referencias; absorbida en `StructuralSchedulePro/lib/logic_structural_bom.py` | muerta |

## Notas

- Las 12 usadas se cargan con `imp.load_source` desde hubs; se conservan enteras (algunas cargan también
  `ui.py` o `rules.json`, no solo `logic.py`).
- `ExportSheets.nobutton` solo se usa por el encadenado Issue Gate → Export de `IssueWorkflowHub`; el
  sucesor activo es `SheetExportHub`. Ver nota fuera de alcance en `MASTER_ROADMAP.md` (T5.2).

## Fase 2 — Borrado (aprobado y ejecutado en `577881e`)

Borrar estas 44 carpetas (19659 LOC). Excluida `ClashReport.nobutton` (T3.4).

- `NOSA.tab/Data.panel/DataTools.pulldown/ExcelSync.nobutton`
- `NOSA.tab/Data.panel/DataTools.pulldown/TypeRenamer.nobutton`
- `NOSA.tab/Data.panel/DataTools.pulldown/WorksetHealth.nobutton`
- `NOSA.tab/Data.panel/ModelCleanup.nobutton`
- `NOSA.tab/Data.panel/ProjectSetup.stack/LinkManager.nobutton`
- `NOSA.tab/Documentation.panel/Annotations.pulldown/BatchRename.nobutton`
- `NOSA.tab/Documentation.panel/Annotations.pulldown/CaseConverter.nobutton`
- `NOSA.tab/Documentation.panel/Annotations.pulldown/DimensionWalls.nobutton`
- `NOSA.tab/Documentation.panel/Annotations.pulldown/GAAutoDimension.nobutton`
- `NOSA.tab/Documentation.panel/Issue.pulldown/IssueGate.nobutton`
- `NOSA.tab/Documentation.panel/Issue.pulldown/RevisionPackageDiff.nobutton`
- `NOSA.tab/Documentation.panel/Issue.pulldown/RevisionTracker.nobutton`
- `NOSA.tab/Documentation.panel/Issue.pulldown/SheetIssueManager.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/AlignViewTitles.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/BaySections.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/ColourByParam.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/CopyViewTemplates.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/HalftoneSelection.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/LevelNavigator.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/SectionBoxer.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/ViewDependencyExplorer.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/ViewFilterBatch.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/ViewHub.nobutton`
- `NOSA.tab/Documentation.panel/Views.pulldown/ViewOrganiser.nobutton`
- `NOSA.tab/Foundations.panel/PadFootings.nobutton`
- `NOSA.tab/Foundations.panel/Survey.pulldown/CuadroReplanteo.nobutton`
- `NOSA.tab/Foundations.panel/Survey.pulldown/PileSurveyExport.nobutton`
- `NOSA.tab/Foundations.panel/WallFootings.nobutton`
- `NOSA.tab/Structures.panel/Coordination.pulldown/AnalyticalHealthCheck.nobutton`
- `NOSA.tab/Structures.panel/Coordination.pulldown/ConnectionChecker.nobutton`
- `NOSA.tab/Structures.panel/Coordination.pulldown/CoverCompliance.nobutton`
- `NOSA.tab/Structures.panel/Coordination.pulldown/FoundationLoadExtractor.nobutton`
- `NOSA.tab/Structures.panel/Coordination.pulldown/HealthScore.nobutton`
- `NOSA.tab/Structures.panel/Coordination.pulldown/LevelGridSync.nobutton`
- `NOSA.tab/Structures.panel/Coordination.pulldown/ModelSyncChecker.nobutton`
- `NOSA.tab/Structures.panel/Coordination.pulldown/ParameterDriftMonitor.nobutton`
- `NOSA.tab/Structures.panel/Coordination.pulldown/WarningsTriage.nobutton`
- `NOSA.tab/Structures.panel/Elements.pulldown/RebarCoverage.nobutton`
- `NOSA.tab/Structures.panel/QA.pulldown/DrawingChecker.nobutton`
- `NOSA.tab/Structures.panel/QA.pulldown/FamilyAudit.nobutton`
- `NOSA.tab/Structures.panel/QA.pulldown/IFCStructuralExportQA.nobutton`
- `NOSA.tab/Structures.panel/QA.pulldown/ScheduleImpact.nobutton`
- `NOSA.tab/Structures.panel/Quantities.pulldown/QuantificationQA.nobutton`
- `NOSA.tab/Structures.panel/Quantities.pulldown/StructuralBOM.nobutton`
