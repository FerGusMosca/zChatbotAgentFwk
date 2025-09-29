@echo off
REM Movernos al directorio donde está este .bat (raíz del proyecto)
cd /d %~dp0

REM Activar el virtualenv
call zz_deploy\venv\Scripts\activate

REM Ejecutar el indexador desde la raíz
python -m zz_deploy.tools.build_vectorstore

REM Mantener la consola abierta al terminar
pause
