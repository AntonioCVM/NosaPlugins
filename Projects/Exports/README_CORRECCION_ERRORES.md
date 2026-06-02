# Scripts de Corrección de Errores de Revit

## 📍 Ubicación
Todos los scripts están en la carpeta de NOSA:
```
C:\Users\AntonioCViñas\AppData\Roaming\pyRevit\Extensions\NOSA.extension\Projects\Exports\
```

## 🚀 Inicio Rápido

### Opción 1: Ejecutar Todo Automáticamente (RECOMENDADO)

```python
exec(open(r'C:\Users\AntonioCViñas\AppData\Roaming\pyRevit\Extensions\NOSA.extension\Projects\Exports\EJECUTAR_TODOS_LOS_SCRIPTS.py').read())
```

Este script ejecuta automáticamente todos los scripts de corrección.

### Opción 2: Ejecutar Scripts Individualmente

1. **fix_revit_errors.py** - Corrige elementos unidos, muros adjuntos y pisos superpuestos
2. **fix_stair_errors.py** - Identifica problemas de escaleras
3. **fix_remaining_errors.py** - Identifica vigas/líneas fuera de eje y líneas de propiedad

## 📋 Archivos Disponibles

- ✅ **EJECUTAR_TODOS_LOS_SCRIPTS.py** - Script maestro (ejecuta todo)
- ✅ **fix_revit_errors.py** - Corrección principal de errores
- ✅ **fix_stair_errors.py** - Análisis de escaleras
- ✅ **fix_remaining_errors.py** - Errores restantes
- 📖 **INSTRUCCIONES.md** - Documentación completa
- 📖 **README_CORRECCION_ERRORES.md** - Este archivo

## ⚠️ Importante

- **Haz una copia de seguridad** del modelo antes de ejecutar
- Algunos errores requieren **ajuste manual** (especialmente escaleras)
- Los scripts crean **transacciones** en Revit (cambios se guardan automáticamente)

## 📊 Errores que se Corrigen Automáticamente

- ✅ 24 pares de elementos unidos que no se intersectan
- ✅ 3 muros adjuntos que no alcanzan objetivos  
- ✅ 103+ pares de pisos superpuestos

## 🔧 Errores que Requieren Ajuste Manual

- ⚠️ 6 vigas fuera de eje
- ⚠️ 2 líneas fuera de eje
- ⚠️ 1 línea de propiedad sin bucle cerrado
- ⚠️ 99+ problemas de escaleras (varios tipos)

## 📝 Para Más Información

Consulta el archivo **INSTRUCCIONES.md** para documentación detallada.








