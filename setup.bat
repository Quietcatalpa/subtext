@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [Subtext] 创建 conda 环境 subtext ...
call conda create -n subtext python=3.11 -y || goto :fail
echo [Subtext] 安装 PyTorch（有 NVIDIA 显卡用 GPU 版，否则 CPU 版）...
where nvidia-smi >nul 2>nul
if %errorlevel%==0 (
  call conda run -n subtext python -m pip install torch --index-url https://download.pytorch.org/whl/cu130 || goto :fail
) else (
  call conda run -n subtext python -m pip install torch || goto :fail
)
echo [Subtext] 安装其他依赖 ...
call conda run -n subtext python -m pip install -r requirements.txt || goto :fail
echo.
echo [Subtext] 安装完成，双击 start.bat 启动。首次启动会自动下载约 650 MB 的 Laya 模型。
pause
exit /b 0
:fail
echo [Subtext] 安装失败，请把上面的报错贴到 GitHub Issues。
pause
exit /b 1
