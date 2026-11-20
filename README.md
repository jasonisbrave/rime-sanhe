# 三合输入法（rime-sanhe）

一套基于 [Rime](https://rime.im) 的中文输入方案，面向全拼、小鹤双拼和五笔 86 用户。内核精简自 [万象拼音](https://github.com/amzxyz/rime_wanxiang)，保留带调词库、智能纠错、反查和 Lua 增强等能力。

> **快速安装：** 下载 [v1.2.0 安装包](https://github.com/jasonisbrave/rime-sanhe/releases/download/v1.2.0/rime-sanhe-v1.2.0.zip)，解压后将 `rime-sanhe/` 内的全部文件复制到 Rime 用户目录，再重新部署。也可将本仓库完整克隆到用户目录。
>
> 其他下载入口：[GitHub Releases](https://github.com/jasonisbrave/rime-sanhe/releases) · [GitCode Releases](https://gitcode.com/jasonisbrave/rime-sanhe/releases)。详细步骤见 [安装与部署](#安装与部署)。

[![版本](https://img.shields.io/badge/版本-v1.2.0-green)](https://github.com/jasonisbrave/rime-sanhe/releases/tag/v1.2.0)
[![许可](https://img.shields.io/badge/许可-CC%20BY%204.0-blue)](LICENSE)
[![引擎](https://img.shields.io/badge/引擎-Rime%20中州韻-red)](https://rime.im)
[![方案](https://img.shields.io/badge/方案-全拼%20·%20小鹤双拼%20·%20五笔86-orange)](#输入方案)
[![平台](https://img.shields.io/badge/平台-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20Android%20%7C%20iOS-9cf)](#安装与部署)

## 输入方案

| 方案 | 说明 | 切换方式 |
| --- | --- | --- |
| **三合拼音 · 全拼** | 带调词库，支持智能纠错、简拼和整句输入 | 默认方案 |
| **三合拼音 · 小鹤双拼** | 与全拼共用词库和智能功能 | 输入 `/flypy`；输入 `/pinyin` 切回全拼 |
| **五笔 86** | 极点 86 码表，作为独立方案使用 | 按 `F4` 或 ``Ctrl+` `` 打开状态面板选择 |

拼音与五笔 86 共用 `custom_phrase.txt` 维护置顶短语，但自动学习的用户词库彼此独立。

## 拼音方案特性

- **带调词库与声调筛选**：`7`、`8`、`9`、`0` 分别对应一、二、三、四声，连按可自动覆盖；不确定声调时，可依次按下 `7`、`8`、`9`、`0`
- **智能纠错**：兼容常见错音、错字，同时支持简拼和整句输入
- **拆字与笔画反查**：输入反引号（`` ` ``）进入反查
- **中英混输**：可直接输入英文单词，自动识别中英文混合内容
- **Lua 增强**：提供拆分输入、超级注释、日期时间（`\rq`）、计算器、符号大全（`/fh`）等功能
- **双拼计算器**：小鹤双拼下直接输入 `v1+2*3` 即可计算（v 后跟算符或数字的表达式形态），无需切换大写；注意双拼下裸 `v` 后直接按数字会进入计算器（数字选词/声调键此时让位，Esc 可退出）
- **深度性能优化**：v1.2.0 重构 Lua 组件链，实测每键延迟降低约 35%（符号库惰性加载、统计写库限流、低频翻译器合并按需分发，常规输入不再承担其重逻辑）
- **五笔召唤**：在拼音方案中输入 `/w`，后接五笔编码（如 `/wvbg`），即可显示五笔候选，并在注释中查看完整编码
- **性能档位**：输入 **`/fast`**、**`/balance`** 或 **`/full`**，一键切换极速、均衡、标准三档配置，改善响应速度；详见下文
- **可选语法模型**：改善长句输入效果，启用方法见下文

## 安装与部署

### 1. 复制文件

将本仓库（或解压后的 `rime-sanhe/`）中的全部文件和子目录复制到 Rime 用户目录：

| 平台 | 输入法 | 用户目录 |
| --- | --- | --- |
| Windows | 小狼毫（Weasel） | `%APPDATA%\Rime` |
| macOS | 鼠鬚管（Squirrel） | `~/Library/Rime` |
| Linux | fcitx5-rime | `~/.local/share/fcitx5/rime` |
| Linux | ibus-rime | `~/.config/ibus/rime` |
| Android | 同文输入法（Trime） | 应用内用户目录 |
| iOS | 仓输入法（Hamster） | 应用内用户目录 |

### 2. 重新部署

- **Windows**：右键单击托盘图标，选择「重新部署」
- **macOS**：单击菜单栏输入法图标，选择「重新部署」
- **Linux（fcitx5）**：执行 `fcitx5-remote -r`，或在配置工具中点击「部署」

首次部署需要编译词库，请耐心等待。

### 3. 切换全拼与小鹤双拼

1. 在拼音方案中输入 `/flypy`，候选栏会出现切换到小鹤双拼的提示。
2. 再次重新部署，使切换生效。
3. 需要切回全拼时，输入 `/pinyin`，然后重新部署。

> 切换方案会改写用户目录下的 `sanhe.custom.yaml` 等文件，属于正常现象。请保留 `custom/` 中的切换模板。

## 启用语法模型（可选）

语法模型约 400 MB，可改善长句输入准确率：

1. 从 [RIME-LMDG 的 LTS Release](https://github.com/amzxyz/RIME-LMDG/releases/tag/LTS) 下载 `wanxiang-lts-zh-hans.gram`。
2. 将 `.gram` 文件放入 Rime 用户目录。
3. 打开 `sanhe.schema.yaml`，搜索 `# grammar:`，取消 `grammar:` 和 `language: wanxiang-lts-zh-hans` 两行的注释。
4. 重新部署。

不启用语法模型时，其余功能不受影响，仅长句候选效果可能稍逊。

## 自定义

### 模糊音

将 `custom/sanhe.custom.yaml` 复制到 Rime 用户目录根目录；如果之前切换过全拼或小鹤双拼，该文件通常已经生成。

编辑用户目录下的 `sanhe.custom.yaml`，找到需要的模糊音规则并取消注释。例如，启用 `z` / `zh` 模糊音：

```yaml
- sanhe_algebra:/模糊音_z_zh
```

保存后重新部署。

### 自定义短语

编辑 Rime 用户目录下的 `custom_phrase.txt`。每项一行，依次填写短语、编码和权重，并使用 Tab 分隔：

```text
邮箱	yx	1
三合输入法	shsr	1
```

保存后重新部署。

### 性能档位

在拼音方案中输入 `/fast`、`/balance` 或 `/full`，然后**重新部署**，即可切换性能档位。切换机制与 `/flypy` 相同：命令会改写 `sanhe.custom.yaml`，且与全拼、小鹤双拼切换互不影响。

| 档位 | 命令 | 配置变化 | 适合 |
| --- | --- | --- | --- |
| 标准档 | **`/full`** | 恢复默认配置 | 追求完整功能 |
| 均衡档 | **`/balance`** | 候选注释数 30 → 15 | 与标准档差异在测量噪声内 |
| 极速档 | **`/fast`** | 关闭长词补全（`enable_completion`）、注释数降至 6、关闭英文/混输补全 | 追求最快响应；不依赖长词联想和英文补全 |

> 档位配置写在 `sanhe.custom.yaml` 的 `# >>> 性能档位` 标记注释之间，由命令自动维护；手动修改会在下次切换时被覆盖。

### 五笔 86

- 输入 `z`，后接拼音，即可反查汉字的五笔编码；例如输入 `zni`，查看「你」的编码
- 自定义短语同样写在 `custom_phrase.txt`，与拼音方案共用
- 连续上屏可自动造词，最长 4 字

## 延迟基准测试（开发者）

`tools/bench/` 提供基于真实 librime 引擎（小狼毫 `rime.dll`）的按键延迟测量工具，可对比标准、均衡、极速三档配置的每键处理耗时。

你可以用它验证性能档位的优化效果，并评估后续词库瘦身的收益。具体用法见 [tools/bench/README.md](tools/bench/README.md)。

## 目录结构

```text
rime-sanhe/
├── sanhe.schema.yaml        # 拼音主方案（全拼 + 小鹤双拼）
├── sanhe_algebra.yaml       # 拼音转写规则（含模糊音库）
├── sanhe.dict.yaml          # 拼音词库索引
├── sanhe_reverse.*          # 拆字与笔画反查
├── sanhe_english.*          # 英文词汇
├── sanhe_mixedcode.*        # 中英混合编码
├── sanhe_symbols.yaml       # 拼音方案符号配置
├── wubi86.schema.yaml       # 五笔 86 方案
├── wubi86.dict.yaml         # 五笔 86 码表
├── pinyin_reverse.*         # 五笔拼音反查词库与部署依赖
├── custom_phrase.txt        # 自定义置顶短语（拼音与五笔 86 共用）
├── default.yaml             # 全局配置（方案列表、状态面板与快捷键）
├── symbols.yaml             # 标点符号预设（源自 rime-prelude）
├── weasel.yaml              # 小狼毫界面配置
├── version.txt              # 当前版本号
├── custom/                  # 方案切换模板（勿删）
├── dicts/                   # 分类词库
├── docs/                    # 开发日志
├── licenses/                # 第三方许可证
├── lua/                     # Lua 增强脚本
└── tools/bench/             # 延迟基准测试工具（开发者）
```

开发过程与版本记录见 [开发日志](docs/devlog.md)。

## 许可与致谢

- **拼音方案、词库与 Lua 脚本**：衍生自万象拼音 [amzxyz/rime_wanxiang](https://github.com/amzxyz/rime_wanxiang)，遵循 [CC BY 4.0](LICENSE)；词库另含万象项目所引用的开源数据
- **五笔 86 码表**：源自 [rime/rime-wubi](https://github.com/rime/rime-wubi)，采用 MIT License，见 [许可证](licenses/rime-wubi-LICENSE)
- **`symbols.yaml`**：源自 [rime/rime-prelude](https://github.com/rime/rime-prelude)，采用 BSD-3-Clause，见 [许可证](licenses/rime-prelude-LICENSE)
- **Rime 引擎**：[rime.im](https://rime.im)（BSD / GPL / LGPL）

按 CC BY 4.0 要求，衍生分发时请保留对本项目及万象上游的署名。
