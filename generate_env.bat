@echo off
REM Crear entorno virtual (solo si no existe)
if not exist venv (
    python -m venv venv
)

REM Activar entorno
call venv\Scripts\activate

REM Actualizar pip e instalar requirements
python -m pip install -U pip
pip install -r requirements.txt
