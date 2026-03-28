# -*- coding: utf-8 -*-
"""小红书搜索 + 评论抓取 + 图文内容提取模块（undetected-chromedriver + Cookie 注入）"""

import json
import random
import re
import time
from typing import Any, Dict, List, Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import global_settings, get_logger

logger = get_logger()

XHS_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_notes"
XHS_NOTE_URL = "https://www.xiaohongshu.com/explore/{note_id}"
XHS_DOMAIN = ".xiaohongshu.com"


def _parse_cookie_string(cookie_string: str) -> List[Dict[str, str]]:
    """解析 Cookie 字符串为 Selenium 格式"""
    cookies = []
    for pair in cookie_string.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        name, value = name.strip(), value.strip()
        if name and value:
            cookies.append({"name": name, "value": value, "domain": XHS_DOMAIN, "path": "/"})
    return cookies


def _create_browser(cookie_string: str = ""):
    """创建 undetected-chromedriver 浏览器（自动绕过反爬检测）"""
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=zh-CN")
    options.add_argument("--disable-gpu")

    driver = uc.Chrome(options=options, use_subprocess=True, version_main=145)
    driver.set_page_load_timeout(global_settings.browser.page_load_timeout)

    if cookie_string:
        logger.info("[xhs] 注入 Cookie 登录态（undetected-chromedriver）")
        driver.get("https://www.xiaohongshu.com")
        time.sleep(4)
        parsed_cookies = _parse_cookie_string(cookie_string)
        injected_count = 0
        for cookie in parsed_cookies:
            try:
                driver.add_cookie(cookie)
                injected_count += 1
            except Exception:
                pass
        logger.info(f"[xhs] 已注入 {injected_count}/{len(parsed_cookies)} 个 Cookie")
        driver.refresh()
        time.sleep(4)

    return driver


def _parse_count(count_text: str) -> int:
    """解析数量文本（如 '1.2万' -> 12000）"""
    if not count_text:
        return 0
    count_text = count_text.strip()
    try:
        if "w" in count_text.lower() or "万" in count_text:
            num_part = re.sub(r"[^\d.]", "", count_text)
            return int(float(num_part) * 10000) if num_part else 0
        if "亿" in count_text:
            num_part = re.sub(r"[^\d.]", "", count_text)
            return int(float(num_part) * 100000000) if num_part else 0
        num_part = re.sub(r"[^\d]", "", count_text)
        return int(num_part) if num_part else 0
    except (ValueError, TypeError):
        return 0


def create_browser(cookie_string: str = ""):
    """创建浏览器实例（供外部调用，实现浏览器复用）"""
    return _create_browser(cookie_string=cookie_string)

def search(keywords: str, page_size: int = 10, cookie_string: str = "", driver=None) -> Dict[str, Any]:
    """小红书关键词搜索，返回按点赞排序的 Top N 笔记"""
    logger.info(f"[xhs.search] 开始搜索: keywords={keywords}")
    own_driver = driver is None
    try:
        if own_driver:
            driver = _create_browser(cookie_string=cookie_string)
        search_url = XHS_SEARCH_URL.format(keyword=keywords)
        driver.get(search_url)
        time.sleep(5)

        # 滚动加载更多
        for _ in range(8):
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(1.5)

        items = _extract_notes_from_dom(driver, page_size * 3)

        # 从 SSR 数据提取详细信息
        ssr_details = _extract_ssr_data(driver)
        if ssr_details:
            for item in items:
                note_id = item.get("note_id")
                if note_id and note_id in ssr_details:
                    item["detail"] = ssr_details[note_id]
                    # 更新基本字段
                    detail = ssr_details[note_id]
                    if detail.get("title") and not item.get("title"):
                        item["title"] = detail["title"]
                    if detail.get("displayTitle") and not item.get("title"):
                        item["title"] = detail["displayTitle"]
                    if detail.get("nickname") and not item.get("author"):
                        item["author"] = detail["nickname"]
                    if detail.get("likedCount") and item.get("like_count") == 0:
                        item["like_count"] = detail["likedCount"]
                    if detail.get("type"):
                        item["is_video"] = detail["type"] == "video"
                        item["content_type"] = "video" if item["is_video"] else "image_text"

        # 按点赞排序
        items.sort(key=lambda n: n.get("like_count", 0), reverse=True)
        items = items[:page_size]

        logger.info(f"[xhs.search] 找到 {len(items)} 条笔记（按点赞排序）")
        return {"items": items, "total": len(items), "keywords": keywords, "platform": "xiaohongshu"}
    except Exception as search_error:
        logger.error(f"[xhs.search] 搜索失败: {search_error}")
        return {"items": [], "total": 0, "keywords": keywords, "error": str(search_error)}
    finally:
        if own_driver and driver:
            driver.quit()


def _extract_notes_from_dom(driver, max_count: int) -> List[Dict[str, Any]]:
    """从搜索结果页 DOM 提取笔记列表"""
    items = []

    note_selectors = [
        "section.note-item",
        "div[class*='note-item']",
        "a[class*='cover']",
        "div[class*='feeds-page'] section",
    ]

    note_elements = []
    for selector in note_selectors:
        note_elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if note_elements:
            break

    for element in note_elements[:max_count]:
        try:
            note_data = _parse_note_card(element, driver)
            if note_data:
                items.append(note_data)
        except Exception:
            continue

    # 如果 DOM 提取不到，尝试从页面源码提取
    if not items:
        items = _extract_notes_from_source(driver, max_count)

    return items


def _parse_note_card(element, driver) -> Optional[Dict[str, Any]]:
    """解析单个笔记卡片"""
    try:
        # 提取标题
        title = ""
        for title_selector in ["a.title span", "span.title", "a[class*='title']", "p[class*='desc']"]:
            try:
                title_el = element.find_element(By.CSS_SELECTOR, title_selector)
                title = title_el.text.strip()
                if title:
                    break
            except Exception:
                continue

        if not title:
            full_text = element.text.strip()
            lines = [line.strip() for line in full_text.split("\n") if line.strip()]
            title = lines[0] if lines else ""

        # 提取链接和 note_id
        note_id = ""
        note_url = ""
        try:
            link_el = element.find_element(By.CSS_SELECTOR, "a[href*='/explore/'], a[href*='/discovery/item/']")
            href = link_el.get_attribute("href") or ""
            note_url = href
            note_id_match = re.search(r"/explore/([a-f0-9]+)", href)
            if not note_id_match:
                note_id_match = re.search(r"/discovery/item/([a-f0-9]+)", href)
            if note_id_match:
                note_id = note_id_match.group(1)
        except Exception:
            pass

        # 提取点赞数
        like_count = 0
        for like_selector in ["span.like-wrapper span.count", "span[class*='like'] span", "span[class*='count']"]:
            try:
                like_el = element.find_element(By.CSS_SELECTOR, like_selector)
                like_count = _parse_count(like_el.text)
                if like_count > 0:
                    break
            except Exception:
                continue

        # 提取作者
        author = ""
        for author_selector in ["span.author-wrapper span.name", "a[class*='author']", "span[class*='name']"]:
            try:
                author_el = element.find_element(By.CSS_SELECTOR, author_selector)
                author = author_el.text.strip()
                if author:
                    break
            except Exception:
                continue

        # 判断是否为视频（通过视频图标或标记）
        is_video = False
        try:
            video_indicators = element.find_elements(
                By.CSS_SELECTOR,
                "svg[class*='video'], span[class*='video'], div[class*='play'], svg[class*='play']"
            )
            if video_indicators:
                is_video = True
        except Exception:
            pass

        if title or note_id:
            return {
                "note_id": note_id,
                "title": title,
                "author": author,
                "url": note_url or (f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else ""),
                "like_count": like_count,
                "is_video": is_video,
                "content_type": "video" if is_video else "image_text",
            }
    except Exception:
        pass
    return None


