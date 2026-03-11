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
if exist "loading.gif" (
    echo   Found loading.gif - bundling loading animation...
) else (
    echo   loading.gif not found - continuing without loading animation asset.
)

if exist "loading.wav" (
    echo   Found loading.wav - bundling loading audio...
) else (
    echo   loading.wav not found - continuing without loading audio asset.
)

if exist "icon.ico" (
    echo   Found icon.ico - building with custom icon...
) else (
    echo   icon.ico not found - building without custom icon...
)

powershell -NoProfile -Command ^
  "$args = @('-y', '--onefile', '--windowed', '--name', 'PO Builder');" ^
  "if (Test-Path 'loading.gif') { $args += @('--add-data', 'loading.gif;.') };" ^
  "if (Test-Path 'loading.wav') { $args += @('--add-data', 'loading.wav;.') };" ^
  "if (Test-Path 'icon.ico') { $args += @('--add-data', 'icon.ico;.', '--icon', 'icon.ico') };" ^
  "$args += 'po_builder.py';" ^
  "& pyinstaller @args;" ^
  "exit $LASTEXITCODE"
if errorlevel 1 (
    echo.
    echo   BUILD FAILED - check errors above
    echo ========================================
    pause
    exit /b 1
)

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
