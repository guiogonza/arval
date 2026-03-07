# 🔧 Guía de Resolución de Problemas

## 🚨 Problema: Error de autenticación PostgreSQL

### Síntomas
```
psycopg2.OperationalError: FATAL: password authentication failed for user "postgres"
```

### Causa Raíz

**El problema ocurre cuando:**
1. Un volumen de Docker de PostgreSQL ya existe con datos antiguos
2. La contraseña en el volumen NO coincide con la definida en `docker-compose.yml`
3. PostgreSQL **NO reinicializa** la contraseña cuando se inicia con un volumen existente

**¿Por qué sucede esto?**
- PostgreSQL solo inicializa la base de datos (y la contraseña) en el **primer arranque** cuando el directorio de datos está vacío
- Si el volumen ya tiene datos, PostgreSQL usa la contraseña existente en esos datos
- Las variables de entorno `POSTGRES_PASSWORD` en `docker-compose.yml` son **ignoradas** si el volumen ya existe

### Solución Rápida

```bash
# 1. Detener los contenedores
docker-compose down

# 2. IMPORTANTE: Hacer backup si hay datos importantes
docker run --rm -v geotab_postgres_data:/data -v $(pwd):/backup ubuntu tar czf /backup/postgres_backup_$(date +%Y%m%d_%H%M%S).tar.gz /data

# 3. Eliminar el volumen corrupto
docker volume rm geotab_postgres_data

# 4. Recrear los contenedores
docker-compose up -d

# 5. Verificar logs
docker logs geotab_app --tail 50
```

### Prevención - Mejores Prácticas

#### 1. **Usar nombres de volumen únicos**

Modifica `docker-compose.yml` para usar nombres de volumen versionados:

```yaml
volumes:
  postgres_data_v1:  # Agregar versión

services:
  postgres:
    volumes:
      - postgres_data_v1:/var/lib/postgresql/data
```

#### 2. **Script de inicialización con verificación**

Crea un archivo `scripts/init_db.sh`:

```bash
#!/bin/bash
set -e

# Verificar si el volumen existe
if docker volume inspect geotab_postgres_data > /dev/null 2>&1; then
    echo "⚠️  ADVERTENCIA: El volumen geotab_postgres_data ya existe"
    echo "¿Quieres eliminarlo y recrearlo? (s/n)"
    read -r response
    if [[ "$response" =~ ^[Ss]$ ]]; then
        docker-compose down
        docker volume rm geotab_postgres_data
        echo "✅ Volumen eliminado"
    fi
fi

# Iniciar servicios
docker-compose up -d
echo "✅ Servicios iniciados"
```

#### 3. **Variables de entorno externas**

En lugar de hardcodear contraseñas, usa el archivo `.env`:

```bash
# .env
POSTGRES_PASSWORD=tu_contraseña_segura_aqui
```

Y en `docker-compose.yml`:

```yaml
services:
  postgres:
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  
  app:
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
```

#### 4. **Comando de verificación de salud**

Agrega este comando al `docker-compose.yml` para detectar problemas temprano:

```yaml
services:
  app:
    healthcheck:
      test: ["CMD", "python", "-c", "import psycopg2; psycopg2.connect(host='postgres', user='postgres', password='postgres', database='geotab_gps')"]
      interval: 30s
      timeout: 5s
      retries: 3
```

#### 5. **Documentar el estado esperado**

Crea un archivo `DEPLOYMENT_CHECKLIST.md`:

```markdown
## Checklist de Despliegue

### Pre-despliegue
- [ ] Verificar que no existan volúmenes antiguos: `docker volume ls | grep geotab`
- [ ] Confirmar credenciales en `.env`
- [ ] Hacer backup de datos existentes (si aplica)

### Despliegue
- [ ] `docker-compose down` (si hay contenedores corriendo)
- [ ] `docker-compose up -d`
- [ ] Esperar 30 segundos para inicialización

### Post-despliegue
- [ ] Verificar logs: `docker logs geotab_app --tail 50`
- [ ] Verificar conectividad: `curl http://localhost:5000`
- [ ] Verificar datos: `docker exec geotab_postgres psql -U postgres -d geotab_gps -c 'SELECT COUNT(*) FROM dispositivos;'`
```

### Script de Diagnóstico Automático

Crea `scripts/diagnose.sh`:

```bash
#!/bin/bash

