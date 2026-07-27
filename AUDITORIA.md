# Auditoría — NOSA.extension

Fecha original: 2026-07-27 (contra un worktree de auditoría, ~39 pushbuttons)
**Reconciliada: 2026-07-27, misma tarde, contra el disco real (`main`, ~88 plugins) — ver sección 0-BIS.**
Alcance original: `NOSA.tab/` (5 paneles, 39 pushbuttons, 8 pulldowns) + `lib/nosa_utils/` + `lib/pilecap_utils/`
Metodología original: lectura completa de los 150 archivos `.py` de la extensión (4 agentes en paralelo, uno por panel, más revisión directa de la librería compartida), verificando cada hallazgo crítico con `grep` antes de incluirlo aquí.

---

## 0-BIS. Reconciliación contra el disco real (2026-07-27)

Esta auditoría se hizo contra un worktree que reflejaba el último commit (`e292a4c`), pero el disco real (`NOSA.extension`, rama `main`) tenía sin commitear una reorganización grande de ribbon (documentada en `AUDIT_REFACTOR_PLAN.md`, ~60 tareas en 12 bloques, autoinformado como 100% completo) que renombró paneles, fusionó ~20 pushbuttons en hubs, y creó infraestructura compartida nueva (`bootstrap.py`, `compat.py`, `collectors.py`, `transactions.py`, `telemetry.py`, `progress.py`, `export_io.py`, `nosa_utils.solids`). Un informe de solo-lectura posterior (`INFORME_FINAL.txt`, 2026-07-02) encontró 5 pendientes.

**Proceso de reconciliación**: checkpoint commit del disco real (`88cf14c`) + verificación con grep/lectura directa de cada hallazgo de este documento contra las nuevas rutas, usando 2 agentes en paralelo (Data.panel+lib, Documentation+Structures+Foundations) más verificación personal de los 5 hallazgos de `INFORME_FINAL.txt` y de los ítems de Fase 0 del `PLAN_MEJORA.md`.

### Resultado de los 5 hallazgos de INFORME_FINAL.txt

| # | Hallazgo | Estado tras reconciliación |
|---|---|---|
| 1 | DMU roto — `logic_dmu.py` apuntaba a `Piling.panel` | **YA CORREGIDO.** `_LIB_DIR` (logic_dmu.py:40-44), `startup.py:_PILE_LIB`, y `logic_coords.py` están todos consistentes con `Foundations.panel`. Alguien lo arregló después del 2 de julio sin actualizar este informe. |
| 2 | ExportSheets pre-flight silencioso | **INCONCLUSO / matiz** — `script.py` actual solo tiene 22 líneas, sin la lógica de pre-flight descrita; no se encontró integración con IssueGate en `lib/ui.py` tampoco, pese a que `AUDIT_REFACTOR_PLAN.md` Bloque 11.4 dice que sí existe. El bug original en `config.py` (enums `DB.*` a nivel de clase + `ensure_dirs()` al importar) **sigue vigente** — ver C5-bis abajo. |
| 3 | Config en dos rutas (`config_manager.py` vs `base_window.py`) | **YA CORREGIDO.** Ambos apuntan hoy a la misma carpeta. (Una *tercera* ruta, `ui_helpers.ConfigHelper`, sigue divergente pero está inerte — 0 llamadas en todo `NOSA.tab`.) |
| 4 | RebarCoverage duplicado (Elements + Coordination.nobutton) | **YA CORREGIDO** — con matiz: no quedó como `.nobutton` sino como pushbutton visible renombrado `CoverCompliance.pushbutton` (EC2 exposure-class check), distinto del `RebarCoverage.pushbutton` de Elements.pulldown. Resultado razonable, pero `AUDIT_REFACTOR_PLAN.md` Bloque 7.5 describe algo que no es literalmente lo que pasó. |
| 5 | Carpeta huérfana `Sheets.pulldown/DrawingIndex` | **PARCIALMENTE VIGENTE** — ya está oculta como `.nobutton` (segura), pero la carpeta muerta sigue sin borrarse. |

### Falsos positivos confirmados en `AUDIT_REFACTOR_PLAN.md` (autoinformado 100%, no lo es)

1. **§3 / Bloque 7.2** — dice `Elements.pulldown → Model.pulldown`: falso, `Structures.panel/bundle.yaml` sigue diciendo literalmente `Elements`. (`Analysis → Coordination` y `Piling → Foundations`, en cambio, sí ocurrieron de verdad.)
2. **Bloque 3** — marca "ViewHub — fusión ViewBatchManager + ViewOrganiser" como ✅ completo: `ViewHub.pushbutton` es hoy `ViewHub.nobutton`, fuera del ribbon y de `bundle.yaml`. La gestión de vistas activa vive en `ViewManager.pushbutton`/`ViewTemplateManager.pushbutton`, plugins no documentados en el plan.
3. **Bloque 5/11.4** — dice que ExcelSync usa `export_io.py` y que ExportSheets ejecuta el pre-flight de IssueGate: ninguna de las dos cosas se encontró en el código actual (`export_io.py` solo tiene 1 consumidor real en todo el árbol: `ScheduleImpact.pushbutton`).

**Conclusión práctica: no os fiéis del ✅ de `AUDIT_REFACTOR_PLAN.md` sin verificar** — varias tareas están marcadas completas sin estarlo del todo, mientras que paradójicamente 4 de los 5 hallazgos de `INFORME_FINAL.txt` (que parecía el documento "malas noticias") ya estaban resueltos. La única forma fiable de saber el estado real de algo en este código es grep/lectura directa, no ninguno de los dos documentos de seguimiento.

### Hallazgos propios reconciliados — resumen ejecutivo

