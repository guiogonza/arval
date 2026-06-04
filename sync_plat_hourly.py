#!/usr/bin/env python3
"""
sync_plat_hourly.py — Sincronización horaria
──────────────────────────────────────────────
Fuente  : https://plataforma.sistemagps.online  (servidor principal)
Destino : gps.rastrear.com.co / 127.0.0.1      (servidor backup)

Reglas:
  - Si un dispositivo existe en fuente pero NO en destino → se crea en destino.
  - Si existe en AMBOS: valida que IMEI y placa coincidan (log de mismatches).
  - NUNCA se modifica la fuente (el destino es backup, sólo recibe).
  - Cron: 0 * * * *  (cada hora)

Después de sincronizar el catálogo, obtiene el historial de las últimas 2 horas
de cada dispositivo e inserta directamente en gpswox_traccar.positions_{traccar_id}.
"""

import requests
import os
import time
import json
import threading
import pymysql
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── CONFIG ──────────────────────────────────────────────────────────────────
SRC_BASE  = 'https://plataforma.sistemagps.online/api'
SRC_EMAIL = os.getenv('PLATAFORMA_EMAIL', 'gerencia@rastrear.com.co')
SRC_PASS  = os.getenv('PLATAFORMA_PASSWORD', '')

DST_BASE   = 'https://gps.rastrear.com.co/api'   # HTTPS con cert válido
DST_EMAIL  = os.getenv('GPSWOX_EMAIL', 'gerencia@rastrear.com.co')
DST_PASS   = os.getenv('GPSWOX_PASSWORD', '')

# MySQL directo en el VPS
MYSQL_HOST       = '127.0.0.1'
MYSQL_PORT       = 3306
MYSQL_USER       = os.getenv('GPSWOX_DB_USER', 'root')
MYSQL_PASS       = os.getenv('GPSWOX_DB_PASSWORD', '')
MYSQL_DB         = 'gpswox_web'
MYSQL_TRACCAR_DB = 'gpswox_traccar'

LOG_FILE    = '/root/sync_gps/sync_plat_hourly.log'
ESTADO_FILE = '/root/sync_gps/sync_plat_estado.json'
MAX_LOG_LINES = 10000   # rotación ligera
SRC_TIMEZONE = 'America/Bogota'

# Concurrencia
MAX_SRC_SEM = 3    # workers paralelos (API fuente + inserts MySQL)
PAUSA_DEVS  = 0.3  # segundos entre dispositivos

_src_sem = threading.Semaphore(MAX_SRC_SEM)
# ─────────────────────────────────────────────────────────────────────────────


# ─── UTILIDADES ──────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    s.mount('http://',  HTTPAdapter(max_retries=retry))
    s.mount('https://', HTTPAdapter(max_retries=retry))
    return s


def log(msg: str):
    ts   = datetime.now(ZoneInfo(SRC_TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def login(session: requests.Session, base: str, email: str, pw: str) -> str:
    r = session.post(f'{base}/login',
                     json={'email': email, 'password': pw}, timeout=30)
    r.raise_for_status()
    d = r.json()
    if 'user_api_hash' not in d:
        raise ValueError(f'Login failed en {base}: {d}')
    return d['user_api_hash'].strip()


def guardar_estado(datos: dict):
    try:
        with open(ESTADO_FILE, 'w', encoding='utf-8') as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ─── CATÃLOGO DE DISPOSITIVOS ─────────────────────────────────────────────────

def get_all_devices_src(session: requests.Session, token: str) -> dict:
    """
    Lee dispositivos del servidor FUENTE via API.
    Retorna {imei: {name, device_id, group_id, group_name}}.
    """
    r = session.post(f'{SRC_BASE}/get_devices',
                     json={'user_api_hash': token}, timeout=60)
    r.raise_for_status()
    resultado = {}
    for g in r.json():
        if not isinstance(g, dict):
            continue
        gid   = g.get('id')
        gname = (g.get('title') or g.get('name') or 'Sin grupo').strip()
        for item in (g.get('items') or []):
            if not isinstance(item, dict):
                continue
            dd     = item.get('device_data') or {}
            imei   = str(dd.get('imei') or '').strip()
            name   = (item.get('name') or '').strip()
            dev_id = item.get('id')
            if imei and dev_id:
                resultado[imei] = {
                    'name':       name,
                    'device_id':  dev_id,
                    'group_id':   gid,
                    'group_name': gname,
                }
    return resultado


def get_all_devices_dst() -> dict:
    """
    Lee dispositivos del servidor DESTINO directamente por MySQL.
    Retorna {imei: {name, device_id}}.
    GPSWox v3.7.7: get_devices API devuelve 400, usamos MySQL local.
    """
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, charset='utf8mb4',
        connect_timeout=10,
    )
    resultado = {}
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT id, imei, name FROM devices'
            )
            for row in cur.fetchall():
                dev_id, imei, name = row
                imei = str(imei or '').strip()
                if imei:
                    resultado[imei] = {
                        'name':      (name or '').strip(),
                        'device_id': dev_id,
                    }
    finally:
        conn.close()
    return resultado


