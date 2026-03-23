"""
Actualiza la fecha de vencimiento de todos los dispositivos del grupo Geotab
en plataforma.sistemagps.online a una fecha lejana (2030-01-01).
"""
import requests, time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PLATAFORMA_BASE  = "https://plataforma.sistemagps.online/api"
PLATAFORMA_EMAIL = "gerencia@rastrear.com.co"
PLATAFORMA_PASS  = "a791025*"
GRUPO_GEOTAB_ID  = 7444
NUEVA_FECHA      = "2030-01-01 00:00:00"

def make_session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=1)))
    return s

# 1. Login
session = make_session()
r = session.post(f"{PLATAFORMA_BASE}/login",
                 json={"email": PLATAFORMA_EMAIL, "password": PLATAFORMA_PASS}, timeout=30)
token = r.json()["user_api_hash"]
print(f"Autenticado | hash: {token[:12]}...")

# 2. Obtener dispositivos del grupo Geotab
r2 = session.post(f"{PLATAFORMA_BASE}/get_devices", json={"user_api_hash": token}, timeout=60)
dispositivos = []
for g in r2.json():
    if g.get("group_id") == GRUPO_GEOTAB_ID or str(g.get("id")) == str(GRUPO_GEOTAB_ID):
        for d in g.get("items", []):
            dispositivos.append(d)

# Fallback: buscar por nombre del grupo
if not dispositivos:
    for g in r2.json():
        if "geotab" in g.get("name", "").lower():
            for d in g.get("items", []):
                dispositivos.append(d)

print(f"Dispositivos encontrados en grupo Geotab: {len(dispositivos)}")

if not dispositivos:
    print("No se encontraron dispositivos. Verificar grupo.")
    exit(1)

# 3. Probar primero con un solo dispositivo para verificar el parametro correcto
primer = dispositivos[0]
print(f"\nProbando con: {primer['name']} (id={primer['id']})")

# Intentar con 'expiration_date'
r_test = session.post(f"{PLATAFORMA_BASE}/edit_device", json={
    "user_api_hash": token,
    "id": primer["id"],
    "expiration_date": NUEVA_FECHA,
}, timeout=30)
resp_test = r_test.json()
print(f"  Respuesta con 'expiration_date': {resp_test}")

# Si falla intentar con 'billing_date'
if resp_test.get("status") != 1:
    r_test2 = session.post(f"{PLATAFORMA_BASE}/edit_device", json={
        "user_api_hash": token,
        "id": primer["id"],
        "billing_date": NUEVA_FECHA,
    }, timeout=30)
    resp_test2 = r_test2.json()
    print(f"  Respuesta con 'billing_date': {resp_test2}")

# 4. Verificar resultado en edit_device_data
r_check = session.get(f"{PLATAFORMA_BASE}/edit_device_data",
                      params={"user_api_hash": token, "device_id": primer["id"]}, timeout=30)
data_check = r_check.json()
print(f"  Datos actuales del dispositivo:")
for k, v in data_check.items():
    if "expir" in k.lower() or "billing" in k.lower() or "date" in k.lower() or "venc" in k.lower():
        print(f"    {k}: {v}")

print("\n--- Si ves la fecha correcta arriba, ejecuta de nuevo con UPDATE_ALL=True ---")
print("    Cambia UPDATE_ALL = False -> True al final del script")

UPDATE_ALL = True  # Cambiar a True para actualizar todos

if not UPDATE_ALL:
    exit(0)

# 5. Actualizar todos
print(f"\nActualizando {len(dispositivos)} dispositivos a vencimiento {NUEVA_FECHA}...")
ok = 0
errores = 0

for i, dev in enumerate(dispositivos, 1):
    dev_id   = dev["id"]
    dev_name = dev.get("name", "")
    try:
        r3 = session.post(f"{PLATAFORMA_BASE}/edit_device", json={
            "user_api_hash":  token,
            "id":             dev_id,
            "expiration_date": NUEVA_FECHA,
        }, timeout=30)
        resp = r3.json()
        if resp.get("status") == 1:
            ok += 1
            print(f"  [{i}/{len(dispositivos)}] OK: {dev_name}")
        else:
            errores += 1
            print(f"  [{i}/{len(dispositivos)}] ERROR {dev_name}: {r3.text[:100]}")
    except Exception as e:
        errores += 1
        print(f"  [{i}/{len(dispositivos)}] EXCEPCION {dev_name}: {e}")
    time.sleep(0.2)

print(f"\n{'='*50}")
print(f"  OK      : {ok}")
print(f"  Errores : {errores}")
print(f"{'='*50}")
