@echo off
title Cute Poker - Starting...

echo ==========================================
echo   Cute Poker Modular - Auto Launcher
echo ==========================================
echo.

:: Start the Python server in the background
echo [1/2] Starting poker server on port 8000...
start /B python server.py > nul 2>&1

:: Wait a moment for server to boot
timeout /t 2 /nobreak > nul

:: Start ngrok and capture the public URL
echo [2/2] Starting ngrok tunnel...
set NGROK_PATH=C:\Users\Yeeroo\Desktop\ngrok\ngrok.exe
start "" /B "%NGROK_PATH%" http 8000 > nul 2>&1

:: Wait for ngrok to establish the tunnel
timeout /t 5 /nobreak > nul

:: Fetch the public URL from ngrok's local API
echo.
echo ==========================================
echo   Your URLs:
echo ==========================================
echo.
echo   Local:  http://127.0.0.1:8000
echo.

:: Use PowerShell to grab the ngrok URL (retry a few times)
set PUBLIC_URL=
for /L %%a in (1,1,5) do (
    if not defined PUBLIC_URL (
        for /f "delims=" %%i in ('powershell -Command "try { (Invoke-RestMethod http://127.0.0.1:4040/api/tunnels).tunnels[0].public_url } catch { '' }"') do (
            if not "%%i"=="" set PUBLIC_URL=%%i
        )
        if not defined PUBLIC_URL timeout /t 2 /nobreak > nul
    )
)

if defined PUBLIC_URL (
    echo   Public: %PUBLIC_URL%
) else (
    echo   Public: [FAILED] ngrok may need an auth token.
    echo           Run: C:\Users\Yeeroo\Desktop\ngrok\ngrok.exe config add-authtoken YOUR_TOKEN
    echo           Get a free token at https://dashboard.ngrok.com/get-started/your-authtoken
)

echo.
echo ==========================================
echo   Share the Public URL with friends!
echo   Press Ctrl+C to stop everything.
echo ==========================================
echo.

:: Keep the window open and wait for Ctrl+C
:loop
timeout /t 60 /nobreak > nul
goto loop
