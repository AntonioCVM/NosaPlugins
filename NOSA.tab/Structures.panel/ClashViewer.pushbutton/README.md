# Clash Viewer

Lee un informe de clashes de Navisworks maquetado en Excel (`.xlsm` / `.xlsx`), muestra los clashes en un
árbol navegable y, al elegir uno, localiza los dos elementos en Revit, los aísla y los resalta en una vista
3D propia con la caja de sección ajustada.

Ribbon: **NOSA ▸ Structures ▸ Clash Viewer**. La ventana es *modeless*: se puede navegar el modelo con ella abierta.

## Instalación

El botón ya forma parte de la extensión. Tras actualizar la extensión hay que **reiniciar Revit** (un botón
nuevo no aparece con *pyRevit Reload*). No necesita Excel ni `openpyxl`: el `.xlsm` se lee como OOXML
(zip + XML) con la librería estándar, en IronPython 2.7 y en IronPython 3.

## Uso

1. **Load report…** y elige el `.xlsm`. Se recuerda el último archivo y se recarga al abrir la ventana.
2. Filtra: texto (nombre de clash, Element Id, tag, familia, categoría, responsable), test, *assigned to*,
   categoría, modelo (nombre completo del `.nwc`; coincide si cualquiera de los dos elementos es de ese modelo) y estado. Por defecto se ocultan *Approved* y *Resolved*.
3. Selecciona un clash en el árbol (**test ▸ grupo ▸ clash**): el panel derecho muestra miniatura, estado,
   responsable, fecha, punto, y una ficha por elemento con su situación en Revit
   (*Found in the active model / Found in link X / Not found / Id found but category differs / Link not loaded /
   AutoCAD Plant item - not present in Revit*).
4. **Go to clash** (o doble clic / `Enter`): crea o reutiliza la vista 3D `CLASH_VIEWER_<usuario>`, ajusta la caja
   de sección (unión de ambos elementos + margen), orienta la vista, colorea el elemento 1 en rojo y el 2 en azul,
   aísla, selecciona y hace zoom. Todo en transacciones `NOSA — Clash Viewer: …` (se puede deshacer con `Ctrl+Z`).
5. **Previous / Next** (`Ctrl+←` / `Ctrl+→`) recorren la lista filtrada y van directamente al clash.
6. **Done y notas**: la casilla *Done* del panel de detalle (o `Ctrl+D`, o clic derecho en el árbol) marca el clash como tratado. En el árbol
   cada clash se ve con **fondo verde claro si está Done y rojo claro si sigue abierto**; un ✎ indica que tiene nota. Clic derecho sobre un grupo o un
   test permite *Mark all as done* / *Reopen all*. La **nota** (texto libre) se guarda al salir del cuadro. El filtro **REVIEW** (*All / Open / Done*) muestra solo
   lo pendiente o solo lo hecho. No es el estado *Resolved* de Navisworks: es una marca del equipo, independiente del Excel, que nunca se modifica.
7. **Re-check** (panel de detalle; **automático** al seleccionar el clash, desactivable en *View settings*): intersecta los dos elementos tal como están ahora en el modelo (tolerancia del test) y dice
   *Still clashing (≈ N cm³)*, *No longer clashing* o *Cannot check* (elemento no encontrado, sin geometría o fallo del booleano; un fallo nunca se
   cuenta como "resuelto"). Es orientativo: la geometría de Revit y la de Navisworks no son idénticas.
   Cada elemento tiene su botón **Select**, que selecciona *solo* ese elemento en Revit y hace zoom (también si está en un vínculo), y una barra de color
   (rojo = elemento 1, azul = elemento 2) igual a la de la vista 3D, para saber qué elemento es de qué modelo.
8. **Report…** genera un único `.html` (se abre en el navegador y se imprime a PDF) con, por cada clash de la lista actual: la imagen original del Excel
   ("As reported") junto a la imagen tomada de Revit en ese momento ("Now"), estado, Done, nota, estado de los elementos y el re-check. Tarda unos
   2 s por clash, con barra de progreso y botón *Cancel*; no modifica el modelo (solo usa la vista `CLASH_VIEWER_<usuario>`).
9. **Reset view** quita aislamiento, colores y caja de sección. **Export list…** guarda la lista filtrada con el
   estado de localización en CSV.

Opciones: *Isolate*, *Permanent* (aislamiento permanente; la vista se reconstruye al resetear o al pasar al siguiente
clash), *Dim the rest* (halftone cuando no se aísla), *Keep camera*. En *View settings*: margen de la caja (m), recorte
alrededor del punto del clash (m, 0 = desactivado, útil para elementos muy largos) y colores `#RRGGBB`.

### Dónde se guardan las marcas *Done*

En `<código del documento>.clashreview.json` **junto al informe** (p. ej. `UWWTP-AA-00-BM-RP-00002.clashreview.json`), de modo que
todo el equipo ve las mismas marcas. El nombre usa el código del documento, no la revisión, así que al llegar una revisión nueva
del informe (P07…) las marcas se conservan mientras los clashes mantengan su nombre (`Clash74`) en el mismo test. Cada marca guarda
quién y cuándo. Si la carpeta es de solo lectura se usa una copia local en `NOSA_Configs` y la ventana lo avisa. Dos personas pueden
marcar a la vez: cada cambio se fusiona con lo que hay en disco antes de guardar. La exportación CSV incluye *Done / Done by / Done on*.

## Elementos de vínculos y de AutoCAD