def _extract_notes_from_source(driver, max_count: int) -> List[Dict[str, Any]]:
    """从页面源码正则提取笔记数据"""
    items = []
    try:
        page_source = driver.page_source
        # 匹配 SSR 数据中的笔记
        note_pattern = re.compile(
            r'"noteId"\s*:\s*"([a-f0-9]+)".*?"title"\s*:\s*"([^"]*)"',
            re.DOTALL,
        )
        matches = note_pattern.findall(page_source)
        for note_id, title in matches[:max_count]:
            decoded_title = title.encode().decode("unicode_escape", errors="ignore")
            items.append({
                "note_id": note_id,
                "title": decoded_title,
                "author": "",
                "url": f"https://www.xiaohongshu.com/explore/{note_id}",
                "like_count": 0,
                "is_video": False,
                "content_type": "image_text",
            })
    except Exception:
        pass
    return items

def _extract_ssr_data(driver) -> Dict[str, Dict[str, Any]]:
    """从 __INITIAL_STATE__ SSR 数据中提取笔记详细信息"""
    ssr_data = {}
    try:
        page_source = driver.page_source
        # 提取 __INITIAL_STATE__ JSON
        ssr_pattern = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(.+?)\s*</script>', re.DOTALL)
        match = ssr_pattern.search(page_source)
        if not match:
            logger.warning("[xhs.ssr] 未找到 __INITIAL_STATE__ 数据")
            return ssr_data

        raw_json = match.group(1)
        # 替换 undefined 为 null
        clean_json = re.sub(r'\bundefined\b', 'null', raw_json)
        state_data = json.loads(clean_json)

        # 从 state 中提取笔记数据
        notes_map = {}
        # 尝试多种可能的路径
        possible_paths = [
            state_data.get("search", {}).get("note", {}).get("data", []),
            state_data.get("search", {}).get("result", {}).get("data", []),
            state_data.get("note", {}).get("detail", {}).get("note", {}),
            state_data.get("note", {}).get("noteDetail", {}).get("note", {}),
        ]

        for data in possible_paths:
            if isinstance(data, dict):
                data = [data]
            if isinstance(data, list):
                for note_item in data:
                    if isinstance(note_item, dict):
                        note_id = note_item.get("noteId") or note_item.get("id")
                        if note_id:
                            notes_map[note_id] = note_item

        # 尝试从 feeds 或其他路径提取
        if not notes_map:
            for key in ["feeds", "items", "notes"]:
                if key in state_data:
                    feeds_data = state_data[key]
                    if isinstance(feeds_data, dict):
                        feeds_data = feeds_data.get("data", [])
                    if isinstance(feeds_data, list):
                        for item in feeds_data:
                            if isinstance(item, dict):
                                note_id = item.get("noteId") or item.get("id")
                                if note_id:
                                    notes_map[note_id] = item

        ssr_data = notes_map
        logger.info(f"[xhs.ssr] 从 SSR 数据提取到 {len(ssr_data)} 条笔记详情")

    except json.JSONDecodeError as e:
        logger.error(f"[xhs.ssr] JSON 解析失败: {e}")
    except Exception as e:
        logger.error(f"[xhs.ssr] 提取 SSR 数据失败: {e}")

    return ssr_data

def _find_note_card_element(driver, note_id: str):
    """在搜索结果页中找到指定 note_id 的可点击链接元素"""
    # 优先直接查找包含 note_id 的 <a> 链接（点击链接才能触发弹窗）
    try:
        links = driver.find_elements(By.CSS_SELECTOR, f"a[href*='{note_id}']")
        if links:
            # 优先返回封面链接（通常是第一个匹配的 <a>）
            for link in links:
                href = link.get_attribute("href") or ""
                if "/explore/" in href or "/discovery/" in href:
                    return link
            return links[0]
    except Exception:
        pass

    # 备选：从卡片容器中查找内部链接
    card_selectors = [
        "section.note-item",
        "div[class*='note-item']",
        "div[class*='feeds-page'] section",
    ]
    
    for selector in card_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                try:
                    inner_links = element.find_elements(By.CSS_SELECTOR, "a[href*='/explore/']")
                    for link in inner_links:
                        if note_id in (link.get_attribute("href") or ""):
                            return link
                except Exception:
                    continue
        except Exception:
            continue
    return None

def _open_note_modal(driver, note_id: str, max_retries: int = 3) -> bool:
    """点击笔记卡片打开侧边栏弹窗"""
    from selenium.webdriver.common.action_chains import ActionChains

    # 弹窗检测选择器（小红书搜索结果页点击后弹出的侧边栏）
    modal_selectors = [
        "div[class*='note-detail']",
        "div[class*='detail-modal']",
        "div[class*='note-container']",
        "div[class*='NoteContainer']",
        "div[class*='note-content']",
        "div[class*='NoteContent']",
        "div[id*='note-detail']",
        "div[class*='modal']",
    ]

    for attempt in range(max_retries):
        try:
            card_element = _find_note_card_element(driver, note_id)
            if not card_element:
                logger.warning(f"[xhs.modal] 未找到笔记 {note_id} 的卡片元素")
                return False

            # 先滚动到元素可见位置（居中显示），避免被顶部 tab 栏遮挡
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                card_element
            )
            time.sleep(1)

            # 尝试多种点击方式
            if attempt == 0:
                # 第一次：使用 ActionChains 模拟真实用户点击
                ActionChains(driver).move_to_element(card_element).click().perform()
            elif attempt == 1:
                # 第二次：使用 JavaScript 点击
                driver.execute_script("arguments[0].click();", card_element)
            else:
                # 第三次：直接 Selenium 点击
                card_element.click()

            time.sleep(2)

            # 检测弹窗是否出现
            for modal_selector in modal_selectors:
                try:
                    WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, modal_selector))
                    )
                    logger.info(f"[xhs.modal] 笔记 {note_id} 弹窗已打开")
                    return True
                except Exception:
                    continue

            # 检查 URL 是否变化（点击卡片后 URL 可能包含 noteId）
            current_url = driver.current_url
            if note_id in current_url:
                logger.info(f"[xhs.modal] 笔记 {note_id} 页面已跳转/弹窗已打开（URL 包含 noteId）")
                return True

            logger.warning(f"[xhs.modal] 笔记 {note_id} 弹窗未出现，重试 {attempt + 1}/{max_retries}")
        except Exception as e:
            logger.error(f"[xhs.modal] 打开弹窗失败 (尝试 {attempt + 1}): {e}")
            time.sleep(1)

    return False

