# Plan de pruebas manuales — NOSA.extension

Checklist de verificación en Revit para cada fase de `PLAN_MEJORA.md`. Complementa (no sustituye) `QA_CHECKLIST.md` y `RELEASE_READY_QA_CHECKLIST.md` ya existentes en la raíz — úsalos como smoke test general antes/después de cada tanda de fases; este documento se centra en verificar específicamente lo que cada fase cambia.

## Preparación

- Modelo de prueba recomendado: un modelo estructural real (o una copia de sandbox) con: vistas huérfanas, familias sin usar, algún muro curvo, al menos una grid, varios pilotes/encepados existentes, warnings de Revit variados, y elementos sin material asignado — para poder ejercer las purgas y comprobaciones sin depender de un modelo vacío.
- Ten pyRevit en modo que permita recargar la extensión (`Reload` en el panel pyRevit) entre fases — varios bugs de esta auditoría son "cacheo de módulo", así que recarga siempre antes de repetir una prueba tras un cambio de código.
- Anota resultados "antes" de cada fix cuando el bug sea reproducible (p. ej. "purga borra 0 elementos") para poder comparar con el "después".

---

## Fase 1 — `doc.Delete(ICollection[...])` → `List[ElementId]`

**ModelCleanup** (`Documentation > Views > Model Cleanup`)
1. Abrir el tool en un modelo con vistas huérfanas conocidas (crea 2-3 vistas sin usar si no hay).
2. Ejecutar "Purge Orphan Views". Antes del fix: 0 borrados, contador "Failed" > 0. Después del fix: las vistas desaparecen del modelo y el contador de éxito > 0.
3. Repetir para: familias sin usar, plantillas sin usar, imports CAD, rooms sin colocar — cada una debe borrar de verdad al menos un elemento de prueba conocido.

**FamilyAudit** (`Data > Family Audit`)
4. Seleccionar una familia sin usar de prueba → "Purge Families" → confirmar que desaparece del modelo (antes: permanecía).

**MaterialManager** (`Structures > Quantities > Material Manager`)
5. Crear un material de prueba sin uso → "Delete Materials" → confirmar que desaparece de la lista de materiales del proyecto (antes: permanecía, marcado como fallo).

---

## Fase 2 — Burbujas de grid (AnnotationBatch)

1. `Documentation > Annotations > Annotation Batch` → pestaña Grid Bubbles.
2. Seleccionar una grid con burbujas visibles en ambos extremos.
3. "Hide bubbles" → ambos extremos deben ocultarse (antes: solo `End0`, `End1` seguía visible).
4. "Show bubbles" → ambos extremos reaparecen.

---

## Fase 3 — Contador de fallos en DimensionWalls

1. `Documentation > Annotations > Dimension Walls`.
2. Incluir al menos un muro curvo en la selección/vista.
3. Ejecutar. El resultado final debe mostrar "Failed" > 0 reflejando el muro curvo no acotado (antes: "Failed: 0" pese al fallo real).
4. Confirmar que los muros rectos sí se acotan correctamente (sin regresión).

---

## Fase 4 — `doc`/`uidoc` obsoletos en `pilecap_utils`

No hay UI directa hoy (nadie usa el módulo en producción según la auditoría). Verificación = revisión de código (las funciones ya no leen `doc`/`uidoc` de una variable de módulo). Si esta fase se hace junto con la Fase 13:
1. Abrir Documento A, crear un encepado.
2. Sin cerrar Revit, abrir/activar Documento B (otro proyecto).
3. Crear un encepado en Documento B.
4. Confirmar que el encepado se crea en Documento B, no en el A (el bug haría que, si el módulo estaba cacheado, operara sobre A).

---

## Fase 5 — Colores de tema en DiRootsHub

1. `Data > DiRoots Hub`.
2. Alternar el checkbox de dark mode.
3. Confirmar que **los 5** elementos de color cambian (fondo, panel, texto, acento, borde) — antes del fix, 2 de los 5 no cambiaban tras el primer toggle (o la ventana lanzaba error silencioso al aplicar tema).

---

## Fase 6 — Docstrings RevisionTracker / PilecapLoadChecker

1. Pasar el ratón sobre el botón en el ribbon → el tooltip debe describir lo que la herramienta hace de verdad.
2. Abrir cada tool y confirmar que el texto de la ventana (si lo hay) es coherente con el tooltip corregido.
3. Sin cambios funcionales — no requiere prueba sobre el modelo, solo revisión visual del texto.

---

## Fase 7 — Unificar naming ElementJoin/SmartJoin

1. Abrir `Structures > Elements > Element Join`.
2. Antes de la fase: guardar una preferencia (p. ej. modo de join elegido), cerrar, reabrir, confirmar que se recupera.
3. Tras el rename: repetir el mismo paso — la preferencia debe seguir recuperándose (si se migró el archivo de config) o, si no se migró, verificar explícitamente que esto se comunicó como pérdida de configuración esperada.
4. Confirmar que título de ventana, cualquier mensaje de resultado, y nombre de archivo de config usan el mismo nombre consistentemente.

---

## Fase 8 — Consolidar `get_id_value`

Smoke test de los 7 pushbuttons tocados (deben abrir y ejecutar igual que antes, sin excepción de import):
- [ ] ConnectionChecker — ejecuta sobre selección de vigas/columnas, resultado idéntico a antes del refactor.
- [ ] HealthScore — score idéntico sobre el mismo modelo, antes/después.
- [ ] WarningsTriage — mismo número de warnings clasificados.
- [ ] ElementJoin — mismo comportamiento de join/unjoin.
- [ ] RebarCoverage — mismo % de cobertura.
- [ ] QuantificationQA — mismas cantidades en el export.
- [ ] RevisionTracker — snapshot/diff produce el mismo JSON de salida.

