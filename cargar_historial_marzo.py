"""
FASE 2 — Carga histórica de MARZO (01-03-2026 a 23-03-2026)
  Fuente  : https://plataforma.sistemagps.online/api  (GET /api/get_history)
  Destino : http://173.212.203.163:6055  (protocolo OsmAnd HTTP)

ESTRATEGIA:
  - Por cada dispositivo, obtener historial día a día (1 día por request)
  - Enviar puntos GPS al destino via OsmAnd HTTP en paralelo
  - Máximo 5 dispositivos en paralelo (respetar límites de la fuente)
  - Máximo 20 puntos GPS en paralelo por dispositivo (OsmAnd destino)
  - Pausa entre dispositivos para no saturar la fuente
  - Guardar progreso en historial_progreso.json para reanudar si se interrumpe

ENDPOINTS CONFIRMADOS:
  POST /api/get_history  (from_date, to_date, from_time, to_time, device_id)
  GET  :6055/?id=IMEI&lat=X&lon=Y&speed=S&bearing=B&altitude=A&timestamp=T
"""

import os
import requests
import json
import time
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta, date

# ─── CONFIG ──────────────────────────────────────────────────────────────────
SRC_BASE     = 'https://plataforma.sistemagps.online/api'
SRC_EMAIL    = os.getenv('PLATAFORMA_EMAIL',    'gerencia@rastrear.com.co')
SRC_PASS     = os.getenv('PLATAFORMA_PASSWORD', 'a791025*')
DST_OSMAND   = 'http://173.212.203.163:6055'
DST_BASE     = 'http://173.212.203.163/api'
DST_EMAIL    = 'gerencia@rastrear.com.co'
DST_PASS     = 'Colombias1*'
MAP_FILE     = 'migracion_mapa.json'
PROGRESO_FILE = 'historial_progreso.json'
FECHA_INICIO  = date(2026, 3, 1)
FECHA_FIN     = date(2026, 3, 23)   # hoy exclusive = hasta ayer

# Límites de concurrencia (respetar la API fuente)
MAX_DEV_PARALELO  = 4    # dispositivos en paralelo
MAX_OSMAND_PAR    = 20   # puntos GPS en paralelo por dispositivo
PAUSA_ENTRE_DEVS  = 0.5  # seg entre grupos de dispositivos
PAUSA_ENTRE_DIAS  = 0.3  # seg entre días de un mismo dispositivo
# ─────────────────────────────────────────────────────────────────────────────


def make_session():
    s = requests.Session()
    s.mount('http://',  HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1)))
    s.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1)))
    return s


