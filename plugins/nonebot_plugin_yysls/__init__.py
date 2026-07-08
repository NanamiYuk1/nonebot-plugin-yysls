"""
NoneBot2 插件 - 燕云十六声 助手
"""

from nonebot import get_plugin_config, on_command, on_message, require, logger
from nonebot.plugin import PluginMetadata
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, Message, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from .config import YyslsConfig
from .data_manager import load_subscribed_groups, save_subscribed_groups
from .announcements import check_and_push_announcements, get_http_content, parse_announcements
from .ai_extractor import process_new_dynamics
from .cdkey import (
    handle_cdkey_list,
    handle_add_cdkey,
    handle_expire_cdkey,
    handle_reactivate_cdkey,
    handle_edit_note,
)
from .shop_reminder import (
    send_shop_reminder,
    send_cdkey_digest,
    handle_weekly_exchange,
    handle_monthly_exchange,
)
from .auto_extract import try_auto_add_cdkey

plugin_config = get_plugin_config(YyslsConfig)
_subscribed_groups: set = set()

from nonebot import get_driver
driver = get_driver()

@driver.on_startup
async def _load_groups_on_startup():
    global _subscribed_groups
    _subscribed_groups = await load_subscribed_groups()
    logger.info(f"[燕云助手] 已从本地恢复 {len(_subscribed_groups)} 个订阅群")

__plugin_meta__ = PluginMetadata(
    name="燕云十六声助手",
    description="燕云十六声游戏助手：公告推送、兑换码管理、商城与资源提醒、B 站 AI 抓码",
    usage="发送 /yysls_help 或 燕云帮助 查看完整指令菜单",
    config=YyslsConfig,
)

# ============================================================
#  定时任务注册
# ============================================================

@scheduler.scheduled_job(
    "interval",
    minutes=plugin_config.yysls_check_interval,
    id="yysls_check_news",
    misfire_grace_time=60,
)
async def _check_news():
    await check_and_push_announcements(
        subscribe_groups=_subscribed_groups,
        news_url=plugin_config.yysls_news_url,
        base_url=plugin_config.yysls_news_base_url,
    )

@scheduler.scheduled_job(
    "cron", day=1,
    hour=plugin_config.yysls_shop_remind_hour, minute=0,
    id="yysls_shop_reminder_refresh",
    misfire_grace_time=3600,
)
async def _monthly_shop_reminder_refresh():
    await send_shop_reminder(
        subscribe_groups=_subscribed_groups,
        shop_items=plugin_config.yysls_shop_items,
        remind_type="refresh",
    )

@scheduler.scheduled_job(
    "cron", day="last",
    hour=plugin_config.yysls_shop_remind_hour, minute=0,
    id="yysls_shop_reminder_expire",
    misfire_grace_time=3600,
)
async def _monthly_shop_reminder_expire():
    await send_shop_reminder(
        subscribe_groups=_subscribed_groups,
        shop_items=plugin_config.yysls_shop_items,
        remind_type="expire",
    )

@scheduler.scheduled_job(
    "cron", day_of_week="mon",
    hour=10, minute=0,
    id="yysls_weekly_digest",
    misfire_grace_time=3600,
)
async def _weekly_digest():
    await send_cdkey_digest(
        subscribe_groups=_subscribed_groups,
    )

# ============================================================
#  命令注册
# ============================================================

HELP_TEXT = """[燕云十六声助手 - 指令菜单]
========================
【日常查询】(所有人可用)
/cdkey (兑换码) - 查看当前可用兑换码
/每周必换 - 查看每周刷新必换清单
/每月必换 - 查看每月商城必换清单
/yysls_help (燕云帮助) - 查看本帮助菜单

【兑换码管理】(仅管理员)
/add_cdkey <码> [备注] - 添加/批量录入兑换码
/edit_note <码> <备注> - 修改兑换码备注
/expire_cdkey <码> - 标记兑换码为过期
/re_cdkey <码> - 重新激活已过期的兑换码
/check_bili - 手动测试兑换码抓取 (调试用)
/check_news - 手动测试燕云官网公告抓取 (调试用)

【订阅与系统】(仅管理员)
/yysls_sub (订阅燕云) - 开启本群自动推送
/yysls_unsub (取消订阅燕云) - 关闭本群自动推送
/yysls_status (燕云状态) - 查看插件运行状态
========================
提示：括号内为指令别名，可直接替代主指令使用。"""

help_cmd = on_command("yysls_help", aliases={"燕云帮助", "助手帮助", "yysls_menu"}, priority=10, block=True)

@help_cmd.handle()
async def _(bot: Bot, event: MessageEvent):
    await bot.send(event, HELP_TEXT)

cdkey_cmd = on_command("cdkey", aliases={"兑换码"}, priority=10, block=True)

