# Script de Dynamo para Editar Curvas de Contorno de Toposólido

Basado en el video: [Revit Arazi Modelleme | #3 Arazi Model Eğrilerini Düzenleme](https://www.youtube.com/watch?v=z3lT4u7LXHI)

## Descripción

Este conjunto de scripts permite editar las curvas de contorno de un toposólido en Revit usando Dynamo, aplicando suavizado y ajustes de elevación para hacer las curvas más fluidas.

## Archivos Incluidos

1. **EditToposolidContourCurves.py** - Script Python básico para Dynamo
2. **EditToposolidContourCurves_Complete.py** - Script Python completo con más funcionalidades
3. **EditToposolidContourCurves_Simplified.dyn** - Guía de estructura del graph de Dynamo
4. **EditToposolidContourCurves.dyn** - Documentación de nodos requeridos

## Instrucciones de Uso

### Opción 1: Usar Script Python en Dynamo

1. Abre Dynamo en Revit
2. Añade un nodo **Python Script** al canvas
3. Copia el contenido de `EditToposolidContourCurves_Complete.py`
4. Pega el código en el nodo Python
5. Conecta los inputs:
   - **IN[0]**: Toposólido (usar nodo "Select Model Element" o "All Elements of Category")
   - **IN[1]**: Smoothing Factor (0.0 a 1.0) - Opcional, default: 0.5
   - **IN[2]**: Elevation Offset (double) - Opcional, default: 0.0
   - **IN[3]**: Apply Smoothing (bool) - Opcional, default: True

### Opción 2: Crear Graph Visual en Dynamo

Sigue la estructura descrita en `EditToposolidContourCurves_Simplified.dyn`:

#### Paso 1: Seleccionar Toposólido
- Usa **Categories** → **Toposolid**
- Conecta a **All Elements of Category**
- O usa **Select Model Element** para selección manual

#### Paso 2: Obtener Curvas de Contorno
- Busca el nodo **Toposolid.GetContourCurves** (si está disponible)
- Si no existe, usa **Element.Geometry** y filtra las curvas

#### Paso 3: Extraer Elevaciones
- Usa **Curve.StartPoint** y **Curve.EndPoint**
- Extrae componente Z con **Point.Z**

#### Paso 4: Aplicar Suavizado (Opcional)
- Usa un **Code Block** para aplicar algoritmo de suavizado
- Ejemplo:
  ```
  avg = (prev + curr + next) / 3.0;
  newZ = curr * 0.6 + avg * 0.4;
  ```

#### Paso 5: Crear Nuevas Curvas
- Usa **Curve.Translate** con vector (0, 0, elevationChange)
- O recrea curvas con **Line.ByStartPointEndPoint**

#### Paso 6: Actualizar Toposólido
- Si existe **Toposolid.EditContourCurves**, úsalo
- Si no, exporta puntos y recrea con **Toposolid.ByPoints**

## Parámetros

### Smoothing Factor (Factor de Suavizado)
- **Rango**: 0.0 a 1.0
- **0.0**: Sin suavizado (mantiene elevaciones originales)
- **0.5**: Suavizado moderado (recomendado)
- **1.0**: Suavizado máximo (todas las elevaciones al promedio)

### Elevation Offset (Desplazamiento Vertical)
- **Tipo**: Double (en unidades del proyecto)
- **Uso**: Ajustar todas las elevaciones por una cantidad fija
- **Ejemplo**: 2.0 para subir 2 unidades, -1.5 para bajar 1.5 unidades

## Limitaciones

1. **API de Revit**: Algunos métodos pueden no estar disponibles en todas las versiones de Revit
2. **Curvas Complejas**: Las curvas muy complejas (splines NURBS) se simplifican a líneas
3. **Rendimiento**: Toposólidos con muchas curvas pueden tardar en procesarse

## Solución de Problemas

### Error: "No se encontraron curvas de contorno"
- Verifica que el toposólido tenga curvas de contorno visibles
- Intenta usar **Element.Geometry** en lugar de métodos directos

### Error: "El elemento seleccionado no es un toposólido"
- Asegúrate de seleccionar un elemento de tipo Toposolid
- Usa **Element.ElementType** para verificar el tipo

### Las curvas no se actualizan
- Verifica que la transacción esté activa
- Intenta recrear el toposólido en lugar de editarlo directamente
- Exporta los puntos a CSV y usa **Toposolid.CreateFromImport**

## Notas Adicionales

- El script genera puntos adicionales para recrear el toposólido si es necesario
- Los resultados incluyen tanto las curvas modificadas como los puntos para recreación
- Se recomienda hacer una copia de seguridad del modelo antes de ejecutar

## Versión

- **Versión**: 1.0
- **Fecha**: 2025
- **Compatible con**: Revit 2020+ (puede requerir ajustes según versión)



