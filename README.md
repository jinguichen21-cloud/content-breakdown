# 🔥 多平台爆款内容拆解器 (Content Crawler)

一站式采集和分析**小红书、抖音、B 站**三个平台的爆款内容。

## ✨ 核心特点

- **灵活的平台选择**：可以单独爬取某个平台，也可以多平台同时采集
- **多关键词搜索**：自动拓展 1 个核心关键词为 5 个相关搜索词
- **智能去重**：按标题去重，保留点赞更高的版本
- **Top N 筛选**：按点赞数排序，自动选取最优质内容
- **视频转录**：自动检测字幕 → 有字幕直接提取 / 无字幕用 Whisper 转录
- **评论分析**：抓取高赞评论，分析用户关注点
- **跨平台报告**：多平台采集时自动生成跨平台对比分析报告

## 📦 目录结构

```
skill-content-crawler/
├── SKILL.md                         # AI 指令文档
├── README.md                        # 本文件
├── scripts/
│   ├── run.py                       # 🚀 统一入口
│   ├── generate_cross_report.py     # 跨平台对比报告
│   ├── bilibili/                    # B 站采集模块
│   ├── douyin/                      # 抖音采集模块
│   └── xiaohongshu/                 # 小红书采集模块
└── references/                      # 参考文档
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install selenium undetected-chromedriver demucs openai-whisper torch torchaudio soundfile scipy
```

### 2. 配置 Cookie

脚本会自动处理 Cookie：
- 如果在配置区填入了 Cookie，直接使用
- 如果有缓存的 Cookie，自动加载
- 如果都没有，自动弹出浏览器让你登录，登录后自动提取并缓存

**Cookie 存储位置**：`scripts/<platform>/.cookie_cache/`（工作区内的相对路径）

### 3. 修改配置并运行

编辑 `scripts/run.py` 中的配置区：

```python
# 选择平台
PLATFORMS = ["bilibili", "douyin", "xiaohongshu"]  # 全平台
# PLATFORMS = ["bilibili"]                          # 仅 B 站

# 设置关键词
KEYWORDS = ["你的关键词", "关键词变体1", "关键词变体2"]

# 运行
# cd scripts && python run.py
```

## 📊 使用场景

| 场景 | 配置 |
|------|------|
| 全网爆款分析 | `PLATFORMS = ["bilibili", "douyin", "xiaohongshu"]` |
| 只看 B 站 | `PLATFORMS = ["bilibili"]` |
| 只看抖音 | `PLATFORMS = ["douyin"]` |
| 只看小红书 | `PLATFORMS = ["xiaohongshu"]` |
| 分析指定视频 | `VIDEO_URLS = ["https://..."]` |

## 📋 输出

- **单平台报告**：每个平台独立生成爆款分析报告（Markdown 格式）
- **跨平台报告**：多平台采集时自动生成对比分析报告，包含：
  - 平台数据总览表格
  - 各平台 Top 内容详情
  - 跨平台对比洞察

## ⚠️ 注意事项

1. 小红书和抖音**必须提供 Cookie** 才能正常采集
2. B 站字幕提取和评论获取也需要 Cookie
3. 首次运行会自动下载 AI 模型（Demucs ~80MB, Whisper ~140MB）
4. 需要安装 Chrome 浏览器（抖音和小红书使用浏览器自动化）
5. 需要安装 ffmpeg（音视频处理）

## 📄 License

仅供个人学习和研究使用。
