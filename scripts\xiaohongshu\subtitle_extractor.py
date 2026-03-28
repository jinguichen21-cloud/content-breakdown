# -*- coding: utf-8 -*-
"""
字幕检测与提取模块（基于 yt-dlp）
参考：action-transcription-main 项目
支持平台：小红书、抖音、B 站

核心逻辑：
1. 使用 yt-dlp --all-subs --skip-download 检测并下载字幕（不下载视频）
2. 如果没有字幕，尝试 yt-dlp --write-auto-sub --skip-download（自动生成字幕）
3. 如果仍然没有字幕，返回失败，由调用方降级为音频转录
"""

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List


def _find_subtitle_files(directory: Path) -> List[Path]:
    """在目录中查找所有字幕文件（vtt/srt/ttml/ass）"""
    subtitle_extensions = {".vtt", ".srt", ".ttml", ".ass", ".json"}
    found_files = []
    
    if not directory.exists():
        return found_files
    
    for file_path in directory.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in subtitle_extensions:
            found_files.append(file_path)
    
    return found_files


def _parse_vtt_to_text(vtt_path: Path) -> str:
    """将 VTT 字幕文件解析为纯文本"""
    with open(vtt_path, "r", encoding="utf-8") as vtt_file:
        content = vtt_file.read()
    
    # 移除 WEBVTT 头部
    content = re.sub(r'WEBVTT.*?\n\n', '', content, flags=re.DOTALL)
    # 移除时间戳行
    content = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}.*\n', '', content)
    # 移除 HTML 标签
    content = re.sub(r'<[^>]+>', '', content)
    # 移除空行和序号行
    lines = []
    seen_lines = set()
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.isdigit():
            continue
        # 去重（VTT 经常有重复行）
        if line not in seen_lines:
            seen_lines.add(line)
            lines.append(line)
    
    return '\n'.join(lines)


def _parse_srt_to_text(srt_path: Path) -> str:
    """将 SRT 字幕文件解析为纯文本"""
    with open(srt_path, "r", encoding="utf-8") as srt_file:
        content = srt_file.read()
    
    # 移除序号行
    content = re.sub(r'^\d+\s*$', '', content, flags=re.MULTILINE)
    # 移除时间戳行
    content = re.sub(r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}.*\n', '', content)
    # 移除 HTML 标签
    content = re.sub(r'<[^>]+>', '', content)
    
    lines = []
    seen_lines = set()
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line not in seen_lines:
            seen_lines.add(line)
            lines.append(line)
    
    return '\n'.join(lines)


