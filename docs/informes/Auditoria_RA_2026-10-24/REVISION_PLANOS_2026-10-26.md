# Revisión de presentación de planos — registro de cambios (2026-10-26)

Pruebas en Revit 2026 (copia, pid 8584), proyecto nuevo sin guardar desde la plantilla v30 copia, edificio de 1 planta (`building_test.py`, STOREYS = 1). La tolerancia de la auditoría no se ha cambiado. Ninguna comprobación se ha desactivado.

Commit local `1e243b9` (no subido).

## Resumen antes / después (1 planta)

| Comprobación | Antes (`nosa_a9_s1`) | Después (`nosa_fix3_s1`) |
|---|---|---|
| A9 línea de indicación sobre una barra | 162 (135 pilares + 27 escalera) | 18 (6 pilares de borde × 3 tramos) |
| A7 vista fuera del cajetín | 1 (planta superior de losa a x = 927 mm) | 0 |
| Vistas fuera del área útil del A1 (25–715 × 25–575 mm) | 8 | 0 |
| Vistas solapadas entre sí | 2 | 0 |
| A3 rótulo sobre rótulo en alzados de viga | 12 | 0 |
| Total de avisos de la revisión | 215 | 191 |

## Cambios

### 1. A7: planta superior de losa fuera de la hoja (4516–4519 en 4 plantas; 4508 en 1 planta)

- **Causa.** `view_plan.layout_packed` maquetaba cada losa como un bloque: planta inferior + planta superior lado a lado (441 + 441 + 20 = 902 mm) con sus secciones debajo. El área útil del A1 mide 690 mm. El bloque no cabía en ninguna hoja de ninguna forma y se colocaba igualmente, con la planta superior hasta x = 927 mm.
- **Corrección.** Si un bloque no cabe en una hoja vacía de ninguna forma, se divide (`_split_to_fit`): la planta inferior con sus secciones y la planta superior en la hoja siguiente. No se reduce la escala; es el criterio vigente para dibujos de varios miembros. Una vista que no quepa en ninguna hoja usa la hoja vacía disponible en lugar de dejarla en blanco.
- **Evidencia.** S1 pasa a 4505 (planta inferior + secciones A-A y B-B) y 4506 (planta superior). Prueba: `test_packed_block_too_wide_for_a_sheet_is_split_not_run_off`.

### 2. Vistas que crecen después de maquetar (fuera del área útil y solapadas)

- **Causa.** Las notas "SEE DRG nnnn" de las barras de otros miembros (`foreign_bars`) se escriben cuando ya todos los dibujos tienen número, es decir, después de maquetar. La vista crece unos 20 mm.
  - B1-B2 Elevation (4510) pasó de x = 25 a x = 5 mm, sobre el margen, y quedó encima de B5-B6 Elevation.
  - Lo mismo ocurrió con B3-B4/B7-B8 (4509), B9-B10, B11-B12 y las secciones A-A/B-B de S1.
- **Corrección.** `rebar_views._keep_inside` (con `view_plan.push_inside`) desplaza en horizontal lo mínimo las vistas que han crecido, para que queden dentro del área útil y separadas entre sí y de las leyendas. Si una fila no cabe, no mueve nada y el aviso queda.
- **Auditoría.** El A7 comprueba ahora el área útil del A1 y no solo el borde del papel. La caja del cajetín empieza en (12,06; 10,90) mm, por lo que se usa `A1_AREA` en coordenadas de hoja. Es un criterio más estricto, no más laxo.
- **Evidencia.** Vistas fuera del área útil: 8 → 0. Solapes: 2 → 0. Pruebas: `test_viewports_grown_after_the_layout_are_pushed_back_inside` y dos más.

### 3. A9: línea de cercos sobre la barra central en los alzados de pilar

- **Causa (medida con `tools/revit_harness/mra_line_probe.py`).** Para los cercos de todos los pilares, `free_junction` no encontraba ninguna posición libre en ninguno de los 34 candidatos, y la línea se quedaba en el eje, encima de la barra vertical central mostrada (por ejemplo, el pilar C1: MRA 1514810, dimensión 1514808, sobre la barra 1513652). Lo bloqueaban dos cosas:
  - **Cercos de viga fuera de la vista.** Eran cercos de las vigas que entran de frente, a x = ±90 mm, más allá del plano lejano de la vista. El colector de la vista los devuelve por su caja envolvente, pero no se dibujan. La auditoría sí recortaba por profundidad; la colocación no.
  - **Falta de hueco real en los pilares de borde.** El cerco de la viga sí está dentro de la vista, en la cota de la viga (2456–2816). A 1:50, el criterio de 1 mm en papel exige 50 mm a cada lado, y entre la barra central (x = 0) y la pata del cerco (x = 90) solo hay 90 mm.
