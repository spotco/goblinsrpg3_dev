@echo off
setlocal

cd /d "%~dp0"

if not exist "docs\index.html" (
  echo ERROR: docs\index.html was not found.
  echo Run this script from the repository checkout, or rebuild the docs output first.
  pause
  exit /b 1
)

echo Serving Goblins RPG 3 from:
echo   %CD%\docs
echo.
echo Open this URL:
echo   http://127.0.0.1:8765/
echo.
echo Debug hotspots:
echo   http://127.0.0.1:8765/?debug=1
echo.
echo Press Ctrl+C or close this console window to stop the server.
echo.

python -m http.server 8765 --bind 127.0.0.1 --directory docs

