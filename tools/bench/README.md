# 三合输入法按键延迟基准测试工具（tools/bench）

用**真实的 librime 引擎**（小狼毫自带 `rime.dll`）测量三合/万象方案在不同性能档位下的
**每次按键处理延迟**，用于量化「完整配置 vs 性能档位配置」的优化效果。

## 测的是什么

每个按键事件分两段计时：

- **t1**：`RimeProcessKey()` 耗时（引擎处理按键：处理器链、翻译、候选计算都在此完成，实测占绝对大头）
- **t2**：`RimeGetContext()` 耗时（读取上下文快照，实测仅 0.02～0.04 ms）

合计 t_total = t1 + t2 视为该键的端到端延迟。另单独测量**部署（编译词库）耗时**。

三个变体（通过在工作区 `sanhe.custom.yaml` 追加性能档位 patch 实现）：

| 变体 | 配置 |
|---|---|
| `full` | `custom/sanhe.custom.yaml` 模板原样（全功能） |
| `balance` | 追加 `translator/spelling_hints: 15` |
| `fast` | 追加主/英/混三个 translator 的 `enable_completion: false` + `spelling_hints: 6` |

## 用法

```powershell
# 依次跑 full / balance / fast 三个变体并生成汇总
python tools\bench\run_all.py

# 单变体（调试用）
python tools\bench\bench.py --variant full
python tools\bench\bench.py --variant fast --rounds 5

# 参数
#   --rime-dll     rime.dll 路径（默认 D:\Software\Rime-nightly\weasel-0.17.4\rime.dll）
#   --shared-dir   小狼毫 data 目录（默认自动探测 <rime.dll目录>\data）
#   --repo         方案仓库根（默认本工具的 ../../）
#   --out          结果目录（默认 tools/bench/results）
#   --rounds       正式测量轮数（默认 3；全部正式轮次前先跑 1 轮预热不计分）
```

输出：

- `results/<variant>.csv` —— 逐键事件明细（含 preedit/commit 供人工检查）
- `results/<variant>.json` —— 每分组 mean/p50/p95/max + 部署/总耗时
- `results/summary.md` —— 三变体对比表 + 相对 full 的百分比变化

## 工作机制

1. 在 `ws/<variant>/user/` 搭建独立用户目录：复制仓库顶层 `*.yaml`/`*.txt` 与
   `dicts/`、`lua/`、`custom/` 整目录，写入档位 `sanhe.custom.yaml` 和精简
   `default.custom.yaml`（schema_list 只留 sanhe，避免五笔也部署拖慢编译）。
2. ctypes 加载 `rime.dll`（`modules` 为 NULL 结尾字符串数组 `{"default","lua"}`，
   **不含 lua 则全部 lua 组件失效**；`min_log_level=2` 即 ERROR 及以上），`RimeSetup → RimeInitialize → RimeStartMaintenance(1)
   → RimeJoinMaintenanceThread` 完成部署。
3. `RimeCreateSession` + `RimeSelectSchema("sanhe")` 后按 `workload.txt` 逐键测量。
4. 健康断言：`health` 分组 type 后 `menu.num_candidates` 必须 >0，否则扫描工作区
   rime 日志并显式报错退出（不允许输出假数据）。

`ws/` 与 `results/` 已被 .gitignore 忽略，可随时删除重来。

## 局限性

- **无渲染开销**：未模拟前端 UI（高亮、着色、注释排版等），数值偏理想；不同变体间
  的相对差距仍有参考价值。
- 按键通过 API 直接注入，绕过了键盘消息管线，测的是引擎纯计算延迟。
- 负载为固定脚本（workload.txt），与真实打字的键序分布不同；`t2` 取整份上下文，
  键长按逐词组平均会略高估日常手感。
- 每轮测量使用同一会话（不清用户词典），自动调频（`enable_user_dict`）带来的
  逐轮漂移未做隔离；预热一轮 + 多轮取均值可大部分抵消。
- 负载中的反查/声调筛选等输入依赖方案 lua 组件真实生效，健康断言只覆盖
  `health` 组，其他分组请在 CSV 里人工核对 preedit/commit 是否符合预期。
- **五笔召唤（/wvbg）不在负载中**：该功能依赖 wubi86 词表，而工具为控制部署耗时将
  schema_list 精简为只部署 sanhe（default.custom.yaml），wubi86.table.bin 不存在时
  super_wubi 无候选（会话日志里的 wubi86 加载错误即源于此，属预期现象）。

## librime FFI 实现要点（踩坑记录）

以 nightly rime.dll（librime 1.11，2025-02 构建）实测为准：

- `RimeTraits.modules` 是 **`const char**`（NULL 结尾的字符串数组），不是逗号分隔
  字符串**。传 `"default,lua"` 会在 `RimeInitialize` 直接访问违例崩溃；正确做法是
  `(c_char_p * 3)(b"default", b"lua", None)`，且数组对象必须保活（ctypes 结构体
  只存指针，临时数组被 GC 后变悬垂指针，症状是部署随机空跑）。
- ctypes 对结构体不存在的字段名赋值会**静默创建 Python 属性**而不报错——写错字段名
  时引擎拿到 NULL 指针，部署空跑且日志为空。务必核对 `_fields_` 名字。
- librime 1.11 的 `RimeComposition` 只有 5 个字段（length/cursor_pos/sel_start/
  sel_end/preedit），**没有** commit_text_preview/specialize（旧教程里的布局），
  commit_text_preview 在 `RimeContext` 层。多声明字段会把 menu 偏移推错，
  表现为 `num_candidates` 恒 0。`Bool` 是 `int`。
- `RimeTraits` 第二个字段官方名是 `user_data_dir`（部分旧文档写作 user_dir）。

## 文件

```
tools/bench/
├── bench.py       # 主程序（单变体）
├── run_all.py     # 三变体串联 + summary.md 汇总
├── workload.txt   # 按键工作负载
├── README.md
├── results/       # 输出（gitignore）
└── ws/            # 私有工作区（gitignore），首次运行自动创建
```
