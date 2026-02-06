"""
Módulo de base de datos para GPS Geotab - PostgreSQL
"""
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de PostgreSQL
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'geotab_gps'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
}


def get_connection():
    """Obtiene conexión a la base de datos PostgreSQL"""
    conn = psycopg2.connect(**DB_CONFIG)
    return conn


def init_database():
    """Inicializa la base de datos con todas las tablas necesarias"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabla de dispositivos/vehículos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dispositivos (
            id TEXT PRIMARY KEY,
            placa TEXT UNIQUE,
            serial_number TEXT,
            tipo_dispositivo TEXT,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            activo INTEGER DEFAULT 1
        )
    ''')
    
    # Tabla de ubicaciones (última conocida por vehículo)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ubicaciones (
            id SERIAL PRIMARY KEY,
            dispositivo_id TEXT,
            placa TEXT,
            latitud REAL,
            longitud REAL,
            velocidad REAL,
            direccion REAL,
            fecha_gps TIMESTAMP,
            comunicando INTEGER,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (dispositivo_id) REFERENCES dispositivos(id)
        )
    ''')
    
    # Tabla de viajes diarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS viajes (
            id SERIAL PRIMARY KEY,
            dispositivo_id TEXT,
            placa TEXT,
            fecha DATE,
            viaje_num INTEGER,
            hora_inicio TIMESTAMP,
            hora_fin TIMESTAMP,
            distancia_km REAL,
            duracion_min REAL,
            velocidad_max REAL,
            lat_inicio REAL,
            lng_inicio REAL,
            lat_fin REAL,
            lng_fin REAL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (dispositivo_id) REFERENCES dispositivos(id)
        )
    ''')
    
    # Tabla de reportes GPS (puntos de cada viaje)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reportes_gps (
            id SERIAL PRIMARY KEY,
            dispositivo_id TEXT,
            placa TEXT,
            fecha DATE,
            latitud REAL,
            longitud REAL,
            velocidad REAL,
            fecha_gps TIMESTAMP,
            ignicion INTEGER,
            FOREIGN KEY (dispositivo_id) REFERENCES dispositivos(id)
        )
    ''')
    
    # Tabla de excesos de velocidad
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS excesos_velocidad (
            id SERIAL PRIMARY KEY,
            dispositivo_id TEXT,
            placa TEXT,
            fecha DATE,
            velocidad REAL,
            limite_velocidad REAL DEFAULT 80,
            latitud REAL,
            longitud REAL,
            fecha_gps TIMESTAMP,
            FOREIGN KEY (dispositivo_id) REFERENCES dispositivos(id)
        )
    ''')
    
    # Tabla de resumen diario por vehículo
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS resumen_diario (
            id SERIAL PRIMARY KEY,
            dispositivo_id TEXT,
            placa TEXT,
            fecha DATE,
            total_viajes INTEGER DEFAULT 0,
            total_km REAL DEFAULT 0,
            total_reportes INTEGER DEFAULT 0,
            total_excesos INTEGER DEFAULT 0,
            hora_primer_encendido TEXT,
            hora_ultimo_apagado TEXT,
            tiempo_activo_min REAL DEFAULT 0,
            velocidad_max_dia REAL DEFAULT 0,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(dispositivo_id, fecha),
            FOREIGN KEY (dispositivo_id) REFERENCES dispositivos(id)
        )
    ''')
    
    # Tabla de sincronización
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sync_log (
            id SERIAL PRIMARY KEY,
            tipo TEXT,
            fecha_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            registros_procesados INTEGER DEFAULT 0,
            estado TEXT DEFAULT 'OK',
            mensaje TEXT
        )
    ''')
    
    # Crear índices para mejor rendimiento
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_viajes_placa_fecha ON viajes(placa, fecha)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reportes_placa_fecha ON reportes_gps(placa, fecha)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_excesos_placa_fecha ON excesos_velocidad(placa, fecha)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_resumen_fecha ON resumen_diario(fecha)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ubicaciones_placa ON ubicaciones(placa)')
    
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Base de datos PostgreSQL inicializada correctamente")


def guardar_ubicacion(dispositivo_id, placa, lat, lng, velocidad, direccion, fecha_gps, comunicando):
    """Guarda o actualiza la última ubicación de un vehículo"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Verificar si ya existe
    cursor.execute('SELECT id FROM ubicaciones WHERE placa = %s', (placa,))
    existe = cursor.fetchone()
    
    if existe:
        cursor.execute('''
            UPDATE ubicaciones 
            SET latitud = %s, longitud = %s, velocidad = %s, direccion = %s, 
                fecha_gps = %s, comunicando = %s, fecha_actualizacion = %s
            WHERE placa = %s
        ''', (lat, lng, velocidad, direccion, fecha_gps, comunicando, datetime.now(), placa))
    else:
        cursor.execute('''
            INSERT INTO ubicaciones (dispositivo_id, placa, latitud, longitud, velocidad, direccion, fecha_gps, comunicando)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (dispositivo_id, placa, lat, lng, velocidad, direccion, fecha_gps, comunicando))
    
    conn.commit()
    cursor.close()
    conn.close()


def guardar_viaje(dispositivo_id, placa, fecha, viaje_num, hora_inicio, hora_fin, 
                  distancia_km, duracion_min, velocidad_max, lat_inicio, lng_inicio, lat_fin, lng_fin):
    """Guarda un viaje en la base de datos"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Verificar si ya existe este viaje
    cursor.execute('''
        SELECT id FROM viajes 
        WHERE placa = %s AND fecha = %s AND viaje_num = %s
    ''', (placa, fecha, viaje_num))
    existe = cursor.fetchone()
    
    if not existe:
        cursor.execute('''
            INSERT INTO viajes (dispositivo_id, placa, fecha, viaje_num, hora_inicio, hora_fin,
                               distancia_km, duracion_min, velocidad_max, lat_inicio, lng_inicio, lat_fin, lng_fin)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (dispositivo_id, placa, fecha, viaje_num, hora_inicio, hora_fin,
              distancia_km, duracion_min, velocidad_max, lat_inicio, lng_inicio, lat_fin, lng_fin))
    
    conn.commit()
    cursor.close()
    conn.close()


