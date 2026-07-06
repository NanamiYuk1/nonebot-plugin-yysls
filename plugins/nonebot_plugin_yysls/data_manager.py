# data_manager.py
import json
import asyncio
from pathlib import Path
from typing import Set
from nonebot import logger

# 数据文件路径，存放在插件目录下的 data 文件夹中
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "subscribe_groups.json"

async def load_subscribed_groups() -> Set[int]:
    """从 JSON 文件异步加载订阅群号"""
    if DATA_FILE.exists():
        try:
            # 使用 to_thread 避免阻塞事件循环
            text = await asyncio.to_thread(DATA_FILE.read_text, encoding="utf-8")
            return set(json.loads(text))
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.error(f"[数据管理] 读取订阅群文件失败: {e}")
            return set()
    return set()

async def save_subscribed_groups(groups: Set[int]):
    """将订阅群号异步持久化到 JSON 文件"""
    try:
        data = json.dumps(list(groups), ensure_ascii=False, indent=2)
        await asyncio.to_thread(DATA_FILE.write_text, data, encoding="utf-8")
    except OSError as e:
        logger.error(f"[数据管理] 保存订阅群文件失败: {e}")