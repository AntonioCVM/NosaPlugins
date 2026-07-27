# Plan de mejora — NOSA.extension

Basado en `AUDITORIA.md`. Cada fase es pequeña, tocando el mínimo número de archivos, verificable manualmente en Revit (ver `PLAN_PRUEBAS.md` para el detalle de cada prueba) y pensada para un commit propio. Orden: primero bugs reales en producción, después desajustes de documentación/nombre, después arquitectura/duplicación, por último cosmético.

No ejecutar todavía — esto es la planificación. Antes de dar cada fase por terminada: `/verification-before-completion`. Al cerrar cada fase: `/commit-work`.

---

## RECONCILIACIÓN 2026-07-27 — este plan se ejecutó sobre el disco real, no sobre el worktree de auditoría

El disco real (`main`) tenía una reorganización grande sin commitear (`AUDIT_REFACTOR_PLAN.md`, Piling→Foundations, ~88 plugins) que cambió las rutas de casi todos los archivos citados abajo. Cada Fase de Nivel 1 se re-verificó contra las rutas nuevas antes de tocar nada — ver `AUDITORIA.md` §0-BIS para el detalle completo de la reconciliación. Resumen de lo ejecutado en esta sesión:

| Fase | Estado | Commit |
|---|---|---|
| Fase 0 — RevisionTracker docstring | **No hizo falta** — la implementación ya gestiona `DB.Revision` real (movido a `Documentation.panel/Issue.pulldown/`), el docstring ya describe lo que hace. | — |
| Fase 0 — PilecapLoadChecker docstring | **Ejecutada** — el docstring ya decía "chequeo geométrico", pero además había quedado desactualizado en sentido inverso (decía que el check de cargas estaba "planificado para el futuro" cuando ya existe un chequeo parcial de N axial). Corregido para reflejar el estado real. | `14f2b79` |
| Fase 0 — QRCode confirmación pip | **Ejecutada** | `203a293` |
| Fase 0 — `pilecap_utils` migración completa | **Aplazada**, tal como decidiste — no ejecutada. | — |
| **Fase 1** — `DB.ICollection` → `List[ElementId]` | **Ejecutada** — rutas nuevas: `Data.panel/ModelCleanup.pushbutton/lib/logic.py`, `Structures.panel/QA.pulldown/FamilyAudit.pushbutton/lib/logic.py`, `Structures.panel/Quantities.pulldown/MaterialManager.pushbutton/lib/logic.py` (FamilyAudit y MaterialManager se habían movido de Data.panel a Structures.panel) | `2dc82a3` |
| **Fase 2** — bug de burbujas de grid | **No hizo falta** — ya corregido por el refactor: `AnnotationSuite.pushbutton` (el hub activo) usa `GridBubbleBatch.pushbutton/lib/logic.py`, que ya tiene `ShowBubbleInView`/`HideBubbleInView` separados correctamente. La copia vieja con el bug sigue en `AnnotationBatch.nobutton` pero es código muerto (nada la llama). | — |
| **Fase 3** — conteo de fallos en cotas de arco | **Ejecutada** — el bug sobrevivió a la fusión, pero en un archivo nuevo: `Documentation.panel/Annotations.pulldown/AnnotationHub.pushbutton/lib/ui.py` (la rama de muros curvos nunca incrementaba `failed`) | `975a52d` |
| **Fase 4** — `doc`/`uidoc` obsoletos en pilecap_utils | **No hizo falta** — ya corregido: `creation.py`/`data_retrieval.py`/`ui.py` ahora usan funciones `_doc()`/`_uidoc()` que releen `revit.doc`/`revit.uidoc` en cada llamada. | — |
| **Fase 5** — colores XAML de DiRootsHub | **No hizo falta** — DiRootsHub ya no existe; su sucesor `Data.panel/ParameterHub.pushbutton/lib/ui.xaml` ya tiene los 5 recursos de color completos. | — |

**3 de 8 puntos de Nivel 1 requirieron cambio de código real; los otros 5 ya estaban resueltos por el refactor previo.** Esto no es infrecuente en un ciclo de auditoría→refactor→re-auditoría: los bugs de arquitectura tienden a desaparecer solos cuando se consolida código, mientras que aparecen bugs nuevos en las costuras de la fusión (como el de Fase 3, que sobrevivió literalmente byte-a-byte en el archivo nuevo).

