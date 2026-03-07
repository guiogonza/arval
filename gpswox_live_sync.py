"""
Sincronización en vivo Geotab → GPSWox (173.212.203.163)

FLUJO CONFIRMADO VIA API (probado 2026-03-06):
  ✅ POST /api/login              → obtiene user_api_hash
  ✅ POST /api/get_devices        → lista grupos y dispositivos
  ✅ POST /api/add_device         → crea dispositivo (acepta group_id)
  ✅ POST /api/edit_device        → actualiza nombre/grupo (acepta group_id)
  ✅ POST /api/destroy_device     → elimina dispositivo
  ✅ GET  :6055/?id=IMEI&lat=...  → envía posición OsmAnd HTTP (HTTP 200)

GRUPO ARVAL: id=43 en el servidor (ya existe)

NOTA: La API REST NO expone endpoints de gestión de usuarios/sharing.
  La asignación de guiogonza@gmail.com debe hacerse desde el panel web:
  http://173.212.203.163 → Administración → Usuarios → Compartir grupo arval
"""

import os
import time
import requests
import mygeotab
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ============ CONFIGURACIÓN ============
GPSWOX_API_URL   = "http://173.212.203.163/api"
GPSWOX_OSMAND    = "http://173.212.203.163:6055"
GPSWOX_EMAIL     = os.getenv("GPSWOX_EMAIL",    "gerencia@rastrear.com.co")
GPSWOX_PASSWORD  = os.getenv("GPSWOX_PASSWORD", "Colombias1*")
SYNC_INTERVAL    = 300          # segundos entre cada ciclo (5 minutos)
REQUEST_TIMEOUT  = 15           # segundos por petición HTTP
GRUPO_ARVAL_ID   = 43           # id del grupo "arval" en GPSWox (confirmado)
# =======================================


# ---------------------------------------------------------------------------
# 1. AUTENTICACIÓN GPSWox
# ---------------------------------------------------------------------------

