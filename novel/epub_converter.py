#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import zipfile
import datetime
from xml.sax.saxutils import escape as xml_escape
import uuid

class SimpleEpubGenerator:
    def __init__(self, title, author="Unknown Author", language="zh"):
        self.title = title
        self.author = author
        self.language = language
        self.book_id = str(uuid.uuid4())
        self.chapters = []
        self.images = []
        
    def clean_text(self, text):
        """清理文本内容（不截断）"""
        if not text:
            return ""
        
        # 处理转义的换行符
        text = text.replace('\\r\\n', '\n')
        text = text.replace('\\n', '\n')
        
        # 移除BOM标记
        text = text.replace('\ufeff', '')
        
        # 标准化换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # 新增：压缩多个连续的空行（仅包含空白符的行）为一个空行，方便后续处理
        # 这主要影响 parse_chapter_content 和 text_to_html_paragraphs 对段落的判断
        text = re.sub(r'^\s*$\n(?:^\s*$\n)+', '\n', text, flags=re.MULTILINE)
        
        return text.strip()
    
    def parse_chapter_content(self, content):
        """解析章节内容，提取标题和正文"""
        # 注意：clean_text 已在调用此方法前被调用 (如在 add_chapter_via_parser 中)
        # 或者在此方法开始时调用（如果直接从外部调用此方法的话）
        # content = self.clean_text(content) # 确保清理

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
    
    def text_to_html_paragraphs(self, text):
        """将文本转换为HTML段落，保留原始换行并处理小标题。"""
        if not text.strip():
            return "    <p>（空章节）</p>"
        
        # 按空行分割文本成段落块
        paragraph_blocks = re.split(r'\n\s*\n', text.strip())
        html_parts = []
        
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
        
        return '\n'.join(html_parts) if html_parts else "    <p>（空章节）</p>"
    
    def _generate_unique_filename(self, title_str, base_prefix="chapter"):
        """根据标题生成一个在当前EPUB实例中唯一的文件名。"""
        safe_filename_base = re.sub(r'[^\\w\\s-]', '', str(title_str)).strip()
        safe_filename_base = re.sub(r'[-\\s]+', '-', safe_filename_base)
        
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

    def add_raw_chapter(self, title: str, body_text: str):
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
            'id': chapter_id
        }
        self.chapters.append(chapter_info)
        print(f"添加章节 (raw): {title} ({len(cleaned_body)} 字符)")
        return True

    def add_chapter_via_parser(self, full_content_string: str):
        """通过内部解析器从完整内容字符串中提取标题和正文来添加章节。"""
        cleaned_content = self.clean_text(full_content_string)
        if not cleaned_content.strip(): # 如果清理后内容为空
            print("警告: 提供的章节内容 (via parser) 为空或仅含空白，已跳过。")
            return False
        
        title, main_content = self.parse_chapter_content(cleaned_content)
        
        chapter_filename = self._generate_unique_filename(title)
        # ID生成应确保唯一性且符合XML ID规范
        chapter_id = f"ch_{chapter_filename.replace('.xhtml', '').replace('-', '_').replace('.', '_')}"

        chapter_info = {
            'title': title,
            'content': main_content,
            'filename': chapter_filename,
            'id': chapter_id
        }
        self.chapters.append(chapter_info)
        print(f"添加章节 (parsed): {title} ({len(main_content)} 字符)")
        return True
        
    def add_chapter_from_file(self, file_path):
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
        
        # 使用 add_chapter_via_parser 的逻辑来避免代码重复
        # 注意：原版 add_chapter_from_file 有自己的 print 输出和错误处理
        # 为了保持行为一致性，我们可以在这里调用并根据结果返回
        
        # 现在使用 add_chapter_via_parser 来处理内容
        # 这会确保 clean_text 和 parse_chapter_content 被一致地调用
        # 以及文件名和ID的生成也是一致的
        return self.add_chapter_via_parser(content)
    
    def generate_chapter_xhtml(self, chapter):
        """生成章节的XHTML内容"""
        html_content = self.text_to_html_paragraphs(chapter['content'])
        
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
        for chapter in self.chapters:
            manifest_items.append(f'    <item id="{chapter["id"]}" href="Text/{chapter["filename"]}" media-type="application/xhtml+xml"/>')
        
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
    </metadata>
    <manifest>
        <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
        <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
        <item id="style" href="Styles/style.css" media-type="text/css"/>
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