De ~55 hallazgos de FASE 1-3 rastreados contra el disco real:
- **~14 YA CORREGIDOS** por el refactor (config unificada, `doc`/`uidoc` de pilecap_utils, DMU, `_instance_count` O(N²) de FamilyAudit, `get_id_value` centralizado 7/7, RevisionTracker ahora gestiona `DB.Revision` real, WaffleSlab título+NOSAWindow, StructuralTypeManager shim unicode, autoría uniformada, transacciones "NOSA — " en su mayoría, bubble bug de grids, ExportScheduleToExcel absorbido sin reproducir su bug, ParameterInspector CSV, `Foundations.panel`/`PileTools.pulldown` renombrados).
- **~24 VIGENTES**, misma naturaleza de bug, casi siempre en una ruta nueva: `DB.ICollection` (3 archivos — **corregido en esta sesión, ver Nivel 1**), arc-dimension count (movido a AnnotationHub — **corregido en esta sesión**), `_log_debug` no-op de ClashReport, `config.py` de ExportSheets con API a nivel de módulo, FEC sin filtro/en bucle (ConnectionChecker, MaterialManager, RebarCoverage, TagAll, PilecapLoadChecker), geometría duplicada (parcial — ClashReport ya usa `nosa_utils.solids` nuevo, ConnectionChecker/ElementJoin/WaffleSlab siguen 100% locales), config fragmentada en AddPileToPilecap (ahora híbrida: usa `ConfigManager` Y `NOSAWindow.LoadConfig` a la vez), `point_in_face` con `NameError` latente, ElementJoin/SmartJoin sin unificar, CenterBeamToColumn sigue sin NOSAWindow/lib, PilecapLoadChecker (matiz: docstring ya corregido pero quedó desactualizado en sentido inverso — **corregido en esta sesión**), QRCode auto-pip-install (**corregido en esta sesión**), `ui_helpers.ConfigHelper` con ruta incorrecta (inerte, 0 llamadas), duplicación de colector "vistas sin plantilla" (empeoró: 8 sitios en 5 archivos, antes 6) y de "aplicar plantilla" (empeoró: 4 sitios, antes 2).
- **~2 hallazgos NUEVOS/empeorados** descubiertos solo en la reconciliación: `lib/nosa_utils/__init__.py` pasó de 5 a **~20 imports eager** de API de Revit (el problema no se resolvió, creció); `export_io.py`/`pilecap_utils`/`nosa_utils.solids`/`bootstrap.py` existen y están bien construidos pero prácticamente nadie los usa (adopción real: 1/88, 0/88, 1/88, 0/155 respectivamente) — la deuda de infraestructura-construida-pero-no-adoptada de `INFORME_FINAL.txt` EJE A se confirma y es peor de lo que ese informe estimaba.
- **~9 OBSOLETOS** (archivo/feature ya no existe): DiRootsHub, `_demo_ec_levels.py` de QRCode, ExportScheduleToExcel como archivo propio, sys.path muerto hacia pilecap_utils en CreatePilecapType, y varios `.nobutton` que ya no son alcanzables por ningún código activo.

### Riesgo multi-versión (Revit 2024-2027 / IronPython-CPython) — hallazgos transversales

- **`imp.load_source` universal**: 155 archivos lo usan, **0 usan `nosa_utils.bootstrap`** (existe desde Bloque 1, código muerto en la práctica). Bloqueante confirmado para una futura migración a pyRevit-CPython puro; no urgente mientras pyRevit siga soportando el motor IronPython 2.7, pero cualquier código NUEVO debe usar `importlib`/`nosa_utils.bootstrap` por instrucción explícita del usuario.
- **`DisplayUnitType`/`ParameterType` legacy**: fallbacks correctamente encadenados tras `UnitTypeId`/`SpecTypeId` en `PileMaster/lib/logic_coords.py:190,380,384` y `logic_sheets.py:103,106` — riesgo medio, sin validar aún contra Revit 2027 según pide el propio `AUDIT_REFACTOR_PLAN.md`.
- **`ElementId`**: centralizado correctamente vía `get_id_value()` en el 100% de los sitios revisados — riesgo bajo.
- **`from pyrevit import DB`**: 0 ocurrencias reales confirmadas — riesgo bajo.
- **`unicode()`/`basestring`/`xrange`**: shim presente donde se verificó (StructuralTypeManager); no se auditó el 100% de los ~8 archivos que `AUDIT_REFACTOR_PLAN.md` dice que lo necesitan.
- **COM Excel**: confirmado eliminado de RebarManager (openpyxl). No se encontró ningún `clr.AddReference` a Office/COM nuevo en las áreas revisadas.

### Ejecutado en esta sesión (Nivel 1 de `PLAN_MEJORA.md`, ver ese documento para detalle y commits)

Fase 1, Fase 3, y las 3 decisiones de Fase 0 (docstring PilecapLoadChecker, confirmación QRCode; RevisionTracker no necesitó cambio). Fases 2, 4, 5 y el DMU de PileMaster confirmados ya corregidos, sin acción necesaria.

---

## 0. Notas de alcance — antes de leer el resto

