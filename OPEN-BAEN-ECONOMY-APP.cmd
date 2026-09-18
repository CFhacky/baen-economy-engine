@echo off
setlocal
cd /d "%~dp0"

title Baen Economy Engine

set "BAEN_PYTHON=.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
set "PYTHONPATH=%CD%\src"
set "BAEN_DATA=%USERPROFILE%\Documents\Baen Economy"
set "BAEN_DATABASE=%BAEN_DATA%\baen-empire-operator.sqlite"

if exist "%BAEN_PYTHON%" goto :run

where py >nul 2>nul
if errorlevel 1 goto :no_python

echo Preparing the local Baen Economy Engine application...
py -3 -m venv .venv
if errorlevel 1 goto :failed

:run
if not exist "%BAEN_DATA%" mkdir "%BAEN_DATA%"
if errorlevel 1 goto :failed
echo Opening the Baen Economy Engine in your browser...
echo This application is preview-only: zero Notion writes, zero canonical ledger posts, zero campaign-time advance.
echo Keep this window open while you use it. Press Ctrl+C here to stop it.
"%BAEN_PYTHON%" -m baen_economy.empire_ops_server --database "%BAEN_DATABASE%" --open
if errorlevel 1 goto :failed
exit /b 0

:no_python
echo.
echo Python 3.11 or newer was not found. Install Python 3, then double-click this file again.
pause
exit /b 1

:failed
echo.
echo The Baen Economy Engine application could not start.
echo No Notion data, campaign time, or canonical ledger state was changed.
pause
exit /b 1
