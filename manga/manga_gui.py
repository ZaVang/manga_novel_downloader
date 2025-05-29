import sys
import os
import shutil
import re
import requests
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget, 
                             QMenuBar, QStatusBar, QLineEdit, QPushButton, QListWidget, QTabWidget,
                             QGroupBox, QFormLayout, QSpinBox, QCheckBox, QComboBox, QFileDialog,
                             QListWidgetItem, QTextEdit, QProgressBar, QMessageBox, QDialog,
                             QDialogButtonBox, QTreeWidget, QTreeWidgetItem, QRadioButton
)
from PyQt6.QtGui import QAction, QPixmap
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QTimer
from utils import get_app_base_dir


import manga.config as config
from manga.settings import load_settings, save_settings
load_success, load_msg = load_settings()
print(load_msg)

INITIAL_SETTINGS = config.SETTINGS.copy() if hasattr(config, 'SETTINGS') and config.SETTINGS else {}
INITIAL_API_HEADER = config.API_HEADER.copy() if hasattr(config, 'API_HEADER') and config.API_HEADER else {}
INITIAL_PROXIES = config.PROXIES.copy() if hasattr(config, 'PROXIES') and config.PROXIES else {}

def ensure_gui_defaults(settings_dict):
    defaults = {
        'download_path': str(get_app_base_dir() / "manga_downloads"), 
        'export_path': str(get_app_base_dir() / "manga_downloads"), 
        'api_url': "copymanga.site",
        'epub_filename_prefix': "",
        'epub_language': "zh-CN",
        'epub_target_width': 0,
        'epub_target_height': 0,
        'epub_create_title_page': True,
        'epub_auto_delete_source': False,
        'use_webp': "1",
        'use_oversea_cdn': "0",
        'proxies': "",
        'max_concurrent_downloads': 3, # New setting for download concurrency
        'auto_create_epub_after_download': False # New setting for auto EPUB
    }
    for key, value in defaults.items():
        settings_dict.setdefault(key, value)

ensure_gui_defaults(INITIAL_SETTINGS)

# Convert string "0"/"1" to bool for specific header-like items for easier GUI use internally
_initial_use_webp_bool = INITIAL_SETTINGS.get('use_webp') == "1"
_initial_use_oscdn_bool = INITIAL_SETTINGS.get('use_oversea_cdn') == "1"

# Import the EPUB generation utility
try:
    from manga.epub_utils import generate_epub_from_folder_content
except ImportError:
    print("Error: epub_utils.py not found. EPUB generation will not work.")
    def generate_epub_from_folder_content(*args, **kwargs):
        print("Dummy generate_epub_from_folder_content called.")
        return False


def parse_chapter_range(range_text, max_chapters):
    """
    解析章节范围字符串，返回章节索引列表
    
    支持的格式：
    - "0-5" -> [0, 1, 2, 3, 4, 5]
    - "1,3,5" -> [1, 3, 5] 
    - "0-2,5,7-9" -> [0, 1, 2, 5, 7, 8, 9]
    
    Args:
        range_text: 范围字符串
        max_chapters: 最大章节数
        
    Returns:
        list: 章节索引列表，失败返回None
    """
    if not range_text.strip():
        return None
        
    try:
        chapter_indices = set()
        
        # 按逗号分割
        parts = [part.strip() for part in range_text.split(',')]
        
        for part in parts:
            if '-' in part:
                # 处理范围，如 "0-5"
                range_parts = part.split('-')
                if len(range_parts) != 2:
                    return None
                    
                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())
                
                if start > end:
                    return None
                    
                for i in range(start, end + 1):
                    if 0 <= i < max_chapters:
                        chapter_indices.add(i)
            else:
                # 处理单个数字
                index = int(part.strip())
                if 0 <= index < max_chapters:
                    chapter_indices.add(index)
        
        return sorted(list(chapter_indices))
        
    except ValueError:
        return None


class NetworkWorker(QThread):
    search_complete = pyqtSignal(list)
    chapters_ready = pyqtSignal(list, str)
    cover_ready = pyqtSignal(QPixmap, str)
    error = pyqtSignal(str, str)
    def __init__(self, query=None, cover_url=None, chapter_request_info=None, api_url_base=None, headers=None, proxies=None):
        super().__init__()
        self.query, self.cover_url, self.chapter_request_info = query, cover_url, chapter_request_info
        self.api_url_base, self.headers, self.proxies = api_url_base, headers or {}, proxies or {}
    def run(self):
        if self.query and self.api_url_base:
            search_url = f"https://api.{self.api_url_base}/api/v3/search/comic"
            params = {"format": "json", "platform": 3, "q": self.query, "limit": 30, "offset": 0}
            try:
                r = requests.get(search_url, params=params, headers=self.headers, proxies=self.proxies, timeout=10)
                r.raise_for_status()
                data = r.json()
                if data.get("code") == 200 and "results" in data and "list" in data["results"]: self.search_complete.emit(data["results"]["list"])
                else: self.error.emit(f"API Error: {data.get('message', 'Unknown error')}", "search")
            except Exception as e: self.error.emit(f"Network/JSON Error: {e}", "search")
        elif self.chapter_request_info and self.api_url_base:
            path_word = self.chapter_request_info['path_word']
            group = self.chapter_request_info.get('group', 'default')
            chapters_url = f"https://api.{self.api_url_base}/api/v3/comic/{path_word}/group/{group}/chapters"
            params = {"limit": 500, "offset": 0, "platform": 3}
            try:
                r = requests.get(chapters_url, params=params, headers=self.headers, proxies=self.proxies, timeout=15)
                r.raise_for_status()
                data = r.json()
                if data.get("code") == 200 and "results" in data and "list" in data["results"]: self.chapters_ready.emit(data["results"]["list"], path_word)
                else: self.error.emit(f"API Error: {data.get('message', 'Unknown error')}", "chapters")
            except Exception as e: self.error.emit(f"Network/JSON Error: {e}", "chapters")
        elif self.cover_url:
            try:
                r = requests.get(self.cover_url, headers=self.headers, proxies=self.proxies, timeout=10, stream=True)
                r.raise_for_status()
                pixmap = QPixmap()
                if pixmap.loadFromData(r.content):
                    self.cover_ready.emit(pixmap, self.cover_url)
                else:
                    self.error.emit("Error: Could not load cover image data.", "cover")
            except Exception as e:
                self.error.emit(f"Network/Pixmap Error for {self.cover_url}: {e}", "cover")

