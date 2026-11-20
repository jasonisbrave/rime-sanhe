#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rime-sanhe 发布打包脚本（仅标准库）。

读取仓库根 version.txt，将可部署方案打包为
dist/rime-sanhe-v{版本}.zip，并生成同名 .sha256 校验文件。

zip 内顶层为 rime-sanhe/ 目录，与 README 安装说明一致。
"""
import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOP_LEVEL_PATTERNS = ("*.yaml", "*.txt")
TOP_LEVEL_NAMES = ("README.md", "LICENSE", "CHANGELOG.md")
TOP_LEVEL_DIRS = ("custom", "dicts", "docs", "licenses", "lua", "tools")


def should_exclude(rel: Path) -> bool:
    """判断相对路径（仓库根起）是否应排除。"""
    parts = rel.parts
    if not parts:
        return True
    top = parts[0]
    # 顶层排除
    if top.startswith(".git") or top in (".github", "dist"):
        return True
    # Rime 运行态文件：绝不打入发布包（含 installation_id 等本机状态，
    # 用户解压覆盖会破坏其现有 Rime 安装）
    if top in ("installation.yaml", "user.yaml", "sync", "build"):
        return True
    # 根目录 *.custom.yaml 是用户/切换器维护的本地配置，不属于发布内容
    #（custom/ 目录内的切换模板除外）
    if top.endswith(".custom.yaml"):
        return True
    # 用户词库目录
    if any(p.endswith(".userdb") for p in parts):
        return True
    # tools/bench 下的运行产物
    if top == "tools" and len(parts) >= 2 and parts[1] == "bench":
        if len(parts) >= 3 and (parts[2] in ("ws", "results")
                                or parts[2].startswith("results_smoke")):
            return True
    # 通用排除
    if rel.suffix in (".log", ".pyc"):
        return True
    if "Thumbs.db" in parts:
        return True
    if "__pycache__" in parts:
        return True
    return False


def collect_files(root: Path):
    """返回 (zip 内相对路径, 磁盘绝对路径) 列表，按路径排序。"""
    entries = []
    for pattern in TOP_LEVEL_PATTERNS:
        for p in sorted(root.glob(pattern)):
            if p.is_file():
                entries.append(p)
    for name in TOP_LEVEL_NAMES:
        p = root / name
        if p.is_file():
            entries.append(p)
    for d in TOP_LEVEL_DIRS:
        p = root / d
        if p.is_dir():
            entries.extend(f for f in sorted(p.rglob("*")) if f.is_file())

    result = []
    for p in entries:
        rel = p.relative_to(root)
        if should_exclude(rel):
            continue
        arc = Path("rime-sanhe") / rel
        result.append((arc, p))
    return sorted(result, key=lambda x: str(x[0]).replace("\\", "/"))


def main() -> int:
    parser = argparse.ArgumentParser(description="打包 rime-sanhe 发布 zip")
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="仓库根目录（默认取脚本所在仓库根）",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()

    version = (root / "version.txt").read_text(encoding="utf-8").strip()
    dist_dir = root / "dist"
    dist_dir.mkdir(exist_ok=True)
    zip_name = f"rime-sanhe-v{version}.zip"
    zip_path = dist_dir / zip_name

    files = collect_files(root)
    if not files:
        print("错误：未收集到任何文件", file=sys.stderr)
        return 1

    total_size = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arc, p in files:
            zf.write(p, arc.as_posix())
            total_size += p.stat().st_size

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path = zip_path.with_suffix(".sha256")
    sha_path.write_text(f"{digest}  {zip_name}\n", encoding="ascii")

    # 输出摘要
    print(f"版本: {version}")
    print(f"输出: {zip_path}")
    print(f"文件数: {len(files)}")
    print(f"原始总大小: {total_size / (1024 * 1024):.2f} MiB")
    print(f"zip 大小: {zip_path.stat().st_size / (1024 * 1024):.2f} MiB")
    print(f"SHA256: {digest}  ({sha_path.name})")
    print("顶层条目:")
    seen = set()
    for arc, _ in files:
        top = arc.parts[1] if len(arc.parts) > 1 else arc.name
        if top not in seen:
            seen.add(top)
            print(f"  - {top}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
