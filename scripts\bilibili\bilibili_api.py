import json
import time
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote
import ssl

# B站 API 端点
BILIBILI_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/all"
BILIBILI_VIDEO_DETAIL_API = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_REPLY_API = "https://api.bilibili.com/x/v2/reply"
BILIBILI_PLAYER_API = "https://api.bilibili.com/x/player/v2"

# 请求头
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}

# SSL 上下文（用于解决某些环境的 SSL 证书问题）
_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.check_hostname = False
_SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# 全局配置（从 media_crawler.config 导入）
try:
    from media_crawler.config import global_settings
except ImportError:
    # 如果无法导入配置，使用默认值
    class GlobalSettings:
        class Crawl:
            request_interval = 1
        crawl = Crawl()
    global_settings = GlobalSettings()

# 日志模块（从 media_crawler.logger 导入）
try:
    from media_crawler.logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

def _http_get_json(url: str, params: Dict[str, Any], extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    发送 HTTP GET 请求并返回 JSON 响应

    Args:
        url: 请求 URL
        params: 查询参数
        extra_headers: 额外的请求头

    Returns:
        解析后的 JSON 响应字典
    """
    query_string = "&".join([f"{k}={quote(str(v), safe='')}" for k, v in params.items()])
    full_url = f"{url}?{query_string}"

    request = Request(full_url)
    for key, value in HEADERS.items():
        request.add_header(key, value)
    if extra_headers:
        for key, value in extra_headers.items():
            request.add_header(key, value)

    response = urlopen(request, timeout=15, context=_SSL_CONTEXT)
    response_body = response.read().decode("utf-8")
    return json.loads(response_body)

def _extract_video_item(raw_item: Dict[str, Any]) -> Dict[str, Any]:
    """从 B站 API 原始数据中提取扁平化的视频信息"""
    title = raw_item.get("title", "")
    # B站搜索结果的 title 包含 <em> 高亮标签，需要清理
    title = title.replace('<em class="keyword">', "").replace("</em>", "")

    return {
        "aid": raw_item.get("aid", ""),
        "bvid": raw_item.get("bvid", ""),
        "title": title,
        "description": raw_item.get("description", ""),
        "author": raw_item.get("author", ""),
        "mid": raw_item.get("mid", ""),
        "play_count": raw_item.get("play", 0),
        "danmaku_count": raw_item.get("video_review", 0),
        "like_count": raw_item.get("like", 0),
        "favorites": raw_item.get("favorites", 0),
        "duration": raw_item.get("duration", ""),
        "publish_date": raw_item.get("pubdate", 0),
        "tag": raw_item.get("tag", ""),
        "url": f"https://www.bilibili.com/video/{raw_item.get('bvid', '')}",
        "cover": raw_item.get("pic", ""),
    }

def search(
    keywords: str,
    page_num: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """
    B站关键词搜索

    Args:
        keywords: 搜索关键词
        page_num: 页码，从 1 开始
        page_size: 每页数量（B站 API 固定返回约 20 条，此参数用于截取）

    Returns:
        包含搜索结果的字典
    """
    logger.info(f"[bilibili.search] 开始搜索: keywords={keywords}, page={page_num}")

    params = {
        "keyword": keywords,
        "page": page_num,
        "search_type": "video",
    }

    try:
        data = _http_get_json(BILIBILI_SEARCH_API, params)

        if data.get("code") != 0:
            logger.warning(f"[bilibili.search] API 返回错误: code={data.get('code')}, message={data.get('message')}")
            return {"items": [], "total": 0, "page_num": page_num, "keywords": keywords}

        # 从嵌套结构中提取视频结果
        # 收集候选池（3 倍），以便按点赞排序后取 Top N
        candidate_pool_size = max(page_size * 3, 30)
        result_dict = data.get("data", {}).get("result", {})
        video_items = []
        
        # B 站 API 返回的 result 是字典，视频数据在 result['video'] 字段中
        if isinstance(result_dict, dict) and "video" in result_dict:
            raw_videos = result_dict.get("video", [])
            for raw_video in raw_videos[:candidate_pool_size]:
                video_items.append(_extract_video_item(raw_video))

        # 按点赞数降序排序，取 Top page_size
        video_items.sort(key=lambda video: video.get("like_count", 0), reverse=True)
        video_items = video_items[:page_size]

        logger.info(f"[bilibili.search] 搜索完成: 找到 {len(video_items)} 条视频（按点赞排序）")
        return {
            "items": video_items,
            "total": len(video_items),
            "page_num": page_num,
            "keywords": keywords,
            "platform": "bili",
        }

    except (URLError, HTTPError, Exception) as request_error:
        logger.error(f"[bilibili.search] 请求失败: {request_error}")
        return {"items": [], "total": 0, "page_num": page_num, "keywords": keywords, "error": str(request_error)}

def get_video_detail(video_id: str) -> Dict[str, Any]:
    """
    获取 B站视频详情

    Args:
        video_id: 视频 aid 或 bvid

    Returns:
        视频详情字典
    """
    logger.info(f"[bilibili.detail] 获取视频详情: video_id={video_id}")

    params = {}
    if video_id.startswith("BV"):
        params["bvid"] = video_id
    else:
        params["aid"] = video_id

    try:
        data = _http_get_json(BILIBILI_VIDEO_DETAIL_API, params)

        if data.get("code") != 0:
            logger.warning(f"[bilibili.detail] API 返回错误: {data.get('message')}")
            return {"error": data.get("message", "未知错误")}

        video_data = data.get("data", {})
        stat = video_data.get("stat", {})
        owner = video_data.get("owner", {})

        return {
            "aid": video_data.get("aid", ""),
            "bvid": video_data.get("bvid", ""),
            "title": video_data.get("title", ""),
            "description": video_data.get("desc", ""),
            "author": owner.get("name", ""),
            "mid": owner.get("mid", ""),
            "play_count": stat.get("view", 0),
            "danmaku_count": stat.get("danmaku", 0),
            "like_count": stat.get("like", 0),
            "coin_count": stat.get("coin", 0),
            "favorite_count": stat.get("favorite", 0),
            "share_count": stat.get("share", 0),
            "reply_count": stat.get("reply", 0),
            "duration": video_data.get("duration", 0),
            "publish_date": video_data.get("pubdate", 0),
            "tags": [tag.get("tag_name", "") for tag in video_data.get("tags", []) if tag.get("tag_name")],
            "url": f"https://www.bilibili.com/video/{video_data.get('bvid', '')}",
            "cover": video_data.get("pic", ""),
            "platform": "bili",
        }

    except (URLError, HTTPError, Exception) as request_error:
        logger.error(f"[bilibili.detail] 请求失败: {request_error}")
        return {"error": str(request_error)}

def fetch_comments(
    aid: int,
    page_num: int = 1,
    page_size: int = 20,
    sort: int = 0,
    cookie_string: str = "",
) -> Dict[str, Any]:
    """
    获取 B站视频的一级评论

    Args:
        aid: 视频 aid（数字 ID）
        page_num: 页码，从 1 开始
        page_size: 每页评论数量（最大 20）
        sort: 排序方式，0=按时间，1=按点赞数，2=按热度（仅返回少量热评）
        cookie_string: B站登录 Cookie（反爬需要）

    Returns:
        包含评论列表的字典
    """
    logger.info(f"[bilibili.comments] 获取评论: aid={aid}, page={page_num}, sort={sort}")

    params = {
        "type": 1,          # 1 = 视频评论
        "oid": aid,          # 视频 aid
        "pn": page_num,      # 页码
        "ps": min(page_size, 20),  # 每页数量，最大 20
        "sort": sort,        # 排序：0=按时间，1=按点赞数，2=按热度（仅少量热评）
    }

    extra_headers = {"Cookie": cookie_string} if cookie_string else None

    try:
        data = _http_get_json(BILIBILI_REPLY_API, params, extra_headers=extra_headers)

        if data.get("code") != 0:
            error_message = data.get("message", "未知错误")
            logger.warning(f"[bilibili.comments] API 返回错误: code={data.get('code')}, message={error_message}")
            return {
                "aid": aid,
                "comments": [],
                "total": 0,
                "page_num": page_num,
                "platform": "bili",
                "error": error_message,
            }

        reply_data = data.get("data", {})
        raw_replies = reply_data.get("replies", []) or []
        total_count = reply_data.get("page", {}).get("count", 0)

        comments = []
        for raw_reply in raw_replies:
            comment_item = _extract_comment_item(raw_reply)
            if comment_item:
                comments.append(comment_item)

        logger.info(f"[bilibili.comments] 获取完成: {len(comments)} 条一级评论（总计 {total_count} 条）")
        return {
            "aid": aid,
            "comments": comments,
            "total": len(comments),
            "total_count": total_count,
            "page_num": page_num,
            "platform": "bili",
        }

    except (URLError, HTTPError, Exception) as request_error:
        logger.error(f"[bilibili.comments] 请求失败: {request_error}")
        return {
            "aid": aid,
            "comments": [],
            "total": 0,
            "page_num": page_num,
            "platform": "bili",
            "error": str(request_error),
        }

def _extract_comment_item(raw_reply: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """从 B站评论 API 原始数据中提取一级评论信息"""
    try:
        member = raw_reply.get("member", {})
        content_data = raw_reply.get("content", {})
        reply_control = raw_reply.get("reply_control", {})

        # 发布时间：ctime 是 Unix 时间戳
        ctime = raw_reply.get("ctime", 0)
        publish_time = ""
        if ctime:
            import datetime
            publish_time = datetime.datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S")

        return {
            "rpid": raw_reply.get("rpid", 0),
            "author": member.get("uname", ""),
            "author_mid": member.get("mid", 0),
            "content": content_data.get("message", ""),
            "like_count": raw_reply.get("like", 0),
            "reply_count": raw_reply.get("rcount", 0),
            "publish_time": publish_time,
            "location": reply_control.get("location", ""),
        }
    except Exception as parse_error:
        logger.debug(f"[bilibili._extract_comment] 解析失败: {parse_error}")
        return None

def fetch_comments_for_video(
    bvid: str = "",
    aid: int = 0,
    max_pages: int = 3,
    sort: int = 0,
    cookie_string: str = "",
) -> Dict[str, Any]:
    """
    获取 B站视频的所有一级评论（支持多页）

    Args:
        bvid: 视频 BV 号（与 aid 二选一）
        aid: 视频 aid（与 bvid 二选一）
        max_pages: 最大抓取页数
        sort: 排序方式，0=按时间，1=按点赞数，2=按回复数
        cookie_string: B站登录 Cookie（反爬需要）

    Returns:
        包含所有评论的字典
    """
    # 如果传入 bvid，先获取 aid
    if bvid and not aid:
        logger.info(f"[bilibili.comments] 通过 bvid={bvid} 获取 aid")
        detail = get_video_detail(bvid)
        aid = detail.get("aid", 0)
        if not aid:
            return {
                "bvid": bvid,
                "comments": [],
                "total": 0,
                "platform": "bili",
                "error": "无法获取视频 aid",
            }

    all_comments = []
    video_title = ""

    for page in range(1, max_pages + 1):
        result = fetch_comments(aid=aid, page_num=page, sort=sort, cookie_string=cookie_string)
        comments = result.get("comments", [])

        if not comments:
            break

        all_comments.extend(comments)
        logger.info(f"[bilibili.comments] 第 {page} 页: {len(comments)} 条评论")

        # 请求间隔
        if page < max_pages:
            time.sleep(global_settings.crawl.request_interval)

    # 获取视频标题
    if aid:
        detail = get_video_detail(str(aid))
        video_title = detail.get("title", "")

    logger.info(f"[bilibili.comments] 共获取 {len(all_comments)} 条一级评论")
    return {
        "aid": aid,
        "bvid": bvid,
        "video_title": video_title,
        "video_url": f"https://www.bilibili.com/video/{bvid}" if bvid else f"https://www.bilibili.com/video/av{aid}",
        "comments": all_comments,
        "total": len(all_comments),
        "platform": "bili",
    }

def search_and_fetch_comments(
    keywords: str,
    max_videos: int = 10,
    max_comments_per_video: int = 30,
) -> Dict[str, Any]:
    """
    搜索 B站关键词，取点赞最高的 max_videos 个视频，
    再为每个视频抓取点赞最高的 max_comments_per_video 条一级评论。

    B站评论 API 支持 sort=2（按热度/点赞排序），直接从 API 层面保证评论按点赞排序。

    Args:
        keywords: 搜索关键词
        max_videos: 最多抓取的视频数量
        max_comments_per_video: 每个视频最多抓取的评论数量

    Returns:
        包含视频列表及各自评论的字典
    """
    logger.info(f"[bilibili.search_and_fetch_comments] 开始: keywords={keywords}, max_videos={max_videos}")

    # Step 1: 搜索，按点赞排序取 Top N
    search_result = search(keywords=keywords, page_size=max_videos)
    videos = search_result.get("items", [])
    logger.info(f"[bilibili.search_and_fetch_comments] 搜索到 {len(videos)} 个视频")

    # Step 2: 为每个视频抓取评论（sort=2 按热度/点赞排序）
    results = []
    for idx, video in enumerate(videos):
        bvid = video.get("bvid", "")
        aid = video.get("aid", 0)
        title = video.get("title", "")
        logger.info(f"[bilibili.search_and_fetch_comments] 抓取第 {idx + 1}/{len(videos)} 个视频评论: {bvid}")

        comment_result = fetch_comments_for_video(
            bvid=bvid,
            aid=int(aid) if aid else 0,
            max_pages=max(1, max_comments_per_video // 20 + 1),
            sort=2,  # 2 = 按热度排序（点赞最高优先）
        )

        # 取点赞最高的 max_comments_per_video 条
        all_comments = comment_result.get("comments", [])
        all_comments.sort(key=lambda comment: comment.get("like_count", 0), reverse=True)
        top_comments = all_comments[:max_comments_per_video]

        results.append({
            "video": video,
            "video_title": comment_result.get("video_title", title),
            "video_url": video.get("url", ""),
            "comments": top_comments,
            "comments_total": len(top_comments),
        })

        # 请求间隔，避免触发限流
        if idx < len(videos) - 1:
            time.sleep(1)

    logger.info(f"[bilibili.search_and_fetch_comments] 完成，共处理 {len(results)} 个视频")
    return {
        "keywords": keywords,
        "videos": results,
        "total_videos": len(results),
        "platform": "bili",
    }

def get_video_cid(bvid: str) -> int:
    """
    获取 B站视频的第一个分P的 cid

    Args:
        bvid: 视频 BV 号

    Returns:
        cid 数字，获取失败返回 0
    """
    logger.info(f"[bilibili.get_video_cid] 获取 cid: bvid={bvid}")
    params = {"bvid": bvid}

    try:
        data = _http_get_json(BILIBILI_VIDEO_DETAIL_API, params)
        if data.get("code") != 0:
            logger.warning(f"[bilibili.get_video_cid] API 返回错误: {data.get('message')}")
            return 0

        video_data = data.get("data", {})
        pages = video_data.get("pages", [])
        if pages:
            cid = pages[0].get("cid", 0)
            logger.info(f"[bilibili.get_video_cid] 获取成功: bvid={bvid}, cid={cid}")
            return cid

        logger.warning(f"[bilibili.get_video_cid] 未找到分P信息: bvid={bvid}")
        return 0

    except (URLError, HTTPError, Exception) as request_error:
        logger.error(f"[bilibili.get_video_cid] 请求失败: {request_error}")
        return 0

def fetch_subtitles(bvid: str, cookie_string: str, cid: int = 0) -> Dict[str, Any]:
    """
    通过 B站官方 Player API 获取视频字幕（包括 AI 自动生成字幕）。
    需要登录态（Cookie）才能获取 AI 字幕。

    Args:
        bvid: 视频 BV 号
        cookie_string: B站登录 Cookie 字符串
        cid: 视频分P的 cid，为 0 时自动获取

    Returns:
        字典，包含:
        - success: 是否成功获取到字幕
        - subtitle_text: 拼接后的纯文本字幕
        - subtitle_count: 字幕条数
        - subtitle_language: 字幕语言
        - raw_subtitles: 原始字幕数据列表
        - error: 错误信息（如有）
    """
    logger.info(f"[bilibili.fetch_subtitles] 开始获取字幕: bvid={bvid}")

    if not cid:
        cid = get_video_cid(bvid)
        if not cid:
            return {"success": False, "subtitle_text": "", "error": "无法获取视频 cid"}

    params = {"bvid": bvid, "cid": cid}
    auth_headers = {"Cookie": cookie_string}

    try:
        data = _http_get_json(BILIBILI_PLAYER_API, params, extra_headers=auth_headers)

        if data.get("code") != 0:
            error_message = data.get("message", "未知错误")
            logger.warning(f"[bilibili.fetch_subtitles] Player API 返回错误: {error_message}")
            return {"success": False, "subtitle_text": "", "error": error_message}

        player_data = data.get("data", {})
        subtitle_info = player_data.get("subtitle", {})
        subtitle_list = subtitle_info.get("subtitles", [])

        if not subtitle_list:
            logger.info(f"[bilibili.fetch_subtitles] 该视频无字幕: bvid={bvid}")
            return {"success": False, "subtitle_text": "", "error": "该视频无字幕"}

        # 优先选择中文字幕，其次选第一个
        chosen_subtitle = subtitle_list[0]
        for subtitle_item in subtitle_list:
            language = subtitle_item.get("lan", "")
            if "zh" in language or "cn" in language:
                chosen_subtitle = subtitle_item
                break

        subtitle_url = chosen_subtitle.get("subtitle_url", "")
        subtitle_language = chosen_subtitle.get("lan_doc", chosen_subtitle.get("lan", "unknown"))

        if not subtitle_url:
            return {"success": False, "subtitle_text": "", "error": "字幕 URL 为空"}

        # 补全协议头
        if subtitle_url.startswith("//"):
            subtitle_url = "https:" + subtitle_url

        logger.info(f"[bilibili.fetch_subtitles] 下载字幕: lang={subtitle_language}, url={subtitle_url[:80]}...")

        # 下载字幕 JSON
        subtitle_request = Request(subtitle_url)
        subtitle_request.add_header("User-Agent", HEADERS["User-Agent"])
        subtitle_request.add_header("Referer", "https://www.bilibili.com")
        subtitle_response = urlopen(subtitle_request, timeout=15, context=_SSL_CONTEXT)
        subtitle_body = subtitle_response.read().decode("utf-8")
        subtitle_json = json.loads(subtitle_body)

        # 解析字幕内容：{"body": [{"from": 0, "to": 1, "content": "文本"}, ...]}
        body_items = subtitle_json.get("body", [])
        text_parts = [item.get("content", "") for item in body_items if item.get("content")]
        full_text = "\n".join(text_parts)

        logger.info(f"[bilibili.fetch_subtitles] 字幕获取成功: {len(body_items)} 条, {len(full_text)} 字符")
        return {
            "success": True,
            "subtitle_text": full_text,
            "subtitle_count": len(body_items),
            "subtitle_language": subtitle_language,
            "raw_subtitles": body_items,
        }

    except (URLError, HTTPError, Exception) as request_error:
        logger.error(f"[bilibili.fetch_subtitles] 请求失败: {request_error}")
        return {"success": False, "subtitle_text": "", "error": str(request_error)}