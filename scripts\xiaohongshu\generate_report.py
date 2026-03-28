# -*- coding: utf-8 -*-
"""小红书爆款内容分析报告生成器

读取采集的 JSON 数据，生成 Markdown 格式的爆款分析报告。
支持独立运行，也可被 run.py 调用。
"""

import json
import os
import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List


def format_content_link(label: str, link_text: str, url: str) -> str:
    """格式化报告中的原始内容链接。"""
    if not url:
        return f"- **{label}**: 未提供"
    return f"- **{label}**: [{link_text or '查看内容'}]({url})"

def load_data(json_path: str) -> Dict[str, Any]:
    """加载采集的 JSON 数据"""
    with open(json_path, "r", encoding="utf-8") as json_file:
        return json.load(json_file)

def extract_keyword_from_filename(filename: str) -> str:
    """从文件名中提取关键词"""
    # 尝试从 results.json 或 note 目录名中提取
    match = re.search(r"output[\\/]([^\\/]+)[\\/]", filename)
    if match:
        return match.group(1)
    return "unknown"

def analyze_comments(notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """分析所有笔记的评论，提取高频关键词和用户关注点"""
    all_comment_texts = []
    total_comment_likes = 0
    total_comments = 0
    top_comments_across_notes = []

    for note in notes:
        comments = note.get("comments", [])
        note_title = note.get("note_info", {}).get("title", "")
        for comment in comments:
            content = comment.get("content", "")
            like_count = comment.get("like_count", 0)
            all_comment_texts.append(content)
            total_comment_likes += like_count
            total_comments += 1
            top_comments_across_notes.append({
                "content": content,
                "like_count": like_count,
                "author": comment.get("author", ""),
                "note_title": note_title,
            })

    top_comments_across_notes.sort(key=lambda item: item["like_count"], reverse=True)

    # 提取高频词（简单的中文分词：按标点和空格切分，过滤短词）
    word_counter = Counter()
    stop_words = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
                  "上", "也", "到", "说", "要", "会", "可以", "这", "个", "你", "那", "他", "她",
                  "它", "们", "吗", "吧", "啊", "呢", "哈", "嗯", "哦", "呀", "啦", "嘛", "么",
                  "被", "把", "让", "给", "用", "对", "从", "但", "而", "还", "很", "太", "真",
                  "好", "大", "小", "多", "少", "这个", "那个", "什么", "怎么", "为什么", "没有",
                  "不是", "可以", "已经", "自己", "知道", "觉得", "其实", "因为", "所以", "如果",
                  "就是", "还是", "或者", "然后", "但是", "虽然", "不过", "只是", "比较", "应该"}

    for text in all_comment_texts:
        # 简单切分：按非中文字符和标点分割
        segments = re.findall(r'[\u4e00-\u9fff]{2,8}', text)
        for segment in segments:
            if segment not in stop_words and len(segment) >= 2:
                word_counter[segment] += 1

    return {
        "total_comments": total_comments,
        "total_comment_likes": total_comment_likes,
        "average_comment_likes": total_comment_likes / max(total_comments, 1),
        "top_comments": top_comments_across_notes[:20],
        "hot_words": word_counter.most_common(30),
    }

