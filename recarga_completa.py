"""
Script completo: Limpia datos antiguos de GPSWox y recarga feb 1-10 limpio
"""
import paramiko
import subprocess
import sys
from ssh_config import SSH_CONFIG, DEVICES

def ejecutar_mysql(client, query):
    """Ejecuta query MySQL via SSH"""
    cmd = f"mysql -u root -e '{query}'"
    stdin, stdout, stderr = client.exec_command(cmd)
    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')
    return output, error

def main():
    device = DEVICES['NFV759']
    tabla = device['positions_table']
    
    print("="*70)
    print(" RECARGA COMPLETA GPSWox - Feb 1-10 con velocidades corregidas")
    print("="*70)
    print(f"\nDispositivo: NFV759 (IMEI: {device['imei']})")
    print(f"Tabla: {tabla}")
    print(f"Servidor: {SSH_CONFIG['hostname']}")
    
    # Conectar SSH
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        print("\n[1/4] Conectando via SSH...")
        client.connect(
            hostname=SSH_CONFIG['hostname'],
            username=SSH_CONFIG['username'],
            password=SSH_CONFIG['password'],
            port=SSH_CONFIG['port'],
            timeout=10,
            look_for_keys=False,
            allow_agent=False
        )
        print("      Conectado!")
        
        # Mostrar datos actuales
        print("\n[2/4] Datos actuales en GPSWox:")
        query = f"USE gpswox_traccar; SELECT COUNT(*) as total, MIN(time) as desde, MAX(time) as hasta FROM {tabla};"
        output, _ = ejecutar_mysql(client, query)
        print(f"      {output}")
        
        # Confirmar
        print("\n ADVERTENCIA: Se eliminaran TODOS los datos de", tabla)
        print("      Esto incluye:")
        print("      - 40,954 registros actuales")
        print("      - 4 puntos anomalos en Bogota")
        print("      - Todos los datos de velocidad incorrectos")
        
        respuesta = input("\n      Escribe 'ELIMINAR' para continuar: ")
        if respuesta != 'ELIMINAR':
            print("\nCancelado. No se eliminaron datos.")
            return
        
        # Eliminar
        print("\n[3/4] Eliminando datos de", tabla, "...")
        query = f"USE gpswox_traccar; DELETE FROM {tabla};"
        ejecutar_mysql(client, query)
        
        # Verificar
        query = f"USE gpswox_traccar; SELECT COUNT(*) as restantes FROM {tabla};"
        output, _ = ejecutar_mysql(client, query)
        print(f"      Registros restantes: {output}")
        
        client.close()
        
        # Recargar datos
        print("\n[4/4] Recargando datos limpios (Feb 1-10) con velocidades corregidas...")
        print("      Ejecutando enviar_gpswox.py...")
        print("-"*70)
        
        resultado = subprocess.run(
            [sys.executable, 'enviar_gpswox.py'],
            cwd=r'c:\Users\guiog\OneDrive\Documentos\Geotab',
            capture_output=False
        )
        
        if resultado.returncode == 0:
            print("\n" + "="*70)
            print(" RECARGA COMPLETADA EXITOSAMENTE!")
            print("="*70)
            print("\nVerifica en GPSWox:")
            print("- No debe aparecer el punto en Bogota")
            print("- Las velocidades deben verse correctas")
            print("- Rango: Feb 1-10, 2026")
        else:
            print("\nError al ejecutar enviar_gpswox.py")
            print("Ejecuta manualmente: python enviar_gpswox.py")
    
    except KeyboardInterrupt:
        print("\n\nCancelado por usuario.")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        try:
            client.close()
        except:
            pass

if __name__ == "__main__":
    main()
