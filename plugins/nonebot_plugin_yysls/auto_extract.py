import re
import time
from typing import Optional, Tuple, Dict, List
from nonebot import logger
from .cdkey import add_cdkey

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 3

VALID_CODE_PATTERN = re.compile(r'^[A-Za-z0-9\u4e00-\u9fa5_\-]+$')

TRIGGER_PATTERN = re.compile(
    r'燕云十六声兑换码 [：:\s]+([A-Za-z0-9\u4e00-\u9fa5_\-]{2,24})'
)

_rate_limit_cache: Dict[int, List[float]] = {}

def _check_rate_limit(user_id: int) -> bool:
    now = time.time()
    if user_id not in _rate_limit_cache:
        _rate_limit_cache[user_id] = []

    _rate_limit_cache[user_id] = [
        ts for ts in _rate_limit_cache[user_id]
        if now - ts < RATE_LIMIT_WINDOW
    ]

    if len(_rate_limit_cache[user_id]) >= RATE_LIMIT_MAX:
        return False

    _rate_limit_cache[user_id].append(now)
    return True

def _is_valid_code(code: str) -> bool:
    if not (2 <= len(code) <= 24):
        return False
    if not VALID_CODE_PATTERN.match(code):
        return False
    has_alpha_or_cn = any(
        c.isalpha() or '\u4e00' <= c <= '\u9fa5' for c in code
    )
    return has_alpha_or_cn

def extract_cdkey_from_text(text: str) -> Optional[str]:
    normalized = text.replace(":", "：")
    match = TRIGGER_PATTERN.search(normalized)
    if match:
        return match.group(1).strip()
    return None

async def try_auto_add_cdkey(text: str, source: str, user_id: int = 0) -> Tuple[Optional[str], Optional[str]]:
    if user_id and not _check_rate_limit(user_id):
        logger.warning(f"[自动提取·限流] 用户{user_id} 触发过于频繁 | 来源：{source}")
        return None, "操作过于频繁，请稍后再试"

    code = extract_cdkey_from_text(text)
    if not code:
        return None, None

    if not _is_valid_code(code):
        logger.warning(f"[自动提取·拦截] 非法兑换码格式：{code} | 用户：{user_id}")
        return None, "❌ 兑换码格式不合法，请检查后重试"

    result = await add_cdkey(code, source=source)

    if result == "added":
        logger.info(f"[自动提取] 新兑换码 {code} 已录入 | 用户：{user_id} | 来源：{source}")
        return code, "新兑换码已自动录入"
    elif result == "reactivated":
        logger.info(f"[自动提取] 过期兑换码 {code} 已重新激活 | 用户：{user_id} | 来源：{source}")
        return code, "该兑换码曾过期，已重新激活"
    elif result == "updated":
        return code, "兑换码备注已更新"
    else:
        logger.debug(f"[自动提取] 兑换码 {code} 已存在，跳过 | 用户：{user_id}")
        return None, None