# -*- coding: utf-8 -*-
"""抖音搜索 + 评论抓取模块（undetected_chromedriver + Cookie 注入）"""

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

DOUYIN_SEARCH_URL = "https://www.douyin.com/search/{keyword}?type=video"
DOUYIN_DOMAIN = ".douyin.com"

# 简繁转换字典（常用字）
TRADITIONAL_TO_SIMPLIFIED = {
    '強': '强', '別': '别', '風': '风', '裝': '装', '舉': '举', '麼': '么', '當': '当',
    '然': '然', '鮮': '鲜', '是': '是', '沒': '没', '錯': '错', '如': '如', '果': '果',
    '看': '看', '完': '完', '視': '视', '頻': '频', '大': '大', '家': '家', '還': '还',
    '想': '想', '試': '试', '試': '试', '我': '我', '妹': '妹', '在': '在', '後': '后',
    '面': '面', '給': '给', '了': '了', '些': '些', '使': '使', '用': '用', '的': '的',
    '建': '建', '議': '议', '首': '首', '先': '先', '毫': '毫', '不': '不', '誇': '夸',
    '張': '张', '時': '时', '候': '候', '產': '产', '品': '品', '只': '只', '要': '要',
    '把': '把', '它': '它', '裝': '装', '在': '在', '電': '电', '腦': '脑', '上': '上', '或': '或',
    '者': '者', '不': '不', '輸': '输', '到': '到', '隱': '隐', '瞻': '瞻', '咱': '咱',
    '在': '在', '聊': '聊', '天': '天', '軟': '软', '件': '件', '裡': '里', '都': '都',
    '弄': '弄', '嘴': '嘴', '皮': '皮', '子': '子', '這': '这', '個': '个', '做': '做',
    '手': '手', '就': '就', '能': '能', '幫': '帮', '你': '你', '完': '完', '成': '成',
    '任': '任', '務': '务', '當': '当', '然': '然', '前': '前', '提': '提', '是': '是',
    '小': '小', '時': '时', '全': '全', '線': '线', '都': '都', '給': '给', '到': '到',
    '位': '位', '了': '了', '又': '又', '因': '因', '為': '为', '這': '这', '個': '个',
    '單': '单', '子': '子', '有': '有', '小': '小', '龍': '龙', '蝦': '虾', '前': '前',
    '資': '资', '的': '的', '說': '说', '實': '实', '話': '话', '讓': '让', '我': '我',
    '們': '们', '來': '来', '認': '认', '識': '识', '一': '一', '下': '下', '這': '这',
    '個': '个', '東': '东', '西': '西', '到': '到', '底': '底', '是': '是', '什': '什',
    '麼': '么', '東': '东', '西': '西', '為': '为', '什': '什', '麼': '么', '這': '这',
    '麼': '么', '火': '火', '現': '现', '在': '在', '讓': '让', '我': '我', '們': '们',
    '起': '起', '開': '开', '始': '始', '體': '体', '驗': '验', '吧': '吧', '覺': '觉',
    '得': '得', '樣': '样', '樣': '样', '麼': '么', '樣': '样', '點': '点', '擊': '击',
    '關': '关', '註': '注', '讚': '赞', '賞': '赏', '評': '评', '論': '论', '轉': '转',
    '發': '发', '購': '购', '買': '买', '賣': '卖', '賣': '卖', '錢': '钱', '賺': '赚',
    '費': '费', '費': '费', '廣': '广', '告': '告', '歡': '欢', '迎': '迎', '謝': '谢',
    '謝': '谢', '請': '请', '問': '问', '嗎': '吗', '呢': '呢', '啊': '啊', '呀': '呀',
    '啦': '啦', '哦': '哦', '噢': '噢', '嘿': '嘿', '嗨': '嗨', '嗯': '嗯', '嘛': '嘛',
    '咯': '咯', '嘍': '喽', '唄': '呗', '啵': '啵', '嘞': '嘞', '嘛': '嘛', '啰': '啰',
}

def traditional_to_simplified(text: str) -> str:
    """将繁体中文转换为简体中文"""
    if not text:
        return text
    result = []
    for char in text:
        result.append(TRADITIONAL_TO_SIMPLIFIED.get(char, char))
    return ''.join(result)


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
            cookies.append({"name": name, "value": value, "domain": DOUYIN_DOMAIN, "path": "/"})
    return cookies


