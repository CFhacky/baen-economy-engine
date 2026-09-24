@echo off
setlocal
cd /d "%~dp0"
echo The evidence-only Agriculture Workbench has been replaced by the interactive Food-Sector Operator.
call "%~dp0OPEN-BAEN-FOOD-OPERATOR.cmd"
exit /b %errorlevel%
