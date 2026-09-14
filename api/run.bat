@echo off
setlocal enabledelayedexpansion
WHERE php >nul 2>nul
if %ERRORLEVEL% neq 0 echo ensure you have installed PHP to PATH.
php -S 127.0.0.1:90
endlocal