def analyze_content(notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """分析笔记内容（转录文本 + 图文正文），提取关键主题"""
    content_notes = []
    total_content_chars = 0
    
    for note in notes:
        # 视频笔记使用转录文本，图文笔记使用正文
        content_text = note.get("transcript", "") or note.get("text_content", "")
        if content_text:
            content_notes.append(note)
            total_content_chars += len(content_text)

    # 提取内容中的高频词
    word_counter = Counter()
    stop_words = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
                  "上", "也", "到", "说", "要", "会", "可以", "这", "个", "你", "那", "他", "她",
                  "它", "们", "吗", "吧", "啊", "呢", "哈", "嗯", "哦", "呀", "啦", "嘛", "么",
                  "被", "把", "让", "给", "用", "对", "从", "但", "而", "还", "很", "太", "真",
                  "好", "大", "小", "多", "少", "这个", "那个", "什么", "怎么", "为什么", "没有",
                  "不是", "可以", "已经", "自己", "知道", "觉得", "其实", "因为", "所以", "如果",
                  "就是", "还是", "或者", "然后", "但是", "虽然", "不过", "只是", "比较", "应该",
                  "我们", "他们", "这样", "那么", "一下", "起来", "出来", "进去", "下来", "过来",
                  "今天", "现在", "时候", "东西", "事情", "问题", "开始", "之后", "之前", "里面",
                  "上面", "下面", "这里", "那里", "这些", "那些", "大家", "非常", "其中", "通过"}

    for note in content_notes:
        content_text = note.get("transcript", "") or note.get("text_content", "")
        segments = re.findall(r'[\u4e00-\u9fff]{2,8}', content_text)
        for segment in segments:
            if segment not in stop_words and len(segment) >= 2:
                word_counter[segment] += 1

    return {
        "content_note_count": len(content_notes),
        "total_content_chars": total_content_chars,
        "hot_topics": word_counter.most_common(30),
    }

