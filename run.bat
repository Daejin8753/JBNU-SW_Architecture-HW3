@echo off
setlocal
rem Prepare and run the HW3 converter. See run.ps1 header.
set "HW3_DIR=%~dp0."
set "HW3_APP=docconv"
powershell -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create([IO.File]::ReadAllText($env:HW3_DIR + '\run.ps1', [Text.Encoding]::UTF8)))"
pause