def _close_note_modal(driver, search_url: str = ""):
    """关闭笔记详情弹窗，并确保页面恢复到搜索结果页"""
    try:
        # 方法1: 按 ESC 键
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(1)
        
        # 方法2: 点击遮罩层（如果有）
        try:
            overlay = driver.find_element(By.CSS_SELECTOR, "div[class*='overlay'], div[class*='mask']")
            overlay.click()
        except Exception:
            pass
        
        # 方法3: 点击关闭按钮
        try:
            close_btn = driver.find_element(By.CSS_SELECTOR, "button[class*='close'], svg[class*='close']")
            close_btn.click()
        except Exception:
            pass
            
        time.sleep(1)
        
        # 检查页面是否被 sec 网关重定向到 404 页面
        current_url = driver.current_url
        if "/404" in current_url or "error_code" in current_url:
            logger.warning(f"[xhs.modal] 检测到页面被重定向到 404，正在恢复搜索结果页...")
            if search_url:
                driver.get(search_url)
            else:
                driver.back()
            time.sleep(3)
            
            # 再次检查是否恢复成功
            recovered_url = driver.current_url
            if "/404" in recovered_url or "error_code" in recovered_url:
                logger.warning(f"[xhs.modal] driver.back() 未恢复，尝试再次后退...")
                driver.back()
                time.sleep(3)
            
            # 恢复后重新滚动加载搜索结果
            if "search_result" in driver.current_url:
                logger.info(f"[xhs.modal] 已恢复到搜索结果页: {driver.current_url}")
                for _ in range(3):
                    driver.execute_script("window.scrollBy(0, 600);")
                    time.sleep(1)
            else:
                logger.warning(f"[xhs.modal] 恢复后页面仍非搜索结果页: {driver.current_url}")
        else:
            logger.info("[xhs.modal] 弹窗已关闭，页面正常")
    except Exception as e:
        logger.error(f"[xhs.modal] 关闭弹窗失败: {e}")

def _extract_content_from_modal(driver) -> Dict[str, Any]:
    """从弹窗中提取笔记正文内容"""
    result = {
        "title": "",
        "content": "",
        "author": "",
        "like_count": 0,
        "collect_count": 0,
        "comment_count": 0,
        "share_count": 0,
        "is_video": False,
        "content_type": "image_text",
    }

    try:
        # 提取标题
        for title_selector in [
            "div[class*='note-detail'] div[class*='title']",
            "div[class*='detail-modal'] h1, div[class*='detail-modal'] h2",
            "div[class*='note-container'] h1, div[class*='note-container'] h2",
            "div[class*='title'] span",
        ]:
            try:
                title_el = driver.find_element(By.CSS_SELECTOR, title_selector)
                title = title_el.text.strip()
                if title:
                    result["title"] = title
                    break
            except Exception:
                continue

        # 提取正文
        for content_selector in [
            "div[class*='note-detail'] div[class*='desc']",
            "div[class*='detail-modal'] div[class*='content']",
            "div[class*='note-container'] div[class*='desc']",
            "div[class*='desc'] span",
        ]:
            try:
                content_el = driver.find_element(By.CSS_SELECTOR, content_selector)
                content = content_el.text.strip()
                if content:
                    result["content"] = content
                    break
            except Exception:
                continue

        # 提取作者
        for author_selector in [
            "div[class*='note-detail'] span[class*='username']",
            "div[class*='detail-modal'] a[class*='author'] span",
            "div[class*='note-container'] span[class*='nickname']",
        ]:
            try:
                author_el = driver.find_element(By.CSS_SELECTOR, author_selector)
                author = author_el.text.strip()
                if author:
                    result["author"] = author
                    break
            except Exception:
                continue

        # 提取互动数据
        interaction_data = _extract_interaction_data(driver)
        result.update(interaction_data)

        # 不在弹窗中判断 is_video，保持搜索结果中的判断（弹窗中 video 标签不可靠）

    except Exception as e:
        logger.error(f"[xhs.modal] 提取弹窗内容失败: {e}")

    return result

def _extract_comments_from_modal(driver, max_comments: int = 30) -> List[Dict[str, Any]]:
    """从弹窗中提取评论"""
    comments = []

    try:
        # 等待弹窗内容加载
        time.sleep(2)

        # 尝试在弹窗内部滚动评论区（而不是整个页面）
        comment_container_selectors = [
            "div[class*='comment-container']",
            "div[class*='comments-container']",
            "div[class*='commentContainer']",
            "div[class*='CommentsContainer']",
            "div[class*='note-scroller']",
            "div[class*='content-container']",
            "div[class*='detail-content']",
            "div[class*='note-content']",
            "div[class*='interaction-container']",
        ]

        scroll_container = None
        for selector in comment_container_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    if el.size.get("height", 0) > 100:
                        scroll_container = el
                        logger.info(f"[xhs.comments.debug] 找到评论滚动容器: {selector}")
                        break
                if scroll_container:
                    break
            except Exception:
                continue

        # 滚动加载评论
        for scroll_round in range(5):
            try:
                if scroll_container:
                    driver.execute_script(
                        "arguments[0].scrollTop += 500;", scroll_container
                    )
                else:
                    driver.execute_script("window.scrollBy(0, 400);")
                time.sleep(1)
            except Exception:
                break

        # 调试：打印弹窗中所有包含 comment 的元素
        try:
            all_comment_related = driver.find_elements(
                By.CSS_SELECTOR,
                "[class*='comment'], [class*='Comment']"
            )
            logger.info(f"[xhs.comments.debug] 页面中包含 comment 的元素数: {len(all_comment_related)}")
            for debug_idx, debug_el in enumerate(all_comment_related[:5]):
                class_attr = debug_el.get_attribute("class") or ""
                tag_name = debug_el.tag_name
                text_preview = debug_el.text[:80].replace("\n", " ") if debug_el.text else ""
                logger.info(f"[xhs.comments.debug]   [{debug_idx}] <{tag_name} class='{class_attr}'> text='{text_preview}'")
        except Exception as debug_error:
            logger.warning(f"[xhs.comments.debug] 调试信息获取失败: {debug_error}")

        # 提取评论 - 扩展选择器列表
        comment_selectors = [
            "div[class*='comment-item']",
            "div[class*='commentItem']",
            "div[class*='CommentItem']",
            "div[class*='comment-inner']",
            "div[class*='commentInner']",
            "div[class*='note-detail'] div[class*='comment-item']",
            "div[class*='detail-modal'] div[class*='comment']",
            "div[class*='note-container'] div[class*='CommentItem']",
            "div[class*='comment'] div[class*='content']",
            "li[class*='comment']",
        ]

        comment_elements = []
        matched_selector = ""
        for selector in comment_selectors:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, selector)
                if found:
                    comment_elements = found
                    matched_selector = selector
                    logger.info(f"[xhs.comments.debug] 匹配到评论选择器: {selector}, 数量: {len(found)}")
                    break
            except Exception:
                continue

        if not comment_elements:
            logger.warning("[xhs.comments.debug] 所有评论选择器均未匹配到元素")
            # 尝试从页面源码提取评论
            comments = _extract_comments_from_source(driver, max_comments)
            if comments:
                logger.info(f"[xhs.comments.debug] 从页面源码提取到 {len(comments)} 条评论")
            return comments

        for element in comment_elements[:max_comments * 2]:
            try:
                full_text = element.text.strip()
                if not full_text:
                    continue
                
                lines = [line.strip() for line in full_text.split("\n") if line.strip()]
                if len(lines) < 2:
                    continue

                author = lines[0]
                content = lines[1] if len(lines) > 1 else ""

                like_count = 0
                for line in lines[2:]:
                    parsed = _parse_count(line)
                    if parsed > 0:
                        like_count = parsed
                        break

                reply_count = 0
                for line in lines:
                    reply_match = re.search(r"(\d+)\s*条回复", line)
                    if not reply_match:
                        reply_match = re.search(r"共\s*(\d+)\s*条", line)
                    if reply_match:
                        reply_count = int(reply_match.group(1))
                        break

                if content and author:
                    comments.append({
                        "author": author,
                        "content": content,
                        "like_count": like_count,
                        "reply_count": reply_count,
                    })
            except Exception:
                continue

    except Exception as e:
        logger.error(f"[xhs.modal] 提取弹窗评论失败: {e}")

    return comments