### Hallazgos nuevos de alta prioridad descubiertos en la reconciliación (propuestos, NO ejecutados — a decidir en el próximo checkpoint)

Estos no estaban en las Fases 1-8 originales porque no existían o no se habían localizado en el worktree de auditoría. Quedan pendientes de que decidas si entran en Nivel 1/2 o se posponen:

- **C5-bis — `ExportSheets/lib/config.py:86-105,109`** (Documentation.panel/Issue.pulldown): enums `DB.RasterQualityType`/`DB.ColorDepthType`/`DB.ACADVersion`/`DB.ExportColorMode` evaluados en el cuerpo de la clase `Config` (nivel de módulo) + `Config.ensure_dirs()` crea carpetas al importar. Viola la regla explícita de `AUDIT_REFACTOR_PLAN.md` §6 ("BuiltInCategory y llamadas Revit API jamás a nivel de módulo"). Riesgo real: en multi-Revit, importar este módulo antes de que el contexto de Revit esté listo puede fallar. **Candidato a Fase 1-bis** (bajo riesgo, cambio mecánico: mover a lazy-load dentro de `__init__`/métodos).
- **C6 — ClashReport `_log_debug(msg, exc=None): pass`** (`Structures.panel/QA.pulldown/ClashReport.pushbutton/lib/logic.py:13-14`): sigue siendo un no-op total: todos los fallos de geometría se descartan sin ningún rastro. Con la Regla 2 de `AUDIT_REFACTOR_PLAN.md` (política anti-silencio / `telemetry.log_error`) ya construida y disponible, esto es un candidato barato: sustituir el cuerpo por una llamada a `nosa_utils.telemetry.log_error`.
- **AddPileToPilecap — config fragmentada, ahora híbrida** (`Foundations.panel/PileTools.pulldown/AddPileToPilecap.pushbutton/lib/logic.py:16,36` + `lib/ui.py:55`): usa `ConfigManager` (ruta incorrecta, sin `Extensions/NOSA.extension/`) para spacing/pile_type/embedment Y `NOSAWindow.LoadConfig()` para otro estado, en el mismo plugin. Empeoró respecto a la auditoría original (antes solo usaba un sistema incorrecto, ahora usa dos a la vez).
- **AddPileToPilecap — `point_in_face()` con bloque inalcanzable y `NameError` latente** (`lib/logic.py:408-448`, movido desde el antiguo `script.py` monolítico durante la consolidación — el bug se copió intacto).
- **`lib/nosa_utils/__init__.py` — el import eager EMPEORÓ**: pasó de 5 a ~20 submódulos importados de forma eager a nivel de paquete (incluye ahora `base_window` y `theme`, que no estaban antes). Cualquier `from nosa_utils.X import Y`, sin importar cuán ligero sea `X`, arrastra la API de Revit completa. Dado que esto afecta potencialmente a los ~88 plugins, es de las piezas de mayor apalancamiento del plan, pero también de mayor riesgo de regresión si algo dependía implícitamente del import eager — requiere probar contra una muestra amplia antes de aplicar.
- **Infraestructura construida pero no adoptada** (confirma y agrava el EJE A de `INFORME_FINAL.txt`): `export_io.py` (1/88 consumidores), `pilecap_utils` (0/88), `nosa_utils.solids` (1/88 — solo ClashReport), `bootstrap.py` (0/155 archivos con `imp.load_source`). El propio `AUDIT_REFACTOR_PLAN.md` reconoce que la migración de `imp` a `bootstrap` se difirió; los otros tres módulos ni siquiera se mencionan como pendientes de adopción en ese documento pese a tener consumo casi nulo.
- **Duplicación de colector "vistas sin plantilla" y "aplicar plantilla" — EMPEORARON**: 8 sitios en 5 archivos (antes 6) y 4 sitios (antes 2) respectivamente, repartidos ahora entre `.nobutton` huérfanos y los pushbuttons activos `ViewManager`/`ViewTemplateManager`. Nadie usa `nosa_utils.collectors` (existente desde Bloque 1) para esto.
- **`ElementJoin`/"SmartJoin"** sigue sin unificar (Fase 7 original, sin cambios) — y ahora hay una inconsistencia adicional: `lib/ui.py:209` tiene una transacción sin prefijo "NOSA — " mientras `lib/logic.py:223,281` sí lo tienen, en el mismo plugin.
- **`CenterBeamToColumn.pushbutton`** sigue siendo un script monolítico sin `lib/` ni `NOSAWindow` — el único de los pushbuttons de Structures.panel que no adoptó el patrón estándar.

