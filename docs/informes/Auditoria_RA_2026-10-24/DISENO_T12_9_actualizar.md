# T12.9 — "Actualizar planos" en lugar de regenerar (diseño para aprobación)

**Estado:** aprobado e implementado (24-10-2026): `drawing_registry.py` y `nosa_utils/drawing_update.py`. Verificado en Revit 2027; ver INFORME_FINAL.md §3. Las claves `NOSA_RA_View` y `NOSA_RA_Sheet` se guardan como registro en Extensible Storage, no como parámetros.
**Alcance aprobado (decisión 7):** se conservan las posiciones de los viewports, las anotaciones propias del usuario, las etiquetas movidas cuya barra no ha cambiado, y el recorte y la escala de las vistas.

## 1. Cómo se identifican los elementos del plugin

| Elemento | Marca de identidad (ya existe o se añade) |
|---|---|
| Hojas 45xx / 55xx | Número en la serie del plugin y `NOSA_BBS_*` (BBS). **Nuevo:** `NOSA_RA_Sheet = <clave de dibujo>`. |
| Vistas | **Nuevo:** `NOSA_RA_View = <host id>\|<tipo de vista>\|<clave>` (por ejemplo `1513973\|plan\|S1`), escrito al crearla. |
| Etiquetas, MRA, líneas de detalle, cotas, notas | **Nuevo:** registro por vista guardado en *Extensible Storage* de la propia vista: lista de ids creados por el plugin, con huella geométrica (posición de cabeza, codo y extremo) y la clave de la barra (`mark` + id de la barra). |
| Barras | `NOSA_Rebar_Batch_Id`, `NOSA_Rebar_Mark`, `NOSA_Rebar_Group`, `NOSA_Rebar_Assembly` (ya existen). |

Cualquier elemento de una vista que no esté en el registro es **del usuario** y nunca se toca.

## 2. Cómo se detectan las modificaciones manuales

- **Etiqueta o MRA:** se compara su posición actual con la huella guardada. Si difiere más de 0,5 mm en papel, se considera movida a mano.
- **Viewport:** se compara el centro del cuadro con el guardado al colocarlo.
- **Vista:** se comparan el recorte (CropBox) y la escala con los guardados.
- **Barra:** se recalcula su firma de identidad (`_dedup_key` + número de posiciones + varying). Si cambia, la barra se considera **modificada** en el modelo.

## 3. Qué se conserva, qué se actualiza y qué se reconstruye

| Caso | Acción |
|---|---|
| Viewport movido por el usuario | Se conserva su posición; los viewports nuevos se colocan en el espacio libre. |
| Recorte o escala cambiados por el usuario | Se conservan; el layout de etiquetas de esa vista se rehace dentro de ese recorte. |
| Anotación del usuario | Se conserva siempre, sin moverla ni borrarla. |
| Etiqueta movida y barra sin cambios | Se conserva (incluida su línea de referencia); solo se actualiza su texto si cambió la marca. |
| Etiqueta no movida y barra sin cambios | Se conserva tal cual. |
| Barra modificada (marca, cantidad, forma o geometría) | Se borran solo las anotaciones del plugin de esa barra y se recolocan respetando las del usuario y las movidas. |
| Barra nueva | Se anota con el algoritmo actual, evitando lo conservado. |
| Barra eliminada | Se borran sus anotaciones del plugin. Si el usuario había movido alguna, se informa en la revisión antes de borrarla. |
| Miembro nuevo | Vistas nuevas en la hoja de su tipo, o en una hoja de continuación (M7). |
| BBS | Se regenera siempre a partir del modelo: es un dato y no lleva ajustes manuales. |

## 4. Cómo se evitan duplicados y pérdidas de trabajo

- Antes de crear, se busca por clave `NOSA_RA_View` / `NOSA_RA_Sheet`. Si ya existe, se reutiliza y nunca se crea una segunda.
- Todo se hace en un **TransactionGroup**. Ante cualquier error, se deshace entero y el plano queda como estaba.
- La revisión automática se ejecuta igual que ahora (A1–A9) y añade una lista de lo conservado, lo actualizado y lo eliminado.
- Las marcas siguen el criterio de M1: se conservan las marcas existentes del plano y solo reciben número nuevo las barras nuevas. Así, las etiquetas conservadas siguen siendo válidas.
- "Regenerar" (el comportamiento actual) sigue disponible como opción explícita.

## 5. Pruebas previstas

- **Unitarias (puras):** decidir conservar, actualizar o reconstruir a partir de huellas; detección de movimiento; renumeración solo de barras nuevas.
- **En Revit** (modelo de pruebas, sin guardar):
  1. Mover a mano 2 etiquetas y 1 viewport y cambiar el recorte de 1 vista.
  2. Añadir una nota propia.
  3. Modificar una barra.
  4. Pulsar "Actualizar".
  5. Comprobar que lo manual se conserva, que la barra modificada se reanota, que no hay duplicados, y que A8 = A9 = 0 y el cross-check del BBS sale limpio.
