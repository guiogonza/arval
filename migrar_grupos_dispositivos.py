"""
FASE 1 — Migrar grupos y dispositivos
  Fuente  : https://plataforma.sistemagps.online  (809 objetos, 70 grupos)
  Destino : http://173.212.203.163

ENDPOINTS CONFIRMADOS:
  POST /api/devices_groups/store   → crea un grupo
  GET  /api/devices_groups         → lista grupos existentes
  POST /api/add_device             → crea dispositivo (acepta group_id)
  POST /api/get_devices            → lista todos los dispositivos
"""

import requests
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime

# ─── CONFIG ──────────────────────────────────────────────────────────────────
SRC_BASE  = 'https://plataforma.sistemagps.online/api'
DST_BASE  = 'http://173.212.203.163/api'
SRC_EMAIL = 'gerencia@rastrear.com.co'
SRC_PASS  = 'a791025*'
DST_EMAIL = 'gerencia@rastrear.com.co'
DST_PASS  = 'Colombias1*'
MAP_FILE  = 'migracion_mapa.json'   # {imei: dst_device_id, '_grupos': {nombre: dst_group_id}}
MAX_PAR   = 5      # solicitudes paralelas
PAUSA     = 0.3    # seg entre requests
# Usuarios que tendrán acceso a TODOS los dispositivos
USER_IDS_ACCESO = [3, 1]   # gerencia@rastrear.com.co=3, guiogonza@gmail.com=1
# ─────────────────────────────────────────────────────────────────────────────


def make_session():
    s = requests.Session()
    s.mount('http://',  HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1)))
    s.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1)))
    return s


def login(session, base, email, pw):
    r = session.post(base + '/login', json={'email': email, 'password': pw}, timeout=30)
    r.raise_for_status()
    d = r.json()
    if d.get('status') != 1:
        raise ValueError(f'Login fallido: {d}')
    return d['user_api_hash']


def log(msg):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}')


# ─── GRUPOS ──────────────────────────────────────────────────────────────────

def leer_grupos_fuente(session, token):
    """Devuelve {nombre_grupo: [dispositivos]} del fuente."""
    r = session.post(SRC_BASE + '/get_devices', json={'user_api_hash': token}, timeout=60)
    r.raise_for_status()
    resultado = {}
    for g in r.json():
        nombre = (g.get('title') or g.get('name') or 'Sin grupo').strip()
        resultado[nombre] = g.get('items', [])
    return resultado


def leer_grupos_destino(session, token):
    """Devuelve {nombre_grupo: group_id} del destino."""
    r = session.get(DST_BASE + '/devices_groups', params={'user_api_hash': token}, timeout=30)
    r.raise_for_status()
    data = r.json()
    mapa = {}
    for v in data.values() if isinstance(data, dict) else data:
        titulo = (v.get('title') or '').strip()
        gid = v.get('id')
        if titulo and gid:
            mapa[titulo] = gid
    # Sin grupo → siempre id=0
    mapa['Sin grupo'] = 0
    return mapa


def crear_grupo_destino(session, token, nombre):
    """Crea un grupo en el destino. Devuelve id o None."""
    time.sleep(PAUSA)
    try:
        r = session.post(DST_BASE + '/devices_groups/store',
                         json={'user_api_hash': token, 'title': nombre}, timeout=15)
        r.raise_for_status()
        data = r.json()
        # Respuesta confirmada: {"status":1, "id": <nuevo_id>}
        if data.get('status') == 1:
            return data.get('id')
        return None
    except Exception as e:
        log(f'  ⚠ Error creando grupo "{nombre}": {e}')
        return None


def sincronizar_grupos(session, token_src, token_dst, grupos_src):
    """Crea en destino los grupos que faltan. Devuelve {nombre: group_id}."""
    log('\n[Grupos] Sincronizando grupos...')
    grupos_dst = leer_grupos_destino(session, token_dst)
    log(f'  Fuente : {len(grupos_src)} grupos')
    log(f'  Destino: {len(grupos_dst)} grupos existentes')

    mapa = dict(grupos_dst)
    creados = 0
    for nombre in grupos_src.keys():
        if nombre in mapa:
            log(f'  ✓ ya existe: {nombre} (id={mapa[nombre]})')
            continue
        # Crear
        new_id = crear_grupo_destino(session, token_dst, nombre)
        if new_id:
            mapa[nombre] = new_id
            log(f'  ✅ creado: {nombre} → id={new_id}')
            creados += 1
        else:
            # Si no devuelve id, releer grupos para ver si se creó
            grupos_dst2 = leer_grupos_destino(session, token_dst)
            if nombre in grupos_dst2:
                mapa[nombre] = grupos_dst2[nombre]
                log(f'  ✅ creado (relect): {nombre} → id={mapa[nombre]}')
                creados += 1
            else:
                log(f'  ❌ no se pudo crear: {nombre} → asignado a Sin grupo (0)')
                mapa[nombre] = 0

    log(f'  → {creados} grupos nuevos creados')
    return mapa


