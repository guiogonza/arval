#!/bin/bash
# Script de inicialización segura para Geotab GPS Tracker

set -e

echo "🚀 Inicialización de Geotab GPS Tracker"
echo "======================================="
echo ""

# Verificar si docker-compose está disponible
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Error: docker-compose no está instalado"
    exit 1
fi

# Verificar si el archivo .env existe
if [ ! -f ".env" ]; then
    echo "⚠️  Advertencia: No se encontró el archivo .env"
    if [ -f ".env.example" ]; then
        echo "📝 Copiando .env.example a .env"
        cp .env.example .env
        echo "⚠️  IMPORTANTE: Edita .env con tus credenciales antes de continuar"
        exit 1
    else
        echo "❌ Error: No se encontró .env.example"
        exit 1
    fi
fi

# Verificar si el volumen existe
echo "🔍 Verificando volúmenes existentes..."
if docker volume inspect geotab_postgres_data > /dev/null 2>&1; then
    echo ""
    echo "⚠️  ADVERTENCIA: El volumen geotab_postgres_data ya existe"
    echo ""
    echo "Esto puede causar problemas de autenticación si la contraseña antigua es diferente."
    echo ""
    echo "Opciones:"
    echo "  1) Eliminar el volumen y recrearlo (SE PERDERÁN LOS DATOS)"
    echo "  2) Continuar con el volumen existente"
    echo "  3) Hacer backup primero y luego eliminar"
    echo "  4) Cancelar"
    echo ""
    read -p "Selecciona una opción (1-4): " option
    
    case $option in
        1)
            echo "🗑️  Eliminando volumen..."
            docker-compose down 2>/dev/null || true
            docker volume rm geotab_postgres_data
            echo "✅ Volumen eliminado"
            ;;
        2)
            echo "⚠️  Continuando con volumen existente..."
            ;;
        3)
            BACKUP_FILE="postgres_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
            echo "💾 Creando backup: $BACKUP_FILE"
            docker run --rm -v geotab_postgres_data:/data -v $(pwd):/backup ubuntu tar czf /backup/$BACKUP_FILE /data
            echo "✅ Backup creado: $BACKUP_FILE"
            echo "🗑️  Eliminando volumen..."
            docker-compose down 2>/dev/null || true
            docker volume rm geotab_postgres_data
            echo "✅ Volumen eliminado"
            ;;
        4)
            echo "❌ Operación cancelada"
            exit 0
            ;;
        *)
            echo "❌ Opción inválida"
            exit 1
            ;;
    esac
fi

# Detener contenedores si están corriendo
echo ""
echo "🛑 Deteniendo contenedores existentes (si los hay)..."
docker-compose down 2>/dev/null || true

# Construir imágenes
echo ""
echo "🔨 Construyendo imágenes..."
docker-compose build

# Iniciar servicios
echo ""
echo "▶️  Iniciando servicios..."
docker-compose up -d

# Esperar a que PostgreSQL esté listo
echo ""
echo "⏳ Esperando a que PostgreSQL esté listo..."
for i in {1..30}; do
    if docker exec geotab_postgres pg_isready -U postgres > /dev/null 2>&1; then
        echo "✅ PostgreSQL está listo"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Timeout esperando a PostgreSQL"
        exit 1
    fi
    sleep 1
done

# Esperar a que la aplicación esté lista
echo ""
echo "⏳ Esperando a que la aplicación esté lista..."
sleep 10

# Verificar logs
echo ""
echo "📝 Verificando logs de la aplicación..."
docker logs geotab_app --tail 20

# Verificar conectividad
echo ""
echo "🔌 Verificando conectividad..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Servicio web responde correctamente"
else
    echo "⚠️  Servicio web no responde aún (HTTP $HTTP_CODE)"
    echo "💡 Ejecuta: docker logs geotab_app para más detalles"
fi

echo ""
echo "=========================================="
echo "✅ Inicialización completada"
echo ""
echo "🌐 Accede a la aplicación en:"
echo "   http://localhost:5000"
echo ""
echo "📊 Ver estadísticas en:"
echo "   http://localhost:5000/estadisticas"
echo ""
echo "🔍 Comandos útiles:"
echo "   docker-compose logs -f        # Ver logs en tiempo real"
echo "   docker-compose ps             # Ver estado de contenedores"
echo "   bash scripts/diagnose.sh      # Ejecutar diagnóstico"
echo "=========================================="
