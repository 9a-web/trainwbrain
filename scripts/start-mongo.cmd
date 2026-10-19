@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-mongo.ps1" %*
pause
