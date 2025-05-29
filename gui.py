#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QVBoxLayout, 
                            QWidget, QStatusBar, QLabel, QMessageBox,
                            QDialog, QTextBrowser, QDialogButtonBox)
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import Qt, QObject, pyqtSignal

# 导入漫画和小说的GUI模块
from manga.manga_gui import MainWindow as MangaMainWindow
from novel.novel_gui import MainWindow as NovelMainWindow

class AboutDialog(QDialog):
    """关于对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于漫画与小说下载器")
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(self)
        
        about_text = QTextBrowser(self)
        about_text.setOpenExternalLinks(True)
        about_text.setHtml("""
        <h2>漫画与小说下载器</h2>
        <p>一个集成了漫画下载和小说下载功能的应用程序。</p>
        <p>本程序支持：</p>
        <ul>
            <li>漫画搜索和下载</li>
            <li>轻小说搜索和下载</li>
            <li>EPUB格式导出</li>
        </ul>
        <p>使用方法：通过顶部的选项卡切换漫画下载器和小说下载器。</p>
        """)
        
        layout.addWidget(about_text)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

class StatusMessageProxy(QObject):
    """状态消息代理，用于将子窗口的状态消息传递到主窗口"""
    status_message = pyqtSignal(str, int)
    
    def __init__(self, parent_status_bar):
        super().__init__()
        self.parent_status_bar = parent_status_bar
        self.status_message.connect(self._show_message)
    
    def _show_message(self, message, timeout=0):
        self.parent_status_bar.showMessage(message, timeout)

    def showMessage(self, message, timeout=0):
        self.status_message.emit(message, timeout)

class IntegratedDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 设置窗口标题和大小
        self.setWindowTitle("漫画与小说下载器")
        self.setGeometry(100, 50, 1280, 800)
        
        # 创建中央部件和主布局
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        
        # 创建共享的菜单栏
        self._create_menu_bar()
        
        # 创建顶层选项卡
        self.main_tab_widget = QTabWidget()
        main_layout.addWidget(self.main_tab_widget)
        
        # 添加状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("欢迎使用漫画与小说下载器")
        
        # 创建状态消息代理
        self.status_proxy = StatusMessageProxy(self.status_bar)
        
        # 初始化漫画和小说的选项卡
        self._init_manga_tab()
        self._init_novel_tab()
        
        # 连接选项卡切换信号
        self.main_tab_widget.currentChanged.connect(self._handle_tab_change)
    
    def _create_menu_bar(self):
        """创建共享的菜单栏"""
        menu_bar = self.menuBar()
        
        # 文件菜单
        file_menu = menu_bar.addMenu("&文件")
        
        # 切换到漫画下载器
        manga_action = QAction("漫画下载器", self)
        manga_action.triggered.connect(lambda: self.main_tab_widget.setCurrentIndex(0))
        file_menu.addAction(manga_action)
        
        # 切换到小说下载器
        novel_action = QAction("小说下载器", self)
        novel_action.triggered.connect(lambda: self.main_tab_widget.setCurrentIndex(1))
        file_menu.addAction(novel_action)
        
        file_menu.addSeparator()
        
        # 退出
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 帮助菜单
        help_menu = menu_bar.addMenu("&帮助")
        
        # 关于
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)
    
    def _show_about_dialog(self):
        """显示关于对话框"""
        dialog = AboutDialog(self)
        dialog.exec()
    
    def _init_manga_tab(self):
        """初始化漫画选项卡"""
        # 创建漫画下载器容器
        manga_container = QWidget()
        manga_layout = QVBoxLayout(manga_container)
        manga_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建漫画下载器实例
        try:
            self.manga_window = MangaMainWindow()
            
            # 移除原始的菜单栏和状态栏
            self.manga_window.menuBar().setParent(None)
            
            # 替换状态栏
            if hasattr(self.manga_window, 'statusBar'):
                original_status_bar = self.manga_window.statusBar
                self.manga_window.statusBar = self.status_proxy
                # 如果状态栏是属性
                if isinstance(original_status_bar, QStatusBar):
                    original_status_bar.setParent(None)
                
            # 将漫画下载器的中央部件添加到容器中
            manga_layout.addWidget(self.manga_window.centralWidget())
            
            # 添加到主选项卡
            self.main_tab_widget.addTab(manga_container, "漫画下载器")
            
        except Exception as e:
            error_widget = QWidget()
            error_layout = QVBoxLayout(error_widget)
            error_label = QLabel(f"加载漫画下载器失败: {str(e)}")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_layout.addWidget(error_label)
            self.main_tab_widget.addTab(error_widget, "漫画下载器 (错误)")
            print(f"Error initializing manga tab: {e}")
    
    def _init_novel_tab(self):
        """初始化小说选项卡"""
        # 创建小说下载器容器
        novel_container = QWidget()
        novel_layout = QVBoxLayout(novel_container)
        novel_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建小说下载器实例
        try:
            self.novel_window = NovelMainWindow()
            
            # 移除原始的菜单栏和状态栏
            self.novel_window.menuBar().setParent(None)
            
            # 替换状态栏
            if hasattr(self.novel_window, 'status_bar'):
                original_status_bar = self.novel_window.status_bar
                self.novel_window.status_bar = self.status_proxy
                # 如果状态栏是属性
                if isinstance(original_status_bar, QStatusBar):
                    original_status_bar.setParent(None)
                
            # 将小说下载器的中央部件添加到容器中
            novel_layout.addWidget(self.novel_window.centralWidget())
            
            # 添加到主选项卡
            self.main_tab_widget.addTab(novel_container, "小说下载器")
            
        except Exception as e:
            error_widget = QWidget()
            error_layout = QVBoxLayout(error_widget)
            error_label = QLabel(f"加载小说下载器失败: {str(e)}")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_layout.addWidget(error_label)
            self.main_tab_widget.addTab(error_widget, "小说下载器 (错误)")
            print(f"Error initializing novel tab: {e}")
    
    def _handle_tab_change(self, index):
        """处理选项卡切换事件"""
        tab_name = self.main_tab_widget.tabText(index)
        self.status_bar.showMessage(f"已切换到{tab_name}")
    
    def closeEvent(self, event):
        """处理关闭窗口事件"""
        reply = QMessageBox.question(
            self, '确认退出', 
            '确定要退出应用程序吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 确保正确关闭两个子窗口
            if hasattr(self, 'manga_window'):
                try:
                    # 断开信号连接，防止关闭时发生错误
                    if hasattr(self.manga_window, 'download_worker') and self.manga_window.download_worker:
                        try:
                            self.manga_window.download_worker.cancel()
                        except:
                            pass
                    self.manga_window.close()
                except Exception as e:
                    print(f"关闭漫画窗口时出错: {e}")
            
            if hasattr(self, 'novel_window'):
                try:
                    # 断开信号连接，防止关闭时发生错误
                    if hasattr(self.novel_window, 'download_worker') and self.novel_window.download_worker:
                        try:
                            self.novel_window.download_worker.cancel()
                        except:
                            pass
                    self.novel_window.close()
                except Exception as e:
                    print(f"关闭小说窗口时出错: {e}")
                
            event.accept()
        else:
            event.ignore()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 设置应用图标（如果有）
    if os.path.exists('icon.ico'):
        app.setWindowIcon(QIcon('icon.ico'))
    elif os.path.exists('icon.icns'):
        app.setWindowIcon(QIcon('icon.icns'))
    
    window = IntegratedDownloaderApp()
    window.show()
    sys.exit(app.exec()) 