- **El panel no se llama "Foundations"**: la carpeta real es `NOSA.tab/Piling.panel/`. En ningún sitio del código (título de botón, docstring, XAML) aparece la palabra "Foundations". Si el nombre "Foundations" viene de una convención que queréis adoptar, es un rename pendiente, no un hecho ya existente.
- **No hay 379 archivos Python en la extensión** — hay **150**. `NOSA.tab/` tiene 116, `lib/` tiene 23 más. El resto de `.py` del repo (11) vive en `Projects/Exports/` — scripts Dynamo/CPython sueltos, sin relación con los pushbuttons, no forman parte del ribbon. Si el número 379 venía de otra fuente, probablemente incluya `NOSA_NEW.extension` (que no se ha tocado, como pediste) o esté desactualizado.
- **Ningún bundle usa `bundle.yaml`** — los 39 pushbuttons se configuran solo con `script.py` (docstring + `__title__`/`__author__`/`__doc__`). No es un problema, solo una aclaración frente al contexto técnico que dabas.
- **Ya existe planificación previa en la raíz** que se solapa con esta auditoría: `PHASE1_TASKS.md`, `NOSA_TASKS_DIROOTS_UI_BACKLOG.md`, `QA_CHECKLIST.md`, `ERROR_REGISTRY.md`, `DIROOTS_TOOLS_CHECKLIST.md`. Los referencio en vez de duplicarlos; `PLAN_MEJORA.md` los tiene en cuenta.
- `error_registry.py` referencia un plugin `LevelNavigator` que **no existe** en el árbol actual — estaba planificado en `PHASE1_TASKS.md` (bloque B6.A) pero nunca se llegó a construir (o se retiró). Referencia obsoleta, no bug.

---

## FASE 1 — Arquitectura

### 1.1 Mapa de la extensión

| Panel (carpeta real) | Pulldowns | Pushbuttons | Notas |
|---|---|---|---|
| `Data.panel` | — | BulkParameterEditor, DiRootsHub, ExcelSync, ExportScheduleToExcel, FamilyAudit, ParameterInspector | Todos en inglés, todos con icono |
| `Documentation.panel` | Annotations, Sheets, Text, Views | 13 en total (ver 1.2) | Pulldown "Views" sobrecargado (7 herramientas) |
| `Piling.panel` | Utilities | PileMaster, AddPileToPilecap, CreatePilecapType, PilecapLoadChecker | `lib/pilecap_utils/` apenas se usa aquí (ver 1.3) |
| `Structures.panel` | Analysis, Elements, Quantities | 11 en total | `ElementJoin` se llama internamente "SmartJoin" |
| `NOSA.Panel` | — | NOSA.pushbutton | Dashboard de solo lectura (inventario + info), no lanzador |

### 1.2 Convención de ventana (NOSAWindow) — adopción real

De los ~30 pushbuttons con ventana WPF, **9 no extienden `NOSAWindow`** (`lib/nosa_utils/base_window.py`) y reimplementan tema/config a mano con `forms.WPFWindow` directo:

`PileMaster`, `DimensionWalls`, `TagAll`, `ExportSheets`, `AlignViewTitles`, `CopyViewTemplates`, `QRCode` (Documentation/Piling), más `CenterBeamToColumn` y `WaffleSlab` que no tienen ni siquiera carpeta `lib/` (script monolítico).

Consecuencia real, no teórica: `PileMaster.pushbutton/lib/ui.py:32` (`class PileMasterWindow(forms.WPFWindow)`) nunca aplica dark mode ni persiste tamaño de ventana — el XAML fija colores de tema claro a mano. Es el mismo patrón, más leve, que `DiRootsHub.pushbutton/lib/ui.xaml:6-9`, donde faltan 2 de los 5 recursos de color (`PanelColor`, `BorderColor`) y `NOSAWindow.ApplyTheme()` aborta a mitad de la asignación al no encontrarlos.

### 1.3 Librerías compartidas — quién las usa de verdad

- **`lib/nosa_utils/geometry.py` y `revit_helpers.py`**: bien adoptadas (18 archivos las importan). Patrón sano.
- **`lib/pilecap_utils/`** (~1000 líneas, `creation.py`/`data_retrieval.py`/`geometry.py`/`validation.py`/`ui.py`, específicamente escritas para crear pilotes/encepados): **prácticamente no la usa nadie**. `PileMaster` no la toca (no le corresponde). `AddPileToPilecap.pushbutton` (sin `lib/`, ~700 líneas en `script.py`) reimplementa creación de losa + pilotes + agrupación con su propia convención de nombres. `CreatePilecapType.pushbutton/lib/logic.py` reimplementa lo mismo otra vez (y hasta prepara el `sys.path` hacia `pilecap_utils` sin llegar a importarlo — código muerto). Motivo probable: `pilecap_utils` está enteramente en español y las herramientas más nuevas se escribieron en inglés sin adaptarlo.
- **Tres sistemas de persistencia de configuración incompatibles y coexistentes**:
  1. `NOSAWindow.SaveConfig/LoadConfig` (`base_window.py:202-218`) → `%APPDATA%/pyRevit/Extensions/NOSA.extension/NOSA_Configs/` — el estándar, usado por la mayoría de ventanas.
  2. `nosa_utils.config_manager.ConfigManager` (`config_manager.py:20-24`) → `%APPDATA%/pyRevit/NOSA_Configs/` (**sin** `Extensions/NOSA.extension/`) — usado solo por `AddPileToPilecap/script.py` y `ExportScheduleToExcel/script.py`.
  3. `nosa_utils.ui_helpers.ConfigHelper` (`ui_helpers.py:158-196`) → por defecto `lib/nosa_utils/config/` (relativo a `__file__`) o el mismo directorio incompleto que (2) — usado por 4 archivos.
  Ningún plugin que use (2) o (3) comparte carpeta de config con el resto de la extensión; si alguna vez se movieron o convivieron configuraciones, se perdieron silenciosamente.
