# -*- coding: utf-8 -*-
"""
Cookie 自动获取助手
当 Cookie 为空时，弹出浏览器让用户登录，登录后自动提取并缓存 Cookie。
"""

import json
import time
from pathlib import Path

COOKIE_CACHE_DIR = Path(__file__).parent / ".cookie_cache"

PLATFORM_CONFIG = {
    "xiaohongshu": {
        "name": "小红书",
        "login_url": "https://www.xiaohongshu.com",
        "login_check_cookie": "web_session",
        "cache_file": "xhs_cookies.json",
    },
    "douyin": {
        "name": "抖音",
        "login_url": "https://www.douyin.com",
        "login_check_cookie": "sessionid",
        "cache_file": "douyin_cookies.json",
    },
    "bilibili": {
        "name": "B站",
        "login_url": "https://passport.bilibili.com/login",
        "login_check_cookie": "SESSDATA",
        "cache_file": "bili_cookies.json",
    },
}


def get_cookie_or_login(platform: str, hardcoded_cookie: str = "") -> str:
    """获取 Cookie：优先使用硬编码 → 缓存文件 → 弹出浏览器登录

    Args:
        platform: 平台标识，如 "xiaohongshu"、"douyin"、"bilibili"
        hardcoded_cookie: run.py 中硬编码的 Cookie 字符串

    Returns:
        Cookie 字符串
    """
    config = PLATFORM_CONFIG[platform]
    platform_name = config["name"]
    cache_file = COOKIE_CACHE_DIR / config["cache_file"]

    # 1. 优先使用硬编码的 Cookie
    if hardcoded_cookie.strip():
        print(f"  ✓ 使用配置区填入的{platform_name} Cookie")
        return hardcoded_cookie.strip()

    # 2. 尝试从缓存文件读取
    cached_cookie = _load_cached_cookie(cache_file)
    if cached_cookie:
        print(f"  ✓ 从缓存加载{platform_name} Cookie（{cache_file.name}）")
        return cached_cookie

    # 3. 弹出浏览器让用户登录
    print(f"\n  ⚠️  未检测到{platform_name} Cookie，将打开浏览器让你登录")
    print(f"  请在浏览器中完成登录，登录成功后脚本会自动继续...\n")
    cookie_string = _login_and_extract_cookie(config)

    if cookie_string:
        _save_cookie_cache(cache_file, cookie_string)
        print(f"  ✓ {platform_name} Cookie 已保存到缓存，下次运行无需重新登录")
        return cookie_string

    print(f"  ✗ 未能获取{platform_name} Cookie，请手动在配置区填入")
    return ""


def clear_cookie_cache(platform: str):
    """清除指定平台的 Cookie 缓存"""
    config = PLATFORM_CONFIG[platform]
    cache_file = COOKIE_CACHE_DIR / config["cache_file"]
    if cache_file.exists():
        cache_file.unlink()
        print(f"  ✓ 已清除{config['name']} Cookie 缓存")


def _load_cached_cookie(cache_file: Path) -> str:
    """从缓存文件加载 Cookie"""
    if not cache_file.exists():
        return ""
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        cookie_string = data.get("cookie_string", "")
        saved_time = data.get("saved_at", "")
        if cookie_string:
            print(f"  ℹ️  Cookie 缓存时间: {saved_time}")
        return cookie_string
    except (json.JSONDecodeError, KeyError):
        return ""


def _save_cookie_cache(cache_file: Path, cookie_string: str):
    """保存 Cookie 到缓存文件"""
    COOKIE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    data = {
        "cookie_string": cookie_string,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _login_and_extract_cookie(config: dict) -> str:
    """弹出浏览器让用户登录，登录成功后提取 Cookie

    使用 undetected-chromedriver 避免被反爬检测。
    轮询检测登录状态（通过检查特定 Cookie 是否存在），
    登录成功后提取所有 Cookie 并拼接为字符串。
    """
    try:
        import undetected_chromedriver as uc
    except ImportError:
        print("  ✗ 缺少 undetected-chromedriver，请先安装：pip install undetected-chromedriver")
        return ""

    platform_name = config["name"]
    login_url = config["login_url"]
    login_check_cookie = config["login_check_cookie"]

    print(f"  🌐 正在打开{platform_name}登录页面...")

    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--window-size=1280,900")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")

    driver = None
    try:
        # 指定 version_main 避免自动下载不匹配的 ChromeDriver
        driver = uc.Chrome(options=chrome_options, version_main=145)
        driver.get(login_url)

        print(f"  📱 请在浏览器中登录{platform_name}账号...")
        print(f"  ⏳ 等待登录完成（最长等待 5 分钟）...\n")

        max_wait_seconds = 300
        check_interval = 3
        elapsed = 0

        while elapsed < max_wait_seconds:
            time.sleep(check_interval)
            elapsed += check_interval

            # 检查是否已登录：查找特定的登录态 Cookie
            cookies = driver.get_cookies()
            cookie_names = {c["name"] for c in cookies}

            if login_check_cookie in cookie_names:
                print(f"\n  ✅ 检测到登录成功！正在提取 Cookie...")
                time.sleep(2)  # 等待页面完全加载

                # 重新获取最新的 Cookie
                cookies = driver.get_cookies()
                cookie_string = "; ".join(
                    f"{c['name']}={c['value']}" for c in cookies
                )
                return cookie_string

            # 每 30 秒提示一次
            if elapsed % 30 == 0:
                remaining = max_wait_seconds - elapsed
                print(f"  ⏳ 仍在等待登录... 剩余 {remaining} 秒")

        print(f"\n  ⏰ 等待超时（5 分钟），请手动在配置区填入 Cookie")
        return ""

    except Exception as error:
        print(f"  ✗ 浏览器启动失败: {error}")
        return ""
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
