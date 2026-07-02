import re
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from nonebot import require, get_bot, logger
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, Message, MessageSegment

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CDKEY_FILE = DATA_DIR / "cdkeys.json"


def load_cdkeys() -> List[Dict]:
    if CDKEY_FILE.exists():
        return json.loads(CDKEY_FILE.read_text(encoding="utf-8"))
    return []


def save_cdkeys(cdkeys: List[Dict]):
    CDKEY_FILE.write_text(
        json.dumps(cdkeys, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_cdkey(code: str, source: str = "手动录入", note: str = "") -> str:
    """
    添加兑换码。
    返回值: 
      - "added": 新添加成功
      - "reactivated": 重新激活了已过期的码
      - "updated": 已存在但更新了备注
      - "exists": 码已存在且未过期（无备注更新）
    """
    cdkeys = load_cdkeys()
    for item in cdkeys:
        if item["code"] == code:
            if item.get("expired"):
                item["expired"] = False
                if note:
                    item["note"] = note
                item["added_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_cdkeys(cdkeys)
                return "reactivated"
            
            if note: 
                item["note"] = note
                save_cdkeys(cdkeys)
                return "updated"
            
            return "exists"

    cdkeys.append({
        "code": code,
        "source": source,
        "note": note,
        "added_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "expired": False,
    })
    save_cdkeys(cdkeys)
    return "added"


def get_active_cdkeys() -> List[Dict]:
    """获取所有未过期的兑换码"""
    cdkeys = load_cdkeys()
    return [item for item in cdkeys if not item.get("expired", False)]


def mark_cdkey_expired(code: str) -> bool:
    cdkeys = load_cdkeys()
    for item in cdkeys:
        if item["code"] == code:
            item["expired"] = True
            save_cdkeys(cdkeys)
            return True
    return False


def reactivate_cdkey(code: str) -> bool:
    cdkeys = load_cdkeys()
    for item in cdkeys:
        if item["code"] == code and item.get("expired"):
            item["expired"] = False
            item["added_time"] = datetime.now().strftime("%Y-%m-%d %H:%M (重新激活)")
            save_cdkeys(cdkeys)
            return True
    return False


def update_cdkey_note(code: str, note: str) -> bool:
    """单独更新兑换码的备注"""
    cdkeys = load_cdkeys()
    for item in cdkeys:
        if item["code"] == code:
            item["note"] = note
            save_cdkeys(cdkeys)
            return True
    return False


# ============ 命令处理函数 ============

async def handle_cdkey_list(bot: Bot, event: MessageEvent):
    """查看当前可用兑换码"""
    active = get_active_cdkeys()
    if not active:
        await bot.send(event, "当前没有可用的兑换码~\n管理员可使用 /add_cdkey <码> 添加")
        return

    msg_lines = ["【燕云十六声·可用兑换码】\n"]
    for i, item in enumerate(active, 1):
        line = f"{i}. {item['code']}"
        if item.get("note"):
            line += f" - {item['note']}"
        msg_lines.append(line)

    msg_lines.append("\n请尽快兑换，过期不候哦！")
    await bot.send(event, "\n".join(msg_lines))


async def handle_add_cdkey(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """管理员添加兑换码"""
    text = args.extract_plain_text().strip()
    if not text:
        await bot.send(event, "用法：/add_cdkey <兑换码> [备注]\n例如：/add_cdkey YYSLS2026 7月5日过期")
        return

    parts = text.split(maxsplit=1)
    code = parts[0].strip().upper()
    note = parts[1].strip() if len(parts) > 1 else ""

    result = add_cdkey(code, source="管理员手动录入", note=note)
    if result == "added":
        await bot.send(event, f"兑换码 {code} 已添加！")
    elif result == "reactivated":
        await bot.send(event, f"兑换码 {code} 原本已过期，现已为您重新激活！")
    elif result == "updated":
        await bot.send(event, f"兑换码 {code} 的备注已更新！")
    else:
        await bot.send(event, f"兑换码 {code} 已存在且正在生效中，无需重复添加！")


async def handle_expire_cdkey(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """标记兑换码过期"""
    code = args.extract_plain_text().strip().upper()
    if not code:
        await bot.send(event, "用法：/expire_cdkey <兑换码>")
        return

    if mark_cdkey_expired(code):
        await bot.send(event, f"兑换码 {code} 已标记为过期")
    else:
        await bot.send(event, f"未找到兑换码 {code}")


async def handle_reactivate_cdkey(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """重新激活兑换码"""
    code = args.extract_plain_text().strip().upper()
    if not code:
        await bot.send(event, "用法：/re_cdkey <兑换码>")
        return

    if reactivate_cdkey(code):
        await bot.send(event, f"兑换码 {code} 已重新激活！")
    else:
        await bot.send(event, f"未找到已过期的兑换码 {code}，或该码当前仍可用。")


async def handle_edit_note(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """单独新增或修改已有兑换码的备注"""
    text = args.extract_plain_text().strip()
    if not text:
        await bot.send(event, "用法：/edit_note <兑换码> <新备注>\n例如：/edit_note YYSLS2026 7月最新福利")
        return

    parts = text.split(maxsplit=1)
    code = parts[0].strip().upper()
    
    if len(parts) < 2 or not parts[1].strip():
        await bot.send(event, f"请输入要修改的备注内容！\n用法：/edit_note {code} <新备注>")
        return
        
    note = parts[1].strip()

    if update_cdkey_note(code, note):
        await bot.send(event, f"成功！兑换码 {code} 的备注已更新为：{note}")
    else:
        await bot.send(event, f"未找到兑换码 {code}，请检查兑换码是否正确。")


# ============ 🌟 智能过期识别与自动清理 ============

def extract_expiry_date(note: str) -> Optional[datetime]:
    """
    从备注文本中智能提取过期时间。
    支持格式：2026-07-05, 2026/7/5, 2026年7月5日, 7月5日, 20260705 等。
    """
    if not note:
        return None

    now = datetime.now()
    
    # 1. 匹配带年份的格式：2026-07-05, 2026/7/5, 2026年7月5日, 2026.7.5
    match = re.search(r'(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})[日号]?', note)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return datetime(y, m, d, 23, 59, 59)  # 默认到当天晚上 23:59:59 过期
        except ValueError:
            pass

    # 2. 匹配不带年份的格式：7月5日, 7-5, 7/5 (默认使用当前年份)
    match = re.search(r'(\d{1,2})[-/月.](\d{1,2})[日号]?', note)
    if match:
        m, d = int(match.group(1)), int(match.group(2))
        try:
            expiry = datetime(now.year, m, d, 23, 59, 59)
            # 如果提取的日期已经过了（比如现在是8月，备注写的是7月），则自动认为是明年的
            if expiry < now:
                expiry = expiry.replace(year=now.year + 1)
            return expiry
        except ValueError:
            pass

    # 3. 匹配纯数字格式：20260705
    match = re.search(r'(\d{4})(\d{2})(\d{2})', note)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return datetime(y, m, d, 23, 59, 59)
        except ValueError:
            pass

    return None


# 🌟 定时任务：每天凌晨 00:05 自动检查并清理过期兑换码
@scheduler.scheduled_job(
    "cron",
    hour=0,
    minute=5,
    id="yysls_auto_expire_cdkeys",
    misfire_grace_time=3600,
)
async def auto_expire_cdkeys():
    """自动将到达过期时间的兑换码标记为过期"""
    cdkeys = load_cdkeys()
    now = datetime.now()
    expired_count = 0
    expired_codes = []

    for item in cdkeys:
        if item.get("expired"):
            continue  # 已经过期的跳过
        
        note = item.get("note", "")
        expiry_date = extract_expiry_date(note)
        
        # 如果识别到了过期时间，且当前时间已经超过了该时间
        if expiry_date and now > expiry_date:
            item["expired"] = True
            expired_count += 1
            expired_codes.append(item["code"])

    if expired_count > 0:
        save_cdkeys(cdkeys)
        logger.info(f"[燕云助手] 自动清理了 {expired_count} 个过期兑换码: {', '.join(expired_codes)}")