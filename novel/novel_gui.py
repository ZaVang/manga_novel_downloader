#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import re
import shutil
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QWidget, 
                             QMenuBar, QStatusBar, QLineEdit, QPushButton, QListWidget, QTabWidget,
                             QGroupBox, QFormLayout, QSpinBox, QCheckBox, QComboBox, QFileDialog,
                             QListWidgetItem, QTextEdit, QProgressBar, QMessageBox, QRadioButton,
                             QScrollArea, QInputDialog, QDialog, QDialogButtonBox, QSplitter,
                             QTreeWidget, QTreeWidgetItem
)
from PyQt6.QtGui import QAction, QFont, QPixmap
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
import time

# 导入您的下载器类
from main import Wenku8Downloader
from epub_converter import convert_single_volume, convert_multiple_volumes, txt_to_epub


def parse_volume_range(range_text, max_volumes):
    """
    解析卷范围字符串，返回卷索引列表
    
    支持的格式：
    - "0-2" -> [0, 1, 2]
    - "1,3,5" -> [1, 3, 5] 
    - "0-2,5,7-9" -> [0, 1, 2, 5, 7, 8, 9]
    
    Args:
        range_text: 范围字符串
        max_volumes: 最大卷数
        
    Returns:
        list: 卷索引列表，失败返回None
    """
    if not range_text.strip():
        return None
        
    try:
        volume_indices = set()
        
        # 按逗号分割
        parts = [part.strip() for part in range_text.split(',')]
        
        for part in parts:
            if '-' in part:
                # 处理范围，如 "0-2"
                range_parts = part.split('-')
                if len(range_parts) != 2:
                    return None
                    
                start = int(range_parts[0].strip())
                end = int(range_parts[1].strip())
                
                if start > end:
                    return None
                    
                for i in range(start, end + 1):
                    if 0 <= i < max_volumes:
                        volume_indices.add(i)
            else:
                # 处理单个数字
                index = int(part.strip())
                if 0 <= index < max_volumes:
                    volume_indices.add(index)
        
        return sorted(list(volume_indices))
        
    except ValueError:
        return None


class ChapterInfoDialog(QDialog):
    """章节信息对话框"""
    def __init__(self, novel_data, volumes, parent=None):
        super().__init__(parent)
        self.novel_data = novel_data
        self.volumes = volumes
        self.selected_volume_indices = []
        self.download_type = None  # 'full', 'volume', 'range'
        
        self.setWindowTitle(f"《{novel_data['name']}》章节信息")
        self.setMinimumSize(700, 600)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 小说信息
        info_group = QGroupBox("小说信息")
        info_layout = QFormLayout()
        info_layout.addRow("标题:", QLabel(self.novel_data['name']))
        info_layout.addRow("ID:", QLabel(str(self.novel_data['id'])))
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # 章节列表
        chapters_group = QGroupBox("章节信息")
        chapters_layout = QVBoxLayout()
        
        self.chapter_tree = QTreeWidget()
        self.chapter_tree.setHeaderLabels(["卷/章节", "章节数"])
        
        total_chapters = 0
        for i, volume in enumerate(self.volumes):
            volume_item = QTreeWidgetItem([f"第{i+1}卷: {volume['title']}", f"{len(volume['chapters'])} 章节"])
            volume_item.setData(0, Qt.ItemDataRole.UserRole, i)  # 存储卷索引
            
            for j, chapter in enumerate(volume['chapters']):
                chapter_item = QTreeWidgetItem([f"{j+1:03d}. {chapter['title']}", ""])
                volume_item.addChild(chapter_item)
            
            self.chapter_tree.addTopLevelItem(volume_item)
            total_chapters += len(volume['chapters'])
        
        self.chapter_tree.expandAll()
        chapters_layout.addWidget(self.chapter_tree)
        
        # 统计信息
        stats_label = QLabel(f"总计: {len(self.volumes)} 卷, {total_chapters} 章节")
        stats_label.setStyleSheet("font-weight: bold; color: #666;")
        chapters_layout.addWidget(stats_label)
        
        chapters_group.setLayout(chapters_layout)
        layout.addWidget(chapters_group)
        
        # 下载选项
        download_group = QGroupBox("下载选项")
        download_layout = QVBoxLayout()
        
        self.full_download_radio = QRadioButton("下载整本小说")
        self.full_download_radio.setChecked(True)
        self.volume_download_radio = QRadioButton("下载选中的卷")
        self.range_download_radio = QRadioButton("按范围下载")
        
        download_layout.addWidget(self.full_download_radio)
        download_layout.addWidget(self.volume_download_radio)
        download_layout.addWidget(self.range_download_radio)
        
        # 范围输入框
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("  范围 (例: 0-2,5 表示第1-3卷和第6卷):"))
        self.range_input = QLineEdit()
        self.range_input.setPlaceholderText("例如: 0-2 或 1,3,5 或 0-1,4-6")
        self.range_input.setEnabled(False)
        range_layout.addWidget(self.range_input)
        download_layout.addLayout(range_layout)
        
        # 范围说明
        range_help = QLabel("  说明: 卷编号从0开始，0表示第1卷，1表示第2卷，以此类推")
        range_help.setStyleSheet("color: #666; font-style: italic;")
        download_layout.addWidget(range_help)
        
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        self.add_to_queue_button = QPushButton("添加到下载队列")
        self.add_to_queue_button.clicked.connect(self.add_to_queue)
        
        self.download_now_button = QPushButton("立即下载")
        self.download_now_button.clicked.connect(self.download_now)
        
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.add_to_queue_button)
        button_layout.addWidget(self.download_now_button)
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
        current_item = self.chapter_tree.currentItem()
        if current_item and current_item.parent() is None:  # 是卷节点
            volume_index = current_item.data(0, Qt.ItemDataRole.UserRole)
            if volume_index is not None:
                self.volume_download_radio.setEnabled(True)
                # 自动选择单卷下载并设置范围
                self.volume_download_radio.setChecked(True)
                self.range_input.setText(str(volume_index))
        else:
            self.volume_download_radio.setEnabled(False)
    
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
            
        indices = parse_volume_range(range_text, len(self.volumes))
        if indices is not None:
            self.range_input.setStyleSheet("color: green;")
            # 在树形控件中高亮选中的卷
            self.highlight_selected_volumes(indices)
        else:
            self.range_input.setStyleSheet("color: red;")
            self.clear_volume_highlights()
    
    def highlight_selected_volumes(self, indices):
        """高亮选中的卷"""
        self.clear_volume_highlights()
        
        for i in range(self.chapter_tree.topLevelItemCount()):
            item = self.chapter_tree.topLevelItem(i)
            volume_index = item.data(0, Qt.ItemDataRole.UserRole)
            
            if volume_index in indices:
                # 设置背景色为浅蓝色
                item.setBackground(0, Qt.GlobalColor.lightGray)
                item.setBackground(1, Qt.GlobalColor.lightGray)
    
    def clear_volume_highlights(self):
        """清除卷的高亮"""
        for i in range(self.chapter_tree.topLevelItemCount()):
            item = self.chapter_tree.topLevelItem(i)
            item.setBackground(0, Qt.GlobalColor.white)
            item.setBackground(1, Qt.GlobalColor.white)
    
    def get_selected_options(self):
        """获取选择的下载选项"""
        if self.full_download_radio.isChecked():
            return 'full', []
        elif self.volume_download_radio.isChecked():
            current_item = self.chapter_tree.currentItem()
            if current_item and current_item.parent() is None:
                volume_index = current_item.data(0, Qt.ItemDataRole.UserRole)
                if volume_index is not None:
                    return 'volume', [volume_index]
            return None, []
        elif self.range_download_radio.isChecked():
            range_text = self.range_input.text().strip()
            indices = parse_volume_range(range_text, len(self.volumes))
            if indices:
                return 'range', indices
            return None, []
        
        return None, []
    
    def add_to_queue(self):
        """添加到下载队列"""
        download_type, volume_indices = self.get_selected_options()
        
        if download_type is None:
            QMessageBox.warning(self, "选择错误", "请选择有效的下载选项")
            return
        
        self.download_type = 'queue'
        self.selected_volume_indices = volume_indices
        self.accept()
    
    def download_now(self):
        """立即下载"""
        download_type, volume_indices = self.get_selected_options()
        
        if download_type is None:
            QMessageBox.warning(self, "选择错误", "请选择有效的下载选项")
            return
        
        self.download_type = 'now'
        self.selected_volume_indices = volume_indices
        self.accept()


