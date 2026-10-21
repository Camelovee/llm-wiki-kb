#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
索引.py — 重建 索引.md 与 仪表盘.md(唯一的"写者";校验.py 保持只读)

职责(见 AGENTS.md §3 / §4):
- 扫描知识层全部页(排除 索引/仪表盘/维护日志 三个导航页),按主题目录分组
  重建唯一索引:主题速览计数、各主题条目列表、总计。条目用 vault 根相对
  路径链接,天然通过校验.py 的断链检测。
- 保留旧索引条目里的人写「一句话说明」(解析合并,非纯重建):
  优先级 旧说明 > frontmatter description > 省略。
- 主题下的一行主题说明(## 主题 下、条目之上的那行文字)同样保留。
- 刷新仪表盘统计(总数 / 按主题 / 最近更新 / 孤儿 / 待编译);
  frontmatter 保留、仅 bump updated。孤儿/待编译经子进程调同级的
  校验.py / 清单.py --json 取数,失败降级显示 "—"。
- 机械合规是 校验.py 的事;本脚本只管「修」:跑一遍即修复索引漂移。

幂等性:空库下本脚本的输出与 init 脚手架的初始 索引.md / 仪表盘.md 逐字一致,
首次运行是 no-op。

用法:
  python3 索引.py                # 重建(临时文件 + os.replace 原子写)
  python3 索引.py --dry-run      # 打印将发生的变更(unified diff 预览),不写盘
  python3 索引.py --check        # 有漂移退出 1(供自动化 / CI)
  python3 索引.py --root <KB_ROOT> [--json]
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

KB_DIR = "知识库"
RAW_DIR = "原始资料"
NAV = {"index": "索引.md", "dash": "仪表盘.md", "log": "维护日志.md"}
TOOLS = {"manifest": "清单.py", "validate": "校验.py", "evidence": "证据.py"}

ENTRY_RE = re.compile(r"^\s*[-*]\s+\[\[([^\[\]]+?)\]\]\s*(?:[—–-]\s*(.*))?$")

INDEX_HEADER = (
    "# 索引\n\n"
    "> **本页是唯一索引。** 查询从这里进,按主题找到目标页面。\n"
    "> 知识页按主题目录组织;本页按主题列出所有页面,并附一句话说明。\n\n"
    "## 主题速览\n\n"
    "| 主题 | 数量 |\n"
    "|---|---|\n"
)
INDEX_FOOTER = (
    "\n---\n\n"
    "## 导航\n\n"
    "- [[仪表盘]] — 知识库生长状况统计\n"
    "- [[维护日志]] — 维护历史(只追加)\n"
    "- [[AGENTS]] — 规则真源\n\n"
    "## 怎么用这个知识库\n\n"
    "| 我想…… | 怎么做 |\n"
    "|---|---|\n"
    "| **投喂资料** | 把来源存进 `原始资料/<主题>/`,然后说「编译一下知识库」 |\n"
    "| **问问题** | 直接问,我先检索知识库并引用来源;好答案可要求「存进知识库」 |\n"
    "| **看全貌** | 打开 Obsidian 的图谱视图(Graph View),或看 [[仪表盘]] |\n"
    "| **体检** | 说「检查知识库」,我跑 `工具/校验.py` 报 0/0/0/0,再跑 `工具/证据.py` 核查事实 |\n\n"
    "---\n"
    "---\n"
    "> 维护说明:本页由 `工具/索引.py` 重建维护;条目尾部的一句话说明可手写,"
    "脚本重建时保留。新增页面后跑 `python3 工具/索引.py`,不要手改计数。\n"
)

DASH_STATS = (
    "# 📊 仪表盘\n\n"
    "- **笔记总数**:{total}(不含索引、仪表盘、维护日志)\n"
    "- **按主题**:{by_topic}\n"
    "- **孤儿笔记(无知识页入链)**:{orphans}\n"
    "- **源资料待编译**:{pending}\n"
    "- **最近更新**:{latest}\n\n"
    "---\n\n"
    "## 怎么更新本页\n\n"
    "编辑完知识库后,跑:\n\n"
    "```\npython3 工具/索引.py\n```\n\n"
    "它会重建 [[索引]] 并重写本页统计。\n\n"
    "> 本页统计由 `工具/索引.py` 依据 `工具/校验.py` / `工具/清单.py` 的输出重写;"
    "引入 Dataview 插件后可改为自动查询。\n"
)


def parse_frontmatter(text: str):
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm = {}
    for line in text[3:end].strip("\n").splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#") or line[0] in (" ", "\t"):
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm


def load_pages(root: Path):
    """扫描知识层。返回 Page dict 列表;导航页跳过,主题 = kb 下一级目录名。"""
    kb = root / KB_DIR
    pages = []
    for p in sorted(kb.rglob("*.md")):
        if p.name in set(NAV.values()):
            continue
        fm = parse_frontmatter(p.read_text(encoding="utf-8", errors="replace")) or {}
        rel = p.relative_to(kb)
        topic = rel.parts[0] if len(rel.parts) > 1 else "未归类"
        pages.append({
            "key": p.relative_to(root).as_posix()[:-3],
            "path": p,
            "topic": topic,
            "title": fm.get("title") or p.stem,
            "updated": fm.get("updated", ""),
            "description": fm.get("description", ""),
        })
    return pages


def parse_old_index(text: str):
    """解析旧索引:返回 (entries {key: 说明}, topics {主题名: 主题说明或 ""})。"""
    kb_prefix = KB_DIR + "/"
    entries = {}
    topics = {}
    current_topic = None
    in_speed = False
    for line in text.splitlines():
        if line.startswith("## "):
            current_topic = line[3:].strip()
            if current_topic in ("主题速览",):
                in_speed = True
            elif current_topic in ("导航",):
                in_speed = False
                current_topic = None
            continue
        if in_speed:
            continue
        if current_topic is None:
            continue
        m = ENTRY_RE.match(line)
        if m:
            inner = m.group(1).replace("\\|", "|")
            target = inner.split("|", 1)[0].strip().replace("\\", "/")
            if target.lower().endswith(".md"):
                target = target[:-3]
            if target.startswith(kb_prefix):
                target = target[len(kb_prefix):]
            entries[target] = (m.group(2) or "").strip()
        elif line.strip() and not line.startswith("|") and current_topic not in topics:
            # 条目之上的一行主题说明
            topics[current_topic] = line.strip()
    return entries, topics


def preserved_desc(page, old_entries):
    for k in (page["key"], page["key"].split("/", 1)[-1], page["path"].stem):
        if k in old_entries and old_entries[k]:
            return old_entries[k]
    return page["description"]


def build_index_text(pages, old_entries, old_topics) -> str:
    by_topic = {}
    for pg in pages:
        by_topic.setdefault(pg["topic"], []).append(pg)

    parts = [INDEX_HEADER]
    for topic in sorted(by_topic):
        parts.append(f"| {topic} | {len(by_topic[topic])} |\n")
    parts.append(f"\n**总计:{len(pages)} 页**\n\n---\n\n")

    for topic in sorted(by_topic):
        parts.append(f"## {topic}\n\n")
        desc = old_topics.get(topic)
        if desc:
            parts.append(desc + "\n\n")
        for pg in sorted(by_topic[topic], key=lambda x: x["key"]):
            d = preserved_desc(pg, old_entries)
            dash = f" — {d}" if d else ""
            parts.append(f"- [[{pg['key']}|{pg['title']}]]{dash}\n")
        parts.append("\n")
    parts.append(INDEX_FOOTER)
    return "".join(parts)


def sibling_json(root: Path, which: str) -> dict | None:
    script = root / "工具" / TOOLS[which]
    if script.exists():
        try:
            r = subprocess.run([sys.executable, str(script), "--json"],
                               capture_output=True, text=True, timeout=120)
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout)
        except Exception:
            pass
    return None