def guardar_exceso_velocidad(dispositivo_id, placa, fecha, velocidad, lat, lng, fecha_gps, limite=80):
    """Guarda un exceso de velocidad"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO excesos_velocidad (dispositivo_id, placa, fecha, velocidad, limite_velocidad, latitud, longitud, fecha_gps)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ''', (dispositivo_id, placa, fecha, velocidad, limite, lat, lng, fecha_gps))
    
    conn.commit()
    cursor.close()
    conn.close()


def actualizar_resumen_diario(placa, fecha):
    """Actualiza el resumen diario de un vehículo"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Obtener dispositivo_id
    cursor.execute('SELECT id FROM dispositivos WHERE placa = %s', (placa,))
    disp = cursor.fetchone()
    dispositivo_id = disp['id'] if disp else None
    
    # Calcular estadísticas del día
    cursor.execute('''
        SELECT 
            COUNT(*) as total_viajes,
            COALESCE(SUM(distancia_km), 0) as total_km,
            COALESCE(SUM(duracion_min), 0) as tiempo_activo,
            COALESCE(MAX(velocidad_max), 0) as velocidad_max,
            MIN(hora_inicio) as primer_encendido,
            MAX(hora_fin) as ultimo_apagado
        FROM viajes 
        WHERE placa = %s AND fecha = %s
    ''', (placa, fecha))
    stats = cursor.fetchone()
    
    # Contar reportes
    cursor.execute('''
        SELECT COUNT(*) as total FROM reportes_gps WHERE placa = %s AND fecha = %s
    ''', (placa, fecha))
    reportes = cursor.fetchone()
    
    # Contar excesos
    cursor.execute('''
        SELECT COUNT(*) as total FROM excesos_velocidad WHERE placa = %s AND fecha = %s
    ''', (placa, fecha))
    excesos = cursor.fetchone()
    
    # Insertar o actualizar resumen (ON CONFLICT para PostgreSQL)
    cursor.execute('''
        INSERT INTO resumen_diario 
        (dispositivo_id, placa, fecha, total_viajes, total_km, total_reportes, total_excesos,
         hora_primer_encendido, hora_ultimo_apagado, tiempo_activo_min, velocidad_max_dia, fecha_actualizacion)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (dispositivo_id, fecha) DO UPDATE SET
            total_viajes = EXCLUDED.total_viajes,
            total_km = EXCLUDED.total_km,
            total_reportes = EXCLUDED.total_reportes,
            total_excesos = EXCLUDED.total_excesos,
            hora_primer_encendido = EXCLUDED.hora_primer_encendido,
            hora_ultimo_apagado = EXCLUDED.hora_ultimo_apagado,
            tiempo_activo_min = EXCLUDED.tiempo_activo_min,
            velocidad_max_dia = EXCLUDED.velocidad_max_dia,
            fecha_actualizacion = EXCLUDED.fecha_actualizacion
    ''', (
        dispositivo_id, placa, fecha,
        stats['total_viajes'] or 0,
        stats['total_km'] or 0,
        reportes['total'] or 0,
        excesos['total'] or 0,
        stats['primer_encendido'],
        stats['ultimo_apagado'],
        stats['tiempo_activo'] or 0,
        stats['velocidad_max'] or 0,
        datetime.now()
    ))
    
    conn.commit()
    cursor.close()
    conn.close()


