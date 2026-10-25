@echo off
rem Command-line entry. Use the root .vbs entry for silent desktop startup.
wscript.exe //B //NoLogo "%~dp0clock_silent.vbs" start
