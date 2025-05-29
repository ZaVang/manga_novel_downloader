#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import zipfile
import datetime
from xml.sax.saxutils import escape as xml_escape
import uuid

_CH_NUM_MAP = {
    '零':0, '一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9,
    '壹':1, '贰':2, '叁':3, '肆':4, '伍':5, '陆':6, '柒':7, '捌':8, '玖':9
}

def _chinese_to_arabic_for_vol(cn_str):
    """
    将简单的中文数字字符串转换为阿拉伯数字。
    支持如 "一", "十", "十一", "二十", "二十三", "百", "一百", "二百三十五" 等常见卷号模式。
    主要覆盖到百位。
    """
    if not cn_str or not isinstance(cn_str, str):
        return None

    if len(cn_str) == 1:
        if cn_str in _CH_NUM_MAP:
            return _CH_NUM_MAP[cn_str]
        if cn_str in ['十', '拾']:
            return 10
        if cn_str in ['百', '佰']:
             return 100
        return None

    if (cn_str.startswith('十') or cn_str.startswith('拾')) and len(cn_str) == 2:
        if cn_str[1] in _CH_NUM_MAP:
            return 10 + _CH_NUM_MAP[cn_str[1]]
        return None

    if len(cn_str) == 2 and cn_str[0] in _CH_NUM_MAP and (cn_str[1] in ['十', '拾']):
        return _CH_NUM_MAP[cn_str[0]] * 10
        
    if len(cn_str) == 3 and \
       cn_str[0] in _CH_NUM_MAP and \
       (cn_str[1] in ['十', '拾']) and \
       cn_str[2] in _CH_NUM_MAP:
        return _CH_NUM_MAP[cn_str[0]] * 10 + _CH_NUM_MAP[cn_str[2]]

    if len(cn_str) == 2 and cn_str[0] in _CH_NUM_MAP and (cn_str[1] in ['百', '佰']):
        return _CH_NUM_MAP[cn_str[0]] * 100
    
    if (cn_str.startswith('百') or cn_str.startswith('佰') or (len(cn_str) > 1 and cn_str[1] in ['百', '佰'])) and \
        not (cn_str.startswith('十') or cn_str.startswith('拾')):
        
        n_str = cn_str.replace('佰', '百').replace('拾', '十')
        if n_str == "百": return 100
        idx = 0
        temp_total = 0
        
        # 处理百位
        if idx < len(n_str) and n_str[idx] in _CH_NUM_MAP:
            digit = _CH_NUM_MAP[n_str[idx]]
            idx += 1
            if idx < len(n_str) and n_str[idx] == '百':
                temp_total += digit * 100
                idx += 1
            else: 
                return None
        elif n_str.startswith('百'):
            temp_total += 100
            idx +=1

        if idx < len(n_str) and n_str[idx] == '零':
            idx += 1
            if idx < len(n_str) and n_str[idx] in _CH_NUM_MAP:
                 if not (idx + 1 < len(n_str) and n_str[idx+1] in ['十', '拾']):
                    temp_total += _CH_NUM_MAP[n_str[idx]]
                    idx += 1

        # 处理十位
        ten_digit_processed = False
        if idx < len(n_str):
            if n_str[idx] in _CH_NUM_MAP:
                digit = _CH_NUM_MAP[n_str[idx]]
                if idx + 1 < len(n_str) and n_str[idx+1] in ['十', '拾']:
                    temp_total += digit * 10
                    idx += 2
                    ten_digit_processed = True
                else: 
                    if not ten_digit_processed and temp_total % 10 == 0: 
                        temp_total += digit 
                    idx +=1
            elif n_str[idx] in ['十', '拾']:
                temp_total += 10
                idx += 1
                ten_digit_processed = True
        if idx < len(n_str) and n_str[idx] in _CH_NUM_MAP:
             if temp_total % 10 == 0 or ten_digit_processed :
                temp_total += _CH_NUM_MAP[n_str[idx]]
                idx +=1
        
        if temp_total > 0 and idx == len(n_str):
            return temp_total
            
    return None


def extract_file_number(filename):
    """从文件名中提取编号用于排序"""
    # 匹配开头的三位数编号，如 001_xxx.txt, 010_xxx.jpg
    match = re.match(r'^(\d{3})_', filename)
    if match:
        return int(match.group(1))
    
    # 如果没有找到三位数编号，尝试匹配任意数字开头
    match = re.match(r'^(\d+)', filename)
    if match:
        return int(match.group(1))
    
    # 如果没有找到数字，返回一个很大的数，让它排在后面
    return 9999


def group_files_by_number(file_paths):
    """将文件按编号分组"""
    grouped_files = {}
    
    for file_path in file_paths:
        filename = os.path.basename(file_path)
        file_number = extract_file_number(filename)
        
        if file_number not in grouped_files:
            grouped_files[file_number] = {
                'txt_files': [],
                'image_files': []
            }
        
        if filename.lower().endswith('.txt'):
            grouped_files[file_number]['txt_files'].append(file_path)
        elif filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
            grouped_files[file_number]['image_files'].append(file_path)
    
    return grouped_files


