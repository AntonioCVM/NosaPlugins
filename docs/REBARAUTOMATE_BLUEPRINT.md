# RebarAutomate — Blueprint de Implementación

> Especificación completa para llevar `NOSA.tab/Structures.panel/Quantities.pulldown/RebarAutomate.pushbutton`
> desde un generador geométrico de barras sin datos ni normativa, a un plugin de armado
> profesional comparable a SOFiSTiK Reinforcement, funcionando de forma **idéntica en
> Revit 2024, 2025, 2026 y 2027**.
>
> Fuente: análisis en disco de `C:\ProgramData\Autodesk\ApplicationPlugins\sofistik_reinforcement_2026.bundle`
> + baseline real de `NOSA.extension`. Fecha: 2026-08-27.
>
> **Los GUIDs de la Parte 5 son DEFINITIVOS. Cópialos tal cual y no los regeneres nunca.**

---

## Índice

- [00 · Cómo usar este documento](#00--cómo-usar-este-documento)
- [01 · Objetivo y alcance multi-versión](#01--objetivo-y-alcance-multi-versión)
- [02 · Auditoría del estado actual](#02--auditoría-del-estado-actual)
- [03 · Arquitectura objetivo](#03--arquitectura-objetivo)
- [04 · Capa de compatibilidad Revit 2024–2027](#04--capa-de-compatibilidad-revit-20242027)
- [05 · Sistema de Shared Parameters](#05--sistema-de-shared-parameters)
- [06 · Perfiles de normativa (EHE / ISO / BS)](#06--perfiles-de-normativa-ehe--iso--bs)
- [07 · Catálogo de formas y clasificador](#07--catálogo-de-formas-y-clasificador)
- [08 · Motor de numeración y marcado](#08--motor-de-numeración-y-marcado)
- [09 · Subsistema de detallado](#09--subsistema-de-detallado)
- [10 · Despiece y exportación a fabricación](#10--despiece-y-exportación-a-fabricación)
- [11 · Generadores por tipología](#11--generadores-por-tipología)
- [12 · Rediseño de la interfaz](#12--rediseño-de-la-interfaz)
- [13 · Contenido entregable (.rfa / plantillas)](#13--contenido-entregable-rfa--plantillas)
- [14 · Empaquetado, despliegue y versionado](#14--empaquetado-despliegue-y-versionado)
- [15 · Estrategia de pruebas y QA](#15--estrategia-de-pruebas-y-qa)
- [16 · Hoja de ruta por fases](#16--hoja-de-ruta-por-fases)
- [17 · Decisiones pendientes de confirmar](#17--decisiones-pendientes-de-confirmar)
- [18 · Apéndices](#18--apéndices)

---

## 00 · Cómo usar este documento

Este blueprint es la fuente de verdad del rediseño. No es código: define contratos, esquemas,
nombres, GUIDs y criterios de aceptación. El código lo escribe el agente respetando estos
contratos al pie de la letra. Se ejecuta por fases (Parte 16).

### Reglas de trabajo

1. **No romper lo que funciona.** El motor geométrico (creación de curvas, `CoverGeometryManager`,
   `split_rebar_by_stock_length`, generadores de zapatas/pilares) está probado en fuego real
   (Phase 4/5). Se refactoriza *alrededor*, no *encima*.
2. **Reglas como dato, no como código.** Recubrimientos, diámetros de doblado, longitudes de
   solape, ganchos, shape codes y columnas de tabla salen de los `.py` y pasan a JSON versionado
   en `data/`. Es la lección central de SOFiSTiK.
3. **Todo lo que crea el plugin lleva marca de origen.** Ninguna barra sin
   `NOSA_Rebar_Created_By_NOSA`, `NOSA_Rebar_Batch_Id` y `NOSA_Rebar_Generator_Version`. Sin
   esto no hay selección por lote, ni rollback, ni re-etiquetado, ni detección de huérfanos.
4. **Una sola API abstraída.** Ninguna llamada directa a un miembro de la API de Revit que
   difiera entre 2024–2027 fuera de `nosa_utils/revit_compat.py`. Ver Parte 4.
5. **mm en el borde, pies dentro.** Toda función pública trabaja en milímetros; la conversión a
   pies internos de Revit ocurre dentro. Ya es la convención del código; mantenerla.
6. **Fallar avisando, no reventar.** Las funciones *plurales* (lotes) capturan el error por
   elemento y siguen; las *singulares* lanzan. Convención ya establecida en `rebar_detailing.py`.
7. **IronPython 2.7 + CPython 3 a la vez.** Importar de `nosa_utils.compat` (`text_type`,
   `iteritems`, `ensure_text`…), nunca usar `unicode()`, `basestring`, `xrange` directamente.

### Leyenda de estados

- **[OK]** verificado en disco o en fuego real
- **[NUEVO]** a construir desde cero
- **[DECISIÓN]** requiere confirmación del usuario (Parte 17)
- **[RIESGO API]** difiere o puede diferir entre versiones de Revit

---

## 01 · Objetivo y alcance multi-versión

### Definición del producto final

Un plugin de armado 3D→2D que, dado un elemento estructural (zapata, pilar, viga, muro, losa)
o un conjunto de ellos, genera armado real de Revit conforme a una normativa configurable,
lo numera, lo detalla en planos y lo exporta a despiece y a fabricación — con paridad de
comportamiento en cuatro versiones de Revit.

| Capacidad | Hoy | Objetivo |
|---|---|---|
| Generación geométrica de barras | Parcial: zapatas + pilares OK; vigas/muros stub | 5 tipologías completas + variables |
| Datos en las barras (marca, capa, estado) | Ninguno | Shared parameters NOSA (Parte 5) |
| Normativa configurable | Ninguna (cover 40 mm fijo) | Perfiles EHE-08 / EN ISO 3766 / BS 8666 (Parte 6) |
| Shape codes / formas normalizadas | Ninguno | Catálogo + clasificador (Parte 7) |
| Numeración de posiciones | Nativa de Revit | Motor propio, dedup, prefijos por proyecto (Parte 8) |
| Etiquetado / detallado | Tag nativo por categoría | Familias de tag NOSA + MRA + secciones (Parte 9) |
| Despiece (BBS) | Nada | Generador de tabla + Excel/CSV (Parte 10) |
| Exportación a fabricación | Nada | BVBS (Parte 10) |
| Multi-versión Revit | Parcheado ad hoc (`get_id_value`) | Capa `revit_compat` completa (Parte 4) |

### Matriz de entornos de destino

| Revit | Runtime .NET | Motor pyRevit por defecto | Notas de armado relevantes |
|---|---|---|---|
| 2024 | .NET Framework 4.8 | IronPython 2.7.12 (CPython 3 opcional) | Última versión con `ElementId.IntegerValue`. API `DB.Structure` estable. |
| 2025 | .NET 8 | IronPython 2.7.12 / CPython 3.x | **Corte grande:** `ElementId.IntegerValue` eliminado → `ElementId.Value` (Int64). Cambio de runtime .NET. Revisión de APIs obsoletas. |
| 2026 | .NET 8 | IronPython 2.7.12 / CPython 3.x | Continuidad con 2025. Verificar novedades de `Rebar`/`RebarShape`. |
| 2027 | .NET 8 (verificar en RTM) | por confirmar en release | Asumir continuidad; la capa de compat aísla el riesgo. Validar en beta. |

**Por qué el riesgo es acotado:** RebarAutomate es 100 % Python sobre pyRevit. No compila
ensamblados .NET propios, así que el cambio a .NET 8 de Revit 2025+ **no obliga a recompilar
nada**. El riesgo real es doble y pequeño: (1) miembros de API renombrados/eliminados, (2)
cambios de comportamiento silenciosos. Ambos se contienen en `revit_compat.py` + una matriz de
pruebas de humo por versión (Parte 15).

### Fuera de alcance (explícito)

- Cálculo estructural / dimensionado de armadura (el usuario introduce diámetros y separaciones).
- Mallazo electrosoldado (`FabricArea`/`FabricSheet`) — fase futura.
- Postesado / tendones.
- Localización de la UI a idiomas distintos de ES/EN en esta iteración (infraestructura
  `nosa_utils.i18n` queda preparada).

---

## 02 · Auditoría del estado actual

### Mapa de módulos

| Archivo | Tamaño | Responsabilidad | Estado |
|---|---|---|---|
| `script.py` | 633 B | Entry point pyRevit → `launch_nosa_window(RebarAutomateWindow)` | OK |
| `lib/rebar_engine.py` | 68 KB | Geometría y cover; `RebarWrapper` (wrappers defensivos de `Rebar.CreateFromCurves`, Sets, FreeForm, shape); lookups `RebarBarType`/`RebarShape`/`RebarHookType`; `split_rebar_by_stock_length` (solapes). | Núcleo probado |
| `lib/column_rebar.py` | 123 KB | Pilares: eje, geometría de sección, distribución perimetral, estribos + zonas + horquillas, arranques acodados, empalmes por planta, columnas circulares. | Maduro |
| `lib/footing_rebar.py` | 92 KB | Zapatas: parrillas orto., mats como Set / como cadenas, U-bars perimetrales, armadura de piel, esperas (dowels), integración con topología. | Probado fuego real |
| `lib/floor_rebar.py` | 58 KB | Losas: armado por dirección con huecos, U-bars de borde, normal hacia material. Usa `slab_topology`. | Parcial |
| `lib/slab_topology.py` | 20 KB | Loops de cara, clasificación hueco/contorno, offset de polígono, intervalos de material por scanline. | OK |
| `lib/beam_rebar.py` | 20 KB | Vigas: eje, caras, barras long. sup/inf, estribos. **Sin cableado a la UI.** | Stub funcional |
| `lib/rebar_detailing.py` | 14 KB | Tags (`IndependentTag.Create`), dimensiones de estribos, secciones de detalle automáticas. | Sin verificar en vivo |
| `lib/rebar_preview.py` | 37 KB | Preview WPF puro-Python (sección y alzado), sin tocar el documento. | OK |
| `lib/ui.py` / `ui.xaml` | 86 / 43 KB | Ventana WPF. Pestañas: *Footings & Slabs*, *Columns*, *Beams* (vacía), *Walls* (vacía), *Detailing & Tools*. Flujo Configure→Generate→Select→Apply. `ExternalEvent` para ejecución. | Deuda: 2 pestañas vacías |

### Infraestructura compartida disponible (y hoy infrautilizada)

- **`nosa_utils/compat.py`** — Shims IronPython 2.7 / CPython 3. **Usar siempre.**
- **`nosa_utils/bootstrap.py`** — Cargador unificado (`load_module`, `ensure_lib`). Sustituye
  los `imp.load_source` dispersos.
- **`nosa_utils/revit_helpers.py`** — `get_id_value` / `element_id_from_int` / `coerce_element_id`
  ya cubren el corte 2024→2025 de `ElementId`. `collect_by_*`, `get/set_parameter_value`,
  `safe_transaction`.
- **`nosa_utils/param_element_ops.py`** — Lectura/escritura genérica de parámetros,
  `apply_param_batch`, `discover_param_specs`. Reutilizable para el writer de shared params.
- **`nosa_utils/base_window.py`** — `NOSAWindow` + `LoadConfig`/`SaveConfig` (JSON por plugin
  en `NOSA_Configs/_<key>.json`) + `ApplyTheme`.
- **`Data.panel/SharedParamManager`** — Herramienta hermana **solo de auditoría**: lee el `.txt`
  del proyecto, detecta huérfanos y conflictos de GUID. **No hay writer, ni fichero `.txt`
  propio de NOSA en el repo.**

### Huecos críticos (ordenados por impacto)

1. **Cero identidad en las barras.** Nada de `Mark`, `Partition`, capa, revisión ni marca de
   origen. Consecuencia: el usuario no puede seleccionar "lo que generó esta ejecución", ni
   deshacerlo, ni volver a etiquetarlo.
2. **Cero normativa.** `DEFAULT_COVER_MM = 40.0` constante única; factores de doblado/solape
   hardcoded o inexistentes.
3. **Cero shape codes.** La forma la deduce Revit; buena parte de los comentarios del código
   documentan peleas con `CreateFromCurves "Internal Error"` por no controlar la forma.
4. **Cero despiece / export.** No hay tabla de doblado ni BVBS.
5. **Multi-versión ad hoc.** Solo `ElementId` está cubierto; el resto de la API se usa a pelo.
6. **2 tipologías incompletas** (vigas cableada a medias, muros sin nada).

---

## 03 · Arquitectura objetivo

SOFiSTiK separa físicamente: binarios in-process · motor de cálculo fuera de proceso ·
contenido de fábrica inmutable · contenido de usuario editable · reglas como dato (JSON + Lua).
RebarAutomate no necesita proceso separado, pero sí las otras cuatro capas.

### Estructura de directorios objetivo

```
NOSA.extension/
├── lib/nosa_utils/
│   ├── revit_compat.py            # NUEVO · Parte 4 — única abstracción de API por versión
│   ├── shared_params.py           # NUEVO · Parte 5 — writer + binding del .txt NOSA
│   ├── standards.py               # NUEVO · Parte 6 — loader de perfiles de normativa
│   ├── rebar_catalog.py           # NUEVO · Parte 7 — loader del catálogo de formas
│   ├── compat.py  bootstrap.py  revit_helpers.py  param_element_ops.py   # ya existen
│   └── base_window.py  i18n.py  ...
│
├── data/                          # NUEVO · REGLAS COMO DATO (versionado en git, solo lectura en runtime)
│   ├── shared_parameters/
│   │   └── NOSA_SharedParameters.txt          # GUIDs FIJOS PARA SIEMPRE — Parte 5
│   ├── rebar_standards/
│   │   ├── _schema.json                       # json-schema del perfil
│   │   ├── EHE-08.json  EN-ISO-3766.json  BS-8666-2020.json
│   ├── shape_catalogs/
│   │   ├── en_iso_3766/ { options.json, 01_ISO_00.json, ... }
│   │   └── bs_8666_2020/ { options.json, ... }
│   └── content_manifest.json                  # versión de cada familia .rfa entregable
│
├── content/                       # NUEVO · CONTENIDO ENTREGABLE (.rfa) — Parte 13
│   ├── tags/       NOSA_Tag_Rebar.rfa  NOSA_Tag_Rebar_Spacing.rfa  NOSA_Tag_Rebar_Multi.rfa
│   ├── shapes/     NOSA_BendingDetail_Generic.rfa
│   └── titleblocks/ NOSA_TitleBlock_Rebar_A1.rfa
│
└── NOSA.tab/Structures.panel/Quantities.pulldown/RebarAutomate.pushbutton/
    ├── script.py
    └── lib/
        ├── rebar_engine.py  column_rebar.py  beam_rebar.py  footing_rebar.py
        ├── floor_rebar.py  slab_topology.py  wall_rebar.py   # wall_rebar NUEVO
        ├── rebar_detailing.py  rebar_preview.py
        ├── rebar_marking.py           # NUEVO · Parte 8 — numeración/dedup/marcado
        ├── rebar_shape_classifier.py  # NUEVO · Parte 7
        ├── rebar_schedule.py          # NUEVO · Parte 10 — BBS
        ├── rebar_export_bvbs.py       # NUEVO · Parte 10
        ├── rebar_batch.py             # NUEVO · Parte 8 — TransactionGroup + Batch_Id + rollback
        └── ui.py  ui.xaml

%APPDATA%/pyRevit/Extensions/NOSA.extension/NOSA_Configs/   # estado de usuario (NO en git)
├── _rebar_automate.json               # ya existe — estado de ventana
├── rebar_project.json                 # NUEVO — normativa activa, prefijos de marca del proyecto
└── rebar_standards/<code>.json         # NUEVO — overrides de usuario sobre los perfiles de data/
```

### Principio de dependencias

```
ui.py
  └─ rebar_batch  ──────────────┐
       ├─ <tipology>_rebar  ────┤
       │    └─ rebar_engine ────┤
       ├─ rebar_marking  ───────┤
       ├─ rebar_shape_classifier┤
       └─ rebar_detailing  ─────┤
                                ▼
         nosa_utils: revit_compat · shared_params · standards · rebar_catalog · compat
```

Los módulos de tipología nunca importan `ui`. `rebar_engine` nunca importa un módulo de
tipología. Toda función de generación recibe un `standard` (dict del perfil de normativa) y un
`ctx` (contexto de ejecución) como parámetros — no leen constantes globales.

### Contrato transversal: el objeto `ctx`

Un `dict` (o dataclass ligera compatible con IPy2) que acompaña a toda ejecución y a toda barra
creada:

```python
ctx = {
  "doc": doc,
  "standard": standards.load("EHE-08"),      # perfil resuelto (fábrica + override usuario)
  "batch_id": "RA-20260827-153012-a1b2",     # id único de esta ejecución
  "generator_version": "1.0.0",
  "host": host_element,
  "host_mark": "Z-12",
  "compat": revit_compat.api(),              # fachada de API por versión
}
```

---

## 04 · Capa de compatibilidad Revit 2024–2027

`nosa_utils/revit_compat.py` — la única parte del código que conoce diferencias de versión.

### Detección de versión

```python
def revit_year(app_or_doc):
    # app.VersionNumber devuelve "2024".."2027" en todas las versiones objetivo
    app = getattr(app_or_doc, "Application", app_or_doc)
    return int(app.VersionNumber)

YEAR = revit_year(__revit__)          # pyRevit expone __revit__
IS_2025_PLUS = YEAR >= 2025
```

### Deltas de API conocidos y cómo se abstraen

| Área | 2024 | 2025 – 2027 | Fachada en `revit_compat` |
|---|---|---|---|
| `ElementId` → entero | `.IntegerValue` (Int32) | `.Value` (Int64); `.IntegerValue` eliminado en 2025 | **[OK ya resuelto]** `revit_helpers.get_id_value()`. Reexportar desde `revit_compat`. |
| `ElementId(int)` | `ElementId(Int32)` | requiere `ElementId(Int64(x))` | **[OK ya resuelto]** `element_id_from_int()` |
| Runtime .NET | Framework 4.8 | .NET 8 | No afecta a Python puro. `revit_compat.DOTNET = 8 if IS_2025_PLUS else 48` solo para logging. |
| Unidades | `ForgeTypeId` / `UnitTypeId` (desde 2022) | igual | `compat.to_internal(mm)` / `compat.from_internal(ft)` vía `UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Millimeters)`. **[DECISIÓN 6.B]** mantener el factor fijo `304.8` como fallback o migrar todo a `UnitUtils`. |
| `Rebar.CreateFromCurves` | firma estable | firma estable | **[OK confirmado no-hook en 2024, Phase 4]**. Envolver igualmente en `compat.create_rebar_from_curves(...)`. |
| `IndependentTag.Create` | overload 2022+ (doc, viewId, ref, addLeader, tagMode, orient, point) | igual; en 2024+ existe overload con `Reference`-múltiple | `compat.create_tag(...)` — usa siempre el overload 2022+. |
| `Rebar.GetCenterlineCurves` | (adjust, suppressHooks, suppressBendRadius, MultiplanarOption, barIndex) | igual (verificar 2027) | `compat.centerline_curves(rebar, ...)` |
| `RebarBarType` diámetro | `BarModelDiameter` / `BarNominalDiameter` | igual; `BarDiameter` obsoleto de largo | `compat.bar_diameter(bar_type)` — prueba `BarModelDiameter` → `BarNominalDiameter` → `BarDiameter`. |
| `BuiltInParameter` de rebar | set completo | verificar renombrados en 2025 (limpieza de API) | **[RIESGO API]** `compat.bip("REBAR_...")` con tabla de alias por año. |
| `FilteredElementCollector` + `WhereElementIsElementType` | estable | estable | Sin cambio; usar `revit_helpers.collect_by_class`. |
| Familias / Shared params API | `app.OpenSharedParameterFile`, `Definitions.Create`, `BindingMap` | igual | `shared_params.py` lo usa directamente; estable en las 4 versiones. |
| `Category.Id` vs `BuiltInCategory` | `ElementId(BuiltInCategory)` | preferir `Category.GetCategory` / `ElementId(Int64)` | `compat.category_id(bic)` |
| pyRevit engine | IPy 2.7 (CPy3 opcional) | IPy 2.7 / CPy3; 2027 por confirmar | Resuelto por `nosa_utils.compat`. Nada específico de Revit. |

> **[RIESGO API — obligatorio validar en beta]** Las columnas "2025–2027" son la mejor
> información disponible a fecha del blueprint, no una garantía. Antes de publicar soporte para
> cada versión nueva:
> 1. Ejecutar la matriz de humo de la Parte 15 en esa versión.
> 2. Revisar el *API Changes* oficial del SDK filtrando por `Autodesk.Revit.DB.Structure`,
>    `ElementId`, `IndependentTag`, `Parameter`.
> 3. Cualquier diferencia nueva se resuelve **solo** añadiendo una rama en `revit_compat.py`;
>    jamás un `if year ==` disperso por los módulos.

### Forma del módulo

```python
# nosa_utils/revit_compat.py
class _Api2024(_ApiBase): ...
class _Api2025Plus(_ApiBase): ...   # hereda de 2024, sobrescribe solo lo que cambia

def api():
    return _Api2025Plus() if IS_2025_PLUS else _Api2024()

# Uso en cualquier módulo:
c = ctx["compat"]
dia_mm = c.from_internal(c.bar_diameter(bt))
rebar  = c.create_rebar_from_curves(doc, style, bt, None, None, host, normal, curves, ...)
```

La fachada expone **métodos con semántica de dominio** (`bar_diameter`, `create_tag`), no
wrappers 1:1 de la API. Así un cambio de firma en Revit 2027 se absorbe sin tocar los llamantes.

---

## 05 · Sistema de Shared Parameters

SOFiSTiK **no distribuye** un `.txt` de shared parameters: inyecta los parámetros por API con
GUIDs compilados. NOSA hace lo mismo pero con un `.txt` versionado en git como fuente única de
los GUIDs — así `SharedParamManager` (la herramienta de auditoría que ya existe) puede validarlo,
y el usuario nunca lo edita.

### Reglas del sistema

- **Los GUIDs de abajo son DEFINITIVOS.** Nunca se regeneran. Si un parámetro se renombra, se
  conserva su GUID. Si se retira, su GUID queda "quemado" y no se reutiliza.
- `data/shared_parameters/NOSA_SharedParameters.txt` es la fuente. `shared_params.py` lo lee al
  arrancar RebarAutomate y garantiza el binding.
- El plugin **no** cambia el *Shared Parameter File* configurado en el proyecto del usuario: usa
  la API de `Definition` a partir de su propio `DefinitionFile` temporal, o inserta las
  definiciones en el fichero del usuario si éste lo autoriza (preferencia en
  `rebar_project.json`). **[DECISIÓN 5.A]**
- Grupo del parámetro en el `.txt` (columna `GROUP`) = agrupación funcional. El *parameter group*
  de Revit (dónde aparece en Propiedades) se fija en el binding vía `GroupTypeId` (2024+) — todos
  bajo *Datos* / *Construcción*.

### Categorías a las que se enlaza

- **`OST_Rebar`** — barra / conjunto de barras — *instancia*
- **`OST_AreaRein`** — armadura de área
- **`OST_PathRein`** — armadura de trayectoria
- **`OST_FabricAreas` / `OST_FabricReinforcement`** — mallazo (preparado, sin uso aún)
- **`OST_RebarTags` / `OST_MultiReferenceAnnotations`** — solo los parámetros `NOSA_Rebar_Tag_*`
  y los de lectura de marca

### Grupo `NOSA_Rebar_Identity` — identidad y organización

| Parámetro | GUID | Tipo | I/T | Rol |
|---|---|---|---|---|
| `NOSA_Rebar_Mark` | `b0a7083b-fab5-43da-a8d6-be2dbba2b310` | Text | INST | Marca de posición visible (p. ej. `Z12-04`) |
| `NOSA_Rebar_Mark_Number` | `f743bc96-c90e-419b-a1fd-978eeb07fa78` | Integer | INST | Nº de posición puro, para ordenar |
| `NOSA_Rebar_Mark_Prefix` | `bdf4e7c4-427a-4ba1-ac7a-d8311b40da70` | Text | INST | Prefijo (marca de host / tipología) |
| `NOSA_Rebar_Mark_Suffix` | `0dc98d97-3440-4275-a91b-68f26dc4fe2b` | Text | INST | Sufijo opcional |
| `NOSA_Rebar_Host_Mark` | `b924bef3-194e-4cab-adbf-17d45483fa25` | Text | INST | Marca del elemento hospedador |
| `NOSA_Rebar_Host_Id` | `6dfa3bff-84ce-4b33-b549-64e28ece316e` | Text | INST | `ElementId` del host (string, multi-versión) |
| `NOSA_Rebar_Layer` | `d06c7f54-06e1-43b2-b577-af951d3c0e85` | Text | INST | Capa de armado — taxonomía en Parte 8 |
| `NOSA_Rebar_Group` | `924457d4-36b3-4cfa-9e43-ecd50bba68d5` | Text | INST | Agrupación libre (paquete de plano) |
| `NOSA_Rebar_Assembly` | `574f41d2-9fcd-4b87-8e15-f020f4f7e7b6` | Text | INST | Conjunto / assembly |
| `NOSA_Rebar_Position_In_Host` | `da6d9efa-635d-49f1-a18c-c1f4d5d90c30` | Text | INST | Posición semántica: `bottom-X`, `stirrup`, `dowel`… |

### Grupo `NOSA_Rebar_Shape` — forma normalizada

| Parámetro | GUID | Tipo | I/T | Rol |
|---|---|---|---|---|
| `NOSA_Rebar_Shape_Code` | `3af513b3-360f-4184-ac71-15352196e0e8` | Text | INST | Código de forma (`21`, `51`, `99`…) según catálogo |
| `NOSA_Rebar_Shape_Catalog` | `93e114b7-61e3-4b55-9999-123047a052cc` | Text | INST | Catálogo activo (`en_iso_3766`, `bs_8666_2020`) |
| `NOSA_Rebar_Shape_Params` | `9d6f4403-dfec-4e42-8874-f08a0a1a6254` | Text | INST | `A=1200;B=300;R=64` para la tabla de doblado |
| `NOSA_Rebar_Bend_Diameter` | `834af015-5907-4db6-a9ce-49aae7157710` | Length | INST | Diámetro de mandril usado |
| `NOSA_Rebar_Hook_Start` | `e6296fa2-4b65-4255-9408-88f1039def22` | Text | INST | Gancho inicio: `none`/`90`/`135`/`180` |
| `NOSA_Rebar_Hook_End` | `2650ae68-68b6-4e08-88cf-8ab318fa8d17` | Text | INST | Gancho fin |
| `NOSA_Rebar_Is_Variable` | `d84c3a95-a9d3-4ebf-b30f-77bd21c89e64` | Yes/No | INST | Barra de longitud variable (mat en cuña, etc.) |
| `NOSA_Rebar_Segment_Count` | `24fb1e29-fef1-46da-841f-f5fdcc8ab8d5` | Integer | INST | Nº de tramos rectos |

### Grupo `NOSA_Rebar_Status` — ciclo de vida y trazabilidad

| Parámetro | GUID | Tipo | I/T | Rol |
|---|---|---|---|---|
| `NOSA_Rebar_Created_By_NOSA` | `7fcd3b49-56f5-4687-8095-67f153ee2d02` | Yes/No | INST | **Marca de origen** — equivale a `SOFiSTiK_Identifier` |
| `NOSA_Rebar_Batch_Id` | `0233dc14-11d9-44e1-95b7-e82662da4759` | Text | INST | Id de la ejecución que la creó — selección/rollback por lote |
| `NOSA_Rebar_Generator_Version` | `9cfdaebb-465e-4c95-b342-c81484917a4e` | Text | INST | Versión del plugin |
| `NOSA_Rebar_Standard_Code` | `5711215e-99dd-4fcc-a4d6-2f1ab4a27516` | Text | INST | Perfil de normativa activo al crearla |
| `NOSA_Rebar_Finalized` | `4a687ef1-4e0a-4f62-8a80-6e2c98b11e9c` | Yes/No | INST | "No regenerar" — equivale a `SOFiSTiK_Finalized` |
| `NOSA_Rebar_Revision` | `77bab632-d23d-4a91-ae17-03eed8c4412b` | Text | INST | Revisión |
| `NOSA_Rebar_Issue_Status` | `7e9822da-b3b4-406c-8d59-77b1c79af1df` | Text | INST | Estado de emisión (*Para construcción*, *Información*…) |
| `NOSA_Rebar_Last_Modified` | `cca44491-979b-4d1d-b12d-5f41a8e151ec` | Text | INST | ISO-8601 de la última acción del plugin sobre la barra |

### Grupo `NOSA_Rebar_Fabrication` — fabricación y despiece

| Parámetro | GUID | Tipo | I/T | Rol |
|---|---|---|---|---|
| `NOSA_Rebar_Steel_Grade` | `49266137-bb93-48bb-8473-1cd1b14bef3a` | Text | TYPE | `B500SD` / `B500S` … |
| `NOSA_Rebar_Mass_Per_Length` | `e8842236-4817-44c4-a658-bfb3cbee40e4` | Number | TYPE | kg/m del diámetro |
| `NOSA_Rebar_Total_Length` | `5091b739-01c2-48e0-a212-4f181cfb85e4` | Length | INST | Longitud total de la posición (×nº barras) |
| `NOSA_Rebar_Cut_Length` | `bafe48b8-787a-4bf8-90f4-ab0a5c39224d` | Length | INST | Longitud de corte de una barra |
| `NOSA_Rebar_Coupler_Start` | `c82adfee-18de-4d2d-ac96-7f45124fa11c` | Text | INST | Manguito en inicio |
| `NOSA_Rebar_Coupler_End` | `490f6e0f-fe07-44b7-9828-a674e211c799` | Text | INST | Manguito en fin |
| `NOSA_Rebar_EndTreatment_Start` | `caca5c09-7644-443e-bab1-07d48a4e701d` | Text | INST | Tratamiento de extremo inicio |
| `NOSA_Rebar_EndTreatment_End` | `c4fb884e-26f8-40e8-aada-888d59d95603` | Text | INST | Tratamiento de extremo fin |
| `NOSA_Rebar_Export_Id` | `4669bb75-74d7-456b-87d0-791cd3c4382d` | Text | INST | Id estable para BVBS / Excel |
| `NOSA_Rebar_BVBS_Line` | `f2fb2f85-aa1c-40b1-bf29-ab1fc59357b2` | Text | INST | Cadena BVBS pre-generada (cache) |

### Grupo `NOSA_Rebar_Detailing` — anotación

| Parámetro | GUID | Tipo | I/T | Rol |
|---|---|---|---|---|
| `NOSA_Rebar_Tag_Offset_X` | `1fa47447-1b45-4516-8a07-a6590a69b83b` | Length | INST | Desplazamiento de etiqueta X |
| `NOSA_Rebar_Tag_Offset_Y` | `245b5c8c-1813-4935-8c27-8d89df2d48f3` | Length | INST | Desplazamiento de etiqueta Y |
| `NOSA_Rebar_Detail_Section_Id` | `2abdcbaa-8f6b-48e1-8607-26d6efc679d0` | Text | INST | Id de la sección de detalle asociada |
| `NOSA_Rebar_Show_In_Schedule` | `ff5b23e1-7668-48ad-b600-71b754a212bb` | Yes/No | INST | Incluir en despiece |

### `data/shared_parameters/NOSA_SharedParameters.txt` (formato)

```
# This is a Revit shared parameter file.
# Do not edit manually. Generated from the blueprint. GUIDs are FINAL.
*META	VERSION	MINVERSION
META	2	1
*GROUP	ID	NAME
GROUP	1	NOSA_Rebar_Identity
GROUP	2	NOSA_Rebar_Shape
GROUP	3	NOSA_Rebar_Status
GROUP	4	NOSA_Rebar_Fabrication
GROUP	5	NOSA_Rebar_Detailing
*PARAM	GUID	NAME	DATATYPE	DATACATEGORY	GROUP	VISIBLE	DESCRIPTION	USERMODIFIABLE	HIDEWHENNOVALUE
PARAM	b0a7083b-fab5-43da-a8d6-be2dbba2b310	NOSA_Rebar_Mark	TEXT		1	1	Marca de posicion NOSA	1	0
PARAM	f743bc96-c90e-419b-a1fd-978eeb07fa78	NOSA_Rebar_Mark_Number	INTEGER		1	1		1	0
PARAM	7fcd3b49-56f5-4687-8095-67f153ee2d02	NOSA_Rebar_Created_By_NOSA	YESNO		3	1		0	0
# ... resto de PARAM según las tablas de arriba (usar DATATYPE: TEXT / INTEGER / YESNO / NUMBER / LENGTH)
```

### `shared_params.py` — API del módulo

```python
def ensure_bound(doc, categories=DEFAULT_CATS, insert_into_user_file=False):
    """Idempotente. Al arrancar RebarAutomate:
       1. abre/crea el DefinitionFile desde data/shared_parameters/NOSA_SharedParameters.txt
       2. para cada PARAM del .txt que no esté ya bound a `categories`, crea el
          InstanceBinding/TypeBinding con GroupTypeId.Data (o .Construction).
       3. NUNCA re-crea un binding existente (evita conflictos de GUID).
       Devuelve un informe: {bound:[...], already:[...], skipped:[...], errors:[...]}"""

def write(elem, guid_or_name, value):        # set robusto por GUID (multi-versión)
def read(elem, guid_or_name, default=None):
def stamp_provenance(elem, ctx):             # Created_By_NOSA=1, Batch_Id, Generator_Version,
                                             # Standard_Code, Last_Modified — en TODA barra creada
```

**Cuándo se escriben:** `stamp_provenance` se llama dentro del mismo `Transaction` que crea
cada barra (en `rebar_batch`, no en los módulos de tipología). Marca, capa y forma se escriben
en una segunda pasada tras la numeración (Parte 8). Los de fabricación, tras el despiece
(Parte 10).

---

## 06 · Perfiles de normativa (EHE / ISO / BS)

SOFiSTiK selecciona la normativa en runtime y ésta gobierna *dos* conjuntos de reglas-dato: el
catálogo de formas (Parte 7) y el formato de despiece (Parte 10). NOSA añade un tercero: los
**valores normativos de proyecto** (recubrimientos, mandriles, solapes, anclajes, separaciones).
Todo en un JSON por normativa.

> **Nota sobre España:** SOFiSTiK no trae catálogo EHE; para España usa EN ISO 3766. NOSA hace
> lo mismo: el perfil `EHE-08.json` apunta a `shape_catalog: "en_iso_3766"` pero lleva sus
> propios recubrimientos, mandriles y anclajes según EHE-08 (y ruta a Código Estructural cuando
> se añada `CE-21.json`).

### `data/rebar_standards/EHE-08.json`

```json
{
  "code": "EHE-08",
  "display_name": "EHE-08 (España)",
  "revision": "2026-08",
  "shape_catalog": "en_iso_3766",
  "units": "mm",
  "steel": {
    "default_grade": "B500SD",
    "grades": {
      "B500S":  { "fyk_mpa": 500, "ductility": "S"  },
      "B500SD": { "fyk_mpa": 500, "ductility": "SD" }
    },
    "bar_diameters_mm": [6, 8, 10, 12, 16, 20, 25, 32, 40],
    "mass_per_length_kg_m": { "6":0.222,"8":0.395,"10":0.617,"12":0.888,"16":1.578,
                              "20":2.466,"25":3.854,"32":6.313,"40":9.865 }
  },

  "cover_mm": {
    "_comment": "recubrimiento nominal por elemento y clase de exposición; el host manda si trae Rebar Cover nativo",
    "by_element": { "foundation": 70, "column": 35, "beam": 30, "slab": 25, "wall": 30, "pile_cap": 75 },
    "by_exposure": { "IIa": 25, "IIb": 30, "IIIa": 35, "IIIb": 40, "IIIc": 45, "IV": 45, "Qa": 40 }
  },

  "bend": {
    "_comment": "diametro de mandril = factor * diametro de barra",
    "mandrel_factor": [
      { "bar_max_mm": 16, "stirrup_factor": 4,  "bar_factor": 4  },
      { "bar_max_mm": 25, "stirrup_factor": 6,  "bar_factor": 7  },
      { "bar_max_mm": 40, "stirrup_factor": 8,  "bar_factor": 10 }
    ],
    "min_straight_after_bend_factor": 5
  },

  "hook": {
    "standard_bend_deg": 90,
    "stirrup_bend_deg": 135,
    "seismic_stirrup_bend_deg": 135,
    "hook_extension_factor": { "90": 12, "135": 10, "180": 4 },
    "min_hook_extension_mm": 70
  },

  "anchorage": {
    "mode": "factor",
    "basic_length_factor": { "good_bond": 40, "poor_bond": 57 },
    "min_factor": 10, "min_mm": 150,
    "compression_factor": 0.7
  },

  "lap": {
    "mode": "factor",
    "tension_factor": { "pct_lapped_le_25": 40, "pct_lapped_gt_50": 57 },
    "compression_factor": 40,
    "min_mm": 200,
    "stagger_offset_mm": 25
  },

  "stirrups": {
    "default_spacing_mm": 200,
    "min_spacing_mm": 75,
    "max_spacing_beam_factor_h": 0.75,
    "max_spacing_column_min": { "factor_min_dim": 1.0, "factor_bar_dia": 12, "abs_mm": 300 },
    "confinement_zone_factor_h": 2.0
  },

  "stock_length_mm": 12000,

  "marking": {
    "mark_format": "{host_mark}-{number:02d}",
    "number_scope": "per_host",
    "dedup_tolerance_mm": 2.0,
    "layer_names": {
      "bottom_x":"Inf-X","bottom_y":"Inf-Y","top_x":"Sup-X","top_y":"Sup-Y",
      "long_top":"Long-Sup","long_bot":"Long-Inf","skin":"Piel",
      "stirrup":"Cerco","crosstie":"Horquilla","dowel":"Espera",
      "edge_u":"Refuerzo-Borde"
    }
  },

  "schedule": {
    "columns": ["mark","count","diameter","shape_code","A","B","C","D","E","R",
                "total_length_mm","unit_mass_kg_m","total_mass_kg"],
    "length_precision_mm": 10,
    "round_cut_length_to_mm": 10,
    "group_by": ["host_mark","layer"]
  }
}
```

`EN-ISO-3766.json` y `BS-8666-2020.json` tienen la misma estructura con valores propios
(BS 8666: mandriles 4Ø ≤16 / 7Ø >16, ganchos según tabla, `shape_catalog: "bs_8666_2020"`).

### Resolución y overrides

```python
# nosa_utils/standards.py
def load(code):
    base = json_load(f"data/rebar_standards/{code}.json")
    user = json_load(f"NOSA_Configs/rebar_standards/{code}.json", optional=True)
    return deep_merge(base, user)      # user pisa clave a clave; validado contra _schema.json

def list_available(): ...             # para el desplegable de la UI
def cover_for(std, element_kind, exposure=None): ...
def mandrel_diameter_mm(std, bar_dia_mm, is_stirrup): ...
def lap_length_mm(std, bar_dia_mm, in_compression=False, pct_lapped=25): ...
def anchorage_length_mm(std, bar_dia_mm, good_bond=True, in_compression=False): ...
def hook_extension_mm(std, bar_dia_mm, angle_deg): ...
```

> **[DECISIÓN 6.A — perfiles iniciales]** Propuesto: shippear `EHE-08.json`,
> `EN-ISO-3766.json`, `BS-8666-2020.json`. ¿Añadimos ya `CE-21.json` (Código Estructural,
> España 2021) y `EC2.json` (Eurocódigo 2 genérico)?

### Migración del código existente

| Hoy (hardcoded) | Pasa a |
|---|---|
| `rebar_engine.DEFAULT_COVER_MM = 40.0` | fallback último; prioridad: cover nativo host → `standards.cover_for(std, kind, exposure)` → 40 |
| `column_rebar.default_lap_length_mm(dia, multiplier=40.0)` | `standards.lap_length_mm(std, dia, ...)` |
| `footing_rebar.default_anchorage_length_mm(dia, multiplier=40.0)` | `standards.anchorage_length_mm(std, dia, ...)` |
| `column_rebar.default_joint_zone_length_mm(...)` | `std.stirrups.confinement_zone_factor_h` |
| `*_rebar: stock_length_mm=12000` en firmas | default desde `std.stock_length_mm` |
| `get_hook_type_by_angle(doc, 90.0)` | ángulo desde `std.hook.standard_bend_deg` / `stirrup_bend_deg` |

Las firmas de las funciones de tipología ganan un primer parámetro `std` (o lo toman de
`ctx["standard"]`). Los `default_*_mm` se mantienen como envoltorio de compatibilidad que
delega en `standards`, para no romper llamantes de golpe.

---

## 07 · Catálogo de formas y clasificador

SOFiSTiK define cada forma como un JSON de *constraints* geométricos por segmento (`geom_type`
0=recto/1=doblez/2=transición, `angle_min/max`, `relation` entre segmentos) y un mapeo de
parámetros (`displayed_name` → `segment_id` → `calculation_type`). NOSA copia el **esquema**,
no los datos.

### `data/shape_catalogs/en_iso_3766/options.json`

```json
{
  "catalog_id": "en_iso_3766",
  "display_name": "EN ISO 3766:2003",
  "default_shape_code": "99",
  "not_bent_code": "00",
  "precision_decimals": 0,
  "include_hooks_in_shape_definition": false,
  "bending_detail_family": "NOSA_BendingDetail_Generic"
}
```

### `data/shape_catalogs/en_iso_3766/06_ISO_21.json` (forma en L / patilla)

```json
{
  "shape_code": "21",
  "segments": [
    { "id": 0, "geom_type": 0 },
    { "id": 1, "geom_type": 1, "angle_min": 0, "angle_max": 90, "angle_incl": false },
    { "id": 2, "geom_type": 0 }
  ],
  "relations": [],
  "parameters": [
    { "name": "A", "segment_id": 0, "calc": "segment_length" },
    { "name": "B", "segment_id": 2, "calc": "segment_length" }
  ],
  "hook_start": null, "hook_end": null
}
```

### `calc` — enum de medición (equivalente a `calculation_type` de SOFiSTiK)

- `segment_length` — longitud del tramo recto (10)
- `projection` — proyección del tramo sobre un eje (12)
- `radius` — radio de doblado (20)
- `point_to_point` — distancia entre puntos de dos tramos (23)
- `helix_diameter` / `helix_pitch` / `helix_length` — geometría de hélice (40/41/43)

### `rebar_shape_classifier.py` — API

```python
def classify(rebar, catalog, std, compat):
    """1. compat.centerline_curves(rebar, suppressHooks=False) -> lista de curvas
       2. reduce a poligonal: tramos rectos + angulos de doblez + radios
       3. detecta ganchos en extremos (angulo > 135 sobre tramo corto)
       4. matchea contra cada forma del catalogo:
            - mismo nº de segmentos rectos
            - cada doblez dentro de [angle_min, angle_max]
            - relations satisfechas (tolerancia std.marking.dedup_tolerance_mm)
       5. si matchea: devuelve (shape_code, {A:.., B:.., R:..}, hook_start, hook_end)
          si no:      devuelve ('99', medidas_libres, ...)   # forma a medida
       6. barra recta sin dobleces -> '00'  (not_bent)
    Puro: no abre transaccion, no toca el documento."""

def stamp(rebar, result, ctx):     # escribe Shape_Code, Shape_Catalog, Shape_Params,
                                    # Hook_Start/End, Segment_Count, Bend_Diameter
```

> **[NOTA F0 → F4]** `compat.centerline_curves` (Parte 04) por defecto usa
> `MultiplanarOption.IncludeOnlyPlanarCurves` — correcto para toda forma recta/plana que el
> motor genera hoy. Para las formas genuinamente 3D de este catálogo (zuncho helicoidal de
> pilar circular, shape code `77`) hay que pasar `multiplanar_option` explícito al llamar a
> `compat.centerline_curves` desde `classify()`, o la geometría fuera de plano de la hélice se
> descarta en silencio. Queda anotado en el propio `revit_compat.py`.

**Doble uso del clasificador:**
1. **Post-proceso**: tras generar, clasifica y sella cada barra para el despiece.
2. **Pre-validación**: antes de llamar a `Rebar.CreateFromCurves`, comprobar que la poligonal
   propuesta corresponde a una forma del catálogo con radios válidos según `std.bend` — esto
   ataca de raíz los `"Internal Error"` documentados en los comentarios de `column_rebar`/
   `footing_rebar`.

### Alcance inicial de catálogos

- **EN ISO 3766**: formas `00, 11, 12, 13, 15, 21, 25, 26, 31, 33, 41, 44, 46, 67, 75, 95, 96,
  98, 99` — cubre zapatas, pilares, vigas y losas del alcance actual.
- **BS 8666:2020**: `00, 11, 12, 13, 14, 15, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33,
  34, 35, 36, 41, 44, 46, 47, 48, 51, 63, 67, 75, 98, 99`.
- SSHV/SANS/DIN: fuera de alcance de esta iteración.

> **[DECISIÓN 7.A]** Los croquis de cada forma en el despiece: ¿(a) una única familia
> `NOSA_BendingDetail_Generic.rfa` con etiquetas de cotas paramétricas colocadas por código, o
> (b) el *Bending Detail* nativo de Revit? Recomendación: (b) para v1, (a) si (b) no da la
> calidad necesaria.

---

## 08 · Motor de numeración y marcado

SOFiSTiK abandonó el `Mark` nativo de Revit en 2025.0 ("Use SOFiSTiK_Mark instead of Revit Mark
parameter") porque colisiona entre categorías y no sobrevive a regeneraciones. NOSA hace lo
mismo: `NOSA_Rebar_Mark` propia, controlada por el plugin.

### Deduplicación (barras "iguales" = misma posición)

Dos barras comparten posición (y por tanto marca) si, dentro de `std.marking.dedup_tolerance_mm`:
- mismo `RebarBarType` (diámetro),
- misma forma normalizada (`Shape_Code` + parámetros `A,B,C…` redondeados),
- mismos ganchos,
- mismo `NOSA_Rebar_Layer` y mismo host (según `number_scope`).

La longitud de una barra *variable* (`Is_Variable=1`) nunca deduplica: cada una es su propia
posición o se agrupa como "marca total" con longitud media + rango.

### Formato de marca

```
std.marking.mark_format   = "{host_mark}-{number:02d}"      # EHE: Z12-04
std.marking.number_scope  = "per_host" | "per_project" | "per_view"
# tokens disponibles: {host_mark} {host_kind} {layer} {number} {number:0Nd} {diameter} {prefix}
```

### Taxonomía de capas (`NOSA_Rebar_Layer`)

Los generadores etiquetan cada barra con una **clave interna estable** (`bottom_x`, `stirrup`,
`dowel`…); `rebar_marking` la traduce al nombre visible vía `std.marking.layer_names`.

| Tipología | Claves de capa |
|---|---|
| Zapata / losa | `bottom_x · bottom_y · top_x · top_y · edge_u · skin · dowel` |
| Pilar | `long_corner · long_face · stirrup · crosstie · starter · lap` |
| Viga | `long_top · long_bot · long_skin · stirrup · stirrup_confine` |
| Muro | `vert_face1 · vert_face2 · horiz_face1 · horiz_face2 · tie · edge` |

### `rebar_batch.py` — orquestación de una ejecución

```python
class RebarBatch:
    def __init__(self, doc, standard, generator_version):
        self.ctx = make_ctx(doc, standard, generator_version)   # genera batch_id

    def run(self, hosts, plan):
        """1. TransactionGroup("NOSA RebarAutomate — {batch_id}")
           2. por host:
                Transaction: generar curvas (modulo tipologia) -> crear Rebar/Sets
                             stamp_provenance() en cada barra creada
           3. Transaction: rebar_shape_classifier.classify+stamp para TODO el lote
           4. Transaction: rebar_marking.assign  (dedup + marca + capa + Total_Length)
           5. (opcional) rebar_detailing: tags + dimensiones
           6. TransactionGroup.Assimilate()
           Devuelve BatchResult{created:[ids], skipped:[...], errors:[...], batch_id}"""

    @staticmethod
    def select_batch(doc, batch_id):        # FilteredElementCollector + filtro por NOSA_Rebar_Batch_Id
    @staticmethod
    def delete_batch(doc, batch_id):        # "deshacer ejecucion" — respeta Finalized=1
    @staticmethod
    def list_batches(doc):                  # para el gestor de lotes de la UI
```

**Por qué esto es la fase 1:** Con solo `Identity` + `Status` + `rebar_batch`, el usuario ya
gana: seleccionar todo lo de una ejecución, borrarla limpia, re-etiquetar, y ver de un vistazo
qué armado es del plugin y con qué versión/normativa se hizo. Es el mayor salto de valor con
el menor riesgo.

---

## 09 · Subsistema de detallado

### Familias de tag propias [NUEVO contenido]

Como SOFiSTiK (`Annotation_RebarSet`, `SOFiSTiK_Annotation_Table_RebarSet`): la *lógica de
colocación* vive en código; el *dibujo del rótulo* en familias `.rfa` de categoría
`OST_RebarTags` que leen los shared params.

| Familia | Lee | Uso |
|---|---|---|
| `NOSA_Tag_Rebar.rfa` | `Mark`, Ø, forma | rótulo de una posición |
| `NOSA_Tag_Rebar_Spacing.rfa` | `Mark`, Ø, "cØ200", nº | rótulo de conjunto con separación |
| `NOSA_Tag_Rebar_Multi.rfa` | `Mark` ×N | anotación multi-referencia (MRA) |

### Ampliaciones a `rebar_detailing.py`

- `create_rebar_tags(...)` — **[OK existe]** — pasar `tag_type_id` de la familia NOSA; leer
  offset de `NOSA_Rebar_Tag_Offset_*`.
- `create_multi_rebar_annotation(view, rebars)` — **[NUEVO]** — `MultiReferenceAnnotation.Create`;
  el botón `BtnAutoMRA` de la UI ya existe y hoy no hace nada.
- `create_stirrup_dimension(...)` — **[OK existe]** — verificar en vivo (`MEDIUM` confidence).
  Calcular `dim_line` desde el eje del host, no pedirla al llamante.
- `create_rebar_detail_section(...)` — **[RIESGO: el punto menos fiable del plugin]** — mantener
  estilo defensivo (devuelve `None`, no lanza). Añadir preset por tipología (2 secciones
  ortogonales para zapata; 1 transversal + 1 long. para viga/pilar).
- `tag_rebar_set_along_run(...)` — **[NUEVO]** — un solo rótulo + acotado de la serie para un
  `Rebar` con `ShapeDrivenAccessor`.

### Vista de croquis de doblado

Para cada posición única del despiece, colocar en una *drafting view* (o usar el Bending Detail
nativo — Decisión 7.A) el croquis acotado con `A,B,C,R` de `NOSA_Rebar_Shape_Params`. Alimenta
la columna gráfica de la tabla de la Parte 10.

---

## 10 · Despiece y exportación a fabricación

### Tabla de despiece (Bar Bending Schedule)

SOFiSTiK genera la tabla en un proceso aparte con plantillas `.docx` y `units.json` por
normativa. NOSA, más simple:

1. **Fuente de datos**: recolectar todas las `Rebar` con `NOSA_Rebar_Created_By_NOSA = 1` y
   `Show_In_Schedule = 1`.
2. **Agrupar** por `std.schedule.group_by` (host + capa), luego por marca.
3. **Columnas**: de `std.schedule.columns`. Longitud de corte = suma de tramos rectos + ganchos
   − descuentos de doblado (según `std.bend`) redondeada a `round_cut_length_to_mm`.
4. **Salidas**:
   - **[v1]** *Schedule* nativo de Revit sobre `OST_Rebar` con los shared params como campos
     (cero dependencias, se coloca en plano).
   - **[v1]** Export CSV / XLSX (vía `openpyxl` si el engine CPython lo permite, o CSV puro
     para IronPython).
   - **[v2]** Tabla gráfica en una *drafting view* con croquis (familia `NOSA_Schedule_Row`).

> **[DECISIÓN 10.A]** ¿La tabla oficial de obra sale de (a) un *Schedule* nativo de Revit
> maquetado, o (b) un export a Excel con plantilla de la oficina? Recomendación: (a) para v1
> porque vive en el plano y se actualiza solo; (b) como export paralelo.

### Exportación BVBS [NUEVO]

BVBS (*Bundesvereinigung Bausoftware*) es el formato ASCII estándar que consumen las
dobladoras/cizallas de ferralla — es lo que hace `sofistik.model.cad.bvbs_rc.dll`. Formato por
barra: bloques `BF2D@`/`BF3D@` con sub-campos `H` (cabecera: proyecto, plano, marca, nº, Ø,
longitud, calidad), `G` (geometría: pares tramo/ángulo), `C` (checksum), terminador `@`.

```python
# rebar_export_bvbs.py
def bar_to_bvbs(rebar, ctx):
    """Construye la linea BVBS 2D desde:
       - cabecera: rebar_project.json (proyecto, plano) + NOSA_Rebar_Mark, _Number,
         diametro (compat.bar_diameter), NOSA_Rebar_Steel_Grade, NOSA_Rebar_Total_Length
       - geometria: tramos+angulos de rebar_shape_classifier (ya calculados)
       - checksum modulo segun spec BVBS
       Cachea el resultado en NOSA_Rebar_BVBS_Line."""

def export_batch(doc, batch_id_or_selection, out_path): ...   # .abs / .txt
```

**Prerrequisitos BVBS:** BVBS necesita geometría de tramos y ángulos fiable → depende de
**Parte 7** (clasificador) funcionando. Por eso BVBS es fase tardía. La cabecera necesita
`rebar_project.json` con nº de proyecto y de plano.

---

## 11 · Generadores por tipología

### Zapatas — `footing_rebar.py` [OK maduro]

- Añadir parámetro `std`; sustituir `default_anchorage_length_mm` por
  `standards.anchorage_length_mm`.
- Etiquetar cada barra con clave de capa (`bottom_x`…) y `Position_In_Host`.
- Consolidar el dilema mat-como-Set vs mat-como-cadenas: mantener ambos, elegir por `ctx` (Set
  por defecto, cadenas si el Set falla — ya está el fallback).
- Esperas (dowels): longitud de anclaje y solape con arranque de pilar desde `std.lap`.

### Pilares — `column_rebar.py` [OK maduro]

- `std` en firmas; zona de confinamiento desde `std.stirrups.confinement_zone_factor_h`;
  separación máxima de cerco desde `std.stirrups.max_spacing_column_min`.
- Arranques acodados / empalmes por planta: solape desde `std.lap`, decalaje desde
  `std.lap.stagger_offset_mm`.
- Columnas circulares (zuncho helicoidal): shape code `77`, marcar `Is_Variable` según paso.
- Capas: `long_corner` / `long_face` separadas para el despiece.

### Vigas — `beam_rebar.py` [CABLEAR + COMPLETAR]

- **Cablear a la pestaña *Beams* de la UI** (hoy vacía): selección de vigas, campos Ø sup/inf,
  nº barras, recubrimiento, separación de cercos, longitud de confinamiento en apoyos.
- Preview de sección (reusar `rebar_preview.compute_section_preview`, ya sirve).
- Barras dobladas en apoyos (patillas), refuerzo de negativos sobre pilares.
- Piel (`long_skin`) para cantos > umbral de `std`.
- Cercos: rectángulo cerrado `RebarStyle.StirrupTie`, gancho 135° desde `std.hook.stirrup_bend_deg`.

> **[DECISIÓN 11.A — continuidad entre vanos de viga]** ¿v1 arma cada viga (elemento Revit) de
> forma aislada, o resuelve continuidad de armadura de negativos entre vanos consecutivos?
> Recomendación: v1 aislado, continuidad como fase posterior.

### Muros — `wall_rebar.py` [DESDE CERO]

No existe. Alcance v1:
- Detección de geometría del muro (cara, longitud, altura, huecos) — reutilizar patrones de
  `slab_topology` y `CoverGeometryManager`.
- Dos mallas verticales + horizontales (una por cara), separación y Ø por dirección y cara.
- Horquillas de atado (`tie`) entre caras según `std`.
- Refuerzo de borde / jambas de hueco (`edge`) — U-bars, reutilizar
  `build_perimeter_closure_ubar_sets` de `footing_rebar` como referencia.
- Esperas de arranque desde la cimentación.
- Pestaña *Walls* de la UI (hoy vacía) + preview.

### Losas — `floor_rebar.py` [COMPLETAR]

- Cerrar el camino de "zona irregular" (freeform group) — comentarios indican que aún no ha
  hecho un `CreateFreeForm` exitoso en vivo.
- Refuerzos de negativos sobre apoyos / pilares (bandas superiores).
- Refuerzo perimetral de huecos y de borde (parcialmente hecho vía U-bars).
- `std` + capas + marcado.

---

## 12 · Rediseño de la interfaz

### Cambios estructurales

- **Barra de normativa global** (arriba, fuera de las pestañas): desplegable poblado por
  `standards.list_available()`; se guarda en `rebar_project.json` (por documento, no por
  usuario). Todo generador toma `std` de aquí.
- **Cabecera de proyecto**: nº de proyecto, nº/serie de plano, revisión, estado de emisión,
  prefijo de marca — a `rebar_project.json`; alimenta marca, tabla y BVBS.
- **Pestaña *Beams*** y **Pestaña *Walls***: construir UI real (Parte 11).
- **Pestaña *Detailing & Tools***: cablear los botones que hoy son stub — `BtnGenerateSchedule`,
  `BtnAutoMRA`; añadir **Gestor de lotes** (lista de `batch_id` con fecha/normativa/nº barras +
  acciones Seleccionar / Borrar / Re-etiquetar / Exportar BVBS).
- **Botón "Sellar shared params"** (o hacerlo automático al abrir): ejecuta
  `shared_params.ensure_bound` y muestra el informe.

### Persistencia de configuración

- `_rebar_automate.json` — **[OK existe]** — estado de ventana (dark_mode, últimos
  Ø/separaciones). Se mantiene.
- `rebar_project.json` — **[NUEVO]** — `{ standard_code, project_number, sheet_series, revision,
  issue_status, mark_prefix_scheme, insert_shared_params_into_user_file }`. Ligado al path del
  documento (o a `Document.PathName` hasheado).
- `rebar_standards/<code>.json` — **[NUEVO]** — overrides del usuario sobre los perfiles de
  fábrica.

### Paridad preview ↔ resultado

`rebar_preview.py` debe consumir el mismo `std` que el generador (recubrimientos, mandriles,
ganchos) para que el dibujo previo coincida con lo que se crea. Hoy usa `get_native_cover_mm`
+ defaults; pasarle `std`.

> **Restricción WPF ya conocida en el código:** `ui.py` documenta que **ningún** `ComboBox`
> puede llevar `SelectedIndex`/`SelectionChanged` en el XAML (crashea antes de que el objeto
> Python exista): defaults y eventos se cablean en código tras `wpf.LoadComponent`, con guarda
> `self._is_loaded`. El desplegable de normativa sigue esa misma regla.

---

## 13 · Contenido entregable (.rfa / plantillas)

| Artefacto | Categoría | Prioridad | Notas |
|---|---|---|---|
| `NOSA_Tag_Rebar.rfa` | OST_RebarTags | Alta | Lee `NOSA_Rebar_Mark`, Ø. Label editable. |
| `NOSA_Tag_Rebar_Spacing.rfa` | OST_RebarTags | Alta | Marca + "cØ200" + nº. |
| `NOSA_Tag_Rebar_Multi.rfa` | OST_RebarTags | Media | Para MRA. |
| `NOSA_BendingDetail_Generic.rfa` | Detail Item | Media (según Decisión 7.A) | Croquis paramétrico A/B/C/R. |
| `NOSA_Schedule_Row.rfa` | Detail Item | Baja (v2) | Fila gráfica de tabla de despiece. |
| `NOSA_TitleBlock_Rebar_A1.rfa` | Title Block | Baja | Cajetín de plano de armado. |

### Manifiesto de versión de contenido

Como `SOFiSTiK_ContentVersionFile_runtime.json`: `data/content_manifest.json` lista cada `.rfa`,
su versión y changelog. Al arrancar, el plugin compara con lo cargado en el proyecto y avisa si
hay una familia NOSA obsoleta.

```json
{ "families": [
  { "name": "NOSA_Tag_Rebar", "version": "1.0.0",
    "changes": "1.0.0 - Release. Lee NOSA_Rebar_Mark." },
  { "name": "NOSA_BendingDetail_Generic", "version": "1.0.0",
    "changes": "1.0.0 - Release." }
]}
```

> **[RIESGO API — versión de familia]** Una `.rfa` guardada en Revit 2024 **carga** en
> 2025–2027, pero no al revés. Guardar y versionar todas las familias entregables en
> **Revit 2024** para máxima compatibilidad hacia adelante. Documentarlo en `content/README`.

---

## 14 · Empaquetado, despliegue y versionado

### Modelo de despliegue

RebarAutomate es una *pushbutton* de una extensión pyRevit — no un `.bundle` de Autodesk.
pyRevit ya resuelve el aislamiento por versión de Revit. Lo que NOSA controla:

- **Un solo código para las 4 versiones.** No hay carpetas `2024/ 2025/…`. La diferencia vive
  en `revit_compat.py`. Esto es lo contrario del modelo SOFiSTiK (un bundle por año) y es
  correcto para pyRevit.
- **Contenido `.rfa` compartido** guardado en Revit 2024 (Parte 13).
- **`data/` versionado en git**, solo lectura en runtime. Nunca se escribe ahí; los overrides
  van a `NOSA_Configs/`.
- **Versionado semántico del plugin** en `script.py` (`__version__`) y en
  `data/content_manifest.json`; ese string va a `NOSA_Rebar_Generator_Version` de cada barra.

### Checks de CI (repo de la extensión)

- `json-schema` valida cada `data/rebar_standards/*.json` contra `_schema.json`.
- Test: cada `shape_catalog/*/NN_*.json` parsea y su `shape_code` es único por catálogo.
- Test: cada GUID de `NOSA_SharedParameters.txt` es único y coincide con la tabla del blueprint
  (fixture).
- Lint: ningún módulo de `RebarAutomate.pushbutton/lib/` importa `Autodesk.Revit` con un patrón
  de la lista negra de "API que difiere" fuera de `revit_compat` (grep en CI).
- Compat sintáctica IPy2 + Py3: parsear todos los `.py` con ambos.

### Instalación en cliente

Sin cambios respecto a hoy: la extensión NOSA se despliega por el mecanismo habitual de pyRevit.
Primer arranque de RebarAutomate en un proyecto → `shared_params.ensure_bound` corre solo. Nada
que instalar por versión de Revit.

---

## 15 · Estrategia de pruebas y QA

### Tres niveles

1. **Puro (pytest)** — Fuera de Revit. Geometría, `slab_topology`,
   `split_rebar_by_stock_length`, `standards` (merge + cálculos), `rebar_shape_classifier` con
   poligonales sintéticas, parser BVBS, dedup de marcas. Corre en IPy2 y Py3.
2. **Humo en Revit (por versión)** — Script pyRevit que, en un modelo fixture, arma 1 zapata +
   1 pilar + 1 viga + 1 muro + 1 losa, verifica: nº de `Rebar` creadas, todas con
   `Created_By_NOSA=1`, marca asignada, sin excepción no capturada. **Obligatorio pasar en
   2024, 2025, 2026, 2027 antes de publicar.**
3. **Fuego real** — Modelos de proyecto reales; revisión visual de secciones, ganchos, solapes,
   despiece contra cálculo manual.

### Matriz de humo (mínimo por release)

| Caso | 2024 | 2025 | 2026 | 2027 |
|---|---|---|---|---|
| Binding de shared params (`ensure_bound`) | ✔ | ✔ | ✔ | ✔ |
| Zapata: mat inf/sup + U-bars + esperas | ✔ | ✔ | ✔ | ✔ |
| Pilar rect. + circular, estribos + horquillas | ✔ | ✔ | ✔ | ✔ |
| Viga: long + cercos + confinamiento | ✔ | ✔ | ✔ | ✔ |
| Muro: mallas + tie + borde de hueco | ✔ | ✔ | ✔ | ✔ |
| Losa: direcciones + hueco + borde | ✔ | ✔ | ✔ | ✔ |
| Numeración + dedup + `Total_Length` | ✔ | ✔ | ✔ | ✔ |
| Clasificador de forma (ISO + BS) | ✔ | ✔ | ✔ | ✔ |
| Tags NOSA + MRA + dimensión de cercos | ✔ | ✔ | ✔ | ✔ |
| *Schedule* nativo + export CSV/XLSX | ✔ | ✔ | ✔ | ✔ |
| Export BVBS (checksum válido) | ✔ | ✔ | ✔ | ✔ |
| `select_batch` / `delete_batch` | ✔ | ✔ | ✔ | ✔ |

### Fixtures

Modelo `NOSA_RebarAutomate_Fixture.rvt` guardado en 2024 (abre en todas). Contiene los 5 hosts
en configuración conocida. Se versiona en el repo (o en LFS).

### Cómo ejecutar el nivel "Puro" — estado real desde F0

`RebarAutomate.pushbutton/tests/` contiene DOS estilos de fichero, deliberadamente distintos —
no forzados a converger en uno solo:

- **Pytest real** (`test_revit_compat.py`, `test_ci_checks.py`, y todo lo que F1+ añada siguiendo
  este mismo patrón): funciones `def test_*():` con `assert` normales, descubribles por pytest.
  `pytest.ini` en la raíz del pushbutton fija `testpaths = tests` para que
  `pytest NOSA.tab/Structures.panel/Quantities.pulldown/RebarAutomate.pushbutton` (o `pytest`
  desde dentro de esa carpeta) las encuentre solas.
- **Scripts de verificación de fase** (`test_phase35*_fixes.py`, `test_column_rebar_phase3.py`,
  `test_floor_rebar_phase23.py` — la red de regresión heredada de las Fases 3.5.1-3.5.9, movida
  aquí en F0 para que quede versionada): `assert` a nivel de módulo con `print(...)` de
  confirmación, SIN funciones `test_*` — un estilo de "script ejecutable", no de suite pytest.
  pytest los IMPORTARÍA igualmente durante la recolección (ejecutando sus asserts como efecto
  secundario del import) pero no los listaría como tests recolectados ni daría un resumen
  legible — se ejecutan como scripts sueltos, uno por uno o en bucle:

```bash
# pytest real (revit_compat, CI checks, y lo que añadan las fases siguientes)
pytest NOSA.tab/Structures.panel/Quantities.pulldown/RebarAutomate.pushbutton

# red de regresión heredada (scripts de verificación, no pytest)
cd NOSA.tab/Structures.panel/Quantities.pulldown/RebarAutomate.pushbutton/tests
for f in test_phase35*_fixes.py test_column_rebar_phase3.py test_floor_rebar_phase23.py; do
    python "$f" || echo "FAILED: $f"
done
```

Si una fase futura quiere que los scripts heredados también aparezcan en el resumen de pytest,
la conversión (envolver su cuerpo en una función `test_main()`) es un refactor aparte — no se
ha hecho en F0 para no tocar unas verificaciones ya probadas y estables.

---

## 16 · Hoja de ruta por fases

Orden por dependencias. Cada fase termina con criterio de aceptación verificable.

### F0 · Capa de compatibilidad + andamiaje — deps: —

- `nosa_utils/revit_compat.py` con la fachada de la Parte 4 (reexporta `get_id_value` etc.).
- Estructura `data/` vacía + `_schema.json`.
- Migrar los `imp.load_source` de RebarAutomate a `nosa_utils.bootstrap`.
- CI: parseo dual IPy2/Py3, grep de API prohibida.

**Aceptación:** La UI abre sin cambios funcionales en las 4 versiones; `revit_compat.api()`
devuelve la clase correcta por versión; CI verde.

### F1 · Shared params + provenance + lotes — deps: F0

- `NOSA_SharedParameters.txt` con los GUIDs de la Parte 5.
- `shared_params.py` (`ensure_bound`, `write`, `read`, `stamp_provenance`).
- `rebar_batch.py` (`RebarBatch.run` envuelve la generación actual de zapata/pilar;
  `select_batch`/`delete_batch`/`list_batches`).
- UI: sellado automático al abrir + Gestor de lotes básico en *Detailing & Tools*.

**Aceptación:** Toda barra generada lleva `Created_By_NOSA`, `Batch_Id`, `Generator_Version`,
`Standard_Code`; "Borrar ejecución" elimina exactamente ese lote y respeta `Finalized=1`. Humo
OK en 2024–2027.

### F2 · Perfiles de normativa — deps: F0

- `standards.py` + `EHE-08.json`, `EN-ISO-3766.json`, `BS-8666-2020.json`.
- Desplegable de normativa en la UI + `rebar_project.json`.
- Migrar `DEFAULT_COVER_MM`, `default_lap_*`, `default_anchorage_*`, zona de confinamiento,
  stock length a `standards.*` (con envoltorios de compat).
- `rebar_preview` consume `std`.

**Aceptación:** Cambiar de EHE-08 a BS-8666-2020 en la UI cambia recubrimientos, mandriles y
solapes en la siguiente generación y en el preview; tests puros de `standards` verdes.

### F3 · Numeración y marcado — deps: F1, F2

- `rebar_marking.py`: dedup, `mark_format`, capas, `Total_Length`.
- Generadores etiquetan clave de capa + `Position_In_Host`.
- UI: cabecera de proyecto (prefijos, revisión, estado).

**Aceptación:** Dos barras idénticas comparten marca; el *Schedule* nativo agrupa correctamente
por marca; renumerar un lote es idempotente.

### F4 · Catálogo de formas + clasificador — deps: F2, F3

- `data/shape_catalogs/en_iso_3766/` y `bs_8666_2020/`.
- `rebar_catalog.py` + `rebar_shape_classifier.py` (classify + stamp).
- Pre-validación de forma antes de `CreateFromCurves` (mitiga "Internal Error").

**Aceptación:** >90 % de las barras generadas reciben un `Shape_Code` distinto de `99`; el
resto quedan como `99` con medidas libres sin excepción; tests con poligonales sintéticas
verdes.

### F5 · Despiece (BBS) + export CSV/XLSX — deps: F3, F4

- `rebar_schedule.py`: recolección, agrupación, longitud de corte con descuentos de doblado.
- *Schedule* nativo parametrizado + export tabla.
- Botón `BtnGenerateSchedule` cableado.

**Aceptación:** La tabla cuadra con un despiece manual de la zapata fixture (±1 en longitudes
redondeadas); export abre en Excel.

### F6 · Detallado completo — deps: F3, F4

- Familias `NOSA_Tag_*.rfa` (guardadas en 2024).
- `rebar_detailing`: MRA, dimensión de cercos verificada, secciones preset por tipología,
  croquis de doblado.
- Botón `BtnAutoMRA` cableado.

**Aceptación:** Un plano de zapata sale etiquetado, acotado y con 2 secciones automáticas
legibles sin intervención manual, en las 4 versiones.

### F7 · Vigas + Muros completos — deps: F2, F3, F4

- Cablear pestaña *Beams*; completar `beam_rebar` (piel, cercos 135°, confinamiento).
- `wall_rebar.py` desde cero + pestaña *Walls*.
- Preview para ambas.

**Aceptación:** Las 5 tipologías generan armado válido, marcado y clasificado en el fixture, en
las 4 versiones.

### F8 · Exportación BVBS — deps: F4, F5

- `rebar_export_bvbs.py` (2D; 3D si aplica a hélices).
- Cabecera desde `rebar_project.json`; checksum validado contra spec.
- Acción "Exportar BVBS" en el Gestor de lotes.

**Aceptación:** Un fichero `.abs` del lote fixture pasa un validador BVBS externo; longitudes
coinciden con la tabla.

### F9 · Endurecimiento + losas + release — deps: todas

- Cerrar el camino freeform de `floor_rebar`; negativos sobre apoyos.
- Manifiesto de contenido + aviso de familia obsoleta.
- Matriz de humo completa 2024–2027 verde; documentación de usuario.

**Aceptación:** Release `1.0.0`: matriz de humo 100 % en 4 versiones; un proyecto real armado de
principio a fin (modelo → planos → despiece → BVBS).

---

## 17 · Decisiones pendientes de confirmar

Antes de arrancar F1. El resto puede decidirse sobre la marcha.

| # | Decisión | Recomendación del blueprint |
|---|---|---|
| 5.A | ¿El plugin inserta sus shared params en el fichero `.txt` del usuario, o gestiona un `DefinitionFile` propio temporal? | Preguntar al usuario en el primer arranque; guardar preferencia en `rebar_project.json`. Por defecto: fichero propio (no toca el del cliente). |
| 6.A | Perfiles iniciales: ¿solo EHE-08 + ISO + BS, o también CE-21 y EC2? | EHE-08 + ISO + BS en F2. CE-21 y EC2 como fase menor posterior. |
| 6.B | Unidades: ¿migrar todo a `UnitUtils`/`UnitTypeId` o mantener el factor `304.8`? | Mantener `304.8` interno (ya probado), `UnitUtils` solo para mostrar/parsear en la UI respetando las unidades del proyecto. |
| 7.A | Croquis de doblado: ¿familia genérica NOSA o *Bending Detail* nativo de Revit? | Nativo en v1; familia propia si la calidad no basta. |
| 10.A | Tabla oficial: ¿*Schedule* nativo maquetado o export a plantilla Excel? | Nativo para el plano (v1) + export Excel paralelo. |
| 11.A | Vigas: ¿armado por elemento aislado o continuidad de negativos entre vanos? | Aislado en v1 (F7); continuidad como fase posterior. |
| 13.A | ¿Familias `.rfa` y fixture `.rvt` en el repo git o en almacenamiento aparte? | Git LFS si el repo lo soporta; si no, carpeta `content/` versionada con tags. |
| 16.A | ¿F7 (vigas+muros) va antes o después de F5/F6 (despiece+detallado)? | Como está: despiece/detallado primero sobre zapata+pilar (ya maduros), tipologías nuevas después. |

---

## 18 · Apéndices

### A · Ledger de confianza de API (heredado del código actual)

| Llamada | Confianza | Acción en el blueprint |
|---|---|---|
| `Rebar.CreateFromCurves` (sin ganchos, Standard) | Alta — fuego real Phase 4 | Envolver en `compat`, sin cambios de lógica. |
| Solid/Face/XYZ/Transform math, RebarBarType by class | Alta | — |
| `RebarHostData.GetRebarHostData` | Media | No depender de más superficie que la factory. |
| `RebarHookType.HookAngle` | Media — no probado en vivo | Ángulo objetivo desde `std.hook`; skip defensivo si falla. |
| `start_hook`/`end_hook` en `CreateFromCurves` | Media — solo dowels lo usan | Verificar visualmente; mats usan geometría de patilla explícita. |
| `GetShapeDrivenAccessor.SetLayoutAsMaximumSpacing` | Media — Set abierto funciona (Phase 5.5); signo de `normal` delicado | Pasar `propagation_reference`; fallback a cadenas. |
| `Rebar.CreateFreeForm` (IList<CurveLoop>) | Media-baja — sin creación exitosa en vivo aún | Cerrar en F9; llamantes tratan `None` como esperado. |
| `IndependentTag.Create` (2022+ overload) | Media — no ejercitado | Verificar en F6, en las 4 versiones. |
| `doc.Create.NewDimension` sobre `Reference(rebar)` | Media | Verificar en F6. |
| `ViewSection.CreateDetail` + `BoundingBoxXYZ.Transform` | Baja — "el punto menos fiable del plugin" | Estilo defensivo (devuelve `None`); presets por tipología; iterar. |

### B · Glosario

- **BBS** — Bar Bending Schedule — tabla de despiece de ferralla.
- **BVBS** — Formato ASCII estándar para máquinas de ferralla (dobladoras/cizallas).
- **Shape code** — Código normalizado de forma de barra (BS 8666 / EN ISO 3766).
- **MRA** — Multi-Reference Annotation — una etiqueta que referencia varias barras iguales.
- **Mandril** — Diámetro del rodillo de doblado; determina el radio interior de los dobleces.
- **Rebar Set** — Un elemento `Rebar` de Revit que representa una serie de barras iguales
  espaciadas (vía `ShapeDrivenAccessor`).
- **Provenance** — Marca de origen: qué creó el elemento, cuándo, con qué versión y normativa.
- **ctx** — Objeto de contexto de ejecución que acompaña a toda generación (Parte 3).

### C · Referencias verificadas en disco (SOFiSTiK Reinforcement 2026)

- `PackageContents.xml` — 1 `ComponentEntry`, `SeriesMin=SeriesMax=R2026` (un bundle por año).
- `Contents/sof_rvt_rc.addin` — 1 `IExternalApplication` (`SOFiSTiK.ToolbarCAD.CreateToolbar`);
  ribbon construido en código.
- `Contents/SOFiSTiK_ContentVersionFile_runtime.json` — manifiesto de versión de familias con
  changelog (modelo para `content_manifest.json`).
- `Contents/shape_catalogs/{BS_8666_2005,BS_8666_2020,EN_ISO_3766,SANS_282_2011,SSHV_2014}/` —
  JSON de constraints por forma (modelo para Parte 7). Sin catálogo EHE.
- `Contents/analysis_bin/data/cad/schedule/codes/{bs,bs_2020,din,iso,sans,sshv}/` — reglas de
  despiece como Lua + `units.json`.
- `Contents/analysis_bin/model.server/plugins/sofistik.model.cad.bvbs_rc.dll` — exportador BVBS
  (modelo para Parte 10).
- Shared parameters SOFiSTiK inyectados por API (sin `.txt` en el bundle); nombres extraídos de
  `sof_rvt_base_rc.dll`: `SOFiSTiK_Mark`, `SOFiSTiK_Layer`, `SOFiSTiK_Identifier`,
  `SOFiSTiK_Finalized`, `SOFiSTiK_Coupler_At_Start`/`_At_End`, `SOFiSTiK_EndTreatment_At_Start`/
  `_At_End`, `SOFiSTiK_Mass_Per_Length`, `SOFiSTiK_Mark_Prefix`/`_Suffix`,
  `SOFiSTiK_Mark_TotalLength`, `SOFiSTiK_Number`, `SOFiSTiK_Assignment`, `SOFiSTiK_Running_Length`,
  `SOFiSTiK_Not_Bent`, `SOFiSTiK_Variable_RebarSet`, `SOFiSTiK_Spacer_BF98`, `SOFiSTiK_Text_Custom`.

---

*Blueprint generado el 2026-08-27 a partir del análisis en disco de*
*`C:\ProgramData\Autodesk\ApplicationPlugins\sofistik_reinforcement_2026.bundle` y del baseline*
*real de `NOSA.extension\...\RebarAutomate.pushbutton`. Los GUIDs de la Parte 5 son definitivos.*
