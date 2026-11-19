# -*- coding: utf-8 -*-
"""依次以子进程跑 full / balance / fast 三个变体，汇总生成 results/summary.md。"""
import argparse
import json
import os
import subprocess
import sys

VARIANTS = ["full", "balance", "fast"]


def fmt(v, digits=3):
    return ("%.*f" % (digits, v)) if isinstance(v, float) else str(v)


def pct(new, base):
    if not base:
        return "-"
    return "%+.1f%%" % ((new - base) / base * 100.0)


def main():
    ap = argparse.ArgumentParser(description="三合基准：跑全部变体并汇总")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--rime-dll",
                    default=r"D:\Software\Rime-nightly\weasel-0.17.4\rime.dll")
    ap.add_argument("--shared-dir", default=None)
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    bench_dir = os.path.dirname(os.path.abspath(__file__))
    results = {}
    for v in VARIANTS:
        cmd = [args.python, os.path.join(bench_dir, "bench.py"),
               "--variant", v, "--rounds", str(args.rounds),
               "--rime-dll", args.rime_dll]
        if args.shared_dir:
            cmd += ["--shared-dir", args.shared_dir]
        print("==> 运行变体 %s" % v, flush=True)
        r = subprocess.run(cmd, cwd=bench_dir)
        if r.returncode != 0:
            print("变体 %s 失败（退出码 %d），中止汇总" % (v, r.returncode))
            sys.exit(1)
        with open(os.path.join(bench_dir, "results", v + ".json"),
                  "r", encoding="utf-8") as f:
            results[v] = json.load(f)

    os.makedirs(os.path.join(bench_dir, "results"), exist_ok=True)
    md_path = os.path.join(bench_dir, "results", "summary.md")
    base = results["full"]
    lines = []
    lines.append("# 三合输入法按键延迟基准（librime 实测）")
    lines.append("")
    lines.append("- 引擎: `%s`" % args.rime_dll)
    lines.append("- 每变体正式测量 %d 轮（先 1 轮预热，不计分）" % args.rounds)
    lines.append("- t_total = RimeProcessKey + RimeGetContext（前者占绝对大头，后者为读取上下文快照）")
    lines.append("")
    lines.append("## 变体 × 指标（总体，全部按键事件）")
    lines.append("")
    header = "| 指标 | full | balance | fast | balance vs full | fast vs full |"
    lines.append(header)
    lines.append("|---|---|---|---|---|---|")
    metrics = [
        ("每键 mean (ms)", lambda s: s["overall"]["mean_ms"]),
        ("每键 p50 (ms)", lambda s: s["overall"]["p50_ms"]),
        ("每键 p95 (ms)", lambda s: s["overall"]["p95_ms"]),
        ("每键 max (ms)", lambda s: s["overall"]["max_ms"]),
        ("全部按键合计 (ms)", lambda s: s["overall"]["sum_ms"]),
        ("部署耗时 (ms)", lambda s: s["deploy_ms"]),
        ("测量墙钟时间 (ms)", lambda s: s["wall_ms"]),
    ]
    for name, fn in metrics:
        f_, b_, s_ = fn(base), fn(results["balance"]), fn(results["fast"])
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            name, fmt(f_), fmt(b_), fmt(s_), pct(b_, f_), pct(s_, f_)))
    lines.append("")

    # 分组明细
    all_tags = []
    for v in VARIANTS:
        for tag in results[v]["tags"]:
            if tag not in all_tags:
                all_tags.append(tag)
    lines.append("## 分组明细（每键 mean / p95，ms）")
    lines.append("")
    lines.append("| 分组 | full mean | balance mean | fast mean | full p95 | balance p95 | fast p95 |")
    lines.append("|---|---|---|---|---|---|---|")
    for tag in all_tags:
        row = [tag]
        for v in VARIANTS:
            t = results[v]["tags"].get(tag)
            row.append(fmt(t["mean_ms"]) if t else "-")
        for v in VARIANTS:
            t = results[v]["tags"].get(tag)
            row.append(fmt(t["p95_ms"]) if t else "-")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## 说明")
    lines.append("")
    lines.append("- full：custom/sanhe.custom.yaml 模板原样（注释全开，spelling_hints=30）")
    lines.append("- balance：追加 `translator/spelling_hints: 15`")
    lines.append("- fast：追加 `enable_completion: false`（主/英/混）+ `spelling_hints: 6`")
    lines.append("- 原始逐键数据：`<variant>.csv`；机器可读汇总：`<variant>.json`")
    lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("汇总已生成: %s" % md_path)


if __name__ == "__main__":
    main()