class SimpleEpubGenerator:
    def __init__(self, title, author="Unknown Author", language="zh"):
        self.title = title
        self.author = author
        self.language = language
        self.book_id = str(uuid.uuid4())
        self.chapters = []
        self.images = []  # 存储章节内的图片
        self.cover_image_info = None
        
    def clean_text(self, text):
        """清理文本内容（不截断）"""
        if not text:
            return ""

        text = text.replace('\\r\\n', '\n')
        text = text.replace('\\n', '\n')
        text = text.replace('\ufeff', '')
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'^\s*$\n(?:^\s*$\n)+', '\n', text, flags=re.MULTILINE)
        
        return text.strip()
    
    def parse_chapter_content(self, content):
        """解析章节内容，提取标题和正文"""
        lines = content.split('\n')
        
        parsed_title = None
        main_content_lines = []
        title_found = False
        content_should_start_after_this_line_index = -1

        for i, line_text in enumerate(lines):
            stripped_line = line_text.strip()

            if not title_found:
                if stripped_line.startswith('#'):
                    parsed_title = stripped_line.lstrip('#').strip()
                    title_found = True
                    content_should_start_after_this_line_index = i
                    continue # Title found, move to content gathering phase potentially

                # Skip meta-information or empty lines if title not yet found
                is_meta_or_empty = (
                    '台版' in stripped_line or '转自' in stripped_line or '发布：' in stripped_line or
                    '论坛：' in stripped_line or stripped_line == '' or
                    re.match(r'^０+\d*$', stripped_line)
                )
                if is_meta_or_empty:
                    continue # Skip this line, look for title in next lines
                
                parsed_title = stripped_line
                title_found = True
                content_should_start_after_this_line_index = i

            else:
                if i > content_should_start_after_this_line_index:
                    main_content_lines.append(line_text) 

        if not parsed_title:
            parsed_title = "未命名章节"

        # 处理内容，将章节标记转换为小标题
        processed_content = self._process_sub_chapters('\n'.join(main_content_lines))
        
        return parsed_title, processed_content
    
    def _process_sub_chapters(self, content):
        """处理子章节标记，将它们转换为小标题"""
        if not content:
            return content
            
        lines = content.split('\n')
        processed_lines = []
        
        for line in lines:
            stripped = line.strip()
            # 检查是否是章节标记（如０４１、０４２、001、002等）
            if re.match(r'\n([０-９0-9]+)\n', stripped):
                # 将章节标记转换为小标题格式
                processed_lines.append('')  # 空行分隔
                processed_lines.append(f'## {stripped}')
                processed_lines.append('')  # 空行分隔
            else:
                processed_lines.append(line)
        
        return '\n'.join(processed_lines)
    
    def add_image(self, image_path, image_id=None):
        """添加图片到EPUB中"""
        if not os.path.isfile(image_path):
            print(f"警告: 图片文件不存在: {image_path}")
            return None
        
        filename = os.path.basename(image_path)
        file_ext = filename.split('.')[-1].lower()
        
        # 确定媒体类型
        mime_type_map = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'bmp': 'image/bmp'
        }
        
        if file_ext not in mime_type_map:
            print(f"警告: 不支持的图片格式: {file_ext}")
            return None
        
        # 生成唯一的ID
        if not image_id:
            image_id = f"img_{len(self.images)}"
        
        # 生成EPUB内部的文件名
        epub_filename = f"{image_id}.{file_ext}"
        
        image_info = {
            'original_path': image_path,
            'epub_path': f"Images/{epub_filename}",
            'id': image_id,
            'media_type': mime_type_map[file_ext],
            'filename': epub_filename
        }
        
        self.images.append(image_info)
        print(f"添加图片: {filename} -> {epub_filename}")
        return image_info
    
    def text_to_html_paragraphs(self, text, chapter_images=None):
        """将文本转换为HTML段落，保留原始换行并处理小标题和图片。"""
        if not text.strip() and not chapter_images:
            return "    <p> </p>"
        
        html_parts = []
        
        # 如果有图片，先添加图片
        if chapter_images:
            for img_info in chapter_images:
                html_parts.append(f'    <div class="image-container">')
                html_parts.append(f'        <img src="../{img_info["epub_path"]}" alt="插图" class="chapter-image"/>')
                html_parts.append(f'    </div>')
        
        # 如果没有文本内容，只返回图片
        if not text.strip():
            return '\n'.join(html_parts) if html_parts else "    <p> </p>"
        
        # 按空行分割文本成段落块
        paragraph_blocks = re.split(r'\n\s*\n', text.strip())
        
        for block_text in paragraph_blocks:
            block_text = block_text.strip()
            if not block_text:
                continue
            
            # 检查是否是小标题（以##开头）
            if block_text.startswith('## '):
                title_text = block_text[3:].strip()
                html_parts.append(f"    <h2>{xml_escape(title_text)}</h2>")
                continue
            
            # 先对整个文本块进行HTML转义
            escaped_block_text = xml_escape(block_text)
            
            # 在HTML转义过的文本中，将换行符替换为<br />
            html_content_for_p_tag = escaped_block_text.replace('\n', '<br />\n')
            
            html_parts.append(f"    <p>{html_content_for_p_tag}</p>")
        
        return '\n'.join(html_parts) if html_parts else "    <p> </p>"
    
    def _generate_unique_filename(self, title_str, base_prefix="chapter"):
        """根据标题生成一个在当前EPUB实例中唯一的文件名。"""
        safe_filename_base = re.sub(r'[^\w\s-]', '', str(title_str)).strip()
        safe_filename_base = re.sub(r'[-\s]+', '-', safe_filename_base)
        
        if not safe_filename_base:
            # 如果标题处理后为空（例如，标题全是特殊符号，或为空字符串）
            # 使用基本前缀和章节计数器
            idx = len(self.chapters)
            while True:
                safe_filename_base = f"{base_prefix}_{idx}"
                candidate_xhtml = f"{safe_filename_base}.xhtml"
                if not any(ch['filename'] == candidate_xhtml for ch in self.chapters):
                    break
                idx +=1
            return candidate_xhtml

        candidate_xhtml = f"{safe_filename_base}.xhtml"
        if not any(ch['filename'] == candidate_xhtml for ch in self.chapters):
            return candidate_xhtml

        # 如果存在文件名冲突，添加计数器
        counter = 1
        while True:
            candidate_xhtml = f"{safe_filename_base}_{counter}.xhtml"
            if not any(ch['filename'] == candidate_xhtml for ch in self.chapters):
                return candidate_xhtml
            counter += 1

    def add_raw_chapter(self, title: str, body_text: str, chapter_images=None):
        """直接添加章节，使用明确的标题和正文。正文会被清理。"""
        if not title:
            print("警告: 尝试添加无标题章节 (raw), 已跳过。")
            return False
            
        # clean_text 应该在这里处理 body_text，因为它只包含纯文本内容
        cleaned_body = self.clean_text(body_text) 
        
        chapter_filename = self._generate_unique_filename(title)
        chapter_id = f"ch_{chapter_filename.replace('.xhtml', '').replace('-', '_').replace('.', '_')}"

        chapter_info = {
            'title': title,
            'content': cleaned_body, 
            'filename': chapter_filename,
            'id': chapter_id,
            'images': chapter_images or []
        }
        self.chapters.append(chapter_info)
        
        image_count = len(chapter_images) if chapter_images else 0
        print(f"添加章节 (raw): {title} ({len(cleaned_body)} 字符, {image_count} 张图片)")
        return True

    def add_chapter_via_parser(self, full_content_string: str, chapter_images=None):
        """通过内部解析器从完整内容字符串中提取标题和正文来添加章节。"""
        cleaned_content = self.clean_text(full_content_string)
        if not cleaned_content.strip() and not chapter_images: # 如果清理后内容为空且没有图片
            print("警告: 提供的章节内容 (via parser) 为空或仅含空白，且无图片，已跳过。")
            return False
        
        title, main_content = self.parse_chapter_content(cleaned_content)
        
        chapter_filename = self._generate_unique_filename(title)
        # ID生成应确保唯一性且符合XML ID规范
        chapter_id = f"ch_{chapter_filename.replace('.xhtml', '').replace('-', '_').replace('.', '_')}"

        chapter_info = {
            'title': title,
            'content': main_content,
            'filename': chapter_filename,
            'id': chapter_id,
            'images': chapter_images or []
        }
        self.chapters.append(chapter_info)
        
        image_count = len(chapter_images) if chapter_images else 0
        print(f"添加章节 (parsed): {title} ({len(main_content)} 字符, {image_count} 张图片)")
        return True
        
    def add_chapter_from_file(self, file_path, chapter_images=None):
        """从文件添加章节"""
        # 尝试多种编码读取文件
        content = None
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16', 'utf-16le']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                print(f"使用 {encoding} 编码成功读取: {os.path.basename(file_path)}")
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        if content is None:
            print(f"警告: 无法读取文件 {file_path}")
            return False
        
        return self.add_chapter_via_parser(content, chapter_images)

    def set_cover_image(self, image_path):
        """设置封面图片"""
        if not image_path or not os.path.isfile(image_path):
            print(f"警告: 封面图片路径无效或文件不存在: {image_path}")
            return False

        filename = os.path.basename(image_path)
        file_ext = filename.split('.')[-1].lower()
        mime_type = None

        if file_ext in ['jpg', 'jpeg']:
            mime_type = 'image/jpeg'
        elif file_ext == 'png':
            mime_type = 'image/png'
        else:
            print(f"警告: 不支持的封面图片格式: {file_ext}. 请使用 jpg, jpeg, 或 png.")
            return False

        # 规范化EPUB内部的封面图片名
        epub_cover_filename = f"cover.{file_ext}"
        self.cover_image_info = {
            'original_path': image_path,
            'epub_path': f"Images/{epub_cover_filename}",
            'id': 'cover-image',
            'media_type': mime_type
        }
        print(f"设置封面图片: {filename}")
        return True
    
    def generate_chapter_xhtml(self, chapter):
        """生成章节的XHTML内容"""
        html_content = self.text_to_html_paragraphs(chapter['content'], chapter.get('images'))
        
        xhtml = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <title>{xml_escape(chapter['title'])}</title>
    <link rel="stylesheet" type="text/css" href="../Styles/style.css"/>
