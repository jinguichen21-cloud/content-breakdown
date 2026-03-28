# -*- coding: utf-8 -*-
"""
字幕检测与提取模块（基于 yt-dlp + 必剪 ASR 降级方案）
参考：action-transcription-main 项目、video-link-pipeline-main 项目
支持平台：小红书、抖音、B 站

核心逻辑：
1. 使用 yt-dlp --all-subs --skip-download 检测并下载字幕（不下载视频）
2. 如果没有字幕，尝试 yt-dlp --write-auto-sub --skip-download（自动生成字幕）
3. 如果仍然没有字幕，使用必剪云端 ASR 进行音频转录（降级方案）
4. 抖音平台优先使用专属提取 + 移动端 API 方案
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

# 导入必剪 ASR 模块
try:
    from .bcut_asr import transcribe_video_with_bcut, extract_audio_ffmpeg
except ImportError:
    from bcut_asr import transcribe_video_with_bcut, extract_audio_ffmpeg


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


def try_extract_subtitles(video_url: str, output_dir: Path,
                          platform: str = "", cookie_string: str = "") -> dict:
    """
    使用 yt-dlp 尝试提取视频字幕（不下载视频）
    
    流程（参考 action-transcription-main）：
    1. 如果是抖音平台，优先使用 extract_douyin_subtitles
    2. yt-dlp --all-subs --skip-download 尝试获取人工字幕
    3. 如果没有，yt-dlp --write-auto-sub --skip-download 尝试获取自动字幕
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
            "subtitle_type": "manual/auto",
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
    
    # ===== 抖音平台优先使用专属提取 =====
    if platform.lower() == "douyin":
        print(f"    使用抖音专属字幕提取...")
        douyin_result = extract_douyin_subtitles(video_url, cookie_string)
        if douyin_result.get("success"):
            return {
                "success": True,
                "subtitle_text": douyin_result.get("subtitle_text", ""),
                "subtitle_path": None,
                "subtitle_type": douyin_result.get("subtitle_type", "auto"),
                "error": None
            }
        print(f"    抖音专属提取失败: {douyin_result.get('error')}, 尝试 yt-dlp...")
    
    # ===== 原有 yt-dlp 提取逻辑 =====
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
        
        # 两种方式都没有找到字幕，尝试 bcut ASR 降级方案
        print(f"    ✗ 未检测到平台字幕，尝试必剪 ASR 转录...")
        return _try_bcut_asr_fallback(video_url, output_dir, platform, cookie_string)
    
    except subprocess.TimeoutExpired:
        result["error"] = "yt-dlp 字幕提取超时"
        print(f"    ✗ 字幕提取超时")
    
    except FileNotFoundError:
        result["error"] = "未安装 yt-dlp，请运行 pip install yt-dlp"
        print(f"    ✗ 未安装 yt-dlp")
    
    except Exception as unexpected_error:
        result["error"] = f"字幕提取异常：{unexpected_error}"
        print(f"    ✗ 字幕提取异常：{unexpected_error}")
    
    finally:
        # 清理临时 Cookie 文件
        if cookie_file_path and os.path.exists(cookie_file_path):
            try:
                os.unlink(cookie_file_path)
            except Exception:
                pass
    
    return result