def get_vehiculos_sin_reportar(dias=1):
    """Obtiene vehículos que no han reportado en X días"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    fecha_limite = datetime.now() - timedelta(days=dias)
    
    cursor.execute('''
        SELECT d.placa, d.serial_number, u.fecha_gps, u.latitud, u.longitud,
               CASE 
                   WHEN u.fecha_gps IS NULL THEN NULL
                   ELSE ROUND(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - u.fecha_gps)) / 86400, 1)
               END as dias_sin_reportar
        FROM dispositivos d
        LEFT JOIN ubicaciones u ON d.placa = u.placa
        WHERE u.fecha_gps < %s OR u.fecha_gps IS NULL
        ORDER BY u.fecha_gps ASC NULLS FIRST
    ''', (fecha_limite,))
    
    resultados = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return resultados


def get_estadisticas_por_fecha(fecha_inicio, fecha_fin):
    """Obtiene estadísticas agregadas por rango de fechas"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cursor.execute('''
        SELECT 
            placa,
            SUM(total_viajes) as viajes,
            SUM(total_km) as km_total,
            SUM(total_reportes) as reportes,
            SUM(total_excesos) as excesos,
            AVG(velocidad_max_dia) as vel_max_promedio,
            SUM(tiempo_activo_min) as tiempo_total
        FROM resumen_diario
        WHERE fecha BETWEEN %s AND %s
        GROUP BY placa
        ORDER BY km_total DESC
    ''', (fecha_inicio, fecha_fin))
    
    resultados = [dict(row) for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return resultados


def get_resumen_por_placa_fecha(placa, fecha):
    """Obtiene el resumen de un vehículo en una fecha específica"""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cursor.execute('''
        SELECT * FROM resumen_diario WHERE placa = %s AND fecha = %s
    ''', (placa, fecha))
    
    resultado = cursor.fetchone()
    cursor.close()
    conn.close()
    return dict(resultado) if resultado else None


def log_sync(tipo, registros, estado='OK', mensaje=''):
    """Registra una sincronización"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO sync_log (tipo, registros_procesados, estado, mensaje)
        VALUES (%s, %s, %s, %s)
    ''', (tipo, registros, estado, mensaje))
    
    conn.commit()
    cursor.close()
    conn.close()


# Inicializar BD al importar
init_database()