- **`lib/nosa_utils/__init__.py:14-20`** importa de forma **eager** `geometry`, `unit_conversion`, `ui_helpers`, `revit_helpers`, `config_manager` — todos con acceso a `Autodesk.Revit.DB` o `pyrevit.forms/script` a nivel de módulo. Como Python siempre ejecuta `__init__.py` de un paquete al importar cualquiera de sus submódulos, **cualquier** `from nosa_utils.theme import ThemeManager` o `from nosa_utils.logging import Logger` arrastra silenciosamente la API de Revit completa como efecto colateral. Esto anula, a nivel de paquete, la regla "nunca acceso a `DB` en el nivel de módulo" que el resto del código intenta seguir archivo a archivo. `lib/pilecap_utils/__init__.py:5-9` tiene el mismo patrón.
- **`lib/nosa_utils/i18n.py`**: sistema bilingüe (EN/ES) completo y bien construido, con ~90 claves por idioma — pero solo lo usa **un** plugin (`ExportSheets`). El problema que resolvería (inconsistencia de idioma) sigue presente sin resolver en el resto de la extensión (ver 1.4).

### 1.4 Idioma — dónde es inconsistente de verdad

- El XAML (texto de UI) es 100% inglés en los 39 pushbuttons — no hay inconsistencia ahí.
- El código Python interno mezcla idiomas: `lib/pilecap_utils/*` es 100% español (variables, prompts, logs), `WaffleSlab.pushbutton/script.py` tiene nombres de clase/función/variable en español (`ForjadoReticularReal`, `detectar_columnas`, `calcular_zonas_macizadas`) mientras su UI es inglesa, y `QRCode.pushbutton/lib/ui.py` es el único sitio donde la **misma sesión de usuario** puede ver mensajes de estado en inglés y en español según la ruta de código que se ejecute.
- `ExportSheets` es el pushbutton más "español" del árbol (docstrings, logs, excepciones) pese a ser el único que sí usa el sistema `i18n` bilingüe correctamente.

### 1.5 Top 10 problemas estructurales (por impacto)

1. **`doc.Delete(DB.ICollection[DB.ElementId]([...]))` — tipo inexistente/no instanciable, usado en 8 sitios de 3 archivos**: `ModelCleanup/lib/logic.py:54,102,136,180,230`, `FamilyAudit/lib/logic.py:169,179`, `MaterialManager/lib/logic.py:107`. `Autodesk.Revit.DB` no tiene `ICollection`; la llamada lanza excepción siempre, capturada por un `except Exception` que solo incrementa el contador de "Failed". **Ningún borrado por lotes de estas 3 herramientas ha funcionado nunca** (purga de vistas huérfanas, familias sin usar, plantillas sin usar, imports CAD, rooms sin colocar; purga de familias; borrado de materiales). Confirmado con `grep`, no es una suposición del agente.
2. **`doc = revit.doc` capturado a nivel de módulo** en `lib/pilecap_utils/creation.py:16-17` y `data_retrieval.py:24`. Estos módulos se cachean en `sys.modules` entre ejecuciones (patrón conocido de pyRevit, documentado por el propio equipo en `error_registry.py` ERR008 — "Reload pyRevit after any change to lib/ui.py"); si el usuario cambia de documento activo entre dos usos del mismo pushbutton sin recargar pyRevit, estas funciones seguirán operando sobre el documento antiguo.
3. **Adopción inconsistente de `NOSAWindow`** (9 de ~30 ventanas la evitan) → dark mode roto o parcialmente roto en `PileMaster`, `DiRootsHub`, y sin persistencia de tamaño de ventana en los otros 8. Es la deuda visual más extendida de la extensión (ya estaba parcialmente trackeada en `NOSA_TASKS_DIROOTS_UI_BACKLOG.md`, bloque A).
4. **Tres sistemas de persistencia de configuración incompatibles** (ver 1.3) — cualquier plugin que use `ConfigManager` o `ConfigHelper` en vez de `NOSAWindow.SaveConfig/LoadConfig` guarda su configuración en una carpeta distinta al resto de la extensión.
5. **`lib/pilecap_utils/` (~1000 líneas) esencialmente sin usar** por las 3 herramientas que deberían usarla (`AddPileToPilecap`, `CreatePilecapType`, y por diseño no aplica a `PilecapLoadChecker`) — un bug de geometría de pilotes hay que arreglarlo hasta 3 veces en vez de una.
6. **Lógica de proximidad/geometría duplicada de forma independiente al menos 4 veces**: `ClashReport` (intersección de sólidos), `ConnectionChecker` (proximidad de extremos de viga), `ElementJoin` (tolerancia de bounding box), `CenterBeamToColumn`/`WaffleSlab` (centro de elemento + distancia 2D) — todas reimplementan funciones que ya existen en `lib/nosa_utils/geometry.py` (`get_element_center`, `calculate_distance_2d/3d`, `get_solid_from_element`).
7. **`__init__.py` de ambas librerías compartidas hace import eager de submódulos con dependencia de la API de Revit** (ver 1.3) — anula la protección "no `DB` a nivel de módulo" para cualquier consumidor de `nosa_utils`/`pilecap_utils`, por inocuo que parezca el submódulo que se quería importar.
8. **Desajuste nombre/documentación/función en al menos 2 herramientas**: `RevisionTracker.pushbutton` (Structures.panel) dice en su docstring que gestiona revisiones de planos Revit, pero su implementación real es un snapshot/diff JSON de elementos estructurales — no toca objetos `Revision` de Revit en absoluto. `PilecapLoadChecker.pushbutton` (Piling.panel) dice que lee cargas axiales/cortante/momento y las compara con límites, pero solo implementa comprobaciones geométricas (separación, distancia a borde, esbeltez, canto) — el XAML sí es honesto ("Geometry & Load Rules"), el docstring de `script.py` no.
9. **Organización de paneles/pulldowns desalineada con la función real**: `ElementJoin` (Elements.pulldown) es internamente "SmartJoin" en cada identificador — nombre público y nombre interno no coinciden; funcionalmente es la pareja natural de `ConnectionChecker` (Analysis.pulldown), que detecta lo que `ElementJoin` corrige, pero están en pulldowns distintos. `Views.pulldown` (Documentation) agrupa 7 herramientas de naturaleza distinta (edición por lotes, utilidad puntual, auditoría de solo lectura) — es el cajón de sastre del árbol.
10. **"¿Tiene material?" y "clasificar warnings" se comprueban de 2-3 formas independientes cada una**: `HealthScore.check_elements_without_material` / `MaterialManager._get_structural_material` / `QuantificationQA._has_material` por un lado; `HealthScore.check_elements_with_warnings` / `WarningsTriage.classify_warnings` por otro. Un cambio de criterio (p. ej. qué cuenta como "sin material") requiere tocar 2-3 sitios y ya han divergido entre sí (WarningsTriage clasifica severidad con reglas propias que HealthScore ignora).

