# Cómo se rotulan los armados en los planos de las grandes ingenierías (2026-10-18)

## Fuentes

Los planos de armado de Arup, AKT, WSP y otras ingenierías no se publican: en los expedientes de urbanismo solo aparecen planos generales y métodos constructivos, sin armado. La referencia común de estas ingenierías en el Reino Unido es el **IStructE SMDSC 4.ª ed.**, cuyos planos tipo están dibujados por ellas. He estudiado sus figuras:

| Figura | Elemento |
|---|---|
| 6.13 | Losa plana |
| 6.24 | Vigas, método tradicional |
| 6.31 | Pilares |
| 6.33 | Muros |
| 6.40 | Zapatas y encepados |

Las imágenes están en `%TEMP%\smdsc_figs`.

## Convenciones

1. **El rótulo va sobre una línea horizontal**: el texto se apoya en un trazo que lo subraya en todo su largo, y ese trazo sigue con un solo tramo recto hasta la barra, terminado en flecha. Nunca hay quiebros oblicuos.
2. **Plantas de losas y alzados de muros**:
   - el rótulo se escribe en la **prolongación de la línea indicadora**, fuera del elemento;
   - la línea sigue recta desde la zona hasta el texto, así que no hay duda de a qué zona pertenece;
   - los textos de las líneas horizontales forman una **columna alineada** a un lado;
   - los de las líneas verticales van girados y forman una **fila alineada** arriba o abajo;
   - el orden de los textos sigue el de las líneas, de modo que las prolongaciones nunca se cruzan.
3. **La línea indicadora** abarca la zona con trazos perpendiculares cortos en los extremos. La barra tipo la cruza con un punto grande en la intersección.
4. **Cantidades por subzona entre paréntesis sobre la línea indicadora**, dentro del elemento: «(7+7) @200», «(14)», «(8)». Un solo rótulo da el total.
5. **Juegos ALT/STG en dos líneas apiladas sobre el mismo rótulo**:

   ```
   21 H16 01-200 B2
   20 H16 05 ALT
   ```
6. **Secciones**: solo el número de marca («01», «02/03») junto a la cara. Las barras de las esquinas se marcan sin línea; el resto, con una línea corta en escuadra y media flecha.
7. **Cercos en alzado de viga**: una línea de cota con las zonas «(19@300) (5@200) (13@150)» y un único rótulo «37 H12 07 LINKS» con su línea hasta el punto de la línea de zonas.
8. **Pilares**: alzado esquemático con rótulos cortos («4 H20 19», «15 H8 20 200») y la sección a escala con las marcas en cada cara.
9. **Zapatas**: un rótulo por dirección, fuera de la zapata, en la prolongación de su línea indicadora («13 H25 01-250 B2»); en la sección, las marcas y «65 COVER TO 03».

## Comparación con lo que hace hoy NOSA

| Punto | NOSA hoy | SMDSC / ingenierías |
|---|---|---|
| Rótulo de zona en planta | Junto a la barra tipo, dentro de la losa, con una línea corta en escuadra (elegido el 2026-10-17) | Fuera, en la prolongación recta de la línea indicadora, en columnas o filas alineadas |
| Subrayado del texto | El texto de la etiqueta de Revit sin trazo bajo él | Texto apoyado en su línea |
| Cantidades por subzona | Paréntesis en marcas repetidas | Igual |
| ALT/STG | Relación ALT/STG en una nota aparte | Dos líneas en el mismo rótulo |
| Secciones | Número de marca junto a la cara, en filas | Igual |
| Cercos de viga | Zonas «(n@s)» y un rótulo total | Igual |

## Propuesta (T11.7)

1. **Plantas y alzados de muro al estilo SMDSC**:
   - rótulo fuera, en la prolongación recta de la línea indicadora;
   - textos alineados en columna (líneas horizontales) o en fila (verticales);
   - ordenados para que ninguna prolongación cruce otra;
   - se acaban las líneas de referencia largas con quiebros.

   Es lo contrario de lo que se eligió el 2026-10-17 («al punto de la barra tipo»), así que **lo decide el usuario**.
2. **Familia de etiqueta con el texto subrayado** (el trazo bajo el texto forma parte de la etiqueta), para que los rótulos se lean como en las figuras.
3. **ALT/STG apilados** en el mismo rótulo cuando dos juegos comparten zona.

## Estado (2026-10-18)

Aplicado con el manual de Arup (R. Whittle, 1.5.1), que el usuario aportó porque los rótulos «no dejaban saber dónde va cada barra»:

- **Texto sobre su subrayado**: cada rótulo es nivelado y se apoya en una línea de detalle (estilo NOSA Total Lines) que lo subraya. Esa línea sale en escuadra de la línea indicadora de la zona, o de la propia barra suelta, y llega a una columna de textos a cada lado del elemento (`callout_layout.align_rows`). No hace falta una familia de etiqueta nueva.
- **Zonas y barras sueltas juntas**: una sola maquetación por planta o alzado de muro (`_layout_joint`), de modo que ninguna línea cruza a otra.
- **Quiebros escalonados**: los que se apartan de su altura quiebran en escuadra en el hueco junto al elemento, cada uno a su distancia.
- **ALT/STG apilados**: dos zonas relacionadas van en un solo rótulo, una encima de otra con la palabra entre ellas y una sola línea (`callout_layout.stack`). Sustituye a la nota aparte.
