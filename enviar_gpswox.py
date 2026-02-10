"""
Script para enviar recorrido GPS de Geotab a GPSWox
Obtiene el historial GPS de un vehículo desde Geotab y lo envía
al servidor GPSWox/Traccar usando protocolo OsmAnd (HTTP, puerto 6055)
Optimizado: envío paralelo con aiohttp (20 conexiones simultáneas)
Incluye datos de sensores: ignición, odómetro, combustible, voltaje, RPM, temperatura
"""
import os
import asyncio
import aiohttp
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from bisect import bisect_right
from dotenv import load_dotenv
import mygeotab

load_dotenv()

# ============ CONFIGURACIÓN ============
GPSWOX_HOST = "213.199.45.139"
OSMAND_PORT = 6055          # Puerto OsmAnd (HTTP)
PLACA = "NFV759"
FECHA_INICIO = "2026-02-10"  # Desde último dato cargado
FECHA_FIN = "2026-02-10"
# Último timestamp cargado en GPSWox (para no enviar duplicados)
ULTIMO_ENVIADO = "2026-02-10T21:09:53"  # positions_68 id=66739

# Diagnósticos de Geotab que queremos enviar como sensores a GPSWox
# Los nombres de parámetro OsmAnd se convierten a lowercase en el XML de Traccar
DIAGNOSTICOS_SENSORES = {
    'DiagnosticIgnitionId':                 'ignition',      # Motor ON/OFF (true/false)
    'DiagnosticOdometerId':                 'totalDistance',  # Odómetro (metros) → XML: totaldistance
    'DiagnosticFuelLevelId':                'fuel',           # Combustible (%)
    'DiagnosticGoDeviceVoltageId':          'power',          # Voltaje batería (V)
    'DiagnosticEngineSpeedId':              'rpm',            # RPM motor
    'DiagnosticEngineCoolantTemperatureId': 'coolantTemp',    # Temp refrigerante → XML: coolanttemp
    'DiagnosticOutsideTemperatureId':       'driverTemp',     # Temp exterior → XML: drivertemp
    'DiagnosticDriverSeatbeltId':           'seatbelt',       # Cinturón (0/1)
}
# =======================================


def get_geotab_client():
    """Conecta a Geotab API"""
    client = mygeotab.API(
        username=os.getenv('GEOTAB_USERNAME'),
        password=os.getenv('GEOTAB_PASSWORD'),
        database=os.getenv('GEOTAB_DATABASE')
    )
    client.authenticate()
    return client


def obtener_recorrido(client, placa, fecha_inicio, fecha_fin):
    """Obtiene los puntos GPS del recorrido desde Geotab para un rango de fechas"""
    print(f"🔍 Buscando dispositivo {placa}...")
    devices = client.get('Device', name=placa)
    if not devices:
        print(f"❌ Dispositivo {placa} no encontrado en Geotab")
        return [], None
    
    device = devices[0]
    device_id = device.get('id')
    imei = device.get('serialNumber')
    print(f"✅ Dispositivo: {device.get('name')} (Serial/IMEI: {imei})")
    
    f_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d')
    f_fin = datetime.strptime(fecha_fin, '%Y-%m-%d') + timedelta(days=1)
    
    # Generar lista de días
    dias = []
    dia_actual = f_inicio
    while dia_actual < f_fin:
        dias.append(dia_actual)
        dia_actual += timedelta(days=1)
    
    def descargar_dia(dia):
        """Descarga puntos de un día (para ejecutar en paralelo)"""
        dia_sig = dia + timedelta(days=1)
        fecha_str = dia.strftime('%Y-%m-%d')
        try:
            log_records = client.get('LogRecord',
                deviceSearch={'id': device_id},
                fromDate=dia,
                toDate=dia_sig
            )
            puntos_dia = []
            for record in log_records:
                lat = record.get('latitude', 0)
                lng = record.get('longitude', 0)
                speed = record.get('speed', 0) or 0
                dt = record.get('dateTime')
                
                # Datos adicionales disponibles en LogRecord (aunque no vienen en API)
                # Los establecemos en 0/None si no existen
                if lat and lng and lat != 0 and lng != 0 and dt:
                    puntos_dia.append({
                        'lat': lat,
                        'lng': lng,
                        'speed': speed,
                        'datetime': dt
                    })
            print(f"  📥 {fecha_str}: {len(puntos_dia)} puntos")
            return puntos_dia
        except Exception as e:
            print(f"  ❌ {fecha_str}: {e}")
            return []
    
    # Descargar todos los días en paralelo (4 hilos)
    print(f"  ⚡ Descargando {len(dias)} días en paralelo...")
    todos_puntos = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        resultados = list(executor.map(descargar_dia, dias))
    for r in resultados:
        todos_puntos.extend(r)
    
    # Ordenar por fecha
    todos_puntos.sort(key=lambda x: str(x['datetime']))
    print(f"\n📍 Total: {len(todos_puntos)} puntos GPS")
    return todos_puntos, imei, device_id


