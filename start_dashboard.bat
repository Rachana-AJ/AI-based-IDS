@echo off
title Skylearn IoT - Neural Shield Launcher
cd /d "%~dp0"

echo ======================================================================
echo    🛡️ SKYLEARN IoT - NEURAL SHIELD INTRUSION DETECTION SYSTEM 🛡️
echo ======================================================================
echo  Starting FastAPI PyTorch Backend & Port 1884 MQTT Proxy...
echo  Starting Skylearn React Dashboard on Vite...
echo.
echo  💻 PC Dashboard:     http://localhost:5173
echo  📱 Mobile Dashboard: http://10.240.36.194:5173
echo  🧠 Backend API:      http://localhost:8000
echo  📶 Mobile MQTT App:  10.240.36.194:1884
echo ======================================================================

start "Neural Shield - ML Backend & MQTT Proxy" cmd /k "cd /d "%~dp0my_project" && .\.venv\Scripts\python.exe -m uvicorn backend.service:app --host 0.0.0.0 --port 8000"

timeout /t 2 /nobreak >nul

start "Skylearn IoT - React Dashboard" cmd /k "cd /d "%~dp0frontend" && npm run dev"

timeout /t 2 /nobreak >nul

start http://localhost:5173