---

## FASE 2 — Limpieza (candidatos — nada borrado todavía)

### 2.1 Código muerto confirmado

| Archivo | Qué es | Por qué se sabe que está muerto |
|---|---|---|
| `Data.panel/BulkParameterEditor.pushbutton/lib/logic.py:163-169` | función `export_csv` | Nunca llamada; el export real está reimplementado a mano en `lib/ui.py` |
| `Data.panel/FamilyAudit.pushbutton/lib/logic.py:34-51` | función `_instance_count` | Sustituida por `_fast_instance_count`; además tiene un collector-en-bucle latente si se reactivara |
| `Structures.panel/Quantities.pulldown/QuantificationQA.pushbutton/lib/logic.py:176-202` | `collect_concrete_quantities` (v1) | Sustituida por `collect_concrete_quantities_v2`, usada en `run_all` |
| `Structures.panel/Quantities.pulldown/QuantificationQA.pushbutton/lib/logic.py:292-307` | `aggregate_by_level_category` | Sustituida por `aggregate_concrete_v2` |
| `Structures.panel/RevisionTracker.pushbutton/lib/ui.py:12` | instancia `logger` | Creada, nunca usada en el archivo |
| `Structures.panel/Elements.pulldown/RebarCoverage.pushbutton/lib/ui.py:13` | import `get_available_categories` | Importada, nunca llamada |
| `Documentation.panel/Annotations.pulldown/AnnotationBatch.pushbutton/lib/logic.py:75-89,96-131` | `get_tag_types_for_category`, `get_spot_elevation_types`, `batch_spot_elevations` | No referenciadas desde `ui.py` |
| `Documentation.panel/Annotations.pulldown/TagAll.pushbutton/lib/logic.py:81-84` | `diagnose_tags_in_project` | No-op deshabilitado; hay un bloque comentado en `ui.py:55-58` que lo confirma |
| `Documentation.panel/QRCode.pushbutton/lib/_demo_ec_levels.py` | archivo completo (78 líneas) | No lo importa ni `ui.py` ni `script.py`; además haría `import qrcode`/`from PIL import Image` a nivel de módulo, que fallaría bajo IronPython si algo lo cargara |
| `Piling.panel/Utilities.pulldown/CreatePilecapType.pushbutton/lib/logic.py:6-8` | inserción de `sys.path` hacia `pilecap_utils` | Nunca se usa; el archivo reimplementa la lógica en vez de importar |
| `Piling.panel/Utilities.pulldown/AddPileToPilecap.pushbutton/script.py:422-464` | ~42 líneas dentro de `point_in_face()` | Inalcanzable (después de un `return False`) y además rota: referencia `solid`, `transform`, `z_value`, que no son parámetros de la función — lanzaría `NameError` si alguna vez se alcanzara |

### 2.2 Duplicación — candidatos a extraer a `lib/`

| Candidato a helper compartido | Sitios que lo reimplementan hoy |
|---|---|
| `get_id_value` (ya existe en `nosa_utils.revit_helpers`) | Reimplementado byte a byte 7 veces: `ConnectionChecker`, `HealthScore`, `WarningsTriage`, `ElementJoin`, `RebarCoverage`, `QuantificationQA`, `RevisionTracker` (todos en Structures.panel) |
| "¿Están dos elementos cerca/tocándose?" (bounding box / distancia / intersección de sólidos) | `ClashReport`, `ConnectionChecker`, `ElementJoin`, `CenterBeamToColumn`, `WaffleSlab` — 4-5 implementaciones independientes; ya existe base en `nosa_utils.geometry` |
| Conversión mm↔ft (`304.8`) | Al menos 10 archivos usan el literal `304.8`/`0.3048` en vez de `nosa_utils.unit_conversion`; `WaffleSlab/script.py:35-36` incluso usa una aproximación redondeada (`0.00328084`) menos precisa que la constante real |
| Colección de vistas no-plantilla (`FilteredElementCollector(doc).OfClass(DB.View)` + filtro `IsTemplate`) | `AlignViewTitles`, `CopyViewTemplates`, `ModelCleanup`, `TemplateGuard`, `ViewBatchManager`, `ViewFilterBatch` — 6 implementaciones con listas de exclusión de tipo de vista que ya no son idénticas entre sí |
| Aplicar/quitar plantilla de vista a una lista de vistas | `CopyViewTemplates.copy_template_to_view` y `ViewBatchManager` (`lib/logic.py:128-146`) hacen literalmente `view.ViewTemplateId = template_id` cada uno por su lado |
| Export CSV con comillas/escapado | `BulkParameterEditor/lib/ui.py:589` y `ExportScheduleToExcel/script.py:163-182` reimplementan a mano el escapado en vez de usar el módulo `csv` (que sí usan correctamente `FamilyAudit` y `ParameterInspector`) |
| "¿Tiene material asignado?" | `HealthScore`, `MaterialManager`, `QuantificationQA` — 3 implementaciones |
| Clasificación de warnings de Revit | `HealthScore.check_elements_with_warnings` (cuenta plano) vs `WarningsTriage.classify_warnings` (severidad real vía `warning_rules.json`) — deberían compartir una función |
| Creación de losa de cimentación + array de pilotes | `pilecap_utils.creation` vs `AddPileToPilecap/script.py` vs `CreatePilecapType/lib/logic.py` — 3 implementaciones, ver 1.3/1.5 |
| "Cargar módulo hermano" (ui.py → logic.py) | Al menos 3 convenciones distintas conviven: `imp.load_source` directo, un `_lm()` local con fallback `importlib`, y el helper compartido `nosa_utils.loader.load_local_module` — mismo problema, 3 soluciones |

