import requests, mygeotab
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def make_session():
    s = requests.Session()
    s.mount('https://', HTTPAdapter(max_retries=Retry(total=5, backoff_factor=1)))
    return s

# 1. Obtener placas de Geotab
print('Obteniendo placas de Geotab...')
api = mygeotab.API('cgutierrez@hesegoingenieria.com', 'Telematics', 'Arval_col')
api.authenticate()
geotab_devs = api.get('Device', resultsLimit=200)
geotab_placas = set()
for d in geotab_devs:
    nombre = d.get('name', '').strip().upper().replace('-', '').replace(' ', '')
    if nombre:
        geotab_placas.add(nombre)
print(f'Geotab: {len(geotab_placas)} placas')

# 2. Login plataforma
BASE = 'https://plataforma.sistemagps.online/api'
session = make_session()
r = session.post(f'{BASE}/login', json={'email':'gerencia@rastrear.com.co','password':'a791025*'}, timeout=30)
token = r.json()['user_api_hash']

# 3. Obtener dispositivos de plataforma
r2 = session.post(f'{BASE}/get_devices', json={'user_api_hash': token}, timeout=60)

ok = 0
ya_tiene = 0
no_match = 0

for g in r2.json():
    for d in g.get('items', []):
        nombre = d.get('name', '').strip()
        # Normalizar para comparar (quitar espacios, guiones, mayúsculas, y sufijo " arval" si ya existe)
        nombre_limpio = nombre.upper().replace('-', '').replace(' ', '').replace('ARVAL', '').strip()
        # Tomar solo los primeros 6 chars (la placa base)
        placa_base = nombre_limpio[:6]

        if placa_base in geotab_placas:
            # Ya tiene arval?
            if nombre.endswith(' arval'):
                ya_tiene += 1
                continue
            nuevo = nombre + ' arval'
            imei = d.get('device_data', {}).get('imei', '')
            try:
                r3 = session.post(f'{BASE}/edit_device', json={
                    'user_api_hash': token,
                    'id': d['id'],
                    'name': nuevo,
                    'imei': imei
                }, timeout=30)
                if r3.json().get('status') == 1:
                    ok += 1
                    print(f'OK: {nombre} -> {nuevo}')
                else:
                    print(f'ERROR: {nombre}: {r3.text}')
            except Exception as e:
                print(f'EXCEPCION {nombre}: {e}')
        else:
            no_match += 1

print(f'\nListo: {ok} renombrados | {ya_tiene} ya tenian arval | {no_match} sin coincidencia Geotab')