def _create_browser(cookie_string: str = ""):
    """创建 undetected Chrome 浏览器（可见模式，抖音检测 headless 极严）"""
    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={global_settings.browser.user_agent}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=zh-CN")
    options.add_argument("--disable-gpu")

    driver = uc.Chrome(options=options, headless=False, version_main=145)
    driver.set_page_load_timeout(global_settings.browser.page_load_timeout)

    if cookie_string:
        logger.info("[douyin] 注入 Cookie 登录态")
        driver.get("https://www.douyin.com")
        time.sleep(5)
        parsed_cookies = _parse_cookie_string(cookie_string)
        injected_count = 0
        for cookie in parsed_cookies:
            try:
                driver.add_cookie(cookie)
                injected_count += 1
            except Exception:
                pass
        logger.info(f"[douyin] 已注入 {injected_count}/{len(parsed_cookies)} 个 Cookie")
        driver.refresh()
        time.sleep(3)

    return driver


def _is_captcha_page(driver) -> bool:
    """检测是否为验证码页面"""
    title = driver.title or ""
    if "验证" in title or "captcha" in title.lower():
        return True
    page_source = driver.page_source
    if len(page_source) < 20000 and ("验证码" in page_source or "captcha" in page_source.lower()):
        return True
    return False


def _wait_past_captcha(driver, max_wait_seconds: int = 120):
    """如果检测到验证码，等待用户手动解决"""
    if not _is_captcha_page(driver):
        return
    print("\n" + "=" * 60)
    print("  [验证码] 抖音弹出了验证码，请在浏览器中手动完成验证")
    print(f"  等待最多 {max_wait_seconds} 秒...")
    print("=" * 60)

    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        if not _is_captcha_page(driver):
            logger.info("[douyin] 验证码已解决")
            break
        time.sleep(2)
    time.sleep(2)


def search_with_driver(driver, keywords: str, page_size: int = 10) -> Dict[str, Any]:
    """抖音关键词搜索（复用已初始化的浏览器实例）"""
    logger.info(f"[douyin.search] 开始搜索：keywords={keywords}")
    try:
        search_url = DOUYIN_SEARCH_URL.format(keyword=keywords)
        logger.info(f"[douyin.search] 直接跳转搜索页：{search_url}")
        driver.get(search_url)
        time.sleep(5)

        # 调试：打印页面状态
        page_title = driver.title or "(无标题)"
        page_len = len(driver.page_source)
        print(f"  [DEBUG] 页面标题：{page_title}")
        print(f"  [DEBUG] 页面大小：{page_len} 字符")
        print(f"  [DEBUG] 当前 URL: {driver.current_url}")

        # 处理验证码
        if _is_captcha_page(driver):
            print("  [DEBUG] 检测到验证码页面，等待用户解决...")
        _wait_past_captcha(driver)

        # 如果仍在验证码页面，重新加载一次
        if _is_captcha_page(driver):
            logger.warning("[douyin.search] 仍在验证码页面，重新加载...")
            driver.get(search_url)
            time.sleep(5)

        # 再次打印页面状态
        page_title = driver.title or "(无标题)"
        page_len = len(driver.page_source)
        print(f"  [DEBUG] 验证码处理后 - 标题：{page_title}, 大小：{page_len}")

        # 滚动加载更多结果，收集 3 倍候选池再按点赞排序
        candidate_pool_size = max(page_size * 3, 30)
        
        # 先等待搜索结果加载
        logger.info("[douyin.search] 等待搜索结果加载...")
        time.sleep(8)
        
        # 多次滚动加载更多
        for scroll_round in range(10):
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(2.0)
            
        # 滚回顶部，确保内容已渲染
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(3)

        # 优先从 SSR script 标签提取（更可靠，包含点赞数）
        items = _extract_from_ssr(driver, candidate_pool_size)
        print(f"  [DEBUG] SSR 提取：{len(items)} 条")

        # 降级：从 DOM 提取
        if not items:
            items = _extract_from_dom(driver, candidate_pool_size)
            print(f"  [DEBUG] DOM 提取：{len(items)} 条")

        # 如果都没提取到，保存页面源码用于调试
        if not items:
            import tempfile
            debug_path = tempfile.gettempdir() + "/douyin_debug.html"
            with open(debug_path, "w", encoding="utf-8") as debug_file:
                debug_file.write(driver.page_source)
            print(f"  [DEBUG] 未找到视频，页面源码已保存：{debug_path}")

        # 按点赞排序，取 Top N
        items.sort(key=lambda v: v.get("like_count", 0), reverse=True)
        items = items[:page_size]

        logger.info(f"[douyin.search] 找到 {len(items)} 条视频（按点赞排序）")
        return {"items": items, "total": len(items), "keywords": keywords, "platform": "douyin"}
    except Exception as search_error:
        logger.error(f"[douyin.search] 搜索失败：{search_error}")
        return {"items": [], "total": 0, "keywords": keywords, "error": str(search_error)}

