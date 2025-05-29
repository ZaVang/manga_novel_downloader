import datetime
from utils import get_app_base_dir

SETTINGS = {
    'username': '2497360927',
    'password': 'testtest',
    'output_dir': str(get_app_base_dir() / "novel_downloads"),
    'output_epub_dir': str(get_app_base_dir() / "novel_downloads"),
    'max_retries': 3,
    'auto_login': True  # 默认自动登录
}