### 2.3 Nombres confusos

| Elemento | Problema | Sugerencia |
|---|---|---|
| `NOSA.Panel/NOSA.pushbutton` | El nombre no indica que es un dashboard de solo lectura (inventario de plugins + info de empresa); no lanza nada al hacer clic en un plugin listado | Renombrar a algo como `Dashboard`/`About` |
| `Structures.panel/Elements.pulldown/ElementJoin.pushbutton` | Public-facing "ElementJoin" pero cada identificador interno dice "SmartJoin"/"SmartJoin Pro" (config `_smartjoin.json`, `NOSAWindow(..., 'smartjoin_pro')`, transacciones `"SmartJoin — ..."`) | Unificar en un solo nombre, público e interno |
| `Structures.panel/RevisionTracker.pushbutton` | Nombre + docstring sugieren gestión de revisiones de planos Revit; la implementación real es snapshot/diff de elementos estructurales en JSON | Renombrar (p. ej. `ModelSnapshotDiff`) o corregir el docstring — ahora mismo confunde a cualquiera que lo abra por primera vez |
| `Data.panel/ExcelSync.pushbutton/lib/logic.py:2-3` | Un `import io` se cuela antes de lo que iba a ser el docstring del módulo, así que ese string nunca se asigna a `__doc__` | Mover el import después del docstring |
| Casing de icono inconsistente | `icon.png` (mayoría) vs `Icon.png` (`ExcelSync`, `FamilyAudit`, `ParameterInspector`, `PileMaster` y otros en Piling/Structures) | Unificar a minúsculas en un pase de limpieza |
| `WaffleSlab.pushbutton/script.py` | Identificadores internos 100% en español (`ForjadoReticularReal`, `detectar_columnas`, `intereje`, `ancho_nervio`) mientras la UI y el resto de Structures.panel son en inglés | Traducir en el mismo pase que se toque el archivo por otros motivos (no urgente en solitario) |
| `WaffleSlab.pushbutton/script.py:2` | `__title__ = "Waffle\\nSlab"` — doble barra invertida literal en vez de salto de línea real | Corregir a `"Waffle\nSlab"` (bug cosmético, incluido aquí porque es un rename de una línea) |

### 2.4 Archivos que no deberían enviarse dentro del bundle

- `Piling.panel/Utilities.pulldown/CreatePilecapType.pushbutton/MEJORAS_APLICADAS.md` — notas de desarrollo en español, no es código ni documentación de usuario.
- `Documentation.panel/QRCode.pushbutton/lib/_demo_ec_levels.py` — script de demo/prueba sin referencias (ver 2.1).

---

## FASE 3 — Revisión de código (bugs reales)

### CRÍTICO

| # | Archivo:línea | Problema |
|---|---|---|
| C1 | `Documentation.panel/Views.pulldown/ModelCleanup.pushbutton/lib/logic.py:54,102,136,180,230` | `doc.Delete(DB.ICollection[DB.ElementId]([...]))` — `ICollection` no existe/no es instanciable en `Autodesk.Revit.DB`; la excepción se traga en un `except Exception` que solo suma a "Failed". **Ninguna de las 5 purgas (vistas huérfanas, familias sin usar, plantillas sin usar, imports CAD, rooms sin colocar) ha borrado nunca nada.** `ui.py:160-163` demuestra que sí conocen el patrón correcto (`System.Collections.Generic.List[DB.ElementId]`) para otra operación del mismo archivo. |
| C2 | `Data.panel/FamilyAudit.pushbutton/lib/logic.py:169,179` | Mismo bug que C1 — purga de familias nunca ha borrado nada. |
| C3 | `Structures.panel/Quantities.pulldown/MaterialManager.pushbutton/lib/logic.py:107` | Mismo bug que C1 — borrado de materiales nunca ha funcionado. |
| C4 | `lib/pilecap_utils/creation.py:16-17`, `lib/pilecap_utils/data_retrieval.py:24` | `doc = revit.doc` / `uidoc = revit.uidoc` a nivel de módulo — referencia de documento potencialmente obsoleta tras cambiar de documento activo sin recargar pyRevit (módulos cacheados en `sys.modules`). |
| C5 | `Documentation.panel/Sheets.pulldown/ExportSheets.pushbutton/lib/config.py:84-109` | `DB.RasterQualityType`, `DB.ColorDepthType`, `DB.ACADVersion`, `DB.ExportColorMode` evaluados en el cuerpo de la clase `Config` (nivel de módulo) + `Config.ensure_dirs()` crea carpetas en disco al importar el módulo. |
| C6 | `Structures.panel/Analysis.pulldown/ClashReport.pushbutton/lib/logic.py:12-13` | `_log_debug(msg, exc=None): pass` — no-op real; todos los fallos de geometría/collector del archivo se descartan sin ningún rastro, ni siquiera en log. |

