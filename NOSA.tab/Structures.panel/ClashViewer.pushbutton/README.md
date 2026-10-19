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
6. **Reset view** quita aislamiento, colores y caja de sección. **Export list…** guarda la lista filtrada con el
   estado de localización en CSV.

Opciones: *Isolate*, *Permanent* (aislamiento permanente; la vista se reconstruye al resetear o al pasar al siguiente
clash), *Dim the rest* (halftone cuando no se aísla), *Keep camera*. En *View settings*: margen de la caja (m), recorte
alrededor del punto del clash (m, 0 = desactivado, útil para elementos muy largos) y colores `#RRGGBB`.

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

- Revit no permite colorear **un elemento concreto de un vínculo**: los elementos vinculados se aíslan (instancia del
  vínculo recortada por la caja de sección) y quedan **seleccionados**, pero sin color propio. Los del modelo activo sí se colorean.
- Los elementos de **AutoCAD Plant 3D** no existen en Revit: se muestran como tales y la vista se centra en el punto del
  clash. Solo se buscan por `Tag` / `PnPGuid` en DirectShapes del modelo activo.
- No se dibuja marcador (esfera) en el punto del clash para no añadir elementos al modelo.
- Rendimiento medido con el informe real (1001 clashes): carga 2,7 s en IronPython 2.7 y 3,0 s en IronPython 3.4.
