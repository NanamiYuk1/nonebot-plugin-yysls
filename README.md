<div align="center">
  <h1>🎮 NoneBot Plugin - yysls</h1>
  <p><strong>燕云十六声 Bot</strong>：公告推送 · 兑换码管理 · 商城与资源提醒</p>
  <p>使用 AI 辅助编写的自用燕云十六声 QQ Bot 插件</p>

  <img src="https://img.shields.io/pypi/v/nonebot-plugin-yysls" alt="PyPI Version">
  <img src="https://img.shields.io/badge/python-3.9+-blue" alt="Python">
  <img src="https://img.shields.io/badge/nonebot-2.2.0+-green" alt="NoneBot2">
  <img src="https://img.shields.io/badge/license-MIT-orange" alt="License">
</div>

---

## ✨ 功能特性

- 📢 **官网公告自动推送**：版本更新、维护公告实时同步
- 🔑 **兑换码智能管理**：支持全员自动识别录入 + 防刷屏恶意防护
- 📋 **资源清单推送**：每周 / 每月必换资源定时推送提醒

---

<div align="center">
  <img src="https://i.ibb.co/dwTj8q1R/qq.jpg" alt="qq Bot" width="300" />
  <p> 扫码添加已部署的燕云十六声 Bot
  （该bot存在其他功能，若只需要燕云功能，可自行部署服务）</p>
</div>

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

> - 每周/每月必换资源清单，在群聊使用订阅功能后，在每周/每月的第一天，会自动触发提醒。若忘记哪些资源需要兑换，可自行发送对应指令查看。

### 🔐 仅管理员可用

| 指令 | 别名 | 说明 |
| :--- | :--- | :--- |
| `/add_cdkey <码> [备注]` | `添加兑换码` / `批量添加兑换码` | 添加单条或批量录入兑换码（换行分隔） |
| `/edit_note <码> <备注>` | `set_note` / `修改备注` | 修改指定兑换码的备注信息 |
| `/expire_cdkey <码>` | — | 手动标记指定兑换码为过期 |
| `/re_cdkey <码>` | `重新激活兑换码` / `恢复兑换码` | 重新激活已过期的兑换码 |
| `/check_bili` | — | 手动触发检查B站最新动态 |
| `/yysls_sub` | `订阅燕云` | 开启本群公告与提醒自动推送 |
| `/yysls_unsub` | `取消订阅燕云` | 关闭本群公告与提醒自动推送 |
| `/yysls_status` | `燕云状态` | 查看插件运行状态、订阅情况与兑换码数量 |

> - *Bot 会全自动定时巡查B站官方动态，利用 AI 捕获并入库新兑换码，无需手动干预。若有遗漏，可使用上方指令手动补录。
> - **提示**：表格中「别名」列的内容可直接替代主指令使用，无需加 `/` 前缀。管理员权限包括群主、群管理员及 Bot 超级用户。

---

## 🚀 快速开始

### 📦 1. 安装插件与依赖

#### 使用 nb-cli（推荐）

```bash
nb plugin install nonebot-plugin-yysls
```

#### 使用 pip

```bash
pip install nonebot-plugin-yysls
```

#### 使用 requirements.txt

运行以下命令安装依赖：

```bash
pip install -r requirements.txt
```

安装后在 `bot.py` 或 `pyproject.toml` 中加载插件：

```python
nonebot.load_plugin("nonebot_plugin_yysls")
```

---


### ⚙️ 2. 配置 `.env` 文件

在项目根目录创建或编辑 `.env` / `.env.prod` 文件，添加以下配置：

