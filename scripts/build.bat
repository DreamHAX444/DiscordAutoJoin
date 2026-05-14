@echo off

:: =========================================================
:: FORCE SCRIPT DIRECTORY
:: =========================================================

cd /d "%~dp0.."

title Discord Auto Join - Runtime Builder
color 0A

:: =========================================================
:: CONFIG
:: =========================================================

set APP_NAME=DiscordAutoJoin
set PYTHON_VERSION=3.12.10
set PYTHON_INSTALLER=python-installer.exe
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe

set VENV_DIR=venv

:: =========================================================
:: START
:: =========================================================

cls

echo.
echo ==========================================
echo Discord Auto Join Runtime Builder
echo ==========================================
echo.

:: =========================================================
:: PYTHON CHECK
:: =========================================================

python --version >nul 2>&1

IF %ERRORLEVEL% NEQ 0 (

    echo Python not found.
    echo.
    echo Downloading Python %PYTHON_VERSION%...

    powershell -Command ^
    "Invoke-WebRequest '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'"

    echo.
    echo Installing Python silently...

    start /wait %PYTHON_INSTALLER% ^
    /quiet ^
    InstallAllUsers=1 ^
    PrependPath=1 ^
    Include_test=0

    del %PYTHON_INSTALLER%
)

:: =========================================================
:: VERIFY PYTHON
:: =========================================================

python --version

IF %ERRORLEVEL% NEQ 0 (

    echo.
    echo Python installation failed.
    echo.
    pause
    exit
)

:: =========================================================
:: WARN ABOUT PYTHON 3.14
:: =========================================================

python --version | findstr "3.14" >nul

IF %ERRORLEVEL% EQU 0 (

    echo.
    echo ==========================================
    echo WARNING:
    echo Python 3.14 detected.
    echo.
    echo Recommended:
    echo Python 3.12 for maximum Playwright stability.
    echo ==========================================
    echo.
)

:: =========================================================
:: UPDATE PIP
:: =========================================================

echo.
echo Updating pip...

python -m pip install --upgrade ^
pip ^
setuptools ^
wheel

:: =========================================================
:: CREATE VENV
:: =========================================================

IF NOT EXIST %VENV_DIR% (

    echo.
    echo Creating virtual environment...

    python -m venv %VENV_DIR%
)

:: =========================================================
:: ACTIVATE VENV
:: =========================================================

call %VENV_DIR%\Scripts\activate.bat

:: =========================================================
:: INSTALL DEPENDENCIES
:: =========================================================

echo.
echo Installing dependencies...

pip install --upgrade ^
playwright ^
pystray ^
pillow ^
psutil ^
keyboard ^
pywin32 ^
requests ^
aiohttp ^
websockets ^
colorama ^
rich ^
orjson ^
watchdog ^
pyinstaller

:: =========================================================
:: INSTALL PLAYWRIGHT CHROMIUM ONLY
:: =========================================================

echo.
echo Installing Chromium only...

playwright install chromium

:: =========================================================
:: REMOVE UNUSED PLAYWRIGHT BROWSERS
:: =========================================================

echo.
echo Removing unused Playwright browsers...

playwright uninstall firefox >nul 2>&1
playwright uninstall webkit >nul 2>&1

:: =========================================================
:: GOOGLE CHROME CHECK
:: =========================================================

IF EXIST "C:\Program Files\Google\Chrome\Application\chrome.exe" (

    echo.
    echo Google Chrome detected.

) ELSE (

    echo.
    echo Google Chrome not found.
    echo Downloading Chrome...

    powershell -Command ^
    "Invoke-WebRequest 'https://dl.google.com/chrome/install/latest/chrome_installer.exe' -OutFile 'chrome_installer.exe'"

    echo.
    echo Installing Chrome...

    start /wait chrome_installer.exe /silent /install

    del chrome_installer.exe
)

:: =========================================================
:: CREATE DIRECTORIES
:: =========================================================

echo.
echo Creating runtime directories...

mkdir dist 2>nul
mkdir logs 2>nul
mkdir cache 2>nul
mkdir crash_dumps 2>nul

:: =========================================================
:: CLEAN OLD BUILDS
:: =========================================================

echo.
echo Cleaning old builds...

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

del /f /q *.spec 2>nul

:: =========================================================
:: ICON CHECK
:: =========================================================

IF NOT EXIST "icon.ico" (

    echo.
    echo ==========================================
    echo WARNING:
    echo icon.ico not found.
    echo Building without icon.
    echo ==========================================
    echo.

    set ICON_ARG=

) ELSE (

    set ICON_ARG=--icon=icon.ico
)

:: =========================================================
:: BUILD EXE
:: =========================================================

echo.
echo Building executable...

pyinstaller ^
--noconfirm ^
--clean ^
--onefile ^
--windowed ^
--name=%APP_NAME% ^
%ICON_ARG% ^
--hidden-import=playwright ^
--hidden-import=playwright.async_api ^
--hidden-import=pystray ^
--hidden-import=PIL ^
--hidden-import=psutil ^
--hidden-import=keyboard ^
--hidden-import=win32api ^
--hidden-import=win32gui ^
--hidden-import=win32con ^
--hidden-import=win32process ^
src\DiscordAutoJoin\main.py

:: =========================================================
:: BUILD CHECK
:: =========================================================

IF EXIST "dist\%APP_NAME%.exe" (

    echo.
    echo ==========================================
    echo BUILD SUCCESSFUL
    echo ==========================================
    echo.

    echo Executable:
    echo dist\%APP_NAME%.exe

    echo.

) ELSE (

    echo.
    echo ==========================================
    echo BUILD FAILED
    echo ==========================================
    echo.
)

pause