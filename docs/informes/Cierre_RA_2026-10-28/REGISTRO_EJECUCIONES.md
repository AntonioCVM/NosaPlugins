# Registro de ejecuciones (cierre de RebarAutomate)

Banco de pruebas: `tools/revit_harness/building_test.py` en un proyecto nuevo sin guardar, creado desde la copia de la plantilla `nosa_t857\NOSA v30 template copy 2026-10-28.rte` (hash idéntico a la maestra del 26/10, con la fórmula M4). Nunca se guarda ningún modelo.

Tiempos en segundos de reloj; entre paréntesis, segundos de CPU de Revit. Memoria: GB privados de Revit (límite 12 GB). Tablas por fase: `tools/revit_harness/phase_table.py`.

| Fecha y hora | Modelo | Revit | Código | Total s | Pico GB | QA | Avisos de planos | BBS | Resultado |
|---|---|---|---|---:|---:|---:|---:|---|---|
| 26/10 | 4 plantas (final2_s4) | 2026 | c5b7751 | 1549 | — | 2354 | 272 | 43/43 filas | referencia anterior («26 minutos») |
| 28/10 14:56 | 1 planta (b28_s1) | 2026 (pid 54188, recién abierto) | c5b7751 + 3.1 | 1029 | 3,53 | — | 44 | 44 filas, pesos 0 dif. | Correcto. Lento por ser la primera ejecución de la instancia |
| 28/10 15:19 | 2 plantas (b28_s2) | 2026 (pid 54188) | + 3.4 (nota de peso) | 991 | 3,50 | 1199 | 92 | 46 filas, 2 dif. de peso (incidencia I1), 6/6 notas correctas | 3.4 correcto; «point 7» 16 (fallo del detalle B, corregido para b28_s4) |
| 28/10 15:43 | 4 plantas (b28_s4) | 2026 (pid 54188) | + corrección del detalle B | en curso | | | | | |

## Ruido de las medidas

Con el mismo código, las ejecuciones de 1 planta del 26/10 dieron entre 414 y 1313 s. La primera ejecución en una instancia recién abierta es la más lenta: b28_s1 tardó 1029 s y b28_s2, con el doble de elementos, 991 s. Por eso las comparaciones de optimización se hacen en la misma instancia y con el tiempo de CPU.

## Incidencias

**I1 — Peso BBS de H8 (3.3).** BBS 4514-01, marca 04 (cercos H8, forma 52), miembros «B1 to B23» y «B2 to B24»: 480 barras × 1575 mm.
- Esperado según la masa de la BS 4449 (0,395 kg/m): 298,6 kg.
- Impreso: 298,3 kg.
- La fórmula de la plantilla calcula la masa como π·d²/4 × 7850 kg/m³ = 0,39458 kg/m. 480 × 1,575 × 0,39458 = 298,30 kg, exactamente lo impreso.
- En las filas pequeñas la diferencia desaparece al redondear a 0,1 kg.
- Afecta a todos los diámetros: la BS 4449 redondea su tabla (H12 0,888 frente a 0,8878; H16 1,579 frente a 1,5783...).
- Corrección: en la plantilla maestra (no la toca el plugin). Usar la masa tabulada por diámetro, o bien aceptar π·d²/4·ρ como criterio. Decisión del usuario.

## Cambios del 28/10 y su motivo

- **3.4 — Total de «No. of bars in each».** Revit no permite quitar el total general de una sola columna. `ScheduleField.DisplayType` solo admite Standard, Totals, MinMax, Max y Min. Con Standard, las 9 filas que agrupan miembros con distinto número de barras pasan a mostrar «varios». Por eso (opción c, decisión del usuario):
  - se oculta la fila de totales de cada BBS (`ShowGrandTotal = False`, también en la «BBS» maestra del proyecto);
  - el peso total va como nota «Total weight: N kg» bajo la tabla, en cada hoja BBS (`bar_schedules.weight_note`);
  - la nota es la suma de los pesos que imprime la propia tabla (fórmula de la plantilla), leídos de sus celdas, y se rehace en cada generación.

  El total que imprimía Revit no coincidía con la suma de las filas: en b28_s1, 4 de 6 tablas diferían en 0,1–0,2 kg, porque Revit suma sin redondear (S1: 5621,1 frente a 5621,3 kg). La nota coincide exactamente con la suma de las filas. `ra_bbs_crosscheck.py` lo comprueba en cada ejecución (fila de totales ausente, nota igual a la suma).