---

## Fase 9 — Helpers de geometría/proximidad compartidos (por sub-fase)

Para cada pushbutton migrado, comparar resultado **antes/después** sobre el mismo modelo y misma selección:
- **9a ClashReport**: mismo número de clashes detectados, mismos volúmenes de intersección reportados.
- **9b ConnectionChecker**: mismas conexiones marcadas como "sin unir".
- **9c ElementJoin**: mismo resultado de join/unjoin sobre el mismo conjunto de elementos.
- **9d CenterBeamToColumn / WaffleSlab**: vigas centradas en la misma posición; forjado reticular genera los mismos huecos/zonas macizadas.

---

## Fase 10 — Conversión mm↔ft unificada

Para cada herramienta tocada, introducir un valor conocido (p. ej. spacing = 1500 mm) y confirmar que el valor resultante en el modelo (en pies, unidad interna de Revit) es idéntico antes y después del cambio — especial atención a **WaffleSlab**, donde el fix corrige una pérdida de precisión: comparar la dimensión resultante con más decimales de precisión que antes.

---

## Fase 11 — Persistencia de configuración unificada

1. En `AddPileToPilecap`, guardar una preferencia (último tipo de pilote usado, por ejemplo).
2. Cerrar Revit completamente.
3. Reabrir, abrir la herramienta, confirmar que la preferencia se recupera desde la nueva ruta unificada.
4. Repetir para `ExportScheduleToExcel` (última ruta de exportación usada).
5. Si existía una configuración previa en la ruta antigua (`%APPDATA%/pyRevit/NOSA_Configs/`), confirmar si se migró o si el usuario debe reconfigurar una vez (documentar cuál de las dos ocurrió).

---

## Fase 12 — `__init__.py` perezoso (lazy) en nosa_utils/pilecap_utils

Smoke test amplio — abrir al menos 2-3 pushbuttons de **cada** panel (10-15 en total) y confirmar que ninguno lanza `ImportError`/`AttributeError` al abrir. Prestar atención especial a los que solo usan módulos "ligeros" (`theme`, `logging`, `i18n`, `error_registry`) para confirmar que siguen funcionando sin el import eager de `geometry`/`revit_helpers`/`ui_helpers`/`config_manager`.

---

## Fase 13 — Migración real a `pilecap_utils` (13a/13b)

**13a CreatePilecapType**
1. Crear un tipo de encepado con parámetros conocidos (dimensiones, nº de pilotes, spacing, cutoff).
2. Comparar la losa y el array de pilotes generado contra un caso ya creado con la versión anterior — mismas coordenadas, mismo espesor, mismo offset de altura.

**13b AddPileToPilecap**
1. Sobre un encepado existente, añadir un pilote nuevo.
2. Confirmar posición, altura, y que el nuevo pilote se agrupa/renombra igual que antes de la migración.
3. Repetir el escenario de "dos documentos abiertos" de la Fase 4 para confirmar que el fix de `doc`/`uidoc` se mantiene tras la migración.

---

## Fase 14 — Migración a NOSAWindow (por herramienta)

Checklist idéntico para cada una de: AlignViewTitles, CopyViewTemplates, DimensionWalls, TagAll, ExportSheets, QRCode, PileMaster:
- [ ] Ventana abre sin error.
- [ ] Dark mode alterna correctamente los 5 colores.
- [ ] Cambiar tamaño de ventana, cerrar, reabrir → tamaño se recuerda.
- [ ] Toda la funcionalidad previa de la herramienta sigue funcionando igual (usar el checklist específico de esa herramienta en `QA_CHECKLIST.md` si existe, o el smoke test general).
- [ ] Configuración previa (última carpeta, último preset, etc.) sigue recuperándose tras el cambio de base class.

---

## Fase 15 — Borrado de código muerto

Para cada pushbutton tocado (BulkParameterEditor, FamilyAudit, QuantificationQA, RevisionTracker, RebarCoverage, AnnotationBatch, TagAll, QRCode, CreatePilecapType, AddPileToPilecap): abrir y ejercer su funcionalidad principal una vez, confirmar que no hay `ImportError`/`NameError` (el código muerto eliminado no estaba siendo llamado en ningún camino real, así que no debería haber ningún cambio de comportamiento visible).

---

## Fase 16 — Limpieza de nombres/packaging

1. Confirmar que todos los iconos se siguen mostrando correctamente en el ribbon tras unificar casing (`Icon.png` → `icon.png`) — en Windows el sistema de archivos no distingue mayúsculas, pero confirmar igualmente que pyRevit no tenía una referencia hardcodeada al nombre exacto anterior.
2. Confirmar que el botón de WaffleSlab muestra "Waffle" / "Slab" en dos líneas en el ribbon (antes: `Waffle\nSlab` literal en una línea).

---

## Regresión general (ejecutar tras cualquier tanda de fases)

- [ ] Revit abre con la extensión activa, sin errores de arranque en el panel de salida de pyRevit.
- [ ] Los 39 pushbuttons abren sin excepción (smoke test rápido, un clic cada uno).
- [ ] `QA_CHECKLIST.md` (existente) — pasar completo antes de considerar cualquier fase de Nivel 3 en adelante como cerrada.
- [ ] `RELEASE_READY_QA_CHECKLIST.md` (existente) — pasar antes de cualquier release tras completar varias fases.
- [ ] Ningún icono desaparecido, ningún panel/pulldown vacío en el ribbon.

## Firma

_Marcar ☑ al verificar cada fase. Responsable: ________________________  Fecha: ___________  Fase(s) cubiertas: ____________
