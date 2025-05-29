import json
import os
import manga.config as config
from utils import get_app_base_dir


def save_settings(settings):
    settings_path = os.path.join(get_app_base_dir(), "manga_settings.json")
    # 写入settings.json文件
    with open(settings_path, "w") as f:
        json.dump(settings, f)


def load_settings():
    # 获取用户目录的路径
    settings_path = os.path.join(get_app_base_dir(), "manga_settings.json")
    # 检查是否有文件
    if not os.path.exists(settings_path):
        return False, "settings.json文件不存在"
    # 读取json配置文件
    with open(settings_path, 'r') as f:
        settings = json.load(f)

    # 判断必要的字段是否存在
    necessary_fields = ["download_path", "authorization", "use_oversea_cdn", "use_webp", "proxies", "api_url",
                        "loginPattern"]
    for field in necessary_fields:
        if field not in settings:
            return False, "settings.json中缺少必要字段{}".format(field)
    config.SETTINGS = settings
    # if "HC" not in settings:
    #     config.SETTINGS['HC'] = None
    #     print("[bold yellow]我们更新了设置，请您按照需求重新设置一下，还请谅解[/]")
    #     change_settings()
    #     print("[bold yellow]感谢您的支持，重新启动本程序后新的设置将会生效[/]")
    #     exit(0)
    config.OG_SETTINGS = settings
    # 设置请求头
    config.API_HEADER['use_oversea_cdn'] = settings['use_oversea_cdn']
    config.API_HEADER['use_webp'] = settings['use_webp']
    if 'UA' in settings:
        config.API_HEADER['User-Agent'] = settings['UA']
    # 设置代理
    if settings["proxies"]:
        config.PROXIES = {
            "http": settings["proxies"],
            "https": settings["proxies"]
        }
    return True, "manga_settings.json文件加载成功"
