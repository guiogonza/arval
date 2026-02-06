"""
Servicio de sincronización automática con Geotab
Actualiza datos cada 5 minutos
"""
import threading
import time
import mygeotab
import psycopg2.extras
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# Importar módulo de base de datos
from database import (
    get_connection, guardar_ubicacion, guardar_viaje,
    guardar_exceso_velocidad, actualizar_resumen_diario, log_sync, init_database
)

load_dotenv()

# Configuración
SYNC_INTERVAL = 300  # 5 minutos en segundos
LIMITE_VELOCIDAD = 80  # km/h para excesos

class SyncService:
    def __init__(self):
        self.api = None
        self.running = False
        self.thread = None
        self.ultima_sync = None
        self.conectar()
    
    def conectar(self):
        """Conecta con la API de Geotab"""
        try:
            self.api = mygeotab.API(
                username=os.getenv('GEOTAB_USERNAME'),
                password=os.getenv('GEOTAB_PASSWORD'),
                database=os.getenv('GEOTAB_DATABASE')
            )
            self.api.authenticate()
            print("✅ Conectado a Geotab API")
            return True
        except Exception as e:
            print(f"❌ Error conectando a Geotab: {e}")
            return False
    
    def sync_dispositivos(self):
        """Sincroniza lista de dispositivos"""
        try:
            devices = self.api.get('Device')
            conn = get_connection()
            cursor = conn.cursor()
            
            for device in devices:
                cursor.execute('''
                    INSERT INTO dispositivos (id, placa, serial_number, tipo_dispositivo, activo)
                    VALUES (%s, %s, %s, %s, 1)
                    ON CONFLICT (id) DO UPDATE SET
                        placa = EXCLUDED.placa,
                        serial_number = EXCLUDED.serial_number,
                        tipo_dispositivo = EXCLUDED.tipo_dispositivo,
                        activo = EXCLUDED.activo
                ''', (
                    device.get('id'),
                    device.get('name'),
                    device.get('serialNumber', ''),
                    device.get('deviceType', '')
                ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            log_sync('dispositivos', len(devices))
            print(f"✅ Sincronizados {len(devices)} dispositivos")
            return len(devices)
        except Exception as e:
            log_sync('dispositivos', 0, 'ERROR', str(e))
            print(f"❌ Error sincronizando dispositivos: {e}")
            return 0
    
    def sync_ubicaciones(self):
        """Sincroniza ubicaciones actuales de todos los vehículos"""
        try:
            device_statuses = self.api.get('DeviceStatusInfo')
            count = 0
            
            for status in device_statuses:
                try:
                    device = status.get('device', {})
                    device_id = device.get('id') if isinstance(device, dict) else device
                    placa = device.get('name', str(device_id)) if isinstance(device, dict) else str(device_id)
                    
                    lat = status.get('latitude', 0)
                    lng = status.get('longitude', 0)
                    velocidad = status.get('speed', 0)
                    direccion = status.get('bearing', 0)
                    fecha_gps = status.get('dateTime')
                    comunicando = 1 if status.get('isDeviceCommunicating', False) else 0
                    
                    guardar_ubicacion(
                        device_id, placa, lat, lng, velocidad, direccion, fecha_gps, comunicando
                    )
                    count += 1
                except Exception as e:
                    continue
            
            log_sync('ubicaciones', count)
            print(f"✅ Sincronizadas {count} ubicaciones")
            return count
        except Exception as e:
            log_sync('ubicaciones', 0, 'ERROR', str(e))
            print(f"❌ Error sincronizando ubicaciones: {e}")
            return 0
    
    def sync_viajes_dia(self, fecha=None):
        """Sincroniza viajes de un día para todos los vehículos"""
        if fecha is None:
            fecha = datetime.now().date()
        
        try:
            conn = get_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute('SELECT id, placa FROM dispositivos')
            dispositivos = cursor.fetchall()
            cursor.close()
            conn.close()
            
            if not dispositivos:
                print("⚠️ No hay dispositivos en BD, sincronizando primero...")
                self.sync_dispositivos()
                conn = get_connection()
                cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cursor.execute('SELECT id, placa FROM dispositivos')
                dispositivos = cursor.fetchall()
                cursor.close()
                conn.close()
            
            from_date = datetime.combine(fecha, datetime.min.time())
            to_date = datetime.combine(fecha, datetime.max.time())
            
            total_viajes = 0
            total_excesos = 0
            
            for disp in dispositivos:
                try:
                    trips = self.api.get('Trip', 
                                        deviceSearch={'id': disp['id']},
                                        fromDate=from_date,
                                        toDate=to_date)
                    
                    for i, trip in enumerate(trips, 1):
                        # Obtener datos del viaje (usando .get() para diccionarios)
                        start_time = trip.get('start')
                        stop_time = trip.get('stop')
                        distance = (trip.get('distance') or 0) / 1000  # convertir a km
                        
                        duracion = 0
                        driving_dur = trip.get('drivingDuration')
                        if driving_dur:
                            try:
                                if hasattr(driving_dur, 'total_seconds'):
                                    duracion = driving_dur.total_seconds() / 60
                            except:
                                duracion = 0
                        
                        # Obtener velocidad máxima del viaje (ya viene en el Trip)
                        vel_max = trip.get('maximumSpeed', 0) or 0
                        
                        # Guardar viaje
                        guardar_viaje(
                            disp['id'], disp['placa'], str(fecha), i,
                            start_time, stop_time, distance, duracion, vel_max,
                            0, 0, 0, 0
                        )
                        total_viajes += 1
                        
                        # Detectar exceso de velocidad basado en velocidad máxima del viaje
                        if vel_max > LIMITE_VELOCIDAD:
                            guardar_exceso_velocidad(
                                disp['id'], disp['placa'], str(fecha),
                                vel_max, 0, 0, start_time, LIMITE_VELOCIDAD
                            )
                            total_excesos += 1
                            
                except Exception as e:
                    continue
                
                # Actualizar resumen diario del vehículo
                actualizar_resumen_diario(disp['placa'], str(fecha))
            
            log_sync('viajes', total_viajes)
            print(f"✅ Sincronizados {total_viajes} viajes, {total_excesos} excesos de velocidad")
            return total_viajes
            
        except Exception as e:
            log_sync('viajes', 0, 'ERROR', str(e))
            print(f"❌ Error sincronizando viajes: {e}")
            return 0
    
    def ejecutar_sync_completa(self):
        """Ejecuta sincronización completa"""
        print(f"\n🔄 Iniciando sincronización - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Reconectar si es necesario
        if self.api is None:
            self.conectar()
        
        # Sincronizar dispositivos (solo 1 vez al día sería suficiente)
        self.sync_dispositivos()
        
        # Sincronizar ubicaciones actuales
        self.sync_ubicaciones()
        
        # Sincronizar viajes del día actual
        self.sync_viajes_dia()
        
        self.ultima_sync = datetime.now()
        print(f"✅ Sincronización completa - {self.ultima_sync.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    def loop_sync(self):
        """Loop principal de sincronización"""
        while self.running:
            try:
                self.ejecutar_sync_completa()
            except Exception as e:
                print(f"❌ Error en loop de sincronización: {e}")
            
            # Esperar hasta próxima sincronización
            time.sleep(SYNC_INTERVAL)
    
    def iniciar(self):
        """Inicia el servicio de sincronización en segundo plano"""
        if self.running:
            print("⚠️ El servicio ya está corriendo")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self.loop_sync, daemon=True)
        self.thread.start()
        print(f"🚀 Servicio de sincronización iniciado (cada {SYNC_INTERVAL//60} minutos)")
    
    def detener(self):
        """Detiene el servicio de sincronización"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("⏹️ Servicio de sincronización detenido")
    
    def get_status(self):
        """Obtiene estado del servicio"""
        return {
            'running': self.running,
            'ultima_sync': self.ultima_sync.isoformat() if self.ultima_sync else None,
            'intervalo_min': SYNC_INTERVAL // 60,
            'conectado': self.api is not None
        }


# Instancia global del servicio
sync_service = SyncService()


def iniciar_sync_automatica():
    """Función helper para iniciar sincronización"""
    sync_service.iniciar()
    return sync_service


if __name__ == '__main__':
    # Ejecutar sincronización manual si se ejecuta directamente
    print("Ejecutando sincronización manual...")
    sync_service.ejecutar_sync_completa()
