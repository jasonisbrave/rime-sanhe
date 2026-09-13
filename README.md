# 三合输入法（rime-sanhe）

![版本](https://img.shields.io/badge/版本-v1.0.0-green)
![许可](https://img.shields.io/badge/许可-CC%20BY%204.0--MIT--BSD--3-blue)
![引擎](https://img.shields.io/badge/引擎-Rime%20中州韻-red)
![方案](https://img.shields.io/badge/方案-全拼%20·%20小鹤双拼%20·%20五笔86-orange)
![平台](https://img.shields.io/badge/平台-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20Android%20%7C%20iOS-9cf)

> **下载安装包** → [GitCode Releases](https://gitcode.com/jasonisbrave/rime-sanhe/releases)（含打包好的 v1.0.0 zip，克隆本仓库亦可直接部署）

一套基于 [Rime](https://rime.im) 引擎的中文输入方案，内核精简自 [万象拼音](https://github.com/amzxyz/rime_wanxiang)（amzxyz，CC BY 4.0），只保留 **三种输入方案**：

| 方案 | 说明 | 切换方式 |
|------|------|----------|
| **三合拼音·全拼** | 带调词库、智能纠错、简拼、整句输入 | 默认方案 |
| **三合拼音·小鹤双拼** | 与全拼共用词库和全部智能功能 | 输入 `/flypy`；切回全拼输入 `/pinyin` |
| **五笔86** | 极点86码表，独立方案 | `F4` 或状态面板（`Ctrl+``）选单 |

拼音方案与五笔方案**共享同一套用户词库管理习惯**（custom_phrase.txt 自定义短语），但各自独立记词。

## 主要特性（拼音方案）

- 带调全拼词库，支持声调辅助筛选（数字 1-4 选声调）
- 智能纠错：错音、错字兼容（如 `zhidao`→知道、`jandan`→简单）
- 拆字与笔画反查：输入 `` ` `` 进入拆字反查
- 中英混输：直接打英文单词、自动识别
- 拆分输入、超级注释、时间日期（`\rq`）、计算器、符号大全（`/fh`）等 Lua 增强
- 语法模型（可选，见下文）：整句输入质量大幅提升

## 安装

将本目录（或解压后的 `rime-sanhe/`）中**所有文件**复制到 Rime 用户目录：

| 平台 | 输入法 | 用户目录 |
|------|--------|----------|
| Windows | 小狼毫 weasel | `%APPDATA%\Rime` |
| macOS | 鼠鬚管 squirrel | `~/Library/Rime` |
| Linux | fcitx5-rime | `~/.local/share/fcitx5/rime` |
| Linux | ibus-rime | `~/.config/ibus/rime` |
| Android | 同文 / Hamsters | 应用内用户目录 |
| iOS | 仓输入法 | 应用内用户目录 |

然后**重新部署**：
- Windows：右键托盘图标 →「重新部署」
- macOS：菜单栏输入法图标 →「重新部署」
- Linux fcitx5：`fcitx5-remote -r` 或配置工具中点击部署

首次部署需要编译词库（约 20 万词条），请耐心等待 1-3 分钟。

### 首次使用拼音双拼切换

输入 `/flypy` 候选栏会出现「已切换到〔小鹤双拼〕」，按提示**再次重新部署**即可生效；
切回全拼输入 `/pinyin`，同样重新部署。

> 双拼切换会改写用户目录下的 `sanhe.custom.yaml` 等文件，属于正常现象。

## 开启语法模型（可选，强烈推荐）

语法模型（400MB）能显著提升长句输入准确率：

1. 下载模型：https://github.com/amzxyz/RIME-LMDG/releases （`LTS` 版中的 `wanxiang-lts-zh-hans.gram`）
2. 将 `.gram` 文件放入 Rime 用户目录
3. 打开 `sanhe.schema.yaml`，找到 `# grammar:` 一段，取消注释（第 113-116 行附近）
4. 重新部署

不启用语法模型时一切功能正常，仅长句候选稍逊。

## 自定义

### 模糊音
编辑用户目录下的 `sanhe.custom.yaml`，取消对应行注释，如 `z/zh` 模糊音取消注释 `- sanhe_algebra:/模糊音_z_zh`，然后重新部署。

### 自定义短语
编辑 `custom_phrase.txt`，格式：`短语\t编码\t权重`，如：

```
邮箱      yx      1
三合输入法   shsr    1
```

### 五笔方案
- **z + 拼音** 反查汉字五笔编码（如 `zni` 查看「你」的编码）
- 短语同样写在 `custom_phrase.txt`，两个方案通用
- 用户词库自动学习，`Ctrl+=` 手动造词

## 目录结构

```
rime-sanhe/
├── sanhe.schema.yaml        # 拼音主方案（全拼+小鹤双拼）
├── sanhe_algebra.yaml       # 拼音转写规则（含模糊音库）
├── sanhe.dict.yaml          # 拼音词库索引
├── sanhe_reverse.*          # 拆字/笔画反查
├── sanhe_english.*          # 英文词汇
├── sanhe_mixedcode.*        # 中英混合编码
├── wubi86.schema.yaml       # 五笔86方案
├── wubi86.dict.yaml         # 五笔86码表
├── pinyin_reverse.*         # 五笔拼音反查词库（含部署依赖）
├── custom_phrase.txt        # 自定义短语（两方案通用）
├── default.yaml             # 全局配置（方案列表、快捷键）
├── symbols.yaml             # 标点符号预设（源自 rime-prelude）
├── weasel.yaml              # 小狼毫界面皮肤
├── custom/                  # 方案切换模板（勿删）
├── dicts/                   # 各分类词库
├── licenses/                # 第三方许可证
└── lua/                     # Lua 增强脚本
```

## 许可与致谢

- 拼音方案、词库、Lua 脚本：衍生自 **万象拼音** [amzxyz/rime_wanxiang](https://github.com/amzxyz/rime_wanxiang)，遵循 **CC BY 4.0**，词库另含万象项目所引用的开源数据
- 五笔86码表：源自 [rime/rime-wubi](https://github.com/rime/rime-wubi)（**MIT License**，见 `licenses/rime-wubi-LICENSE`）
- symbols.yaml：源自 [rime/rime-prelude](https://github.com/rime/rime-prelude)（**BSD-3-Clause**，见 `licenses/rime-prelude-LICENSE`）
- Rime 引擎：[rime.im](https://rime.im)（BSD / GPL / LGPL）

按 CC BY 4.0 要求，衍生分发时请保留对本项目及万象上游的署名。
