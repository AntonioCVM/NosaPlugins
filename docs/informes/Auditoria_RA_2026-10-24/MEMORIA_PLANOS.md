# Memoria en la generación de planos: medición, causa y corrección (Revit 2026, 25–26/10/26)

Las pruebas se hicieron en proyectos nuevos creados desde la copia local de la plantilla v30. Ninguno se guardó. Se usó el arnés `tools/revit_harness/building_test.py`, que registra la memoria privada y el working set de Revit al empezar y al terminar cada fase, con un vigilante externo que corta a 12–20 GB. Las cifras son de memoria privada (GB).

## Tabla antes / después

| Fase | Antes: 1 planta | Antes: 2 plantas | Antes: 4 plantas | Después: 1 planta | Después: 2 plantas | Después: 4 plantas |
|---|---|---|---|---|---|---|
| Armado (6 comandos) | 2,3 → 2,7 | 1,2 → 2,9 | – | 3,9 → 4,2 (+0,25) | 3,8 → 3,9 (+0,15) | 4,1 → 4,3 (+0,20) |
| QA de armado (`rebar_qa.audit`) | 2,6 → **> 20, cortada a 9,5 min** | 2,9 → **> 20, cortada a 8 min** | – | **+0,02, 4 s** | **+0,06, 10 s** | **+0,12, 29 s** |
| Vistas + rótulos | 6,5 → **> 20 al llegar a las vigas** | – | – | +0,03 (363 s) | −0,01 (759 s) | +0,04 (1571 s) |
| QA por plano (`_buildability`) | (dentro de lo anterior) | – | – | −0,01 (10 s) | +0,01 (18 s) | 0,00 (41 s) |
| `congested_stations` | – | – | – | +0,02 (0 s) | +0,03 (1 s) | +0,02 (1 s) |
| Hojas + viewports + notas | – | – | – | – | +0,02 (99 s) | +0,02 (213 s) |
| BBS | no se llegó | no se llegó | no se llegó | – | +0,02 (23 s) | +0,02 (49 s) |
| Revisión de planos | no se llegó | no se llegó | no se llegó | – | +0,02 (19 s) | +0,04 (35 s) |
| Auditoría + CSV de BBS | no se llegó | no se llegó | no se llegó | +0,01 (1 s) | 0,00 (2 s) | 0,00 (2 s) |
| PDF | no se llegó | no se llegó | no se llegó | +0,02 (27 s, 23 hojas) | +0,01 (48 s, 26 hojas) | +0,01 (83 s, 39 hojas) |
| **Pico del proceso** | **> 20 (no termina)** | **> 20 (no termina)** | **37 GB (no termina)** | **4,2** | **4,1** | **4,6** |
| Tiempo total | – | – | > 70 min sin terminar | 534 s | 1050 s | 2172 s |

Las ejecuciones "después" se hicieron seguidas en la misma instancia de Revit: 1 planta, 2 plantas y 4 plantas. Cada una empezó donde terminó la anterior (3,8 / 3,8 / 4,1 GB), así que **no hay acumulación entre ejecuciones**. Dentro de cada ejecución el crecimiento total es de +0,3 a +0,5 GB, muy por debajo del umbral de 12 GB.

## Causa confirmada

1. **Por miembro y por separado**, `_audit_host` y `congested_stations` suben entre +0,01 y +0,03 GB, en menos de un segundo, y no acumulan al repetir (sonda `qa_memory_probe.py`, 33 miembros, dos pasadas). No eran el origen.
2. **La traza del `audit` real** (`qa_audit_trace.py`) señaló `_pairs`, la comparación de barras de dos miembros en cada nudo. Cada llamada dejaba entre +0,06 y +0,39 GB, y la memoria llegó a 12 GB en 134 s.
3. Es **memoria gestionada, no nativa**. Tras una recolección completa vuelve a su nivel, y la sonda lo midió. `_pairs` comparaba todos los segmentos con todos (unas 245.000 iteraciones por pareja de vigas) y creaba en cada iteración tuplas, generadores y listas. El recolector de .NET de Revit no libera ese ritmo de objetos de vida corta antes de que el proceso crezca muchos GB.
4. La explosión de los planos "sin QA" (6,5 → 20 GB al llegar a las vigas) se debía a la misma función. La nota de constructibilidad de cada plano llama a `rebar_qa.audit`. Además, esas mediciones se tomaron con la regresión del forjado partido por las vigas (448 juegos de barras en lugar de 68), corregida antes de la medición final.

