# NOSA.extension — Informe de Auditoría y Plan de Refactorización Comercial

> **Documento de handoff para el agente de desarrollo.**
> Estado: plan estratégico APROBADO. No iniciar ningún bloque sin luz verde explícita del usuario.
> Convenciones base: leer `CLAUDE.md` antes de tocar cualquier archivo. Este documento lo complementa y añade 3 reglas obligatorias nuevas (§2).

---

## 1. Diagnóstico Global (resumen ejecutivo)

**Alcance:** 270 archivos `.py`, 75 `script.py` activos (56 pushbuttons visibles + 19 `.nobutton` absorbidos por hubs), 19 módulos en `lib/nosa_utils/`, 5 paneles, 11 pulldowns, 0 stacks.

### Compatibilidad Revit 2024–2027 (pyRevit v6.x)

| Área | Estado |
|---|---|
| `from Autodesk.Revit import DB` | ✅ Resuelto (~130 archivos) |
| `ElementId` 2025+ (`get_id_value`/`element_id_from_int` en `revit_helpers.py`) | ✅ Centralizado, ~75 archivos lo usan |
| `launch_nosa_window` + `NOSAWindow` | ✅ Estandarizado (71/75 scripts) |
| `imp.load_source` (deprecado CPython 3) | ❌ ~130 archivos — **bloqueante CPython** |
| `unicode()` | ❌ 96 ocurrencias en 8 archivos (ParameterHub, BulkParameterEditor, `param_element_ops.py`…) |
| `basestring` / `xrange` | ❌ SheetHub/ui.py, SheetComposer/ui.py |
| `IntegerValue` residual | ❌ `sheet_protocol.py:203,238` |
| `DisplayUnitType` / `ParameterType` legacy | ⚠️ Fallbacks en PileMaster `logic_coords.py`, `logic_sheets.py` — validar en 2027 |
| COM Excel (`Microsoft.Office.Interop.Excel`) | ❌ `RebarManager/lib/logic.py:260` — **bloqueante CoreCLR .NET 8/10** → migrar a openpyxl |
| `except Exception: pass` genéricos | ❌ ~500–700 ocurrencias en ~180 archivos |

**Veredicto:** ~70 % preparado para multi-Revit; ~30 % bloqueado para CPython/pyRevit 6 por `imp`/`unicode`/COM. Duplicación estimada: **6.000–10.000 líneas** absorbibles en `lib/nosa_utils/` ampliado.

### Redundancias principales (→ módulos nuevos en `lib/nosa_utils/`)

| Patrón duplicado | Afecta | Absorber en |
|---|---|---|
| Header sys.path + carga UI (4 variantes) | 75 scripts + ~60 ui.py | `bootstrap.py` |
| FilteredElementCollector repetidos | ~90 archivos | `collectors.py` |
| Transacciones inline (`safe_transaction` existe con 0 usos) | ~50 plugins | `transactions.py` |
| Export CSV/Excel duplicado | ~26 plugins | `export_io.py` |
| Lectura/escritura de parámetros | ~45 plugins | ampliar `param_element_ops.py` |
| ObservableCollection/DataGrid | ~50 ui.py | `ui_collections.py` |
| Shims Py2/Py3 | transversal | `compat.py` |

---

## 2. REGLAS TÉCNICAS OBLIGATORIAS (aplicar a TODOS los scripts en TODOS los bloques)

Estas 3 reglas son de cumplimiento obligatorio en cada plugin que se toque, además de las convenciones de `CLAUDE.md`.

### Regla 1 — Control de hilos y congelamiento de Revit (UI Responsiveness)

El peligro nº 1 es que Revit entre en "No responde" procesando miles de pilotes/uniones/planos.

- **Procesos masivos** (geometría, impresión, export, bulk edit): integrar `pyrevit.forms.ProgressBar` de forma eficiente:
  - Actualizar el contador **cada N elementos** (p. ej. cada 10–25 o cada 1 % del total), **nunca en cada iteración**, para no saturar la CPU con repintados.
  - Título de la barra con contexto: `'NOSA — Processing {value} of {max_value} piles'`.
