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
