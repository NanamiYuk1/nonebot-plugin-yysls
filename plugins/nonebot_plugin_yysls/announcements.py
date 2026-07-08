import re
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Set
from nonebot import logger, get_bot
from nonebot.adapters.onebot.v11 import Bot
import httpx
from bs4 import BeautifulSoup

# ===== 1. 状态记录文件 =====
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PUSHED_CACHE_FILE = DATA_DIR / "pushed_announcements.json"

_pushed_cache: Optional[Set[str]] = None

async def load_pushed_cache() -> Set[str]:
    global _pushed_cache
    if _pushed_cache is not None:
        return _pushed_cache
    
    if PUSHED_CACHE_FILE.exists():
        try:
            text = await asyncio.to_thread(PUSHED_CACHE_FILE.read_text, encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, list):
                _pushed_cache = set(data)
            else:
                _pushed_cache = set()
        except Exception as e:
            logger.error(f"[燕云助手] 读取公告缓存失败：{e}")
            _pushed_cache = set()
    else:
        _pushed_cache = set()
        
    logger.debug(f"[燕云助手] 已加载 {len(_pushed_cache)} 条历史公告缓存")
    return _pushed_cache

async def save_pushed_cache(cache: Set[str]):
    global _pushed_cache
    _pushed_cache = cache
    try:
        trimmed = list(cache)[-200:]
        data = json.dumps(trimmed, ensure_ascii=False)
        await asyncio.to_thread(PUSHED_CACHE_FILE.write_text, data, encoding="utf-8")
    except Exception as e:
        logger.error(f"[燕云助手] 保存公告缓存失败：{e}")

# ===== 2. 公告解析逻辑 (✅ 适配网易官网结构) =====
def parse_announcements(html_content: str, base_url: str) -> List[Dict]:
    """使用 BeautifulSoup 解析网易官网新闻页 HTML"""
    soup = BeautifulSoup(html_content, "html.parser")
    announcements = []
    
    # 网易游戏官网常见的新闻列表结构
    # 尝试多种选择器以适配不同的 DOM 结构
    news_selectors = [
        ".news-list li",           # 常见的列表结构
        ".news_list li",
        ".news-item",              # 单个新闻项
        ".list-item",
        "[class*='news'] li",      # 包含 news 的 class
        "[class*='list'] li",
        "ul li",                   # 通用列表（作为 fallback）
    ]
    
    news_items = []
    for selector in news_selectors:
        news_items = soup.select(selector)
        if news_items:
            logger.debug(f"[燕云助手] 使用选择器 '{selector}' 找到 {len(news_items)} 个元素")
            break
    
    if not news_items:
        logger.warning("[燕云助手] 未找到新闻列表元素，尝试解析所有 <a> 标签")
        # Fallback: 解析所有 <a> 标签，过滤出新闻链接
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            title = a_tag.get_text(strip=True)
            
            if not title or len(title) < 4:
                continue
            
            # 过滤非新闻链接
            if not any(keyword in href.lower() for keyword in ["/news/", "/official/", "/update/", "/activity/"]):
                continue
            
            if href.startswith("/"):
                full_link = f"{base_url}{href}"
            else:
                full_link = href
            
            announcements.append({
                "date": "最新",
                "category": "新闻",
                "title": title,
                "link": full_link
            })
    else:
        # 解析找到的新闻列表项
        for item in news_items:
            try:
                # 提取分类（如：新闻、公告、活动）
                category_tag = item.select_one(".tag, .category, .type, [class*='tag'], [class*='category']")
                category = category_tag.get_text(strip=True) if category_tag else "新闻"
                
                # 提取标题和链接
                link_tag = item.select_one("a")
                if not link_tag:
                    continue
                
                title = link_tag.get_text(strip=True) or link_tag.get("title", "")
                href = link_tag.get("href", "")
                
                if not title or not href:
                    continue
                
                # 构建完整 URL
                if href.startswith("/"):
                    full_link = f"{base_url}{href}"
                elif href.startswith("http"):
                    full_link = href
                else:
                    full_link = f"{base_url}/{href}"
                
                # 提取日期
                date_tag = item.select_one(".date, .time, [class*='date'], [class*='time']")
                date_str = date_tag.get_text(strip=True) if date_tag else "最新"
                
                announcements.append({
                    "date": date_str,
                    "category": category,
                    "title": title,
                    "link": full_link
                })
            except Exception as e:
                logger.debug(f"[燕云助手] 解析新闻条目出错：{e}")
                continue
    
    # 去重（按链接）
    seen_links = set()
    unique_announcements = []
    for ann in announcements:
        if ann["link"] not in seen_links:
            seen_links.add(ann["link"])
            unique_announcements.append(ann)
    
    logger.info(f"[燕云助手] 成功解析 {len(unique_announcements)} 条新闻")
    return unique_announcements

# ===== 3. 核心推送逻辑 =====
async def check_and_push_announcements(
    subscribe_groups: set,
    news_url: str,
    base_url: str
):
    if not subscribe_groups:
        return

    logger.info("[燕云助手] 开始检查官网公告...")
    
    try:
        response = await get_http_content(news_url)
        if not response:
            logger.error("[燕云助手] 获取官网公告失败")
            return

        announcements = parse_announcements(response, base_url)
        if not announcements:
            logger.warning("[燕云助手] 未解析到有效公告")
            return

        pushed_cache = await load_pushed_cache()
        new_announcements = []

        for ann in announcements:
            if ann["link"] not in pushed_cache:
                new_announcements.append(ann)

        if not new_announcements:
            logger.info("[燕云助手] 无新公告，跳过推送")
            return

        logger.info(f"[燕云助手] 发现 {len(new_announcements)} 条新公告")
        
        new_announcements.reverse()
        
        bot = get_bot()
        success_links = []

        for ann in new_announcements:
            msg = format_announcement_message(ann)
            for group_id in subscribe_groups:
                try:
                    await bot.send_group_msg(group_id=group_id, message=msg)
                except Exception as e:
                    logger.error(f"[燕云助手] 推送公告到群 {group_id} 失败：{e}")
            
            success_links.append(ann["link"])
            logger.info(f"[燕云助手] 已推送公告：{ann['title']}")

        if success_links:
            pushed_cache.update(success_links)
            await save_pushed_cache(pushed_cache)
            logger.info(f"[燕云助手] 缓存已更新，当前共 {len(pushed_cache)} 条记录")

    except Exception as e:
        logger.exception(f"[燕云助手] 公告检查异常：{e}")

# ===== 4. 工具函数 =====
async def get_http_content(url: str) -> Optional[str]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Referer": "https://www.yysls.cn/"
        }
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as e:
        logger.error(f"[燕云助手] 获取 {url} 失败：{e}")
        return None

def format_announcement_message(announcement: Dict) -> str:
    return (
        f"[燕云十六声 - {announcement.get('category', '最新公告')}]\n"
        f"------------------------\n"
        f"日期：{announcement['date']}\n"
        f"标题：{announcement['title']}\n"
        f"链接：{announcement['link']}\n"
        f"------------------------\n"
        f"点击链接查看完整公告内容"
    )