class DownloadWorker(QThread):
    progress_update = pyqtSignal(str, int, int)
    chapter_complete = pyqtSignal(str, str, str, bool)
    error = pyqtSignal(str, str, str)
    def __init__(self, manga_name, manga_path_word, chapter_data, download_root_path, api_url_base, headers, proxies, parent=None):
        super().__init__(parent)
        self.manga_name = manga_name; self.manga_path_word = manga_path_word; self.chapter_data = chapter_data
        self.download_root_path = download_root_path; self.api_url_base = api_url_base; self.headers = headers; self.proxies = proxies
        self.is_cancelled = False
    def run(self):
        chapter_uuid = self.chapter_data.get("uuid"); chapter_name_sanitized = re.sub(r'[\\/*?"<>|]', "_", self.chapter_data.get("name", f"Chapter_{chapter_uuid}"))
        manga_name_sanitized = re.sub(r'[\\/*?"<>|]', "_", self.manga_name); chapter_download_path = os.path.join(self.download_root_path, manga_name_sanitized, chapter_name_sanitized)
        os.makedirs(chapter_download_path, exist_ok=True)
        content_url = f"https://api.{self.api_url_base}/api/v3/comic/{self.manga_path_word}/chapter/{chapter_uuid}"
        params = {"platform": 3}; image_urls = []
        try:
            response = requests.get(content_url, params=params, headers=self.headers, proxies=self.proxies, timeout=15)
            response.raise_for_status()
            content_data = response.json()
            if content_data.get("code") == 200 and "results" in content_data and "chapter" in content_data["results"]:
                image_urls = [img["url"] for img in content_data["results"]["chapter"]["contents"]]
            else: self.error.emit(chapter_uuid, chapter_name_sanitized, f"API Error: {content_data.get('message')}"), self.chapter_complete.emit(chapter_uuid, chapter_name_sanitized, chapter_download_path, False); return
        except Exception as e: self.error.emit(chapter_uuid, chapter_name_sanitized, f"Net error img list: {e}"); self.chapter_complete.emit(chapter_uuid, chapter_name_sanitized, chapter_download_path, False); return
        if not image_urls: self.error.emit(chapter_uuid, chapter_name_sanitized, "No image URLs."), self.chapter_complete.emit(chapter_uuid, chapter_name_sanitized, chapter_download_path, False); return
        total_pages = len(image_urls)
        for i, img_url in enumerate(image_urls):
            if self.is_cancelled: self.chapter_complete.emit(chapter_uuid, chapter_name_sanitized, chapter_download_path, False); return
            page_num = i + 1; _, ext = os.path.splitext(QUrl(img_url).path()); ext = ext or ".jpg"; ext = ext.split('?')[0] if '?' in ext else ext; ext = ".jpg" if len(ext) > 5 else ext
            filename = os.path.join(chapter_download_path, f"{page_num:03d}{ext}")
            try:
                img_response = requests.get(img_url, headers=self.headers, proxies=self.proxies, timeout=20, stream=True); img_response.raise_for_status()
                with open(filename, 'wb') as f: f.write(img_response.content)
                self.progress_update.emit(chapter_uuid, page_num, total_pages)
            except Exception as e: self.error.emit(chapter_uuid, chapter_name_sanitized, f"Page {page_num} DL fail: {e}")
        self.chapter_complete.emit(chapter_uuid, chapter_name_sanitized, chapter_download_path, True)
    def cancel(self): self.is_cancelled = True

class ExportWorker(QThread):
    finished = pyqtSignal(bool, str, str); progress = pyqtSignal(str)
    def __init__(self, source_folder, export_format, epub_output_path, epub_params, auto_delete_setting):
        super().__init__(); self.source_folder, self.export_format, self.epub_output_path = source_folder, export_format, epub_output_path
        self.epub_params, self.auto_delete_source = epub_params, auto_delete_setting
    def run(self):
        if self.export_format == "EPUB":
            try:
                self.progress.emit(f"开始导出EPUB: {os.path.basename(self.epub_output_path)}...")
                success = generate_epub_from_folder_content(source_folder_path=self.source_folder, output_epub_full_path=self.epub_output_path, **self.epub_params)
                if success:
                    msg, source_to_delete_for_signal = f"成功导出到 {self.epub_output_path}", ""
                    if self.auto_delete_source:
                        try: shutil.rmtree(self.source_folder); msg += " 并已删除源文件夹。"; source_to_delete_for_signal = self.source_folder
                        except Exception as e: msg += f" 但删除源文件夹失败: {e}"
                    self.finished.emit(True, msg, source_to_delete_for_signal)
                else: self.finished.emit(False, "EPUB 导出失败。请查看控制台日志。", "")
            except Exception as e: import traceback; self.progress.emit(f"导出EPUB时发生严重错误: {e}"); traceback.print_exc(); self.finished.emit(False, f"EPUB 导出时发生严重错误: {e}", "")
        else: self.finished.emit(False, f"不支持的导出格式: {self.export_format}", "")

