# 依赖安装和环境配置

## Python 依赖

核心依赖（图文笔记）：
```bash
pip install undetected-chromedriver selenium
```

完整依赖（含视频笔记转录）：
```bash
pip install undetected-chromedriver selenium openai-whisper torch torchaudio soundfile scipy
```

## 各模块依赖说明

| 模块 | 依赖 | 用途 |
|------|------|------|
| xhs_api.py | undetected-chromedriver, selenium | 浏览器管理、搜索、卡片点击导航、DOM 提取 |
| downloader.py | selenium | 提取视频地址并下载（仅视频笔记） |
| transcriber.py | ffmpeg / moviepy | 视频→音频提取（仅视频笔记） |
| transcriber.py | demucs, torch | 人声分离（仅视频笔记） |
| transcriber.py | openai-whisper, soundfile, scipy | 语音识别（仅视频笔记） |

## AI 模型介绍

### Demucs (htdemucs)

- **来源**: Facebook Research (Meta AI) 开源项目
- **模型名**: `htdemucs`（Hybrid Transformer Demucs）
- **大小**: 约 80MB，首次运行时自动下载
- **功能**: 音源分离，将混合音频分离为 4 个独立音轨：vocals（人声）、drums（鼓点）、bass（贝斯）、other（其他乐器）
- **为什么需要**: 视频中通常有背景音乐和音效，直接转录识别率极低。Demucs 先分离出纯人声，再交给 Whisper 识别
- **适用范围**: 仅视频笔记需要，图文笔记不使用此模型
- **运行要求**: CPU 可运行，GPU 可加速；内存建议 8GB+

### Whisper (base)

- **来源**: OpenAI 开源项目
- **模型名**: `base`（可选 tiny/base/small/medium/large）
- **大小**: 约 140MB，首次运行时自动下载
- **功能**: 自动语音识别（ASR），将音频转为文字，支持 99 种语言，本 skill 使用中文模式 (`language="zh"`)
- **适用范围**: 仅视频笔记需要，图文笔记不使用此模型
- **模型规格对比**:

| 模型 | 参数量 | 大小 | 速度 | 准确率 |
|------|--------|------|------|--------|
| tiny | 39M | ~75MB | 最快 | 一般 |
| **base** | **74M** | **~140MB** | **快** | **较好（默认）** |
| small | 244M | ~460MB | 中等 | 好 |
| medium | 769M | ~1.5GB | 慢 | 很好 |
| large | 1550M | ~3GB | 最慢 | 最好 |

### 处理流程（仅视频笔记）

```
视频文件 → [ffmpeg] → 音频(WAV 16kHz) → [重采样44100Hz] → [Demucs htdemucs] → 人声(vocals.wav) → [Whisper base] → 转录文本
```

图文笔记直接通过 Selenium 提取标题和正文，不经过上述流程。

## Chrome 浏览器

- 必须安装 Chrome 浏览器
- 使用 undetected-chromedriver 自动管理 ChromeDriver 版本
- 自动隐藏 webdriver 特征，绕过小红书 sec 网关反爬检测

## ffmpeg 安装

- **Windows**: `choco install ffmpeg` 或从 https://ffmpeg.org/download.html 下载
- **macOS**: `brew install ffmpeg`
- **Linux**: `apt install ffmpeg`

## Cookie 获取方式

1. 打开 `https://www.xiaohongshu.com` 并登录
2. 按 F12 打开开发者工具
3. 切换到 Application → Cookies → `https://www.xiaohongshu.com`
4. 复制所有 Cookie（或在 Console 中执行 `document.cookie`）
5. Cookie 有效期有限，过期需重新获取

## 图文 vs 视频笔记

- **图文笔记**: 只需 undetected-chromedriver + selenium，从详情页 DOM 直接提取标题和正文
- **视频笔记**: 额外需要下载视频 → 提取音频 → Demucs 人声分离 → Whisper 转录
- 脚本通过详情页 DOM 中的 video 标签自动判断笔记类型

## 硬件要求

- Demucs + Whisper 转录需要较多内存（建议 8GB+）
- GPU 可加速但非必须，CPU 模式可正常运行
- 视频笔记转录约需 5-10 分钟/个（CPU模式）
- 首次运行需下载模型（htdemucs ~80MB + whisper-base ~140MB），之后缓存在本地
