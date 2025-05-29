#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import os
import re
import time
from urllib.parse import urljoin, quote
import concurrent.futures
from threading import Lock
from novel.fix_text import fix_all_txt_files
from utils import get_app_base_dir

class Wenku8Downloader:
    def __init__(self, username='2497360927', password='testtest'):
        self.base_url = 'https://www.wenku8.net/book/'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.wenku8.net/',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8' # Added Accept-Language
        })
        self.print_lock = Lock()
        self.search_cache = {}  # Cache for search results
        self.cover_cache_dir = os.path.join(get_app_base_dir(), 'novel_cache', 'covers')
        os.makedirs(self.cover_cache_dir, exist_ok=True)
        
        # 尝试登录
        username_to_use = username if username else '2497360927'
        password_to_use = password if password else 'testtest'

        if username_to_use and password_to_use:
            if not self.login(username_to_use, password_to_use):
                print("登录失败，后续操作可能无法正常进行。")
        else:
            print("未提供用户名和密码，将尝试以未登录状态访问。")
        
    def login(self, username, password):
        """用户登录"""
        login_url = 'https://www.wenku8.net/login.php?do=submit'
        jumpurl = quote('https://www.wenku8.net/index.php') 
        login_url_with_jump = f"{login_url}&jumpurl={jumpurl}"

        login_data = {
            'username': username,
            'password': password,
            'usecookie': '315360000',
            'action': 'login',
            'submit': ' 登  录 ' 
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://www.wenku8.net/login.php'
        }
        
        try:
            with self.print_lock:
                print(f"尝试登录用户: {username}...")
            response = self.session.post(login_url_with_jump, data=login_data, headers=headers)
            response.encoding = 'gbk'
            
            if "<title>登录成功</title>" in response.text and "欢迎您到来！" in response.text:
                with self.print_lock:
                    print("登录成功!")
                return True
            elif response.url == jumpurl.replace('%3A', ':').replace('%2F', '/'):
                with self.print_lock:
                    print("登录成功 (通过URL跳转判断)! ")
                return True
            elif "用户登录" not in response.text and "我的帐号" in response.text:
                 with self.print_lock:
                    print("登录成功 (通过页面内容判断)! ")
                 return True
            else:
                with self.print_lock:
                    print("登录失败。响应URL:", response.url)
                soup = BeautifulSoup(response.text, 'html.parser')
                error_msg = soup.select_one('div[style*="color:red"]')
                if error_msg:
                    with self.print_lock:
                        print(f"登录错误信息: {error_msg.get_text().strip()}")
                return False
        except Exception as e:
            with self.print_lock:
                print(f"登录请求发生错误: {e}")
            return False
    
    def _download_image(self, image_url, novel_id):
        """Downloads an image to the cache if not already present."""
        if not image_url:
            return None
        try:
            image_filename = image_url.split('/')[-1]
            # Sanitize filename further if needed, though novel IDs in names are usually safe
            # Prepend novel_id to ensure uniqueness if image filenames are not globally unique across novels
            # (although in wenku8, 'xxxxs.jpg' seems tied to novel ID xxxx)
            # local_filename = f"{novel_id}_{image_filename}" 
            local_filename = image_filename # Filenames like 1234s.jpg are usually unique
            
            local_path = os.path.join(self.cover_cache_dir, local_filename)

            if os.path.exists(local_path):
                with self.print_lock:
                    print(f"封面图片已存在于缓存: {local_path}")
                return local_path

            with self.print_lock:
                print(f"正在下载封面图片: {image_url} 到 {local_path}")
            
            img_response = self.session.get(image_url, stream=True, timeout=10)
            img_response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                for chunk in img_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            with self.print_lock:
                print(f"封面图片下载成功: {local_path}")
            return local_path
        except requests.exceptions.RequestException as e:
            with self.print_lock:
                print(f"下载封面图片失败 {image_url}: {e}")
            return None
        except IOError as e:
            with self.print_lock:
                print(f"保存封面图片失败 {local_path}: {e}")
            return None

    def search_novels(self, keyword=None, search_type='articlename', page_url=None):
        """
        搜索小说
        search_type: 'articlename' 按小说名搜索, 'author' 按作者名搜索
        page_url: 用于翻页的完整URL
        Returns a dictionary with 'novels' list and 'pagination_info'.
        Each novel in the list is a dictionary with detailed info.
        """
        search_url_key = None

        if page_url:
            search_url = page_url
            search_url_key = page_url
            print(f"正在获取搜索结果页面: {search_url}")
        elif keyword:
            print(f"正在搜索: {keyword} (类型: {search_type})")
            encoded_keyword = quote(keyword.encode('gbk'))
            search_url = f'https://www.wenku8.net/modules/article/search.php?searchtype={search_type}&searchkey={encoded_keyword}'
            search_url_key = search_url
        else:
            print("错误：必须提供搜索关键词或页面URL")
            return {'novels': [], 'pagination_info': None}

        # Check cache first
        if search_url_key in self.search_cache:
            with self.print_lock:
                print(f"从缓存加载搜索结果: {search_url_key}")
            return self.search_cache[search_url_key]

        try:
            response = self.session.get(search_url)
            response.encoding = 'gbk'
            # with open('novel/error.html', 'w', encoding='utf-8') as f: # For debugging search page
            #     f.write(response.text)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            novels = []
            
            # Try to select the main table containing search results first for robustness
            search_result_table = soup.select_one('table.grid')
            if search_result_table:
                 novel_entries = search_result_table.select('td > div[style*="width:373px"]')
            else: # Fallback to original direct selection if table.grid not found
                 novel_entries = soup.select('td > div[style*="width:373px"]')

            if not novel_entries and '/book/' not in response.url: # Check if not already a direct book page
                # If no standard entries and not a direct book page, check for "没有找到记录"
                no_results_msg = soup.find(string=re.compile("没有找到记录"))
                if no_results_msg:
                    with self.print_lock:
                        print("搜索结果: 没有找到记录。")
                    # Cache empty result for this search to avoid re-fetching
                    self.search_cache[search_url_key] = {'novels': [], 'pagination_info': None}
                    return {'novels': [], 'pagination_info': None}

            if not novel_entries:
                # Handle case where search might redirect to a single book's page
                if '/book/' in response.url and response.url.endswith('.htm'):
                    with self.print_lock:
                        print("搜索可能直接导向了单个小说页面。正在尝试提取基本信息。")
                    novel_info = {}
                    novel_id_match = re.search(r'/book/(\d+)\.htm', response.url)
                    if novel_id_match:
                        novel_info['id'] = int(novel_id_match.group(1))

                        title_elem = soup.select_one('div#title > h1') or \
                                     soup.select_one('td span[style*="font-size:16px"] b') or \
                                     soup.select_one('div#content table[width="90%"] tr > td[colspan="2"] > span > b')
                        novel_info['name'] = title_elem.get_text().strip() if title_elem else f"Novel {novel_info['id']}"
                        
                        cover_elem = soup.select_one('#fmimg img') or \
                                     soup.select_one('div#content td[width="20%"] img[src*="/image/"]')
                        if cover_elem and cover_elem.get('src'):
                            novel_info['cover_image_url'] = urljoin(response.url, cover_elem.get('src'))
                            novel_info['cover_image_path'] = self._download_image(novel_info['cover_image_url'], novel_info['id'])
                        else:
                            novel_info['cover_image_url'] = None
                            novel_info['cover_image_path'] = None
                        
                        # Default other fields for direct hits
                        defaults = {
                            'author': '详见小说页面', 'update_date': '详见小说页面', 'word_count': '详见小说页面',
                            'status': '详见小说页面', 'animated': False, 'tags': [], 'intro': '详见小说页面',
                        }
                        for key, default_val in defaults.items():
                            if key not in novel_info: novel_info[key] = default_val
                        
                        novels.append(novel_info)
                        result = {'novels': novels, 'pagination_info': None}
                        self.search_cache[search_url_key] = result # Cache this direct hit
                        return result

            for entry_div in novel_entries:
                novel_info = {}
                
                link_element = entry_div.select_one('b > a[href*="/book/"]')
                if not link_element:
                    continue
                
                href = link_element.get('href')
                title_text = link_element.get('title') or link_element.get_text()
                novel_info['name'] = title_text.strip()
                
                novel_id_match = re.search(r'/book/(\d+)\.htm', href)
                if not novel_id_match:
                    continue
                novel_info['id'] = int(novel_id_match.group(1))

                # Cover Image
                cover_img_element = entry_div.select_one('div[style*="width:95px"] img')
                if cover_img_element and cover_img_element.get('src'):
                    novel_info['cover_image_url'] = urljoin(response.url, cover_img_element.get('src'))
                    novel_info['cover_image_path'] = self._download_image(novel_info['cover_image_url'], novel_info['id'])
                else:
                    novel_info['cover_image_url'] = None
                    novel_info['cover_image_path'] = None

                # Details from <p> tags
                info_div = entry_div.select_one('div[style*="margin-top:2px"]')
                if info_div:
                    paragraphs = info_div.select('p')

                    # Author
                    if len(paragraphs) > 0:
                        author_text = paragraphs[0].get_text().strip()
                        novel_info['author'] = author_text.split('/')[0].replace('作者:', '').strip()
                    else:
                        novel_info['author'] = '未知作者'

                    # Update, Word Count, Status, Animated
                    if len(paragraphs) > 1:
                        p_status_line = paragraphs[1]
                        novel_info['animated'] = bool(p_status_line.select_one('span.hottext'))

                        temp_status_soup = BeautifulSoup(str(p_status_line), 'html.parser')
                        hottext_span = temp_status_soup.select_one('span.hottext')
                        if hottext_span:
                            hottext_span.decompose()
                        status_text_cleaned = temp_status_soup.get_text().strip()
                        
                        parts = status_text_cleaned.split('/')
                        novel_info['update_date'] = parts[0].replace('更新:', '').strip() if len(parts) > 0 else None
                        novel_info['word_count'] = parts[1].replace('字数:', '').strip() if len(parts) > 1 else None
                        raw_status = parts[2].strip() if len(parts) > 2 and parts[2].strip() else '未知状态'
                        # Ensure status doesn't include "已动画化" if it was only in span
                        novel_info['status'] = raw_status.replace("已动画化", "").strip("/") if novel_info['animated'] else raw_status

                    else:
                        novel_info['update_date'] = None
                        novel_info['word_count'] = None
                        novel_info['status'] = '未知状态'
                        novel_info['animated'] = False
                    
                    # Tags
                    if len(paragraphs) > 2:
                        tags_p = paragraphs[2]
                        tags_span = tags_p.select_one('span')
                        if tags_span:
                            novel_info['tags'] = [tag.strip() for tag in tags_span.get_text().strip().split(' ') if tag.strip()]
                        else: # Fallback if structure is different (e.g. no span)
                            tag_text_content = tags_p.get_text().replace('Tags:', '').strip()
                            novel_info['tags'] = [tag.strip() for tag in tag_text_content.split(' ') if tag.strip()] if tag_text_content else []
                    else:
                        novel_info['tags'] = []
                    
                    # Intro
                    if len(paragraphs) > 3:
                        novel_info['intro'] = paragraphs[3].get_text().replace('简介:', '').strip()
                    else:
                        novel_info['intro'] = '暂无简介'
                else: # Fallback if info_div is not found
                    novel_info.update({
                        'author': '未知作者', 'update_date': None, 'word_count': None,
                        'status': '未知状态', 'animated': False, 'tags': [], 'intro': '暂无简介'
                    })
                
                novels.append(novel_info)

            # Parse pagination info
            pagination_info = {
                'current_page': 1,
                'total_pages': 1,
                'next_page_url': None,
                'prev_page_url': None,
                'page_urls': {} # For direct page number access
            }
            
            pages_div = soup.select_one('div.pages div#pagelink, div.pages') # Added div.pages as alternative
            if pages_div:
                page_stats_elem = pages_div.select_one('em#pagestats')
                if page_stats_elem:
                    stats_text = page_stats_elem.get_text().strip()
                    page_match = re.match(r'(\d+)/(\d+)', stats_text)
                    if page_match:
                        pagination_info['current_page'] = int(page_match.group(1))
                        pagination_info['total_pages'] = int(page_match.group(2))
                
                next_page_link_elem = pages_div.select_one('a.next[href]')
                if next_page_link_elem:
                    next_href = next_page_link_elem.get('href')
                    if next_href:
                        pagination_info['next_page_url'] = urljoin(response.url, next_href)

                # Previous page link (often uses 'pgroup' for <, 'prev' might be specific)
                # Using a more general approach for previous link
                prev_page_link_elem = pages_div.select('a[href*="page="]') 
                # Find the link that is likely the previous page relative to current
                current_pg_num = pagination_info['current_page']
                if current_pg_num > 1:
                    for plink in prev_page_link_elem:
                        try:
                            # Check if it's the direct previous page number or a "<" type link
                            if f"page={current_pg_num-1}" in plink.get('href') or (plink.get_text(strip=True) == '<' or plink.get_text(strip=True) == '<<'):
                                # Ensure it's not the current page itself if text is just number
                                if plink.get_text(strip=True) != str(current_pg_num):
                                    # Check if the href is not just '#' or javascript:;
                                    href_val = plink.get('href')
                                    if href_val and href_val.strip() not in ['#', 'javascript:;']:
                                        pagination_info['prev_page_url'] = urljoin(response.url, href_val)
                                        # Prefer the link that explicitly says "page=X-1" if multiple match
                                        if f"page={current_pg_num-1}" in href_val:
                                            break 
                        except:
                            pass


                # Extract all page number links for direct access
                all_page_links = pages_div.select('a[href*="page="]')
                for link in all_page_links:
                    page_num_match = re.search(r'page=(\d+)', link.get('href'))
                    link_text = link.get_text().strip()
                    if page_num_match:
                        try:
                            pg_num = int(page_num_match.group(1))
                            if link_text.isdigit() and int(link_text) == pg_num: # Ensure it's a direct page number link
                                pagination_info['page_urls'][pg_num] = urljoin(response.url, link.get('href'))
                        except ValueError:
                            continue # Link text might be '<<', '>>', etc.
            
            if not novels and not page_url: # Changed from original to check page_url
                with self.print_lock:
                    print("未找到相关小说。")

            result = {'novels': novels, 'pagination_info': pagination_info}
            self.search_cache[search_url_key] = result # Store in cache
            return result
            
        except requests.exceptions.RequestException as e:
            with self.print_lock:
                print(f"搜索请求失败: {e}")
            return {'novels': [], 'pagination_info': None}
        except Exception as e:
            with self.print_lock:
                print(f"搜索解析失败: {e}")
            import traceback
            traceback.print_exc()
            return {'novels': [], 'pagination_info': None}
    
    def _is_cloudflare_error(self, text_content):
        if not text_content:
            return False
        
        # 编译正则表达式以提高效率和实现不区分大小写的匹配
        error_patterns = [
            re.compile(r"You are being rate limited", re.IGNORECASE),
            re.compile(r"Error\\s+1015", re.IGNORECASE), 
            re.compile(r"Ray ID:", re.IGNORECASE), 
            re.compile(r"Cloudflare Ray ID:", re.IGNORECASE),
            re.compile(r"Performance & security by Cloudflare", re.IGNORECASE),
            re.compile(r"The owner of this website .* has banned you temporarily", re.IGNORECASE),
            re.compile(r"Please enable cookies", re.IGNORECASE), # 常见于拦截页面
            re.compile(r"Checking if the site connection is secure", re.IGNORECASE), # Cloudflare的JS挑战页面
            re.compile(r"why_was_i_blocked", re.IGNORECASE), # Cloudflare拦截页面链接中的常见片段
            re.compile(r"Enable JavaScript and cookies to continue", re.IGNORECASE) # 另一种JS挑战提示
        ]
        for pattern_re in error_patterns:
            if pattern_re.search(text_content):
                return True
        return False

    def get_novel_details(self, novel_id):
        """获取小说详细信息"""
        url = f"{self.base_url}{novel_id}.htm"
        
        try:
            response = self.session.get(url)
            response.encoding = 'gbk'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            title = f"Novel_{novel_id}"
            title_span = soup.select_one('div#title > h1')
            if not title_span:
                title_span = soup.select_one('td span[style*="font-size:16px"] b')
            if title_span:
                title = title_span.get_text().strip()
            else:
                title_tag = soup.find('title')
                if title_tag:
                    title_text = title_tag.get_text().strip()
                    if " - " in title_text:
                        title = title_text.split(" - ")[0].strip()
                    elif "-" in title_text:
                        title = title_text.split("-")[0].strip()
                    else:
                        title = title_text
            
            author = "未知作者"
            author_elem = soup.select_one('.author, #author') 
            if author_elem:
                author = author_elem.get_text().replace('作者：', '').strip()
            else:
                for td in soup.select('td'):
                    text = td.get_text().strip()
                    if text.startswith('小说作者：'):
                        author = text.replace('小说作者：', '').strip()
                        break
            
            catalog_url = None
            catalog_link_elem = soup.find('a', string=re.compile(r"小说目录"))
            if catalog_link_elem and catalog_link_elem.get('href'):
                catalog_href = catalog_link_elem.get('href')
                catalog_url = urljoin(response.url, catalog_href)
            
            if not catalog_url:
                with self.print_lock:
                     print(f"警告: 未能在页面上动态找到小说ID {novel_id} 的目录链接。将尝试使用默认模式，但这可能不准确。")

            if not catalog_url:
                with self.print_lock:
                    print(f"错误: 无法确定小说ID {novel_id} 的目录URL。下载可能失败。")
            else:
                 print(f"解析结果: 标题='{title}', 作者='{author}', 目录URL='{catalog_url}'")
            
            return {
                'id': novel_id,
                'title': title,
                'author': author,
                'catalog_url': catalog_url
            }
            
        except Exception as e:
            print(f"获取小说详情失败: {e}")
            return None
    
    def get_chapter_list(self, catalog_url):
        """获取章节列表，按卷分组"""
        try:
            response = self.session.get(catalog_url)
            response.encoding = 'gbk'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            volumes = []  # 存储卷信息的列表
            current_volume = None
            
            table = soup.select_one('table.css')
            if not table:
                print("未找到章节表格")
                return []
            
            for row in table.select('tr'):
                # 检查是否是卷标题行
                volume_td = row.select_one('td.vcss[colspan="4"]')
                if volume_td:
                    volume_title = volume_td.get_text().strip()
                    print(f"找到卷: {volume_title}")
                    
                    # 创建新的卷
                    current_volume = {
                        'title': volume_title,
                        'chapters': []
                    }
                    volumes.append(current_volume)
                    continue
                
                # 处理章节行
                chapter_tds = row.select('td.ccss')
                for td in chapter_tds:
                    link = td.select_one('a')
                    if link and link.get('href'):
                        href = link.get('href')
                        chapter_title = link.get_text().strip()
                        
                        if not chapter_title or chapter_title == ' ':
                            continue
                        
                        if href.startswith('http'):
                            chapter_url = href
                        else:
                            base_url = catalog_url.rsplit('/', 1)[0]
                            chapter_url = f"{base_url}/{href}"
                        
                        chapter_info = {
                            'title': chapter_title,
                            'url': chapter_url
                        }
                        
                        # 如果当前没有卷，创建一个默认卷
                        if current_volume is None:
                            current_volume = {
                                'title': '默认卷',
                                'chapters': []
                            }
                            volumes.append(current_volume)
                        
                        current_volume['chapters'].append(chapter_info)
            
            total_chapters = sum(len(vol['chapters']) for vol in volumes)
            print(f"总共找到 {len(volumes)} 卷，{total_chapters} 个章节")
            return volumes
            
        except Exception as e:
            print(f"获取章节列表失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def download_chapter(self, chapter, output_dir, novel_id): # Added novel_id for robust aid in fallback
        """下载单个章节，包括文本和图片"""
        try:
            with self.print_lock:
                print(f"正在处理章节: {chapter['title']} (URL: {chapter['url']})")
            response = self.session.get(chapter['url'], timeout=20)
            response.encoding = 'gbk'
            
            # 立刻检查是否为Cloudflare错误页面
            initial_content_check = response.text
            if self._is_cloudflare_error(initial_content_check):
                with self.print_lock:
                    print(f"  ✗ 页面被Cloudflare拦截 (初始加载): {chapter['title']}")
                return False # 触发重试
                
            soup = BeautifulSoup(response.text, 'html.parser')
            text_content = ""
            image_urls_to_download = []

            # 1. Identify the main content area
            main_content_area = None
            # Ordered by preference, #content is often the one for wenku8
            content_selectors = ['#content', '#contentmain', 'div[id="content"]', '.content'] 
            for selector in content_selectors:
                candidate = soup.select_one(selector)
                if candidate:
                    main_content_area = candidate
                    break
            
            if not main_content_area:
                main_content_area = soup.body if soup.body else soup # Fallback to whole body

            # 2. Extract Image URLs from the identified content area
            if main_content_area:
                image_elements = main_content_area.select('div.divimage img.imagecontent')
                if not image_elements: # Broader search if specific one fails within content area
                    image_elements = main_content_area.select('img.imagecontent')
                
                for img_tag in image_elements:
                    img_src = img_tag.get('src')
                    if img_src:
                        full_img_url = urljoin(chapter['url'], img_src)
                        if full_img_url not in image_urls_to_download:
                            image_urls_to_download.append(full_img_url)
            
            with self.print_lock:
                if image_urls_to_download:
                    print(f"  找到 {len(image_urls_to_download)} 张图片待下载。")
                else:
                    print(f"  未在该章节页面找到主要图片元素。")

            # 3. Extract Text Content from a cleaned version of the content area
            if main_content_area:
                text_extraction_soup = BeautifulSoup(str(main_content_area), 'html.parser')
                elements_to_remove_for_text = 'div.divimage, ul#contentdp, div.chapter_turnpage, div#contentadv, script, style'
                if 'div[align="center"] > table' in str(text_extraction_soup): # Remove potential ad tables
                    elements_to_remove_for_text += ', div[align="center"] > table'

                for element_to_remove in text_extraction_soup.select(elements_to_remove_for_text):
                    element_to_remove.decompose()
                
                text_content = text_extraction_soup.get_text(separator='\n', strip=True)
                text_content = re.sub(r'\n{2,}', '\n\n', text_content)
            
            # 检查提取的文本是否为Cloudflare错误
            if self._is_cloudflare_error(text_content):
                with self.print_lock:
                    print(f"  ✗ 提取的文本内容为Cloudflare错误页面: {chapter['title']}")
                return False # 触发重试

            # 4. Handle fallback for text if primary extraction is unsatisfactory
            primary_text_unsatisfactory = (
                not text_content.strip() or
                text_content.strip() == 'null' or
                '因版权问题' in text_content or
                '文库不再提供' in text_content
            )

            if primary_text_unsatisfactory:
                with self.print_lock:
                    print(f"  主要文本提取不满意或为空，尝试备用下载...")
                original_text_content_before_fallback = text_content 
                
                try:
                    path_segments = [seg for seg in chapter['url'].replace('.htm', '').split('/') if seg]
                    vid = ''
                    # Novel_id passed to function is effectively 'aid'
                    aid = str(novel_id) 

                    if len(path_segments) > 0:
                         # vid is typically the last numeric part of chapter url path
                        chapter_filename_part = path_segments[-1]
                        # Extract digits from chapter_filename_part, as it might be '12345.htm' or just '12345'
                        vid_match = re.search(r'(\\d+)', chapter_filename_part)
                        if vid_match:
                            vid = vid_match.group(1)
                        else: # Fallback if no number in last segment, less likely
                           raise ValueError(f"无法从章节URL最后一个路径部分 '{chapter_filename_part}' 提取vid。")
                    else:
                        raise ValueError("章节URL路径分段为空，无法确定vid。")


                    if not aid.isdigit() or not vid.isdigit():
                        raise ValueError(f"从URL提取的aid ({aid}) 或 vid ({vid}) 无效。")

                    _content_from_dl = ""
                    # Attempt 1: packtxt.php
                    alt_url_packtxt = f"http://dl.wenku8.com/packtxt.php?aid={aid}&vid={vid}"
                    with self.print_lock: print(f"    ↪ 尝试备用 (packtxt): {alt_url_packtxt}")
                    
                    try:
                        alt_response_packtxt = self.session.get(alt_url_packtxt, timeout=15)
                        alt_response_packtxt.raise_for_status()
                        # Try common encodings, gbk is often used for packtxt
                        for encoding in ['gbk', 'utf-8']:
                            alt_response_packtxt.encoding = encoding
                            temp_dl_text = alt_response_packtxt.text
                            if self._is_cloudflare_error(temp_dl_text):
                                with self.print_lock: print(f"      备用 (packtxt) 返回Cloudflare错误页面。")
                                _content_from_dl = "CLOUDFLARE_ERROR_PAGE" # 标记为错误
                                break
                            if temp_dl_text and len(temp_dl_text.strip()) > 50:
                                _content_from_dl = temp_dl_text.strip()
                                break
                    except requests.exceptions.RequestException as e_packtxt:
                        with self.print_lock: print(f"      备用 (packtxt) 请求失败: {e_packtxt}")
                    
                    # Attempt 2: pack.php (if packtxt failed or content too short or was Cloudflare error)
                    if not _content_from_dl or len(_content_from_dl) < 50 or _content_from_dl == "CLOUDFLARE_ERROR_PAGE":
                        if _content_from_dl == "CLOUDFLARE_ERROR_PAGE": _content_from_dl = "" # 重置
                        alt_url_pack = f"http://dl.wenku8.com/pack.php?aid={aid}&vid={vid}"
                        with self.print_lock: print(f"    ↪ 尝试备用 (pack): {alt_url_pack}")
                        try:
                            alt_response_pack = self.session.get(alt_url_pack, timeout=15)
                            alt_response_pack.raise_for_status()
                            alt_response_pack.encoding = 'utf-8' # pack.php is usually HTML with UTF-8
                            alt_soup_pack = BeautifulSoup(alt_response_pack.text, 'html.parser')
                            body_pack = alt_soup_pack.body
                            if body_pack:
                                temp_dl_text_pack = body_pack.get_text(separator='\n', strip=True)
                                if self._is_cloudflare_error(temp_dl_text_pack):
                                    with self.print_lock: print(f"      备用 (pack) 返回Cloudflare错误页面。")
                                    _content_from_dl = "CLOUDFLARE_ERROR_PAGE"
                                else:
                                    _content_from_dl = re.sub(r'\n{2,}', '\n\n', temp_dl_text_pack)
                        except requests.exceptions.RequestException as e_pack:
                             with self.print_lock: print(f"      备用 (pack) 请求失败: {e_pack}")
                    
                    if _content_from_dl and _content_from_dl != "CLOUDFLARE_ERROR_PAGE" and len(_content_from_dl.strip()) > 50:
                        text_content = _content_from_dl
                        with self.print_lock: print(f"    ✓ 备用下载文本成功。")
                    else:
                        # If fallback also fails & no images were initially found, restore original short/problematic text
                        if not image_urls_to_download and primary_text_unsatisfactory :
                            text_content = original_text_content_before_fallback
                        with self.print_lock: print(f"    ✗ 备用下载文本失败或内容不足或为Cloudflare错误。")
                        if _content_from_dl == "CLOUDFLARE_ERROR_PAGE": # 如果备用下载是CF错误，则整个下载失败
                            return False
                
                except ValueError as ve:
                    with self.print_lock: print(f"    ✗ 备用下载预处理失败 (aid/vid提取): {ve}")
                    if not image_urls_to_download and primary_text_unsatisfactory: text_content = original_text_content_before_fallback
                except Exception as e_fallback: # Catch any other error during fallback
                    with self.print_lock: print(f"    ✗ 备用下载文本时发生未知错误: {e_fallback}")
                    if not image_urls_to_download and primary_text_unsatisfactory: text_content = original_text_content_before_fallback

            # 5. Final content validation (Check again for Cloudflare error before saving)
            if self._is_cloudflare_error(text_content):
                with self.print_lock:
                    print(f"  ✗ 最终文本内容为Cloudflare错误页面，将不保存: {chapter['title']}")
                return False # 标记下载失败以进行重试
                
            final_text_content_stripped = text_content.strip()
            if not final_text_content_stripped and not image_urls_to_download:
                with self.print_lock:
                    print(f"✗ 无法获取章节内容 (文本和图片均无或无效): {chapter['title']}")
                return False
            
            if len(final_text_content_stripped) < 20 and not image_urls_to_download: # Stricter short text check
                 with self.print_lock:
                    print(f"✗ 文本内容过短 (<20 chars) 且无图片: {chapter['title']}")
                 return False

            # 6. Clean up final text content
            if final_text_content_stripped:
                cleanup_patterns = [
                    '本文来自 轻小说文库(http://www.wenku8.com)',
                    '台版 转自 轻之国度', # This might be desirable for some, but for generic cleanup, remove
                    '最新最全的日本动漫轻小说 轻小说文库(http://www.wenku8.com) 为你一网打尽！',
                    '更多精彩热门日本轻小说、动漫小说，轻小说文库(http://www.wenku8.com) 为你一网打尽！',
                    'www.wenku8.com',
                    'wenku8.com',
                    '轻小说文库',
                    # Regex patterns for more complex cleanup
                    r'^插图来源[:：]?.*$',
                    r'^文字来源[:：]?.*$',
                    r'^(?=.*轻之国度)(?=.*仅供试阅).*$', # Line with "轻之国度" and "仅供试阅"
                    r'^(?=.*LKID)(?=.*录入).*$',      # Line with LKID and 录入
                    r'^\s*扫图：.*$',
                    r'^\s*录入：.*$',
                    r'^\s*校对：.*$',
                    r'^\s*翻译：.*$',
                    r'^\s*润色：.*$',
                    r'^\s*修图：.*$',
                    r'^\s*转自：.*$',
                    r'^\s*仅供个人学习交流使用，禁作商业用途.*$',
                    r'^\s*下载后请在24小时内删除，LK不负担任何责任.*$',
                    r'^\s*请尊重翻译、扫图、录入、校对的辛勤劳动，转载请保留信息.*$',
                    r'^\s*本文特别严禁转载至SF轻小说频道及轻小说文库测(.*)$', # SF and wenku8 repost warning
                    r'^\s*──────────────$', # Separator lines
                    r'^\s*━━━━━━━━━━━━$',
                    r'^\s*＊＊＊$',
                    r'(?i)novel Horizons - Présente', # French scanlation group
                    r'(?i)Par Ln Vol.(.*)Traduction(.*)'
                ]
                current_text_to_clean = final_text_content_stripped
                for pattern in cleanup_patterns:
                    try:
                        if any(c in pattern for c in r'.*+?^$[]{}()|\\\\'): # Basic check if it's a regex
                             current_text_to_clean = re.sub(pattern, '', current_text_to_clean, flags=re.MULTILINE).strip()
                        else: # Simple string replace
                            current_text_to_clean = current_text_to_clean.replace(pattern, '').strip()
                    except re.error as e_re:
                        with self.print_lock: print(f"  警告: 清理规则 '{pattern}' 正则表达式错误: {e_re}")

                text_content = re.sub(r'\n{3,}', '\n\n', current_text_to_clean.strip())
            else:
                text_content = ""

            # 7. Save chapter text and images
            # Sanitize chapter title for file/dir names: remove problematic chars, limit length
            safe_chapter_title = re.sub(r'[<>:"/\\|?*]', '_', chapter['title'])
            safe_chapter_title = re.sub(r'[\\s\\.\\(\\)]+', '_', safe_chapter_title) # Replace whitespace, dots, parens with underscore
            safe_chapter_title = re.sub(r'_+', '_', safe_chapter_title) # Consolidate multiple underscores
            safe_chapter_title = safe_chapter_title.strip('_')
            if len(safe_chapter_title) > 60: # Limit length to avoid issues with long paths
                safe_chapter_title = safe_chapter_title[:60].strip('_')
            if not safe_chapter_title: # If title becomes empty after sanitization
                safe_chapter_title = f"chapter_{chapter['url'].split('/')[-1].replace('.htm','')}"


            text_file_saved_successfully = False
            image_files_references = []

            if text_content: # 只有当文本内容不是Cloudflare错误时才保存
                text_filename = f"{safe_chapter_title}.txt"
                text_filepath = os.path.join(output_dir, text_filename)
                try:
                    with open(text_filepath, 'w', encoding='utf-8') as f:
                        f.write(f"# {chapter['title']}\n\n")
                        f.write(text_content)
                    text_file_saved_successfully = True
                except IOError as e_io_text:
                    with self.print_lock: print(f"  ✗ 保存文本文件失败 {text_filename}: {e_io_text}")
            
            # Download and save images
            downloaded_image_count = 0
            for i, img_url in enumerate(image_urls_to_download):
                try:
                    # Determine image extension
                    img_original_filename = img_url.split('/')[-1].split('?')[0].split('#')[0]
                    img_ext = 'jpg' # Default
                    if '.' in img_original_filename:
                        candidate_ext = img_original_filename.split('.')[-1].lower()
                        if len(candidate_ext) <= 4 and candidate_ext.isalnum() and candidate_ext not in ['php', 'html', 'htm']:
                            img_ext = candidate_ext
                    
                    img_filename_for_ref = f"{safe_chapter_title}_img_{i+1}.{img_ext}"
                    img_filepath = os.path.join(output_dir, img_filename_for_ref)
                    image_files_references.append(img_filename_for_ref) # Add to list for text file ref

                    if os.path.exists(img_filepath) and os.path.getsize(img_filepath) > 0:
                        with self.print_lock: print(f"    ✓ 图片已存在且有效: {img_filename_for_ref}")
                        downloaded_image_count += 1
                        continue

                    with self.print_lock: print(f"    ↪ 下载图片 ({i+1}/{len(image_urls_to_download)}): {img_url} -> {img_filename_for_ref}")
                    
                    img_response = self.session.get(img_url, stream=True, timeout=30)
                    img_response.raise_for_status()
                    
                    with open(img_filepath, 'wb') as f_img:
                        for chunk in img_response.iter_content(chunk_size=8192):
                            f_img.write(chunk)
                    
                    if os.path.exists(img_filepath) and os.path.getsize(img_filepath) > 0:
                         downloaded_image_count += 1
                         with self.print_lock: print(f"    ✓ 图片下载成功: {img_filename_for_ref}")
                    else:
                         with self.print_lock: print(f"    ✗ 图片下载后文件无效或为0字节: {img_filename_for_ref}")
                         if os.path.exists(img_filepath): os.remove(img_filepath)
                    time.sleep(0.3) # Small polite delay
                except requests.exceptions.Timeout:
                    with self.print_lock: print(f"    ✗ 下载图片超时: {img_url}")
                except requests.exceptions.RequestException as req_e:
                    with self.print_lock: print(f"    ✗ 下载图片网络请求失败 {img_url}: {req_e}")
                except IOError as io_e:
                    with self.print_lock: print(f"    ✗ 保存图片文件失败 {img_filename_for_ref}: {io_e}")
                except Exception as e_img: # Catch any other error during image processing
                    with self.print_lock: print(f"    ✗ 处理图片时发生未知错误 {img_url}: {e_img}")

            # If text file was saved and there were images, append image references to text file
            if text_file_saved_successfully and image_files_references:
                text_filepath = os.path.join(output_dir, f"{safe_chapter_title}.txt") # Reconstruct path
                try:
                    with open(text_filepath, 'a', encoding='utf-8') as f:
                        f.write("\n\n--- (本章节包含插图) ---\n")
                        for img_ref in image_files_references:
                            f.write(f"[插图: {img_ref}]\n")
                except IOError as e_io_append:
                     with self.print_lock: print(f"  警告: 追加图片引用到文本文件失败 {text_filepath}: {e_io_append}")
            
            # Final status determination
            overall_success = False
            status_message_parts = []

            if text_file_saved_successfully:
                status_message_parts.append("文本")
                overall_success = True
            elif text_content: # Text existed but failed to save
                status_message_parts.append("文本(保存失败)")

            if image_urls_to_download:
                status_message_parts.append(f"图片 {downloaded_image_count}/{len(image_urls_to_download)}")
                if downloaded_image_count > 0:
                    overall_success = True # At least one image downloaded is a success
            
            if not text_content and not image_urls_to_download: # Nothing was ever expected
                 # This case means the chapter was deemed empty from the start (after primary/fallback)
                 # `overall_success` will be false based on current logic, which is correct for empty source.
                 # The earlier checks should prevent this from being reported as a "download failure" if source is empty.
                 pass


            if overall_success:
                 with self.print_lock:
                    print(f"  ✓ 处理完成: {chapter['title']} ({', '.join(status_message_parts) if status_message_parts else '内容为空'})")
            else:
                 # This implies:
                 # 1. No text was successfully saved (either not present, or save failed)
                 # AND
                 # 2. EITHER no images were expected OR all expected images failed to download.
                 with self.print_lock:
                    print(f"  ✗ 下载失败 (无有效内容输出): {chapter['title']}")
            return overall_success
            
        except requests.exceptions.Timeout:
            with self.print_lock:
                print(f"✗ 处理章节超时: {chapter['title']} (URL: {chapter['url']})")
            return False
        except requests.exceptions.RequestException as e_req:
            with self.print_lock:
                print(f"✗ 处理章节时网络请求错误: {chapter['title']} - {e_req}")
            return False
        except Exception as e:
            with self.print_lock:
                print(f"✗ 下载章节时发生意外错误: {chapter['title']} - {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def download_volume(self, novel_id, volume_index, output_dir='./novels', max_retries=3, retry_delay=5):
        """下载指定卷的所有章节"""
        novel = self.get_novel_details(novel_id)
        if not novel or not novel['catalog_url']:
            print("无法获取小说信息或目录链接")
            return False
        
        volumes = self.get_chapter_list(novel['catalog_url'])
        if not volumes or volume_index >= len(volumes):
            print(f"无法找到指定的卷 (索引: {volume_index})")
            return False
        
        volume = volumes[volume_index]
        print(f"开始下载: 《{novel['title']}》- {volume['title']}")
        
        # 创建输出目录
        safe_volume_title = re.sub(r'[<>:"/\\|?*]', '_', volume['title'])
        volume_dir = os.path.join(output_dir, safe_volume_title)
        os.makedirs(volume_dir, exist_ok=True)
        
        # 下载章节
        success_count = 0
        for i, chapter in enumerate(volume['chapters'], 1):
            # 添加序号前缀以保持顺序
            chapter_with_prefix = {
                'title': f"{i:03d}_{chapter['title']}",
                'url': chapter['url']
            }
            
            retries = 0
            downloaded_successfully = False
            while retries < max_retries and not downloaded_successfully:
                if retries > 0:
                    with self.print_lock:
                        print(f"正在重试下载: {chapter['title']} (尝试 {retries}/{max_retries-1})")
                    time.sleep(retry_delay)
                
                downloaded_successfully = self.download_chapter(chapter_with_prefix, volume_dir, novel_id)
                
                if downloaded_successfully:
                    success_count += 1
                    time.sleep(retry_delay)
                else:
                    retries += 1
            
            if not downloaded_successfully:
                with self.print_lock:
                    print(f"✗ 下载失败 (已达最大重试次数): {chapter['title']}")

        print(f"\n卷下载完成! 成功下载 {success_count}/{len(volume['chapters'])} 个章节")
        print(f"文件保存在: {volume_dir}")
        
        # 自动修复下载的TXT文件
        fix_all_txt_files(volume_dir)        
        return success_count > 0
    
    def download_novel(self, novel_id, output_dir='./novels', max_retries=3, retry_delay=5):
        """下载整本小说"""
        novel = self.get_novel_details(novel_id)
        if not novel or not novel['catalog_url']:
            print("无法获取小说信息或目录链接")
            return False
        
        print(f"开始下载: 《{novel['title']}》 作者: {novel['author']}")
        
        # 创建输出目录
        safe_title = re.sub(r'[<>:"/\\|?*]', '_', novel['title'])
        novel_dir = output_dir
        os.makedirs(novel_dir, exist_ok=True)
        
        # 获取章节列表
        volumes = self.get_chapter_list(novel['catalog_url'])
        if not volumes:
            print("无法获取章节列表")
            return False
        
        total_chapters = sum(len(vol['chapters']) for vol in volumes)
        print(f"找到 {len(volumes)} 卷，{total_chapters} 个章节，开始下载...")
        
        # 按卷下载
        total_success = 0
        all_volume_dirs = []  # 存储所有卷的目录路径
        
        for vol_idx, volume in enumerate(volumes):
            print(f"\n开始下载卷: {volume['title']}")
            
            # 创建卷目录
            safe_volume_title = re.sub(r'[<>:"/\\|?*]', '_', volume['title'])
            volume_dir = os.path.join(novel_dir, safe_volume_title)
            os.makedirs(volume_dir, exist_ok=True)
            all_volume_dirs.append(volume_dir)
            
            success_count = 0
            for i, chapter in enumerate(volume['chapters'], 1):
                # 添加序号前缀以保持顺序
                chapter_with_prefix = {
                    'title': f"{i:03d}_{chapter['title']}",
                    'url': chapter['url']
                }
                
                retries = 0
                downloaded_successfully = False
                while retries < max_retries and not downloaded_successfully:
                    if retries > 0:
                        with self.print_lock:
                            print(f"正在重试下载: {chapter['title']} (尝试 {retries}/{max_retries-1})")
                        time.sleep(retry_delay)
                    
                    downloaded_successfully = self.download_chapter(chapter_with_prefix, volume_dir, novel_id)
                    
                    if downloaded_successfully:
                        success_count += 1
                        time.sleep(2)  # 每个章节下载后等待2秒
                    else:
                        retries += 1
                
                if not downloaded_successfully:
                    with self.print_lock:
                        print(f"✗ 下载失败 (已达最大重试次数): {chapter['title']}")
            
            total_success += success_count
            print(f"卷 {volume['title']} 下载完成: {success_count}/{len(volume['chapters'])} 个章节")
            
            # 对当前卷的TXT文件进行修复
            fix_all_txt_files(volume_dir)

        print(f"\n小说下载完成! 总共成功下载 {total_success}/{total_chapters} 个章节")
        print(f"文件保存在: {novel_dir}")
        
        return total_success > 0

def main():
    downloader = Wenku8Downloader()

    while True:
        print("\n" + "="*50)
        print("轻小说下载器")
        print("="*50)
        print("1. 按小说名搜索")
        print("2. 按作者名搜索")
        print("3. 直接输入小说ID下载")
        print("4. 退出")
        
        choice = input("\n请选择操作 (1-4): ").strip()
        
        current_search_results = []
        current_pagination_info = None

        if choice == '1' or choice == '2':
            search_term_prompt = "请输入小说名: " if choice == '1' else "请输入作者名: "
            search_type_val = 'articlename' if choice == '1' else 'author'
            
            page_to_fetch = None
            
            while True:
                if page_to_fetch:
                    print(f"正在获取第 {current_pagination_info['current_page'] if current_pagination_info else '?'} 页...")
                    search_data = downloader.search_novels(page_url=page_to_fetch)
                else:
                    keyword = input(search_term_prompt).strip()
                    if not keyword:
                        break
                    search_data = downloader.search_novels(keyword=keyword, search_type=search_type_val)

                if search_data and search_data['novels']:
                    current_search_results = search_data['novels']
                    current_pagination_info = search_data['pagination_info']
                    
                    print(f"\n找到 {len(current_search_results)} 本小说 (第 {current_pagination_info['current_page']}/{current_pagination_info['total_pages']} 页):")
                    for i, novel in enumerate(current_search_results, 1):
                        print(f"{i}. 《{novel['name']}》 (ID: {novel['id']})")
                    
                    options_prompt = f"\n请选择要下载的小说 (1-{len(current_search_results)})"
                    if current_pagination_info and current_pagination_info.get('next_page_url'):
                        options_prompt += ", 输入 'n' 查看下一页"
                    if current_pagination_info and current_pagination_info.get('prev_page_url'):
                        options_prompt += ", 输入 'p' 查看上一页"
                    options_prompt += ", 或 'q' 返回主菜单: "
                    
                    user_selection = input(options_prompt).strip().lower()

                    if user_selection == 'n' and current_pagination_info and current_pagination_info.get('next_page_url'):
                        page_to_fetch = current_pagination_info['next_page_url']
                        current_search_results = []
                        continue
                    elif user_selection == 'p' and current_pagination_info and current_pagination_info.get('prev_page_url'):
                        page_to_fetch = current_pagination_info['prev_page_url']
                        current_search_results = []
                        continue
                    elif user_selection == 'q':
                        break
                    else:
                        try:
                            selection_idx = int(user_selection)
                            if 1 <= selection_idx <= len(current_search_results):
                                selected_novel = current_search_results[selection_idx - 1]
                                
                                # 显示章节信息并允许选择下载方式
                                novel_details = downloader.get_novel_details(selected_novel['id'])
                                if novel_details and novel_details['catalog_url']:
                                    volumes = downloader.get_chapter_list(novel_details['catalog_url'])
                                    if volumes:
                                        print(f"\n《{novel_details['title']}》章节信息:")
                                        for i, volume in enumerate(volumes):
                                            print(f"卷 {i+1}: {volume['title']} ({len(volume['chapters'])} 章节)")
                                        
                                        download_choice = input("\n请选择下载方式:\n1. 下载整本小说\n2. 下载指定卷\n请输入选择 (1-2): ").strip()
                                        
                                        if download_choice == '1':
                                            downloader.download_novel(selected_novel['id'])
                                        elif download_choice == '2':
                                            vol_choice = input(f"请选择要下载的卷 (1-{len(volumes)}): ").strip()
                                            try:
                                                vol_idx = int(vol_choice) - 1
                                                if 0 <= vol_idx < len(volumes):
                                                    downloader.download_volume(selected_novel['id'], vol_idx)
                                                else:
                                                    print("无效的卷选择")
                                            except ValueError:
                                                print("请输入有效的数字")
                                        else:
                                            print("无效选择")
                                    else:
                                        print("无法获取章节信息")
                                else:
                                    print("无法获取小说详情")
                                break
                            else:
                                print("选择无效")
                        except ValueError:
                            print("请输入有效数字、'n'、'p' 或 'q'")
                elif page_to_fetch:
                     print("没有更多结果了。")
                     break
                else:
                    break
        
        elif choice == '3':
            try:
                novel_id_input = input("请输入小说ID: ").strip()
                # Allow multiple IDs separated by comma or space
                novel_ids_str = re.split(r'[\\s,]+', novel_id_input)
                novel_ids = [int(nid) for nid in novel_ids_str if nid.isdigit()]
                
                if not novel_ids:
                    print("未输入有效的小说ID。")
                
                for novel_id in novel_ids:
                    print(f"\n开始处理小说ID: {novel_id}")
                    # Display chapter info and allow choice for single ID download
                    novel_details_single = downloader.get_novel_details(novel_id)
                    if novel_details_single and novel_details_single['catalog_url']:
                        volumes_single = downloader.get_chapter_list(novel_details_single['catalog_url'])
                        if volumes_single:
                            print(f"\n《{novel_details_single['title']}》章节信息:")
                            for i, volume_s in enumerate(volumes_single):
                                print(f"卷 {i+1}: {volume_s['title']} ({len(volume_s['chapters'])} 章节)")
                            
                            download_choice_single = input("\n请选择下载方式:\n1. 下载整本小说\n2. 下载指定卷\n请输入选择 (1-2, 或按Enter跳过此小说): ").strip()
                            
                            if download_choice_single == '1':
                                downloader.download_novel(novel_id)
                            elif download_choice_single == '2':
                                vol_choice_single = input(f"请选择要下载的卷 (1-{len(volumes_single)}): ").strip()
                                try:
                                    vol_idx_single = int(vol_choice_single) - 1
                                    if 0 <= vol_idx_single < len(volumes_single):
                                        downloader.download_volume(novel_id, vol_idx_single)
                                    else:
                                        print("无效的卷选择")
                                except ValueError:
                                    print("请输入有效的数字")
                            elif not download_choice_single: # User pressed Enter
                                print(f"跳过小说ID: {novel_id}")
                            else:
                                print("无效选择，跳过此小说。")
                        else:
                            print(f"无法获取小说ID {novel_id} 的章节信息，尝试直接下载整本。")
                            downloader.download_novel(novel_id) # Fallback to download all if no chapters shown
                    else:
                        print(f"无法获取小说ID {novel_id} 的详情，尝试直接下载整本。")
                        downloader.download_novel(novel_id) # Fallback if details fail

            except ValueError:
                print("请输入有效的数字ID (可使用空格或逗号分隔多个ID)")
        
        elif choice == '4':
            print("感谢使用，再见!")
            break
        
        else:
            print("无效选择，请重新输入")

if __name__ == "__main__":
    main()