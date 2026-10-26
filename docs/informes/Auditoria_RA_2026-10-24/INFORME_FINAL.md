# RebarAutomate — Informe final de la auditoría de planos y BBS (24-10-2026)

**Alcance:** planos de armado (serie 4500), planillas BBS (serie 5500), datos y PDF, en Revit 2025, 2026 y 2027.
**Código:** `feature/ra-ui-v2` @ `aaab831`; `develop` @ `aaab831` (cherry-pick).
**Modelos (copias de prueba, ninguno guardado):** "Rebar test 2026" (Revit 2026.5); "Rebar test 2027 (copia de 2026)" (2027.3); "Rebar test 2025 (copia de 2024)" (2025.5).
**Evidencias:** `fase3/` (CSV, PDF y PNG por versión), `fase3/csv_M4_formula2/` (M4), `fase3/T12_9_2027/`, `fase3/T10_11_2027/`, `fase3/T10_11_2025/`.

## Veredicto (actualizado el 25-10-2026, ver §7)

| Conjunto | Veredicto |
|---|---|
| Modelo de referencia 2026 (planos 4501–4506 y BBS 5500–5512) | **APTO CON OBSERVACIONES** |
| Plugin en Revit 2027 (copia) | **APTO CON OBSERVACIONES** |
| Plugin en Revit 2025 y 2024 (copias, modelo con otras tipologías) | **APTO CON OBSERVACIONES**: los 5 A3 están cerrados |
| **Emisión general del plugin** | **APTO CON OBSERVACIONES** |

Las observaciones son las siguientes:
- **m1**, aceptado como menor: líneas de referencia que cruzan cotas o líneas indicadoras; 4 en el modelo de 2026 y 7 en el de 2024/2025.
- Las limitaciones acordadas: M1, M6 y m4.
- **Modelos 2024, 2025 y 2027:** 3 cercos de forma 51 (F10-06, PC10-05, B12-10) se crearon antes de M5 y no tienen patillas. Hay que rearmarlos con el plugin actual.
- **Copia de 2025:** mantiene la fórmula de peso antigua, que solo se corrigió en la plantilla y en 2026.
- m6 y la fusión de la interfaz v2 en develop quedaron hechas (§7).

"Con observaciones" significa que no quedan errores de datos (BBS) ni de marcas. Lo que queda abierto son defectos menores de composición, documentados y aceptados por el usuario (m1), y limitaciones acordadas (M1, M6, m4).

## 1. Datos: BBS y marcas

| Comprobación | 2026 | 2027 | Método |
|---|---|---|---|
| Filas de BBS trazadas al modelo | 92 / 92 | 92 / 92 | `ra_bbs_crosscheck.py` |
| Problemas del cross-check | 0 | 2 (\*) | idem |
| Peso = longitud programada (redondeada a 25 mm) × π/4·d²·7850 (±0,05 kg) | 92 / 92 | — | `m4check.py` sobre CSV |
| Peso y longitud impresos en el PDF iguales a los datos | 92 / 92 | — | texto de los 7 PDF |
| Marcas que no muestran su marca (A8) | 0 | 0 | revisión automática |
| Líneas indicadoras sobre una barra (A9) | 0 | 0 | revisión automática |

(\*) Los 2 avisos de 2027 son cercos cerrados de forma 51 (PC1-04 y B2-07). La copia de 2027 se hizo del modelo guardado el 19-10, anterior al rearmado con patillas (M5). No es un fallo del plugin en 2027: el modelo de 2026, ya rearmado, da 0.

**M4 queda cerrado.** El usuario cambió la fórmula de "Total weight (Kg)" en la plantilla v30 y en las BBS de 2026, usando `roundup(Bar Length / 25 mm) * 25 mm`. Las 92 filas cuadran con la fórmula en los datos y en el PDF.
- **Nota:** 4 filas difieren de la tabla de masas de BS 4449 en ≤ 0,21 kg sobre 200–450 kg (≤ 0,05 %). Es el redondeo de la tabla frente a π/4·d²·7850; es aceptable y queda documentado.

## 2. Planos: revisión automática (A1–A9) y PDF