@cdkey_cmd.handle()
async def _(bot: Bot, event: MessageEvent):
    await handle_cdkey_list(bot, event)

weekly_cmd = on_command("weekly", aliases={"每周必换", "每周清单"}, priority=10, block=True)
monthly_cmd = on_command("monthly", aliases={"每月必换", "每月清单"}, priority=10, block=True)

@weekly_cmd.handle()
async def _(bot: Bot, event: MessageEvent):
    await handle_weekly_exchange(bot, event)

@monthly_cmd.handle()
async def _(bot: Bot, event: MessageEvent):
    await handle_monthly_exchange(bot, event)

add_cdkey_cmd = on_command("add_cdkey", aliases={"添加兑换码", "批量添加兑换码"}, priority=5, block=True)

@add_cdkey_cmd.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    if not text:
        await bot.send(event,
            "用法说明:\n"
            "【单条录入】\n/add_cdkey <兑换码> [备注]\n\n"
            "【批量录入】(使用换行分隔)\n/add_cdkey\n<码 1> <备注 1>\n<码 2> <备注 2>\n..."
        )
        return

    lines = [line.strip() for line in text.split('\n') if line.strip()]

    if len(lines) == 1:
        parts = lines[0].split(maxsplit=1)
        code = parts[0].strip().upper()
        note = parts[1].strip() if len(parts) > 1 else ""

        from .cdkey import add_cdkey
        result = await add_cdkey(code, source="管理员手动录入", note=note)

        if result == "added":
            await bot.send(event, f"新兑换码 {code} 已添加！")
        elif result == "reactivated":
            await bot.send(event, f"兑换码 {code} 原本已过期，现已为您重新激活！")
        elif result == "updated":
            await bot.send(event, f"兑换码 {code} 的备注已更新！")
        else:
            await bot.send(event, f"兑换码 {code} 已存在且正在生效中，无需重复添加！")
        return

    from .cdkey import add_cdkey
    success_added = success_reactivated = success_updated = skipped_exists = 0
    error_lines = []

    for line in lines:
        parts = line.split(maxsplit=1)
        code = parts[0].strip().upper()
        note = parts[1].strip() if len(parts) > 1 else ""
        if len(code) < 4:
            error_lines.append(f"格式错误：{line}")
            continue
        result = await add_cdkey(code, source="管理员批量录入", note=note)
        if result == "added":
            success_added += 1
        elif result == "reactivated":
            success_reactivated += 1
        elif result == "updated":
            success_updated += 1
        else:
            skipped_exists += 1

    report = "[批量录入完成]\n"
    report += f"新增成功：{success_added} 个\n"
    if success_reactivated > 0:
        report += f"重新激活：{success_reactivated} 个\n"
    if success_updated > 0:
        report += f"更新备注：{success_updated} 个\n"
    if skipped_exists > 0:
        report += f"已存在跳过：{skipped_exists} 个\n"
    if error_lines:
        report += "\n失败列表:\n" + "\n".join(error_lines)
    await bot.send(event, report)

edit_note = on_command("edit_note", aliases={"set_note", "修改备注"}, priority=5, block=True)

@edit_note.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    await handle_edit_note(bot, event, args)

re_cdkey_cmd = on_command("re_cdkey", aliases={"重新激活兑换码", "恢复兑换码"}, priority=5, block=True)

@re_cdkey_cmd.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    await handle_reactivate_cdkey(bot, event, args)

expire_cdkey_cmd = on_command("expire_cdkey", priority=5, block=True)