def _navigate_to_detail_page(driver, note_id: str) -> bool:
    """从搜索结果页点击笔记封面链接进入详情页
    
    小红书搜索结果页的卡片结构：<section class="note-item">
      - 隐藏 <a href="/explore/{note_id}"> (size=0, 不可点击，点击会被 sec 网关拦截)
      - 可见 <a class="cover mask ld" href="/search_result/{note_id}?xsec_token=..."> (封面图，可点击)
      - <a class="title"> (标题)
    
    必须点击带 xsec_token 的 a.cover 封面链接，才能绕过 sec 网关成功进入详情页。
    driver.get() 直接导航会被拦截到 404（error_code=300031）。
    """
    from selenium.webdriver.common.action_chains import ActionChains

    logger.info(f"[xhs.navigate] 点击封面链接进入详情页: {note_id}")
    try:
        # 随机延迟 2~5 秒，模拟真实用户浏览间隔
        delay = random.uniform(2, 5)
        logger.info(f"[xhs.navigate] 等待 {delay:.1f}s 模拟用户行为...")
        time.sleep(delay)

        # 在搜索结果页找到包含该 note_id 的 section.note-item
        # 小红书搜索结果页是瀑布流懒加载，返回后目标卡片可能不在当前 DOM 中
        # 需要逐步滚动页面，让目标卡片加载出来
        cover_link = None
        max_scroll_attempts = 10
        for scroll_attempt in range(max_scroll_attempts):
            try:
                note_sections = driver.find_elements(By.CSS_SELECTOR, "section.note-item")
                for section in note_sections:
                    inner_links = section.find_elements(By.CSS_SELECTOR, "a")
                    has_note_id = False
                    for link in inner_links:
                        href = link.get_attribute("href") or ""
                        if note_id in href:
                            has_note_id = True
                            break
                    if has_note_id:
                        cover_candidates = section.find_elements(By.CSS_SELECTOR, "a.cover, a[class*='cover']")
                        for candidate in cover_candidates:
                            if candidate.is_displayed() and candidate.size.get("height", 0) > 0:
                                cover_link = candidate
                                break
                        if not cover_link:
                            for link in inner_links:
                                if link.is_displayed() and link.size.get("height", 0) > 50:
                                    cover_link = link
                                    break
                        break
            except Exception as find_err:
                logger.warning(f"[xhs.navigate] 查找卡片元素失败: {find_err}")

            if cover_link:
                break

            # 未找到，滚动页面加载更多卡片
            if scroll_attempt < max_scroll_attempts - 1:
                driver.execute_script(f"window.scrollBy(0, {random.randint(400, 700)});")
                time.sleep(random.uniform(1.0, 2.0))

        if not cover_link:
            logger.warning(f"[xhs.navigate] 滚动 {max_scroll_attempts} 次后仍未找到笔记 {note_id} 的封面链接")
            return False

        cover_href = cover_link.get_attribute("href") or ""
        logger.info(f"[xhs.navigate] 找到封面链接: {cover_href[:80]}...")

        # 滚动到元素可见位置（居中显示）
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            cover_link
        )
        time.sleep(random.uniform(0.5, 1.0))

        # 记录点击前的 URL 和窗口句柄
        original_url = driver.current_url
        original_handles = set(driver.window_handles)

        # 模拟鼠标移动到封面上，短暂停留后点击
        ActionChains(driver).move_to_element(cover_link).pause(random.uniform(0.3, 0.8)).click().perform()
        time.sleep(4)

        # 检查是否打开了新标签页
        new_handles = set(driver.window_handles) - original_handles
        if new_handles:
            new_handle = new_handles.pop()
            driver.switch_to.window(new_handle)
            logger.info(f"[xhs.navigate] 点击后打开了新标签页，已切换")
            time.sleep(2)

        current_url = driver.current_url
        page_title = driver.title or ""

        # 检查是否被拦截
        if "/404" in current_url or "error_code" in current_url:
            logger.warning(f"[xhs.navigate] 被重定向到 404: {current_url}")
            return False

        if "验证" in page_title or "captcha" in current_url.lower():
            logger.warning(f"[xhs.navigate] 遇到验证码页面，等待 10s...")
            time.sleep(10)
            current_url = driver.current_url
            if "/404" in current_url or "captcha" in current_url.lower():
                return False

        # 检查是否成功到达详情页
        if note_id in current_url or "explore" in current_url:
            logger.info(f"[xhs.navigate] 成功到达详情页: {current_url}")
        elif current_url != original_url:
            logger.info(f"[xhs.navigate] 页面已跳转: {current_url}")
        else:
            logger.info(f"[xhs.navigate] URL 未变化，可能是弹窗模式")

        # 等待详情页内容加载，模拟用户滚动浏览
        time.sleep(2)
        for _ in range(3):
            driver.execute_script(f"window.scrollBy(0, {random.randint(200, 400)});")
            time.sleep(random.uniform(0.5, 1.5))

        return True
    except Exception as navigate_error:
        logger.error(f"[xhs.navigate] 点击导航失败: {navigate_error}")
        return False


def find_and_click_next_note(driver, processed_note_ids: set, max_scroll: int = 15) -> Optional[str]:
    """在搜索结果页上找到下一个未处理的笔记卡片，点击进入详情页
    
    按页面上卡片的出现顺序逐个处理，而不是按排序后的列表查找特定 note_id。
    这样可以避免瀑布流返回后找不到之前滚动加载的卡片的问题。
    
    Returns:
        成功点击的 note_id，或 None（没有更多未处理的卡片）
    """
    from selenium.webdriver.common.action_chains import ActionChains
    import re

    for scroll_attempt in range(max_scroll):
        try:
            note_sections = driver.find_elements(By.CSS_SELECTOR, "section.note-item")
            for section in note_sections:
                # 从该 section 的链接中提取 note_id
                section_note_id = None
                inner_links = section.find_elements(By.CSS_SELECTOR, "a")
                for link in inner_links:
                    href = link.get_attribute("href") or ""
                    # 从 href 中提取 note_id（/explore/{id} 或 /search_result/{id}?...）
                    match = re.search(r'/(?:explore|search_result)/([a-f0-9]{24})', href)
                    if match:
                        section_note_id = match.group(1)
                        break

                if not section_note_id or section_note_id in processed_note_ids:
                    continue

                # 找到未处理的卡片，查找可见的 a.cover 封面链接
                cover_link = None
                cover_candidates = section.find_elements(By.CSS_SELECTOR, "a.cover, a[class*='cover']")
                for candidate in cover_candidates:
                    if candidate.is_displayed() and candidate.size.get("height", 0) > 0:
                        cover_link = candidate
                        break
                if not cover_link:
                    for link in inner_links:
                        if link.is_displayed() and link.size.get("height", 0) > 50:
                            cover_link = link
                            break

                if not cover_link:
                    continue

                # 找到可点击的封面链接，执行点击
                cover_href = cover_link.get_attribute("href") or ""
                logger.info(f"[xhs.navigate] 找到未处理笔记 {section_note_id}，封面链接: {cover_href[:80]}...")

                # 随机延迟模拟用户行为
                time.sleep(random.uniform(2, 4))

                # 滚动到元素可见位置
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                    cover_link
                )
                time.sleep(random.uniform(0.5, 1.0))

                # 记录点击前状态
                original_url = driver.current_url
                original_handles = set(driver.window_handles)

                # 模拟点击
                ActionChains(driver).move_to_element(cover_link).pause(random.uniform(0.3, 0.8)).click().perform()
                time.sleep(4)

                # 检查新标签页
                new_handles = set(driver.window_handles) - original_handles
                if new_handles:
                    driver.switch_to.window(new_handles.pop())
                    logger.info(f"[xhs.navigate] 点击后打开了新标签页，已切换")
                    time.sleep(2)

                current_url = driver.current_url
                page_title = driver.title or ""

                # 检查是否被拦截
                if "/404" in current_url or "error_code" in current_url:
                    logger.warning(f"[xhs.navigate] 被重定向到 404: {current_url}")
                    processed_note_ids.add(section_note_id)
                    return None

                if "验证" in page_title or "captcha" in current_url.lower():
                    logger.warning(f"[xhs.navigate] 遇到验证码页面，等待 10s...")
                    time.sleep(10)

                # 成功到达详情页
                logger.info(f"[xhs.navigate] 成功到达详情页: {current_url}")

                # 等待内容加载，模拟滚动
                time.sleep(2)
                for _ in range(3):
                    driver.execute_script(f"window.scrollBy(0, {random.randint(200, 400)});")
                    time.sleep(random.uniform(0.5, 1.5))

                return section_note_id

        except Exception as find_err:
            logger.warning(f"[xhs.navigate] 查找卡片失败: {find_err}")

        # 滚动加载更多卡片
        driver.execute_script(f"window.scrollBy(0, {random.randint(400, 700)});")
        time.sleep(random.uniform(1.0, 2.0))

    logger.info(f"[xhs.navigate] 滚动 {max_scroll} 次后没有更多未处理的卡片")
    return None


