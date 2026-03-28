# -*- coding: utf-8 -*-
"""抖音爆款内容分析报告生成器

读取采集的 JSON 数据，生成 Markdown 格式的爆款分析报告。
支持独立运行，也可被 run.py 调用。
"""

import json
import os
import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List

# 简繁转换字典（常用字）
TRADITIONAL_TO_SIMPLIFIED = {
    '強': '强', '別': '别', '風': '风', '裝': '装', '舉': '举', '麼': '么', '當': '当',
    '然': '然', '鮮': '鲜', '是': '是', '沒': '没', '錯': '错', '如': '如', '果': '果',
    '看': '看', '完': '完', '視': '视', '頻': '频', '大': '大', '家': '家', '還': '还',
    '想': '想', '試': '试', '我': '我', '妹': '妹', '在': '在', '後': '后',
    '面': '面', '給': '给', '了': '了', '些': '些', '使': '使', '用': '用', '的': '的',
    '建': '建', '議': '议', '首': '首', '先': '先', '毫': '毫', '不': '不', '誇': '夸',
    '張': '张', '時': '时', '產': '产', '品': '品', '只': '只', '要': '要',
    '把': '把', '它': '它', '電': '电', '腦': '脑', '上': '上', '或': '或',
    '者': '者', '輸': '输', '到': '到', '隱': '隐', '瞻': '瞻', '咱': '咱',
    '聊': '聊', '天': '天', '軟': '软', '件': '件', '裡': '里', '都': '都',
    '弄': '弄', '嘴': '嘴', '皮': '皮', '子': '子', '這': '这', '個': '个', '做': '做',
    '手': '手', '就': '就', '能': '能', '幫': '帮', '你': '你', '完': '完', '成': '成',
    '任': '任', '務': '务', '前': '前', '提': '提',
    '小': '小', '時': '时', '全': '全', '線': '线',
    '位': '位', '又': '又', '因': '因', '為': '为',
    '單': '单', '有': '有', '龍': '龙', '蝦': '虾', '前': '前',
    '資': '资', '說': '说', '實': '实', '話': '话', '讓': '让',
    '們': '们', '來': '来', '認': '认', '識': '识', '一': '一', '下': '下',
    '東': '东', '西': '西', '底': '底', '什': '什',
    '火': '火', '現': '现', '在': '在',
    '起': '起', '開': '开', '始': '始', '體': '体', '驗': '验', '吧': '吧', '覺': '觉',
    '得': '得', '樣': '样', '點': '点', '擊': '击',
    '關': '关', '註': '注', '讚': '赞', '賞': '赏', '評': '评', '論': '论', '轉': '转',
    '發': '发', '購': '购', '買': '买', '賣': '卖', '錢': '钱', '賺': '赚',
    '費': '费', '廣': '广', '告': '告', '歡': '欢', '迎': '迎', '謝': '谢',
    '請': '请', '問': '问', '嗎': '吗', '呢': '呢', '啊': '啊', '呀': '呀',
    '啦': '啦', '哦': '哦', '噢': '噢', '嘿': '嘿', '嗨': '嗨', '嗯': '嗯', '嘛': '嘛',
    '咯': '咯', '嘍': '喽', '唄': '呗', '啵': '啵', '嘞': '嘞', '啰': '啰',
    '確': '确', '定': '定', '你': '你', '真': '真', '跟': '跟', '甚': '甚', '至': '至',
    '說': '说', '著': '着', '折': '折', '騰': '腾', '常': '常', '沒': '没', '錯': '错',
    '如': '如', '果': '果', '還': '还', '想': '想', '試': '试', '我': '我', '妹': '妹',
    '在': '在', '後': '后', '面': '面', '給': '给', '了': '了', '些': '些', '使': '使',
    '用': '用', '的': '的', '建': '建', '議': '议', '首': '首', '先': '先', '毫': '毫',
    '不': '不', '誇': '夸', '張': '张', '時': '时', '候': '候', '是': '是', '今': '今',
    '年': '年', '目': '目', '為': '为', '止': '止', '最': '最', '火': '火', '的': '的', 'AI': 'AI',
    '產': '产', '品': '品', '只': '只', '要': '要', '把': '把', '它': '它', '裝': '装', '在': '在',
    '電': '电', '腦': '脑', '上': '上', '或': '或', '者': '者', '不': '不', '輸': '输', '到': '到',
    '隱': '隐', '瞻': '瞻', '咱': '咱', '在': '在', '聊': '聊', '天': '天', '軟': '软',
    '件': '件', '裡': '里', '都': '都', '弄': '弄', '嘴': '嘴', '皮': '皮', '子': '子',
    '這': '这', '個': '个', '做': '做', '手': '手', '就': '就', '能': '能', '幫': '帮',
    '你': '你', '完': '完', '成': '成', '任': '任', '務': '务', '當': '当', '然': '然',
    '前': '前', '提': '提', '是': '是', '大': '大', '家': '家', '小': '小', '時': '时',
    '全': '全', '線': '线', '都': '都', '給': '给', '到': '到', '位': '位', '了': '了',
    '又': '又', '因': '因', '為': '为', '這': '这', '個': '个', '單': '单', '子': '子',
    '有': '有', '龍': '龙', '蝦': '虾', '資': '资', '的': '的',
}

