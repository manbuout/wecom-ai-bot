# Wecom-AI-Bot 🤖

> 基于大语言模型的 AI 人格克隆聊天机器人，部署于企业微信。

通过分析真实聊天数据自动提取说话风格，注入 AI System Prompt，实现个性化对话效果。

## ✨ 功能特性

- **聊天风格分析**：从 QQ/微信聊天记录（24,000+ 条）中自动提取语气词、高频词、句式特征
- **多阶段对话提取**：按关系阶段（初识/磨合/热聊/降温/沉默）分组，通过质量打分算法筛选高代表性示例
- **人格注入**：动态构建 System Prompt，将提取的说话风格注入大语言模型
- **企业微信集成**：支持企业微信自建应用消息收发，AES 加解密，异步回复与去重
- **多用户隔离**：每个用户独立的对话历史管理
- **云端部署**：支持腾讯云服务器部署与 Vercel 部署

## 🛠 技术栈

| 模块 | 技术 |
|------|------|
| AI 服务 | Anthropic SDK / 小米 MiMo API |
| 聊天解析 | Python / BeautifulSoup / 正则表达式 |
| 消息对接 | 企业微信 API / AES 加解密 / Flask |
| 部署 | 腾讯云轻量服务器 / Vercel / Ngrok |
| Web 界面 | HTML / WebSocket 实时日志 |

## 📁 项目结构

```
wecom-ai-bot/
├── app.py                 # Flask 回调服务器（含 AES 解密）
├── main.py                # 命令行入口（解析/对话测试/启动Bot）
├── start_bot.py           # 一键启动器（Flask + SSH隧道）
├── config.example.yaml    # 配置模板
├── requirements.txt       # Python 依赖
── ChatParser/            # 聊天记录解析模块
│   └── chat_parser.py     # QQ/微信 HTML 解析 + 风格分析 + 多轮对话提取
├── WXBOT/                 # 企业微信 Bot 模块
│   └── bot.py             # 消息收发 + access_token 管理 + 回调服务
├── 艾科尔/                # AI 核心服务模块
│   ── service.py         # Anthropic SDK 调用 + System Prompt 构建
├── 简介/                  # 人设配置文件
│   └── pig头.yaml         # 人格数据（风格特征 + 对话示例）
── 网络/                  # Web 仪表盘
│   └── index.html         # WebSocket 实时日志界面
└── vercel.json            # Vercel 部署配置
```

##  快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

复制配置模板并填写你的参数：

```bash
cp config.example.yaml config.yaml
```

需要配置：
- `ai.api_key` — 小米 MiMo API Key
- `ai.base_url` — API 地址
- `wecom.corp_id` / `agent_id` / `secret` — 企业微信应用信息

### 3. 解析聊天记录（可选）

```bash
python main.py parse
```

从 QQ/微信 HTML 导出文件中提取说话风格，生成人设 YAML 文件。

### 4. 命令行测试

```bash
python main.py chat
```

### 5. 启动企业微信 Bot

```bash
python main.py wechat
```

或使用一键启动器（自动创建 SSH 隧道）：

```bash
python start_bot.py
```

## 📸 效果预览

> 项目已部署至 [wecom-ai-bot.vercel.app](https://wecom-ai-bot.vercel.app)

##  实现亮点

1. **风格提取算法**：基于 2-gram 高频词、语气词统计、句式特征分析，自动构建人格画像
2. **分阶段对话采样**：将 24,000+ 条消息按时间线划分为 6 个关系阶段，每个阶段均匀采样高质量多轮对话
3. **对话质量打分**：综合轮次深度、内容长度、情感表达等维度为对话打分，筛选最具代表性的示例
4. **企业微信安全对接**：完整实现 AES-CBC 消息加解密、SHA1 签名验证、access_token 自动缓存与刷新
5. **异步回复 + 去重**：线程池处理消息回复，消息锁防止重复响应

## 📄 许可证

MIT License
