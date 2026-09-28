# NOSA.extension — Roadmap maestro

**Hilo principal del proyecto.** Este fichero es la única fuente de verdad de lo que queda pendiente.
`ROADMAP.md` (RebarAutomate) y `PLAN_MEJORA.md` (extensión) siguen siendo el detalle técnico; aquí solo se
rastrea *qué* falta, *en qué orden* y *en qué estado está*.

Creado: 2026-09-28 · Rama de integración: **`develop`** (= `fix/rebar-f7-...` + Fase 0/1). `main` no recibe nada hasta T2.9.

## Cómo se usa este fichero

- Cada tarea tiene un **ID** (`T2.3`). Una subtarea = una sesión de Claude Code = una rama.
- Al empezar una tarea: marcar `[~]` y anotar la rama. Al terminar: `[x]` + hash del commit.
- Una sesión de subtarea **solo edita la fila de su propia tarea** en este fichero.
- Columnas: **∥** = se puede hacer en paralelo con otras de su fase · **R** = necesita Revit abierto ·
  **U** = necesita una acción/decisión del usuario.
- Leyenda: `[ ]` pendiente · `[~]` en curso · `[x]` hecha · `[-]` descartada

---

## Decisiones pendientes (bloquean tareas concretas)

| ID | Decisión | Bloquea | Estado |
|---|---|---|---|
| D1 | Estrategia de ramas | T0.4 | [x] `develop` como integración; `main` solo tras humo 4 versiones |
| D2 | `NOSA_Configs` en git | T0.3 | [x] Personales fuera de git; presets compartidos (NamingProfiles, ColumnPresets, ExportPresets) versionados |
| D3 | Bugs legacy de RebarAutomate (densificación en nudos intermedios, esquineras 45° en huecos, ventana modeless): ¿dentro de 1.0 o post-1.0? | T4.6 | [ ] |
| D4 | Fase 13 de `PLAN_MEJORA` (migrar pilecap tools a `pilecap_utils`): ¿se desbloquea? | T5.5 | [ ] |
| D5 | Hubs grandes con uso casi nulo (ModelHealthHub, StructuralQA, DataToolsHub, IssueWorkflowHub): ¿mantener, simplificar o fusionar? | T6.2 | [ ] |
| D6 | ¿Adoptar GSD (`/gsd-new-project`) para gestionar este roadmap, o seguir con este fichero + sesiones? | — | [ ] |

---

## Fase 0 — Consolidar el estado actual (BLOQUEANTE, secuencial)

Sin esto, cualquier sesión nueva en worktree parte de `main`, que no tiene los 27 commits de F7.

| | ID | Tarea | ∥ | R | U | Rama / commit |
|---|---|---|---|---|---|---|
| [x] | T0.1 | Revisar y commitear el trabajo sin commitear de `SheetExportHub` (ui/xaml/exporters) + `bundle.yaml` de Data y Foundations | – | – | ✔ | `8775cdd` (encima de T3.1 `c3c1578`); el cambio de `config.json` de CenterBeamToColumn era solo reordenación → descartado. **Probado en Revit 2026-09-28**: ventana abre, fila seleccionada naranja, sin PNG/JPG sueltos junto al DWG |
| [x] | T0.2 | Pasar `/check-plugin` a **SharedParamManager**, **WorksharingAudit**, **SiteToolkit** y commitearlos (uno por commit) | – | – | ✔ | `74405ff`, `e291042`, `a9ced93` — nosa_lint limpio (solo 1 NOSA006 en SharedParamManager y SiteToolkit) |
| [x] | T0.3 | Aplicar D2 (`.gitignore` de configs personales) | – | – | ✔ | `4f510e2` — 53 ficheros fuera de git (siguen en disco) |
| [~] | T0.4 | Aplicar D1: crear rama de integración y hacer que las worktrees nuevas partan de ella | – | – | ✔ | rama `develop` creada; falta que el checkout principal cambie a `develop` (pasos en el chat del 2026-09-28) |
| [x] | T0.5 | Actualizar la tabla "Estado actual" de `ROADMAP.md` (dice "nada commiteado desde `9df02d7`", ya es falso) y el bloque ESTADO de `PLAN_MEJORA.md`; traer este `MASTER_ROADMAP.md` a la rama de integración | – | – | – | ROADMAP.md actualizado; PLAN_MEJORA se sigue desde aquí (Fases 3 y 5) |

## Fase 1 — Guardarraíles (antes de tocar código en masa)