def traditional_to_simplified(text: str) -> str:
    """将繁体中文转换为简体中文"""
    if not text:
        return text
    result = []
    for char in text:
        result.append(TRADITIONAL_TO_SIMPLIFIED.get(char, char))
    return ''.join(result)


def format_content_link(label: str, link_text: str, url: str) -> str:
    """格式化报告中的原始内容链接。"""
    if not url:
        return f"- **{label}**: 未提供"
    return f"- **{label}**: [{link_text or '查看视频'}]({url})"


def load_data(json_path: str) -> Dict[str, Any]:
    """加载采集的 JSON 数据"""
    with open(json_path, "r", encoding="utf-8") as json_file:
        return json.load(json_file)


def analyze_comments(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """分析所有视频的评论，提取高频关键词和用户关注点"""
    all_comment_texts = []
    total_comment_likes = 0
    total_comments = 0
    top_comments_across_videos = []

    for video in videos:
        comments = video.get("comments", [])
        video_title = video.get("video_info", {}).get("title", "")
        for comment in comments:
            content = comment.get("content", "")
            like_count = comment.get("like_count", 0)
            all_comment_texts.append(content)
            total_comment_likes += like_count
            total_comments += 1
            top_comments_across_videos.append({
                "content": content,
                "like_count": like_count,
                "author": comment.get("author", ""),
                "video_title": video_title,
            })

    top_comments_across_videos.sort(key=lambda item: item["like_count"], reverse=True)

    # 提取高频词（简单的中文分词：按标点和空格切分，过滤短词）
    word_counter = Counter()
    stop_words = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
        "上", "也", "到", "说", "要", "会", "可以", "这", "个", "你", "那", "他", "她",
        "它", "们", "吗", "吧", "啊", "呢", "哈", "嗯", "哦", "呀", "啦", "嘛", "么",
        "被", "把", "让", "给", "用", "对", "从", "但", "而", "还", "很", "太", "真",
        "好", "大", "小", "多", "少", "这个", "那个", "什么", "怎么", "为什么", "没有",
        "不是", "可以", "已经", "自己", "知道", "觉得", "其实", "因为", "所以", "如果",
        "就是", "还是", "或者", "然后", "但是", "虽然", "不过", "只是", "比较", "应该",
    }

    for text in all_comment_texts:
        segments = re.findall(r'[\u4e00-\u9fff]{2,8}', text)
        for segment in segments:
            if segment not in stop_words and len(segment) >= 2:
                word_counter[segment] += 1

    return {
        "total_comments": total_comments,
        "total_comment_likes": total_comment_likes,
        "average_comment_likes": total_comment_likes / max(total_comments, 1),
        "top_comments": top_comments_across_videos[:20],
        "hot_words": word_counter.most_common(30),
    }


