import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import re
import logging

logger = logging.getLogger("yysls")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.yysls.cn/",
}


class NewsItem:
    """新闻条目"""
    def __init__(self, title: str, url: str, date: str, category: str):
        self.title = title
        self.url = url
        self.date = date
        self.category = category

    def __repr__(self):
        return f"[{self.category}] {self.title} ({self.date})"

    def __eq__(self, other):
        if isinstance(other, NewsItem):
            return self.url == other.url
        return False

    def __hash__(self):
        return hash(self.url)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "date": self.date,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NewsItem":
        return cls(**data)


async def fetch_news_list(
    news_url: str = "https://www.yysls.cn/news/index.html",
    base_url: str = "https://www.yysls.cn",
) -> List[NewsItem]:
    """
    抓取官网新闻列表页，解析出所有新闻条目。

    官网结构（根据实际搜索到的页面）：
    - 新闻列表在 https://www.yysls.cn/news/index.html
    - 每条新闻包含：分类标签（新闻/公告/活动）、标题、日期、链接
    """
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            resp = await client.get(news_url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.error(f"抓取燕云官网新闻失败: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    news_list: List[NewsItem] = []

    # ========================================================
    # ⚠️  以下选择器需要根据官网实际 HTML 结构进行调整！
    #     官网使用了前端渲染（可能是 Vue/React），
    #     如果直接 GET 拿不到数据，可能需要：
    #     1. 找到后端 JSON API 接口（F12 抓包）
    #     2. 使用 Playwright/Selenium 渲染后再解析
    #     下面提供了两种解析方案的框架代码
    # ========================================================

    # --- 方案 A: 静态 HTML 解析（如果页面是 SSR） ---
    # 常见的新闻列表结构
    news_items = soup.select(".news-list li, .news_list .item, .list-item, [class*='news'] li")

    for item in news_items:
        try:
            # 尝试提取分类
            category_tag = item.select_one(".tag, .category, .type, [class*='tag']")
            category = category_tag.get_text(strip=True) if category_tag else "新闻"

            # 提取标题和链接
            link_tag = item.select_one("a")
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True) or link_tag.get("title", "")
            href = link_tag.get("href", "")
            if href and not href.startswith("http"):
                href = base_url + (href if href.startswith("/") else "/" + href)

            # 提取日期
            date_tag = item.select_one(".date, .time, [class*='date']")
            date_str = date_tag.get_text(strip=True) if date_tag else ""

            if title and href:
                news_list.append(NewsItem(title, href, date_str, category))
        except Exception as e:
            logger.debug(f"解析新闻条目出错: {e}")
            continue

    # --- 方案 C: 使用 RSSHub（推荐，最稳定） ---
    # 如果你自建了 RSSHub，可以直接请求 RSS 订阅源
    # RSSHub 路由示例: /yysls/news
    #
    # rsshub_url = "http://your-rsshub-instance.com/yysls/news"
    # async with httpx.AsyncClient() as client:
    #     resp = await client.get(rsshub_url)
    #     # 解析 RSS XML ...
    #     import feedparser
    #     feed = feedparser.parse(resp.text)
    #     for entry in feed.entries:
    #         news_list.append(NewsItem(
    #             title=entry.title,
    #             url=entry.link,
    #             date=entry.get("published", "")[:10],
    #             category="新闻",
    #         ))

    logger.info(f"成功抓取 {len(news_list)} 条燕云十六声新闻")
    return news_list


async def fetch_cdkey_from_activity(
    activity_url: str = "https://www.yysls.cn/news/acitivity/",
) -> List[Dict[str, str]]:
    """
    从活动页面抓取兑换码（如果有的话）。
    实际兑换码通常发布在微信公众号、微博等渠道，
    这里提供一个框架，你可以替换为实际的抓取逻辑。
    """
    cdkeys = []

    # 方案: 抓取网易大神/微信公众号文章中的兑换码
    # 这里仅作示例，实际需要根据具体来源定制
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            resp = await client.get(activity_url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # 尝试匹配常见兑换码格式：大写字母+数字，6-16位
        text = soup.get_text()
        import re
        # 兑换码正则（根据实际情况调整）
        pattern = r'\b([A-Z0-9]{6,16})\b'
        found = re.findall(pattern, text)

        for code in set(found):
            # 过滤掉明显不是兑换码的字符串
            if not code.isalpha():  # 纯字母大概率不是
                cdkeys.append({
                    "code": code,
                    "source": activity_url,
                    "found_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                })
    except Exception as e:
        logger.error(f"抓取兑换码失败: {e}")

    return cdkeys