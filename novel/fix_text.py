#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re

def fix_txt_file(file_path):
    """修复单个txt文件中的换行符问题"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 修复字符串形式的换行符
        content = content.replace('\\n', '\n')
        content = content.replace('\\r\\n', '\n')
        content = content.replace('\\r', '\n')
        
        # 标准化换行符
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # 压缩多个连续空行为最多两个换行符
        content = re.sub(r'\n{3,}', '\n\n', content)
        
        # 处理章节标记，为它们添加适当的间距
        # 识别只包含数字的行作为章节标题（包括全角和半角数字）
        content = re.sub(r'\n([０-９0-9]+)\n', r'\n\n\1\n\n', content)
        
        # 识别"第X章/节"等格式的章节标题
        content = re.sub(r'\n(第[０-９0-9一二三四五六七八九十百千]+[章节].*?)\n', r'\n\n\1\n\n', content)
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"已修复: {file_path}")
        return True
        
    except Exception as e:
        print(f"修复失败 {file_path}: {e}")
        return False

def fix_all_txt_files(directory):
    """修复目录下所有txt文件"""
    fixed_count = 0
    total_count = 0
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.txt'):
                file_path = os.path.join(root, file)
                total_count += 1
                if fix_txt_file(file_path):
                    fixed_count += 1
    
    print(f"\n修复完成: {fixed_count}/{total_count} 个文件")

if __name__ == "__main__":
    # 使用示例
    novels_dir = "../novels"  # 替换为你的小说目录
    
    if os.path.exists(novels_dir):
        print(f"开始修复 {novels_dir} 目录下的txt文件...")
        fix_all_txt_files(novels_dir)
    else:
        print(f"目录不存在: {novels_dir}")
        print("请修改脚本中的 novels_dir 变量为正确的路径")