def get_groups_dst_mysql() -> dict:
    """Lee los grupos del destino desde MySQL. Retorna {nombre: id}."""
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, charset='utf8mb4',
        connect_timeout=10,
    )
    grupos = {}
    try:
        with conn.cursor() as cur:
            try:
                cur.execute('SELECT id, title FROM device_groups')
                for gid, gtitle in cur.fetchall():
                    if gtitle:
                        grupos[gtitle.strip()] = gid
            except Exception:
                pass   # si no existe la tabla, retorna dict vacío
    finally:
        conn.close()
    return grupos


def get_or_create_group(session: requests.Session, token_dst: str,
                         gname: str, groups_by_name: dict) -> Optional[int]:
    """Devuelve el group_id del destino que coincide con gname, creándolo si no existe."""
    if gname in groups_by_name:
        return groups_by_name[gname]
    # Intentar crear
    try:
        r = session.post(f'{DST_BASE}/add_group',
                          json={'user_api_hash': token_dst, 'title': gname}, timeout=20)
        if r.status_code == 200:
            d = r.json()
            gid = d.get('id') or d.get('group_id')
            if gid:
                groups_by_name[gname] = int(gid)
                log(f'  [GRUPO] Creado "{gname}" → id {gid}')
                return int(gid)
    except Exception as exc:
        log(f'  [GRUPO] No se pudo crear "{gname}": {exc}')
    # Fallback: retorna None (GPSWox asignará grupo por defecto)
    return None


