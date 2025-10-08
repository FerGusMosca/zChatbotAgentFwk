@echo off
REM ============================================================
REM  Script: build_vectorstore.bat
REM  Purpose: Activate venv and build vectorstore index
REM  Author: Fer
REM ============================================================

REM Movernos al directorio raíz del proyecto (donde está este .bat)
cd /d "%~dp0"

REM Activar el entorno virtual
call .\venv\Scripts\activate

REM Ejecutar el indexador desde la carpeta tools
python -m tools.build_vectorstore

REM Mantener la consola abierta al finalizar
pause
