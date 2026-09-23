# Subtext 潜台词

**中文** | [English](README.en.md)

**读懂对方的潜台词，再决定怎么回。**

Subtext 是一个跑在你自己电脑上的聊天回复助手：粘贴一张微信聊天截图，它会分析对方的意图、情绪、是不是在开玩笑，并帮你给几条候选回复排序。

- 🔒 **本地运行**：截图识别和分析都在你电脑上完成，默认不联网
- ⚡ **很快**：基于开源决策模型 [Laya](https://huggingface.co/convaiinnovations/laya)，一次分析约 50 ms（RTX 4060）
- 🙅 **不碰微信**：不读取微信数据、不注入、不自动发送，只看你主动粘贴的截图
- ✍️ **可选 AI 代写**：配上 DeepSeek 等大模型 API，自动写 3 条候选回复

![演示](docs/demo.gif)

<details><summary>界面截图（浅色 / 深色）</summary>

![界面截图](docs/screenshot-light.png)

![深色模式截图](docs/screenshot-dark.png)

</details>

## 它能做什么

| 功能 | 说明 |
|---|---|
| 截图识别 | 在页面按 `Ctrl+V` 粘贴聊天截图，本地 OCR 识别文字，按气泡颜色区分「对方」和「我」。手机版、电脑版、深色浅色都支持，图片消息和表情包里的文字会自动忽略 |
| 意图分析 | 闲聊、提问、求助、邀约、要求、吐槽、分享、调侃、收尾 |
| 情绪分析 | 开心、平静、焦虑、生气、难过、无聊，带概率分布 |
| 玩笑检测 | 判断对方是不是在开玩笑 |
| 回复排序 | 对你写的（或 AI 写的）候选回复打分，给出「最合适」的概率 |

## 安装

需要 Windows 和 [Anaconda / Miniconda](https://www.anaconda.com/download)。有 NVIDIA 显卡会快很多，没有也能用 CPU 跑（一次分析约 0.2–0.5 秒）。

1. 下载本项目（右上角 **Code → Download ZIP** 并解压，或 `git clone`）
2. 双击 **`setup.bat`**：自动创建 `subtext` 环境并安装依赖（约 3 GB，主要是 PyTorch）
3. 双击 **`start.bat`**：首次启动会自动下载 Laya 模型（约 650 MB），之后启动约 30–40 秒，浏览器会自动打开 http://127.0.0.1:7860

<details><summary>手动安装（macOS / Linux 或不想用 bat）</summary>

```bash
conda create -n subtext python=3.11 -y
conda activate subtext
pip install torch            # 有 NVIDIA 显卡请按 https://pytorch.org 选择 CUDA 版本
pip install -r requirements.txt
python server.py
```

</details>

## 使用

1. 电脑版微信按 `Alt+A` 截取聊天区域，或直接用手机截屏发到电脑，回到页面按 `Ctrl+V`
2. 识别有误时：鼠标移到气泡上点 ⇄ 换成另一方说的，点 × 删除；或展开「编辑文字」直接改
3. 也可以粘贴单条消息，点「＋对方说」/「＋我说」手动添加
4. 选择对方和你的关系、希望的回复风格，写几条候选回复，点「分析并排序」

打开 http://127.0.0.1:7860/#demo 可以直接看示例效果。

## 开启「AI 帮我写」（可选）

1. 在 [platform.deepseek.com](https://platform.deepseek.com) 创建 API key
2. 在 PowerShell 里运行（把 `你的key` 换成真实的 key）：

   ```
   setx DEEPSEEK_API_KEY "你的key"
   ```

3. 重新打开终端，重启 Subtext

也支持任何 OpenAI 兼容接口（OpenRouter、Ollama 等），设置 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` 三个环境变量即可。

> ⚠️ 开启后，最近的聊天内容（包括对方的消息）会发送给你配置的大模型服务商。

## 让 AI 用你的口吻说话

给它看你以前怎么说话，生成的回复就会像你，不用训练模型。

1. 把自己的聊天截图放进一个文件夹，比如 `聊天记录/`（几十张就够）
2. 生成语料：

   ```
   conda run -n subtext python build_corpus.py 聊天记录
   ```

   它只提取**你自己发的消息**和上下文，写进 `my_style.jsonl`。建议翻一遍，把识别错的行删掉。
3. 重启 Subtext，在「AI 帮我写」里勾上 **像我说话**

工具会统计你的说话习惯（平均长度、标点和 emoji 用得多不多、常用开头），再挑出几段和当前情况最像的真实对话，一起交给大模型模仿。

实际效果（同一句「你那个论文写完了吗」）：

| 关闭 | 开启（参考 169 条真实回复） |
|---|---|
| 哎呀正愁这事呢，你写多少了？ | 就是有点赶 |
| 快了快了，你呢？别告诉我你也没写完 | 我想再改改 |

**`my_style.jsonl` 和采纳记录 `adopted.jsonl` 都在 `.gitignore` 里，只存在你电脑上。**

### 语料会自己长大

每次点「复制」，工具都会把上下文、候选和你的选择记到 `adopted.jsonl`，这是以后微调排序模型的训练数据。

在「自己写候选」模式下，那几条本来就是你亲手写的，所以**你复制的那条还会自动加进 `my_style.jsonl`**，界面上会提示「已加进你的语料（N 条）」。用得越久，AI 越像你。

「AI 帮我写」模式下采纳的回复**不会**进风格语料 —— 那是大模型写的，回流进去会让它越学越偏。

## 实测表现与局限

诚实地说：

- ✅ **情绪、玩笑检测**：大多数情况判断正确
- ⚠️ **意图**：大部分正确，但有明显误判，比如把「帮我顶一下会」判成「邀约」（见上方折叠的界面截图）
- ⚠️ **回复排序**：只作参考。Laya 是分类模型，不擅长判断回复的「好坏」，偶尔会偏爱又长又啰嗦的回复；同一段对话，候选换个说法排序就可能完全变样
- ⚠️ **截图识别**：按微信的绿色气泡判断「我」，手机和电脑截图都支持；群聊中对方的昵称可能被识别成一句话，需要手动删除
- Laya 本身发布不久（2026 年 9 月），效果和接口都可能变化

欢迎在 Issues 里反馈识别错误的例子（请先打码）。

## 工作原理

```
聊天截图 ──RapidOCR──▶ 文字 + 气泡位置/颜色 ──▶ 「对方：…」「我：…」
                                                    │
                     Laya（一次前向，非生成式） ◀───┘
                        ├─ 意图 / 情绪 / 玩笑：choice、noul 题型
                        └─ 候选回复排序：把候选当作 choice 选项，输出每条的概率
```

所有代码只有两个文件：`server.py`（Python 标准库 HTTP 服务 + 模型调用）和 `index.html`（界面）。

## 免责声明

- 本项目与微信、腾讯、Convai Innovations、DeepSeek 均无关联
- 本工具只处理你主动提供的截图或文字，不访问任何账号或聊天数据库，不会自动发送消息
- 请尊重聊天对象的隐私，不要用于骚扰、欺诈或其他违法用途
- 模型输出仅供参考，最终怎么回复由你自己决定

## 致谢

- [Laya](https://huggingface.co/convaiinnovations/laya) by Convai Innovations（Apache 2.0）
- [RapidOCR](https://github.com/RapidAI/RapidOCR)（Apache 2.0）

## 许可证

[MIT](LICENSE)
