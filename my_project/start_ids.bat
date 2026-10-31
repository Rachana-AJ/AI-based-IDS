@echo off
title IoT Intrusion Detection System - Terminal Monitor & API Hub
cd /d "%~dp0"

echo ======================================================================
echo  Starting IoT Intrusion Detection System Terminal Monitor ^& API Hub
echo  Desktop Dashboard: http://localhost:3000
echo  Backend API Server: http://localhost:8000
echo  Mobile MQTT Broker: 10.240.36.194:1884
echo  Hardware Nodes:     COM9 (ESP-A) and COM13 (ESP-B)
echo ======================================================================

.\.venv\Scripts\python.exe run_terminal.py

if errorlevel 1 (
    echo.
    echo System exited with an error.
    pause
)