- **3.1 — Detalle B en la cara de borde de los pilares de coronación.** Criterio aprobado. En b28_s2 se aplicó, pero la QA siguió con 16 choques. Las horquillas en la dirección u tienen su tramo horizontal a la cota del final de las verticales y pasan por encima de las barras intermedias de las caras v (ejes a 0 mm). El fallo ya existía en el detalle B para losas finas, sin ejercitar en el edificio de prueba. Corrección: las verticales terminan una separación entre ejes (1,1φ + s_min, 47 mm con H20) bajo los tramos horizontales, y el solape de las patas se mide desde ese final (`detail_b_bar_end_ft`). Verificación pendiente: b28_s4.
- **3.1 — Pilares circulares.** Sin cambios: el plugin no genera las horquillas del detalle B en pilares circulares (limitación documentada; mejora futura).

## Actualización 28/10 tarde

| Fecha y hora | Modelo | Revit | Código | Total s | Pico GB | Resultado |
|---|---|---|---|---:|---:|---|
| 28/10 15:43 | 4 plantas (b28_s4) | 2026 (pid 54188) | detail B en las 4 caras | 2722 | 3,89 | «point 7» 16 → 0, pero los nudos de cubierta pasan de 274 a 333 hallazgos (+59): descartado (ver docs/PILARES_BORDE_L_CORONACION.md §5). 47 filas BBS. 210 avisos de planos |
| 28/10 17:4x | 1 planta (c28_s1, d28_s1) | 2026 | L con aviso por pilar; 3.2 conectado | 423 / — | — | Aviso en los 8 pilares de borde. Nudos: 0 R1 y 12 R3 |
| 28/10 18:0x | 1 planta (e28_s1) | 2026 | total de peso en tabla de Revit | 509 | — | 6/6 totales en su hoja; 0 a 0,2 kg de la suma impresa |

**Condiciones de b28_s4 frente a final2_s4 (26/10): no comparables.** El trabajo es el mismo: 219 vistas, y 3549 frente a 3533 etiquetas. Pero durante la anotación:
- Revit tenía 3,69 GB privados y solo 1,87 GB residentes (el 26/10, 4,44 y 4,52: todo en RAM);
- el equipo tenía 43 GB comprometidos sobre 31,7 GB de RAM, con «Memory Compression» en 3,15 GB.

Las vistas de losa, las de más etiquetas, se ralentizan ×2–3 y el resto ×1,3. Hay que repetir la medición con la memoria del equipo libre.

**3.4, cambio de criterio (decisión del usuario, 28/10 tarde).** El peso total no es una nota escrita por el plugin. Es una tabla de Revit «BBS dddd-nn total weight» bajo cada BBS: una copia de la BBS filtrada por la misma referencia, sin agrupar y con solo la columna de peso visible. Revit suma los pesos de las filas y la tabla sigue al modelo. Puede diferir de la suma de lo impreso en hasta 0,05 kg por fila (redondeo de cada fila), diferencia aceptada por el usuario. `ra_bbs_crosscheck.py` comprueba que está en la hoja de su BBS y dentro de esa tolerancia.

**I1 (3.3).** 69 de las 137 filas de 1, 2 y 4 plantas difieren de la masa tabulada de la BS 4449 (−1,8 a +0,2 kg). Todas se deben al criterio de la fórmula de densidad (`tools/revit_harness/bbs_weight_table.py`); ninguna al redondeo. La API de Revit no da acceso a las fórmulas de los campos calculados (ni lectura ni escritura), así que la corrección de la plantilla debe hacerse en su diálogo de campos.

**3.2.** Mecánica de R1 verificada en Revit (vigas de 400, `joint_apply_probe_mech.py`): 12/12 barras con el mismo anfitrión, el conjunto con una barra menos y las demás en su sitio, y la barra desplazada con la misma forma, marca, diámetro y longitud, en su nueva posición (−47 mm). Pero en esos nudos cruza la otra viga a la misma cota: la QA pasaba de 749 a 790 (+41, ninguno eliminado). R1 se rechaza ahora cuando hay barras de otra viga cruzando la capa a su cota en el nudo, y pasa a R3 con ese motivo. Resultado: vigas de 300, 12 R3; vigas de 400, 36 R3; 0 R1. QA idéntica antes y después.

