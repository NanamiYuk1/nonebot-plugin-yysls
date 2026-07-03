import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Set
from nonebot import logger, get_bot
from nonebot.adapters.onebot.v11 import Bot
import httpx

# ===== 1. 状态记录文件 (升级为记录已推送的公告链接集合) =====
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PUSHED_CACHE_FILE = DATA_DIR / "pushed_announcements.json"

# 内存缓存，避免频繁读写磁盘
_pushed_cache: Optional[Set[str]] = None

def load_pushed_cache() -> Set[str]:
    """加载已推送公告的链接集合"""
    global _pushed_cache
    if _pushed_cache is not None:
        return _pushed_cache
    
    if PUSHED_CACHE_FILE.exists():
        try:
            data = json.loads(PUSHED_CACHE_FILE.read_text(encoding="utf-8"))
            # 兼容旧格式或新格式
            if isinstance(data, list):
                _pushed_cache = set(data)
            else:
                _pushed_cache = set()
        except Exception as e:
            logger.error(f"[燕云助手] 读取公告缓存失败: {e}")
            _pushed_cache = set()
    else:
        _pushed_cache = set()
        
    logger.debug(f"[燕云助手] 已加载 {len(_pushed_cache)} 条历史公告缓存")
    return _pushed_cache

def save_pushed_cache(cache: Set[str]):
    """保存已推送公告缓存到磁盘"""
    global _pushed_cache
    _pushed_cache = cache
    try:
        # 只保留最近 200 条记录，防止文件无限膨胀
        trimmed = list(cache)[-200:]
        PUSHED_CACHE_FILE.write_text(
            json.dumps(trimmed, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"[燕云助手] 保存公告缓存失败: {e}")

# ===== 2. 公告解析逻辑 =====
def parse_announcements(html_content: str) -> List[Dict]:
    """解析官网公告列表，返回结构化数据"""
    items = re.findall(
        r'<div class="news-item.*?">.*?<div class="date">(.*?)</div>.*?<h3>(.*?)</h3>.*?<a href="(.*?)".*?</a>',
        html_content,
        re.DOTALL
    )
    
    announcements = []
    for date, title, link in items:
        title = re.sub(r'\s+', ' ', title).strip()
        full_link = f"https://yysls.com{link}" if not link.startswith("http") else link
        
        announcements.append({
            "date": date.strip(),
            "title": title,
            "link": full_link
        })
    
    # 按列表原始顺序（通常官网已是最新在前），这里保持解析顺序即可
    return announcements

# ===== 3. 核心推送逻辑 =====
async def check_and_push_announcements(
    subscribe_groups: set,
    news_url: str,
    base_url: str  # 保留参数以兼容 __init__.py 的调用
):
    """检查并推送新公告 - 支持多条漏推补发 + 缓存去重"""
    if not subscribe_groups:
        return

    logger.info("[燕云助手] 开始检查官网公告...")
    
    try:
        response = await get_http_content(news_url)
        if not response:
            logger.error("[燕云助手] 获取官网公告失败")
            return

        announcements = parse_announcements(response)
        if not announcements:
            logger.warning("[燕云助手] 未解析到有效公告")
            return

        pushed_cache = load_pushed_cache()
        new_announcements = []

        # 筛选出未推送过的新公告
        for ann in announcements:
            if ann["link"] not in pushed_cache:
                new_announcements.append(ann)

        if not new_announcements:
            logger.info("[燕云助手] 无新公告，跳过推送")
            return

        logger.info(f"[燕云助手] 发现 {len(new_announcements)} 条新公告")
        
        # ⚠️ 注意：new_announcements 是最新在前，推送时应倒序（先发旧的再发新的）
        new_announcements.reverse()
        
        bot = get_bot()
        success_links = []

        for ann in new_announcements:
            msg = format_announcement_message(ann)
            for group_id in subscribe_groups:
                try:
                    await bot.send_group_msg(group_id=group_id, message=msg)
                except Exception as e:
                    logger.error(f"[燕云助手] 推送公告到群 {group_id} 失败: {e}")
            
            success_links.append(ann["link"])
            logger.info(f"[燕云助手] 已推送公告: {ann['title']}")

        # 批量更新缓存
        if success_links:
            pushed_cache.update(success_links)
            save_pushed_cache(pushed_cache)
            logger.info(f"[燕云助手] 缓存已更新，当前共 {len(pushed_cache)} 条记录")

    except Exception as e:
        logger.exception(f"[燕云助手] 公告检查异常: {e}")

# ===== 4. 工具函数 =====
async def get_http_content(url: str) -> Optional[str]:
    """获取HTTP内容"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as e:
        logger.error(f"[燕云助手] 获取 {url} 失败: {e}")
        return None

def format_announcement_message(announcement: Dict) -> str:
    """格式化公告消息"""
    return (
        f"[燕云十六声 - 最新公告]\n"
        f"------------------------\n"
        f"日期: {announcement['date']}\n"
        f"标题: {announcement['title']}\n"
        f"链接: {announcement['link']}\n"
        f"------------------------\n"
        f"点击链接查看完整公告内容"
    )