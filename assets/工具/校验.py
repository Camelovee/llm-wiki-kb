#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校验.py — 知识库机械预筛器(规模哨兵 + frontmatter 合规 / 断链 / 孤儿 / 索引对账 + 待查问题汇总)

定位(见 AGENTS.md §4 Lint、§6、§10):
- **只读检测器**:只扫描、只报告,绝不改 / 删 / 合并任何页
  (修复索引漂移请跑 索引.py;事实保真请跑 证据.py)。
- **规模哨兵**:先数知识层页数,阈值 THRESHOLD=200;越阈在报告顶部打醒目预警。
- **机械预筛四项**(语义层「矛盾 / 过期 / 重复 / 该建未建」交 LLM):
  1. frontmatter 合规:须含非空 title / description / updated。豁免 索引 / 维护日志。
  2. 断链:正文 [[wikilink]] 与 markdown 链接目标须存在。
  3. 孤儿:无任何**知识页**入链(导航页——索引/仪表盘/维护日志——里的链接不算入链,
     重建索引洗不掉孤儿;豁免三个导航页自身)。
  4. 索引对账:唯一索引的死条目 / 漏条目 / 计数虚。
- **待查问题汇总**(兑现 AGENTS.md §6):抓取各页 `## 待查问题` 小节未划掉的条目。
- 事实保真由姊妹脚本 证据.py 负责(机械报告层),两者互补。

v3 变化:纯中文库(删布局感知/双语输出);frontmatter 必填改为
title/description/updated(状态机降级为可选自由字段,不枚举);
知识层改 topic 布局;断链检测扩展 markdown 链接。

用法:
  python3 校验.py                 # 全量机械预筛,文本报告
  python3 校验.py --json          # JSON 输出(机器可读)
  python3 校验.py --count         # 只报规模哨兵
  python3 校验.py --root <KB_ROOT>
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

THRESHOLD = 200  # 规模哨兵阈值(页)

KB_DIR = "知识库"
RAW_DIR = "原始资料"
NAV = {"index": "索引.md", "dash": "仪表盘.md", "log": "维护日志.md"}
NAV_NAMES = set(NAV.values())
FM_EXEMPT = {NAV["index"], NAV["log"]}
ORPHAN_EXEMPT = NAV_NAMES

# 示例 / 占位链接(文档演示用,非真链接)
PLACEHOLDER_TARGETS = {
    "wikilink", "page", "relative-path", "wiki-link", "wiki/...",
    "raw/source-file", "raw/xxx", "raw/paper-xxx", "raw/article-xxx",
    "页面名", "其他页面", "相关页面", "来源页", "笔记", "其他笔记",
    "other-page", "related-page", "source-page", "project-name", "note-title",
}
PLACEHOLDER_HINT = re.compile(r"(xxx|yyy|zzz|aaa|bbb|\.\.\.)")

WIKILINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")
MDLINK_RE = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)#\s]+)[^)]*\)")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
OPENQ_HEADING_RE = re.compile(r"^##\s*待查问题\s*$")
HEADING_ANY_RE = re.compile(r"^#{1,6}\s")
ENTRY_RE = re.compile(r"^\s*[-*]\s+\[\[([^\[\]]+?)\]\]\s*(?:[—–-]\s*(.*))?$")
SPEED_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|", re.MULTILINE)
STRUCK_RE = re.compile(r"^~~.*~~\s*$")

