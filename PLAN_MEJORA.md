# Plan de mejora — NOSA.extension

Basado en `AUDITORIA.md`. Cada fase es pequeña, tocando el mínimo número de archivos, verificable manualmente en Revit (ver `PLAN_PRUEBAS.md` para el detalle de cada prueba) y pensada para un commit propio. Orden: primero bugs reales en producción, después desajustes de documentación/nombre, después arquitectura/duplicación, por último cosmético.

No ejecutar todavía — esto es la planificación. Antes de dar cada fase por terminada: `/verification-before-completion`. Al cerrar cada fase: `/commit-work`.

---

## ⚠ Hallazgo sistémico nuevo — bare `.Name` roto bajo pyRevit 6.5/CPython (2026-07-28)

MaterialManager reveló, con datos reales (diagnóstico de categorías), que `el_type.Name` (acceso directo a la propiedad, sin `BuiltInParameter`) lanza `AttributeError` en el entorno del usuario (Revit 2026, pyRevit 6.5.0.26173, motor CPython/pythonnet — no IronPython). Se confirmó también en `DimensionWalls` que `Document.Create.NewRadialDimension` no se resuelve como atributo en el mismo entorno. Ambos son síntomas de que **algunas propiedades/métodos de la API de Revit no se resuelven igual bajo pythonnet que bajo IronPython** en esta combinación concreta de versiones — justo el tipo de riesgo multi-runtime que ya preocupaba de antemano.

**Alcance sin acotar todavía**: un grep de `.Name` en todo `NOSA.tab` da 143 archivos / ~499 apariciones — una cota superior muy ruidosa (incluye nombres de controles WPF, variables Python, etc., no solo llamadas a la API de Revit), no una lista de bugs confirmados. **No se ha hecho un barrido general** — solo se corrigieron los sitios concretos de MaterialManager donde se confirmó el fallo en vivo.

**Recomendación para una sesión futura**: auditar sistemáticamente los usos de `.Name` sobre objetos de la API de Revit (`Element`, `ElementType`, `Category`, `Material`, etc.) en los ~88 plugins, priorizando por uso, y sustituir por `nosa_utils.revit_helpers.get_element_type_name()` / `getattr(el, 'Name', None)` donde corresponda. Dado que esto podría explicar fallos silenciosos aún no reportados en otras herramientas, tiene prioridad alta pero alcance grande — candidato a su propia fase dedicada, no a un fix rápido.

---

## Hallazgos de pruebas en vivo — 2026-07-28 (fuera de la numeración de fases, ejecutados igualmente)

Tras el Checkpoint A, el usuario probó en Revit y reportó 2 cosas que no estaban en la auditoría original (ambas ya resueltas):

- **MaterialManager — "no encuentra elementos" (commit `e6b6fb6`)**: el escaneo de la pestaña Elements solo cubría 5 categorías fijas (Framing/Columns/Walls/Floors/Foundation) sin ninguna vía alternativa. El usuario confirmó que sus elementos objetivo incluían categorías fuera de esa lista (Generic Models / familias in-place). Se revisó todo el código del escaneo, filtros y binding del grid — sin bug estático encontrado en la ruta de las 5 categorías — y se añadió un modo "Use current selection (any category)" como vía alternativa, sin quitar el escaneo por categoría existente.
- **AddPileToPilecap — sin vista previa (commit `dd50373`)**: se añadió un Canvas de previsualización igual al de CreatePilecapType (contorno de losa + puntos de pilotes a escala), actualizado en vivo según patrón/spacing/embedment/distribución. Se extrajo `_compute_grid_points()` para que la previsualización y la creación real usen exactamente el mismo cálculo — el modo "Manual" (picking interactivo) no tiene previsualización estática posible, se indica así en el panel.

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

### Fase 7 — ✅ EJECUTADA (commit `2e19333`) — Unificar nombre público/interno de ElementJoin ("SmartJoin")
- Se mantuvo "SmartJoin" en los identificadores internos (config `_smartjoin.json`, `plugin_key='smartjoin_pro'`, comentario de docstring) — cero riesgo de pérdida de configuración de usuarios existentes. Se alinearon a "Element Join" los 4 sitios visibles: `Title` de la ventana, cabecera `TextBlock` dentro de la ventana, y 3 nombres de transacción (2 en `logic.py` + 1 en `ui.py`, esta última además corregida para llevar el prefijo "NOSA — " que le faltaba).

---

## Nivel 3 — Arquitectura y duplicación

### Fase 8 — ✅ NO HIZO FALTA — Consolidar `get_id_value`
- Reconciliación confirmó 7/7 ya usan `from nosa_utils.revit_helpers import get_id_value`; verificado además con un grep de todo el árbol (no solo Structures.panel): 0 reimplementaciones locales, 0 usos de `.IntegerValue` fuera de `revit_helpers.py` (que es la implementación canónica). Sin cambios necesarios.

