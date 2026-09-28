# RebarAutomate — Roadmap F0→F9

Objetivo: Plugin de armado profesional con paridad/superioridad vs SOFiSTiK Reinforcement, funcionando idénticamente en Revit 2024/2025/2026/2027.

---

## Estado actual (actualizado 2026-09-28)

| Fase | Descripción | Estado | Rama | Commits |
|---|---|---|---|---|
| **F0** | Revit 2024–2027 compat facade + tooling migration | ✅ **DONE** | `feat/rebar-F0-compat` | 3cfa461 |
| **F1** | Shared params + provenance + batch manager | ✅ **DONE** | `feat/rebar-F1-shared-params` | 736497b, 252e379 |
| **F2** | Perfiles de normativa (EHE-08, ISO, BS) | ✅ **DONE** | `feat/rebar-F2-standards` | 02d2a65 |
| **F2.5** | Lap/mandrel/confinamiento/anclaje conectados a la normativa | ✅ **DONE** | `develop` | commits 2026-09-02/03 |
| **F3** | Numeración y marcado | ✅ Código completo — **estaba roto en TODAS las ejecuciones** hasta hoy (firma `shared_params` incorrecta), corregido | `develop` | commits 2026-09-02/03 |
| **F4** | Catálogo de formas + clasificador | ✅ Código completo — **estaba roto en TODAS las ejecuciones** hasta hoy (`import Rebar` del módulo equivocado), corregido | `develop` | commits 2026-09-02/03 |
| **F5** | Despiece (BBS) + export CSV/XLSX + peso | ✅ **DONE** | `develop` | commits 2026-09-02/03 |
| **F6** | Detallado completo (tags, MRA, secciones) | ✅ Code-complete — tagging tenía un bug real (vista 3D sin bloquear), corregido; smoke 4 versiones sigue pendiente | `develop` | 72ad5be, 0eba562 |
| **F7** | Vigas + muros + pilares circulares + losas/zapatas (cierres perimetrales) | 🚧 **En smoke real del usuario, F7.1→F7.17** — cierres perimetrales y Shape Code en huecos confirmados en vivo; **vigas: causa raíz encontrada, reproducida y corregida EN VIVO** (`SetLayoutAsMaximumSpacing` propaga desde la barra semilla hacia `+normal`, no "rellena entre" dos barras — la semilla caía en el lado equivocado; corregido y reverificado con `revit_create_rebar_by_curves`+`revit_set_rebar_layout`); huecos pequeños ahora garantizan mínimo 3 U-bars/lado. Ambos pendientes de confirmación en vivo del usuario. Commiteado (rama `fix/rebar-f7-smoke-and-shared-params-bugs` → `develop`) | `develop` | 189b985 → ee4a9b1 |
| **F8** | Export BVBS (máquinas ferralla) | 🚧 Código+tests escritos; formato BF2D/checksum explícitamente SIN validar contra un `.abs` real | `develop` | commits 2026-09-02/03 |
| **F9** | Losas + endurecimiento + release 1.0.0 | ⏳ El motor de losas (`floor_rebar.py`) ya existe y se está probando dentro de F7 — falta la matriz de humo 4 versiones y el empaquetado de release | — | — |

**Tests:** 20 ficheros en `tests/`, todos en verde (re-ejecutados 2026-09-28) (`python tests/test_X.py`, exit 0 cada uno).

**Estado git (2026-09-28):** todo el trabajo de F2.5 a F7.18 está commiteado (27 commits del 2 y 3 de septiembre, `189b985`→`ee4a9b1`) y forma la base de la rama de integración `develop`. `main` sigue sin F7 hasta pasar el humo en 4 versiones (Matriz de validación). El seguimiento global de tareas vive en `MASTER_ROADMAP.md`.

---

## 🎯 Dónde estamos y cómo avanzar

**Resumen de una línea:** las 5 tipologías (zapata, pilar, viga, muro, losa) generan armado real contra el modelo del usuario; el ciclo de esta sesión ha sido "el usuario prueba con el botón real → reporta con capturas/element IDs → se verifica en vivo vía HuskyBIM → se corrige → se repite", y ha sacado a la luz (y corregido) bugs que llevaban ahí desde el principio, no solo geometría nueva de F7 — incluido que **F3 (marcado) y F4 (clasificación de formas) no habían funcionado NUNCA** hasta hoy.

**Para cerrar F7 formalmente, en orden:**

1. **Vigas — causa raíz encontrada y CORREGIDA (F7.16), verificada en vivo con reproducción manual (no solo lectura de código):** `create_rebar_set`'s `SetLayoutAsMaximumSpacing` propaga las copias DESDE la barra semilla hacia `+normal`, no "rellena entre" dos barras — la barra semilla podía caer en el lado `+normal` en vez de `-normal` (orden arbitrario de `_beam_faces`), empujando el Set entero fuera de la sección. Corregido con un `seed_side_normal` compartido entre top y bottom. Reproducido en vivo antes y después del fix contra la viga real 1318407 — confirmado. **Pendiente:** que el usuario vuelva a generar el armado con el botón real y confirme.
2. **Huecos — mínimo 3 U-bars por lado en huecos pequeños, implementado (F7.17) por decisión explícita del usuario:** margen de esquina más ajustado (`leg/4`) SOLO para huecos, SOLO cuando ni el spacing estándar ni el margen relajado dan 2+, apuntando directamente a 3 posiciones — la pata de anclaje nunca se reduce. Verificado con un test que reproduce el caso exacto reportado (hueco 500×500mm, pata 400mm) — 19/19 suites en verde. **Pendiente de confirmar en vivo.**
3. **Aviso del usuario: Revit se cierra inesperadamente de vez en cuando al recargar pyRevit** — no investigado (no hay traza/repro en este hilo); dado el volumen de ediciones a `beam_rebar.py`/`floor_rebar.py` hoy, recomendable guardar antes de cada Reload y considerar reiniciar Revit del todo en vez de depender solo del hot-reload de pyRevit al probar estos cambios concretos.
3. **`NOSA_Rebar_Layer` sin stampar en los generadores** (deuda conocida desde F3, confirmada de nuevo por el análisis de brecha SOFiSTiK) — ahora que F3 realmente funciona (bug de firma corregido hoy), vale la pena cerrarla: sin esto, todo sale con `Layer="uncategorized"`.
4. **Decisión de commit:** hay ~23 ficheros modificados + 4 nuevos sin commitear desde F2.5. Cuando el usuario dé el visto bueno final de este ciclo de smoke, toca dividir esto en commits lógicos (por fase o por bug) en vez de uno solo gigante — pendiente de que el usuario lo pida explícitamente.
5. **Matriz de humo en 2024/2025/2026/2027** — todo lo probado hasta ahora es sobre Revit 2026 real del usuario; **obligatoria antes de mergear F7** según la Matriz de validación más abajo. Sin fecha todavía.

**Después de cerrar F7:**
- **F8 (BVBS):** conseguir un fichero `.abs` real o el spec oficial y contrastar `bar_to_bvbs_line`/`_compute_checksum` — es lo único que falta para pasar de "código escrito" a "cerrado".
- **F9:** con el motor de losas ya maduro dentro de F7, lo que realmente queda de F9 es la matriz de humo completa + `docs/USER_GUIDE.md` + el tag de release `1.0.0` — menos trabajo de motor del que sugiere la tabla de fases original.
- Ítems 3 y 6 del análisis de brecha SOFiSTiK (esquineras 45° en huecos de losa, `NOSA_Rebar_Layer`) — el ítem 6 ya está en el punto 3 de arriba; el ítem 3 (geometría de esquinera a 45°, no solo U-bar recto) queda para cuando el punto 2 de arriba esté cerrado.

---

## F0 — Compat facade ✅ DONE

**Entregables:**
- `lib/nosa_utils/revit_compat.py` (fachada API por versión)
- `.gitattributes` (line endings)
- Estructura `data/` vacía
- CI: parseo dual IPy2/Py3

**Criterio de éxito:** UI abre sin cambios funcionales en 4 versiones; `revit_compat.api()` devuelve clase correcta.

---

## F1 — Shared params + provenance ✅ DONE

**Entregables:**
- `data/shared_parameters/NOSA_SharedParameters.txt` (40 GUIDs fijos)
- `lib/nosa_utils/shared_params.py` (ensure_bound, write, read, stamp_provenance)
- `lib/rebar_batch.py` (RebarBatch.run/select/delete/list)
- UI: sellado automático + Gestor de lotes básico
- Fix: idioma británico consistente

**Criterio de éxito:** Toda barra lleva `Created_By_NOSA`, `Batch_Id`, `Generator_Version`, `Standard_Code`. "Delete batch" respeta `Finalized=1`. Humo OK 2024–2027.

**Desviaciones documentadas:**
- TransactionGroup no anidado (correcto — Revit no admite)
- `(created_rebars, summary)` en vez de solo summary
- USERMODIFIABLE por criterio (documentado en .txt)

---

## F2 — Perfiles de normativa ✅ DONE (partial)

**Entregables:**
- `lib/nosa_utils/standards.py` (load, list_available, cover_for, mandrel_*, lap_*, anchorage_*, hook_*)
- `data/rebar_standards/{_schema.json, EHE-08.json, EN-ISO-3766.json, BS-8666-2020.json}`
- `rebar_project.json` (standard_code por documento)
- UI: desplegable global de normativa
- Migración: DEFAULT_COVER_MM → standards.cover_for (con envoltorios compat)
- `ctx["standard"]` pasa de None a perfil resuelto
- `rebar_preview` consume std
- tests/test_standards.py: 25 tests puros (sin Revit)

**Criterio de éxito:** Cambiar de EHE-08 a BS-8666 en UI cambia cover/lap/mandrel en siguiente generación. Tests puros verdes.

**Desviaciones documentadas (F2, cerradas en F2.5 — ver más abajo):**
- **COVER: conectado end-to-end** desde F2 — preview y generación real usan el mismo helper `_standard_default_cover_mm()`
- ~~LAP/MANDREL/STOCK_LENGTH: wrappers listos pero NO conectados~~ — **cerrado en F2.5, ver abajo**

**Bug corregido:** column_rebar.py/footing_rebar.py faltaban sys.path para `import nosa_utils` — los 9 scripts legacy ahora corren standalone sin ModuleNotFoundError.

---

## F2.5 — Lap/mandrel/confinamiento/anclaje conectados a la normativa ✅ DONE (2026-09-01)

**Lo que se conectó de verdad (con `std=None` por defecto, retrocompatible, verificado con 8 tests numéricos nuevos que comparan CON std vs. SIN std):**
- `column_rebar.build_column_reinforcement` (rectangular) y `_build_circular_column_reinforcement` (circular — ver corrección importante más abajo): la longitud de esperas usa `default_lap_length_mm(..., std=std, in_compression=True)` — **decisión de diseño explícita**: se asume que las esperas de pilar empalman en compresión (el caso convencional para armadura principal de pilar bajo carga gravitatoria); un caso de tracción real seguiría necesitando un `starter_bar_length_mm` explícito. La longitud de la zona de confinamiento usa `default_joint_zone_length_mm(..., std=std)` (factor `stirrups.confinement_zone_factor_h` de la normativa).
- `footing_rebar.build_footing_reinforcement` → `build_perimeter_closure_ubars_topology`: la pata de anclaje de los cierres perimetrales usa `default_anchorage_length_mm(..., std=std)` (buen contacto, tracción — el caso por defecto de la función).
- `floor_rebar.build_floor_reinforcement` → `_build_direction_bars` (×4, malla inferior/superior × X/Y) y sus propios cierres perimetrales: mismo `default_anchorage_length_mm(..., std=std)` — descubierto durante el cableado que floor_rebar.py YA reutilizaba este wrapper de footing_rebar.py, así que quedó conectado igual, sin trabajo extra.
- `ui.py`: los 3 puntos de llamada (`_process_footing`, `_process_floor`, `_process_column`) pasan `std=getattr(self, 'ra_standard', None)`.
- **Explícitamente NO conectado todavía** (alcance real, no un descuido): el anclaje/empalme de esperas de zapata (`dowel_anchor_length_mm`/`dowel_splice_length_mm`) y el `max_stock_length_mm` de todas las tipologías son siempre valores explícitos que la UI ya pasa desde sus propios campos de texto — conectar ESTOS a la normativa significaría cambiar el VALOR POR DEFECTO que esos campos de texto muestran al cargar la ventana (trabajo de UI, no de motor), no una llamada de función. Queda como mejora de UI, no como bug.

**Corrección importante descubierta durante F2.5** (verificar antes de "arreglar" — Regla de Oro): el backlog de este documento afirmaba *"Columnas circulares — preview circular OK, generación trata como rectangulares"*. **Es falso.** `build_column_reinforcement` ya detecta el parámetro `Diameter` y delega en `_build_circular_column_reinforcement` (barras radiales + cercos poligonales de 24 cuerdas, Phase 3.5.7/3.5.9) — ya trata las columnas circulares como circulares, con su propia geometría, desde antes de esta sesión. Se retira esa entrada del backlog de "Bugs legacy columnas" más abajo.

**Tests:** `tests/test_f25_standards_wiring.py` (8 tests nuevos, verdes) — comprueban que CON std el resultado es numéricamente distinto del valor fijo pre-F2.5, y que SIN std (`std=None`) el resultado es EXACTAMENTE igual al de antes de F2.5 (cero pérdida de funcionalidad). Los 9 scripts de fase legacy + toda la suite pytest siguen en verde tras el cableado.

**Pendiente de verdad:** como con F7, esto está verificado por tests numéricos puros (sin Revit) — el smoke con la UI real sigue siendo quien confirma que, por ejemplo, cambiar a BS-8666-2020 cambia de verdad la longitud de esperas de un pilar generado en un modelo real.

**Deps:** F0 (compat), F1 (provenance)

**Timeline:** 3–4 días

---

## F3 — Numeración y marcado ✅ DONE

