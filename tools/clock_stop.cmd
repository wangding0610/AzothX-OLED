@echo off
rem Command-line entry. Use the root .vbs entry for silent desktop control.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0clock_control.ps1" -Action stop
