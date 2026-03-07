import requests, re, time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def make_session():
    s = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[500,502,503,504])
    s.mount('https://', HTTPAdapter(max_retries=retry))
    return s

BASE = 'https://plataforma.sistemagps.online/api'
session = make_session()

r = session.post(f'{BASE}/login', json={'email':'gerencia@rastrear.com.co','password':'a791025*'}, timeout=30)
token = r.json()['user_api_hash']

r2 = session.post(f'{BASE}/get_devices', json={'user_api_hash': token}, timeout=60)

ok = 0
err = 0
for g in r2.json():
    for d in g.get('items', []):
        nombre = d.get('name', '')
        if re.search(r'[A-Z]{3}-[A-Z0-9]{2,4}', nombre):
            nuevo = re.sub(r'([A-Z]{3})-([A-Z0-9]{2,4})', r'\1\2', nombre)
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
                    err += 1
                    print(f'ERROR ID={d["id"]} {nombre}: {r3.text}')
            except Exception as e:
                err += 1
                print(f'EXCEPCION ID={d["id"]} {nombre}: {e}')
                time.sleep(3)
            time.sleep(0.2)

print(f'\nListo: {ok} renombrados | {err} errores')
