@echo off
rem MouseTranslating launcher (no console window). %~dp0 = this script's folder.
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
