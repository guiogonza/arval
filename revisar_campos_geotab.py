"""
Script de diagnóstico: muestra TODOS los campos que llegan de Geotab
para cada entidad que usa el proyecto (Device, DeviceStatusInfo, Trip, LogRecord)
"""
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import mygeotab

load_dotenv()

def get_client():
    client = mygeotab.API(
        username=os.getenv('GEOTAB_USERNAME'),
        password=os.getenv('GEOTAB_PASSWORD'),
        database=os.getenv('GEOTAB_DATABASE')
    )
    client.authenticate()
    return client

def serializar(obj):
    """Convierte objetos Geotab a tipos serializables"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return str(obj)
    if isinstance(obj, dict):
        return {k: serializar(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serializar(i) for i in obj]
    return obj

def mostrar_campos(titulo, datos, max_items=2):
    """Muestra los campos de una lista de objetos Geotab"""
    print(f"\n{'='*70}")
    print(f" {titulo}")
    print(f"{'='*70}")
    print(f"Total registros: {len(datos)}")
    
    if not datos:
        print("  (sin datos)")
        return
    
    # Mostrar todos los campos del primer registro
    primer = datos[0]
    campos = sorted(primer.keys()) if isinstance(primer, dict) else []
    
    print(f"\nCampos encontrados ({len(campos)}):")
    print("-" * 50)
    for campo in campos:
        valor = primer.get(campo)
        tipo = type(valor).__name__
        valor_str = str(valor)
        if len(valor_str) > 80:
            valor_str = valor_str[:80] + "..."
        print(f"  {campo:30s} | {tipo:15s} | {valor_str}")
    
    # Mostrar registros de ejemplo completos
    for i, item in enumerate(datos[:max_items]):
        print(f"\n--- Ejemplo #{i+1} ---")
        print(json.dumps(serializar(item), indent=2, ensure_ascii=False, default=str))

def main():
    print("🔍 Conectando a Geotab API...")
    client = get_client()
    print("✅ Conectado\n")

    # ===== 1. DEVICE =====
    devices = client.get('Device')
    mostrar_campos("1. DEVICE (Dispositivos)", devices)

    # Guardar primer device_id para consultas posteriores
    device_id = devices[0].get('id') if devices else None
    placa = devices[0].get('name') if devices else None

    # ===== 2. DEVICE STATUS INFO =====
    statuses = client.get('DeviceStatusInfo')
    mostrar_campos("2. DEVICE STATUS INFO (Estado actual)", statuses)

    # ===== 3. TRIP (Viajes del día) =====
    if device_id:
        hoy = datetime.now().date()
        ayer = hoy - timedelta(days=1)
        # Intentar hoy, si no hay datos probar ayer y antier
        trips = []
        for dias_atras in range(0, 7):
            fecha = hoy - timedelta(days=dias_atras)
            from_dt = datetime.combine(fecha, datetime.min.time())
            to_dt = datetime.combine(fecha, datetime.max.time())
            trips = client.get('Trip',
                              deviceSearch={'id': device_id},
                              fromDate=from_dt,
                              toDate=to_dt)
            if trips:
                print(f"\n(Viajes encontrados para {placa} en fecha {fecha})")
                break
        mostrar_campos(f"3. TRIP (Viajes de {placa})", trips)
    else:
        print("\n⚠️ Sin dispositivos, no se pueden consultar viajes")

    # ===== 4. LOG RECORD (Puntos GPS) =====
    if device_id:
        records = []
        for dias_atras in range(0, 7):
            fecha = hoy - timedelta(days=dias_atras)
            from_dt = datetime.combine(fecha, datetime.min.time())
            to_dt = datetime.combine(fecha, datetime.max.time())
            records = client.get('LogRecord',
                                deviceSearch={'id': device_id},
                                fromDate=from_dt,
                                toDate=to_dt)
            if records:
                print(f"\n(LogRecords encontrados para {placa} en fecha {fecha})")
                break
        mostrar_campos(f"4. LOG RECORD (Puntos GPS de {placa})", records)
    else:
        print("\n⚠️ Sin dispositivos, no se pueden consultar LogRecords")

    # ===== 5. STATUS DATA (Datos de diagnóstico del motor) =====
    if device_id:
        status_data = []
        for dias_atras in range(0, 7):
            fecha = hoy - timedelta(days=dias_atras)
            from_dt = datetime.combine(fecha, datetime.min.time())
            to_dt = datetime.combine(fecha, datetime.max.time())
            try:
                status_data = client.get('StatusData',
                                        deviceSearch={'id': device_id},
                                        fromDate=from_dt,
                                        toDate=to_dt)
            except:
                status_data = []
            if status_data:
                print(f"\n(StatusData encontrado para {placa} en fecha {fecha})")
                break
        mostrar_campos(f"5. STATUS DATA (Diagnóstico motor de {placa})", status_data[:10] if status_data else [])

    # ===== RESUMEN: Campos usados vs disponibles =====
    print(f"\n{'='*70}")
    print(" RESUMEN: Campos USADOS en el código vs DISPONIBLES en Geotab")
    print(f"{'='*70}")
    
    print("\n📦 Device:")
    print("  Usados:      id, name (→placa), serialNumber, deviceType")
    if devices:
        print(f"  Disponibles: {', '.join(sorted(devices[0].keys()))}")
    
    print("\n📍 DeviceStatusInfo:")
    print("  Usados:      device.id, device.name, latitude, longitude, speed, bearing, dateTime, isDeviceCommunicating")
    if statuses:
        print(f"  Disponibles: {', '.join(sorted(statuses[0].keys()))}")
    
    print("\n🚗 Trip:")
    print("  Usados:      start, stop, distance, drivingDuration, maximumSpeed")
    if trips:
        print(f"  Disponibles: {', '.join(sorted(trips[0].keys()))}")
    
    print("\n📡 LogRecord:")
    print("  Usados:      latitude, longitude, speed, dateTime")
    if device_id and records:
        print(f"  Disponibles: {', '.join(sorted(records[0].keys()))}")

    print(f"\n{'='*70}")
    print(" FIN DEL DIAGNÓSTICO")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
