#!/bin/bash

# 脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
OUTPUT_DIR="$PROJECT_ROOT/dist/mac"
APP_NAME="漫画小说下载器"
MAIN_SCRIPT="gui.py"
ICON_FILE="icon.icns" # macOS 使用 .icns

# 清理旧的构建文件
echo "清理旧的构建文件..."
rm -rf "$PROJECT_ROOT/build"
rm -rf "$PROJECT_ROOT/dist"
rm -f "$PROJECT_ROOT/$APP_NAME.spec"

# 创建虚拟环境 (可选但推荐)
VENV_DIR="$PROJECT_ROOT/venv_mac"
if [ ! -d "$VENV_DIR" ]; then
    echo "创建虚拟环境..."
    python3 -m venv "$VENV_DIR"
fi

echo "激活虚拟环境..."
source "$VENV_DIR/bin/activate"

# 安装依赖
echo "安装依赖..."
pip install --upgrade pip
pip install -r "$PROJECT_ROOT/requirements.txt"
pip install pyinstaller

# 运行 PyInstaller
echo "开始打包 macOS 应用程序..."
pyinstaller --noconfirm \
    --name "$APP_NAME" \
    --onedir \
    --windowed \
    --icon "$PROJECT_ROOT/$ICON_FILE" \
    --add-data "$PROJECT_ROOT/$ICON_FILE:." \
    --add-data "$PROJECT_ROOT/icon.ico:." \
    --hidden-import "PIL._tkinter_finder" \
    --hidden-import "PyQt6.sip" \
    --hidden-import "PyQt6.QtGui" \
    --hidden-import "PyQt6.QtWidgets" \
    --hidden-import "PyQt6.QtCore" \
    --exclude-module "matplotlib" \
    --exclude-module "numpy" \
    --exclude-module "pandas" \
    --distpath "$OUTPUT_DIR" \
    "$PROJECT_ROOT/$MAIN_SCRIPT"

# 检查打包是否成功
if [ -f "$OUTPUT_DIR/$APP_NAME.app/$APP_NAME" ] || [ -f "$OUTPUT_DIR/$APP_NAME" ]; then
    echo "macOS 应用程序打包成功！"
    echo "输出目录: $OUTPUT_DIR"
else
    echo "macOS 应用程序打包失败。"
    # 退出虚拟环境
    deactivate
    exit 1
fi

# 退出虚拟环境
deactivate

echo "脚本执行完毕。" 