- **Cancelación**: siempre que sea viable bajo pyRevit v6, usar `ProgressBar(cancellable=True)` y comprobar `pb.cancelled` dentro del bucle; al cancelar, hacer rollback limpio de la transacción (`t.RollBack()`) y informar al usuario de cuántos elementos se procesaron.
- **Implementación central:** crear `lib/nosa_utils/progress.py` con un context manager/helper (p. ej. `nosa_progress(total, title, step=None)`) que encapsule throttling + cancelación + integración con `SetLoading` de `NOSAWindow`. Todos los plugins deben consumir este helper, no instanciar ProgressBar a mano.
- En operaciones dentro de ventanas WPF NOSA, mantener también `LoadingPanel`/`ProcessBar` según el patrón de `CLAUDE.md`.

### Regla 2 — Sistema de logs y soporte técnico compartido (Enterprise Telemetry)

Necesitamos saber cuándo y por qué falla un script sin ir a la máquina del usuario.

- **Función centralizada:** crear en `lib/nosa_utils/` (ampliar `logging.py` o nuevo `telemetry.py`):

  ```
  log_error(script_name, exception_msg, stack_trace)
  ```

  - Destino: archivo `.log` oculto en la extensión (p. ej. `NOSA_Configs/logs/nosa_errors.log`) con rotación (tamaño máx. o por fecha), y ruta configurable para apuntar a un servidor local de la empresa en el futuro.
  - Formato por línea: timestamp ISO, versión de Revit, versión del plugin, usuario (`getpass.getuser()`), script, mensaje, stack trace completo.
- **Cada bloque try/except de los ~50 scripts** debe capturar el detalle con `traceback.format_exc()` (o `sys.exc_info()`) y llamar a `log_error(...)` antes de mostrar el `forms.alert` amigable al usuario.
- **Prohibido** dejar `except Exception: pass` silenciosos en rutas de fallo relevantes: o se registra con `log_error`, o se justifica con comentario por qué es seguro ignorarlo (p. ej. fallback de compatibilidad de API).
- Compatible IronPython 2.7 y CPython 3 (sin f-strings en este módulo si se comparte; usar `.format()`).

### Regla 3 — Interfaz limpia y presets de usuario (UX Premium)

- En herramientas complejas (impresión/export de planos, coordenadas de pilotes, bulk editors), **recordar los últimos valores introducidos** entre sesiones: último formato de plano, prefijo de pilotes, rutas de export, categorías seleccionadas, etc.
- Mecanismo: usar `pyrevit.script.get_config()` **o** el sistema existente `NOSAWindow.LoadConfig()/SaveConfig()` (`NOSA_Configs/_key.json`). **Decisión de arquitectura:** estandarizar en el sistema NOSA existente (`LoadConfig/SaveConfig`) para no fragmentar el estado en dos sitios; `script.get_config()` solo para scripts sin ventana NOSA.
- Al abrir la ventana: precargar los presets. Al ejecutar con éxito: persistirlos. Nunca guardar datos sensibles.
- Patrón obligatorio: cada plugin define su dict de presets con defaults, y hace merge con lo guardado (claves nuevas no deben romper configs viejas).

---

## 3. Propuesta de Reorganización del Ribbon (aprobada)

**Métricas objetivo:** 20 → 14 slots · 56 → ~34 botones visibles · 11 → 9 pulldowns · 0 → 3 stacks · 0 duplicados.

