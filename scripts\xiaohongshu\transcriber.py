# -*- coding: utf-8 -*-
"""Demucs + Whisper 转录模块 — 从视频提取音频 → 人声分离 → 语音识别"""

import os
import subprocess
import sys
from pathlib import Path


def extract_audio_from_video(video_path: Path, output_path: Path) -> bool:
    """从视频中提取音频（WAV 16kHz 单声道）"""
    if output_path.exists():
        print(f"  音频已存在: {output_path}")
        return True

    print("  从视频提取音频...")

    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-y",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if output_path.exists():
            print(f"  ✓ 音频提取完成: {output_path}")
            return True
    except FileNotFoundError:
        pass
    except Exception as ffmpeg_error:
        print(f"  ffmpeg 错误: {ffmpeg_error}")

    try:
        from moviepy import VideoFileClip
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "moviepy"])
        from moviepy import VideoFileClip

    try:
        try:
            import imageio_ffmpeg
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "imageio-ffmpeg"])
            import imageio_ffmpeg
        os.environ["IMAGEIO_FFMPEG_EXE"] = imageio_ffmpeg.get_ffmpeg_exe()

        video = VideoFileClip(str(video_path))
        video.audio.write_audiofile(str(output_path), fps=16000, nbytes=2, codec="pcm_s16le")
        video.close()
        if output_path.exists():
            print(f"  ✓ 音频提取完成 (moviepy): {output_path}")
            return True
    except Exception as moviepy_error:
        print(f"  ✗ moviepy 提取失败: {moviepy_error}")

    return False


def separate_vocals_demucs(audio_path: Path, output_dir: Path) -> Path | None:
    """使用 Demucs 分离人声"""
    wav_path = audio_path.parent / f"{audio_path.stem}_converted.wav"
    if not wav_path.exists():
        try:
            import soundfile as sf
            from scipy import signal as scipy_signal
            data, samplerate = sf.read(str(audio_path))
            if samplerate != 44100:
                num_samples = int(len(data) * 44100 / samplerate)
                if len(data.shape) == 1:
                    data = scipy_signal.resample(data, num_samples)
                else:
                    data = scipy_signal.resample(data, num_samples, axis=0)
            sf.write(str(wav_path), data, 44100)
        except Exception as convert_error:
            print(f"  ✗ 音频转换失败: {convert_error}")
            return None

    vocals_dir = output_dir / "htdemucs" / wav_path.stem
    vocals_path = vocals_dir / "vocals.wav"
    if vocals_path.exists():
        print(f"  人声文件已存在: {vocals_path}")
        return vocals_path

    print("  使用 Demucs 分离人声...")
    try:
        import torch
        import numpy as np
        import soundfile as sf
        from scipy import signal as scipy_signal
        from demucs.pretrained import get_model
        from demucs.apply import apply_model

        model = get_model("htdemucs")
        model.eval()
        device = torch.device("cpu")
        model.to(device)

        data, sample_rate = sf.read(str(wav_path))
        if len(data.shape) == 1:
            waveform = torch.from_numpy(data).float().unsqueeze(0).repeat(2, 1)
        else:
            waveform = torch.from_numpy(data.T).float()
            if waveform.shape[0] == 1:
                waveform = waveform.repeat(2, 1)

        if sample_rate != model.samplerate:
            num_samples = int(waveform.shape[1] * model.samplerate / sample_rate)
            waveform_np = waveform.numpy()
            resampled = np.zeros((waveform_np.shape[0], num_samples))
            for channel_idx in range(waveform_np.shape[0]):
                resampled[channel_idx] = scipy_signal.resample(waveform_np[channel_idx], num_samples)
            waveform = torch.from_numpy(resampled).float()

        if waveform.shape[0] == 1:
            waveform = waveform.repeat(2, 1)

        waveform = waveform.unsqueeze(0).to(device)

        print("  分离人声中（可能需要几分钟）...")
        with torch.no_grad():
            sources = apply_model(model, waveform, device=device)

        vocals = sources[0, -1]
        vocals_dir.mkdir(parents=True, exist_ok=True)
        vocals_np = vocals.cpu().numpy().T
        sf.write(str(vocals_path), vocals_np, model.samplerate)
        print(f"  ✓ 人声分离完成: {vocals_path}")
        return vocals_path

    except Exception as demucs_error:
        print(f"  ✗ Demucs 错误: {demucs_error}")
        import traceback
        traceback.print_exc()
        return None


def transcribe_whisper(audio_path: Path, model_name: str = "base") -> dict | None:
    """使用 OpenAI Whisper 进行语音识别"""
    print(f"  使用 Whisper ({model_name}) 转录...")
    try:
        import whisper
        import numpy as np
        import soundfile as sf

        model = whisper.load_model(model_name)
        audio_data, sample_rate = sf.read(str(audio_path))

        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)
        if sample_rate != 16000:
            from scipy import signal as scipy_signal
            num_samples = int(len(audio_data) * 16000 / sample_rate)
            audio_data = scipy_signal.resample(audio_data, num_samples)

        audio_data = audio_data.astype(np.float32)
        result = model.transcribe(audio_data, language="zh", verbose=False)

        return {
            "text": result.get("text", ""),
            "segments": result.get("segments", []),
            "model": f"whisper-{model_name}",
        }
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "openai-whisper"])
        return transcribe_whisper(audio_path, model_name)
    except Exception as whisper_error:
        print(f"  ✗ Whisper 错误: {whisper_error}")
        return None


def process_video(video_dir: Path, skip_vocal_separation: bool = True) -> dict:
    """
    完整处理单个视频：提取音频 → [可选：人声分离] → Whisper 转录
    
    参数:
        video_dir: 视频所在目录
        skip_vocal_separation: 是否跳过人声分离（默认 True，直接转录音频）
    """
    result = {"video_dir": str(video_dir), "success": False, "transcript": ""}

    video_path = None
    for ext in ["mp4", "webm", "mkv", "avi", "mov"]:
        candidate = video_dir / f"video.{ext}"
        if candidate.exists():
            video_path = candidate
            break

    if not video_path:
        result["error"] = "未找到视频文件"
        return result

    audio_path = video_dir / "audio.wav"
    if not extract_audio_from_video(video_path, audio_path):
        result["error"] = "音频提取失败"
        return result

    # 根据配置决定是否进行人声分离
    transcribe_audio_path = audio_path
    if not skip_vocal_separation:
        vocals_path = separate_vocals_demucs(audio_path, video_dir)
        if vocals_path:
            transcribe_audio_path = vocals_path
        else:
            print("  ⚠️ 人声分离失败，使用原始音频继续转录")
    else:
        print("  ℹ️ 跳过人声分离，直接转录音频")

    transcript = transcribe_whisper(transcribe_audio_path, "base")
    if transcript:
        result["success"] = True
        result["transcript"] = transcript.get("text", "")

        transcript_path = video_dir / "transcript.txt"
        with open(transcript_path, "w", encoding="utf-8") as transcript_file:
            transcript_file.write(result["transcript"])
        print(f"  ✓ 转录完成，字数: {len(result['transcript'])}")
    else:
        result["error"] = "Whisper 转录失败"

    return result
