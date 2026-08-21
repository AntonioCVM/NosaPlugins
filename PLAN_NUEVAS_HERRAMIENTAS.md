# Plan de actuación — Nomenclatura automática (sheets + elementos)

Basado en:
- `00000-NOSA-TN-XXX-T-X-0018-I23-File_Naming_Protocols.pdf` (protocolo NOSA de nomenclatura, campos F1–F9)
- La imagen de referencia "Structural dimensions" (tabla tamaño → código: `RC beam 400x500mm → B1`, `Concrete column 500mmØ → C1`, `Pile cap 900x1950x1200mm → PC-01`, etc.)
- El código real ya existente en el disco del usuario (leído esta sesión, no supuesto)
- Datos reales del modelo abierto (conectado vía HuskyBIM — Revit 2025)

**No se ha implementado nada todavía — esto es solo el plan.**

---

## Hallazgo clave: gran parte de esto ya existe, no se parte de cero

Antes de proponer nada nuevo, se auditó qué ya hay construido. Resultado — **ambas peticiones tienen ya una base sólida**, en distinto grado:

| Petición | Estado real |
|---|---|
| 1. Parámetros de sheets según el protocolo NOSA | **Ya implementado ~85%** — `SheetHub.pushbutton` (activo en el ribbon) + `nosa_utils/sheet_protocol.py` + la lógica heredada de `SheetNamer.nobutton` ya leen el contenido de cada sheet (vistas, niveles, nombres) y **sugieren** los 9 campos del protocolo, incluyendo sugerencias de campos nuevos no vistos antes. Quedan huecos concretos, no una construcción desde cero (ver §1). |
| 2. Comments automáticos por tipo+tamaño | **Existe el patrón, pero solo para pilotes/encepados** — `PileMaster`'s `NumberingLogic.apply_numbering` ya agrupa elementos por Familia+Tipo y asigna `Comments` igual a todo el grupo (exactamente el comportamiento que pides), pero está acotado a Structural Foundations. Confirmado en tu modelo real: la viga 500x500mm (id 1325620) **ya tiene `Comments = "B2"`** — es decir, ya sigues esta convención manualmente; falta sistematizarla. |
| 3. Automatización tipo "live coordinates" | **El mecanismo ya existe y funciona** — `PileMaster/lib/logic_dmu.py` registra un `IUpdater` de Revit (vía `nosa_utils/dmu_lifecycle.py`, activado desde `startup.py`) que escribe parámetros dentro de la misma transacción cuando un pilote se mueve o se crea. Es un patrón reutilizable directo para lo que pides. |

Esto cambia el enfoque: en vez de "construir 2 plugins nuevos", el plan es **completar/generalizar** infraestructura que ya está en producción.

---

## 1. Parámetros de sheets (protocolo de nomenclatura)

### 1.1 — Qué hace ya `SheetHub` / `sheet_protocol.py`
- Lee cada sheet (`ViewSheet.SheetNumber/Name`) y sus title blocks, con alias de nombres de parámetro (`Project Number`, `Functional Breakdown`, `Spatial Breakdown`, `Form`, `Discipline`, `Document Number`, `Current Revision` — F1, F3–F8).
- **Sugiere F3** (función) por palabras clave del nombre del sheet ("General Arrangement" → GA, "Section" → SC, "Detail" → DT, etc.) y por tipo de vista Revit (`ViewType.Section` → SC, etc.).
- **Sugiere F4** (espacial) por nivel de las vistas colocadas en el sheet, con diccionario de sinónimos (Ground/GF → 000, Roof → RF1, Basement → BA1/BA2...).
- **Sugiere F7** (nº de documento) por un diccionario `F7_HINTS` — pero **solo 14 entradas, una por código F3** (p.ej. todo lo que sea `GA` sugiere `2200`, sin distinguir 21xx/22xx/25xx como hace la tabla real del PDF).
- Ya numera F7 secuencialmente por paquete/nivel/edificio cuando hay varios sheets del mismo tipo (`assign_f7_sequences`).
- Ya soporta un flujo de "sugerir → revisar → aplicar", no escribe a ciegas.

### 1.2 — Huecos confirmados contra el PDF y el modelo real
Se comparó `F7_HINTS` contra la tabla de la página 2 del PDF y contra los 31 sheets reales del proyecto abierto (todos siguen ya el esquema numérico del PDF correctamente, p.ej. `2100` Site plan, `2200` Substructure, `2500` RC plans, `3000`/`3500` secciones generales/RC, `4000`/`4500` detalles generales/RC, `5000`–`5002` cantidades, `5500` BBS, `6000`/`6500` analítico/Revit, `7000`/`7500` general/sketches):