def generate_report(data: Dict[str, Any], keyword: str) -> str:
    """生成 Markdown 格式的爆款分析报告"""
    notes = data.get("notes", [])
    comment_analysis = analyze_comments(notes)
    content_analysis = analyze_content(notes)

    total_likes = sum(note.get("note_info", {}).get("like_count", 0) for note in notes)
    total_collects = sum(note.get("note_info", {}).get("collect_count", 0) for note in notes)
    average_likes = total_likes / max(len(notes), 1)
    total_comments = comment_analysis["total_comments"]
    content_count = content_analysis["content_note_count"]
    video_count = sum(1 for note in notes if note.get("note_info", {}).get("is_video"))
    image_text_count = len(notes) - video_count

    # 按点赞排序
    sorted_notes = sorted(notes, key=lambda note: note.get("note_info", {}).get("like_count", 0), reverse=True)

    report_lines = []

    # 标题
    report_lines.append(f"# 🔥 小红书爆款内容拆解报告")
    report_lines.append("")
    report_lines.append(f"**选题/关键词**: {keyword}")
    all_keywords = data.get("all_keywords", [])
    if all_keywords and len(all_keywords) > 1:
        report_lines.append(f"**搜索关键词**: {', '.join(all_keywords)}")
    report_lines.append(f"**平台**: 小红书 (xiaohongshu.com)")
    report_lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    # 数据总览
    report_lines.append("## 📊 数据总览")
    report_lines.append("")
    report_lines.append(f"| 指标 | 数值 |")
    report_lines.append(f"|------|------|")
    report_lines.append(f"| 分析笔记数 | {len(notes)} |")
    report_lines.append(f"| 视频笔记 | {video_count} |")
    report_lines.append(f"| 图文笔记 | {image_text_count} |")
    report_lines.append(f"| 总点赞数 | {total_likes:,} |")
    report_lines.append(f"| 总收藏数 | {total_collects:,} |")
    report_lines.append(f"| 平均点赞数 | {average_likes:,.0f} |")
    report_lines.append(f"| 内容提取成功 | {content_count}/{len(notes)} |")
    report_lines.append(f"| 总评论数 | {total_comments} |")
    report_lines.append(f"| 总内容字符数 | {content_analysis['total_content_chars']:,} |")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    # Top 笔记排行
    report_lines.append("## 🏆 Top 笔记排行")
    report_lines.append("")
    for rank, note in enumerate(sorted_notes, 1):
        note_info = note.get("note_info", {})
        title = note_info.get("title", "")
        author = note_info.get("author", "")
        like_count = note_info.get("like_count", 0)
        collect_count = note_info.get("collect_count", 0)
        comment_count = note_info.get("comment_count", 0)
        note_url = note_info.get("url", "")
        is_video = note_info.get("is_video", False)
        content_type = "📹视频" if is_video else "📝图文"
        link_label = "视频链接" if is_video else "笔记链接"
        link_text = note_info.get("note_id", "") or ("查看视频" if is_video else "查看笔记")
        content_status = "✅" if (note.get("transcript") or note.get("text_content")) else "❌"

        report_lines.append(f"### {rank}. {title}")
        report_lines.append("")
        report_lines.append(f"- **作者**: {author}")
        report_lines.append(f"- **类型**: {content_type}")
        report_lines.append(f"- **点赞**: {like_count:,}")
        report_lines.append(f"- **收藏**: {collect_count:,}")
        report_lines.append(f"- **评论数**: {comment_count}")
        report_lines.append(f"- **内容**: {content_status}")
        report_lines.append(format_content_link(link_label, link_text, note_url))
        report_lines.append("")

        # 显示内容摘要（前 200 字）
        content_text = note.get("transcript", "") or note.get("text_content", "")
        if content_text:
            content_preview = content_text[:200].replace("\n", " ")
            report_lines.append(f"> 📝 **内容摘要**: {content_preview}...")
            report_lines.append("")

        # 显示该笔记的 Top 5 评论
        comments = note.get("comments", [])
        if comments:
            report_lines.append(f"**热门评论 Top 5:**")
            report_lines.append("")
            for cidx, comment in enumerate(comments[:5], 1):
                content = comment.get("content", "").replace("\n", " ")[:120]
                comment_author = comment.get("author", "")
                comment_likes = comment.get("like_count", 0)
                report_lines.append(f"{cidx}. 「{content}」 —— {comment_author} (👍{comment_likes})")
            report_lines.append("")

    report_lines.append("---")
    report_lines.append("")

    # 评论区分析
    report_lines.append("## 💬 评论区深度分析")
    report_lines.append("")

    # 全网最热评论 Top 10
    report_lines.append("### 全网最热评论 Top 10")
    report_lines.append("")
    for idx, comment in enumerate(comment_analysis["top_comments"][:10], 1):
        content = comment["content"].replace("\n", " ")[:150]
        report_lines.append(f"{idx}. 「{content}」")
        report_lines.append(f"   —— {comment['author']} (👍{comment['like_count']}) | 来自《{comment['note_title'][:30]}》")
        report_lines.append("")

    # 评论高频词
    report_lines.append("### 评论高频关键词")
    report_lines.append("")
    report_lines.append("| 排名 | 关键词 | 出现次数 |")
    report_lines.append("|------|--------|----------|")
    for rank, (word, count) in enumerate(comment_analysis["hot_words"][:20], 1):
        report_lines.append(f"| {rank} | {word} | {count} |")
    report_lines.append("")

    report_lines.append("---")
    report_lines.append("")

    # 内容分析
    report_lines.append("## 📝 内容分析")
    report_lines.append("")
    report_lines.append("### 笔记内容高频主题词")
    report_lines.append("")
    report_lines.append("| 排名 | 主题词 | 出现次数 |")
    report_lines.append("|------|--------|----------|")
    for rank, (word, count) in enumerate(content_analysis["hot_topics"][:20], 1):
        report_lines.append(f"| {rank} | {word} | {count} |")
    report_lines.append("")

    report_lines.append("---")
    report_lines.append("")

    # 爆款特征总结
    report_lines.append("## 🎯 爆款特征总结")
    report_lines.append("")

    # 标题特征分析
    report_lines.append("### 标题特征")
    report_lines.append("")
    title_lengths = [len(note.get("note_info", {}).get("title", "")) for note in notes]
    average_title_length = sum(title_lengths) / max(len(title_lengths), 1)

    # 统计标题中的常见元素
    titles = [note.get("note_info", {}).get("title", "") for note in notes]
    emoji_count = sum(1 for title in titles if re.search(r'[\U0001F300-\U0001F9FF]', title))
    bracket_count = sum(1 for title in titles if re.search(r'[【】\[\]]', title))
    question_count = sum(1 for title in titles if "？" in title or "?" in title)
    exclamation_count = sum(1 for title in titles if "！" in title or "!" in title)

    report_lines.append(f"- **平均标题长度**: {average_title_length:.0f} 字")
    report_lines.append(f"- **使用 Emoji**: {emoji_count}/{len(notes)} 个笔记")
    report_lines.append(f"- **使用【】括号**: {bracket_count}/{len(notes)} 个笔记")
    report_lines.append(f"- **使用问号**: {question_count}/{len(notes)} 个笔记")
    report_lines.append(f"- **使用感叹号**: {exclamation_count}/{len(notes)} 个笔记")
    report_lines.append("")

    # 标题关键词
    report_lines.append("### 标题常见关键词")
    report_lines.append("")
    title_word_counter = Counter()
    for title in titles:
        title_segments = re.findall(r'[\u4e00-\u9fff]{2,6}', title)
        for segment in title_segments:
            title_word_counter[segment] += 1

    common_title_words = [f"**{word}**({count}次)" for word, count in title_word_counter.most_common(15) if count >= 2]
    if common_title_words:
        report_lines.append(f"高频标题词: {', '.join(common_title_words)}")
    else:
        report_lines.append("标题用词较为分散，无明显高频词")
    report_lines.append("")

    # 互动数据分析
    report_lines.append("### 互动数据特征")
    report_lines.append("")
    like_counts = [note.get("note_info", {}).get("like_count", 0) for note in notes]
    collect_counts = [note.get("note_info", {}).get("collect_count", 0) for note in notes]
    report_lines.append(f"- **最高点赞**: {max(like_counts):,}")
    report_lines.append(f"- **最低点赞**: {min(like_counts):,}")
    report_lines.append(f"- **平均点赞**: {average_likes:,.0f}")
    report_lines.append(f"- **中位数点赞**: {sorted(like_counts)[len(like_counts) // 2]:,}")
    report_lines.append(f"- **总收藏**: {sum(collect_counts):,}")
    report_lines.append("")

    report_lines.append("---")
    report_lines.append("")

    # 可复制的爆款公式
    report_lines.append("## 🔑 可复制的爆款公式")
    report_lines.append("")
    report_lines.append("基于以上数据分析，总结出以下可复制的创作建议：")
    report_lines.append("")
    report_lines.append(f"1. **标题策略**: 平均 {average_title_length:.0f} 字标题，善用【】括号突出关键信息，适当使用问号引发好奇心")
    report_lines.append(f"2. **内容定位**: 围绕「{keyword}」的核心话题，结合教程、测评、深度解读等形式")

    # 根据评论高频词推断用户关注点
    if comment_analysis["hot_words"]:
        top_concerns = [word for word, _ in comment_analysis["hot_words"][:5]]
        report_lines.append(f"3. **用户关注点**: 评论区高频讨论 {', '.join(top_concerns)} 等话题")

    if content_analysis["hot_topics"]:
        top_topics = [word for word, _ in content_analysis["hot_topics"][:5]]
        report_lines.append(f"4. **内容主题**: 笔记内容集中在 {', '.join(top_topics)} 等方向")

    report_lines.append(f"5. **互动策略**: 头部笔记点赞 {max(like_counts):,}，建议在评论区积极互动提升热度")
    report_lines.append("")

    return "\n".join(report_lines)

def generate_and_save_report(json_path: str, output_dir: str = None):
    """生成报告并保存到文件，返回 (报告文件路径, 报告内容) 元组"""
    data = load_data(json_path)
    keyword = data.get("keyword", extract_keyword_from_filename(json_path))

    report_content = generate_report(data, keyword)

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "report")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_filename = f"xhs_report_{keyword}_{timestamp}.md"
    report_path = os.path.join(output_dir, report_filename)

    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write(report_content)

    return report_path, report_content

if __name__ == "__main__":
    import sys
    import glob

    if len(sys.argv) > 1:
        input_json_path = sys.argv[1]
    else:
        # 自动查找最新的 results.json 文件
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        json_files = glob.glob(os.path.join(output_dir, "*", "results.json"))
        if not json_files:
            print("❌ 未找到数据文件，请先运行 run.py 采集数据")
            sys.exit(1)
        input_json_path = max(json_files, key=os.path.getmtime)
        print(f"📂 自动选择最新数据文件: {input_json_path}")

    print(f"📊 正在生成报告...")
    saved_report_path = generate_and_save_report(input_json_path)
    print(f"✅ 报告已生成: {saved_report_path}")