Revit no permite colorear ni aislar *un* elemento de un vínculo Revit. Para poder verlos, el visor crea **copias temporales** (*DirectShape* de Modelos
genéricos, marcadas `NOSA.ClashViewer.proxy`) en el proyecto activo, las colorea y las aísla en lugar de aislar todo el vínculo.
**Los CAD no se copian**: son líneas 3D con los colores de sus capas, así que se aísla el vínculo CAD (recortado por la caja de sección) y se deja tal cual. Se eliminan al pulsar
**Reset view**, al pasar al siguiente clash y al cerrar la ventana; si Revit se cerrara a la fuerza, se barren al abrir el visor de nuevo. Se pueden
desactivar en *View settings* (entonces se aísla la instancia completa del vínculo). Las copias se pueden deshacer con `Ctrl+Z` como cualquier cambio.
En un modelo con worksharing no se tocan las copias que tenga reservadas otro usuario.

Los modelos de **AutoCAD (Plant 3D)** vinculados como CAD (`.dwg`) ahora se reconocen por el nombre del modelo. Revit no conserva el `PnPGuid`, así que el objeto
concreto se busca **por posición**: se toman los objetos del CAD cuya caja contiene el punto del clash (los más pequeños, cerca del otro elemento); se usan
para encuadrar la vista y la caja de sección. Es orientativo; si el CAD tiene muchos objetos la primera lectura puede tardar unos segundos (se guarda en caché).
Si el modelo está como vínculo Revit se aísla la instancia y se muestra el entorno del punto.

## Cómo se localizan los elementos

1. El *Path* `.nwc` se compara con el modelo activo y los vínculos (por nombre base o por el código
   `PROYECTO-AUTOR-ZONA-DISC-TIPO-NNNNN`, ignorando sufijos como `_detached` o el usuario).
2. Se busca por `UniqueId` y, si falla, por `Element Id`; se valida que la categoría coincida con *Element Category*
   (también con revit en otro idioma, usando el nombre `OST_`). Si hay `Element Id` repetido entre host y vínculo, solo se
   acepta el del modelo emparejado.
3. En vínculos se transforman las cajas con `RevitLinkInstance.GetTotalTransform()` y se selecciona la referencia del
   elemento vinculado.
4. El punto del clash (mm, coordenadas compartidas) se convierte a coordenadas internas del modelo activo; si queda muy
   lejos de los elementos se avisa de que las coordenadas compartidas pueden no estar establecidas.

Si el nombre del `.nwc` no coincide con ningún modelo, añade una equivalencia en
`%APPDATA%\pyRevit\Extensions\NOSA.extension\NOSA_Configs\_clash_viewer.json`:

```json
{ "model_map": { "UWWTP-AA-10-AR-MD-00001": ["Nombre del vínculo en Revit"] } }
```

## Estructura

| Archivo | Contenido |
|---|---|
| `lib/clash_reader.py` | Parser `.xlsm` → `ClashReport` / `ClashTest` / `Clash` / `ClashItem`. Sin Revit, sin dependencias. Detecta hojas por la cabecera `Clash Name`, columnas por nombre de cabecera, imágenes por los anclajes del dibujo (se leen bajo demanda). |
| `lib/clash_locator.py` | Búsqueda en documento activo y vínculos, conversión de coordenadas. |
| `lib/clash_view.py` | Vista 3D, caja de sección, overrides, aislamiento, selección, reset. |
| `lib/ui.py`, `lib/ui.xaml` | Ventana `NOSAWindow` modeless; las acciones sobre Revit pasan por un `ExternalEvent`. |
| `tests/` | `python -m unittest discover -s tests`. Parser contra el informe real (si está disponible) y contra un libro sintético; heurística de nombres sin Revit. |

## Límites conocidos

- Los elementos vinculados y los objetos de CAD se colorean mediante copias temporales (ver arriba); con esa opción desactivada solo se aísla el vínculo y se selecciona.
- Los elementos de **AutoCAD Plant 3D** no existen en Revit: se muestran como tales y la vista se centra en el punto del
  clash. Solo se buscan por `Tag` / `PnPGuid` en DirectShapes del modelo activo.
- La tecla `Esc` no cierra la ventana (pyRevit lo hace por defecto; aquí está desactivado).
- No se dibuja marcador (esfera) en el punto del clash para no añadir elementos al modelo.
- Rendimiento medido con el informe real (1001 clashes): carga 2,7 s en IronPython 2.7 y 3,0 s en IronPython 3.4.
- El *Re-check* usa la geometría actual de Revit: dos elementos **unidos** (*Join Geometry*, o muros que Revit une solos al cruzarse) tienen la
  geometría ya recortada y salen como *No longer clashing* aunque Navisworks los siga marcando. El solape se mide en volumen (umbral 1 cm³); no replica
  la tolerancia de Navisworks al milímetro.
- Si el objeto de AutoCAD se importó como malla (no como sólido), el re-check no puede intersectarlo y lo indica.
- Las imágenes "Now" del informe son **cuadradas** (640 px) y se muestran al mismo tamaño que la imagen original de Navisworks; la vista se recorta (*crop box*)
  alrededor de la zona del clash, de modo que un elemento largo o un CAD enorme no dejen el clash como un detalle diminuto. El recorte se quita al terminar cada imagen.
- **Elementos unidos con Join Geometry**: Revit recorta la geometría de los elementos unidos, así que el solape desaparece aunque Navisworks (que ve las formas
  originales) lo siga marcando. Si el re-check no encuentra solape pero los elementos están unidos, el visor los des-une dentro de una transacción que se deshace,
  mide el solape sin la unión y, si existe, muestra **"Joined in Revit"** (ámbar) en lugar de "No longer clashing". El modelo no cambia.
