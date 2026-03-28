# -*- coding: utf-8 -*-
"""
必剪云端语音识别工具 - 作为抖音字幕提取的降级方案

参考 video-link-pipeline-main 项目的 bcut_asr.py
优势：
- 免费：使用 B站/必剪 的免费 ASR 服务
- 准确：针对中文优化，识别准确率高
- 快速：云端处理，无需本地 GPU
- 完整：返回带时间戳的 SRT 格式字幕

用法:
  from bcut_asr import transcribe_with_bcut
  result = transcribe_with_bcut("audio.mp3", output_dir="./output")
"""

import json
import logging
import time
from enum import Enum
from os import PathLike
from pathlib import Path
from typing import Literal, Optional, Dict, List

import requests

# 关闭日志
logging.disable(logging.INFO)

# ──────────────────────────────── 数据模型 ────────────────────────────────

class ASRDataSeg:
    """文字识别-断句"""
    def __init__(self, data: dict):
        self.start_time = data.get("start_time", 0)
        self.end_time = data.get("end_time", 0)
        self.transcript = data.get("transcript", "")
        self.confidence = data.get("confidence", 0)
        self.words = data.get("words", [])
    
    def to_srt_ts(self) -> str:
        """转换为 SRT 时间戳"""
        def _conv(ms: int) -> tuple:
            return ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000
        
        s_h, s_m, s_s, s_ms = _conv(self.start_time)
        e_h, e_m, e_s, e_ms = _conv(self.end_time)
        return f"{s_h:02d}:{s_m:02d}:{s_s:02d},{s_ms:03d} --> {e_h:02d}:{e_m:02d}:{e_s:02d},{e_ms:03d}"


class ASRData:
    """语音识别结果"""
    def __init__(self, data: dict):
        self.utterances = [ASRDataSeg(u) for u in data.get("utterances", [])]
        self.version = data.get("version", "")
    
    def has_data(self) -> bool:
        return len(self.utterances) > 0
    
    def to_txt(self) -> str:
        """纯文本（无时间标记）"""
        return "\n".join(seg.transcript for seg in self.utterances)
    
    def to_srt(self) -> str:
        """SRT 字幕"""
        return "\n".join(
            f"{n}\n{seg.to_srt_ts()}\n{seg.transcript}\n"
            for n, seg in enumerate(self.utterances, 1)
        )


class ResultStateEnum(Enum):
    STOP = 0
    RUNNING = 1
    ERROR = 3
    COMPLETE = 4


# ──────────────────────────────── 核心类 ────────────────────────────────

API_REQ_UPLOAD = "https://member.bilibili.com/x/bcut/rubick-interface/resource/create"
API_COMMIT_UPLOAD = "https://member.bilibili.com/x/bcut/rubick-interface/resource/create/complete"
API_CREATE_TASK = "https://member.bilibili.com/x/bcut/rubick-interface/task"
API_QUERY_RESULT = "https://member.bilibili.com/x/bcut/rubick-interface/task/result"

SUPPORT_SOUND_FORMAT = ["flac", "aac", "m4a", "mp3", "wav"]


class APIError(Exception):
    def __init__(self, code, msg) -> None:
        self.code = code
        self.msg = msg
        super().__init__()
    
    def __str__(self) -> str:
        return f"{self.code}:{self.msg}"


