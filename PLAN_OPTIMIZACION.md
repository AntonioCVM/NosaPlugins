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

**Lo que queda por medir, no asumido**: no se ha perfilado el tiempo de
arranque real del ribbon (cuánto tarda pyRevit en cargar los ~88
`script.py` al iniciar Revit). Cada `script.py` solo define metadata
(`__title__`, `__doc__`, etc.) y no debería ejecutar lógica pesada al cargar
— pero esto no se ha verificado sistemáticamente.

**Propuesta**: perfilar el arranque real (pyRevit tiene su propio log de
tiempos de carga por extensión) antes de proponer cualquier cambio — no
optimizar a ciegas sin medir primero.

**Prioridad**: Media — no hay evidencia todavía de que el arranque sea
lento, solo la ausencia de medición.

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

**Propuesta**: no es urgente mientras siga funcionando (no tocar 130
archivos sin necesidad, por la misma razón que se aplazó la Fase 10 de
`304.8`), pero sí conviene:
1. Confirmar explícitamente si pyRevit 6.5 trae un shim de `imp` o si
   `imp.load_source` está funcionando por otra vía (p.ej. `importlib` bajo
   el capó).
2. Si NO hay shim garantizado, reclasificar esto de "deuda técnica diferida"
   a "riesgo de ruptura en la próxima actualización de pyRevit" — cambiaría
   la prioridad de baja a alta.
3. Para código NUEVO (no migrar lo existente), usar siempre el patrón
   `nosa_utils.bootstrap` o `importlib.util`, como ya indica CLAUDE.md §2.

**Prioridad**: depende del punto 1 — pendiente de verificar antes de decidir.

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

| # | Item | Prioridad | Alcance | Motivo |
|---|---|---|---|---|
| 1 | Barrido de métodos de API con superficie reducida bajo pythonnet | Alta | Grande | Fiabilidad — puede haber más `NewRadialDimension` sin descubrir |
| 2 | Barrido sistemático de bare `.Name` | Alta | Grande | Ya confirmado que rompe en producción (MaterialManager) |
| 4 | Confirmar riesgo real de `imp.load_source` bajo Python 3.14 | Alta (condicional) | Pequeño (solo investigar) | Puede no ser "deuda diferida" sino "va a romper pronto" |
| 5 | Barrido nuevo de collectors sin filtro/en bucle | Media | Medio | Los conocidos ya están resueltos |
| 3 | Perfilar arranque real del ribbon | Media | Pequeño (medir primero) | Sin evidencia de que sea lento todavía |

**No implementar nada de esto todavía** — es una propuesta para que decidas
qué abordar y en qué orden en una futura sesión.