</head>
<body>
    <h1>{xml_escape(chapter['title'])}</h1>
{html_content}
</body>
</html>'''
        return xhtml
    
    def generate_container_xml(self):
        """生成container.xml"""
        return '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>'''
    
    def generate_content_opf(self):
        """生成content.opf"""
        # 生成manifest项目
        manifest_items = []
        
        # 添加章节
        for chapter in self.chapters:
            manifest_items.append(f'    <item id="{chapter["id"]}" href="Text/{chapter["filename"]}" media-type="application/xhtml+xml"/>')
        
        # 添加章节内图片
        for image in self.images:
            manifest_items.append(f'    <item id="{image["id"]}" href="{image["epub_path"]}" media-type="{image["media_type"]}"/>')
        
        # 生成spine项目
        spine_items = []
        for chapter in self.chapters:
            spine_items.append(f'    <itemref idref="{chapter["id"]}"/>')
        
        current_time = datetime.datetime.now().isoformat()
        
        opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package version="3.0" unique-identifier="BookId" xmlns="http://www.idpf.org/2007/opf">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
        <dc:identifier id="BookId">urn:uuid:{self.book_id}</dc:identifier>
        <dc:title>{xml_escape(self.title)}</dc:title>
        <dc:creator>{xml_escape(self.author)}</dc:creator>
        <dc:language>{self.language}</dc:language>
        <dc:date>{current_time}</dc:date>
        <meta property="dcterms:modified">{current_time}</meta>
        {f'<meta name="cover" content="{self.cover_image_info["id"]}"/>' if self.cover_image_info else ''}
    </metadata>
    <manifest>
        <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
        <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
        <item id="style" href="Styles/style.css" media-type="text/css"/>
        {f'<item id="{self.cover_image_info["id"]}" href="{self.cover_image_info["epub_path"]}" media-type="{self.cover_image_info["media_type"]}" properties="cover-image"/>' if self.cover_image_info else ''}
{chr(10).join(manifest_items)}
    </manifest>
    <spine toc="ncx">
        <itemref idref="nav"/>
{chr(10).join(spine_items)}
    </spine>
