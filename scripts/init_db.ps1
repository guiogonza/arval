# Script de inicialización segura para Geotab GPS Tracker (PowerShell)
# Uso: .\scripts\init_db.ps1

Write-Host "🚀 Inicialización de Geotab GPS Tracker" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

# Verificar si docker-compose está disponible
try {
    $null = Get-Command docker-compose -ErrorAction Stop
} catch {
    Write-Host "❌ Error: docker-compose no está instalado" -ForegroundColor Red
    exit 1
}

# Verificar si el archivo .env existe
if (-not (Test-Path ".env")) {
    Write-Host "⚠️  Advertencia: No se encontró el archivo .env" -ForegroundColor Yellow
    if (Test-Path ".env.example") {
        Write-Host "📝 Copiando .env.example a .env" -ForegroundColor Cyan
        Copy-Item ".env.example" ".env"
        Write-Host "⚠️  IMPORTANTE: Edita .env con tus credenciales antes de continuar" -ForegroundColor Yellow
        exit 1
    } else {
        Write-Host "❌ Error: No se encontró .env.example" -ForegroundColor Red
        exit 1
    }
}

# Verificar si el volumen existe
Write-Host "🔍 Verificando volúmenes existentes..." -ForegroundColor Cyan
$volumeExists = docker volume inspect geotab_postgres_data 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "⚠️  ADVERTENCIA: El volumen geotab_postgres_data ya existe" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Esto puede causar problemas de autenticación si la contraseña antigua es diferente." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Opciones:" -ForegroundColor Cyan
    Write-Host "  1) Eliminar el volumen y recrearlo (SE PERDERÁN LOS DATOS)" -ForegroundColor Red
    Write-Host "  2) Continuar con el volumen existente" -ForegroundColor Yellow
    Write-Host "  3) Hacer backup primero y luego eliminar" -ForegroundColor Green
    Write-Host "  4) Cancelar" -ForegroundColor Gray
    Write-Host ""
    
    $option = Read-Host "Selecciona una opción (1-4)"
    
    switch ($option) {
        "1" {
            Write-Host "🗑️  Eliminando volumen..." -ForegroundColor Yellow
            docker-compose down 2>&1 | Out-Null
            docker volume rm geotab_postgres_data
            Write-Host "✅ Volumen eliminado" -ForegroundColor Green
        }
        "2" {
            Write-Host "⚠️  Continuando con volumen existente..." -ForegroundColor Yellow
        }
        "3" {
            $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
            $backupFile = "postgres_backup_$timestamp.tar.gz"
            Write-Host "💾 Creando backup: $backupFile" -ForegroundColor Cyan
            docker run --rm -v geotab_postgres_data:/data -v ${PWD}:/backup ubuntu tar czf /backup/$backupFile /data
            Write-Host "✅ Backup creado: $backupFile" -ForegroundColor Green
            Write-Host "🗑️  Eliminando volumen..." -ForegroundColor Yellow
            docker-compose down 2>&1 | Out-Null
            docker volume rm geotab_postgres_data
            Write-Host "✅ Volumen eliminado" -ForegroundColor Green
        }
        "4" {
            Write-Host "❌ Operación cancelada" -ForegroundColor Red
            exit 0
        }
        default {
            Write-Host "❌ Opción inválida" -ForegroundColor Red
            exit 1
        }
    }
}

# Detener contenedores si están corriendo
Write-Host ""
Write-Host "🛑 Deteniendo contenedores existentes (si los hay)..." -ForegroundColor Yellow
docker-compose down 2>&1 | Out-Null

# Construir imágenes
Write-Host ""
Write-Host "🔨 Construyendo imágenes..." -ForegroundColor Cyan
docker-compose build

# Iniciar servicios
Write-Host ""
Write-Host "▶️  Iniciando servicios..." -ForegroundColor Green
docker-compose up -d

# Esperar a que PostgreSQL esté listo
Write-Host ""
Write-Host "⏳ Esperando a que PostgreSQL esté listo..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
while ($attempt -lt $maxAttempts) {
    $result = docker exec geotab_postgres pg_isready -U postgres 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ PostgreSQL está listo" -ForegroundColor Green
        break
    }
    $attempt++
    if ($attempt -eq $maxAttempts) {
        Write-Host "❌ Timeout esperando a PostgreSQL" -ForegroundColor Red
        exit 1
    }
    Start-Sleep -Seconds 1
}

# Esperar a que la aplicación esté lista
Write-Host ""
Write-Host "⏳ Esperando a que la aplicación esté lista..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Verificar logs
Write-Host ""
Write-Host "📝 Verificando logs de la aplicación..." -ForegroundColor Cyan
docker logs geotab_app --tail 20

# Verificar conectividad
Write-Host ""
Write-Host "🔌 Verificando conectividad..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5003/" -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Servicio web responde correctamente" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Servicio web no responde aún (HTTP $($response.StatusCode))" -ForegroundColor Yellow
        Write-Host "💡 Ejecuta: docker logs geotab_app para más detalles" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  Servicio web no responde aún" -ForegroundColor Yellow
    Write-Host "💡 Ejecuta: docker logs geotab_app para más detalles" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "✅ Inicialización completada" -ForegroundColor Green
Write-Host ""
Write-Host "🌐 Accede a la aplicación en:" -ForegroundColor Yellow
Write-Host "   http://localhost:5003" -ForegroundColor Cyan
Write-Host ""
Write-Host "📊 Ver estadísticas en:" -ForegroundColor Yellow
Write-Host "   http://localhost:5003/estadisticas" -ForegroundColor Cyan
Write-Host ""
Write-Host "🔍 Comandos útiles:" -ForegroundColor Yellow
Write-Host "   docker-compose logs -f        # Ver logs en tiempo real" -ForegroundColor Gray
Write-Host "   docker-compose ps             # Ver estado de contenedores" -ForegroundColor Gray
Write-Host "   .\scripts\diagnose.ps1        # Ejecutar diagnóstico" -ForegroundColor Gray
Write-Host "==========================================" -ForegroundColor Cyan