| Versión | Incidencias | Detalle |
|---|---|---|
| 2026 | 4 (a veces 5) | m1: 4 líneas de referencia que cruzan cotas o líneas indicadoras en S1; de forma intermitente, 1 más en W1 |
| 2027 | 4 (a veces 5) | las mismas m1 que en 2026; el A3 de B1 hallado en 2027 está corregido (§3) |
| 2025 | 12 | 7 A4 (m1, en S1 superior e inferior y en S10) y **5 A3 abiertos** (§4) |

**m1 (menor, documentado; el usuario decidió no insistir en esta fase).** Los 4 cruces de S1:
1. La línea de referencia del juego 08 cruza una línea indicadora larga.
2. La barra suelta 1H16-12 cruza esa misma línea.
3. La barra suelta 1H16-12 cruza la línea indicadora del juego 04.
4. La línea de referencia del juego 04 cruza la línea indicadora del juego 01.

En todos los casos la línea indicadora atraviesa la losa entera. No hay salida sin cruce que no cree un punto sobre la línea de la sección B (se probó y se revirtió). El cruce adicional de W1 aparece en algunas regeneraciones y no en otras. Es de la misma naturaleza: una línea de referencia sobre una línea indicadora de todo el muro.

## 3. Cambios de esta sesión (verificados en Revit y publicados en develop)

| Id | Cambio | Verificación |
|---|---|---|
| T10.11 / 2027 | La marca de extremo de una barra inclinada se aparta de la barra. Se mide con la caja real de la etiqueta, que Revit dibuja más alta que el texto. | El A3 de B1 desaparece en 2027 y no se pierde ninguna etiqueta (564). En 2026, sin regresión. |
| Paquete BBS | Las hojas 5500 en adelante se archivan en "5500's - RC schedules"; los planos siguen en "4500's - RC details". | Las 7 hojas BBS de 2026 aparecen en el paquete nuevo. |
| **T12.9** | **"Actualizar" o "Regenerar" planos existentes.** Ver detalle abajo. | Escenario en Revit 2027, más abajo. |
| T12.8 en develop | Faltaba en develop la revisión automática en la ventana de "Create views". | Cherry-pick `0afadc9`. |
| T8.55 | Matriz de capacidades de la API medida en 2025, 2026 y 2027. | `docs/REVIT_CAPABILITIES.md`. 2027 sustituye `RebarHookOrientation` por `BarTerminationsData`, y el motor ya contempla los dos. |

**T12.9: qué hace**
- Cada vista y cada hoja guardan un registro en Extensible Storage: recorte, escala, posición en la hoja y la huella de cada anotación con la firma de sus barras.
- Al crear planos de miembros que ya tienen planos, el plugin pregunta si actualizar o regenerar.
- **Actualizar conserva** lo que es del usuario:
  - los viewports movidos;
  - los recortes y escalas cambiados;
  - las anotaciones propias;
  - las etiquetas movidas cuya barra no ha cambiado.
- Lo que el usuario cambió sigue siendo suyo en las actualizaciones siguientes.
- Si se movió una etiqueta y su barra cambió, la etiqueta se recoloca y se informa de ello.
- Las marcas existentes se conservan y solo se numeran las barras nuevas.
- Las dos opciones reutilizan las hojas del plano, así que se conservan los datos del cajetín.
- Nunca se duplican vistas. Todo va en un TransactionGroup: ante cualquier error se deshace entero, y así se comprobó en vivo.

**Escenario de T12.9 en Revit 2027 (copia)**
1. Regenerar sobre planos existentes:
   - mismas 14 hojas con los mismos ids;
   - 40 vistas y ninguna duplicada;
   - quedan registradas 40 vistas y 6 hojas.
2. Cambios manuales simulados:
   - 2 etiquetas movidas en B1 Elevation, de barras sin cambios;
   - viewport de S2 Plan desplazado;
   - recorte de C1 Section 1-1 ampliado;
   - nota propia en C1 Elevation;
   - en una prueba previa, una etiqueta de cercos movida y su juego modificado (de 17 a 14 cercos).
3. Actualizar:
   - se conservan las 5 modificaciones, con las posiciones exactas comprobadas en el modelo;
   - la etiqueta de los cercos modificados se recoloca y ya dice "40H8-08 LINKS".
