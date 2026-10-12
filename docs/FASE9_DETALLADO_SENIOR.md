# Fase 9 — Planos de armado de nivel «detallista senior»

Origen: cinco análisis de los planos de muestra (4002–4011, Project1, Revit 2024) aportados por el usuario el
2026-10-11. Referencia normativa: **IStructE SMDSC 4.ª edición (2021)** (PDF del usuario, `lib4192`), BS 8666:2020,
EC2 + UK NA; la 3.ª edición (2006) queda como histórico. Las tareas están en [MASTER_ROADMAP.md](../MASTER_ROADMAP.md),
Fase 9.

## Decisiones del usuario (2026-10-11)

| Tema | Decisión |
|---|---|
| Filosofía | El plugin **sigue generando** armado por reglas SMDSC (U en bordes libres, zunchos, barras de piel, bandas) pero cada barra añadida por regla queda **marcada «regla de detallado aplicada — confirmar con el diseño»** en el QA y la planilla. Nunca mueve ni cambia barras de diseño: nudos y congestión solo avisan. |
| Norma | SMDSC 4.ª ed. Cada regla registra edición y cláusula. |
| Cercos de viga | Como la 4.ª ed. Fig. 6.24: `(13@100)` sobre cada zona, con su cota desde la cara del apoyo, y una llamada total por marca `82H8-04 LINKS`. |
| Llamada | ~~Sin espacio antes de la capa~~ → **con espacio** `20H16-63-150 B1` por claridad (usuario 2026-10-12, se aparta de la 4.ª ed. 4.2.1). |
| Orden | Oleada A, luego B, C y D. |
| Hojas | Varios elementos del mismo tipo agrupados en un A1 (todas las vigas de una planta, todos los pilares…) a las escalas del SMDSC. |
| Cajetín | Los datos de prueba («Client X», «Author»…) solo bloquean la emisión *For Construction*. |

## Revisión del usuario de los planos 4002–4007 (2026-10-12)

| Tema | Decisión / cambio |
|---|---|
| Recuento | Cada conjunto lleva su llamada completa con su propio número, aunque haya otro idéntico (las U de los dos extremos de un muro: `15H12-09-200 U-BARS` en cada uno, no `30…` con `(15)`). Se aparta de la 4.ª ed. 4.2.1 («stated only once»); la marca no cambia y la planilla suma. |
| Barras sueltas | Agrupadas por sitio: las 8 de un pilar circular `8H20-01` aunque el alzado vea 5; los recercados de cada lado de un hueco por separado. Sin marcas sueltas sin llamada. |
| Secciones | Marca sobre cada barra cortada también en losas, bases y muros (sin línea de referencia); en muros, a los lados. Flecha horizontal con la marca en cada extremo libre de las barras vistas en alzado. Hormigón cortado en su color (naranja claro). |
| Marcas de sección | En alzados, trazo + flecha hacia donde mira + número. En plantas, siempre hacia arriba o a la izquierda. Las secciones de pilar son plantas cortadas mirando hacia abajo (Revit no dibuja el pilar en una sección horizontal). |
| Hojas | Orden de lectura: alzados (A antes que B) alineados a la misma cota, secciones en orden numérico. Plantas de cimentación a la escala de sus secciones. |
| Vistas | Solo las barras del elemento detallado. Llamadas de viga horizontales y cerca de la viga salvo que no quepan. |

## Contradicciones detectadas entre los análisis y la norma

1. **Formato de la llamada.** Prompt 1: `20H16-63-150 B1`; prompt 3 y la **4.ª ed. (4.2.1 y todas sus figuras)**:
   `20H16-63-150B1`, sin espacio. Hoy el plugin pone espacio (decisión del 2026-10-11 tomada con la 3.ª ed.).
2. **Zonas de cercos.** El usuario eligió «llamada completa por zona»; la **4.ª ed. Fig. 6.24** usa los recuentos por
   zona entre paréntesis bajo la viga, `(19@300) (5@200) (13@150)`, y **una sola llamada por marca**,
   `37H12-07 LINKS` (4.2.1: «the number of bars in a group should be stated only once»). Hoy: `13/100` + línea de total.
3. **Plantas «Bottom/Top reinforcement».** El prompt 3 pide quitarlas; los prompts 1 y 5 y la decisión del 2026-10-10
   las mantienen. Se mantienen.
4. **Sólo documentar vs generar.** Resuelto: generar con aviso.
5. **Grosores.** Prompt 2 habla de plumas 7/5/3/1; prompt 3 y SMDSC 3.10 dan mm (0,35 / 0,7 / 0,35–0,7 / 0,25).
   Se siguen los mm del SMDSC (ya aplicados en T8.26).

## Qué ya cubre el plugin

