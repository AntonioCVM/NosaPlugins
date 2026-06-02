# Script de Dimensionado de Muros en Planta

## Descripción
Script para crear dimensiones automáticas de muros en vistas de planta con soporte para muros rectos y arcos.

## Ubicación
`dimensionar_muros_planta.py`

## Mejoras Implementadas

### 1. **Compatibilidad con pyRevit**
- Adaptado para usar `from pyrevit import revit` en lugar de referencias complejas
- Uso de `revit.Transaction()` para manejo de transacciones más limpio
- Integración con el sistema de logging de pyRevit

### 2. **Manejo de Errores Mejorado**
- Try-except más específicos en funciones críticas
- Logging detallado con niveles apropiados (debug, info, warning, error)
- Fallbacks para casos donde la API puede fallar

### 3. **Soporte para Versiones de Revit**
- Detección automática de disponibilidad de `NewArcLengthDimension` (solo Revit 2024+)
- Fallback a dimensiones lineales para versiones anteriores
- Manejo robusto de geometría de arcos

### 4. **Optimizaciones de Rendimiento**
- Cache de vectores de muros para evitar recálculos
- Mejor filtrado de bordes verticales
- Detección más eficiente de espacios libres para dimensiones

### 5. **Gestión de Configuración**
- Guardado automático de offset predeterminado
- Archivo de configuración separado (`dimension_walls_config.json`)
- Carga automática de valores predeterminados

### 6. **Validaciones Mejoradas**
- Verificación de existencia de niveles antes de mostrar diálogo
- Validación de referencias antes de crear dimensiones
- Detección de duplicados mejorada

### 7. **Manejo de Geometría**
- Mejor detección de bordes verticales (tolerancia ajustada)
- Manejo robusto de muros con geometría compleja
- Soporte mejorado para muros arqueados

### 8. **Interfaz de Usuario**
- Mensajes de error más claros
- Resumen de resultados al finalizar
- Contador de dimensiones creadas y muros procesados

## Uso

1. Ejecutar el script desde pyRevit
2. Seleccionar opciones:
   - **Nivel**: Todos los niveles o nivel específico
   - **Cara**: Externa o Interna
   - **Distancia de offset**: En milímetros
   - **Tipo de dimensionado**: 
     - **Wall Thickness**: Dimensiona el espesor del muro
     - **Overall**: Dimensiona la longitud total del muro

## Problemas Conocidos y Soluciones

### Problema: No se crean dimensiones para algunos muros
**Solución**: 
- Verificar que el muro tenga geometría sólida válida
- Comprobar que exista una vista de planta para el nivel
- Revisar los logs para detalles específicos

### Problema: Dimensiones se superponen
**Solución**: 
- El script intenta encontrar espacio libre automáticamente
- Si persiste, aumentar la distancia de offset
- El script incrementa el offset automáticamente hasta 10 intentos

### Problema: Muros arqueados no se dimensionan correctamente
**Solución**: 
- En Revit 2024+ se usa dimensiones de longitud de arco
- En versiones anteriores se usa dimensiones lineales como fallback
- Verificar que el muro tenga referencias válidas

## Configuración

El script guarda automáticamente la última distancia de offset utilizada en `dimension_walls_config.json`.

## Logs

Los logs se guardan en la carpeta de logs de pyRevit y contienen información detallada sobre:
- Muros procesados
- Dimensiones creadas
- Errores encontrados
- Advertencias

## Notas Técnicas

- El script usa tolerancia de 0.01 unidades internas para comparaciones
- El incremento de offset es de 10mm por intento
- Máximo de 10 intentos para encontrar espacio libre
- Cache de vectores se mantiene durante la ejecución

## Mejoras Futuras Sugeridas

1. **Filtrado de muros**: Permitir seleccionar muros específicos
2. **Estilos de dimensión**: Permitir seleccionar tipo de dimensión
3. **Agrupación**: Agrupar dimensiones relacionadas
4. **Preview**: Vista previa antes de crear dimensiones
5. **Undo mejorado**: Mejor manejo de deshacer operaciones

