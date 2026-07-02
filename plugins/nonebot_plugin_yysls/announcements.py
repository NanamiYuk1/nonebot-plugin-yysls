import re
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot
from .config import YyslsConfig

# ===== 1. 新增状态记录文件 =====
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LAST_ANNOUNCEMENT_FILE = DATA_DIR / "last_announcement.json"

def load_last_announcement() -> Dict[str, str]:
    """加载最后推送的公告记录"""
    if LAST_ANNOUNCEMENT_FILE.exists():
        try:
            return json.loads(LAST_ANNOUNCEMENT_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {"last_date": "", "last_title": ""}

def save_last_announcement(date: str, title: str):
    """保存最新推送的公告记录"""
    LAST_ANNOUNCEMENT_FILE.write_text(
        json.dumps({"last_date": date, "last_title": title}, ensure_ascii=False),
        encoding="utf-8",
    )

# ===== 2. 优化公告解析逻辑 =====
def parse_announcements(html_content: str) -> List[Dict]:
    """解析官网公告列表，返回结构化数据"""
    # 提取所有公告条目
    items = re.findall(
        r'<div class="news-item.*?">.*?<div class="date">(.*?)</div>.*?<h3>(.*?)</h3>.*?<a href="(.*?)".*?</a>',
        html_content,
        re.DOTALL
    )
    
    announcements = []
    for date, title, link in items:
        # 清理标题中的多余空格和换行
        title = re.sub(r'\s+', ' ', title).strip()
        # 标准化日期格式 (06/19 -> 0619)
        date_key = date.replace("/", "").strip()
        
        announcements.append({
            "date": date,
            "date_key": date_key,
            "title": title,
            "link": f"https://yysls.com{link}" if not link.startswith("http") else link
        })
    
    # 按日期倒序排列 (最新公告在前)
    return sorted(announcements, key=lambda x: x["date_key"], reverse=True)

# ===== 3. 核心推送逻辑 =====
async def check_and_push_announcements(
    subscribe_groups: set,
    news_url: str,
    base_url: str
):
    """检查并推送新公告 - 仅推送最新一条"""
    if not subscribe_groups:
        return

    logger.info("[燕云助手] 开始检查官网公告...")
    
    try:
        # 获取官网内容
        response = await get_http_content(news_url)
        if not response:
            logger.error("[燕云助手] 获取官网公告失败")
            return

        # 解析公告列表
        announcements = parse_announcements(response)
        if not announcements:
            logger.warning("[燕云助手] 未解析到有效公告")
            return

        # 加载最后推送记录
        last_announcement = load_last_announcement()
        logger.debug(f"[燕云助手] 上次推送记录: {last_announcement}")

        # 查找最新公告
        latest = announcements[0]
        
        # 检查是否为新公告 (日期或标题变化)
        is_new = (latest["date_key"] != last_announcement["last_date"] or 
                  latest["title"] != last_announcement["last_title"])

        # 仅当有新公告时推送
        if not is_new:
            logger.info("[燕云助手] 无新公告，跳过推送")
            return

        # 发送最新公告
        msg = format_announcement_message(latest)
        bot = get_bot()
        for group_id in subscribe_groups:
            try:
                await bot.send_group_msg(group_id=group_id, message=msg)
                logger.info(f"[燕云助手] 已向群 {group_id} 推送新公告: {latest['title']}")
            except Exception as e:
                logger.error(f"[燕云助手] 推送公告到群 {group_id} 失败: {e}")

        # 更新最后推送记录
        save_last_announcement(latest["date_key"], latest["title"])
        logger.info(f"[燕云助手] 已更新最后推送记录: {latest['title']}")

    except Exception as e:
        logger.exception(f"[燕云助手] 公告检查异常: {e}")

# ===== 4. 工具函数 =====
async def get_http_content(url: str) -> Optional[str]:
    """获取HTTP内容"""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as e:
        logger.error(f"[燕云助手] 获取 {url} 失败: {e}")
        return None

def format_announcement_message(announcement: Dict) -> str:
    """格式化公告消息（无Emoji版）"""
    return (
        f"[燕云十六声 - 最新公告]\n"
        f"------------------------\n"
        f"日期: {announcement['date']}\n"
        f"标题: {announcement['title']}\n"
        f"链接: {announcement['link']}\n"
        f"------------------------\n"
        f"点击链接查看完整公告内容"
    )