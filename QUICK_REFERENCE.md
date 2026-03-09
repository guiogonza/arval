# ⚡ Guía Rápida de Referencia - Geotab GPS Tracker

## 🚀 Comandos Esenciales

### Iniciar Sistema
```bash
# Opción 1: Inicialización automática con verificaciones
.\scripts\init_db.ps1  # Windows
bash scripts/init_db.sh  # Linux/Mac

# Opción 2: Inicio directo
docker-compose up -d
```

### Verificar Estado
```bash
# Diagnóstico completo
.\scripts\diagnose.ps1  # Windows
bash scripts/diagnose.sh  # Linux/Mac

# Ver contenedores
docker-compose ps

# Ver logs en tiempo real
docker-compose logs -f

# Ver logs específicos
docker logs geotab_app --tail 50
docker logs geotab_postgres --tail 50
```

### Detener Sistema
```bash
docker-compose down  # Detiene pero conserva datos
docker-compose down -v  # Detiene y elimina volúmenes (¡PELIGRO!)
```

---

## 🔧 Solución Rápida de Problemas

### ❌ Error de Autenticación PostgreSQL
```bash
docker-compose down
docker volume rm geotab_postgres_data
docker-compose up -d
```

### ❌ Puerto Ocupado
```bash
# Ver qué está usando el puerto
docker ps | grep 5003

# Cambiar puerto en docker-compose.yml
ports:
  - "NUEVO_PUERTO:5000"
```

### ❌ Contenedor Reiniciando
```bash
# Ver logs para identificar el error
docker logs geotab_app --tail 100

# Reconstruir imagen
docker-compose build --no-cache
docker-compose up -d
```

### ❌ Base de Datos Sin Datos
```bash
# Verificar sincronización
docker logs geotab_app | grep "Sincronizados"

# Forzar sincronización (reiniciar app)
docker-compose restart app
```

---

## 💾 Backups

### Crear Backup
```bash
# Backup de volumen PostgreSQL
docker run --rm \
  -v geotab_postgres_data:/data \
  -v $(pwd):/backup \
  ubuntu tar czf /backup/postgres_backup_$(date +%Y%m%d).tar.gz /data
```

### Restaurar Backup
```bash
# 1. Detener servicios
docker-compose down

# 2. Eliminar volumen actual
docker volume rm geotab_postgres_data

# 3. Crear nuevo volumen vacío
docker volume create geotab_postgres_data

# 4. Restaurar datos
docker run --rm \
  -v geotab_postgres_data:/data \
  -v $(pwd):/backup \
  ubuntu tar xzf /backup/postgres_backup_YYYYMMDD.tar.gz -C /

# 5. Reiniciar servicios
docker-compose up -d
```

---

## 🔍 Consultas Útiles de Base de Datos

```bash
# Entrar a PostgreSQL
docker exec -it geotab_postgres psql -U postgres -d geotab_gps

# Ver cantidad de registros
SELECT COUNT(*) FROM dispositivos;
SELECT COUNT(*) FROM ubicaciones;
SELECT COUNT(*) FROM viajes;

# Ver últimas ubicaciones
SELECT d.placa, u.latitud, u.longitud, u.fecha 
FROM ubicaciones u 
JOIN dispositivos d ON u.dispositivo_id = d.id 
ORDER BY u.fecha DESC 
LIMIT 10;

# Ver dispositivos activos
SELECT placa, tipo_dispositivo, fecha_registro 
FROM dispositivos 
WHERE activo = 1;
```

---

## 📊 Endpoints de la Aplicación

| URL | Descripción |
|-----|-------------|
| http://localhost:5003 | Mapa principal |
| http://localhost:5003/estadisticas | Dashboard de estadísticas |
| http://164.68.118.86:5000 | Servidor remoto (mapa) |
| http://164.68.118.86:5000/estadisticas | Servidor remoto (stats) |

---

## 🔐 Gestión de Credenciales

### Archivo .env
```bash
# Ver configuración actual (sin mostrar contraseñas)
cat .env | grep -v PASSWORD

# Editar credenciales
notepad .env  # Windows
nano .env  # Linux/Mac
```

### Variables Importantes
```env
GEOTAB_USERNAME=usuario@empresa.com
GEOTAB_PASSWORD=contraseña_geotab
GEOTAB_DATABASE=Arval_col
POSTGRES_PASSWORD=postgres
```

---

## 🚨 Números de Emergencia

### Sistema No Responde
1. Verificar Docker está corriendo
2. Ejecutar diagnóstico: `.\scripts\diagnose.ps1`
3. Revisar logs: `docker-compose logs`
4. Reiniciar: `docker-compose restart`

### Datos Incorrectos
1. Verificar credenciales Geotab en `.env`
2. Forzar sincronización: `docker-compose restart app`
3. Revisar logs de sincronización

