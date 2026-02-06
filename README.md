# Sistema de Rastreo GPS - Geotab

Sistema de rastreo GPS en tiempo real que se conecta a la API de Geotab para monitorear flotas vehiculares.

## 🚀 Características

- **Rastreo en tiempo real**: Visualización de ubicaciones GPS de vehículos
- **Mapas interactivos**: 
  - Vista de mapa estándar (OpenStreetMap)
  - Vista satelital (Google Satellite)
  - Visualización de rutas con múltiples colores
  - Marcadores con estado de ignición (ON/OFF)
- **Estadísticas completas**:
  - Resumen diario de kilómetros recorridos
  - Detección de excesos de velocidad
  - Vehículos sin reportar
  - Gráficos con Chart.js
- **Sincronización automática**: Actualización cada 5 minutos
- **Base de datos PostgreSQL**: Almacenamiento escalable y confiable

## 📋 Requisitos Previos

- Docker y Docker Compose instalados
- Credenciales de acceso a Geotab API
- Git (opcional)

## 🐳 Instalación con Docker

### 1. Clonar el repositorio (o descargar archivos)

```bash
git clone <url-del-repositorio>
cd Geotab
```

### 2. Configurar variables de entorno

Copiar el archivo de ejemplo y editar con tus credenciales:

```bash
cp .env.example .env
```

Editar `.env` y configurar:
```env
GEOTAB_USERNAME=tu_usuario@empresa.com
GEOTAB_PASSWORD=tu_contraseña
GEOTAB_DATABASE=nombre_base_geotab
```

### 3. Iniciar los servicios

```bash
docker-compose up -d
```

Esto iniciará:
- PostgreSQL en el puerto 5432
- Aplicación Flask en el puerto 5000

### 4. Acceder a la aplicación

Abrir en el navegador:
- **Página principal**: http://localhost:5000
- **Estadísticas**: http://localhost:5000/estadisticas

## 🛠️ Comandos Útiles

### Ver logs de la aplicación
```bash
docker-compose logs -f app
```

### Ver logs de PostgreSQL
```bash
docker-compose logs -f postgres
```

### Reiniciar servicios
```bash
docker-compose restart
```

### Detener servicios
```bash
docker-compose down
```

### Detener y eliminar datos
```bash
docker-compose down -v
```

### Reconstruir la imagen
```bash
docker-compose build --no-cache
docker-compose up -d
```

## 📊 Estructura del Proyecto

```
Geotab/
├── app.py                  # Aplicación Flask principal
├── database.py             # Gestión de base de datos PostgreSQL
├── sync_service.py         # Servicio de sincronización automática
├── templates/              # Plantillas HTML
│   ├── index.html         # Página principal con mapa
│   └── estadisticas.html  # Dashboard de estadísticas
├── Dockerfile             # Imagen Docker de la aplicación
├── docker-compose.yml     # Orquestación de servicios
├── requirements.txt       # Dependencias Python
└── .env                   # Variables de entorno (NO INCLUIR EN GIT)
```

## 🗄️ Base de Datos

La base de datos PostgreSQL incluye las siguientes tablas:

- **dispositivos**: Información de vehículos
- **ubicaciones**: Registros GPS
- **viajes**: Viajes individuales
- **excesos_velocidad**: Infracciones de velocidad
- **resumen_diario**: Estadísticas diarias por vehículo
- **sync_log**: Registro de sincronizaciones

## 🔧 Desarrollo Local

Si prefieres ejecutar sin Docker:

### 1. Crear entorno virtual
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Configurar PostgreSQL local
Asegúrate de tener PostgreSQL instalado y crea la base de datos:
```sql
CREATE DATABASE geotab_gps;
```

### 4. Ejecutar aplicación
```bash
python app.py
```

## 📝 Notas

- La sincronización automática se ejecuta cada 5 minutos
- Los datos se conservan en un volumen Docker persistente
- Para producción, cambiar las contraseñas en `.env` y `docker-compose.yml`

## 🔐 Seguridad

- **NUNCA** subir el archivo `.env` a Git
- Cambiar las contraseñas por defecto de PostgreSQL
- Usar HTTPS en producción
- Revisar permisos de acceso a la base de datos

## 📄 Licencia

Uso interno - Hesego Ingeniería

## 👤 Autor

Desarrollado para el monitoreo de flota Arval Colombia