- **Correcciones.**
  - `_seen_bars` recorta por la profundidad de la sección, con la misma función que la auditoría (`_depth_range` / `_within_depth`, compartidas).
  - Si ninguna posición queda libre, la línea va donde menos recorrido comparte con barras (`presentation.least_along`) y no encima de una barra en toda su altura.
- **Evidencia.**
  - Pilares interiores de fila (C2, C5, C8): sin avisos. La línea pasa a x = −54 mm.
  - Pilares de borde (C1, C3, C4, C6, C7, C9): de 15 tramos sobre la barra principal a 3 tramos junto a la pata del cerco de la viga, solo en los 340 mm del canto. Es una limitación geométrica a 1:50 y queda señalada.
  - Pruebas: `test_where_no_place_is_clear_the_line_shares_least_with_the_bars` y `test_along_length_merges_overlapping_bars`.

### 4. A9: plano de escalera ST1 (27 avisos)

- **Causa.** A 1:50, las barras superiores e inferiores de los tramos se ven en planta a 91 mm, menos de 2 × 50 mm, así que no cabía ninguna línea de reparto a 1 mm en papel de ambas. Además, el plano salía pequeño en una hoja casi vacía.
- **Corrección.** El plano de escalera se dibuja primero a 1:25 (`view_plan.SCALES['stair_plan']`), como las secciones de losa (SMDSC 4.ª ed. 3.5: escalas de detalle). Si no cabe, pasa a 1:50 o 1:100.
- **Evidencia.** A9 en la escalera: 27 → 0. Prueba: `test_stair_plan_at_1_25_when_it_fits`.

### 5. A3: textos de zona de cercos montados en alzados de viga

- **Causa.** Cada texto "(n@paso)" se centraba sobre su zona sin comprobar los de su misma fila. En B1-B2, "(16@200)" y "(12@100)" de una zona corta junto al apoyo se superponían ("(16@1220100)").
- **Corrección.** `presentation.spread` pone los textos de una fila uno junto a otro, con hueco, centrados donde querían estar.
- **Evidencia.** Rótulo sobre rótulo en alzados de viga: 12 → 0. Comprobado en el PDF de 4510. Pruebas: `test_zone_texts_on_one_line_are_kept_apart` y `test_spread_merges_runs_until_nothing_touches`.

### 6. Regresión de geometría corregida: zonas de cercos de viga desplazadas (commit `947c985`)

- **Hallazgo.** Comparando el PDF de B5-B6 con el de una ejecución anterior. Desde `6d58a08` (ajuste de cercos cerrados con `ScaleToBox`), los juegos de cercos de viga salían hacia el otro lado de su primera barra.
  - En B1-B2: 12@100 en −825..275 mm en lugar de 275..1375, y 16@200 cruzando el apoyo central.
  - 16 de los 24 juegos de 1 planta tenían cercos dentro de un pilar.
  - La BBS no lo detectaba, porque cantidades y longitudes no cambian.
- **Corrección.** Tras cada `ScaleToBox`, si la última barra del juego ha pasado al otro lado de la primera, el juego se rehace en su lado con la misma regla, número y separación (`_flip_side`), y la primera barra vuelve a su plano. Además, el reajuste solo mueve el cerco dentro de su propio plano.
- **Evidencia (`tools/revit_harness/beam_link_zones_probe.py`).**
  - Vigas de 1 planta y de 4 plantas: zonas en 275..1375 / 1500..4500 / 4625..5725, iguales que antes de `6d58a08`, y 0 juegos dentro de pilares.
  - Pilares: cercos en 55..2945 mm sobre la base, sin ninguno fuera del pilar.
  - El ajuste a 360 × 360 de los cercos de pilar se conserva (`link_corner_probe`: −180..180).

### 7. Nota "SEE DRG" cruzada por la barra del pilar extremo (commit `947c985`)

