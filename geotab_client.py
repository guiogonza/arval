"""
Cliente de conexión a Geotab API
"""
import os
from dotenv import load_dotenv
import mygeotab

# Cargar variables de entorno desde .env
load_dotenv()

def get_geotab_client():
    """Crea y retorna un cliente autenticado de Geotab"""
    username = os.getenv('GEOTAB_USERNAME')
    password = os.getenv('GEOTAB_PASSWORD')
    database = os.getenv('GEOTAB_DATABASE')
    
    if not all([username, password, database]):
        raise ValueError("Faltan credenciales en el archivo .env")
    
    client = mygeotab.API(
        username=username,
        password=password,
        database=database
    )
    
    client.authenticate()
    print(f"✓ Conectado exitosamente a la base de datos: {database}")
    return client


if __name__ == "__main__":
    try:
        # Conectar a Geotab
        client = get_geotab_client()
        
        # Ejemplo: Obtener lista de dispositivos
        devices = client.get('Device')
        print(f"\n📍 Se encontraron {len(devices)} dispositivos:")
        
        for device in devices[:5]:  # Mostrar primeros 5
            print(f"  - {device.get('name', 'Sin nombre')} (Serial: {device.get('serialNumber', 'N/A')})")
        
        if len(devices) > 5:
            print(f"  ... y {len(devices) - 5} más")
            
    except Exception as e:
        print(f"❌ Error: {e}")