def obtener_sensores(client, device_id, fecha_inicio, fecha_fin):
    """Descarga StatusData de Geotab para los diagnósticos de sensores.
    Retorna un dict {nombre_sensor: [(timestamp_epoch, valor), ...]} ordenado por tiempo."""
    f_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d')
    f_fin = datetime.strptime(fecha_fin, '%Y-%m-%d') + timedelta(days=1)
    
    sensores = {}  # {nombre_osmand: [(epoch, valor), ...]}
    
    for diag_id, param_name in DIAGNOSTICOS_SENSORES.items():
        try:
            data = client.get('StatusData',
                             deviceSearch={'id': device_id},
                             diagnosticSearch={'id': diag_id},
                             fromDate=f_inicio,
                             toDate=f_fin)
            if data:
                registros = []
                for sd in data:
                    dt = sd.get('dateTime')
                    valor = sd.get('data', 0)
                    if dt is not None:
                        if hasattr(dt, 'timestamp'):
                            epoch = dt.timestamp()
                        else:
                            epoch = datetime.fromisoformat(str(dt).replace('Z', '+00:00')).timestamp()
                        
                        # Transformar valores según el sensor
                        if param_name == 'ignition':
                            valor = 1 if valor and valor > 0 else 0
                        elif param_name == 'totalDistance':
                            valor = int(valor)  # ya en metros desde Geotab
                        elif param_name == 'fuel':
                            valor = round(valor, 1)  # porcentaje
                        elif param_name == 'power':
                            valor = round(valor, 2)  # voltios
                        elif param_name == 'rpm':
                            valor = round(valor, 0)
                        
                        registros.append((epoch, valor))
                
                registros.sort(key=lambda x: x[0])
                sensores[param_name] = registros
                print(f"  Sensor {param_name:15s} ({diag_id}): {len(registros)} registros")
            else:
                print(f"  Sensor {param_name:15s} ({diag_id}): sin datos")
        except Exception as e:
            print(f"  Sensor {param_name:15s} ({diag_id}): error - {e}")
    
    return sensores


def buscar_valor_sensor(registros_sensor, timestamp_punto):
    """Busca el valor más reciente del sensor para un timestamp dado (interpolación por último valor conocido)."""
    if not registros_sensor:
        return None
    
    epochs = [r[0] for r in registros_sensor]
    idx = bisect_right(epochs, timestamp_punto)
    
    if idx == 0:
        # No hay valor antes de este timestamp, usar el primero si está cerca (< 5 min)
        if abs(registros_sensor[0][0] - timestamp_punto) < 300:
            return registros_sensor[0][1]
        return None
    
    return registros_sensor[idx - 1][1]


def preparar_urls(puntos, imei, sensores=None):
    """Pre-calcula todas las URLs para envío masivo con datos de sensores"""
    base_url = f"http://{GPSWOX_HOST}:{OSMAND_PORT}"
    urls = []
    sensores = sensores or {}
    
    for punto in puntos:
        dt = punto['datetime']
        if hasattr(dt, 'timestamp'):
            timestamp = int(dt.timestamp())
            ts_float = dt.timestamp()
        else:
            dt_parsed = datetime.fromisoformat(str(dt).replace('Z', '+00:00'))
            timestamp = int(dt_parsed.timestamp())
            ts_float = dt_parsed.timestamp()
        
        # Convertir de km/h a nudos (protocolo OsmAnd espera nudos)
        speed_knots = punto['speed'] / 1.852
        
        # URL base con datos obligatorios
        url = f"{base_url}/?id={imei}&lat={punto['lat']}&lon={punto['lng']}&speed={speed_knots:.2f}&timestamp={timestamp}"
        
        # Motion
        if punto['speed'] > 0:
            url += "&motion=true"
        else:
            url += "&motion=false"
        
        # Agregar datos de sensores interpolados al timestamp del punto GPS
        for param_name, registros in sensores.items():
            valor = buscar_valor_sensor(registros, ts_float)
            if valor is not None:
                if param_name == 'ignition':
                    url += f"&ignition={'true' if valor else 'false'}"
                else:
                    url += f"&{param_name}={valor}"
        
        urls.append(url)
    return urls


