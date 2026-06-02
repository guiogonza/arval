# Sync GPS — Contexto del Sistema

## Qué hace este proceso

Sincroniza dispositivos GPS y posiciones históricas desde el servidor principal
(`plataforma.sistemagps.online`) hacia el servidor de backup (`gps.rastrear.com.co`).

```
FUENTE (principal)                    DESTINO (backup)
plataforma.sistemagps.online    →     gps.rastrear.com.co
API GPSWox v3.7.7                     GPSWox v3.7.7 (VPS 158.220.110.46)
689 dispositivos activos              841 dispositivos (incluye históricos)
```

**Reglas de negocio:**
- Si un dispositivo existe en fuente pero NO en destino → se crea en destino.
- Si existe en ambos: valida que IMEI y placa (nombre) coincidan → log de mismatches.
- **NUNCA se modifica la fuente.** El destino es solo backup/receptor.
- Las posiciones se insertan directamente en MySQL (`gpswox_traccar.positions_N`), nunca vía API (el API de destino tiene limitaciones en esta versión de GPSWox).

---

## Infraestructura

| Elemento | Valor |
|---|---|
| VPS destino | `158.220.110.46` (AlmaLinux 9.7) |
| Usuario SSH | `root` / `<ssh-password-en-vault>` |
| Directorio scripts | `/root/sync_gps/` |
| MySQL host | `127.0.0.1:3306` |
| MySQL user/pass | `root` / `<mysql-password-en-vault>` |
| DB catálogo | `gpswox_web` |
| DB posiciones | `gpswox_traccar` |
| GPSWox versión | v3.7.7 (Traccar custom JAR) |

### Por qué MySQL directo (no OsmAnd/API)

GPSWox v3.7.7 usa un JAR de Traccar modificado con tablas particionadas
(`positions_N`) y sin la query `database.insertDevice` configurada. Todo intento
de enviar posiciones por OsmAnd (puerto 6055) devuelve **HTTP 400** aunque la
conexión TCP funcione. La solución es insertar directamente en MySQL.

### Esquema de tablas de posiciones

```sql
-- Una tabla por dispositivo en gpswox_traccar
-- N = traccar_device_id (campo en gpswox_web.devices, distinto del campo id)
CREATE TABLE positions_N (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  device_id   BIGINT DEFAULT 0,   -- siempre 0 en esta versión de GPSWox
  altitude    DOUBLE,
  course      DOUBLE,
  latitude    DOUBLE,
  longitude   DOUBLE,
  other       TEXT,
  power       DOUBLE,
  speed       DOUBLE,
  time        DATETIME,           -- hora GPS (fuente)
  device_time DATETIME,           -- igual a time
  server_time DATETIME,           -- NOW() al momento de inserción
  sensors_values TEXT,
  valid       TINYINT DEFAULT 1,
  distance    DOUBLE DEFAULT 0,
  protocol    VARCHAR(20)         -- 'sync' para las posiciones importadas
);
```

**Mapeo clave:** `gpswox_web.devices.traccar_device_id` → sufijo de tabla `positions_N`

---

## Archivos del sistema

### En el VPS (`/root/sync_gps/`)

| Archivo | Propósito |
|---|---|
| `sync_plat_hourly.py` | **Script diario/horario (OBLIGATORIO)** — cron cada hora |
| `sync_plat_backfill.py` | Script de carga histórica única — 90 días atrás |
| `sync_plat_hourly.log` | Log del script horario |
| `sync_plat_backfill.log` | Log del backfill |
| `sync_plat_backfill_progreso.json` | Progreso del backfill (reanuda si se interrumpe) |
| `sync_plat_estado.json` | Estado del último run horario |

### En local (`C:\Users\guiog\OneDrive\Documentos\Geotab\`)

| Archivo | Propósito |
|---|---|
| `sync_plat_hourly.py` | Fuente del script horario |
| `sync_plat_backfill.py` | Fuente del script backfill |
| `_deploy_sync_final.py` | Sube ambos scripts al VPS y relanza el backfill |
| `_check_backfill.py` | Consulta el estado del backfill desde local |
| `SYNC_GPS_CONTEXTO.md` | Este archivo |

---

## Script horario — `sync_plat_hourly.py`