def analyze_content(videos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """分析视频内容（转录文本），提取关键主题"""
    content_videos = []
    total_content_chars = 0

    for video in videos:
        transcript = video.get("transcript", "")
        if transcript:
            content_videos.append(video)
            total_content_chars += len(transcript)

    # 提取内容中的高频词
    word_counter = Counter()
    stop_words = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
        "上", "也", "到", "说", "要", "会", "可以", "这", "个", "你", "那", "他", "她",
        "它", "们", "吗", "吧", "啊", "呢", "哈", "嗯", "哦", "呀", "啦", "嘛", "么",
        "被", "把", "让", "给", "用", "对", "从", "但", "而", "还", "很", "太", "真",
        "好", "大", "小", "多", "少", "这个", "那个", "什么", "怎么", "为什么", "没有",
        "不是", "可以", "已经", "自己", "知道", "觉得", "其实", "因为", "所以", "如果",
        "就是", "还是", "或者", "然后", "但是", "虽然", "不过", "只是", "比较", "应该",
        "我们", "他们", "这样", "那么", "一下", "起来", "出来", "进去", "下来", "过来",
        "今天", "现在", "时候", "东西", "事情", "问题", "开始", "之后", "之前", "里面",
        "上面", "下面", "这里", "那里", "这些", "那些", "大家", "非常", "其中", "通过",
    }

    for video in content_videos:
        transcript = video.get("transcript", "")
        segments = re.findall(r'[\u4e00-\u9fff]{2,8}', transcript)
        for segment in segments:
            if segment not in stop_words and len(segment) >= 2:
                word_counter[segment] += 1

    return {
        "content_video_count": len(content_videos),
        "total_content_chars": total_content_chars,
        "hot_topics": word_counter.most_common(30),
    }