def sync_catalogo(session_src: requests.Session, token_src: str,
                   session_dst: requests.Session, token_dst: str) -> dict:
    """
    Sincroniza catálogo fuente → destino.
    Retorna el mapa completo de dispositivos de la fuente.
    """
    log('\n[CATÃLOGO] Leyendo fuente (API)...')
    devs_src = get_all_devices_src(session_src, token_src)
    log(f'  Fuente : {len(devs_src)} dispositivos')

    log('[CATÃLOGO] Leyendo destino (MySQL directo)...')
    devs_dst = get_all_devices_dst()
    log(f'  Destino: {len(devs_dst)} dispositivos')

    # Grupos del destino desde MySQL
    groups_by_name = get_groups_dst_mysql()
    log(f'  Grupos en destino: {len(groups_by_name)}')

    nuevos     = 0
    mismatches = []
    ya_existen = 0

    for imei, src in devs_src.items():
        if imei in devs_dst:
            dst = devs_dst[imei]
            src_plate = src['name'].upper().strip()
            dst_plate = dst['name'].upper().strip()
            if src_plate != dst_plate:
                mismatches.append({
                    'imei':     imei,
                    'fuente':   src['name'],
                    'destino':  dst['name'],
                })
                log(f'  [MISMATCH] IMEI={imei} | Fuente="{src["name"]}" | Destino="{dst["name"]}"')
            else:
                ya_existen += 1
        else:
            # Crear en destino
            gid = get_or_create_group(session_dst, token_dst,
                                       src['group_name'], groups_by_name)
            payload = {
                'user_api_hash': token_dst,
                'name':          src['name'],
                'imei':          imei,
                'protocol':      'osmand',
            }
            if gid:
                payload['group_id'] = gid
            try:
                r = session_dst.post(f'{DST_BASE}/add_device', json=payload, timeout=30)
                if r.status_code == 200 and r.json().get('status') == 1:
                    new_id = r.json().get('id')
                    nuevos += 1
                    log(f'  [NUEVO] "{src["name"]}" IMEI={imei} → id {new_id}')
                else:
                    log(f'  [ERROR-CREAR] "{src["name"]}" IMEI={imei}: {r.text[:200]}')
            except Exception as exc:
                log(f'  [ERROR-CREAR] "{src["name"]}" IMEI={imei}: {exc}')

    log(f'[CATÃLOGO] OK: {ya_existen} existentes | {nuevos} creados | {len(mismatches)} mismatches')

    if mismatches:
        log('[CATÃLOGO] Mismatches IMEI/Placa:')
        for m in mismatches:
            log(f'           IMEI={m["imei"]} | Fuente="{m["fuente"]}" | Destino="{m["destino"]}"')

    return devs_src, nuevos, mismatches


def get_traccar_id_map() -> dict:
    """Retorna {imei: traccar_device_id} desde gpswox_web.devices."""
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, charset='utf8mb4',
        connect_timeout=10,
    )
    resultado = {}
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT imei, traccar_device_id FROM devices WHERE traccar_device_id > 0')
            for imei, tid in cur.fetchall():
                imei = str(imei or '').strip()
                if imei and tid:
                    resultado[imei] = int(tid)
    finally:
        conn.close()
    return resultado


def actualizar_traccar_device_latest(traccar_id: int, pos: dict):
    # /objects reads traccar_devices for the current map position.
    if not pos:
        return
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, charset='utf8mb4',
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        pos_time = pos.get('time')
        with conn.cursor() as cur:
            cur.execute(
                'SELECT time, latest_positions FROM traccar_devices WHERE id = %s',
                (traccar_id,),
            )
            current = cur.fetchone()
            if not current:
                return
            current_time = current.get('time')
            if current_time and pos_time and current_time >= pos_time:
                return
            point = f"{float(pos['latitude']):.6f}/{float(pos['longitude']):.6f}"
            tail = [x for x in (current.get('latest_positions') or '').split(';') if x]
            latest_positions = ';'.join(([point] + tail)[:15])
            cur.execute(
                'UPDATE traccar_devices '
                'SET latestPosition_id = %s, '
                'lastValidLatitude = %s, lastValidLongitude = %s, '
                'altitude = %s, course = %s, speed = %s, '
                'time = %s, device_time = %s, server_time = %s, '
                'protocol = %s, latest_positions = %s, updated_at = NOW() '
                'WHERE id = %s',
                (pos.get('id'), pos.get('latitude'), pos.get('longitude'),
                 pos.get('altitude') or 0, pos.get('course') or 0, pos.get('speed') or 0,
                 pos.get('time'), pos.get('device_time') or pos.get('time'),
                 pos.get('server_time') or datetime.now(ZoneInfo(SRC_TIMEZONE)).strftime('%Y-%m-%d %H:%M:%S'),
                 pos.get('protocol') or 'plataforma', latest_positions, traccar_id),
            )
        conn.commit()
    except Exception as exc:
        log(f'[MYSQL-LATEST-ERR] traccar_id={traccar_id}: {exc}')
    finally:
        conn.close()


