# Credenciales SSH para servidor GPSWox
SSH_CONFIG = {
    'hostname': '213.199.45.139',
    'username': 'root',
    'password': 'Colombiaw1**',
    'port': 22
}

# Credenciales MySQL (sin password para root local)
MYSQL_CONFIG = {
    'host': '127.0.0.1',  # Desde SSH
    'port': 3306,
    'user': 'root',
    'password': '',  # Sin password
    'database': 'gpswox_traccar'
}

# Mapeo de dispositivos
DEVICES = {
    'NFV759': {
        'gpswox_id': 588,
        'imei': 'G91D32202MSK',
        'positions_table': 'positions_68',
        'device_id': 68
    }
}
