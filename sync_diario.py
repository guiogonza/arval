"""
FASE 3 — Sincronización automática diaria
  Corre a la 1:00 AM GMT-5 (06:00 UTC)
  Descarga el día ANTERIOR del fuente y lo sube al destino

EJECUCIÓN:
  python sync_diario.py              → loop infinito (proceso permanente)
  python sync_diario.py --ahora     → ejecuta una sola vez inmediatamente (debug)
  python sync_diario.py --fecha 2026-03-20  → procesa una fecha específica

INSTALAR COMO SERVICIO WINDOWS:
  pip install pywin32
  python sync_diario.py --instalar-servicio   (requiere privilegios admin)

TASK SCHEDULER (alternativa sin privilegios admin):
  El script crea la tarea automáticamente si se ejecuta con --programar-tarea
"""

import sys
import os
import time
import json
import asyncio
import aiohttp
import requests
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta, date, timezone

# ─── CONFIG ──────────────────────────────────────────────────────────────────
SRC_BASE   = 'https://plataforma.sistemagps.online/api'
SRC_EMAIL  = os.getenv('PLATAFORMA_EMAIL',  'gerencia@rastrear.com.co')
SRC_PASS   = os.getenv('PLATAFORMA_PASSWORD', 'a791025*')
DST_OSMAND = 'http://173.212.203.163:6055'
DST_BASE   = 'http://173.212.203.163/api'
DST_EMAIL  = os.getenv('DST_EMAIL',    'gerencia@rastrear.com.co')
DST_PASS   = os.getenv('DST_PASSWORD', 'Colombias1*')
MAP_FILE   = 'migracion_mapa.json'
LOG_FILE   = 'historial_out.txt'
ERR_FILE   = 'historial_err.txt'

# Hora de ejecución: 1:00 AM GMT-5 = 06:00 UTC
HORA_UTC_EJECUCION = 6    # 06:00 UTC = 01:00 GMT-5
MINUTO_EJECUCION   = 0

MAX_DEV_PARALELO   = 4
MAX_OSMAND_PAR     = 20
PAUSA_ENTRE_DEVS   = 0.5
PAUSA_ENTRE_DIAS   = 0.3
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