> **Este script SIEMPRE debe estar ejecutándose vía cron. Es el corazón del sistema.**

### Cron configurado en VPS

```cron
0 * * * * /usr/bin/python3 /root/sync_gps/sync_plat_hourly.py >> /root/sync_gps/sync_plat_hourly.log 2>&1
```

### Flujo de ejecución

```
1. Login en fuente (plataforma.sistemagps.online)
2. Login en destino (gps.rastrear.com.co) — para crear dispositivos nuevos
3. sync_catalogo():
   ├── get_all_devices_src()  — API fuente: /api/get_devices
   ├── get_all_devices_dst()  — MySQL gpswox_web.devices (no el API, que falla en v3.7.7)
   ├── get_groups_dst_mysql() — MySQL gpswox_web.device_groups
   ├── Para cada dispositivo en fuente:
   │   ├── Si no existe en destino → get_or_create_group() + add_device() via API
   │   └── Si existe → valida IMEI + placa, log si hay mismatch
   └── Retorna: devs_src (dict {imei: {device_id, name}})
4. sync_posiciones_recientes():
   ├── Calcula intervalo: últimas 2 horas
   ├── get_traccar_id_map() — MySQL: IMEI → traccar_device_id
   ├── ThreadPoolExecutor (3 workers):
   │   └── Para cada dispositivo:
   │       ├── obtener_historia_intervalo() — API fuente /api/get_history
   │       └── insertar_posiciones_mysql_dev() — INSERT directo en gpswox_traccar.positions_N
   └── Log: Insertados / Errores / Vehículos con datos
```

### Funciones principales

| Función | Descripción |
|---|---|
| `get_all_devices_src()` | Lee catálogo de fuente vía API |
| `get_all_devices_dst()` | Lee catálogo de destino vía MySQL (no API) |
| `get_groups_dst_mysql()` | Lee grupos del destino vía MySQL |
| `get_or_create_group()` | Busca o crea grupo en destino vía API |
| `add_device()` | Crea dispositivo en destino vía API |
| `sync_catalogo()` | Orquesta la sincronización de catálogo |
| `get_traccar_id_map()` | `{imei: traccar_device_id}` desde MySQL |
| `insertar_posiciones_mysql_dev()` | INSERT en `gpswox_traccar.positions_N` |
| `obtener_historia_intervalo()` | Historial de 2h desde API fuente |
| `sync_posiciones_recientes()` | Orquesta el envío de posiciones |

### Credenciales

```python
# Fuente
SRC_BASE  = 'https://plataforma.sistemagps.online/api'
SRC_EMAIL = 'gerencia@rastrear.com.co'
SRC_PASS  = os.getenv('PLATAFORMA_PASSWORD', '')

# Destino (API — solo para crear devices/grupos)
DST_BASE  = 'https://gps.rastrear.com.co/api'
DST_EMAIL = 'gerencia@rastrear.com.co'
DST_PASS  = os.getenv('GPSWOX_PASSWORD', '')

# MySQL destino (para leer catálogo e insertar posiciones)
MYSQL_HOST = '127.0.0.1'
MYSQL_PORT = 3306
MYSQL_USER = 'root'
MYSQL_PASS = os.getenv('GPSWOX_DB_PASSWORD', '')
```

---

## Script backfill — `sync_plat_backfill.py`

Script de uso único para cargar los últimos 90 días de historia.
Se ejecuta en segundo plano y guarda progreso para poder reanudarse.

### Arrancar / Relanzar

```bash
# En el VPS (158.220.110.46):
nohup python3 -u /root/sync_gps/sync_plat_backfill.py \
  >> /root/sync_gps/sync_plat_backfill.log 2>&1 &

# Ver PID
pgrep -f sync_plat_backfill.py

# Ver log en tiempo real
tail -f /root/sync_gps/sync_plat_backfill.log
```

### Reiniciar desde cero (si se quiere borrar el progreso)

```bash
pkill -f sync_plat_backfill.py
rm -f /root/sync_gps/sync_plat_backfill_progreso.json
nohup python3 -u /root/sync_gps/sync_plat_backfill.py \
  >> /root/sync_gps/sync_plat_backfill.log 2>&1 &
```

### Flujo de ejecución

