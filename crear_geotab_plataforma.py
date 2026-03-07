"""
Crea en plataforma.sistemagps.online todas las placas de Geotab
en el grupo 'Geotab' (id=7444) y restringe el acceso a solo 2 usuarios.
"""
import os, time, requests, mygeotab
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

PLATAFORMA_BASE  = "https://plataforma.sistemagps.online/api"
PLATAFORMA_EMAIL = "gerencia@rastrear.com.co"
PLATAFORMA_PASS  = "a791025*"
GRUPO_GEOTAB_ID  = 7444          # grupo "Geotab" en plataforma
USUARIOS_OK      = [14682, 17234] # gerencia@rastrear.com.co, guiogonza@gmail.com

def make_session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=1)))
    return s

# ---------- 1. Login plataforma ----------
session = make_session()
r = session.post(f"{PLATAFORMA_BASE}/login",
                 json={"email": PLATAFORMA_EMAIL, "password": PLATAFORMA_PASS}, timeout=30)
token = r.json()["user_api_hash"]
print(f"✅ Plataforma autenticada | hash: {token[:12]}...")

# ---------- 2. Dispositivos ya existentes en plataforma ----------
r2 = session.post(f"{PLATAFORMA_BASE}/get_devices", json={"user_api_hash": token}, timeout=60)
existentes = {}  # {nombre_normalizado: {id, imei}}
for g in r2.json():
    for d in g.get("items", []):
        nombre = d.get("name", "").strip().upper()
        dd = d.get("device_data", {})
        existentes[nombre] = {"id": d["id"], "imei": dd.get("imei", "")}

print(f"   Dispositivos en plataforma actualmente: {len(existentes)}")

# ---------- 3. Obtener placas de Geotab ----------
print("\n🔌 Conectando a Geotab...")
client = mygeotab.API(
    username=os.getenv("GEOTAB_USERNAME", "cgutierrez@hesegoingenieria.com"),
    password=os.getenv("GEOTAB_PASSWORD", "Telematics"),
    database=os.getenv("GEOTAB_DATABASE", "Arval_col"),
)
client.authenticate()
devices_geo = client.get("Device")
print(f"✅ Geotab: {len(devices_geo)} dispositivos")

# ---------- 4. Crear / actualizar en plataforma ----------
creados    = 0
existia    = 0
errores    = 0

for dev in devices_geo:
    placa = dev.get("name", "").strip()
    imei  = dev.get("serialNumber", "").strip()

    if not placa or not imei:
        continue

    placa_key = placa.upper()

    if placa_key in existentes:
        existia += 1
        print(f"   ⏩ Ya existe: {placa}")
        continue

    try:
        r3 = session.post(f"{PLATAFORMA_BASE}/add_device", json={
            "user_api_hash": token,
            "name":          placa,
            "imei":          imei,
            "protocol":      "osmand",
            "group_id":      GRUPO_GEOTAB_ID,
            "users":         USUARIOS_OK,
        }, timeout=30)
        resp = r3.json()
        if resp.get("status") == 1:
            new_id = resp.get("id")
            creados += 1
            print(f"   ✅ Creado: {placa} (IMEI:{imei}) → id={new_id}")
        else:
            errores += 1
            print(f"   ❌ Error creando {placa}: {r3.text[:120]}")
    except Exception as e:
        errores += 1
        print(f"   ❌ Excepción {placa}: {e}")

    time.sleep(0.3)

print(f"\n{'='*50}")
print(f"  Creados  : {creados}")
print(f"  Ya existían: {existia}")
print(f"  Errores  : {errores}")
print(f"{'='*50}")