</package>'''
        return opf
    
    def generate_toc_ncx(self):
        """生成toc.ncx"""
        # 生成导航点
        nav_points = []
        for i, chapter in enumerate(self.chapters, 1):
            nav_points.append(f'''    <navPoint id="navPoint-{i}" playOrder="{i}">
        <navLabel>
            <text>{xml_escape(chapter['title'])}</text>
        </navLabel>
        <content src="Text/{chapter['filename']}"/>
    </navPoint>''')
        
        ncx = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
    <head>
        <meta name="dtb:uid" content="urn:uuid:{self.book_id}"/>
        <meta name="dtb:depth" content="1"/>
        <meta name="dtb:totalPageCount" content="0"/>
        <meta name="dtb:maxPageNumber" content="0"/>
    </head>
    <docTitle>
        <text>{xml_escape(self.title)}</text>
    </docTitle>
    <navMap>
{chr(10).join(nav_points)}
    </navMap>
</ncx>'''
        return ncx
    
    def generate_nav_xhtml(self):
        """生成nav.xhtml"""
        # 生成目录列表
        toc_items = []
        for chapter in self.chapters:
            toc_items.append(f'        <li><a href="Text/{chapter["filename"]}">{xml_escape(chapter["title"])}</a></li>')
        
        nav = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>目录</title>
    <link rel="stylesheet" type="text/css" href="Styles/style.css"/>
</head>
<body>
    <nav epub:type="toc" id="toc">
        <h1>目录</h1>
        <ol>
{chr(10).join(toc_items)}
        </ol>
    </nav>
</body>
</html>'''
        return nav
    
    def generate_css(self):
        """生成CSS样式"""
        return '''/* EPUB样式表 */
body {
    font-family: "SimSun", "宋体", serif;
    font-size: 1em;
    line-height: 1.6;
    margin: 1em;
    text-align: justify;
}

h1 {
    font-size: 1.5em;
    font-weight: bold;
    text-align: center;
    margin: 1em 0;
    border-bottom: 1px solid #ccc;
    padding-bottom: 0.5em;
}

h2 {
    font-size: 1.2em;
    font-weight: bold;
    margin: 1em 0 0.5em 0;
    color: #333;
}

p {
    margin: 0.8em 0;
    text-indent: 2em;
}

.image-container {
    text-align: center;
    margin: 1em 0;
}

.chapter-image {
    max-width: 100%;
    height: auto;
    margin: 0.5em 0;
}

nav#toc h1 {
    border-bottom: 2px solid #333;
}

nav#toc ol {
    list-style-type: none;
    padding-left: 0;
}

nav#toc li {
    margin: 0.5em 0;
    padding: 0.2em 0;
}

