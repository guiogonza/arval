# Script de diagnóstico para Geotab GPS Tracker (PowerShell)
# Uso: .\scripts\diagnose.ps1

Write-Host "🔍 Diagnóstico de Geotab GPS Tracker" -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar contenedores
Write-Host "📦 Estado de contenedores:" -ForegroundColor Yellow
docker ps --filter "name=geotab" --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}"
Write-Host ""

# 2. Verificar volúmenes
Write-Host "💾 Volúmenes de PostgreSQL:" -ForegroundColor Yellow
$volumes = docker volume ls | Select-String "geotab"
if ($volumes) {
    docker volume ls | Select-String "geotab"
} else {
    Write-Host "No se encontraron volúmenes de geotab" -ForegroundColor Gray
}
Write-Host ""

# 3. Verificar logs de app
Write-Host "📝 Últimos 10 logs de la aplicación:" -ForegroundColor Yellow
try {
    docker logs geotab_app --tail 10 2>&1
} catch {
    Write-Host "❌ No se pudo obtener logs de geotab_app" -ForegroundColor Red
}
Write-Host ""

# 4. Verificar conexión a PostgreSQL
Write-Host "🔌 Verificando conexión a PostgreSQL:" -ForegroundColor Yellow
try {
    $result = docker exec geotab_postgres psql -U postgres -d geotab_gps -c '\q' 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Conexión exitosa a PostgreSQL" -ForegroundColor Green
        
        # Verificar datos
        Write-Host ""
        Write-Host "📊 Conteo de registros:" -ForegroundColor Yellow
        docker exec geotab_postgres psql -U postgres -d geotab_gps -t -c "SELECT 'Dispositivos: ' || COUNT(*)::text FROM dispositivos;"
        docker exec geotab_postgres psql -U postgres -d geotab_gps -t -c "SELECT 'Ubicaciones: ' || COUNT(*)::text FROM ubicaciones;"
    } else {
        Write-Host "❌ Error de conexión a PostgreSQL" -ForegroundColor Red
        Write-Host "💡 Ejecuta: docker logs geotab_postgres para más detalles" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Error al verificar PostgreSQL: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "🌐 Endpoints:" -ForegroundColor Yellow
Write-Host "   - Aplicación: http://localhost:5003" -ForegroundColor Cyan
Write-Host "   - Estadísticas: http://localhost:5003/estadisticas" -ForegroundColor Cyan
Write-Host ""

# 5. Verificar salud del servicio
Write-Host "🏥 Verificando salud del servicio:" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5003/" -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Servicio web responde correctamente (HTTP $($response.StatusCode))" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Servicio web respondió con HTTP $($response.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Servicio web no responde" -ForegroundColor Red
    Write-Host "💡 Verifica que los contenedores estén corriendo" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "✅ Diagnóstico completado" -ForegroundColor Green