---

## Nivel 0 — Antes de tocar código

**Fase 0.** Decisiones que necesito de ti antes de planificar el detalle de algunas fases (no bloquean empezar por la Fase 1):

- ~~**RevisionTracker** (Structures.panel)~~ — **resuelto en la reconciliación**: ya no hace falta, la implementación actual gestiona revisiones Revit de verdad.
- ~~**PilecapLoadChecker**~~ — **resuelto y ejecutado** (commit `14f2b79`).
- ~~**QRCode — auto-instalación**~~ — **resuelto y ejecutado** (commit `203a293`).
- **`lib/pilecap_utils`**: ¿migramos `AddPileToPilecap`/`CreatePilecapType` para que lo usen de verdad (elimina ~2 duplicaciones grandes), o preferís mantenerlos independientes por ahora? — **sigue pendiente de tu decisión**, la migración completa (Fase 13) sigue aplazada tal como pediste.

---

## Nivel 1 — Bugs reales (rompen funcionalidad hoy)

### Fase 1 — ✅ EJECUTADA (commit `2dc82a3`) — Arreglar `doc.Delete(DB.ICollection[...])` (purgas que nunca han borrado nada)
- **Qué**: sustituir `DB.ICollection[DB.ElementId]([...])` por `System.Collections.Generic.List[DB.ElementId]([...])` (patrón ya correcto en `ModelCleanup/lib/ui.py:160-163`) en los 8 sitios de:
  - `Documentation.panel/Views.pulldown/ModelCleanup.pushbutton/lib/logic.py:54,102,136,180,230`
  - `Data.panel/FamilyAudit.pushbutton/lib/logic.py:169,179`
  - `Structures.panel/Quantities.pulldown/MaterialManager.pushbutton/lib/logic.py:107`
- **Riesgo**: bajo — es un cambio de una línea por sitio, mismo comportamiento pretendido, ahora funcional en vez de fallar silenciosamente.
- **Verificación**: cada una de las 5 purgas de ModelCleanup borra de verdad (antes: 0 elementos borrados, "Failed" > 0; después: elementos borrados, "Created"/resultado > 0). Igual para purga de familias en FamilyAudit y borrado de materiales en MaterialManager.
- **Commit sugerido**: `fix: use List[ElementId] instead of invalid ICollection[ElementId] in bulk deletes`

### Fase 2 — ✅ NO HIZO FALTA (ya corregido por el refactor previo) — Arreglar bug de burbujas de grid (AnnotationBatch)
- **Qué**: `Documentation.panel/Annotations.pulldown/AnnotationBatch.pushbutton/lib/logic.py:182-183` — la rama "ocultar" debe usar `DB.DatumEnds.End1` en vez de repetir `End0`.
- **Riesgo**: muy bajo, una línea.
- **Verificación**: con una grid seleccionada, "Hide bubbles" oculta la burbuja en ambos extremos, no solo en uno.
- **Commit sugerido**: `fix: AnnotationBatch hide-bubble action was targeting End0 twice`

### Fase 3 — ✅ EJECUTADA (commit `975a52d`, en AnnotationHub.pushbutton tras la fusión) — Contar de verdad los fallos de cota de arco (DimensionWalls)
- **Qué**: en `lib/logic.py:232-234,279-281` y `lib/ui.py:161-167`, que el `except Exception` de la rama de cotas de arco/radio incremente el contador de fallos en vez de descartarse en silencio.
- **Riesgo**: bajo — solo cambia qué se reporta al usuario, no la lógica de creación.
- **Verificación**: en un modelo con muros curvos que no se puedan acotar, el resultado final muestra "Failed: N" > 0 en vez de "Failed: 0" engañoso.
- **Commit sugerido**: `fix: DimensionWalls now reports arc-dimension failures instead of silently dropping them`

