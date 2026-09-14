@echo off
setlocal enabledelayedexpansion
where tex3ds >nul 2>nul
if %errorlevel% neq 0 echo Please install tex3ds. pacman ^-S tex3ds
tex3ds -i textures.t3s -o textures.t3x
endlocal