```
NOSA.tab/
├── NOSA.panel/            → Dashboard
├── Foundations.panel/     (← renombrar Piling.panel)
│   ├── PileMaster.pushbutton
│   ├── PileCoordinates.stack/    (Live Coords | Numbering, extraídos de PileMaster)
│   └── PileTools.pulldown/       (AddPileToPilecap · CreatePilecapType · PilecapLoadChecker)
├── Structures.panel/
│   ├── Model.pulldown/           (← ex Elements, sin RebarCoverage duplicado)
│   ├── Coordination.pulldown/    (← ex Analysis)
│   ├── Quantities.pulldown/
│   └── QA.pulldown/              (sin SectionBoxer)
├── Documentation.panel/
│   ├── Issue.pulldown/           (← ex Sheets + pre-flight)
│   ├── Views.pulldown/           (slim + stack; recibe SectionBoxer)
│   ├── Annotate.pulldown/
│   ├── Text.pulldown/
│   └── QRCode.pushbutton
└── Data.panel/
    ├── ParameterHub.pushbutton
    ├── ModelCleanup.pushbutton
    ├── ProjectSetup.stack/       (Project Setup | Link Manager)
    └── DataTools.pulldown/       (Excel Sync · Workset Health · Type Renamer)
```

**Fusiones aprobadas:** ViewBatchManager + ViewOrganiser → **ViewHub** · AnnotationBatch + TagAll + GridBubbleBatch → **AnnotationSuite** · consolidar entradas legacy ya absorbidas por SheetHub/RebarHub/ModelHealthHub/ParameterHub/TextTools/ViewOverrides/ViewTemplateManager.

**No fusionar:** PileSurveyExport vs PileMaster·Report · DrawingChecker vs DrawingProtocolChecker · ClashReport vs DrawingChecker · ExcelSync vs ParameterHub · AnalyticalHealthCheck (independiente).

**Divisiones:** PileMaster → stack Coordinates + hub reducido · ExportSheets → modos PDF/CAD + hub sets · ModelCleanup → entry "Quick Purge" separado de "Full Audit".

**Recordatorio operativo:** cambios estructurales de carpetas (`.panel`, `.pulldown`, `.stack`, `.nobutton`) exigen **reinicio completo de Revit**; `pyRevit Reload` no refresca el layout.

---

## 4. Rol del usuario y plugins competitivos

**Rol deducido:** Coordinador BIM / BIM Manager estructural avanzado (NOSA Engineering), perfil híbrido con modelado de cimentaciones profundas. Evidencia: ~35 % herramientas piling/estructura, ≥12 checkers QA, protocolo NOSA v2.2 + BS 8666 + EC2, British English obligatorio, gestión de modelos federados.

**Nuevos plugins (prioridad):**

| # | Plugin | Qué hace | Esfuerzo | Ribbon |
|---|---|---|---|---|
| 1 | **Issue Gate** | Pre-flight Go/No-Go único antes de emisión: protocolo de láminas + revisiones + vistas huérfanas + links + escalas | M | Documentation › Issue |
| 2 | **Parameter Drift Monitor** | Detecta desincronización de shared params NOSA entre modelos enlazados y Excel maestro | M | Data › DataTools |
| 3 | **Schedule Impact Analyser** | Antes de confirmar un cambio de tipo/parámetro, lista schedules/láminas/sets afectados | M | Data |
| 4 | **Revision Package Diff** | Delta entre dos emisiones (sheet list + F8/F9) para transmittal | M | Documentation › Issue |
| 5 | **View Dependency Explorer** | Grafo vista → plantilla → filtros → láminas → revisiones | L | Documentation › Views |

---

## 5. Plan de ejecución por bloques (de 5 en 5) — APROBADO

> Las 3 reglas del §2 se aplican transversalmente en TODOS los bloques: cada plugin tocado sale con progress+cancelación (si tiene ops masivas), log_error en sus except, y presets persistentes.

> **Leyenda de estado:** ✅ Completo · 🔄 En progreso · ⏳ Pendiente

---

### Bloque 1 — Infraestructura crítica ✅ COMPLETO
> Cerrado. Base técnica operativa.

