# -*- coding: utf-8 -*-
"""抖音 HTML 结构检测模块 — 检测页面结构变化，辅助调整选择器"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import global_settings, get_logger

logger = get_logger()

# 关键元素的选择器模板（用于对比检测）
KEY_SELECTORS = {
    "search_video_list": [
        "div[data-e2e='search-video-list'] div[class*='video-card']",
        "div[class*='search-result'] div[class*='video-item']",
        "div[class*='video-list'] > div",
    ],
    "video_card": [
        "div[data-e2e='video-card']",
        "div[class*='video-card']",
        "div[class*='video-item']",
    ],
    "video_title": [
        "div[data-e2e='video-title']",
        "h3[class*='title']",
        "div[class*='video-desc']",
    ],
    "video_author": [
        "div[data-e2e='video-author']",
        "span[class*='author']",
        "div[class*='user-info'] span",
    ],
    "video_like_count": [
        "div[data-e2e='like-count']",
        "span[class*='like']",
        "div[class*='interaction'] span",
    ],
    "comment_list": [
        "div[data-e2e='comment-list']",
        "div[class*='comment-list']",
        "div[class*='comment-item']",
    ],
    "comment_item": [
        "div[data-e2e='comment-item']",
        "div[class*='comment-item']",
        "div[class*='comment'] > div",
    ],
    "comment_content": [
        "div[data-e2e='comment-text']",
        "div[class*='comment-text']",
        "span[class*='content']",
    ],
    "comment_like_count": [
        "div[data-e2e='comment-like']",
        "span[class*='like-count']",
        "div[class*='comment-like']",
    ],
}

# 页面结构特征指纹（用于判断是否变化）
STRUCTURE_FEATURES = {
    "search_page": {
        "ssr_data_pattern": r'<script\s+id="RENDER_DATA"[^>]*>(.*?)</script>',
        "video_container_pattern": r'data-e2e=["\']video-?(card|item|list)["\']',
        "interaction_pattern": r'data-e2e=["\'](like|comment|share)-count["\']',
    },
    "video_page": {
        "comment_pattern": r'data-e2e=["\']comment-?(list|item|text)["\']',
        "video_player_pattern": r'data-e2e=["\']video-player["\']',
    },
}


class HTMLStructureDetector:
    """抖音 HTML 结构检测器"""

    def __init__(self, cookie_string: str = ""):
        self.cookie_string = cookie_string
        self.driver = None
        self.structure_history = self._load_history()
        self.current_structure = {}
        self.changes = []

    def _load_history(self) -> Dict[str, Any]:
        """加载历史结构数据"""
        history_path = Path(__file__).parent / "structure_history.json"
        if history_path.exists():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载历史结构失败：{e}")
        return {"search_page": None, "video_page": None, "last_update": None}

    def _save_history(self):
        """保存历史结构数据"""
        history_path = Path(__file__).parent / "structure_history.json"
        try:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(self.structure_history, f, ensure_ascii=False, indent=2)
            logger.info(f"已保存结构历史：{history_path}")
        except Exception as e:
            logger.warning(f"保存历史结构失败：{e}")

    def _create_browser(self):
        """创建浏览器"""
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--user-agent={global_settings.browser.user_agent}")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=zh-CN")
        options.add_argument("--disable-gpu")

        self.driver = uc.Chrome(options=options, headless=False, version_main=145)
        self.driver.set_page_load_timeout(global_settings.browser.page_load_timeout)

        if self.cookie_string:
            logger.info("[detector] 注入 Cookie 登录态")
            self.driver.get("https://www.douyin.com")
            time.sleep(5)
            self._inject_cookie(self.cookie_string)
            self.driver.refresh()
            time.sleep(3)

    def _inject_cookie(self, cookie_string: str):
        """注入 Cookie"""
        from douyin_api import _parse_cookie_string

        parsed_cookies = _parse_cookie_string(cookie_string)
        injected_count = 0
        for cookie in parsed_cookies:
            try:
                self.driver.add_cookie(cookie)
                injected_count += 1
            except Exception:
                pass
        logger.info(f"[detector] 已注入 {injected_count}/{len(parsed_cookies)} 个 Cookie")

    def detect_search_page(self, keywords: str = "抖音") -> Dict[str, Any]:
        """检测搜索页面结构"""
        logger.info(f"[detector] 检测搜索页面结构：{keywords}")
        
        if not self.driver:
            self._create_browser()

        try:
            search_url = f"https://www.douyin.com/search/{keywords}?type=video"
            self.driver.get(search_url)
            time.sleep(8)

            # 等待搜索结果加载
            time.sleep(5)

            # 提取结构特征
            structure = {
                "timestamp": datetime.now().isoformat(),
                "url": search_url,
                "page_title": self.driver.title,
                "page_size": len(self.driver.page_source),
                "selectors": {},
                "features": {},
                "elements": {},
            }

            # 检测 SSR 数据
            ssr_match = re.search(
                STRUCTURE_FEATURES["search_page"]["ssr_data_pattern"],
                self.driver.page_source,
                re.DOTALL,
            )
            structure["features"]["has_ssr_data"] = bool(ssr_match)
            if ssr_match:
                ssr_content = ssr_match.group(1)[:500]  # 只取前 500 字符作为指纹
                structure["features"]["ssr_fingerprint"] = hash(ssr_content)

            # 检测关键元素
            for element_name, selectors in KEY_SELECTORS.items():
                if element_name not in ["comment_list", "comment_item", "comment_content", "comment_like_count"]:
                    found_selector = self._find_working_selector(selectors, element_name)
                    structure["selectors"][element_name] = found_selector
                    
                    # 统计元素数量
                    if found_selector:
                        try:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, found_selector)
                            structure["elements"][element_name] = len(elements)
                        except Exception:
                            structure["elements"][element_name] = 0

            # 检测视频卡片特征
            video_card_pattern = STRUCTURE_FEATURES["search_page"]["video_container_pattern"]
            structure["features"]["has_video_e2e"] = bool(re.search(video_card_pattern, self.driver.page_source))

            # 检测互动数据特征
            interaction_pattern = STRUCTURE_FEATURES["search_page"]["interaction_pattern"]
            structure["features"]["has_interaction_e2e"] = bool(re.search(interaction_pattern, self.driver.page_source))

            self.current_structure["search_page"] = structure
            logger.info(f"[detector] 搜索页面结构检测完成")
            return structure

        except Exception as e:
            logger.error(f"[detector] 搜索页面检测失败：{e}")
            return {"error": str(e)}

    def detect_video_page(self, video_url: str) -> Dict[str, Any]:
        """检测视频页面结构"""
        logger.info(f"[detector] 检测视频页面结构：{video_url}")
        
        if not self.driver:
            self._create_browser()

        try:
            self.driver.get(video_url)
            time.sleep(8)

            # 点击评论按钮展开评论区
            self._try_open_comments()

            structure = {
                "timestamp": datetime.now().isoformat(),
                "url": video_url,
                "page_title": self.driver.title,
                "page_size": len(self.driver.page_source),
                "selectors": {},
                "features": {},
                "elements": {},
            }

            # 检测 SSR 数据
            ssr_match = re.search(
                STRUCTURE_FEATURES["search_page"]["ssr_data_pattern"],
                self.driver.page_source,
                re.DOTALL,
            )
            structure["features"]["has_ssr_data"] = bool(ssr_match)

            # 检测评论相关元素
            for element_name, selectors in KEY_SELECTORS.items():
                if element_name in ["comment_list", "comment_item", "comment_content", "comment_like_count"]:
                    found_selector = self._find_working_selector(selectors, element_name)
                    structure["selectors"][element_name] = found_selector
                    
                    if found_selector:
                        try:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, found_selector)
                            structure["elements"][element_name] = len(elements)
                        except Exception:
                            structure["elements"][element_name] = 0

            # 检测评论特征
            comment_pattern = STRUCTURE_FEATURES["video_page"]["comment_pattern"]
            structure["features"]["has_comment_e2e"] = bool(re.search(comment_pattern, self.driver.page_source))

            # 检测视频播放器特征
            player_pattern = STRUCTURE_FEATURES["video_page"]["video_player_pattern"]
            structure["features"]["has_player_e2e"] = bool(re.search(player_pattern, self.driver.page_source))

            self.current_structure["video_page"] = structure
            logger.info(f"[detector] 视频页面结构检测完成")
            return structure

        except Exception as e:
            logger.error(f"[detector] 视频页面检测失败：{e}")
            return {"error": str(e)}

    def _try_open_comments(self):
        """尝试点击评论按钮"""
        comment_btn_selectors = [
            "div[class*='comment-btn']",
            "div[class*='CommentBtn']",
            "button[class*='comment']",
            "span[class*='comment-count']",
        ]
        for selector in comment_btn_selectors:
            try:
                comment_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                if comment_btn.is_displayed():
                    self.driver.execute_script("arguments[0].click();", comment_btn)
                    time.sleep(3)
                    logger.info("[detector] 已点击评论按钮")
                    break
            except Exception:
                continue

    def _find_working_selector(self, selectors: List[str], element_name: str) -> Optional[str]:
        """找到第一个有效的选择器"""
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    logger.info(f"[detector] {element_name}: 找到有效选择器 {selector} ({len(elements)} 个元素)")
                    return selector
            except Exception:
                continue
        logger.warning(f"[detector] {element_name}: 未找到有效选择器")
        return None

    def compare_with_history(self) -> List[Dict[str, Any]]:
        """对比当前结构与历史结构，返回变化列表"""
        self.changes = []

        # 对比搜索页面
        if self.structure_history.get("search_page"):
            search_changes = self._compare_page(
                "search_page",
                self.structure_history["search_page"],
                self.current_structure.get("search_page", {}),
            )
            self.changes.extend(search_changes)

        # 对比视频页面
        if self.structure_history.get("video_page"):
            video_changes = self._compare_page(
                "video_page",
                self.structure_history["video_page"],
                self.current_structure.get("video_page", {}),
            )
            self.changes.extend(video_changes)

        return self.changes

    def _compare_page(
        self, page_type: str, old_structure: Dict[str, Any], new_structure: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """对比单个页面的结构变化"""
        changes = []

        if not new_structure:
            return changes

        # 对比页面大小
        old_size = old_structure.get("page_size", 0)
        new_size = new_structure.get("page_size", 0)
        size_diff = abs(new_size - old_size)
        if size_diff > old_size * 0.1:  # 变化超过 10%
            changes.append({
                "type": "page_size_change",
                "page": page_type,
                "old_value": old_size,
                "new_value": new_size,
                "change_percent": f"{(size_diff / old_size * 100):.1f}%",
                "severity": "medium",
            })

        # 对比 SSR 特征
        old_ssr = old_structure.get("features", {}).get("has_ssr_data", False)
        new_ssr = new_structure.get("features", {}).get("has_ssr_data", False)
        if old_ssr != new_ssr:
            changes.append({
                "type": "ssr_structure_change",
                "page": page_type,
                "old_value": old_ssr,
                "new_value": new_ssr,
                "severity": "high",
                "suggestion": "SSR 数据结构发生变化，需检查 _extract_from_ssr 方法",
            })

        # 对比选择器
        old_selectors = old_structure.get("selectors", {})
        new_selectors = new_structure.get("selectors", {})
        for element_name, new_selector in new_selectors.items():
            old_selector = old_selectors.get(element_name)
            if old_selector and old_selector != new_selector:
                changes.append({
                    "type": "selector_change",
                    "page": page_type,
                    "element": element_name,
                    "old_selector": old_selector,
                    "new_selector": new_selector,
                    "severity": "high",
                    "suggestion": f"更新 douyin_api.py 中 {element_name} 的选择器",
                })
            elif not old_selector and new_selector:
                changes.append({
                    "type": "new_selector_found",
                    "page": page_type,
                    "element": element_name,
                    "new_selector": new_selector,
                    "severity": "low",
                })

        # 对比元素数量
        old_elements = old_structure.get("elements", {})
        new_elements = new_structure.get("elements", {})
        for element_name, new_count in new_elements.items():
            old_count = old_elements.get(element_name, 0)
            if old_count > 0 and new_count == 0:
                changes.append({
                    "type": "element_disappeared",
                    "page": page_type,
                    "element": element_name,
                    "old_count": old_count,
                    "severity": "high",
                    "suggestion": f"元素 {element_name} 已消失，需检查选择器",
                })

        return changes

    def generate_report(self) -> str:
        """生成结构变化报告"""
        report_lines = [
            "=" * 70,
            "  📊 抖音 HTML 结构检测报告",
            f"  生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 70,
            "",
        ]

        if not self.changes:
            report_lines.append("✅ 未检测到明显结构变化")
            report_lines.append("")
            report_lines.append("提示：如果评论抓取仍然不准确，可能是：")
            report_lines.append("  1. 评论区需要滚动加载更多")
            report_lines.append("  2. Cookie 登录态过期")
            report_lines.append("  3. 遇到验证码验证")
        else:
            report_lines.append(f"⚠️  检测到 {len(self.changes)} 处结构变化：")
            report_lines.append("")

            # 按严重程度排序
            severity_order = {"high": 0, "medium": 1, "low": 2}
            self.changes.sort(key=lambda c: severity_order.get(c.get("severity", "low"), 3))

            for idx, change in enumerate(self.changes, 1):
                severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(change.get("severity", "low"), "⚪")
                report_lines.append(f"{idx}. {severity_icon} [{change.get('severity', 'unknown').upper()}] {change.get('type', '')}")
                report_lines.append(f"   页面：{change.get('page', '')}")
                
                if change.get("element"):
                    report_lines.append(f"   元素：{change.get('element', '')}")
                
                if change.get("old_selector") and change.get("new_selector"):
                    report_lines.append(f"   旧选择器：{change.get('old_selector', '')}")
                    report_lines.append(f"   新选择器：{change.get('new_selector', '')}")
                
                if change.get("suggestion"):
                    report_lines.append(f"   建议：{change.get('suggestion', '')}")
                
                report_lines.append("")

        # 输出当前有效的选择器
        report_lines.append("=" * 70)
        report_lines.append("  📋 当前检测到的有效选择器")
        report_lines.append("=" * 70)
        report_lines.append("")

        for page_type in ["search_page", "video_page"]:
            structure = self.current_structure.get(page_type, {})
            if structure:
                report_lines.append(f"**{page_type}**:")
                selectors = structure.get("selectors", {})
                for element_name, selector in selectors.items():
                    if selector:
                        report_lines.append(f"  - {element_name}: `{selector}`")
                report_lines.append("")

        report_lines.append("=" * 70)

        return "\n".join(report_lines)

    def save_report(self, output_dir: Optional[Path] = None):
        """保存检测报告"""
        if not output_dir:
            output_dir = Path(__file__).parent / "output" / "structure_reports"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = output_dir / f"douyin_structure_{timestamp}.md"

        report_content = self.generate_report()
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"[detector] 报告已保存：{report_path}")
        return str(report_path)

    def update_history(self):
        """更新历史结构数据"""
        if self.current_structure.get("search_page"):
            self.structure_history["search_page"] = self.current_structure["search_page"]
        if self.current_structure.get("video_page"):
            self.structure_history["video_page"] = self.current_structure["video_page"]
        self.structure_history["last_update"] = datetime.now().isoformat()
        self._save_history()

    def close(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("[detector] 浏览器已关闭")
            except Exception:
                pass


def detect_and_report(cookie_string: str, keywords: str = "抖音", video_url: Optional[str] = None) -> str:
    """执行结构检测并生成报告"""
    detector = HTMLStructureDetector(cookie_string=cookie_string)
    
    try:
        # 检测搜索页面
        detector.detect_search_page(keywords)
        
        # 检测视频页面（如果提供了视频 URL）
        if video_url:
            detector.detect_video_page(video_url)
        
        # 对比历史
        detector.compare_with_history()
        
        # 生成并保存报告
        report_path = detector.save_report()
        
        # 更新历史
        detector.update_history()
        
        # 打印报告
        print("\n" + detector.generate_report())
        
        return report_path
    finally:
        detector.close()


if __name__ == "__main__":
    # 测试运行
    import sys
    
    # 从命令行或环境变量获取 Cookie
    cookie = os.getenv("DOUYIN_COOKIE", "")
    if len(sys.argv) > 1:
        cookie = sys.argv[1]
    
    if not cookie:
        print("请提供抖音 Cookie:")
        print("用法：python html_structure_detector.py <cookie_string>")
        print("或设置环境变量：export DOUYIN_COOKIE='your_cookie'")
        sys.exit(1)
    
    report_path = detect_and_report(cookie)
    print(f"\n报告已保存：{report_path}")
