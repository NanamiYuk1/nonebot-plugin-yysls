import re
import json
import asyncio
from pathlib import Path
from typing import List, Dict

import httpx
from nonebot import get_driver, get_bot, logger, require
from nonebot.exception import ActionFailed

from .cdkey import add_cdkey
from .data_manager import load_subscribed_groups

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

try:
    from bilibili_api import user, Credential
    from bilibili_api.exceptions import ResponseCodeException, NetworkException
except ImportError:
    logger.error("[AI 提取] 未安装 bilibili-api-python，请执行：pip install bilibili-api-python")
    raise

driver = get_driver()
config = driver.config

AI_API_KEY = getattr(config, "ai_api_key", "")
AI_BASE_URL = getattr(config, "ai_base_url", "https://api.openai.com/v1")
AI_MODEL = getattr(config, "ai_model", "gpt-4o-mini")

BILIBILI_SESSDATA = getattr(config, "bilibili_sessdata", "")
BILIBILI_BILI_JCT = getattr(config, "bilibili_bili_jct", "")
BILIBILI_BUVID3 = getattr(config, "bilibili_buvid3", "")

YYSLS_BILI_UID = 1567141152
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
HISTORY_FILE = DATA_DIR / "bili_dynamic_history.json"

credential = None
if BILIBILI_SESSDATA and BILIBILI_BILI_JCT:
    cred_kwargs = {
        "sessdata": BILIBILI_SESSDATA,
        "bili_jct": BILIBILI_BILI_JCT
    }
    if BILIBILI_BUVID3:
        cred_kwargs["buvid3"] = BILIBILI_BUVID3
        
    credential = Credential(**cred_kwargs)
    logger.info("[B 站配置] ✅ 已加载 B 站登录凭证，风控概率大幅降低")
else:
    logger.warning("[B 站配置] ⚠️ 未配置 BILIBILI_SESSDATA/BILI_JCT，裸奔请求极易触发 412 风控！")

bili_user = user.User(uid=YYSLS_BILI_UID, credential=credential)

SYSTEM_PROMPT = (
    "你是一个游戏资讯提取助手。请从以下 B 站动态内容中，严格提取《燕云十六声》的兑换码（礼包口令）。\n"
    "注意：兑换码可能是纯大写字母数字组合，也可能是中文汉字，或者两者都有。\n"
    "仅返回 JSON 对象格式，不要包含任何 Markdown 标记（如```json）或解释。\n"
    '格式要求：{"codes": [{"code": "兑换码内容", "note": "奖励内容或备注 (若无则填空字符串)"}]}\n'
    "如果没有发现任何有效兑换码，返回 {\"codes\": []}。"
)

async def load_history() -> List[str]:
    if HISTORY_FILE.exists():
        try:
            text = await asyncio.to_thread(HISTORY_FILE.read_text, encoding="utf-8")
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"[AI 提取] 历史文件 {HISTORY_FILE} 解析失败，使用空列表")
            return []
    return []

async def save_history(history: List[str]):
    data = json.dumps(history[-100:], ensure_ascii=False, indent=2)
    await asyncio.to_thread(HISTORY_FILE.write_text, data, encoding="utf-8")

async def fetch_bili_dynamics() -> List[Dict]:
    try:
        logger.debug("[B 站抓取] ⏳ 正在请求 B 站 API 获取动态...")
        
        dynamics_data = None
        if hasattr(bili_user, "get_dynamics_new"):
            dynamics_data = await bili_user.get_dynamics_new()
        else:
            dynamics_data = await bili_user.get_dynamics()
        
        items = []
        if isinstance(dynamics_data, dict):
            items = dynamics_data.get("items", [])
        elif isinstance(dynamics_data, list):
            items = dynamics_data
            
        articles = []
        for item in items[:10]:
            modules = item.get("modules", {})
            desc_module = modules.get("module_dynamic", {}).get("desc")

            text = ""
            if desc_module and desc_module.get("text"):
                text = desc_module["text"]
            else:
                major = modules.get("module_dynamic", {}).get("major", {})
                if major and major.get("opus", {}).get("summary", {}).get("text"):
                    text = major["opus"]["summary"]["text"]

            if not text:
                continue

            articles.append({
                "dynamic_id": str(item.get("id_str", item.get("id", ""))),
                "content": text,
                "pub_time": modules.get("module_author", {}).get("pub_ts", 0)
            })
        
        logger.success(f"[B 站抓取] ✅ 成功获取 {len(articles)} 条动态")
        return articles

    except ResponseCodeException as e:
        logger.error(f"[B 站抓取] ❌ B 站 API 业务拦截：错误码 {e.code} - {e.msg}")
        if e.code in [-352, -412, 412]:
            logger.warning("[B 站抓取] 🛑 触发 B 站风控！请在 .env 中配置 BILIBILI_SESSDATA 和 BILIBILI_BILI_JCT，或更换服务器 IP")
    except NetworkException as e:
        err_str = str(e)
        if "412" in err_str:
            logger.error("[B 站抓取] 🛑 触发 412 安全风控策略！服务器 IP 已被 B 站临时拉黑，本次抓取直接放弃。")
            logger.warning("[B 站抓取] 💡 解决方案：1. 在 .env 配置 B 站账号 Cookie；2. 为 Bot 配置 HTTP 代理；3. 等待 1-2 小时后 IP 自动解封。")
        else:
            logger.error(f"[B 站抓取] ❌ 网络异常：{e}")
    except Exception as e:
        logger.error(f"[B 站抓取] ❌ 未知异常：{e}")
        
    return []

