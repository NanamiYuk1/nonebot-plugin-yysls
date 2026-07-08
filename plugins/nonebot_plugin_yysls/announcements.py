import re
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Set
from urllib.parse import urlparse, urlunparse
from nonebot import logger, get_bot
from nonebot.adapters.onebot.v11 import Bot, MessageSegment, Message
import httpx
from bs4 import BeautifulSoup

# ===== 1. 状态记录文件 =====
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PUSHED_CACHE_FILE = DATA_DIR / "pushed_announcements.json"

_pushed_cache: Optional[Set[str]] = None
_pushed_titles: Optional[Set[str]] = None

async def load_pushed_cache() -> tuple[Set[str], Set[str]]:
    global _pushed_cache, _pushed_titles
    if _pushed_cache is not None and _pushed_titles is not None:
        return _pushed_cache, _pushed_titles
    
    if PUSHED_CACHE_FILE.exists():
        try:
            text = await asyncio.to_thread(PUSHED_CACHE_FILE.read_text, encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                _pushed_cache = set(data.get("links", []))
                _pushed_titles = set(data.get("titles", []))
            else:
                # 兼容旧版纯列表格式
                _pushed_cache = set(data) if isinstance(data, list) else set()
                _pushed_titles = set()
        except Exception as e:
            logger.error(f"[燕云助手] 读取公告缓存失败：{e}")
            _pushed_cache = set()
            _pushed_titles = set()
    else:
        _pushed_cache = set()
        _pushed_titles = set()
        
    logger.debug(f"[燕云助手] 已加载 {len(_pushed_cache)} 条历史链接缓存，{len(_pushed_titles)} 条标题缓存")
    return _pushed_cache, _pushed_titles

async def save_pushed_cache(links: Set[str], titles: Set[str]):
    global _pushed_cache, _pushed_titles
    _pushed_cache = links
    _pushed_titles = titles
    try:
        # 限制缓存大小，防止文件无限增长
        trimmed_links = list(links)[-300:]
        trimmed_titles = list(titles)[-300:]
        data = json.dumps({"links": trimmed_links, "titles": trimmed_titles}, ensure_ascii=False)
        await asyncio.to_thread(PUSHED_CACHE_FILE.write_text, data, encoding="utf-8")
    except Exception as e:
        logger.error(f"[燕云助手] 保存公告缓存失败：{e}")

# ===== 2. URL 标准化工具 =====
def normalize_url(url: str) -> str:
    """清理 URL，去除追踪参数和末尾斜杠，确保比对准确"""
    if not url: return ""
    try:
        parsed = urlparse(url)
        # 去除常见的追踪参数
        query = parsed.query
        if query:
            clean_queries = [q for q in query.split('&') if not q.startswith(('spm=', 'from=', 't=', 'timestamp='))]
            query = '&'.join(clean_queries)
        
        # 重新构建 URL
        normalized = urlunparse((
            parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), 
            parsed.params, query, '' # 去除 fragment (#xxx)
        ))
        return normalized
    except Exception:
        return url.rstrip('/')

# ===== 3. 公告解析逻辑 (适配网易官网结构) =====
def parse_announcements(html_content: str, base_url: str) -> List[Dict]:
    """使用 BeautifulSoup 解析网易官网新闻页 HTML"""
    soup = BeautifulSoup(html_content, "html.parser")
    announcements = []
    
    # 尝试多种常见的新闻列表选择器
    news_selectors = [
        ".news-list li", ".news_list li", ".news-item", ".list-item",
        "[class*='news'] li", "[class*='list'] li", "ul li",
    ]
    
    news_items = []
    for selector in news_selectors:
        news_items = soup.select(selector)
        if news_items:
            logger.debug(f"[燕云助手] 使用选择器 '{selector}' 找到 {len(news_items)} 个元素")
            break
    
    if not news_items:
        logger.warning("[燕云助手] 未找到新闻列表元素，尝试解析所有 <a> 标签")
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            title = a_tag.get_text(strip=True)
            
            if not title or len(title) < 4: continue
            if not any(keyword in href.lower() for keyword in ["/news/", "/official/", "/update/", "/activity/"]): continue
            
            full_link = f"{base_url}{href}" if href.startswith("/") else href
            announcements.append({"date": "最新", "category": "新闻", "title": title, "link": normalize_url(full_link)})
    else:
        for item in news_items:
            try:
                category_tag = item.select_one(".tag, .category, .type, [class*='tag'], [class*='category']")
                category = category_tag.get_text(strip=True) if category_tag else "新闻"
                
                link_tag = item.select_one("a")
                if not link_tag: continue
                
                title = link_tag.get_text(strip=True) or link_tag.get("title", "")
                href = link_tag.get("href", "")
                if not title or not href: continue
                
                if href.startswith("/"): full_link = f"{base_url}{href}"
                elif href.startswith("http"): full_link = href
                else: full_link = f"{base_url}/{href}"
                
                date_tag = item.select_one(".date, .time, [class*='date'], [class*='time']")
                date_str = date_tag.get_text(strip=True) if date_tag else "最新"
                
                announcements.append({
                    "date": date_str, "category": category, 
                    "title": title.strip(), "link": normalize_url(full_link)
                })
            except Exception as e:
                logger.debug(f"[燕云助手] 解析新闻条目失败：{e}")
                continue
    
    # 内部去重
    seen_links = set()
    unique_announcements = []
    for ann in announcements:
        if ann["link"] not in seen_links:
            seen_links.add(ann["link"])
            unique_announcements.append(ann)
    
    logger.info(f"[燕云助手] 成功解析 {len(unique_announcements)} 条新闻")
    return unique_announcements