```ini
# ============ NoneBot 基础配置 ============
# Bot 超级用户 QQ 号（用于接收私聊通知和管理权限，填写你自己的 QQ）
SUPERUSERS=["123456789"]

# 命令起始符（支持多个）
COMMAND_START=["/", ""]

# 命令分隔符
COMMAND_SEP=[" "]

# ============ 反向 WebSocket 驱动配置 ============
# 使用 websockets 驱动
DRIVER=~websockets

# 监听地址与端口（需与 NapCat 配置中的目标端口一致）
HOST=0.0.0.0
PORT=8080

# ============ 燕云十六声插件配置 ============
# 公告检查间隔（分钟）
YYSLS_CHECK_INTERVAL=30

# 商城提醒触发时间（24小时制，小时）
YYSLS_SHOP_REMIND_HOUR=10

# ===== 定时任务核心配置 =====
# 无需修改此处配置
APSCHEULER_AUTOSTART=true
YYSLS_TIMEZONE=Asia/Shanghai

# 官网公告 API 地址（通常无需修改，使用内置默认值即可）
# YYSLS_NEWS_URL=https://yysls.qq.com/act/a20240605news/index.html

# ==============================
# AI 大模型配置 (核心必填)
# ==============================
# 推荐使用 DeepSeek、通义千问 或 OpenAI 兼容接口
# 请前往对应云平台的控制台获取 API Key
# 你的 API 密钥 (请替换为真实的 Key，切勿泄露！)
AI_API_KEY=sk-your_api_key_here

# API 接口的基础 URL (以通义千问/DashScope为例，DeepSeek/OpenAI请替换为对应地址)
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 使用的模型名称 (如 qwen-turbo, deepseek-chat, gpt-3.5-turbo 等)
AI_MODEL=qwen-turbo

# B站API配置
# Cookie 获取方式：
# 1. 浏览器登录 B 站 (www.bilibili.com)
# 2. 按 F12 打开开发者工具 → 顶部菜单选择 Application (应用)
# 3. 左侧展开 Cookies → 点击 https://www.bilibili.com
# 4. 在右侧列表中找到 SESSDATA、bili_jct、buvid3，将它们的 Value 复制填入下方

BILIBILI_SESSDATA="这里填入你的SESSDATA值"
BILIBILI_BILI_JCT="这里填入你的bili_jct值"
BILIBILI_BUVID3="这里填入你的buvid3值"
```

> 📝 **配置说明**：
> - `SUPERUSERS`：务必替换为你自己的 QQ 号，否则无法使用管理员指令。
> - `PORT`：反向 WebSocket 监听端口，需与下方 NapCat 配置中的端口保持一致。
> - 完整配置项及默认值请参考插件源码中的 `config.py`。

---

### 🤖 3. 连接 NapCat（反向 WebSocket）

[NapCat](https://github.com/NapNeko/NapCatQQ) 是基于 QQNT 的无头 QQ 客户端，支持 OneBot 11 协议。本插件推荐使用**反向 WebSocket** 方式连接。

#### 步骤 1：安装并登录 NapCat

1. 前往 [NapCat Releases](https://github.com/NapNeko/NapCatQQ/releases) 下载最新版本。
2. 解压到任意目录（如 `C:\NapCat`）。
3. 运行启动脚本（Windows 为 `launcher.bat`，Linux 为 `launcher.sh`）。
4. 使用手机 QQ 扫码登录 Bot 账号。

#### 步骤 2：配置 NapCat 反向 WebSocket

在 NapCat 配置目录中找到 `config/onebot11_<你的Bot QQ号>.json`（或使用 WebUI 配置），修改网络配置如下：

```json
{
  "network": {
    "reverseWs": [
      {
        "enable": true,
        "urls": [
          "ws://127.0.0.1:8080/onebot/v11/ws"
        ]
      }
    ]
  },
  "message": {
    "postSelfMessage": false,
    "ignoreSelfMessage": true
  }
}
```

> ⚠️ **重要提示**：
> - `urls` 中的端口 `8080` 必须与 `.env` 文件中配置的 `PORT` 完全一致。
> - 确保 `reverseWs` 的 `enable` 字段为 `true`。
> - 如果 NoneBot 与 NapCat 不在同一台机器上，请将 `127.0.0.1` 替换为 NoneBot 所在服务器的局域网 IP 或公网 IP。

#### 步骤 3：验证连接

启动 NapCat 后，观察 NapCat 的控制台日志。如果看到类似以下输出，说明连接成功：

```log
[INFO] 反向 WebSocket 连接成功：ws://127.0.0.1:8080/onebot/v11/ws
```

---

### 🎯 4. 启动服务

确保 NapCat 已启动且连接成功后，再启动 NoneBot 服务。

#### 方式 1：使用 nb-cli（推荐）

在项目根目录执行：

```bash
nb run
```

#### 方式 2：直接运行 bot.py

```bash
python bot.py
```

#### 启动成功标志

当控制台出现以下日志时，表示服务已成功启动并加载插件：

```log
[INFO] nonebot | NoneBot is initializing...
[INFO] nonebot | Running NoneBot...
[INFO] uvicorn | Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
[INFO] nonebot | Succeeded to load plugin "nonebot_plugin_yysls"
```

#### 验证 Bot 是否正常工作

1. 将 Bot 账号拉入目标 QQ 群。
2. 在群内发送 `/yysls_help` 或 `燕云帮助`。
3. 此时 Bot 应该会回复帮助菜单。
4. 管理员发送 `/yysls_sub` 开启该群的自动推送功能。

---

## 📝 更新日志

见 [CHANGELOG.md](./CHANGELOG.md)

---

## 📄 许可证

本项目采用 [MIT License](./LICENSE) 开源

---

<div align="center">
  <p>如果这个项目对你有帮助，请给一个 ⭐️ Star 支持！</p>
</div>
