# RebarAutomate — Roadmap F0→F9

Objetivo: Plugin de armado profesional con paridad/superioridad vs SOFiSTiK Reinforcement, funcionando idénticamente en Revit 2024/2025/2026/2027.

---

## Estado actual

| Fase | Descripción | Estado | Rama | Commits |
|---|---|---|---|---|
| **F0** | Revit 2024–2027 compat facade + tooling migration | ✅ **DONE** | `feat/rebar-F0-compat` | 3cfa461 |
| **F1** | Shared params + provenance + batch manager | ✅ **DONE** | `feat/rebar-F1-shared-params` | 736497b, 252e379 |
| **F2** | Perfiles de normativa (EHE-08, ISO, BS) | ✅ **DONE** (partial) | `feat/rebar-F2-standards` | 02d2a65 |
| **F3** | Numeración y marcado | 🚧 **IN PROGRESS** | `feat/rebar-F3-marking` | — |
| **F4** | Catálogo de formas + clasificador | ⏳ Pending | — | — |
| **F5** | Despiece (BBS) + export CSV/XLSX | ⏳ Pending | — | — |
| **F6** | Detallado completo (tags, MRA, secciones) | ⏳ Pending | — | — |
| **F7** | Vigas + muros completos | ⏳ Pending | — | — |
| **F8** | Export BVBS (máquinas ferralla) | ⏳ Pending | — | — |
| **F9** | Losas + endurecimiento + release 1.0.0 | ⏳ Pending | — | — |

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

**Desviaciones documentadas:**
- **COVER: conectado end-to-end** — preview y generación real usan el mismo helper `_standard_default_cover_mm()`
- **LAP/MANDREL/STOCK_LENGTH: wrappers listos pero NO conectados** — `column_rebar.default_lap_length_mm(..., std=None)`, `footing_rebar.default_anchorage_length_mm(..., std=None)` existen con backward-compat (std=None reproduce pre-F2), pero NO están llamados desde `build_column_reinforcement`/`build_footing_reinforcement` (cambio de firma >2000 líneas, riesgo alto de romper geometría ya testada en fases 4/5)
- **Consecuencia honesta**: hoy, cambiar "Standard:" en UI SOLO cambia cover (preview + real). Lap/mandrel/stock siguen fijos, coherentes entre sí, pero no gobernados por normativa aún. Conexión completa diferida a fase posterior (F2.5 o F3).

**Bug corregido:** column_rebar.py/footing_rebar.py faltaban sys.path para `import nosa_utils` — los 9 scripts legacy ahora corren standalone sin ModuleNotFoundError.

**Deps:** F0 (compat), F1 (provenance)

**Timeline:** 3–4 días

---

## F3 — Numeración y marcado 🚧 IN PROGRESS

**Progreso actual:**
- ✅ `lib/rebar_marking.py` creado (deduplicate_and_mark, compute_total_length_mm, assign_layers_and_lengths, renumber_batch)
- ✅ Integrado en `rebar_batch.py` (paso 3: marking tras provenance, antes de Assimilate)
- ✅ `tests/test_rebar_marking.py` creado (6/6 tests puros PASS)
- ⏳ Pendiente: UI cabecera proyecto, actualizar perfiles JSON, etiquetado Layer en generadores

**Entregables:**
- `lib/rebar_marking.py` (dedup, mark_format, capas, Total_Length)
- Generadores etiquetan clave de capa + Position_In_Host
- UI: cabecera de proyecto (prefijos, revisión, estado)

**Criterio de éxito:** Barras idénticas comparten marca. Schedule nativo agrupa correctamente. Renumerar lote es idempotente.

**Deps:** F1 (provenance), F2 (std.marking.*)

**Timeline:** 4–5 días

---

## F4 — Catálogo de formas + clasificador ⏳ Pending

**Entregables:**
- `data/shape_catalogs/{en_iso_3766,bs_8666_2020}/` (JSON constraints por forma)
- `lib/nosa_utils/rebar_catalog.py` + `lib/rebar_shape_classifier.py`
- Pre-validación antes de `CreateFromCurves` (mitiga "Internal Error")
- `RebarBatch.run`: Transaction clasificar+sellar forma

**Criterio de éxito:** >90% barras con shape_code ≠ 99. Resto `99` sin crash. Tests con poligonales sintéticas verdes. **Humo obligatorio 4 versiones.**

**Deps:** F2 (std.bend), F3 (marcado espera Shape_Code)

**Timeline:** 5–7 días

**Riesgo:** Alto (clasificador debe tolerar variaciones geométricas)

---

## F5 — Despiece (BBS) + export ⏳ Pending

**Entregables:**
- `lib/rebar_schedule.py` (recolección, agrupación, long. corte con descuentos)
- Schedule nativo + export CSV/XLSX
- Botón `BtnGenerateSchedule` cableado

**Criterio de éxito:** Tabla fixture cuadra con despiece manual (±10 mm). Export abre en Excel.

**Deps:** F3 (marcado), F4 (forma)

**Timeline:** 4–5 días

---

## F6 — Detallado completo ⏳ Pending

**Entregables:**
- Familias `NOSA_Tag_*.rfa` (OST_RebarTags, guardadas en 2024)
- `lib/rebar_detailing.py` ampliado (MRA, dimensiones verificadas, secciones preset, croquis)
- Botón `BtnAutoMRA` cableado

**Criterio de éxito:** Plano de zapata etiquetado+acotado+2 secciones automáticas legibles, sin intervención manual. **Humo obligatorio 4 versiones.**

**Deps:** F3 (marcado), F4 (forma)

**Timeline:** 5–6 días

**Riesgo:** Medio-alto (`create_rebar_detail_section` inestable; estilo defensivo obligatorio)

---

## F7 — Vigas + muros ⏳ Pending

**Entregables:**
- **Vigas:** pestaña UI cableada, long. sup/inf, piel, cercos 135°, confinamiento, preview
- **Muros:** `lib/wall_rebar.py` desde cero, mallas vert.+horiz., ties, borde/hueco, esperas, preview

**Criterio de éxito:** 5 tipologías (zapata, pilar, viga, muro, losa) generan armado válido, marcado y clasificado. **Humo obligatorio 4 versiones.**

**Deps:** F2 (std), F3 (marcado), F4 (forma)

**Timeline:** 6–8 días

**Decisión:** Vigas aisladas en v1; continuidad entre vanos = fase posterior.

---

## F8 — Export BVBS ⏳ Pending

**Entregables:**
- `lib/rebar_export_bvbs.py` (bar_to_bvbs: cabecera + geometría + checksum)
- Acción "Export BVBS" en Gestor de lotes

**Criterio de éxito:** Fichero `.abs` fixture pasa validador BVBS externo. Checksum correcto. Longitudes coinciden con tabla F5.

**Deps:** F4 (forma), F5 (despiece)

**Timeline:** 3–4 días

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

**Última actualización:** F1 cerrado, F2 arrancando (2026-08-27)
