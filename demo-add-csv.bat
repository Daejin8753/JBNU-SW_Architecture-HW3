@echo off
setlocal
rem Demo step 5 (converter): copy the csv plugin example into plugins\. Then click [rescan] in the browser.
copy /Y "%~dp0candidate-docconv\examples\csv_conv.py" "%~dp0candidate-docconv\plugins\" >nul
if errorlevel 1 (
  echo FAILED: could not copy csv_conv.py
  pause
  exit /b 1
)
echo OK: csv_conv.py copied to candidate-docconv\plugins
timeout /t 2 /nobreak >nul 2>&1
exit /b 0