- `F7_HINTS` no distingue sub-rangos dentro de un mismo F3 (ej: un GA de "Site plan" debería sugerir `21xx`, uno de "Substructure/GA" `22xx`, uno de "RC plans" `25xx` — hoy los 3 sugieren `2200` sin más matiz).
- Faltan rangos enteros de la tabla del PDF: `1000's` (Existing/Demolition/Cut&fill), `5000's` desglosado (Project cover `5000` vs Quantities `50xx` vs RC schedules `55xx`), `6000's` desglosado (Structural analysis `60xx` vs Revit models `65xx`), `7000's` desglosado (General `70xx` vs Sketches `75xx`), `8000's` (Health & safety).
- El campo F9 (descripción libre) y el F8 (revisión: P/C/I/PC + sufijo `.01/.02` de borrador) no se validan contra el formato exacto del PDF.

### 1.3 — Propuesta (mejora, no reconstrucción)
1. Sustituir `F7_HINTS` (dict plano F3→F7) por una tabla de sugerencia de dos niveles: **F3 + palabras clave del contenido del sheet** → sub-rango F7 correcto, cubriendo la tabla completa de la página 2 del PDF.
2. Cuando el contenido no encaje en ningún patrón conocido (p.ej. un tipo de sheet nuevo), **sugerir explícitamente un F7 nuevo dentro del rango correcto** (siguiente número libre en el sub-rango que más se le parezca) en vez de caer en un valor por defecto genérico — esto es literalmente el "sugerir caracteres aunque no existieran" que pides.
3. Extender `F4_PRESETS`/`LEVEL_KEYWORDS` con los códigos de bloque (`A01`, `AEL`, `ASC`, `CB2`...) de la página 1 del PDF que hoy no están cubiertos, con el mismo mecanismo de "sugerir nuevo si no coincide".
4. Confirmar contigo si `SheetHub` es ya la herramienta que usas para esto, o si hace falta promover `SheetNamer` de `.nobutton` a visible — antes de tocar nada, para no duplicar UI.

**Riesgo**: bajo — es extender tablas de datos y añadir un caso "sugerir nuevo", no tocar el mecanismo de lectura/escritura que ya funciona.

---

## 2. Comments automáticos por Categoría + Tipo (como los Marks de PileMaster)

### 2.1 — Patrón a generalizar
`PileMaster/lib/logic_numbering.py` → `NumberingLogic`:
- Agrupa elementos por `FamilyName` (o Familia+Tipo).
- Asigna el mismo valor de `Comments` (o `Mark`, según el modo) a todo el grupo.
- Tiene UI de revisión: una grid (`dgPrefixes`) que muestra cada grupo detectado con un prefijo/sufijo editable antes de aplicar — el usuario ve "RC Beam: RC beam - 400x500mm → 12 elementos" y puede ajustar el código antes de escribir nada.
- Ya evita duplicados con `only_empty` (no toca elementos que ya tienen valor) y calcula el siguiente número libre mirando lo que ya existe en el modelo.

Dato real confirmado: el `Type Name` de los elementos **ya incluye el tamaño de forma legible** (`"RC beam - 500x500mm"`, no solo `"RC beam"`) — así que agrupar por `Family : Type` (igual que ya hace `NumberingLogic` para encepados) es suficiente para conseguir "mismo tamaño → mismo Comment" **sin** tener que leer y comparar parámetros de ancho/alto por separado. Es la misma simplicidad que ya usa el código existente, generalizada.

### 2.2 — Alcance propuesto (categorías + prefijo, según tu imagen de referencia)

| Categoría Revit | Prefijo sugerido | Nota de detección |
|---|---|---|
| Structural Framing (vigas) | `B` | Ya existe la categoría directamente |
| Structural Framing / Foundation (vigas de atado / ground beams) | `GB` | **A confirmar contigo**: en este modelo, `CenterBeamToColumn` ya distingue "ground beam" como `OST_StructuralFoundation` con `LocationCurve` (vs. encepado = `LocationPoint`) — reutilizar ese mismo criterio |
| Structural Columns | `C` | Directo |
| Floors | `F` | Directo |
| Structural Foundations, `LocationPoint`, no-pilote | `PC` | Ya existe en `NumberingLogic` |
| Structural Foundations, familia "pile" | `P` | Ya existe en `NumberingLogic` |
| Walls | `W` | Directo |

### 2.3 — Propuesta de herramienta
Dos opciones, a decidir contigo:
- **(A) Nueva pestaña/modo dentro de PileMaster** ("Element Numbering" en vez de solo "Pile Numbering") — reutiliza el 90% del código (`NumberingLogic`, la grid de prefijos, la lógica de `only_empty`) y solo añade las categorías nuevas a `classify_elements`/`group_by_type`.
- **(B) Plugin nuevo independiente** (p.ej. `ElementCommentsHub`) que **importa y reutiliza** `NumberingLogic` desde `PileMaster.pushbutton/lib` (mismo patrón que ya usa `logic_dmu.py` para importar `logic_coords` de un pushbutton distinto) — mantiene PileMaster centrado en pilotaje y separa esto en su propia herramienta de "nomenclatura de elementos" para todo el modelo.

**Recomendación**: (A) si quieres una sola herramienta de numeración estructural; (B) si prefieres mantener PileMaster enfocado solo en pilotaje/encepados y tener una herramienta aparte para el resto de elementos. Lo decides tú — el coste de desarrollo es similar porque el núcleo (`NumberingLogic`) se reutiliza igual en ambos casos.

