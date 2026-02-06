"""
Aplicación web para visualizar GPS de Geotab
- Última ubicación de todos los vehículos en mapa
- Viajes diarios por placa y fecha
- Estadísticas y reportes
- Sincronización automática cada 5 minutos
"""
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
import mygeotab
import psycopg2.extras

# Importar módulos propios
from database import (
    get_connection, init_database, get_estadisticas_por_fecha,
    get_vehiculos_sin_reportar, get_resumen_por_placa_fecha
)
from sync_service import sync_service, iniciar_sync_automatica

load_dotenv()

app = Flask(__name__)

# Inicializar base de datos
init_database()

# Cliente de Geotab (singleton)
_client = None

def get_client():
    """Obtiene o crea el cliente de Geotab"""
    global _client
    if _client is None:
        _client = mygeotab.API(
            username=os.getenv('GEOTAB_USERNAME'),
            password=os.getenv('GEOTAB_PASSWORD'),
            database=os.getenv('GEOTAB_DATABASE')
        )
        _client.authenticate()
    return _client


@app.route('/')
def index():
    """Página principal con mapa de ubicaciones"""
    return render_template('index.html')


@app.route('/estadisticas')
def estadisticas():
    """Página de estadísticas"""
    return render_template('estadisticas.html')


@app.route('/api/dispositivos')
def get_dispositivos():
    """Retorna lista de dispositivos (placas)"""
    client = get_client()
    devices = client.get('Device')
    
    resultado = [
        {'id': d.get('id'), 'placa': d.get('name'), 'serial': d.get('serialNumber')}
        for d in devices
    ]
    resultado.sort(key=lambda x: x['placa'] or '')
    return jsonify(resultado)


@app.route('/api/ubicaciones')
def get_ubicaciones():
    """Retorna última ubicación de todos los dispositivos"""
    client = get_client()
    
    # Obtener dispositivos con serial
    devices = client.get('Device')
    device_map = {d.get('id'): {'name': d.get('name'), 'serial': d.get('serialNumber', '')} for d in devices}
    
    # Obtener estado actual de dispositivos (incluye ubicación)
    status_info = client.get('DeviceStatusInfo')
    
    ubicaciones = []
    for status in status_info:
        device_id = status.get('device', {}).get('id') if isinstance(status.get('device'), dict) else status.get('device')
        device_info = device_map.get(device_id, {'name': 'Desconocido', 'serial': ''})
        
        lat = status.get('latitude', 0)
        lng = status.get('longitude', 0)
        
        if lat and lng and lat != 0 and lng != 0:
            ubicaciones.append({
                'placa': device_info['name'],
                'serial': device_info['serial'],
                'lat': lat,
                'lng': lng,
                'velocidad': status.get('speed', 0),
                'direccion': status.get('bearing', 0),
                'fecha': str(status.get('dateTime', '')),
                'encendido': status.get('isDeviceCommunicating', False)
            })
    
    return jsonify(ubicaciones)


@app.route('/api/viajes')
def get_viajes():
    """Retorna viajes de un dispositivo en una fecha específica"""
    placa = request.args.get('placa')
    fecha = request.args.get('fecha')  # formato: YYYY-MM-DD
    
    if not placa or not fecha:
        return jsonify({'error': 'Se requiere placa y fecha'}), 400
    
    try:
        client = get_client()
        
        # Buscar dispositivo por nombre (placa)
        devices = client.get('Device', name=placa)
        if not devices:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404
        
        device = devices[0]
        device_id = device.get('id')
        
        # Parsear fecha
        fecha_inicio = datetime.strptime(fecha, '%Y-%m-%d')
        fecha_fin = fecha_inicio + timedelta(days=1)
        
        # Obtener viajes del día
        trips = client.get('Trip', 
            deviceSearch={'id': device_id},
            fromDate=fecha_inicio,
            toDate=fecha_fin
        )
        
        viajes = []
        for i, trip in enumerate(trips):
            # Manejar duración de forma segura
            duracion = trip.get('drivingDuration')
            if duracion:
                if hasattr(duracion, 'total_seconds'):
                    duracion_min = round(duracion.total_seconds() / 60, 1)
                else:
                    duracion_min = 0
            else:
                duracion_min = 0
            
            # Obtener ubicación de inicio y fin del viaje
            inicio_lat = trip.get('startLatitude', 0) or 0
            inicio_lng = trip.get('startLongitude', 0) or 0
            fin_lat = trip.get('stopLatitude', 0) or 0
            fin_lng = trip.get('stopLongitude', 0) or 0
            
            viajes.append({
                'viaje_num': i + 1,
                'inicio': str(trip.get('start', '')),
                'fin': str(trip.get('stop', '')),
                'distancia_km': round(trip.get('distance', 0) if trip.get('distance') else 0, 2),
                'duracion_min': duracion_min,
                'velocidad_max': trip.get('maximumSpeed', 0) or 0,
                'paradas': trip.get('stopCount', 0) or 0,
                'inicio_lat': inicio_lat,
                'inicio_lng': inicio_lng,
                'fin_lat': fin_lat,
                'fin_lng': fin_lng
            })
    except Exception as e:
        print(f"Error en /api/viajes: {e}")
        return jsonify({'error': str(e)}), 500
    
    return jsonify({
        'placa': placa,
        'fecha': fecha,
        'viajes': viajes,
        'total_viajes': len(viajes)
    })