Llamada BS 8666 con capa calculada por geometría (T1/T2/B1/B2, N1/N2/F1/F2) · grosores SMDSC 3.10 · secciones
1:20 de solo plano de corte, vigas a la izquierda y pilares hacia abajo · secciones reales A-A/B-B de losas y bases
con marca en planta · zunchado de huecos (barras de borde + diagonales) en losas y muros · separación libre y hueco
de vibrador (QA T8.48) · barras de piel cada 250 · solapes escalonados y acopladores · espaciadores `nHxx-01 SPACERS`
· marcas únicas por plano · planillas A4 BS 8666 (Revit y Excel) · leyenda de capas y notas de armado por hoja ·
QA de recubrimientos, separaciones y cruces · amarre (ties) y mallas · estancos · tablas de pilares/zapatas.

## Huecos priorizados (de mayor a menor impacto)

### Oleada A — Comunicación constructiva en los planos (lo que más «delata» al software)
- **A1 Cotas de colocación**: límites de zonas de armado, inicio/fin de barras adicionales desde la cara del apoyo,
  longitudes de negativos, zonas de cercos con primer cerco desde la cara, posiciones de huecos/recercados (SMDSC 3.13,
  6.x.4). Cotas a caras de hormigón y ejes, nunca a barras; fuera del elemento; sin cruces.
- **A2 Corte, anclaje y solape dibujados**: extremos de barra con símbolo, longitud de anclaje/solape acotada, zonas
  «LAP ZONE» y «SUPPORT ZONE», extensión más allá del apoyo (regla de decalaje a_l = 1,25d ya calculada).
- **A3 Geometría y niveles**: b × h, longitudes, luces entre caras, espesores, cotas de nivel con flecha cerrada
  (SMDSC 3.14.3), ejes visibles en todas las vistas.
- **A4 Marcas de sección en alzados**: secciones de viga/pilar numeradas `1-1`, `2-2` con su marca en el alzado,
  colocada fuera de las filas de llamadas; títulos alfanuméricos (prompt 4, SMDSC 3.18).
- **A5 Notas paramétricas por plano**: clase de hormigón, c_nom (+ Δc_dev), árido máximo, acero, referencia a las
  planillas de ese plano y a la GA (SMDSC 3.7); alerta si faltan datos.
- **A6 Composición**: agrupar elementos del mismo tipo en A1, escala de lectura, reparto con cajas reales.

### Oleada B — Constructibilidad
- **B1 Congestión**: detector por sección (capas > 2, barras agrupadas, nudos) y **sección automática** extra a 1:10/1:20.
- **B2 Vibrador**: 75 mm cada 300 mm de ancho de viga en nudos (4.ª ed. Fig. 4.2), además del hueco en la capa.
- **B3 Retención de barras de pilar**: toda barra retenida por cerco salvo separación ≤ 150 (4.2.2 nota 1).
- **B4 Notas de montaje** (FIXING NOTES) por tipo de elemento y **jaulas prefabricables** etiquetadas (4.2.3).
- **B5 Plano/informe RC BUILDABILITY CHECK** y **puntuación QA** (A+/A/B/C).

### Oleada C — Emisión y trazabilidad
- **C1 Comprobación previa a la emisión** con niveles Error/Warning/Info/Passed: barras sin marca, marcas duplicadas
  con geometría distinta, planilla ≠ plano, sección sin referencia, textos solapados, cajetín con datos de prueba
  (bloquea *For Construction*), referencias a GA/0900/planillas inexistentes.
- **C2 Registro de revisiones**: base de marcas y geometrías por revisión (UniqueId), tabla de cambios, nubes opcionales,
  estados P/T/C… ya presentes en la planilla.
- **C3 Bandera «añadido por regla»** en barras generadas por regla (decisión de filosofía) y su listado.

### Oleada D — Elementos
- **D1 Losas**: bandas de pilar / centrales rotuladas (COLUMN STRIP / MIDDLE STRIP), U en bordes libres con bandera,
  sillas solo en cimentaciones multipilar/rafts (4.2.6), comprobación de curtailment MD S1 de la 4.ª ed.
- **D2 Vigas**: hanger bars mínimas con nota, límites de apoyo dibujados, barras de piel por tabla MD B1 (4.ª ed.),
  viga curva con radio, centro y estaciones acotados.
- **D3 Pilares**: cuantía ρ, zonas de solape y confinamiento, arranque desde cimentación con kicker 75/150.
- **D4 Muros**: estilos distintos para verticales/horizontales, MW4 huecos completo.
- **D5 Cimentaciones**: bandas MF1 cuando l > 1,5(c + 3d), arranques con solape/proyección/recubrimiento acotados,
  tabla de pilotes en encepados.
- **D6 Biblioteca de detalles tipo** (MD de la 4.ª ed.) insertados por condición.

### Fuera de alcance (avisar, no resolver)
Sísmico, pretensado, prefabricado, contención de líquidos especial, marinas, fuego > 40 mm de recubrimiento
(SMDSC 6.3.3): el plugin detecta el caso y pide la referencia aprobada.
