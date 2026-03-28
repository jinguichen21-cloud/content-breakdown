# -*- coding: utf-8 -*-
"""抖音视频下载模块 — 使用 undetected_chromedriver 提取视频地址并下载"""

import re
import ssl
import time
from pathlib import Path
from urllib.request import Request, urlopen

_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.check_hostname = False
_SSL_CONTEXT.verify_mode = ssl.CERT_NONE

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)


def _download_file(url: str, output_path: Path, headers: dict = None) -> bool:
    """通用文件下载"""
    default_headers = {"User-Agent": _DEFAULT_UA}
    if headers:
        default_headers.update(headers)

    request = Request(url)
    for header_name, header_value in default_headers.items():
        request.add_header(header_name, header_value)

    try:
        response = urlopen(request, timeout=120, context=_SSL_CONTEXT)
        with open(output_path, "wb") as video_file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                video_file.write(chunk)
        return output_path.exists() and output_path.stat().st_size > 10000
    except Exception as download_error:
        print(f"    ✗ 下载文件失败: {download_error}")
        return False


def init_browser(cookie_string: str = ""):
    """初始化浏览器并注入 Cookie（只调用一次）"""
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    import os

    # 使用固定的用户数据目录，保持登录态
    user_data_dir = os.path.join(os.path.expanduser("~"), ".aone_copilot", "skills", "skill-douyin", "chrome_user_data")
    os.makedirs(user_data_dir, exist_ok=True)

    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=zh-CN")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # 修复：指定 Chrome 版本为 145，避免版本不匹配
    driver = uc.Chrome(options=options, headless=False, version_main=145)
    driver.set_page_load_timeout(30)

    # 先访问抖音首页
    driver.get("https://www.douyin.com")
    time.sleep(5)

    # 注入 Cookie
    if cookie_string:
        # 清除可能存在的旧 Cookie
        driver.delete_all_cookies()
        time.sleep(1)
        
        # 注入新 Cookie
        for pair in cookie_string.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            try:
                driver.add_cookie({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".douyin.com",
                    "path": "/",
                })
            except Exception as cookie_error:
                print(f"    跳过无效 Cookie: {name[:20]}... - {cookie_error}")
        
        # 刷新页面使 Cookie 生效
        driver.refresh()
        time.sleep(3)
        
        # 验证登录状态
        try:
            driver.get("https://www.douyin.com")
            time.sleep(3)
            current_url = driver.current_url
            if "login" in current_url.lower():
                print("    ⚠ 警告：注入 Cookie 后仍处于登录页面，Cookie 可能已过期")
            else:
                print("    ✓ Cookie 注入成功，登录态验证通过")
        except Exception:
            pass

    return driver


def download_douyin_with_driver(driver, video_url: str, output_dir: Path) -> Path | None:
    """使用已初始化的浏览器实例下载视频（复用登录态）"""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "video.mp4"

    if output_path.exists() and output_path.stat().st_size > 10000:
        print(f"    视频已存在：{output_path}")
        return output_path

    print(f"    下载抖音视频：{video_url}")

    driver.get(video_url)
    time.sleep(5)

    video_src = _extract_video_src(driver)

    if not video_src:
        print("    ✗ 未能从页面中提取到视频地址")
        return None

    print(f"    提取到视频地址：{video_src[:80]}...")

    if _download_file(video_src, output_path, headers={"Referer": "https://www.douyin.com/"}):
        file_size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"    ✓ 抖音视频下载完成：{output_path} ({file_size_mb:.1f} MB)")
        return output_path
    else:
        print("    ✗ 抖音视频下载失败")
        return None


def download_douyin(video_url: str, output_dir: Path, cookie_string: str = "") -> Path | None:
    """抖音视频下载（兼容旧接口，单次使用）"""
    driver = init_browser(cookie_string)
    try:
        return download_douyin_with_driver(driver, video_url, output_dir)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _extract_video_src(driver) -> str | None:
    """从浏览器中提取视频地址"""
    from selenium.webdriver.common.by import By

    # 方法1：直接从 video 标签获取 src
    try:
        video_elements = driver.find_elements(By.TAG_NAME, "video")
        for video_el in video_elements:
            src = video_el.get_attribute("src")
            if src and src.startswith("http") and "blob:" not in src:
                return src
    except Exception:
        pass

    # 方法2：从 source 子标签获取
    try:
        source_elements = driver.find_elements(By.CSS_SELECTOR, "video source")
        for source_el in source_elements:
            src = source_el.get_attribute("src")
            if src and src.startswith("http"):
                return src
    except Exception:
        pass

    # 方法3：通过 JS 获取
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
            return video_src
    except Exception:
        pass

    # 方法4：从页面源码正则提取
    try:
        page_source = driver.page_source
        patterns = [
            r'"playAddr"\s*:\s*\[\s*\{\s*"src"\s*:\s*"(https?://[^"]+)"',
            r'"play_addr"\s*:.*?"url_list"\s*:\s*\[\s*"(https?://[^"]+)"',
            r'(https://v[0-9a-z-]+\.douyinvod\.com/[^"\'\\\s]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, page_source)
            if match:
                url = match.group(1)
                if "\\u002F" in url:
                    url = url.encode().decode("unicode_escape")
                return url
    except Exception:
        pass

    return None