# -*- coding: utf-8 -*-
"""Lua 组件成本分解测量（v1.2.0 Lua 链路瘦身的数据依据）。

方法：以 sanhe.schema.yaml 当前 engine 列表为基线，通过工作区
sanhe.custom.yaml 的 patch 整列表替换 engine/processors / engine/filters /
engine/translators，从原列表中删掉目标组件；逐变体部署 + 测量，
与 full 基线的每键 mean 差值 ≈ 该组件成本。

全流程（默认）：
    python breakdown.py
内部以子进程逐变体执行（每变体独立进程加载 rime.dll，避免同进程重复
初始化引擎的污染）：
    python breakdown.py --variant no_super_processor

产物（均在 gitignored 的 results/ 下）：
    results/<variant>.json / .csv   每变体原始数据
    results/component-breakdown.md  汇总报告（成本降序 + Top3 结论）
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BENCH_DIR)
import bench  # noqa: E402  复用 FFI 结构体 / load_rime / deploy / parse_workload / measure_round / summarize

SCHEMA_NAME = "sanhe.schema.yaml"

# trigger 型翻译器组（与 no_translators_misc 一致；组内二分定位用）
TRANSLATORS_MISC = [
    "lua_translator@*sanhe.shijian",
    "lua_translator@*sanhe.super_calculator",
    "lua_translator@*sanhe.random_tools",
    "lua_translator@*sanhe.input_statistics",
    "lua_translator@*sanhe.super_symbols",
    "lua_translator@*sanhe.version_display",
    "lua_translator@*sanhe.set_schema",
    "lua_translator@*sanhe.set_profile",
    "lua_translator@*sanhe.unicode_conversion*T",
    "lua_translator@*sanhe.number_conversion",
]

# 组内二分：每个变体只删其中一个翻译器（name -> {段: [删除项]}）
SINGLE_TRANSLATOR_VARIANTS = {
    "no_tr_shijian": {"translators": ["lua_translator@*sanhe.shijian"]},
    "no_tr_super_calculator": {"translators": ["lua_translator@*sanhe.super_calculator"]},
    "no_tr_random_tools": {"translators": ["lua_translator@*sanhe.random_tools"]},
    "no_tr_input_statistics": {"translators": ["lua_translator@*sanhe.input_statistics"]},
    "no_tr_super_symbols": {"translators": ["lua_translator@*sanhe.super_symbols"]},
    "no_tr_version_display": {"translators": ["lua_translator@*sanhe.version_display"]},
    "no_tr_set_schema": {"translators": ["lua_translator@*sanhe.set_schema"]},
    "no_tr_set_profile": {"translators": ["lua_translator@*sanhe.set_profile"]},
    "no_tr_unicode_conversion": {"translators": ["lua_translator@*sanhe.unicode_conversion*T"]},
    "no_tr_number_conversion": {"translators": ["lua_translator@*sanhe.number_conversion"]},
}

# 变体定义：name -> {段: [要从原列表删除的组件]}；no_lua_all 为特例（只留非 lua 项）
VARIANTS = {
    "no_super_processor": {
        "processors": ["lua_processor@*sanhe.super_processor"],
    },
    "no_super_comment": {
        "filters": ["lua_filter@*sanhe.super_comment_preedit"],
    },
    "no_super_replacer": {
        "filters": ["lua_filter@*sanhe.super_replacer"],
    },
    "no_super_filter": {
        "filters": ["lua_filter@*sanhe.super_filter"],
    },
    "no_auto_phrase": {
        "filters": ["lua_filter@*sanhe.auto_phrase"],
    },
    "no_super_english": {
        "processors": ["lua_processor@*sanhe.super_english*P"],
        "filters": ["lua_filter@*sanhe.super_english*F"],
    },
    "no_super_lookup": {
        "filters": ["lua_filter@*sanhe.super_lookup"],
    },
    "no_charset_filter": {
        "filters": ["lua_filter@*sanhe.charset_filter"],
    },
    "no_misc_processors": {
        "processors": [
            "lua_processor@*sanhe.unicode_conversion*P",
            "lua_processor@*sanhe.context_reorder*P",
            "lua_processor@*sanhe.partial_commit",
            "lua_processor@*sanhe.super_sequence*P",
            "lua_processor@*sanhe.super_tips",
            "lua_processor@*sanhe.key_binder",
        ],
    },
    "no_translators_misc": {
        "translators": TRANSLATORS_MISC,
    },
    "no_lua_all": "__non_lua_only__",  # processors/filters/translators 全去掉 lua 项（极限参照）
}

ORDERS = {
    "components": ["full"] + list(VARIANTS.keys()),
    "translators": ["full"] + list(SINGLE_TRANSLATOR_VARIANTS.keys()),
}

NOTES = {
    "full": "基线：sanhe.custom.yaml 模板原样（无任何 engine patch）",
    "no_super_processor": "声调回退/小键盘/以词定字/退格限制等失效；tone 组（nihao+8）行为异常属预期，健康断言只看 health 组",
    "no_super_comment": "候选注释（辅助码/错词提示/读音注释）消失",
    "no_super_replacer": "emoji 追加、简繁替换、中英互注、简码置顶等 replacer 规则失效",
    "no_super_filter": "字符集过滤与简繁权重继承失效",
    "no_auto_phrase": "无感造词/英文造词失效",
    "no_super_english": "英文按键捕获与中英混输格式化失效（*P + *F 同组）",
    "no_super_lookup": "输入中反查辅助筛选失效",
    "no_charset_filter": "字符集过滤失效",
    "no_misc_processors": "低频 trigger 处理器一组：unicode/上下文调频/局部提交/手动排序/super_tips/lua 按键绑定",
    "no_translators_misc": "trigger 型翻译器一组：时间/计算器/随机工具/输入统计/超级符号/版本/切方案/切档位/unicode/数字大写",
    "no_lua_all": "极限参照：整条 Lua 链（processors/filters/translators 中的 lua 项）全去掉，非 lua 项保留",
    "no_tr_shijian": "单删 shijian（农历/日期/节气/节日/时间/问候模板）",
    "no_tr_super_calculator": "单删 super_calculator（V 前缀超级计算器）",
    "no_tr_random_tools": "单删 random_tools（UUID/ULID/随机密码）",
    "no_tr_input_statistics": "单删 input_statistics（输入统计，含提交写库）",
    "no_tr_super_symbols": "单删 super_symbols（/sym /emoji 符号库）",
    "no_tr_version_display": "单删 version_display（/wx 版本显示）",
    "no_tr_set_schema": "单删 set_schema（/flypy 等切双拼方案）",
    "no_tr_set_profile": "单删 set_profile（/fast /balance /full 切性能档）",
    "no_tr_unicode_conversion": "单删 unicode_conversion*T（U 前缀 Unicode 查询）",
    "no_tr_number_conversion": "单删 number_conversion（R 前缀数字金额大写）",
}

ALL_VARIANTS = dict(VARIANTS)
ALL_VARIANTS.update(SINGLE_TRANSLATOR_VARIANTS)

SECTION_KEYS = ("processors", "translators", "filters")


def read_engine_lists(schema_path):
    """从 sanhe.schema.yaml 逐行解析 engine/processors|translators|filters 列表。"""
    lists = {k: [] for k in SECTION_KEYS}
    in_engine = False
    current = None
    with open(schema_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            if not line[0].isspace():
                if line.startswith("engine:"):
                    in_engine = True
                    current = None
                    continue
                if in_engine:
                    break  # 下一个顶层键，engine 块结束
                continue
            if not in_engine:
                continue
            m = re.match(r"^  (processors|segmentors|translators|filters):\s*$", line)
            if m:
                current = m.group(1)
                continue
            m = re.match(r"^    -\s+(\S+)", line)
            if m and current in lists:
                lists[current].append(m.group(1))
    for k in SECTION_KEYS:
        if not lists[k]:
            bench.die("从 %s 解析 engine/%s 为空，检查 schema 格式" % (schema_path, k))
    return lists


def lists_for_variant(name, engine):
    """返回 (processors, filters, translators) 删除目标组件后的副本。"""
    procs = list(engine["processors"])
    filters = list(engine["filters"])
    trans = list(engine["translators"])
    if name == "full":
        return procs, filters, trans
    spec = ALL_VARIANTS[name]
    if spec == "__non_lua_only__":
        keep = lambda xs: [x for x in xs if not x.startswith("lua_")]
        return keep(procs), keep(filters), keep(trans)
    targets = {"processors": procs, "filters": filters, "translators": trans}
    for section, removes in spec.items():
        for r in removes:
            if r not in targets[section]:
                bench.die("变体 %s 的目标组件不在 engine/%s 列表中: %s" % (name, section, r))
            targets[section].remove(r)
    return procs, filters, trans


def build_patch_yaml(procs, filters, trans):
    """手工生成 patch 片段：整列表替换 engine 三个段（2 空格缩进挂 patch: 下）。"""
    out = ["  engine/processors:"]
    out += ["    - " + x for x in procs]
    out.append("  engine/translators:")
    out += ["    - " + x for x in trans]
    out.append("  engine/filters:")
    out += ["    - " + x for x in filters]
    return "\n".join(out) + "\n"


def build_workspace(repo, ws_dir, custom_content):
    """复制仓库方案文件进工作区并写入 sanhe.custom.yaml（复用 bench.py 的搭建思路）。"""
    user_dir = os.path.join(ws_dir, "user")
    if os.path.isdir(ws_dir):
        shutil.rmtree(ws_dir)
    os.makedirs(user_dir)

    copied = []
    for name in os.listdir(repo):
        src = os.path.join(repo, name)
        dst = os.path.join(user_dir, name)
        if os.path.isfile(src) and (name.endswith(".yaml") or name.endswith(".txt")):
            shutil.copy2(src, dst)
            copied.append(name)
    for sub in ("dicts", "lua", "custom"):
        src = os.path.join(repo, sub)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(user_dir, sub))
            copied.append(sub + "/")
    if not copied:
        bench.die("工作区为空：%s 下没有找到任何方案文件" % repo)

    with open(os.path.join(user_dir, "sanhe.custom.yaml"), "w", encoding="utf-8") as f:
        f.write(custom_content)
    with open(os.path.join(user_dir, "default.custom.yaml"), "w", encoding="utf-8") as f:
        f.write(bench.DEFAULT_CUSTOM)
    return user_dir


def run_one(run_name, variant_name, args):
    """单变体：搭工作区 -> 部署 -> 预热 1 轮 + 正式 rounds 轮 -> 写 csv/json。

    run_name 决定工作区与产物文件名（允许 full@xxx 交错基线重复跑 full）；
    variant_name 决定 engine 里删哪些组件。
    """
    name = variant_name
    engine = read_engine_lists(os.path.join(args.repo, SCHEMA_NAME))
    procs, filters, trans = lists_for_variant(name, engine)

    with open(os.path.join(args.repo, "custom", "sanhe.custom.yaml"),
              "r", encoding="utf-8") as f:
        custom = f.read()
    if not custom.endswith("\n"):
        custom += "\n"
    if name != "full":
        custom += "\n" + build_patch_yaml(procs, filters, trans)

    ws_dir = os.path.join(BENCH_DIR, "ws", run_name)
    user_dir = build_workspace(args.repo, ws_dir, custom)
    print("[%s] 工作区: %s（processors %d -> %d, filters %d -> %d, translators %d -> %d）"
          % (name, user_dir,
             len(engine["processors"]), len(procs),
             len(engine["filters"]), len(filters),
             len(engine["translators"]), len(trans)), flush=True)

    rime, traits = bench.load_rime(args.rime_dll, args.shared_dir, user_dir)
    try:
        deploy_ms = bench.deploy(rime, traits)
        print("[%s] 部署完成: %.1f ms" % (name, deploy_ms), flush=True)

        built = os.path.join(user_dir, "build", "sanhe.schema.yaml")
        if not os.path.isfile(built):
            bench.die("部署失败（缺少 %s）。工作区日志摘要：\n%s"
                      % (built, bench.dump_logs(user_dir)))
        errors = bench.check_logs_for_errors(user_dir)
        if errors:
            bench.die("部署日志存在错误：\n" + "\n".join(errors) +
                      "\n\n工作区日志摘要：\n" + bench.dump_logs(user_dir))

        sid = rime.RimeCreateSession()
        if not sid:
            bench.die("RimeCreateSession 返回空会话。工作区日志摘要：\n%s"
                      % bench.dump_logs(user_dir))
        if not rime.RimeSelectSchema(sid, b"sanhe"):
            bench.die("RimeSelectSchema(sanhe) 失败。工作区日志摘要：\n%s"
                      % bench.dump_logs(user_dir))

        events = bench.parse_workload(args.workload)
        bench.EVENTS.clear()
        bench.WARMUP.clear()
        bench.measure_round(rime, sid, events, record=False)
        rime.RimeProcessKey(sid, bench.XK_ESCAPE, 0)

        import time as _time
        t_start = _time.perf_counter()
        for _ in range(args.rounds):
            bench.measure_round(rime, sid, events, record=True)
        wall_ms = (_time.perf_counter() - t_start) * 1000.0

        # 健康断言：health 组每个 type 事件后必须有候选（与 bench.py 一致）。
        # 注意：只看 health 组——tone 组在 no_super_processor 下行为异常属预期。
        bad = [e for e in bench.EVENTS if e["tag"] == "health" and e["kind"] == "type"
               and e["num_candidates"] <= 0]
        if bad:
            sample = "\n".join(str(e) for e in bad[:5])
            bench.die("健康断言失败：type nihao 后 num_candidates=0（lua 失效或部署异常？）。\n%s\n"
                      "工作区日志摘要：\n%s" % (sample, bench.dump_logs(user_dir)))
    finally:
        rime.RimeFinalize()

    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, run_name + ".csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        import csv as _csv
        w = _csv.writer(f)
        w.writerow(["tag", "kind", "key", "t1_ms", "t2_ms", "total_ms",
                    "num_candidates", "preedit", "commit"])
        for e in bench.EVENTS:
            w.writerow([e["tag"], e["kind"], e["key"], e["t1_ms"], e["t2_ms"],
                        e["total_ms"], e["num_candidates"], e["preedit"], e["commit"]])

    summary = bench.summarize(bench.EVENTS, deploy_ms, wall_ms, args.rounds)
    summary["variant"] = name
    summary["run"] = run_name
    summary["removed"] = ALL_VARIANTS.get(name) if name != "full" else None
    json_path = os.path.join(args.out, run_name + ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("[%s] 完成: 总体 mean=%.3f ms  p95=%.3f ms  deploy=%.1f ms"
          % (name, summary["overall"]["mean_ms"],
             summary["overall"]["p95_ms"], deploy_ms), flush=True)


def extract_reason(lines):
    """从子进程输出尾部提取失败原因。"""
    err = [ln for ln in lines if ln.startswith("ERROR:")]
    tail = lines[-6:] if len(lines) > 6 else lines
    return "\n".join(err[-3:] + ([""] if err else []) + tail).strip() or "未知错误"


def run_all(args):
    """全流程：逐变体子进程执行，按模式汇总生成报告。

    translators 模式采用交错基线协议（对抗运行间时间漂移）：
    实测发现单遍顺序测量受机器负载漂移污染（部署耗时 20.5s→27.5s 爬升，
    靠后的变体整体偏慢 ~1ms，Δ 之和与组删严重矛盾），故按
    full, v1, full, v2, full, ... 交替执行，每个变体取前后相邻两个
    full 基线的均值作为自己的基准。组删参照 no_translators_misc 同样穿插重测。
    """
    results, skipped = {}, {}
    if args.mode == "translators":
        seq = [("full@start", "full")]
        for v in ORDERS["translators"][1:]:
            seq.append((v, v))
            seq.append(("full@" + v, "full"))
        seq.append(("no_translators_misc", "no_translators_misc"))
        seq.append(("full@no_translators_misc", "full"))
    else:
        seq = [(n, n) for n in ORDERS["components"]]

    for run_name, variant in seq:
        cmd = [sys.executable, os.path.abspath(__file__),
               "--variant", variant, "--run-name", run_name,
               "--rounds", str(args.rounds),
               "--rime-dll", args.rime_dll, "--repo", args.repo,
               "--workload", args.workload, "--out", args.out]
        if args.shared_dir:
            cmd += ["--shared-dir", args.shared_dir]
        print("==> 运行 %s（变体 %s）" % (run_name, variant), flush=True)
        proc = subprocess.Popen(cmd, cwd=BENCH_DIR,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        lines = []
        for ln in proc.stdout:
            lines.append(ln.rstrip("\n"))
            print("    " + ln.rstrip("\n"), flush=True)
        rc = proc.wait()
        json_path = os.path.join(args.out, run_name + ".json")
        if rc == 0 and os.path.isfile(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                results[run_name] = json.load(f)
        else:
            skipped[run_name] = extract_reason(lines)
            print("==> %s 失败/跳过：%s" % (run_name, skipped[run_name]), flush=True)

    if args.mode == "translators":
        # 计算每个变体的相邻基线差值：Δ = mean(前后 full) − 变体 mean
        rows = []          # (delta, name, variant_mean, adj_base_mean)
        group_row = None   # no_translators_misc 的 (delta, mean, adj_base)
        for i, (run_name, variant) in enumerate(seq):
            if variant == "full" or run_name in skipped:
                continue
            adj = []
            for j in (i - 1, i + 1):
                if 0 <= j < len(seq) and seq[j][1] == "full" \
                        and seq[j][0] in results:
                    adj.append(results[seq[j][0]]["overall"]["mean_ms"])
            if not adj or run_name not in results:
                continue
            vmean = results[run_name]["overall"]["mean_ms"]
            base = sum(adj) / len(adj)
            row = (base - vmean, variant, vmean, base)
            if variant == "no_translators_misc":
                group_row = row
            else:
                rows.append(row)
        rows.sort(key=lambda r: r[0], reverse=True)
        write_translator_report(rows, group_row, results, skipped, args)
    else:
        flat = {}
        for run_name, s in results.items():
            if s.get("variant") not in flat:
                flat[s["variant"]] = s
        # components 模式每个变体只跑一次，skipped 的键就是变体名，直接沿用
        flat_skipped = dict(skipped)
        write_report(flat, flat_skipped, args)


def write_translator_report(rows, group_row, results, skipped, args):
    """trigger 型翻译器组内二分报告（交错基线协议版）。

    rows: [(delta, variant, variant_mean, adj_base_mean), ...] 已按 delta 降序；
    group_row: no_translators_misc 的同格式行（本轮穿插重测）。
    """
    md_path = os.path.join(args.out, "translator-bisect.md")
    lines = []
    lines.append("# trigger 型翻译器组内二分（librime 实测，交错基线协议）")
    lines.append("")
    group_delta = group_row[0] if group_row else None
    lines.append("- 协议修正：首轮单遍顺序测量受机器时间漂移污染（部署耗时 20.5s→27.5s 爬升，"
                 "靠后变体整体偏慢，单删 Δ 之和为负、与组删矛盾，已作废）。本轮采用"
                 "**交错基线**：full, v1, full, v2, full, ... 交替执行，"
                 "每个变体 Δ = 前后相邻 full 基线均值 − 变体 mean。")
    lines.append("- 组删参照 no_translators_misc 在本轮同协议下穿插重测，"
                 "实测 Δ = %s ms/键。" % ("%+.3f" % group_delta if group_delta is not None else "N/A"))
    lines.append("- 方法与健康断言同 component-breakdown；每变体预热 1 轮 + 正式 %d 轮；引擎: `%s`。"
                 % (args.rounds, args.rime_dll))
    lines.append("")

    if rows:
        base = rows[0][3]  # 展示用：取最高 Δ 变体的相邻基线均值（各变体基线略有漂移）
        fulls = {k: s for k, s in results.items() if s.get("variant") == "full"}
        lines.append("## 交错基线观测")
        lines.append("")
        lines.append("共 %d 次 full 基线穿插（漂移监测）：" % len(fulls))
        lines.append("")
        lines.append("| full 运行 | 每键 mean (ms) |")
        lines.append("|---|---|")
        for k in sorted(fulls):
            lines.append("| %s | %.3f |" % (k, fulls[k]["overall"]["mean_ms"]))
        lines.append("")

        lines.append("## 单删结果（按 Δ 降序，Δ = 相邻 full 基线均值 − 变体 mean）")
        lines.append("")
        lines.append("| # | 单删变体 | 变体 mean (ms) | 相邻基线 (ms) | Δ (ms) | Δ 占基线 | 说明 |")
        lines.append("|---|---|---|---|---|---|---|")
        for i, (diff, name, mean, adj_base) in enumerate(rows, 1):
            lines.append("| %d | %s | %.3f | %.3f | %+.3f | %+.1f%% | %s |"
                         % (i, name, mean, adj_base, diff, diff / adj_base * 100.0, NOTES[name]))
        if group_row:
            gd, gname, gmean, gbase = group_row
            lines.append("| 组 | %s | %.3f | %.3f | %+.3f | %+.1f%% | %s |"
                         % (gname, gmean, gbase, gd, gd / gbase * 100.0, NOTES[gname]))
        lines.append("")
        lines.append("- 校验：单删 Δ 之和 = %+.3f ms/键，组删 Δ = %+.3f ms/键（应基本吻合）。"
                     % (sum(r[0] for r in rows), group_delta if group_delta is not None else float("nan")))
        lines.append("")

        # 元凶判定阈值：单删 Δ > 0.5 ms 视为明显元凶
        # rest_rows/rest 在分支前统一计算，保证「无元凶」分支后文引用不崩溃
        TH = 0.5
        culprits = [r for r in rows if r[0] > TH]
        rest_rows = [r for r in rows if r[0] <= TH]
        rest = sum(r[0] for r in rest_rows)
        top = rows[0]
        lines.append("## 结论")
        lines.append("")
        if culprits:
            lines.append("**Q1 答案：混合情形——%d 个突出元凶 + 其余入口成本累加。** "
                         "单删 Δ > %.1f ms 的有 %d 个：" % (
                             len(culprits), TH, len(culprits)))
            lines.append("")
            for d, name, mean, adj_base in culprits:
                lines.append("- **%s**：%+.3f ms/键（%.1f%%）" % (name, d, d / adj_base * 100.0))
            if rest_rows:
                lines.append("")
                lines.append("其余 %d 个翻译器合计 %+.3f ms/键（平均 %.3f ms/个，"
                             "spread %.3f ms，均匀分布无突出项）——这部分是"
                             "**每键固定入口成本 × 翻译器数量**的累加；"
                             "组删 Δ（%+.3f）≈ 元凶 %.3f + 其余 %.3f（差 %.3f 为交互/残余噪声）。"
                             % (len(rest_rows), rest,
                                rest / len(rest_rows),
                                (rest_rows[0][0] - rest_rows[-1][0]),
                                group_delta if group_delta is not None else 0.0,
                                sum(r[0] for r in culprits), rest,
                                abs((group_delta or 0.0) - sum(r[0] for r in rows))))
            lines.append("")
            lines.append("元凶的机制定性（伪 trigger/每键常驻 vs 纯入口成本）"
                         "以 devlog 本轮记录为准，报告只呈现数据。")
        else:
            avg = sum(r[0] for r in rows) / len(rows)
            spread = rows[0][0] - rows[-1][0]
            lines.append("**Q1 答案：无单个元凶——是 %d 个翻译器累加的每键固定入口成本。**"
                         % len(rows))
            lines.append("")
            lines.append("单删 Δ 最大仅 %+.3f ms（%s），最小 %+.3f ms，"
                         "%d 个单删之和 %+.3f ms ≈ 组删 Δ %+.3f ms；"
                         "平均每个翻译器入口成本 ≈ %.3f ms/键（spread %.3f ms，"
                         "分布均匀，无突出项）。"
                         % (top[0], top[1], rows[-1][0], len(rows),
                            sum(r[0] for r in rows),
                            group_delta if group_delta is not None else 0.0,
                            avg, spread))
        lines.append("")
        lines.append("## 对 v1.2.0 的建议（Q2）")
        lines.append("")
        if culprits:
            lines.append("**优先真 trigger 化（本轮实测元凶，收益最大）**：")
            for d, name, mean, adj_base in culprits:
                short = name.replace("no_tr_", "")
                if short == "input_statistics":
                    lines.append("- **%s**：单删已省 %.2f ms/键。它没有输入前缀可隔离，"
                                 "元凶是每键/每次提交都执行的统计逻辑（含写库）——"
                                 "应改为仅在触发 `/tj` 等查询时统计读取 + 提交写库限流/批量落盘。"
                                 % (short, d))
                else:
                    lines.append("- **%s**：单删已省 %.2f ms/键，用 recognizer tag 隔离后"
                                 "常规输入完全不进 Lua，可全额回收。"
                                 % (short, d))
            lines.append("")
        if rest_rows:
            n_rest = len(rest_rows)
            lines.append("**其余 %d 个合并为 hub（入口成本 × 数量问题，合并即可解决）**："
                         "将其余低频翻译器合并为 1 个 `lua_translator@*sanhe.hub_translator`，"
                         "内部按输入前缀分发——平均每个入口 ≈%.2f ms，%d 合 1 后入口开销降为 1/%d，"
                         "预计可回收 ~%.1f ms/键，功能与触发方式不变。"
                         % (n_rest, rest / n_rest, n_rest, n_rest,
                            rest * (n_rest - 1) / n_rest))
        lines.append("")
        lines.append("**合并 hub + 前缀分发即可（真 trigger 化性价比一般，模式现成时可选做）**：")
        lines.append("- `super_calculator`（V 前缀，`recognizer/patterns/calculator: ^V.*$` 已存在）")
        lines.append("- `number_conversion`（R 前缀，pattern `^number` 已存在）")
        lines.append("- `unicode_conversion`（U 前缀，pattern 已存在）")
        lines.append("- `super_symbols`（/sym /emoji，pattern 已存在）")
        lines.append("- `shijian`（o 引导 / 斜杠触发，key_binder 已配 shijian_keys）")
        lines.append("  引擎只对匹配 tag 的段落调用对应翻译器，常规拼音输入完全绕过 Lua 入口。")
        lines.append("")
        lines.append("**合并进 hub 即可保持现状**：version_display（/wx）、set_schema（/zrm 等）、"
                     "set_profile（/fast 等）、random_tools（/uuid 等）"
                     "——低频纯展示型，合并到 hub 内部分发后无额外成本，无需 trigger 化。"
                     "（super_symbols、input_statistics 见上方优先项。）")
        lines.append("")
    else:
        lines.append("**无成功变体，无法计算差值。**")
        lines.append("")

    if skipped:
        lines.append("## 跳过的运行")
        lines.append("")
        for name, reason in skipped.items():
            lines.append("- **%s**：%s" % (name, reason.replace("\n", "；")))
        lines.append("")

    lines.append("## 备注")
    lines.append("")
    lines.append("- 原始逐键数据：`<run_name>.csv`；机器可读汇总：`<run_name>.json`"
                 "（full@* 为交错基线）。")
    lines.append("- 差值为单次测量结果，绝对值 < 0.3 ms 的项存在残余噪声；判定以 0.5 ms 阈值为准。")
    lines.append("")

    os.makedirs(args.out, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("汇总已生成: %s" % md_path, flush=True)


def write_report(results, skipped, args):
    md_path = os.path.join(args.out, "component-breakdown.md")
    lines = []
    lines.append("# Lua 组件成本分解（librime 实测）")
    lines.append("")
    lines.append("- 方法：full 基线上通过 custom patch 整列表替换 engine/processors|filters|translators，")
    lines.append("  删掉目标组件后部署测量；**Δ = full mean − 变体 mean ≈ 该组件成本**（正数=去掉后变快）。")
    lines.append("- 每变体预热 1 轮 + 正式 %d 轮；t_total = RimeProcessKey + RimeGetContext。" % args.rounds)
    lines.append("- 引擎: `%s`；workload: `tools/bench/workload.txt`" % args.rime_dll)
    lines.append("- 健康断言：health 组（type nihao）每个按键后 num_candidates>0；tone 组在")
    lines.append("  no_super_processor 下行为异常不计失败。uniquifier 与全部非 lua 组件保留。")
    lines.append("")

    if "full" not in results:
        lines.append("**full 基线未成功，无法计算差值。**")
        lines.append("")
    else:
        base = results["full"]["overall"]["mean_ms"]
        rows = []
        for name, s in results.items():
            if name == "full":
                continue
            mean = s["overall"]["mean_ms"]
            diff = base - mean
            rows.append((diff, name, mean))
        rows.sort(key=lambda r: r[0], reverse=True)

        lines.append("## 结果（按 Δ 成本降序）")
        lines.append("")
        lines.append("| # | 变体 | 每键 mean (ms) | Δ (ms) | Δ 占 full | 说明 |")
        lines.append("|---|---|---|---|---|---|")
        lines.append("| 0 | full | %.3f | — | — | %s |"
                     % (base, NOTES["full"]))
        for i, (diff, name, mean) in enumerate(rows, 1):
            lines.append("| %d | %s | %.3f | %+.3f | %+.1f%% | %s |"
                         % (i, name, mean, diff, diff / base * 100.0, NOTES[name]))
        lines.append("")

        # no_lua_all 是极限参照（与其余变体有重叠，不能计入组件合计），
        # 最贵的 3 个组件从单组件/单组变体中取。
        comp_rows = [r for r in rows if r[1] != "no_lua_all"]
        top = comp_rows[:3]
        total = sum(d for d, _, _ in top)
        lines.append("## 结论")
        lines.append("")
        lines.append("最贵的 3 个组件/组件组（合计 Δ = %+.3f ms/键，占 full 基线 %.1f%%）："
                     % (total, total / base * 100.0))
        lines.append("")
        for i, (d, name, mean) in enumerate(top, 1):
            lines.append("%d. **%s**：%+.3f ms/键（%.1f%%）" % (i, name, d, d / base * 100.0))
        lines.append("")
        rest_comp = comp_rows[3:]
        if rest_comp:
            lines.append("其余 %d 个组件 Δ 范围 %+.3f～%+.3f ms/键（见上表）——"
                         "接近单次测量的运行间噪声量级（±0.1~0.3 ms），相互排序不宜过度解读。"
                         % (len(rest_comp), rest_comp[0][0], rest_comp[-1][0]))
        lua_all = results.get("no_lua_all")
        if lua_all:
            d = base - lua_all["overall"]["mean_ms"]
            lines.append("")
            lines.append("极限参照：no_lua_all（整条 Lua 链全去掉）节省 %+.3f ms/键，"
                         "占 full 基线 %.1f%%——即 Lua 组件链的合计成本上限。"
                         "注意逐项相加（%+.3f ms）比它多 %.2f ms：说明组件间存在非线性交互"
                         "（组件会改变候选列表长度/类型，影响下游组件每键工作量），"
                         "各组件成本不宜简单线性外推，组内定位需进一步二分测量。"
                         % (d, d / base * 100.0, sum(r[0] for r in comp_rows),
                            sum(r[0] for r in comp_rows) - d))
        lines.append("")

    if skipped:
        lines.append("## 跳过的变体")
        lines.append("")
        for name, reason in skipped.items():
            lines.append("- **%s**：%s" % (name, reason.replace("\n", "；")))
        lines.append("")

    lines.append("## 备注")
    lines.append("")
    lines.append("- 原始逐键数据：`<variant>.csv`；机器可读汇总：`<variant>.json`。")
    lines.append("- 单变体耗时含部署约 20s+；差值为单次测量结果，存在运行间噪声（±0.1~0.3 ms 量级）。")
    lines.append("- 某些变体功能退化（见说明列）是预期现象，不影响延迟测量有效性。")
    lines.append("")

    os.makedirs(args.out, exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("汇总已生成: %s" % md_path, flush=True)


def main():
    ap = argparse.ArgumentParser(description="Lua 组件成本分解测量")
    ap.add_argument("--mode", choices=["components", "translators"],
                    default="components",
                    help="components：组件分解（默认，component-breakdown.md）；"
                         "translators：trigger 翻译器组内二分（translator-bisect.md）")
    ap.add_argument("--variant", default=None,
                    help="单变体模式运行（默认全流程）。components 模式可选: %s；"
                         "translators 模式可选 no_tr_* 单删变体"
                         % ", ".join(ORDERS["components"]))
    ap.add_argument("--run-name", default=None,
                    help="单变体模式下工作区/产物命名（默认同 --variant；"
                         "全流程用 full@xxx 形式交错基线）")
    ap.add_argument("--rime-dll",
                    default=r"D:\Software\Rime-nightly\weasel-0.17.4\rime.dll")
    ap.add_argument("--shared-dir", default=None,
                    help="小狼毫 data 目录（默认自动探测 <rime.dll目录>/data）")
    ap.add_argument("--repo", default=os.path.abspath(os.path.join(BENCH_DIR, "..", "..")))
    ap.add_argument("--out", default=os.path.join(BENCH_DIR, "results"))
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--workload", default=os.path.join(BENCH_DIR, "workload.txt"))
    args = ap.parse_args()

    if args.shared_dir is None:
        guess = os.path.join(os.path.dirname(os.path.abspath(args.rime_dll)), "data")
        args.shared_dir = guess if os.path.isdir(guess) else None
    if not args.shared_dir or not os.path.isdir(args.shared_dir):
        print("ERROR: 找不到 shared_data_dir（小狼毫 data 目录），请用 --shared-dir 指定",
              file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.rime_dll):
        print("ERROR: 找不到 rime.dll: %s" % args.rime_dll, file=sys.stderr)
        sys.exit(1)

    if args.variant:
        known = set(ORDERS["components"]) | set(ORDERS["translators"])
        if args.variant not in known:
            print("ERROR: 未知变体: %s（可选: %s）" % (args.variant, ", ".join(sorted(known))),
                  file=sys.stderr)
            sys.exit(2)
        try:
            run_one(args.run_name or args.variant, args.variant, args)
        except bench.BenchError as e:
            print("ERROR: %s" % e, file=sys.stderr)
            sys.exit(1)
    else:
        run_all(args)


if __name__ == "__main__":
    main()
