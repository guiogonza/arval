# Agent: Sistema de Rastreo GPS Geotab

## Descripción general

Aplicación web de rastreo GPS en tiempo real que conecta la **API de Geotab** con una base de datos **PostgreSQL** y opcionalmente reenvía datos a servidores **GPSWox/Traccar**. Permite monitorear flotas vehiculares con mapas interactivos, estadísticas y sincronización automática.

---

## Stack tecnológico

| Componente | Tecnología |
|---|---|
| Backend | Python 3 + Flask 3.0 |
| Base de datos | PostgreSQL (psycopg2) |
| API GPS | Geotab (mygeotab 0.8.5) |
| Reenvío GPS | GPSWox/Traccar — protocolo OsmAnd HTTP (puerto 6055) |
| Frontend | HTML + Chart.js + OpenStreetMap / Google Satellite |
| Contenedores | Docker + Docker Compose |
| Variables de entorno | python-dotenv |

---

## Arquitectura del proyecto

```
Geotab/
├── app.py                  # Aplicación Flask principal (rutas y API REST)
├── sync_service.py         # Servicio de sincronización automática cada 5 min
├── database.py             # Capa de acceso a PostgreSQL
├── geotab_client.py        # Cliente auxiliar de la API Geotab
├── enviar_gpswox.py        # Script: envío paralelo de historial GPS a GPSWox
├── extraer_placas.py       # Script: extrae placas de Geotab a SQLite (utilitario)
├── limpiar_gpswox.py       # Script: limpieza de datos en GPSWox
├── recarga_completa.py     # Script: recarga completa de datos históricos
├── revisar_campos_geotab.py# Script: diagnóstico de campos disponibles en Geotab
├── ssh_config.py           # Configuración de túnel SSH
├── templates/
│   ├── index.html          # Mapa principal con marcadores
│   └── estadisticas.html   # Dashboard de estadísticas con gráficos
├── static/                 # Archivos estáticos (CSS, JS, imágenes)
├── docker-compose.yml      # Orquestación: app Flask + PostgreSQL
├── Dockerfile              # Imagen Docker de la aplicación
├── requirements.txt        # Dependencias Python
└── scripts/
    ├── init_db.sh / .ps1   # Inicialización de base de datos
    └── diagnose.sh / .ps1  # Diagnóstico del sistema
```

---

## Módulos principales

### `app.py` — API REST Flask

Endpoints disponibles:

| Ruta | Método | Descripción |
|---|---|---|
| `/` | GET | Página principal con mapa |
| `/estadisticas` | GET | Dashboard de estadísticas |
| `/api/dispositivos` | GET | Lista de dispositivos/placas |
| `/api/ubicaciones` | GET | Última ubicación de todos los vehículos |
| `/api/viajes` | GET | Viajes de un vehículo por fecha (`?placa=&fecha=`) |

### `sync_service.py` — Sincronización automática

- Clase `SyncService` que corre en un **hilo independiente**
- Intervalo: **5 minutos** (`SYNC_INTERVAL = 300`)
- Límite de velocidad para excesos: **80 km/h**
- Operaciones: `sync_dispositivos()`, `sync_ubicaciones()`, `sync_viajes_dia()`
- Registro de cada sincronización en tabla `sync_log`

### `database.py` — Capa de datos PostgreSQL

Funciones principales:
- `get_connection()` — conexión a PostgreSQL
- `init_database()` — crea tablas si no existen
- `guardar_ubicacion()` — persiste posición GPS
- `guardar_viaje()` — persiste un viaje/recorrido
- `guardar_exceso_velocidad()` — registra infracciones
- `actualizar_resumen_diario()` — agrega km por vehículo/día
- `log_sync()` — auditoría de sincronizaciones
- `get_estadisticas_por_fecha()`, `get_vehiculos_sin_reportar()`, `get_resumen_por_placa_fecha()`

### `enviar_gpswox.py` — Integración GPSWox

- Envío **asíncrono y paralelo** con `aiohttp` (20 conexiones simultáneas)
- Protocolo: **OsmAnd HTTP** al puerto 6055
- Sensores enviados desde diagnósticos Geotab:

| Diagnóstico Geotab | Parámetro OsmAnd |
|---|---|
| `DiagnosticIgnitionId` | `ignition` |
| `DiagnosticOdometerId` | `totalDistance` |
| `DiagnosticFuelLevelId` | `fuel` |
| `DiagnosticGoDeviceVoltageId` | `power` |
| `DiagnosticEngineSpeedId` | `rpm` |
| `DiagnosticEngineCoolantTemperatureId` | `coolantTemp` |
| `DiagnosticOutsideTemperatureId` | `driverTemp` |
| `DiagnosticDriverSeatbeltId` | `seatbelt` |