class NetworkWorker(QThread):
    search_complete = pyqtSignal(dict)
    novel_details_ready = pyqtSignal(dict)
    chapter_list_ready = pyqtSignal(list)
    error = pyqtSignal(str, str)
    
    def __init__(self, operation_type, downloader, parent=None, **kwargs):
        super().__init__(parent)
        self.operation_type = operation_type
        self.downloader = downloader
        self.kwargs = kwargs
    
    def run(self):
        try:
            if self.operation_type == "search":
                keyword = self.kwargs.get('keyword')
                search_type = self.kwargs.get('search_type', 'articlename')
                page_url = self.kwargs.get('page_url')
                
                result = self.downloader.search_novels(
                    keyword=keyword, 
                    search_type=search_type,
                    page_url=page_url
                )
                self.search_complete.emit(result)
                
            elif self.operation_type == "novel_details":
                novel_id = self.kwargs.get('novel_id')
                details = self.downloader.get_novel_details(novel_id)
                if details:
                    self.novel_details_ready.emit(details)
                else:
                    self.error.emit("无法获取小说详情", "novel_details")
            
            elif self.operation_type == "chapter_list":
                catalog_url = self.kwargs.get('catalog_url')
                chapters = self.downloader.get_chapter_list(catalog_url)
                self.chapter_list_ready.emit(chapters)
                    
        except Exception as e:
            self.error.emit(f"网络操作失败: {e}", self.operation_type)

class DownloadWorker(QThread):
    progress_update = pyqtSignal(str)
    download_complete = pyqtSignal(bool, str)
    
    def __init__(self, downloader, novel_id, novel_name, output_dir, max_retries, 
                 download_type='full', volume_indices=None, parent=None):
        super().__init__(parent)
        self.downloader = downloader
        self.novel_id = novel_id
        self.novel_name = novel_name
        self.output_dir = output_dir
        self.max_retries = max_retries
        self.download_type = download_type
        self.volume_indices = volume_indices or []
        self.is_cancelled = False
    
    def run(self):
        try:
            safe_novel_name = re.sub(r'[\\\\/:*?\"<>|]', '_', self.novel_name)
            novel_specific_output_dir = os.path.join(self.output_dir, safe_novel_name)
            os.makedirs(novel_specific_output_dir, exist_ok=True)
            
            if self.download_type == 'full':
                self.progress_update.emit(f"开始下载小说 ID: {self.novel_id} ({self.novel_name}) 到 {novel_specific_output_dir}")
                success = self.downloader.download_novel(
                    self.novel_id,
                    output_dir=novel_specific_output_dir,
                    max_retries=self.max_retries
                )
            elif self.download_type in ['volume', 'range'] and self.volume_indices:
                if len(self.volume_indices) == 1:
                    # 单卷下载
                    volume_index = self.volume_indices[0]
                    self.progress_update.emit(f"开始下载小说卷 ID: {self.novel_id} 第{volume_index+1}卷 ({self.novel_name}) 到 {novel_specific_output_dir}")
                    success = self.downloader.download_volume(
                        self.novel_id,
                        volume_index,
                        output_dir=novel_specific_output_dir,
                        max_retries=self.max_retries
                    )
                else:
                    # 多卷下载
                    volume_names = [f"第{i+1}卷" for i in self.volume_indices]
                    self.progress_update.emit(f"开始下载小说多卷 ID: {self.novel_id} ({', '.join(volume_names)}) ({self.novel_name}) 到 {novel_specific_output_dir}")
                    success = True
                    
                    for volume_index in self.volume_indices:
                        if self.is_cancelled:
                            break
                            
                        self.progress_update.emit(f"正在下载第{volume_index+1}卷...")
                        volume_success = self.downloader.download_volume(
                            self.novel_id,
                            volume_index,
                            output_dir=novel_specific_output_dir,
                            max_retries=self.max_retries
                        )
                        
                        if not volume_success:
                            success = False
                            self.progress_update.emit(f"第{volume_index+1}卷下载失败")
                        else:
                            self.progress_update.emit(f"第{volume_index+1}卷下载完成")
            else:
                success = False
                self.progress_update.emit("下载参数错误")
            
            if not self.is_cancelled:
                if success:
                    if self.download_type == 'full':
                        download_desc = "整本小说"
                    elif len(self.volume_indices) == 1:
                        download_desc = f"第{self.volume_indices[0]+1}卷"
                    else:
                        volume_names = [f"第{i+1}卷" for i in self.volume_indices]
                        download_desc = f"({', '.join(volume_names)})"
                    
                    self.download_complete.emit(True, f"小说《{self.novel_name}》{download_desc} 下载完成")
                else:
                    self.download_complete.emit(False, f"小说《{self.novel_name}》下载失败")
        except Exception as e:
            if not self.is_cancelled:
                self.download_complete.emit(False, f"下载《{self.novel_name}》过程中发生错误: {e}")
    
    def cancel(self):
        self.is_cancelled = True

