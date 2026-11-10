@echo off
setlocal
rem Demo step 6 (auction): copy the lowest_unique auction type example into plugins\. Then click [rescan] in the browser.
copy /Y "%~dp0candidate-auction\examples\lowest_unique.py" "%~dp0candidate-auction\plugins\" >nul
if errorlevel 1 (
  echo FAILED: could not copy lowest_unique.py
  pause
  exit /b 1
)
echo OK: lowest_unique.py copied to candidate-auction\plugins
timeout /t 2 /nobreak >nul 2>&1
exit /b 0