---

## Variables de entorno requeridas

```env
# Credenciales Geotab
GEOTAB_USERNAME=usuario@empresa.com
GEOTAB_PASSWORD=contraseña
GEOTAB_DATABASE=nombre_bd_geotab

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=geotab_gps
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

---

## Despliegue con Docker

```bash
# Levantar servicios (app + PostgreSQL)
docker-compose up -d

# Ver logs de la aplicación
docker-compose logs -f app

# Reiniciar servicios
docker-compose restart
```

Acceso:
- **Mapa principal**: http://localhost:5000
- **Estadísticas**: http://localhost:5000/estadisticas

---

## Dependencias Python

```
Flask==3.0.0
mygeotab==0.8.5
psycopg2-binary==2.9.9
python-dotenv==1.0.0
Werkzeug==3.0.1
```

---

## Flujo de datos

```
Geotab API
    │
    ▼
SyncService (cada 5 min)
    │
    ├──► dispositivos (PostgreSQL)
    ├──► ubicaciones  (PostgreSQL)
    ├──► viajes       (PostgreSQL)
    └──► excesos_velocidad (PostgreSQL)
    
Flask App ◄──── PostgreSQL ────► Frontend (mapa + stats)

enviar_gpswox.py ──► GPSWox/Traccar (protocolo OsmAnd)
```

---

## Integración con servidor Rastrear GPS (173.212.203.163)

### Información del servidor

| Campo | Valor |
|---|---|
| URL base API | `http://173.212.203.163/api` |
| Documentación | `http://173.212.203.163/api-docs/index.html` |
| Puerto OsmAnd (GPS) | `6055` |
| Autenticación | `user_api_hash` (obtenido via login) |
| Usuario admin | `gerencia@rastrear.com.co` |
| Grupo arval | `id=43` (ya existe en el servidor) |

---

### Endpoints confirmados (probados 2026-03-06)

| Endpoint | Método | Estado | Descripción |
|---|---|---|---|
| `/api/login` | POST | ✅ | Login → devuelve `user_api_hash` |
| `/api/get_devices` | POST | ✅ | Lista grupos con sus dispositivos |
| `/api/add_device` | POST | ✅ | Crea dispositivo (acepta `group_id`) |
| `/api/edit_device` | POST | ✅ | Actualiza nombre y/o `group_id` |
| `/api/destroy_device` | POST | ✅ | Elimina un dispositivo |
| `:6055/?id=IMEI&lat=...` | GET | ✅ | Envía posición OsmAnd HTTP → HTTP 200 |
| `/api/get_sensors` | POST | ✅ | Lista sensores de un dispositivo |
| `/api/add_sensor` | POST | ✅ | Agrega sensor |

| `/api/admin/clients` | GET | ✅ | Lista todos los usuarios (paginado, 25/página) |
| `/api/edit_device_data` | GET | ✅ | Obtiene datos del dispositivo incl. `sel_users` (usuarios asignados) |

**Asignación de un dispositivo a un usuario (vía API):**
1. `GET /api/admin/clients?user_api_hash=H&page=N` → buscar `id` del usuario target por email
2. `GET /api/edit_device_data?device_id=X&user_api_hash=H` → leer `sel_users` (usuarios ya asignados)
3. `POST /api/edit_device?device_id=X&user_api_hash=H` con body `{"user_id": [ids_existentes + nuevo_id]}` → asigna sin eliminar

**IDs clave:** `gerencia@rastrear.com.co` = user_id **3**, `guiogonza@gmail.com` = user_id **1**

---

### Paso 1 — Login

```python
import requests

resp = requests.post("http://173.212.203.163/api/login", json={
    "email": "gerencia@rastrear.com.co",
    "password": "Colombias1*"
})
api_hash = resp.json()["user_api_hash"].strip()
```

### Paso 2 — Ver grupos y dispositivos existentes

```python
resp = requests.post("http://173.212.203.163/api/get_devices",
                     json={"user_api_hash": api_hash})
grupos = resp.json()
# Estructura: [{id, title, items: [{id, name, protocol, lat, lng, ...}]}]
# Grupo arval: id=43
for g in grupos:
    print(g["id"], g["title"], len(g.get("items", [])), "devs")
```

### Paso 3 — Crear dispositivo en grupo arval

```python
# CONFIRMADO: add_device acepta group_id
resp = requests.post("http://173.212.203.163/api/add_device", json={
    "user_api_hash": api_hash,
    "name":          "NFV759",           # placa
    "imei":          "G91D32202MSK",     # serialNumber de Geotab
    "protocol":      "osmand",
    "group_id":      43                  # grupo arval
})
# Respuesta exitosa: {"status": 1, "id": <nuevo_id>}
```