## Decisiones del usuario (28/10 noche)

- **I1 y 3.3: cerrados, aceptados por criterio del usuario.** El peso de la BBS se calcula con la fórmula de densidad de la plantilla (número de barras × longitud impresa × π·d²/4 × 7850 kg/m³), no con la masa tabulada de la BS 4449. Las diferencias frente a la BS 4449 (hasta unos 2 kg por fila; 298,3 frente a 298,6 kg en el caso revisado) son despreciables y no cuentan como incidencia. No se toca la plantilla.
  - Desde ahora `ra_bbs_crosscheck.py` compara cada fila con esa fórmula. Solo es incidencia una fila que no cuadre más allá del redondeo a 0,1 kg.
  - Repetida la comprobación sobre b28_s1, b28_s2, b28_s4 y e28_s1: 0 filas fuera de la fórmula.
- **3.4.** La tabla «Total weight [kg]» debe dar el sumatorio de los pesos de su BBS. La diferencia con la suma de lo impreso, si solo viene del redondeo de cada fila (hasta 0,05 kg por fila), se desprecia. Cualquier otra es incidencia. Pendiente de verificar en todas las hojas de 1, 2 y 4 plantas (t28_*).
- **3.1 y 3.2: para revisión técnica uno a uno.** Lista en `docs/informes/Cierre_RA_2026-10-28/REVISION_TECNICA_3.1_3.2.md`: 8 pilares de coronación y 84 barras de nudo en R3 (edificio de 4 plantas, `review_probe.py`). Motivo común de los nudos: la barra central tendría que desplazarse 47 mm, por encima del límite s/2 = 45,1 mm, y quedaría a menos de s_min de su vecina; el acodado necesitaría 47 mm, por encima de 2φ = 40 mm, y no hay esfuerzos para R2. En las barras superiores de algunos nudos se añaden barras paralelas de losa o de otra viga.

## Mediciones en instancia limpia (28/10, 20:42–21:50)

Revit 2026 pid 74692, recién abierto, con el vigilante de 12 GB en marcha. Equipo con Chrome cerrado: 8,0 GB de RAM libres y 37,0 GB comprometidos al empezar (antes, 4,8 y 42,7). Código c750f0f más la comprobación de pesos por densidad.

| Ejecución | Total s | Pico GB | QA | Avisos de planos (A3 + A4; A4i aparte) | BBS: filas, incidencias de peso | Totales de peso |
|---|---:|---:|---:|---|---|---|
| 1 planta, en frío (t28_s1) | 383 | 2,9 | 530 | 51 (34 + 17; 14) | 41 filas, 0 | 6/6, diferencia ≤ 0,2 kg (redondeo) |
| 2 plantas (t28_s2) | 725 | 3,4 | 1102 | 95 (49 + 46; 32) | 43 filas, 0 | 6/6, ≤ 0,2 kg |
| 4 plantas (t28_s4) | 1457 | 3,73 | 2354 (igual que el 26/10) | 205 (92 + 113; 66) | 43 filas, 0 | 6/6, ≤ 0,1 kg |
| 1 planta, en caliente (t28_s1w) | 386 | — | — | — | — | — |

- **Arranque en frío:** 383 s en frío frente a 386 s en caliente. No tiene efecto medible. La lentitud de b28_s1 (1029 s) y de b28_s4 (2722 s) se debió a la presión de memoria del equipo (Revit con la mitad de su memoria fuera de RAM).
- **4 plantas frente al 26/10 (final2_s4): 1549 → 1457 s (−92 s, −6 %), pico 4,53 → 3,73 GB.** La anotación pasa de 912 a 847 s (CPU 870 → 801). Las demás fases quedan dentro de ±6 s. Tabla fase a fase: `phase_table.py nosa_t28_s4.txt nosa_final2_s4.txt`.
- **3.4 cerrado.** Las 18 tablas «Total weight [kg]» de 1, 2 y 4 plantas están en la hoja de su BBS y dan el sumatorio de sus pesos. La diferencia con la suma de lo impreso es de 0 a 0,2 kg y viene solo del redondeo de cada fila. Ninguna incidencia.