def _go_back_to_search(driver, search_url: str):
    """从详情页返回搜索结果页
    
    优先关闭新标签页回到原标签页，否则用 driver.back() 返回。
    返回后重新滚动加载搜索结果，确保后续笔记卡片可见。
    """
    try:
        handles = driver.window_handles
        if len(handles) > 1:
            # 有多个标签页：关闭当前标签页，切回第一个（搜索结果页）
            try:
                driver.close()
            except Exception as close_err:
                logger.warning(f"[xhs.navigate] close() 失败: {close_err}，尝试切回原窗口")
            # 无论 close 是否成功，都切回第一个可用窗口
            remaining_handles = driver.window_handles
            if remaining_handles:
                driver.switch_to.window(remaining_handles[0])
                logger.info("[xhs.navigate] 关闭详情页标签，回到搜索结果页")
            else:
                # 所有窗口都关了，重新打开搜索页
                logger.warning("[xhs.navigate] 所有窗口已关闭，无法恢复")
                return
            time.sleep(1)

            # 切回后检查是否在搜索结果页
            current_url = driver.current_url
            if "search_result" not in current_url:
                logger.warning(f"[xhs.navigate] 切回的窗口不是搜索页: {current_url}，重新导航")
                driver.get(search_url)
                time.sleep(4)
        else:
            # 只有一个标签页，用 back() 返回
            driver.back()
            time.sleep(3)

            # 检查是否成功返回搜索结果页
            current_url = driver.current_url
            if "search_result" not in current_url:
                logger.warning(f"[xhs.navigate] back() 未回到搜索页，当前: {current_url}，重新导航")
                driver.get(search_url)
                time.sleep(4)

        # 返回后重新滚动加载搜索结果，确保后续笔记卡片可见
        for _ in range(5):
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(1)

        logger.info(f"[xhs.navigate] 已返回搜索结果页: {driver.current_url}")
    except Exception as back_error:
        logger.error(f"[xhs.navigate] 返回搜索页失败: {back_error}")
        # 兜底：切回任意可用窗口，然后导航到搜索页
        try:
            remaining = driver.window_handles
            if remaining:
                driver.switch_to.window(remaining[0])
            driver.get(search_url)
            time.sleep(4)
            for _ in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
        except Exception:
            pass


def _extract_content_from_detail_page(driver) -> Dict[str, Any]:
    """从笔记详情页提取正文内容（标题、正文、作者、互动数据）"""
    result = {
        "title": "",
        "content": "",
        "author": "",
        "like_count": 0,
        "collect_count": 0,
        "comment_count": 0,
        "share_count": 0,
        "is_video": False,
        "content_type": "image_text",
    }

    # 方案1: 从 __INITIAL_STATE__ SSR 数据提取（最可靠）
    try:
        page_source = driver.page_source
        ssr_pattern = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(.+?)\s*</script>', re.DOTALL)
        match = ssr_pattern.search(page_source)
        if match:
            raw_json = match.group(1)
            clean_json = re.sub(r'\bundefined\b', 'null', raw_json)
            state_data = json.loads(clean_json)

            # 从 note.noteDetailMap 或 note.noteDetail 提取
            note_detail = None
            note_data = state_data.get("note", {})

            # 尝试 noteDetailMap（新版结构）
            detail_map = note_data.get("noteDetailMap", {})
            if detail_map:
                for key, val in detail_map.items():
                    if isinstance(val, dict):
                        note_detail = val.get("note", val)
                        break

            # 尝试 noteDetail（旧版结构）
            if not note_detail:
                note_detail = note_data.get("noteDetail", {}).get("note", {})
            if not note_detail:
                note_detail = note_data.get("detail", {}).get("note", {})

            if note_detail and isinstance(note_detail, dict):
                result["title"] = note_detail.get("title", "") or note_detail.get("displayTitle", "")
                result["content"] = note_detail.get("desc", "")
                result["author"] = note_detail.get("user", {}).get("nickname", "") if isinstance(note_detail.get("user"), dict) else ""

                interact_info = note_detail.get("interactInfo", {})
                if isinstance(interact_info, dict):
                    result["like_count"] = _parse_count(str(interact_info.get("likedCount", "0")))
                    result["collect_count"] = _parse_count(str(interact_info.get("collectedCount", "0")))
                    result["comment_count"] = _parse_count(str(interact_info.get("commentCount", "0")))
                    result["share_count"] = _parse_count(str(interact_info.get("shareCount", "0")))

                note_type = note_detail.get("type", "")
                result["is_video"] = note_type == "video"
                result["content_type"] = "video" if result["is_video"] else "image_text"

                # 提取标签
                tag_list = note_detail.get("tagList", [])
                if isinstance(tag_list, list):
                    tags = [t.get("name", "") for t in tag_list if isinstance(t, dict) and t.get("name")]
                    if tags:
                        result["tags"] = tags

                logger.info(f"[xhs.detail] SSR 提取成功: title='{result['title'][:30]}...', likes={result['like_count']}")
                return result
    except json.JSONDecodeError as json_err:
        logger.warning(f"[xhs.detail] SSR JSON 解析失败: {json_err}")
    except Exception as ssr_err:
        logger.warning(f"[xhs.detail] SSR 提取失败: {ssr_err}")

    # 方案2: 从 DOM 提取（使用已验证的精确选择器）
    try:
        # 标题（已验证: #detail-title 直接匹配）
        for title_selector in [
            "#detail-title",
            "div[class*='title'] span",
        ]:
            try:
                title_el = driver.find_element(By.CSS_SELECTOR, title_selector)
                title = title_el.text.strip()
                if title:
                    result["title"] = title
                    break
            except Exception:
                continue

        # 正文（已验证: #detail-desc 直接匹配）
        for content_selector in [
            "#detail-desc",
            "div.desc",
        ]:
            try:
                content_el = driver.find_element(By.CSS_SELECTOR, content_selector)
                content = content_el.text.strip()
                if content:
                    result["content"] = content
                    break
            except Exception:
                continue

        # 作者（从 interaction-container 内的作者名提取）
        for author_selector in [
            "div.interaction-container a[class*='name'] span",
            "a[class*='name'] span",
            "span[class*='username']",
            "div[class*='author-wrapper'] span[class*='name']",
        ]:
            try:
                author_el = driver.find_element(By.CSS_SELECTOR, author_selector)
                author = author_el.text.strip()
                if author:
                    result["author"] = author
                    break
            except Exception:
                continue

        # 互动数据（已验证: 底部 engage-bar 内的 like/collect/chat wrapper）
        try:
            # 底部互动栏的点赞数（engage-bar 内第一个 like-wrapper）
            engage_bar = driver.find_element(By.CSS_SELECTOR, "div.engage-bar-container, div[class*='engage-bar-container']")
            like_el = engage_bar.find_element(By.CSS_SELECTOR, "span.like-wrapper span.count")
            result["like_count"] = _parse_count(like_el.text.strip())
            collect_el = engage_bar.find_element(By.CSS_SELECTOR, "span.collect-wrapper span.count")
            result["collect_count"] = _parse_count(collect_el.text.strip())
            chat_el = engage_bar.find_element(By.CSS_SELECTOR, "span.chat-wrapper span.count")
            result["comment_count"] = _parse_count(chat_el.text.strip())
        except Exception:
            # 备选：使用通用选择器
            interaction_data = _extract_interaction_data(driver)
            result.update(interaction_data)

        if result["title"] or result["content"]:
            logger.info(f"[xhs.detail] DOM 提取成功: title='{result['title'][:30]}...'")

    except Exception as dom_err:
        logger.error(f"[xhs.detail] DOM 提取失败: {dom_err}")

    return result


