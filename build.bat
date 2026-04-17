@echo off
echo === YT Downloader - Build ===
echo.

echo [1/2] Installing dependencies...
pip install -r requirements.txt pyinstaller
if errorlevel 1 ( echo FAILED && pause && exit /b 1 )

echo.
echo [2/2] Building executable...
python -m PyInstaller ^
  --onefile ^
  --noconsole ^
  --name "YT Downloader" ^
  --add-data "templates;templates" ^
  --collect-all imageio_ffmpeg ^
  --hidden-import "yt_dlp" ^
  --hidden-import "flask" ^
  app.py
if errorlevel 1 ( echo FAILED && pause && exit /b 1 )

echo.
echo Done! Executable: dist\YT Downloader.exe
echo.
pause
