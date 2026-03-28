# -*- coding: utf-8 -*-
"""
跨平台对比分析报告生成器
汇总 B 站、抖音、小红书的采集数据，生成跨平台对比报告。
"""

import json
import os
from datetime import datetime
from pathlib import Path


PLATFORM_NAMES = {
    "bilibili": "B 站",
    "douyin": "抖音",
    "xiaohongshu": "小红书",
}

PLATFORM_ICONS = {
    "bilibili": "📺",
    "douyin": "🎵",
    "xiaohongshu": "📕",
}


def format_content_link(label, link_text, url):
    """格式化跨平台报告中的原始内容链接。"""
    if not url:
        return f"- **{label}**: 未提供"
    return f"- **{label}**: [{link_text or '查看内容'}]({url})"


def load_platform_data(result_path):
    """加载单个平台的结果数据"""
    with open(result_path, "r", encoding="utf-8") as data_file:
        raw = json.load(data_file)

    # 兼容不同平台的数据格式
    if isinstance(raw, list):
        return {"videos": raw, "keyword": "", "all_keywords": []}
    return raw


def extract_platform_stats(data, platform):
    """从平台数据中提取统计信息"""
    if platform == "xiaohongshu":
        items = data.get("notes", data.get("videos", []))
    else:
        items = data.get("videos", [])

    total_items = len(items)
    total_likes = 0
    total_comments = 0
    video_count = 0
    image_text_count = 0
    top_items = []

    for item in items:
        # 统一提取字段（不同平台字段名不同）
        if platform == "xiaohongshu":
            info = item.get("note_info", item)
            like_count = info.get("like_count", 0)
            title = info.get("title", "")
            author = info.get("author", "")
            url = info.get("url", "")
            is_video = info.get("is_video", False)
            link_label = "视频链接" if is_video else "笔记链接"
            link_text = info.get("note_id", "") or ("查看视频" if is_video else "查看笔记")
            comments = item.get("comments", [])
            transcript = item.get("transcript", "") or item.get("text_content", "")
        elif platform == "douyin":
            info = item.get("video_info", item)
            like_count = info.get("like_count", 0)
            title = info.get("title", "")
            author = info.get("author", "")
            url = info.get("url", "")
            is_video = True
            link_label = "视频链接"
            link_text = info.get("video_id", "") or "查看视频"
            comments = item.get("comments", [])
            transcript = item.get("transcript", "")
        else:  # bilibili
            like_count = item.get("like_count", 0)
            title = item.get("video_title", item.get("title", ""))
            author = item.get("author", "")
            url = item.get("video_url", item.get("url", ""))
            is_video = True
            link_label = "视频链接"
            link_text = item.get("bvid", "") or "查看视频"
            comments = item.get("comments", [])
            transcript = item.get("subtitle_text", "")

        total_likes += like_count
        total_comments += len(comments)

        if is_video:
            video_count += 1
        else:
            image_text_count += 1

        top_items.append({
            "title": title,
            "author": author,
            "url": url,
            "link_label": link_label,
            "link_text": link_text,
            "like_count": like_count,
            "comment_count": len(comments),
            "is_video": is_video,
            "transcript_length": len(transcript) if transcript else 0,
            "top_comments": [
                {
                    "content": comment.get("content", "")[:100],
                    "like_count": comment.get("like_count", 0),
                }
                for comment in sorted(comments, key=lambda c: c.get("like_count", 0), reverse=True)[:3]
            ],
        })

    # 按点赞排序
    top_items.sort(key=lambda item: item["like_count"], reverse=True)

    average_likes = total_likes // total_items if total_items > 0 else 0

    return {
        "total_items": total_items,
        "video_count": video_count,
        "image_text_count": image_text_count,
        "total_likes": total_likes,
        "average_likes": average_likes,
        "total_comments": total_comments,
        "top_items": top_items[:5],
    }


