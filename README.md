<div align="center">
  <h1>🎮 NoneBot Plugin - YYSLs</h1>
  <p><strong>燕云十六声游戏助手</strong>：公告推送 · 兑换码管理 · 商城与资源提醒</p>
  <p><sub>使用 AI 辅助编写的自用燕云十六声 QQ Bot 插件</sub></p>

  <img src="https://img.shields.io/pypi/v/nonebot-plugin-yysls" alt="PyPI Version">
  <img src="https://img.shields.io/badge/python-3.9+-blue" alt="Python">
  <img src="https://img.shields.io/badge/nonebot-2.2.0+-green" alt="NoneBot2">
  <img src="https://img.shields.io/badge/license-MIT-orange" alt="License">
</div>

## ✨ 功能特性

- 📢 **官网公告自动推送**：版本更新、维护公告实时同步
- 🔑 **兑换码智能管理**：支持全员自动识别录入 + 防刷屏恶意防护
- 🛒 **商城限时提醒**：每月商城必换道具到期 / 刷新双提醒
- 📋 **资源清单推送**：每周 / 每月必换资源定时汇总推送

---

## 📖 可用指令

> 💡 发送 `/yysls_help` 或 `燕云帮助` 可随时在群内查看完整指令菜单。

### 👥 所有人可用

| 指令 | 别名 | 说明 |
| :--- | :--- | :--- |
| `/cdkey` | `兑换码` | 查看当前所有可用兑换码列表 |
| `/weekly` | `每周必换` / `每周清单` | 查看每周刷新必换资源清单 |
| `/monthly` | `每月必换` / `每月清单` | 查看每月商城限时必换道具清单 |
| `/yysls_help` | `燕云帮助` / `助手帮助` / `yysls_menu` | 查看本帮助菜单 |

#### 🔍 自动识别兑换码（全员可用）

群内任意成员发送以下格式消息即可自动录入兑换码：

```text
燕云十六声兑换码：<兑换码>

```

> **示例**：
> - `燕云十六声兑换码：陈叔邀你下江南`
> - `燕云十六声兑换码：yysls2026`
>
> - 支持中英文混合口令，最长 10 个汉字
> - ⚠️ **必须包含完整前缀** `燕云十六声兑换码：`，否则不会触发识别
> - 同一用户 60 秒内最多触发 3 次，防止恶意刷屏录入

### 🔐 仅管理员可用

| 指令 | 别名 | 说明 |
| :--- | :--- | :--- |
| `/add_cdkey <码> [备注]` | `添加兑换码` / `批量添加兑换码` | 添加单条或批量录入兑换码（换行分隔） |
| `/edit_note <码> <备注>` | `set_note` / `修改备注` | 修改指定兑换码的备注信息 |
| `/expire_cdkey <码>` | — | 手动标记指定兑换码为过期 |
| `/re_cdkey <码>` | `重新激活兑换码` / `恢复兑换码` | 重新激活已过期的兑换码 |
| `/yysls_sub` | `订阅燕云` | 开启本群公告与提醒自动推送 |
| `/yysls_unsub` | `取消订阅燕云` | 关闭本群公告与提醒自动推送 |
| `/yysls_status` | `燕云状态` | 查看插件运行状态、订阅情况与兑换码数量 |

> **提示**：表格中「别名」列的内容可直接替代主指令使用，无需加 `/` 前缀。管理员权限包括群主、群管理员及 Bot 超级用户。

---

## 📦 安装

### 使用 nb-cli（推荐）

```bash
nb plugin install nonebot-plugin-yysls

```

### 使用 pip

```bash
pip install nonebot-plugin-yysls

```

安装后在 `bot.py` 或 `pyproject.toml` 中加载插件：

```python
nonebot.load_plugin("nonebot_plugin_yysls")

```

---

## ⚙️ 配置项

在 `.env` / `.env.prod` 中添加以下配置：

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `YYSLS_CHECK_INTERVAL` | int | `30` | 公告检查间隔（分钟） |
| `YYSLS_NEWS_URL` | str | *(内置)* | 官网公告 API 地址 |
| `YYSLS_SHOP_REMIND_HOUR` | int | `10` | 商城提醒触发时间（小时） |

> 完整配置项及默认值请参考插件源码中的 `config.py`。

---

## 📝 更新日志

见 [CHANGELOG.md](./CHANGELOG.md)

## 📄 许可证

本项目采用 [MIT License](./LICENSE) 开源
