# Fase 11 (propuesta) — Comparativa de RebarAutomate con otros programas (2026-10-18)

Revisados: **Graitec PowerPack for Revit** (Rebar Design + Rebar Detailing), **CADS RC3D for Revit** (con CADS Rebar Extensions y CADS Markup) y el **Rebar Automate de KS Digital Innovations**.

Fuentes:
- las páginas públicas de los fabricantes;
- la ficha de Autodesk Marketplace;
- una publicación de LinkedIn sobre el plugin de KS Digital.

No se ha probado ningún programa.

## Qué hace cada uno

| | Graitec PowerPack | CADS RC3D | KS Digital (KennySTRUCT / Rebar Automate) | NOSA RebarAutomate |
|---|---|---|---|---|
| **Generación por elemento** | Asistentes para vigas, pilares, zapatas y muros («Main Bars») | Rebar Extensions: vigas, pilares, zapatas corridas y aisladas, petos, encepados, pilotes, muros de contención | Losas (según LinkedIn); sin confirmar el resto | Losas, zapatas, encepados, pilares, vigas (continuas, curvas), muros, escaleras, ménsulas |
| **Reglas de detalle** | Huecos y bordes de losas y muros, barras acodadas, separación transversal variable | Huecos y esquinas de losas, esquinas e intersecciones de muros | — | SMDSC 4.ª ed. completas (MD S1–ST1, huecos, U de borde, torsión, punzonamiento, empalmes y empotramientos EC2) |
| **Diseño** | Desde resultados FEM, o «Constructive Dispositions» (mínimos sin cálculo) | CADS Markup: importa mapas de armado de FEA y los convierte en zonas de armado | — | No (datos del calculista) |
| **Edición** | Recortar, prolongar, copiar, partir con reglas de empalme | Unir barras, recortar a huecos y caras, partir a longitud comercial, copiar conjuntos a otra estructura | Copiar y borrar barras, seleccionar el anfitrión | Partir a longitud comercial, borrar por anfitrión, lotes |
| **Marcas** | Filtro por marca, tipo, partición, forma o diámetro, para resaltar o seleccionar | Lógica de marcas propia por anfitrión, plano o proyecto | — | Particiones BS 8666, renumeración, miembros idénticos |
| **Visibilidad** | Por tipo y capas en cada vista | Capas por elemento o por malla (T1/B1…) | Mostrar u ocultar barras | Sólidos en 3D; capas en los planos |
| **Planos** | Secciones, vistas etiquetadas, despieces y planilla en hoja; clonar planos (2024) | Rótulos, ticks y referencias automáticos; asignar a estructura, entrega y hoja | Cortes, alzados, hojas y etiquetas | Serie 4500 completa según el SMDSC, notas, leyendas y QA |
| **Planillas** | Planillas, despieces y mediciones con esquemas personalizables | Planilla y pesos en hoja o Excel; «Host Count Override»; historial de revisiones de planillas; congelar barras | Planillas (LinkedIn) | BS 8666 en A4 (serie 5500), Excel, CSV y paquete de fabricación |
| **Exportación** | A software de fabricación | BVBS, aSa, Soulé, Excel | — | BVBS |
| **Comprobación** | Tensiones e interacción (diseño) | Detección de choques | — | QA: recubrimiento, separaciones, choques, vibrado, edificabilidad A+–C |
| **Otros** | Partición automática del modelo; roles de barra | Soporte en el Reino Unido | Coordenadas de cimentación, numeración de pilotes, unir vigas o losas colineales | Detalles típicos SMDSC como leyendas |

## Qué merece la pena incorporar (por valor para NOSA)

| # | Propuesta | Inspirada en | Por qué |
|---|---|---|---|
| 1 | **Plano de pilotes**: numeración P1… y tabla de coordenadas, diámetro y cota de corte en un plano propio (serie 4500 o la que indiques) | KS Digital: coordenadas de cimentación y numeración de pilotes | Lo pediste al quitar las coordenadas de 4506; ya existe `pile_table` |
| 2 | **Congelar planillas emitidas e historial de revisiones**: al emitir, las barras quedan Finalized y la planilla guarda la revisión (P1, C1…) con fecha y cambios | CADS RC3D: freeze/unfreeze y emisión electrónica | Evita que una regeneración cambie un plano emitido sin dejar rastro |
| 3 | **Copiar armado a elementos idénticos** (misma geometría y tipo) en lugar de generar cada uno | RC3D (copiar conjuntos); Graitec (clonar planos) | Rápido en edificios repetitivos; la planilla ya admite «No. of mbrs = N» |
| 4 | **Visibilidad por capa** (T1, T2, B1, B2, N1, F1… y U, trimmers, esperas) con un clic en *Check & manage* | Graitec y RC3D | NOSA_Rebar_Layer ya existe; ayuda a revisar mallas en 3D |
| 5 | **Resaltar o seleccionar por marca** en la vista activa (desde la planilla o el registro) | Graitec: Rebar Numbering | Revisión rápida de una marca dudosa |
| 6 | **Herramientas sueltas de huecos y bordes**: armado de hueco, U de borde o esquinas de muro sobre elementos ya armados a mano, sin regenerar todo | Graitec y CADS | Para modelos de terceros o cambios tardíos |
| 7 | **Barra acodada (crank) en barras seleccionadas** para resolver un choque que marca el QA | Graitec: Cranked Bars | Corrección dirigida en lugar de regenerar |
| 8 | **Importar el armado requerido del cálculo** (As por zona, desde Robot, ETABS o SAFE, CSV o Excel) y proponer barra y separación por zona | CADS Markup; Graitec FEM | El salto mayor; proyecto aparte (fase 12) |
| 9 | **Exportar aSa o Soulé** | CADS | Solo si algún ferrallista lo pide; BVBS cubre el Reino Unido y Europa |

Lo que NOSA ya hace mejor:
- reglas SMDSC 4.ª ed. completas y planos según el estándar;
- QA de edificabilidad;
- detalles típicos;
- multiestándar EC2 (UK NA);
- todo dentro de Revit, sin licencia de pago.

## Recomendación

Fase 11 con las propuestas 1–5, que son pequeñas y aprovechan lo que ya existe. Dejar la 6–7 para cuando aparezcan en un proyecto real y la 8 como fase propia.