4. Segundo Actualizar sin cambios: se conservan las mismas 5 modificaciones (idempotente).
5. Resultado: A3 = A8 = A9 = 0 y el cross-check del BBS sale limpio (salvo los 2 avisos conocidos de la copia).

Durante la prueba aparecieron y se corrigieron 4 fallos:
- Revit no admite "~" en un número de hoja.
- Algunas hojas se tomaban por vistas porque `ViewSheet` hereda de `View`.
- La posición del viewport se medía por el centro de la caja, que cambia al añadir una nota.
- El registro perdía el carácter "del usuario" en la segunda actualización.

Todos tienen pruebas unitarias (`tests/test_drawing_update.py`).

**Pruebas:** 246 de la raíz y 273 del plugin, todas en verde.

## 4. Abierto

| Id | Estado | Detalle |
|---|---|---|
| **A3 en 2025** | **Abierto: bloquea la emisión** | 4505 F10 Section B-B: dos marcas "06" (cercos de las esperas del pilar) sobre la barra 1563185. 4505 F10 Plan: una etiqueta sobre la marca de sección B. 4507 B1-B3 Elevation: dos etiquetas sobre la rejilla C (zona de solape). Son tipologías que el modelo de 2026 no tiene; las páginas están en `fase3/T10_11_2025/pdf`. |
| m1 | Documentado (decisión del usuario) | §2 |
| m6 | Pendiente | Composición de las hojas A1: grandes zonas vacías; la 4503 (S2) queda casi vacía. Cambiar la composición puede mover todo lo ya verificado, así que conviene decidirlo con el usuario. |
| T8.57 | Bloqueado | El modelo de regresión por script exige el proyecto de pruebas "Project1" con las familias NOSA en cada versión; en 2025–2027 no existe. |
| T8.55 (resto) | Pendiente | Pruebas en vivo de manguitos y mallas en 2025–2027: necesitan el mismo contenido de pruebas. |
| T8.27, T8.58, T7.1–T7.4, T7.8 | Pendientes de revisión visual del usuario o de desarrollo nuevo | Según `MASTER_ROADMAP.md`. Ninguna afecta a los planos auditados. |
| Divergencia de develop | Observación | El `tab_tools.py` de develop no tiene la sección "Phase 11" (capas, marcas, copias y emisión) que sí está en la rama. Es anterior a esta sesión; conviene alinearlo antes de cualquier fusión. |

## 5. Limitaciones aceptadas por el usuario

- **M1:** el cajetín no se rellena; imprime los valores por defecto (Author, Checker, Client X). La fecha del cajetín sale de la plantilla en formato m/d/aa (10/18/26), no en dd/mm/aa: es un dato de la plantilla.
- **M6:** orden 03a, 03aa… 03b en el BBS de los juegos variables de más de 26 barras.
- **m4:** el Grand total suma "No. of bars in each".
- **Cimentaciones:** recubrimiento de 40 mm, con su aviso visible en el plano.
- **Revit 2024:** no se ha repetido la verificación en 2024; la instancia abierta tiene la plantilla v30, no el modelo de pruebas.

## 6. Para cerrar la emisión

1. Corregir los 5 A3 de la copia de 2025 (F10 y B1-B3), con pruebas de regresión, y volver a verificar 2025, 2026 y 2027.
2. Decidir m6 con el usuario.
3. Alinear develop con la rama (sección "Phase 11").

## 7. Cierre del 25-10-2026

**Código:** `feature/ra-ui-v2` @ `66210b5`; `develop` @ `f841912`. Pruebas: 249 (raíz) + 276 (plugin), todas en verde. Develop, comprobado aparte: 246 + 266.

### Defectos corregidos y verificados