### Fase 4 — ✅ NO HIZO FALTA (ya corregido por el refactor previo) — Referencia de documento obsoleta en `pilecap_utils`
- **Qué**: en `lib/pilecap_utils/creation.py:16-17` y `data_retrieval.py:24`, quitar `doc = revit.doc` / `uidoc = revit.uidoc` a nivel de módulo; pasar `doc`/`uidoc` como parámetro explícito a cada función pública (o releer `revit.doc` dentro de cada función en vez de cachearlo).
- **Riesgo**: medio — toca la firma de varias funciones internas; hay que revisar los 3 consumidores actuales (`AddPileToPilecap`, `CreatePilecapType`, y cualquier futuro consumidor de la Fase 13) para pasar el documento explícitamente. Como confirmó la auditoría, **hoy nadie usa `pilecap_utils.creation`/`data_retrieval` en producción** (los pushbuttons reimplementan su propia lógica), así que el riesgo real de romper algo visible es bajo — pero es la base necesaria para la Fase 13.
- **Verificación**: no hay UI que ejercite este archivo directamente hoy; verificación = revisión de código + (si se hace junto a la Fase 13) prueba de creación de encepado en dos documentos abiertos a la vez sin recargar pyRevit.
- **Commit sugerido**: `fix: stop caching doc/uidoc at module level in pilecap_utils`

### Fase 5 — ✅ NO HIZO FALTA (DiRootsHub ya no existe; su sucesor ParameterHub ya tiene los 5 colores) — Recursos de color que faltan en DiRootsHub (dark mode roto a medias)
- **Qué**: añadir `PanelColor` y `BorderColor` a `Documentation... /DiRootsHub.pushbutton/lib/ui.xaml:6-9` (o el panel que corresponda; ver AUDITORIA 1.2) junto a los 3 que ya existen.
- **Riesgo**: muy bajo, solo XAML.
- **Verificación**: alternar dark mode en DiRootsHub cambia los 5 colores, no solo 3.
- **Commit sugerido**: `fix: add missing PanelColor/BorderColor resources to DiRootsHub XAML`

---

## Nivel 2 — Desajustes doc/nombre/función (pueden llevar a decisiones erróneas)

### Fase 6 — ✅ COMPLETA (ver RECONCILIACIÓN arriba) — Corregir docstrings de RevisionTracker y PilecapLoadChecker
- RevisionTracker no necesitó cambio (ya gestiona `DB.Revision` real). PilecapLoadChecker corregido en el commit `14f2b79`.

### Fase 7 — Unificar nombre público/interno de ElementJoin ("SmartJoin")
- **Qué**: elegir un solo nombre (recomendado: quedarse con "SmartJoin" ya que así se llama en config/transacciones/clase, y renombrar solo el título visible si hace falta, o al revés) y aplicarlo consistentemente en `Structures.panel/Elements.pulldown/ElementJoin.pushbutton/`.
- **Riesgo**: bajo si solo se tocan strings/nombres de archivo de config (`_smartjoin.json`) — **cuidado**: si se renombra el archivo de config, los usuarios existentes pierden su configuración guardada salvo que se migre el archivo antiguo.
- **Verificación**: abrir el plugin, comprobar que título de ventana/config/transacciones usan el mismo nombre.
- **Commit sugerido**: `refactor: unify ElementJoin/SmartJoin naming`

---

## Nivel 3 — Arquitectura y duplicación

### Fase 8 — Consolidar `get_id_value` en Structures.panel
- **Qué**: sustituir las 7 reimplementaciones idénticas (`ConnectionChecker`, `HealthScore`, `WarningsTriage`, `ElementJoin`, `RebarCoverage`, `QuantificationQA`, `RevisionTracker`) por `from nosa_utils.revit_helpers import get_id_value`.
- **Riesgo**: muy bajo — la función es idéntica byte a byte según la auditoría.
- **Verificación**: smoke test de los 7 pushbuttons (abren y ejecutan sin error de import).
- **Commit sugerido**: `refactor: use shared get_id_value from nosa_utils instead of 7 local copies`

