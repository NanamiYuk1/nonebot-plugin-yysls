# data_manager.py
import json
from pathlib import Path

# 数据文件路径，存放在插件目录下的 data 文件夹中
DATA_DIR = Path(__file__).parent / "data"
DATA_FILE = DATA_DIR / "subscribe_groups.json"

def load_subscribed_groups() -> set:
    """从 JSON 文件加载订阅群号"""
    if DATA_FILE.exists():
        try:
            return set(json.loads(DATA_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError):
            return set()
    return set()

def save_subscribed_groups(groups: set):
    """将订阅群号持久化到 JSON 文件"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(list(groups), ensure_ascii=False, indent=2), 
        encoding="utf-8"
    )