# -*- coding: utf-8 -*-
"""
多平台爆款内容拆解器 - 统一入口
支持单平台或多平台同时采集，通过 PLATFORMS 配置控制。
"""

import glob
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# ========== 配置区（由 AI 根据用户输入修改） ==========

# 要采集的平台列表（可选值："bilibili", "douyin", "xiaohongshu"）
# 全平台：PLATFORMS = ["bilibili", "douyin", "xiaohongshu"]
# 当前：只采集抖音和小红书（B 站已完成）
PLATFORMS = ["douyin", "xiaohongshu"]

# 关键词列表：AI 基于用户提供的核心关键词，拓展为 5 个相关搜索词
KEYWORDS = ["钉钉A1", "钉钉 AI", "钉钉智能助手", "钉钉办公 AI", "钉钉效率工具"]

# 每平台保留的内容数量（去重后取 Top N）
MAX_ITEMS = 10

# 每条内容最多抓取的评论数量
MAX_COMMENTS = 30

# 每个关键词搜索返回的结果数量
SEARCH_PER_KEYWORD = 10

# URL 直接分析模式（非空时跳过搜索，直接分析指定 URL）
VIDEO_URLS = []

# Cookie 配置（留空则自动从缓存或浏览器登录获取）
BILI_COOKIE = ""
DOUYIN_COOKIE = ""
XHS_COOKIE = ""

# ====================================================

SCRIPT_DIR = Path(__file__).parent

PLATFORM_NAMES = {
    "bilibili": "📺 B 站",
    "douyin": "🎵 抖音",
    "xiaohongshu": "📕 小红书",
}


def build_config(platform):
    """为指定平台构建 config 字典"""
    cookie_map = {
        "bilibili": BILI_COOKIE,
        "douyin": DOUYIN_COOKIE,
        "xiaohongshu": XHS_COOKIE,
    }
    return {
        "keywords": KEYWORDS,
        "video_urls": VIDEO_URLS,
        "max_videos": MAX_ITEMS,
        "max_comments": MAX_COMMENTS,
        "search_per_keyword": SEARCH_PER_KEYWORD,
        "cookie": cookie_map.get(platform, ""),
    }


def run_platform(platform):
    """运行单个平台的采集流程，返回结果文件路径"""
    platform_dir = SCRIPT_DIR / platform
    if not platform_dir.exists():
        print(f"  ✗ 平台目录不存在：{platform_dir}")
        return None

    # 将平台目录加入 sys.path（确保平台内部 import 正常）
    platform_dir_str = str(platform_dir)
    if platform_dir_str not in sys.path:
        sys.path.insert(0, platform_dir_str)

    try:
        if platform == "bilibili":
            from bilibili.run import run
        elif platform == "douyin":
            from douyin.run import run
        elif platform == "xiaohongshu":
            from xiaohongshu.run import run
        else:
            print(f"  ✗ 未知平台：{platform}")
            return None

        config = build_config(platform)
        result_path = run(config)
        return result_path

    except Exception as error:
        print(f"\n  ✗ {PLATFORM_NAMES.get(platform, platform)} 采集失败：{error}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """主入口：按顺序执行各平台采集，最后生成跨平台报告"""
    total_start = time.time()

    print("\n" + "=" * 70)
    print("  🔥 多平台爆款内容拆解器")
    print(f"  平台：{', '.join(PLATFORM_NAMES.get(p, p) for p in PLATFORMS)}")
    print(f"  关键词 ({len(KEYWORDS)}个): {KEYWORDS}")
    print(f"  每平台保留：Top {MAX_ITEMS} | 每内容评论：{MAX_COMMENTS}")
    print("=" * 70)

    results = {}

    for platform_index, platform in enumerate(PLATFORMS, 1):
        platform_name = PLATFORM_NAMES.get(platform, platform)
        print(f"\n{'━' * 70}")
        print(f"  [{platform_index}/{len(PLATFORMS)}] 开始采集 {platform_name}")
        print(f"{'━' * 70}")

        platform_start = time.time()
        result_path = run_platform(platform)
        platform_elapsed = time.time() - platform_start

        if result_path:
            results[platform] = result_path
            print(f"\n  ✅ {platform_name} 采集完成 (耗时 {platform_elapsed:.1f}s)")
            print(f"     数据文件：{result_path}")
        else:
            print(f"\n  ❌ {platform_name} 采集失败 (耗时 {platform_elapsed:.1f}s)")

    # 生成跨平台报告（仅当多平台时）
    if len(results) > 1:
        print(f"\n{'━' * 70}")
        print(f"  生成跨平台对比报告...")
        print(f"{'━' * 70}")
        try:
            from generate_cross_report import generate_cross_platform_report
            report_path = generate_cross_platform_report(
                results,
                keywords=KEYWORDS,
                output_dir=str(SCRIPT_DIR / "output"),
            )
            if report_path:
                print(f"  ✅ 跨平台报告：{report_path}")
        except Exception as report_error:
            print(f"  ⚠️ 跨平台报告生成失败：{report_error}")
    elif len(results) == 1:
        # 单平台模式：读取该平台的报告文件并输出到控制台
        platform = list(results.keys())[0]
        platform_name = PLATFORM_NAMES.get(platform, platform)
        result_path = results[platform]
        # 查找对应的报告文件（在平台的 output/report 目录下）
        report_dir = SCRIPT_DIR / platform / "output" / "report"
        if report_dir.exists():
            report_files = sorted(glob.glob(str(report_dir / "*.md")), key=os.path.getmtime, reverse=True)
            if report_files:
                latest_report = report_files[0]
                try:
                    with open(latest_report, "r", encoding="utf-8") as report_file:
                        single_report_content = report_file.read()
                    print(f"\n{'=' * 70}")
                    print(f"  📋 以下是 {platform_name} 的完整分析报告内容：")
                    print(f"{'=' * 70}\n")
                    print(single_report_content)
                    print(f"\n{'=' * 70}")
                    print(f"  📋 {platform_name} 报告内容结束")
                    print(f"{'=' * 70}")
                except Exception as read_error:
                    print(f"  ⚠️ 读取报告文件失败：{read_error}")

    total_elapsed = time.time() - total_start

    print(f"\n{'=' * 70}")
    print(f"  ✅ 全部完成！")
    print(f"  成功平台：{len(results)}/{len(PLATFORMS)}")
    for platform, path in results.items():
        print(f"    {PLATFORM_NAMES.get(platform, platform)}: {path}")
    print(f"  总耗时：{total_elapsed:.1f}s")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