@app.route('/api/recorrido')
def get_recorrido():
    """Retorna los puntos GPS del recorrido de un dispositivo en una fecha, agrupados por viaje"""
    placa = request.args.get('placa')
    fecha = request.args.get('fecha')  # formato: YYYY-MM-DD
    
    if not placa or not fecha:
        return jsonify({'error': 'Se requiere placa y fecha'}), 400
    
    try:
        client = get_client()
        
        # Buscar dispositivo
        devices = client.get('Device', name=placa)
        if not devices:
            return jsonify({'error': 'Dispositivo no encontrado'}), 404
        
        device = devices[0]
        device_id = device.get('id')
        
        # Parsear fecha
        fecha_inicio = datetime.strptime(fecha, '%Y-%m-%d')
        fecha_fin = fecha_inicio + timedelta(days=1)
        
        # Obtener viajes del día para saber los rangos de tiempo
        trips = client.get('Trip', 
            deviceSearch={'id': device_id},
            fromDate=fecha_inicio,
            toDate=fecha_fin
        )
        
        # Obtener registros GPS del día
        log_records = client.get('LogRecord',
            deviceSearch={'id': device_id},
            fromDate=fecha_inicio,
            toDate=fecha_fin
        )
        
        # Obtener datos de ignición (StatusData con DiagnosticIgnitionId)
        try:
            status_data = client.get('StatusData',
                deviceSearch={'id': device_id},
                diagnosticSearch={'id': 'DiagnosticIgnitionId'},
                fromDate=fecha_inicio,
                toDate=fecha_fin
            )
            # Crear diccionario de estados de ignición por tiempo aproximado
            ignition_states = {}
            for sd in status_data:
                dt = sd.get('dateTime')
                if dt:
                    # data = 1 significa encendido, 0 apagado
                    ignition_states[str(dt)] = sd.get('data', 0) == 1
        except:
            ignition_states = {}
        
        # Ordenar registros por fecha
        log_records.sort(key=lambda x: x.get('dateTime', ''))
        
        # Agrupar puntos por viaje
        viajes_con_puntos = []
        punto_global = 0  # Contador global de puntos
        
        for i, trip in enumerate(trips):
            trip_start = trip.get('start')
            trip_stop = trip.get('stop')
            
            # Obtener coordenadas de fin del viaje
            fin_lat = trip.get('stopLatitude', 0) or 0
            fin_lng = trip.get('stopLongitude', 0) or 0
            
            puntos_viaje = []
            for record in log_records:
                record_time = record.get('dateTime')
                if record_time and trip_start and trip_stop:
                    if trip_start <= record_time <= trip_stop:
                        lat = record.get('latitude', 0)
                        lng = record.get('longitude', 0)
                        velocidad = record.get('speed', 0) or 0
                        if lat and lng and lat != 0 and lng != 0:
                            punto_global += 1
                            
                            # Determinar estado de ignición
                            # Buscar el estado de ignición más cercano
                            ignicion = None
                            for ign_time, ign_state in ignition_states.items():
                                # Si hay un registro de ignición cercano, usarlo
                                ignicion = ign_state
                            
                            # Si no hay datos de ignición, usar velocidad como indicador
                            if ignicion is None:
                                ignicion = velocidad > 0
                            
                            puntos_viaje.append({
                                'num': punto_global,
                                'lat': lat,
                                'lng': lng,
                                'velocidad': velocidad,
                                'fecha': str(record_time),
                                'ignicion': ignicion
                            })
            
            if puntos_viaje:
                viajes_con_puntos.append({
                    'viaje_num': i + 1,
                    'inicio': str(trip_start),
                    'fin': str(trip_stop),
                    'fin_lat': fin_lat,
                    'fin_lng': fin_lng,
                    'puntos': puntos_viaje,
                    'total_puntos': len(puntos_viaje)
                })
        
        return jsonify({
            'placa': placa,
            'fecha': fecha,
            'viajes': viajes_con_puntos,
            'total_viajes': len(viajes_con_puntos)
        })
        
    except Exception as e:
        print(f"Error en /api/recorrido: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== ENDPOINTS DE ESTADÍSTICAS ====================

@app.route('/api/estadisticas')
def api_estadisticas():
    """Retorna estadísticas por rango de fechas"""
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    
    if not fecha_inicio:
        fecha_inicio = datetime.now().strftime('%Y-%m-%d')
    if not fecha_fin:
        fecha_fin = fecha_inicio
    
    try:
        stats = get_estadisticas_por_fecha(fecha_inicio, fecha_fin)
        return jsonify({
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'datos': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sin_reportar')
def api_sin_reportar():
    """Retorna vehículos que no han reportado"""
    dias = request.args.get('dias', 1, type=int)
    
    try:
        vehiculos = get_vehiculos_sin_reportar(dias)
        return jsonify({
            'dias': dias,
            'total': len(vehiculos),
            'vehiculos': vehiculos
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/resumen_diario')
def api_resumen_diario():
    """Retorna resumen diario de todos los vehículos"""
    fecha = request.args.get('fecha')
    
    if not fecha:
        fecha = datetime.now().strftime('%Y-%m-%d')
    
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cursor.execute('''
            SELECT * FROM resumen_diario WHERE fecha = %s ORDER BY total_km DESC
        ''', (fecha,))
        
        resultados = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        return jsonify({
            'fecha': fecha,
            'total_vehiculos': len(resultados),
            'datos': resultados
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/excesos')
def api_excesos():
    """Retorna excesos de velocidad por rango de fechas"""
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    placa = request.args.get('placa')
    
    if not fecha_inicio:
        fecha_inicio = datetime.now().strftime('%Y-%m-%d')
    if not fecha_fin:
        fecha_fin = fecha_inicio
    
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        if placa:
            cursor.execute('''
                SELECT * FROM excesos_velocidad 
                WHERE fecha BETWEEN %s AND %s AND placa = %s
                ORDER BY fecha_gps DESC
            ''', (fecha_inicio, fecha_fin, placa))
        else:
            cursor.execute('''
                SELECT * FROM excesos_velocidad 
                WHERE fecha BETWEEN %s AND %s
                ORDER BY fecha_gps DESC
            ''', (fecha_inicio, fecha_fin))
        
        excesos = [dict(row) for row in cursor.fetchall()]
        
        # Agrupar por placa
        cursor.execute('''
            SELECT placa, COUNT(*) as total, MAX(velocidad) as velocidad_max
            FROM excesos_velocidad 
            WHERE fecha BETWEEN %s AND %s
            GROUP BY placa
            ORDER BY total DESC
        ''', (fecha_inicio, fecha_fin))
        
        resumen = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        return jsonify({
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'total': len(excesos),
            'excesos': excesos[:100],
            'resumen_por_placa': resumen
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sync/status')
def api_sync_status():
    """Retorna estado del servicio de sincronización"""
    return jsonify(sync_service.get_status())


@app.route('/api/sync/ejecutar', methods=['POST'])
def api_sync_ejecutar():
    """Ejecuta sincronización manual"""
    try:
        sync_service.ejecutar_sync_completa()
        return jsonify({'status': 'ok', 'mensaje': 'Sincronización completada'})
    except Exception as e:
        return jsonify({'status': 'error', 'mensaje': str(e)}), 500


@app.route('/api/historial_km')
def api_historial_km():
    """Retorna historial de km por día para gráficas"""
    placa = request.args.get('placa')
    dias = request.args.get('dias', 30, type=int)
    
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        fecha_inicio = (datetime.now() - timedelta(days=dias)).strftime('%Y-%m-%d')
        
        if placa:
            cursor.execute('''
                SELECT fecha, total_km, total_viajes, total_excesos
                FROM resumen_diario 
                WHERE placa = %s AND fecha >= %s
                ORDER BY fecha
            ''', (placa, fecha_inicio))
        else:
            cursor.execute('''
                SELECT fecha, SUM(total_km) as total_km, SUM(total_viajes) as total_viajes, SUM(total_excesos) as total_excesos
                FROM resumen_diario 
                WHERE fecha >= %s
                GROUP BY fecha
                ORDER BY fecha
            ''', (fecha_inicio,))
        
        resultados = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        return jsonify(resultados)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("🚗 Iniciando servidor GPS Geotab...")
    print("📍 Abre http://localhost:5000 en tu navegador")
    print("📊 Estadísticas en http://localhost:5000/estadisticas")
    
    # Iniciar sincronización automática cada 5 minutos
    iniciar_sync_automatica()
    
    app.run(debug=True, port=5000, use_reloader=False)
