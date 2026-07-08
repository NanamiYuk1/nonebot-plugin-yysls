import json
import asyncio
from pathlib import Path
from typing import Set
from nonebot import logger

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "subscribe_groups.json"

async def load_subscribed_groups() -> Set[int]:
    if DATA_FILE.exists():
        try:
            text = await asyncio.to_thread(DATA_FILE.read_text, encoding="utf-8")
            return set(json.loads(text))
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.error(f"[数据管理] 读取订阅群文件失败：{e}")
            return set()
    return set()

async def save_subscribed_groups(groups: Set[int]):
    try:
        data = json.dumps(list(groups), ensure_ascii=False, indent=2)
        await asyncio.to_thread(DATA_FILE.write_text, data, encoding="utf-8")
    except OSError as e:
        logger.error(f"[数据管理] 保存订阅群文件失败：{e}")