def _extract_aweme_id(video_url: str) -> str:
    """从视频 URL 中提取 aweme_id（视频 ID）"""
    match = re.search(r'/video/(\d+)', video_url)
    if match:
        return match.group(1)
    match = re.search(r'modal_id=(\d+)', video_url)
    if match:
        return match.group(1)
    return ""


def _fetch_comments_via_api(driver, aweme_id: str, max_comments: int = 30) -> List[Dict[str, Any]]:
    """通过抖音评论 API 接口获取评论（稳定可靠，不受 DOM 变化影响）
    
    利用浏览器已有的 Cookie 和会话状态，通过 JavaScript fetch 调用抖音内部 API。
    """
    comments = []
    cursor = 0
    page_count = 20

    logger.info(f"[douyin.comments.api] 通过 API 抓取评论，aweme_id={aweme_id}")

    for page in range(10):
        if len(comments) >= max_comments:
            break

        api_url = (
            f"https://www.douyin.com/aweme/v1/web/comment/list/"
            f"?aweme_id={aweme_id}&cursor={cursor}&count={page_count}"
            f"&item_type=0&insert_ids=&whale_cut_token=&cut_version=1"
            f"&rcFT=&update_version_code=170400"
        )

        try:
            fetch_script = f"""
            return await fetch("{api_url}", {{
                method: "GET",
                credentials: "include",
                headers: {{
                    "Accept": "application/json",
                    "Referer": "https://www.douyin.com/video/{aweme_id}"
                }}
            }}).then(r => r.text()).catch(e => JSON.stringify({{"error": e.message}}));
            """
            response_text = driver.execute_script(fetch_script)

            if not response_text:
                logger.warning(f"[douyin.comments.api] 第 {page + 1} 页返回空响应")
                break

            data = json.loads(response_text)

            if data.get("error"):
                logger.warning(f"[douyin.comments.api] API 错误: {data['error']}")
                break

            status_code = data.get("status_code", -1)
            if status_code != 0:
                logger.warning(f"[douyin.comments.api] API 状态码异常: {status_code}")
                break

            raw_comments = data.get("comments", [])
            if not raw_comments:
                logger.info(f"[douyin.comments.api] 第 {page + 1} 页无更多评论")
                break

            for raw_comment in raw_comments:
                text = raw_comment.get("text", "")
                if not text or len(text.strip()) < 1:
                    continue

                user_info = raw_comment.get("user", {})
                author_name = user_info.get("nickname", "未知用户")

                digg_count = raw_comment.get("digg_count", 0)
                reply_count = raw_comment.get("reply_comment_total", 0)
                create_time = raw_comment.get("create_time", 0)

                comments.append({
                    "author": author_name,
                    "content": traditional_to_simplified(text.strip()),
                    "like_count": digg_count,
                    "reply_count": reply_count,
                    "create_time": create_time,
                })

            has_more = data.get("has_more", 0)
            cursor = data.get("cursor", cursor + page_count)

            logger.info(f"[douyin.comments.api] 第 {page + 1} 页获取 {len(raw_comments)} 条，累计 {len(comments)} 条")

            if not has_more:
                break

            time.sleep(1.5)

        except json.JSONDecodeError as json_error:
            logger.warning(f"[douyin.comments.api] JSON 解析失败: {json_error}")
            break
        except Exception as api_error:
            logger.warning(f"[douyin.comments.api] API 请求异常: {api_error}")
            break

    logger.info(f"[douyin.comments.api] API 共获取 {len(comments)} 条评论")
    return comments


