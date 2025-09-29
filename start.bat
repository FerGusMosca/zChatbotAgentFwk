@echo off
REM Activar entorno virtual (prueba venv y .venv)
if exist venv\Scripts\activate (
  call venv\Scripts\activate
) else if exist .venv\Scripts\activate (
  call .venv\Scripts\activate
) else (
  echo [ERROR] No se encontro venv/.venv. Crealo primero.
  exit /b 1
)

REM Iniciar app
python main.py
