@echo off
cd /d "%~dp0"
REM Build a single-file Windows .exe of Mei with PyInstaller.
REM Run this inside the project folder. PyInstaller is already installed in .venv.

set PY=.venv\Scripts\python.exe
if not exist .venv\Scripts\python.exe set PY=python

REM Validate and regenerate shared manifests and extension before packaging.
"%PY%" tools\build_shared_assets.py
if errorlevel 1 exit /b 1

REM --- Free the space old builds are holding -------------------------------
REM dist\Mei.exe is deliberately NOT deleted here: PyInstaller overwrites it at
REM the END of a successful build, so a failed build never costs you the app.
echo Pruning stale builds (not dist\Mei.exe) ...
if exist "dist\PolarAppWin.exe" del /q "dist\PolarAppWin.exe"
if exist "dist\browser.exe"      del /q "dist\browser.exe"
if exist "dist\LiteBrowser.exe"  del /q "dist\LiteBrowser.exe"
if exist "dist\Mei.exe.bak"      del /q "dist\Mei.exe.bak"
if exist "dist\*.old"            del /q "dist\*.old"
if exist "build\Mei"             rmdir /s /q "build\Mei"
if exist "build\LiteBrowser"     rmdir /s /q "build\LiteBrowser"
if exist "build\browser"         rmdir /s /q "build\browser"

REM --- Pick the Qt binding that is actually installed ---------------------
REM The app runs on PyQt5 or PyQt6 (litebrowser\qt.py). Collect whichever one
REM exists, so this script also works on a machine that has only one of them.
set "QTFLAGS=--collect-all PyQt5.QtWebEngineCore --collect-all PyQt5.QtWebEngineWidgets --collect-all PyQt5.QtWebChannel --exclude-module PyQt6"
set "QTVERSION=PyQt5"
"%PY%" -c "import PyQt6.QtWebEngineWidgets" >nul 2>nul
if not errorlevel 1 (
  set "QTFLAGS=--collect-all PyQt6.QtWebEngineCore --collect-all PyQt6.QtWebEngineWidgets --collect-all PyQt6.QtWebChannel --exclude-module PyQt5"
  set "QTVERSION=PyQt6"
)
echo Building Mei.exe with %QTVERSION% ...

"%PY%" -m PyInstaller ^
  --onefile ^
  --noconfirm ^
  --windowed ^
  --icon=icon.ico ^
  --name="Mei" ^
  --add-data "icon.png;." ^
  --add-data "litebrowser\data\chain.json;litebrowser\data" ^
  --add-data "litebrowser\data\plugins;litebrowser\data\plugins" ^
  --add-data "web_support\boitoan;web_support\boitoan" ^
  --collect-all cryptography ^
  --collect-all segno ^
  %QTFLAGS% ^
  browser.py ^
  --clean

REM PyInstaller rewrites dist\Mei.exe at the very end, so a running Mei holds the
REM file open (WinError 5) and the build aborts AFTER the long compile. Report it
REM instead of printing "Done" over a stale exe.
if errorlevel 1 (
  echo.
  echo Build FAILED - PyInstaller could not finish.
  echo If it says "Access is denied: dist\Mei.exe", a Mei window is still open -
  echo close it, check the tray too, and run build_exe.bat again.
  pause
  exit /b 1
)

if not exist "dist\Mei.exe" (
  echo.
  echo Build FAILED - dist\Mei.exe was not produced. Your previous build is untouched.
  pause
  exit /b 1
)

echo.
echo Creating dist\web_support (large offline sites live here, next to the exe) ...
REM Deliberately done in Python, so keep the folder names in that script: cmd.exe
REM decodes this UTF-8 batch file in the OEM code page, so the Vietnamese legacy
REM hub name never matched here and the old copy step shipped the dead ~600 MB
REM duplicate on every build. sync_web_support.py skips it while copying and
REM prunes whatever an older build already left in dist, dev logs included.
"%PY%" tools\sync_web_support.py
if errorlevel 1 (
  echo.
  echo Build FAILED - could not refresh dist\web_support.
  pause
  exit /b 1
)

echo.
echo -----------------------------------------------------
echo  Done. Two things you must ship together:
echo    -  dist\Mei.exe
echo    -  dist\web_support  (folder, keep beside the .exe)
echo.
echo  web_support is NOT bundled into the exe on purpose
echo  (it is ~600 MB; the app loads it from beside the exe).
echo.
echo  Let a Mei that is ALREADY installed upgrade itself
echo  (needs a higher version in litebrowser\core\product.py):
echo      "%PY%" tools\write_local_update.py dist
echo  then drop dist\update beside the installed exe and launch it.
echo -----------------------------------------------------
echo.
pause