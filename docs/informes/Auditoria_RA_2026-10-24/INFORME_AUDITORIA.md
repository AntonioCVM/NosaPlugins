# Auditoría documental RebarAutomate — 24-10-2026

**Versión revisada:** RebarAutomate v2.0.0 + fase 12. Rama `feature/ra-ui-v2` @ `4c73fab`, `develop` @ `6089384`.
**Modelo:** "Rebar test 2026" (Revit 2026.5), copia de pruebas autorizada. Unidades: mm. No se ha guardado ni sincronizado.
**Alcance:** los planos 4501–4506 y los BBS 5500–5510 generados por el plugin, identificados por el número de plano (series 45xx y 55xx), por los parámetros NOSA_Rebar_Group, NOSA_Rebar_Assembly y NOSA_BBS_* y por el registro de generación. No se ha tocado documentación ajena al plugin.

## A. Resumen ejecutivo

**Veredicto: APTO CON OBSERVACIONES** para revisión técnica. **NO APTO todavía para emisión** mientras no se cierren M1–M3, que dependen de datos del proyecto y de validación técnica.

Al empezar, la documentación **no era apta**. Había 4 incidencias críticas en las que planos y BBS describían barras distintas, y cualquiera de ellas podía llevar a fabricar mal. Las cuatro tenían su causa en el plugin. Se ha corregido el generador, no los planos a mano, se han añadido pruebas de regresión y se ha regenerado y verificado todo:

- en Revit;
- en los BBS exportados a CSV;
- en los PDF.

## B. Cobertura

| Elemento | Revisado / total |
|---|---|
| Planos RC (A1) | 6 / 6 |
| BBS colocados (A4) | 6 / 6 |
| BBS sin colocar | 1, el maestro "BBS" de la plantilla: fuera del alcance, sin filtro de plano |
| Páginas PDF exportadas e inspeccionadas | 12 / 12, página completa |
| Ampliaciones de zonas densas | 4501, 4502, 4504 y 4506 |
| Filas de BBS contrastadas con el modelo | 92 / 92 |

La fila W2-09 pertenece a la barra 1514206. La API devuelve "matched with multiple shapes" y no se puede leer, así que esa fila se ha verificado solo contra la etiqueta y el BBS.

## C. Matriz por plano y BBS (estado final)

| Documento | Técnico (datos) | Visual | Pendiente |
|---|---|---|---|
| 4501 Columns | Conforme: marcas = BBS 4501-01; miembros C1, C2, C3 ×3, C4, C5 | Conforme con observaciones | M1, M2, M3, m2 |
| 4502 Slabs | Conforme: S1 y S3 = BBS 4502-01 y 4502-02; marcas únicas en el plano | Conforme con observaciones | M1, M3, m1 (4 líneas de referencia sobre cotas en S1) |
| 4503 Slabs (2) | Conforme: S2 = BBS 4502-01 (01 ×20, 02 ×20, 08 ×60) | Conforme; hoja casi vacía | M1, M3, M7, m5, m6 |
| 4504 Walls | Conforme: W1 y W2 = BBS 4504-01 | Conforme con observaciones | M1, M3, m3, m7 |
| 4505 Foundations | Conforme: F1 y PC1 = BBS 4505-01 | Conforme | M1, M3, M5 |
| 4506 Beams | Conforme: B1–B4 = BBS 4506-01 | Conforme con observaciones | M1, M2, M3, M5 |
| BBS 4501-01 … 4506-01 | Cantidades, diámetros, formas y longitudes (redondeo a 25 mm por exceso) correctos | Legibles, sin cortes ni desbordes | M4, M5, M6, m4 |

## D. Incidencias por gravedad

### Críticas (todas corregidas y verificadas)

**C1. Las marcas de los planos no coincidían con las de los BBS.**
- Afectaba a:
  - 4502: S3 rotulaba "6H16-06(a to f)" para las barras que el BBS llama 03, y la marca 01 aparecía en dos barras distintas del mismo plano;
  - 4506: casi todas las marcas;
  - 4504: W2 "09" y "12".
- Causa: al emitir los BBS se renumeraba cada BBS por separado después de etiquetar, y las etiquetas guardaban el texto anterior en NOSA_Rebar_Callout.

**C2. 4501: los cercos de C2 y C3 llevaban la marca "03"**, que en el BBS es el cerco circular de C5.
- Causa: las copias de miembros idénticos (que no se listan en el BBS) no se renumeraban.

**C3. El nombre de miembro del BBS no coincidía con el plano.**
- En el BBS, "C1" era el pilar C4 y "C3 ×3" eran C1, C2 y C3.
- "F2" era el encepado PC1.
- B1–B4 estaban intercambiadas.
- Causa: nombres automáticos de partición asignados antes de que los elementos tuvieran Mark.

**C4. El rango de las barras variables no coincidía.** S3 rotulaba "(a to q)" y el BBS lista 01a…01ag (33 barras).
- Causa: el rango se calculaba por longitudes distintas y Revit asigna una letra a cada barra.

### Mayores (pendientes; requieren dato o decisión)

**M1. Cajetín y cabecera del BBS con valores de marcador:**
- Drawn by "Author", Checked "Checker", Approved "Approver", Designer "Designer";
- Status "Project Status", Client "Client X", "1st Rock Street", Job 12345;
- fecha en formato EE. UU. "10/24/26".

