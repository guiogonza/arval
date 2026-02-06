"""
Extrae placas de dispositivos de Geotab y las guarda en SQLite
"""
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import mygeotab

# Cargar variables de entorno
load_dotenv()

# Configuración de la base de datos
DB_PATH = 'geotab_data.db'


def crear_base_datos():
    """Crea la base de datos y tabla si no existen"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dispositivos (
            id TEXT PRIMARY KEY,
            placa TEXT,
            serial_number TEXT,
            tipo_dispositivo TEXT,
            fecha_actualizacion TIMESTAMP
        )
    ''')
    
    conn.commit()
    return conn


def get_geotab_client():
    """Crea y retorna un cliente autenticado de Geotab"""
    username = os.getenv('GEOTAB_USERNAME')
    password = os.getenv('GEOTAB_PASSWORD')
    database = os.getenv('GEOTAB_DATABASE')
    
    client = mygeotab.API(
        username=username,
        password=password,
        database=database
    )
    
    client.authenticate()
    return client


def extraer_y_guardar_placas():
    """Extrae placas de Geotab y las guarda en la BD"""
    print("🔄 Conectando a Geotab...")
    client = get_geotab_client()
    
    print("📥 Extrayendo dispositivos...")
    devices = client.get('Device')
    
    print(f"💾 Guardando {len(devices)} dispositivos en la base de datos...")
    conn = crear_base_datos()
    cursor = conn.cursor()
    
    fecha_actual = datetime.now()
    
    for device in devices:
        cursor.execute('''
            INSERT OR REPLACE INTO dispositivos 
            (id, placa, serial_number, tipo_dispositivo, fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            device.get('id'),
            device.get('name'),  # La placa está en el campo 'name'
            device.get('serialNumber'),
            device.get('deviceType'),
            fecha_actual
        ))
    
    conn.commit()
    
    # Mostrar resumen
    cursor.execute('SELECT placa, serial_number FROM dispositivos ORDER BY placa')
    registros = cursor.fetchall()
    
    print(f"\n✅ Se guardaron {len(registros)} placas en '{DB_PATH}':\n")
    print(f"{'PLACA':<15} {'SERIAL':<20}")
    print("-" * 35)
    
    for placa, serial in registros:
        print(f"{placa or 'N/A':<15} {serial or 'N/A':<20}")
    
    conn.close()
    print(f"\n📊 Base de datos guardada en: {os.path.abspath(DB_PATH)}")


if __name__ == "__main__":
    extraer_y_guardar_placas()
