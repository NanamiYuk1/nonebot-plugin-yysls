from typing import List, Set
from nonebot import require, get_bot, logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

# ============ 🌟 资源兑换清单数据 ============

WEEKLY_EXCHANGE_TEXT = """【每周必换/必做清单】

1️⃣ 萌新/回归优先：不肝商店-赛季追赶资源
2️⃣ 袅袅之音·绑 (固定3个+概率)：
   • 商城-精选-江湖百珍 (2个)
   • 不肝商店-外观兑换 (1个)
   • 群力共伐 / 赤金小铺 (概率掉落)
3️⃣ 不肝商店-么玉兑换：
   • 心法/心得/奇术/生活物资支援箱/营生手记/转律/定音/金妙音石
4️⃣ 杂货铺(叠音材料)：
   • 粗毛皮 / 粗矿石 (清河/开封杂货铺)
5️⃣ 战令商店 & 传承兑换：
   • 各类每周刷新资源 (传承材料在太平武墓-流派试炼获取)"""

MONTHLY_EXCHANGE_TEXT = """【每月必换清单】

1️⃣ 袅袅之音·绑：
   • 商城-和鸣-地华商店 (2个)
2️⃣ 折音券：
   • 商城-和鸣-地华商店 (1个)"""


# ============ 命令处理函数 ============

async def handle_weekly_exchange(bot: Bot, event: MessageEvent):
    """响应 /每周必换 命令"""
    await bot.send(event, WEEKLY_EXCHANGE_TEXT)

async def handle_monthly_exchange(bot: Bot, event: MessageEvent):
    """响应 /每月必换 命令"""
    await bot.send(event, MONTHLY_EXCHANGE_TEXT)


# ============ 定时推送函数 ============

async def send_shop_reminder(
    subscribe_groups: Set[int], 
    shop_items: List[str], 
    remind_type: str = "refresh"
):
    """每月商城限时道具提醒 + 每月必换清单"""
    if not subscribe_groups:
        return

    # 根据类型生成商城文案
    if remind_type == "expire":
        title = "【燕云十六声·月末商城临期提醒】"
        content = "本月商城限时道具即将下架！\n还没购买的少侠请抓紧时间，错过等一年！"
        items_header = "以下道具即将过期，请及时兑换："
    else:
        title = "[商城提醒] 【燕云十六声·月初商城上新提醒】"
        content = "本月商城限时道具已刷新！\n快来看看有没有你心仪的绝版外观和道具吧~"
        items_header = "本月可购买道具列表："

    # 组装道具列表
    items_text = "\n".join([f"  🔸 {item}" for item in shop_items]) if shop_items else "  (暂无配置特殊道具)"
    
    # 🌟 拼接商城文案 + 每月必换清单
    msg = (
        f"{title}\n━━━━━━━━━━━━━━━\n"
        f"{content}\n\n{items_header}\n{items_text}\n\n"
        f"{MONTHLY_EXCHANGE_TEXT}\n"
        f"━━━━━━━━━━━━━━━\n"
    )

    bot = get_bot()
    for group_id in subscribe_groups:
        try:
            await bot.send_group_msg(group_id=group_id, message=msg)
            logger.info(f"[燕云助手] 已向群 {group_id} 发送商城 {remind_type} 提醒")
        except Exception as e:
            logger.error(f"[燕云助手] 向群 {group_id} 发送商城提醒失败: {e}")


async def send_cdkey_digest(subscribe_groups: Set[int]):
    """每周推送：兑换码汇总 + 每周必换清单"""
    if not subscribe_groups:
        return
        
    from .cdkey import get_active_cdkeys
    active = get_active_cdkeys()

    # 组装兑换码部分
    if active:
        lines = ["【本周可用兑换码】"]
        for item in active:
            line = f"  📌 {item['code']}"
            if item.get("note"):
                line += f" ({item['note']})"
            lines.append(line)
        lines.append("[即将过期] 请尽快兑换！使用 /cdkey 随时查看")
        cdkey_text = "\n".join(lines)
    else:
        cdkey_text = "本周暂无可用兑换码"

    # 🌟 拼接兑换码 + 每周必换清单
    msg = (
        f"[每周必换] 【燕云十六声·周一早报】\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{cdkey_text}\n\n"
        f"{WEEKLY_EXCHANGE_TEXT}\n"
        f"━━━━━━━━━━━━━━━\n"
    )

    bot = get_bot()
    for group_id in subscribe_groups:
        try:
            await bot.send_group_msg(group_id=group_id, message=msg)
            logger.info(f"[燕云助手] 已向群 {group_id} 发送周一早报(兑换码+每周必换)")
        except Exception as e:
            logger.error(f"[燕云助手] 发送周一早报失败: {e}")