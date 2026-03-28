# -*- coding: utf-8 -*-
"""B 站关键词搜索 + 字幕提取 + 高赞评论爬虫（字幕提取需要 Cookie）"""

import json
import os
import re
import time
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))

import bilibili_api as bilibili
from cookie_helper import get_cookie_or_login

# ========== 配置区（由 AI 根据用户输入修改） ==========
# 关键词列表：AI 基于用户提供的核心关键词，拓展为 5 个相关搜索词
# 示例: KEYWORDS = ["openclaw", "openclaw教程", "openclaw测评", "openclaw怎么用", "openclaw开源"]
KEYWORDS = ["openclaw", "openclaw教程", "openclaw测评", "openclaw怎么用", "openclaw开源"]
MAX_VIDEOS = 10          # 最终保留的点赞最高视频数量（去重后取 Top N）
MAX_COMMENTS = 30        # 每个视频最多抓取的评论数量（按热度/点赞排序）
MAX_PAGES = 2            # 每个视频最多抓取的评论页数（每页最多 20 条）
SEARCH_PER_KEYWORD = 10  # 每个关键词搜索返回的视频数量

# URL 直接分析模式：填入B站视频 URL 列表，非空时跳过搜索
# 示例: VIDEO_URLS = ["https://www.bilibili.com/video/BV1xxx"]
VIDEO_URLS = []

# Cookie 配置（需要用户手动提供）
# 获取方式：打开 bilibili.com → F12 → Application → Cookies → 复制全部 Cookie 字符串
# 将 Cookie 粘贴到下方引号内
BILI_COOKIE = ""
# ============================

