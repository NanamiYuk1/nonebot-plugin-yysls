import re
import json
import asyncio
from pathlib import Path
from typing import List, Dict

import httpx
from nonebot import get_driver, get_bot, logger, require

# 引入 cdkey 模块的添加方法
from .cdkey import add_cdkey
from .data_manager import load_subscribed_groups

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

# 🆕 引入 B 站官方 API 库
from bilibili_api import user, Credential

# ============ 配置读取 ============
driver = get_driver()
config = driver.config

# 从 .env 文件中读取配置
AI_API_KEY = getattr(config, "ai_api_key", "")
AI_BASE_URL = getattr(config, "ai_base_url", "https://api.openai.com/v1")
AI_MODEL = getattr(config, "ai_model", "gpt-4o-mini")

BILIBILI_SESSDATA = getattr(config, "bilibili_sessdata", "")
BILIBILI_BILI_JCT = getattr(config, "bilibili_bili_jct", "")

# ============ 常量与路径 ============
YYSLS_BILI_UID = 1567141152  # 燕云十六声 B站官号 UID
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
HISTORY_FILE = DATA_DIR / "bili_dynamic_history.json"

# 🆕 初始化 B 站 Credential（登录凭证）
credential = None
if BILIBILI_SESSDATA and BILIBILI_BILI_JCT:
    credential = Credential(
        sessdata=BILIBILI_SESSDATA,
        bili_jct=BILIBILI_BILI_JCT
    )
    logger.info("[B站配置] ✅ 已加载 B 站登录凭证")
else:
    logger.warning("[B站配置] ⚠️ 未配置 BILIBILI_SESSDATA 或 BILIBILI_BILI_JCT，可能触发风控")

# 初始化 B 站用户对象
bili_user = user.User(uid=YYSLS_BILI_UID, credential=credential)

# AI Prompt
SYSTEM_PROMPT = (
    "你是一个游戏资讯提取助手。请从以下B站动态内容中，严格提取《燕云十六声》的兑换码（礼包口令）。\n"
    "注意：兑换码可能是纯大写字母数字组合，也可能是中文汉字，或者两者都有。\n"
    "仅返回JSON对象格式，不要包含任何Markdown标记或解释。\n"
    '格式要求：{"codes": [{"code": "兑换码内容", "note": "奖励内容或备注(若无则填\'\\\'\')}]}'
    "\n如果没有发现任何有效兑换码，返回 {\"codes\": []}。"
)


# ============ 历史记录管理 ============
def load_history() -> List[str]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning(f"[AI提取] 历史文件 {HISTORY_FILE} 解析失败，使用空列表")
            return []
    return []