### ALTO

| # | Archivo:línea | Problema |
|---|---|---|
| H1 | `Piling.panel/PileMaster.pushbutton/lib/ui.py:32` | `PileMasterWindow` extiende `forms.WPFWindow` en vez de `NOSAWindow` → sin dark mode, sin persistencia de tamaño de ventana. |
| H2 | `Piling.panel/PileMaster.pushbutton/lib/ui.py:266-284` | `run_coordinates()` no comprueba `if not elements:` antes de operar (a diferencia de `run_numbering`/`run_sheets` en el mismo archivo) — con selección vacía informa "Success: 0 / Failed: 0" sin explicar por qué. |
| H3 | `Piling.panel/Utilities.pulldown/CreatePilecapType.pushbutton/lib/logic.py` (todo el archivo) | Reimplementa creación de losa + array de pilotes en vez de llamar a `lib/pilecap_utils/` (ver FASE 1 punto 5). |
| H4 | `Piling.panel/Utilities.pulldown/PilecapLoadChecker.pushbutton/lib/logic.py:120-143` | `_piles_on_pilecap()` crea un `FilteredElementCollector` nuevo dentro del bucle por elemento de `check_all_pilecaps` — recorre toda la categoría de cimentaciones una vez por cada elemento comprobado. |
| H5 | `Piling.panel/Utilities.pulldown/PilecapLoadChecker.pushbutton/script.py:4-13` | Docstring dice que lee carga axial/cortante/momento y compara límites; la implementación solo comprueba geometría (separación, distancia a borde, esbeltez, canto). |
| H6 | `Documentation.panel/Annotations.pulldown/AnnotationBatch.pushbutton/lib/logic.py:182-183` | `grid.ShowBubbleInView(DB.DatumEnds.End0 if show_bubbles else DB.DatumEnds.End0, view)` — las dos ramas del condicional son `End0`; nunca se puede ocultar la burbuja del extremo `End1`. |
| H7 | `Documentation.panel/Annotations.pulldown/DimensionWalls.pushbutton/lib/ui.py:161-167`, `lib/logic.py:232-234,279-281` | Fallos en cotas de arco/radio se tragan con `except Exception: pass` sin sumar al contador de fallos — el "Failed: N" final no refleja fallos reales en muros curvos. |
| H8 | `Documentation.panel/Views.pulldown/CopyViewTemplates.pushbutton/lib/ui.py:162,189` | Llama a `System.Windows.Forms.Application.DoEvents()` sin `import`/`clr.AddReference` propio ni try/except (a diferencia de `DimensionWalls`/`TagAll`, que sí lo protegen). |
| H9 | `Documentation.panel/QRCode.pushbutton/lib/qr_generator.py:158,170`, `lib/_qr_subprocess.py:29-31` | Auto-instala (`pip install`) `qrcode`/`Pillow` en el intérprete CPython que encuentre, sin confirmación del usuario — efecto colateral sobre el sistema disparado por un simple clic en "Generate". |
| H10 | `Documentation.panel/QRCode.pushbutton/lib/_demo_ec_levels.py:64` | URL de SharePoint hardcodeada en un archivo de demo sin referencias (ver también 2.1/2.4). |
| H11 | `Structures.panel/Analysis.pulldown/ConnectionChecker.pushbutton/lib/logic.py:97-107` | `check_beam_joins` ejecuta un `FilteredElementCollector` sin filtro de categoría (todo el modelo) dentro de un bucle anidado, 2 veces por viga. |
| H12 | `Structures.panel/Quantities.pulldown/MaterialManager.pushbutton/lib/logic.py:36,44` | `collect_materials` recorre 2 veces todo el modelo sin filtro de categoría/clase. |
| H13 | `Structures.panel/Elements.pulldown/RebarCoverage.pushbutton/lib/logic.py:60-72` | Fallback de `_has_rebar` recolecta **todos** los `OST_Rebar` del modelo potencialmente una vez por cada elemento estructural comprobado. |
| H14 | `Structures.panel/RevisionTracker.pushbutton/script.py:4-12` | Docstring describe gestión de revisiones de planos Revit; la implementación real es snapshot/diff JSON de elementos estructurales (ver FASE 1 punto 8). |
| H15 | `Data.panel/FamilyAudit.pushbutton/lib/logic.py:110,145-148` | `_fast_instance_count` crea un `FilteredElementCollector` sobre todo el modelo por cada familia auditada — O(N_familias × instancias_modelo). |
| H16 | `Data.panel/ExcelSync.pushbutton/lib/logic.py:31-33` | `_build_mark_index` recorre `FilteredElementCollector` sin ningún filtro de categoría/clase cuando se activa "Match by Mark". |
| H17 (×7 duplicados) | Ver tabla 2.2 — `get_id_value` reimplementado en `ConnectionChecker`, `HealthScore`, `WarningsTriage`, `ElementJoin`, `RebarCoverage`, `QuantificationQA`, `RevisionTracker` | Duplicación de una función ya existente en `nosa_utils.revit_helpers`. |
| H18 | `Documentation.panel/Views.pulldown/TagAll.pushbutton/lib/ui.py:278-305` | `get_elements_in_view` (collector nuevo) invocado dentro de un bucle anidado vistas × asignaciones. |
| H19 | 9 pushbuttons — ver 1.2 | No extienden `NOSAWindow`: `PileMaster`, `DimensionWalls`, `TagAll`, `ExportSheets`, `AlignViewTitles`, `CopyViewTemplates`, `QRCode`, `CenterBeamToColumn`, `WaffleSlab`. |

