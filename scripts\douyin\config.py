# -*- coding: utf-8 -*-
"""抖音爆款拆解器 - 配置与日志模块"""

import logging
import sys
from dataclasses import dataclass, field
from typing import List


@dataclass
class BrowserConfig:
    headless: bool = False
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )
    page_load_timeout: int = 120


@dataclass
class CrawlConfig:
    max_results: int = 20
    request_interval: float = 2.0
    save_format: str = "json"


@dataclass
class Settings:
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    crawl: CrawlConfig = field(default_factory=CrawlConfig)


global_settings = Settings()

_logger = None


def get_logger(name: str = "douyin_crawler") -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    _logger = logger
    return logger
