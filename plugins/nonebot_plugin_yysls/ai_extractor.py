import re
import json
import asyncio
from pathlib import Path
from typing import List, Dict

import httpx
from nonebot import get_driver, get_bot, logger, require
from nonebot.exception import ActionFailed

# 引入 cdkey 模块的添加方法
from .cdkey import add_cdkey
from .data_manager import load_subscribed_groups

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

# 🆕 引入 B 站官方 API 库
try:
    from bilibili_api import user, Credential
    from bilibili_api.exceptions import ResponseCodeException, NetworkException
except ImportError:
    logger.error("[AI提取] 未安装 bilibili-api-python，请执行: pip install bilibili-api-python")
    raise

# ============ 配置读取 ============
driver = get_driver()
config = driver.config

# 从 .env 文件中读取配置
AI_API_KEY = getattr(config, "ai_api_key", "")
AI_BASE_URL = getattr(config, "ai_base_url", "https://api.openai.com/v1")
AI_MODEL = getattr(config, "ai_model", "gpt-4o-mini")

BILIBILI_SESSDATA = getattr(config, "bilibili_sessdata", "")
BILIBILI_BILI_JCT = getattr(config, "bilibili_bili_jct", "")
BILIBILI_BUVID3 = getattr(config, "bilibili_buvid3", "")

# ============ 常量与路径 ============
YYSLS_BILI_UID = 1567141152  # 燕云十六声 B站官号 UID
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
HISTORY_FILE = DATA_DIR / "bili_dynamic_history.json"

# 🆕 初始化 B 站 Credential（登录凭证）
credential = None
if BILIBILI_SESSDATA and BILIBILI_BILI_JCT:
    cred_kwargs = {
        "sessdata": BILIBILI_SESSDATA,
        "bili_jct": BILIBILI_BILI_JCT
    }
    if BILIBILI_BUVID3:
        cred_kwargs["buvid3"] = BILIBILI_BUVID3
        
    credential = Credential(**cred_kwargs)
    logger.info("[B站配置] ✅ 已加载 B 站登录凭证，风控概率大幅降低")
else:
    logger.warning("[B站配置] ⚠️ 未配置 BILIBILI_SESSDATA/BILI_JCT，裸奔请求极易触发 412 风控！")

# 初始化 B 站用户对象
bili_user = user.User(uid=YYSLS_BILI_UID, credential=credential)

# AI Prompt
SYSTEM_PROMPT = (
    "你是一个游戏资讯提取助手。请从以下B站动态内容中，严格提取《燕云十六声》的兑换码（礼包口令）。\n"
    "注意：兑换码可能是纯大写字母数字组合，也可能是中文汉字，或者两者都有。\n"
    "仅返回JSON对象格式，不要包含任何Markdown标记（如```json）或解释。\n"
    '格式要求：{"codes": [{"code": "兑换码内容", "note": "奖励内容或备注(若无则填空字符串)"}]}\n'
    "如果没有发现任何有效兑换码，返回 {\"codes\": []}。"
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
    # 只保留最近 100 条，防止文件无限膨胀
    HISTORY_FILE.write_text(
        json.dumps(history[-100:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ============ B站动态抓取（单次请求，遇风控直接放弃） ============
async def fetch_bili_dynamics() -> List[Dict]:
    """获取B站最新动态（单次请求，避免无效重试）"""
    try:
        logger.debug("[B站抓取] ⏳ 正在请求 B 站 API 获取动态...")
        
        # 兼容新旧版本 API
        dynamics_data = None
        if hasattr(bili_user, "get_dynamics_new"):
            dynamics_data = await bili_user.get_dynamics_new()
        else:
            dynamics_data = await bili_user.get_dynamics()
        
        # 兼容不同的返回结构
        items = []
        if isinstance(dynamics_data, dict):
            items = dynamics_data.get("items", [])
        elif isinstance(dynamics_data, list):
            items = dynamics_data
            
        articles = []
        for item in items[:10]:  # 只检查最新 10 条
            modules = item.get("modules", {})
            desc_module = modules.get("module_dynamic", {}).get("desc")

            # 兼容纯文本动态和图文动态
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
        
        logger.success(f"[B站抓取] ✅ 成功获取 {len(articles)} 条动态")
        return articles

    except ResponseCodeException as e:
        # B 站业务错误（如 -352 Wbi签名错误, -412 拦截, -403 权限）
        logger.error(f"[B站抓取] ❌ B站API业务拦截: 错误码 {e.code} - {e.msg}")
        if e.code in [-352, -412, 412]:
            logger.warning("[B站抓取] 🛑 触发 B 站风控！请在 .env 中配置 BILIBILI_SESSDATA 和 BILIBILI_BILI_JCT，或更换服务器 IP")
    except NetworkException as e:
        # 网络层面的错误（精准捕获 412 状态码）
        err_str = str(e)
        if "412" in err_str:
            logger.error("[B站抓取] 🛑 触发 412 安全风控策略！服务器 IP 已被 B 站临时拉黑，本次抓取直接放弃。")
            logger.warning("[B站抓取] 💡 解决方案：1. 在 .env 配置 B 站账号 Cookie；2. 为 Bot 配置 HTTP 代理；3. 等待 1-2 小时后 IP 自动解封。")
        else:
            logger.error(f"[B站抓取] ❌ 网络异常: {e}")
    except Exception as e:
        logger.error(f"[B站抓取] ❌ 未知异常: {e}")
        
    # 🆕 遇到错误直接返回空列表，不再进行无意义的重试
    return []


# ============ 文本清洗与 AI 提取 ============
def clean_bili_text(text: str) -> str:
    """清洗B站动态文本，移除表情和@"""
    text = re.sub(r'  $ [\u4e00-\u9fa5a-zA-Z0-9]+ $  ', '', text)
    text = re.sub(r'@[\w\s]+', '', text)
    return text.strip()


def clean_json_response(text: str) -> str:
    """清洗大模型返回的 JSON 字符串，去除 Markdown 标记"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
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
                "temperature": 0.1
            }
            # 如果模型支持 json_object 格式，则添加
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
        logger.error(f"[AI提取] LLM 返回的不是有效 JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"[AI提取] LLM 请求或解析失败: {e}")
        return []


# ============ 核心处理逻辑 ============
async def process_new_dynamics() -> int:
    """检查新动态并处理，返回新发现的兑换码数量"""
    history = load_history()
    dynamics = await fetch_bili_dynamics()

    if not dynamics:
        return 0

    new_codes_found = []

    for dyn in dynamics:
        dyn_id = dyn["dynamic_id"]
        if dyn_id in history:
            continue  # 已处理过

        content = dyn["content"]

        # 1. 关键词预过滤 (节省 AI 成本)
        if "礼包口令" not in content and "兑换码" not in content and "口令" not in content:
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

    return len(new_codes_found)


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
            except ActionFailed as e:
                logger.error(f"[通知] 发送群 {group_id} 失败 (可能被风控或退群): {e}")
            except Exception as e:
                logger.error(f"[通知] 发送群 {group_id} 失败: {e}")
    except Exception as e:
        logger.error(f"[通知] 获取 Bot 实例失败: {e}")


# ============ 定时任务 ============
@scheduler.scheduled_job(
    "interval",
    minutes=1440,  # 1440分钟(24小时)查询一次
    id="yysls_bili_ai_extractor",
    misfire_grace_time=60,
)
async def auto_check_bili_dynamics():
    """定时检查 B站动态"""
    logger.debug("[定时任务] 开始检查 B站燕云十六声官方动态...")
    await process_new_dynamics()