### MEDIO

- **`__author__` inconsistente** (no es `"NOSA Engineering"`): `ExportScheduleToExcel/script.py:13`, `PileMaster/script.py:7` ("NOSA"), `AddPileToPilecap/script.py:3`, `NOSA.pushbutton/script.py:5`, `ExportSheets/script.py:6`, `TagAll/script.py:11`, `BatchRename/script.py:13`, `AlignViewTitles/script.py:11`, `CopyViewTemplates/script.py:7`, `DimensionWalls/script.py:8` ("NOSA Extension"), `HalftoneSelection/script.py:3` ("NOSA"), `ClashReport/script.py:12`, `CenterBeamToColumn/script.py:14`, `WaffleSlab/script.py:14`.
- **Nombres de transacción sin el patrón `"NOSA — ..."`**: `ExcelSync/lib/logic.py:89`, `FamilyAudit/lib/logic.py:170`, `ParameterInspector/lib/logic.py:130,159`, `DimensionWalls/lib/ui.py:153`, `TagAll/lib/ui.py:260`, `BatchRename/script.py:338`, `AlignViewTitles/lib/ui.py:178`, `CopyViewTemplates/lib/ui.py:165,192`, `HalftoneSelection/script.py:54`, `SheetComposer/lib/logic.py` (6 sitios), `ModelCleanup/lib/logic.py` (5 sitios), `ViewFilterBatch/lib/logic.py` (4 sitios), `ClashReport/lib/ui.py:200`, `CenterBeamToColumn/script.py:536`, `WarningsTriage/lib/logic.py:172,200`, `HealthScore/lib/ui.py` (4 sitios), `ElementJoin/lib/logic.py:219,277`, `MaterialManager/lib/logic.py:103,263`, `PileMaster/lib/logic_coords.py:241,333`, `logic_numbering.py:309`, `logic_sheets.py:82,173,201`, `pilecap_utils/creation.py:145,196,231,271`, `AddPileToPilecap/script.py` (4 sitios).
- **Factor de conversión `304.8` hardcodeado** en vez de `nosa_utils.unit_conversion` (≥10 archivos): `AlignViewTitles/lib/ui.py:118-119`, `ExportSheets/lib/utils.py:60,64`, `CenterBeamToColumn/script.py:78-82`, `HealthScore/lib/logic.py:39-40`, `ElementJoin/lib/logic.py:10`, `WaffleSlab/script.py:35-36` (versión redondeada, menos precisa), `QuantificationQA/lib/logic.py:370`, `AddPileToPilecap/script.py` (20+ sitios, pese a importar `mm_to_feet` en el mismo archivo), `CreatePilecapType/lib/logic.py:10`, `PilecapLoadChecker/lib/logic.py:11` y `lib/ui.py:193`, `PileMaster/lib/logic_coords.py:148`.
- **Duplicación de parámetros/materiales/geometría** — ver tabla 2.2 completa (get/set de parámetro reimplementado en `HealthScore/lib/ui.py:264-411`, `MaterialManager/lib/logic.py:257-288`, `QuantificationQA/lib/ui.py:190-244` en vez de `nosa_utils.param_element_ops`).
- **CSV sin el patrón `io.open(..., encoding='utf-8-sig', newline='')`**: `BulkParameterEditor/lib/ui.py:589` (`codecs.open` sin `newline=''`), `RevisionTracker/lib/ui.py:2,113` (`open()` plano).
- **`WaffleSlab/script.py:2`**: `__title__ = "Waffle\\nSlab"` (doble barra invertida literal, no salto de línea).

### BAJO

- **Falta `lib/__init__.py`** en la gran mayoría de pushbuttons con carpeta `lib/` (~35 de 39) — inofensivo dado que todos usan carga dinámica de módulos (`imp.load_source`/`importlib`) en vez de imports de paquete, pero merece un pase de limpieza único.
- Código muerto y comentarios de bloque largos — ver tabla 2.1 y hallazgos de los agentes (`ExportSheets/lib/validation.py:169-184`, `CopyViewTemplates/lib/logic.py:88-98`, `ExportSheets/lib/utils.py:190-196`).
- Casing de icono inconsistente (`icon.png` vs `Icon.png`) — ver 2.3.
- Naming/estructura inconsistente: `CenterBeamToColumn` y `WaffleSlab` no tienen `lib/` (script monolítico) a diferencia de sus 9 vecinos en los mismos pulldowns.

---

## Resumen

| Severidad | Nº hallazgos |
|---|---|
| Crítico | 6 (afectando 8 sitios de código en 5 archivos distintos) |
| Alto | 19 grupos de hallazgos (varios con múltiples sitios duplicados) |
| Medio | ~45 sitios individuales agrupados en 6 categorías |
| Bajo | ~15 candidatos de limpieza |

El patrón dominante no es "hay bugs sueltos" — es que **3-4 problemas estructurales (config duplicada, `pilecap_utils` sin adoptar, `NOSAWindow` sin adoptar, helpers de geometría/parámetro reimplementados) explican la mayoría de los hallazgos de MEDIO/BAJO**, y **un único bug de tipo (`DB.ICollection`) explica los 3 hallazgos más graves de FASE 3**. `PLAN_MEJORA.md` prioriza en ese orden: primero el bug de borrado (impacto real inmediato en producción), después los desajustes doc/implementación que pueden llevar a decisiones de ingeniería erróneas (RevisionTracker, PilecapLoadChecker), después la consolidación estructural, y por último lo cosmético.