| | ID | Tarea | ∥ | R | U | Rama / commit |
|---|---|---|---|---|---|---|
| [x] | T1.1 | `tools/nosa_lint.py`: validador determinista con las reglas de `CLAUDE.md` y `/audit-nosa` (imports `pyrevit DB`, `BuiltInCategory` a nivel de módulo, `{Binding type}`/`{Binding _x}`, `SelectedIndex` en XAML, profundidad `sys.path`, español en UI, recursos de color, prefijo `NOSA —` en transacciones, `except: pass`) | ✔ | – | – | `76e41ca` — 20 reglas, AST, `--summary/--json/--fail-on` |
| [x] | T1.2 | Hook de Claude Code (PostToolUse en Edit/Write de `.py`/`.xaml`) que ejecute T1.1 sobre el fichero tocado | – | – | – | `76e41ca` — `.claude/settings.json` + `tools/nosa_lint_hook.py`, bloquea critical/high; probado en vivo |
| [x] | T1.3 | Hook `pre-commit` de git con T1.1 | – | – | – | `76e41ca` — `tools/git-hooks/pre-commit` vía `core.hooksPath`, bloquea critical |
| [ ] | T1.6 | Plugins de apoyo: `claude-code-setup` (ejecutar una vez) y `pyright-lsp` con un `pyrightconfig.json` ajustado a IronPython (silenciar imports `clr`/`System`/`Autodesk`, mantener nombres no definidos) | ✔ | – | ✔ | |
| [ ] | T1.4 | Extraer los stubs de `Autodesk.Revit.DB`/`System` de `RebarAutomate/tests` a un `lib/tests_support/` compartido para que cualquier plugin pueda tener tests sin Revit | ✔ | – | – | |
| [x] | T1.5 | Línea base: ejecutar T1.1 sobre todo el árbol y guardar el informe (será la lista de trabajo de la Fase 3) | – | – | – | 2026-09-28: 982 hallazgos — critical: 8×NOSA001 (SheetExportHub), 33×NOSA002 (ElementCommentsHub, RebarAutomate, SheetExportHub, SheetGen, StructuralSchedulePro, sheet_protocol), 2×NOSA103 (TabMain de SheetGen y MaterialManager, mitigados por try/except) · high: 8×NOSA004 (ProjectSetupWizard, SurveyExport: `..` de menos, inocuo porque pyRevit ya añade `lib/`), 8×NOSA202 iconos, 3×NOSA105, 3×NOSA203 · medium: 854×NOSA006, 45×NOSA106, 16×NOSA005, 2×NOSA007 |

## Fase 2 — Cerrar F7 de RebarAutomate (secuencial: mismos ficheros)

| | ID | Tarea | ∥ | R | U | Rama / commit |
|---|---|---|---|---|---|---|
| [ ] | T2.1 | Confirmar en vivo F7.16 (barras longitudinales de viga dentro de la sección) con el botón real | – | ✔ | ✔ | |
| [ ] | T2.2 | Confirmar en vivo F7.17 (mínimo 3 U-bars por lado en huecos pequeños) | – | ✔ | ✔ | |
| [ ] | T2.3 | Confirmar en vivo F7.18 (esperas en L hacia zapata aislada / losa / zapata corrida) + decidir si lleva preview | – | ✔ | ✔ | |
| [ ] | T2.4 | Verificar `NOSA_Rebar_Layer`: el commit `6fbe47e` dice que se estampa, `ROADMAP.md` dice que no — comprobar en el modelo | – | ✔ | – | |
| [ ] | T2.5 | Investigar los cierres de Revit al recargar pyRevit (reproducir, recoger journal de Revit) | – | ✔ | ✔ | |
| [ ] | T2.6 | Smoke visual: pestañas normalizadas + previews (hooks, alzado de viga, 2 vistas de muro) | – | ✔ | ✔ | |
| [x] | T2.7 | Pasar `RebarAutomate/lib/ui.py:65-69` (`BuiltInCategory` a nivel de módulo) a carga perezosa | – | – | – | `eb8d4d4` — `_cat_id()` con caché + `sys.path` corregido (faltaba un `..`); 20/20 tests. Se verifica solo al abrir RebarAutomate y seleccionar elementos en T2.1 |
| [ ] | T2.8 | **Humo en 4 versiones** (2024/2025/2026/2027) de F4, F6 y F7 según la Matriz de validación de `ROADMAP.md` | – | ✔ | ✔ | |
| [ ] | T2.9 | Fusionar a `main` (solo tras T2.8) | – | – | ✔ | |