nav#toc a {
    text-decoration: none;
    color: #333;
}

nav#toc a:hover {
    color: #666;
    text-decoration: underline;
}'''
    
    def save_epub(self, output_path):
        """保存EPUB文件"""
        if not self.chapters:
            print("错误: 没有章节内容")
            return False
        
        print(f"开始生成EPUB文件: {output_path}")
        print(f"包含 {len(self.chapters)} 个章节")
        print(f"包含 {len(self.images)} 张章节内图片")
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as epub_zip:
                # 添加mimetype文件（必须是第一个，且不压缩）
                epub_zip.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
                
                # 添加META-INF/container.xml
                epub_zip.writestr('META-INF/container.xml', self.generate_container_xml())
                
                # 添加OEBPS文件
                epub_zip.writestr('OEBPS/content.opf', self.generate_content_opf())
                epub_zip.writestr('OEBPS/toc.ncx', self.generate_toc_ncx())
                epub_zip.writestr('OEBPS/nav.xhtml', self.generate_nav_xhtml())
                epub_zip.writestr('OEBPS/Styles/style.css', self.generate_css())
                
                # 添加封面图片
                if self.cover_image_info:
                    epub_zip.write(self.cover_image_info['original_path'], f"OEBPS/{self.cover_image_info['epub_path']}")
                    print(f"添加封面图片: {self.cover_image_info['epub_path']}")

                # 添加章节内图片
                for image in self.images:
                    epub_zip.write(image['original_path'], f"OEBPS/{image['epub_path']}")
                    print(f"添加章节图片: {image['epub_path']}")

                # 添加章节文件
                for chapter in self.chapters:
                    chapter_xhtml = self.generate_chapter_xhtml(chapter)
                    epub_zip.writestr(f'OEBPS/Text/{chapter["filename"]}', chapter_xhtml)
                    print(f"添加章节文件: {chapter['filename']}")
                
            print(f"EPUB文件生成成功: {output_path}")
            return True
            
        except Exception as e:
            print(f"生成EPUB文件时出错: {e}")
            return False


def extract_volume_number(folder_name):
    """从文件夹名中提取卷号用于排序"""
    chinese_chars_for_num = "零一二三四五六七八九十百壹贰叁肆伍陆柒捌玖拾佰"
    
    # 优先匹配中文卷名格式
    # 格式: "第[中文数]卷", "第[中文数]季", "卷[中文数]"
    patterns_cn = [
        rf'第([{chinese_chars_for_num}]+)卷',
        rf'第([{chinese_chars_for_num}]+)季',
        rf'卷([{chinese_chars_for_num}]+)'
    ]
    
    for pattern in patterns_cn:
        match = re.search(pattern, folder_name)
        if match:
            cn_num_str = match.group(1)
            num = _chinese_to_arabic_for_vol(cn_num_str)
            if num is not None:
                return num

    # 匹配 "第x卷" 格式 (阿拉伯数字)
    match = re.search(r'第(\d+)卷', folder_name)
    if match:
        return int(match.group(1))
    
    # 匹配 "第x季" 格式 (阿拉伯数字)
    match = re.search(r'第(\d+)季', folder_name)
    if match:
        return int(match.group(1))
    
    # 匹配 "卷x" 格式 (阿拉伯数字)
    match = re.search(r'卷(\d+)', folder_name)
    if match:
        return int(match.group(1))

    if folder_name and all(c in chinese_chars_for_num for c in folder_name):
        num = _chinese_to_arabic_for_vol(folder_name)
        if num is not None:
            return num
            
    # 匹配纯数字开头 (阿拉伯数字)
    match = re.match(r'^(\d+)', folder_name)
    if match:
        return int(match.group(1))
    
    # 匹配 "Volume x" 或 "Vol x" 格式 (阿拉伯数字)
    match = re.search(r'(?:Volume|Vol)\.?\s*(\d+)', folder_name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # 如果没有找到数字，返回一个很大的数，让它排在后面
    return 9999


def find_cover_image(directory_path):
    """在指定目录中查找第一个支持的封面图片。"""
    supported_extensions = ('.jpg', '.jpeg', '.png')
    image_files = []
    try:
        for item in os.listdir(directory_path):
            item_path = os.path.join(directory_path, item)
            if os.path.isfile(item_path) and item.lower().endswith(supported_extensions):
                image_files.append(item_path)
    except OSError as e:
        print(f"读取目录 {directory_path} 时出错: {e}")
        return None

    if not image_files:
        return None

    image_files.sort() # 按文件名排序，确保一致性
    return image_files[0]


def discover_and_convert_novels(input_dir, output_dir, novel_title, author="Unknown Author", cover_image_path=None):
    """发现并转换小说文件 - 单卷模式，支持txt和图片文件"""
    if not os.path.isdir(input_dir):
        print(f"错误: 输入目录不存在 {input_dir}")
        return False
    
    # 查找所有相关文件（txt和图片）
    all_files = []
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.lower().endswith(('.txt', '.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                all_files.append(os.path.join(root, file))
    
    if not all_files:
        print(f"错误: 在 {input_dir} 中未找到txt或图片文件")
        return False
    
    # 按编号分组文件
    grouped_files = group_files_by_number(all_files)
    
    if not grouped_files:
        print("错误: 没有找到带编号的文件")
        return False
    
    # 按编号排序
    sorted_numbers = sorted(grouped_files.keys())
    
    print(f"找到 {len(sorted_numbers)} 个编号组")
    
    # 创建EPUB生成器
    epub_gen = SimpleEpubGenerator(novel_title, author)
    
    # 设置封面（如果找到）
    if cover_image_path:
        epub_gen.set_cover_image(cover_image_path)
    
    # 按编号顺序处理每组文件
    for number in sorted_numbers:
        group = grouped_files[number]
        txt_files = group['txt_files']
        image_files = group['image_files']
        
        # 处理图片
        chapter_images = []
        for img_path in sorted(image_files):  # 按文件名排序
            img_info = epub_gen.add_image(img_path, f"img_{number}_{len(chapter_images)}")
            if img_info:
                chapter_images.append(img_info)
        
        # 处理文本文件
        if txt_files:
            # 如果有多个txt文件，合并内容
            combined_content = ""
            for txt_file in sorted(txt_files):  # 按文件名排序
                try:
                    content = None
                    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16', 'utf-16le']
                    
                    for encoding in encodings:
                        try:
                            with open(txt_file, 'r', encoding=encoding) as f:
                                content = f.read()
                            break
                        except (UnicodeDecodeError, UnicodeError):
                            continue
                    
                    if content:
                        combined_content += content + "\n\n"
                        print(f"读取文件: {os.path.basename(txt_file)}")
                    else:
                        print(f"警告: 无法读取文件 {txt_file}")
                        
                except Exception as e:
                    print(f"警告: 读取文件 {txt_file} 时出错: {e}")
            
            if combined_content.strip():
                success = epub_gen.add_chapter_via_parser(combined_content, chapter_images)
                if not success:
                    print(f"警告: 跳过编号 {number} 的文本内容")
            elif chapter_images:
                # 如果没有文本但有图片，创建一个只包含图片的章节
                chapter_title = f"插图 {number:03d}"
                epub_gen.add_raw_chapter(chapter_title, "", chapter_images)
        elif chapter_images:
            # 如果只有图片没有文本，创建一个只包含图片的章节
            chapter_title = f"插图 {number:03d}"
            epub_gen.add_raw_chapter(chapter_title, "", chapter_images)
    
    if not epub_gen.chapters:
        print("错误: 没有成功添加任何章节")
        return False
    
    # 生成EPUB文件
    output_file = os.path.join(output_dir, f"{novel_title}.epub")
    return epub_gen.save_epub(output_file)


def convert_single_volume(input_dir, output_dir, novel_title, author="Unknown Author"):
    """转换单个卷（目录中的所有txt和图片文件）"""
    # 尝试查找封面图片
    cover_image_path = find_cover_image(input_dir)
    
    return discover_and_convert_novels(input_dir, output_dir, novel_title, author, cover_image_path)


def convert_multiple_volumes_to_single_epub(base_dir, output_dir, base_title, author="Unknown Author"):
    """将多个卷合并转换为单个EPUB文件，支持txt和图片"""
    if not os.path.isdir(base_dir):
        print(f"错误: 基础目录不存在 {base_dir}")
        return False
    
    # 查找所有子目录
    subdirs = []
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path):
            # 忽略常见的非内容目录
            if item.lower() not in ['__macosx', '.vscode', '.git', 'node_modules']:
                subdirs.append((item, item_path))
    
    if not subdirs:
        print(f"在 {base_dir} 中未找到子目录，尝试作为单卷处理...")
        return convert_single_volume(base_dir, output_dir, base_title, author)
    
    # 按卷号排序
    subdirs.sort(key=lambda x: extract_volume_number(x[0]))
    
    print(f"找到 {len(subdirs)} 个卷，按顺序处理...")
    for volume_name, _ in subdirs:
        print(f"  - {volume_name} (卷号: {extract_volume_number(volume_name)})")
    
    # 创建单个EPUB生成器
    epub_gen = SimpleEpubGenerator(base_title, author)
    
    # 查找封面图片 (从第一个卷的目录中查找)
    first_volume_cover_path = None
    if subdirs: # 确保至少有一个子目录
        first_volume_dir_path = subdirs[0][1] # 第一个子目录的路径
        first_volume_cover_path = find_cover_image(first_volume_dir_path)
        
    if first_volume_cover_path:
        epub_gen.set_cover_image(first_volume_cover_path)
    
    # 遍历所有卷，将章节添加到同一个epub中
    for volume_name, volume_path in subdirs:
        print(f"\n处理卷: {volume_name}")
        
        # 添加一个以卷名为标题的空白章节作为分隔
        epub_gen.add_raw_chapter(volume_name, "")
        
        # 查找该卷中的所有相关文件
        all_files = []
        for root, dirs, files in os.walk(volume_path):
            for file in files:
                if file.lower().endswith(('.txt', '.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                    all_files.append(os.path.join(root, file))
        
        if not all_files:
            print(f"警告: 在卷 {volume_name} 中未找到txt或图片文件")
            continue
        
        # 按编号分组文件
        grouped_files = group_files_by_number(all_files)
        
        if not grouped_files:
            print(f"警告: 在卷 {volume_name} 中没有找到带编号的文件")
            continue
        
        # 按编号排序
        sorted_numbers = sorted(grouped_files.keys())
        
        print(f"在卷 {volume_name} 中找到 {len(sorted_numbers)} 个编号组")
        
        # 按编号顺序处理每组文件
        for number in sorted_numbers:
            group = grouped_files[number]
            txt_files = group['txt_files']
            image_files = group['image_files']
            
            # 处理图片
            chapter_images = []
            for img_path in sorted(image_files):
                img_info = epub_gen.add_image(img_path, f"vol_{volume_name}_img_{number}_{len(chapter_images)}")
                if img_info:
                    chapter_images.append(img_info)
            
            # 处理文本文件
            if txt_files:
                # 合并同一编号的所有txt文件
                combined_content = ""
                for txt_file in sorted(txt_files):
                    try:
                        content = None
                        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16', 'utf-16le']
                        
                        for encoding in encodings:
                            try:
                                with open(txt_file, 'r', encoding=encoding) as f:
                                    content = f.read()
                                break
                            except (UnicodeDecodeError, UnicodeError):
                                continue
                        
                        if content:
                            combined_content += content + "\n\n"
                        else:
                            print(f"警告: 无法读取文件 {txt_file}")
                            
                    except Exception as e:
                        print(f"警告: 读取文件 {txt_file} 时出错: {e}")
                
                if combined_content.strip():
                    success = epub_gen.add_chapter_via_parser(combined_content, chapter_images)
                    if not success:
                        print(f"警告: 跳过卷 {volume_name} 编号 {number} 的文本内容")
                elif chapter_images:
                    # 如果没有文本但有图片，创建一个只包含图片的章节
                    chapter_title = f"{volume_name} - 插图 {number:03d}"
                    epub_gen.add_raw_chapter(chapter_title, "", chapter_images)
            elif chapter_images:
                # 如果只有图片没有文本，创建一个只包含图片的章节
                chapter_title = f"{volume_name} - 插图 {number:03d}"
                epub_gen.add_raw_chapter(chapter_title, "", chapter_images)
    
    if not epub_gen.chapters:
        print("错误: 没有成功添加任何章节")
        return False
    
    # 生成单个EPUB文件
    output_file = os.path.join(output_dir, f"{base_title}.epub")
    return epub_gen.save_epub(output_file)


def convert_multiple_volumes(base_dir, output_dir, base_title, author="Unknown Author"):
    """转换多个卷（每个子目录作为一卷）- 生成多个EPUB文件"""
    if not os.path.isdir(base_dir):
        print(f"错误: 基础目录不存在 {base_dir}")
        return False
    
    # 查找所有子目录
    subdirs = []
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path):
            # 忽略常见的非内容目录
            if item.lower() not in ['__macosx', '.vscode', '.git', 'node_modules']:
                subdirs.append((item, item_path))
    
    if not subdirs:
        print(f"在 {base_dir} 中未找到子目录，尝试作为单卷处理...")
        return convert_single_volume(base_dir, output_dir, base_title, author)
    
    subdirs.sort(key=lambda x: extract_volume_number(x[0]))  # 按卷号排序
    
    success_count = 0
    for volume_name, volume_path in subdirs:
        print(f"\n处理卷: {volume_name}")
        volume_title = f"{base_title} - {volume_name}"
        
        success = convert_single_volume(volume_path, output_dir, volume_title, author)
        if success:
            success_count += 1
    
    print(f"\n转换完成! 成功转换 {success_count}/{len(subdirs)} 卷")
    return success_count > 0


# 便捷函数
def txt_to_epub(input_path, output_dir, title, author="Unknown Author", mode="auto"):
    """
    TXT转EPUB的主函数
    
    Args:
        input_path: 输入路径（文件夹或单个TXT文件）
        output_dir: 输出目录
        title: 书籍标题
        author: 作者
        mode: 转换模式 ("single" - 单卷, "multi_single" - 多卷合并为一个epub, 
              "multi_separate" - 多卷分别生成epub, "single_file" - 单文件, "auto" - 自动检测)
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 处理单个文件的情况
    if os.path.isfile(input_path) and input_path.lower().endswith('.txt'):
        return convert_single_file_to_epub(input_path, output_dir, title, author)
    
    if mode == "auto":
        # 自动检测模式
        if os.path.isdir(input_path):
            # 检查目录中的内容
            subdirs_with_content = []
            direct_content_files = []
            
            for item in os.listdir(input_path):
                item_path = os.path.join(input_path, item)
                if os.path.isfile(item_path) and item.lower().endswith(('.txt', '.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                    direct_content_files.append(item_path)
                elif os.path.isdir(item_path):
                    # 检查子目录中是否有相关文件
                    has_content = False
                    for subitem in os.listdir(item_path):
                        if subitem.lower().endswith(('.txt', '.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                            has_content = True
                            break
                    if has_content:
                        subdirs_with_content.append((item, item_path))
            
            if direct_content_files and not subdirs_with_content:
                print("检测到单层目录结构，所有文件在同一目录")
                return convert_single_volume(input_path, output_dir, title, author)
            elif subdirs_with_content and not direct_content_files:
                print("检测到多卷结构，将合并为单个EPUB")
                return convert_multiple_volumes_to_single_epub(input_path, output_dir, title, author)
            elif subdirs_with_content and direct_content_files:
                print("检测到混合结构，优先处理子目录，将合并为单个EPUB")
                return convert_multiple_volumes_to_single_epub(input_path, output_dir, title, author)
            else:
                print("未找到任何txt或图片文件")
                return False
        else:
            print("错误: 输入路径必须是目录或TXT文件")
            return False
    
    elif mode == "single":
        return convert_single_volume(input_path, output_dir, title, author)
    
    elif mode == "multi_single":
        return convert_multiple_volumes_to_single_epub(input_path, output_dir, title, author)
    
    elif mode == "multi_separate":
        return convert_multiple_volumes(input_path, output_dir, title, author)
    
    elif mode == "single_file":
        if os.path.isfile(input_path) and input_path.lower().endswith('.txt'):
            return convert_single_file_to_epub(input_path, output_dir, title, author)
        else:
            print("错误: 单文件模式需要指定一个TXT文件作为输入")
            return False
    
    else:
        print(f"错误: 未知的转换模式 {mode}")
        return False


def split_and_add_multiple_chapters_from_file(file_path, epub_generator):
    """从单个文件中提取多个章节并添加到EPUB生成器中
    
    这个函数适用于一个TXT文件包含多个章节的情况，
    以#开头的行会被视为新章节的标题。
    
    Args:
        file_path: TXT文件路径
        epub_generator: SimpleEpubGenerator实例
        
    Returns:
        添加的章节数量
    """
    # 尝试多种编码读取文件
    content = None
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16', 'utf-16le']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            print(f"使用 {encoding} 编码成功读取: {os.path.basename(file_path)}")
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    if content is None:
        print(f"警告: 无法读取文件 {file_path}")
        return 0
    
    # 清理文本
    cleaned_content = epub_generator.clean_text(content)
    if not cleaned_content:
        print(f"警告: 文件内容为空: {file_path}")
        return 0
    
    # 按#标记分割章节
    chapter_blocks = re.split(r'(?m)^#', cleaned_content)
    
    # 移除第一个块如果它不包含标题
    if chapter_blocks and not chapter_blocks[0].strip().startswith('#'):
        # 检查第一个块是否包含标题性质的内容
        first_block_lines = chapter_blocks[0].strip().split('\n')
        if first_block_lines and not re.match(r'^０+\d+', first_block_lines[0].strip()):
            potential_title = first_block_lines[0].strip()
            # 如果第一行不是元信息，可能是标题
            if not ('台版' in potential_title or '转自' in potential_title or 
                   '发布：' in potential_title or '论坛：' in potential_title):
                # 将第一行视为标题，其余作为内容
                title = potential_title
                content = '\n'.join(first_block_lines[1:]) if len(first_block_lines) > 1 else ""
                # 添加章节
                epub_generator.add_raw_chapter(title, content)
        chapter_blocks = chapter_blocks[1:]
    
    # 处理剩余的章节块
    for block in chapter_blocks:
        if not block.strip():
            continue
        
        # 添加#前缀回来
        block = "#" + block
        # 使用解析器添加章节
        epub_generator.add_chapter_via_parser(block)
    
    total_chapters = len(epub_generator.chapters)
    print(f"从文件中提取了 {total_chapters} 个章节: {os.path.basename(file_path)}")
    return total_chapters


def convert_single_file_to_epub(file_path, output_dir, title, author="Unknown Author"):
    """将单个TXT文件转换为EPUB，支持文件包含多个章节的情况"""
    if not os.path.isfile(file_path) or not file_path.lower().endswith('.txt'):
        print(f"错误: 不是有效的TXT文件 {file_path}")
        return False
    
    # 创建EPUB生成器
    epub_gen = SimpleEpubGenerator(title, author)
    
    # 尝试从文件中提取多个章节
    chapters_added = split_and_add_multiple_chapters_from_file(file_path, epub_gen)
    
    if chapters_added == 0:
        # 如果没有成功提取章节，尝试作为单个章节处理
        success = epub_gen.add_chapter_from_file(file_path)
        if not success:
            print(f"错误: 无法从文件中提取章节内容 {file_path}")
            return False
    
    # 生成EPUB文件
    output_file = os.path.join(output_dir, f"{title}.epub")
    return epub_gen.save_epub(output_file)


if __name__ == "__main__":
    # 测试示例
    single_file_path = '/Users/lilithgames/Downloads/novels/物语系列 Monster Season(物语系列十四)'
    target_folder = "/Users/lilithgames/Downloads/novels/"
    txt_to_epub(single_file_path, target_folder, "物语系列 Monster Season", "西尾维新")