echo "🔍 Diagnóstico de Geotab GPS Tracker"
echo "===================================="
echo ""

# 1. Verificar contenedores
echo "📦 Estado de contenedores:"
docker ps --filter "name=geotab" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# 2. Verificar volúmenes
echo "💾 Volúmenes de PostgreSQL:"
docker volume ls | grep geotab
echo ""

# 3. Verificar logs de app
echo "📝 Últimos logs de la aplicación:"
docker logs geotab_app --tail 10
echo ""

# 4. Verificar conexión a PostgreSQL
echo "🔌 Verificando conexión a PostgreSQL:"
if docker exec geotab_postgres psql -U postgres -d geotab_gps -c '\q' > /dev/null 2>&1; then
    echo "✅ Conexión exitosa"
    
    # Verificar datos
    echo ""
    echo "📊 Conteo de registros:"
    docker exec geotab_postgres psql -U postgres -d geotab_gps -c 'SELECT COUNT(*) as dispositivos FROM dispositivos; SELECT COUNT(*) as ubicaciones FROM ubicaciones;'
else
    echo "❌ Error de conexión a PostgreSQL"
fi

echo ""
echo "🌐 Endpoints:"
echo "   - Aplicación: http://localhost:5000"
echo "   - Estadísticas: http://localhost:5000/estadisticas"
```

Hazlo ejecutable:
```bash
chmod +x scripts/diagnose.sh scripts/init_db.sh
```

### Monitoreo Continuo

#### Agregar alertas en el código

Modifica `database.py` para registrar intentos fallidos:

```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_connection():
    """Obtiene conexión a la base de datos PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info("✅ Conexión exitosa a PostgreSQL")
        return conn
    except psycopg2.OperationalError as e:
        logger.error(f"❌ Error de conexión a PostgreSQL: {e}")
        logger.error(f"🔧 Configuración: host={DB_CONFIG['host']}, user={DB_CONFIG['user']}")
        raise
```

### Resumen de Lecciones Aprendidas

1. **Los volúmenes de Docker persisten datos entre recreaciones de contenedores**
2. **PostgreSQL NO cambia contraseñas en volúmenes existentes**
3. **Siempre verificar volúmenes existentes antes de desplegar**
4. **Usar scripts de inicialización con verificaciones**
5. **Documentar el estado esperado del sistema**

### Comandos Útiles

```bash
# Ver todos los volúmenes
docker volume ls

# Inspeccionar un volumen
docker volume inspect geotab_postgres_data

# Hacer backup de un volumen
docker run --rm -v geotab_postgres_data:/data -v $(pwd):/backup ubuntu tar czf /backup/postgres_backup.tar.gz /data

# Restaurar un volumen
docker run --rm -v geotab_postgres_data:/data -v $(pwd):/backup ubuntu tar xzf /backup/postgres_backup.tar.gz -C /

# Eliminar volumen (¡cuidado!)
docker volume rm geotab_postgres_data

# Ver contraseña actual en PostgreSQL (dentro del contenedor)
docker exec geotab_postgres psql -U postgres -c "SELECT * FROM pg_shadow;"
```

## 🔐 Rotación de Contraseñas

Si necesitas cambiar la contraseña de PostgreSQL en producción:

```bash
# 1. Conectarse al contenedor
docker exec -it geotab_postgres psql -U postgres

# 2. Cambiar contraseña
ALTER USER postgres WITH PASSWORD 'nueva_contraseña';
\q

# 3. Actualizar .env
vim .env  # Cambiar POSTGRES_PASSWORD

# 4. Recrear contenedor de la app
docker-compose up -d --no-deps --build app
```

---

**Última actualización:** 26 de febrero de 2026  
**Autor:** Sistema Geotab GPS Tracker