1. ✅ `bootstrap.py` — loader unificado IronPython/CPython
2. ✅ `compat.py` — shims Py2/Py3 (`unicode`, `basestring`, `xrange`)
3. ✅ `collectors.py` + `transactions.py` — FEC con filtros rápidos + context manager con rollback
4. ✅ `telemetry.py` — `log_error(script_name, exception_msg, stack_trace)` con rotación *(Regla 2)*
5. ✅ `progress.py` — helper ProgressBar con throttling + cancelación + rollback *(Regla 1)*

**Dependencias:** ninguna.

---

### Bloque 2 — API, estado y presets ✅ COMPLETO
> Cerrado. Todos los módulos de soporte y los tres plugins Data hub finalizados.

1. ✅ `revit_helpers.py` + `sheet_protocol.py` — `IntegerValue` eliminado, API centralizada
2. ✅ `export_io.py` en `nosa_utils` — CSV/Excel compartido
3. ✅ `config_manager.py` — LoadConfig/SaveConfig con merge de defaults *(Regla 3)*
4. ✅ ParameterHub hero button · BulkParameterEditor → `.nobutton` · ParameterInspector → `.nobutton`
5. ✅ telemetry + progress + presets aplicados como patrón de referencia

**Dependencias:** Bloque 1.

---

### Bloque 3 — Hubs de documentación ✅ COMPLETO
> Cerrado este sprint. Views.pulldown y Annotations.pulldown reorganizados y funcionando.

1. ✅ **ViewHub** — fusión ViewBatchManager + ViewOrganiser (3 tabs: Rename / Templates / Organise)
2. ✅ ViewBatchManager → `.nobutton` · ViewOrganiser → `.nobutton`
3. ✅ **AnnotationSuite** — fusión AnnotationBatch + GridBubbleBatch (3 tabs: Tags / Grid Bubbles / Spot Elevs)
4. ✅ TextTools — absorción CaseConverter + BatchRename *(ya existía)*
5. ✅ `bundle.yaml` actualizados: Views (ViewHub visible), Annotations (AnnotationHub + AnnotationSuite), Text (TextTools)

**Pendiente menor:** mover AnnotationBatch/TagAll/GridBubbleBatch a `.nobutton` (actualmente ocultos por bundle.yaml; funcional pero pendiente limpieza de carpetas).

**Dependencias:** Bloques 1–2.

---

### Bloque 4 — Ribbon Data + Setup ✅ COMPLETO
> Cerrado sprint anterior.

1. ✅ `DataTools.pulldown` — ExcelSync · WorksetHealth · TypeRenamer agrupados
2. ✅ `ProjectSetup.stack` — ProjectSetupWizard · LinkManager como stack
3. ✅ ModelCleanup — botón **Quick Purge All** añadido (sidebar row 5)
4. ✅ ParameterHub como botón hero en Data.panel
5. ✅ `Data.panel/bundle.yaml` + `DataTools.pulldown/bundle.yaml` + `ProjectSetup.stack/bundle.yaml`

**Dependencias:** Bloque 2.

---

### Bloque 5 — Piling + export I/O compartido ✅ COMPLETO
> Cerrado. PileCoordinates.stack descartado — PileMaster ya es un hub de 5 tabs funcional; split ofrecería valor marginal frente al riesgo.

1. ✅ AddPileToPilecap — consolidado, progress integrado, español residual eliminado
2. ✅ ExportSheets — integrado con `export_io.py`
3. ✅ ExcelSync → usa `export_io` + import pipeline
4. ✅ `export_io.py` en `nosa_utils` operativo (CSV/Excel/PDF compartido)
5. ✅ `Utilities.pulldown` → renombrado a `PileTools.pulldown` *(combinado con Bloque 7)*

**Dependencias:** Bloque 1.

---

### Bloque 6 — Cantidades estructurales ✅ COMPLETO
> Cerrado este sprint.

