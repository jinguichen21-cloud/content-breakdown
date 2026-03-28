# -*- coding: utf-8 -*-
"""小红书视频下载模块 — 通过 Selenium 提取视频地址并下载"""

import re
import ssl
import time
from pathlib import Path
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from config import global_settings

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


def _create_browser(cookie_string: str = ""):
    """创建 Chrome 浏览器"""
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={global_settings.browser.user_agent}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=zh-CN")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.set_page_load_timeout(global_settings.browser.page_load_timeout)

    if cookie_string:
        driver.get("https://www.xiaohongshu.com")
        time.sleep(3)
        for pair in cookie_string.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            try:
                driver.add_cookie({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".xiaohongshu.com",
                    "path": "/",
                })
            except Exception:
                pass
        driver.refresh()
        time.sleep(2)

    return driver


def download_xiaohongshu(note_url: str, output_dir: Path, cookie_string: str = "") -> Path | None:
    """小红书视频下载：用 Selenium 打开笔记页，提取 video src 下载"""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "video.mp4"

    if output_path.exists() and output_path.stat().st_size > 10000:
        print(f"    视频已存在: {output_path}")
        return output_path

    print(f"    通过浏览器自动化下载小红书视频: {note_url}")

    driver = None
    try:
        driver = _create_browser(cookie_string=cookie_string)
        driver.get(note_url)
        time.sleep(8)

        video_src = _extract_video_src(driver)

        if not video_src:
            print("    ✗ 未能从页面中提取到视频地址")
            return None

        print(f"    提取到视频地址: {video_src[:80]}...")

        if _download_file(video_src, output_path, headers={"Referer": "https://www.xiaohongshu.com/"}):
            file_size_mb = output_path.stat().st_size / 1024 / 1024
            print(f"    ✓ 小红书视频下载完成: {output_path} ({file_size_mb:.1f} MB)")
            return output_path
        else:
            print("    ✗ 小红书视频下载失败")
            return None

    except Exception as xhs_error:
        print(f"    ✗ 小红书下载错误: {xhs_error}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _extract_video_src(driver) -> str | None:
    """从浏览器中提取视频地址"""
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
            r'"originVideoKey"\s*:\s*"([^"]+)"',
            r'"url"\s*:\s*"(https?://sns-video[^"]+)"',
            r'(https://sns-video-[a-z0-9-]+\.xhscdn\.com/[^"\'\\\s]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, page_source)
            if match:
                url = match.group(1)
                if not url.startswith("http"):
                    url = f"https://sns-video-bd.xhscdn.com/{url}"
                return url
    except Exception:
        pass

    return None


def download_video_by_url(video_src: str, output_dir: Path, cookie_string: str = "") -> Path | None:
    """直接通过视频 URL 下载视频（不创建浏览器）
    
    用于新架构中已从详情页 DOM 提取到视频地址的场景，
    避免创建独立浏览器实例被 sec 网关拦截。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "video.mp4"

    if output_path.exists() and output_path.stat().st_size > 10000:
        print(f"    视频已存在: {output_path}")
        return output_path

    print(f"    下载视频: {video_src[:80]}...")
    headers = {"Referer": "https://www.xiaohongshu.com/"}
    if cookie_string:
        headers["Cookie"] = cookie_string

    if _download_file(video_src, output_path, headers=headers):
        file_size_mb = output_path.stat().st_size / 1024 / 1024
        print(f"    ✓ 视频下载完成: {output_path} ({file_size_mb:.1f} MB)")
        return output_path
    else:
        print("    ✗ 视频下载失败")
        return None