def extract_video_src_from_detail_page(driver) -> Optional[str]:
    """从当前详情页 DOM 中提取视频播放地址（不创建新浏览器）

    提取策略（按优先级）：
    1. SSR 数据中的 video.consumer.originVideoKey
    2. <video> 标签的 src 属性
    3. <video> 内 <source> 标签的 src 属性
    4. JS 执行获取 video.src
    5. 页面源码正则匹配 sns-video CDN 地址
    """
    # 方案1: 从 SSR 数据提取视频地址（最可靠）
    try:
        page_source = driver.page_source
        ssr_pattern = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(.+?)\s*</script>', re.DOTALL)
        match = ssr_pattern.search(page_source)
        if match:
            raw_json = match.group(1)
            clean_json = re.sub(r'\bundefined\b', 'null', raw_json)
            state_data = json.loads(clean_json)
            note_data = state_data.get("note", {})
            detail_map = note_data.get("noteDetailMap", {})
            for key, val in detail_map.items():
                if isinstance(val, dict):
                    note_detail = val.get("note", val)
                    video_info = note_detail.get("video", {})
                    if isinstance(video_info, dict):
                        consumer = video_info.get("consumer", {})
                        if isinstance(consumer, dict):
                            origin_key = consumer.get("originVideoKey", "")
                            if origin_key:
                                video_url = f"https://sns-video-bd.xhscdn.com/{origin_key}"
                                logger.info(f"[xhs.video] SSR 提取视频地址: {video_url[:80]}...")
                                return video_url
                    break
    except Exception as ssr_err:
        logger.warning(f"[xhs.video] SSR 提取视频地址失败: {ssr_err}")

    # 方案2: 从 <video> 标签获取 src
    try:
        video_elements = driver.find_elements(By.TAG_NAME, "video")
        for video_el in video_elements:
            src = video_el.get_attribute("src")
            if src and src.startswith("http") and "blob:" not in src:
                logger.info(f"[xhs.video] video.src 提取成功: {src[:80]}...")
                return src
    except Exception:
        pass

    # 方案3: 从 <source> 子标签获取
    try:
        source_elements = driver.find_elements(By.CSS_SELECTOR, "video source")
        for source_el in source_elements:
            src = source_el.get_attribute("src")
            if src and src.startswith("http"):
                logger.info(f"[xhs.video] source.src 提取成功: {src[:80]}...")
                return src
    except Exception:
        pass

    # 方案4: 通过 JS 获取
    try:
        video_src = driver.execute_script("""
            var videos = document.querySelectorAll('video');
            for (var v of videos) {
                if (v.src && v.src.startsWith('http') && !v.src.includes('blob:')) return v.src;
                var sources = v.querySelectorAll('source');
                for (var s of sources) {
                    if (s.src && s.src.startsWith('http')) return s.src;
                }
            }
            return null;
        """)
        if video_src:
            logger.info(f"[xhs.video] JS 提取成功: {video_src[:80]}...")
            return video_src
    except Exception:
        pass

    # 方案5: 从页面源码正则提取 CDN 地址
    try:
        page_source = driver.page_source
        cdn_patterns = [
            r'"originVideoKey"\s*:\s*"([^"]+)"',
            r'"url"\s*:\s*"(https?://sns-video[^"]+)"',
            r'(https://sns-video-[a-z0-9-]+\.xhscdn\.com/[^"\'\\\s]+)',
        ]
        for pattern in cdn_patterns:
            cdn_match = re.search(pattern, page_source)
            if cdn_match:
                url = cdn_match.group(1)
                if not url.startswith("http"):
                    url = f"https://sns-video-bd.xhscdn.com/{url}"
                logger.info(f"[xhs.video] 正则提取成功: {url[:80]}...")
                return url
    except Exception:
        pass

    logger.warning("[xhs.video] 未能从详情页提取到视频地址")
    return None


def _extract_comments_from_detail_page(driver, max_comments: int = 30) -> List[Dict[str, Any]]:
    """从笔记详情页提取评论"""
    comments = []

    try:
        # 先滚动到评论区
        for _ in range(5):
            driver.execute_script(f"window.scrollBy(0, {random.randint(300, 500)});")
            time.sleep(random.uniform(0.8, 1.5))

        # 方案1: 从 SSR 数据提取评论
        try:
            page_source = driver.page_source
            ssr_pattern = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(.+?)\s*</script>', re.DOTALL)
            match = ssr_pattern.search(page_source)
            if match:
                raw_json = match.group(1)
                clean_json = re.sub(r'\bundefined\b', 'null', raw_json)
                state_data = json.loads(clean_json)

                # 尝试从 comment 路径提取
                comment_data = state_data.get("comment", {})
                comments_list = comment_data.get("comments", [])
                if not comments_list:
                    comments_list = comment_data.get("commentList", [])
                if not comments_list:
                    # 尝试从 commentsMap 提取
                    comments_map = comment_data.get("commentsMap", {})
                    for key, val in comments_map.items():
                        if isinstance(val, list):
                            comments_list = val
                            break
                        elif isinstance(val, dict) and val.get("comments"):
                            comments_list = val["comments"]
                            break

                if isinstance(comments_list, list):
                    for comment_item in comments_list:
                        if not isinstance(comment_item, dict):
                            continue
                        content = comment_item.get("content", "")
                        if not content:
                            continue
                        user_info = comment_item.get("userInfo", {})
                        if not isinstance(user_info, dict):
                            user_info = {}
                        author = user_info.get("nickname", "")
                        like_count = _parse_count(str(comment_item.get("likeCount", "0")))
                        sub_comment_count = comment_item.get("subCommentCount", 0)
                        if isinstance(sub_comment_count, str):
                            sub_comment_count = _parse_count(sub_comment_count)

                        comments.append({
                            "author": author,
                            "content": content,
                            "like_count": like_count,
                            "reply_count": sub_comment_count,
                        })

                if comments:
                    logger.info(f"[xhs.comments.detail] SSR 提取到 {len(comments)} 条评论")
                    comments.sort(key=lambda c: c.get("like_count", 0), reverse=True)
                    return comments[:max_comments]
        except Exception as ssr_err:
            logger.warning(f"[xhs.comments.detail] SSR 评论提取失败: {ssr_err}")

        # 方案2: 从 DOM 提取评论
        comment_selectors = [
            "div[class*='comment-item']",
            "div[class*='commentItem']",
            "div[class*='CommentItem']",
            "div[class*='comment-inner']",
            "li[class*='comment']",
        ]

        comment_elements = []
        for selector in comment_selectors:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, selector)
                if found:
                    comment_elements = found
                    logger.info(f"[xhs.comments.detail] DOM 匹配到评论选择器: {selector}, 数量: {len(found)}")
                    break
            except Exception:
                continue

        for element in comment_elements[:max_comments * 2]:
            try:
                full_text = element.text.strip()
                if not full_text:
                    continue
                lines = [line.strip() for line in full_text.split("\n") if line.strip()]
                if len(lines) < 2:
                    continue

                author = lines[0]
                content = lines[1] if len(lines) > 1 else ""

                like_count = 0
                for line in lines[2:]:
                    parsed = _parse_count(line)
                    if parsed > 0:
                        like_count = parsed
                        break

                reply_count = 0
                for line in lines:
                    reply_match = re.search(r"(\d+)\s*条回复", line)
                    if not reply_match:
                        reply_match = re.search(r"共\s*(\d+)\s*条", line)
                    if reply_match:
                        reply_count = int(reply_match.group(1))
                        break

                if content and author:
                    comments.append({
                        "author": author,
                        "content": content,
                        "like_count": like_count,
                        "reply_count": reply_count,
                    })
            except Exception:
                continue

        if comments:
            logger.info(f"[xhs.comments.detail] DOM 提取到 {len(comments)} 条评论")

        # 方案3: 从页面源码正则提取
        if not comments:
            comments = _extract_comments_from_source(driver, max_comments)
            if comments:
                logger.info(f"[xhs.comments.detail] 源码正则提取到 {len(comments)} 条评论")

    except Exception as extract_err:
        logger.error(f"[xhs.comments.detail] 提取评论失败: {extract_err}")

    comments.sort(key=lambda c: c.get("like_count", 0), reverse=True)
    return comments[:max_comments]