@expire_cdkey_cmd.handle()
async def _(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    await handle_expire_cdkey(bot, event, args)

check_bili_cmd = on_command(
    "check_bili",
    priority=5,
    block=True,
    permission=SUPERUSER | GROUP_ADMIN | GROUP_OWNER,
)

@check_bili_cmd.handle()
async def _(bot: Bot, event: MessageEvent):
    await bot.send(event, "🔍 正在检查 B 站官方动态，请稍候...")
    try:
        new_codes_count = await process_new_dynamics()
        
        if new_codes_count and new_codes_count > 0:
            await bot.send(event, f"✅ B 站动态检查完成！\n🎉 发现 {new_codes_count} 个新兑换码，已自动入库并推送至订阅群。")
        else:
            await bot.send(event, "✅ B 站动态检查完成！\n当前暂无新的兑换码。")
    except Exception as e:
        logger.error(f"[手动检查] 执行失败：{e}")
        await bot.send(event, f"❌ 检查失败，请查看后台日志：{e}")

# 🆕 新增：手动测试官网公告抓取
check_news_cmd = on_command(
    "check_news",
    priority=5,
    block=True,
    permission=SUPERUSER | GROUP_ADMIN | GROUP_OWNER,
)

@check_news_cmd.handle()
async def _(bot: Bot, event: MessageEvent):
    await bot.send(event, "🔍 正在抓取官网公告，请稍候...")
    try:
        html = await get_http_content(plugin_config.yysls_news_url)
        if not html:
            await bot.send(event, "❌ 抓取官网 HTML 失败，请检查网络或 URL 配置。")
            return
            
        announcements = parse_announcements(html, plugin_config.yysls_news_base_url)
        if not announcements:
            await bot.send(event, "⚠️ 未解析到任何有效公告链接。可能是官网结构变更，请查看后台日志。")
            return
            
        msg = f"✅ 成功抓取 {len(announcements)} 条官网公告:\n\n"
        for i, ann in enumerate(announcements[:5], 1):  # 只显示前 5 条
            msg += f"{i}. {ann['title']}\n   {ann['link']}\n\n"
        if len(announcements) > 5:
            msg += f"...还有 {len(announcements) - 5} 条未显示"
            
        await bot.send(event, msg)
    except Exception as e:
        logger.error(f"[手动检查新闻] 执行失败：{e}")
        await bot.send(event, f"❌ 检查失败：{e}")

sub_cmd = on_command("yysls_sub", aliases={"订阅燕云"}, priority=5, block=True)
unsub_cmd = on_command("yysls_unsub", aliases={"取消订阅燕云"}, priority=5, block=True)
status_cmd = on_command("yysls_status", aliases={"燕云状态"}, priority=10, block=True)

async def _check_admin_permission(bot: Bot, event: MessageEvent) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    sender_role = getattr(event.sender, 'role', '')
    is_superuser = await SUPERUSER(bot, event)
    return sender_role in ("owner", "admin") or is_superuser

@sub_cmd.handle()
async def _(bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await bot.send(event, "请在群聊中使用此命令")
        return

    if not await _check_admin_permission(bot, event):
        await bot.send(event, "仅群主或管理员可操作订阅指令")
        return

    group_id = event.group_id
    if group_id in _subscribed_groups:
        await bot.send(event, f"本群 ({group_id}) 已在订阅列表中，无需重复订阅")
        return

    _subscribed_groups.add(group_id)
    await save_subscribed_groups(_subscribed_groups)  
    await bot.send(event, f"本群 ({group_id}) 已订阅燕云十六声公告推送！")

@unsub_cmd.handle()
async def _(bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await bot.send(event, "请在群聊中使用此命令")
        return

    if not await _check_admin_permission(bot, event):
        await bot.send(event, "仅群主或管理员可操作订阅指令")
        return

    group_id = event.group_id
    if group_id not in _subscribed_groups:
        await bot.send(event, f"本群 ({group_id}) 未订阅，无需取消")
        return

    _subscribed_groups.discard(group_id)
    await save_subscribed_groups(_subscribed_groups)  
    await bot.send(event, f"本群 ({group_id}) 已取消订阅燕云十六声公告推送")

@status_cmd.handle()
async def _(bot: Bot, event: MessageEvent):
    is_subscribed = (
        isinstance(event, GroupMessageEvent)
        and event.group_id in _subscribed_groups
    )

    from .cdkey import get_active_cdkeys
    active_keys = await get_active_cdkeys()
    active_count = len(active_keys)

    msg = (
        f"[燕云十六声助手 - 运行状态]\n"
        f"========================\n"
        f"公告检查间隔：{plugin_config.yysls_check_interval} 分钟\n"
        f"订阅群数量：{len(_subscribed_groups)} 个\n"
        f"可用兑换码：{active_count} 个\n"
        f"商城提醒：每月 1 日 & 月末最后一天 {plugin_config.yysls_shop_remind_hour}:00\n"
        f"B 站 AI 抓码：每 24 小时自动巡查\n"
        f"========================\n"
    )

    if isinstance(event, GroupMessageEvent):
        sub_status = "[已订阅]" if is_subscribed else "[未订阅]"
        msg += f"本群订阅状态：{sub_status}"
    else:
        groups_str = (
            ", ".join(map(str, _subscribed_groups))
            if _subscribed_groups else "无"
        )
        msg += f"订阅群号：{groups_str}"

    await bot.send(event, msg)

AUTO_EXTRACT_TRIGGER = "燕云十六声兑换码："

auto_cdkey_listener = on_message(priority=99, block=False)

@auto_cdkey_listener.handle()
async def _(bot: Bot, event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        return

    if event.self_id == event.user_id:
        return

    text = event.get_plaintext().strip()
    normalized_text = text.replace(":", "：")
    if AUTO_EXTRACT_TRIGGER not in normalized_text:
        return

    code, feedback = await try_auto_add_cdkey(
        text=text,
        source=f"群{event.group_id}用户{event.user_id}自动提取",
        user_id=event.user_id,
    )

    if feedback:
        await bot.send(event, f"[燕云助手·自动识别]\n{feedback}: {code}")