# ─── DISPOSITIVOS ─────────────────────────────────────────────────────────────

def leer_dispositivos_destino(session, token):
    """Devuelve {imei: device_id} de lo que ya hay en destino."""
    r = session.post(DST_BASE + '/get_devices', json={'user_api_hash': token}, timeout=60)
    r.raise_for_status()
    mapa = {}
    for g in r.json():
        for d in g.get('items', []):
            dd = d.get('device_data') or {}
            # Leer IMEI de todos los campos posibles
            imei = (
                str(dd.get('imei') or '').strip() or
                str(d.get('imei') or '').strip() or
                str(dd.get('uniqueId') or '').strip() or
                str(d.get('uniqueId') or '').strip()
            )
            did = d.get('id')
            if imei and did:
                mapa[imei] = did
    return mapa


def crear_dispositivo(session, token, nombre, imei, group_id):
    """Crea dispositivo en el destino y asigna acceso a ambos usuarios. Devuelve id o None."""
    time.sleep(PAUSA)
    try:
        r = session.post(DST_BASE + '/add_device', json={
            'user_api_hash': token,
            'name'         : nombre,
            'imei'         : imei,
            'protocol'     : 'osmand',
            'group_id'     : group_id,
        }, timeout=20)
        data = r.json()

        # IMEI ya existe → reutilizar el device existente
        if r.status_code == 400 and 'IMEI' in data.get('message', '') and 'tomado' in data.get('message', ''):
            dev_id = _buscar_device_por_imei(session, token, imei)
            if dev_id:
                _asignar_usuarios(session, token, dev_id)
                return dev_id
            return None

        r.raise_for_status()
        if data.get('status') == 1:
            dev_id = data.get('id')
            _asignar_usuarios(session, token, dev_id)
            return dev_id
        log(f'  ⚠ add_device {nombre}: {data}')
        return None
    except Exception as e:
        log(f'  ❌ Error creando {nombre}: {e}')
        return None


# Cache de dispositivos destino para lookup por IMEI
_cache_dst = {}

def _buscar_device_por_imei(session, token, imei):
    """Busca el device_id en destino cuyo IMEI coincide."""
    global _cache_dst
    if not _cache_dst:
        _cache_dst = leer_dispositivos_destino(session, token)
    return _cache_dst.get(str(imei).strip())


def _asignar_usuarios(session, token, device_id):
    """Asigna USER_IDS_ACCESO al dispositivo vía edit_device."""
    try:
        session.post(DST_BASE + '/edit_device', json={
            'user_api_hash': token,
            'device_id'    : device_id,
            'user_id'      : USER_IDS_ACCESO,
        }, timeout=15)
    except Exception as e:
        log(f'    ⚠ No se pudo asignar usuarios a device {device_id}: {e}')