class EpubExportWorker(QThread):
    export_progress = pyqtSignal(str)
    export_finished = pyqtSignal(bool, str)

    def __init__(self, novel_title, author, input_novel_dir, output_epub_dir, mode, parent=None):
        super().__init__(parent)
        self.novel_title = novel_title
        self.author = author
        self.input_novel_dir = input_novel_dir
        self.output_epub_dir = output_epub_dir
        self.mode = mode

    def run(self):
        try:
            self.export_progress.emit(f"开始转换小说: {self.novel_title}...")
            self.export_progress.emit(f"源文件夹: {self.input_novel_dir}")
            self.export_progress.emit(f"输出目录: {self.output_epub_dir}")
            self.export_progress.emit(f"转换模式: {'按卷分别生成 EPUB' if self.mode == 'per_volume' else '合并为单个 EPUB'}")

            txt_to_epub(self.input_novel_dir, self.output_epub_dir, self.novel_title, self.author)
            self.export_progress.emit(f"转换完成")
            self.export_finished.emit(True, f"EPUB转换完成: {self.novel_title}")

        except Exception as e:
            self.export_finished.emit(False, f"EPUB 转换过程中发生错误: {e}")
    
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("轻小说文库下载器")
        self.setGeometry(100, 100, 1200, 800)
        
        # 初始化变量
        self.downloader = None
        self.network_worker = None
        self.download_worker = None
        self.epub_export_worker = None
        self.current_search_results = []
        self.current_pagination_info = None
        self.download_queue = []
        self.cover_cache_dir_path = os.path.join(os.getcwd(), 'novel_cache', 'covers')
        
        # 默认设置
        self.settings = {
            'username': '2497360927',
            'password': 'testtest',
            'output_dir': os.path.expanduser("~/Downloads/novels"),
            'max_retries': 3,
            'auto_login': True  # 默认自动登录
        }
        
        self._create_menu_bar()
        self._create_status_bar()
        self._init_ui()
        self._load_settings()
        
    def _create_menu_bar(self):
        menu_bar = self.menuBar()
        
        file_menu = menu_bar.addMenu("&文件")
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self._open_settings_tab)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        action_menu = menu_bar.addMenu("&操作")
        search_action = QAction("搜索小说", self)
        search_action.triggered.connect(self._focus_search)
        action_menu.addAction(search_action)
        
    def _create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("准备就绪")
        
    def _init_ui(self):
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)
        
        # 搜索下载标签页
        self.search_tab = QWidget()
        self.tab_widget.addTab(self.search_tab, "搜索下载")
        self._setup_search_tab()
        
        # 下载队列标签页
        self.queue_tab = QWidget()
        self.tab_widget.addTab(self.queue_tab, "下载队列")
        self._setup_queue_tab()
        
        # EPUB 导出标签页
        self.export_tab = QWidget()
        self.tab_widget.addTab(self.export_tab, "导出 EPUB")
        self._setup_export_tab()
        
        # 设置标签页
        self.settings_tab = QWidget()
        self.tab_widget.addTab(self.settings_tab, "设置")
        self._setup_settings_tab()
        
    def _setup_search_tab(self):
        layout = QVBoxLayout(self.search_tab)
        
        # 搜索组
        search_group = QGroupBox("小说搜索")
        search_layout = QVBoxLayout()
        
        # 搜索类型选择
        search_type_layout = QHBoxLayout()
        self.search_by_name_radio = QRadioButton("按小说名搜索")
        self.search_by_author_radio = QRadioButton("按作者名搜索")
        self.search_by_name_radio.setChecked(True)
        
        search_type_layout.addWidget(self.search_by_name_radio)
        search_type_layout.addWidget(self.search_by_author_radio)
        search_type_layout.addStretch()
        
        search_layout.addLayout(search_type_layout)
        
        # 搜索输入框
        search_input_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入搜索关键词...")
        self.search_input.returnPressed.connect(self._trigger_search)
        
        self.search_button = QPushButton("搜索")
        self.search_button.clicked.connect(self._trigger_search)
        
        search_input_layout.addWidget(self.search_input)
        search_input_layout.addWidget(self.search_button)
        
        search_layout.addLayout(search_input_layout)
        search_group.setLayout(search_layout)
        layout.addWidget(search_group)
        
        # 主内容区域 - 使用分割器
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 搜索结果列表
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        
        results_group = QGroupBox("搜索结果")
        results_group_layout = QVBoxLayout()
        
        self.results_list = QListWidget()
        self.results_list.currentItemChanged.connect(self._handle_selection_change)
        self.results_list.itemDoubleClicked.connect(self._handle_double_click)
        
        # 分页控制
        pagination_layout = QHBoxLayout()
        self.prev_page_button = QPushButton("上一页")
        self.prev_page_button.clicked.connect(self._load_prev_page)
        self.prev_page_button.setEnabled(False)
        
        self.page_info_label = QLabel("1/1 页")
        
        self.next_page_button = QPushButton("下一页")
        self.next_page_button.clicked.connect(self._load_next_page)
        self.next_page_button.setEnabled(False)
        
        pagination_layout.addWidget(self.prev_page_button)
        pagination_layout.addWidget(self.page_info_label)
        pagination_layout.addWidget(self.next_page_button)
        pagination_layout.addStretch()
        
        results_group_layout.addWidget(self.results_list)
        results_group_layout.addLayout(pagination_layout)
        results_group.setLayout(results_group_layout)
        results_layout.addWidget(results_group)
        
        content_splitter.addWidget(results_widget)
        
        # 小说详情
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        
        details_group = QGroupBox("小说详情")
        details_group_layout = QVBoxLayout()
        
        self.novel_title_label = QLabel("选择一本小说查看详情")
        self.novel_title_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.novel_title_label.setWordWrap(True)
        
        # Cover Image Label
        self.novel_cover_label = QLabel()
        self.novel_cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.novel_cover_label.setMinimumSize(150, 200)
        self.novel_cover_label.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")
        self.novel_cover_label.setText("无封面")

        self.novel_author_label = QLabel("作者: ")
        self.novel_id_label = QLabel("ID: ")
        
        self.novel_description = QTextEdit()
        self.novel_description.setMaximumHeight(150)
        self.novel_description.setPlaceholderText("双击小说查看章节信息...")
        self.novel_description.setReadOnly(True)
        
        # 下载控制
        download_control_layout = QVBoxLayout()
        
        self.add_to_queue_button = QPushButton("添加到下载队列")
        self.add_to_queue_button.clicked.connect(self._add_to_download_queue)
        self.add_to_queue_button.setEnabled(False)
        
        self.download_now_button = QPushButton("立即下载")
        self.download_now_button.clicked.connect(self._download_now)
        self.download_now_button.setEnabled(False)
        
        download_control_layout.addWidget(self.add_to_queue_button)
        download_control_layout.addWidget(self.download_now_button)
        
        details_group_layout.addWidget(self.novel_title_label)
        details_group_layout.addWidget(self.novel_cover_label)
        details_group_layout.addWidget(self.novel_author_label)
        details_group_layout.addWidget(self.novel_id_label)
        details_group_layout.addWidget(QLabel("提示:"))
        details_group_layout.addWidget(self.novel_description)
        details_group_layout.addLayout(download_control_layout)
        details_group_layout.addStretch()
        
        details_group.setLayout(details_group_layout)
        details_layout.addWidget(details_group)
        
        content_splitter.addWidget(details_widget)
        content_splitter.setSizes([350, 450])
        
        layout.addWidget(content_splitter)
        
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
        layout = QVBoxLayout(self.export_tab)
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # --- 源文件选择 ---
        source_group = QGroupBox("源小说 (已下载的小说文件夹)")
        source_form = QFormLayout()

        source_dir_layout = QHBoxLayout()
        self.epub_source_dir_edit = QLineEdit()
        default_epub_source_dir = os.path.join(self.settings.get('output_dir', os.path.expanduser("~/Downloads/novels")))
        self.epub_source_dir_edit.setText(default_epub_source_dir)
        self.epub_source_dir_edit.setPlaceholderText("选择已下载的小说根目录")
        self.epub_source_dir_edit.textChanged.connect(self._update_epub_novel_title_preview)
        browse_source_button = QPushButton("浏览源...")
        browse_source_button.clicked.connect(self._browse_epub_source_dir)
        source_dir_layout.addWidget(self.epub_source_dir_edit)
        source_dir_layout.addWidget(browse_source_button)
        source_form.addRow("小说文件夹:", source_dir_layout)

        self.epub_novel_title_edit = QLineEdit()
        self.epub_novel_title_edit.setPlaceholderText("小说标题 (自动从文件夹名获取)")
        source_form.addRow("EPUB书名:", self.epub_novel_title_edit)

        self.epub_author_edit = QLineEdit("佚名")
        source_form.addRow("作者:", self.epub_author_edit)

        source_group.setLayout(source_form)
        scroll_layout.addWidget(source_group)

        # --- 转换设置 ---
        conversion_group = QGroupBox("转换设置")
        conversion_form = QFormLayout()

        self.epub_conversion_mode_combo = QComboBox()
        self.epub_conversion_mode_combo.addItem("合并为单个EPUB", "all_in_one")
        self.epub_conversion_mode_combo.addItem("按卷分别生成EPUB", "per_volume")
        conversion_form.addRow("转换模式:", self.epub_conversion_mode_combo)
        
        epub_output_dir_layout = QHBoxLayout()
        self.epub_output_dir_edit = QLineEdit()
        default_epub_out = os.path.join(self.settings.get('output_dir', os.path.expanduser("~/Downloads/novels")))
        self.epub_output_dir_edit.setText(default_epub_out)

        browse_epub_output_button = QPushButton("浏览输出...")
        browse_epub_output_button.clicked.connect(self._browse_epub_output_dir)
        epub_output_dir_layout.addWidget(self.epub_output_dir_edit)
        epub_output_dir_layout.addWidget(browse_epub_output_button)
        conversion_form.addRow("EPUB输出目录:", epub_output_dir_layout)
        
        conversion_group.setLayout(conversion_form)
        scroll_layout.addWidget(conversion_group)

        # --- 操作按钮 ---
        action_layout = QHBoxLayout()
        self.start_epub_conversion_button = QPushButton("开始转换")
        self.start_epub_conversion_button.clicked.connect(self._start_epub_conversion)
        action_layout.addWidget(self.start_epub_conversion_button)
        action_layout.addStretch()
        scroll_layout.addLayout(action_layout)
        
        # --- 状态显示 ---
        status_group = QGroupBox("转换状态")
        status_layout = QVBoxLayout()
        self.epub_status_text = QTextEdit()
        self.epub_status_text.setReadOnly(True)
        self.epub_status_text.setMaximumHeight(150)
        status_layout.addWidget(self.epub_status_text)
        status_group.setLayout(status_layout)
        scroll_layout.addWidget(status_group)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

    def _setup_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)
        
        # 滚动区域
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # 账户设置和登录状态
        account_group = QGroupBox("账户设置")
        account_layout = QFormLayout()
        
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.auto_login_checkbox = QCheckBox("启动时自动登录")
        
        # 登录状态显示
        login_status_layout = QHBoxLayout()
        self.login_status_label = QLabel("未登录")
        self.login_status_label.setStyleSheet("color: red; font-weight: bold;")
        
        self.login_button = QPushButton("登录")
        self.login_button.clicked.connect(self._handle_login)
        
        login_status_layout.addWidget(self.login_status_label)
        login_status_layout.addStretch()
        login_status_layout.addWidget(self.login_button)
        
        account_layout.addRow("用户名:", self.username_edit)
        account_layout.addRow("密码:", self.password_edit)
        account_layout.addRow(self.auto_login_checkbox)
        account_layout.addRow("登录状态:", login_status_layout)
        
        account_group.setLayout(account_layout)
        scroll_layout.addWidget(account_group)
        
        # 下载设置
        download_group = QGroupBox("下载设置")
        download_layout = QFormLayout()
        
        # 输出目录
        output_dir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.browse_output_button = QPushButton("浏览...")
        self.browse_output_button.clicked.connect(self._browse_output_dir)
        
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(self.browse_output_button)
        
        download_layout.addRow("输出目录:", output_dir_layout)
        
        # 其他下载设置
        self.max_retries_spinbox = QSpinBox()
        self.max_retries_spinbox.setRange(1, 10)
        self.max_retries_spinbox.setValue(3)
        
        download_layout.addRow("最大重试次数:", self.max_retries_spinbox)
        
        download_group.setLayout(download_layout)
        scroll_layout.addWidget(download_group)
        
        # Cache Management
        cache_group = QGroupBox("缓存管理")
        cache_layout = QVBoxLayout()
        self.clear_cache_button = QPushButton("清除封面缓存")
        self.clear_cache_button.clicked.connect(self._confirm_clear_cache)
        cache_layout.addWidget(self.clear_cache_button)
        cache_group.setLayout(cache_layout)
        scroll_layout.addWidget(cache_group)

        scroll_layout.addStretch()
        
        # 保存按钮
        save_button = QPushButton("保存设置")
        save_button.clicked.connect(self._save_settings)
        scroll_layout.addWidget(save_button)
        
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        
    def _load_settings(self):
        """加载设置到界面"""
        self.username_edit.setText(self.settings.get('username', ''))
        self.password_edit.setText(self.settings.get('password', ''))
        self.output_dir_edit.setText(self.settings.get('output_dir', ''))
        self.max_retries_spinbox.setValue(self.settings.get('max_retries', 3))
        self.auto_login_checkbox.setChecked(self.settings.get('auto_login', True))
        
        # 如果设置了自动登录，则尝试登录
        if self.settings.get('auto_login', True) and self.settings.get('username'):
            QTimer.singleShot(1000, self._handle_login)  # 延迟1秒后自动登录
    
    def _save_settings(self):
        """保存设置"""
        self.settings.update({
            'username': self.username_edit.text().strip(),
            'password': self.password_edit.text().strip(),
            'output_dir': self.output_dir_edit.text().strip(),
            'max_retries': self.max_retries_spinbox.value(),
            'auto_login': self.auto_login_checkbox.isChecked()
        })
        
        # 创建输出目录
        output_dir = self.settings['output_dir']
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        self.status_bar.showMessage("设置已保存", 3000)
    
    def _browse_output_dir(self):
        """浏览输出目录"""
        current_dir = self.output_dir_edit.text() or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", current_dir)
        if directory:
            self.output_dir_edit.setText(directory)
    
    def _handle_login(self):
        """处理登录"""
        username = self.settings.get('username') or self.username_edit.text().strip()
        password = self.settings.get('password') or self.password_edit.text().strip()
        
        if not username or not password:
            QMessageBox.warning(self, "登录失败", "请先填写用户名和密码")
            return
            
        try:
            self.login_button.setEnabled(False)
            self.login_status_label.setText("登录中...")
            self.login_status_label.setStyleSheet("color: orange; font-weight: bold;")
            
            # 创建下载器实例
            self.downloader = Wenku8Downloader(username=username, password=password)
            
            self.login_status_label.setText("已登录")
            self.login_status_label.setStyleSheet("color: green; font-weight: bold;")
            self.login_button.setText("重新登录")
            
            self.status_bar.showMessage("登录成功", 3000)
            
        except Exception as e:
            self.login_status_label.setText("登录失败")
            self.login_status_label.setStyleSheet("color: red; font-weight: bold;")
            self.status_bar.showMessage(f"登录失败: {e}", 5000)
        finally:
            self.login_button.setEnabled(True)
    
    def _trigger_search(self):
        """触发搜索"""
        if not self.downloader:
            QMessageBox.warning(self, "未登录", "请先在设置页面登录")
            return
            
        keyword = self.search_input.text().strip()
        if not keyword:
            self.status_bar.showMessage("请输入搜索关键词", 3000)
            return
            
        search_type = 'articlename' if self.search_by_name_radio.isChecked() else 'author'
        
        self._perform_search(keyword=keyword, search_type=search_type)
    
    def _perform_search(self, keyword=None, search_type='articlename', page_url=None):
        """执行搜索"""
        if self.network_worker and self.network_worker.isRunning():
            self.status_bar.showMessage("请等待当前搜索完成", 3000)
            return
            
        self.search_button.setEnabled(False)
        self.results_list.setEnabled(False)
        
        search_text = f"搜索: {keyword}" if keyword else "加载页面..."
        self.status_bar.showMessage(search_text)
        
        self.network_worker = NetworkWorker(
            "search", 
            self.downloader,
            parent=self,
            keyword=keyword,
            search_type=search_type,
            page_url=page_url
        )
        
        self.network_worker.search_complete.connect(self._handle_search_results)
        self.network_worker.error.connect(self._handle_network_error)
        self.network_worker.finished.connect(self._clear_network_worker)
        self.network_worker.start()
    
    def _handle_search_results(self, result):
        """处理搜索结果"""
        novels = result.get('novels', [])
        self.current_pagination_info = result.get('pagination_info', {})
        
        if not novels:
            self.status_bar.showMessage("未找到相关小说", 3000)
            self.results_list.clear()
            self._update_pagination_controls()
            return
            
        self.current_search_results = novels
        
        # 更新结果列表
        self.results_list.clear()
        for novel in novels:
            item = QListWidgetItem(f"《{novel['name']}》 (ID: {novel['id']})")
            item.setData(Qt.ItemDataRole.UserRole, novel)
            self.results_list.addItem(item)
            
        self._update_pagination_controls()
        self.status_bar.showMessage(f"找到 {len(novels)} 个结果", 3000)
        
        # 选中第一个结果
        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)
    
    def _update_pagination_controls(self):
        """更新分页控制"""
        if not self.current_pagination_info:
            self.page_info_label.setText("1/1 页")
            self.prev_page_button.setEnabled(False)
            self.next_page_button.setEnabled(False)
            return
            
        current = self.current_pagination_info.get('current_page', 1)
        total = self.current_pagination_info.get('total_pages', 1)
        
        self.page_info_label.setText(f"{current}/{total} 页")
        self.prev_page_button.setEnabled(
            current > 1 and bool(self.current_pagination_info.get('prev_page_url'))
        )
        self.next_page_button.setEnabled(
            current < total and bool(self.current_pagination_info.get('next_page_url'))
        )
        
    def _load_prev_page(self):
        """加载上一页"""
        if not self.current_pagination_info or not self.current_pagination_info.get('prev_page_url'):
            return
            
        prev_url = self.current_pagination_info['prev_page_url']
        self._perform_search(page_url=prev_url)
        
    def _load_next_page(self):
        """加载下一页"""
        if not self.current_pagination_info or not self.current_pagination_info.get('next_page_url'):
            return
            
        next_url = self.current_pagination_info['next_page_url']
        self._perform_search(page_url=next_url)
    
    def _handle_selection_change(self, current_item, previous_item):
        """处理选择改变"""
        if not current_item:
            self._clear_novel_details()
            return
            
        novel_data = current_item.data(Qt.ItemDataRole.UserRole)
        if novel_data:
            self._load_novel_details(novel_data)
    
    def _load_novel_details(self, novel_data):
        """加载小说详情"""
        self.novel_title_label.setText(f"《{novel_data['name']}》")
        self.novel_id_label.setText(f"ID: {novel_data['id']}")
        self.novel_author_label.setText("作者: 加载中...")
        self.novel_description.setPlainText("双击查看章节信息和下载选项...")
        
        # Load cover image
        cover_path = novel_data.get('cover_image_path')
        if cover_path and os.path.exists(cover_path):
            pixmap = QPixmap(cover_path)
            if not pixmap.isNull():
                self.novel_cover_label.setPixmap(pixmap.scaled(
                    self.novel_cover_label.size(), 
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                ))
            else:
                self.novel_cover_label.setText("无法加载封面")
        else:
            self.novel_cover_label.setText("无封面")
            self.novel_cover_label.setPixmap(QPixmap())

        self.add_to_queue_button.setEnabled(True)
        self.download_now_button.setEnabled(True)
        
        # 异步加载详细信息
        if self.network_worker and self.network_worker.isRunning():
            return
            
        self.network_worker = NetworkWorker(
            "novel_details",
            self.downloader,
            parent=self,
            novel_id=novel_data['id']
        )
        
        self.network_worker.novel_details_ready.connect(self._handle_novel_details)
        self.network_worker.error.connect(self._handle_network_error)
        self.network_worker.finished.connect(self._clear_network_worker)
        self.network_worker.start()
    
    def _handle_novel_details(self, details):
        """处理小说详情"""
        self.novel_author_label.setText(f"作者: {details.get('author', '未知')}")
        self.novel_description.setPlainText("双击查看章节信息和下载选项...")
    
    def _clear_novel_details(self):
        """清空小说详情"""
        self.novel_title_label.setText("选择一本小说查看详情")
        self.novel_author_label.setText("作者: ")
        self.novel_id_label.setText("ID: ")
        self.novel_description.setPlainText("")
        self.novel_cover_label.setText("无封面")
        self.novel_cover_label.setPixmap(QPixmap())
        self.add_to_queue_button.setEnabled(False)
        self.download_now_button.setEnabled(False)
    
    def _handle_double_click(self, item):
        """处理双击事件 - 显示章节信息"""
        novel_data = item.data(Qt.ItemDataRole.UserRole)
        if not novel_data:
            return
            
        self._show_chapter_info(novel_data)
    
    def _show_chapter_info(self, novel_data):
        """显示章节信息对话框"""
        if self.network_worker and self.network_worker.isRunning():
            QMessageBox.information(self, "请稍候", "正在加载其他信息，请稍后再试")
            return
            
        self.status_bar.showMessage("正在获取章节信息...")
        
        # 先获取小说详情
        self.network_worker = NetworkWorker(
            "novel_details",
            self.downloader,
            parent=self,
            novel_id=novel_data['id']
        )
        
        def on_details_ready(details):
            if details and details.get('catalog_url'):
                # 获取章节列表
                chapter_worker = NetworkWorker(
                    "chapter_list",
                    self.downloader,
                    parent=self,
                    catalog_url=details['catalog_url']
                )
                
                def on_chapters_ready(volumes):
                    if volumes:
                        dialog = ChapterInfoDialog(novel_data, volumes, self)
                        if dialog.exec() == QDialog.DialogCode.Accepted:
                            # 根据用户选择处理
                            if dialog.download_type == 'queue':
                                self._add_novel_to_queue(novel_data, dialog.selected_volume_indices)
                            elif dialog.download_type == 'now':
                                self._start_download_from_dialog(novel_data, dialog.selected_volume_indices)
                    else:
                        QMessageBox.warning(self, "错误", "无法获取章节信息")
                    self.status_bar.showMessage("准备就绪")
                
                chapter_worker.chapter_list_ready.connect(on_chapters_ready)
                chapter_worker.error.connect(lambda msg, op: QMessageBox.warning(self, "错误", f"获取章节信息失败: {msg}"))
                chapter_worker.finished.connect(lambda: setattr(self, 'network_worker', None))
                chapter_worker.start()
                self.network_worker = chapter_worker
            else:
                QMessageBox.warning(self, "错误", "无法获取小说详情")
                self.status_bar.showMessage("准备就绪")
        
        self.network_worker.novel_details_ready.connect(on_details_ready)
        self.network_worker.error.connect(lambda msg, op: QMessageBox.warning(self, "错误", f"获取小说详情失败: {msg}"))
        self.network_worker.finished.connect(lambda: None)  # 这里不清空，因为可能有后续操作
        self.network_worker.start()
    
    def _add_novel_to_queue(self, novel_data, volume_indices):
        """将小说（带卷选择）添加到下载队列"""
        # 检查是否已在队列中
        for existing_item in self.download_queue:
            if (existing_item['novel_data']['id'] == novel_data['id'] and 
                existing_item.get('volume_indices') == volume_indices):
                self.status_bar.showMessage("该下载任务已在队列中", 3000)
                return
        
        # 创建下载任务
        download_task = {
            'novel_data': novel_data,
            'volume_indices': volume_indices,
            'download_type': 'full' if not volume_indices else ('volume' if len(volume_indices) == 1 else 'range')
        }
        
        self.download_queue.append(download_task)
        
        # 生成描述
        if not volume_indices:
            desc = "整本小说"
        elif len(volume_indices) == 1:
            desc = f"第{volume_indices[0]+1}卷"
        else:
            volume_names = [f"第{i+1}卷" for i in volume_indices]
            desc = f"({', '.join(volume_names)})"
        
        # 更新队列列表
        queue_item = QListWidgetItem(
            f"《{novel_data['name']}》 {desc} - 等待下载"
        )
        queue_item.setData(Qt.ItemDataRole.UserRole, download_task)
        self.queue_list.addItem(queue_item)
        
        self.status_bar.showMessage(f"已添加《{novel_data['name']}》 {desc} 到下载队列", 3000)
    
    def _start_download_from_dialog(self, novel_data, volume_indices):
        """从对话框开始下载"""
        if self.download_worker and self.download_worker.isRunning():
            reply = QMessageBox.question(
                self, 
                "下载中", 
                "当前有下载任务正在进行，是否要停止当前下载并开始新的下载？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._pause_download()
            else:
                return
        
        download_type = 'full' if not volume_indices else ('volume' if len(volume_indices) == 1 else 'range')
        self._start_single_download(novel_data, download_type, volume_indices)
    
    def _add_to_download_queue(self):
        """添加到下载队列（整本小说）"""
        current_item = self.results_list.currentItem()
        if not current_item:
            return
            
        novel_data = current_item.data(Qt.ItemDataRole.UserRole)
        if not novel_data:
            return
        
        self._add_novel_to_queue(novel_data, [])  # 空列表表示整本小说
    
    def _download_now(self):
        """立即下载（整本小说）"""
        current_item = self.results_list.currentItem()
        if not current_item:
            return
            
        novel_data = current_item.data(Qt.ItemDataRole.UserRole)
        if not novel_data:
            return
            
        if self.download_worker and self.download_worker.isRunning():
            reply = QMessageBox.question(
                self, 
                "下载中", 
                "当前有下载任务正在进行，是否要停止当前下载并开始新的下载？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._pause_download()
            else:
                return
                
        self._start_single_download(novel_data, 'full', [])
    
    def _start_single_download(self, novel_data, download_type='full', volume_indices=None):
        """开始单个下载"""
        if not self.settings.get('output_dir'):
            QMessageBox.warning(self, "设置错误", "请先在设置中指定输出目录")
            self._open_settings_tab()
            return
        
        volume_indices = volume_indices or []
        novel_name = novel_data.get('name', f"UnknownNovel_{novel_data['id']}")
        
        # 生成描述
        if download_type == 'full':
            download_desc = "整本小说"
        elif len(volume_indices) == 1:
            download_desc = f"第{volume_indices[0]+1}卷"
        else:
            volume_names = [f"第{i+1}卷" for i in volume_indices]
            download_desc = f"({', '.join(volume_names)})"
        
        self.current_download_label.setText(f"当前下载: 《{novel_name}》{download_desc}")
        self.download_progress_bar.setRange(0, 0)  # 不确定进度
        
        self.download_worker = DownloadWorker(
            self.downloader,
            novel_data['id'],
            novel_name,
            self.settings['output_dir'],
            self.settings.get('max_retries', 3),
            download_type,
            volume_indices,
            parent=self
        )
        
        self.download_worker.progress_update.connect(self._handle_download_progress)
        self.download_worker.download_complete.connect(self._handle_download_complete)
        self.download_worker.start()
        
        self.pause_queue_button.setEnabled(True)
        self.start_queue_button.setEnabled(False)
        
        # 切换到下载队列标签页
        self.tab_widget.setCurrentWidget(self.queue_tab)
    
    def _start_queue_download(self):
        """开始队列下载"""
        if not self.download_queue:
            self.status_bar.showMessage("下载队列为空", 3000)
            return
            
        if self.download_worker and self.download_worker.isRunning():
            self.status_bar.showMessage("已有下载任务在进行中", 3000)
            return
            
        # 取出队列中的第一个
        download_task = self.download_queue.pop(0)
        novel_data = download_task['novel_data']
        volume_indices = download_task['volume_indices']
        download_type = download_task['download_type']
        
        # 更新队列显示
        self._update_queue_display()
        
        self._start_single_download(novel_data, download_type, volume_indices)
    
    def _pause_download(self):
        """暂停/取消下载"""
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.download_worker.wait()  # 等待线程结束
            
        self.current_download_label.setText("当前下载: 无")
        self.download_progress_bar.setRange(0, 100)
        self.download_progress_bar.setValue(0)
        
        self.pause_queue_button.setEnabled(False)
        self.start_queue_button.setEnabled(True)
        
        self.status_bar.showMessage("下载已暂停", 3000)
    
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
            self.status_bar.showMessage("下载队列已清空", 3000)
    
    def _update_queue_display(self):
        """更新队列显示"""
        self.queue_list.clear()
        for i, download_task in enumerate(self.download_queue):
            novel_data = download_task['novel_data']
            volume_indices = download_task['volume_indices']
            
            # 生成描述
            if not volume_indices:
                desc = "整本小说"
            elif len(volume_indices) == 1:
                desc = f"第{volume_indices[0]+1}卷"
            else:
                volume_names = [f"第{i+1}卷" for i in volume_indices]
                desc = f"({', '.join(volume_names)})"
            
            queue_item = QListWidgetItem(
                f"{i+1}. 《{novel_data['name']}》 {desc} - 等待下载"
            )
            queue_item.setData(Qt.ItemDataRole.UserRole, download_task)
            self.queue_list.addItem(queue_item)
    
    def _handle_download_progress(self, message):
        """处理下载进度更新"""
        self.download_status_text.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        self.status_bar.showMessage(message)
        
        # 自动滚动到底部
        cursor = self.download_status_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.download_status_text.setTextCursor(cursor)
    
    def _handle_download_complete(self, success, message):
        """处理下载完成"""
        self.download_progress_bar.setRange(0, 100)
        self.download_progress_bar.setValue(100 if success else 0)
        
        self.download_status_text.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        
        if success:
            self.status_bar.showMessage("下载完成！", 5000)
        else:
            self.status_bar.showMessage("下载失败", 5000)
            
        self.current_download_label.setText("当前下载: 无")
        self.pause_queue_button.setEnabled(False)
        self.start_queue_button.setEnabled(True)
        
        # 如果队列中还有项目，询问是否继续
        if self.download_queue:
            reply = QMessageBox.question(
                self,
                "继续下载",
                f"队列中还有 {len(self.download_queue)} 个下载项目，是否继续下载？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                QTimer.singleShot(2000, self._start_queue_download)  # 2秒后继续下载
    
    def _handle_network_error(self, error_msg, operation_type):
        """处理网络错误"""
        self.status_bar.showMessage(f"网络错误: {error_msg}", 5000)
        
        if operation_type == "search":
            self.results_list.clear()
        elif operation_type == "novel_details":
            self.novel_description.setPlainText(f"加载详情失败: {error_msg}")
    
    def _clear_network_worker(self):
        """清理网络工作线程"""
        self.search_button.setEnabled(True)
        self.results_list.setEnabled(True)
        self.network_worker = None
    
    # EPUB 导出相关方法
    def _browse_epub_source_dir(self):
        current_dir = self.epub_source_dir_edit.text() or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "选择EPUB源目录", current_dir)
        if directory:
            self.epub_source_dir_edit.setText(directory)
            self.epub_status_text.append(f"已选择EPUB源目录: {directory}")

    def _update_epub_novel_title_preview(self, text):
        if not self.epub_novel_title_edit.text() and text and os.path.isdir(text):
             self.epub_novel_title_edit.setText(os.path.basename(text))

    def _browse_epub_output_dir(self):
        current_dir = self.epub_output_dir_edit.text() or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "选择EPUB输出目录", current_dir)
        if directory:
            self.epub_output_dir_edit.setText(directory)
            self.epub_status_text.append(f"已选择EPUB输出目录: {directory}")

    def _start_epub_conversion(self):
        input_dir = self.epub_source_dir_edit.text().strip()
        output_dir = self.epub_output_dir_edit.text().strip()
        novel_title = self.epub_novel_title_edit.text().strip()
        author = self.epub_author_edit.text().strip() or "佚名"
        conversion_mode = self.epub_conversion_mode_combo.currentData()

        if not input_dir or not os.path.isdir(input_dir):
            QMessageBox.warning(self, "输入错误", "请选择有效的小说源文件夹。")
            return
        if not output_dir:
            QMessageBox.warning(self, "输入错误", "请选择有效的EPUB输出目录。")
            return
        if not novel_title:
            novel_title = os.path.basename(input_dir)
            self.epub_novel_title_edit.setText(novel_title)
            if not novel_title:
                QMessageBox.warning(self, "输入错误", "请输入EPUB书名。")
                return
        
        os.makedirs(output_dir, exist_ok=True)

        if self.epub_export_worker and self.epub_export_worker.isRunning():
            QMessageBox.information(self, "提示", "当前已有EPUB转换任务在进行中，请稍后再试。")
            return

        self.start_epub_conversion_button.setEnabled(False)
        self.epub_status_text.clear()
        self.epub_status_text.append("开始EPUB转换...")

        self.epub_export_worker = EpubExportWorker(
            novel_title=novel_title,
            author=author,
            input_novel_dir=input_dir,
            output_epub_dir=output_dir,
            mode=conversion_mode,
            parent=self
        )
        self.epub_export_worker.export_progress.connect(self._handle_epub_export_progress)
        self.epub_export_worker.export_finished.connect(self._handle_epub_export_finished)
        self.epub_export_worker.start()

    def _handle_epub_export_progress(self, message):
        self.epub_status_text.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        cursor = self.epub_status_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.epub_status_text.setTextCursor(cursor)

    def _handle_epub_export_finished(self, success, message):
        self.epub_status_text.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        QMessageBox.information(self, "EPUB转换完成" if success else "EPUB转换出错", message)
        self.start_epub_conversion_button.setEnabled(True)
        self.epub_export_worker = None
    
    def _open_settings_tab(self):
        """打开设置标签页"""
        self.tab_widget.setCurrentWidget(self.settings_tab)
    
    def _focus_search(self):
        """聚焦到搜索"""
        self.tab_widget.setCurrentWidget(self.search_tab)
        self.search_input.setFocus()
    
    def closeEvent(self, event):
        """关闭事件处理"""
        if self.network_worker and self.network_worker.isRunning():
            self.network_worker.quit()
            self.network_worker.wait()
            
        if self.download_worker and self.download_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "确认退出",
                "有下载任务正在进行，确定要退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
                
            self.download_worker.cancel()
            self.download_worker.wait()
            
        self._clear_novel_cache_directory(silent=True)
        event.accept()

    def _confirm_clear_cache(self):
        reply = QMessageBox.question(
            self,
            "确认清除缓存",
            "确定要清除所有已下载的封面图片缓存吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._clear_novel_cache_directory()

    def _clear_novel_cache_directory(self, silent=False):
        """Clears the novel cover cache directory."""
        cache_dir_to_clear = os.path.join(os.getcwd(), 'novel_cache')
        
        if os.path.exists(cache_dir_to_clear):
            try:
                shutil.rmtree(cache_dir_to_clear)
                if not silent:
                    QMessageBox.information(self, "缓存已清除", f"缓存文件夹 '{cache_dir_to_clear}' 已成功删除。")
                self.status_bar.showMessage("封面缓存已清除", 3000)
                # Recreate the base novel_cache and covers directory if needed for future operations
                os.makedirs(self.cover_cache_dir_path, exist_ok=True)
            except Exception as e:
                if not silent:
                    QMessageBox.warning(self, "清除缓存失败", f"无法删除缓存文件夹 '{cache_dir_to_clear}':\n{e}")
                self.status_bar.showMessage(f"清除缓存失败: {e}", 5000)
        elif not silent:
            QMessageBox.information(self, "缓存不存在", f"缓存文件夹 '{cache_dir_to_clear}' 不存在。")
            self.status_bar.showMessage("封面缓存目录不存在", 3000)

def main():
    app = QApplication(sys.argv)
    
    app.setApplicationName("轻小说文库8下载器")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("Novel Downloader")
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()