def fetch_comments_with_driver(driver, video_url: str, max_comments: int = 30) -> List[Dict[str, Any]]:
    """抓取抖音视频的高赞一级评论（复用已初始化的浏览器实例）
    
    策略：API 优先 → 页面源码正则 → DOM 解析（三级降级）
    """
    logger.info(f"[douyin.comments] 抓取评论：{video_url}")
    try:
        aweme_id = _extract_aweme_id(video_url)

        # 先导航到视频页面（确保浏览器上下文正确，Cookie 生效）
        driver.get(video_url)
        time.sleep(6)
        _wait_past_captcha(driver)

        comments = []

        # 策略 1：API 接口抓取（最稳定）
        if aweme_id:
            logger.info(f"[douyin.comments] 策略 1: API 接口抓取 (aweme_id={aweme_id})")
            comments = _fetch_comments_via_api(driver, aweme_id, max_comments)
            if comments:
                logger.info(f"[douyin.comments] API 成功获取 {len(comments)} 条评论")

        # 策略 2：从页面源码正则提取
        if len(comments) < max_comments // 2:
            logger.info("[douyin.comments] 策略 2: 页面源码正则提取")
            source_comments = _extract_comments_from_source(driver, max_comments)
            if source_comments:
                logger.info(f"[douyin.comments] 源码提取到 {len(source_comments)} 条评论")
                existing_contents = {c["content"] for c in comments}
                for source_comment in source_comments:
                    if source_comment["content"] not in existing_contents:
                        comments.append(source_comment)

        # 策略 3：DOM 解析（降级方案）
        if len(comments) < max_comments // 2:
            logger.info("[douyin.comments] 策略 3: DOM 解析降级")
            # 滚动加载评论区
            for scroll_index in range(20):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(0.8)
                if scroll_index % 10 == 9:
                    try:
                        current_height = driver.execute_script("return window.pageYOffset + window.innerHeight")
                        total_height = driver.execute_script("return document.body.scrollHeight")
                        if current_height >= total_height * 0.95:
                            break
                    except Exception:
                        pass

            dom_comments = _extract_comments_from_dom(driver, max_comments)
            if dom_comments:
                logger.info(f"[douyin.comments] DOM 提取到 {len(dom_comments)} 条评论")
                existing_contents = {c["content"] for c in comments}
                for dom_comment in dom_comments:
                    if dom_comment["content"] not in existing_contents:
                        comments.append(dom_comment)

        # 按点赞数排序，取 Top N
        comments.sort(key=lambda c: c.get("like_count", 0), reverse=True)
        result = comments[:max_comments]
        logger.info(f"[douyin.comments] 最终获取 {len(result)} 条高赞评论")
        return result

    except Exception as comment_error:
        logger.error(f"[douyin.comments] 抓取失败：{comment_error}")
        return []

def _parse_count(count_text: str) -> int:
    """解析数量文本（如 '1.2w' -> 12000）"""
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


