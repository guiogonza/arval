"""
sync_diario.py
────────────────────────────────────────────────────────────────
Sincronización diaria automática GPS plataforma → GPSWox
Corre a la 01:00 AM GMT-5 (06:00 UTC) cada día.
INSERT directo en MySQL (gpswox_traccar.positions_N).

EJECUCIÓN:
  python sync_diario.py               → scheduler (loop infinito)
  python sync_diario.py --ahora       → ejecuta una vez (día anterior)
  python sync_diario.py --fecha 2026-05-10  → fecha específica
"""

import sys, os, time, threading, argparse
from datetime import datetime, timedelta, date, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "pymysql", "-q"], check=True)
    import pymysql
    import pymysql.cursors

# ─── CONFIG ──────────────────────────────────────────────────────────────────
SRC_BASE  = "https://plataforma.sistemagps.online/api"
SRC_EMAIL = os.getenv("PLATAFORMA_EMAIL",    "gerencia@rastrear.com.co")
SRC_PASS  = os.getenv("PLATAFORMA_PASSWORD", "")

DB_HOST    = "127.0.0.1"
DB_PORT    = 3306
DB_USER    = os.getenv("GPSWOX_DB_USER", "root")
DB_PASS    = os.getenv("GPSWOX_DB_PASSWORD", "")
DB_TRACCAR = "gpswox_traccar"
DB_WEB     = "gpswox_web"

HORA_UTC   = 6
MINUTO_UTC = 0

MAX_WORKERS   = 8
SRC_SEM_LIMIT = 4

LOG_FILE = "/root/sync_gps/sync_diario.log"

FRANJAS = [
    ("00:00", "05:59"),
    ("06:00", "11:59"),
    ("12:00", "17:59"),
    ("18:00", "23:59"),
]
# ─────────────────────────────────────────────────────────────────────────────

_src_sem = threading.Semaphore(SRC_SEM_LIMIT)


def make_session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=1.5)))
    s.mount("http://",  HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1)))
    return s


def log(msg: str, error: bool = False):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    # stdout ya va al log via redireccion crontab (no escribir doble)
    print(line, flush=True)


# ─── MYSQL ────────────────────────────────────────────────────────────────────

def _conn(db_name: str):
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
        database=db_name, charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor, autocommit=False,
        connect_timeout=10,
    )


def build_imei_map() -> dict:
    db = _conn(DB_WEB)
    mapa = {}
    try:
        with db.cursor() as cur:
            cur.execute("SELECT id, uniqueId FROM traccar_devices")
            for row in cur.fetchall():
                mapa[str(row[1]).strip()] = int(row[0])
    finally:
        db.close()
    return mapa


