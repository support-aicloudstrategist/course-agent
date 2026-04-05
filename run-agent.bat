@echo off
echo ============================================
echo  Course Training Agent
echo ============================================
echo.

set PATH=C:\Users\home\AppData\Local\Programs\Python\Python312;C:\Users\home\AppData\Local\Programs\Python\Python312\Scripts;%PATH%

cd /d "%~dp0"
python main.py %*
pause
