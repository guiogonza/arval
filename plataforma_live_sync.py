"""
Sincronización Geotab → plataforma.sistemagps.online

FLUJO:
  1. Al arrancar: carga historial desde HISTORY_FROM (2026-03-01) para todas
     las placas Geotab (grupo Geotab id=7444), enviando puntos GPS vía OsmAnd.
  2. Loop cada 5 minutos: envía la última posición de cada vehículo.

ENDPOINTS PLATAFORMA:
  POST https://plataforma.sistemagps.online/api/login
  POST https://plataforma.sistemagps.online/api/get_devices
  POST https://plataforma.sistemagps.online/api/add_device
  POST https://plataforma.sistemagps.online/api/edit_device
  GET  http://plataforma.sistemagps.online:6055/?id=IMEI&lat=...  (OsmAnd)

GRUPO GEOTAB en plataforma: id=7444
USUARIOS con acceso: 14682 (gerencia@rastrear.com.co), 17234 (guiogonza@gmail.com)
"""

import os
import time
import requests
import mygeotab
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

# ============ CONFIGURACIÓN ============
PLATAFORMA_API   = "https://plataforma.sistemagps.online/api"
PLATAFORMA_OSMAND= "http://plataforma.sistemagps.online:6055"
PLATAFORMA_EMAIL = os.getenv("PLATAFORMA_EMAIL",    "gerencia@rastrear.com.co")
PLATAFORMA_PASS  = os.getenv("PLATAFORMA_PASSWORD", "a791025*")
GRUPO_GEOTAB_ID  = 7444           # grupo "Geotab" en plataforma (confirmado)
USUARIOS_OK      = [14682, 17234] # gerencia + guiogonza
SYNC_INTERVAL    = 300            # segundos entre ciclos (5 min)
REQUEST_TIMEOUT  = 20
HISTORY_BATCH    = 500            # registros por dispositivo máximo por llamada

# HISTORY_DAYS: cuántos días atrás cargar al arrancar.
# 0 = no cargar historial (modo Docker normal)
# 7 = cargar última semana (carga inicial one-time)
_history_days = int(os.getenv("PLATAFORMA_HISTORY_DAYS", "0"))
HISTORY_FROM = (
    datetime.now(timezone.utc) - timedelta(days=_history_days)
    if _history_days > 0 else None
)
# =======================================


def make_session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1)))
    s.mount("http://",  HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.5)))
    return s

SESSION = make_session()


