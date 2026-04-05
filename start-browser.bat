@echo off
echo ============================================
echo  Starting Chrome with Remote Debugging
echo ============================================
echo.

:: Try Chrome first, then Edge
set CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
set EDGE_PATH="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
set EDGE_PATH2="C:\Program Files\Microsoft\Edge\Application\msedge.exe"

if exist %CHROME_PATH% (
    echo Starting Google Chrome on port 9222...
    start "" %CHROME_PATH% --remote-debugging-port=9222
    goto :done
)

if exist %EDGE_PATH% (
    echo Starting Microsoft Edge on port 9222...
    start "" %EDGE_PATH% --remote-debugging-port=9222
    goto :done
)

if exist %EDGE_PATH2% (
    echo Starting Microsoft Edge on port 9222...
    start "" %EDGE_PATH2% --remote-debugging-port=9222
    goto :done
)

echo ERROR: Neither Chrome nor Edge found.
echo Please install Chrome or Edge, or start your browser manually with:
echo   chrome.exe --remote-debugging-port=9222
pause
exit /b 1

:done
echo.
echo Browser started with remote debugging enabled.
echo Now open your training course in the browser.
echo Then run: python main.py
echo.
pause