def log(msg, error=False):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    archivo = ERR_FILE if error else LOG_FILE
    try:
        with open(archivo, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except:
        pass


def cargar_mapa():
    try:
        with open(MAP_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# ─── GET HISTORY + OSMAND ──────────────────────────────────────────────────

def obtener_historia_dia(session, token, device_id, dia: date):
    """Puntos GPS de un dispositivo para un día dado."""
    fecha_str = dia.strftime('%Y-%m-%d')
    try:
        r = session.post(SRC_BASE + '/get_history', json={
            'user_api_hash': token,
            'device_id'    : device_id,
            'from_date'    : fecha_str,
            'to_date'      : fecha_str,
            'from_time'    : '00:00',
            'to_time'      : '23:59',
        }, timeout=60)
        r.raise_for_status()
        data = r.json()
        if data.get('status') != 1:
            return []
        puntos = []
        for segmento in (data.get('items') or []):
            for p in (segmento.get('items') or []):
                lat  = p.get('latitude') or p.get('lat', 0)
                lng  = p.get('longitude') or p.get('lng', 0)
                spd  = p.get('speed', 0) or 0
                alt  = p.get('altitude', 0) or 0
                crs  = p.get('course', 0) or 0
                raw_t = p.get('raw_time') or p.get('time') or ''
                if lat and lng and raw_t:
                    try:
                        dt = datetime.strptime(raw_t, '%Y-%m-%d %H:%M:%S')
                        ts = int(dt.timestamp())
                    except:
                        ts = int(time.time())
                    puntos.append({'lat': lat, 'lng': lng, 'speed': spd,
                                   'altitude': alt, 'course': crs, 'timestamp': ts})
        return puntos
    except Exception as e:
        log(f'  ⚠ get_history dev={device_id} {fecha_str}: {e}', error=True)
        return []


async def enviar_puntos_osmand(imei, puntos, aio_session):
    """Envío paralelo de puntos GPS via OsmAnd."""
    enviados = 0
    errores  = 0
    sem = asyncio.Semaphore(MAX_OSMAND_PAR)

    async def _uno(p):
        nonlocal enviados, errores
        url = (f"{DST_OSMAND}/?id={imei}&lat={p['lat']}&lon={p['lng']}"
               f"&speed={p['speed']}&bearing={p['course']}"
               f"&altitude={p['altitude']}&timestamp={p['timestamp']}")
        async with sem:
            try:
                async with aio_session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        enviados += 1
                    else:
                        errores += 1
            except:
                errores += 1

    await asyncio.gather(*[_uno(p) for p in puntos])
    return enviados, errores


def procesar_dispositivo_dia(args):
    """Thread worker: procesa un dispositivo para el día indicado."""
    nombre, imei, dev_id_src, token_src, dia = args
    session = make_session()
    puntos = obtener_historia_dia(session, token_src, dev_id_src, dia)
    if not puntos:
        return nombre, imei, 0, 0, 0

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    connector = aiohttp.TCPConnector(limit=MAX_OSMAND_PAR, loop=loop)
    try:
        async def _run():
            async with aiohttp.ClientSession(connector=connector) as aio:
                return await enviar_puntos_osmand(imei, puntos, aio)
        env, err = loop.run_until_complete(_run())
    finally:
        loop.close()

    time.sleep(PAUSA_ENTRE_DEVS)
    return nombre, imei, len(puntos), env, err


# ─── SINCRONIZACIÓN DE UN DÍA ─────────────────────────────────────────────

def sync_dia(dia: date):
    """Descarga y sube todos los dispositivos para la fecha indicada."""
    log(f'\n{"="*65}')
    log(f' SYNC DIARIO: {dia.strftime("%Y-%m-%d")}')
    log(f'{"="*65}')

    mapa = cargar_mapa()
    if not mapa:
        log('ERROR: migracion_mapa.json no encontrado. Ejecuta primero migrar_grupos_dispositivos.py', error=True)
        return

    session = make_session()

    # Auth
    log('[Auth] Autenticando...')
    try:
        token_src = login(session, SRC_BASE, SRC_EMAIL, SRC_PASS)
    except Exception as e:
        log(f'[Auth] ERROR fuente: {e}', error=True)
        return
    log('  OK')

    # Leer dispositivos fuente
    log('[Fuente] Leyendo dispositivos...')
    try:
        r = session.post(SRC_BASE + '/get_devices', json={'user_api_hash': token_src}, timeout=60)
        r.raise_for_status()
        grupos_src = r.json()
    except Exception as e:
        log(f'[Fuente] ERROR get_devices: {e}', error=True)
        return

    # Construir lista de trabajos
    trabajos = []
    for g in grupos_src:
        for d in g.get('items', []):
            dd = d.get('device_data') or {}
            imei = str(dd.get('imei') or '').strip()
            nombre = (d.get('name') or '').strip()
            dev_id = d.get('id')
            if imei and nombre and dev_id and imei in mapa:
                trabajos.append((nombre, imei, dev_id, token_src, dia))

    log(f'  {len(trabajos)} dispositivos a sincronizar')

    total_pts = 0
    total_env = 0
    total_err = 0
    ok = 0

    with ThreadPoolExecutor(max_workers=MAX_DEV_PARALELO) as ex:
        futures = {ex.submit(procesar_dispositivo_dia, t): t for t in trabajos}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                nombre, imei, pts, env, err = fut.result()
                total_pts += pts
                total_env += env
                total_err += err
                ok += 1
                if pts > 0:
                    log(f'  [{i}/{len(trabajos)}] {nombre} | {pts} pts | {env} enviados')
            except Exception as e:
                log(f'  ❌ Error: {e}', error=True)

    log(f'\nRESUMEN {dia}:')
    log(f'  Devs procesados : {ok}')
    log(f'  Puntos leídos   : {total_pts:,}')
    log(f'  Enviados OK     : {total_env:,}')
    log(f'  Errores         : {total_err:,}')


# ─── SCHEDULER ────────────────────────────────────────────────────────────────

def segundos_hasta_proxima_ejecucion():
    """Segundos hasta la próxima ejecución a las 01:00 AM GMT-5 (06:00 UTC)."""
    ahora_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    hoy_target = ahora_utc.replace(hour=HORA_UTC_EJECUCION, minute=MINUTO_EJECUCION,
                                    second=0, microsecond=0)
    if ahora_utc >= hoy_target:
        # Ya pasó hoy → próxima ejecución mañana
        hoy_target += timedelta(days=1)
    delta = (hoy_target - ahora_utc).total_seconds()
    return max(0, delta)


def loop_scheduler():
    """Loop infinito: espera hasta las 01:00 AM GMT-5 y ejecuta el sync."""
    log('Scheduler iniciado — sincronización diaria a las 01:00 AM GMT-5 (06:00 UTC)')
    while True:
        espera = segundos_hasta_proxima_ejecucion()
        proxima = datetime.now() + timedelta(seconds=espera)
        log(f'Próxima ejecución en {espera/3600:.1f}h ({proxima.strftime("%Y-%m-%d %H:%M:%S local")})')
        time.sleep(espera)

        # El día a sincronizar es el día anterior (GMT-5)
        ayer = (datetime.now(timezone.utc) - timedelta(hours=5)).date() - timedelta(days=1)
        try:
            sync_dia(ayer)
        except Exception as e:
            log(f'ERROR en sync_dia: {e}', error=True)

        # Esperar 60 seg para no disparar doble si el sleep se adelanta
        time.sleep(60)


# ─── TASK SCHEDULER WINDOWS ───────────────────────────────────────────────────

def programar_tarea_windows():
    """Crea una tarea en el Programador de tareas de Windows."""
    import subprocess, sys, os
    script = os.path.abspath(__file__)
    python = sys.executable
    cmd = (
        f'schtasks /Create /TN "GPSSync_Diario" /TR "{python} {script} --ahora" '
        f'/SC DAILY /ST 01:00 /F /RU SYSTEM'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        log('✅ Tarea programada: GPSSync_Diario → 01:00 AM cada día')
    else:
        log(f'❌ Error creando tarea: {result.stderr}', error=True)
        log('Intenta correr como Administrador o usa el loop_scheduler()', error=True)


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sync diario GPS fuente→destino')
    parser.add_argument('--ahora', action='store_true',
                        help='Ejecutar sync del día anterior una sola vez ahora')
    parser.add_argument('--fecha', type=str, metavar='YYYY-MM-DD',
                        help='Sincronizar una fecha específica')
    parser.add_argument('--programar-tarea', action='store_true',
                        help='Crear tarea en el Programador de tareas de Windows')
    args = parser.parse_args()

    if args.programar_tarea:
        programar_tarea_windows()

    elif args.fecha:
        try:
            dia = datetime.strptime(args.fecha, '%Y-%m-%d').date()
        except ValueError:
            print('Formato de fecha inválido. Usa YYYY-MM-DD')
            sys.exit(1)
        sync_dia(dia)

    elif args.ahora:
        ayer = (datetime.now(timezone.utc) - timedelta(hours=5)).date() - timedelta(days=1)
        sync_dia(ayer)

    else:
        # Modo normal: loop infinito
        loop_scheduler()
