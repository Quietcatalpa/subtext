@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
rem 优先用 setup.bat 建的 subtext 环境，没有就用 laya 环境
set ENV=subtext
call conda env list | findstr /b /c:"subtext " >nul || set ENV=laya
start "" cmd /c "timeout /t 40 >nul && start http://127.0.0.1:7860"
conda run --no-capture-output -n %ENV% python server.py
pause
