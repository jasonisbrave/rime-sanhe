# -*- coding: utf-8 -*-
"""三合输入法按键延迟基准测试（单变体）。

用真实的 librime 引擎（小狼毫自带 rime.dll）测量每次按键的处理延迟：
t1 = RimeProcessKey 耗时（处理器链/翻译/候选计算均在此完成），t2 = RimeGetContext 耗时（读取上下文快照）。

用法：
    python bench.py --variant full [--rounds 3]
                    [--rime-dll D:\\Software\\Rime-nightly\\weasel-0.17.4\\rime.dll]
                    [--shared-dir <小狼毫 data 目录>]
                    [--repo D:\\Code\\Projects\\rime-sanhe]
                    [--out results]
"""
import argparse
import csv
import ctypes
import json
import os
import shutil
import statistics
import sys
import time
from ctypes import (CDLL, POINTER, Structure, c_char_p, c_int, c_size_t,
                    c_ubyte, c_void_p)

XK_RETURN = 0xFF0D
XK_ESCAPE = 0xFF1B
XK_BACKSPACE = 0xFF08

PERF_BLOCKS = {
    # 标记注释顶格、键值缩进 2 空格——与 lua/sanhe/set_profile.lua 写入的格式完全一致
    "balance": (
        "# >>> 性能档位（/fast /balance /full 自动维护，手动修改会被覆盖）>>>\n"
        "  translator/spelling_hints: 15\n"
        "# <<< 性能档位 <<<\n"
    ),
    "fast": (
        "# >>> 性能档位（/fast /balance /full 自动维护，手动修改会被覆盖）>>>\n"
        "  translator/enable_completion: false\n"
        "  translator/spelling_hints: 6\n"
        "  sanhe_english/enable_completion: false\n"
        "  sanhe_mixedcode/enable_completion: false\n"
        "# <<< 性能档位 <<<\n"
    ),
}

DEFAULT_CUSTOM = "patch:\n  schema_list:\n    - schema: sanhe\n"


class RimeTraits(Structure):
    _fields_ = [
        ("data_size", c_int),
        ("shared_data_dir", c_char_p),
        ("user_data_dir", c_char_p),  # 旧文档常写作 user_dir，同一字段
        ("distribution_name", c_char_p),
        ("distribution_code_name", c_char_p),
        ("distribution_version", c_char_p),
        ("app_name", c_char_p),
        ("modules", POINTER(c_char_p)),
        ("min_log_level", c_int),
        ("log_dir", c_char_p),
        ("prebuilt_data_dir", c_char_p),
        ("staging_dir", c_char_p),
    ]


class RimeCandidate(Structure):
    _fields_ = [("text", c_char_p), ("comment", c_char_p), ("reserved", c_void_p)]


class RimeComposition(Structure):
    # librime 1.11 rime_api.h：只有 5 个字段（无 commit_text_preview/specialize，
    # 后者已移到 RimeContext 层）——多加字段会把 menu 偏移推错，num_candidates 恒 0
    _fields_ = [
        ("length", c_int),
        ("cursor_pos", c_int),
        ("sel_start", c_int),
        ("sel_end", c_int),
        ("preedit", c_char_p),
    ]


class RimeMenu(Structure):
    _fields_ = [
        ("page_size", c_int),
        ("page_no", c_int),
        ("is_last_page", c_int),  # librime Bool = int
        ("highlighted_candidate_index", c_int),
        ("num_candidates", c_int),
        ("candidates", POINTER(RimeCandidate)),
        ("select_keys", c_char_p),
    ]


class RimeContext(Structure):
    _fields_ = [
        ("data_size", c_int),
        ("composition", RimeComposition),
        ("menu", RimeMenu),
        ("commit_text_preview", c_char_p),
        ("select_labels", POINTER(c_char_p)),
    ]


class RimeCommit(Structure):
    _fields_ = [("data_size", c_int), ("text", c_char_p)]


class BenchError(Exception):
    pass


def die(msg):
    raise BenchError(msg)


def find_logs(user_dir):
    """收集工作区 rime 日志文件路径（用于失败时定位）。"""
    logdir = os.path.join(user_dir, "log")
    out = []
    for root in (logdir, user_dir):
        if os.path.isdir(root):
            for name in os.listdir(root):
                if name.lower().endswith(".log"):
                    out.append(os.path.join(root, name))
    return out