- **Causa.** La nota solo evitaba textos. Además, la barra vertical del pilar recorre toda la altura, así que ninguna posición a la misma distancia quedaba libre.
- **Corrección.** La nota se aleja más allá de las barras verticales que la cruzan, sobre su línea desde la barra. Si aun así no hay sitio, se mantiene la colocación anterior.
- **Evidencia.** "SEE DRG 4527" en B5-B6 ya no está cruzada (comprobado en el PDF).

### 8. Retirado: recorte por profundidad en `_seen_bars` (commit `cb3bf92`)

- Se introdujo en el punto 3 y provocaba rótulos sobre barras cortadas en secciones de viga.
- Prueba A/B en 1 planta (`seen_bars_old_probe.py`): 8 avisos con el recorte y 0 sin él.
- No aportaba nada al A9 de pilares: 12 en ambos casos, porque la mejora la da `least_along`.
- En 4 plantas: 168 → 56, el mismo valor que antes de los cambios.

## Verificación de 4 plantas (Revit 2026 copia, instancia nueva pid 96524)

| | Antes (`nosa_v3_s4`, 08:19) | Después (`nosa_v6_s4`, 12:57) |
|---|---|---|
| Avisos de la revisión de planos | 803 | 481 |
| A9 línea de indicación sobre barra | 378 | 72 (pilares de borde, 3 tramos cada uno) |
| A7 fuera del cajetín / del área útil | 4 | 0 |
| Vista sobre vista (A3) | 12 | 0 |
| Vistas fuera del área útil o solapadas (medido en `audit.json`) | 43 | 0 |
| A3 restantes | 233 | 225 |
| A4 | 188 | 184 |
| Hallazgos de la QA de armado | 2852 (`nosa_v4_s4`) | 2354 |
| Juegos de cercos de viga dentro de pilares | (no medido) | 0 de 24 en la muestra de vigas |
| BBS | 43/43 filas | 43/43 filas; 4 diferencias de peso de 0,1–0,6 kg (masa por densidad de la plantilla, ≤0,1 %) |
| Inventario | 36 hojas / 39 PDF, 0 problemas | 36 hojas / 39 PDF, 0 problemas |
| Tiempo total | 2804 s | 2188 s (planos 1954 s; anotación 1407 s) |
| Memoria privada | pico 6,4–6,7 GB (instancia de larga duración) | 4,76 → 5,27 GB (+0,5 GB en toda la ejecución) |

La nota de construibilidad de cada plano refleja la QA actualizada: grado C en todos, con 530 a 961 errores según el grupo. Así que **no es APTO**. Siguen abiertos los choques reales de nudos viga–pilar (pendientes de tu aprobación de reglas) y los de las L de coronación de pilares de borde.

## Pendiente (avisos que quedan en 1 planta, 191)

| Avisos | Categoría | Vista |
|---|---|---|
| 20 | A3 rótulo sobre barra | Alzados de viga (por ejemplo, "03" sobre la barra superior junto a la marca de sección 1 y "SEE DRG 4509" cruzado por la barra del pilar extremo en B1-B2) |
| 12 | A3 | Sección B-B de losa |
| 10 | A3 rótulo sobre rótulo | Planta inferior de losa |
| 9 + 8 | A4 / A4i | Planta inferior de losa (líneas que cruzan cotas) |
| 6 | A4i | Planta superior de losa |
| 18 | A9 | Pilares de borde (limitación a 1:50, descrita en el punto 3) |

Problemas vistos en los PDF que la auditoría automática no detecta:
- **Forjado de la planta inferior en los alzados de viga de plantas altas.** Aparece cortado como una franja bajo la cadena de cotas, sobre "SUPPORT" (por ejemplo, B5-B6 en 4525). Ya existía antes de estos cambios; el recorte inferior de la vista llega al forjado de abajo.
- **Rotulaciones sobre la escalera vecina.** En la planta inferior de losa S1, tres rotulaciones de la derecha caen sobre el dibujo de la escalera, que queda dentro del recorte.
- **"03" sobre la barra superior.** En los alzados de viga, el rótulo "03" de las barras de solape queda encima de la barra superior, junto a la marca de sección.
- **Nombres de hoja repetidos.** Las plantas inferior y superior de una losa quedan en hojas distintas con el mismo nombre ("Slabs reinforcement - S1").

Pruebas unitarias: 442 + 271 correctas. Fallan 2 pruebas de `test_stair_rebar.py` que ya fallaban antes de estos cambios; esos archivos no se han tocado.
