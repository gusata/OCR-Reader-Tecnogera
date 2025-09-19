@echo off
setlocal
chcp 65001 >nul

rem === CONFIG ===
set "WORKDIR=C:\OCR (V1.0)\"
set "VENV=%WORKDIR%\.venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "SCRIPT=%WORKDIR%\all.py"
set "LOG=%WORKDIR%\scheduler.log"

rem Garante diretório de trabalho correto
pushd "%WORKDIR%"

echo [%%date%% %%time%%] START >> "%LOG%"
"%PYTHON%" "%SCRIPT%" >> "%LOG%" 2>&1
echo [%%date%% %%time%%] EXIT %%errorlevel%% >> "%LOG%"

popd
endlocal
