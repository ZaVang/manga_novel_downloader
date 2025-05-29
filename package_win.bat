@echo off
setlocal

REM 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
REM 移除末尾的反斜杠（如果存在）
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PROJECT_ROOT=%SCRIPT_DIR%"
set "OUTPUT_DIR=%PROJECT_ROOT%\dist\windows"
set "APP_NAME=漫画与小说下载器"
set "MAIN_SCRIPT=gui.py"
set "ICON_FILE=icon.ico" REM Windows 使用 .ico

REM 清理旧的构建文件
echo 清理旧的构建文件...
if exist "%PROJECT_ROOT%\build" rmdir /s /q "%PROJECT_ROOT%\build"
if exist "%PROJECT_ROOT%\dist" rmdir /s /q "%PROJECT_ROOT%\dist"
if exist "%PROJECT_ROOT%\%APP_NAME%.spec" del "%PROJECT_ROOT%\%APP_NAME%.spec"

REM 创建虚拟环境 (可选但推荐)
set "VENV_DIR=%PROJECT_ROOT%\venv_win"
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo 创建虚拟环境...
    python -m venv "%VENV_DIR%"
)

echo 激活虚拟环境...
call "%VENV_DIR%\Scripts\activate.bat"

REM 安装依赖
echo 安装依赖...
python -m pip install --upgrade pip
python -m pip install -r "%PROJECT_ROOT%\requirements.txt"
python -m pip install pyinstaller

REM 运行 PyInstaller
echo 开始打包 Windows 应用程序...
pyinstaller --noconfirm ^
    --name "%APP_NAME%" ^
    --onedir ^
    --windowed ^
    --icon "%PROJECT_ROOT%\%ICON_FILE%" ^
    --add-data "%PROJECT_ROOT%\manga;manga" ^
    --add-data "%PROJECT_ROOT%\novel;novel" ^
    --add-data "%PROJECT_ROOT%\novel_cache;novel_cache" ^
    --add-data "%PROJECT_ROOT%\%ICON_FILE%;." ^
    --add-data "%PROJECT_ROOT%\icon.icns;." ^
    --hidden-import "PIL._tkinter_finder" ^
    --hidden-import "PyQt6.sip" ^
    --hidden-import "PyQt6.QtGui" ^
    --hidden-import "PyQt6.QtWidgets" ^
    --hidden-import "PyQt6.QtCore" ^
    --distpath "%OUTPUT_DIR%" ^
    "%PROJECT_ROOT%\%MAIN_SCRIPT%"

REM 检查打包是否成功
if exist "%OUTPUT_DIR%\%APP_NAME%\%APP_NAME%.exe" (
    echo Windows 应用程序打包成功！
    echo 输出目录: %OUTPUT_DIR%
) else (
    echo Windows 应用程序打包失败。
    REM 退出虚拟环境
    call "%VENV_DIR%\Scripts\deactivate.bat"
    exit /b 1
)

REM 退出虚拟环境
call "%VENV_DIR%\Scripts\deactivate.bat"

echo 脚本执行完毕。
endlocal 