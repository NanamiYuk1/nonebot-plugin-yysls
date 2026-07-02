# auto_extract.py
import re
import time
from typing import Optional, Tuple, Dict, List
from nonebot import logger
from .cdkey import add_cdkey

# ============================================================
#  恶意录入防护配置
# ============================================================
# 滑动窗口限流：每个用户每60秒最多触发3次有效录入
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 3

# 兑换码合法性校验正则（仅允许字母、数字、中文、下划线、连字符）
VALID_CODE_PATTERN = re.compile(r'^[A-Za-z0-9\u4e00-\u9fa5_\-]+$')

# 固定前缀匹配（兼容全半角冒号、空格）
TRIGGER_PATTERN = re.compile(
    r'燕云十六声兑换码[：:\s]+([A-Za-z0-9\u4e00-\u9fa5_\-]{2,24})'
)

# 内存级限流记录 {user_id: [timestamp1, timestamp2, ...]}
_rate_limit_cache: Dict[int, List[float]] = {}


def _check_rate_limit(user_id: int) -> bool:
    """检查用户是否超出频率限制，未超限则记录本次时间戳"""
    now = time.time()
    if user_id not in _rate_limit_cache:
        _rate_limit_cache[user_id] = []

    # 清理窗口外的过期记录
    _rate_limit_cache[user_id] = [
        ts for ts in _rate_limit_cache[user_id]
        if now - ts < RATE_LIMIT_WINDOW
    ]

    if len(_rate_limit_cache[user_id]) >= RATE_LIMIT_MAX:
        return False

    _rate_limit_cache[user_id].append(now)
    return True


def _is_valid_code(code: str) -> bool:
    """校验兑换码内容合法性"""
    # 长度校验（2~24位）
    if not (2 <= len(code) <= 24):
        return False
    # 字符合法性校验
    if not VALID_CODE_PATTERN.match(code):
        return False
    # 纯数字/纯符号堆砌检测（至少包含1个字母或中文）
    has_alpha_or_cn = any(
        c.isalpha() or '\u4e00' <= c <= '\u9fa5' for c in code
    )
    return has_alpha_or_cn


def extract_cdkey_from_text(text: str) -> Optional[str]:
    """从已确认包含触发词的文本中提取兑换码"""
    normalized = text.replace(":", "：")
    match = TRIGGER_PATTERN.search(normalized)
    if match:
        return match.group(1).strip()
    return None


def try_auto_add_cdkey(text: str, source: str, user_id: int = 0) -> Tuple[Optional[str], Optional[str]]:
    """尝试从文本提取并录入兑换码（含完整防护链路）"""
    # 1. 频率限制检查
    if user_id and not _check_rate_limit(user_id):
        logger.warning(f"[自动提取·限流] 用户{user_id} 触发过于频繁 | 来源: {source}")
        return None, "操作过于频繁，请稍后再试"

    # 2. 提取兑换码
    code = extract_cdkey_from_text(text)
    if not code:
        return None, None

    # 3. 内容合法性校验
    if not _is_valid_code(code):
        logger.warning(f"[自动提取·拦截] 非法兑换码格式: {code} | 用户: {user_id}")
        return None, "❌ 兑换码格式不合法，请检查后重试"

    # 4. 执行录入
    result = add_cdkey(code, source=source)

    if result == "added":
        logger.info(f"[自动提取] 新兑换码 {code} 已录入 | 用户: {user_id} | 来源: {source}")
        return code, "新兑换码已自动录入"
    elif result == "reactivated":
        logger.info(f"[自动提取] 过期兑换码 {code} 已重新激活 | 用户: {user_id} | 来源: {source}")
        return code, "该兑换码曾过期，已重新激活"
    elif result == "updated":
        return code, "兑换码备注已更新"
    else:
        logger.debug(f"[自动提取] 兑换码 {code} 已存在，跳过 | 用户: {user_id}")
        return None, None