```
1. Login en fuente
2. Leer catálogo fuente: 689 dispositivos
3. get_traccar_id_map() — MySQL: IMEI → traccar_device_id (841 dispositivos en destino)
4. Cargar progreso desde sync_plat_backfill_progreso.json
5. ThreadPoolExecutor (3 dispositivos en paralelo):
   └── procesar_dispositivo():
       ├── Verificar que el dispositivo tiene traccar_id en destino (si no → SKIP)
       ├── Para cada día pendiente (FECHA_FIN → FECHA_INICIO, más reciente primero):
       │   ├── obtener_historia_dia(): 4 franjas × /api/get_history
       │   ├── insertar_posiciones_mysql_dev(): INSERT en positions_N
       │   └── Registrar día en progreso.json
       └── Retorna: (nombre, imei, total_puntos, total_enviados, total_errores)
6. Log resumen por dispositivo: puntos=N env=N err=0
7. Al finalizar: resumen total
```

### Parámetros de concurrencia

```python
MAX_DEV_PARALELO = 3    # dispositivos en paralelo
MAX_SRC_SEM      = 2    # requests simultáneos a la API fuente
PAUSA_ENTRE_DIAS = 0.2  # segundos entre franjas del mismo día
```

### Formato del progreso

```json
{
  "75538": { "dias_ok": ["2026-05-21", "2026-05-20", "..."] },
  "12345": { "dias_ok": ["2026-05-21"] }
}
```
*(la clave es el `device_id` de la fuente)*

---

## Historial de cambios

### v2.0 — 2026-05-22 (versión actual)

**Cambio principal: Reemplazo de OsmAnd HTTP por MySQL directo**

#### Problema raíz
GPSWox v3.7.7 usa un JAR de Traccar personalizado que:
- No tiene configurada la query `database.insertDevice`
- Devuelve HTTP 400 para TODOS los envíos OsmAnd aunque la conexión TCP funcione
- Usa tablas particionadas `positions_N` en lugar de una sola tabla `positions`
- El campo `traccar_device_id` en `gpswox_web.devices` mapea al sufijo N

#### Cambios en `sync_plat_hourly.py`

| Elemento | Antes (v1) | Ahora (v2) |
|---|---|---|
| Imports | `asyncio`, `aiohttp` | Eliminados |
| Constantes | `DST_OSMAND`, `MAX_OSMAND_PAR` | Eliminadas |
| Constantes nuevas | — | `MYSQL_TRACCAR_DB = 'gpswox_traccar'` |
| Función eliminada | `enviar_osmand_async()` | — |
| Función nueva | — | `get_traccar_id_map()` |
| Función nueva | — | `insertar_posiciones_mysql_dev()` |
| `sync_posiciones_recientes()` | asyncio loop + aiohttp + OsmAnd | ThreadPoolExecutor + MySQL INSERT |
| Resultado | `env=0 err=N` (todos fallaban) | `env=N err=0` (todos insertan) |

#### Cambios en `sync_plat_backfill.py`

| Elemento | Antes (v1) | Ahora (v2) |
|---|---|---|
| Imports | `asyncio`, `aiohttp` | Eliminados; agregado `pymysql` |
| Constantes | `DST_OSMAND`, `MAX_OSMAND_PAR` | Eliminadas |
| Constantes nuevas | — | `MYSQL_HOST/PORT/USER/PASS/WEB_DB/TRACCAR_DB` |
| Función eliminada | `enviar_osmand_async()` | — |
| Función nueva | — | `get_traccar_id_map()` |
| Función nueva | — | `insertar_posiciones_mysql_dev()` |
| `procesar_dispositivo()` | asyncio loop + aiohttp + OsmAnd | Loop síncrono + MySQL INSERT |
| Argumento extra | `(nombre,imei,dev_id,token,progreso,lock)` | `+ traccar_map` al final |
| `main()` | Sin carga de traccar_map | Llama `get_traccar_id_map()` y pasa el mapa |
| Resultado | `env=0 err=N` (todos fallaban) | `env=N err=0` ✅ |

### v1.0 — 2026-05-21 (versión inicial)

- Primera implementación con OsmAnd HTTP (puerto 6055)
- Funcionaba para catálogo pero fallaba en posiciones (400 en todos los envíos)
- Se descubrió que GPSWox v3.7.7 no tiene `database.insertDevice` configurado
- El catálogo `get_devices` también falla vía API → workaround: MySQL directo para leer destino