p {
    margin: 0.8em 0;
    text-indent: 2em;
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
    

def discover_and_convert_novels(input_dir, output_dir, novel_title, author="Unknown Author"):
    """发现并转换小说文件"""
    if not os.path.isdir(input_dir):
        print(f"错误: 输入目录不存在 {input_dir}")
        return False
    
    # 查找所有txt文件
    txt_files = []
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.lower().endswith('.txt'):
                txt_files.append(os.path.join(root, file))
    
    if not txt_files:
        print(f"错误: 在 {input_dir} 中未找到txt文件")
        return False
    
    # 按文件名排序
    txt_files.sort(key=lambda x: os.path.basename(x))
    
    print(f"找到 {len(txt_files)} 个txt文件")
    
    # 创建EPUB生成器
    epub_gen = SimpleEpubGenerator(novel_title, author)
    
    # 添加所有章节
    for txt_file in txt_files:
        success = epub_gen.add_chapter_from_file(txt_file)
        if not success:
            print(f"警告: 跳过文件 {txt_file}")
    
    if not epub_gen.chapters:
        print("错误: 没有成功添加任何章节")
        return False
    
    # 生成EPUB文件
    output_file = os.path.join(output_dir, f"{novel_title}.epub")
    return epub_gen.save_epub(output_file)

def convert_single_volume(input_dir, output_dir, novel_title, author="Unknown Author"):
    """转换单个卷（目录中的所有txt文件）"""
    return discover_and_convert_novels(input_dir, output_dir, novel_title, author)

def convert_multiple_volumes(base_dir, output_dir, base_title, author="Unknown Author"):
    """转换多个卷（每个子目录作为一卷）"""
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
    
    subdirs.sort(key=lambda x: x[0])  # 按目录名排序
    
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
        mode: 转换模式 ("single" - 单卷, "multi" - 多卷, "single_file" - 单文件, "auto" - 自动检测)
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 处理单个文件的情况
    if os.path.isfile(input_path) and input_path.lower().endswith('.txt'):
        return convert_single_file_to_epub(input_path, output_dir, title, author)
    
    if mode == "auto":
        # 自动检测模式
        if os.path.isdir(input_path):
            # 检查是否有子目录包含txt文件
            has_subdirs_with_txt = False
            for item in os.listdir(input_path):
                item_path = os.path.join(input_path, item)
                if os.path.isdir(item_path):
                    for subitem in os.listdir(item_path):
                        if subitem.lower().endswith('.txt'):
                            has_subdirs_with_txt = True
                            break
                    if has_subdirs_with_txt:
                        break
            
            if has_subdirs_with_txt:
                print("检测到多卷结构")
                return convert_multiple_volumes(input_path, output_dir, title, author)
            else:
                print("检测到单卷结构")
                return convert_single_volume(input_path, output_dir, title, author)
        else:
            print("错误: 输入路径必须是目录或TXT文件")
            return False
    
    elif mode == "single":
        return convert_single_volume(input_path, output_dir, title, author)
    
    elif mode == "multi":
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

# 修改便捷函数，增加对单个文件包含多章节的支持
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
    # 示例用法
    # 1. 单个文件包含多个章节
    single_file_path = '/Users/lilithgames/Downloads/novels/物语系列 Monster Season(物语系列十四)'
    target_folder = "/Users/lilithgames/Downloads/novels/"
    txt_to_epub(single_file_path, target_folder, "xx", "xx")
    
    # 2. 单个卷目录
    #source_folder = '/Users/lilithgames/Downloads/novels/物语系列 Monster Season(物语系列十四)/第一卷 忍物语'
    #txt_to_epub(source_folder, target_folder, "忍物语", "西尾维新", "single")
    
    # 3. 多卷（如果有多个子目录）
    #base_folder = "/Users/lilithgames/Downloads/novels/物语系列 Monster Season(物语系列十四)"
    #txt_to_epub(base_folder, target_folder, "物语系列 Monster Season", "西尾维新", "multi")