### Fase 9 — ✅ EJECUTADA (commits `b817345`, `493dbf2`) — Consolidar helpers de proximidad/geometría
- **9a/9b** (`b817345`): `CenterBeamToColumn` y `WaffleSlab` reimplementaban localmente `get_element_center`/`calculate_distance_2d`/`calculate_distance_3d`, ya existentes en `nosa_utils.geometry`. Ambos delegan ahora al módulo compartido (mismo resultado para elementos con `Location`; el helper compartido además cubre el caso sin `Location` vía bounding-box, que las copias locales no manejaban).
- **9c** (`493dbf2`): `ClashReport.bounding_boxes_intersect` y `ElementJoin._bboxes_within_tolerance` reimplementaban el mismo test de solape de bounding-box en 3 ejes (la única diferencia real era el margen de tolerancia de `ElementJoin`). Añadido `nosa_utils.geometry.bboxes_overlap(bbox1, bbox2, tolerance_ft=0.0)` y ambos pushbuttons ahora lo usan.
- **ConnectionChecker — sin cambios, y así debe quedar**: al revisar `check_beam_joins`, la "proximidad de extremos" ya usa el filtro espacial nativo de Revit (`DB.Outline` + `BoundingBoxIntersectsFilter`), no una reimplementación manual de distancia/bbox — no hay duplicación real que extraer aquí. Forzar una abstracción compartida solo para que encajara con el plan habría sido una abstracción prematura sin duplicación real detrás; se descarta.
- **Riesgo real vs. estimado**: bajo, no medio-alto — la duplicación real resultó ser pequeña y mecánica (delegar a funciones ya existentes), no una refactorización profunda de 5 pushbuttons.

### Fase 10 — ⏸ APLAZADA (alcance real 4× mayor de lo estimado) — Unificar conversión mm↔ft
- **Qué cambió al re-escanear todo el árbol** (no solo los ~10 archivos originales): **43 archivos** en los 5 paneles definen su propia constante `304.8`/`0.3048` (`FT2MM`, `_FT_TO_MM`, `MM_TO_FEET`, etc.) en vez de importar `nosa_utils.unit_conversion`. Todas las constantes encontradas son **matemáticamente correctas** — a diferencia de lo que decía la auditoría original, `WaffleSlab/lib/logic.py:20` ya usa `1.0 / 304.8` exacto (la versión redondeada `0.00328084` que motivó ese hallazgo ya no existe, corregida en el refactor previo). Es decir: **no hay ningún bug detrás de esta fase, solo duplicación de una constante correcta en 43 sitios.**
- **Decisión**: dado que (a) no corrige ningún bug real, (b) tocar 43 archivos en una sola sesión no encaja con "cada fase pequeña y verificable", y (c) el riesgo de introducir una errata al tocar tantos sitios a la vez supera el beneficio cosmético — **la aplazo a Nivel 4 (cosmético)**, dividida por panel en sub-fases futuras si se decide abordarla, en vez de ejecutarla ahora dentro de Nivel 3.
- **Commit sugerido** (si se retoma): `refactor: replace hardcoded 304.8 conversions with nosa_utils.unit_conversion` (uno por panel/sub-fase)

### Fase 11 — Unificar persistencia de configuración
- **Qué**: migrar `AddPileToPilecap` y `ExportScheduleToExcel` (los únicos usuarios de `ConfigManager`/`ConfigHelper`) al patrón `NOSAWindow.SaveConfig/LoadConfig`, o como mínimo apuntar `ConfigManager.DEFAULT_CONFIG_DIR` a la misma carpeta que usa `NOSAWindow` (`%APPDATA%/pyRevit/Extensions/NOSA.extension/NOSA_Configs/`).
- **Riesgo**: medio — cualquier configuración ya guardada en la carpeta incorrecta actual se "pierde" desde el punto de vista del usuario salvo que se migre el archivo existente a la nueva ruta como parte del cambio.
- **Verificación**: guardar una preferencia, cerrar Revit, reabrir, comprobar que se recupera desde la carpeta correcta.
- **Commit sugerido**: `fix: unify config persistence path for AddPileToPilecap/ExportScheduleToExcel`

### Fase 12 — ✅ EJECUTADA (commit `529400c`) — Dejar de importar todo de forma eager en `__init__.py`
- Antes de tocar nada, se verificó con grep en todo `NOSA.tab`: **0 archivos** hacen `import nosa_utils`/`import pilecap_utils` a secas seguido de acceso por atributo (`nosa_utils.geometry.foo()`) — todo el árbol ya usa `from nosa_utils.X import Y` explícito, así que nada dependía del import eager. Se vació `lib/nosa_utils/__init__.py` (pasó de ~20 imports eager a solo docstring/versión) y `lib/pilecap_utils/__init__.py` (de 5 a 0).
- Nota: no se usó `__getattr__` a nivel de módulo (PEP 562) porque IronPython 2.7 no lo soporta y el código debe funcionar en ambos runtimes — se optó por la solución más simple y más compatible: no importar nada en `__init__.py`.

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