---

## Diagnóstico rápido

### Verificar que el cron está activo

```bash
# En el VPS:
crontab -l | grep sync_plat_hourly
```

Debe mostrar:
```
0 * * * * /usr/bin/python3 /root/sync_gps/sync_plat_hourly.py >> /root/sync_gps/sync_plat_hourly.log 2>&1
```

### Verificar que el backfill sigue corriendo

```bash
pgrep -f sync_plat_backfill.py
tail -20 /root/sync_gps/sync_plat_backfill.log
```

### Verificar posiciones insertadas

```sql
-- Desde el VPS (mysql -u root -p):
-- Últimas posiciones por fecha (positions_2 = ejemplo, device traccar_id=2)
SELECT COUNT(*), MAX(server_time) FROM gpswox_traccar.positions_2;

-- Ver cuántas tablas de posiciones existen
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema='gpswox_traccar' AND table_name LIKE 'positions_%';

-- Posiciones insertadas en las últimas 2 horas (todas las tablas → difícil sin loop)
-- Alternativa: buscar en tables con update_time reciente
SELECT table_name, table_rows, update_time
FROM information_schema.tables
WHERE table_schema='gpswox_traccar' AND table_name LIKE 'positions_%'
  AND update_time > DATE_SUB(NOW(), INTERVAL 2 HOUR)
ORDER BY update_time DESC LIMIT 20;
```

### Línea de log esperada (backfill funcionando)

```
[2026-05-22 03:47:50]   [1/689 0.1%] "ADK30G" | puntos=20491 env=20491 err=0
```

`err=0` confirma que las inserciones MySQL están funcionando.

### Línea de log del run horario (posiciones recientes)

```
[POSICIONES] Insertados=1234 | Errores=0 | Vehículos con datos=45
```

---

## Despliegue / Actualización de scripts

Desde la máquina local:

```bash
cd "C:\Users\guiog\OneDrive\Documentos\Geotab"
python _deploy_sync_final.py
```

Este script:
1. Sube `sync_plat_hourly.py` y `sync_plat_backfill.py` al VPS
2. Mata el proceso backfill anterior
3. Borra el archivo de progreso
4. Lanza el nuevo backfill en segundo plano
5. Muestra las últimas líneas del log

> ⚠️ Si solo se actualiza el hourly (sin tocar el backfill), editar `_deploy_sync_final.py`
> para omitir el `pkill` y el borrado del progreso.

---

## Dependencias Python (VPS)

```bash
pip3 install requests pymysql
```

`requests` y `pymysql` son las únicas dependencias externas.
No se requiere `aiohttp` ni `asyncio` (módulo estándar, pero no se usa).

---

## Nota operativa 2026-06-02

### Incidente: historial visible, pero sin ultima ubicacion en `/objects`

El problema no estaba en la carga de historial. Las posiciones si estaban llegando a
`gpswox_traccar.positions_N`, por eso el historial del vehiculo mostraba ruta.

La pantalla de objetos usa el resumen de posicion actual en
`gpswox_web.traccar_devices`. Si ese registro no se actualiza, el vehiculo puede
tener historial pero no aparece correctamente al seleccionarlo en el mapa.

Campos criticos para la vista actual:

- `latestPosition_id`
- `lastValidLatitude`
- `lastValidLongitude`
- `time`
- `device_time`
- `server_time`
- `protocol`
- `latest_positions`

Correccion aplicada:

- `sync_plat_hourly.py` ahora actualiza `traccar_devices` despues de insertar en
  `positions_N`.
- `sync_diario.py` tambien actualiza los campos completos de ultima posicion.
- Se elimino del `docker-compose.yml` el flujo directo `Geotab -> GPSWox` para
  evitar duplicados. El flujo correcto queda:

```text
Geotab -> plataforma.sistemagps.online -> gps.rastrear.com.co
```

Validacion realizada:

- `sync_plat_hourly.py` ejecuto una corrida manual sin errores de insercion.
- El listener OsmAnd custom quedo activo en puerto `6055`.
- La mayoria de dispositivos con puntos historicos recibieron `latestPosition_id`
  y coordenadas actuales reconstruidas desde sus tablas `positions_N`.