def gpswox_login() -> str:
    """Hace login en GPSWox y devuelve el user_api_hash.
    CONFIRMADO: POST /api/login con {email, password} → {user_api_hash, ...}
    """
    print("🔐 Autenticando en GPSWox...")
    resp = requests.post(
        f"{GPSWOX_API_URL}/login",
        json={"email": GPSWOX_EMAIL, "password": GPSWOX_PASSWORD},
        timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    data = resp.json()

    api_hash = (
        data.get("user_api_hash")
        or data.get("api_hash")
        or data.get("hash")
        or (data.get("user") or {}).get("api_hash")
    )
    if not api_hash:
        raise ValueError(f"No se encontró api_hash en la respuesta: {data}")

    print(f"✅ Autenticado — hash: {api_hash[:12]}...")
    return api_hash


# ---------------------------------------------------------------------------
# 2. DISPOSITIVOS EN GPSWox
# ---------------------------------------------------------------------------

def gpswox_get_devices(api_hash: str) -> dict:
    """Devuelve un dict {imei: device_info} con todos los dispositivos en GPSWox.
    CONFIRMADO: POST /api/get_devices → lista de grupos con items[]
    Estructura: [{id, title, items: [{id, name, protocol, ...}]}]
    """
    resp = requests.post(
        f"{GPSWOX_API_URL}/get_devices",
        json={"user_api_hash": api_hash},
        timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    grupos = resp.json()   # lista de grupos

    dispositivos = {}      # {imei_o_nombre: {id, name, group_id}}
    for grupo in grupos:
        gid = grupo.get("id", 0)
        for d in grupo.get("items", []):
            # GPSWox devuelve el IMEI en el campo 'imei' dentro del detalle
            # pero en get_devices solo viene el resumen; usamos 'name' como fallback
            dev_id = d.get("id")
            name   = d.get("name", "")
            dispositivos[name] = {"id": dev_id, "name": name, "group_id": gid}
    return dispositivos


def gpswox_crear_dispositivo(api_hash: str, placa: str, imei: str) -> dict:
    """Crea un dispositivo en GPSWox asignado al grupo arval.
    CONFIRMADO: POST /api/add_device con {user_api_hash, name, imei, protocol, group_id}
    → HTTP 200 {status:1, id:<nuevo_id>}
    """
    resp = requests.post(
        f"{GPSWOX_API_URL}/add_device",
        json={
            "user_api_hash": api_hash,
            "name":          placa,
            "imei":          imei,
            "protocol":      "osmand",
            "group_id":      GRUPO_ARVAL_ID,
        },
        timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def gpswox_actualizar_dispositivo(api_hash: str, device_id: int, placa: str) -> bool:
    """Actualiza nombre y grupo de un dispositivo existente.
    CONFIRMADO: POST /api/edit_device con {user_api_hash, device_id, name, group_id}
    → HTTP 200 {status:1, id:<device_id>}
    """
    resp = requests.post(
        f"{GPSWOX_API_URL}/edit_device",
        json={
            "user_api_hash": api_hash,
            "device_id":     device_id,
            "name":          placa,
            "group_id":      GRUPO_ARVAL_ID,
        },
        timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json().get("status") == 1


# ---------------------------------------------------------------------------
# 3. GEOTAB
# ---------------------------------------------------------------------------

def geotab_connect() -> mygeotab.API:
    """Conecta y autentifica con la API de Geotab."""
    print("🔌 Conectando a Geotab...")
    client = mygeotab.API(
        username=os.getenv("GEOTAB_USERNAME"),
        password=os.getenv("GEOTAB_PASSWORD"),
        database=os.getenv("GEOTAB_DATABASE"),
    )
    client.authenticate()
    print("✅ Conectado a Geotab")
    return client


def geotab_get_devices(client: mygeotab.API) -> list:
    """Devuelve todos los dispositivos de Geotab como lista de dicts."""
    return client.get("Device")


def geotab_get_posiciones(client: mygeotab.API) -> list:
    """Devuelve DeviceStatusInfo — posición actual de cada vehículo."""
    return client.get("DeviceStatusInfo")


# ---------------------------------------------------------------------------
# 4. SINCRONIZAR CATÁLOGO (crear nuevos en GPSWox)
# ---------------------------------------------------------------------------

def sincronizar_catalogo(client: mygeotab.API, api_hash: str) -> dict:
    """
    Compara dispositivos Geotab vs GPSWox.
    - Si la placa NO existe en GPSWox → la CREA con group_id=arval (id=43)
    - Si la placa YA existe → la mueve a arval si no estaba
    - Si el nombre cambió → actualiza
    Devuelve dict {geotab_device_id: imei} para todos los vehículos válidos.

    ENDPOINTS UTILIZADOS (confirmados):
      POST /api/get_devices  → lista grupos+dispositivos
      POST /api/add_device   → crea con group_id
      POST /api/edit_device  → actualiza nombre/group_id
    """
    print("\n📋 Verificando catálogo de dispositivos...")

    devices_geotab = geotab_get_devices(client)
    devices_gpswox = gpswox_get_devices(api_hash)   # keyed by name/placa

    print(f"   Geotab : {len(devices_geotab)} dispositivos")
    print(f"   GPSWox : {len(devices_gpswox)} dispositivos")
    print(f"   Grupo arval destino: id={GRUPO_ARVAL_ID}")

    catalogo = {}   # {geotab_device_id: imei}
    nuevos      = 0
    actualizados = 0
    ya_ok       = 0

    for device in devices_geotab:
        placa = device.get("name", "").strip()
        imei  = device.get("serialNumber", "").strip()
        gid   = device.get("id", "")

        if not placa or not imei:
            continue

        catalogo[gid] = imei

        if placa in devices_gpswox:
            dev_wox = devices_gpswox[placa]
            wox_id  = dev_wox["id"]
            wox_grp = dev_wox["group_id"]

            if wox_grp != GRUPO_ARVAL_ID:
                # Está en otro grupo → mover a arval
                print(f"   🔄 Moviendo a arval: {placa} (grupo actual={wox_grp})")
                try:
                    gpswox_actualizar_dispositivo(api_hash, wox_id, placa)
                    actualizados += 1
                except Exception as e:
                    print(f"   ⚠️  No se pudo mover {placa}: {e}")
            else:
                ya_ok += 1
        else:
            # No existe → crear en GPSWox con group_id=arval
            print(f"   ➕ Creando en arval: {placa} (IMEI: {imei})")
            try:
                resultado = gpswox_crear_dispositivo(api_hash, placa, imei)
                print(f"      → id={resultado.get('id')}")
                nuevos += 1
            except Exception as e:
                print(f"   ❌ Error creando {placa}: {e}")

    print(f"\n✅ Catálogo listo — {ya_ok} ya en arval | {actualizados} movidos | {nuevos} nuevos")
    return catalogo


# ---------------------------------------------------------------------------
# 5. ENVIAR POSICIONES (OsmAnd HTTP)
# ---------------------------------------------------------------------------

def enviar_posiciones(client: mygeotab.API, catalogo: dict):
    """
    Obtiene posiciones actuales de Geotab y las envía al servidor
    via protocolo OsmAnd HTTP (puerto 6055).

    CONFIRMADO:
      GET http://173.212.203.163:6055/?id=IMEI&lat=X&lon=Y&speed=S&timestamp=T
      → HTTP 200 cuando el dispositivo existe y el protocolo es osmand
    """
    ahora = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"\n📡 [{ahora}] Enviando posiciones...")

    statuses = geotab_get_posiciones(client)

    enviados = 0
    sin_gps  = 0
    errores  = 0

    for status in statuses:
        try:
            # Extraer device_id de Geotab
            device_raw = status.get("device", {})
            gid = device_raw.get("id", "") if isinstance(device_raw, dict) else str(device_raw)

            imei = catalogo.get(gid)
            if not imei:
                continue   # sin serial → no sincronizable

            lat  = status.get("latitude",  0) or 0
            lng  = status.get("longitude", 0) or 0
            spd  = status.get("speed",     0) or 0   # km/h
            bear = status.get("bearing",   0) or 0

            if not lat or not lng:
                sin_gps += 1
                continue

            # Timestamp preferir del GPS
            dt_gps = status.get("dateTime")
            if dt_gps:
                if hasattr(dt_gps, "timestamp"):
                    ts = int(dt_gps.timestamp())
                else:
                    from dateutil.parser import parse as _parse
                    ts = int(_parse(str(dt_gps)).timestamp())
            else:
                ts = int(time.time())

            # OsmAnd espera velocidad en nudos
            speed_knots = spd / 1.852
            ignicion = status.get("isDeviceCommunicating", False)

            # CONFIRMADO: este formato funciona → HTTP 200
            url = (
                f"{GPSWOX_OSMAND}/"
                f"?id={imei}"
                f"&lat={lat}"
                f"&lon={lng}"
                f"&speed={speed_knots:.2f}"
                f"&bearing={bear}"
                f"&timestamp={ts}"
                f"&ignition={'true' if ignicion else 'false'}"
                f"&motion={'true' if spd > 0 else 'false'}"
            )

            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                enviados += 1
            else:
                errores += 1
                print(f"   ⚠️  HTTP {resp.status_code} para IMEI {imei}")

        except Exception as e:
            errores += 1
            print(f"   ❌ Error: {e}")

    print(f"   ✅ {enviados} enviados | ⚪ {sin_gps} sin GPS | ❌ {errores} errores")
    return enviados


# ---------------------------------------------------------------------------
# 6. LOOP PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Geotab -> GPSWox Live Sync")
    print(f"  Destino : {GPSWOX_API_URL}")
    print(f"  OsmAnd  : {GPSWOX_OSMAND}")
    print(f"  Intervalo: {SYNC_INTERVAL // 60} minutos")
    print("=" * 60)

    # Conectar a Geotab una sola vez
    client = geotab_connect()

    # Obtener api_hash (se renueva si expira)
    api_hash = gpswox_login()

    # Sincronización inicial del catálogo
    catalogo = sincronizar_catalogo(client, api_hash)

    ciclo = 0
    while True:
        ciclo += 1
        print(f"\n{'─'*60}")
        print(f"  Ciclo #{ciclo}")
        print(f"{'─'*60}")

        try:
            # Cada 10 ciclos (50 min) re-verificar el catálogo por vehículos nuevos
            if ciclo % 10 == 0:
                print("🔄 Re-verificando catálogo de dispositivos...")
                try:
                    catalogo = sincronizar_catalogo(client, api_hash)
                except Exception as e:
                    print(f"⚠️  Error sincronizando catálogo: {e}")

            # Enviar posiciones actuales
            enviar_posiciones(client, catalogo)

        except mygeotab.exceptions.AuthenticationException:
            print("🔄 Sesión Geotab expirada — reconectando...")
            client   = geotab_connect()
            catalogo = sincronizar_catalogo(client, api_hash)

        except requests.exceptions.HTTPError as e:
            # Si GPSWox devuelve 401/403 renovar token
            if e.response is not None and e.response.status_code in (401, 403):
                print("🔄 Token GPSWox expirado — renovando...")
                api_hash = gpswox_login()
            else:
                print(f"⚠️  Error HTTP GPSWox: {e}")

        except Exception as e:
            print(f"⚠️  Error en ciclo #{ciclo}: {e}")

        siguiente = datetime.now().strftime("%H:%M:%S")
        print(f"\n⏳ Próxima sync en {SYNC_INTERVAL // 60} min (a las ~"
              f"{datetime.now().replace(second=0).strftime('%H:%M')}+{SYNC_INTERVAL//60}min)")
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Sincronización detenida por el usuario.")
