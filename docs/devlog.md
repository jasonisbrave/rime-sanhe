# 三合输入法开发

> 开发日志（Devlog）——记录每个阶段的决策、实现与踩坑，持续更新。

---

## 2026-09-13 · 立项到 v1.1.0-beta1：一天走完全程

### 一、立项

**需求**：制作自己的输入法，参考 [Rime 万象](https://github.com/amzxyz/rime_wanxiang)，但只保留三种输入方案：

1. 全拼
2. 小鹤双拼
3. 86 版五笔

### 二、技术调研

拆解万象内核后确认的关键架构：

- **带调词库**：`dicts/` 全部词库的编码是带声调的全拼（如 `ā bà`），这是万象智能功能的基础
- **转写规则**：`wanxiang_algebra.yaml` 按方案分节（base/reverse/mixed/english × 各双拼），全拼与双拼**共用词库**，只换字母映射规则
- **动态切换**：`set_schema.lua` 通过改写 `.custom.yaml` 里的 algebra 引用目标 + 重新部署实现 `/flypy` 一键切换
- **许可**：万象 CC BY 4.0（可改造、需署名）；五笔86 码表取自 [rime/rime-wubi](https://github.com/rime/rime-wubi)（MIT）；symbols 取自 rime-prelude（BSD-3）

### 三、构建

- 全局改名 wanxiang→sanhe（含 Lua 目录、模块引用），上游署名链接与语法模型文件名做保护性替换
- 用 ruamel.yaml（保留注释）裁剪 algebra：删除 lite/pro 两段和其余 12 种双拼，仅留全拼 + 小鹤双拼
- 剔除九宫格（t9）、pro/lite 变体；清理 `set_schema.lua` 中引用已删段落的 `/zjf //jjf` 死分支
- 五笔86 作为**独立方案**接入：极点86 码表 + z 键拼音反查
  - 自建 `pinyin_reverse.dict.yaml`（5.1 万条，由带调字库去声调生成）供反查
  - 按 Rime 惯例补 `dependencies` + 极简依赖 schema，否则部署器不编译反查词库
- 400MB 语法模型默认禁用，README 提供开启教程

### 四、验证

不满足于"写完"，搭建了真实编译验证环境：

- 无 root 环境：`apt-get download` + `dpkg -x` 本地解包 librime 工具链（含 lua 插件）
- `rime_deployer --build` 干净部署：**零错误**，拼音 82MB 词库 + 反查 + 混输 + 英文 + 五笔全部编译成功
- 模拟 `/flypy` 切换后重新部署，双拼转写链验证通过

### 五、发布

- GitCode：API 建仓库 + 推送（坑：POST 接口必须用 `private-token` header）
- GitHub：SSH 部署（沙盒无 22 端口，走 `ssh.github.com:443`，主机密钥指纹逐一对照官方值核验）
- 双平台 Release v1.0.0：GitHub 支持附件上传（36.3MB 安装包直链），GitCode API 不支持附件
- README 徽章 + 下载直链

### 六、踩坑记录

| 坑 | 修法 |
|----|------|
| 方案选单漏绑 F4（README 吹了但配置没有） | `switcher/hotkeys` 补上 |
| README 声调键位误写"数字 1-4" | 实为 **7/8/9/0 对应一二三四声**（官方文档实锤），连按自动覆盖 |
| 会话中断造成静默字符损坏（Tab→空格） | 提交前 git diff 兜底，发现即还原 |
| `set_schema.lua` 残留 /zjf //jjf 分支引用已删段落 | 裁剪时同步清理死分支 |
| symbols 预设缺失导致五笔编译失败 | 随包自带 symbols.yaml（rime-prelude） |

### 七、beta：五笔召唤（v1.1.0-beta1）

**需求**：拼音方案中直接调用五笔，不想切方案。

**决策过程**：否决了"改写配置热切引擎"的重架构方案（万象 Lua 全按拼音流假设写，翻车风险高），选择照搬 `super_english` 成熟模式的**召唤式**设计：

- 新增 `lua/sanhe/super_wubi.lua`：`Component.TableTranslator` 挂载 wubi86 词典
- 拼音流输入 `/w+编码`（如 `/wvbg`）直接出五笔候选，**注释显示完整编码**，边打边学码
- 支持前缀补全（`/wvb` 列出 vb 开头编码），单次上限 30 条（可配）
- 纯增量：拼音流、`/flypy` 切换、五笔86 独立方案互不影响，删一行注册即可回退

验证：luac5.4 语法检查 ✓、YAML ✓、librime 整包部署 ✓。**真机实测进行中**。

### 八、当前状态与下一步

- 版本：`v1.1.0-beta1`（提交 `bd3767b`），GitCode / GitHub 双平台 Release 已发布
- 真机实测：✅ 全部通过（2026-09-13 22:19 冰糖反馈）
  - [x] `/wvbg` 召唤出「好」，注释显示编码
  - [x] `nihao8` 声调筛选（二声）正常
- 决策：**暂不转正**，beta 继续迭代新功能
- 待办：
  - [ ] 收集下一批 beta 功能需求
  - [ ] 迭代完成后视稳定性决定 v1.1.0 转正