## Fase 3 — Correcciones transversales de la extensión (paralelizable por plugin)

| | ID | Tarea | ∥ | R | U | Rama / commit |
|---|---|---|---|---|---|---|
| [~] | T3.1 | **SheetExportHub** (el más usado): 8 ficheros con `from pyrevit import DB` → `from Autodesk.Revit import DB`; `Config.ensure_dirs()` al importar (`config.py:120`) → perezoso (C5-bis) | ✔ | ✔ | – | imports + `_BIP_FALLBACK` perezoso en `c3c1578`; **pendiente de re-probar tras T0.4** (la prueba del 2026-09-28 se hizo con el checkout principal aún en `fix/...`, sin este cambio) |
| [x] | T3.1b | SheetExportHub C5-bis: enums `DB.RasterQualityType`/`ColorDepthType`/`ACADVersion`/`ExportColorMode` en el cuerpo de `Config` (`config.py:97-116`) y `Config.ensure_dirs()` al importar (`config.py:120`) → perezosos | – | ✔ | – | `fb34a55` — `Config.preset(name)` resuelve los enums bajo demanda; `ensure_dirs()` se queda al importar (solo toca disco) pero protegido. Re-probar junto con T3.1 |
| [x] | T3.7 | Eliminar los hallazgos **critical** restantes de la línea base: enums de Revit al importar (ElementCommentsHub `logic`/`logic_dmu`, SheetGen, StructuralSchedulePro BOM, `nosa_utils.sheet_protocol`) y `TabMain.SelectionChanged` en XAML (SheetGen, MaterialManager) | – | ✔ | – | `3149881`, `210b2ba` — **0 critical en todo el árbol**. Re-probar: abrir ElementCommentsHub, SheetGen (pestaña Drawing Index), MaterialManager (cambiar de pestaña) y StructuralSchedulePro (BOM). Nota fuera de alcance: los `SelectionChanged` de ComboBox/DataGrid dentro de las pestañas suben (routed event) hasta `TabMain` y ejecutan `Tab_Changed`; en SheetGen eso repuebla el Drawing Index en cada cambio de combo de esa pestaña → filtrar por `args.OriginalSource` tras confirmar que nada depende de ello |
| [x] | T3.8 | `sys.path` sin salida (NOSA004): ProjectSetupWizard, SurveyExport, RebarAutomate (script + `rebar_shape_classifier`) con un `..` de menos; ElementCommentsHub `script.py` con uno de más | ✔ | – | – | `eb8d4d4`, `e7e63af` — 0 NOSA004 |
| [ ] | T3.2 | Barrido de `.Name` sobre objetos de la API de Revit (pythonnet/CPython), por panel: T3.2a Data · T3.2b Documentation · T3.2c Foundations · T3.2d Structures | ✔ | ✔ | – | |
| [ ] | T3.3 | `except: pass` → `nosa_utils.telemetry.log_error`, empezando por ModelHealthHub (52), StructuralQA (49), SheetExportHub (43) | ✔ | – | – | |
| [ ] | T3.4 | C6: `ClashReport` `_log_debug` es un no-op (`ClashReport.nobutton/lib/logic.py:14`) | ✔ | – | – | |
| [ ] | T3.5 | AddPileToPilecap: config en dos sistemas (`ConfigManager` + `NOSAWindow`) y `NameError` latente en `point_in_face` | ✔ | ✔ | – | |
| [ ] | T3.6 | Telemetría: unificar claves de `_usage.json` (`export_sheets`/`exportsheets`/`sheet_export_hub`, `qrcode`/`qr_code`, `pilemaster`/`pile_master`…) para poder medir uso real | ✔ | – | – | |

## Fase 4 — RebarAutomate 1.0.0 (F8 + F9)

| | ID | Tarea | ∥ | R | U | Rama / commit |
|---|---|---|---|---|---|---|
| [ ] | T4.1 | F8: conseguir un `.abs` real o el spec BVBS y validar `bar_to_bvbs_line`/`_compute_checksum`; poner `BVBS_FORMAT_VERIFIED = True` | ✔ | – | ✔ | |
| [ ] | T4.2 | Familias de anotación: auditar `NOSA Rebar Tag`/MRA, ajustar labels a `NOSA_Rebar_*`, empaquetar `.rfa` en Revit 2024 | ✔ | ✔ | – | |
| [ ] | T4.3 | `data/content_manifest.json` (versión de familias + aviso de obsoletas) | ✔ | – | – | |
| [ ] | T4.4 | `docs/USER_GUIDE.md` | ✔ | – | – | |
| [ ] | T4.5 | Humo completo F9 en 4 versiones con un proyecto real armado de principio a fin | – | ✔ | ✔ | |
| [ ] | T4.6 | Según D3: densificación en nudos intermedios · esquineras 45° en huecos · ventana modeless | – | ✔ | – | |
| [ ] | T4.7 | Tag `1.0.0` + `RELEASE_CHANGELOG` | – | – | ✔ | |

