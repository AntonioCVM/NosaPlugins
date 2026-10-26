# L de coronación en pilares de borde: propuesta (pendiente de aprobación)

Estado: **propuesta, no aplicada**. No se cambia nada en el armado hasta que la apruebes.

## 1. El problema, medido

En un pilar que termina en una losa, `column_rebar.resolve_column_top` dobla las barras verticales en L dentro de la losa (SMDSC 4.ª ed. MD C4, detalle A):

- Altura del doblado: bajo la parrilla superior de la losa y su recubrimiento.
- Longitud de patilla: `max(anclaje − empotramiento, 12φ)` (`top_l_foot_mm`). El anclaje es la estimación de 40φ de `footing_rebar.default_anchorage_length_mm`.
- Sentido: hacia fuera del pilar si la patilla cabe en la losa; si no, hacia dentro (`choose_foot_direction`).

En un pilar de borde, la cara que da al borde del edificio no tiene losa fuera, así que **gira sus patillas hacia dentro**. Con un pilar de 450 y H20:

- Empotramiento: losa de 300 − recubrimiento superior − parrilla superior − φ/2, unos 225 mm.
- Patilla: 40φ − 225 = 800 − 225, unos 575 mm. Es más larga que el pilar.
- Cada patilla cruza el pilar en su propia línea y pasa por la vertical de la cara opuesta, que está en la misma posición transversal (tres barras por cara, simétricas).
- La separación entre ejes es 0 mm, cuando el mínimo es 47 mm (1,1·20 + máx(20; 20 + 5; 20)).

La QA lo detecta como «Clash» en los 600 mm superiores de los pilares de la última planta: **16 hallazgos por planta de coronación** en el edificio de prueba. Los ids de cada pilar y barra figuran en la clasificación de la QA de la verificación final (clase «point 7: column top L-bars»).

Lo que **no** funciona (probado el 2026-10-25 y revertido): cambiar la cota de las patillas de una cara. La vertical opuesta sigue en esa posición en toda la altura, y además las patillas pasan a chocar con las barras de las vigas. Los choques subieron de 16 a 65.

## 2. Opciones (sin mover las barras verticales)

| | Opción | Qué cambia | Comprobaciones | Valoración |
|---|---|---|---|---|
| A | **SMDSC MD C4 detalle B en la cara de borde**: las barras de esa cara terminan rectas bajo la parrilla superior y se solapan con horquillas invertidas (forma 21) colocadas entre las verticales, que anclan en la losa | Solo las barras de la cara de borde de los pilares de coronación. El plugin ya tiene este detalle (`'kind': 'u'`, `_mc4_ubar_sets`) para losas finas | Solape tracción (EC2 8.7, `default_lap_length_mm`). Horquillas entre verticales a ≥ s_min. Recubrimientos. BBS: nuevas marcas forma 21 | **Recomendada**: es un detalle normalizado, no crea choques y no depende de la longitud de patilla |
| B | Patilla hacia dentro **acortada** hasta quedar a s_min de la vertical opuesta: 2·170 − 47 = 293 mm en pilar 450 | Longitud de patilla de la cara de borde | Anclaje: empotramiento + patilla ≥ lb,rqd. Con 40φ: 225 + 293 = 518 < 800, **no cumple**. Solo valdría con un lb,rqd de cálculo menor (EC2 8.4.3 con hormigón y adherencia reales) | Solo si el cálculo de anclaje lo justifica; si no, A |
| C | Patilla de la cara de borde **acodada en planta** para pasar entre las verticales opuestas | Forma de la barra (patilla con doble codo) | Radio de mandril, BS 8666, s_min en el codo | No recomendada: forma no estándar, difícil de montar |
| D | Recolocar las verticales de una cara | Disposición de barras del pilar | Cálculo del pilar | Fuera de alcance: cambio de diseño (como P1 en nudos) |

## 3. Propuesta concreta (opción A), para tu aprobación

1. Solo en pilares de coronación cuya cara gire las patillas hacia dentro y cuya patilla alcance la vertical opuesta (choque medido, no supuesto). Esa cara pasa al detalle B; las demás caras siguen con su L hacia fuera.
2. Horquillas forma 21, del mismo diámetro que las verticales, una por vertical de la cara, colocadas entre las verticales opuestas a ≥ s_min. Solape de tracción según `default_lap_length_mm` (EC2 8.7).
3. Nota en el plano: «Edge column top: MD C4 detail B on the edge face - confirm with design».
4. Después de aplicar: regenerar armado, planos y BBS del pilar; pasar la QA. La clase «point 7» debe quedar en 0 sin nuevos choques con vigas ni losa.
5. Pruebas en copias: pilar de esquina, pilar de borde y pilar interior (sin cambio), en 2024, 2025, 2026 y 2027.

## 4. Lo que te pido

- ¿Apruebas la opción A para la cara de borde de los pilares de coronación?
- ¿O prefieres la B con un lb,rqd de cálculo? En ese caso, indícame la clase de hormigón y las condiciones de adherencia que debo usar.