async def enviar_a_gpswox(puntos, imei, sensores=None):
    """Envía los puntos GPS en paralelo via protocolo OsmAnd (HTTP GET)"""
    CONCURRENCIA = 20   # Conexiones simultáneas
    
    print(f"\nEnviando a {GPSWOX_HOST}:{OSMAND_PORT} via OsmAnd (HTTP)")
    print(f"   IMEI/ID: {imei}")
    print(f"   Concurrencia: {CONCURRENCIA} conexiones simultaneas")
    if sensores:
        print(f"   Sensores incluidos: {', '.join(sensores.keys())}")
    
    urls = preparar_urls(puntos, imei, sensores)
    total = len(urls)
    enviados = 0
    errores = 0
    t0 = time.time()
    
    connector = aiohttp.TCPConnector(limit=CONCURRENCIA, limit_per_host=CONCURRENCIA)
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Enviar en lotes
        BATCH = 100
        for inicio in range(0, total, BATCH):
            lote = urls[inicio:inicio + BATCH]
            tasks = [session.get(url) for url in lote]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            for resp in responses:
                if isinstance(resp, Exception):
                    errores += 1
                else:
                    if resp.status == 200:
                        enviados += 1
                    else:
                        errores += 1
                    resp.release()
            
            progreso = inicio + len(lote)
            elapsed = time.time() - t0
            rate = progreso / elapsed if elapsed > 0 else 0
            print(f"  📤 {progreso}/{total} ({rate:.0f} pts/s) | ok={enviados} err={errores}")
    
    elapsed = time.time() - t0
    print(f"\n✅ Envío completado en {elapsed:.1f}s ({total/elapsed:.0f} pts/s)")
    print(f"   {enviados} enviados, {errores} errores de {total} total")


def main():
    print("=" * 60)
    print(f"  Enviar recorrido {PLACA}")
    print(f"  Período: {FECHA_INICIO} a {FECHA_FIN}")
    print(f"  Destino: {GPSWOX_HOST}:{OSMAND_PORT} (OsmAnd HTTP)")
    print("=" * 60)
    
    # 1. Obtener recorrido de Geotab
    client = get_geotab_client()
    puntos, imei, device_id = obtener_recorrido(client, PLACA, FECHA_INICIO, FECHA_FIN)
    
    if not puntos:
        print("No hay puntos GPS para enviar")
        return
    
    # Filtrar puntos ya enviados (posteriores al último cargado)
    if ULTIMO_ENVIADO:
        from dateutil.parser import parse as parse_dt
        from datetime import timezone
        ultimo_dt = parse_dt(ULTIMO_ENVIADO).replace(tzinfo=timezone.utc)
        antes = len(puntos)
        puntos = [p for p in puntos if p['datetime'].replace(tzinfo=timezone.utc) > ultimo_dt]
        print(f"\n🔽 Filtro: {antes} puntos totales → {len(puntos)} nuevos (después de {ULTIMO_ENVIADO})")
        if not puntos:
            print("No hay puntos nuevos para enviar")
            return
    
    # 2. Obtener datos de sensores de Geotab (StatusData)
    print(f"\n--- Descargando sensores de Geotab (StatusData) ---")
    sensores = obtener_sensores(client, device_id, FECHA_INICIO, FECHA_FIN)
    
    if sensores:
        print(f"\nSensores disponibles: {', '.join(sensores.keys())}")
        total_sensor_records = sum(len(v) for v in sensores.values())
        print(f"Total registros de sensores: {total_sensor_records}")
    else:
        print("Sin datos de sensores, se enviarán solo coordenadas")
    
    # Resumen
    print(f"\nResumen del recorrido:")
    print(f"   Primer punto: {puntos[0]['datetime']}")
    print(f"   Ultimo punto: {puntos[-1]['datetime']}")
    print(f"   Total puntos: {len(puntos)}")
    print(f"   Vel. maxima:  {max(p['speed'] for p in puntos):.0f} km/h")
    
    # 3. Enviar a GPSWox (async paralelo) con sensores
    asyncio.run(enviar_a_gpswox(puntos, imei, sensores))
    
    # 4. Actualizar sensors_values en la BD (GPSWox no lo hace automáticamente para OsmAnd)
    if sensores:
        print(f"\n--- Actualizando sensors_values en BD GPSWox ---")
        actualizar_sensors_values_db()
    
    print(f"\n🎉 Proceso completado. Verifica en http://{GPSWOX_HOST}/")