def sincronizar_dispositivos(session, token_dst, grupos_src, mapa_grupos, mapa_existentes):
    """Crea los dispositivos que faltan en destino. Devuelve {imei: dst_id}."""
    log('\n[Dispositivos] Sincronizando dispositivos...')

    # Construir lista de pendientes
    pendientes = []
    for grupo_nombre, items in grupos_src.items():
        group_id = mapa_grupos.get(grupo_nombre, 0)
        for d in items:
            dd = d.get('device_data') or {}
            imei = str(dd.get('imei') or '').strip()
            nombre = (d.get('name') or '').strip()
            if not imei or not nombre:
                continue
            if imei not in mapa_existentes:
                pendientes.append((nombre, imei, group_id))

    log(f'  Ya en destino: {len(mapa_existentes)}')
    log(f'  Por crear    : {len(pendientes)}')

    mapa_final = dict(mapa_existentes)
    creados = 0
    errores = 0

    lotes = [pendientes[i:i+MAX_PAR] for i in range(0, len(pendientes), MAX_PAR)]
    for num, lote in enumerate(lotes, 1):
        log(f'  Lote {num}/{len(lotes)} ({len(lote)} items)...')
        futures = {}
        with ThreadPoolExecutor(max_workers=MAX_PAR) as ex:
            for nombre, imei, gid in lote:
                fut = ex.submit(crear_dispositivo, session, token_dst, nombre, imei, gid)
                futures[fut] = (nombre, imei)

        for fut, (nombre, imei) in futures.items():
            new_id = fut.result()
            if new_id:
                mapa_final[imei] = new_id
                creados += 1
                log(f'    ✅ {nombre} (IMEI:{imei}) → id={new_id}')
            else:
                errores += 1

        time.sleep(0.5)  # pausa entre lotes

        # Re-autenticar cada 60 lotes
        if num % 60 == 0:
            log('  🔁 Re-autenticando...')
            token_dst = login(session, DST_BASE, DST_EMAIL, DST_PASS)

    log(f'  → {creados} creados | {errores} errores')
    return mapa_final


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    log('=' * 65)
    log(' FASE 1: Migración grupos + dispositivos')
    log(' Fuente : plataforma.sistemagps.online')
    log(' Destino: 173.212.203.163')
    log('=' * 65)

    # Cargar mapa previo si existe
    mapa = {'_grupos': {}}
    try:
        with open(MAP_FILE, 'r', encoding='utf-8') as f:
            mapa = json.load(f)
        log(f'\nMapa previo cargado: {len(mapa)-1} IMEIs mapeados')
    except FileNotFoundError:
        pass

    session = make_session()

    log('\n[Auth] Autenticando...')
    token_src = login(session, SRC_BASE, SRC_EMAIL, SRC_PASS)
    token_dst = login(session, DST_BASE, DST_EMAIL, DST_PASS)
    log('  OK')

    # 1. Leer fuente organizada por grupos
    log('\n[Fuente] Leyendo grupos y dispositivos...')
    grupos_src = leer_grupos_fuente(session, token_src)
    total_devs = sum(len(v) for v in grupos_src.values())
    log(f'  {len(grupos_src)} grupos | {total_devs} dispositivos')

    # 2. Sincronizar grupos
    mapa_grupos = sincronizar_grupos(session, token_src, token_dst, grupos_src)
    mapa['_grupos'] = mapa_grupos
    _guardar(mapa)

    # 3. Leer existentes en destino
    log('\n[Destino] Leyendo dispositivos existentes...')
    mapa_existentes = leer_dispositivos_destino(session, token_dst)
    log(f'  {len(mapa_existentes)} dispositivos ya en destino')
    # Complementar con mapa guardado
    for imei, did in mapa.items():
        if imei != '_grupos' and imei not in mapa_existentes:
            mapa_existentes[imei] = did

    # 4. Sincronizar dispositivos
    mapa_final = sincronizar_dispositivos(session, token_dst, grupos_src, mapa_grupos, mapa_existentes)

    # Actualizar mapa
    for k, v in mapa_final.items():
        mapa[k] = v
    _guardar(mapa)

    # 5. Asignar usuarios a dispositivos ya existentes que aún no tienen acceso
    log('\n[Usuarios] Asignando acceso a dispositivos existentes...')
    token_dst = login(session, DST_BASE, DST_EMAIL, DST_PASS)
    asignados = 0
    for imei, dev_id in mapa_existentes.items():
        _asignar_usuarios(session, token_dst, dev_id)
        asignados += 1
        if asignados % 50 == 0:
            log(f'  ... {asignados} procesados')
            token_dst = login(session, DST_BASE, DST_EMAIL, DST_PASS)
            time.sleep(0.5)
    log(f'  → {asignados} dispositivos con acceso asignado')

    log('\n' + '=' * 65)
    log('RESUMEN:')
    log(f'  Grupos en destino    : {len(mapa_grupos)}')
    log(f'  Dispositivos mapeados: {len(mapa)-1}')
    log(f'  Usuarios con acceso  : gerencia@rastrear.com.co (id=3), guiogonza@gmail.com (id=1)')
    log(f'  Guardado en          : {MAP_FILE}')
    log('=' * 65)


def _guardar(mapa):
    with open(MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(mapa, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
