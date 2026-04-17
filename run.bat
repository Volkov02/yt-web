@echo off
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting YT Downloader at http://127.0.0.1:5757
echo Press Ctrl+C to stop.
echo.
python app.py
pause