def clean_bili_text(text: str) -> str:
    # 🔥 修复：修正正则表达式，正确匹配并移除 B 站话题标签（如 #燕云十六声#）
    text = re.sub(r'#[\u4e00-\u9fa5a-zA-Z0-9]+#', '', text)
    text = re.sub(r'@[\w\s]+', '', text)
    return text.strip()

def clean_json_response(text: str) -> str:
    text = text.strip()
    # 🔥 修复：使用单引号包裹反引号，彻底解决转义导致的 SyntaxError
    if text.startswith('```json'):
        text = text[7:]
    elif text.startswith('```'):
        text = text[3:]
    
    if text.endswith('```'):
        text = text[:-3]
    return text.strip()

async def extract_codes_with_ai(text: str) -> List[Dict]:
    if not AI_API_KEY:
        logger.error("[AI 提取] 未配置 AI_API_KEY，请在 .env 中配置！")
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
                "temperature": 0.1
            }
            if "gpt" in AI_MODEL.lower() or "moonshot" in AI_MODEL.lower():
                payload["response_format"] = {"type": "json_object"}

            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload
            )
            resp.raise_for_status()

            result = resp.json()
            content = result["choices"][0]["message"]["content"]
            
            clean_content = clean_json_response(content)
            parsed = json.loads(clean_content)
            return parsed.get("codes", [])
    except json.JSONDecodeError as e:
        logger.error(f"[AI 提取] LLM 返回的不是有效 JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"[AI 提取] LLM 请求或解析失败：{e}")
        return []

async def process_new_dynamics() -> int:
    history = await load_history()
    dynamics = await fetch_bili_dynamics()

    if not dynamics:
        return 0

    new_codes_found = []

    for dyn in dynamics:
        dyn_id = dyn["dynamic_id"]
        if dyn_id in history:
            continue

        content = dyn["content"]

        if "礼包口令" not in content and "兑换码" not in content and "口令" not in content:
            history.append(dyn_id)
            continue

        clean_text = clean_bili_text(content)
        logger.info(f"[AI 提取] 发现疑似兑换码动态 (ID: {dyn_id})，正在调用 AI 分析...")

        extracted = await extract_codes_with_ai(clean_text)

        for item in extracted:
            code = item.get("code", "").strip()
            note = item.get("note", "").strip()

            if not code or len(code) < 2:
                continue

            if code.isascii():
                code = code.upper()

            final_note = f"{note} (B 站动态)" if note else "来源：B 站官方动态"

            result = await add_cdkey(code, source="AI 自动提取", note=final_note)
            if result in ["added", "reactivated"]:
                logger.success(f"[AI 提取] 新码入库：{code}")
                new_codes_found.append(code)

        history.append(dyn_id)

    if dynamics:
        await save_history(history)

    if new_codes_found:
        await notify_groups(new_codes_found)

    return len(new_codes_found)

async def notify_groups(codes: List[str]):
    subscribed_groups = await load_subscribed_groups()

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
            except ActionFailed as e:
                logger.error(f"[通知] 发送群 {group_id} 失败 (可能被风控或退群): {e}")
            except Exception as e:
                logger.error(f"[通知] 发送群 {group_id} 失败：{e}")
    except Exception as e:
        logger.error(f"[通知] 获取 Bot 实例失败：{e}")

@scheduler.scheduled_job(
    "interval",
    minutes=1440,
    id="yysls_bili_ai_extractor",
    misfire_grace_time=60,
)
async def auto_check_bili_dynamics():
    logger.debug("[定时任务] 开始检查 B 站燕云十六声官方动态...")
    await process_new_dynamics()