**Entregables:**
- ✅ `lib/rebar_marking.py` (deduplicate_and_mark, compute_total_length_mm, assign_layers_and_lengths, renumber_batch)
- ✅ Integrado en `rebar_batch.py` (paso 3 tras provenance, antes de Assimilate)
- ✅ UI: cabecera de proyecto en pestaña *Detailing & Tools* (Mark Prefix, Revision, Status → persiste en rebar_project.json)
- ✅ Perfiles JSON: sección "marking" ya presente desde F2 (dedup_tolerance_mm, mark_format, number_scope, layer_names)
- ✅ `_schema.json`: validación de sección "marking"
- ✅ `tests/test_rebar_marking.py`: 6 tests puros (mark_format, dedup_tolerance, layer_translation, is_variable, redondeo)
- ⚠️  **Desviación conocida:** etiquetado de `NOSA_Rebar_Layer` en generadores NO implementado aún (footing/column/beam/floor_rebar no stamp Layer tras cada creación de Rebar). El motor de marking funciona y agrupa por Layer correctamente, pero los generadores devuelven estructuras complejas (dicts de curvas) que ui.py consume — etiquetar Layer requiere modificar ui.py para stamp Layer según qué parte del dict se está creando (bottom_mat → bottom_x/y, top_mat → top_x/y, etc.). Diferido a fase posterior por riesgo de romper lógica testada.

**Criterio de éxito:** 
- ✅ Deduplicación funciona (lógica de clustering por shape_params + tolerance implementada)
- ✅ Schedule nativo puede agrupar por `NOSA_Rebar_Mark` (parámetro compartido ya bound desde F1)
- ✅ `renumber_batch()` es idempotente (re-ejecuta dedup + assign sobre el mismo lote)
- ✅ Todos los tests verdes (58/58: CI 5, standards 25, shared_params 22, marking 6)
- ✅ UI guarda y carga cabecera de proyecto (mark_prefix, revision, status persisten en rebar_project.json)

**Deps:** F1 (provenance), F2 (standards)

**Desviaciones documentadas:**
- Etiquetado de Layer en generadores diferido — el marking core está completo pero los generadores aún no stamp Layer tras crear Rebar. Impacto: barras creadas tendrán Layer="uncategorized" (asignado por `assign_layers_and_lengths` como fallback) hasta que los generadores lo stampen explícitamente.

**Timeline:** 1 día

---

## F4 — Catálogo de formas + clasificador ✅ DONE

**Entregables:**
- ✅ `data/shape_catalogs/{en_iso_3766,bs_8666_2020}/catalog.json` (formas básicas: 00, 11, 51, 99 con constraints)
- ✅ `lib/nosa_utils/rebar_catalog.py` (load, get_shape_def, list_shape_codes, is_valid_shape_code)
- ✅ `lib/rebar_shape_classifier.py` (classify_and_stamp, batch_classify, analiza curvas centerline)
- ✅ Integrado en `RebarBatch.run` (Transaction "Shape Classification" tras provenance, antes de marking)
- ✅ `tests/test_rebar_catalog.py`: 7 tests puros (load, shape_def, list, validation, constraints)

**Criterio de éxito:**
- ✅ Catálogos JSON cargados correctamente (EN ISO 3766, BS 8666:2020)
- ✅ Clasificador analiza curvas y asigna códigos de forma (00, 11, 51, 99)
- ✅ NOSA_Rebar_Shape_Code + Shape_Params sellados automáticamente tras creación
- ✅ Todos los tests verdes (65/65: CI 5, standards 25, shared_params 22, marking 6, catalog 7)

**Implementación realizada:**
- Catálogos básicos con 4 formas fundamentales por normativa
- Clasificador analiza número de segmentos, ángulos entre segmentos, y longitudes
- Algoritmo simple pero robusto: detecta barras rectas (00), L-shape (11), U-bar (51), custom (99)
- Parámetros de forma calculados automáticamente (A, B, C, R) desde geometría centerline
- Validación contra catálogo normativo (fallback a 99 si forma no existe en catálogo)

**Desviaciones conocidas:**
- Implementación inicial con formas básicas (00, 11, 51, 99) — catálogo completo se expandirá progresivamente
- Radio de bend (R) estimado en 50mm por defecto — refinamiento futuro leerá desde RebarBarType
- Sin pre-validación de constraints antes de CreateFromCurves (diferido a mejora futura si "Internal Error" persiste)

**Deps:** F2 (standards), F3 (marking espera Shape_Code)

**Timeline:** 1 día

---

## F5 — Despiece (BBS) + export CSV/XLSX ✅ DONE

**Entregables:**
- ✅ `lib/rebar_schedule.py` (recolección, agrupación, cálculo longitudes, export CSV/XLSX)
- ✅ UI: botón "Generate Schedule..." en pestaña Detailing & Tools
- ✅ Export a CSV (compatible Python 2/3)
- ✅ Export a XLSX (requiere openpyxl, opcional)
- ✅ `tests/test_rebar_schedule.py`: 5 tests puros

**Criterio de éxito:**
- ✅ Recolecta todas las barras NOSA del proyecto
- ✅ Agrupa por NOSA_Rebar_Mark (posición)
- ✅ Calcula totales (count × unit_length)
- ✅ Muestra estadísticas (posiciones, barras totales, longitud por diámetro)
- ✅ Exporta a CSV y XLSX con columnas: Mark, Host, Layer, Diameter, Shape Code, Shape Params, Quantity, Unit Length, Total Length
- ✅ Todos los tests verdes (70/70: CI 5, standards 25, shared_params 22, marking 6, catalog 7, schedule 5)

**Implementación realizada:**
- `SchedulePosition`: clase contenedora por posición (mark)
- `collect_rebars()`: filtra barras NOSA, opcional por batch_id y Finalized
- `group_by_position()`: agrupa por Mark, calcula totales
- `generate_schedule_data()`: pipeline completo → list[dict]
- `export_csv()`: exporta con compatibilidad Py2/Py3
- `export_xlsx()`: exporta a Excel (requiere openpyxl), con formato bold headers + auto-width
- `get_summary_stats()`: estadísticas sumarias (total positions/bars/length, breakdown por diámetro)
- UI: botón cableado, diálogo con summary, SaveFileDialog, abre carpeta tras export

**Deps:** F3 (marking), F4 (shape code)

**Timeline:** 1 día

---

## F6 — Detallado completo ✅ Code-complete (smoke pendiente)

**Entregables:**
- `lib/rebar_detailing.py` ampliado (MRA, smart tags, secciones) — ✅ F6.2 (`72ad5be`)
- UI Auto Tag / Auto MRA / Auto Sections — ✅ F6.3 (`0eba562`)
- Familias `NOSA_Tag_*.rfa` optimizadas — **DIFERIDO → post-F7 / final de proyecto** (usar familias existentes del proyecto mientras tanto)

**Criterio de éxito:** Plano de zapata etiquetado+acotado+2 secciones automáticas. **Humo 4 versiones** — pendiente (F6.4 / junto con F7).

**Deps:** F3 (marcado), F4 (forma)

**Notas:**
- Smoke test de F6 se puede hacer en paralelo mientras avanza F7.
- Optimización de familias de anotación (tags/MRA) queda planificada **después de F7** (o al cierre del proyecto con F9).

---

## ✅ Normalización de ventanas RebarAutomate — DONE (2026-09-02)

Implementado a petición explícita del usuario (adelantado respecto al plan
original de "empezar cuando F7 esté cerrado" — decisión suya). Cambios en
`ui.xaml` únicamente, ningún `x:Name`/`Click` tocado (solo se cambiaron
atributos de layout/Style y el texto de 2 botones):

- **Beams y Walls reestructuradas al mismo layout de 2 columnas** que
  Footings/Slabs y Columns ya usaban (columna izquierda `ScrollViewer` con
  los controles, columna derecha `380px` fija con el Section Preview) — antes
  eran una única columna con todo apilado, incluida la preview al final.
- **Panel "Result" envuelto en `Card` con título**, igual que
  `TxtResult`/`TxtColumnResult` — antes `TxtBeamResult`/`TxtWallResult` eran
  un `TextBox` suelto sin `Card` ni título.
- **Botones "Generate" unificados**: `Style="{DynamicResource ActionButton}"`,
  `Height="52" FontSize="14" FontWeight="Bold"`, texto "GENERATE
  REINFORCEMENT" — antes Beams/Walls usaban el botón WPF por defecto,
  `Height="36"`, sin `ActionButton`, con texto distinto por pestaña
  ("Generate Beam/Wall Reinforcement...").
- **`BeamPreviewCanvas`/`WallPreviewCanvas` envueltas en el mismo patrón
  `Border` + `Viewbox Stretch="Uniform"`** que ya usaban `PreviewCanvas`/
  `ColumnPreviewCanvas` — verificado en `ui.py` que `_draw_simple_section_
  preview` lee `canvas.Width`/`.Height` directamente (nunca `ActualWidth`/
  `.ActualHeight`), así que envolver en `Viewbox` es un cambio puramente
  visual, sin riesgo de romper el dibujo.
- "Detailing & Tools" queda deliberadamente distinta — es un dashboard de
  herramientas de proyecto, no una pestaña de generación de armado por
  tipología, tal como contemplaba el backlog original.

Verificado: XAML bien formado (`xml.dom.minidom.parse` sin error), 5
`TabItem` presentes, cero `x:Name` duplicados, 19/19 suites de test en
verde (no tocan `ui.xaml` pero confirman que nada más se rompió). **Pendiente:
smoke visual real en Revit** (abrir la ventana y confirmar que las 4 pestañas
de generación se ven iguales).

---

## ✅ Previsualizaciones RebarAutomate — DONE (2026-09-02, Phase 2.6)

Petición explícita del usuario, aplicable a las 4 pestañas de generación:
que cualquier cambio seleccionado/ejecutado sea visible en la previsualización,
más 4 bugs concretos reportados en vivo. `rebar_preview.py` sigue
DELIBERADAMENTE desacoplado de Revit/WPF (su propio docstring) — todo lo
de abajo es Python puro, sin necesidad de mock alguno.

- **Footings/Slabs — "Include 90° Hooks" no tenía ningún efecto visible:**
  causa real, `compute_section_preview` no tenía NINGÚN concepto de hooks
  — los checkboxes ya estaban cableados a `Preview_Changed` (redibujaba),
  pero no había nada que dibujar. Añadido `bottom_hooks`/`top_hooks` +
  nueva salida `'hooks'`: un pequeño tramo doblado 90° en cada extremo de
  la línea B2/T2 (el único elemento realmente VISIBLE desde este ángulo de
  corte — B1/T1 son puntos, mirando de frente al extremo de la barra, un
  hook ahí no añadiría geometría visible). Hooks de fondo doblan hacia
  abajo, de techo hacia arriba.
- **Vigas — "las barras mostradas... ahora parece que chocan":** causa
  real confirmada, `compute_beam_section_preview` usaba el MISMO inset
  para el estribo Y para las barras — el punto de la barra quedaba
  centrado EXACTAMENTE sobre la línea del estribo (mitad del punto
  sobresaliendo), sobre todo en las 2 barras de esquina. Corregido con el
  mismo convenio de doble inset YA usado (y correcto) en columnas/zapatas:
  el estribo se dibuja a `cover + su propio radio`; las barras, más
  adentro, a `cover + diámetro completo del estribo + su propio radio`.
