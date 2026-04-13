@echo off
setlocal
echo ========================================
echo   POBuilder - Build Executable
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
      --collect-all PySide6.QtCore ^
      --collect-all PySide6.QtGui ^
      --collect-all PySide6.QtWidgets ^
      --collect-all shiboken6 ^
      --hidden-import PySide6.QtCore ^
      --hidden-import PySide6.QtGui ^
      --hidden-import PySide6.QtWidgets
) else (
    echo   Using PO_Builder.spec for reliable bundling...
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