def _search_with_requests(keywords: str, page_size: int = 10, cookie_string: str = "") -> List[Dict[str, Any]]:
    """使用 requests 直接调用抖音搜索 API（备用方案）"""
    import requests
    import urllib.parse
    
    logger.info("[douyin.search] 尝试使用 requests API 搜索...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    
    # 解析 Cookie
    cookies = {}
    if cookie_string:
        for pair in cookie_string.split(";"):
            pair = pair.strip()
            if "=" in pair:
                name, value = pair.split("=", 1)
                cookies[name.strip()] = value.strip()
    
    try:
        # 抖音搜索 API
        encoded_keyword = urllib.parse.quote(keywords)
        search_url = f"https://www.douyin.com/aweme/v1/web/search/item/?keyword={encoded_keyword}&search_source=normal_search&search_type=video&cursor=0&count={page_size * 2}"
        
        response = requests.get(search_url, headers=headers, cookies=cookies, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            videos = data.get("data", [])
            
            items = []
            for video in videos[:page_size]:
                aweme_info = video.get("aweme_info", {})
                if not aweme_info:
                    continue
                    
                video_id = aweme_info.get("aweme_id", "")
                statistics = aweme_info.get("statistics", {})
                author = aweme_info.get("author", {})
                
                items.append({
                    "video_id": video_id,
                    "title": aweme_info.get("desc", ""),
                    "author": author.get("nickname", ""),
                    "author_id": author.get("unique_id", "") or author.get("short_id", ""),
                    "like_count": statistics.get("digg_count", 0),
                    "comment_count": statistics.get("comment_count", 0),
                    "share_count": statistics.get("share_count", 0),
                    "collect_count": statistics.get("collect_count", 0),
                    "play_count": statistics.get("play_count", 0),
                    "url": f"https://www.douyin.com/video/{video_id}",
                })
            
            logger.info(f"[douyin.search] API 搜索成功: {len(items)} 条")
            return items
        else:
            logger.warning(f"[douyin.search] API 请求失败: {response.status_code}")
            return []
            
    except Exception as e:
        logger.warning(f"[douyin.search] API 搜索失败: {e}")
        return []


def search(keywords: str, page_size: int = 10, cookie_string: str = "") -> Dict[str, Any]:
    """抖音关键词搜索，返回按点赞排序的 Top N 视频
    
    直接使用浏览器方案（与 media_crawler 成功版本一致），
    跳过不可靠的 requests API。
    """
    logger.info(f"[douyin.search] 开始搜索: keywords={keywords}")
    driver = None
    try:
        driver = _create_browser(cookie_string=cookie_string)
        search_url = DOUYIN_SEARCH_URL.format(keyword=keywords)
        logger.info(f"[douyin.search] 直接跳转搜索页: {search_url}")
        driver.get(search_url)
        time.sleep(5)

        # 调试：打印页面状态
        page_title = driver.title or "(无标题)"
        page_len = len(driver.page_source)
        print(f"  [DEBUG] 页面标题: {page_title}")
        print(f"  [DEBUG] 页面大小: {page_len} 字符")
        print(f"  [DEBUG] 当前URL: {driver.current_url}")

        # 处理验证码
        if _is_captcha_page(driver):
            print("  [DEBUG] 检测到验证码页面，等待用户解决...")
        _wait_past_captcha(driver)

        # 如果仍在验证码页面，重新加载一次
        if _is_captcha_page(driver):
            logger.warning("[douyin.search] 仍在验证码页面，重新加载...")
            driver.get(search_url)
            time.sleep(5)

        # 再次打印页面状态
        page_title = driver.title or "(无标题)"
        page_len = len(driver.page_source)
        print(f"  [DEBUG] 验证码处理后 - 标题: {page_title}, 大小: {page_len}")

        # 滚动加载更多结果，收集 3 倍候选池再按点赞排序
        candidate_pool_size = max(page_size * 3, 30)
        for scroll_round in range(8):
            driver.execute_script("window.scrollBy(0, 800);")
            time.sleep(1.5)

        # 优先从 SSR script 标签提取（更可靠，包含点赞数）
        items = _extract_from_ssr(driver, candidate_pool_size)
        print(f"  [DEBUG] SSR 提取: {len(items)} 条")

        # 降级：从 DOM 提取
        if not items:
            items = _extract_from_dom(driver, candidate_pool_size)
            print(f"  [DEBUG] DOM 提取: {len(items)} 条")

        # 如果都没提取到，保存页面源码用于调试
        if not items:
            import tempfile
            debug_path = tempfile.gettempdir() + "/douyin_debug.html"
            with open(debug_path, "w", encoding="utf-8") as debug_file:
                debug_file.write(driver.page_source)
            print(f"  [DEBUG] 未找到视频，页面源码已保存: {debug_path}")

        # 按点赞排序，取 Top N
        items.sort(key=lambda v: v.get("like_count", 0), reverse=True)
        items = items[:page_size]

        logger.info(f"[douyin.search] 找到 {len(items)} 条视频（按点赞排序）")
        return {"items": items, "total": len(items), "keywords": keywords, "platform": "douyin"}
    except Exception as search_error:
        logger.error(f"[douyin.search] 搜索失败: {search_error}")
        return {"items": [], "total": 0, "keywords": keywords, "error": str(search_error)}
    finally:
        if driver:
            driver.quit()


def _extract_from_ssr(driver, page_size: int) -> List[Dict[str, Any]]:
    """从 SSR script 标签提取视频数据"""
    items = []
    try:
        page_source = driver.page_source
        render_data_match = re.search(
            r'<script\s+id="RENDER_DATA"[^>]*>(.*?)</script>', page_source, re.DOTALL
        )
        if render_data_match:
            from urllib.parse import unquote
            raw_text = unquote(render_data_match.group(1))
            data = json.loads(raw_text)
            for key, value in data.items():
                if not isinstance(value, dict):
                    continue
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, list):
                        for item in sub_value[:page_size]:
                            video_item = _parse_ssr_video_item(item)
                            if video_item:
                                items.append(video_item)
                    elif isinstance(sub_value, dict):
                        data_list = sub_value.get("data", [])
                        if isinstance(data_list, list):
                            for item in data_list[:page_size]:
                                video_item = _parse_ssr_video_item(item)
                                if video_item:
                                    items.append(video_item)
                if items:
                    break
    except Exception as ssr_error:
        logger.debug(f"[douyin._extract_from_ssr] SSR 提取失败: {ssr_error}")
    return items[:page_size]


def _parse_ssr_video_item(raw_item: Any) -> Optional[Dict[str, Any]]:
    """解析 SSR 数据中的单个视频"""
    if not isinstance(raw_item, dict):
        return None
    aweme_info = raw_item.get("aweme_info", raw_item)
    if not isinstance(aweme_info, dict):
        return None

    video_id = aweme_info.get("aweme_id", "")
    if not video_id:
        return None

    desc = aweme_info.get("desc", "")
    author_info = aweme_info.get("author", {})
    statistics = aweme_info.get("statistics", {})

    return {
        "video_id": video_id,
        "title": desc,
        "author": author_info.get("nickname", ""),
        "author_id": author_info.get("unique_id", "") or author_info.get("short_id", ""),
        "like_count": statistics.get("digg_count", 0),
        "comment_count": statistics.get("comment_count", 0),
        "share_count": statistics.get("share_count", 0),
        "collect_count": statistics.get("collect_count", 0),
        "play_count": statistics.get("play_count", 0),
        "url": f"https://www.douyin.com/video/{video_id}",
    }


def _extract_from_dom(driver, page_size: int) -> List[Dict[str, Any]]:
    """从 DOM 提取视频数据，通过 a[href*='/video/'] 链接定位视频"""
    items = []
    seen_ids = set()
    try:
        video_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/video/']")
        for link in video_links:
            try:
                href = link.get_attribute("href") or ""
                if "/video/" not in href:
                    continue
                video_id = href.split("/video/")[-1].split("?")[0].strip("/")
                if not video_id or not video_id.isdigit() or video_id in seen_ids:
                    continue
                seen_ids.add(video_id)

                raw_text = link.text.strip()
                if not raw_text:
                    continue

                # 链接文本格式: "时长\n点赞数\n标题内容"
                # 例如: "00:39\n196\n《菜包精选》AI玩家必看！..."
                # 或: "05:52\n1.9万\nOpenClaw 必装的 10 个核心技能..."
                lines = [line.strip() for line in raw_text.split("\n") if line.strip()]

                title = ""
                like_text = ""
                duration_pattern = re.compile(r"^\d{1,2}:\d{2}$")

                if len(lines) >= 3 and duration_pattern.match(lines[0]):
                    like_text = lines[1]
                    title = "\n".join(lines[2:])
                elif len(lines) >= 2 and duration_pattern.match(lines[0]):
                    title = "\n".join(lines[1:])
                elif len(lines) >= 2:
                    like_text = lines[0]
                    title = "\n".join(lines[1:])
                else:
                    title = raw_text

                if not title or len(title) < 3:
                    continue

                # 尝试从父容器中获取作者信息
                author_text = ""
                try:
                    card = link.find_element(By.XPATH, "./ancestor::li[1]")
                    author_elements = card.find_elements(
                        By.CSS_SELECTOR, "span[class*='author'], a[class*='author'], span[class*='nickname']"
                    )
                    if author_elements:
                        author_text = author_elements[0].text.strip()
                except Exception:
                    pass

                items.append({
                    "video_id": video_id,
                    "title": title,
                    "author": author_text,
                    "like_count": _parse_count(like_text),
                    "url": f"https://www.douyin.com/video/{video_id}",
                    "comment_count": 0,
                    "share_count": 0,
                    "collect_count": 0,
                    "play_count": 0,
                })
            except Exception:
                continue
    except Exception as dom_error:
        logger.debug(f"[douyin._extract_from_dom] DOM 提取失败: {dom_error}")
    return items


def fetch_comments(video_url: str, cookie_string: str = "", max_comments: int = 30) -> List[Dict[str, Any]]:
    """抓取抖音视频的高赞一级评论（独立入口，会创建新浏览器实例）
    
    策略与 fetch_comments_with_driver 一致：API 优先 → 源码正则 → DOM 解析
    """
    logger.info(f"[douyin.comments] 抓取评论: {video_url}")
    driver = None
    try:
        aweme_id = _extract_aweme_id(video_url)
        driver = _create_browser(cookie_string=cookie_string)
        driver.get(video_url)
        time.sleep(6)

        _wait_past_captcha(driver)

        comments = []

        # 策略 1：API 接口抓取
        if aweme_id:
            comments = _fetch_comments_via_api(driver, aweme_id, max_comments)

        # 策略 2：页面源码正则提取
        if len(comments) < max_comments // 2:
            source_comments = _extract_comments_from_source(driver, max_comments)
            if source_comments:
                existing_contents = {c["content"] for c in comments}
                for source_comment in source_comments:
                    if source_comment["content"] not in existing_contents:
                        comments.append(source_comment)

        # 策略 3：DOM 解析降级
        if len(comments) < max_comments // 2:
            for _ in range(10):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1.5)
            dom_comments = _extract_comments_from_dom(driver, max_comments)
            if dom_comments:
                existing_contents = {c["content"] for c in comments}
                for dom_comment in dom_comments:
                    if dom_comment["content"] not in existing_contents:
                        comments.append(dom_comment)

        comments.sort(key=lambda c: c.get("like_count", 0), reverse=True)
        result = comments[:max_comments]
        logger.info(f"[douyin.comments] 最终获取 {len(result)} 条高赞评论")
        return result

    except Exception as comment_error:
        logger.error(f"[douyin.comments] 抓取失败: {comment_error}")
        return []
    finally:
        if driver:
            driver.quit()


