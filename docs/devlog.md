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
  - [x] 收集下一批 beta 功能需求（2026-11-19 完成，见下节）
  - [x] 迭代完成后视稳定性决定 v1.1.0 转正（本次转正）

---

## 2026-11-19 · 性能专项与 v1.1.0 转正

### 一、动机与决策

万象日常使用卡顿，决定全面转向自维护三合。迭代路线：**v1.1.0（延迟基准 + 性能档位 + 五笔召唤转正 + 工程化）→ v1.2.0（词库瘦身与 Lua 链路优化）→ v2.0（语音第三输入模式，已立项）**。平台适配作为最后的扩展阶段。

### 二、延迟基准工具（tools/bench/）

ctypes 直驱小狼毫 `rime.dll`（真实引擎 + lua 插件），逐键测量 `RimeProcessKey` + `RimeGetContext`；三变体（full/balance/fast）各预热 1 轮 + 正式 3 轮 × 60 键；健康断言（nihao 后候选数 >0）防 lua 静默失效。

**librime FFI 踩坑（复用价值高，详见 tools/bench/README.md）**：

| 坑 | 解法 |
|----|------|
| `RimeTraits.modules` 是 `char**` 数组而非逗号分隔字符串，传错直接访问违例崩溃 | `(c_char_p*3)(b"default", b"lua", None)` |
| ctypes 结构体只存指针，modules 数组被 GC → 悬垂指针，部署随机空跑 | 数组挂保活引用 |
| 对不存在字段赋值会静默建 Python 属性（引擎拿到 NULL） | 赋值后读回校验 |
| librime 1.11 的 `RimeComposition` 只有 5 字段（旧教程多 2 个）→ menu 偏移错 16 字节，num_candidates 恒 0 | 以上游 1.11.2 rime_api.h 为准 |

### 三、基线数字与关键发现（weasel-0.17.4 / librime 1.11）

| 指标 | full | balance | fast |
|---|---|---|---|
| 每键 mean | 5.458 ms | 5.529 ms | **5.160 ms（-5.5%）** |
| 每键 p95 | 9.347 ms | 9.843 ms | 9.281 ms |
| 部署耗时 | 20.8 s | 20.9 s | 21.0 s |

- 分组：short_word -6.4%、tone -6.2%、sentence 基本持平、balance 全指标在噪声内。
- **关键发现：延迟几乎全部在 process_key（3.7～6.5 ms/键），get_context 仅 0.02～0.04 ms**——候选在 process_key 阶段已算完；补全/注释参数的档位收益有限（-5.5%），延迟集中在 process_key 所覆盖的处理链上（Lua 处理器/过滤器/翻译器与词典检索都在此阶段执行）。**各组件的具体成本占比由 v1.2.0 前置的组件分解测量给出**（见 tools/bench/results/component-breakdown.md），据此确定瘦身优先级。
- 五笔召唤场景因基准部署精简（schema_list 只留 sanhe 控制部署时长）未纳入负载，属工具已知局限。

### 四、性能档位（/fast /balance /full）

- 新增 `lua/sanhe/set_profile.lua`：与 `/flypy` 同机制（改写用户目录 `sanhe.custom.yaml` 的标记块后重新部署），行级块操作、fast→full 可逐字节还原模板、不触碰 algebra 行，两套切换互不干扰。
- fast＝关补全（主/英/混）+ 注释数 6；balance＝注释数 15；full＝恢复默认。
- 块格式与 bench 工具写入格式完全一致（标记顶格、键值缩进 2 空格）。

### 五、工程化与发布

- **CI**（`.github/workflows/ci.yml`）：Debian trixie 容器装 `librime-bin + librime-plugin-lua + librime-data`，`luac -p` 全量语法检查 → `rime_deployer --build` 真实部署 → 断言 sanhe/wubi86 的 prism/table 产物 → 日志错误检查（含 pipefail 防 tee 吞退出码、glog `E20…` 行首格式检测）。首轮真实运行待 push 后观察。
- **打包**（`tools/release/package.py`）：读 version.txt 生成 `dist/rime-sanhe-v{版本}.zip` + sha256。v1.1.0 实测：105 文件 / 原始 100.12 MiB / 压缩 37.26 MiB。
- **CHANGELOG.md** 建立（Keep a Changelog 风格）。

### 六、v2.0 语音立项调研