| Id | Causa y corrección | Verificación |
|---|---|---|
| A3 F10 Section B-B (×2) | Las marcas de barra cortada no evitaban las barras dibujadas en la vista. Ahora se apartan a un lado y, si no basta, hacia fuera. | 2025 y 2024: 0 A3. PDF de F10. |
| A3 F10 Plan | La planta de un miembro mostraba las marcas de vistas de otros miembros (el alzado de C3). Ahora solo muestra las de sus propias secciones. | PDF de F10 (se mantienen A y B). Plantas de 2026 con sus secciones propias. |
| A3 B1-B3 "04" | La flecha de extremo se alarga hasta que el texto quede al otro lado de la rejilla. | PDF de B1-B3 |
| A3 B1-B3 "129H8-11 LINKS" | El rótulo total de cercos y las cantidades por zona se apartan de las rejillas dentro de su tramo. | PDF de B1-B3 |
| Nombres "(2)" | Al renumerar las secciones de un plano, una chocaba con otra todavía sin renombrar. Ahora se renombran en dos pasos. | 2025 y 2024: 0 nombres numerados |
| **Revit 2027, barras FreeForm** | `Rebar.CreateFreeForm` cambió de firma en 2027: ahora recibe un `RebarStyle` y devuelve un `RebarFreeFormCreationResult`. Las vigas curvas perdían sus barras superiores e inferiores, y los muros curvos y los bordes curvos de losa se partían en barras sueltas. `create_free_form` admite las dos firmas. | T8.57: los 12 casos de 2027 son idénticos a los de 2025 y 2026 |

Cada corrección tiene prueba de regresión.

### Verificación final por versión

| Versión (modelo) | Planos: incidencias | A3 / A8 / A9 | BBS trazado | Peso (π/4·d²·7850) | PDF BBS |
|---|---|---|---|---|---|
| 2026 (Rebar test 2026) | 4, todas m1 | 0 / 0 / 0 | 92 / 92, 0 problemas | 92 / 92 | 92 / 92 |
| 2027 (copia de 2026) | 4, todas m1; T12.9 conserva los 5 cambios | 0 / 0 / 0 | 92 / 92, 2 avisos (\*) | — | — |
| 2025 (copia de 2024) | 7, todas m1 | 0 / 0 / 0 | 72 / 72, 3 avisos (\*) | 70 / 72 (\*\*) | — |
| 2024 (copia) | 7, todas m1 | 0 / 0 / 0 | 72 / 72, 3 avisos (\*) | — | — |

(\*) Cercos de forma 51 creados antes de M5 (patillas). Hay que rearmar esos miembros; no es un fallo del plugin actual.
(\*\*) La copia de 2025 conserva la fórmula de peso antigua; la nueva solo está en la plantilla v30 y en 2026.

### Tareas

| Tarea | Estado |
|---|---|
| T8.57 | **Hecha en 2025, 2026 y 2027.** Se ejecuta en un proyecto nuevo creado desde una copia local de la plantilla v30 y cerrado sin guardar. Los 12 casos se arman sin errores en 34–45 s. Destapó el defecto de 2027. |
| T8.55 | Matriz de 2025–2027 hecha. Faltan las pruebas en vivo de manguitos y mallas, que necesitan un pilar con el manguito NOSA y un forjado en el proyecto de pruebas. |
| T10.11 | Hecha en 2024, 2025, 2026 y 2027 |
| MCP en Revit 2027 | Retirado HuskyBIM, el único MCP externo, a `Documents\NOSA_addins_retirados\2027` (se puede revertir). Quedan RvtMcp (Bimwright) y el Autodesk Assistant de Revit. El "Revit-AI-Chatbot" no carga en 2027: solo declara hasta 2026. |
| m6 | **Hecho (decisión del usuario: llenar cada hoja antes de abrir otra).** Cada miembro puede dibujarse también con sus secciones en columna junto a la planta o el alzado, y toma la primera forma que quepa en una hoja ya empezada. Revit 2025: F10 y PC10 comparten la 4505, y la 4506 y su BBS 4506-01, vacías, se eliminan (una BBS emitida se conservaría, con aviso). En 2026, S2 no cabe en la 4502 de ninguna forma (el hueco mide 350 × 196 mm y su planta 229 × 202), así que sigue en la 4503. |
| Fusión de la interfaz v2 en develop | **Hecha (decisión del usuario):** merge `18cf92e`. Develop es igual a la rama; pruebas 249 + 276 en verde. |
| T8.27, T8.58, T7.1–T7.4, T7.8 | Pendientes de revisión visual del usuario o de desarrollo nuevo |
