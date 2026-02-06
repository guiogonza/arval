# 🚀 Guía de Despliegue

## 📦 Subir a GitHub

### 1. Crear repositorio en GitHub

1. Ve a https://github.com/new
2. Nombre del repositorio: `geotab-gps-tracker`
3. Descripción: "Sistema de rastreo GPS para flota Geotab con PostgreSQL"
4. Selecciona **Privado** (para proteger credenciales)
5. **NO** inicialices con README (ya tenemos uno)
6. Clic en "Create repository"

### 2. Conectar repositorio local con GitHub

Ejecuta estos comandos en la terminal:

```bash
# Agregar remote de GitHub (reemplaza TU_USUARIO)
git remote add origin https://github.com/TU_USUARIO/geotab-gps-tracker.git

# Verificar configuración
git remote -v

# Subir código a GitHub
git push -u origin master
```

### 3. Verificar archivo .env NO se sube

El archivo `.env` está en `.gitignore` y **NO** se subirá a GitHub (contiene credenciales).

Los colaboradores deben:
1. Clonar el repositorio
2. Copiar `.env.example` a `.env`
3. Editar `.env` con sus credenciales

## 🐳 Despliegue con Docker

### Producción local o servidor

```bash
# 1. Clonar repositorio
git clone https://github.com/TU_USUARIO/geotab-gps-tracker.git
cd geotab-gps-tracker

# 2. Configurar credenciales
cp .env.example .env
nano .env  # Editar con tus credenciales Geotab

# 3. Iniciar servicios
docker-compose up -d

# 4. Ver logs
docker-compose logs -f

# 5. Acceder
# http://localhost:5000
```

### Verificar estado

```bash
# Ver contenedores activos
docker-compose ps

# Ver logs de la aplicación
docker-compose logs -f app

# Ver logs de PostgreSQL
docker-compose logs -f postgres

# Entrar a PostgreSQL
docker-compose exec postgres psql -U postgres -d geotab_gps

# Ver datos
SELECT COUNT(*) FROM dispositivos;
SELECT COUNT(*) FROM ubicaciones;
SELECT COUNT(*) FROM viajes;
```

## 🌐 Despliegue en la Nube

### Opción 1: Railway.app (Recomendado - Gratis)

1. Crear cuenta en https://railway.app
2. "New Project" → "Deploy from GitHub repo"
3. Seleccionar repositorio `geotab-gps-tracker`
4. Railway detectará automáticamente `Dockerfile`
5. Agregar PostgreSQL:
   - "New" → "Database" → "PostgreSQL"
   - Railway creará automáticamente variables de entorno
6. Configurar variables de entorno:
   - `GEOTAB_USERNAME` = tu usuario
   - `GEOTAB_PASSWORD` = tu contraseña
   - `GEOTAB_DATABASE` = Arval_col
7. La app estará en: `https://tu-proyecto.up.railway.app`

### Opción 2: Render.com (Gratis)

1. Crear cuenta en https://render.com
2. "New" → "Web Service"
3. Conectar repositorio GitHub
4. Configuración:
   - **Name**: geotab-gps
   - **Environment**: Docker
   - **Plan**: Free
5. Agregar PostgreSQL:
   - "New" → "PostgreSQL"
   - Copiar "Internal Database URL"
6. Variables de entorno en la Web Service:
   - `GEOTAB_USERNAME`
   - `GEOTAB_PASSWORD`
   - `GEOTAB_DATABASE`
   - `POSTGRES_HOST` = (del Internal Database URL)
   - `POSTGRES_PORT` = 5432
   - `POSTGRES_DB` = (del URL)
   - `POSTGRES_USER` = (del URL)
   - `POSTGRES_PASSWORD` = (del URL)
7. Deploy automático

### Opción 3: DigitalOcean App Platform

1. Crear cuenta en https://www.digitalocean.com
2. "Create" → "Apps" → "GitHub"
3. Seleccionar repositorio
4. Configuración:
   - Detecta Dockerfile automáticamente
   - Plan: $5/mes (básico)
5. Agregar PostgreSQL:
   - "Add Resource" → "Database" → "PostgreSQL"
6. Variables de entorno (autoconfiguradas)
7. Deploy

### Opción 4: Servidor VPS (Ubuntu)

```bash
# 1. Conectar por SSH
ssh root@tu-servidor.com

# 2. Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# 3. Instalar Docker Compose
apt-get install docker-compose-plugin

# 4. Clonar repositorio
git clone https://github.com/TU_USUARIO/geotab-gps-tracker.git
cd geotab-gps-tracker

# 5. Configurar .env
cp .env.example .env
nano .env

# 6. Iniciar con reinicio automático
docker-compose up -d

# 7. Configurar Nginx (opcional)
apt install nginx
nano /etc/nginx/sites-available/geotab

# Contenido:
server {
    listen 80;
    server_name gps.tudominio.com;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Activar
ln -s /etc/nginx/sites-available/geotab /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# 8. HTTPS con Let's Encrypt
apt install certbot python3-certbot-nginx
certbot --nginx -d gps.tudominio.com
```

## 🔧 Mantenimiento

### Actualizar código

```bash
# Detener servicios
docker-compose down

# Obtener últimos cambios
git pull origin master

# Reconstruir y reiniciar
docker-compose up -d --build

# Ver logs
docker-compose logs -f
```

### Backup de base de datos

```bash
# Backup
docker-compose exec postgres pg_dump -U postgres geotab_gps > backup_$(date +%Y%m%d).sql

# Restaurar
docker-compose exec -T postgres psql -U postgres geotab_gps < backup_20260206.sql
```

### Limpiar datos antiguos

```bash
# Entrar a PostgreSQL
docker-compose exec postgres psql -U postgres -d geotab_gps

# Borrar ubicaciones de hace más de 90 días
DELETE FROM ubicaciones WHERE datetime < NOW() - INTERVAL '90 days';

# Borrar viajes antiguos
DELETE FROM viajes WHERE fecha < NOW() - INTERVAL '90 days';
```

## 📊 Monitoreo

### Ver métricas Docker

```bash
# Uso de recursos
docker stats

# Espacio en disco
docker system df

# Limpiar imágenes no usadas
docker system prune -a
```

### Logs de sincronización

```bash
# Ver última sincronización
docker-compose exec postgres psql -U postgres -d geotab_gps -c "SELECT * FROM sync_log ORDER BY timestamp DESC LIMIT 5;"
```

## 🔐 Seguridad Producción

1. **Cambiar contraseñas**:
   - PostgreSQL: Editar `POSTGRES_PASSWORD` en `docker-compose.yml`
   - Usar contraseñas fuertes

2. **Variables de entorno**:
   ```bash
   # NO incluir credenciales en docker-compose.yml
   # Usar archivo .env o secrets de Docker
   ```

3. **HTTPS obligatorio**:
   - Usar Nginx/Caddy como proxy inverso
   - Certificado SSL con Let's Encrypt

4. **Firewall**:
   ```bash
   # Solo permitir puertos necesarios
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw allow 22/tcp
   ufw enable
   ```

5. **Actualizaciones automáticas**:
   ```bash
   # Watchtower para actualizar contenedores
   docker run -d \
     --name watchtower \
     -v /var/run/docker.sock:/var/run/docker.sock \
     containrrr/watchtower
   ```

## 📞 Soporte

Para problemas o dudas:
- Revisar logs: `docker-compose logs -f`
- Verificar PostgreSQL: `docker-compose exec postgres psql -U postgres -l`
- Estado de contenedores: `docker-compose ps`