# ===== 4. 核心推送逻辑 (严格去重 + 合并转发) =====
async def check_and_push_announcements(subscribe_groups: set, news_url: str, base_url: str):
    if not subscribe_groups: return

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

        pushed_links, pushed_titles = await load_pushed_cache()
        new_announcements = []

        # 🔥 严格去重：只要链接或标题在缓存中，就视为旧公告，绝不重复推送
        for ann in announcements:
            link = ann["link"]
            title = ann["title"]
            
            if link in pushed_links or title in pushed_titles:
                continue
                
            new_announcements.append(ann)

        if not new_announcements:
            logger.info("[燕云助手] 无新公告，跳过推送")
            return

        logger.info(f"[燕云助手] 发现 {len(new_announcements)} 条新公告，准备推送")
        
        # 按时间正序排列（旧的在上，新的在下）
        new_announcements.reverse()
        
        bot = get_bot()
        
        # 🔥 构建合并转发消息的节点列表
        nodes = []
        success_links = []
        success_titles = []
        
        # 添加一个头部说明节点
        header_msg = f"📢 燕云十六声官网发布了 {len(new_announcements)} 条新公告，请查阅：\n官网链接：{news_url}"
        nodes.append(
            MessageSegment.node_custom(
                user_id=int(bot.self_id),
                nickname="燕云十六声助手",
                content=Message(header_msg)
            )
        )

        for ann in new_announcements:
            msg_content = format_announcement_message(ann)
            # 构建自定义节点
            node = MessageSegment.node_custom(
                user_id=int(bot.self_id),
                nickname="燕云十六声助手",
                content=Message(msg_content)
            )
            nodes.append(node)
            success_links.append(ann["link"])
            success_titles.append(ann["title"])

        # 发送到所有订阅群
        for group_id in subscribe_groups:
            try:
                # 调用 OneBot V11 底层 API 发送合并转发消息
                await bot.call_api(
                    "send_group_forward_msg",
                    group_id=int(group_id),
                    messages=nodes
                )
                logger.success(f"[燕云助手] 成功向群 {group_id} 推送合并转发公告")
            except Exception as e:
                logger.error(f"[燕云助手] 推送公告到群 {group_id} 失败：{e}")
                # 如果合并转发失败，降级为普通文本发送
                try:
                    fallback_msg = f"📢 燕云十六声官网发布了 {len(new_announcements)} 条新公告：\n\n"
                    for ann in new_announcements:
                        fallback_msg += format_announcement_message(ann) + "\n\n"
                    await bot.send_group_msg(group_id=int(group_id), message=fallback_msg)
                except Exception as fallback_e:
                    logger.error(f"[燕云助手] 降级推送也失败：{fallback_e}")

        # 🔥 推送成功后，将新链接和新标题加入缓存，确保下次绝对不会重复推送
        if success_links:
            pushed_links.update(success_links)
            pushed_titles.update(success_titles)
            await save_pushed_cache(pushed_links, pushed_titles)
            logger.info(f"[燕云助手] 缓存已更新，当前共 {len(pushed_links)} 条链接，{len(pushed_titles)} 条标题")

    except Exception as e:
        logger.exception(f"[燕云助手] 公告检查异常：{e}")

# ===== 5. 工具函数 =====
async def get_http_content(url: str) -> Optional[str]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Referer": "https://www.yysls.cn/"
        }
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as e:
        logger.error(f"[燕云助手] 获取 {url} 失败：{e}")
        return None

def format_announcement_message(announcement: Dict) -> str:
    return (
        f"【{announcement.get('category', '最新公告')}】\n"
        f"日期：{announcement['date']}\n"
        f"标题：{announcement['title']}\n"
        f"🔗 链接：{announcement['link']}"
    )