def build_dashboard_text(root: Path, pages) -> str:
    dash_path = root / KB_DIR / NAV["dash"]
    old_fm = {}
    if dash_path.exists():
        old_fm = parse_frontmatter(dash_path.read_text(encoding="utf-8", errors="replace")) or {}
    fm = {"title": old_fm.get("title", "仪表盘 · 知识库"),
          "description": old_fm.get(
              "description", "知识库生长状况统计(页数 / 主题分布 / 孤儿 / 待编译 / 最近更新)。")}
    fm["updated"] = date.today().isoformat()

    v = sibling_json(root, "validate")
    orphans = str(v["counts"]["orphans"]) if v else "—"
    m = sibling_json(root, "manifest")
    pending = str(m["counts"]["added"] + m["counts"]["changed"]) if m else "—"

    by_topic = {}
    for pg in pages:
        by_topic[pg["topic"]] = by_topic.get(pg["topic"], 0) + 1
    by_topic_s = " / ".join(f"{t} {n}" for t, n in sorted(by_topic.items())) or "—"

    latest, latest_pages = "", []
    for pg in pages:
        if pg["updated"] and pg["updated"] >= latest:
            if pg["updated"] > latest:
                latest_pages = []
            latest = pg["updated"]
            latest_pages.append(pg)
            latest_pages = [x for x in latest_pages if x["updated"] == latest]
    latest = latest or "—"
    latest_pages = sorted(latest_pages, key=lambda x: x["key"])[:3]
    if latest_pages:
        links = " ".join(f"[[{p['key']}|{p['title']}]]" for p in latest_pages)
        latest = f"{latest}({links})"

    fm_text = "---\n" + "".join(f"{k}: {v}\n" for k, v in fm.items()) + "---\n\n"
    return fm_text + DASH_STATS.format(total=len(pages), by_topic=by_topic_s,
                                       orphans=orphans, pending=pending, latest=latest)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser(description="重建唯一索引与仪表盘(写者)")
    ap.add_argument("--root", default=None, help="KB 根目录(默认脚本上一级)")
    ap.add_argument("--dry-run", action="store_true", help="打印 diff 预览,不写盘")
    ap.add_argument("--check", action="store_true", help="有漂移退出 1(供自动化)")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    kb = root / KB_DIR
    if not kb.is_dir():
        print(f"ERROR: 知识层目录不存在: {kb}", file=sys.stderr)
        return 2

    index_path = kb / NAV["index"]
    dash_path = kb / NAV["dash"]

    pages = load_pages(root)
    old_text = index_path.read_text(encoding="utf-8", errors="replace") if index_path.exists() else ""
    old_entries, old_topics = parse_old_index(old_text)

    new_index = build_index_text(pages, old_entries, old_topics)
    new_dash = build_dashboard_text(root, pages)

    old_dash = dash_path.read_text(encoding="utf-8", errors="replace") if dash_path.exists() else ""
    changes = []
    if old_text != new_index:
        changes.append((index_path, old_text, new_index))
    if old_dash != new_dash:
        changes.append((dash_path, old_dash, new_dash))

    if args.json:
        print(json.dumps({
            "pages": len(pages),
            "changed": [c[0].relative_to(root).as_posix() for c in changes],
            "in_sync": not changes,
        }, ensure_ascii=False, indent=2))

    if args.dry_run:
        for path, old, new in changes:
            print(f"--- {path.relative_to(root)} (将重写)")
            diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=2)
            for i, line in enumerate(diff):
                if i > 60:
                    print("  …")
                    break
                print("  " + line)
        if not changes:
            print("(索引与仪表盘已是最新)")

    if args.check:
        return 1 if changes else 0
    if args.dry_run:
        return 0
    for path, _old, new in changes:
        atomic_write(path, new)
        if not args.json:
            print(f"rebuilt: {path.relative_to(root)}")
    if not changes and not args.json:
        print("(索引与仪表盘已是最新)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