def actualizar_sensors_values_db():
    """Conecta via SSH y actualiza sensors_values para positions_68 
    donde hay datos de sensores en el XML 'other' pero sensors_values es NULL."""
    try:
        import paramiko
        from ssh_config import SSH_CONFIG, DEVICES
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            SSH_CONFIG['hostname'],
            port=SSH_CONFIG['port'],
            username=SSH_CONFIG['username'],
            password=SSH_CONFIG['password']
        )
        
        device_info = DEVICES.get(PLACA, {})
        pos_table = device_info.get('positions_table', 'positions_68')
        
        # IDs de sensores en gpswox_web.device_sensors para este dispositivo
        # 484=ignition, 485=totaldistance, 486=fuel, 487=power, 
        # 488=rpm, 489=coolanttemp, 490=drivertemp, 491=seatbelt
        update_sql = f"""
UPDATE gpswox_traccar.{pos_table} 
SET sensors_values = CONCAT(
    '[',
    '{{"id":484,"val":', IF(ExtractValue(other, '//ignition')='true', 'true', 'false'), '}},',
    '{{"id":485,"val":', IF(ExtractValue(other, '//totaldistance')='', '0', ExtractValue(other, '//totaldistance')), '}},',
    '{{"id":486,"val":', IF(ExtractValue(other, '//fuel')='', '0', ExtractValue(other, '//fuel')), '}},',
    '{{"id":487,"val":', IF(ExtractValue(other, '//power')='', '0', ExtractValue(other, '//power')), '}},',
    '{{"id":488,"val":', IF(ExtractValue(other, '//rpm')='', '0', ExtractValue(other, '//rpm')), '}},',
    '{{"id":489,"val":', IF(ExtractValue(other, '//coolanttemp')='', '0', ExtractValue(other, '//coolanttemp')), '}},',
    '{{"id":490,"val":', IF(ExtractValue(other, '//drivertemp')='', '0', ExtractValue(other, '//drivertemp')), '}},',
    '{{"id":491,"val":', IF(ExtractValue(other, '//seatbelt')='', '0', ExtractValue(other, '//seatbelt')), '}}',
    ']'
)
WHERE other LIKE '%<ignition>%' AND (sensors_values IS NULL OR sensors_values = '');
"""
        # Escribir SQL a archivo temporal y ejecutar
        sftp = ssh.open_sftp()
        with sftp.open('/tmp/update_sensors.sql', 'w') as f:
            f.write(update_sql)
        sftp.close()
        
        stdin, stdout, stderr = ssh.exec_command('mysql -u root < /tmp/update_sensors.sql')
        err = stderr.read().decode()
        
        if err:
            print(f"  ⚠️ Error SQL: {err}")
        else:
            # Contar actualizados
            stdin, stdout, stderr = ssh.exec_command(
                f'mysql -u root -e "SELECT COUNT(*) FROM gpswox_traccar.{pos_table} WHERE sensors_values IS NOT NULL;"'
            )
            count = stdout.read().decode().strip().split('\n')[-1]
            print(f"  ✅ sensors_values actualizados: {count} registros con sensores")
        
        ssh.close()
    except Exception as e:
        print(f"  ⚠️ No se pudo actualizar sensors_values: {e}")
        print(f"     (Los datos GPS se enviaron correctamente, solo falta el paso de sensores en BD)")


if __name__ == "__main__":
    main()
