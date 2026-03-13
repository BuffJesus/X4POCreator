@echo off
setlocal
echo ========================================
echo   PO Builder - Build Executable
echo ========================================
echo.

set BUILD_MODE=release
if /i "%1"=="debug" set BUILD_MODE=debug

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
echo Building executable (%BUILD_MODE% mode)...

if /i "%BUILD_MODE%"=="debug" (
    echo   [DEBUG MODE] Building with console window so errors are visible.
    echo   Run "dist\PO Builder Debug.exe" and check the console for any errors.
    echo.
    python -m PyInstaller -y --onefile --name "PO Builder Debug" po_builder.py ^
      --specpath . ^
      --hidden-import openpyxl ^
      --collect-all openpyxl ^
      --add-data "VERSION;."
) else (
    echo   Using PO_Builder.spec for reliable openpyxl bundling...
    python -m PyInstaller -y PO_Builder.spec
)

if errorlevel 1 (
    echo.
    echo   BUILD FAILED - check errors above
    echo ========================================
    pause
    exit /b 1
)

echo.
echo ========================================
if exist "VERSION" (
    if /i "%BUILD_MODE%"=="debug" (
        copy /Y "VERSION" "dist\VERSION" >nul
    ) else (
        copy /Y "VERSION" "dist\VERSION" >nul
    )
)
if /i "%BUILD_MODE%"=="debug" (
    if exist "dist\PO Builder Debug.exe" (
        echo   DEBUG BUILD SUCCESSFUL!
        echo   Executable: dist\PO Builder Debug.exe
        echo.
        echo   Run it and read the console output to find any remaining errors.
        echo   Then run "build.bat" ^(no argument^) for the final release build.
    ) else (
        echo   BUILD FAILED - check errors above
    )
) else (
    if exist "dist\PO Builder.exe" (
        echo   BUILD SUCCESSFUL!
        echo   Executable: dist\PO Builder.exe
        echo.
        echo   Just share "PO Builder.exe" with your coworker.
        echo.
        echo   These files are created automatically next
        echo   to the .exe on first use:
        echo     - duplicate_whitelist.txt
        echo     - order_history.json
    ) else (
        echo   BUILD FAILED - check errors above
    )
)
echo ========================================
pause