MSG = {
    "kb_missing": "ERROR: 知识层目录不存在: {kb}",
    "scale_over": "⚠️ 规模预警:知识库已达 {pages} 页 > 阈值 {threshold} "
                  "—— 本轮以「脚本机械预筛 + LLM 语义」模式运行。",
    "scale_ok": "规模哨兵:{pages} 页 ≤ 阈值 {threshold}(LLM 全量语义体检足矣)。",
    "scale_short_over": "规模哨兵:{n} 页 / 阈值 {t} → ⚠️ 越阈",
    "scale_short_ok": "规模哨兵:{n} 页 / 阈值 {t} → ≤ 阈值",
    "summary": "机械预筛:frontmatter 不合规={fm}  断链={bl}  孤儿={orph}  索引不一致={ix}",
    "fm": "[frontmatter 不合规]",
    "broken": "[断链]",
    "orphans": "[孤儿页(无知识页入链)]",
    "index": "[索引不一致]",
    "idx_dead": "死条目",
    "idx_missing": "漏条目",
    "idx_count": "计数虚",
    "idx_absent": "唯一索引文件不存在",
    "openq": "[待查问题] {n} 条未结(分布在 {m} 页)",
    "openq_more": "  …(其余 {n} 条略)",
    "all_green": "✅ 机械预筛全绿:0 / 0 / 0 / 0。",
    "evidence_hint": "提示:事实保真请再跑 `python3 工具/证据.py`(机械核查每个数字/日期/引语可溯源)。",
    "reason_no_fm": "缺 frontmatter",
    "reason_missing": "缺字段: ",
    "err_prefix": "  ✗ ",
    "orphan_mark": "  ○ ",
}


def parse_frontmatter(text: str):
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm = {}
    for line in text[3:end].strip("\n").splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line[0] in (" ", "\t"):
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm


def strip_code(text: str) -> str:
    return FENCE_RE.sub("", text)


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text if end == -1 else text[end + 4:]


def normalize_wikilink(raw: str) -> str:
    t = raw.replace("\\|", "|")
    t = t.split("|", 1)[0]
    t = t.split("#", 1)[0]
    t = t.strip().replace("\\", "/")
    if t.lower().endswith(".md"):
        t = t[:-3]
    return t


def is_placeholder(target: str) -> bool:
    if target in PLACEHOLDER_TARGETS:
        return True
    return bool(PLACEHOLDER_HINT.search(target))


def resolve_exists(root: Path, target: str) -> bool:
    """wikilink 目标以库根为基准解析。"""
    if "/" in target:
        return (root / (target + ".md")).exists() or (root / target).exists()
    for dirpath, _dirs, filenames in os.walk(root):
        if ".obsidian" in dirpath:
            continue
        for fn in filenames:
            if fn.lower().endswith(".md") and Path(fn).stem == target:
                return True
    return False


def resolve_md_link(root: Path, page: Path, link: str) -> bool:
    """markdown 链接:先按文件相对解析,再按库根相对兜底。"""
    link = link.split("#", 1)[0].strip()
    if not link or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link):  # URL scheme
        return True
    if (page.parent / link).exists():
        return True
    return (root / link).exists()