def save_history(history: List[str]):
    HISTORY_FILE.write_text(
        json.dumps(history[-50:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ============ B站动态抓取（带重试机制） ============
async def fetch_bili_dynamics() -> List[Dict]:
    """获取B站最新动态（使用官方库 + 3次重试）"""
    max_retries = 3
    retry_delay = 2  # 秒

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"[B站抓取] 尝试第 {attempt} 次获取动态...")
            
            # 🆕 使用官方库获取动态（自动处理 WBI 签名和风控）
            dynamics_data = await bili_user.get_dynamics()
            
            items = dynamics_data.get("items", [])
            articles = []
            
            for item in items[:10]:  # 只检查最新 10 条
                modules = item.get("modules", {})
                desc = modules.get("module_dynamic", {}).get("desc", {})

                if not desc or not desc.get("text"):
                    continue

                articles.append({
                    "dynamic_id": item.get("id_str"),
                    "content": desc["text"],
                    "pub_time": modules.get("module_author", {}).get("pub_ts", 0)
                })
            
            logger.success(f"[B站抓取] ✅ 成功获取 {len(articles)} 条动态")
            return articles

        except Exception as e:
            logger.error(f"[B站抓取] ❌ 第 {attempt} 次尝试失败: {e}")
            if attempt < max_retries:
                logger.info(f"[B站抓取] ⏳ {retry_delay} 秒后重试...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # 指数退避
            else:
                logger.error("[B站抓取] 🚨 达到最大重试次数，放弃抓取")
                return []


# ============ 文本清洗与 AI 提取 ============
def clean_bili_text(text: str) -> str:
    """清洗B站动态文本，移除表情和@"""
    text = re.sub(r'\[[\u4e00-\u9fa5a-zA-Z0-9]+\]', '', text)
    text = re.sub(r'@[\w\s]+', '', text)
    return text.strip()


async def extract_codes_with_ai(text: str) -> List[Dict]:
    """调用 LLM 提取兑换码"""
    if not AI_API_KEY:
        logger.error("[AI提取] 未配置 AI_API_KEY，请在 .env 中配置！")
        return []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            headers = {
                "Authorization": f"Bearer {AI_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": AI_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"}
            }

            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload
            )
            resp.raise_for_status()

            result = resp.json()
            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return parsed.get("codes", [])
    except Exception as e:
        logger.error(f"[AI提取] LLM 请求或解析失败: {e}")
        return []


# ============ 核心处理逻辑 ============
async def process_new_dynamics() -> int:  # 🆕 1. 增加返回类型提示
    """检查新动态并处理，返回新发现的兑换码数量"""
    history = load_history()
    dynamics = await fetch_bili_dynamics()

    if not dynamics:
        return 0  # 🆕 2. 没有动态时返回 0

    new_codes_found = []

    for dyn in dynamics:
        dyn_id = dyn["dynamic_id"]
        if dyn_id in history:
            continue  # 已处理过

        content = dyn["content"]

        # 1. 关键词预过滤 (节省 AI 成本)
        if "礼包口令" not in content and "兑换码" not in content:
            history.append(dyn_id)
            continue

        # 2. 文本清洗
        clean_text = clean_bili_text(content)
        logger.info(f"[AI提取] 发现疑似兑换码动态 (ID: {dyn_id})，正在调用 AI 分析...")

        # 3. AI 提取
        extracted = await extract_codes_with_ai(clean_text)

        # 4. 入库与通知
        for item in extracted:
            code = item.get("code", "").strip()
            note = item.get("note", "").strip()

            # 基础校验：过滤太短或包含明显无效字符的码
            if not code or len(code) < 2:
                continue

            # 统一转为大写（如果是纯英文/数字），中文保持原样
            if code.isascii():
                code = code.upper()

            # 补充来源备注
            final_note = f"{note} (B站动态)" if note else "来源: B站官方动态"

            result = add_cdkey(code, source="AI自动提取", note=final_note)
            if result in ["added", "reactivated"]:
                logger.success(f"[AI提取] 新码入库: {code}")
                new_codes_found.append(code)

        # 记录已处理
        history.append(dyn_id)

    # 保存历史
    if dynamics:
        save_history(history)

    # 5. 推送通知到群
    if new_codes_found:
        await notify_groups(new_codes_found)

    return len(new_codes_found)  # 🆕 3. 返回新发现的兑换码数量


async def notify_groups(codes: List[str]):
    """向已订阅的群聊推送新兑换码"""
    subscribed_groups = load_subscribed_groups()

    if not subscribed_groups:
        return

    try:
        bot = get_bot()
        msg = "🎉 【燕云十六声·新兑换码发现】\n\n"
        for c in codes:
            msg += f"👉 {c}\n"
        msg += "\n快上游戏兑换吧！(使用 /cdkey 查看全部)"

        for group_id in subscribed_groups:
            try:
                await bot.send_group_msg(group_id=int(group_id), message=msg)
            except Exception as e:
                logger.error(f"[通知] 发送群 {group_id} 失败: {e}")
    except Exception as e:
        logger.error(f"[通知] 获取 Bot 实例失败: {e}")


# ============ 定时任务 ============
@scheduler.scheduled_job(
    "interval",
    minutes=1440,  # 每 1440 分钟 = 24 小时检查一次
    id="yysls_bili_ai_extractor",
    misfire_grace_time=60,
)
async def auto_check_bili_dynamics():
    """定时检查 B站动态"""
    logger.debug("[定时任务] 开始检查 B站燕云十六声官方动态...")
    await process_new_dynamics()