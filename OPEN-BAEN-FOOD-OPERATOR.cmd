@echo off
setlocal
cd /d "%~dp0"

set "BAEN_PYTHON=.venv\Scripts\python.exe"
set "BAEN_DATA=%USERPROFILE%\Documents\Baen Economy"
set "BAEN_DATABASE=%BAEN_DATA%\baen-food-operator.sqlite"

if exist "%BAEN_PYTHON%" goto :prepare

where py >nul 2>nul
if errorlevel 1 goto :no_python

echo Preparing the local Baen Food-Sector Operator...
py -3 -m venv .venv
if errorlevel 1 goto :failed

:prepare
if not exist "%BAEN_DATA%" mkdir "%BAEN_DATA%"
if errorlevel 1 goto :failed

set "PYTHONPATH=%CD%\src"
echo Opening the Baen Food-Sector Operator in your browser...
echo Keep this window open while you use it. Press Ctrl+C here to stop it.
"%BAEN_PYTHON%" -m baen_economy.food_ops_server --database "%BAEN_DATABASE%" --open
if errorlevel 1 goto :failed
exit /b 0

:no_python
echo.
echo Python 3 was not found. Install Python 3, then double-click this file again.
pause
exit /b 1

:failed
echo.
echo The Baen Food-Sector Operator could not start.
echo No Notion data, campaign time, dice, or canonical ledger state was changed.
pause
exit /b 1