def fetch_note_content(note_url: str, cookie_string: str = "", driver=None, note_id: str = "") -> Dict[str, Any]:
    """获取单条笔记的完整内容（标题、正文、图片、数据、是否视频）
    
    使用 Selenium 直接导航到详情页提取数据。
    """
    logger.info(f"[xhs.note] 获取笔记内容: {note_url}")
    own_driver = driver is None
    try:
        if own_driver:
            driver = _create_browser(cookie_string=cookie_string)
        
        result = {
            "title": "",
            "content": "",
            "author": "",
            "like_count": 0,
            "collect_count": 0,
            "comment_count": 0,
            "share_count": 0,
            "is_video": False,
            "content_type": "image_text",
        }

        # 提取 note_id
        if not note_id:
            note_id_match = re.search(r"/explore/([a-f0-9]+)", note_url)
            if note_id_match:
                note_id = note_id_match.group(1)

        if note_id and _navigate_to_detail_page(driver, note_id):
            result = _extract_content_from_detail_page(driver)
        else:
            logger.warning(f"[xhs.note] 无法导航到详情页，返回基础数据")

        if note_id:
            result["note_id"] = note_id
            result["url"] = note_url

        return result

    except Exception as note_error:
        logger.error(f"[xhs.note] 获取失败: {note_error}")
        return {"error": str(note_error)}
    finally:
        if own_driver and driver:
            driver.quit()


def _extract_interaction_data(driver) -> Dict[str, int]:
    """提取笔记的互动数据（点赞、收藏、评论、分享）"""
    data = {"like_count": 0, "collect_count": 0, "comment_count": 0, "share_count": 0}

    # 尝试从互动栏提取
    interaction_selectors = [
        ("like_count", ["span.like-wrapper span.count", "span[class*='like'] span[class*='count']"]),
        ("collect_count", ["span.collect-wrapper span.count", "span[class*='collect'] span[class*='count']"]),
        ("comment_count", ["span.chat-wrapper span.count", "span[class*='chat'] span[class*='count']"]),
        ("share_count", ["span.share-wrapper span.count", "span[class*='share'] span[class*='count']"]),
    ]

    for field_name, selectors in interaction_selectors:
        for selector in selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                data[field_name] = _parse_count(el.text)
                if data[field_name] > 0:
                    break
            except Exception:
                continue

    # 如果上面没提取到，尝试从页面源码提取
    if all(v == 0 for v in data.values()):
        try:
            page_source = driver.page_source
            for field_name, pattern in [
                ("like_count", r'"likedCount"\s*:\s*"?(\d+)"?'),
                ("collect_count", r'"collectedCount"\s*:\s*"?(\d+)"?'),
                ("comment_count", r'"commentCount"\s*:\s*"?(\d+)"?'),
                ("share_count", r'"shareCount"\s*:\s*"?(\d+)"?'),
            ]:
                match = re.search(pattern, page_source)
                if match:
                    data[field_name] = int(match.group(1))
        except Exception:
            pass

    return data


def _extract_note_from_source(driver) -> Optional[Dict[str, Any]]:
    """从页面源码提取笔记内容"""
    try:
        page_source = driver.page_source

        result = {}

        title_match = re.search(r'"title"\s*:\s*"([^"]*)"', page_source)
        if title_match:
            result["title"] = title_match.group(1).encode().decode("unicode_escape", errors="ignore")

        desc_match = re.search(r'"desc"\s*:\s*"([^"]*)"', page_source)
        if desc_match:
            result["content"] = desc_match.group(1).encode().decode("unicode_escape", errors="ignore")

        author_match = re.search(r'"nickname"\s*:\s*"([^"]*)"', page_source)
        if author_match:
            result["author"] = author_match.group(1).encode().decode("unicode_escape", errors="ignore")

        type_match = re.search(r'"type"\s*:\s*"(video|normal)"', page_source)
        if type_match:
            result["is_video"] = type_match.group(1) == "video"
            result["content_type"] = "video" if result["is_video"] else "image_text"

        return result if result else None
    except Exception:
        return None


def fetch_comments(note_url: str, cookie_string: str = "", max_comments: int = 30, driver=None, note_id: str = "", search_url: str = "") -> List[Dict[str, Any]]:
    """抓取小红书笔记的高赞一级评论
    
    使用 Selenium 直接导航到详情页提取评论。
    如果当前已在详情页，直接提取；否则先导航到详情页。
    """
    logger.info(f"[xhs.comments] 抓取评论: {note_url}")
    own_driver = driver is None
    try:
        if own_driver:
            driver = _create_browser(cookie_string=cookie_string)
        
        comments = []

        # 提取 note_id
        if not note_id:
            note_id_match = re.search(r"/explore/([a-f0-9]+)", note_url)
            if note_id_match:
                note_id = note_id_match.group(1)

        if note_id and driver:
            current_url = driver.current_url
            
            # 检查当前是否已在该笔记的详情页
            already_on_detail = note_id in current_url and "explore" in current_url
            
            if already_on_detail:
                logger.info(f"[xhs.comments] 当前已在笔记详情页，直接提取评论")
                comments = _extract_comments_from_detail_page(driver, max_comments)
            else:
                # 导航到详情页
                if _navigate_to_detail_page(driver, note_id):
                    comments = _extract_comments_from_detail_page(driver, max_comments)
                else:
                    logger.warning(f"[xhs.comments] 无法导航到笔记 {note_id} 的详情页")

        if not comments:
            logger.warning(f"[xhs.comments] 未能获取到评论")

        comments.sort(key=lambda c: c.get("like_count", 0), reverse=True)
        result = comments[:max_comments]
        logger.info(f"[xhs.comments] 获取 {len(result)} 条高赞评论")
        return result

    except Exception as comment_error:
        logger.error(f"[xhs.comments] 抓取失败: {comment_error}")
        return []
    finally:
        if own_driver and driver:
            driver.quit()


