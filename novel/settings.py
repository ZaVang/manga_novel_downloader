import json
import os
import novel.config as config
from utils import get_app_base_dir


def save_settings(settings):
    settings_path = os.path.join(get_app_base_dir(), "novel_settings.json")
    # 写入settings.json文件
    with open(settings_path, "w") as f:
        json.dump(settings, f)


def load_settings():
    # 获取用户目录的路径
    settings_path = os.path.join(get_app_base_dir(), "novel_settings.json")
    # 检查是否有文件
    if not os.path.exists(settings_path):
        return False, "settings.json文件不存在"
    # 读取json配置文件
    with open(settings_path, 'r') as f:
        settings = json.load(f)

    config.SETTINGS = settings
    return True, "novel_settings.json文件加载成功"