def _extract_comments_from_dom(driver, max_comments: int) -> List[Dict[str, Any]]:
    """从 DOM 提取评论（优化版：使用更精确的选择器）"""
    comments = []
    
    # 优化的评论容器选择器（更精确匹配抖音评论区结构）
    # 必须包含 info-wrap 的才是完整的评论项
    comment_container_selectors = [
        "div[class*='comment-item-info-wrap']",
        "div[class*='commentItemInfoWrap']",
        "div[class*='comment-item-container']",
        "div[class*='commentItemContainer']",
        "div[class*='CommentItemContainer']",
    ]
    
    # 评论内容选择器（直接定位评论文本）
    content_selectors = [
        "span[class*='comment-text']",
        "span[class*='commentText']",
        "div[class*='comment-content']",
        "div[class*='commentContent']",
        "p[class*='comment-text']",
        "span[class*='text']",
    ]
    
    # 作者选择器
    author_selectors = [
        "span[class*='author-name']",
        "span[class*='authorName']",
        "span[class*='nickname']",
        "span[class*='user-name']",
        "span[class*='userName']",
        "div[class*='user-info'] span",
    ]
    
    # 点赞数选择器
    like_selectors = [
        "span[class*='like-count']",
        "span[class*='likeCount']",
        "span[class*='digg-count']",
        "span[class*='diggCount']",
        "span[class*='like-num']",
        "span[class*='likeNum']",
    ]

    # 查找评论容器
    comment_containers = []
    for selector in comment_container_selectors:
        comment_containers = driver.find_elements(By.CSS_SELECTOR, selector)
        if comment_containers:
            logger.info(f"[douyin.comments] 使用选择器找到 {len(comment_containers)} 个评论容器：{selector}")
            break
    
    if not comment_containers:
        logger.warning("[douyin.comments] 未找到评论容器")
        return comments

    logger.info(f"[douyin.comments] 开始提取评论，共找到 {len(comment_containers)} 个容器")

    for container in comment_containers[:max_comments * 2]:
        try:
            # 提取作者
            author = ""
            for selector in author_selectors:
                try:
                    author_elem = container.find_element(By.CSS_SELECTOR, selector)
                    if author_elem and author_elem.text.strip():
                        author = author_elem.text.strip()
                        break
                except Exception:
                    continue
            
            # 提取评论内容 - 简化策略：直接从容器中找所有 span，取第一个有效内容
            content = ""
            try:
                # 获取容器内所有 span 标签
                all_spans = container.find_elements(By.TAG_NAME, "span")
                for span in all_spans:
                    text = span.text.strip()
                    # 跳过空文本、操作按钮、时间地点、点赞数
                    if not text:
                        continue
                    if text in ['分享', '回复', '举报', '删除', '展开', '收起', '作者']:
                        continue
                    if re.match(r'^\d+[天周月年]前', text) or '·' in text:
                        continue
                    if re.match(r'^[\d.]+[万千百]?$', text):
                        continue
                    # 找到第一个有效的文本，且长度合理
                    if len(text) >= 2:
                        content = text
                        break
            except Exception as e:
                logger.debug(f"[douyin.comments] 从 span 提取评论内容失败: {e}")
            
            # 提取点赞数
            like_count = 0
            for selector in like_selectors:
                try:
                    like_elem = container.find_element(By.CSS_SELECTOR, selector)
                    if like_elem and like_elem.text.strip():
                        like_count = _parse_count(like_elem.text.strip())
                        break
                except Exception:
                    continue
            
            # 如果点赞选择器找不到，尝试从文本解析
            if like_count == 0:
                full_text = container.text
                like_count = _parse_count(full_text)
            
            # 提取回复数
            reply_count = 0
            full_text = container.text
            reply_match = re.search(r"(\d+)\s*条回复", full_text)
            if reply_match:
                reply_count = int(reply_match.group(1))
            
            # 只添加有效的评论
            if content and len(content) > 1:
                comments.append({
                    "author": author if author else "未知用户",
                    "content": content,
                    "like_count": like_count,
                    "reply_count": reply_count,
                })
                logger.debug(f"[douyin.comments] 提取到评论：{content[:30]}... (👍{like_count})")
                
        except Exception as e:
            logger.debug(f"[douyin.comments] 提取单条评论失败：{e}")
            continue

    logger.info(f"[douyin.comments] 成功提取 {len(comments)} 条有效评论")
    return comments


