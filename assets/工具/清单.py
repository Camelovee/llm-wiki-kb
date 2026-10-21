#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manifest.py / 清单.py — 扫描源资料层,生成 / 比对内容哈希清单(增量检测)

v3 变化:
- 纯中文库:删布局感知与双语输出(仓库只做中文版)。
- 基线文件名固定 .清单.json(v2 的双名兼容随双语机制一并移除)。

设计(见 AGENTS.md §4 Ingest):
- 预筛: mtime + size 相等则视为未变(保留旧哈希,不重算)
- 精判: 预筛命中(mtime / size 不同)才计算指纹哈希
- 大文件: 单文件 > LARGE_FILE_THRESHOLD 时改用「头尾各采样 + size」做指纹,避免全文 I/O
- 忽略: node_modules / build / .git / __pycache__、编辑器临时文件、清单自身、.obsidian
- 写入: 先写临时文件再 os.replace 原子替换,防并发写损坏
- 基线文件名: 读取时 .manifest.json / .清单.json 哪个存在用哪个;写回用已存在的那个,
  避免一个库长出两份基线

用法:
  python3 清单.py                 # 比对并打印变更(不写回)
  python3 清单.py --update        # 比对并原子写回基线
  python3 清单.py --root <KB_ROOT>
  python3 清单.py --json          # JSON 输出
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

RAW_DIR = "原始资料"
MANIFEST_NAME = ".清单.json"

IGNORE_DIRS = {"node_modules", "build", ".git", "__pycache__", ".obsidian"}
# 编辑器 / 系统临时文件
TEMP_SUFFIXES = (".tmp", ".swp", ".part", "~")
TEMP_NAMES = {".DS_Store", "Thumbs.db"}
# 大文件指纹阈值与采样大小
LARGE_FILE_THRESHOLD = 50 * 1024 * 1024  # 50 MB
SAMPLE = 1024 * 1024  # 1 MB

MSG = {
    "raw_missing": "ERROR: {raw}/ 目录不存在: {path}",
    "summary": "已跟踪={tracked}  新增={added}  变更={changed}  移除={removed}",
    "no_change": "  (无变更,知识库与源资料已同步)",
    "baseline": "基线已写回: {path}",
}




def is_temp_file(name: str) -> bool:
    """编辑器 / 系统临时文件判定。"""
    if name in TEMP_NAMES:
        return True
    if name.startswith("~$"):
        return True
    return name.endswith(TEMP_SUFFIXES)


def included(path: Path) -> bool:
    """判断文件是否纳入清单。"""
    if path.name == MANIFEST_NAME:
        return False
    if path.name.startswith("."):
        return False
    if is_temp_file(path.name):
        return False
    return True


def fingerprint_of(path: Path) -> str:
    """内容指纹哈希。
    - 常规文件:全文 sha256(分块读,不爆内存)
    - 大文件(> 阈值):头尾各采样 + size 拼接哈希,避免全文 I/O
    """
    h = hashlib.sha256()
    size = path.stat().st_size
    if size <= LARGE_FILE_THRESHOLD:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    with open(path, "rb") as f:
        head = f.read(SAMPLE)
        h.update(head)
        if size > SAMPLE:
            f.seek(max(SAMPLE, size - SAMPLE))
            tail = f.read()
            h.update(tail)
    h.update(str(size).encode("utf-8"))
    return h.hexdigest()


def scan(raw: Path) -> dict:
    """遍历源资料层,返回 {相对路径: {mtime, size}}。"""
    manifest: dict = {}
    for dirpath, dirnames, filenames in os.walk(raw):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        dp = Path(dirpath)
        for fn in filenames:
            fp = dp / fn
            if not included(fp):
                continue
            try:
                st = fp.stat()
            except OSError:
                continue
            rel = fp.relative_to(raw).as_posix()
            manifest[rel] = {"mtime": int(st.st_mtime), "size": st.st_size}
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="源资料清单工具(增量检测)")
    ap.add_argument("--root", default=None, help="KB 根目录(默认脚本上一级)")
    ap.add_argument("--update", action="store_true", help="原子写回基线清单")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    msg = MSG

    raw = root / RAW_DIR
    if not raw.exists():
        print(msg["raw_missing"].format(raw=RAW_DIR, path=raw), file=sys.stderr)
        return 2
    manifest_path = raw / MANIFEST_NAME

    new = scan(raw)
    old: dict = {}
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            old = {}

    old_keys, new_keys = set(old), set(new)
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    changed = []

    for k in sorted(new_keys & old_keys):
        o, n = old[k], new[k]
        if o.get("mtime") == n["mtime"] and o.get("size") == n["size"]:
            n["sha256"] = o.get("sha256")  # 未变,保留旧哈希
            continue
        new[k]["sha256"] = fingerprint_of(raw / k)  # 预筛命中,算指纹精判
        if new[k]["sha256"] != o.get("sha256"):
            changed.append(k)

    for k in added:
        new[k]["sha256"] = fingerprint_of(raw / k)

    result = {
        "added": added,
        "changed": changed,
        "removed": removed,
        "counts": {"added": len(added), "changed": len(changed),
                   "removed": len(removed), "tracked": len(new)},
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        c = result["counts"]
        print(msg["summary"].format(**c))
        for k in added:
            print(f"  + {k}")
        for k in changed:
            print(f"  ~ {k}")
        for k in removed:
            print(f"  - {k}")
        if not (added or changed or removed):
            print(msg["no_change"])

    if args.update:
        tmp = manifest_path.with_name(manifest_path.name + ".tmp")
        tmp.write_text(json.dumps(new, ensure_ascii=False, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, manifest_path)  # 原子替换
        if not args.json:
            print(msg["baseline"].format(path=manifest_path))

    return 0


if __name__ == "__main__":
    sys.exit(main())