def rel_key(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()[:-3]


def build_stem_index(pages, root: Path):
    stem_map = {}
    for p in pages:
        stem_map.setdefault(p.stem, rel_key(root, p))
    return stem_map


def collect_open_questions(page_texts):
    result = {}
    for rel, text in page_texts:
        in_section = False
        items = []
        for line in text.splitlines():
            if line.startswith("## "):
                in_section = bool(OPENQ_HEADING_RE.match(line.strip()))
                continue
            if in_section and HEADING_ANY_RE.match(line):
                in_section = False
                continue
            if not in_section:
                continue
            m = re.match(r"^\s*[-*]\s+(.*)$", line)
            if not m:
                continue
            item = m.group(1).strip()
            if item and not STRUCK_RE.match(item):
                items.append(item)
        if items:
            result[rel] = items
    return result


def lint_index(root: Path, pages, stem_map):
    issues = []
    index_path = root / KB_DIR / NAV["index"]
    if not index_path.exists():
        return [{"kind": "absent", "detail": NAV["index"]}]

    page_keys = {rel_key(root, p) for p in pages}
    kb_prefix = KB_DIR + "/"
    text = index_path.read_text(encoding="utf-8", errors="replace")

    entries = {}
    in_speed = False
    past_nav = False
    for line in text.splitlines():
        if line.startswith("## "):
            title = line.strip()
            in_speed = title == "## 主题速览"
            if title == "## 导航":
                past_nav = True   # 导航及之后(用法表/维护说明)的 [[链接]] 不算索引条目
            continue
        if in_speed or past_nav:
            continue
        m = ENTRY_RE.match(line)
        if not m:
            continue
        inner = m.group(1).replace("\\|", "|")
        target = inner.split("|", 1)[0].strip().replace("\\", "/")
        if target.lower().endswith(".md"):
            target = target[:-3]
        if target.startswith(kb_prefix):
            target = target[len(kb_prefix):]
        entries[target] = True

    for target in sorted(entries):
        if "/" in target:
            hit = (KB_DIR + "/" + target) in page_keys
        else:
            hit = target in stem_map
        if not hit:
            issues.append({"kind": "dead", "detail": target})

    for p in pages:
        if p.name in NAV_NAMES:
            continue
        key = rel_key(root, p)
        short_key = key[len(kb_prefix):] if key.startswith(kb_prefix) else key
        if short_key not in entries and p.stem not in entries:
            issues.append({"kind": "missing", "detail": key})

    actual = {}
    for p in pages:
        if p.name in NAV_NAMES:
            continue
        topic = p.relative_to(root / KB_DIR).parts[0] \
            if len(p.relative_to(root / KB_DIR).parts) > 1 else "未归类"
        actual[topic] = actual.get(topic, 0) + 1
    declared = {}
    for m in SPEED_ROW_RE.finditer(text):
        name, n = m.group(1).strip(), int(m.group(2))
        if name in ("主题",):
            continue
        declared[name] = n
    for topic, n in sorted(declared.items()):
        if topic in actual and actual[topic] != n:
            issues.append({"kind": "count", "detail": f"{topic}: {n}≠{actual[topic]}"})
    total_match = re.search(r"\*\*总计[:：]\s*(\d+)\s*页\*\*", text)
    n_pages = len([p for p in pages if p.name not in NAV_NAMES])
    if total_match and int(total_match.group(1)) != n_pages:
        issues.append({"kind": "count", "detail": f"总计: {total_match.group(1)}≠{n_pages}"})
    return issues


def lint(root: Path) -> dict:
    kb = root / KB_DIR
    pages = sorted(kb.rglob("*.md"))
    page_texts = [(p.relative_to(root).as_posix(),
                   p.read_text(encoding="utf-8", errors="replace")) for p in pages]
    page_keys = {rel_key(root, p) for p in pages}
    stem_map = build_stem_index(pages, root)

    fm_bad, broken, inbound = [], [], {k: 0 for k in page_keys}

    for p, (rel, text) in zip(pages, page_texts):
        # 1. frontmatter 合规(豁免索引与日志)
        if p.name not in FM_EXEMPT:
            fm = parse_frontmatter(text)
            if fm is None:
                fm_bad.append({"page": rel, "reason": "no_fm"})
            else:
                miss = [k for k in ("title", "description", "updated") if not fm.get(k)]
                if miss:
                    fm_bad.append({"page": rel, "reason": "missing:" + ",".join(miss)})

        # 2 & 3. 链接扫描(frontmatter 与代码块不计)
        body = strip_frontmatter(strip_code(text))
        count_inbound = p.name not in NAV_NAMES
        self_key = rel_key(root, p)

        def register(target: str, exists: bool):
            hit = None
            if target in page_keys:
                hit = target
            elif "/" not in target:
                hit = stem_map.get(target)
            if hit and hit != self_key and count_inbound:
                inbound[hit] += 1
            if not exists:
                broken.append({"page": rel, "target": target})

        for m in WIKILINK_RE.finditer(body):
            target = normalize_wikilink(m.group(1))
            if not target or is_placeholder(target):
                continue
            register(target, resolve_exists(root, target))
        for m in MDLINK_RE.finditer(body):
            link = m.group(2)
            if is_placeholder(link):
                continue
            register(link, resolve_md_link(root, p, link))

    orphans = sorted(
        k + ".md" for k, n in inbound.items()
        if n == 0 and Path(k + ".md").name not in ORPHAN_EXEMPT
    )

    index_issues = lint_index(root, pages, stem_map)
    open_questions = collect_open_questions(page_texts)

    n_pages = len(pages)
    return {
        "scale": {"pages": n_pages, "threshold": THRESHOLD, "over": n_pages > THRESHOLD},
        "frontmatter_issues": fm_bad,
        "broken_links": broken,
        "orphans": orphans,
        "index_issues": index_issues,
        "open_questions": open_questions,
        "counts": {"pages": n_pages, "frontmatter_issues": len(fm_bad),
                   "broken_links": len(broken), "orphans": len(orphans),
                   "index_issues": len(index_issues)},
    }


def fmt_fm_reason(reason: str) -> str:
    if reason == "no_fm":
        return MSG["reason_no_fm"]
    if reason.startswith("missing:"):
        return MSG["reason_missing"] + reason.split(":", 1)[1]
    return reason


def print_report(r: dict) -> None:
    s = r["scale"]
    print(MSG["scale_over"].format(**s) if s["over"] else MSG["scale_ok"].format(**s))
    c = r["counts"]
    print(MSG["summary"].format(fm=c["frontmatter_issues"], bl=c["broken_links"],
                                orph=c["orphans"], ix=c["index_issues"]))
    if r["frontmatter_issues"]:
        print("\n" + MSG["fm"])
        for it in r["frontmatter_issues"]:
            print(f"{MSG['err_prefix']}{it['page']} — {fmt_fm_reason(it['reason'])}")
    if r["broken_links"]:
        print("\n" + MSG["broken"])
        for it in r["broken_links"]:
            print(f"{MSG['err_prefix']}{it['page']} → {it['target']}")
    if r["orphans"]:
        print("\n" + MSG["orphans"])
        for it in r["orphans"]:
            print(MSG["orphan_mark"] + it)
    if r["index_issues"]:
        print("\n" + MSG["index"])
        for it in r["index_issues"]:
            kind = {"dead": MSG["idx_dead"], "missing": MSG["idx_missing"],
                    "count": MSG["idx_count"], "absent": MSG["idx_absent"]}.get(it["kind"], it["kind"])
            print(f"{MSG['err_prefix']}{kind}: {it['detail']}")
    oq = r["open_questions"]
    if oq:
        total = sum(len(v) for v in oq.values())
        print("\n" + MSG["openq"].format(n=total, m=len(oq)))
        shown = 0
        for rel, items in oq.items():
            for it in items:
                if shown >= 50:
                    print(MSG["openq_more"].format(n=total - shown))
                    break
                print(f"  ? {rel} — {it}")
                shown += 1
            if shown >= 50:
                break
    if not (r["frontmatter_issues"] or r["broken_links"] or r["orphans"] or r["index_issues"]):
        print("\n" + MSG["all_green"])
    print(MSG["evidence_hint"])


def main() -> int:
    ap = argparse.ArgumentParser(description="知识库校验(见 AGENTS.md §4)")
    ap.add_argument("--root", default=None, help="KB 根目录(默认脚本上一级)")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--count", action="store_true", help="只报规模哨兵")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    kb = root / KB_DIR
    if not kb.exists():
        print(MSG["kb_missing"].format(kb=kb), file=sys.stderr)
        return 2

    if args.count:
        n = len(list(kb.rglob("*.md")))
        over = n > THRESHOLD
        if args.json:
            print(json.dumps({"pages": n, "threshold": THRESHOLD, "over": over},
                             ensure_ascii=False))
        else:
            print(MSG["scale_short_over"].format(n=n, t=THRESHOLD) if over
                  else MSG["scale_short_ok"].format(n=n, t=THRESHOLD))
        return 0

    r = lint(root)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print_report(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
