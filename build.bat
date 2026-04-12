@echo off
setlocal
echo ========================================
echo   POBuilder - Build Executable
echo ========================================
echo.

set BUILD_MODE=release
if /i "%1"=="debug" set BUILD_MODE=debug
if /i "%1"=="qt"    set BUILD_MODE=qt

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
      --collect-all openpyxl
) else if /i "%BUILD_MODE%"=="qt" (
    echo   [QT BUILD] Using PO_Builder_Qt.spec for the PySide6 build...
    echo   Output: dist\POBuilder_Qt.exe  ^(v0.10.0 alpha - runs alongside the tkinter build^)
    echo.
    python -m PyInstaller -y PO_Builder_Qt.spec
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
) else if /i "%BUILD_MODE%"=="qt" (
    if exist "dist\POBuilder_Qt.exe" (
        echo   QT BUILD SUCCESSFUL!
        echo   Executable: dist\POBuilder_Qt.exe
        echo.
        echo   This is the v0.10.0 alpha Qt rewrite.  During the migration the
        echo   tkinter build ^(POBuilder.exe^) remains the primary weekly-run
        echo   target; POBuilder_Qt.exe is here so you can try the new surfaces
        echo   as each alpha lands.
    ) else (
        echo   BUILD FAILED - check errors above
    )
) else (
    if exist "dist\POBuilder.exe" (
        echo   BUILD SUCCESSFUL!
        echo   Executable: dist\POBuilder.exe
        echo.
        echo   Just share "POBuilder.exe" with your coworker.
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
