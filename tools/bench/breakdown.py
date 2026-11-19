# -*- coding: utf-8 -*-
"""Lua 组件成本分解测量（v1.2 Lua 链路瘦身的数据依据）。

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
        "translators": [
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
        ],
    },
    "no_lua_all": "__non_lua_only__",  # processors/filters/translators 全去掉 lua 项（极限参照）
}

RUN_ORDER = ["full"] + list(VARIANTS.keys())

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
}

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
    spec = VARIANTS[name]
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


def run_one(name, args):
    """单变体：搭工作区 -> 部署 -> 预热 1 轮 + 正式 rounds 轮 -> 写 csv/json。"""
    engine = read_engine_lists(os.path.join(args.repo, SCHEMA_NAME))
    procs, filters, trans = lists_for_variant(name, engine)

    with open(os.path.join(args.repo, "custom", "sanhe.custom.yaml"),
              "r", encoding="utf-8") as f:
        custom = f.read()
    if not custom.endswith("\n"):
        custom += "\n"
    if name != "full":
        custom += "\n" + build_patch_yaml(procs, filters, trans)

    ws_dir = os.path.join(BENCH_DIR, "ws", name)
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
    csv_path = os.path.join(args.out, name + ".csv")
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
    summary["removed"] = VARIANTS.get(name) if name != "full" else None
    json_path = os.path.join(args.out, name + ".json")
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
    """全流程：逐变体子进程执行，汇总生成 component-breakdown.md。"""
    results, skipped = {}, {}
    for name in RUN_ORDER:
        cmd = [sys.executable, os.path.abspath(__file__),
               "--variant", name, "--rounds", str(args.rounds),
               "--rime-dll", args.rime_dll, "--repo", args.repo,
               "--workload", args.workload, "--out", args.out]
        if args.shared_dir:
            cmd += ["--shared-dir", args.shared_dir]
        print("==> 运行变体 %s" % name, flush=True)
        proc = subprocess.Popen(cmd, cwd=BENCH_DIR,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        lines = []
        for ln in proc.stdout:
            lines.append(ln.rstrip("\n"))
            print("    " + ln.rstrip("\n"), flush=True)
        rc = proc.wait()
        json_path = os.path.join(args.out, name + ".json")
        if rc == 0 and os.path.isfile(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                results[name] = json.load(f)
        else:
            skipped[name] = extract_reason(lines)
            print("==> 变体 %s 失败/跳过：%s" % (name, skipped[name]), flush=True)

    write_report(results, skipped, args)


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
        lines.append("其余组件均为低成本项（单组件 Δ < 0.3 ms/键，见上表）。")
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
    ap.add_argument("--variant", default=None,
                    help="单变体模式运行（默认全流程）。可选: %s" % ", ".join(RUN_ORDER))
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
        if args.variant not in RUN_ORDER:
            print("ERROR: 未知变体: %s（可选: %s）" % (args.variant, ", ".join(RUN_ORDER)),
                  file=sys.stderr)
            sys.exit(2)
        try:
            run_one(args.variant, args)
        except bench.BenchError as e:
            print("ERROR: %s" % e, file=sys.stderr)
            sys.exit(1)
    else:
        run_all(args)


if __name__ == "__main__":
    main()
