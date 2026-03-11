@echo off
setlocal
echo ========================================
echo   PO Builder - Build Executable
echo ========================================
echo.

echo Installing dependencies...
python -m pip install -r requirements.txt pyinstaller

echo.
echo Running tests...
python -m unittest discover -s tests -q
if errorlevel 1 (
    echo.
    echo Tests failed. Build cancelled.
    pause
    exit /b 1
)

echo.
echo Building executable...
set "ASSET_GIF="
set "ASSET_WAV="
set "ASSET_ICON_DATA="
set "ASSET_ICON_ARG="

if exist "loading.gif" (
    echo   Found loading.gif - bundling loading animation...
    set "ASSET_GIF=--add-data ""loading.gif;."""
) else (
    echo   loading.gif not found - continuing without loading animation asset.
)

if exist "Nyan Cat! [Official].wav" (
    echo   Found Nyan Cat! [Official].wav - bundling loading audio...
    set "ASSET_WAV=--add-data ""Nyan Cat! [Official].wav;."""
) else (
    echo   Nyan Cat! [Official].wav not found - continuing without loading audio asset.
)

if exist "icon.ico" (
    echo   Found icon.ico - building with custom icon...
    set "ASSET_ICON_DATA=--add-data ""icon.ico;."""
    set "ASSET_ICON_ARG=--icon ""icon.ico"""
) else (
    echo   icon.ico not found - building without custom icon...
)

pyinstaller --onefile --windowed %ASSET_GIF% %ASSET_WAV% %ASSET_ICON_DATA% %ASSET_ICON_ARG% --name "PO Builder" po_builder.py

echo.
echo ========================================
if exist "dist\PO Builder.exe" (
    echo   BUILD SUCCESSFUL!
    echo   Executable: dist\PO Builder.exe
    echo.
    echo   Just share "PO Builder.exe" with your coworker.
    echo   The dancing cat is bundled inside.
    echo.
    echo   These files are created automatically next
    echo   to the .exe on first use:
    echo     - duplicate_whitelist.txt
    echo     - order_history.json
) else (
    echo   BUILD FAILED - check errors above
)
echo ========================================
pause