# ---------------------------------------------------------------------------
# 1. AUTENTICACIÓN PLATAFORMA
# ---------------------------------------------------------------------------
def plataforma_login() -> str:
    print("Autenticando en plataforma.sistemagps.online...")
    r = SESSION.post(f"{PLATAFORMA_API}/login",
                     json={"email": PLATAFORMA_EMAIL, "password": PLATAFORMA_PASS},
                     timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    token = r.json().get("user_api_hash")
    if not token:
        raise ValueError(f"No se obtuvo token: {r.text[:200]}")
    print(f"  Autenticado | hash: {token[:12]}...")
    return token


# ---------------------------------------------------------------------------
# 2. DISPOSITIVOS EN PLATAFORMA
# ---------------------------------------------------------------------------
def plataforma_get_devices(token: str) -> dict:
    """Devuelve {nombre_upper: {id, imei}} de todos los dispositivos."""
    r = SESSION.post(f"{PLATAFORMA_API}/get_devices",
                     json={"user_api_hash": token}, timeout=60)
    r.raise_for_status()
    result = {}
    for g in r.json():
        for d in g.get("items", []):
            nombre = d.get("name", "").strip()
            dd = d.get("device_data", {})
            result[nombre.upper()] = {
                "id":   d["id"],
                "name": nombre,
                "imei": dd.get("imei", ""),
            }
    return result


def plataforma_crear_dispositivo(token: str, placa: str, imei: str) -> int:
    r = SESSION.post(f"{PLATAFORMA_API}/add_device", json={
        "user_api_hash": token,
        "name":          placa,
        "imei":          imei,
        "protocol":      "osmand",
        "group_id":      GRUPO_GEOTAB_ID,
        "users":         USUARIOS_OK,
    }, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != 1:
        raise RuntimeError(f"add_device falló: {r.text[:150]}")
    return data["id"]


# ---------------------------------------------------------------------------
# 3. GEOTAB
# ---------------------------------------------------------------------------
def geotab_connect() -> mygeotab.API:
    print("Conectando a Geotab...")
    client = mygeotab.API(
        username=os.getenv("GEOTAB_USERNAME"),
        password=os.getenv("GEOTAB_PASSWORD"),
        database=os.getenv("GEOTAB_DATABASE"),
    )
    client.authenticate()
    print("  Conectado a Geotab")
    return client


# ---------------------------------------------------------------------------
# 4. SINCRONIZAR CATÁLOGO
# ---------------------------------------------------------------------------
def sincronizar_catalogo(client: mygeotab.API, token: str) -> dict:
    """
    Asegura que todos los dispositivos Geotab existan en plataforma.
    Devuelve {geotab_device_id: imei}.
    """
    print("\nVerificando catálogo de dispositivos...")
    devices_geo = client.get("Device")
    devices_plt = plataforma_get_devices(token)

    print(f"  Geotab     : {len(devices_geo)} dispositivos")
    print(f"  Plataforma : {len(devices_plt)} dispositivos")

    catalogo = {}   # {geotab_id: imei}
    nuevos = 0

    for dev in devices_geo:
        placa = dev.get("name", "").strip()
        imei  = dev.get("serialNumber", "").strip()
        gid   = dev.get("id", "")
        if not placa or not imei:
            continue

        catalogo[gid] = imei

        if placa.upper() not in devices_plt:
            print(f"  + Creando: {placa} (IMEI:{imei})")
            try:
                plataforma_crear_dispositivo(token, placa, imei)
                nuevos += 1
            except Exception as e:
                print(f"  ! Error creando {placa}: {e}")
            time.sleep(0.3)

    print(f"  Catalogo listo | {nuevos} nuevos creados")
    return catalogo


# ---------------------------------------------------------------------------
# 5. ENVIAR PUNTO OsmAnd
# ---------------------------------------------------------------------------
def enviar_osmand(imei: str, lat: float, lng: float, speed_kmh: float,
                  bearing: float, ts: int, ignicion: bool) -> bool:
    speed_knots = speed_kmh / 1.852
    url = (
        f"{PLATAFORMA_OSMAND}/"
        f"?id={imei}"
        f"&lat={lat}"
        f"&lon={lng}"
        f"&speed={speed_knots:.2f}"
        f"&bearing={bearing}"
        f"&timestamp={ts}"
        f"&ignition={'true' if ignicion else 'false'}"
        f"&motion={'true' if speed_kmh > 0 else 'false'}"
    )
    r = SESSION.get(url, timeout=REQUEST_TIMEOUT)
    return r.status_code == 200


# ---------------------------------------------------------------------------
# 6. CARGAR HISTORIAL (una sola vez al arrancar)
# ---------------------------------------------------------------------------
def cargar_historial(client: mygeotab.API, catalogo: dict):
    """
    Obtiene el historial de LogRecord de Geotab desde HISTORY_FROM hasta ahora
    y lo envía a plataforma via OsmAnd con el timestamp original.
    """
    ahora = datetime.now(timezone.utc)
    dias = (ahora - HISTORY_FROM).days
    print(f"\n{'='*60}")
    print(f"  CARGA DE HISTORIAL")
    print(f"  Desde  : {HISTORY_FROM.strftime('%Y-%m-%d')}  ({_history_days} dias)")
    print(f"  Hasta  : {ahora.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  Devices: {len(catalogo)}")
    print(f"{'='*60}")

    total_puntos = 0
    total_ok     = 0
    total_err    = 0

    geo_devices = client.get("Device")
    # Filtrar solo los que están en el catálogo
    geo_devices = [d for d in geo_devices if d.get("id") in catalogo]

    for i, dev in enumerate(geo_devices, 1):
        placa = dev.get("name", "").strip()
        gid   = dev.get("id", "")
        imei  = catalogo.get(gid, "")
        if not imei:
            continue

        print(f"\n  [{i}/{len(geo_devices)}] {placa} | IMEI:{imei}")

        try:
            logs = client.get(
                "LogRecord",
                search={
                    "deviceSearch": {"id": gid},
                    "fromDate": HISTORY_FROM.isoformat(),
                    "toDate":   ahora.isoformat(),
                }
            )
        except Exception as e:
            print(f"    ! Error obteniendo logs: {e}")
            continue

        if not logs:
            print(f"    Sin registros")
            continue

        print(f"    {len(logs)} puntos -> enviando...")
        ok = 0
        err = 0

        for log in logs:
            try:
                lat  = log.get("latitude",  0) or 0
                lng  = log.get("longitude", 0) or 0
                spd  = log.get("speed",     0) or 0

                if not lat or not lng:
                    continue

                dt = log.get("dateTime")
                if hasattr(dt, "timestamp"):
                    ts = int(dt.timestamp())
                else:
                    from dateutil.parser import parse as _p
                    ts = int(_p(str(dt)).timestamp())

                if enviar_osmand(imei, lat, lng, spd, 0, ts, False):
                    ok += 1
                else:
                    err += 1

            except Exception as e:
                err += 1

            # Throttle para no saturar
            if (ok + err) % 100 == 0:
                time.sleep(0.1)

        print(f"    OK:{ok} | ERR:{err}")
        total_puntos += len(logs)
        total_ok     += ok
        total_err    += err

        # Escribir progreso en archivo para monitorear externamente
        with open("historial_progreso.txt", "w", encoding="utf-8") as f:
            f.write(f"{i}/{len(geo_devices)} completados\n")
            f.write(f"Ultimo: {placa} | {len(logs)} puntos | OK:{ok} ERR:{err}\n")
            f.write(f"Total acumulado: {total_puntos} puntos | OK:{total_ok} ERR:{total_err}\n")

        time.sleep(0.5)   # pausa entre devices

    print(f"\n  HISTORIAL COMPLETO")
    print(f"  Total puntos : {total_puntos}")
    print(f"  Enviados OK  : {total_ok}")
    print(f"  Errores      : {total_err}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# 7. ENVIAR POSICIONES EN VIVO
# ---------------------------------------------------------------------------
def enviar_posiciones_live(client: mygeotab.API, catalogo: dict):
    ahora = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"\n[{ahora}] Enviando posiciones en vivo...")

    statuses = client.get("DeviceStatusInfo")
    enviados = 0
    sin_gps  = 0
    errores  = 0

    for status in statuses:
        try:
            device_raw = status.get("device", {})
            gid = device_raw.get("id", "") if isinstance(device_raw, dict) else str(device_raw)

            imei = catalogo.get(gid)
            if not imei:
                continue

            lat  = status.get("latitude",  0) or 0
            lng  = status.get("longitude", 0) or 0
            spd  = status.get("speed",     0) or 0
            bear = status.get("bearing",   0) or 0

            if not lat or not lng:
                sin_gps += 1
                continue

            dt_gps = status.get("dateTime")
            if dt_gps:
                ts = int(dt_gps.timestamp()) if hasattr(dt_gps, "timestamp") else int(time.time())
            else:
                ts = int(time.time())

            ignicion = status.get("isDeviceCommunicating", False)

            if enviar_osmand(imei, lat, lng, spd, bear, ts, ignicion):
                enviados += 1
            else:
                errores += 1

        except Exception as e:
            errores += 1
            print(f"  ! Error: {e}")

    print(f"  {enviados} enviados | {sin_gps} sin GPS | {errores} errores")
    return enviados


# ---------------------------------------------------------------------------
# 8. LOOP PRINCIPAL
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  Geotab -> plataforma.sistemagps.online Live Sync")
    print(f"  API     : {PLATAFORMA_API}")
    print(f"  OsmAnd  : {PLATAFORMA_OSMAND}")
    print(f"  Grupo   : {GRUPO_GEOTAB_ID} (Geotab)")
    print(f"  Hist.   : {'desde ' + HISTORY_FROM.strftime('%Y-%m-%d') if HISTORY_FROM else 'omitido'}")
    print(f"  Intervalo: {SYNC_INTERVAL // 60} min")
    print("=" * 60)

    client   = geotab_connect()
    token    = plataforma_login()
    catalogo = sincronizar_catalogo(client, token)

    # --- Carga histórica (solo si PLATAFORMA_HISTORY_DAYS > 0) ---
    if HISTORY_FROM is not None:
        cargar_historial(client, catalogo)
    else:
        print("\nHistorial omitido (PLATAFORMA_HISTORY_DAYS=0)")

    # --- Loop en vivo ---
    ciclo = 0
    while True:
        ciclo += 1
        print(f"\n{'─'*60}  Ciclo #{ciclo}  {'─'*60}")

        try:
            if ciclo % 10 == 0:
                print("Re-verificando catalogo...")
                try:
                    catalogo = sincronizar_catalogo(client, token)
                except Exception as e:
                    print(f"  ! Error catalogo: {e}")

            enviar_posiciones_live(client, catalogo)

        except mygeotab.exceptions.AuthenticationException:
            print("Sesion Geotab expirada, reconectando...")
            client   = geotab_connect()
            catalogo = sincronizar_catalogo(client, token)

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 403):
                print("Token plataforma expirado, renovando...")
                token = plataforma_login()
            else:
                print(f"Error HTTP: {e}")

        except Exception as e:
            print(f"Error en ciclo #{ciclo}: {e}")

        print(f"\nProxima sync en {SYNC_INTERVAL // 60} min...")
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSincronizacion detenida.")