### Servidor Remoto Caído
```bash
# Conectar por SSH
ssh root@164.68.118.86

# Verificar contenedores
docker ps -a | grep geotab

# Revisar logs
docker logs geotab_app --tail 50

# Reiniciar si es necesario
cd /root/geotab
docker-compose restart
```

---

## 📁 Estructura de Archivos

```
Geotab/
├── app.py                    # Aplicación Flask principal
├── database.py               # Gestión de PostgreSQL
├── sync_service.py           # Sincronización con Geotab
├── docker-compose.yml        # Configuración Docker
├── Dockerfile                # Imagen Docker
├── .env                      # Credenciales (NO subir a Git)
├── README.md                 # Documentación principal
├── DEPLOY.md                 # Guía de despliegue
├── TROUBLESHOOTING.md        # Solución de problemas
├── INCIDENT_REPORT.md        # Reporte de incidente
├── templates/                # Plantillas HTML
│   ├── index.html
│   └── estadisticas.html
├── static/                   # Archivos estáticos
│   └── style.css
└── scripts/                  # Scripts de mantenimiento
    ├── diagnose.ps1
    ├── diagnose.sh
    ├── init_db.ps1
    └── init_db.sh
```

---

## 🔄 Flujo de Sincronización (plataforma.sistemagps.online)

```
1. Contenedor plataforma_sync inicia → Conecta Geotab + plataforma
2. Cada 5 min → client.get("LogRecord", fromDate=ahora-5m30s, toDate=ahora)
3. Todos los puntos GPS del periodo → enviados a OsmAnd (puerto 6055)
4. ~700-1000 puntos por ciclo (97 vehículos × puntos/vehículo)
5. 0 errores en condiciones normales
```

### Contenedores Docker (servidor 164.68.118.86)
| Contenedor | Script | Función |
|---|---|---|
| `geotab_app` | `app.py` | Flask web / mapa |
| `geotab_plataforma_sync` | `plataforma_live_sync.py` | Sync cada 5 min → plataforma |
| `geotab_live_sync` | `gpswox_live_sync.py` | Sync GPSWox 173 |
| `geotab_postgres` | postgres:16 | Base de datos |

### Ver logs del sync en vivo
```bash
docker logs geotab_plataforma_sync --tail 20
```

### Reconectar y redesplegar
```bash
ssh root@164.68.118.86
cd /root/geotab
docker compose build plataforma_sync
docker compose up -d plataforma_sync
```

---

## 👥 Gestión de Usuarios en Plataforma GPS

**Grupos en plataforma.sistemagps.online:**
- Grupo `Geotab` (id=7444) → 97 placas → 23 usuarios asignados
- Grupo `ARVAL` (id=7443) → 79 placas → solo 2 admins (gerencia + guiogonza)

### API correcta para reemplazar usuarios (no agregar)
```python
# 1. Ver usuarios actuales de un device
GET /api/edit_device_data?device_id=X&user_api_hash=TOKEN
# → campo sel_users

# 2. Reemplazar usuarios (device_id DEBE ir como query param, no en body)
POST /api/edit_device?device_id=X&user_api_hash=TOKEN
Body JSON: {"user_id": [id1, id2, id3]}
```

### Script de asignación masiva
```bash
python _asignar_usuarios_v2.py    # Asigna 23 usuarios a grupo Geotab (id=7444)
python _restringir_grupo_arval.py # Deja solo 2 admins en grupo ARVAL (id=7443)
```

**Admins permanentes** (nunca eliminar):
- `14682` → gerencia@rastrear.com.co
- `17234` → guiogonza@gmail.com

---

## 📦 Carga Histórica de Puntos GPS

Para cargar todos los puntos desde una fecha pasada a plataforma.sistemagps.online:

```bash
# Carga completa desde 2026-03-01 (4 workers en paralelo, día a día)
python _carga_historica.py

# Monitorear progreso
Get-Content historial_progreso.txt   # Windows PowerShell
cat historial_progreso.txt           # Linux
```

Estructura: procesa día a día, 4 placas en paralelo por día. El archivo
`historial_progreso.txt` se actualiza al completar cada día.

---

## 🔄 Flujo de Sincronización (legacy PostgreSQL)

---

## 📞 Contactos

- **Servidor remoto:** 164.68.118.86
- **Puerto aplicación:** 5000 (remoto), 5003 (local)
- **Puerto PostgreSQL:** 5433
- **Empresa:** Hesego Ingeniería
- **Cliente:** Arval Colombia

---

## 🔖 Referencias Rápidas

- **Documentación completa:** [README.md](README.md)
- **Problemas comunes:** [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Guía de despliegue:** [DEPLOY.md](DEPLOY.md)
- **Docker Compose:** `docker-compose --help`
- **PostgreSQL:** `docker exec -it geotab_postgres psql --help`

---

**💡 Tip:** Ejecuta `.\scripts\diagnose.ps1` regularmente para monitorear la salud del sistema.