## Fase 5 — Deuda estructural

| | ID | Tarea | ∥ | R | U | Rama / commit |
|---|---|---|---|---|---|---|
| [ ] | T5.1 | CenterBeamToColumn al patrón estándar (`lib/`, `NOSAWindow`, `ui.xaml`) — único plugin activo que no lo sigue | ✔ | ✔ | – | |
| [ ] | T5.2 | Mapear las 58 carpetas `.nobutton` (29.6k LOC): cuáles cargan los hubs y cuáles son código muerto; borrar las muertas | ✔ | – | – | |
| [ ] | T5.3 | Adoptar `nosa_utils.collectors` en los 8 sitios duplicados de "vistas sin plantilla"/"aplicar plantilla" | ✔ | – | – | |
| [ ] | T5.4 | Adoptar `nosa_utils.bootstrap` en lugar de `imp.load_source` (preparación CPython) | – | – | – | |
| [ ] | T5.5 | Fase 13 de `PLAN_MEJORA` (según D4) | – | ✔ | – | |
| [ ] | T5.6 | Fase 16 de `PLAN_MEJORA`: `Icon.png`→`icon.png`, `WaffleSlab` `\\n`, `MEJORAS_APLICADAS.md` | ✔ | – | – | |
| [ ] | T5.7 | Fase 17 de `PLAN_MEJORA`: consistencia de idioma interna / `i18n` | ✔ | – | – | |

## Fase 6 — Utilidad y calidad de producto

| | ID | Tarea | ∥ | R | U | Rama / commit |
|---|---|---|---|---|---|---|
| [ ] | T6.1 | Auditoría de 3 ejes (código · apariencia XAML · utilidad) con ficha por plugin; convertirla en `/audit-nosa-full` | – | – | – | |
| [ ] | T6.2 | Aplicar D5 a los hubs grandes poco usados | ✔ | – | ✔ | |
| [ ] | T6.3 | Tests sin Revit para los plugins más usados: SheetExportHub, PileMaster, QRCode, MaterialManager, AddPileToPilecap, CreatePilecapType | ✔ | – | – | |

---

## Orden y dependencias

```
Fase 0 ──► Fase 1 ──┬──► Fase 2 (secuencial) ──► Fase 4 ──► 1.0.0
                    ├──► Fase 3 (paralelo por plugin)
                    └──► Fase 5 / Fase 6 (paralelo, cuando haya hueco)
```

- Fase 2 y Fase 4 tocan los mismos ficheros de RebarAutomate: **nunca dos sesiones a la vez** sobre ellas.
- Fase 3, 5 y 6 se pueden repartir en sesiones paralelas siempre que cada una toque plugins distintos.

## Plantilla para arrancar una subtarea

Pegar como primer mensaje de una sesión nueva:

```
Trabaja SOLO en la tarea <ID> de MASTER_ROADMAP.md.
0. Antes de nada: `git merge --ff-only develop` (las worktrees nuevas pueden partir de main).
1. Lee MASTER_ROADMAP.md, CLAUDE.md y la sección relevante de ROADMAP.md / PLAN_MEJORA.md.
2. Marca la tarea como [~] con el nombre de tu rama.
3. Haz la tarea. Si encuentras algo fuera de alcance, NO lo arregles: añádelo como nota bajo la tarea.
4. Verifica (tests / nosa_lint / prueba en Revit si la tarea lleva R).
5. Marca [x] con el hash del commit y resume en 3 líneas qué cambió y qué queda.
```

## Backlog post-1.0 (no planificado, de `ROADMAP.md`)

Vigas continuas multi-vano · esperas de pilar dobladas en cambio de sección · "Create Views" en un clic ·
Tag All sin cruces de leader · miniatura de doblado en el BBS · ocultar barras intermedias · punzonamiento
geométrico · export PXML · catálogo de formas EHE propio · armado de escaleras · export Tekla/RISA ·
muros curvos en RebarAutomate.
