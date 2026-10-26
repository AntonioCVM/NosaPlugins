# RebarAutomate — Fases 1 y 2 de cierre de la auditoría (24-10-2026)

**Modelo:** "Rebar test 2026" (Revit 2026.5), copia de pruebas autorizada. No se ha guardado.
**Código:** `feature/ra-ui-v2` @ `7a01c04`, `develop` @ `2ea04e6`.
**Evidencias:** `fase2/csv` (8 BBS y `audit.json`), `fase2/pdf` (13 páginas), `fase2/png`.

## Resumen ejecutivo

Las incidencias críticas siguen cerradas y se han cerrado M2, M5, M7, m2, m3 y m5, además del caso de etiqueta incorrecta que indicó el usuario (barra con IfcGUID `3wZ52$FYT0DhddRBdCS4zI`).

Estado verificado de la documentación:

| Comprobación | Resultado |
|---|---|
| Filas de BBS trazadas al modelo | 92 / 92, 0 problemas (`ra_bbs_crosscheck.py`) |
| Etiquetas que no muestran su marca (A8) | 0 |
| Marcas que designan dos barras distintas en un mismo plano | 0 |
| Cercos cerrados sin patillas | 0 |
| Nombres con "(2)" | 0 |
| Notas que citan un BBS ajeno a su plano | 0 |
| QA fallido impreso en un plano | 0 |
| Revisión automática | 6 incidencias menores: líneas de referencia sobre cotas o líneas indicadoras (4 en S1, 2 en W1) |
| Suites de pruebas | 233 + 272 OK |
| Páginas exportadas e inspeccionadas | 13 / 13 (6 A1, 7 A4) |

**Veredicto: APTO CON OBSERVACIONES; todavía NO APTO PARA EMISIÓN.** Faltan:

- **Decisiones 1 y 2** (recubrimiento de 50 mm y C40/50 en pilares): se aplicarán en T12.6, por decisión del usuario.
- **M4 y m4:** dependen de una edición en la interfaz de Revit que la API no permite (ver más abajo).
- **M1:** según la decisión del usuario, el cajetín no se rellena. No impide emitir desde el plugin, pero los planos imprimen los valores por defecto de la plantilla (Author, Checker, Client X).

## Incidencias cerradas en esta fase

| Id | Cambio en el plugin | Verificación | Dónde se ve |
|---|---|---|---|
| Etiqueta de S3-06 (usuario) | Un juego FreeForm de barras rectas y paralelas alineadas en 3D se anota con un MRA (anotación multibarra) y no con una línea suelta. Las barras en arco (B2) y en muro curvo (W2) conservan su tratamiento. | MRA en los 3 juegos de S3, sin líneas sueltas; PDF de S3, W2 y B2. Hubo una regresión intermedia (B2 y W2 sin etiquetas), detectada en el PDF y corregida. | 4502 |
| M2 | Un control de construibilidad con errores pasa a la revisión automática y no se imprime en el plano. | Las notas de 4501 y 4506 ya no lo imprimen. | 4501, 4506 |
| M3 (parte) | Las losas se comparan con el recubrimiento de losas de las notas (40). | Ha desaparecido el falso aviso en 4502 y 4503. | revisión |
| Decisión 5 | Las barras en arco (forma 67) no se rotulan como "LINKS". | PDF de W2. | 4504 |
| M7 | Cada hoja de un plano lleva su propio NOSA_Rebar_Group y sus propias notas. | Se genera el BBS 4503-01 (hoja 5506); las notas citan solo su BBS. | 4503, 5506 |
| m5 | Las hojas de varios planos se nombran por sus miembros: "Slabs reinforcement - S1, S3" y "Slabs reinforcement - S2". Las vistas no reciben "(2)". | El cross-check no encuentra nombres numerados. | 4502, 4503, todas las vistas |
| m3 | Las elevaciones ocultan los elementos que no tocan los miembros dibujados. | Ha desaparecido la franja de F1 bajo "W2 Elevation" (PDF). | 4504 |
| M5 / decisión 4 | Los cercos de vigas curvas y los lacers de encepado se crean con patillas de 135° (forma 52). | Primero un ensayo con rollback (barras principales idénticas) y después el rearmado de B2 y PC1. B2-07 queda como 52 (515/215/115/115); PC1-04 como 52 (1910/1910/160/160). | 4505, 4506 y sus BBS |
| m2 | La marca del cerco sale por una cara libre cuando las filas de marcas tapan su rama principal. La auditoría detecta líneas de referencia que cruzan un texto. | PDF de C1–C3 y de PC1. | 4501, 4505 |

## No aplicadas, con su motivo

- **m1** (líneas de referencia sobre cotas o líneas indicadoras en S1 y W1). Se probó a ampliar la búsqueda del layout:
  - S1 pasó de 4 cruces a 1, pero un punto quedó sobre la línea de la sección B (incidencia A3 nueva).
  - Al penalizar ese caso, volvía a 4 cruces.
  - Por la regla de no reintroducir incidencias, se revirtió. Queda como **menor**: son cruces con líneas de cota o indicadoras, no con otras líneas de referencia.
- **M6** (orden 03a, 03aa…03b en el BBS):
  - Revit numera las barras de un juego variable con letras y ordena el sufijo como texto.
  - La única solución es partir los juegos de más de 26 barras en dos marcas, lo que cambiaría marcas y filas ya verificadas de S3.
  - **No se aplica**, por la regla del usuario.
- **M4** (peso por longitud de cálculo) **y m4** (Grand total que suma "No. of bars in each"):
  - La API de Revit no permite crear ni editar fórmulas de una tabla de planificación.
  - El cambio exacto es editar el campo calculado "Total weight (Kg)" de la tabla maestra **BBS**, en la plantilla v30 y en el modelo, con la fórmula `Total quantity * Bar Length / 1000 mm * (Bar Diameter / 1 mm)^2 * 0.00617`. Es la masa nominal de BS 4449, d²/162.
  - Para m4 no hay en Revit un total por campo que excluya solo el Grand total sin perder la suma por fila.
  - Requiere una acción manual en la interfaz, o la autorización del usuario para automatizar clics en Revit, algo que hasta ahora se ha prohibido.

## Pendiente (Fase 3)

1. **T12.6:** recubrimiento de 50 mm en pilares, vigas y muros, y C40/50 en los tipos de pilar. Exige rearmar el modelo de pruebas.
2. **T12.9:** actualizar en lugar de regenerar. Hay que conservar las posiciones de los viewports, las anotaciones propias, las etiquetas movidas y el recorte y la escala.
3. **T10.11:** pruebas en Revit 2025 y 2027, sobre copias, con autorización.
4. **T8.27, T8.55, T8.57 y T8.58**, y lo que queda de T7.x.
5. **m6:** composición de las hojas A1. La 4503 queda casi vacía.

## Incidente de la sesión

Una limpieza de un worktree temporal con una variable vacía borró archivos de este worktree:

- Los archivos versionados se recuperaron con git.
- `AGENTS.md`, `.agents` y `.codex` se recuperaron de la carpeta principal.
- Se perdieron sin remedio el Excel de la auditoría del 18-10 y las evidencias iniciales de esta auditoría.
- Desde entonces todas las rutas se validan antes de borrar (registrado en memoria).