def run(config=None):
    """B站爬虫主流程，支持外部传参调用"""
    # 从 config 或全局变量获取配置
    if config:
        keywords = config.get("keywords", KEYWORDS)
        video_urls = config.get("video_urls", VIDEO_URLS)
        max_videos = config.get("max_videos", MAX_VIDEOS)
        max_comments = config.get("max_comments", MAX_COMMENTS)
        max_pages = config.get("max_pages", MAX_PAGES)
        search_per_keyword = config.get("search_per_keyword", SEARCH_PER_KEYWORD)
        bili_cookie = config.get("cookie", BILI_COOKIE)
    else:
        keywords = KEYWORDS
        video_urls = VIDEO_URLS
        max_videos = MAX_VIDEOS
        max_comments = MAX_COMMENTS
        max_pages = MAX_PAGES
        search_per_keyword = SEARCH_PER_KEYWORD
        bili_cookie = BILI_COOKIE
    
    total_start_time = time.time()

    # Step 0: 获取 Cookie（优先配置区 → 缓存 → 弹出浏览器登录）
    print(f"\n[Step 0] 获取 Cookie...")
    bili_cookie = get_cookie_or_login("bilibili", bili_cookie)
    if not bili_cookie:
        print("\n  ✗ 错误：未能获取B站 Cookie，无法继续")
        print("  请通过以下方式之一提供 Cookie：")
        print("    1. 在配置区 BILI_COOKIE 中填入 Cookie 字符串")
        print("    2. 在 ~/.aone_copilot/skills/.env 中设置 BILI_COOKIE=xxx")
        print("    3. 重新运行脚本，在弹出的浏览器中登录B站")
        return None

    # 判断使用哪种模式
    use_url_mode = bool(video_urls)

    # 兼容旧格式：如果 KEYWORDS 是字符串，自动转为列表
    keywords_list = keywords if isinstance(keywords, list) else [keywords]

    print(f"\n{'=' * 60}")
    if use_url_mode:
        print(f"  B站爬虫 - URL 直接分析 + 字幕提取 + 评论")
        print(f"  模式: URL 直接分析")
        print(f"  视频数量: {len(video_urls)} | 每个视频评论: {max_comments}")
    else:
        print(f"  B站爬虫 - 多关键词搜索 + 去重 + 字幕提取 + 评论")
        print(f"  关键词({len(keywords_list)}个): {keywords_list}")
        print(f"  每词搜索: {search_per_keyword} | 去重后保留: Top {max_videos} | 每视频评论: {max_comments}")
    print(f"  Cookie: {'已配置' if bili_cookie else '未配置（无法获取AI字幕）'}")
    print(f"{'=' * 60}")
    print()

    # Step 1: 搜索视频 或 从 URL 获取视频详情
    step1_start = time.time()

    if use_url_mode:
        # URL 直接分析模式
        print("[Step 1] 从 URL 获取视频详情...")
        videos = []

        for url_idx, url in enumerate(video_urls, 1):
            # 从 URL 中提取 BV 号
            match = re.search(r'/video/(BV\w+)', url)
            if not match:
                print(f"  ✗ URL {url_idx}: 无法提取 BV 号 - {url}")
                continue

            bvid = match.group(1)
            print(f"  [{url_idx}/{len(video_urls)}] 获取视频详情: {bvid}")

            # 获取视频详情
            video_detail = bilibili.get_video_detail(bvid)

            if not video_detail:
                print(f"    ✗ 获取视频详情失败")
                continue

            # 构造与搜索结果相同格式的视频对象
            video = {
                "bvid": bvid,
                "aid": video_detail.get("aid", 0),
                "title": video_detail.get("title", ""),
                "author": video_detail.get("author", ""),
                "like_count": video_detail.get("like_count", 0),
                "url": url
            }
            videos.append(video)

            title = video.get("title", "")[:80]
            author = video.get("author", "") or "unknown"
            like_count = video.get("like_count", 0)
            print(f"    ✓ [{like_count} 赞] {title}")
            print(f"       Author: {author} | BVID: {bvid}")
            print()

        step1_elapsed = time.time() - step1_start
        print(f"\n  成功获取 {len(videos)} 个视频详情 (耗时 {step1_elapsed:.1f}s)\n")

        if not videos:
            print("  未成功获取任何视频详情。请检查 URL 是否正确。")
            return None

    else:
        # 多关键词搜索模式：逐个关键词搜索 → 合并 → 按标题去重 → 按点赞取 Top N
        print(f"[Step 1] 多关键词搜索（{len(keywords_list)} 个关键词）...")
        all_candidates = []
        for kw_idx, keyword in enumerate(keywords_list, 1):
            print(f"\n  [{kw_idx}/{len(keywords_list)}] 搜索关键词: {keyword}")
            search_result = bilibili.search(
                keywords=keyword,
                page_size=search_per_keyword,
            )
            keyword_videos = search_result.get("items", [])
            print(f"    ✓ 找到 {len(keyword_videos)} 个视频")
            for video in keyword_videos:
                video["_source_keyword"] = keyword
            all_candidates.extend(keyword_videos)
            if kw_idx < len(keywords_list):
                time.sleep(1)

        # 按标题去重（保留点赞数更高的那条）
        print(f"\n  合并去重: 搜索到 {len(all_candidates)} 条结果")
        seen_titles = {}
        for video in all_candidates:
            title = video.get("title", "").strip()
            if not title:
                continue
            existing = seen_titles.get(title)
            if existing is None or video.get("like_count", 0) > existing.get("like_count", 0):
                seen_titles[title] = video
        unique_videos = list(seen_titles.values())
        print(f"  去重后: {len(unique_videos)} 条唯一视频")

        # 按点赞数排序，取 Top N
        unique_videos.sort(key=lambda video: video.get("like_count", 0), reverse=True)
        videos = unique_videos[:max_videos]

        step1_elapsed = time.time() - step1_start
        print(f"\n  最终选取 Top {len(videos)} 视频 (耗时 {step1_elapsed:.1f}s):\n")
        for idx, video in enumerate(videos, 1):
            title = video.get("title", "")[:80]
            author = video.get("author", "") or "unknown"
            bvid = video.get("bvid", "")
            like_count = video.get("like_count", 0)
            source_keyword = video.get("_source_keyword", "")
            print(f"  {idx}. [{like_count} 赞] {title}")
            print(f"     Author: {author} | BVID: {bvid} | 来源词: {source_keyword}")
            print(f"     URL: {video.get('url', '')}")
            print()

        if not videos:
            print("  未找到视频。请检查网络连接或更换关键词。")
            return None

    # Step 2: 为每个视频提取字幕（使用 B站官方 API + Cookie）
    step2_start = time.time()
    subtitle_success_count = 0
    subtitle_fail_count = 0
    print(f"\n[Step 2] 提取 {min(len(videos), max_videos)} 个视频的字幕...\n")

    subtitle_results = {}
    for idx, video in enumerate(videos[:max_videos], 1):
        bvid = video.get("bvid", "")
        title = video.get("title", "")[:50]
        print(f"  [{idx}/{min(len(videos), max_videos)}] {title} ({bvid})")

        subtitle_result = bilibili.fetch_subtitles(bvid=bvid, cookie_string=bili_cookie)

        if subtitle_result.get("success"):
            subtitle_count = subtitle_result.get("subtitle_count", 0)
            subtitle_language = subtitle_result.get("subtitle_language", "")
            subtitle_text = subtitle_result.get("subtitle_text", "")
            print(f"    ✓ 字幕获取成功: {subtitle_count} 条 ({subtitle_language}), {len(subtitle_text)} 字符")
            print(f"    📝 前100字: {subtitle_text[:100].replace(chr(10), ' ')}...")
            subtitle_success_count += 1
            subtitle_results[bvid] = subtitle_result
        else:
            error_message = subtitle_result.get("error", "未知错误")
            print(f"    ✗ 字幕获取失败: {error_message}")
            subtitle_fail_count += 1
            subtitle_results[bvid] = subtitle_result

        if idx < min(len(videos), max_videos):
            time.sleep(0.5)

    step2_elapsed = time.time() - step2_start
    print(f"\n  字幕提取完成 (耗时 {step2_elapsed:.1f}s): 成功 {subtitle_success_count} / 失败 {subtitle_fail_count}")

    # Step 3: 为每个视频抓取评论（sort=2 按热度排序）
    step3_start = time.time()
    print(f"\n[Step 3] 抓取 {min(len(videos), max_videos)} 个视频的评论...\n")
    all_results = []

    for idx, video in enumerate(videos[:max_videos], 1):
        bvid = video.get("bvid", "")
        aid = video.get("aid", 0)
        title = video.get("title", "")[:50]
        like_count = video.get("like_count", 0)

        print(f"  {'=' * 55}")
        print(f"  [{idx}/{min(len(videos), max_videos)}] [{like_count} 赞] {title}")
        print(f"  {'=' * 55}")

        comment_result = bilibili.fetch_comments_for_video(
            bvid=bvid,
            aid=int(aid) if aid else 0,
            max_pages=max_pages,  # 抓取 max_pages 页评论
            sort=1,  # 1 = 按点赞数排序（sort=2 是热度模式，仅返回3条热评）
            cookie_string=bili_cookie,  # 传入 Cookie 才能获取更多评论
        )

        all_comments = comment_result.get("comments", [])
        all_comments.sort(key=lambda comment: comment.get("like_count", 0), reverse=True)
        comments = all_comments[:max_comments]

        video_title = comment_result.get("video_title", title)
        print(f"  标题: {video_title}")
        print(f"  评论数: {len(comments)}\n")

        for cidx, comment in enumerate(comments[:10], 1):
            author = comment.get("author", "匿名")
            content = comment.get("content", "")[:80].replace("\n", " ")
            likes = comment.get("like_count", 0)
            print(f"    {cidx:>3}. {content}")
            print(f"         by {author} | 赞 {likes}")

        if len(comments) > 10:
            print(f"\n    ... 还有 {len(comments) - 10} 条评论")

        # 合并字幕数据到结果中
        video_subtitle = subtitle_results.get(bvid, {})
        all_results.append({
            "bvid": bvid,
            "aid": aid,
            "video_title": video_title,
            "video_url": video.get("url", ""),
            "author": video.get("author", ""),
            "like_count": like_count,
            "subtitle_success": video_subtitle.get("success", False),
            "subtitle_text": video_subtitle.get("subtitle_text", ""),
            "subtitle_count": video_subtitle.get("subtitle_count", 0),
            "subtitle_language": video_subtitle.get("subtitle_language", ""),
            "comments": comments,
            "comment_count": len(comments),
        })

        if idx < min(len(videos), max_videos):
            print(f"\n  等待 2s 后继续下一个视频...")
            time.sleep(2)

    step3_elapsed = time.time() - step3_start

    # 保存结果
    output_dir = os.path.join(script_dir, "output", "json")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    
    # 根据模式选择文件名
    if use_url_mode:
        output_path = os.path.join(output_dir, f"bili_url_analysis_{timestamp}.json")
    else:
        output_path = os.path.join(output_dir, f"bili_{keywords_list[0]}_{timestamp}.json")

    output_data = {
        "keyword": keywords_list[0],
        "all_keywords": keywords_list,
        "videos": all_results,
    }
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(output_data, output_file, ensure_ascii=False, indent=2)

    # Step 4: 生成爆款分析报告
    step4_start = time.time()
    print(f"\n[Step 4] 生成爆款分析报告...\n")

    from generate_report import generate_and_save_report
    report_path, report_content = generate_and_save_report(output_path, output_dir=os.path.join(script_dir, "output", "report"))
    step4_elapsed = time.time() - step4_start
    print(f"  ✅ 报告已生成: {report_path} (耗时 {step4_elapsed:.1f}s)")

    # 将报告内容直接输出到控制台，方便 AI 读取并展示给用户
    print(f"\n{'=' * 70}")
    print("  📋 以下是完整的分析报告内容：")
    print(f"{'=' * 70}\n")
    print(report_content)
    print(f"\n{'=' * 70}")
    print("  📋 报告内容结束")
    print(f"{'=' * 70}")

    total_elapsed = time.time() - total_start_time
    total_comments = sum(item["comment_count"] for item in all_results)
    total_subtitles = sum(1 for item in all_results if item["subtitle_success"])

    print(f"\n{'=' * 60}")
    print(f"  ✅ 全部完成！")
    print(f"  📊 视频: {len(all_results)} 个")
    print(f"  📝 字幕: {total_subtitles}/{len(all_results)} 个视频成功提取")
    print(f"  💬 评论: {total_comments} 条")
    print(f"  💾 数据文件: {output_path}")
    print(f"  📄 分析报告: {report_path}")
    print(f"  ⏱️  耗时统计:")
    print(f"     Step 1 搜索:   {step1_elapsed:.1f}s")
    print(f"     Step 2 字幕:   {step2_elapsed:.1f}s")
    print(f"     Step 3 评论:   {step3_elapsed:.1f}s")
    print(f"     Step 4 报告:   {step4_elapsed:.1f}s")
    print(f"     总耗时:        {total_elapsed:.1f}s")
    print(f"{'=' * 60}")

    return output_path

if __name__ == "__main__":
    run()