class ChapterInfoDialog(QDialog):
    """章节信息对话框"""
    def __init__(self, manga_data, chapters, parent=None):
        super().__init__(parent)
        self.manga_data = manga_data
        self.chapters = chapters
        self.selected_chapter_indices = []
        self.download_type = None  # 'all', 'selected', 'range'
        
        manga_name = manga_data.get("name", "未知漫画")
        self.setWindowTitle(f"《{manga_name}》章节信息")
        self.setMinimumSize(700, 600)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 漫画信息
        info_group = QGroupBox("漫画信息")
        info_layout = QFormLayout()
        info_layout.addRow("标题:", QLabel(self.manga_data.get("name", "未知漫画")))
        authors = self.manga_data.get("author", [])
        author_str = ", ".join([a.get("name","") for a in authors]) if isinstance(authors,list) and authors else "未知"
        info_layout.addRow("作者:", QLabel(author_str))
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # 章节列表
        chapters_group = QGroupBox("章节信息")
        chapters_layout = QVBoxLayout()
        
        self.chapter_tree = QTreeWidget()
        self.chapter_tree.setHeaderLabels(["章节名称"])
        self.chapter_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        
        for i, chapter in enumerate(self.chapters):
            item = QTreeWidgetItem([f"{i+1:03d}. {chapter.get('name', '未知章节')}"])
            item.setData(0, Qt.ItemDataRole.UserRole, i)  # 存储章节索引
            self.chapter_tree.addTopLevelItem(item)
        
        chapters_layout.addWidget(self.chapter_tree)
        
        # 统计信息
        stats_label = QLabel(f"总计: {len(self.chapters)} 章节")
        stats_label.setStyleSheet("font-weight: bold; color: #666;")
        chapters_layout.addWidget(stats_label)
        
        chapters_group.setLayout(chapters_layout)
        layout.addWidget(chapters_group)
        
        # 下载选项
        download_group = QGroupBox("下载选项")
        download_layout = QVBoxLayout()
        
        self.all_download_radio = QRadioButton("下载全部章节")
        self.all_download_radio.setChecked(True)
        self.selected_download_radio = QRadioButton("下载选中的章节")
        self.range_download_radio = QRadioButton("按范围下载")
        
        download_layout.addWidget(self.all_download_radio)
        download_layout.addWidget(self.selected_download_radio)
        download_layout.addWidget(self.range_download_radio)
        
        # 范围输入框
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("  范围 (例: 0-5,10 表示第1-6章和第11章):"))
        self.range_input = QLineEdit()
        self.range_input.setPlaceholderText("例如: 0-5 或 1,3,5 或 0-2,8-10")
        self.range_input.setEnabled(False)
        range_layout.addWidget(self.range_input)
        download_layout.addLayout(range_layout)
        
        # 范围说明
        range_help = QLabel("  说明: 章节编号从0开始，0表示第1章，1表示第2章，以此类推")
        range_help.setStyleSheet("color: #666; font-style: italic;")
        download_layout.addWidget(range_help)
        
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        self.add_to_queue_button = QPushButton("添加到下载队列")
        self.add_to_queue_button.clicked.connect(self.add_to_queue)
        
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.add_to_queue_button)
        button_layout.addWidget(cancel_button)
        button_layout.addStretch()
        
        layout.addWidget(QWidget())  # 添加间隔
        layout.addLayout(button_layout)
        
        # 连接信号
        self.chapter_tree.itemSelectionChanged.connect(self.on_selection_changed)
        self.range_download_radio.toggled.connect(self.on_range_radio_toggled)
        self.range_input.textChanged.connect(self.validate_range_input)
    
    def on_selection_changed(self):
        """处理选择变化"""
        selected_items = self.chapter_tree.selectedItems()
        if selected_items:
            self.selected_download_radio.setEnabled(True)
            self.selected_chapter_indices = [item.data(0, Qt.ItemDataRole.UserRole) for item in selected_items]
            # 自动选择多选模式并设置范围
            if len(selected_items) > 1:
                self.selected_download_radio.setChecked(True)
                # 生成范围字符串
                indices = sorted(self.selected_chapter_indices)
                range_str = self._indices_to_range_string(indices)
                self.range_input.setText(range_str)
            elif len(selected_items) == 1:
                self.selected_download_radio.setChecked(True)
                self.range_input.setText(str(self.selected_chapter_indices[0]))
        else:
            self.selected_download_radio.setEnabled(False)
            self.selected_chapter_indices = []
    
    def _indices_to_range_string(self, indices):
        """将索引列表转换为范围字符串"""
        if not indices:
            return ""
        
        indices = sorted(set(indices))
        ranges = []
        start = indices[0]
        end = indices[0]
        
        for i in range(1, len(indices)):
            if indices[i] == end + 1:
                end = indices[i]
            else:
                if start == end:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{end}")
                start = end = indices[i]
        
        # 处理最后一个范围
        if start == end:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{end}")
        
        return ",".join(ranges)
    
    def on_range_radio_toggled(self, checked):
        """处理范围单选按钮切换"""
        self.range_input.setEnabled(checked)
        if checked:
            self.range_input.setFocus()
    
    def validate_range_input(self):
        """验证范围输入"""
        if not self.range_download_radio.isChecked():
            return
            
        range_text = self.range_input.text().strip()
        if not range_text:
            self.range_input.setStyleSheet("")
            return
            
        indices = parse_chapter_range(range_text, len(self.chapters))
        if indices is not None:
            self.range_input.setStyleSheet("color: green;")
            # 在树形控件中高亮选中的章节
            self.highlight_selected_chapters(indices)
        else:
            self.range_input.setStyleSheet("color: red;")
            self.clear_chapter_highlights()
    
    def highlight_selected_chapters(self, indices):
        """高亮选中的章节"""
        self.clear_chapter_highlights()
        
        for i in range(self.chapter_tree.topLevelItemCount()):
            item = self.chapter_tree.topLevelItem(i)
            chapter_index = item.data(0, Qt.ItemDataRole.UserRole)
            
            if chapter_index in indices:
                # 设置背景色为浅蓝色
                item.setBackground(0, Qt.GlobalColor.lightGray)
    
    def clear_chapter_highlights(self):
        """清除章节的高亮"""
        for i in range(self.chapter_tree.topLevelItemCount()):
            item = self.chapter_tree.topLevelItem(i)
            item.setBackground(0, Qt.GlobalColor.white)
    
    def get_selected_options(self):
        """获取选择的下载选项"""
        if self.all_download_radio.isChecked():
            return 'all', list(range(len(self.chapters)))
        elif self.selected_download_radio.isChecked() and self.selected_chapter_indices:
            return 'selected', self.selected_chapter_indices
        elif self.range_download_radio.isChecked():
            range_text = self.range_input.text().strip()
            indices = parse_chapter_range(range_text, len(self.chapters))
            if indices:
                return 'range', indices
            return None, []
        
        return None, []
    
    def add_to_queue(self):
        """添加到下载队列"""
        download_type, chapter_indices = self.get_selected_options()
        
        if download_type is None or not chapter_indices:
            QMessageBox.warning(self, "选择错误", "请选择有效的下载选项")
            return
        
        self.download_type = download_type
        self.selected_chapter_indices = chapter_indices
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("拷贝漫画下载器")
        self.setGeometry(100, 100, 1200, 800)
        self.export_worker = None
        self.main_network_worker = None
        self.cover_fetch_workers = {}
        self.current_manga_chapters_data = {}
        self.current_search_results_map = {}
        self.results_list_context = "manga_search"
        self.current_manga_for_chapters_path_word = None
        
        self.download_queue = []
        self.active_download_workers = {}
        self.max_concurrent_downloads = INITIAL_SETTINGS.get('max_concurrent_downloads', 3)
        
        self._create_menu_bar()
        self._create_status_bar()
        self._init_ui()
        self._load_app_settings()

    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&文件")
        settings_action = QAction("设置", self); settings_action.triggered.connect(self.open_settings_tab); file_menu.addAction(settings_action)
        exit_action = QAction("退出", self); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)
        action_menu = menu_bar.addMenu("&操作")
        search_action = QAction("搜索漫画", self); search_action.triggered.connect(self.focus_search_and_open_downloader_tab); action_menu.addAction(search_action)

    def _create_status_bar(self): self.statusBar = QStatusBar(); self.setStatusBar(self.statusBar); self.statusBar.showMessage("准备就绪")

    def _init_ui(self):
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)
        
        self.downloader_tab = QWidget()
        self.tab_widget.addTab(self.downloader_tab, "下载器")
        self._setup_downloader_tab()
        
        # 下载队列标签页
        self.queue_tab = QWidget()
        self.tab_widget.addTab(self.queue_tab, "下载队列")
        self._setup_queue_tab()
        
        self.export_tab = QWidget()
        self.tab_widget.addTab(self.export_tab, "EPUB 导出")
        self._setup_export_tab()
        
        self.settings_tab = QWidget()
        self.tab_widget.addTab(self.settings_tab, "设置")
        self._setup_settings_tab()

    def _load_app_settings(self):
        self.download_destination_edit.setText(INITIAL_SETTINGS.get('download_path'))
        self.export_destination_edit.setText(INITIAL_SETTINGS.get('export_path'))
        self.api_url_edit.setText(INITIAL_SETTINGS.get('api_url'))
        self.use_webp_checkbox.setChecked(_initial_use_webp_bool)
        self.use_oscdn_checkbox.setChecked(_initial_use_oscdn_bool)
        self.proxy_edit.setText(INITIAL_SETTINGS.get('proxies'))
        self.epub_filename_prefix_edit.setText(INITIAL_SETTINGS.get('epub_filename_prefix'))
        common_langs = ["zh-CN", "zh-TW", "en", "ja"]
        lang_to_set = INITIAL_SETTINGS.get('epub_language')
        if lang_to_set not in common_langs: common_langs.insert(0, lang_to_set)
        self.epub_language_combo.clear(); self.epub_language_combo.addItems(common_langs); self.epub_language_combo.setCurrentText(lang_to_set)
        self.epub_custom_width_spinbox.setValue(INITIAL_SETTINGS.get('epub_target_width'))
        self.epub_custom_height_spinbox.setValue(INITIAL_SETTINGS.get('epub_target_height'))
        self.epub_include_title_page_checkbox.setChecked(INITIAL_SETTINGS.get('epub_create_title_page'))
        self.epub_auto_delete_source_checkbox.setChecked(INITIAL_SETTINGS.get('epub_auto_delete_source', False))
        self.max_concurrent_downloads_spinbox.setValue(INITIAL_SETTINGS.get('max_concurrent_downloads', 3))
        self.auto_create_epub_checkbox.setChecked(INITIAL_SETTINGS.get('auto_create_epub_after_download', False))
        self.statusBar.showMessage("设置已加载", 2000)

    def _save_app_settings(self):
        gui_settings_map = {
            "download_path": self.download_destination_edit.text(), "export_path": self.export_destination_edit.text(),
            "api_url": self.api_url_edit.text(), "use_webp": "1" if self.use_webp_checkbox.isChecked() else "0",
            "use_oversea_cdn": "1" if self.use_oscdn_checkbox.isChecked() else "0", "proxies": self.proxy_edit.text() or "",
            "epub_filename_prefix": self.epub_filename_prefix_edit.text(), "epub_language": self.epub_language_combo.currentText(),
            "epub_target_width": self.epub_custom_width_spinbox.value(), "epub_target_height": self.epub_custom_height_spinbox.value(),
            "epub_create_title_page": self.epub_include_title_page_checkbox.isChecked(),
            "epub_auto_delete_source": self.epub_auto_delete_source_checkbox.isChecked(),
            "max_concurrent_downloads": self.max_concurrent_downloads_spinbox.value(),
            "auto_create_epub_after_download": self.auto_create_epub_checkbox.isChecked()
        }
        settings_to_save = config.SETTINGS.copy(); settings_to_save.update(gui_settings_map)
        try:
            save_settings(settings_to_save); config.SETTINGS.clear(); config.SETTINGS.update(settings_to_save)
            if hasattr(config, 'API_HEADER'): config.API_HEADER['use_oversea_cdn'] = settings_to_save.get('use_oversea_cdn'); config.API_HEADER['use_webp'] = settings_to_save.get('use_webp')
            if hasattr(config, 'PROXIES'): proxy_str = settings_to_save.get('proxies'); config.PROXIES.clear(); config.PROXIES.update({'http':proxy_str, 'https':proxy_str} if proxy_str else {})
            INITIAL_SETTINGS.clear(); INITIAL_SETTINGS.update(config.SETTINGS)
            global _initial_use_webp_bool, _initial_use_oscdn_bool
            _initial_use_webp_bool = INITIAL_SETTINGS.get('use_webp') == "1"; _initial_use_oscdn_bool = INITIAL_SETTINGS.get('use_oversea_cdn') == "1"
            self.max_concurrent_downloads = INITIAL_SETTINGS.get('max_concurrent_downloads')
            self.statusBar.showMessage("设置已成功保存到文件!", 5000)
        except Exception as e: self.statusBar.showMessage(f"错误: 保存设置失败: {e}", 8000); print(f"Error: {e}"); import traceback; traceback.print_exc()

    def _setup_downloader_tab(self):
        layout = QVBoxLayout(self.downloader_tab)
        
        search_group = QGroupBox("漫画搜索")
        search_layout = QHBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入漫画名称...")
        self.search_input.returnPressed.connect(self._trigger_search)
        
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self._trigger_search)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        
        search_group.setLayout(search_layout)
        layout.addWidget(search_group)
        
        middle_layout = QHBoxLayout()
        
        self.results_group_box = QGroupBox("搜索结果 (双击漫画查看章节)") 
        results_v_layout = QVBoxLayout()
        
        self.results_list_widget = QListWidget()
        self.results_list_widget.currentItemChanged.connect(self._handle_results_list_selection_changed)
        self.results_list_widget.itemDoubleClicked.connect(self._handle_results_list_double_click)
        
        results_v_layout.addWidget(self.results_list_widget)
        self.results_group_box.setLayout(results_v_layout)
        middle_layout.addWidget(self.results_group_box, 2)

        details_group = QGroupBox("漫画详情")
        details_v_layout = QVBoxLayout()
        
        self.manga_cover_label = QLabel("封面图片")
        self.manga_cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.manga_cover_label.setMinimumSize(200,280)
        self.manga_cover_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
        
        self.manga_title_label = QLabel("标题")
        self.manga_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.manga_title_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        
        self.manga_author_label = QLabel("作者: 未知")
        
        self.manga_description_text = QLabel("简介将显示在此处...")
        self.manga_description_text.setWordWrap(True)
        self.manga_description_text.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        details_v_layout.addWidget(self.manga_cover_label)
        details_v_layout.addWidget(self.manga_title_label) 
        details_v_layout.addWidget(self.manga_author_label) 
        details_v_layout.addWidget(self.manga_description_text, 1)
        
        details_group.setLayout(details_v_layout)
        middle_layout.addWidget(details_group, 1)
        
        layout.addLayout(middle_layout)
        
        # 下载目标路径
        dl_dest_group = QGroupBox("下载设置")
        dl_dest_layout = QFormLayout()
        
        dl_path_layout = QHBoxLayout()
        self.download_destination_edit = QLineEdit()
        self.browse_download_destination_button = QPushButton("浏览...")
        self.browse_download_destination_button.clicked.connect(self._browse_download_destination)
        
        dl_path_layout.addWidget(self.download_destination_edit)
        dl_path_layout.addWidget(self.browse_download_destination_button)
        
        dl_dest_layout.addRow("下载目标路径:", dl_path_layout)
        dl_dest_group.setLayout(dl_dest_layout)
        
        layout.addWidget(dl_dest_group)

    def _setup_queue_tab(self):
        layout = QVBoxLayout(self.queue_tab)
        
        # 队列控制
        queue_control_group = QGroupBox("队列控制")
        queue_control_layout = QHBoxLayout()
        
        self.start_queue_button = QPushButton("开始队列下载")
        self.start_queue_button.clicked.connect(self._start_queue_download)
        
        self.pause_queue_button = QPushButton("暂停下载")
        self.pause_queue_button.clicked.connect(self._pause_download)
        self.pause_queue_button.setEnabled(False)
        
        self.clear_queue_button = QPushButton("清空队列")
        self.clear_queue_button.clicked.connect(self._clear_queue)
        
        queue_control_layout.addWidget(self.start_queue_button)
        queue_control_layout.addWidget(self.pause_queue_button)
        queue_control_layout.addWidget(self.clear_queue_button)
        queue_control_layout.addStretch()
        
        queue_control_group.setLayout(queue_control_layout)
        layout.addWidget(queue_control_group)
        
        # 下载队列列表
        queue_list_group = QGroupBox("下载队列")
        queue_list_layout = QVBoxLayout()
        
        self.queue_list = QListWidget()
        
        queue_list_layout.addWidget(self.queue_list)
        queue_list_group.setLayout(queue_list_layout)
        layout.addWidget(queue_list_group)
        
        # 下载进度
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout()
        
        self.current_download_label = QLabel("当前下载: 无")
        self.download_progress_bar = QProgressBar()
        self.download_status_text = QTextEdit()
        self.download_status_text.setMaximumHeight(150)
        self.download_status_text.setReadOnly(True)
        
        progress_layout.addWidget(self.current_download_label)
        progress_layout.addWidget(self.download_progress_bar)
        progress_layout.addWidget(QLabel("下载日志:"))
        progress_layout.addWidget(self.download_status_text)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

    def _setup_export_tab(self):
        layout = QVBoxLayout(self.export_tab); export_controls_group = QGroupBox("EPUB 导出控制"); ec_layout = QFormLayout()
        export_dest_layout = QHBoxLayout(); self.export_destination_edit = QLineEdit(); self.browse_export_destination_button = QPushButton("浏览..."); self.browse_export_destination_button.clicked.connect(self._browse_export_destination)
        export_dest_layout.addWidget(self.export_destination_edit); export_dest_layout.addWidget(self.browse_export_destination_button); ec_layout.addRow("导出目标路径:", export_dest_layout)
        self.export_format_label = QLabel("导出格式:"); self.export_format_value = QLabel("EPUB"); ef_layout = QHBoxLayout(); ef_layout.addWidget(self.export_format_label); ef_layout.addWidget(self.export_format_value); ef_layout.addStretch(); ec_layout.addRow(ef_layout)
        self.epub_filename_prefix_edit = QLineEdit(); ec_layout.addRow("EPUB 文件名前缀（可选）:", self.epub_filename_prefix_edit)
        self.epub_auto_delete_source_checkbox = QCheckBox("自动删除源文件 (导出成功后)"); ec_layout.addRow(self.epub_auto_delete_source_checkbox)
        source_folder_layout = QHBoxLayout(); self.export_source_folder_edit = QLineEdit(); self.browse_export_source_button = QPushButton("浏览..."); self.browse_export_source_button.clicked.connect(self._browse_for_export_source_folder)
        source_folder_layout.addWidget(self.export_source_folder_edit); source_folder_layout.addWidget(self.browse_export_source_button); ec_layout.addRow("导出源文件夹:", source_folder_layout)
        
        export_info_label = QLabel("将选定的漫画文件夹导出为EPUB格式，如果文件夹内有多个子文件夹则会一起打包所有章节到一个文件")
        export_info_label.setWordWrap(True)
        export_info_label.setStyleSheet("color: gray; font-size: 10pt;")
        ec_layout.addRow(export_info_label)
        self.start_export_button = QPushButton("开始导出")
        self.start_export_button.clicked.connect(self._handle_export)
        ec_layout.addRow(self.start_export_button)
        export_controls_group.setLayout(ec_layout); layout.addWidget(export_controls_group); layout.addStretch()

    def _setup_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab); program_settings_group = QGroupBox("常规设置"); program_form_layout = QFormLayout()
        self.api_url_edit = QLineEdit(); program_form_layout.addRow("API 域名:", self.api_url_edit)
        self.use_webp_checkbox = QCheckBox("使用 WebP"); program_form_layout.addRow(self.use_webp_checkbox)
        self.use_oscdn_checkbox = QCheckBox("使用海外 CDN"); program_form_layout.addRow(self.use_oscdn_checkbox)
        self.proxy_edit = QLineEdit(); self.proxy_edit.setPlaceholderText("例如: http://127.0.0.1:7890"); program_form_layout.addRow("HTTP(S) 代理:", self.proxy_edit)
        self.max_concurrent_downloads_spinbox = QSpinBox(); self.max_concurrent_downloads_spinbox.setRange(1, 10); program_form_layout.addRow("同时下载任务数:", self.max_concurrent_downloads_spinbox)
        self.auto_create_epub_checkbox = QCheckBox("下载完成后自动创建EPUB"); program_form_layout.addRow(self.auto_create_epub_checkbox)
        program_settings_group.setLayout(program_form_layout); layout.addWidget(program_settings_group)
        epub_meta_settings_group = QGroupBox("EPUB 元数据设置"); epub_form_layout = QFormLayout()
        self.epub_language_combo = QComboBox(); epub_form_layout.addRow("EPUB 语言:", self.epub_language_combo)
        custom_res_layout = QHBoxLayout(); self.epub_custom_width_spinbox = QSpinBox(); self.epub_custom_height_spinbox = QSpinBox()
        self.epub_custom_width_spinbox.setRange(0,9999); self.epub_custom_width_spinbox.setSuffix(" px (0=自动)")
        self.epub_custom_height_spinbox.setRange(0,9999); self.epub_custom_height_spinbox.setSuffix(" px (0=自动)")
        custom_res_layout.addWidget(QLabel("目标宽度:")); custom_res_layout.addWidget(self.epub_custom_width_spinbox); custom_res_layout.addWidget(QLabel("目标高度:")); custom_res_layout.addWidget(self.epub_custom_height_spinbox)
        epub_form_layout.addRow("自定义分辨率:", custom_res_layout)
        self.epub_include_title_page_checkbox = QCheckBox("包含通用标题页 (若脚本支持)"); epub_form_layout.addRow(self.epub_include_title_page_checkbox)
        epub_meta_settings_group.setLayout(epub_form_layout); layout.addWidget(epub_meta_settings_group)
        layout.addStretch(); save_button = QPushButton("保存设置"); save_button.clicked.connect(self._save_app_settings); layout.addWidget(save_button, alignment=Qt.AlignmentFlag.AlignRight)

    def _trigger_search(self):
        if self.main_network_worker and self.main_network_worker.isRunning(): self.statusBar.showMessage("请等待当前主网络操作(搜索/章节列表)完成...", 3000); return
        query = self.search_input.text().strip()
        if not query: self.statusBar.showMessage("请输入搜索关键词!", 3000); return
        self.search_button.setEnabled(False); self.results_list_widget.setEnabled(False); self.statusBar.showMessage(f"正在搜索: {query}...", 0)
        self.results_list_widget.clear(); self.manga_title_label.setText("标题"); self.manga_author_label.setText("作者: 未知"); self.manga_description_text.setText("简介..."); self.manga_cover_label.clear(); self.manga_cover_label.setText("封面图片")
        self.current_search_results_map.clear(); self.results_list_context = "manga_search"; self.results_group_box.setTitle("搜索结果（双击漫画进入章节选择）"); self.current_manga_for_chapters_path_word = None
        api_url_base = INITIAL_SETTINGS.get('api_url'); headers = config.API_HEADER; proxies = config.PROXIES
        self.main_network_worker = NetworkWorker(query=query, api_url_base=api_url_base, headers=headers, proxies=proxies)
        self.main_network_worker.search_complete.connect(self._handle_search_results)
        self.main_network_worker.error.connect(self._handle_network_error)
        self.main_network_worker.finished.connect(self._clear_main_network_worker)
        self.main_network_worker.start()

    def _handle_search_results(self, results_list):
        if not results_list: self.statusBar.showMessage("未找到相关漫画。", 3000); return
        self.statusBar.showMessage(f"找到 {len(results_list)} 个结果。", 3000)
        for manga_data in results_list:
            name = manga_data.get("name", "未知标题"); path_word = manga_data.get("path_word")
            if path_word: self.current_search_results_map[path_word] = manga_data; item = QListWidgetItem(name); item.setData(Qt.ItemDataRole.UserRole, path_word); self.results_list_widget.addItem(item)
        if self.results_list_widget.count() > 0: self.results_list_widget.setCurrentRow(0)

    def _handle_results_list_selection_changed(self, current_item, previous_item):
        if self.results_list_context == "manga_search": self._display_selected_manga_details(current_item)
        elif self.results_list_context == "chapters":
            if current_item:
                chapter_data = current_item.data(Qt.ItemDataRole.UserRole)
                pass

    def _handle_results_list_double_click(self, item):
        if not item:
            return
            
        if self.results_list_context == "manga_search":
            path_word = item.data(Qt.ItemDataRole.UserRole)
            manga_data = self.current_search_results_map.get(path_word)
            
            if not manga_data:
                return
                
            # 先获取章节列表
            self._fetch_chapters_for_manga(manga_data)
        
    def _fetch_chapters_for_manga(self, manga_data):
        if self.main_network_worker and self.main_network_worker.isRunning():
            self.statusBar.showMessage("请等待当前主网络操作完成...", 3000)
            return
            
        path_word = manga_data.get("path_word")
        manga_name = manga_data.get("name", path_word)
        
        self.statusBar.showMessage(f"正在获取《{manga_name}》的章节列表...", 0)
        self.results_list_widget.setEnabled(False)
        
        api_url_base = INITIAL_SETTINGS.get('api_url')
        headers = config.API_HEADER
        proxies = config.PROXIES
        
        chapter_req_info = {'path_word': path_word, 'group': 'default'}
        
        self.main_network_worker = NetworkWorker(
            chapter_request_info=chapter_req_info,
            api_url_base=api_url_base,
            headers=headers,
            proxies=proxies
        )
        
        self.main_network_worker.chapters_ready.connect(
            lambda chapters, path_word=path_word: self._show_chapter_info_dialog(manga_data, chapters)
        )
        self.main_network_worker.error.connect(self._handle_network_error)
        self.main_network_worker.finished.connect(self._clear_main_network_worker)
        self.main_network_worker.start()
    
    def _show_chapter_info_dialog(self, manga_data, chapters):
        """显示章节信息对话框"""
        if not chapters:
            manga_name = manga_data.get("name", "未知漫画")
            self.statusBar.showMessage(f"《{manga_name}》未找到章节信息或列表为空。", 3000)
            return
            
        # 保存章节数据
        path_word = manga_data.get("path_word")
        self.current_manga_chapters_data[path_word] = chapters
        self.current_manga_for_chapters_path_word = path_word
        
        dialog = ChapterInfoDialog(manga_data, chapters, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 根据用户选择添加到队列
            selected_chapters = [chapters[idx] for idx in dialog.selected_chapter_indices]
            if selected_chapters:
                self._add_chapters_to_queue(selected_chapters)
                
                # 生成描述
                if dialog.download_type == 'all':
                    desc = "全部章节"
                elif len(selected_chapters) == 1:
                    desc = f"第{dialog.selected_chapter_indices[0]+1}章"
                else:
                    first_idx = min(dialog.selected_chapter_indices)
                    last_idx = max(dialog.selected_chapter_indices)
                    if len(dialog.selected_chapter_indices) == last_idx - first_idx + 1:
                        # 连续章节
                        desc = f"第{first_idx+1}-{last_idx+1}章"
                    else:
                        # 非连续章节
                        desc = f"共{len(selected_chapters)}章"
                
                manga_name = manga_data.get("name", "未知漫画")
                self.statusBar.showMessage(f"已添加《{manga_name}》{desc}到下载队列", 3000)
                
        # 切换到队列标签页  
        self.tab_widget.setCurrentWidget(self.queue_tab)

    def _display_selected_manga_details(self, current_item):
        """显示选中漫画的详情"""
        if not current_item or self.results_list_context != "manga_search":
            return
            
        path_word = current_item.data(Qt.ItemDataRole.UserRole)
        manga_data = self.current_search_results_map.get(path_word)
        
        if not manga_data:
            return
            
        self.manga_title_label.setText(manga_data.get("name", "未知标题"))
        
        authors = manga_data.get("author", [])
        author_str = ", ".join([a.get("name","") for a in authors]) if isinstance(authors,list) and authors else "未知"
        self.manga_author_label.setText(f"作者: {author_str}")
        
        self.manga_description_text.setText(
            manga_data.get("brief", manga_data.get("show_brief", "无简介")) or 
            manga_data.get("comic", {}).get("brief", "无简介")
        )
        
        cover_url = manga_data.get("cover")
        self.manga_cover_label.clear()
        self.manga_cover_label.setText("正在加载封面...")
        
        if cover_url:
            if cover_url in self.cover_fetch_workers and self.cover_fetch_workers[cover_url].isRunning():
                pass
            else:
                headers = config.API_HEADER
                proxies = config.PROXIES
                cover_worker = NetworkWorker(cover_url=cover_url, headers=headers, proxies=proxies)
                self.cover_fetch_workers[cover_url] = cover_worker
                cover_worker.cover_ready.connect(self._handle_cover_image)
                cover_worker.error.connect(self._handle_network_error)
                cover_worker.finished.connect(lambda url=cover_url: self._clear_cover_worker(url))
                cover_worker.start()
        else:
            self.manga_cover_label.setText("无封面")

    def _handle_cover_image(self, pixmap, requested_url):
        """处理封面图片加载完成"""
        current_selected_item = self.results_list_widget.currentItem()
        if self.results_list_context == "manga_search" and current_selected_item:
            path_word = current_selected_item.data(Qt.ItemDataRole.UserRole)
            manga_data = self.current_search_results_map.get(path_word)
            if manga_data and manga_data.get("cover") == requested_url:
                scaled_pixmap = pixmap.scaled(
                    self.manga_cover_label.size(), 
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                )
                self.manga_cover_label.setPixmap(scaled_pixmap)

    def _handle_network_error(self, error_msg, operation_type):
        """处理网络错误"""
        self.statusBar.showMessage(f"{operation_type.capitalize()} 错误: {error_msg}", 5000)
        print(f"网络错误 ({operation_type}): {error_msg}")
        
        if operation_type == "chapters" and self.results_list_context == "chapters":
            self.results_list_context = "manga_search"
            self.results_group_box.setTitle("搜索结果 (章节加载失败)")
            
        if operation_type == "cover":
            self.manga_cover_label.setText("封面加载失败")
    
    def _clear_main_network_worker(self):
        """清理主网络工作线程"""
        self.search_button.setEnabled(True)
        self.results_list_widget.setEnabled(True)
        self.main_network_worker = None
    
    def _clear_cover_worker(self, url):
        """清理封面加载工作线程"""
        if url in self.cover_fetch_workers:
            del self.cover_fetch_workers[url]

    def _add_chapters_to_queue(self, chapter_data_list):
        if not chapter_data_list:
            return
            
        manga_path_word = self.current_manga_for_chapters_path_word
        manga_info = self.current_search_results_map.get(manga_path_word, {})
        manga_name = manga_info.get("name", manga_path_word)
        
        queued_count = 0
        for chapter_data in chapter_data_list:
            chapter_uuid = chapter_data.get("uuid")
            if chapter_uuid and not any(item[2].get("uuid") == chapter_uuid for item in self.download_queue) and chapter_uuid not in self.active_download_workers:
                self.download_queue.append((manga_path_word, manga_name, chapter_data))
                
                # 添加到队列列表
                queue_item = QListWidgetItem(
                    f"《{manga_name}》 - {chapter_data.get('name', '未知章节')} - 等待下载"
                )
                queue_item.setData(Qt.ItemDataRole.UserRole, chapter_uuid)
                self.queue_list.addItem(queue_item)
                
                queued_count += 1
                
        if queued_count > 0:
            self.statusBar.showMessage(f"{queued_count} 个章节已添加到下载队列。", 3000)
            self._log_download_status(f"已添加 {queued_count} 个章节到下载队列")
        else:
            self.statusBar.showMessage("选择的章节已在队列或正在下载中。", 3000)
    
    def _start_queue_download(self):
        """开始队列下载"""
        if not self.download_queue:
            self.statusBar.showMessage("下载队列为空", 3000)
            return
            
        self.start_queue_button.setEnabled(False)
        self.pause_queue_button.setEnabled(True)
        
        self._process_download_queue()
    
    def _pause_download(self):
        """暂停下载"""
        for worker in self.active_download_workers.values():
            worker.cancel()
            
        self.start_queue_button.setEnabled(True)
        self.pause_queue_button.setEnabled(False)
        
        self.statusBar.showMessage("下载已暂停", 3000)
        self._log_download_status("下载已暂停")
    
    def _clear_queue(self):
        """清空下载队列"""
        reply = QMessageBox.question(
            self,
            "清空队列",
            "确定要清空下载队列吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.download_queue.clear()
            self.queue_list.clear()
            self.statusBar.showMessage("下载队列已清空", 3000)
            self._log_download_status("下载队列已清空")
    
    def _process_download_queue(self):
        """处理下载队列"""
        if not self.download_queue:
            self.pause_queue_button.setEnabled(False)
            self.start_queue_button.setEnabled(True)
            self.current_download_label.setText("当前下载: 无")
            self.download_progress_bar.setValue(0)
            return
            
        while self.download_queue and len(self.active_download_workers) < self.max_concurrent_downloads:
            manga_path_word, manga_name, chapter_data = self.download_queue[0]
            chapter_uuid = chapter_data.get("uuid")
            
            if chapter_uuid in self.active_download_workers:
                # 已经在下载，移除并跳过
                self.download_queue.pop(0)
                continue
                
            download_dest_root = self.download_destination_edit.text()
            
            if not download_dest_root or not os.path.isdir(download_dest_root):
                self.statusBar.showMessage(f"错误: 下载目标路径无效: {download_dest_root}", 5000)
                self._log_download_status(f"错误: 下载目标路径无效: {download_dest_root}")
                return
                
            # 开始下载，但不从队列中移除，直到下载完成
            chapter_name = chapter_data.get('name', '未知章节')
            self.statusBar.showMessage(f"准备下载《{manga_name}》- {chapter_name}...", 0)
            self._log_download_status(f"开始下载: 《{manga_name}》- {chapter_name}")
            
            self.current_download_label.setText(f"当前下载: 《{manga_name}》- {chapter_name}")
            self.download_progress_bar.setValue(0)
            
            worker = DownloadWorker(
                manga_name,
                manga_path_word,
                chapter_data,
                download_dest_root,
                INITIAL_SETTINGS.get('api_url'),
                config.API_HEADER,
                config.PROXIES
            )
            
            worker.progress_update.connect(self._handle_download_progress)
            worker.chapter_complete.connect(self._handle_chapter_download_complete)
            worker.error.connect(self._handle_download_error)
            
            self.active_download_workers[chapter_uuid] = worker
            worker.start()
            
            # 移除队列中的项目
            self.download_queue.pop(0)
            
            # 更新队列显示
            for i in range(self.queue_list.count()):
                item = self.queue_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == chapter_uuid:
                    self.queue_list.takeItem(i)
                    break

    def _handle_download_progress(self, chapter_uuid, page_num, total_pages):
        """处理下载进度"""
        worker_instance = self.active_download_workers.get(chapter_uuid)
        if not worker_instance:
            return
            
        chapter_name = worker_instance.chapter_data.get("name", "未知章节")
        manga_name = worker_instance.manga_name
        
        progress_percent = int((page_num / total_pages) * 100)
        self.download_progress_bar.setValue(progress_percent)
        
        progress_msg = f"下载中: 《{manga_name}》- {chapter_name} - {page_num}/{total_pages} 页 ({progress_percent}%)"
        self.statusBar.showMessage(progress_msg, 0)
        
        if page_num % 5 == 0 or page_num == total_pages:  # 每5页更新一次日志，减少频繁更新
            self._log_download_status(progress_msg)

    def _handle_chapter_download_complete(self, chapter_uuid, chapter_name, chapter_path, success):
        """处理章节下载完成"""
        if chapter_uuid in self.active_download_workers:
            worker = self.active_download_workers[chapter_uuid]
            manga_name = worker.manga_name
            del self.active_download_workers[chapter_uuid]
            
        if success:
            self.statusBar.showMessage(f"章节《{manga_name} - {chapter_name}》下载完成", 5000)
            self._log_download_status(f"✅ 下载完成: 《{manga_name}》- {chapter_name} 到 {chapter_path}")
            
            if INITIAL_SETTINGS.get('auto_create_epub_after_download', False):
                self.statusBar.showMessage(f"《{chapter_name}》下载完成, 准备自动创建EPUB...", 3000)
                self._log_download_status(f"开始自动转换 《{manga_name}》- {chapter_name} 为EPUB...")
                
                epub_output_folder = self.export_destination_edit.text() or os.path.dirname(chapter_path)
                os.makedirs(epub_output_folder, exist_ok=True)
                
                manga_name_for_epub = os.path.basename(os.path.dirname(chapter_path))
                epub_title = f"{manga_name_for_epub} - {chapter_name}"
                output_epub_filename = f"{INITIAL_SETTINGS.get('epub_filename_prefix', '')}{epub_title}.epub"
                output_epub_full_path = os.path.join(epub_output_folder, re.sub(r'[\\/*?"<>|]',"_", output_epub_filename))
                
                epub_params = {
                    'epub_title': epub_title,
                    'language_code': INITIAL_SETTINGS.get('epub_language'),
                    'target_width_override': INITIAL_SETTINGS.get('epub_target_width') or None,
                    'target_height_override': INITIAL_SETTINGS.get('epub_target_height') or None,
                    'epub_author': "Copymanga Downloader",
                    'processing_mode': 'direct'
                }
                
                auto_delete_for_auto_epub = False
                self.export_worker = ExportWorker(
                    chapter_path,
                    "EPUB",
                    output_epub_full_path,
                    epub_params,
                    auto_delete_for_auto_epub
                )
                
                self.export_worker.finished.connect(self._on_export_finished)
                self.export_worker.progress.connect(self._update_export_progress)
                self.export_worker.start()
        else:
            self.statusBar.showMessage(f"章节《{chapter_name}》下载失败或取消。", 5000)
            self._log_download_status(f"❌ 下载失败: 《{manga_name}》- {chapter_name}")
            
        # 继续处理队列
        self._process_download_queue()

    def _handle_download_error(self, chapter_uuid, chapter_name, error_message):
        """处理下载错误"""
        if chapter_uuid in self.active_download_workers:
            worker = self.active_download_workers[chapter_uuid]
            manga_name = worker.manga_name
            del self.active_download_workers[chapter_uuid]
            
        self.statusBar.showMessage(f"下载《{chapter_name}》时出错: {error_message}", 8000)
        self._log_download_status(f"❌ 下载错误: 《{manga_name}》- {chapter_name}: {error_message}")
        
        # 继续处理队列
        self._process_download_queue()
    
    def _log_download_status(self, message):
        """记录下载状态到日志"""
        timestamp = time.strftime('%H:%M:%S')
        self.download_status_text.append(f"[{timestamp}] {message}")
        
        # 自动滚动到底部
        cursor = self.download_status_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.download_status_text.setTextCursor(cursor)

    def _browse_path_for_lineedit(self, line_edit_widget, dialog_title):
        current_path = line_edit_widget.text() or str(get_app_base_dir())
        path = QFileDialog.getExistingDirectory(self, dialog_title, current_path)
        if path:
            line_edit_widget.setText(path)
            self.statusBar.showMessage(f"{dialog_title} 已选定: {path}", 3000)

    def _browse_download_destination(self): self._browse_path_for_lineedit(self.download_destination_edit, "选择下载目标路径")
    def _browse_export_destination(self): self._browse_path_for_lineedit(self.export_destination_edit, "选择导出目标路径")
    def open_settings_tab(self): self.tab_widget.setCurrentWidget(self.settings_tab); self.statusBar.showMessage("已切换到设置标签页", 3000)
    def focus_search_and_open_downloader_tab(self): self.tab_widget.setCurrentWidget(self.downloader_tab); self.search_input.setFocus(); self.statusBar.showMessage("请输入漫画名称进行搜索", 3000)
    def _browse_for_export_source_folder(self):
        start_path = self.export_source_folder_edit.text() or INITIAL_SETTINGS.get('download_path'); path = QFileDialog.getExistingDirectory(self, "选择已下载漫画文件夹", start_path); (path and (self.export_source_folder_edit.setText(path) or self.statusBar.showMessage(f"导出源选定: {path}", 3000)))

    def _handle_export(self):
        if self.export_worker and self.export_worker.isRunning(): self.statusBar.showMessage("错误: 当前已有导出任务!", 5000); return
        source_folder = self.export_source_folder_edit.text(); export_dest_path = self.export_destination_edit.text()
        if not source_folder or not os.path.isdir(source_folder): self.statusBar.showMessage("错误: 无效的源文件夹!", 5000); return
        if not export_dest_path or not os.path.isdir(export_dest_path): self.statusBar.showMessage("错误: 无效的导出路径!", 5000); return
        os.makedirs(export_dest_path, exist_ok=True); folder_name = os.path.basename(source_folder); epub_prefix = self.epub_filename_prefix_edit.text()
        output_filename = f"{epub_prefix}{folder_name}.epub"; output_epub_full_path = os.path.join(export_dest_path, output_filename)
        epub_params = {'epub_title': folder_name, 'language_code': INITIAL_SETTINGS.get('epub_language'), 'target_width_override': INITIAL_SETTINGS.get('epub_target_width') or None, 'target_height_override': INITIAL_SETTINGS.get('epub_target_height') or None, 'epub_author': "Copymanga Downloader", 'processing_mode': self._determine_processing_mode(source_folder)}
        self.start_export_button.setEnabled(False); self.statusBar.showMessage(f"开始导出 {folder_name} 为 EPUB 到 {export_dest_path}...", 0)
        current_auto_delete_setting = self.epub_auto_delete_source_checkbox.isChecked()
        self.export_worker = ExportWorker(source_folder, "EPUB", output_epub_full_path, epub_params, current_auto_delete_setting)
        self.export_worker.finished.connect(self._on_export_finished); self.export_worker.progress.connect(self._update_export_progress); self.export_worker.start()

    def _update_export_progress(self, message): self.statusBar.showMessage(message, 0)

    def _on_export_finished(self, success, message, deleted_source_folder):
        self.statusBar.showMessage(message, 10000 if success else 0); self.start_export_button.setEnabled(True)
        if success and deleted_source_folder and deleted_source_folder == self.export_source_folder_edit.text(): self.export_source_folder_edit.clear(); self.statusBar.showMessage(message + " (源文件夹已清空)", 10000)
        self.export_worker = None

    def _determine_processing_mode(self, folder_path):
        try:
            for item in os.listdir(folder_path):
                if os.path.isdir(os.path.join(folder_path, item)) and re.search(r'\d', item): return 'subfolder'
        except OSError: return 'direct'
        return 'direct'

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec())