@echo off
title Geotab Live Sync - GPSWox
cd /d "C:\Users\guiog\OneDrive\Documentos\Geotab"
set PYTHONIOENCODING=utf-8

echo ============================================================
echo   Geotab Live Sync - GPSWox (173.212.203.163)
echo   Actualizacion cada 5 minutos
echo   Cierra esta ventana para detener el servicio
echo ============================================================
echo.

call .venv\Scripts\activate.bat
python gpswox_live_sync.py

echo.
echo El servicio se detuvo. Presiona cualquier tecla para cerrar.
pause
