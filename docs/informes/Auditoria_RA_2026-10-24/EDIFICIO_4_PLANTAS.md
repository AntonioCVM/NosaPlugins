# Prueba de un edificio de 4 plantas (Revit 2026, 25/10/26)

Arnés: `tools/revit_harness/building_test.py`. Se usó un proyecto nuevo desde la copia local de la plantilla v30, que se cerró sin guardar. Todo el armado pasó por el flujo real de la ventana, en orden constructivo. Después se crearon los planos, se hizo la auditoría documental y se exportaron 44 PDF (`%LOCALAPPDATA%\Temp\nosa_building_2026`).

**Modelo:** malla de 2 × 2 vanos de 6 m; 9 zapatas, 36 pilares de 450 × 450, 48 vigas de 300 × 600, 4 forjados de 300 mm (el último es la cubierta), 4 muros de núcleo de 300 mm y una escalera en U de hormigón.

## Resultado por comando

| Paso | Elementos | Armaduras (elementos / barras) | Tiempo | Observaciones |
|---|---|---|---|---|
| Zapatas | 9 | 63 / 243 | 9 s | Recubrimiento inferior 40 < 75 de SMDSC 6.7. Es el valor guardado en la ventana; el plugin lo avisa. |
| Pilares | 36 | 207 / 891 | 25 s | Avisos SMDSC 6.4: cercos densificados sin marcar y barra a 165 mm de una atada (> 150). Las esperas no se duplican cuando la zapata ya tiene las suyas. |
| Vigas | 48 | 384 / 3840 | 48 s | El forjado corta las vigas: solo se arman bajo la losa y las patillas en el pilar quedan de 140 mm. El plugin lo avisa y pide cambiar el orden de unión. |
| Forjados | 4 | 272 / 5640 | 31 s | Inferiores 0,8 × luz alternadas (MD S1) y U de borde H10 subidas a H16 (MD S2). |
| Muros | 4 | 28 / 600 | 8 s | Sin avisos. |
| Escalera | 1 | 18 / 109 | 7 s | 4 barras con un extremo de 34 mm (< 5d) y barras ancladas en un forjado inexistente. **Corregido.** |
| Planos | 78 grupos | 246 vistas, 33 hojas, 5674 etiquetas | **76 min** | Ver más abajo. |

Ningún comando dio excepciones ni errores de Revit.

## Defectos encontrados y estado

1. **BBS de miembros iguales en otras hojas** (corregido, `47eb4fb`). Las 9 zapatas son iguales: la BBS 4501-01 las cuenta juntas ("F1 to F9", 9 miembros), pero F2…F9 se dibujan en 4502–4505. Las barras de esas copias se quedaban sin la referencia de la BBS (las notas decían "no bar schedules issued") y fuera de la renumeración, así que sus marcas podían no coincidir con la planilla. Ahora se programan y se marcan con su original.
2. **Escalera** (corregido, `b371327`):
   - quedaban extremos de 34 mm tras una doblez;
   - con una meseta corta la barra superior retrocedía sobre sí misma;
   - las barras se anclaban 425 mm "en el forjado" aunque no hubiera forjado.
3. **Rendimiento de los planos** (mejorado, `b3dbdd5`, pendiente de medir en Revit). Cada marca de sección se ocultaba con una llamada propia en cada vista, y en cada vista se leía la geometría de todas las barras ajenas. Las dos cosas crecen con el cuadrado del número de vistas.

## Pendiente de decisión del usuario

- **Vigas cortadas por el forjado.** Hoy el plugin avisa y arma solo el alma bajo la losa. Propuesta: armar siempre el canto completo, sea cual sea el orden de unión.
- **Pilares de una misma pila.** Hoy sale un alzado por tramo. Propuesta: un alzado continuo por pila.
- **Oblicuas de 30° en planta.** No aparecen en los extremos cortados de la losa (ver `REVISION_VISUAL.md`, punto 11).
- **Calidad de dibujo en el edificio.**
  - Incidencias de la auditoría: 316 A3, 140 A4, 4 A7 y 564 A9 (líneas indicadoras a lo largo de una barra, sobre todo en alzados de pilares).
  - En los modelos de prueba pequeños estaban a cero, así que hay que revisarlas con el edificio.
- **Buildability C (0/100).** Se debe sobre todo a los cruces de barras en los nudos viga–pilar. Hay que revisarlo con el informe de QA.