def insertar_posiciones_mysql_dev(traccar_id: int, puntos: list) -> tuple:
    """
    Inserta posiciones GPS directamente en gpswox_traccar.positions_{traccar_id}.
    Crea la tabla si no existe y actualiza traccar_devices para el mapa actual.
    Retorna (insertados, errores).
    """
    if not puntos:
        return 0, 0
    tabla = f'positions_{traccar_id}'
    tz_src = ZoneInfo(SRC_TIMEZONE)
    server_time = datetime.now(tz_src).strftime('%Y-%m-%d %H:%M:%S')
    vals = []
    for p in puntos:
        try:
            dt = datetime.fromtimestamp(p['timestamp'], tz_src).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            dt = server_time
        vals.append((traccar_id, p.get('altitude', 0), p.get('course', 0),
                     p['lat'], p['lng'],
                     None, None, p.get('speed', 0),
                     dt, dt, server_time,
                     None, 1, 0.0, 'plataforma'))
    conn = pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_TRACCAR_DB, charset='utf8mb4',
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE TABLE IF NOT EXISTS `{tabla}` LIKE positions_1')
            cur.executemany(
                f'INSERT INTO `{tabla}` '
                '(device_id, altitude, course, latitude, longitude, other, power, '
                'speed, time, device_time, server_time, sensors_values, valid, distance, protocol) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                vals
            )
            conn.commit()
            cur.execute(
                f'SELECT id, latitude, longitude, altitude, course, speed, time, device_time, server_time, protocol '
                f'FROM `{tabla}` ORDER BY time DESC, id DESC LIMIT 1'
            )
            latest = cur.fetchone()
        actualizar_traccar_device_latest(traccar_id, latest)
        return len(vals), 0
    except Exception as exc:
        log(f'[MYSQL-ERR] {tabla}: {exc}')
        return 0, len(puntos)
    finally:
        conn.close()


# ─── HISTORIAL (últimas 2 horas) ──────────────────────────────────────────────

FRANJAS_HORARIAS = [
    ('00:00', '05:59'),
    ('06:00', '11:59'),
    ('12:00', '17:59'),
    ('18:00', '23:59'),
]


def _parsear_puntos(data: dict) -> list:
    puntos = []
    vistos = set()
    for seg in (data.get('items') or []):
        for p in (seg.get('items') or []):
            lat   = float(p.get('latitude') or p.get('lat') or 0)
            lng   = float(p.get('longitude') or p.get('lng') or 0)
            spd   = float(p.get('speed') or 0)
            alt   = float(p.get('altitude') or 0)
            crs   = float(p.get('course') or 0)
            raw_t = p.get('raw_time') or p.get('time') or ''
            if not lat or not lng:
                continue
            try:
                ts = int(
                    datetime.strptime(raw_t, '%Y-%m-%d %H:%M:%S')
                    .replace(tzinfo=ZoneInfo(SRC_TIMEZONE))
                    .timestamp()
                )
            except Exception:
                ts = int(time.time())
            if ts not in vistos:
                vistos.add(ts)
                puntos.append({'lat': lat, 'lng': lng, 'speed': spd,
                               'altitude': alt, 'course': crs, 'timestamp': ts})
    return puntos


def obtener_historia_intervalo(session: requests.Session, token: str,
                                device_id: int, from_date: str, to_date: str,
                                from_time: str, to_time: str) -> list:
    """Obtiene puntos GPS de un dispositivo en un intervalo de tiempo."""
    puntos = []
    for intento in range(4):
        try:
            with _src_sem:
                r = session.post(f'{SRC_BASE}/get_history', json={
                    'user_api_hash': token,
                    'device_id':     device_id,
                    'from_date':     from_date,
                    'to_date':       to_date,
                    'from_time':     from_time,
                    'to_time':       to_time,
                }, timeout=60)

            if r.status_code == 429:
                wait = int(r.headers.get('Retry-After', 10))
                log(f'    â³ 429 rate-limit device={device_id} — esperando {wait}s')
                time.sleep(wait)
                continue

            r.raise_for_status()
            data = r.json()
            if data.get('status') == 1:
                puntos = _parsear_puntos(data)
            break

        except Exception as exc:
            espera = 2 ** (intento + 1)
            log(f'    ⚠ get_history device={device_id} intento={intento+1}: {exc} (retry {espera}s)')
            time.sleep(espera)

    return puntos