def dump_logs(user_dir, max_lines=40):
    parts = []
    for path in find_logs(user_dir):
        parts.append("===== %s =====" % path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
            parts.extend(lines[-max_lines:])
        except OSError as e:
            parts.append("<读取失败: %s>" % e)
    return "\n".join(parts) if parts else "<工作区内没有 .log 文件>"


def check_logs_for_errors(user_dir):
    """部署后扫描日志中的明显错误（lua 报错等）。

    wubi86.table.bin 缺失是预期现象：default.custom.yaml 已把 schema_list 精简为
    只部署 sanhe，但方案内的英文/混输等组件仍会尝试加载五笔词典（非致命）。
    """
    bad = []
    for path in find_logs(user_dir):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    low = line.lower()
                    if "wubi86" in low:
                        continue
                    if "error" in low or "exception" in low or "traceback" in low:
                        bad.append("%s: %s" % (os.path.basename(path), line.rstrip()))
                        if len(bad) >= 10:
                            return bad
        except OSError:
            pass
    return bad


def build_workspace(repo, ws_dir, variant):
    """把仓库方案文件复制进 ws/<variant>/user/，并写入档位 custom.yaml。"""
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
        die("工作区为空：%s 下没有找到任何方案文件" % repo)

    custom_dir = os.path.join(user_dir, "custom")
    tpl_path = os.path.join(custom_dir, "sanhe.custom.yaml")
    if not os.path.isfile(tpl_path):
        die("缺少档位模板：%s" % tpl_path)
    with open(tpl_path, "r", encoding="utf-8") as f:
        tpl = f.read()

    if variant in PERF_BLOCKS:
        content = tpl
        if not content.endswith("\n"):
            content += "\n"
        content += PERF_BLOCKS[variant]
    elif variant == "full":
        content = tpl
    else:
        die("未知变体: %s" % variant)

    with open(os.path.join(user_dir, "sanhe.custom.yaml"), "w", encoding="utf-8") as f:
        f.write(content)
    with open(os.path.join(user_dir, "default.custom.yaml"), "w", encoding="utf-8") as f:
        f.write(DEFAULT_CUSTOM)
    return user_dir


def load_rime(rime_dll, shared_dir, user_dir):
    dll_dir = os.path.dirname(os.path.abspath(rime_dll))
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(dll_dir)
    rime = CDLL(rime_dll)

    rime.RimeSetup.argtypes = [POINTER(RimeTraits)]
    rime.RimeSetup.restype = None
    rime.RimeInitialize.argtypes = [POINTER(RimeTraits)]
    rime.RimeInitialize.restype = None
    rime.RimeStartMaintenance.argtypes = [c_int]
    rime.RimeStartMaintenance.restype = c_int
    rime.RimeJoinMaintenanceThread.argtypes = []
    rime.RimeJoinMaintenanceThread.restype = None
    rime.RimeCreateSession.argtypes = []
    rime.RimeCreateSession.restype = c_void_p
    rime.RimeSelectSchema.argtypes = [c_void_p, c_char_p]
    rime.RimeSelectSchema.restype = c_int
    rime.RimeProcessKey.argtypes = [c_void_p, c_int, c_int]
    rime.RimeProcessKey.restype = c_int
    rime.RimeGetContext.argtypes = [c_void_p, POINTER(RimeContext)]
    rime.RimeGetContext.restype = c_int
    rime.RimeFreeContext.argtypes = [POINTER(RimeContext)]
    rime.RimeFreeContext.restype = None
    rime.RimeGetCommit.argtypes = [c_void_p, POINTER(RimeCommit)]
    rime.RimeGetCommit.restype = c_int
    rime.RimeFreeCommit.argtypes = [POINTER(RimeCommit)]
    rime.RimeFreeCommit.restype = None
    rime.RimeFinalize.argtypes = []
    rime.RimeFinalize.restype = None

    log_dir = os.path.join(user_dir, "log")
    os.makedirs(log_dir, exist_ok=True)
    traits = RimeTraits()
    traits.data_size = ctypes.sizeof(RimeTraits)
    traits.shared_data_dir = shared_dir.encode("utf-8")
    traits.user_data_dir = user_dir.encode("utf-8")
    traits.distribution_name = "sanhe-bench".encode("utf-8")
    traits.distribution_code_name = b"sanhe-bench"
    traits.distribution_version = b"1.0"
    traits.app_name = b"rime.sanhe-bench"
    # modules 是 const char**（NULL 结尾的字符串数组），不是逗号分隔字符串！
    # 必须带 lua，否则 lua_processor/lua_translator 全部失效
    modules_arr = (ctypes.c_char_p * 3)(b"default", b"lua", None)
    traits.modules = modules_arr
    traits._modules_keepalive = modules_arr  # 防 GC：结构体只存指针，数组本体必须保活
    traits.min_log_level = 2  # 2 = ERROR 及以上（librime: 0=INFO 1=WARNING 2=ERROR 3=FATAL）
    traits.log_dir = log_dir.encode("utf-8")
    traits.prebuilt_data_dir = None
    traits.staging_dir = None
    return rime, traits


def deploy(rime, traits):
    """Setup + Initialize + 部署（StartMaintenance + Join），返回部署耗时毫秒。"""
    t0 = time.perf_counter()
    rime.RimeSetup(ctypes.byref(traits))
    rime.RimeInitialize(ctypes.byref(traits))
    # Initialize 可能已触发维护线程；StartMaintenance 返回 0 表示已在跑，Join 会等它完成
    rime.RimeStartMaintenance(1)
    rime.RimeJoinMaintenanceThread()
    return (time.perf_counter() - t0) * 1000.0


KEYCODES = {
    "space": 0x20,
    "return": XK_RETURN,
    "escape": XK_ESCAPE,
    "backspace": XK_BACKSPACE,
}


def parse_workload(path):
    """解析 workload.txt -> [(tag, 'type'|'key', 内容)]。"""
    events = []
    tag = "default"
    with open(path, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                m = line[1:].strip()
                if m.startswith("@tag"):
                    tag = m[4:].strip() or "default"
                continue
            if line.startswith("---"):
                tag = "default"
                continue
            parts = line.split(None, 1)
            if len(parts) != 2 or parts[0] not in ("type", "key"):
                die("workload.txt 第 %d 行无法解析: %r" % (lineno, raw.rstrip()))
            kind, arg = parts
            if kind == "key":
                kc = KEYCODES.get(arg.lower())
                if kc is None:
                    die("workload.txt 第 %d 行未知键名: %s" % (lineno, arg))
                events.append((tag, "key", arg.lower(), kc))
            else:
                for ch in arg:
                    events.append((tag, "type", ch, ord(ch)))
    return events


def measure_round(rime, sid, events, record):
    """跑一遍工作负载；record 为 True 时把结果写入全局 EVENTS。"""
    for tag, kind, keyname, keycode in events:
        t1 = t2 = -1.0
        ncand = -1
        preedit = ""
        ctx = RimeContext()
        ctx.data_size = ctypes.sizeof(RimeContext)
        t0 = time.perf_counter()
        rime.RimeProcessKey(sid, keycode, 0)
        t1 = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        if rime.RimeGetContext(sid, ctypes.byref(ctx)):
            t2 = (time.perf_counter() - t0) * 1000.0
            ncand = ctx.menu.num_candidates
            if ctx.composition.preedit:
                preedit = ctypes.string_at(ctx.composition.preedit).decode(
                    "utf-8", errors="replace")
            rime.RimeFreeContext(ctypes.byref(ctx))
        commit_text = ""
        cmt = RimeCommit()
        cmt.data_size = ctypes.sizeof(RimeCommit)
        if rime.RimeGetCommit(sid, ctypes.byref(cmt)):
            if cmt.text:
                commit_text = ctypes.string_at(cmt.text).decode("utf-8", errors="replace")
            rime.RimeFreeCommit(ctypes.byref(cmt))
        if record:
            EVENTS.append({
                "tag": tag, "kind": kind, "key": keyname,
                "t1_ms": round(t1, 4), "t2_ms": round(t2, 4),
                "total_ms": round(t1 + t2, 4),
                "num_candidates": ncand, "preedit": preedit,
                "commit": commit_text,
            })
        else:
            WARMUP.append((tag, ncand, commit_text))


EVENTS = []   # 正式计分事件
WARMUP = []   # 预热事件 (tag, num_candidates, commit)


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def summarize(events, deploy_ms, wall_ms, rounds):
    by_tag = {}
    for e in events:
        by_tag.setdefault(e["tag"], []).append(e)
    tags = {}
    all_totals = []
    for tag, evs in sorted(by_tag.items()):
        totals = sorted(e["total_ms"] for e in evs)
        t1s = sorted(e["t1_ms"] for e in evs)
        t2s = sorted(e["t2_ms"] for e in evs)
        all_totals.extend(totals)
        tags[tag] = {
            "keys": len(evs),
            "process_mean_ms": round(statistics.mean(t1s), 4),
            "context_mean_ms": round(statistics.mean(t2s), 4),
            "mean_ms": round(statistics.mean(totals), 4),
            "p50_ms": round(percentile(totals, 50), 4),
            "p95_ms": round(percentile(totals, 95), 4),
            "max_ms": round(totals[-1], 4),
            "sum_ms": round(sum(totals), 4),
        }
    all_totals.sort()
    return {
        "variant": None,  # 由调用方填入
        "rounds": rounds,
        "deploy_ms": round(deploy_ms, 1),
        "wall_ms": round(wall_ms, 1),
        "total_keys": len(events),
        "overall": {
            "mean_ms": round(statistics.mean(all_totals), 4),
            "p50_ms": round(percentile(all_totals, 50), 4),
            "p95_ms": round(percentile(all_totals, 95), 4),
            "max_ms": round(all_totals[-1] if all_totals else 0.0, 4),
            "sum_ms": round(sum(all_totals), 4),
        },
        "tags": tags,
    }


def main():
    ap = argparse.ArgumentParser(description="三合输入法按键延迟基准测试（单变体）")
    ap.add_argument("--variant", required=True, choices=["full", "balance", "fast"])
    ap.add_argument("--rime-dll",
                    default=r"D:\Software\Rime-nightly\weasel-0.17.4\rime.dll")
    ap.add_argument("--shared-dir", default=None,
                    help="小狼毫 data 目录（默认自动探测 <rime.dll目录>/data）")
    ap.add_argument("--repo", default=os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "results"))
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--workload", default=os.path.join(os.path.dirname(__file__),
                                                       "workload.txt"))
    args = ap.parse_args()

    shared_dir = args.shared_dir
    if shared_dir is None:
        guess = os.path.join(os.path.dirname(os.path.abspath(args.rime_dll)), "data")
        shared_dir = guess if os.path.isdir(guess) else None
    if not shared_dir or not os.path.isdir(shared_dir):
        die("找不到 shared_data_dir（小狼毫 data 目录），请用 --shared-dir 指定")
    if not os.path.isfile(args.rime_dll):
        die("找不到 rime.dll: %s" % args.rime_dll)

    bench_dir = os.path.dirname(os.path.abspath(__file__))
    ws_dir = os.path.join(bench_dir, "ws", args.variant)
    user_dir = build_workspace(args.repo, ws_dir, args.variant)
    print("[%s] 工作区: %s" % (args.variant, user_dir))

    rime, traits = load_rime(args.rime_dll, shared_dir, user_dir)
    deploy_ms = deploy(rime, traits)
    print("[%s] 部署完成: %.1f ms" % (args.variant, deploy_ms))

    # 部署健康检查：产物 + 日志错误
    built = os.path.join(user_dir, "build", "sanhe.schema.yaml")
    if not os.path.isfile(built):
        die("部署失败（缺少 %s）。工作区日志摘要：\n%s" % (built, dump_logs(user_dir)))
    errors = check_logs_for_errors(user_dir)
    if errors:
        die("部署日志存在错误：\n" + "\n".join(errors) +
            "\n\n工作区日志摘要：\n" + dump_logs(user_dir))

    sid = rime.RimeCreateSession()
    if not sid:
        die("RimeCreateSession 返回空会话。工作区日志摘要：\n%s" % dump_logs(user_dir))
    if not rime.RimeSelectSchema(sid, b"sanhe"):
        die("RimeSelectSchema(sanhe) 失败。工作区日志摘要：\n%s" % dump_logs(user_dir))

    events = parse_workload(args.workload)
    print("[%s] 工作负载: %d 个按键事件" % (args.variant, len(events)))

    # 预热（不计分）
    measure_round(rime, sid, events, record=False)
    rime.RimeProcessKey(sid, XK_ESCAPE, 0)  # 清掉残留组合

    t_start = time.perf_counter()
    for _ in range(args.rounds):
        measure_round(rime, sid, events, record=True)
    wall_ms = (time.perf_counter() - t_start) * 1000.0

    # 健康断言：health 组每个 type 事件后必须有候选
    bad = [e for e in EVENTS if e["tag"] == "health" and e["kind"] == "type"
           and e["num_candidates"] <= 0]
    if bad:
        sample = "\n".join(str(e) for e in bad[:5])
        die("健康断言失败：type nihao 后 num_candidates=0（lua 失效或部署异常？）。\n%s\n"
            "工作区日志摘要：\n%s" % (sample, dump_logs(user_dir)))

    rime.RimeFinalize()

    # 输出
    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, args.variant + ".csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tag", "kind", "key", "t1_ms", "t2_ms", "total_ms",
                    "num_candidates", "preedit", "commit"])
        for e in EVENTS:
            w.writerow([e["tag"], e["kind"], e["key"], e["t1_ms"], e["t2_ms"],
                        e["total_ms"], e["num_candidates"], e["preedit"], e["commit"]])

    summary = summarize(EVENTS, deploy_ms, wall_ms, args.rounds)
    summary["variant"] = args.variant
    summary["shared_data_dir"] = shared_dir
    summary["rime_dll"] = args.rime_dll
    json_path = os.path.join(args.out, args.variant + ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("[%s] 完成: 总体 mean=%.3f ms  p95=%.3f ms  deploy=%.1f ms"
          % (args.variant, summary["overall"]["mean_ms"],
             summary["overall"]["p95_ms"], deploy_ms))
    print("  CSV:  %s" % csv_path)
    print("  JSON: %s" % json_path)


if __name__ == "__main__":
    try:
        main()
    except BenchError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        sys.exit(1)