def generate_cross_platform_report(results, keywords=None, output_dir=None):
    """
    生成跨平台对比分析报告

    Args:
        results: dict, {platform: result_path} 各平台结果文件路径
        keywords: list, 搜索关键词列表
        output_dir: str, 报告输出目录

    Returns:
        str: 报告文件路径
    """
    if not results:
        print("  ⚠️ 没有可用的平台数据")
        return None

    # 加载所有平台数据
    platform_data = {}
    platform_stats = {}
    for platform, result_path in results.items():
        try:
            data = load_platform_data(result_path)
            platform_data[platform] = data
            platform_stats[platform] = extract_platform_stats(data, platform)
        except Exception as load_error:
            print(f"  ⚠️ 加载 {PLATFORM_NAMES.get(platform, platform)} 数据失败: {load_error}")

    if not platform_stats:
        print("  ⚠️ 所有平台数据加载失败")
        return None

    # 提取关键词
    if not keywords:
        for data in platform_data.values():
            keywords = data.get("all_keywords", [data.get("keyword", "")])
            if keywords:
                break
    primary_keyword = keywords[0] if keywords else "未知"

    # 构建报告
    report_lines = []
    report_lines.append("# 🔥 多平台爆款内容拆解报告\n")
    report_lines.append(f"**选题/关键词**: {primary_keyword}")
    if keywords and len(keywords) > 1:
        report_lines.append(f"**搜索关键词**: {', '.join(keywords)}")
    report_lines.append(f"**分析平台**: {', '.join(PLATFORM_NAMES.get(p, p) for p in platform_stats)}")
    report_lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("---\n")

    # 平台数据总览表格
    report_lines.append("## 📊 平台数据总览\n")
    report_lines.append("| 平台 | 内容数 | 视频数 | 图文数 | 总点赞 | 平均点赞 | 总评论 |")
    report_lines.append("|------|--------|--------|--------|--------|----------|--------|")
    for platform, stats in platform_stats.items():
        icon = PLATFORM_ICONS.get(platform, "")
        name = PLATFORM_NAMES.get(platform, platform)
        report_lines.append(
            f"| {icon} {name} | {stats['total_items']} | {stats['video_count']} | "
            f"{stats['image_text_count']} | {stats['total_likes']:,} | "
            f"{stats['average_likes']:,} | {stats['total_comments']} |"
        )
    report_lines.append("")
    report_lines.append("---\n")

    # 各平台 Top 内容详情
    for platform, stats in platform_stats.items():
        icon = PLATFORM_ICONS.get(platform, "")
        name = PLATFORM_NAMES.get(platform, platform)
        report_lines.append(f"## {icon} {name}爆款分析\n")

        top_items = stats["top_items"]
        if not top_items:
            report_lines.append("暂无数据\n")
            continue

        report_lines.append(f"### Top {len(top_items)} 爆款内容\n")
        for rank, item in enumerate(top_items, 1):
            content_type = "📹视频" if item["is_video"] else "📝图文"
            report_lines.append(f"**{rank}. [{content_type}] {item['title']}**\n")
            report_lines.append(f"- **作者**: {item['author'] or '未知'}")
            report_lines.append(f"- **点赞**: {item['like_count']:,}")
            report_lines.append(f"- **评论数**: {item['comment_count']}")
            report_lines.append(format_content_link(item["link_label"], item["link_text"], item["url"]))
            if item["transcript_length"] > 0:
                report_lines.append(f"- **转录/正文字数**: {item['transcript_length']}")

            if item["top_comments"]:
                report_lines.append(f"- **热门评论**:")
                for comment in item["top_comments"]:
                    content = comment["content"].replace("\n", " ")
                    report_lines.append(f"  - [{comment['like_count']}赞] {content}")
            report_lines.append("")

        report_lines.append("---\n")

    # 跨平台对比洞察（占位，供 AI 分析填充）
    if len(platform_stats) > 1:
        report_lines.append("## 🔄 跨平台对比洞察\n")
        report_lines.append("### 数据对比\n")

        # 找出各平台最高赞内容
        for platform, stats in platform_stats.items():
            name = PLATFORM_NAMES.get(platform, platform)
            icon = PLATFORM_ICONS.get(platform, "")
            if stats["top_items"]:
                top_item = stats["top_items"][0]
                insight_line = f"- **{icon} {name}最高赞**: [{top_item['like_count']:,}赞] {top_item['title'][:50]}"
                if top_item["url"]:
                    insight_line += f" ([查看原始内容]({top_item['url']}))"
                report_lines.append(insight_line)
        report_lines.append("")

        # 平均点赞对比
        report_lines.append("### 平均互动对比\n")
        sorted_platforms = sorted(platform_stats.items(), key=lambda item: item[1]["average_likes"], reverse=True)
        for platform, stats in sorted_platforms:
            name = PLATFORM_NAMES.get(platform, platform)
            icon = PLATFORM_ICONS.get(platform, "")
            report_lines.append(f"- {icon} {name}: 平均 {stats['average_likes']:,} 赞")
        report_lines.append("")

    report_content = "\n".join(report_lines)

    # 保存报告
    if not output_dir:
        output_dir = str(Path(__file__).parent / "output")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_filename = f"cross_platform_report_{primary_keyword}_{timestamp}.md"
    report_file_path = output_path / report_filename

    with open(report_file_path, "w", encoding="utf-8") as report_file:
        report_file.write(report_content)

    print(f"  ✅ 跨平台报告已生成: {report_file_path}")

    # 将报告内容直接输出到控制台，方便 AI 读取并展示给用户
    print(f"\n{'=' * 70}")
    print("  📋 以下是完整的跨平台对比报告内容：")
    print(f"{'=' * 70}\n")
    print(report_content)
    print(f"\n{'=' * 70}")
    print("  📋 跨平台报告内容结束")
    print(f"{'=' * 70}")

    return str(report_file_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python generate_cross_report.py <bilibili_results.json> [douyin_results.json] [xhs_results.json]")
        sys.exit(1)

    test_results = {}
    platform_order = ["bilibili", "douyin", "xiaohongshu"]
    for index, arg in enumerate(sys.argv[1:]):
        if index < len(platform_order):
            test_results[platform_order[index]] = arg

    generate_cross_platform_report(test_results)