### Fase 9 — Consolidar helpers de proximidad/geometría
- **Qué**: mover la lógica repetida de `ClashReport` (intersección de sólidos), `ConnectionChecker` (proximidad de extremos), `ElementJoin` (tolerancia bbox), `CenterBeamToColumn`/`WaffleSlab` (centro + distancia 2D) a funciones nuevas o ya existentes en `lib/nosa_utils/geometry.py`, y hacer que los 5 pushbuttons las llamen.
- **Riesgo**: medio-alto — es la refactorización más extensa del plan; tocar 5 pushbuttons que ya funcionan. Dividir en sub-fases por pushbutton si se ejecuta (9a ClashReport, 9b ConnectionChecker, 9c ElementJoin, 9d CenterBeamToColumn+WaffleSlab), cada una committeable por separado.
- **Verificación**: cada pushbutton reproduce exactamente los mismos resultados que antes de la refactorización sobre el mismo modelo de prueba (comparar output antes/después).
- **Commit sugerido**: `refactor: extract shared proximity/geometry helpers to nosa_utils.geometry` (uno por sub-fase)

### Fase 10 — Unificar conversión mm↔ft
- **Qué**: sustituir el literal `304.8`/`0.3048` por `nosa_utils.unit_conversion.mm_to_feet/feet_to_mm` en los ~10 archivos listados en AUDITORIA §MEDIO, empezando por `WaffleSlab/script.py:35-36` (que además corrige una pérdida de precisión real).
- **Riesgo**: bajo, pero amplio en superficie (muchos archivos) — hacerlo archivo por archivo o agrupado por panel, cada grupo en su commit.
- **Verificación**: valores dimensionales (spacing, cutoff, thickness, etc.) idénticos antes/después en cada herramienta tocada.
- **Commit sugerido**: `refactor: replace hardcoded 304.8 conversions with nosa_utils.unit_conversion`

### Fase 11 — Unificar persistencia de configuración
- **Qué**: migrar `AddPileToPilecap` y `ExportScheduleToExcel` (los únicos usuarios de `ConfigManager`/`ConfigHelper`) al patrón `NOSAWindow.SaveConfig/LoadConfig`, o como mínimo apuntar `ConfigManager.DEFAULT_CONFIG_DIR` a la misma carpeta que usa `NOSAWindow` (`%APPDATA%/pyRevit/Extensions/NOSA.extension/NOSA_Configs/`).
- **Riesgo**: medio — cualquier configuración ya guardada en la carpeta incorrecta actual se "pierde" desde el punto de vista del usuario salvo que se migre el archivo existente a la nueva ruta como parte del cambio.
- **Verificación**: guardar una preferencia, cerrar Revit, reabrir, comprobar que se recupera desde la carpeta correcta.
- **Commit sugerido**: `fix: unify config persistence path for AddPileToPilecap/ExportScheduleToExcel`

### Fase 12 — Dejar de importar todo de forma eager en `__init__.py`
- **Qué**: en `lib/nosa_utils/__init__.py` y `lib/pilecap_utils/__init__.py`, quitar los `from . import X` a nivel de paquete; cada consumidor importa explícitamente el submódulo concreto que necesita (`from nosa_utils.theme import ThemeManager`, que ya es como se usa hoy en la práctica).
- **Riesgo**: medio — hay que comprobar que ningún archivo dependía del import implícito vía `nosa_utils.geometry.xxx` tras solo hacer `import nosa_utils`.
- **Verificación**: smoke test de una muestra representativa de pushbuttons de cada panel (los que más usan `nosa_utils`).
- **Commit sugerido**: `refactor: make nosa_utils/pilecap_utils __init__.py lazy instead of eager-importing Revit API`

### Fase 13 — Migrar creación de pilotes/encepados a `pilecap_utils` de verdad
- **Qué**: (depende de la Fase 4) hacer que `AddPileToPilecap` y `CreatePilecapType` llamen a `pilecap_utils.creation`/`data_retrieval`/`geometry`/`validation` en vez de reimplementar la lógica.
- **Riesgo**: alto — es la refactorización de mayor riesgo del plan (toca creación real de elementos estructurales). Solo abordar si respondiste "sí" en la Fase 0; dividir en 2 sub-fases (13a `CreatePilecapType`, 13b `AddPileToPilecap`), cada una con pruebas exhaustivas antes de tocar la siguiente.
- **Verificación**: crear un encepado con los mismos parámetros antes/después de la migración produce geometría idéntica (mismas coordenadas de pilotes, mismo espesor de losa, mismo offset).
- **Commit sugerido**: `refactor: CreatePilecapType now uses shared pilecap_utils instead of duplicated logic`

