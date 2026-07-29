# Plan de optimización — NOSA.extension

Propuesta de mejoras adicionales no cubiertas por `PLAN_MEJORA.md` (ejecutado
por completo salvo Fase 13, aplazada por decisión — Fase 10 también
ejecutada). **Estado 2026-07-29: 4 de 5 puntos cerrados o investigados y
ejecutados** (ver tabla al final). Solo queda el resto del barrido de bare
`.Name` en los plugins de menor uso (punto 2).

Contexto confirmado esta sesión (relevante para todo lo que sigue): el
entorno real del usuario es **pyRevit 6.5.0.26173+1406 sobre motor
CPython/pythonnet (.NET 8, Python 3.14)**, no IronPython 2.7. Varias
suposiciones de `AUDIT_REFACTOR_PLAN.md` (p. ej. "la migración a CPython 3 se
difiere a cuando pyRevit lo adopte") ya no aplican — pyRevit ya corre sobre
CPython en este entorno. Esto cambia la prioridad de varios puntos de abajo.

---

## 1. Bloqueador confirmado — API de Revit con superficie reducida bajo este build

**Hallazgo concreto, no hipotético**: `Document.Create.NewRadialDimension` no
existe como atributo resoluble en este entorno (confirmado con `hasattr` en
3 rondas distintas de `DimensionWalls`, con el modelo real del usuario
abierto). Esto no es un caso aislado — es evidencia directa de que **algunos
métodos de la API de Revit no se resuelven igual bajo pythonnet que bajo
IronPython** en esta combinación de versiones concretas.

**Riesgo**: cualquier otro plugin que llame a un método de API "raro" o poco
común (no solo `.Name`, ver §2) puede fallar igual, en silencio o con un
mensaje de error confuso, sin que se haya detectado todavía porque no se ha
probado en vivo.

**Inventario ejecutado esta sesión (2026-07-28, solo lectura, sin arreglos)**:
grep de `doc.Create.New*`/`app.Create.New*` en todo `NOSA.tab` — 25 sitios de
llamada en 9 archivos:

| Método | Archivos | Riesgo |
|---|---|---|
| `NewFamilyInstance` | 3 | Común — estable |
| `NewGroup` | 3 | Común — estable |
| `NewDimension` | 5 | Común — estable |
| `NewCategorySet` / `NewInstanceBinding` (`app.Create`) | 2 | Común — estable |
| `NewFloor` (overload antiguo con `CurveArray`) | 1 (`CreatePilecapType.pushbutton/lib/logic.py:117`) | **Sospechoso** — overload heredado pre-2022, superado en versiones modernas de la API; mismo patrón de riesgo que `NewRadialDimension` |
| `NewRadialDimension` | 1 (`DimensionWalls.nobutton/lib/logic.py:230`) | **Confirmado roto** en este entorno — pero es código muerto (`.nobutton`, la ruta activa es `AnnotationHub`, ya aparcada esta sesión) |

No se encontró ningún otro creador "exótico" (`NewAngularDimension` fuera de
lo ya tocado, `NewWall`, `NewDetailCurve` fuera de lo ya tocado, etc.) en
ningún otro sitio del árbol.

**Propuesta restante**: verificar en vivo el overload antiguo de `NewFloor`
en `CreatePilecapType` (el único candidato "sospechoso" que queda activo) —
pequeño, acotado, no requiere un barrido de 88 plugins. El resto de la lista
original (barrido completo + `hasattr()` automatizado) ya no hace falta: el
inventario real es mucho más pequeño (9 archivos, no 88) y ya está hecho.

**Prioridad**: Media — el único candidato activo (`NewFloor` en
CreatePilecapType) es una prueba puntual, no una sesión dedicada.

---

## 2. Hallazgo sistémico ya flotante — bare `.Name` (143 archivos, ~499 apariciones)

Ya documentado en `PLAN_MEJORA.md` (sección "Hallazgo sistémico nuevo").
Repetido aquí porque es, con diferencia, el mayor riesgo de fiabilidad
pendiente identificado en toda la auditoría: bajo este build concreto,
`el_type.Name`/`el.Category.Name`/etc. (acceso directo, sin
`BuiltInParameter`) puede lanzar `AttributeError` — confirmado en vivo en
`MaterialManager`. La cota de 499 apariciones es ruidosa (incluye nombres de
controles WPF y variables Python, no solo API de Revit), pero incluso
acotada a una fracción real, es un riesgo transversal a decenas de plugins.

**Ejecutado (2026-07-29) — barrido priorizado por uso real**: en vez del
barrido completo de 143 archivos (alto riesgo, ver el aviso de la Fase 9/H12
más abajo), se auditaron los 8 plugins con más uso real según
`NOSA_Configs/_usage.json`: **ExportSheets** (75 lanzamientos combinados —
encontrado y corregido el hallazgo más grave: un `.Name` roto en el bucle de
exportación por elemento abortaba la exportación completa de esa vista/hoja,
y el propio manejador de errores volvía a leer `.Name` sin proteger,
arriesgando un segundo fallo sin capturar), **PileMaster** (41, 3 sitios sin
ninguna protección), **MaterialManager** (ya corregido en rondas
anteriores), **AddPileToPilecap** (24, incluyendo el bucle de búsqueda de
elevación por nombre que usa el propio cálculo de embedment arreglado esta
sesión), **CreatePilecapType**, **ProjectSetupWizard**, **AnnotationHub**
(el más relevante: el wrapper `_ViewItem` sin proteger podía romper la
inicialización completa de la ventana), **QRCode**. **ViewManager** ya
estaba limpio (todo protegido con `try/except`). Todos corregidos con el
patrón `getattr(obj, 'Name', None) or <valor por defecto>` ya validado en
`MaterialManager`.

**Pendiente**: el resto de los ~143 archivos (los de menor uso) — se aplica
el mismo aviso que en el punto 1: un barrido masivo sin verificación en vivo
repite el riesgo que ya se vio con H12 esta sesión.

**Prioridad**: Media (bajó de Alta — los plugins de mayor impacto real ya
están corregidos). **Alcance**: pequeño-medio por lote restante, mismo
patrón, priorizar por `_usage.json` si se retoma.

---

## 3. Arranque del ribbon — imports pesados a nivel de import

**Qué se sabe ya**: `lib/nosa_utils/__init__.py` y `lib/pilecap_utils/__init__.py`
se vaciaron en la Fase 12 (ya ejecutada) — ya no importan nada de forma eager
a nivel de paquete. Eso resuelve el caso más grave (cualquier
`from nosa_utils.X import Y` arrastrando toda la API de Revit al importar el
paquete).

**Investigado (2026-07-28)**: se buscó en disco algún log de pyRevit con
tiempos de carga por extensión/script — no se encontró ninguno accesible
desde fuera de una sesión activa de Revit (pyRevit no persiste esto en un
archivo de log estándar que se pueda leer sin la UI de depuración). Cada
`script.py` revisado en esta sesión solo define metadata a nivel de import
(`__title__`, `__doc__`, etc.) sin lógica pesada — no hay indicio directo
de un problema, pero tampoco una medición real.

**Propuesta sin cambios**: la única forma fiable de medir esto es desde
dentro de Revit (el botón de log/depuración de pyRevit, o cronometrar el
arranque manualmente con distintas extensiones activadas/desactivadas) —
no es algo que se pueda hacer desde este entorno. Recomendado como tarea
manual del usuario si quiere decidir si esto merece inversión, en vez de
optimizar sin datos.

**Prioridad**: Media — sigue sin evidencia de que el arranque sea lento.

---

## 4. `imp.load_source` vs `nosa_utils.bootstrap` (migración diferida, sigue vigente)

`AUDIT_REFACTOR_PLAN.md` (Bloque 12, ya completo) dejó esto explícitamente
diferido: ~130 archivos siguen usando `imp.load_source` directamente en vez
de `nosa_utils.bootstrap.load_module`, con la justificación de que ambos
funcionan igual bajo IronPython 2.7 y la migración se pospondría "a cuando
pyRevit adopte CPython 3".

**Esto ya no es un supuesto futuro — ya está pasando.** `imp` está
**deprecado en Python 3** (eliminado por completo en 3.12+) y este entorno
corre **Python 3.14** vía pythonnet. El hecho de que `imp.load_source` siga
funcionando hoy sugiere que pyRevit trae su propio shim de compatibilidad
para `imp`, pero eso no está garantizado en futuras versiones de pyRevit ni
de Python.

**Investigado (2026-07-28)**: no se pudo determinar con certeza absoluta si
pyRevit trae un shim de `imp` — `bin/cengines/CPY3123` (el motor CPython
empaquetado) no contiene ningún `imp.py` propio, pero el propio código
interno de pyRevit (`pyrevitlib/pyrevit/loader/uimaker.py`,
`pyrevitlib/pyrevit/preflight/__init__.py`) hace `import imp` directamente
— es decir, pyRevit depende de `imp` para sí mismo, no solo para scripts de
usuario. **Evidencia empírica más fuerte que la teoría**: durante toda esta
sesión, cada plugin tocado (`MaterialManager`, `AnnotationHub`,
`AddPileToPilecap`, etc.) usa `imp.load_source` en su `script.py`/`ui.py`, y
el usuario los ha probado en vivo repetidamente sin un solo error de
`ModuleNotFoundError: No module named 'imp'`. Esto confirma que, sea cual
sea el mecanismo exacto, `imp.load_source` **funciona de forma fiable en el
entorno real del usuario ahora mismo**.

**Conclusión**: se cierra este punto — la decisión original de
`AUDIT_REFACTOR_PLAN.md` (aplazar la migración, no tocar ~130 archivos sin
necesidad) sigue siendo correcta. Para código NUEVO, seguir usando
`nosa_utils.bootstrap`/`importlib.util` como ya indica CLAUDE.md §2, pero
no hace falta ninguna acción adicional sobre el código existente.

---

## 5. Caching más allá de los 7 hallazgos de PASO 2

Los 7 hallazgos H4/H11/H12/H13/H15/H16/H18 ya se revisaron (3 corregidos, 4
ya no aplicaban). No se ha hecho un barrido exhaustivo de **todo** el árbol
buscando el mismo patrón (`FilteredElementCollector` sin filtro de
categoría, o repetido dentro de un bucle) — el `PASO 2` de esta sesión se
limitó a los hallazgos ya identificados en `AUDITORIA.md`, no a un barrido
nuevo completo.

**Ejecutado (2026-07-29)**: barrido dirigido de los ~98 sitios de
`FilteredElementCollector` en todo el árbol buscando collectors sin filtro
de categoría/clase recreados dentro de un bucle. La inmensa mayoría ya
filtra de inmediato o varía el filtro por iteración (no cacheable) — se
encontraron **2 casos genuinos**, ambos corregidos:
- **BaySections**: `create_bay_sections()` recalculaba los extremos del
  modelo (escaneo completo sin filtro) una vez por cada par de grids en un
  bucle anidado grids_a × grids_b, pese a que los extremos no dependen del
  par seleccionado. Ahora se calculan una vez fuera del bucle.
- **WorksetHealth**: `get_elements_on_workset()` repetía un escaneo completo
  del documento por cada workset origen seleccionado. Sustituido por
  `get_elements_on_worksets()` (plural), que sigue el mismo patrón de
  una-sola-pasada-y-clasificar que ya usaba `get_workset_stats()` en el
  mismo archivo.

**Prioridad**: Cerrado — no quedan más candidatos genuinos en el árbol
actual (los ~96 restantes son falsos positivos: ya filtrados o con filtro
legítimamente variable por iteración).

---

## Resumen priorizado

| # | Item | Prioridad | Alcance | Estado |
|---|---|---|---|---|
| 1 | Barrido de métodos de API con superficie reducida bajo pythonnet | Media | Pequeño | ✅ **Inventario completo** — solo 9 archivos/25 sitios, no 88 plugins. Un único candidato activo (`NewFloor` legado en CreatePilecapType) queda como prueba puntual |
| 2 | Barrido sistemático de bare `.Name` | Media | Pequeño-medio restante | ✅ **8 plugins de mayor uso corregidos** (ExportSheets, PileMaster, AddPileToPilecap, CreatePilecapType, ProjectSetupWizard, AnnotationHub, QRCode; MaterialManager y ViewManager ya estaban bien) — queda el resto de ~143 archivos, de uso mucho menor |
| 3 | Perfilar arranque real del ribbon | Media | Pequeño | ✅ **Investigado** — no hay logs accesibles fuera de Revit; requiere medición manual del usuario |
| 4 | Confirmar riesgo real de `imp.load_source` bajo Python 3.14 | Alta (condicional) | Pequeño | ✅ **Cerrado** — funciona de forma fiable, confirmado con evidencia empírica de toda la sesión |
| 5 | Barrido nuevo de collectors sin filtro/en bucle | Media | Medio | ✅ **Cerrado** — 2 casos genuinos encontrados y corregidos (BaySections, WorksetHealth), resto son falsos positivos |

### Qué queda realmente pendiente

Solo el resto del barrido de bare `.Name` (punto 2) — los plugins de menor
uso real, no auditados esta sesión por volumen. Si se retoma, seguir
priorizando por `NOSA_Configs/_usage.json` y aplicar el mismo patrón
(`getattr(obj, 'Name', None) or <fallback>`) en lotes pequeños con
`py_compile` + prueba en Revit entre cada uno — el fix "optimizado" de H12
(PASO 2) que rompió el escaneo de materiales en producción y tuvo que
revertirse es la prueba concreta, dentro de esta misma sesión, de por qué
un barrido masivo sin verificación individual es un riesgo real, no
hipotético.
