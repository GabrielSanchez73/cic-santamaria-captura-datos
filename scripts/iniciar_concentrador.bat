@echo off
REM Arranca el concentrador escuchando en toda la red local (para que el ESP32 pueda llegar a el).
REM Uso: scripts\iniciar_concentrador.bat [puerto]
cd /d "%~dp0.."
set PUERTO=%1
if "%PUERTO%"=="" set PUERTO=8000
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
echo Concentrador en el puerto %PUERTO%. Tu IP aparece en la linea "IPv4" de:
ipconfig | findstr /i "IPv4"
echo Jornada: http://localhost:%PUERTO%/jornada
python -m uvicorn app.main:app --host 0.0.0.0 --port %PUERTO%