class BcutASR:
    """必剪语音识别接口"""
    
    def __init__(self, file_path: Optional[str | PathLike] = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })
        self.task_id = None
        self.__etags = []
        self.sound_bin = None
        self.sound_fmt = None
        self.sound_name = None
        
        if file_path:
            self.set_data(file_path)
    
    def set_data(self, file_path: Optional[str | PathLike] = None,
                 raw_data: Optional[bytes] = None,
                 data_fmt: Optional[str] = None) -> None:
        """设置音频数据"""
        if file_path:
            file_path = Path(file_path)
            with open(file_path, "rb") as f:
                self.sound_bin = f.read()
            suffix = data_fmt or file_path.suffix[1:].lower()
            self.sound_name = file_path.name
        elif raw_data:
            self.sound_bin = raw_data
            suffix = data_fmt
            self.sound_name = f"{int(time.time())}.{suffix}"
        else:
            raise ValueError("必须提供 file_path 或 raw_data")
        
        self.sound_fmt = suffix
        print(f"  加载音频文件: {self.sound_name} ({len(self.sound_bin) // 1024}KB)")
    
    def upload(self) -> None:
        """上传音频文件"""
        if not self.sound_bin or not self.sound_fmt:
            raise ValueError("未设置音频数据")
        
        resp = self.session.post(API_REQ_UPLOAD, data={
            "type": 2,
            "name": self.sound_name,
            "size": len(self.sound_bin),
            "resource_file_type": self.sound_fmt,
            "model_id": 7
        })
        resp.raise_for_status()
        resp_json = resp.json()
        
        if resp_json.get("code"):
            raise APIError(resp_json["code"], resp_json.get("message", "未知错误"))
        
        data = resp_json["data"]
        self.__in_boss_key = data["in_boss_key"]
        self.__resource_id = data["resource_id"]
        self.__upload_id = data["upload_id"]
        self.__upload_urls = data["upload_urls"]
        self.__per_size = data["per_size"]
        self.__clips = len(data["upload_urls"])
        
        print(f"  申请上传成功，共 {self.__clips} 个分片")
        self.__upload_part()
        self.__commit_upload()
    
    def __upload_part(self) -> None:
        """分片上传"""
        for clip in range(self.__clips):
            start = clip * self.__per_size
            end = (clip + 1) * self.__per_size
            resp = self.session.put(self.__upload_urls[clip], data=self.sound_bin[start:end])
            resp.raise_for_status()
            self.__etags.append(resp.headers.get("Etag", ""))
    
    def __commit_upload(self) -> None:
        """完成上传"""
        resp = self.session.post(API_COMMIT_UPLOAD, data={
            "in_boss_key": self.__in_boss_key,
            "resource_id": self.__resource_id,
            "etags": ",".join(self.__etags),
            "upload_id": self.__upload_id,
            "model_id": 7
        })
        resp.raise_for_status()
        resp_json = resp.json()
        
        if resp_json.get("code"):
            raise APIError(resp_json["code"], resp_json.get("message", "未知错误"))
        
        self.__download_url = resp_json["data"]["download_url"]
        print("  音频上传完成")
    
    def create_task(self, max_retries: int = 3) -> str:
        """创建识别任务"""
        for attempt in range(1, max_retries + 1):
            resp = self.session.post(API_CREATE_TASK, json={
                "resource": self.__download_url,
                "model_id": "7"
            })
            resp.raise_for_status()
            resp_json = resp.json()
            
            if resp_json.get("code") == 0:
                break
            
            if resp_json.get("code") == -504 and attempt < max_retries:
                print(f"  创建任务超时，第 {attempt}/{max_retries} 次重试...")
                time.sleep(2 * attempt)
                continue
            
            raise APIError(resp_json["code"], resp_json.get("message", "未知错误"))
        
        self.task_id = resp_json["data"]["task_id"]
        print(f"  语音识别任务已创建: {self.task_id[:8]}...")
        return self.task_id
    
    def query_result(self, task_id: Optional[str] = None) -> dict:
        """查询识别结果"""
        resp = self.session.get(API_QUERY_RESULT, params={
            "model_id": 7,
            "task_id": task_id or self.task_id
        })
        resp.raise_for_status()
        resp_json = resp.json()
        
        if resp_json.get("code"):
            raise APIError(resp_json["code"], resp_json.get("message", "未知错误"))
        
        return resp_json["data"]
    
    def wait_for_result(self, timeout: int = 300) -> ASRData:
        """等待识别完成并获取结果"""
        print("  等待语音识别完成...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            result = self.query_result()
            state = result.get("state")
            
            if state == ResultStateEnum.COMPLETE.value:
                print("  语音识别完成")
                return ASRData(json.loads(result.get("result", "{}")))
            
            elif state == ResultStateEnum.ERROR.value:
                raise APIError(-1, f"识别失败: {result.get('remark', '未知错误')}")
            
            time.sleep(1)
        
        raise APIError(-1, "识别超时")


# ──────────────────────────────── 便捷函数 ────────────────────────────────

def transcribe_with_bcut(audio_path: str, output_dir: Optional[str] = None,
                         output_format: str = "txt") -> Dict:
    """
    使用必剪云端 ASR 转录音频文件
    
    Args:
        audio_path: 音频文件路径 (支持 aac/mp3/wav/flac/m4a)
        output_dir: 输出目录（可选，默认使用音频所在目录）
        output_format: 输出格式 (txt/srt/json)
    
    Returns:
        {
            "success": True/False,
            "text": "识别文本",
            "srt": "SRT格式字幕",
            "output_file": "输出文件路径",
            "error": "错误信息"
        }
    """
    result = {
        "success": False,
        "text": "",
        "srt": "",
        "output_file": None,
        "error": None
    }
    
    audio_path = Path(audio_path)
    if not audio_path.exists():
        result["error"] = f"音频文件不存在: {audio_path}"
        return result
    
    # 确定输出目录
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = audio_path.parent
    
    try:
        # 创建 ASR 实例并执行识别
        asr = BcutASR(str(audio_path))
        asr.upload()
        asr.create_task()
        asr_data = asr.wait_for_result()
        
        if not asr_data.has_data():
            result["error"] = "未识别到语音内容"
            return result
        
        # 获取文本和 SRT
        result["text"] = asr_data.to_txt()
        result["srt"] = asr_data.to_srt()
        result["success"] = True
        
        # 保存到文件
        if output_format == "txt":
            output_file = output_path / f"{audio_path.stem}_bcut.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result["text"])
        elif output_format == "srt":
            output_file = output_path / f"{audio_path.stem}_bcut.srt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result["srt"])
        elif output_format == "json":
            output_file = output_path / f"{audio_path.stem}_bcut.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({
                    "text": result["text"],
                    "srt": result["srt"],
                    "segments": [
                        {
                            "start": seg.start_time,
                            "end": seg.end_time,
                            "text": seg.transcript
                        }
                        for seg in asr_data.utterances
                    ]
                }, f, ensure_ascii=False, indent=2)
        else:
            output_file = output_path / f"{audio_path.stem}_bcut.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result["text"])
        
        result["output_file"] = str(output_file)
        print(f"  ✓ 转录完成，字数: {len(result['text'])}")
        
    except APIError as e:
        result["error"] = f"必剪 ASR 错误: {e}"
    except Exception as e:
        result["error"] = f"转录异常: {e}"
    
    return result