**Extra, en la misma línea de "sugerir aunque no exista"**: cuando aparezca un Tipo nuevo sin código asignado todavía, sugerir automáticamente el siguiente número libre dentro de su prefijo de categoría (p.ej. si ya existen B1 y B2, un tercer tamaño de viga sugiere B3), en vez de dejarlo en blanco.

**Riesgo**: medio — toca `Comments`/`Mark` de elementos reales en producción; mitigado por el mismo patrón de revisión-antes-de-aplicar que ya usa PileMaster (nunca escribe sin que el usuario vea la grid primero), y por evitar sobrescribir elementos que ya tienen valor salvo que el usuario lo pida explícitamente.

---

## 3. Automatización (equivalente a "live coordinates")

### 3.1 — Patrón a generalizar
`logic_dmu.py` + `nosa_utils/dmu_lifecycle.py`, registrado desde `startup.py`:
- Un `IUpdater` de Revit, registrado una vez a nivel de aplicación al arrancar pyRevit.
- Se dispara automáticamente cuando un elemento de la categoría objetivo se **crea** o **cambia geometría**, dentro de la misma transacción que causó el cambio (sin pasos de deshacer extra).
- Lee su configuración de un JSON (`live_coords.json`) en cada ejecución, así que activar/desactivar desde la UI de PileMaster tiene efecto inmediato sin reiniciar Revit.
- Recarga el módulo de lógica en caliente en cada arranque de Revit (evita tipos IronPython/CPython obsoletos tras recargar la extensión).

### 3.2 — Diferencia importante con el caso de coordenadas
El updater de coordenadas solo necesita la geometría del propio elemento que cambió. **Asignar Comments necesita más contexto**: si aparece un pilote nuevo, hay que saber si su Tipo **ya tiene** un código asignado en otros elementos del modelo (para reutilizarlo) o si es realmente nuevo (para sugerir el siguiente número libre). Esto es más caro que escribir una coordenada, así que la propuesta es:
- El updater, al detectar un elemento nuevo/con Tipo cambiado en una categoría objetivo, **busca primero** si algún otro elemento del mismo `Family : Type` ya tiene `Comments` con formato válido (prefijo+número) y, si lo encuentra, reutiliza ese mismo valor.
- Si no lo encuentra (Tipo genuinamente nuevo), asigna el siguiente número libre del prefijo de su categoría — igual que en el modo manual, pero sin intervención del usuario.
- Nunca sobrescribe un `Comments` que el usuario haya rellenado a mano con algo que no siga el patrón `PREFIJO+número` (para no borrar anotaciones reales del usuario).

### 3.3 — Propuesta
1. **Fase manual primero**: construir y validar la herramienta de la Sección 2 como acción manual/por lotes (igual que PileMaster empezó siendo solo numeración por lotes antes de añadir el modo en vivo).
2. **Fase automática después**, solo si el modo manual funciona bien en un proyecto real: añadir `logic_dmu_comments.py` siguiendo el mismo esqueleto que `logic_dmu.py` (Updater + config JSON + toggle en la UI), registrado desde `startup.py` igual que el de coordenadas.
3. Activable/desactivable por proyecto desde la propia herramienta, igual que hoy se activa/desactiva "Live Coordinates" en PileMaster — nunca activo por defecto sin que el usuario lo encienda explícitamente.

**Riesgo**: alto si se hace antes de tiempo (un Updater que escribe en cada creación de elemento, mal calibrado, puede generar ruido o sobrescribir datos reales en un proyecto grande) — de ahí la secuencia manual→automático, no automático directo.

---

## Plan de fases (orden sugerido)

| Fase | Qué | Riesgo | Depende de |
|---|---|---|---|
| **A** | Extender tabla F7 de `SheetNamer`/`sheet_protocol` con los sub-rangos completos del PDF + sugerencia de códigos F4 nuevos | Bajo | — |
| **B** | Confirmar contigo: opción (A) o (B) de la Sección 2.3, y el criterio de "ground beam" (§2.2) | — | Decisión tuya |
| **C** | Generalizar `NumberingLogic` a Beams/Columns/Floors/Walls, modo manual/por lotes, con la grid de revisión ya existente | Medio | Fase B |
| **D** | Validar Fase C contigo en un proyecto real antes de tocar nada automático | — | Fase C probada en Revit |
| **E** | Updater automático de Comments (`logic_dmu_comments.py`), opt-in, mismo patrón que coordenadas en vivo | Alto | Fase D validada |

Cada fase, igual que el resto de esta sesión: un commit propio, `py_compile` + prueba en Revit antes de pasar a la siguiente, sin activar nada automático (Fase E) hasta que el modo manual esté confirmado funcionando en tu día a día.

**No se ha tocado ningún archivo todavía** — a la espera de tu confirmación sobre §2.3 (opción A o B) y el criterio de ground beams antes de empezar a ejecutar.
