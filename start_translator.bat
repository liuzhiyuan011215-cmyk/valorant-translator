@echo off
rem pythonw: no console window; output goes to logs\translator.log
cd /d "%~dp0"
start "" pythonw main.py