def ensure_table(traccar_id: int, db):
    tbl = f"positions_{traccar_id}"
    with db.cursor() as cur:
        cur.execute(f"SHOW TABLES LIKE '{tbl}'")
        exists = cur.fetchone()
        if not exists:
            cur.execute(f"""
            CREATE TABLE `{tbl}` (
              `id`             bigint unsigned NOT NULL AUTO_INCREMENT,
              `device_id`      bigint unsigned NOT NULL DEFAULT {traccar_id},
              `altitude`       double          DEFAULT NULL,
              `course`         double          DEFAULT NULL,
              `latitude`       double          DEFAULT NULL,
              `longitude`      double          DEFAULT NULL,
              `other`          text,
              `power`          double          DEFAULT NULL,
              `speed`          double          DEFAULT NULL,
              `time`           datetime        DEFAULT NULL,
              `device_time`    datetime        DEFAULT NULL,
              `server_time`    datetime        DEFAULT NULL,
              `sensors_values` text,
              `valid`          tinyint         DEFAULT NULL,
              `distance`       double          DEFAULT NULL,
              `protocol`       varchar(20)     DEFAULT NULL,
              PRIMARY KEY (`id`),
              KEY `device_id`  (`device_id`),
              KEY `time`       (`time`),
              KEY `server_time`(`server_time`),
              KEY `speed`      (`speed`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
        else:
            # Agregar columnas faltantes en tablas auto-creadas por Traccar
            cur.execute(f"SHOW COLUMNS FROM `{tbl}` LIKE 'device_id'")
            if not cur.fetchone():
                cur.execute(
                    f"ALTER TABLE `{tbl}` ADD COLUMN "
                    f"`device_id` bigint unsigned NOT NULL DEFAULT {traccar_id} AFTER `id`"
                )
            cur.execute(f"SHOW COLUMNS FROM `{tbl}` LIKE 'power'")
            if not cur.fetchone():
                cur.execute(
                    f"ALTER TABLE `{tbl}` ADD COLUMN "
                    f"`power` double DEFAULT NULL AFTER `other`"
                )
    db.commit()


def insertar_puntos(traccar_id: int, puntos: list, db) -> int:
    tbl = f"positions_{traccar_id}"
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        (
            traccar_id,
            p.get("altitude") or 0,
            p.get("course") or 0,
            p["lat"],
            p["lng"],
            p.get("other") or "",
            None,
            p.get("speed") or 0,
            p["time_utc"],
            p.get("device_time") or p["time_utc"],
            now,
            None,
            1 if p.get("valid", 1) else 0,
            p.get("distance") or 0,
            "plataforma",
        )
        for p in puntos
    ]
    with db.cursor() as cur:
        cur.executemany(
            f"""INSERT INTO `{tbl}`
            (device_id, altitude, course, latitude, longitude, other, power, speed,
             time, device_time, server_time, sensors_values, valid, distance, protocol)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            rows,
        )
    db.commit()
    return len(rows)


def actualizar_ultimo_pos(traccar_id: int, ultimo: dict, db_web):
    try:
        tbl = f"positions_{traccar_id}"
        with db_web.cursor() as cur:
            cur.execute("SELECT time, latest_positions FROM traccar_devices WHERE id = %s", (traccar_id,))
            row = cur.fetchone()
            cur_time = row[0] if row else None
            latest_positions_old = row[1] if row and len(row) > 1 else ""
            cur.execute(
                f"SELECT id, latitude, longitude, altitude, course, speed, time, device_time, server_time, protocol "
                f"FROM `{DB_TRACCAR}`.`{tbl}` ORDER BY time DESC, id DESC LIMIT 1"
            )
            pos = cur.fetchone()
        nuevo_time = datetime.strptime(ultimo["time_utc"], "%Y-%m-%d %H:%M:%S")
        if cur_time and isinstance(cur_time, datetime) and cur_time >= nuevo_time:
            return
        if pos:
            pos_id, lat, lng, altitude, course, speed, pos_time, device_time, server_time, protocol = pos
        else:
            pos_id = None
            lat, lng = ultimo["lat"], ultimo["lng"]
            altitude, course, speed = ultimo.get("altitude") or 0, ultimo.get("course") or 0, ultimo.get("speed") or 0
            pos_time = ultimo["time_utc"]
            device_time = ultimo.get("device_time") or ultimo["time_utc"]
            server_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            protocol = "plataforma"
        point = f"{float(lat):.6f}/{float(lng):.6f}"
        tail = [x for x in (latest_positions_old or "").split(";") if x]
        latest_positions = ";".join(([point] + tail)[:15])
        with db_web.cursor() as cur:
            cur.execute(
                "UPDATE traccar_devices "
                "SET latestPosition_id = %s, "
                "lastValidLatitude = %s, lastValidLongitude = %s, "
                "speed = %s, altitude = %s, course = %s, "
                "time = %s, device_time = %s, server_time = %s, "
                "protocol = %s, latest_positions = %s, updated_at = NOW() "
                "WHERE id = %s",
                (pos_id, lat, lng, speed or 0, altitude or 0, course or 0,
                 pos_time, device_time or pos_time, server_time, protocol or "plataforma",
                 latest_positions, traccar_id),
            )
        db_web.commit()
    except Exception as exc:
        log(f"  ⚠ latest traccar_device {traccar_id}: {exc}", error=True)


