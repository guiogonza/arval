"""
Script para limpiar datos de GPSWox via SSH
"""
import paramiko
from ssh_config import SSH_CONFIG, DEVICES

def ejecutar_mysql(client, query, descripcion=""):
    """Ejecuta query MySQL via SSH"""
    cmd = f"mysql -u root -e '{query}'"
    if descripcion:
        print(f"\n{descripcion}")
    print(f"Ejecutando: {query[:80]}...")
    
    stdin, stdout, stderr = client.exec_command(cmd)
    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')
    
    if output:
        print(output)
    if error and 'Warning' not in error:
        print(f"Error: {error}")
    
    return output, error

def main():
    device = DEVICES['NFV759']
    tabla = device['positions_table']
    
    print(f"=== LIMPIEZA DE DATOS GPSWox ===")
    print(f"Dispositivo: NFV759")
    print(f"Tabla: {tabla}")
    print(f"Servidor: {SSH_CONFIG['hostname']}\n")
    
    # Conectar SSH
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(
            hostname=SSH_CONFIG['hostname'],
            username=SSH_CONFIG['username'],
            password=SSH_CONFIG['password'],
            port=SSH_CONFIG['port'],
            timeout=10,
            look_for_keys=False,
            allow_agent=False
        )
        print("Conectado via SSH\n")
        
        # 1. Mostrar datos actuales
        query = f"USE gpswox_traccar; SELECT COUNT(*) as total, MIN(time) as desde, MAX(time) as hasta FROM {tabla};"
        ejecutar_mysql(client, query, "1. Datos actuales:")
        
        # 2. Confirmar eliminacion
        input("\nPresiona ENTER para ELIMINAR TODOS los datos (Ctrl+C para cancelar)...")
        
        # 3. Eliminar datos
        query = f"USE gpswox_traccar; DELETE FROM {tabla};"
        ejecutar_mysql(client, query, "2. Eliminando datos...")
        
        # 4. Verificar
        query = f"USE gpswox_traccar; SELECT COUNT(*) as registros_restantes FROM {tabla};"
        ejecutar_mysql(client, query, "3. Verificacion:")
        
        print("\n LIMPIEZA COMPLETADA!")
        print("\nAhora ejecuta: python enviar_gpswox.py")
        print("para recargar datos limpios con velocidades corregidas.")
        
    except KeyboardInterrupt:
        print("\n\nCancelado por usuario.")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()