### Paso 4 — Mover dispositivo existente a grupo arval

```python
# CONFIRMADO: edit_device acepta group_id
resp = requests.post("http://173.212.203.163/api/edit_device", json={
    "user_api_hash": api_hash,
    "device_id":     574,                # id GPSWox del dispositivo
    "name":          "LPX319",           # nombre/placa
    "group_id":      43                  # grupo arval
})
# Respuesta exitosa: {"status": 1, "id": 574}
```

### Paso 5 — Enviar posición OsmAnd (puerto 6055)

```python
import time, requests

# CONFIRMADO: GET al puerto 6055 retorna HTTP 200
url = (
    "http://173.212.203.163:6055/"
    "?id=G91D32202MSK"          # IMEI / serialNumber Geotab
    "&lat=4.7110"
    "&lon=-74.0721"
    "&speed=0"                  # en nudos (km/h / 1.852)
    "&bearing=0"
    f"&timestamp={int(time.time())}"
    "&ignition=true"
    "&motion=false"
)
resp = requests.get(url, timeout=15)
# resp.status_code == 200 → posición recibida
```

### Paso 6 — Ejecutar sincronización continua (cada 5 minutos)

```bash
# Activar entorno virtual (Windows)
.\.venv\Scripts\Activate.ps1

# Ejecutar sincronización
python gpswox_live_sync.py
```

El script `gpswox_live_sync.py` hace automáticamente:
1. Login en GPSWox
2. Conecta a Geotab
3. Compara dispositivos → crea/mueve los que falten al grupo arval
4. Cada 5 min → obtiene `DeviceStatusInfo` de Geotab y envía posiciones via OsmAnd
5. Cada 50 min → re-verifica el catálogo por placas nuevas

### Flujo completo confirmado

```
Geotab API (DeviceStatusInfo)
        │
        ▼
  gpswox_live_sync.py  (cada 5 min)
        │
        ├── Sync catálogo: add_device / edit_device → group_id=43 (arval)
        │
        └── Para cada vehículo con GPS:
             GET http://173.212.203.163:6055/?id=IMEI&lat=...&lon=...
             → HTTP 200 confirmado
        ▼
  Servidor GPSWox (173.212.203.163)
  Grupo "arval" (id=43) → visible en mapa
```

### Asignación de usuarios a dispositivos (vía API)

Los 97 dispositivos del grupo arval están asignados a **ambos usuarios** (`user_id: [3, 1]`).

Flujo completo (descubierto desde `whatsapp docker/lib/session/gpswox-api.js`):

```python
import requests

# 1. Login como admin
H = requests.post("http://173.212.203.163/api/login",
    json={"email": "gerencia@rastrear.com.co", "password": "Colombias1*"}
).json()["user_api_hash"]

# 2. Buscar user_id del usuario target
clientes = requests.get(f"http://173.212.203.163/api/admin/clients",
    params={"user_api_hash": H, "lang": "es", "page": 1}).json()["data"]
user_id = next(c["id"] for c in clientes if c["email"] == "guiogonza@gmail.com")
# → user_id = 1

# 3. Para cada dispositivo: leer sel_users y agregar el nuevo user_id
data = requests.get("http://173.212.203.163/api/edit_device_data",
    params={"device_id": DEV_ID, "user_api_hash": H, "lang": "es"}).json()
sel = data.get("sel_users", {})
current_ids = [int(v) for v in (sel.values() if isinstance(sel, dict) else sel)]
new_ids = current_ids + [user_id]  # no eliminar los existentes

# 4. Guardar
requests.post("http://173.212.203.163/api/edit_device",
    json={"user_id": new_ids},
    params={"device_id": DEV_ID, "user_api_hash": H, "lang": "es"}
)
```

**Resultado:** `user_id: [3, 1]` en los 97 dispositivos → gerencia (3) y guiogonza (1) los ven.

---

## Notas de contexto para el agente

- El proyecto usa **singleton** para la conexión a la API de Geotab (`_client` en `app.py`).
- La sincronización corre en un **hilo daemon** independiente de Flask.
- `extraer_placas.py` usa **SQLite** como almacenamiento temporal (utilitario independiente).
- Los scripts en `scripts/` existen en versión `.sh` (Linux) y `.ps1` (Windows PowerShell).
- Consulta [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [DEPLOY.md](DEPLOY.md) y [QUICK_REFERENCE.md](QUICK_REFERENCE.md) para guías operativas.
