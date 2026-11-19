# 语音输入（第三输入模式）调研 —— sanhe 2.0 立项依据

> 调研日期：2026-11-19 · 结论：**可行，值得立项** · 定位：v2.0 主特性
> 目标：「全拼/双拼（同源拼音）+ 语音 + 五笔」的真正三合。

---

## 1. 生态现状

- **librime / 小狼毫无任何原生音频能力**：官方插件仅 charcode / legacy / lua / octagram / predict；weasel 与 TSF 前端无麦克风接口。
- **社区先例验证了「lua + sidecar」路线**：[spdc-elm/ASR_plugin_for_RIME](https://github.com/spdc-elm/ASR_plugin_for_RIME) —— `lua_processor` 双击 Ctrl 触发，lua 通过 HTTP 调本机 Python 录音/识别服务（OpenAI 兼容 `/v1/audio/transcriptions` 后端），状态显示用 preedit，**明确支持小狼毫**。可直接参考其 `lua/rime_dictation.lua` + `dictation_server.py`。
- **跨平台完整先例**：[feelime/feelime](https://github.com/feelime/feelime)（Android，2026-09）= librime 中文引擎 + sherpa-onnx（流式 Zipformer 临时文本 + Paraformer 纠错 + 本地标点）。
- **万象上游不做语音**：[RIME-Wanxiang #1019](https://github.com/amzxyz/RIME-Wanxiang/issues/1019)（Android 语音诉求，closed as not_planned）。sanhe 做语音是差异化，不撞车。

## 2. Windows 侧离线语音上屏工具

| 工具 | 引擎 | CPU 延迟（20s 音频） | 上屏 | License |
|---|---|---|---|---|
| [CapsWriter-Offline v2.6](https://github.com/HaujetZhao/CapsWriter-Offline) | Paraformer / SenseVoice-Small / Fun-ASR-Nano / Qwen3-ASR（sherpa-onnx + llama.cpp） | Paraformer/SenseVoice 0.6s；Nano 2s；Qwen3 4s（需 GPU） | SendInput 逐字 / 可选剪贴板 | **MIT** |
| [VoxCaps](https://github.com/xtayjmh/VoxCaps)（活跃 fork） | 同上 | 同上 | 同上 + 灵动岛状态 | MIT |
| Saymore / OpenWispr / whisper.cpp 系 | 本地模型 | 不一 | 模拟输入/剪贴板 | 开源 |

- 2025–2026 该赛道活跃（CapsWriter 2026-01 v2.1、2026-05 v2.6，衍生 VoxCaps/ququ/OpenLess/VocoType；[FunASR 生态页](https://www.funasr.com/ecosystem.html)）。
- 热词（音素模糊匹配）、数字 ITN（「十五六个」→「15~16个」）、去末尾标点均为现成轮子。
- C/S 架构（服务端 WebSocket 默认 6016 端口、**无鉴权需改绑 127.0.0.1**）——服务端可被 sanhe lua 直接复用。

## 3. Win+H 系统听写（兜底，不作卖点）

- **必须联网**（Azure 在线识别）；中文质量中等（[2026-01 横评](https://juejin.cn/post/7699061336558927912)：专名与长句错字多，中英混说易错），无热词、不可自定义词汇。
- 离线替代「语音访问」（Win+Ctrl+S）定位无障碍，语言覆盖少。
- 与第三方输入法无冲突，但识别语言跟随输入法语言，偶有混乱。

## 4. 本地中文 ASR 引擎选型（CPU、短句场景）

| 维度 | SenseVoice-small | Paraformer-large | faster-whisper | 流式 Zipformer |
|---|---|---|---|---|
| 中文准确率 | 与 Paraformer 同档 | 强基线、热词好 | small 弱、medium 慢；静音幻觉 | 低于离线 Paraformer |
| CPU 延迟 | **短句 <300ms 级**（整句非流式） | ~0.6s/20s + 外挂标点 1GB | small ~1s；medium 慢数倍 | 首字级实时 |
| 模型 | **~230MB（int8 更小）** | ~230MB + 标点 1GB | 460MB / 1.5GB | 70–160MB |
| 标点 | **内建** | 需外挂 | 内建（一般） | 无 |
| 许可 | MIT | Apache-2.0 | MIT | Apache-2.0 |

**结论：SenseVoice-small（int8）为默认引擎**；Fun-ASR-Nano / Qwen3-ASR-1.7B 留作 GPU 用户可选（sherpa-onnx 引擎接口统一，配置切换）。不采用 faster-whisper（中文弱+幻觉）与流式 Zipformer（整句上屏场景收益小、复杂度翻倍）。

## 5. 推荐架构与里程碑

**双轨**：
1. **主推：`/vv` lua 候选模式** —— SenseVoice sidecar 常驻（基于 CapsWriter server 裁剪或参考 spdc-elm 自建），识别结果写 `%TEMP%/sanhe_asr_result.txt`（或 GET `http://127.0.0.1:PORT/last`）；lua_processor 触发 `/vv` 读取结果 → 走候选上屏，**复用 sanhe 现有后处理链（简繁/字集/符号规整/用户词学习）**——语音文本养词库，这是 Win+H 与微信输入法都做不到的差异化。
2. **快速通道：推荐用户直接装 CapsWriter-Offline（MIT）**，sanhe 提供「rime 用户词库 → 热词文件」导出脚本（先例：[pofice/voice-input-method](https://github.com/pofice/voice-input-method) 的 `rime_ice2hotwords.py`）。

**里程碑**：
- **M1**：词库 → CapsWriter 热词导出脚本（~1 周，零风险先行验证需求）
- **M2**：`/vv` lua processor（触发/preedit 状态/取消/commit，参考 spdc-elm）+ SenseVoice sidecar（录音+VAD+识别+标点+ITN）
- **M3**：GPU 可选引擎（Qwen3-ASR）+ PyInstaller 打包安装器（注意本仓 PS1/打包规范）

**工作量**：基于 CapsWriter 改造路线约 **2–3 周单人**（sidecar 2–4 天、lua processor 2–4 天、热词脚本 1–2 天、规整+文档 1–2 天、打包 2–3 天）。

**风险**：低。组件全部 MIT/Apache；四个可抄的参考实现；最大不确定性（录音由谁触发：sidecar 键盘钩子 vs lua 内交互）两种做法均有先例。

## 6. 版本路线衔接

- v1.1.0（2026-11-19 发布）
- v1.2.0：词库瘦身与 Lua 链路优化（用基准工具量化收益）
- **v2.0：语音第三输入模式（本调研结论立项，当前维持调研阶段，未启动开发）**