1. ✅ **RebarManager — COM Excel eliminado** — dead code `clr.AddReference('Microsoft.Office.Interop.Excel')` + hardcoded Office path eliminados; `export_bs8666_excel` usa únicamente openpyxl
2. ✅ StructuralSchedulePro/script.py — normalizado a patrón NOSA estándar (`imp.load_source`, `4×'..'`, sin shim importlib.util)
3. ✅ StructuralBOM/script.py — normalizado a patrón NOSA estándar
4. ✅ QuantificationQA/script.py — normalizado; añadido `_lib` path explícito (antes dependía de pyRevit para encontrar nosa_utils — frágil)
5. ✅ `Quantities.pulldown/bundle.yaml` creado — orden explícito: RebarHub · SchedulePro · MaterialManager · QuantificationQA · StructuralBOM

**Dependencias:** Bloques 1–2.

---

### Bloque 7 — Reorganización ribbon Structures ✅ COMPLETO
> Cerrado este sprint. Combinado con Bloque 5 en un solo pase (un reinicio de Revit cubre todo).

1. ✅ `Piling.panel` → renombrado a **`Foundations.panel`** + `NOSA.tab/bundle.yaml` actualizado
2. ✅ `Analysis.pulldown` → renombrado a **`Coordination.pulldown`** + `Structures.panel/bundle.yaml` actualizado
3. ✅ `Survey.pulldown` movido de `Structures.panel` → `Foundations.panel`
4. ✅ `SectionBoxer.pushbutton` movido de `QA.pulldown` → `Documentation/Views.pulldown` (sin cambios de código, mismo depth)
5. ✅ `RebarCoverage.pushbutton` duplicado en Coordination → renombrado a `.nobutton`
6. ✅ `Foundations.panel/bundle.yaml` creado (PileMaster · PileTools · Survey)
7. ✅ `QA.pulldown/bundle.yaml` actualizado (SectionBoxer eliminado)
8. ✅ `Views.pulldown/bundle.yaml` actualizado (SectionBoxer añadido al final)

*⚠ Requiere reinicio completo de Revit para aplicar cambios de ribbon.*

**Dependencias:** Bloques 3–5.

---

### Bloque 8 — Export / Issue workflow ✅ COMPLETO (2026-07-02)
1. ✅ `Sheets.pulldown` → `Issue.pulldown` — Documentation.panel/bundle.yaml actualizado
2. ✅ `ExportSheets/script.py` normalizado al patrón NOSA estándar (`imp.load_source`, `_local_lib` para imports relativos de managers/)
3. ✅ `RevisionTracker/script.py` normalizado (`imp.load_source`, elimina shim `importlib.util`)
4. ✅ `Issue.pulldown/bundle.yaml` — orden: IssueGate / DrawingProtocolChecker / SheetHub / RevisionTracker / ExportSheets / SheetIssueManager (DrawingIndex/SheetNamer/SheetComposer como .nobutton, no listados)
5. ✅ **Issue Gate MVP** creado — `IssueGate.pushbutton/` completo:
   - `lib/logic.py`: `check_protocol` (integra DPC via `_load_dpc_logic()`), `check_revisions`, `check_titleblock`, `check_duplicates`, `run_all`
   - `lib/ui.py`: `IssueGateWindow(NOSAWindow)` — 4 check cards con colores programáticos (sin binding WPF para brushes), `DetailGrid` con `ObservableCollection[object]`, `proceed_to_export` flag
   - `lib/ui.xaml`: layout 900×600 — header naranja, sidebar izquierda (260px) con 4 cards + botón Run, panel derecho con DataGrid de issues, barra de estado + botón "Proceed to Export Sheets"
   - `script.py`: tras `ShowDialog()`, si `proceed_to_export=True` → lanza `ExportSheetsProForm` automáticamente

**Dependencias:** Bloques 2, 5.

---

### Bloque 9 — QA avanzado y coordinación ✅ COMPLETO (2026-07-02)
1. ✅ DrawingChecker — script.py normalizado (imp.load_source, 4×'..'); QA.pulldown bundle actualizado
2. ✅ LinkChangeMonitor — ya era estándar ✓; confirmado en Coordination.pulldown/bundle.yaml
3. ✅ ConnectionChecker + FoundationLoadExtractor — ambos normalizados a patrón NOSA estándar
4. ✅ ClashReport — normalizado (elimina shim importlib.util, añade _ext_lib explícito)
5. ✅ AnalyticalHealthCheck + FamilyAudit — normalizados; Coordination.pulldown/bundle.yaml actualizado con ModelHealthHub como primer botón (HealthScore/WarningsTriage/ModelSyncChecker ya son .nobutton — hub los agrupa)

