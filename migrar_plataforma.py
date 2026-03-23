"""
FASE 1 — Migración masiva de dispositivos
  Fuente  : https://plataforma.sistemagps.online  (809 objetos, 70 grupos)
  Destino : http://173.212.203.163

LIMITACIONES CONOCIDAS:
  - /api/add_group retorna 404 en el destino → todos los dispositivos van a "Sin grupo"
  - /api/get_device_history no existe en la fuente → posiciones históricas no disponibles por API
    (para historiales se requiere acceso SSH/MySQL directo al servidor fuente)

FLUJO:
  1. Login en ambos servidores
  2. Leer todos los dispositivos del destino (por IMEI → para detectar existentes)
  3. Leer los 809 dispositivos de la fuente
  4. Crear en destino los que faltan (5 solicitudes en paralelo, pausa entre lotes)
  5. Guardar mapa IMEI→id_destino en migración.json
"""

import requests
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
SRC_BASE   = 'https://plataforma.sistemagps.online/api'
DST_BASE   = 'http://173.212.203.163/api'
SRC_EMAIL  = 'gerencia@rastrear.com.co'
SRC_PASS   = 'a791025*'
DST_EMAIL  = 'gerencia@rastrear.com.co'
DST_PASS   = 'Colombias1*'

MAX_PARALLEL   = 5     # solicitudes paralelas al destino
PAUSA_LOTE     = 1.0   # segundos de pausa entre lotes
PAUSA_REQUEST  = 0.2   # segundos de pausa mínima entre requests individuales
BACKUP_FILE    = 'migracion.json'   # mapa IMEI → device_id destino
# ─────────────────────────────────────────────────────────────────────────────

_lock = threading.Lock()
log_lines = []


def make_session():
    s = requests.Session()
    s.mount('http://',  HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1)))
    s.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1)))
    return s