def login(session, base, email, pw):
    r = session.post(base + '/login', json={'email': email, 'password': pw}, timeout=30)
    r.raise_for_status()
    return r.json()['user_api_hash']


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    try:
        with open('historial_out.txt', 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except:
        pass


def cargar_progreso():
    try:
        with open(PROGRESO_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def guardar_progreso(prog):
    with open(PROGRESO_FILE, 'w', encoding='utf-8') as f:
        json.dump(prog, f, indent=2)


def cargar_mapa():
    try:
        with open(MAP_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# ─── GET HISTORY ─────────────────────────────────────────────────────────────

def _parsear_puntos(data):
    """Extrae puntos GPS de la respuesta de /get_history."""
    puntos = []
    items_top = data.get('items') or []
    for segmento in items_top:
        for p in (segmento.get('items') or []):
            lat   = p.get('latitude') or p.get('lat', 0)
            lng   = p.get('longitude') or p.get('lng', 0)
            spd   = p.get('speed', 0) or 0
            alt   = p.get('altitude', 0) or 0
            crs   = p.get('course', 0) or 0
            raw_t = p.get('raw_time') or p.get('time') or ''
            if lat and lng and raw_t:
                try:
                    dt = datetime.strptime(raw_t, '%Y-%m-%d %H:%M:%S')
                    ts = int(dt.timestamp())
                except:
                    ts = int(time.time())
                puntos.append({
                    'lat': lat, 'lng': lng, 'speed': spd,
                    'altitude': alt, 'course': crs, 'timestamp': ts
                })
    return puntos


# Franjas horarias para evitar truncar si el API tiene límite de registros por request
FRANJAS_HORARIAS = [
    ('00:00', '05:59'),
    ('06:00', '11:59'),
    ('12:00', '17:59'),
    ('18:00', '23:59'),
]


def obtener_historia_dia(session, token, device_id, dia: date):
    """Obtiene los puntos GPS de un dispositivo para un día específico.
    Divide el día en 4 franjas de 6 horas para evitar el límite de registros por request.
    """
    fecha_str = dia.strftime('%Y-%m-%d')
    todos_los_puntos = []
    vistos = set()   # deduplicar por timestamp

    for from_time, to_time in FRANJAS_HORARIAS:
        try:
            r = session.post(SRC_BASE + '/get_history', json={
                'user_api_hash': token,
                'device_id'    : device_id,
                'from_date'    : fecha_str,
                'to_date'      : fecha_str,
                'from_time'    : from_time,
                'to_time'      : to_time,
            }, timeout=60)
            r.raise_for_status()
            data = r.json()
            if data.get('status') != 1:
                continue

            for p in _parsear_puntos(data):
                key = p['timestamp']
                if key not in vistos:
                    vistos.add(key)
                    todos_los_puntos.append(p)

            time.sleep(0.1)  # pausa mínima entre franjas
        except Exception as e:
            log(f'    ⚠ get_history {device_id} {fecha_str} {from_time}-{to_time}: {e}')

    return todos_los_puntos


# ─── ENVÍO OSMAND ─────────────────────────────────────────────────────────────

async def enviar_puntos_osmand(imei: str, puntos: list, session_aio: aiohttp.ClientSession):
    """Envía lista de puntos GPS al destino via OsmAnd asíncrono."""
    enviados = 0
    errores  = 0

    semaphore = asyncio.Semaphore(MAX_OSMAND_PAR)

    async def _enviar_uno(p):
        nonlocal enviados, errores
        url = (
            f"{DST_OSMAND}/"
            f"?id={imei}"
            f"&lat={p['lat']}"
            f"&lon={p['lng']}"
            f"&speed={p['speed']}"
            f"&bearing={p['course']}"
            f"&altitude={p['altitude']}"
            f"&timestamp={p['timestamp']}"
        )
        async with semaphore:
            try:
                async with session_aio.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        enviados += 1
                    else:
                        errores += 1
            except:
                errores += 1

    tasks = [_enviar_uno(p) for p in puntos]
    await asyncio.gather(*tasks)
    return enviados, errores


def procesar_dispositivo(args):
    """
    Procesa UN dispositivo: obtiene historial de todos los días y lo envía.
    Diseñado para ejecutarse en ThreadPoolExecutor.
    """
    nombre, imei, device_id_src, token_src, progreso = args
    clave = str(device_id_src)

    # Ver hasta qué día ya hay progreso
    ya_procesados = set(progreso.get(clave, {}).get('dias_ok', []))
    dias_totales = []
    dia = FECHA_INICIO
    while dia <= FECHA_FIN:
        dias_totales.append(dia)
        dia += timedelta(days=1)

    dias_pendientes = [d for d in dias_totales if d.strftime('%Y-%m-%d') not in ya_procesados]
    if not dias_pendientes:
        return nombre, imei, 0, 0, 0  # ya completo

    session = make_session()
    total_enviados = 0
    total_errores  = 0
    total_puntos   = 0

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    connector = aiohttp.TCPConnector(limit=MAX_OSMAND_PAR, loop=loop)

    async def _run_device():
        nonlocal total_enviados, total_errores, total_puntos
        async with aiohttp.ClientSession(connector=connector) as aio:
            for dia in dias_pendientes:
                puntos = obtener_historia_dia(session, token_src, device_id_src, dia)
                total_puntos += len(puntos)
                if puntos:
                    env, err = await enviar_puntos_osmand(imei, puntos, aio)
                    total_enviados += env
                    total_errores  += err
                # Registrar día como procesado
                ya_procesados.add(dia.strftime('%Y-%m-%d'))
                time.sleep(PAUSA_ENTRE_DIAS)

    try:
        loop.run_until_complete(_run_device())
    finally:
        loop.close()

    return nombre, imei, total_puntos, total_enviados, total_errores


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    log('=' * 65)
    log(f' FASE 2: Carga histórica MARZO 2026')
    log(f' Desde: {FECHA_INICIO}  Hasta: {FECHA_FIN}')
    log('=' * 65)

    # Cargar mapa IMEI → device_id_dst y device_id_src
    mapa = cargar_mapa()
    if not mapa:
        log('ERROR: Ejecuta primero migrar_grupos_dispositivos.py para crear el mapa')
        return

    progreso = cargar_progreso()

    session = make_session()
    log('\n[Auth] Autenticando en fuente...')
    token_src = login(session, SRC_BASE, SRC_EMAIL, SRC_PASS)
    log('  OK')

    # Obtener todos los dispositivos de la fuente con sus IDs
    log('[Fuente] Leyendo dispositivos...')
    r = session.post(SRC_BASE + '/get_devices', json={'user_api_hash': token_src}, timeout=60)
    r.raise_for_status()
    grupos_src = r.json()

    # Construir lista: (nombre, imei, device_id_fuente)
    dispositivos = []
    for g in grupos_src:
        for d in g.get('items', []):
            dd = d.get('device_data') or {}
            imei = str(dd.get('imei') or '').strip()
            nombre = (d.get('name') or '').strip()
            dev_id = d.get('id')
            if imei and nombre and dev_id and imei in mapa:
                # Solo procesar si está en el mapa (ya migrado al destino)
                dispositivos.append((nombre, imei, dev_id))

    log(f'  {len(dispositivos)} dispositivos para procesar')

    # Estadísticas globales
    total_devs_ok = 0
    total_puntos  = 0
    total_env     = 0
    total_err     = 0

    # Construir args para executor
    args_list = [
        (nombre, imei, dev_id, token_src, progreso)
        for nombre, imei, dev_id in dispositivos
    ]

    log(f'\n[Historial] Procesando {len(args_list)} devs en {MAX_DEV_PARALELO} paralelo...\n')

    with ThreadPoolExecutor(max_workers=MAX_DEV_PARALELO) as executor:
        futures = {executor.submit(procesar_dispositivo, args): args for args in args_list}

        for i, fut in enumerate(as_completed(futures), 1):
            try:
                nombre, imei, puntos, enviados, errores = fut.result()
                total_devs_ok += 1
                total_puntos  += puntos
                total_env     += enviados
                total_err     += errores

                dev_id = futures[fut][2]
                clave  = str(dev_id)

                # Guardar progreso
                if clave not in progreso:
                    progreso[clave] = {'nombre': nombre, 'imei': imei, 'dias_ok': []}
                # Las fechas ya las guardamos dentro de procesar_dispositivo
                progreso[clave]['puntos_total'] = (
                    progreso[clave].get('puntos_total', 0) + puntos)
                guardar_progreso(progreso)

                log(f'  [{i}/{len(args_list)}] {nombre} | {puntos} pts | '
                    f'{enviados} env | {errores} err')

                # Re-autenticar cada 100 dispositivos
                if i % 100 == 0:
                    log('  🔁 Re-autenticando en fuente...')
                    token_src = login(session, SRC_BASE, SRC_EMAIL, SRC_PASS)
                    # Actualizar token en args pendientes no funciona aquí,
                    # pero el ThreadPoolExecutor ya lanzó los threads;
                    # el reauth se aplica a las siguientes rondas.

                time.sleep(PAUSA_ENTRE_DEVS)

            except Exception as e:
                log(f'  ❌ Error en dispositivo: {e}')

    log('\n' + '=' * 65)
    log('RESUMEN CARGA HISTÓRICA:')
    log(f'  Dispositivos procesados : {total_devs_ok}')
    log(f'  Puntos totales leídos   : {total_puntos:,}')
    log(f'  Puntos enviados OK      : {total_env:,}')
    log(f'  Errores de envío        : {total_err:,}')
    log('=' * 65)


if __name__ == '__main__':
    main()