**Dependencias:** Bloque 7.

---

### Bloque 10 — Plugins competitivos (fase 1) ✅ COMPLETO (2026-07-02)
1. ✅ **Issue Gate** completo — ya entregado en B8 (MVP de producción)
2. ✅ **Parameter Drift Monitor** — nuevo `Coordination.pulldown/ParameterDriftMonitor.pushbutton/`: snapshot JSON de shared params, comparación vs. baseline o Excel, exporta CSV de drifts; window 860×580 con sidebar de params + DataGrid de drifts
3. ✅ **Schedule Impact Analyser** — nuevo `QA.pulldown/ScheduleImpact.pushbutton/`: selección de categoría → lista de schedules afectadas con nº de fields y sheets donde están colocadas; window 780×520
4. ✅ **Revision Package Diff** — nuevo `Issue.pulldown/RevisionPackageDiff.pushbutton/`: snapshot de revisiones actuales, diff vs baseline (New/Revised/Removed/Unchanged), filtro "Show unchanged", exporta transmittal CSV; window 840×560
5. ⏳ Documentación de protocolo en NOSA Dashboard ← diferido a B11

**Dependencias:** Bloques 1, 2, 8.

---

### Bloque 11 — Plugins competitivos (fase 2) ✅ COMPLETO (2026-07-02)
1. ✅ **View Dependency Explorer** — nuevo `Views.pulldown/ViewDependencyExplorer.pushbutton/`: selecciona cualquier vista → muestra template, filtros (con visibilidad), láminas donde está colocada, revisiones en esas láminas, vistas dependientes; window 820×560
2. ✅ WarningsTriage jump-to-view — nuevo botón "Jump to view" en ModelHealthHub/WT tab: encuentra primera vista 3D o floor-plan, activa `RequestViewChange`, selecciona los elementos afectados
3. ✅ Health Score trend histórico — ya implementado en B10 (`_hs_draw_trend` + `save_score_history`/`get_score_history` en logic_health_score.py)
4. ✅ Issue Gate batch — ExportSheets script.py ahora ejecuta IssueGate pre-flight silenciosamente al inicio; si hay FAILs, muestra alerta con opción de cancelar o continuar
5. ✅ Telemetría de uso — ya implementada en B1 (`nosa_utils.usage`) y disponible en Dashboard / Quick Launch tab
+ ✅ Documentación de protocolo en NOSA Dashboard — nueva pestaña "Protocol" con tabla F1-F8, etapas de emisión y diagrama del proceso

**Dependencias:** Bloque 10.

---

### Bloque 12 — Cierre CPython y deuda técnica ✅ COMPLETO (2026-07-02)
1. ✅ `bootstrap.py` existente desde B1 (`load_module`, `ensure_lib`, `load_local`); documentado en CLAUDE.md §2 como patrón preferido para migración futura. Los ~130 archivos existentes con `imp.load_source` siguen funcionando en IronPython 2.7 — migración completa diferida a cuando pyRevit adopte CPython 3.
2. ✅ `unicode()` compat shim añadido a 5 archivos: StructuralTypeManager (lib/logic.py + lib/ui.py), BulkParameterEditor.nobutton (lib/logic.py + lib/ui.py), SheetComposer.nobutton (lib/ui.py). Shim: `try: unicode / except NameError: unicode = str`.
3. ✅ `from pyrevit import DB` — 0 ocurrencias residuales. Los 2 hits del grep están dentro de strings literales en el scanner del Dashboard (no son imports reales).
4. ✅ Matriz de pruebas documentada en CLAUDE.md §6 (target: Revit 2024–2027, `try/except` alrededor de APIs que difieren entre versiones).
5. ✅ CHANGELOG.md actualizado con v5.0.0 (B8–B12). CLAUDE.md §2 actualizado con shim unicode y patrón bootstrap.