Son datos de Project Information y del formato regional. No los he cambiado.

**M2. Las notas de 4501 y 4506 imprimen "Buildability check: C (0/100; 14 error(s) …)".**
- Es un resultado de control de calidad negativo impreso en un plano de emisión.
- Hay que revisar el informe RC QA o no imprimir la línea al emitir.

**M3. Datos técnicos que debe validar el responsable:**
- Recubrimiento modelado de 40 mm frente a 50 mm en las notas generales, en todos los planos.
- Los pilares no tienen clase de hormigón en el material; se usa C40/50 de las notas.

**M4. Criterio de peso.**
- Revit calcula el peso con la longitud geométrica del modelo; el BBS imprime la longitud redondeada a 25 mm.
- Ejemplo: W2-06 imprime 30 × 1450 mm × 0,888 kg/m = 38,6 kg, pero la columna de peso dice 38,2 kg.
- No he cambiado la fórmula: hay que confirmar el criterio (BS 8666 o el propio).

**M5. Forma 51 con C = D = 0 y ceros en dimensiones que no aplican.**
- Forma 51 con C = D = 0 en PC1-04 y B2-07, y "0" en las columnas que no aplican de las formas 75 y 67.
- Es posible que falten los datos de las patillas para el taller. Requiere validación técnica.

**M6. Orden de las filas de barras variables en el BBS:** sale 03a, 03aa…03ag, 03b… porque se ordena como texto. Se lee mal (se arregla en la ordenación de la plantilla).

**M7. 4503 no tiene BBS propio.** S2 se traza al BBS 4502-01, porque su grupo de dibujo es 4502. Es trazable, pero poco habitual.

### Menores

- **m1:** 4 líneas de referencia sobre cotas en el plano S1 (zona densa del hueco) y 10 cruces A4i informativos.
- **m2:** en las secciones de C1–C3, la línea de referencia del cerco atraviesa el "01" central.
- **m3:** un rectángulo gris vacío bajo el título "W2 Elevation".
- **m4:** la fila Grand total sigue sumando "No. of bars in each" (72 frente a 120). Hace falta un campo calculado en la plantilla.
- **m5:** nombres con "(2)": "Slabs reinforcement (2)" y vistas "… (2)".
- **m6:** grandes zonas vacías en las hojas A1 (mitad derecha).
- **m7:** las barras en arco (forma 67) de W2 se rotulan "LINKS IN 2s". Hay que confirmar la terminología.

## E. Correcciones realizadas y comprobación posterior

Las correcciones están en `bar_schedules`, `rebar_marking`, `rebar_partitions`, `rebar_views`, `review` y `drawing_audit`:

1. Las marcas son únicas por plano en todos sus BBS, y el BBS conserva las marcas que ya llevan las etiquetas. Si tuviera que renumerar, también reescribe las etiquetas. Las copias de miembros idénticos se marcan igual que el original.
2. El rango de una barra variable cubre todas las barras que lista el BBS.
3. El nombre del miembro en el BBS es el Mark del plano cuando el nombre anterior era automático o era el Mark de otro miembro. Se admiten intercambios entre miembros, y cada cambio queda en la revisión automática.
4. El BBS ya no muestra "Grand total: N", que contaba elementos de Revit y no barras.
5. Nueva comprobación A8 en la revisión automática: avisa si una etiqueta imprime una marca distinta de la de su barra.

**Pruebas de regresión:** 6 nuevas. Resultado de las suites: raíz 232 OK y plugin 268 OK.

**Regenerado en Revit:**
- A8 = 0;
- 0 marcas que designen dos barras distintas en un mismo plano;
- 92/92 filas de BBS trazadas al modelo;
- revisión automática: de 5 a 4 incidencias.

Durante la verificación detecté un error en uno de mis propios arreglos. Al quitar los totales de "No. of bars in each", las filas mostraban "&lt;varies&gt;". Lo revertí y restauré esos campos en el modelo de pruebas.

## F. Mejoras pendientes del plugin

- Ordenar las barras variables de forma natural en el BBS (M6).
- Rellenar con ceros solo las dimensiones que aplican a cada forma (M5).
- No imprimir la nota de "Buildability check" con errores en una emisión (M2).
- Dar BBS propio a las hojas de continuación como 4503 (M7).
- Nombres sin "(2)" (m5).
- Mejorar la composición de las hojas A1 (m6).
- Resolver los cruces de referencias sobre cotas en S1 (m1).

## G. Pendiente de validación del responsable técnico

- Recubrimiento 40 frente a 50 mm.
- Clase de hormigón de los pilares.
- Criterio de peso del BBS.
- Formas 51 con patillas de 0.
- Terminología "LINKS" en barras en arco.
- Datos del cajetín.

Que los planos coincidan con el modelo demuestra coherencia documental; no certifica la seguridad estructural del diseño.

## H. Archivos

Carpeta `docs/informes/Auditoria_RA_2026-10-24/`:

- `csv/`: los 7 BBS exportados y `audit.json` (inventario de hojas, vistas, tablas y las 147 barras);
- `pdf/`: los 12 planos y BBS del estado final;
- `png/`: renderizados a 110 ppp.

**Pérdida de evidencias:** las evidencias del estado inicial (PDF, PNG y CSV de antes de las correcciones) se perdieron por un error mío al limpiar un worktree temporal. El estado inicial queda descrito en este informe y en el registro de la sesión.