def _try_bcut_asr_fallback(video_url: str, output_dir: Path,
                           platform: str, cookie_string: str) -> dict:
    """
    使用必剪云端 ASR 进行音频转录（降级方案）
    
    流程：
    1. 使用 yt-dlp 下载音频（或视频提取音频）
    2. 使用必剪 ASR 进行云端语音识别
    3. 返回转录文本
    
    参数:
        video_url: 视频 URL
        output_dir: 输出目录
        platform: 平台名称
        cookie_string: Cookie 字符串
    
    返回:
        {
            "success": True/False,
            "subtitle_text": "转录文本",
            "subtitle_path": "转录文件路径",
            "subtitle_type": "bcut_asr",
            "error": "错误信息"
        }
    """
    result = {
        "success": False,
        "subtitle_text": "",
        "subtitle_path": None,
        "subtitle_type": "bcut_asr",
        "error": None
    }
    
    # 创建音频目录
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    
    # 构建 Cookie 参数
    cookie_args = _build_yt_dlp_cookie_args(cookie_string, platform)
    cookie_file_path = cookie_args[1] if cookie_args else None
    
    audio_path = None
    
    try:
        # Step 1: 尝试下载音频
        print(f"    下载音频用于 ASR 转录...")
        
        # 先尝试直接下载音频
        audio_cmd = [
            "yt-dlp",
            "-f", "bestaudio/best",
            "-x", "--audio-format", "wav",
            "--audio-quality", "0",
            "--postprocessor-args", "-ar 16000 -ac 1",
            "-o", str(audio_dir / "audio.%(ext)s"),
            *cookie_args,
            video_url
        ]
        
        subprocess.run(
            audio_cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # 查找下载的音频文件
        for ext in [".wav", ".mp3", ".m4a", ".aac"]:
            candidate = audio_dir / f"audio{ext}"
            if candidate.exists():
                audio_path = candidate
                break
        
        # 如果没有下载到音频，尝试下载视频并提取音频
        if not audio_path:
            print(f"    音频下载失败，尝试下载视频提取音频...")
            video_cmd = [
                "yt-dlp",
                "-f", "best[height<=720]/best",
                "-o", str(audio_dir / "video.%(ext)s"),
                *cookie_args,
                video_url
            ]
            
            subprocess.run(
                video_cmd,
                capture_output=True,
                text=True,
                timeout=180
            )
            
            # 查找下载的视频文件
            video_path = None
            for ext in [".mp4", ".webm", ".mkv"]:
                candidate = audio_dir / f"video{ext}"
                if candidate.exists():
                    video_path = candidate
                    break
            
            if video_path:
                # 提取音频
                audio_path = audio_dir / "audio_extracted.wav"
                if extract_audio_ffmpeg(str(video_path), str(audio_path)):
                    print(f"    ✓ 从视频提取音频成功")
                else:
                    audio_path = None
        
        if not audio_path or not audio_path.exists():
            result["error"] = "无法获取音频文件"
            print(f"    ✗ 音频获取失败")
            return result
        
        print(f"    ✓ 音频准备完成: {audio_path.name}")
        
        # Step 2: 使用必剪 ASR 转录
        print(f"    开始必剪云端 ASR 转录...")
        bcut_result = transcribe_video_with_bcut(str(audio_path), str(audio_dir))
        
        if bcut_result.get("success"):
            result["success"] = True
            result["subtitle_text"] = bcut_result.get("text", "")
            result["subtitle_path"] = bcut_result.get("output_file")
            print(f"    ✓ 必剪 ASR 转录完成，字数: {len(result['subtitle_text'])}")
        else:
            result["error"] = bcut_result.get("error", "必剪 ASR 转录失败")
            print(f"    ✗ 必剪 ASR 转录失败: {result['error']}")
    
    except subprocess.TimeoutExpired:
        result["error"] = "音频下载超时"
        print(f"    ✗ 音频下载超时")
    
    except FileNotFoundError:
        result["error"] = "未安装 yt-dlp，请运行 pip install yt-dlp"
        print(f"    ✗ 未安装 yt-dlp")
    
    except Exception as e:
        result["error"] = f"ASR 转录异常: {e}"
        print(f"    ✗ ASR 转录异常: {e}")
    
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


def extract_douyin_subtitles(video_url: str, cookie_string: str = "") -> dict:
    """
    抖音专属字幕提取 - 通过浏览器访问视频详情页获取字幕
    
    抖音字幕存储在：
    1. SSR 数据中的 RENDER_DATA -> aweme_info -> subtitle_infos
    2. 页面源码中的 window._SSR_HYDRATED_DATA 或类似数据结构
    
    参数:
        video_url: 抖音视频 URL (https://www.douyin.com/video/xxx)
        cookie_string: Cookie 字符串
    
    返回:
        {
            "success": True/False,
            "subtitle_text": "字幕纯文本",
            "subtitle_type": "manual/auto/none",
            "error": "错误信息"
        }
    """
    import json
    import re
    import time
    from urllib.parse import unquote
    
    result = {
        "success": False,
        "subtitle_text": "",
        "subtitle_type": None,
        "error": None
    }
    
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
    except ImportError:
        result["error"] = "未安装 undetected_chromedriver"
        return result
    
    # 解析 Cookie
    cookies = []
    if cookie_string:
        for pair in cookie_string.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            name, value = name.strip(), value.strip()
            if name and value:
                cookies.append({"name": name, "value": value, "domain": ".douyin.com", "path": "/"})
    
    driver = None
    try:
        # 创建浏览器
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=zh-CN")
        options.add_argument("--disable-gpu")
        options.add_argument("--headless=new")  # 字幕提取可以用 headless
        
        driver = uc.Chrome(options=options, version_main=145)
        driver.set_page_load_timeout(30)
        
        # 访问视频页面
        driver.get("https://www.douyin.com")
        time.sleep(2)
        
        # 注入 Cookie
        for cookie in cookies:
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass
        
        # 访问视频详情页
        driver.get(video_url)
        time.sleep(5)
        
        # 方法1: 从 SSR RENDER_DATA 提取
        page_source = driver.page_source
        render_data_match = re.search(
            r'<script\s+id="RENDER_DATA"[^>]*>(.*?)</script>', page_source, re.DOTALL
        )
        
        if render_data_match:
            try:
                raw_text = unquote(render_data_match.group(1))
                data = json.loads(raw_text)
                
                # 遍历查找 aweme_info -> subtitle_infos
                def find_subtitle_infos(obj, depth=0):
                    if depth > 10:
                        return None
                    if isinstance(obj, dict):
                        # 检查是否有 subtitle_infos
                        if "subtitle_infos" in obj and obj["subtitle_infos"]:
                            return obj["subtitle_infos"]
                        # 递归查找
                        for value in obj.values():
                            result = find_subtitle_infos(value, depth + 1)
                            if result:
                                return result
                    elif isinstance(obj, list):
                        for item in obj:
                            result = find_subtitle_infos(item, depth + 1)
                            if result:
                                return result
                    return None
                
                subtitle_infos = find_subtitle_infos(data)
                
                if subtitle_infos and isinstance(subtitle_infos, list):
                    # 解析字幕信息
                    all_texts = []
                    for sub in subtitle_infos:
                        if isinstance(sub, dict):
                            # 抖音字幕格式: {"url": "...", "language": "zh", "format": "srt", "source": "auto"}
                            sub_url = sub.get("url", "")
                            sub_format = sub.get("format", "srt")
                            sub_source = sub.get("source", "")  # "auto" 或 "manual"
                            
                            if sub_url:
                                # 下载字幕内容
                                try:
                                    import urllib.request
                                    req = urllib.request.Request(
                                        sub_url,
                                        headers={
                                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
                                        }
                                    )
                                    with urllib.request.urlopen(req, timeout=10) as response:
                                        sub_content = response.read().decode('utf-8')
                                        
                                        # 解析字幕内容
                                        if sub_format == "srt":
                                            text = _parse_srt_content(sub_content)
                                        elif sub_format == "vtt":
                                            text = _parse_vtt_content(sub_content)
                                        else:
                                            text = _parse_srt_content(sub_content)
                                        
                                        if text.strip():
                                            all_texts.append(text)
                                            result["subtitle_type"] = "auto" if sub_source == "auto" else "manual"
                                except Exception as download_error:
                                    print(f"    字幕下载失败: {download_error}")
                                    continue
                    
                    if all_texts:
                        result["success"] = True
                        result["subtitle_text"] = "\n".join(all_texts)
                        print(f"    ✓ 从 RENDER_DATA 提取到字幕，字数: {len(result['subtitle_text'])}")
                        return result
            except Exception as parse_error:
                print(f"    RENDER_DATA 解析失败: {parse_error}")
        
        # 方法2: 从页面源码直接查找 subtitle_infos JSON
        subtitle_pattern = re.search(
            r'"subtitle_infos"\s*:\s*(\[.*?\])', page_source, re.DOTALL
        )
        if subtitle_pattern:
            try:
                # 处理可能的转义
                json_str = subtitle_pattern.group(1)
                json_str = json_str.replace('\\"', '"')
                subtitle_infos = json.loads(json_str)
                
                all_texts = []
                for sub in subtitle_infos:
                    if isinstance(sub, dict):
                        sub_url = sub.get("url", "")
                        sub_format = sub.get("format", "srt")
                        sub_source = sub.get("source", "")
                        
                        if sub_url:
                            try:
                                import urllib.request
                                req = urllib.request.Request(
                                    sub_url,
                                    headers={
                                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
                                    }
                                )
                                with urllib.request.urlopen(req, timeout=10) as response:
                                    sub_content = response.read().decode('utf-8')
                                    
                                    if sub_format == "srt":
                                        text = _parse_srt_content(sub_content)
                                    else:
                                        text = _parse_srt_content(sub_content)
                                    
                                    if text.strip():
                                        all_texts.append(text)
                                        result["subtitle_type"] = "auto" if sub_source == "auto" else "manual"
                            except Exception:
                                continue
                
                if all_texts:
                    result["success"] = True
                    result["subtitle_text"] = "\n".join(all_texts)
                    print(f"    ✓ 从页面源码提取到字幕，字数: {len(result['subtitle_text'])}")
                    return result
            except Exception as regex_error:
                print(f"    正则提取字幕失败: {regex_error}")
        
        # 方法3: 尝试从 video 对象中提取字幕信息
        video_pattern = re.search(
            r'"video"\s*:\s*\{.*?"subtitle_infos"\s*:\s*(\[.*?\])', page_source, re.DOTALL
        )
        if video_pattern:
            try:
                json_str = video_pattern.group(1)
                json_str = json_str.replace('\\"', '"')
                subtitle_infos = json.loads(json_str)
                
                all_texts = []
                for sub in subtitle_infos:
                    if isinstance(sub, dict):
                        sub_url = sub.get("url", "")
                        if sub_url:
                            try:
                                import urllib.request
                                req = urllib.request.Request(sub_url, headers={"User-Agent": "Mozilla/5.0"})
                                with urllib.request.urlopen(req, timeout=10) as response:
                                    sub_content = response.read().decode('utf-8')
                                    text = _parse_srt_content(sub_content)
                                    if text.strip():
                                        all_texts.append(text)
                                        result["subtitle_type"] = "auto"
                            except Exception:
                                continue
                
                if all_texts:
                    result["success"] = True
                    result["subtitle_text"] = "\n".join(all_texts)
                    print(f"    ✓ 从 video 对象提取到字幕，字数: {len(result['subtitle_text'])}")
                    return result
            except Exception:
                pass
        
        result["error"] = "未在页面中找到字幕信息"
        print(f"    ✗ 未检测到抖音字幕")
        
    except Exception as browser_error:
        result["error"] = f"浏览器提取字幕失败: {browser_error}"
        print(f"    ✗ 浏览器提取失败: {browser_error}")
    
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
    
    return result


def _parse_srt_content(srt_content: str) -> str:
    """解析 SRT 格式字幕内容为纯文本"""
    lines = []
    seen_lines = set()
    
    # 移除序号行和时间戳行
    cleaned = re.sub(r'^\d+\s*$', '', srt_content, flags=re.MULTILINE)
    cleaned = re.sub(r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}.*\n', '\n', cleaned)
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    
    for line in cleaned.split('\n'):
        line = line.strip()
        if not line:
            continue
        # 去重
        if line not in seen_lines:
            seen_lines.add(line)
            lines.append(line)
    
    return '\n'.join(lines)


def _parse_vtt_content(vtt_content: str) -> str:
    """解析 VTT 格式字幕内容为纯文本"""
    lines = []
    seen_lines = set()
    
    # 移除 WEBVTT 头部
    cleaned = re.sub(r'WEBVTT.*?\n\n', '', vtt_content, flags=re.DOTALL)
    # 移除时间戳行
    cleaned = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}.*\n', '\n', cleaned)
    # 移除 HTML 标签
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    
    for line in cleaned.split('\n'):
        line = line.strip()
        if not line or line.isdigit():
            continue
        if line not in seen_lines:
            seen_lines.add(line)
            lines.append(line)
    
    return '\n'.join(lines)