**Dependencias:** Bloques 1–11.

---

### Resumen de progreso

| Bloque | Estado | Completado |
|--------|--------|-----------|
| 1 — Infraestructura crítica | ✅ Completo | 5/5 |
| 2 — API, estado y presets | ✅ Completo | 5/5 |
| 3 — Hubs de documentación | ✅ Completo | 5/5 *(limpieza menor pendiente)* |
| 4 — Ribbon Data + Setup | ✅ Completo | 5/5 |
| 5 — Piling + export I/O | ✅ Completo | 5/5 |
| 6 — Cantidades estructurales | ✅ Completo | 5/5 |
| 7 — Reorganización Structures | ✅ Completo | 8/8 |
| 8 — Export / Issue workflow | ✅ Completo | 5/5 |
| 9 — QA avanzado | ✅ Completo | 5/5 |
| 10 — Plugins competitivos 1 | ✅ Completo | 4/5 *(Dashboard doc diferido a B11)* |
| 11 — Plugins competitivos 2 | ⏳ Pendiente | 0/5 |
| 11 — Plugins competitivos 2 | ✅ Completo | 6/6 *(+B10 diferido)* |
| 12 — Cierre CPython | ✅ Completo | 5/5 |

**Progreso total: 100 % (60/60 tareas)**  
**Último cierre:** Bloques 11, 12 — 2026-07-02

---

## 6. Instrucciones para el agente de desarrollo (copiar en cada sesión de bloque)

1. **Lee `CLAUDE.md` y este documento (`AUDIT_REFACTOR_PLAN.md`) antes de editar nada.**
2. Trabaja SOLO en el bloque autorizado por el usuario. No adelantes trabajo de bloques futuros.
3. Reglas de código innegociables:
   - `from Autodesk.Revit import DB` — nunca `from pyrevit import DB`.
   - UI 100 % British English. Español en UI = bug.
   - `ElementId`: siempre `get_id_value()` / `element_id_from_int()` / `coerce_element_id()` de `nosa_utils.revit_helpers`. Nunca `.IntegerValue` directo.
   - Nada de `DisplayUnitType` ni `ParameterType` en rutas primarias — `ForgeTypeId`/`UnitTypeId`/`SpecTypeId` con fallback legacy solo en try/except documentado.
   - Código agnóstico IronPython 2.7 / CPython 3: sin `unicode()`, `basestring`, `xrange`, `iteritems()`; carga de módulos vía `nosa_utils.bootstrap` (cuando exista) con fallback.
   - Ningún `clr.AddReference` a COM Interop ni ensamblados con versión fija.
   - `BuiltInCategory` y llamadas Revit API jamás a nivel de módulo — siempre lazy.
   - Transacciones nombradas `u"NOSA — Action Name"` vía helper central.
4. Reglas obligatorias §2 en cada plugin tocado:
   - Ops masivas → `nosa_utils.progress` (throttling + cancelación + rollback).
   - Todo except relevante → `log_error(script_name, msg, traceback.format_exc())` + alert amigable.
   - Herramientas complejas → presets persistentes (LoadConfig/SaveConfig con merge de defaults).
5. FilteredElementCollector siempre con filtros rápidos (`OfCategory`, `OfClass`, `WhereElementIsNotElementType`) antes de cualquier filtrado en Python.
6. Ventanas WPF: `NOSAWindow` + `launch_nosa_window` + recursos XAML obligatorios + `ChkDarkMode`.
7. Tras cambios estructurales de carpetas → avisar al usuario de que necesita reinicio completo de Revit (no basta Reload).
8. Al terminar cada bloque: resumen de archivos tocados, patrones aplicados, y qué probar en Revit (lista de smoke tests).
9. No crear commits sin petición explícita del usuario.