## Correcciones

| Medida | Qué resolvió |
|---|---|
| `rebar_qa.candidate_pairs`: barrido por X que solo compara los segmentos cuyas cajas pueden tocarse, sin objetos temporales en el bucle interno; procesa los candidatos en el orden del doble bucle original | El crecimiento de la QA y de la nota de constructibilidad de cada plano. Es la corrección principal |
| Unión viga-forjado invertida solo mientras se arma la viga y luego restaurada (`tab_beams._full_depth` / `_join_back`) | La regresión del forjado partido: 448 → 68 juegos de barras, 111 s → 7 s. Viga armada a canto completo |
| Recuento de cruces de rótulos con filtro por caja (`callout_layout`), visibilidad de una etiqueta consultada por su id, marcas de sección ocultadas de una vez por vista, barras ajenas prefiltradas por caja | Tiempo de dibujo. Las disposiciones de rótulos son idénticas (comprobado en 14 casos reales) |

No se desactivó ninguna comprobación ni se quitó ninguna nota. No se usa `gc.collect` como solución: solo aparece en las sondas de diagnóstico, para separar la memoria recuperable de la retenida. Los lotes cortos, el PDF por bloques y el proceso reanudable no han hecho falta para cumplir el criterio, porque el pico es de 4,6 GB con 4 plantas. Quedan como medidas secundarias si un edificio mayor se acercara al umbral.

## Comprobaciones de exactitud

- **Test de equivalencia** (`tests/test_rebar_qa.py`): 60 configuraciones aleatorias de barras (cruces, paralelas, solapes, dobleces, con y sin miembros distintos) dan las mismas 465 incidencias, en el mismo orden y con las mismas coordenadas, que el doble bucle original (`_pairs_reference`). Un segundo test exige que la lista de candidatos del barrido coincida exactamente con el filtro del doble bucle. El test detecta los sabotajes de orden y de radio.
- **En el edificio real** (`qa_equivalence_probe.py`, 1 planta): 100 comprobaciones (33 miembros y 67 nudos) dan las mismas 599 incidencias con el método nuevo que con el original. Tiempo: 3 s frente a 34 s.
- **Planos, BBS y PDF:** antes no llegaban a generarse, así que no hay una referencia anterior con la que compararlos. Se verificaron por su cuenta:
  - las 43 filas de BBS del edificio de 2 plantas cuadran con el modelo (cruce `ra_bbs_crosscheck.py`);
  - la auditoría documental y los PDF se generan completos (29 hojas y 39 PDF en el de 4 plantas).

## Límites que quedan

- **El tiempo de dibujo** es ahora el cuello de botella, no la memoria. Los rótulos suponen el 80 % (1.514 s de 2.172 en 4 plantas). Escala más que linealmente con el número de rótulos por vista.
- **La QA sigue dando muchas incidencias en el edificio.** Son reales en los nudos viga-pilar; en las esquinas de cerco son la simplificación del modelo. Es un problema de criterios de detalle, no de memoria (ver `EDIFICIO_4_PLANTAS.md`).
- **El complemento RvtMcp no está firmado**, así que Revit pide confirmación en cada arranque. Firmarlo requiere un certificado de firma de código y registrar el editor como de confianza en Windows; eso lo debes hacer tú.