def login(session, base, email, password):
    r = session.post(base + '/login', json={'email': email, 'password': password}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get('status') != 1:
        raise ValueError(f'Login fallido en {base}: {data}')
    return data['user_api_hash']


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    log_lines.append(line)


def obtener_dispositivos_fuente(session, token):
    """Lee todos los grupos+dispositivos de la fuente."""
    r = session.post(SRC_BASE + '/get_devices', json={'user_api_hash': token}, timeout=60)
    r.raise_for_status()
    grupos = r.json()

    dispositivos = []
    for g in grupos:
        grupo_nombre = g.get('title') or g.get('name') or 'Sin grupo'
        for d in g.get('items', []):
            dd = d.get('device_data') or {}
            imei = dd.get('imei', '') or d.get('imei', '')
            nombre = (d.get('name') or '').strip()
            if not imei or not nombre:
                continue
            dispositivos.append({
                'nombre'       : nombre,
                'imei'         : str(imei).strip(),
                'grupo_fuente' : grupo_nombre,
                'lat'          : d.get('lat', 0) or 0,
                'lng'          : d.get('lng', 0) or 0,
                'time'         : d.get('time', ''),
                'speed'        : d.get('speed', 0) or 0,
                'course'       : d.get('course', 0) or 0,
                'altitude'     : d.get('altitude', 0) or 0,
            })
    return dispositivos


def obtener_dispositivos_destino(session, token):
    """Devuelve dict {imei: device_id} de todo lo que ya hay en el destino."""
    r = session.post(DST_BASE + '/get_devices', json={'user_api_hash': token}, timeout=60)
    r.raise_for_status()
    grupos = r.json()

    mapa = {}   # imei → id
    for g in grupos:
        for d in g.get('items', []):
            dd = d.get('device_data') or {}
            imei = str(dd.get('imei', '') or d.get('imei', '')).strip()
            dev_id = d.get('id')
            if imei and dev_id:
                mapa[imei] = dev_id
    return mapa


def crear_dispositivo(session, token, nombre, imei):
    """Crea un dispositivo en el destino. Retorna id o None."""
    time.sleep(PAUSA_REQUEST)
    try:
        r = session.post(DST_BASE + '/add_device', json={
            'user_api_hash': token,
            'name'         : nombre,
            'imei'         : imei,
            'protocol'     : 'osmand',
            'group_id'     : 0,    # Sin grupo (add_group no disponible via API)
        }, timeout=20)
        r.raise_for_status()
        data = r.json()
        if data.get('status') == 1:
            return data.get('id')
        else:
            log(f'  ⚠  add_device fallido para {nombre}: {data}')
            return None
    except Exception as e:
        log(f'  ❌ Error creando {nombre}: {e}')
        return None


def main():
    log('=' * 65)
    log(' MIGRACIÓN MASIVA — plataforma.sistemagps.online → 173.212.203.163')
    log('=' * 65)

    session = make_session()

    # 1. Login
    log('\n[1/4] Autenticando...')
    token_src = login(session, SRC_BASE, SRC_EMAIL, SRC_PASS)
    token_dst = login(session, DST_BASE, DST_EMAIL, DST_PASS)
    log('  Fuente  : OK')
    log('  Destino : OK')

    # 2. Leer fuente
    log('\n[2/4] Leyendo dispositivos de la fuente...')
    devs_src = obtener_dispositivos_fuente(session, token_src)
    log(f'  Total en fuente: {len(devs_src)}')

    # 3. Leer destino (existentes)
    log('\n[3/4] Leyendo dispositivos existentes en destino...')
    mapa_dst = obtener_dispositivos_destino(session, token_dst)
    log(f'  Total en destino: {len(mapa_dst)}')

    # Cargar backup previo si existe
    backup = {}
    try:
        with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
            backup = json.load(f)
        log(f'  Backup previo cargado: {len(backup)} registros')
    except FileNotFoundError:
        pass

    # Actualizar mapa con los ya existentes en destino
    for imei, dev_id in mapa_dst.items():
        if imei not in backup:
            backup[imei] = dev_id

    # Filtrar los que ya existen
    pendientes = [d for d in devs_src if d['imei'] not in backup]
    ya_existen = len(devs_src) - len(pendientes)

    log(f'  Ya migrados/existentes: {ya_existen}')
    log(f'  Por migrar ahora      : {len(pendientes)}')

    if not pendientes:
        log('\n✅ Todos los dispositivos ya están en el destino.')
        _guardar_backup(backup)
        return backup

    # 4. Crear en lotes paralelos
    log(f'\n[4/4] Creando {len(pendientes)} dispositivos (lotes de {MAX_PARALLEL})...')
    creados  = 0
    errores  = 0

    lotes = [pendientes[i:i + MAX_PARALLEL] for i in range(0, len(pendientes), MAX_PARALLEL)]

    for num_lote, lote in enumerate(lotes, 1):
        log(f'  Lote {num_lote}/{len(lotes)}  ({len(lote)} items)...')

        futures_map = {}
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as ex:
            for dev in lote:
                fut = ex.submit(crear_dispositivo, session, token_dst, dev['nombre'], dev['imei'])
                futures_map[fut] = dev

        for fut, dev in futures_map.items():
            new_id = fut.result()
            if new_id:
                backup[dev['imei']] = new_id
                creados += 1
                log(f'    ✅ {dev["nombre"]} (IMEI: {dev["imei"]}) → id={new_id}')
            else:
                errores += 1

        # Guardar progreso tras cada lote
        _guardar_backup(backup)
        time.sleep(PAUSA_LOTE)

        # Re-autenticar cada 50 lotes para evitar expiración de sesión
        if num_lote % 50 == 0:
            log('  🔁 Re-autenticando...')
            token_dst = login(session, DST_BASE, DST_EMAIL, DST_PASS)

    log('\n' + '=' * 65)
    log(f'RESUMEN MIGRACIÓN:')
    log(f'  Total fuente         : {len(devs_src)}')
    log(f'  Ya existían / mapeados: {ya_existen}')
    log(f'  Creados ahora        : {creados}')
    log(f'  Errores              : {errores}')
    log(f'  Mapa guardado en     : {BACKUP_FILE}')
    log('=' * 65)

    return backup


def _guardar_backup(backup):
    with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(backup, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
