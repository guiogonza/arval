import requests, time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def make_session():
    s = requests.Session()
    s.mount('https://', HTTPAdapter(max_retries=Retry(total=5, backoff_factor=1)))
    return s

BASE = 'https://plataforma.sistemagps.online/api'
session = make_session()

r = session.post(f'{BASE}/login', json={'email':'gerencia@rastrear.com.co','password':'a791025*'}, timeout=30)
token = r.json()['user_api_hash']

# Solo estos 2 usuarios pueden ver las placas arval
USUARIOS_ARVAL = [14682, 17234]  # gerencia@rastrear.com.co, guiogonza@gmail.com

# Verificar primero con NFV765
r2 = session.post(f'{BASE}/get_devices', json={'user_api_hash': token}, timeout=60)
for g in r2.json():
    for d in g.get('items', []):
        if d.get('id') == 35498:
            users = d.get('device_data', {}).get('users', [])
            print(f'NFV765 tiene {len(users)} usuarios:')
            for u in users:
                uid = u['id']
                email = u['email']
                print(f'  {uid} - {email}')

print()

# Aplicar a todos los dispositivos con " arval" en el nombre
ok = 0
for g in r2.json():
    for d in g.get('items', []):
        nombre = d.get('name', '')
        if ' arval' in nombre.lower():
            imei = d.get('device_data', {}).get('imei', '')
            try:
                r3 = session.post(f'{BASE}/edit_device', json={
                    'user_api_hash': token,
                    'id': d['id'],
                    'name': nombre,
                    'imei': imei,
                    'users': USUARIOS_ARVAL
                }, timeout=30)
                if r3.json().get('status') == 1:
                    ok += 1
                    print(f'OK: {nombre}')
                else:
                    print(f'ERROR {nombre}: {r3.text}')
            except Exception as e:
                print(f'EXCEPCION {nombre}: {e}')
                time.sleep(2)
            time.sleep(0.2)

print(f'\nListo: {ok} dispositivos restringidos a solo 2 usuarios')