def generate_report(data: Dict[str, Any], keyword: str) -> str:
    """生成 Markdown 格式的爆款分析报告"""
    videos = data.get("videos", [])
    comment_analysis = analyze_comments(videos)
    content_analysis = analyze_content(videos)

    total_likes = sum(v.get("video_info", {}).get("like_count", 0) for v in videos)
    total_comments_count = sum(v.get("video_info", {}).get("comment_count", 0) for v in videos)
    total_shares = sum(v.get("video_info", {}).get("share_count", 0) for v in videos)
    total_collects = sum(v.get("video_info", {}).get("collect_count", 0) for v in videos)
    total_plays = sum(v.get("video_info", {}).get("play_count", 0) for v in videos)
    average_likes = total_likes / max(len(videos), 1)
    content_count = content_analysis["content_video_count"]
    fetched_comments = comment_analysis["total_comments"]

    # 按点赞排序
    sorted_videos = sorted(
        videos,
        key=lambda v: v.get("video_info", {}).get("like_count", 0),
        reverse=True,
    )

    report_lines = []

    # 标题
    report_lines.append("# 🎵 抖音爆款内容拆解报告")
    report_lines.append("")
    report_lines.append(f"**选题/关键词**: {keyword}")
    all_keywords = data.get("all_keywords", [])
    if all_keywords and len(all_keywords) > 1:
        report_lines.append(f"**搜索关键词**: {', '.join(all_keywords)}")
    report_lines.append(f"**平台**: 抖音 (douyin.com)")
    report_lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    # 数据总览
    report_lines.append("## 📊 数据总览")
    report_lines.append("")
    report_lines.append("| 指标 | 数值 |")
    report_lines.append("|------|------|")
    report_lines.append(f"| 分析视频数 | {len(videos)} |")
    report_lines.append(f"| 总点赞数 | {total_likes:,} |")
    report_lines.append(f"| 总评论数 | {total_comments_count:,} |")
    report_lines.append(f"| 总分享数 | {total_shares:,} |")
    report_lines.append(f"| 总收藏数 | {total_collects:,} |")
    report_lines.append(f"| 总播放量 | {total_plays:,} |")
    report_lines.append(f"| 平均点赞数 | {average_likes:,.0f} |")
    report_lines.append(f"| 内容提取成功 | {content_count}/{len(videos)} |")
    report_lines.append(f"| 采集评论数 | {fetched_comments} |")
    report_lines.append(f"| 总内容字符数 | {content_analysis['total_content_chars']:,} |")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")

    # Top 视频排行
    report_lines.append("## 🏆 Top 视频排行")
    report_lines.append("")
    for rank, video in enumerate(sorted_videos, 1):
        video_info = video.get("video_info", {})
        title = video_info.get("title", "")
        author = video_info.get("author", "")
        like_count = video_info.get("like_count", 0)
        comment_count = video_info.get("comment_count", 0)
        share_count = video_info.get("share_count", 0)
        collect_count = video_info.get("collect_count", 0)
        play_count = video_info.get("play_count", 0)
        video_url = video_info.get("url", "")
        link_text = video_info.get("video_id", "") or "查看视频"
        content_status = "✅" if video.get("transcript") else "❌"

        report_lines.append(f"### {rank}. {title}")
        report_lines.append("")
        report_lines.append(f"- **作者**: {author}")
        report_lines.append(f"- **点赞**: {like_count:,}")
        report_lines.append(f"- **评论数**: {comment_count:,}")
        report_lines.append(f"- **分享**: {share_count:,}")
        report_lines.append(f"- **收藏**: {collect_count:,}")
        report_lines.append(f"- **播放量**: {play_count:,}")
        report_lines.append(f"- **内容提取**: {content_status}")
        report_lines.append(format_content_link("视频链接", link_text, video_url))
        report_lines.append("")

        # 显示内容摘要（前 200 字）
        transcript = video.get("transcript", "")
        if transcript:
            # 转换为简体中文
            transcript_simplified = traditional_to_simplified(transcript)
            content_preview = transcript_simplified[:200].replace("\n", " ")
            report_lines.append(f"> 📝 **内容摘要**: {content_preview}...")
            report_lines.append("")

        # 显示该视频的 Top 5 评论
        comments = video.get("comments", [])
        if comments:
            report_lines.append("**热门评论 Top 5:**")
            report_lines.append("")
            for cidx, comment in enumerate(comments[:5], 1):
                content = comment.get("content", "").replace("\n", " ")[:120]
                comment_author = comment.get("author", "")
                comment_likes = comment.get("like_count", 0)
                # 转换为简体中文
                content_simplified = traditional_to_simplified(content)
                author_simplified = traditional_to_simplified(comment_author)
                report_lines.append(f"{cidx}. 「{content_simplified}」 —— {author_simplified} (👍{comment_likes})")
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
        # 转换为简体中文
        content_simplified = traditional_to_simplified(content)
        author_simplified = traditional_to_simplified(comment["author"])
        report_lines.append(f"{idx}. 「{content_simplified}」")
        report_lines.append(
            f"   —— {author_simplified} (👍{comment['like_count']}) "
            f"| 来自《{comment['video_title'][:30]}》"
        )
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
    report_lines.append("### 视频内容高频主题词")
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
    titles = [v.get("video_info", {}).get("title", "") for v in videos]
    title_lengths = [len(t) for t in titles]
    average_title_length = sum(title_lengths) / max(len(title_lengths), 1)

    emoji_count = sum(1 for t in titles if re.search(r'[\U0001F300-\U0001F9FF]', t))
    hashtag_count = sum(1 for t in titles if "#" in t)
    question_count = sum(1 for t in titles if "？" in t or "?" in t)
    exclamation_count = sum(1 for t in titles if "！" in t or "!" in t)

    report_lines.append(f"- **平均标题长度**: {average_title_length:.0f} 字")
    report_lines.append(f"- **使用 Emoji**: {emoji_count}/{len(videos)} 个视频")
    report_lines.append(f"- **使用 #话题标签**: {hashtag_count}/{len(videos)} 个视频")
    report_lines.append(f"- **使用问号**: {question_count}/{len(videos)} 个视频")
    report_lines.append(f"- **使用感叹号**: {exclamation_count}/{len(videos)} 个视频")
    report_lines.append("")

    # 标题关键词
    report_lines.append("### 标题常见关键词")
    report_lines.append("")
    title_word_counter = Counter()
    for title in titles:
        title_segments = re.findall(r'[\u4e00-\u9fff]{2,6}', title)
        for segment in title_segments:
            title_word_counter[segment] += 1

    common_title_words = [
        f"**{word}**({count}次)"
        for word, count in title_word_counter.most_common(15)
        if count >= 2
    ]
    if common_title_words:
        report_lines.append(f"高频标题词: {', '.join(common_title_words)}")
    else:
        report_lines.append("标题用词较为分散，无明显高频词")
    report_lines.append("")

    # 互动数据分析
    report_lines.append("### 互动数据特征")
    report_lines.append("")
    like_counts = [v.get("video_info", {}).get("like_count", 0) for v in videos]
    report_lines.append(f"- **最高点赞**: {max(like_counts):,}")
    report_lines.append(f"- **最低点赞**: {min(like_counts):,}")
    report_lines.append(f"- **平均点赞**: {average_likes:,.0f}")
    report_lines.append(f"- **中位数点赞**: {sorted(like_counts)[len(like_counts) // 2]:,}")
    report_lines.append(f"- **总播放量**: {total_plays:,}")
    report_lines.append(f"- **总收藏**: {total_collects:,}")
    report_lines.append("")

    report_lines.append("---")
    report_lines.append("")

    # 可复制的爆款公式
    report_lines.append("## 🔑 可复制的爆款公式")
    report_lines.append("")
    report_lines.append("基于以上数据分析，总结出以下可复制的创作建议：")
    report_lines.append("")
    report_lines.append(
        f"1. **标题策略**: 平均 {average_title_length:.0f} 字标题，"
        f"善用 #话题标签 增加曝光，适当使用问号引发好奇心"
    )
    report_lines.append(
        f"2. **内容定位**: 围绕「{keyword}」的核心话题，"
        f"结合教程、测评、深度解读等形式"
    )

    if comment_analysis["hot_words"]:
        top_concerns = [word for word, _ in comment_analysis["hot_words"][:5]]
        report_lines.append(
            f"3. **用户关注点**: 评论区高频讨论 {', '.join(top_concerns)} 等话题"
        )

    if content_analysis["hot_topics"]:
        top_topics = [word for word, _ in content_analysis["hot_topics"][:5]]
        report_lines.append(
            f"4. **内容主题**: 视频内容集中在 {', '.join(top_topics)} 等方向"
        )

    report_lines.append(
        f"5. **互动策略**: 头部视频点赞 {max(like_counts):,}，"
        f"建议在评论区积极互动提升热度"
    )
    report_lines.append("")

    return "\n".join(report_lines)


def generate_and_save_report(json_path: str, output_dir: str = None):
    """生成报告并保存到文件，返回 (报告文件路径, 报告内容) 元组"""
    data = load_data(json_path)
    keyword = data.get("keyword", "unknown")

    report_content = generate_report(data, keyword)

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "report")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_filename = f"douyin_report_{keyword}_{timestamp}.md"
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

    print("📊 正在生成报告...")
    saved_report_path = generate_and_save_report(input_json_path)
    print(f"✅ 报告已生成: {saved_report_path}")