def _parse_ttml_to_text(ttml_path: Path) -> str:
    """将 TTML 字幕文件解析为纯文本"""
    with open(ttml_path, "r", encoding="utf-8") as ttml_file:
        content = ttml_file.read()
    
    # 提取 <p> 标签中的文本
    text_parts = re.findall(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
    
    lines = []
    seen_lines = set()
    for part in text_parts:
        # 移除 HTML 标签
        clean_text = re.sub(r'<[^>]+>', '', part).strip()
        if clean_text and clean_text not in seen_lines:
            seen_lines.add(clean_text)
            lines.append(clean_text)
    
    return '\n'.join(lines)


def _parse_bilibili_json_subtitle(json_path: Path) -> str:
    """将 B 站 JSON 格式字幕解析为纯文本"""
    with open(json_path, "r", encoding="utf-8") as json_file:
        data = json.load(json_file)
    
    # B 站字幕 JSON 格式：{"body": [{"from": 0, "to": 1, "content": "文本"}, ...]}
    body = data.get("body", [])
    if not body:
        # 也可能是 yt-dlp 下载的格式
        body = data if isinstance(data, list) else []
    
    lines = []
    for item in body:
        content = item.get("content", "").strip()
        if content:
            lines.append(content)
    
    return '\n'.join(lines)


def _parse_subtitle_file(subtitle_path: Path) -> str:
    """根据文件格式自动解析字幕文件为纯文本"""
    suffix = subtitle_path.suffix.lower()
    
    if suffix == ".vtt":
        return _parse_vtt_to_text(subtitle_path)
    elif suffix == ".srt":
        return _parse_srt_to_text(subtitle_path)
    elif suffix == ".ttml":
        return _parse_ttml_to_text(subtitle_path)
    elif suffix == ".json":
        return _parse_bilibili_json_subtitle(subtitle_path)
    else:
        # 尝试作为纯文本读取
        with open(subtitle_path, "r", encoding="utf-8") as generic_file:
            return generic_file.read()


def _build_yt_dlp_cookie_args(cookie_string: str, platform: str) -> List[str]:
    """将 Cookie 字符串转为 yt-dlp 可用的 Cookie 文件参数"""
    if not cookie_string:
        return []
    
    # 创建 Netscape 格式的 Cookie 文件
    cookie_file = tempfile.NamedTemporaryFile(
        mode='w', suffix='.txt', delete=False, encoding='utf-8'
    )
    
    domain_map = {
        "xiaohongshu": ".xiaohongshu.com",
        "douyin": ".douyin.com",
        "bilibili": ".bilibili.com",
    }
    domain = domain_map.get(platform, ".example.com")
    
    cookie_file.write("# Netscape HTTP Cookie File\n")
    for pair in cookie_string.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        # Netscape 格式：domain  flag  path  secure  expiry  name  value
        cookie_file.write(f"{domain}\tTRUE\t/\tFALSE\t0\t{name.strip()}\t{value.strip()}\n")
    
    cookie_file.close()
    return ["--cookies", cookie_file.name]


def _extract_xiaohongshu_subtitles_from_page(video_url: str, cookie_string: str = "") -> dict:
    """
    通过浏览器自动化从小红书页面提取字幕（作为 yt-dlp 的降级方案）
    
    小红书字幕通常嵌入在页面 JSON 中或通过 API 加载
    """
    result = {
        "success": False,
        "subtitle_text": "",
        "error": None
    }
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import json
        import re
        
        # 配置浏览器
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # 设置 User-Agent
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        
        # 注入 Cookie
        if cookie_string:
            driver.get("https://www.xiaohongshu.com")
            for pair in cookie_string.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    name, value = pair.split("=", 1)
                    try:
                        driver.add_cookie({
                            "name": name.strip(),
                            "value": value.strip(),
                            "domain": ".xiaohongshu.com"
                        })
                    except Exception:
                        pass
        
        # 访问视频页面
        driver.get(video_url)
        
        # 等待页面加载
        time.sleep(3)
        
        # 方法1: 从页面脚本标签中提取字幕数据
        page_source = driver.page_source
        
        # 尝试匹配小红书字幕 JSON 数据
        # 格式通常在 window.__INITIAL_STATE__ 或类似的变量中
        subtitle_patterns = [
            r'"subtitle":\s*({[^}]+})',
            r'"captions":\s*(\[[^\]]+\])',
            r'"lyrics":\s*(\[[^\]]+\])',
            r'"text":\s*"([^"]+)"[^}]*"time":\s*\d+',
        ]
        
        for pattern in subtitle_patterns:
            matches = re.findall(pattern, page_source)
            if matches:
                # 找到字幕数据
                subtitle_texts = []
                for match in matches:
                    try:
                        if match.startswith('[') or match.startswith('{'):
                            data = json.loads(match)
                            if isinstance(data, list):
                                for item in data:
                                    if isinstance(item, dict) and "text" in item:
                                        subtitle_texts.append(item["text"])
                            elif isinstance(data, dict) and "text" in data:
                                subtitle_texts.append(data["text"])
                        else:
                            subtitle_texts.append(match)
                    except json.JSONDecodeError:
                        subtitle_texts.append(match)
                
                if subtitle_texts:
                    result["success"] = True
                    result["subtitle_text"] = "\n".join(subtitle_texts)
                    result["subtitle_type"] = "page_extracted"
                    driver.quit()
                    return result
        
        # 方法2: 尝试点击字幕按钮并提取
        try:
            # 查找字幕/CC按钮
            subtitle_button = driver.find_element(By.CSS_SELECTOR, "[class*='subtitle'], [class*='caption'], [class*='cc']")
            if subtitle_button:
                subtitle_button.click()
                time.sleep(1)
                
                # 提取显示的字幕文本
                subtitle_elements = driver.find_elements(By.CSS_SELECTOR, "[class*='subtitle-text'], [class*='caption-text']")
                if subtitle_elements:
                    subtitle_texts = [elem.text for elem in subtitle_elements if elem.text.strip()]
                    if subtitle_texts:
                        result["success"] = True
                        result["subtitle_text"] = "\n".join(subtitle_texts)
                        result["subtitle_type"] = "ui_extracted"
                        driver.quit()
                        return result
        except Exception:
            pass
        
        driver.quit()
        result["error"] = "页面中未找到字幕数据"
        
    except Exception as e:
        result["error"] = f"浏览器提取字幕失败: {e}"
    
    return result


def try_extract_subtitles(video_url: str, output_dir: Path,
                          platform: str = "", cookie_string: str = "") -> dict:
    """
    尝试提取视频字幕（不下载视频）
    
    流程：
    1. yt-dlp --all-subs --skip-download 尝试获取人工字幕
    2. 如果没有，yt-dlp --write-auto-sub --skip-download 尝试获取自动字幕
    3. 对于小红书，如果 yt-dlp 失败，尝试浏览器自动化提取
    4. 解析字幕文件为纯文本
    
    参数:
        video_url: 视频 URL
        output_dir: 输出目录
        platform: 平台名称 (xiaohongshu/douyin/bilibili)
        cookie_string: Cookie 字符串
    
    返回:
        {
            "success": True/False,
            "subtitle_text": "字幕纯文本",
            "subtitle_path": "字幕文件路径",
            "subtitle_type": "manual/auto/page_extracted",
            "error": "错误信息"
        }
    """
    result = {
        "success": False,
        "subtitle_text": "",
        "subtitle_path": None,
        "subtitle_type": None,
        "error": None
    }
    
    # 创建字幕临时目录
    subs_dir = output_dir / "subs"
    auto_dir = output_dir / "auto"
    subs_dir.mkdir(parents=True, exist_ok=True)
    auto_dir.mkdir(parents=True, exist_ok=True)
    
    # 构建 Cookie 参数
    cookie_args = _build_yt_dlp_cookie_args(cookie_string, platform)
    cookie_file_path = cookie_args[1] if cookie_args else None
    
    try:
        # Step 1: 尝试获取人工字幕
        print(f"    尝试提取人工字幕...")
        manual_cmd = [
            "yt-dlp",
            "--all-subs",
            "--skip-download",
            "--sub-format", "vtt/srt/ttml/best",
            *cookie_args,
            video_url
        ]
        
        subprocess.run(
            manual_cmd,
            cwd=str(subs_dir),
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # 检查是否下载到了字幕文件
        manual_subtitle_files = _find_subtitle_files(subs_dir)
        
        if manual_subtitle_files:
            # 优先选择中文字幕
            chosen_file = _pick_best_subtitle(manual_subtitle_files)
            subtitle_text = _parse_subtitle_file(chosen_file)
            
            if subtitle_text.strip():
                result["success"] = True
                result["subtitle_text"] = subtitle_text
                result["subtitle_path"] = str(chosen_file)
                result["subtitle_type"] = "manual"
                print(f"    ✓ 提取到人工字幕，字数：{len(subtitle_text)}")
                return result
        
        # Step 2: 尝试获取自动生成字幕
        print(f"    未找到人工字幕，尝试提取自动字幕...")
        auto_cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--skip-download",
            "--sub-format", "vtt/srt/ttml/best",
            *cookie_args,
            video_url
        ]
        
        subprocess.run(
            auto_cmd,
            cwd=str(auto_dir),
            capture_output=True,
            text=True,
            timeout=60
        )
        
        auto_subtitle_files = _find_subtitle_files(auto_dir)
        
        if auto_subtitle_files:
            chosen_file = _pick_best_subtitle(auto_subtitle_files)
            subtitle_text = _parse_subtitle_file(chosen_file)
            
            if subtitle_text.strip():
                result["success"] = True
                result["subtitle_text"] = subtitle_text
                result["subtitle_path"] = str(chosen_file)
                result["subtitle_type"] = "auto"
                print(f"    ✓ 提取到自动字幕，字数：{len(subtitle_text)}")
                return result
        
        # 两种方式都没有找到字幕，尝试浏览器提取（仅小红书）
        if platform == "xiaohongshu":
            print(f"    yt-dlp 未找到字幕，尝试浏览器提取...")
            page_result = _extract_xiaohongshu_subtitles_from_page(video_url, cookie_string)
            if page_result.get("success"):
                result["success"] = True
                result["subtitle_text"] = page_result.get("subtitle_text", "")
                result["subtitle_type"] = page_result.get("subtitle_type", "page_extracted")
                print(f"    ✓ 浏览器提取字幕成功，字数：{len(result['subtitle_text'])}")
                return result
            else:
                print(f"    ✗ 浏览器提取也失败: {page_result.get('error', '')}")
        
        result["error"] = "该视频没有可用字幕"
        print(f"    ✗ 未检测到任何字幕")
    
    except subprocess.TimeoutExpired:
        result["error"] = "yt-dlp 字幕提取超时"
        print(f"    ✗ 字幕提取超时")
        
        # 超时后也尝试浏览器提取（仅小红书）
        if platform == "xiaohongshu":
            print(f"    yt-dlp 超时，尝试浏览器提取...")
            page_result = _extract_xiaohongshu_subtitles_from_page(video_url, cookie_string)
            if page_result.get("success"):
                result["success"] = True
                result["subtitle_text"] = page_result.get("subtitle_text", "")
                result["subtitle_type"] = page_result.get("subtitle_type", "page_extracted")
                print(f"    ✓ 浏览器提取字幕成功，字数：{len(result['subtitle_text'])}")
                return result
    
    except FileNotFoundError:
        result["error"] = "未安装 yt-dlp，请运行 pip install yt-dlp"
        print(f"    ✗ 未安装 yt-dlp")
        
        # yt-dlp 未安装，尝试浏览器提取（仅小红书）
        if platform == "xiaohongshu":
            print(f"    yt-dlp 未安装，尝试浏览器提取...")
            page_result = _extract_xiaohongshu_subtitles_from_page(video_url, cookie_string)
            if page_result.get("success"):
                result["success"] = True
                result["subtitle_text"] = page_result.get("subtitle_text", "")
                result["subtitle_type"] = page_result.get("subtitle_type", "page_extracted")
                print(f"    ✓ 浏览器提取字幕成功，字数：{len(result['subtitle_text'])}")
                return result
    
    except Exception as unexpected_error:
        result["error"] = f"字幕提取异常：{unexpected_error}"
        print(f"    ✗ 字幕提取异常：{unexpected_error}")
        
        # 异常后也尝试浏览器提取（仅小红书）
        if platform == "xiaohongshu":
            print(f"    yt-dlp 异常，尝试浏览器提取...")
            page_result = _extract_xiaohongshu_subtitles_from_page(video_url, cookie_string)
            if page_result.get("success"):
                result["success"] = True
                result["subtitle_text"] = page_result.get("subtitle_text", "")
                result["subtitle_type"] = page_result.get("subtitle_type", "page_extracted")
                print(f"    ✓ 浏览器提取字幕成功，字数：{len(result['subtitle_text'])}")
                return result
    
    finally:
        # 清理临时 Cookie 文件
        if cookie_file_path and os.path.exists(cookie_file_path):
            try:
                os.unlink(cookie_file_path)
            except Exception:
                pass
    
    return result


def _pick_best_subtitle(subtitle_files: List[Path]) -> Path:
    """从多个字幕文件中选择最佳的一个（优先中文，其次英文）"""
    # 优先级：zh > zh-CN > zh-Hans > en > 其他
    priority_langs = ["zh", "zh-CN", "zh-Hans", "zh-Hant", "en"]
    
    for lang in priority_langs:
        for file_path in subtitle_files:
            if f".{lang}." in file_path.name.lower():
                return file_path
    
    # 没有匹配到优先语言，返回第一个文件
    return subtitle_files[0]