结论：**可行，值得立项**（完整调研见 [voice-2.0-research.md](voice-2.0-research.md)）。要点：librime 无音频能力，采用「SenseVoice-small sidecar（参考 CapsWriter-Offline，MIT）+ `/vv` lua 候选胶水」旁路架构；语音文本过三合过滤链、养用户词库，是与 Win+H（需联网、无热词）的本质差异。里程碑 M1 热词导出脚本 → M2 `/vv` + sidecar → M3 打包。

### 七、v1.1.0 转正清单

- 五笔召唤 beta → 正式（v1.1.0-beta1 已真机验证）
- 版本号：version.txt / sanhe.lua → 1.1.0
- README：性能档位章节、基准工具章节、目录结构更新
- 新增推送前双复核流程（AGENTS.md）：oracle 复核 + designer 润色 README + 用户确认后才提交推送

### 八、真机待办

- [x] 真机点验 `/fast` `/balance` `/full` 切换与重新部署 —— **2026-11-19 通过**：`/fast` 在小狼毫真机切换成功，档位块写入格式正确（标记顶格/键值缩进 2），用户的小鹤双拼 algebra 配置与自定义项原样保留；极速档日常使用中
- [x] push 后观察 CI 首轮运行 —— **2026-11-19 通过（49s）**：luac 全检、容器内部署、prism.bin 断言、错误检查全绿（复核阶段修正的产物名与 pipefail 经住实战）

### 九、v1.2.0 前置测量：Lua 组件成本分解（2026-11-19）

新增 `tools/bench/breakdown.py`（复用 bench.py 的 FFI，engine 列表从 schema 运行时解析，单变体子进程隔离），12 变体实测（full 基线 5.226 ms/键）：

| 发现 | 成本 |
|---|---|
| **整条 Lua 链**（no_lua_all 极限参照 → 0.544 ms/键） | **+4.682 ms/键（89.6%）** |
| **trigger 型翻译器组**（时间/计算器/随机/统计/符号/版本/切档/unicode/数字，10 个） | **+3.678 ms/键（70.4%）** |
| super_replacer（emoji/简繁/简码等常驻规则） | +0.432 ms（8.3%） |
| super_filter（字符集过滤） | +0.364 ms（7.0%） |
| 其余单组件（lookup/comment/processor/english 等） | 各 +0.05～0.33 ms |

**解读**：10 个 trigger 型翻译器即便不触发，每键也要跑一遍 Lua 入口——这解释了 fast 档（只调补全/注释参数）仅 -5.5% 的现象。注意两点：单组件 Δ<0.3 ms 处于噪声量级；逐项 Δ 之和（5.97）大于整体差（4.68），存在非线性交互，不可线性外推。

**v1.2.0 优先级**（据此排序，每步用 breakdown.py 复测验证）：

**二分定位（交错基线协议，2026-11-19）**：组内 10 个翻译器单删测量（首轮顺序协议被机器时间漂移污染作废，重跑采用 full/变体交错的基线协议；12 次 full 穿插基线中首个为 6.446ms——冷启动，其余 11 次落在 5.008～5.196ms。注意 no_tr_shijian 的相邻基线含首个冷启动值，其 Δ=+0.141 置信度较低）：

| 定位 | 成本 | 机制 |
|---|---|---|
| **super_symbols** | **+1.586 ms/键（31.2%）** | 伪 trigger：recognizer pattern 现成却未隔离，每个普通拼音键都跑重逻辑 |
| **input_statistics** | **+0.589 ms/键（11.6%）** | 每键统计 + 提交写库，无前缀可隔离 |
| 其余 8 个 | 合计 +1.995 ms（均 0.249/个） | 每键固定入口成本 × 数量的累加，无突出单项 |
| 组删参照 | +3.626 ms（69.8%） | 与首轮 +3.678 吻合；元凶 2.176 + 其余 1.995 ≈ 组删 |

**v1.2.0 重构方案**（预计 full 5.1ms → 1.6~1.9ms/键，比 fast 档 -5.5% 高一个数量级）：
1. `super_symbols` recognizer tag 隔离（pattern 已在方案中，改动最小，回收 ~1.6ms）
2. `input_statistics` 触发时才读统计 + 写库限流/批量落盘（回收 ~0.6ms）
3. 其余 8 个合并为 `hub_translator` 按输入前缀内部分发（入口成本 8→1，回收 ~1.7ms；V/R/U 前缀的顺手做 tag 化双保险）

v1.1.0 已于 2026-11-19 发布（GitHub Release + CI 通过），组件分解数据即 v1.2.0 开发输入。