def _extract_comments_from_source(driver, max_comments: int) -> List[Dict[str, Any]]:
    """从页面源码正则提取评论（增强版：多种模式匹配）"""
    comments = []
    seen_texts = set()
    try:
        page_source = driver.page_source

        # 模式 1：匹配 "text":"xxx" 紧跟 "digg_count":N 的结构
        pattern_text_digg = re.compile(
            r'"text"\s*:\s*"([^"]{2,500})"[^}]{0,300}?"digg_count"\s*:\s*(\d+)',
            re.DOTALL,
        )
        for text, digg_count in pattern_text_digg.findall(page_source):
            if len(comments) >= max_comments:
                break
            decoded_text = text.encode().decode("unicode_escape", errors="ignore").strip()
            if decoded_text and len(decoded_text) >= 2 and decoded_text not in seen_texts:
                seen_texts.add(decoded_text)
                comments.append({
                    "author": "",
                    "content": traditional_to_simplified(decoded_text),
                    "like_count": int(digg_count),
                    "reply_count": 0,
                })

        # 模式 2：匹配 "digg_count":N 在 "text":"xxx" 前面的结构
        if len(comments) < max_comments // 2:
            pattern_digg_text = re.compile(
                r'"digg_count"\s*:\s*(\d+)[^}]{0,300}?"text"\s*:\s*"([^"]{2,500})"',
                re.DOTALL,
            )
            for digg_count, text in pattern_digg_text.findall(page_source):
                if len(comments) >= max_comments:
                    break
                decoded_text = text.encode().decode("unicode_escape", errors="ignore").strip()
                if decoded_text and len(decoded_text) >= 2 and decoded_text not in seen_texts:
                    seen_texts.add(decoded_text)
                    comments.append({
                        "author": "",
                        "content": traditional_to_simplified(decoded_text),
                        "like_count": int(digg_count),
                        "reply_count": 0,
                    })

        logger.info(f"[douyin.comments.source] 源码正则提取到 {len(comments)} 条评论")
    except Exception as source_error:
        logger.warning(f"[douyin.comments.source] 源码提取异常: {source_error}")
    return comments
