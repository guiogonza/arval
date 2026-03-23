import os
import time
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

GPSWOX_API_URL = os.getenv("GPSWOX_API_URL", "http://173.212.203.163/api")
GPSWOX_OSMAND_URL = os.getenv("GPSWOX_OSMAND_URL", "http://173.212.203.163:6055/")
GPSWOX_EMAIL = os.getenv("GPSWOX_EMAIL", "gerencia@rastrear.com.co")
GPSWOX_PASSWORD = os.getenv("GPSWOX_PASSWORD", "Colombias1*")

# Cache de dispositivos para no consultar la API en cada request
# devices: {nombre_upper: imei, ...}
_devices_cache = {"hash": None, "devices": {}, "ts": 0}
CACHE_TTL = 120  # segundos


def _gpswox_login():
    resp = requests.post(
        f"{GPSWOX_API_URL}/login",
        json={"email": GPSWOX_EMAIL, "password": GPSWOX_PASSWORD},
        timeout=10,
        allow_redirects=False,
    )
    resp.raise_for_status()
    data = resp.json()
    return (
        data.get("user_api_hash")
        or data.get("api_hash")
        or (data.get("user") or {}).get("api_hash")
    )


def _gpswox_get_device_names():
    now = time.time()
    if _devices_cache["devices"] and now - _devices_cache["ts"] < CACHE_TTL:
        return _devices_cache["hash"], _devices_cache["devices"]

    api_hash = _devices_cache["hash"] or _gpswox_login()
    resp = requests.post(
        f"{GPSWOX_API_URL}/get_devices",
        json={"user_api_hash": api_hash},
        timeout=10,
        allow_redirects=False,
    )
    resp.raise_for_status()
    devices = {}  # {nombre_upper: imei}
    for grupo in resp.json():
        for d in grupo.get("items", []):
            name = (d.get("name") or "").strip().upper()
            imei = (d.get("device_data", {}) or {}).get("imei", "") or ""
            if name:
                devices[name] = imei
    _devices_cache.update({"hash": api_hash, "devices": devices, "ts": now})
    return api_hash, devices


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/check_placa", methods=["POST"])
def check_placa():
    data = request.get_json(silent=True)
    placa = (data.get("placa") or "").strip().upper() if data else ""
    if not placa:
        return jsonify({"error": "placa requerida"}), 400
    try:
        _, devices = _gpswox_get_device_names()
        exists = placa in devices
        imei = devices.get(placa, "")
        return jsonify({"exists": exists, "placa": placa, "imei": imei})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/transmit", methods=["POST"])
def transmit():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON requerido"}), 400

    placa = (data.get("placa") or "").strip().upper()
    device_id = (data.get("device_id") or placa).strip()
    lat = data.get("lat")
    lon = data.get("lon")
    speed_kmh = data.get("speed", 0) or 0
    accuracy = data.get("accuracy")
    heading = data.get("heading")

    if not placa or lat is None or lon is None:
        return jsonify({"error": "placa, lat y lon son obligatorios"}), 400

    speed_knots = float(speed_kmh) / 1.852
    ts = int(time.time())

    params = {
        "id": device_id,
        "lat": lat,
        "lon": lon,
        "speed": round(speed_knots, 2),
        "timestamp": ts,
        "motion": "true" if speed_kmh > 0 else "false",
    }
    if accuracy is not None:
        params["accuracy"] = accuracy
    if heading is not None:
        params["bearing"] = heading

    try:
        resp = requests.get(GPSWOX_OSMAND_URL, params=params, timeout=10)
        return jsonify({
            "ok": resp.status_code == 200,
            "status": resp.status_code,
            "placa": placa,
            "lat": lat,
            "lon": lon,
            "speed_kmh": speed_kmh,
        })
    except requests.RequestException as e:
        return jsonify({"ok": False, "error": str(e)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5051, debug=True)