- **Vigas — nuevo Elevation Preview** (petición explícita: "sería
  interesante ver un alzado de la viga"): nueva
  `compute_beam_elevation_preview` (barras superior/inferior como líneas
  a lo largo de toda la longitud, estribos como marcas verticales
  espaciadas — con las mismas 3 zonas de densificación en extremos que ya
  usa `compute_column_elevation_preview`) + nuevo canvas
  `BeamElevationCanvas` en `ui.xaml`, junto al Section Preview existente
  (mismo patrón de doble canvas que Columns). Cableados los campos que
  antes NO disparaban ningún redibujado (spacing de estribos, end offset,
  densify, dense spacing, confine length) — antes solo afectaban al motor
  real, invisibles en el preview.
- **Muros — vista no centrada, mal etiquetada, sin sección real:** 3
  hallazgos en el mismo sitio. (1) `_draw_wall_elevation_preview` usaba un
  margen izquierdo FIJO como offset, en vez de centrar el ancho ya
  escalado dentro del canvas — el muro quedaba pegado a la izquierda con
  hueco vacío a la derecha en cuanto el muro real era más corto que el
  canvas. Corregido con el mismo cálculo de centrado que
  `_draw_column_elevation_preview`/el nuevo `_draw_beam_elevation_preview`
  ya usan correctamente. (2) El canvas se llamaba "Section Preview" pero
  dibujaba un ALZADO (front view) — renombrado a "Elevation Preview"
  (el propio `x:Name` `WallPreviewCanvas` no cambia, solo su etiqueta).
  (3) Añadida una SECCIÓN real (corte horizontal por el espesor del muro)
  usando `rebar_preview.compute_wall_section_preview` — ya escrita desde
  antes pero NUNCA cableada a la UI hasta ahora — reutilizando
  `_draw_simple_section_preview` tal cual (su forma de retorno ya
  coincidía exactamente). Cableados también los 8 campos de Vertical/
  Horizontal Mesh + Ties + U-Bars que antes no disparaban ningún
  redibujado (`TxtWallVertDia/Spacing`, `TxtWallHorizDia/Spacing`,
  `TxtWallTieDia/Spacing`, `TxtWallUBarDia/Spacing`) — el diámetro
  horizontal en concreto no tenía NINGÚN efecto en ningún preview, ni
  siquiera estaba cableado. De paso, `compute_wall_elevation_preview`
  ganó un parámetro `horiz_dia_mm` real (antes SIEMPRE derivaba un valor
  falso, `vert_dia_mm * 0.85`, ignorando el campo que el usuario
  realmente escribía).

Verificado con un nuevo fichero de test, `tests/test_rebar_preview_
phase26.py` (mismo convenio sin-Revit que `test_phase351_fixes.py`) — 6
comprobaciones dirigidas a cada uno de los 4 bugs de arriba, todas en
verde. 20/20 suites de test totales en verde (ninguna regresión).

**Ronda 2 (2026-09-02, mismo día, tras smoke visual real del usuario) — 3
bugs más encontrados y corregidos:**
- **Hooks al revés:** confirmado por captura — doblaban HACIA AFUERA
  (pasando la cara libre) en vez de HACIA DENTRO del hormigón (el
  convenio real de un hook de 90°, que ancla curvando hacia el núcleo).
  Invertida la dirección en ambos call sites (`bottom_hooks` ahora dobla
  hacia arriba/núcleo, `top_hooks` hacia abajo/núcleo).
- **Sección de muro reescrita por completo:** era un corte casi cuadrado
  con solo 2 puntos y una tie — ahora es el corte estructural
  convencional: un corte VERTICAL perpendicular a la longitud del muro
  (espesor x una altura representativa), con barras verticales como
  líneas continuas (una por cara) y barras horizontales como puntos a su
  espaciado real — mismo convenio puntos-vs-líneas que footings/floors,
  rotado 90°. Nueva salida `'bar_lines'` genérica añadida a
  `_draw_simple_section_preview` para soportar esto (reutilizable por
  cualquier preview futuro que necesite una línea de barra no fijada a
  una fila).
- **Starter bars del muro ahora visibles** en el alzado — se extienden
  bajo la base tal y como ya hace `build_wall_reinforcement`
  (`include_starter_bars`/`starter_length_mm`), con el mismo patrón
  `starter_extension_mm` que la elevación de columnas ya usaba.

Verificado con 3 comprobaciones más en el mismo fichero de test — 20/20
suites en verde. **Pendiente de verdad: smoke visual real en Revit** —
confirmar que hooks, el nuevo alzado de vigas y las 2 vistas de muro se
ven correctamente en la ventana real, algo que no puedo verificar sin
ojos en el render WPF.

---

## 🚧 F7.18 — Starter bars en L hacia la cimentación (columnas y muros)

Petición explícita del usuario (2026-09-02), tras confirmar el alcance con
2 preguntas: mismo detalle que las "Dowels" ya existentes en Zapatas
(barra recta + gancho de 90° en la base), pero **generado desde la propia
columna/muro** (no desde la zapata), y funcionando contra los 3 tipos de
cimentación: zapata aislada, losa de cimentación/solera, y zapata corrida.

**Implementado:**
- `rebar_engine.find_foundation_below(doc, x_ft, y_ft, base_z_ft, ...)` —
  detecta el elemento de cimentación (zapata aislada/corrida —
  `OST_StructuralFoundation`, ambas comparten categoría en Revit aunque
  `WallFoundation` sea una clase distinta — o losa/solera,
  `OST_Floors`) directamente bajo un punto dado, vía bounding box (mismo
  convenio ya establecido en `column_rebar.find_floor_split_elevations_
  ft`).
- `rebar_engine.build_starter_into_foundation(...)` — construye UNA
  barra recta desde la elevación del mat inferior de la cimentación
  detectada (offset por su propio cover) hasta `anchor_length_mm` (dentro
  de la cimentación) + `splice_length_mm` (por encima, hacia las barras
  reales de la columna/muro) — mismo reparto de longitud que
  `footing_rebar.build_dowel_curves`. El gancho de 90° se aplica al
  CREAR (start_hook), no está horneado en la geometría — misma
  convención que `_create_dowel_bars` ya usa.
- `column_rebar.build_column_foundation_starters(...)` — 4 barras en las
  esquinas (n_u=n_v=2, mismo valor por defecto que Dowels), reutilizando
  `compute_vertical_bar_lines` para las posiciones reales.
- `wall_rebar.build_wall_foundation_starters(...)` — una barra por
  posición de barra vertical a lo largo del muro (mismo espaciado que la
  malla vertical real), posicionadas en el eje del muro (simplificación
  DIVULGADA: no compensa a qué cara pertenecería cada barra vertical
  real).
- `ui.py`: nuevo `_create_foundation_starter_bars` (barras individuales,
  gancho al crear, mismo patrón que `_create_dowel_bars`); cableado en
  `_process_column`/`_process_wall`; nuevas tarjetas en `ui.xaml` para
  ambas pestañas ("Add L-Shaped Starter Bars into Foundation Below" +
  longitud de anclaje/solape).
- **Distinto** de lo que ya existía: `ChkColStarterBars` (columnas) sigue
  siendo sobre la PROPIA cabeza de la columna, para plantas futuras —
  sin relación. `ChkWallStarters` (muros) sigue siendo la extensión recta
  simple bajo la base — esta nueva opción es un checkbox APARTE
  ("L-Shaped... into Foundation Below"), con detección real de
  cimentación y gancho, sin tocar el comportamiento existente.

**Sin preview todavía** (decisión explícita por alcance/tiempo — la
geometría depende de una consulta en vivo a la cimentación detectada, no
del motor `rebar_preview.py` ilustrativo que el resto de paneles usa) —
los checkboxes solo activan/desactivan sus propios campos por ahora.

**Pendiente de verdad — sin verificar en vivo todavía:** a diferencia del
resto del trabajo de hoy (que sí tiene tests automáticos sin Revit), esta
función depende intensivamente de la API real de Revit
(`FilteredElementCollector`, `get_BoundingBox`) — no hay forma honesta de
mockearla con el mismo rigor que `rebar_preview.py`. Necesito que
selecciones una columna y/o un muro con una cimentación real modelada
debajo (de cualquiera de los 3 tipos), actives el checkbox nuevo, y me
pegues el log completo para verificar contra el modelo real, siguiendo el
mismo método de este sesión.

---

## 🔖 BACKLOG — Normalización de ventanas RebarAutomate (petición 2026-09-02, COMPLETADO arriba)

Petición explícita del usuario: que las 5 pestañas (Footings/Floors, Columns,
Beams, Walls, Detailing & Tools) de la ventana de RebarAutomate se vean
consistentes entre sí. Estado actual verificado en `ui.xaml` — inconsistencias
reales encontradas al planificar esto:

- **Footings/Floors y Columns:** el panel "Result" usa `<Border Style="Card">`
  envolviendo un `<StackPanel>` con título + `TxtResult`/`TxtColumnResult`.
- **Beams y Walls:** el resultado (`TxtBeamResult`/`TxtWallResult`) es un
  `TextBox` suelto SIN la `Card`/título que envuelve a los otros dos — ya eran
  distintos entre sí incluso antes de este backlog (confirmado leyendo el
  XAML actual).
- Botones de "Generate": Footings/Columns usan `Style="{DynamicResource
  ActionButton}"` explícito con `Height="52" FontSize="14" FontWeight="Bold"`;
  Beams/Walls usan el estilo de botón por defecto (WPF) con `Height="36"`, sin
  `ActionButton`. Visualmente son dos tamaños/pesos distintos para la misma
  acción.
- Vale la pena auditar también: espaciado de `Card`/`Margin` entre secciones,
  si las 4 pestañas de generación comparten la misma anchura de columna
  izquierda/derecha, y si "Detailing & Tools" (con layout propio, dashboard-
  style) debería normalizarse con el resto o queda deliberadamente distinto
  por ser una pestaña de naturaleza diferente (herramientas de proyecto, no
  una tipología estructural).

**Alcance:** solo visual/consistencia de `ui.xaml` (estilos compartidos ya
existen como `RA_SectionTitle`, `RA_FieldRow`, `RA_FieldLabel`, `RA_NumField`,
`Card`, `ActionButton` — se trata de APLICARLOS de forma uniforme, no crear
un sistema de estilos nuevo). Sin tocar `ui.py` salvo que algún `x:Name`
tenga que cambiar de tipo de control (p.ej. si se decide que
`TxtBeamResult`/`TxtWallResult` pasen a vivir dentro de una `Card` como los
otros dos — cambio de contenedor, no de nombre).

**Riesgo a vigilar (memoria del proyecto):** nunca fijar `SelectedIndex`/
`SelectionChanged` de un ComboBox o TabControl en el propio XAML — cablear
en code-behind tras `LoadComponent`, con guardas `_is_loaded` (patrón que
esta ventana ya usa en sus `_Click` handlers existentes).

**Prioridad:** media — no bloquea el cierre de F7; el usuario lo pidió como
mejora de pulido, no como fix urgente. Empezar cuando F7 esté cerrado
(commiteado, humo 4 versiones) para no mezclar un cambio puramente visual
con los fixes de geometría/datos aún en curso.

---

## 🔖 BACKLOG — Familias de anotación (post-F7)

| Tarea | Cuándo | Notas |
|---|---|---|
| Auditar familias actuales (`NOSA Rebar Tag`, `Multi-Rebar Annotations`) | Tras F7 | Ya cargadas en proyecto |
| Optimizar labels (Mark, Ø, spacing, multiplier) | Post-F7 | Ajustar a `NOSA_Rebar_*` params |
| Empaquetar `.rfa` en `content/tags/` (Revit 2024) | F9 / release | Compat 2024–2027 |
| Croquis de doblado / bending detail family | Post-F8 | Opcional |

---

## 🔥 FIXES POST-F5 (2026-08-28)

### ✅ FIX CRÍTICO: Shared Parameters no se creaban
**Problema:** Tras completar F3, F4, F5, los smoke tests revelaron que los parámetros NOSA nunca aparecían en las barras. El diálogo de creación de shared params se mostraba, pero los parámetros no se stampaban.

**Root Cause:** `lib/nosa_utils/shared_params.py::ensure_bound()` ejecutaba `doc.ParameterBindings.Insert()` **sin Transaction activa**. En Revit, cualquier modificación al documento DEBE ocurrir dentro de una transacción. La operación fallaba silenciosamente (retornaba `False`).

**Fix aplicado:**
- Envolví el bucle de bindings en `Transaction(doc, u'NOSA — Bind Shared Parameters')`.
- Commit: `5a9319c` (2026-08-28)

**Impacto:** Este bug bloqueaba **TODO** el sistema de provenance (F1), marking (F3), shape classification (F4) y schedule (F5). Era el bloqueador crítico #1.

---

### ✅ MEJORA: Feedback visible de shared parameters
**Problema:** `ensure_bound()` se ejecutaba pero no daba feedback visible al usuario. Era imposible saber si los parámetros se habían creado correctamente o no.

**Mejora aplicada:**
- Agregado logging detallado a consola pyRevit con conteo de bound/already/skipped/errors
- Alert visual cuando se crean parámetros por primera vez (con lista de parámetros disponibles)
- Alert de WARNING si hay errores durante la creación
- Commit: `5b81943` (2026-08-28)

**Impacto:** El usuario ahora tiene visibilidad completa de qué está pasando con los shared parameters al abrir RebarAutomate.

---

### ✅ FIX: Python 2/3 encoding en parse_shared_parameters_txt
**Problema:** Error al abrir RebarAutomate: "open() got an unexpected keyword argument 'encoding'"

**Root Cause:** `parse_shared_parameters_txt()` usaba `open(..., encoding='utf-8')` que IronPython 2.7 no soporta.

**Fix aplicado:**
- Cambié a `io.open(..., encoding='utf-8')` compatible con Python 2/3
- Commit: `5d9759f` (2026-08-28)

**Impacto:** Este era el ÚLTIMO caso de `open()/encoding` en el codebase. Todos los módulos ahora usan `io.open()`.

---

### ✅ FIX: forms.alert ok_only parameter
**Problema:** Error después de crear parámetros: "alert() got an unexpected keyword argument 'ok_only'"

**Root Cause:** pyRevit's `forms.alert()` no tiene parámetro `ok_only`. Por defecto ya muestra botón OK.

**Fix aplicado:**
- Eliminado `ok_only=True` del alert de éxito
- Commit: `1772c69` (2026-08-28)

**Impacto:** El diálogo de éxito ahora se muestra correctamente tras crear parámetros.

---

### ✅ FIX: os import en schedule generation
**Problema:** Error al generar schedule: "Local variable 'os' referenced before assignment"

**Root Cause:** En `BtnGenerateSchedule_Click()`, se usaba `os.path.join()` antes de importar `os`.

**Fix aplicado:**
- Movido `import os` al inicio de la función (junto con `import imp`)
- Commit: `3460a96` (2026-08-28)

**Impacto:** El botón "Generate Schedule" en la pestaña BBS ahora funciona correctamente.

---

### 🎉 RESULTADO FINAL (2026-08-28 12:11)

**✅ TODOS LOS BLOCKERS DE F1-F5 RESUELTOS:**
- ✅ 40 parámetros NOSA creados y visibles en Properties
- ✅ Batch manager reconoce barras NOSA
- ✅ Marking funciona (F3)
- ✅ Shape classification funciona (F4)
- ✅ Schedule generation funciona (F5)

**Total de commits de fixing:** 5 (5a9319c, 5b81943, 5d9759f, 1772c69, 3460a96)

---

### 📋 BUGS CONOCIDOS (No bloqueantes para F6)

Los siguientes issues provienen de **código legacy (fases 3.5.x)** y NO afectan a F0-F5. Se documentan aquí para priorización futura:

1. ~~**Geometría de columnas circulares:** Refuerzan como si fueran cuadradas.~~
   - **FALSO — verificado y corregido en el documento durante F2.5 (2026-09-01).** `column_rebar.build_column_reinforcement` detecta el parámetro `Diameter` y delega en `_build_circular_column_reinforcement` (barras radiales + cercos poligonales de 24 cuerdas, Phase 3.5.7/3.5.9) desde antes de esta sesión. La ruta de fichero citada (`lib/rebar_generators/column_rebar.py`) tampoco existe — la real es `lib/column_rebar.py`. Esta entrada llevaba tiempo obsoleta.

2. **Density at nodes en columnas continuas:** Solo se aplica en parte superior/inferior de TODA la columna, no en cada planta intermedia que atraviesa.
   - **Confirmado real, verificado en código (2026-09-01):** `generate_column_stirrup_zones` calcula sus 3 zonas (extremo denso/medio/extremo denso) sobre el `clear_height_mm` TOTAL de la columna; `_subtract_floor_bands` solo RECORTA el tramo que atraviesa cada losa (para no cruzar el hormigón de la losa), pero no añade una zona de confinamiento nueva en cada nudo intermedio. Para una columna de 3 plantas, solo la base absoluta y la coronación absoluta densifican — los nudos intermedios quedan a espaciado normal.
   - Origen: `lib/column_rebar.py`, `generate_column_stirrup_zones`
   - Prioridad: Media (fix en fase post-F9)

3. ~~**Crank bars en columnas:** No se generan. Las esperas de la siguiente planta quedan rectas.~~
   - **FALSO — verificado en código (2026-09-01).** `build_cranked_starter` (Phase 3.2/3.3) ya genera el doblez diagonal + tramo recto de solape en cada split, con la opción de UI real "Use Cranked Laps (1:6 slope)" (`values['cranked_laps']`, cableada en `ui.py`). El desplazamiento se resuelve por defecto contra la columna real de la planta de arriba (`resolve_crank_offset_mm`), no un valor asumido. Esta entrada también llevaba tiempo obsoleta.

4. **Mínimo 25mm en losas no cuadradas:** Error "The minimum length of rebar shape is 25 mm" en algunos casos no rectangulares.
   - Origen: `lib/rebar_generators/floor_rebar.py` (legacy)
   - Prioridad: Media (fix en F9 durante refactoring de floor_rebar)

5. **Huecos en losas:** Corta barras lisas pero no coloca U-bars. Petición: ignorar huecos < 200x200mm, armar huecos ≥ 200x200mm.
   - Origen: `lib/rebar_generators/floor_rebar.py` (legacy)
   - Prioridad: Alta (fix en F9 durante refactoring de floor_rebar)

6. **UI modeless:** Petición de usuario para poder interactuar con Revit mientras RebarAutomate está abierto.
   - Prioridad: Media (UX improvement en fase post-F9)

**Estrategia:** Estos bugs NO bloquean F6-F8. Los abordaremos en **F9** cuando refactoricemos `floor_rebar.py` y `column_rebar.py` completamente.

---

## F7 — Vigas + muros 🚧 In Progress

**Entregables:**
- **Vigas:** pestaña UI cableada, long. sup/inf, cercos, preview — F7.1 ✅
- **Muros:** `lib/wall_rebar.py` + UI, mallas vert.+horiz. — F7.2 ✅
- Densificación extremos viga + edge bars / ties muro — F7.3 ✅
- U-bars extremos, starters, stock-split, preview WPF — F7.4 ✅ (código)
- Huecos en muros (opening U-bars) → F9
- **Humo 4 versiones** — pendiente (bloquea cierre F7)

**Criterio de éxito:** 5 tipologías (zapata, pilar, viga, muro, losa) generan armado válido, marcado y clasificado. **Humo obligatorio 4 versiones.**

**Deps:** F2 (std), F3 (marcado), F4 (forma)

**Timeline:** 6–8 días

**Decisión:** Vigas aisladas en v1; continuidad entre vanos = fase posterior.

**F7.1 + F7.2 (2026-08-28):**
- Pestaña Beams cableada (long. top/bottom, stirrups, stock/laps) → `beam_rebar.build_beam_rebar_curves`
- Pestaña Walls cableada (mesh vert./horiz., both faces) → nuevo `lib/wall_rebar.py`
- ExternalEvent modes `beams` / `walls` + RebarBatch provenance

**F7.3 (2026-09-01):**
- Viga: densificación de cercos en extremos; UI densify + confine length
- Muro: edge bars + through-wall ties

**F7.4 (2026-09-01) — smoke fixes + wall completeness:**
- **Bug critical:** longitudinal bars failed with `norm` null → `create_from_curves` now infers plane normal; beams pass `BasisZ`
- **Bug:** stirrups floated above beam (LocationCurve on top face) → stirrup section origin offset to mid-height of cover-inset section
- **Bug:** confine length `0` rejected by `_read_number` → `0 = auto` (2 × beam height)
- Muro: end U-bars (wrap thickness), starter bars below base, stock-length split with normative laps
- Preview WPF section canvases on Beams + Walls tabs

**F7.5 (2026-09-01, revisión Claude Code de los cambios F7.4 sin commitear) — 2 bugs reales encontrados y corregidos, verificados por lectura de código + `py_compile`, NO AÚN por smoke en Revit:**
- **Bug (alta confianza):** `wall_rebar.py` — el `normal` del Top U-bar se calculaba como `na.CrossProduct(axis_dir)` (≈ eje Z), cuando las 3 curvas del propio U-bar solo varían en Z y en la dirección de espesor del muro a una posición axial fija — su plano real tiene como normal `axis_dir`, no `na×axis_dir`. Con el valor antiguo, `Rebar.CreateFromCurves` habría recibido un plano incoherente con las curvas (fallo probable en el smoke, silencioso — solo aparece como un error en la lista, fácil de pasar por alto). Corregido a `normal: axis_dir`.
- **Bug (latente/defensivo, no disparado hoy):** la inferencia de `normal=None` en `rebar_engine.create_from_curves` tenía una rama interna inalcanzable (`if abs(d.DotProduct(BasisZ)) > 0.98` dentro de un bloque que ya exige `abs(d.Z) < 0.95` — matemáticamente nunca se cumple) y, para barras casi verticales, llamaba a `compute_vertical_hook_plane_normal(d)` — función cuyo propio docstring dice que es indefinida quando `bar_direction` es paralela a Z (el propio caso que esa rama maneja). Ningún llamante actual dispara esto (todos pasan su propio `normal` ya calculado), pero si algún día lo hiciera con una barra de pilar exactamente vertical, `CrossProduct` daría vector cero y `Normalize()` lanzaría excepción. Corregido: rama muerta eliminada; caso vertical usa `DB.XYZ.BasisX` (siempre bien definido) en vez de la fórmula que se indefine justo en su propio rango de entrada.
- 2 limpiezas cosméticas sin cambio de comportamiento: variable `inward` calculada dos veces en el bucle de End U-bars (la primera asignación quedaba siempre sobrescrita); expresión `y + x_off * 0.0` en `rebar_preview.py` (siempre igual a `y`).
- **Pendiente de verdad:** estos 2 fixes NO se han probado dentro de Revit — sigue bloqueando el cierre de F7 el smoke test descrito arriba. Nada de esto se ha commiteado.

**F7.6 (2026-09-01) — validación empírica de los 2 fixes de F7.5, en vivo contra Revit 2026 real (`Rebar test.rvt` del usuario, vía HuskyBIM MCP — no se pudo disparar el botón real de RebarAutomate, Dynamo no está instalado; se probó la geometría exacta con `Rebar.CreateFromCurves` directamente):**
- **Top U-bar de muro:** con el `normal` corregido (`axis_dir`), Revit crea el elemento sin problema. Con el `normal` antiguo (`na×axis_dir` ≈ Z), Revit lanza `NullReferenceException` — bug confirmado, no solo razonado.
- **Fallback vertical de `rebar_engine.py`:** con `DB.XYZ.BasisX` (el fix), Revit crea una barra exactamente vertical sin problema en el pilar redondo real del modelo (id 1316885). Con un `normal` de longitud cero (lo que producía la fórmula antigua para una dirección exactamente vertical), Revit devuelve literalmente **"norm has zero length"** — la causa raíz confirmada palabra por palabra.
- Los 2 elementos de prueba se crearon y se borraron en la misma sesión; el modelo del usuario queda exactamente como estaba (0 rebar).
- **Esto NO sustituye el smoke test completo** (flujo real de la UI, provenance, marcado, 4 versiones de Revit) — sigue pendiente y sigue bloqueando el cierre formal de F7. Sí es prueba directa, no solo por lectura de código, de que los 2 bugs de F7.5 eran reales y de que las correcciones son válidas en la API de Revit.

**F7.7 (2026-09-01) — barrido geométrico del resto de la geometría F7 nunca antes probada, mismo método (curvas reales + `Rebar.CreateFromCurves` vía HuskyBIM, sobre los hosts reales de `Rebar test.rvt`, cada elemento de prueba creado y borrado en el acto):**

| Geometría | Host real | Resultado |
|---|---|---|
| Viga — cerco centrado en la sección (fix de mid-altura) | Viga 300×600mm (id 1318407) | ✅ Creado; `centerZ` del bounding box = **-300mm exacto**, la mitad exacta de los 600mm — confirma objetivamente que ya NO flota pegado a la cara superior |
| Viga — barra longitudinal (normal = dirección de ancho) | misma viga | ✅ Creada sin error |
| Muro — malla horizontal (normal = Z) | Muro 13.8m (id 1318503) | ✅ Creada sin error |
| Muro — barra de borde (edge bar) | mismo muro | ✅ Creada sin error |
| Muro — atado pasante (tie, normal = eje del muro) | mismo muro | ✅ Creado sin error |
| Muro — espera bajo la base (starter, extiende por debajo de Z=0) | mismo muro | ✅ Creada; bounding box confirma `min.z = -500mm` exacto, extendiéndose bajo la base como se pretende |
| Muro — End U-bar (distinto del Top U-bar ya probado en F7.6) | mismo muro | ✅ Creado; bounding box confirma Z prácticamente constante (plano horizontal correcto) |
| Pilar rectangular — crosstie/atado interior (450×600mm, geometría distinta al pilar redondo de F7.6) | Pilar rectangular (id 1317167) | ✅ Creado sin error |

**Conclusión F7.7:** todos los tipos de curva que F7.3/F7.4 introdujeron (nunca antes ejecutados en Revit, ni siquiera antes del smoke) se comprueban válidos a nivel de API con geometría real del modelo del usuario. **Lo que este barrido NO puede probar** (limitación de la herramienta, no del código): el propagado real de un Rebar SET (array con separación — `create_rebar_by_curves` crea un elemento suelto, no un Set; `create_rebar_set`/el flujo de lotes/provenance/marcado siguen sin probarse en vivo), y los ganchos reales vía `RebarHookType` (p.ej. las esperas en L de zapata, ya confirmadas por lectura de código en la sesión anterior pero no por esta vía). El smoke completo con la UI real sigue siendo el único paso que cierra F7 formalmente.

**Familias de tags:** NO bloquean F7 — ver backlog post-F7 arriba.

**F7.8 (2026-09-01) — feedback real del usuario tras armar el modelo completo (muros funcionando, 2 bugs reales encontrados y corregidos):**

- **Bug crítico — solape de barras al partir por longitud de suministro (`rebar_engine.split_rebar_by_stock_length`):** reportado por el usuario con un caso exacto: barra de muro de 12 m, stock 8 m, solape esperado ~480 mm → el plugin colocaba 2 Rebar Sets de 8 m cada uno, dando un solape real de **4000 mm** (el stock menos el avance calculado), no ~480 mm. Verificado numéricamente offline ANTES de tocar código: la fórmula antigua forzaba cada segmento a medir exactamente `stock_ft`, con un `advance = (total-stock)/(n_segments-1)` que no tenía relación con el lap pedido. Corregido: cada segmento mide ahora `segment_length_ft = (total + (n-1)*lap) / n` (garantizado ≤ stock por construcción), con `advance = segment_length_ft - lap` — el mismo `n_segments` de antes (fórmula sin cambios), pero cada solape consecutivo es EXACTAMENTE `lap_ft`. Esta función es COMPARTIDA — la usan vigas (`beam_rebar.split_long_bars`), muros (`wall_rebar._split_template_curve`/`_split_mesh_sets`), zapatas y losas (`floor_rebar._build_direction_bars`) — así que el fix resuelve el solape incorrecto en las 4 tipologías a la vez, no solo en muros. `rebar_engine.py` no tenía NINGÚN test previo para esta función crítica — se creó `tests/test_rebar_engine_stock_split.py` (5 tests nuevos, incluyendo una regresión exacta del caso 12 m/8 m/480 mm reportado por el usuario) con un stub mínimo de `Autodesk.Revit.DB`/`System`; los 5 pasan, y la suite completa sigue en verde.

- **Bug — End/Top U-bars de muro creados como barras individuales, no como Rebar Sets:** reportado ("los ubars ... los hace individuales, cuando deberían ser rebar sets"). Causa: cada altura (End U-bars) o posición (Top U-bars) generaba su propio `create_from_curves` suelto, aun siendo geometría IDÉNTICA salvo la traslación. Corregido en `wall_rebar.py`: `build_wall_reinforcement` ahora devuelve `end_ubars`/`top_ubars` como `{'sets':[...], 'bars':[...]}` — el MISMO formato que ya usan los U-bars de cierre perimetral de losas/zapatas (`floor_rebar._build_edge_ubars`, `footing_rebar.build_perimeter_closure_ubars_topology`) — agrupando todas las alturas de un mismo extremo (o todas las posiciones de coronación) en UN solo Rebar Set vía `SetLayoutAsMaximumSpacing`, con fallback a bar individual si alguna altura/posición degenera (cara coincidente) y rompe la uniformidad del array. `ui.py` ahora enruta estos U-bars por el helper genérico `_create_grouped_bars` (Set → FreeForm group → bar individual, el mismo camino ya probado para U-bars de losa/zapata), en vez del bucle plano anterior. `style` se deja en `None` (Standard) en vez del `StirrupTie` que usaba la creación individual antigua — decisión deliberada, alineada con el precedente ya en producción de `_build_edge_ubars` (la MISMA topología abierta pata–travesaño–pata usa `style: None` ahí; `StirrupTie` está documentado en `rebar_engine.create_rebar_set` como reservado para lazo CERRADO, no para este U abierto).
  - **Pendiente de verdad:** el propagado real del Set (`SetLayoutAsMaximumSpacing` sobre esta forma abierta concreta) NO se ha podido disparar vía el botón real de pyRevit desde esta sesión (Dynamo no instalado, sin forma de invocar el comando de la extensión por MCP) — la lógica de agrupación se verificó por lectura + `ast.parse` + suite de tests existente (sin regresión), pero el smoke real con Walls tab queda como el siguiente paso del usuario.

- Muros irregulares (no rectos): sigue sin soporte — `get_wall_axis` sigue exigiendo `DB.Line` y rechaza cualquier `LocationCurve` curva. Marcado como prioridad 2 explícita por el propio usuario ("en caso de ser necesario"); no abordado esta vuelta.

**F7.9 (2026-09-01) — segunda vuelta de feedback real tras confirmar los Rebar Sets de muro: 5 fixes más, algunos confirmados por lectura de código, uno (el gap de 440mm en losas) queda abierto:**

- **Capas (armadura principal/secundaria) en muros — confirmado por el usuario: vertical = capa exterior (toca cover), horizontal = capa interior:** `wall_rebar.py` calculaba la malla vertical Y horizontal con la MISMA `depth` (una sola profundidad derivada de `cover_mm + vert_dia_mm/2.0`, reutilizada sin cambio para las horizontales) — física mente imposible, ambas mallas coplanares. Corregido: horizontal usa ahora su propia `cover_mm + vert_dia_mm + horiz_dia_mm/2.0` (capa 2, detrás del diámetro COMPLETO de la vertical), el mismo patrón B1/B2 que `footing_rebar.py` ya usa para along_x/along_y. El mismo bug existía, IDÉNTICO, entre los End U-bars (cierran la malla vertical, capa 1, sin cambios) y los Top U-bars (cierran la horizontal): ambos usaban `cover_mm + u_dia/2.0` — ahora los Top U-bars usan `cover_mm + vert_dia_mm + u_dia/2.0` (capa 2), eliminando la colisión de esquina reportada.

- **Solape — reparto "greedy" en vez de longitud igual (confirmado por el usuario) + diámetro por dirección:** `rebar_engine.split_rebar_by_stock_length` repartía la longitud total EN PARTES IGUALES entre todos los tramos (fix de la vuelta anterior); ahora todos los tramos excepto el último miden exactamente `stock_length_mm` (el máximo), y solo el último absorbe el resto — para 12 m/8 m/480 mm: 8000 mm + 4480 mm (antes: 6240 mm + 6240 mm), mismo número de tramos, mismo solape exacto de 480 mm en cada unión (demostrado algebraicamente en el propio código y con 2 tests nuevos). Además, se encontró y corrigió un bug real de diámetro: `wall_rebar.py` calculaba UN solo `lap_mm` (a partir de `vert_dia`) y lo reutilizaba sin cambio para partir TANTO las verticales COMO las horizontales — empalmando barras de `horiz_dia` con un solape pensado para `vert_dia`. Ahora `build_wall_reinforcement` acepta `horiz_lap_length_mm` por separado, y `ui.py` calcula ambos valores (`standards.lap_length_mm` con `vert_dia` y con `horiz_dia` respectivamente) antes de la llamada. Zapatas y losas ya calculaban el lap correctamente por dirección propia (`default_anchorage_length_mm(own_dia_mm, ...)` dentro de `_build_direction_bars`) — auditado, sin bug ahí.

- **Bug real encontrado y corregido — `RebarWrapper.create_from_curves` podía dejar `self.last_error` en `None` tras un fallo genuino:** si `Rebar.CreateFromCurves` devolvía `None` SIN lanzar excepción (comportamiento válido de la API), el código nunca comprobaba ese `None` — a diferencia de `create_rebar_set`/`create_freeform_group`, que sí lo hacían. Esto explica exactamente el mensaje "— None" reportado en pantalla ("Footing/Floor Perimeter Closure U-Bar (X/Y-anchor) — None") para las 4 aristas de cierre perimetral, en ambos hosts (zapata y losa): la creación INDIVIDUAL (fallback) fallaba sin ningún diagnóstico. Corregido para que siempre reporte `'Rebar.CreateFromCurves returned None.'` como mínimo.

- **Bug real encontrado y corregido — `footing_rebar.build_perimeter_closure_ubars_topology`'s `_one_edge_set` nunca incluía `materialized_bars`:** a diferencia de `floor_rebar._build_edge_ubars` (que sí construye una entrada por cada posición a lo largo del borde), la versión de zapatas devolvía un único `curves`/`array_length_mm`/`spacing_mm` SIN la lista de posiciones individuales — así que si el Set fallaba, `ui.py._create_grouped_bars` no tenía ningún dato con el que reconstruir vía FreeForm ni barras individuales, y directamente no creaba NADA para esa arista (coincide con los "— None" sin ninguna barra resultante). Corregido: `_one_edge_set` ahora calcula cada posición a lo largo del borde (`_evenly_spaced`) y materializa su propia geometría, igual que losas.

- **"Los Ubars están a 440mm de la cara lateral del forjado" — investigado a fondo, SIN causa raíz encontrada todavía; queda abierto:** releída la construcción completa de `_build_edge_ubars`/`_chain_at` — las posiciones de cada U-bar de cierre en losas se derivan directamente del polígono YA offseteado por `side_cover_mm` (el cover lateral real, ver F7.8), así que el "lomo" del U-bar debería quedar a ~cover mm del canto real, no a 440mm. Una comprobación en vivo sobre un elemento real de esta MISMA losa (id 1320717, ejecución anterior a este fix) dio un gap de 35mm para 40mm de cover — correcto. No se pudo reproducir el bug por lectura de código ni con ese dato en vivo. **Pendiente:** el usuario debe reportar el Element ID exacto de la barra mostrada en la imagen (visible en la barra de estado de Revit al seleccionarla, o en el Panel de Propiedades) para inspeccionar su geometría real directamente, o volver a probar tras estos fixes y confirmar si el gap sigue apareciendo.

- **Huecos de forjado sin Ubars — la investigación de esta vuelta apunta a un rechazo real de `Rebar.CreateFromCurves`, no solo a un fallo de `_create_grouped_bars`:** con el fix del `last_error` de arriba, la próxima ejecución debería mostrar un mensaje mucho más informativo que "— None" y decir si el problema es la creación inicial de la barra en sí (probable, dado que las 4 aristas EXTERIORES de zapata y losa fallan igual) o la propagación del Set. Pendiente del próximo test para confirmar.

**F7.10 (2026-09-01) — capas de muro flippable (selector real, no solo la fórmula) + panel de resultados sin truncar en las 4 pestañas:**

- **Selector de capa vertical/horizontal en muros:** confirmé numéricamente contra el muro real (id 1318503) que la fórmula de F7.9 SÍ coloca la vertical más superficial (50mm de cara, cover+Ø/2 exacto) y la horizontal detrás (66mm base); no encontré ningún bug de signo. Aun así, añadido el checkbox pedido — **"Vertical bars in the outer layer"** en la pestaña Walls (`ChkWallVertOuter`, marcado por defecto) — que controla malla principal Y ambos U-bars de forma consistente vía el nuevo parámetro `vert_is_outer` en `build_wall_reinforcement`.

- **Panel "Result" (las 4 pestañas: Footings/Floors, Columns, Beams, Walls) truncaba a 12 líneas — reportado como imposible de revisar un run largo:** `TxtResult`/`TxtColumnResult` cortaban a 12 issues + "...and N more"; `TxtBeamResult`/`TxtWallResult` cortaban a 12 SIN siquiera avisar que había más. Los 4 eran además `TextBlock` (no seleccionable/copiable). Cambiados los 4 a `TextBox` de solo lectura (misma `ScrollViewer` de la columna izquierda que ya existía — ahora crece con todo el contenido en vez de recortarlo) y eliminado el límite de 12 líneas en los 4 sitios de `ui.py`. Esto también resuelve de forma indirecta la petición pendiente de "pégame la lista completa de issues" del punto de los huecos — la próxima ejecución ya la mostrará entera sin pedir nada más.

- **Bugs vistos de paso, NO corregidos aún (fuera de alcance de esta petición concreta):** el panel de resultados de muros mostró "Shape classification failed: Cannot import name Rebar" y "Marking failed: write() takes exactly 3 arguments (4 given)" — errores reales de las fases F3/F4 (marcado/clasificación de forma), no relacionados con la geometría de esta sesión. Pendientes de investigar si el usuario lo pide.

**F7.11 (2026-09-02) — con el log completo ya visible, 3 bugs de F3/F4/tagging reales encontrados y corregidos, más 2 bugs de geometría live-verificados (vigas, capas):**

- **F4 (clasificación de formas) rota en TODAS las ejecuciones desde siempre:** `rebar_shape_classifier.py` hacía `from Autodesk.Revit.DB import Rebar` — `Rebar` vive en `Autodesk.Revit.DB.Structure`, no ahí. Corregido.

- **F3 (marcado) roto en TODAS las ejecuciones desde siempre:** `rebar_marking.py` llamaba `shared_params.read/write(doc, rebar_id, campo, ...)` en absolutamente todos sus usos (11 sitios), pero la firma real es `read(elem, nombre, default)`/`write(elem, nombre, valor)` — un ELEMENTO primero, sin `doc`. Corregido con dos wrappers `_read`/`_write` que resuelven `doc.GetElement(rebar_id)` antes de delegar, sin tocar el resto del fichero.

- **~30 "The 3D view ownerDBViewId is not locked" por ejecución:** no es un bug nuestro — Revit exige la vista 3D bloqueada para poder etiquetar y el plugin nunca lo comprobaba antes de intentarlo, fallando igual para cada barra. Ahora comprueba `View3D.IsLocked` antes y, si no está bloqueada, salta el etiquetado entero con UN mensaje explicando cómo arreglarlo.

- **Bug real de geometría en vigas — "la armadura principal sale fuera de las vigas" (confirmado en vivo, viga 1318407):** las barras longitudinales usaban `axis.GetEndPoint(0)/(1)` (la LocationCurve cruda) sin ningún inset en la dirección de longitud. La LocationCurve mide 10340.0mm; el sólido REAL de la viga (`get_BoundingBox`, tras el mitrado/unión con la columna de apoyo en cada extremo) mide solo 10325.4mm — 7.3mm de más en CADA extremo. Confirmado NO relacionado con el split (la viga mide ~10.3m, muy por debajo del stock de 12m). Corregido: nueva `_clamp_axis_to_bbox()` recorta el eje al bounding box real del sólido (proyectando las 8 esquinas del bbox sobre la dirección del eje — funciona para cualquier orientación), aplicada una sola vez antes de que nada más derive del eje (barras longitudinales Y zonas de cercos).

- **Capas de muro — confirmado en vivo que mi fórmula anterior SÍ era correcta** (vertical a 50mm de cara = cover+Ø/2 exacto, horizontal a 66mm detrás), pero el selector `ChkWallVertOuter` añadido en F7.10 sigue ahí por si el usuario lo necesita en otro muro/orientación.

- **Edge bars eliminadas del todo (petición explícita — "ya tenemos rebar sets, no es necesario"):** quitado `include_edge_bars`/`edge_dia_mm` de `wall_rebar.build_wall_reinforcement` (parámetros, bloque de generación, split, dict de retorno), su wiring en `ui.py` (`_read_wall_inputs`, `_process_wall`, `_run_wall_reinforcement`, `WallEdge_Click`) y el checkbox/panel correspondiente en `ui.xaml` (la card "Edge Bars & Ties" pasa a llamarse simplemente "Ties"). Esto también explicaba el "2 barras al principio y 2 al final" que veía el usuario — exactamente 2 caras × 1 posición por extremo × 2 extremos.

- **"Los ubars paran muy lejos del borde de la losa" — investigado, parece YA corregido en una fase anterior:** el propio código (`floor_rebar.py`, comentario "PHASE 3.5.8 item 1 FIX") ya sustituyó el cover vertical del mat (`bottom_cover_mm`/`top_cover_mm`) por el cover lateral REAL del elemento (`side_cover_mm`, leído de `get_native_cover_mm(doc, host, 'Exterior', ...)`) para el offset en planta (X/Y) de `bottom_outer`/`bottom_holes` — la MISMA fuente que usan tanto el mat principal como `_build_edge_ubars`. Esto es exactamente la causa descrita por el usuario (usar un cover ajeno/vertical como si fuera el lateral, dejando el U-bar "muy lejos" del canto real). El suelo de prueba del modelo (id 1317654) no tiene armado activo ahora mismo para verificarlo en vivo con esta build concreta — probable que la imagen del usuario mostrara barras de una ejecución ANTERIOR a este fix. **Pendiente:** que el usuario vuelva a armar ese forjado desde cero y confirme si el gap persiste; si persiste, es un bug distinto (p.ej. el propio leg length/anclaje, que SÍ debe ser largo por normativa y no es un bug).

**F7.12 (2026-09-02) — 2 causas raíz reales encontradas y confirmadas EN VIVO con `revit_create_rebar_by_curves` (no solo por lectura de código), tras que el fix de ROUND 1 de vigas resultase ser un no-op:**

- **Vigas — el fix de F7.11 (clamp al `get_BoundingBox`) no hizo NADA — confirmado en vivo (mismos 7.3mm de más en cada extremo, dígito a dígito, antes y después del fix):** causa real — `host.get_BoundingBox(None)` de Revit NO se contrae para reflejar una unión/mitrado en el extremo de un elemento de framing, al contrario que el sólido REAL visible (patrón YA documentado en este mismo código: `rebar_engine.get_isolated_solid_bbox`, escrito en la Phase 3.5.6 para un problema análogo en encepados con pilotes anidados). Corregido `_clamp_axis_to_bbox` para usar esa MISMA utilidad ya probada (deriva el bbox de las `Solid.Edges` reales del sólido de nivel superior, que sí reflejan la unión) en vez de escribir un segundo fix específico de vigas para la misma clase de bug.

- **Zapatas/losas — "Rebar.CreateFromCurves returned None" en las 4 aristas exteriores, SIEMPRE, en TODAS las ejecuciones:** reproducido en vivo con geometría real de la zapata 1317591: el rectángulo cerrado (`_link_loop_edge`, el lazo StirrupTie que se usa cuando una arista es demasiado corta para caber un U-bar abierto, o cuando la punta de la pata caería fuera del material) reutilizaba sin cambio el `normal_vec` (= dirección tangente de la arista) del U-bar ABIERTO — pero el propio plano de ESTE rectángulo cerrado contiene la dirección de la arista Y Z, así que su normal real debe ser la dirección perpendicular (hacia dentro), no la tangente. Confirmado con dos pruebas en vivo idénticas salvo el `normal`: con `unit_dir` → `NullReferenceException` real de Revit; con la dirección perpendicular correcta → creado sin problema (`Shape 31`). Exactamente la misma clase de bug ya corregida una vez esta sesión para el Top U-bar de muro. Corregido en las 2 ramas que construyen este rectángulo (arista demasiado corta / punta de pata fuera de material) para usar `leg_dir` en vez de `normal_vec`.
  - **Por qué esto también podría arreglar los huecos sin Ubars:** las 3 losas comprobadas en vivo confirman que el bug SOLO se dispara en el forjado 1317654 (el que tiene forma irregular + el hueco añadido a mano) — las otras 2 losas (rectángulos simples, sin huecos) crean sus 4 cierres perimetrales sin ningún problema. Un hueco, por definición, es más probable que produzca aristas cortas que caen en esta misma rama de "lazo cerrado" — si es así, este MISMO fix resuelve también el hueco sin necesidad de ningún cambio adicional. Pendiente de confirmar en la próxima ejecución.
  - Añadido diagnóstico (`print` + `debug_failed_edges`) en ambas ramas de fallback a lazo cerrado, con la longitud real de la arista y de la pata — para saber, si el problema persiste, si es una arista genuinamente corta o un `nominal_leg_mm` calculado mal.

**F7.13 (2026-09-02) — F7.12 confirmado por el usuario (clasificación 56/56, marcado 38 posiciones, cierres perimetrales exteriores ya se crean); 2 hallazgos más, uno corregido y verificado por tests, el otro con diagnóstico en vez de un tercer fix a ciegas:**

- **Bug real de diseño, corregido — los U-bars de cierre en huecos pequeños salían como un lazo cerrado PARALELO a la cara del hueco, en vez de U-bars perpendiculares hacia el material:** reportado con imagen (un "marco" azul rodeando un hueco de losa) y confirmado con los propios mensajes INFO del log ("edge... length 580mm, fell back to ONE closed link — edge shorter than 2x its own leg length (400mm)"). Causa: cuando una arista es demasiado corta para caber varias U-bars espaciadas con su inset de esquina, el código saltaba DIRECTAMENTE a `_link_loop_edge` (un rectángulo cerrado corriendo A LO LARGO de la arista) — aunque la arista siga siendo perfectamente válida para UNA sola U-bar centrada, con sus patas perpendiculares hacia el material (que es exactamente la función estructural de un cierre perimetral: anclar la armadura cortada en el hormigón de alrededor). Corregido en `floor_rebar._build_edge_ubars`: ahora intenta primero UNA U-bar abierta centrada en la arista (con el mismo chequeo `leg_tips_ok` de material, evaluado solo en esa posición) y únicamente cae al lazo cerrado si NI SIQUIERA una pata centrada cabe dentro de material real (el caso de una costilla genuinamente estrecha, p.ej. entre dos huecos). Actualizado `tests/test_floor_rebar_phase23.py` (el test anterior afirmaba explícitamente lo contrario — las 4 aristas de un hueco pequeño DEBÍAN cerrar en lazo — se ha invertido el criterio para reflejar el comportamiento correcto, verificado con el mismo hueco de 500×500mm: las 4 aristas ahora dan U-bar abierta centrada, ninguna en lazo cerrado, cada pata con la longitud nominal completa).

- **Vigas — "sigue sin meter las barras principales dentro de la viga", confirmado en vivo que DOS fixes distintos (bbox nativo, luego `get_isolated_solid_bbox`) han dado el MISMO resultado exacto, cifra a cifra, en la viga real (1318407):** demasiada coincidencia para ser un bug de lógica distinto cada vez — el sospechoso principal es que `beam_rebar.py` no se está recargando en pyRevit entre pruebas (el propio patrón de caché de módulos ya documentado en esta sesión para las columnas circulares). En vez de arriesgar un TERCER fix a ciegas, se ha añadido un diagnóstico real: `build_beam_rebar_curves` ahora devuelve la longitud del eje ANTES y DESPUÉS de `_clamp_axis_to_bbox` como aviso visible en el panel de resultados de `ui.py` — la próxima ejecución dirá con certeza si el código se está ejecutando y qué calcula, sin necesidad de conjeturar más.

- **"En los huecos de los forjados no coloca Ubars como debería" — causa raíz real encontrada y mitigada:** confirmada como el propio límite YA documentado en `slab_topology.py` (módulo docstring, "POLYGON OFFSET — DISCLOSED LIMITATION"): al crecer un hueco HACIA AFUERA por el cover, una entrante/forma estrecha puede autointersectarse en un polígono "bow-tie", que `polygon_edges_mm` reduce a menos de 3 aristas válidas tras su propio filtro de longitud mínima — CERO U-bars de cierre para ese hueco, solo un `print` de warning en consola, nunca un error visible. Corregido en `floor_rebar._build_edge_ubars`: ahora recibe también los huecos SIN offsetear (`raw_holes`, mismo orden/índice que `large_holes`) y, si un hueco degenera a <3 aristas tras el offset, reintenta con el propio contorno crudo de ESE hueco (geometría real de Revit tesela­da, no puede autointersectarse de esa forma) en vez de quedarse sin ninguna arista — el lomo del U-bar de cierre queda entonces exactamente sobre el borde real del hueco (sin margen de cover para esa barra concreta), con un warning explícito en consola avisando del trade-off, en vez de no colocar ningún U-bar. **Pendiente de verdad:** no verificado aún contra un hueco real que reproduzca el bow-tie (el forjado de prueba disponible ahora mismo no tiene huecos suficientemente estrechos para forzarlo) — lógica revisada por lectura + `ast.parse` + suite de tests existente sin regresión, pero el smoke real con un hueco geométricamente conflictivo queda pendiente.

**F7.14 (2026-09-02, ronda 2) — F7.13 confirmado por el usuario (huecos ya centran su U-bar; cierres exteriores 56 creados); 2 hallazgos nuevos, uno con diagnóstico ampliado (vigas) y otro corregido con decisión explícita del usuario (Shape 00 en huecos):**

- **Vigas — el diagnóstico de F7.13 confirmó que el eje NO es el problema** (`DIAGNOSTIC: beam axis length before clamp = 10300.0mm, after _clamp_axis_to_bbox = 10300.0mm — unchanged`), pero la armadura creada real (viga 1318407, verificada en vivo) sigue saliendo 20mm más larga en CADA extremo (span combinado de los 2 segmentos: 10340mm vs 10300mm del eje). Releído `compute_longitudinal_bar_lines`/`_cross_section_point`: su matemática es puramente transversal, sin ningún mecanismo de extensión axial — descarta esa función como origen directo. Siguiendo el mismo patrón "diagnóstico en vez de un tercer fix a ciegas", se ha añadido un SEGUNDO diagnóstico, más preciso, en `build_beam_rebar_curves`: compara la longitud del eje ya recortado contra la longitud de la PRIMERA línea de barra devuelta por `compute_longitudinal_bar_lines`, **antes** de que `split_long_bars`/`rebar_engine.split_rebar_by_stock_length` entre en juego — aislará si los 20mm/extremo se originan construyendo la línea de la barra o en el split/lap-offset posterior. **Pendiente:** re-ejecutar el armado de vigas (con Reload) y revisar la nueva línea `DIAGNOSTIC: clamped axis = ...mm, first TOP bar line (pre-split...) = ...mm (...)`.

- **Huecos — Shape Code 00 en vez de 21, causa confirmada por código (no era un bug nuevo):** los U-bars centrados de huecos (fix de F7.13) se crean como entradas sueltas `style=None`; con 2+ de ellas, `ui.py::_create_grouped_bars` las agrupa vía `create_freeform_group` — mecanismo que, según el propio docstring de esa función ("PHASE 3.5 REVERSAL"), **siempre** reporta Shape 00 a cambio de mantenerlas agrupables por MRA/schedule. Es la MISMA decisión de compromiso ya tomada explícitamente en una fase anterior, aplicada sin querer también a los huecos. **Decisión del usuario, tomada explícitamente hoy:** para los U-bars de huecos (`is_hole=True`), forzar Shape real (`create_from_curves` individual) en vez de agrupar por FreeForm, aunque se pierda la agrupación MRA en esos huecos concretos — el resto del plugin (perímetro exterior, zapatas, muros) mantiene la prioridad "agrupación > nombre de forma" sin cambios. Implementado: `floor_rebar._build_edge_ubars` etiqueta cada entrada de cierre (`sets` y `bars`) con `'is_hole': is_hole` (True para aristas de huecos, False para el perímetro exterior — se propaga sin cambios a través de `footing_rebar.build_perimeter_closure_ubars_topology`, que ya delegaba directamente en esta función); `ui.py::_create_grouped_bars` separa los candidatos a FreeForm en huecos vs no-huecos — los de hueco NUNCA entran en el bundle FreeForm (ni como `set` ni como `bars` sueltas), van siempre por `create_from_curves` individual.
  - **Segunda petición del usuario ("solo una por cada lado del hueco... quiero más de uno si el lado es largo, igual que las distancias entre Ubars del contorno del forjado"):** confirmado que SÍ era una petición de mejora, no solo una observación. La rama "arista demasiado corta para el espaciado con inset de esquina completo del perímetro" ahora prueba primero un margen RELAJADO (`nominal_leg_mm / 2`, sigue dejando espacio libre de la esquina compartida) al MISMO `spacing_mm` que usa el perímetro principal — si eso cabe con 2+ posiciones (cada punta de pata comprobada contra material real), se crean como un Set de varias U-bars en vez de una sola centrada; solo si ni siquiera cabe 1 posición así, cae a la única U-bar centrada de F7.13, y solo si ni eso cabe, al lazo cerrado.
  - Verificado con la suite de tests existente: `tests/test_floor_rebar_phase23.py` (Test 13) actualizado — para el hueco de prueba de 500×500mm (aristas de 550mm tras el cover), el margen relajado cabe con 3 posiciones a 200mm de espaciado (230mm de tramo útil > 200mm) — cada arista pasa de "1 U-bar centrada" a "Set de 3 U-bars", con nuevas aserciones sobre `is_hole=True` y `materialized_bars` de longitud 3. Las 19 suites de test, sin regresión (`python tests/test_X.py`, exit 0 cada una).
  - **Pendiente:** confirmación en vivo contra el modelo real (Shape Code esperado 21 en vez de 00 para los U-bars de huecos; recuento de U-bars por arista de hueco según su longitud real).

**F7.15 (2026-09-02, ronda 3) — F7.14 confirmado por el usuario (Shape 21 correcto en huecos) con un flequillo pendiente; vigas: la investigación cambia de eje por completo tras conectar de nuevo con HuskyBIM:**

- **Huecos — "solo un ubar por cada cara del hueco" seguía pasando tras F7.14, causa real: un SEGUNDO hueco en la cascada nunca se reintentó con el margen relajado.** El fix de F7.14 solo reintentaba el margen relajado (`nominal_leg_mm/2`, mismo `spacing_mm` del contorno) dentro de la rama "arista demasiado corta para el inset de esquina completo" — pero una arista que SÍ supera ese umbral (`usable_hi > usable_lo`) puede aun así caer en `footing_mod._evenly_spaced` devolviendo un único punto medio, cuando el tramo útil entre los dos insets completos es <= `spacing_mm` — esa rama nunca reintentaba nada, se conformaba directamente con 1 barra. Corregido en `floor_rebar._build_edge_ubars`: factorizado `_relaxed_spaced_positions`/`_make_set` como helpers compartidos, usados AHORA en ambas ramas (la de "demasiado corta" Y la del camino normal cuando solo cabe 1 posición). Verificado con un nuevo Test 13b (hueco de 650×650mm, aristas de 700mm — el caso exacto que antes se quedaba en 1 barra): ahora da un Set de 3 barras por arista. 19/19 suites en verde.
- **Vigas — la investigación se REORIENTA por completo: NO es un problema de longitud axial, es un desplazamiento TRANSVERSAL (ancho) real, confirmado en vivo con HuskyBIM sobre la viga 1318407:** el diagnóstico de F7.14 (longitud pre-split = eje recortado, coinciden exactamente) obligaba a mirar más allá — se volvió a conectar con Revit 2026 y se leyeron los parámetros REALES `Bar Length`/`Length of each bar` de los 2 segmentos partidos: **8000mm y 3100mm exactos** (8000+3100−800mm de solape = 10300mm, EXACTO al eje recortado) — es decir, la longitud SIEMPRE fue correcta; la lectura anterior de "20mm de más en cada extremo" era un artefacto de cómo `get_bounding_box`/`element_geometry` miden el SÓLIDO redondeado de una barra (radio 10mm en una H20), no un error real de longitud. El verdadero problema, encontrado comparando bounding boxes: la viga real ocupa X=[19165, 19465] (300mm de ancho), pero SUS PROPIAS barras longitudinales (top Y bottom, mismo desplazamiento en ambas) ocupan X=[19391, 19589] — **desplazadas ~175mm fuera del centro de una sección de solo 300mm de ancho, sobresaliendo claramente por el lado.** Esto explica "sigue saliendo la armadura principal fuera de las vigas" mucho mejor que cualquier teoría de sobre-longitud axial. Pista adicional: el tipo de esta viga (`RC Beam: 300x600mm`) reporta `Section Shape: Not Defined` en Revit — es una familia cargable personalizada, no un perfil paramétrico estándar, lo que hace sospechar de la detección de caras laterales (`_beam_faces`) o del punto de referencia usado por `engine.compute_cover_point` sobre `side_a`/`side_b` para ESTA familia en concreto. Añadido un tercer diagnóstico en `build_beam_rebar_curves` (antes de calcular las líneas de barra) que surge la posición transversal real de `edge_a`/`edge_b` respecto al eje, y los normales de `side_a`/`side_b` — la próxima ejecución dirá si las caras detectadas son las correctas o no, sin más conjeturas. **Pendiente de verdad:** re-ejecutar el armado de vigas y revisar la nueva línea `DIAGNOSTIC: side_a/side_b width offsets from axis...`.

**F7.16 (2026-09-02, ronda 4) — VIGAS: causa raíz encontrada, reproducida y corregida en vivo (no solo por lectura de código); huecos: aclarada la causa de "siguen saliendo individuales" (no es un bug nuevo):**

- **Vigas — causa raíz real: `create_rebar_set`'s `SetLayoutAsMaximumSpacing` no "rellena entre" la primera y la última barra dadas — propaga las copias adicionales DESDE la barra semilla, MÁS ALLÁ, en la dirección de `+normal`.** El diagnóstico de F7.15 (`side_a/side_b width offsets = 92.0 / -92.0`) demostró que la detección de caras y el cálculo de cover eran correctos — la pista real era que `_beam_faces` añade `side_a`/`side_b` en el orden que sea que `cover_mgr.faces` los enumere (arbitrario), pero `compute_longitudinal_bar_lines` siempre camina de `edge_a` a `edge_b` sin importar cuál cayó en qué lado — así que la barra semilla (`top_lines[0]`, la que `create_rebar_set` usa como plantilla) podía caer en el lado `+normal`. Confirmado EN VIVO con una reproducción manual contra la viga real 1318407 usando `revit_create_rebar_by_curves` + `revit_set_rebar_layout` (los mismos parámetros que usa el plugin, `spacing=92mm, array_length=184mm`): sembrada en el lado `+normal` (X=19407mm, viga de 300mm de ancho X=[19165,19465]) → el Set completo acaba en X=[19391,19589], **totalmente fuera de la sección**; sembrada en el lado `-normal` (X=19223mm) → el MISMO `SetLayoutAsMaximumSpacing` da X=[19219,19417], **exactamente dentro de la sección**. Corregido en `compute_longitudinal_bar_lines`: nuevo parámetro `seed_side_normal` (el mismo `long_bar_normal_vec` compartido entre las llamadas de top Y bottom — usar el `width_dir` local de cada llamada habría arreglado solo una de las dos, ya que su signo se invierte entre `top.normal` y `bottom.normal`) — `edge_a`/`edge_b` se reordenan para que la barra semilla caiga SIEMPRE en el lado `-normal`, sin importar qué cara detectó `_beam_faces` como `side_a`. Reproducido de nuevo en vivo tras el fix: mismo resultado correcto (X=[19219,19417]). 19/19 suites de test en verde.
- **Huecos — "siguen saliendo individuales" aclarado, no es un bug nuevo:** las 8 aristas reportadas (2 huecos × 4 lados, 580mm cada una, pata de anclaje 400mm) SÍ pasan por el margen relajado de F7.15 (`_relaxed_spaced_positions`), pero con margen relajado (200mm) el tramo útil es de solo 180mm — si el `spacing_mm` configurado para el contorno es >= 180mm (razonable, coherente con "misma distancia que el contorno"), la función `_evenly_spaced` devuelve correctamente UNA sola posición, no dos — no hay más margen para meter una segunda barra sin violar el propio `spacing_mm` que el usuario pidió respetar, y sin reducir la longitud de anclaje (400mm, ya calculada por normativa) por debajo de lo estructuralmente necesario. Esto es matemáticamente correcto dado el par (arista 580mm, pata 400mm, spacing del contorno) — no un bug de código.

**F7.17 (2026-09-02, ronda 5) — huecos: decisión explícita del usuario implementada (mínimo 3 U-bars por lado en huecos pequeños, con margen de esquina más ajustado SOLO para huecos):**

- El usuario confirmó su razonamiento: para un hueco de 500×500mm, quiere **al menos 3 U-bars por lado**, aunque eso signifique un margen de esquina más ajustado que el usado en el resto del perímetro (sacrificando la consistencia "misma distancia que el contorno" pedida en F7.14/F7.15, solo para huecos donde haga falta). Implementado en `floor_rebar._build_edge_ubars`: nueva constante `_HOLE_MIN_BARS = 3` y helper `_hole_min_bar_positions`/`_try_hole_min_bars` — SOLO para `is_hole=True`, cuando ni el espaciado estándar ni el margen relajado (F7.15) dan 2+ posiciones, se reintenta con un margen de esquina mucho más ajustado (`nominal_leg_mm / 4`, en vez de `/2`) apuntando directamente a un mínimo de 3 posiciones — cada punta de pata se sigue comprobando individualmente contra material real (`point_in_material_mm`), y la longitud de la pata de anclaje (400mm, ya calculada por normativa) **nunca se reduce** — solo se ajusta la distancia ENTRE barras a lo largo de la arista. Verificado con un nuevo Test 13c que reproduce EXACTAMENTE el caso reportado (hueco 500×500mm, anclaje 10mm→400mm, arista 550mm): ahora da 3 U-bars por arista, cada una con su pata completa de 400mm. 19/19 suites en verde. **Pendiente de confirmar en vivo.**

---

## Competitive notes — SOFiSTiK Reinforcement (verificado en disco 2026-09-01)

KS Digital Studio / KennySTRUCT: **no está instalado en esta máquina** — se buscó en
`Program Files`, `Program Files (x86)`, `ProgramData` y todo el AppData del usuario,
más los manifiestos `.addin` de Revit 2024–2027; cero coincidencias. Cualquier
comparación anterior con "KS Digital Studio" en este documento era especulativa,
no verificada — se retira hasta que el usuario confirme dónde está instalado.

SOFiSTiK Reinforcement 2026 (v5.0.313) SÍ está instalado como ApplicationPlugin
de Revit (`C:\ProgramData\Autodesk\ApplicationPlugins\sofistik_reinforcement_2026.bundle`).
Hechos verificados directamente en disco (no interpretación de marketing):

- **Catálogo de formas real** en `Contents\shape_catalogs\{code}\`: 5 normativas
  (BS_8666_2005 — 36 formas, **BS_8666_2020 — 40 formas**, EN_ISO_3766 — 26 formas,
  SANS_282_2011 — 31 formas, SSHV_2014 — 190 formas). Cada forma es un JSON
  declarativo: `shape_detail_family` (mapea a una familia Revit tipo
  `SOFiSTiK_Detail_RebarShape_11`), `constraints` por segmento (`geom_type`,
  `fixed_length`, `angle`/`angle_min`/`angle_max`, `relation`) y `parameters`
  (`displayed_name`, `calculation_type`) — un esquema paramétrico declarativo,
  separado del renderizado geométrico. Cada catálogo tiene un `options.json`
  (`default_shape_code`, `precision_decimals`, `include_hooks_in_shape_definition`,
  `default_shape_detail_family`). **Directamente comparable con
  `data/rebar_standards/_schema.json`/`data/shape_catalogs/` de NOSA** — vale la
  pena contrastar campo a campo antes de F4/F9.
- **BVBS real, confirmado por DLLs**: `Bvbs_bond_mgd_rc.dll`,
  `Bvbs_rpc_mgd_rc.dll`/`Bvbs_rpc_rc.dll`. Sistema de despiece/BBS SEPARADO del
  catálogo de formas: scripts Lua por normativa en
  `analysis_bin\data\cad\schedule\codes\{bs,bs_2020,din,iso,sans,sshv}\{shapes,hooks,end_treatment,coupler}\*.lua`
  que dibujan cada glifo procedimentalmente, más `units.json` por normativa con
  columnas de tabla de despiece y precisión — referencia útil para el diseño de
  `rebar_schedule.py`/F8.
- **"Rebar Templates" reales** en `Contents\content\reinforcement\runtime\RebarTemplates\`:
  plantillas `.rvt` con `content.json` por tipo de host — Vigas EU (cercos 2/3/4
  ramas), Pilares EU (redondo/cuadrado/rectangular, 2–6 ramas, espiral), Zapatas
  EU (Pad S/M/L, Cup, Sleeve), Muros de cortante EU (básico), Bordes de losa EU
  (basado en cara, no en host — Inner/Outer Edge 1ª/2ª capa, hueco rectangular
  2ª capa). Confirma el flujo real: categoría → plantilla con nombre por
  host/cara → set paramétrico generado — más cercano a "recetas por tipo de
  elemento" que a un catálogo de formas suelto.
- Override de catálogo por usuario en
  `%APPDATA%\SOFiSTiK\SOFiSTiK Reinforcement 2026\shape_catalogs\` — mismo
  patrón que el `NOSA_Configs/rebar_standards/` override de F2.
- No se encontró manual/ayuda offline (.chm/.pdf) — la ayuda se sirve vía un
  control de navegador embebido; no se pudo leer el texto real del flujo de
  la "Rebar Wizard". Tampoco se encontraron tablas de cover/lap/mandrel como
  ficheros externos — probablemente compiladas dentro de las DLLs de análisis,
  no verificable sin decompilar (no se ha intentado).

**Prioridad inmediata derivada de esto (reemplaza la tabla anterior, no verificada):**
El bug de `normal=None` de F7.4/F7.5 es exactamente la clase de error que
SOFiSTiK nunca expone al usuario, porque restringe el plano desde sus propias
plantillas paramétricas en vez de inferirlo genéricamente — confirma que
resolver el `normal` desde geometría de CARAS real (no desde `LocationCurve`)
es la única vía robusta, y ya es el camino que sigue este código.

**El siguiente paso de valor real** sería replicar la ESTRUCTURA declarativa
`constraints`/`parameters` de SOFiSTiK para el propio `data/shape_catalogs/`
de NOSA (F4/F9) en vez de la comparación genérica de la tabla anterior — un
formato ya usado por 5 normativas reales, con 40 formas solo para BS 8666:2020.

---

## Análisis de brecha — manual de SOFiSTiK Reinforcement (aportado por el usuario, 2026-09-01)

El usuario compartió un manual de especificaciones técnicas de SOFiSTiK
Reinforcement (documento comercial/funcional, NO verificado en disco como
la sección anterior — se trata como referencia de producto, no como hecho
comprobado). Contrastado contra el código REAL de NOSA (leído, no asumido)
antes de listar cada brecha:

**Ya cubierto en NOSA, mejor de lo que parecía a primera vista:**
- *Numeración inteligente + agrupación + tolerancia de longitud* — el manual
  lo presenta como diferenciador, pero `rebar_marking.py` YA tiene
  `number_scope` (`per_host`/`per_project`/`per_view`) y
  `dedup_tolerance_mm` configurable por normativa. No es brecha; como mucho,
  falta un modo `per_sheet`/`per_phase` literal si algún cliente lo pide.
- *"Freeze" de marcas aprobadas* — YA EXISTE: `NOSA_Rebar_Finalized=1` y
  `rebar_marking.renumber_batch` lo respeta explícitamente (visto en
  `rebar_batch.py` desde F1). Falta solo exponerlo con un botón/checkbox en
  el Gestor de lotes si no lo tiene ya — verificar UI, no motor.
- *Shape Details 2D asociativos* — Revit ya ofrece `RebarShape`/Bending
  Detail NATIVO con asociatividad bidireccional 3D↔2D de fábrica (por eso
  la Decisión 7.A del blueprint F2 fue "usar Bending Detail nativo" en vez
  de construir un sistema propio). El "diferencial" de SOFiSTiK aquí es
  automatizar la COLOCACIÓN de esas vistas nativas, no inventar la
  asociatividad — coincide con el alcance ya previsto en F6, no es una
  capacidad nueva a construir desde cero.

**Brechas reales, priorizadas:**

| # | Capacidad (manual) | Estado NOSA verificado | Prioridad |
|---|---|---|---|
| 1 | Vigas continuas multi-vano (detecta apoyos, recorta en punto de momento nulo) | Vigas aisladas — decisión explícita v1 (línea 329 de este documento) | Alta, pero requiere detectar vanos adyacentes — fase propia post-F7, no un fix menor |
| 2 | Esperas de pilar dobladas en el nudo si cambia de sección | `column_rebar.py`: esperas rectas únicamente | Ya en backlog legacy §7 de este documento — confirma prioridad |
| 3 | Huecos en losa con esquineras a 45° | `floor_rebar.py` corta la malla pero no arma el hueco (deuda ya documentada) | El manual da la solución concreta a implementar en F9: esquineras 45° + perimetrales, no solo "ignorar/armar por tamaño" |
| 4 | Punzonamiento (stud rails / estribos en cesta) | No existe | Post-1.0 — SOLO la parte geométrica (colocar un patrón de armado dado por el usuario) está al alcance de NOSA; la parte "calcula desde el FEA" queda fuera de alcance porque NOSA no tiene motor de cálculo propio |
| 5 | Motor de "cobertura de Aₛ" leyendo resultados FEA (.cdb) | No existe — NOSA genera desde parámetros de usuario, no desde análisis | **Fuera de alcance de NOSA**: sería integrar o sustituir un solver estructural, una categoría de esfuerzo distinta a un plugin de generación geométrica. No añadir al roadmap salvo decisión explícita del usuario de ampliar el alcance del producto |
| 6 | `NOSA_Rebar_Layer` alimenta filtros de color automáticos | Parámetro existe, pero generadores de viga/muro/pilar no lo stampan aún (deuda ya documentada F2/F3) | El manual confirma que es alto valor real (no solo cosmético) — subir prioridad de esta deuda ya conocida |
| 7 | `Create Views`: alzado + plantas + secciones + plantilla de vista en un clic por elemento | F6 ya crea secciones/MRA/tags por separado; no hay un comando único "paquete de vistas" con View Template aplicada | Mejora F6 polish / post-F7, esfuerzo medio (orquestar comandos ya existentes, no inventar geometría nueva) |
| 8 | `Tag All` sin cruces de leader (anti-colisión) | F6.3 ya tiene Auto Tag; sin garantía anti-colisión de leaders | Mejora F6, esfuerzo medio-alto (geometría de colisión 2D) |
| 9 | Ocultar barras intermedias repetitivas, mantener recuento en la etiqueta | No existe | Post-1.0, esfuerzo alto (filtros de vista dinámicos por elemento) |
| 10 | BBS con miniatura gráfica de doblado por fila | F5 exporta CSV/XLSX sin gráficos | Mejora F5/F8, esfuerzo medio SI se reutiliza la vista de Bending Detail nativa como fuente de la miniatura en vez de dibujar desde cero |
| 11 | Export PXML (ERP/prefabricado) | No existe | Post-1.0, prioridad baja salvo petición de un cliente real |
| 12 | Esperas de zapata en L/U apoyadas sobre la limpia | Verificado: `footing_rebar.build_dowel_curves` ya usa `RebarHookType`/`get_hook_type_by_angle` — los dowels YA llevan un doblez tipo L en el extremo, no son barras rectas | No es brecha real; a lo sumo, confirmar en smoke que el doblez apoya sobre la cara de limpia y no queda suspendido |

**Recomendación de secuencia** (mantiene "cero pérdida de funcionalidad" y
diff quirúrgico — no reordena F7/F8 ya en curso):
1. Cerrar F7 (smoke real, commit) — ya en curso, no tocar por esto.
2. Antes de F9: ítems 3 y 6 (huecos con esquineras 45°, stamp de
   `NOSA_Rebar_Layer`) — ya eran deuda conocida, el manual solo confirma
   prioridad y aporta el diseño concreto del ítem 3.
3. F8 sin cambios (BVBS ya planeado).
4. Post-1.0, en orden de valor/esfuerzo: ítem 7 (Create Views), ítem 2
   (esperas dobladas pilar), ítem 1 (vigas continuas), ítem 10 (miniatura
   BBS), ítem 8 (anti-colisión tags), ítems 4/9/11 (punzonamiento
   geométrico, ocultar barras, PXML) según demanda real.
5. Ítem 5 (motor de cobertura desde FEA) — NO planificar sin que el usuario
   decida explícitamente ampliar el alcance del producto; es un cambio de
   categoría, no una función más.

**Flyer visual de SOFiSTiK Reinforcement (aportado por el usuario, 2026-09-01)** —
2 páginas reales (no 55; la mayoría del PDF original eran imágenes, extraídas
con pdftotext+pymupdf). Confirma con IMÁGENES, no solo texto de marketing:
- Cinta de comandos real: `Shape Detail`, `Split Rebars`, `Copy`, `Mark`,
  `Align`, `Stagger`, `Group`, `Explode`, `Openings`, `Distribute`, `Spacer`,
  `From Line`, `Tag All`, `Bar End`, `Hide/Unhide`, `Layer`, `To Face`,
  `Bent`, `Custom`, `Insert Fabric`, `Update`, `Check`/`Warnings`, `Schedule`.
- Tabla de despiece REAL con columnas: Bar mark, Bar diameter, Length of
  each bar, Total number, Total length, dbr (mandril), Shape code,
  End-hook, Bending A/B/C — y una **miniatura del doblado dibujada en cada
  fila** (no solo texto). Esto es exactamente el ítem 10 del análisis de
  brecha anterior, ahora con la prueba visual de que es así como se hace.
- Una segunda tabla separada **"Rebar Weight Schedule"**: por diámetro,
  nº de barras, longitud total, peso total (kg), con fila de TOTALES —
  **NOSA no tenía ningún campo de peso hasta hoy** (ver F5 más abajo,
  cerrado en esta misma sesión).
- Render 3D de una viga con cerco correctamente ENVOLVIENDO las barras
  longitudinales (confirma visualmente la convención RC correcta que se
  arregló hoy en `beam_rebar.py`).

**F5 — peso de armado añadido (2026-09-01):** `rebar_schedule.py` gana
`mass_per_length_kg_m(diameter_mm)` (fórmula universal densidad×sección,
coincide con las tablas de las 3 normativas propias a menos de 0.02kg/m —
ver la función para el razonamiento de por qué NO se hizo depender de
`std`), `total_weight_kg` en cada posición del despiece, CSV/XLSX con
columna de peso, y una segunda hoja "Weight Summary" en el XLSX por
diámetro + fila de TOTALES — mismo formato que la "Rebar Weight Schedule"
del flyer. 2 tests nuevos, 7/7 en `test_rebar_schedule.py`.

**Bugs reales encontrados y corregidos hoy contra el modelo real del
usuario (smoke manual del usuario, no el mío):**
- **Viga — cerco dentro de las barras, confirmado y corregido.** El
  rectángulo del cerco usaba `cover + diámetro COMPLETO de la barra
  longitudinal` (inset MAYOR = más adentro) mientras la barra usaba
  `cover + mitad de su propio diámetro` (inset MENOR = más afuera) — al
  revés de la convención real (el recubrimiento se mide hasta la
  armadura más exterior, el cerco). Corregido en
  `compute_longitudinal_bar_lines`/`build_beam_rebar_curves` para
  cualquier combinación de diámetros.
- **Losa — "The minimum length of rebar shape is 25 mm", losa entera sin
  armar.** Una losa genuinamente no rectangular (~11% menos área que su
  bounding box) generaba un intervalo de material degenerado que solo se
  filtraba cuando "Perimeter Closure U-Bars" estaba activo. Añadido un
  filtro de longitud mínima (`_MIN_REBAR_SEGMENT_MM = 26mm`) que se aplica
  siempre en `_build_direction_bars`.
- **Vigas — barras longitudinales optimizadas a Rebar Set.** Nueva
  `group_parallel_bar_chains_into_sets` en `beam_rebar.py`; `ui.py`
  intenta el Set primero, cae a barras individuales si falla — mismo
  patrón que los cercos.
- **Columnas circulares — CONFIRMADO Y CORREGIDO (2026-09-01, con
  traceback real del propio Revit del usuario).** La instrumentación de
  diagnóstico funcionó a la primera: `TypeError: unsupported operand
  type(s) for *: 'indexer#' and 'float'` en
  `_find_cylindrical_face_diameter_mm`, línea `radius_ft * 2.0 *
  _MM_PER_FT`. Causa raíz: `DB.CylindricalFace.Radius` (y su accesor
  `get_Radius()`) NO se comporta como un `float` simple en este binding
  de pythonnet — se resuelve como un objeto envoltorio "indexer#". Esto
  explica por qué el fix de detección anterior (que SÍ identificaba
  correctamente la columna como circular) producía 0 armado sin ningún
  error visible hasta que el traceback completo lo sacó a la luz.
  **Corregido evitando `.Radius` por completo**: una vez confirmado que
  existe una `CylindricalFace` real (prueba de circularidad genuina), el
  diámetro se calcula desde el bounding box del propio host
  (`X-extent == Y-extent == diámetro`, exacto para una sección
  circular) — el mismo cálculo que esta función YA usaba como último
  recurso para círculos facetados, solo que ahora se activa antes.
  Verificado dos veces: (1) `test_column_rebar_phase3.py`'s propio test
  de columna circular fallaba tras el cambio porque su fixture nunca
  necesitó un bbox (usaba `.Radius` del stub directamente, que en Python
  puro SÍ es un float normal) — corregido el fixture con un bbox real
  de 400mm y el test vuelve a pasar; (2) el bounding box REAL del pilar
  1316885 del usuario (600×600mm, ya consultado en una ronda anterior de
  esta sesión) confirma que el cálculo dará 600mm de diámetro, no un
  valor degenerado.

  **CONFIRMADO EN VIVO por el usuario (2026-09-01) — capturas + datos
  objetivos vía la API tras su propio Reload + regenerar:** pilar
  1316885 (atraviesa el forjado de "First floor" a media altura) → 12
  barras H20 individuales (verticales, nunca Sets en circulares, por
  diseño) + **2 Sets de cercos H10** (15 y 14 — exactamente las 2 zonas
  esperadas por el cruce con el forjado); pilar 1318255 (sin forjado que
  cruzar) → 6 H20 + **1 Set de cercos H10** (16). **0 warnings de
  Revit.** Bug cerrado del todo — columnas circulares ya funcionan
  correctamente, incluida la lógica multi-planta.

---

## F8 — Export BVBS 🚧 Código escrito, formato SIN validar (2026-09-01)

**Entregables:**
- `lib/rebar_export_bvbs.py` (bar_to_bvbs_line: cabecera + geometría + checksum) — ✅ escrito
- Acción "Export BVBS" en el dashboard de Detailing & Tools (junto a Generate Schedule) — ✅ cableada
- `tests/test_rebar_export_bvbs.py` — 11 tests puros, verifican invariantes estructurales (parseo de `shape_params`, presencia de campos, determinismo, escritura de fichero) — ✅ verdes

**⚠️ NO se cumple el criterio de éxito original todavía — decisión explícita del usuario (2026-09-01):**
No había fichero `.abs` de ejemplo ni el spec oficial de BVBS disponibles; el usuario autorizó implementar "con el mejor conocimiento disponible" en vez de bloquear la fase. Consecuencia: el formato de línea BF2D (anchos de campo exactos, unidades del diámetro, y sobre todo **el algoritmo de checksum**) es un **best-effort explícitamente marcado como no verificado** — `rebar_export_bvbs.BVBS_FORMAT_VERIFIED = False`, con un test que falla si alguien lo cambia a `True` sin querer. La UI muestra una alerta de aviso cada vez que se exporta. **Lo que SÍ está garantizado:** la extracción de datos desde Revit (marca, diámetro, forma, segmentos, cantidades vía `rebar_schedule.generate_schedule_data`) es 100% responsabilidad de NOSA y ya se apoya en F5, probado.

**Pendiente real para cerrar F8:**
1. Conseguir un fichero `.abs` real (de un ferrallista, de SOFiSTiK, o el spec oficial BVBS) y contrastar campo a campo — el propio `bar_to_bvbs_line`/`_compute_checksum` están aislados a propósito para que corregirlos sea un cambio pequeño, no una reescritura.
2. Validar contra un validador BVBS externo o una máquina real antes de dar el criterio de éxito original por cumplido.
3. Fix de paso (2026-09-01): `rebar_schedule` se cargaba con `imp.load_source(...)` dentro de `BtnGenerateSchedule_Click` en cada click (comentario decía "load_module" pero no lo era) — movido a la carga única a nivel de módulo, igual que el resto de hermanos.

**Deps:** F4 (forma), F5 (despiece)

---

## F9 — Losas + release 1.0.0 ⏳ Pending

**Entregables:**
- **Losas:** `lib/floor_rebar.py` completo (freeform, negativos sobre apoyos, borde/huecos)
- `data/content_manifest.json` (versión familias + aviso obsoletas)
- **Matriz de humo 100% en 2024/2025/2026/2027**
- Docs de usuario (`docs/USER_GUIDE.md`)
- **Release `1.0.0` tagged**

**Criterio de éxito:** Proyecto real armado principio a fin. Matriz de humo completa en 4 versiones.

**Deps:** Todas anteriores

**Timeline:** 5–7 días

---

## Matriz de validación (cuándo probar en 4 versiones)

| Fase | Test sin Revit | Humo 1 versión | **Humo 4 versiones** | Cuándo mergear a `main` |
|---|---|---|---|---|
| F0 | Parseo/imports | No necesario | No | Al cerrar F0 (low risk) |
| F1 | 12/12 tests | Bind+gen. zapata | No necesario | Al cerrar F1 ✅ |
| F2 | Standards: schema, cálculos | Cambio std → cambio cover | No necesario | Al cerrar F2 |
| F3 | Dedup: casos sintéticos | Marcas zapata real | No necesario | Al cerrar F3 |
| F4 | Poligonales fake | >90% shape_code | **✅ OBLIGATORIO** | Tras humo 4 versiones |
| F5 | BVBS checksum, CSV | Tabla vs manual | No necesario | Al cerrar F5 |
| F6 | — | Plano etiquetado+acotado | **✅ OBLIGATORIO** | Tras humo 4 versiones |
| F7 | — | Viga+muro sin crash | **✅ OBLIGATORIO** | Tras humo 4 versiones |
| F8 | Checksum BVBS | Fichero .abs válido | No necesario | Al cerrar F8 |
| F9 | — | Losa + fixture completo | **✅ OBLIGATORIO FULL** | Antes de release 1.0.0 |

**Regla:** Fase con ✅ **OBLIGATORIO** en 4 versiones NO se mergea a `main` hasta pasar humo en 2024/2025/2026/2027.

---

## Timeline estimado (conservative)

| Fase | Días | Acumulado | Hito |
|---|---|---|---|
| F0 | — | — | ✅ Cerrado |
| F1 | — | — | ✅ Cerrado |
| **F2** | 3–4 | 3–4 d | Perfiles funcionan |
| F3 | 4–5 | 7–9 d | Marcado real |
| F4 | 5–7 | 12–16 d | Clasificador + humo 4 versiones |
| F5 | 4–5 | 16–21 d | Despiece + export |
| F6 | 5–6 | 21–27 d | Detallado + humo 4 versiones |
| F7 | 6–8 | 27–35 d | Vigas+muros + humo 4 versiones |
| F8 | 3–4 | 30–39 d | BVBS |
| F9 | 5–7 | 35–46 d | Losas + release 1.0.0 |

**Total: 5–7 semanas** (tiempo Claude Code + revisión + humo en Revit).

Part-time: **10–14 semanas**.

---

## Ventajas NOSA sobre SOFiSTiK

| Ventaja | Por qué |
|---|---|
| **Un código 2024–2027** | SOFiSTiK: 4 bundles. NOSA: `revit_compat` centralizado. |
| **Perfiles JSON editables** | SOFiSTiK: Lua compilado. NOSA: JSON plano + overrides en `NOSA_Configs/`. |
| **Catálogo EHE nativo** | SOFiSTiK no trae EHE (usa ISO). NOSA: `EHE-08.json` nativo. |
| **Preview WPF puro Python** | SOFiSTiK: ribbon .NET. NOSA: `rebar_preview.py` ya funciona. |
| **Open source / extensible** | SOFiSTiK: binarios cerrados. NOSA: código abierto pyRevit. |
| **Integración NOSA.extension** | Mismo ecosistema 50+ plugins (SharedParamManager, StructuralQA, etc.). |

---

## Mejoras post-F9 (prioridad 2)

| Mejora | Cuándo | Esfuerzo | Impacto |
|---|---|---|---|
| Catálogo `ehe_08/` con formas EHE propias | Post-F4 | Medio | Alto (España) |
| Integración StructuralQA/ModelHealthHub | Post-F9 | Bajo | Medio |
| Export Tekla / RISA | Post-F8 | Alto | Medio |
| Armado de escaleras (tipología 6) | Post-F9 | Alto | Medio |

---

**Última actualización:** F7 en smoke real del usuario (F7.1→F7.17) — F3/F4 tenían bugs de firma/import que los rompían desde siempre, corregidos; huecos: Shape 21 confirmado correcto, mínimo 3 U-bars por lado en huecos pequeños implementado por decisión explícita del usuario. Vigas: causa raíz real encontrada y CORREGIDA — `SetLayoutAsMaximumSpacing` propagaba el Set entero fuera de la sección por la barra semilla estar en el lado equivocado de `normal`; verificado en vivo antes/después con reproducción manual. Pendiente de que el usuario confirme ambas cosas con el botón real. Aviso pendiente de investigar: crashes ocasionales de Revit al recargar pyRevit. Todo commiteado en `develop` (actualizado 2026-09-28).