# ─── API PLATAFORMA ───────────────────────────────────────────────────────────

def api_login(s) -> str:
    r = s.post(f"{SRC_BASE}/login",
               json={"email": SRC_EMAIL, "password": SRC_PASS}, timeout=30)
    r.raise_for_status()
    return r.json()["user_api_hash"]


def get_devices(s, tok: str) -> list:
    r = s.post(f"{SRC_BASE}/get_devices", json={"user_api_hash": tok}, timeout=60)
    r.raise_for_status()
    out = []

    def _extract(obj):
        if isinstance(obj, list):
            for x in obj:
                _extract(x)
        elif isinstance(obj, dict):
            if "device_data" in obj:
                dd = obj.get("device_data") or {}
                imei = str(dd.get("imei") or "").strip()
                if imei:
                    out.append({"nombre": (obj.get("name") or imei).strip(),
                                "imei": imei, "device_id": obj.get("id")})
            if "items" in obj:
                _extract(obj["items"])

    _extract(r.json())
    return out


def parsear_puntos(data: dict) -> list:
    puntos = []
    vistos = set()
    for seg in (data.get("items") or []):
        for p in (seg.get("items") or []):
            lat = p.get("lat") or p.get("latitude") or 0
            lng = p.get("lng") or p.get("longitude") or 0
            if not lat or not lng:
                continue
            device_time_str = p.get("device_time") or ""
            raw_time_str    = p.get("raw_time") or ""
            if device_time_str:
                time_utc = device_time_str
            elif raw_time_str:
                try:
                    dt = datetime.strptime(raw_time_str, "%Y-%m-%d %H:%M:%S")
                    time_utc = (dt + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    time_utc = raw_time_str
            else:
                continue
            if time_utc in vistos:
                continue
            vistos.add(time_utc)
            puntos.append({
                "lat": lat, "lng": lng,
                "speed": p.get("speed") or 0, "altitude": p.get("altitude") or 0,
                "course": p.get("course") or 0, "time_utc": time_utc,
                "device_time": device_time_str or time_utc,
                "valid": p.get("valid", 1), "distance": p.get("distance") or 0,
                "other": p.get("other") or "",
            })
    return puntos


def obtener_historia_dia(s, tok: str, device_id: int, dia_str: str) -> list:
    puntos = []
    vistos = set()
    for from_t, to_t in FRANJAS:
        for intento in range(4):
            try:
                with _src_sem:
                    r = s.post(f"{SRC_BASE}/get_history", json={
                        "user_api_hash": tok, "device_id": device_id,
                        "from_date": dia_str, "to_date": dia_str,
                        "from_time": from_t, "to_time": to_t,
                    }, timeout=60)
                if r.status_code == 429:
                    time.sleep(int(r.headers.get("Retry-After", 20)))
                    continue
                r.raise_for_status()
                data = r.json()
                if data.get("status") == 1:
                    for p in parsear_puntos(data):
                        if p["time_utc"] not in vistos:
                            vistos.add(p["time_utc"])
                            puntos.append(p)
                break
            except Exception as exc:
                if intento == 3:
                    log(f"  ⚠ get_history dev={device_id} {dia_str} {from_t}: {exc}", error=True)
                time.sleep(2 ** (intento + 1))
        time.sleep(0.1)
    return puntos


# ─── WORKER ──────────────────────────────────────────────────────────────────

def procesar_device(args) -> tuple:
    nombre, imei, device_id, traccar_id, tok, dia_str = args
    s = make_session()
    puntos = obtener_historia_dia(s, tok, device_id, dia_str)
    if not puntos:
        return nombre, imei, 0
    db_t = _conn(DB_TRACCAR)
    db_w = _conn(DB_WEB)
    try:
        ensure_table(traccar_id, db_t)
        n = insertar_puntos(traccar_id, puntos, db_t)
        ultimo = max(puntos, key=lambda p: p["time_utc"])
        actualizar_ultimo_pos(traccar_id, ultimo, db_w)
        return nombre, imei, n
    except Exception as exc:
        log(f"  ❌ MySQL {nombre}: {exc}", error=True)
        try:
            db_t.rollback()
        except Exception:
            pass
        return nombre, imei, 0
    finally:
        db_t.close()
        db_w.close()


# ─── SYNC DE UN DÍA ──────────────────────────────────────────────────────────

def sync_dia(dia: date):
    fecha_str = dia.strftime("%Y-%m-%d")
    log(f"\n{'='*65}")
    log(f" SYNC DIARIO: {fecha_str}")
    log(f"{'='*65}")
    s = make_session()
    log("[Auth] Autenticando plataforma.sistemagps.online...")
    try:
        tok = api_login(s)
    except Exception as e:
        log(f"[Auth] ERROR: {e}", error=True)
        return
    log("  OK")
    log("[Devices] Obteniendo lista...")
    try:
        devices = get_devices(s, tok)
    except Exception as e:
        log(f"[Devices] ERROR: {e}", error=True)
        return
    log(f"  {len(devices)} dispositivos")
    log("[DB] Construyendo mapa IMEI → traccar_id...")
    imei_map = build_imei_map()
    log(f"  {len(imei_map)} traccar_devices en DB")
    trabajos = []
    for d in devices:
        tid = imei_map.get(d["imei"])
        if tid and d["device_id"]:
            trabajos.append((d["nombre"], d["imei"], d["device_id"], tid, tok, fecha_str))
    log(f"  {len(trabajos)} dispositivos a sincronizar\n")
    tot_pts = 0
    tot_ok  = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(procesar_device, t): t for t in trabajos}
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                nombre, imei, pts = fut.result()
                tot_pts += pts
                if pts > 0:
                    tot_ok += 1
                    log(f"  [{i}/{len(trabajos)}] {nombre}: {pts} pts")
            except Exception as exc:
                log(f"  ❌ worker error: {exc}", error=True)
    log(f"\nRESUMEN {fecha_str}: {tot_ok} devs | {tot_pts:,} pts insertados")