def sync_posiciones_recientes(session_src: requests.Session, token_src: str,
                               devs_src: dict) -> tuple:
    """
    Obtiene el historial de las últimas 2 horas de cada dispositivo
    e inserta directamente en gpswox_traccar.positions_{traccar_id}.
    """
    log('\n[POSICIONES] Sincronizando últimas 2 horas...')

    tz_src = ZoneInfo(SRC_TIMEZONE)
    hasta_dt = datetime.now(tz_src)
    desde_dt = hasta_dt - timedelta(hours=2)

    from_date = desde_dt.strftime('%Y-%m-%d')
    to_date = hasta_dt.strftime('%Y-%m-%d')
    from_time = desde_dt.strftime('%H:%M')
    to_time = hasta_dt.strftime('%H:%M')

    log(f'  TZ fuente: {SRC_TIMEZONE}')
    log(f'  Intervalo: {from_date} {from_time} → {to_date} {to_time}')

    traccar_map = get_traccar_id_map()
    log(f'  Mapa traccar_id: {len(traccar_map)} dispositivos')

    total_env  = 0
    total_err  = 0
    devs_ok    = 0

    def _tarea(item):
        imei, info = item
        traccar_id = traccar_map.get(imei)
        if not traccar_id:
            return 0, 0
        dev_id = info['device_id']
        puntos = obtener_historia_intervalo(
            session_src, token_src, dev_id,
            from_date, to_date, from_time, to_time
        )
        if not puntos:
            return 0, 0
        return insertar_posiciones_mysql_dev(traccar_id, puntos)

    with ThreadPoolExecutor(max_workers=MAX_SRC_SEM) as pool:
        for env, err in pool.map(_tarea, list(devs_src.items())):
            total_env += env
            total_err += err
            if env > 0:
                devs_ok += 1

    log(f'[POSICIONES] Insertados={total_env} | Errores={total_err} | Vehículos con datos={devs_ok}')
    return total_env, total_err


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    inicio = datetime.now(ZoneInfo(SRC_TIMEZONE))
    log('=' * 65)
    log(f' SYNC HORARIO: plataforma.sistemagps.online → gps.rastrear.com.co')
    log(f' {inicio.strftime("%Y-%m-%d %H:%M:%S")}')
    log('=' * 65)

    session_src = make_session()
    session_dst = make_session()

    try:
        log('\n[Auth] Autenticando en fuente...')
        token_src = login(session_src, SRC_BASE, SRC_EMAIL, SRC_PASS)
        log('  Fuente OK')

        log('[Auth] Autenticando en destino...')
        token_dst = login(session_dst, DST_BASE, DST_EMAIL, DST_PASS)
        log('  Destino OK')

        devs_src, nuevos, mismatches = sync_catalogo(
            session_src, token_src, session_dst, token_dst
        )

        env_ok, env_err = sync_posiciones_recientes(
            session_src, token_src, devs_src
        )

        fin      = datetime.now(ZoneInfo(SRC_TIMEZONE))
        duracion = round((fin - inicio).total_seconds(), 1)

        guardar_estado({
            'ultima_sync':           fin.strftime('%Y-%m-%d %H:%M:%S'),
            'duracion_s':            duracion,
            'dispositivos_fuente':   len(devs_src),
            'nuevos_creados':        nuevos,
            'mismatches_imei_placa': len(mismatches),
            'posiciones_enviadas':   env_ok,
            'posiciones_error':      env_err,
            'mismatches_detalle':    mismatches,
        })

        log(f'\n[FIN] Completado en {duracion}s')

    except Exception as exc:
        import traceback
        log(f'[FATAL] {exc}')
        log(traceback.format_exc())
        raise


if __name__ == '__main__':
    main()
