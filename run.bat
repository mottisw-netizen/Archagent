@echo off
REM Build (if needed) and run Archagent in Docker, from plain Windows cmd -
REM no WSL/bash required. Requires Docker Desktop to be running.
REM
REM Usage:
REM   run.bat
REM   set ARCHAGENT_PORT=9000 && run.bat
REM   set ANTHROPIC_API_KEY=sk-ant-... && run.bat
REM
REM To connect to a Revit/AutoCAD add-in running on THIS SAME Windows machine,
REM use revit://host.docker.internal:PORT in the web UI's CAD field, not
REM 127.0.0.1 - see DOCKER.md for why.

setlocal
cd /d "%~dp0"

if not defined ARCHAGENT_PORT set ARCHAGENT_PORT=8000
if not defined ANTHROPIC_API_KEY set ANTHROPIC_API_KEY=
set IMAGE=archagent:latest
set CONTAINER=archagent

docker info >nul 2>&1
if errorlevel 1 (
  echo Docker does not seem to be running - start Docker Desktop and try again.
  exit /b 1
)

echo ==^> Building the Archagent image (this only takes a while the first time)...
docker build -t %IMAGE% .
if errorlevel 1 exit /b 1

docker rm -f %CONTAINER% >nul 2>&1

echo ==^> Starting Archagent on http://127.0.0.1:%ARCHAGENT_PORT%
echo     (Ctrl+C stops it; project data is kept in the 'archagent-data' Docker volume)
docker run --rm -it ^
  --name %CONTAINER% ^
  -p %ARCHAGENT_PORT%:8000 ^
  -v archagent-data:/data/projects ^
  -e ANTHROPIC_API_KEY=%ANTHROPIC_API_KEY% ^
  --add-host=host.docker.internal:host-gateway ^
  %IMAGE%