# ─── SCHEDULER ────────────────────────────────────────────────────────────────

def segundos_hasta_proxima():
    ahora_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    target = ahora_utc.replace(hour=HORA_UTC, minute=MINUTO_UTC, second=0, microsecond=0)
    if ahora_utc >= target:
        target += timedelta(days=1)
    return max(0, (target - ahora_utc).total_seconds())


def loop_scheduler():
    log("Scheduler iniciado — sync a las 01:00 AM GMT-5 (06:00 UTC) cada dia")
    while True:
        espera = segundos_hasta_proxima()
        proxima = datetime.now() + timedelta(seconds=espera)
        log(f"Proxima ejecucion: {proxima.strftime('%Y-%m-%d %H:%M:%S')} (en {espera/3600:.1f}h)")
        time.sleep(espera)
        ayer = (datetime.now(timezone.utc) - timedelta(hours=5)).date() - timedelta(days=1)
        try:
            sync_dia(ayer)
        except Exception as exc:
            log(f"ERROR en sync_dia: {exc}", error=True)
        time.sleep(60)


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync diario GPS -> MySQL GPSWox")
    parser.add_argument("--ahora", action="store_true",
                        help="Ejecutar sync del dia anterior inmediatamente")
    parser.add_argument("--fecha", type=str, metavar="YYYY-MM-DD",
                        help="Sincronizar una fecha especifica")
    args = parser.parse_args()
    if args.fecha:
        try:
            dia = datetime.strptime(args.fecha, "%Y-%m-%d").date()
        except ValueError:
            print("Formato invalido. Usa YYYY-MM-DD")
            sys.exit(1)
        sync_dia(dia)
    elif args.ahora:
        ayer = (datetime.now(timezone.utc) - timedelta(hours=5)).date() - timedelta(days=1)
        sync_dia(ayer)
    else:
        loop_scheduler()