def _extract_comments_from_dom(driver, max_comments: int) -> List[Dict[str, Any]]:
    """从 DOM 提取评论"""
    comments = []

    comment_selectors = [
        "div.comment-item",
        "div[class*='comment-item']",
        "div[class*='commentItem']",
        "div[class*='CommentItem']",
    ]

    comment_elements = []
    for selector in comment_selectors:
        comment_elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if comment_elements:
            break

    for element in comment_elements[:max_comments * 2]:
        try:
            full_text = element.text.strip()
            if not full_text:
                continue
            lines = [line.strip() for line in full_text.split("\n") if line.strip()]
            if len(lines) < 2:
                continue

            author = lines[0]
            content = lines[1] if len(lines) > 1 else ""

            like_count = 0
            for line in lines[2:]:
                parsed = _parse_count(line)
                if parsed > 0:
                    like_count = parsed
                    break

            reply_count = 0
            for line in lines:
                reply_match = re.search(r"(\d+)\s*条回复", line)
                if not reply_match:
                    reply_match = re.search(r"共\s*(\d+)\s*条", line)
                if reply_match:
                    reply_count = int(reply_match.group(1))
                    break

            if content and author:
                comments.append({
                    "author": author,
                    "content": content,
                    "like_count": like_count,
                    "reply_count": reply_count,
                })
        except Exception:
            continue

    return comments


def _extract_comments_from_source(driver, max_comments: int) -> List[Dict[str, Any]]:
    """从页面源码正则提取评论"""
    comments = []
    try:
        page_source = driver.page_source

        # 尝试匹配评论 JSON 数据
        comment_pattern = re.compile(
            r'"content"\s*:\s*"([^"]{2,500})".*?"likeCount"\s*:\s*"?(\d+)"?',
            re.DOTALL,
        )
        matches = comment_pattern.findall(page_source)
        for content_text, like_count in matches[:max_comments]:
            decoded_content = content_text.encode().decode("unicode_escape", errors="ignore")
            comments.append({
                "author": "",
                "content": decoded_content,
                "like_count": int(like_count),
                "reply_count": 0,
            })
    except Exception:
        pass
    return comments

def search_and_collect(keywords: str, page_size: int = 10, max_comments: int = 30, cookie_string: str = "") -> Dict[str, Any]:
    """整合搜索+详情+评论的完整流程
    
    流程：
    1. 在搜索结果页搜索关键词，提取笔记列表
    2. 逐个用 Selenium 点击笔记卡片进入详情页（模拟真实用户操作）
    3. 从详情页 SSR 数据和 DOM 提取正文内容和评论
    4. 返回搜索结果页继续处理下一个笔记
    5. 加随机延迟模拟真实用户行为，降低被反爬拦截的风险
    """
    logger.info(f"[xhs.collect] 开始搜索并收集完整数据: keywords={keywords}, page_size={page_size}")
    driver = None
    try:
        driver = _create_browser(cookie_string=cookie_string)
        search_url = XHS_SEARCH_URL.format(keyword=keywords)
        driver.get(search_url)
        time.sleep(5)

        # 滚动加载更多
        for _ in range(8):
            driver.execute_script("window.scrollBy(0, 600);")
            time.sleep(1.5)

        # 从 DOM 提取笔记列表
        items = _extract_notes_from_dom(driver, page_size * 3)

        # 从 SSR 数据提取详细信息
        ssr_details = _extract_ssr_data(driver)
        if ssr_details:
            for item in items:
                note_id = item.get("note_id")
                if note_id and note_id in ssr_details:
                    item["detail"] = ssr_details[note_id]
                    detail = ssr_details[note_id]
                    if detail.get("title") and not item.get("title"):
                        item["title"] = detail["title"]
                    if detail.get("displayTitle") and not item.get("title"):
                        item["title"] = detail["displayTitle"]
                    if detail.get("nickname") and not item.get("author"):
                        item["author"] = detail["nickname"]
                    if detail.get("likedCount") and item.get("like_count") == 0:
                        item["like_count"] = detail["likedCount"]
                    if detail.get("type"):
                        item["is_video"] = detail["type"] == "video"
                        item["content_type"] = "video" if item["is_video"] else "image_text"

        # 按点赞排序
        items.sort(key=lambda n: n.get("like_count", 0), reverse=True)
        items = items[:page_size]

        # 逐个导航到笔记详情页，提取正文和评论
        consecutive_failures = 0
        for idx, item in enumerate(items):
            note_id = item.get("note_id")
            if not note_id:
                logger.warning(f"[xhs.collect] 笔记 {idx + 1} 缺少 note_id，跳过")
                continue

            # 如果连续失败 3 次，说明可能被反爬拦截，停止继续访问
            if consecutive_failures >= 3:
                logger.warning(f"[xhs.collect] 连续 {consecutive_failures} 次导航失败，停止后续笔记的详情抓取")
                item["content"] = ""
                item["comments"] = []
                continue

            logger.info(f"[xhs.collect] 正在处理笔记 {idx + 1}/{len(items)}: {note_id}")

            # 直接导航到详情页
            if _navigate_to_detail_page(driver, note_id):
                consecutive_failures = 0

                # 从详情页提取正文内容
                detail_content = _extract_content_from_detail_page(driver)
                item["content"] = detail_content.get("content", "")
                item["full_content"] = detail_content

                # 更新互动数据（详情页的数据比搜索结果页更准确）
                if detail_content.get("like_count", 0) > 0:
                    item["like_count"] = detail_content["like_count"]
                if detail_content.get("collect_count", 0) > 0:
                    item["collect_count"] = detail_content["collect_count"]
                if detail_content.get("comment_count", 0) > 0:
                    item["comment_count"] = detail_content["comment_count"]
                if detail_content.get("title") and not item.get("title"):
                    item["title"] = detail_content["title"]
                if detail_content.get("author") and not item.get("author"):
                    item["author"] = detail_content["author"]
                if detail_content.get("tags"):
                    item["tags"] = detail_content["tags"]

                # 从详情页提取评论（当前已在详情页，无需再次导航）
                comments = _extract_comments_from_detail_page(driver, max_comments)
                comments.sort(key=lambda c: c.get("like_count", 0), reverse=True)
                item["comments"] = comments[:max_comments]

                logger.info(f"[xhs.collect] 笔记 {idx + 1} 完成: content={len(item['content'])}字, comments={len(item['comments'])}条")

                # 返回搜索结果页，继续处理下一个笔记
                _go_back_to_search(driver, search_url)
            else:
                consecutive_failures += 1
                logger.warning(f"[xhs.collect] 无法导航到笔记 {note_id} 的详情页 (连续失败: {consecutive_failures})")
                # 导航失败也尝试返回搜索页
                _go_back_to_search(driver, search_url)
                item["content"] = ""
                item["comments"] = []

        logger.info(f"[xhs.collect] 收集完成，共 {len(items)} 条笔记")
        return {
            "items": items,
            "total": len(items),
            "keywords": keywords,
            "platform": "xiaohongshu",
        }

    except Exception as collect_error:
        logger.error(f"[xhs.collect] 收集失败: {collect_error}")
        return {
            "items": [],
            "total": 0,
            "keywords": keywords,
            "error": str(collect_error),
        }
    finally:
        if driver:
            driver.quit()
