#!/bin/bash
# Script de diagnóstico para Geotab GPS Tracker

set -e

echo "🔍 Diagnóstico de Geotab GPS Tracker"
echo "===================================="
echo ""

# 1. Verificar contenedores
echo "📦 Estado de contenedores:"
docker ps --filter "name=geotab" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# 2. Verificar volúmenes
echo "💾 Volúmenes de PostgreSQL:"
docker volume ls | grep geotab || echo "No se encontraron volúmenes de geotab"
echo ""

# 3. Verificar logs de app
echo "📝 Últimos 10 logs de la aplicación:"
docker logs geotab_app --tail 10 2>&1 || echo "❌ No se pudo obtener logs de geotab_app"
echo ""

# 4. Verificar conexión a PostgreSQL
echo "🔌 Verificando conexión a PostgreSQL:"
if docker exec geotab_postgres psql -U postgres -d geotab_gps -c '\q' > /dev/null 2>&1; then
    echo "✅ Conexión exitosa a PostgreSQL"
    
    # Verificar datos
    echo ""
    echo "📊 Conteo de registros:"
    docker exec geotab_postgres psql -U postgres -d geotab_gps -t -c "SELECT 'Dispositivos: ' || COUNT(*)::text FROM dispositivos;"
    docker exec geotab_postgres psql -U postgres -d geotab_gps -t -c "SELECT 'Ubicaciones: ' || COUNT(*)::text FROM ubicaciones;"
else
    echo "❌ Error de conexión a PostgreSQL"
    echo "💡 Ejecuta: docker logs geotab_postgres para más detalles"
fi

echo ""
echo "🌐 Endpoints:"
echo "   - Aplicación: http://localhost:5000"
echo "   - Estadísticas: http://localhost:5000/estadisticas"
echo ""

# 5. Verificar salud del servicio
echo "🏥 Verificando salud del servicio:"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Servicio web responde correctamente (HTTP $HTTP_CODE)"
else
    echo "❌ Servicio web no responde (HTTP $HTTP_CODE)"
fi

echo ""
echo "✅ Diagnóstico completado"
