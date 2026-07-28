# Plan de optimización — NOSA.extension

Propuesta de mejoras adicionales no cubiertas por `PLAN_MEJORA.md` (que ya se
ejecutó por completo salvo Fase 10 y 13, aplazadas por decisión). Este
documento es **solo una propuesta priorizada — nada de esto se ha
implementado todavía.**

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

**Propuesta**: un barrido dedicado (no en esta sesión) que:
1. Liste todas las llamadas a métodos de `doc.Create`/`uidoc.Selection`/etc.
   poco comunes en los ~88 plugins (grep de `doc.Create.New` da una lista
   acotada y manejable).
2. Verifique cada uno con `hasattr()` en un script de diagnóstico rápido
   contra el modelo real del usuario, sin necesidad de ejecutar cada plugin
   uno a uno.
3. Documente los que fallen como limitaciones confirmadas del entorno (como
   ya se hizo con `NewRadialDimension`), con alternativas conocidas cuando
   existan (p. ej. geometría auxiliar propia, como se hizo en `DimensionWalls`
   esta sesión).

**Prioridad**: Alta (afecta fiabilidad, no solo rendimiento) pero alcance
grande — candidato a su propia sesión dedicada.

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

**Prioridad**: Alta. **Alcance**: grande — necesita su propia sesión,
priorizando por plugins más usados primero (ver `NOSA_Configs/_usage.json`
para datos reales de uso).

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

**Propuesta**: un grep dirigido (`FilteredElementCollector\(doc\)\s*\)?\s*\.`
sin `.OfCategory`/`.OfClass` inmediatamente después, dentro de un archivo
que también tenga un bucle `for` que lo contenga) daría una lista candidata
rápida para una futura sesión, sin necesidad de repetir el trabajo manual de
esta.

**Prioridad**: Media-baja — los 7 hallazgos conocidos y más probables ya
están resueltos; esto es para encontrar los que la auditoría original no
vio.

---

## Resumen priorizado

| # | Item | Prioridad | Alcance | Estado |
|---|---|---|---|---|
| 1 | Barrido de métodos de API con superficie reducida bajo pythonnet | Alta | Grande | **Pendiente** — necesita su propia sesión (ver nota abajo) |
| 2 | Barrido sistemático de bare `.Name` | Alta | Grande | **Pendiente** — necesita su propia sesión (ver nota abajo) |
| 4 | Confirmar riesgo real de `imp.load_source` bajo Python 3.14 | Alta (condicional) | Pequeño | ✅ **Cerrado** — funciona de forma fiable, confirmado con evidencia empírica de toda la sesión |
| 5 | Barrido nuevo de collectors sin filtro/en bucle | Media | Medio | Pendiente, prioridad media-baja |
| 3 | Perfilar arranque real del ribbon | Media | Pequeño | ✅ **Investigado** — no hay logs accesibles fuera de Revit; requiere medición manual del usuario |

### Nota sobre los puntos 1 y 2 (por qué siguen pendientes, no ejecutados en esta sesión)

Ambos tienen alcance grande (decenas/cientos de archivos) y esta misma
sesión ya demostró el riesgo concreto de tocar código en bloque sin
verificación individual: el fix "optimizado" de H12 (PASO 2) rompió el
escaneo de materiales en producción y tuvo que revertirse tras el primer
uso real. Ejecutar 1 o 2 de golpe, sin poder probar cada cambio contra el
modelo real del usuario uno a uno, repetiría ese mismo riesgo a mucha
mayor escala. Si se quiere avanzar en esto, la vía responsable es una
sesión dedicada con lotes pequeños y verificación en Revit entre cada uno
— igual que el resto de este plan — no un barrido masivo de una sola vez.

**No implementar nada de esto todavía** — es una propuesta para que decidas
qué abordar y en qué orden en una futura sesión.
