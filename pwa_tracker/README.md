# GPS Tracker PWA → GPSWox

App web progresiva (PWA) que transmite la ubicación GPS del teléfono en tiempo real a la plataforma GPSWox/Traccar vía protocolo OsmAnd.

## Estructura

```
pwa_tracker/
├── app.py              # Backend Flask (check_placa, transmit)
├── Dockerfile          # Python 3.12-slim + gunicorn
├── requirements.txt    # flask, requests, gunicorn
├── README.md
├── static/
│   ├── manifest.json   # Manifiesto PWA
│   ├── sw.js           # Service Worker (cache offline)
│   ├── icon-192.png
│   └── icon-512.png
└── templates/
    └── index.html      # Frontend completo (HTML/CSS/JS)
```

## Cómo funciona

1. El usuario ingresa la **placa** del vehículo
2. Se valida contra GPSWox API (`/api/check_placa`) y se obtiene el **IMEI** del dispositivo
3. Al activar transmisión, el navegador obtiene GPS vía `watchPosition`
4. Cada X segundos (configurable: 5s, 10s, 30s, 1m), envía coordenadas al backend
5. El backend reenvía a GPSWox vía protocolo **OsmAnd HTTP** (puerto 6055), usando el IMEI como identificador

## Características

- **PWA instalable**: botón de instalación + detección automática si ya está instalada
- **Filtro de distancia**: solo envía si el dispositivo se movió >50m
- **Cola offline**: si no hay red, guarda puntos en localStorage (hasta 500). Los reenvía automáticamente al recuperar conexión
- **Wake Lock**: mantiene la pantalla activa para que el GPS no se detenga en segundo plano
- **Notificación persistente**: en Android, mantiene la app activa cuando está minimizada
- **Geocodificación inversa**: muestra ciudad y dirección actual (Nominatim/OSM)
- **Mapa en vivo**: mini mapa Leaflet con icono 🚗
- **Log en tiempo real**: registro de envíos, errores y eventos

## Servidor destino

| Componente | URL |
|---|---|
| GPSWox API | `http://173.212.203.163/api` |
| OsmAnd (envío GPS) | `http://173.212.203.163:6055/` |

## Variables de entorno

| Variable | Descripción | Default |
|---|---|---|
| `GPSWOX_API_URL` | URL base de la API GPSWox | `http://173.212.203.163/api` |
| `GPSWOX_OSMAND_URL` | Endpoint OsmAnd HTTP | `http://173.212.203.163:6055/` |
| `GPSWOX_EMAIL` | Email para login API | `gerencia@rastrear.com.co` |
| `GPSWOX_PASSWORD` | Password para login API | `Colombias1*` |

## Docker

La app corre como servicio en `docker-compose.yml` del proyecto principal:

```yaml
pwa_tracker:
  build: ./pwa_tracker
  ports:
    - "5051:5050"
  restart: unless-stopped
  environment:
    - GPSWOX_API_URL=http://173.212.203.163/api
    - GPSWOX_OSMAND_URL=http://173.212.203.163:6055/
```

```bash
# Construir y levantar
docker compose up -d --build pwa_tracker

# Ver logs
docker logs -f pwa_tracker
```

## Desarrollo local

```bash
cd pwa_tracker
pip install -r requirements.txt
python app.py
# → http://localhost:5051
```

## API Endpoints

### `POST /api/check_placa`
Valida que la placa exista en GPSWox y retorna su IMEI.

```json
// Request
{ "placa": "IDO264" }

// Response
{ "exists": true, "placa": "IDO264", "imei": "351510091416647" }
```

### `POST /api/transmit`
Envía coordenadas GPS al servidor GPSWox vía OsmAnd.

```json
// Request
{
  "placa": "IDO264",
  "device_id": "351510091416647",
  "lat": 3.344289,
  "lon": -76.515183,
  "speed": 45.2,
  "accuracy": 8.5,
  "heading": 180.0
}

// Response
{ "ok": true, "status": 200, "placa": "IDO264", "lat": 3.344289, "lon": -76.515183, "speed_kmh": 45.2 }
```

## Notas

- El dispositivo en GPSWox debe tener `valid_by_avg_speed` desactivado para aceptar posiciones desde ubicaciones lejanas
- En iOS/Safari el GPS se pausa al minimizar — limitación de Apple
- En Android/Chrome funciona en segundo plano con Wake Lock + notificación activa
- La cache de dispositivos se refresca cada 120 segundos
