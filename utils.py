import sys
import os
from pathlib import Path

def get_app_base_dir():
    """获取合适的缓存目录"""
    if sys.platform == 'darwin':  # macOS
        # 使用标准的应用缓存位置
        cache_base = Path.home() / 'Downloads' / 'manga_and_novel'
    elif sys.platform == 'win32':  # Windows
        # 使用应用数据目录
        cache_base = Path.cwd() / 'manga_and_novel'
    else:  # Linux
        cache_base = Path.home() / 'Documents' / 'manga_and_novel'
    
    cache_base.mkdir(parents=True, exist_ok=True)
    return cache_base