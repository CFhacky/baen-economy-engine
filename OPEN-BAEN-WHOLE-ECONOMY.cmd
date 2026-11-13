@echo off
setlocal EnableExtensions DisableDelayedExpansion

title Baen Whole-Economy Preview

rem This file belongs in the repository root, beside pyproject.toml.
rem It never invokes git, pip, Notion, or a canonical campaign ledger.
set "REPO_ROOT=%~dp0"
set "CLI=%REPO_ROOT%src\baen_economy\whole_economy_cli.py"
set "SCENARIO=%REPO_ROOT%fixtures\regional-scenarios\baen-north-whole-economy-v1.json"
set "SEED=baen-north-whole-economy-preview-v3"
set "PYTHONUTF8=1"
set "PYTHONPATH=%REPO_ROOT%src"

echo.
echo BAEN WHOLE-ECONOMY PREVIEW
echo Non-canonical local simulation: zero Notion writes and zero canonical postings.
echo.

if not exist "%CLI%" goto :missing_cli
if not exist "%SCENARIO%" goto :missing_scenario

set "PYTHON_CMD="
where py.exe >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py.exe -3"
if defined PYTHON_CMD goto :check_python

where python.exe >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python.exe"
if not defined PYTHON_CMD goto :missing_python

:check_python
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto :old_python

set "DOCUMENTS=%USERPROFILE%\Documents"
for /f "usebackq delims=" %%D in (`powershell.exe -NoProfile -NonInteractive -Command "[Environment]::GetFolderPath('MyDocuments')" 2^>nul`) do set "DOCUMENTS=%%D"
if not defined DOCUMENTS goto :missing_documents

set "WORKSPACE=%DOCUMENTS%\Baen Economy\whole-economy-preview-v3"

if exist "%WORKSPACE%\" goto :advance_month

echo First launch: sealing the bundled scenario in:
echo   "%WORKSPACE%"
%PYTHON_CMD% -m baen_economy.whole_economy_cli init "%WORKSPACE%" --scenario "%SCENARIO%" --seed "%SEED%"
if errorlevel 1 goto :init_failed

:advance_month
echo.
%PYTHON_CMD% -m baen_economy.whole_economy_cli boot "%WORKSPACE%"
if errorlevel 1 goto :boot_failed

echo.
echo Verifying history and committing exactly one next month...
%PYTHON_CMD% -m baen_economy.whole_economy_cli run-month "%WORKSPACE%" --commit
if errorlevel 1 goto :run_failed

echo.
echo Verifying the committed history by deterministic replay...
%PYTHON_CMD% -m baen_economy.whole_economy_cli verify "%WORKSPACE%"
if errorlevel 1 goto :verify_failed

set "LATEST_MONTH="
for /f "delims=" %%D in ('dir /b /ad /o-n "%WORKSPACE%\months" 2^>nul') do if not defined LATEST_MONTH set "LATEST_MONTH=%%D"
if not defined LATEST_MONTH goto :report_missing

set "REPORT=%WORKSPACE%\months\%LATEST_MONTH%\report.html"
if not exist "%REPORT%" goto :report_missing

echo.
echo Month %LATEST_MONTH% committed and verified.
echo Opening:
echo   "%REPORT%"
start "" "%REPORT%"
if errorlevel 1 goto :open_failed
exit /b 0

:missing_cli
echo ERROR: The simulator CLI was not found:
echo   "%CLI%"
echo Keep this launcher in the repository root beside pyproject.toml.
goto :failed

:missing_scenario
echo ERROR: The bundled scenario was not found:
echo   "%SCENARIO%"
goto :failed

:missing_python
echo ERROR: Python 3.11 or newer is required, but py.exe and python.exe were not found.
goto :failed

:old_python
echo ERROR: The detected Python is older than 3.11 or could not start.
echo Install Python 3.11 or newer and ensure py.exe or python.exe is on PATH.
goto :failed

:missing_documents
echo ERROR: Windows did not provide a usable Documents folder.
goto :failed

:init_failed
echo ERROR: The preview workspace could not be initialized. No month was committed.
goto :failed

:run_failed
echo ERROR: The next month was not committed. Read the error above; existing history was preserved.
goto :failed

:boot_failed
echo ERROR: The sealed campaign activation gates could not be checked.
echo No month was committed and no campaign state was changed.
goto :failed

:verify_failed
echo ERROR: A month was written, but its saved history did not pass replay verification.
echo The report will not be opened. Do not treat that month as accepted output.
goto :failed

:report_missing
echo ERROR: The committed month did not contain the expected HTML report.
goto :failed

:open_failed
echo ERROR: The report exists, but Windows could not open it in the default browser.
echo Open it manually at:
echo   "%REPORT%"
goto :failed

:failed
echo.
pause
exit /b 1