### Fase 14 — Migrar ventanas restantes a `NOSAWindow`
- **Qué**: `PileMaster`, `DimensionWalls`, `TagAll`, `ExportSheets`, `AlignViewTitles`, `CopyViewTemplates`, `QRCode` (Documentation panel, orden recomendado: los más pequeños primero — `AlignViewTitles`, `CopyViewTemplates` — dejando `ExportSheets` y `PileMaster`, los más grandes, para el final).
- **Riesgo**: medio por herramienta — cada una es su propia sub-fase y commit; el mayor riesgo es romper persistencia de config existente si el `plugin_key` no coincide con el nombre de archivo de config actual de la herramienta.
- **Verificación**: dark mode funciona, tamaño de ventana se recuerda entre sesiones, resto de funcionalidad sin regresión (checklist específico por herramienta en `PLAN_PRUEBAS.md`).
- **Commit sugerido**: `refactor: migrate <Tool> to NOSAWindow` (uno por herramienta)

---

## Nivel 4 — Cosmético / limpieza final

### Fase 15 — Borrar código muerto confirmado
- **Qué**: eliminar las funciones/archivos de AUDITORIA §2.1 (`export_csv` en BulkParameterEditor, `_instance_count` en FamilyAudit, `collect_concrete_quantities`/`aggregate_by_level_category` v1 en QuantificationQA, `logger` sin usar en RevisionTracker, `get_available_categories` import en RebarCoverage, `get_tag_types_for_category`/`get_spot_elevation_types`/`batch_spot_elevations` en AnnotationBatch, `diagnose_tags_in_project` en TagAll, `lib/_demo_ec_levels.py` completo en QRCode, el `sys.path` muerto en CreatePilecapType, y el bloque inalcanzable con `NameError` latente en `point_in_face` de AddPileToPilecap).
- **Riesgo**: bajo — por definición, código no referenciado.
- **Verificación**: cada pushbutton tocado sigue abriendo y funcionando igual (smoke test).
- **Commit sugerido**: `chore: remove confirmed dead code` (se puede agrupar en 1-2 commits)

### Fase 16 — Limpieza de nombres y archivos sueltos
- **Qué**: unificar casing de icono (`Icon.png` → `icon.png`), corregir `WaffleSlab/script.py:2` (`\\n` → `\n`), renombrar `NOSA.pushbutton` (si se decide), quitar `MEJORAS_APLICADAS.md` del bundle de `CreatePilecapType` (mover a documentación interna del repo si tiene valor histórico, o borrar).
- **Riesgo**: muy bajo.
- **Verificación**: el título del botón "Waffle / Slab" se ve en dos líneas en el ribbon; iconos se siguen mostrando.
- **Commit sugerido**: `chore: naming and packaging cleanup`

### Fase 17 (opcional) — Consistencia de idioma
- **Qué**: decidir si se traduce `pilecap_utils`/`WaffleSlab` internals al inglés (para que coincida con el resto de la extensión) o si se adopta `nosa_utils.i18n` de verdad en más plugins en vez de dejarlo semi-usado. Esto es una decisión de producto, no una corrección de bug — proponer solo si hay presupuesto de tiempo después de las fases anteriores.
- **Riesgo**: bajo técnicamente, pero de alcance amplio.
- **Commit sugerido**: a definir según alcance elegido.

---

## Orden de ejecución recomendado

```
Fase 0 (decisiones) → 1 → 2 → 3 → 4 → 5   (bugs reales, cada una aislada)
                    → 6 → 7                (desajustes doc/nombre)
                    → 8 → 10               (duplicación de bajo riesgo)
                    → 12                   (arquitectura de imports)
                    → 9 (9a..9d)           (duplicación de geometría, mayor riesgo)
                    → 11                   (config persistence)
                    → 14 (por herramienta) (adopción NOSAWindow)
                    → 13 (13a, 13b)        (pilecap_utils — el más arriesgado, al final)
                    → 15 → 16 → 17         (limpieza final, cosmético)
```

Cada fase de este plan es intencionadamente pequeña; si alguna fase de "Nivel 3" resulta ser más grande de lo esperado al abordarla, se puede volver a partir en sub-fases sin renumerar el resto.