def extract_audio_ffmpeg(video_path: str, output_audio_path: str) -> bool:
    """
    使用 ffmpeg 从视频提取音频
    
    Args:
        video_path: 视频文件路径
        output_audio_path: 输出音频路径（建议 .wav 格式）
    
    Returns:
        bool: 是否成功
    """
    import subprocess
    
    try:
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            "-y", output_audio_path
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if Path(output_audio_path).exists():
            return True
    except Exception:
        pass
    
    return False


def transcribe_video_with_bcut(video_path: str, output_dir: Optional[str] = None) -> Dict:
    """
    从视频提取音频并使用必剪 ASR 转录（一站式方案）
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
    
    Returns:
        {
            "success": True/False,
            "text": "识别文本",
            "audio_file": "提取的音频路径",
            "output_file": "转录结果路径",
            "error": "错误信息"
        }
    """
    result = {
        "success": False,
        "text": "",
        "audio_file": None,
        "output_file": None,
        "error": None
    }
    
    video_path = Path(video_path)
    if not video_path.exists():
        result["error"] = f"视频文件不存在: {video_path}"
        return result
    
    # 确定输出目录
    if output_dir:
        work_dir = Path(output_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
    else:
        work_dir = video_path.parent
    
    # 提取音频
    audio_path = work_dir / f"{video_path.stem}_audio.wav"
    print(f"  从视频提取音频...")
    
    if not extract_audio_ffmpeg(str(video_path), str(audio_path)):
        result["error"] = "音频提取失败"
        return result
    
    result["audio_file"] = str(audio_path)
    print(f"  ✓ 音频提取完成: {audio_path.name}")
    
    # 使用 bcut 转录
    transcribe_result = transcribe_with_bcut(str(audio_path), str(work_dir), "txt")
    
    if transcribe_result["success"]:
        result["success"] = True
        result["text"] = transcribe_result["text"]
        result["output_file"] = transcribe_result["output_file"]
    else:
        result["error"] = transcribe_result["error"]
    
    return result
