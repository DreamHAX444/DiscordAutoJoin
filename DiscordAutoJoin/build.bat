@echo off
echo ══════════════════════════════════════════════════════════════
echo   Discord Auto-Join — Build Script (Chrome Edition)
echo ══════════════════════════════════════════════════════════════
echo.

echo [1/3] Installing Python dependencies...
pip install playwright pystray pillow pywin32 pyinstaller

echo.
echo [2/3] Installing Playwright Chrome driver...
playwright install chromium

echo.
echo [3/3] Building standalone .exe with PyInstaller...
pyinstaller --onefile --noconsole --name DiscordAutoJoin ^
  --hidden-import playwright._impl._api_types ^
  --hidden-import pystray._win32 ^
  main.py

echo.
echo ══════════════════════════════════════════════════════════════
echo   BUILD COMPLETE!
echo   Executable: dist\DiscordAutoJoin.exe
echo ══════════════════════════════════════════════════════════════
pause
