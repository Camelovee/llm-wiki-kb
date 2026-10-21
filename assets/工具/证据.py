#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
证据.py — Grounding Invariant 的机械复核器(移植自 Astro-Han/karpathy-llm-wiki 的
check_evidence.py,适配中文库布局与 YAML frontmatter;MIT,感谢原作者)

核心不变式:知识页里每个承重事实(具体数字、ISO 日期、直接引语)都必须能在该页
Raw 字段链接的源文件正文里逐字找到。编译时「先定位后落笔」覆盖其余形式,
本脚本把可机械检查的部分全库复核一遍(秒级,无增量状态)。

三次扫描,只报告、绝不改文件:
1. **保真疑点**——从每篇文章提取候选字面量(带 K/M/B/% 后缀的数字、千分位、
   小数、4 位以上整数、ISO 日期、15 字符以上的直接引语含 "" / 「」 / 块引用),
   在 Raw 源正文里逐字核查;未命中列为疑点。推导值、产品名、刻意转写会误报——
   裁决归读者,不归脚本。
2. **证据错误**——无法验证的文章:非归档页缺 Raw 字段、Raw 链接不存在、
   Raw 链接逃出 原始资料/(证据必须存在于不可变的源层)。
3. **源清单**——没有任何文章 Raw 字段引用的源文件(已在维护日志登记
   「no material」的除外)。

退出码不带信息,报告即接口。
用法: python3 证据.py [KB根] [文章.md ...]   # 默认全库;文章路径可绝对或相对库根
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

KB_DIR = "知识库"
RAW_DIR = "原始资料"
INDEX_NAME = "索引.md"
LOG_NAME = "维护日志.md"

NUMBER_TOKEN_RE = re.compile(
    r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)*(?:\s*[KMB%](?![A-Za-z]))?"
    r"|\d+(?:\.\d+)*(?:\s*[KMB%](?![A-Za-z]))?)(?![A-Za-z])"
)
SUFFIX_RE = re.compile(r"[KMB%]$")
DATE_RE = re.compile(r"\d{4}-\d{2}(?:-\d{2})?")
QUOTE_RES = [re.compile(r'"([^"\n]*)"'), re.compile(r"“([^”\n]*)”"),
             re.compile(r"「([^」\n]*)」")]
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
STATUS_LINE_RE = re.compile(r"^>\s*\*\*Status:")
NO_MATERIAL_HEADING_RE = re.compile(
    r"^##\s*\[[^\]]*\]\s*ingest\s*\|\s*no material:\s*(\S+)", re.IGNORECASE)
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
FENCE_CLOSE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
WS_RE = re.compile(r"\s+")

SKIP_FILES = {INDEX_NAME, LOG_NAME, "仪表盘.md"}


@dataclass(frozen=True)
class Candidate:
    kind: str   # "number" | "date" | "quote"
    value: str


def normalize(text: str) -> str:
    return WS_RE.sub(" ", text).strip()


def fence_opener(line: str):
    m = FENCE_OPEN_RE.match(line)
    if not m:
        return None
    marker, info = m.groups()
    if marker[0] == "`" and "`" in info:
        return None
    return marker[0], len(marker)


def is_fence_closer(line: str, char: str, length: int) -> bool:
    m = FENCE_CLOSE_RE.match(line)
    return bool(m and m.group(1)[0] == char and len(m.group(1)) >= length)


def strip_fences(text: str) -> str:
    """移除围栏代码块(其内字面量不算事实陈述)。"""
    out = []
    fence_char = None
    fence_len = 0
    for line in text.splitlines():
        if fence_char:
            if is_fence_closer(line, fence_char, fence_len):
                fence_char = None
            continue
        opener = fence_opener(line)
        if opener:
            fence_char, fence_len = opener
            continue
        out.append(line)
    return "\n".join(out)


def strip_frontmatter(text: str) -> str:
    """frontmatter 是登记元数据,不是事实陈述;其内的日期/数字不该参与保真核查。"""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4:]


def strip_noise(text: str) -> str:
    text = INLINE_CODE_RE.sub(" ", text)
    text = LINK_RE.sub(r"\1", text)
    return text


def keep_number(token: str) -> bool:
    token = token.strip()
    if SUFFIX_RE.search(token) or "," in token or "." in token:
        return True
    return len(token) >= 4


def extract_numeric_date_candidates(line: str) -> list[Candidate]:
    line = strip_noise(line)
    date_matches = list(DATE_RE.finditer(line))
    candidates = [Candidate("date", m.group(0)) for m in date_matches]
    number_text = list(line)
    for match in date_matches:
        number_text[match.start():match.end()] = " " * (match.end() - match.start())
    candidates.extend(
        Candidate("number", m.group(0))
        for m in NUMBER_TOKEN_RE.finditer("".join(number_text))
        if keep_number(m.group(0))
    )
    return candidates


def extract_candidates(text: str) -> list[Candidate]:
    """候选集是封闭的、有意冻结的:数字(带后缀/千分位/小数/4 位+)、ISO 日期、
    15 字符以上引语(双引号/中文引号/整段块引用)。小整数与奇形形式
    (符号、货币、文字日期)刻意不查——交给编译时的「先定位后落笔」与人工裁决。"""
    text = strip_frontmatter(strip_fences(text))
    candidates: list[Candidate] = []
    skip_status_block = False
    blockquote: list[str] = []
    paragraph: list[str] = []

    def flush_blockquote():
        if blockquote:
            joined = normalize(" ".join(blockquote))
            if len(joined) >= 15:
                candidates.append(Candidate("quote", joined))
            blockquote.clear()

    def flush_paragraph():
        if paragraph:
            joined = normalize(" ".join(paragraph))
            for quote_re in QUOTE_RES:
                candidates.extend(
                    Candidate("quote", m.group(1))
                    for m in quote_re.finditer(joined)
                    if len(m.group(1).strip()) >= 15
                )
            paragraph.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if STATUS_LINE_RE.match(stripped):
            # Status 块(Outdated/Disputed)是版本标注,不是事实,跳过
            flush_blockquote()
            flush_paragraph()
            skip_status_block = True
            continue
        if skip_status_block:
            if stripped.startswith(">"):
                continue
            skip_status_block = False
        if stripped.startswith(">"):
            flush_paragraph()
            content = strip_noise(stripped.lstrip(">").strip())
            blockquote.append(content)
            candidates.extend(extract_numeric_date_candidates(content))
            continue
        flush_blockquote()
        if not stripped:
            flush_paragraph()
            continue
        line = strip_noise(line)
        candidates.extend(extract_numeric_date_candidates(line))
        paragraph.append(line)
    flush_blockquote()
    flush_paragraph()
    seen = set()
    unique = []
    for candidate in candidates:
        value = candidate.value.strip().strip(".,;:()[]")
        candidate = Candidate(candidate.kind, value)
        if value and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def parse_frontmatter(text: str) -> dict:
    """极简 frontmatter 解析:顶层 key: value + 列表(key: [a, b] 或缩进 - item)。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm = {}
    lines = text[3:end].strip("\n").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        m = re.match(r"^([A-Za-z_\-]+)\s*:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, value = m.group(1).lower(), m.group(2).strip()
        if value.startswith("[") and value.endswith("]"):
            fm[key] = [v.strip().strip('"').strip("'")
                       for v in value[1:-1].split(",") if v.strip()]
        elif value == "":
            items = []
            j = i + 1
            while j < len(lines) and re.match(r"^\s+-\s+", lines[j]):
                items.append(re.sub(r"^\s+-\s+", "", lines[j]).strip().strip('"').strip("'"))
                j += 1
            if items:
                fm[key] = items
                i = j
                continue
            fm[key] = ""
        else:
            fm[key] = value.strip('"').strip("'")
        i += 1
    return fm


def raw_links_of(article_text: str) -> list[str]:
    """frontmatter raw 字段里的文件链接(根相对 .md 路径)。
    非文件来源(如 [source:对话]、[对话])是合法来源标注,不属于证据核查范围。"""
    raw = parse_frontmatter(article_text).get("raw", [])
    if isinstance(raw, str):
        raw = [raw]
    return [r for r in raw if r.lower().endswith(".md")]


def has_any_raw_source(article_text: str) -> bool:
    raw = parse_frontmatter(article_text).get("raw")
    return raw not in (None, "", [])


def contains(haystack: str, candidate: Candidate) -> bool:
    if candidate.kind == "quote":
        return candidate.value in haystack
    # 值必须独立成立,句读不算违规;YYYY-MM 不得充作完整 ISO 日期的前缀
    right = r"(?!-\d{2})" if candidate.kind == "date" and len(candidate.value) == 7 else ""
    pattern = (
        r"(?<![\d.,])" + re.escape(candidate.value) + right + r"(?![A-Za-z0-9]|[.,]\d|%)"
    )
    return re.search(pattern, haystack) is not None


def source_content(path: Path) -> str:
    """源文件正文(去掉 frontmatter/元数据头):登记信息(来源/收录日期)是簿记不是证据,
    让它参与匹配会使日期与年份假通过。"""
    return normalize(strip_frontmatter(path.read_text(encoding="utf-8")))


def check_article(article: Path, root: Path) -> tuple[list[str], list[str]]:
    """返回 (保真疑点, 证据错误)。"""
    text = article.read_text(encoding="utf-8")
    links = raw_links_of(text)
    if not links:
        fm = parse_frontmatter(text)
        if fm.get("archived"):
            return [], []   # 归档页(提问沉淀)无 Raw,合理豁免
        if has_any_raw_source(text):
            return [], []   # raw 均为非文件来源(如对话决策),无文件可核查
        return [], ["非归档页缺少 raw 字段"]
    raw_root = (root / RAW_DIR).resolve()
    raws = []
    errors = []
    for link in links:
        target = (root / link).resolve()
        if not target.is_relative_to(raw_root):
            errors.append(f"raw 链接逃出 {RAW_DIR}/: {link}")
        elif not target.is_file():
            errors.append(f"raw 链接无法解析: {link}")
        else:
            raws.append(source_content(target))
    misses = []
    if raws:
        for candidate in extract_candidates(text):
            candidate = Candidate(candidate.kind, normalize(candidate.value))
            if not any(contains(raw, candidate) for raw in raws):
                misses.append(candidate.value)
    return misses, errors


def iter_articles(kb_dir: Path):
    for path in sorted(kb_dir.rglob("*.md")):
        if path.relative_to(kb_dir).as_posix() not in SKIP_FILES:
            yield path


def no_material_paths(log_file: Path) -> set[str]:
    if not log_file.is_file():
        return set()
    paths = set()
    for line in strip_fences(log_file.read_text(encoding="utf-8")).splitlines():
        m = NO_MATERIAL_HEADING_RE.match(line)
        if m:
            paths.add(m.group(1).strip("`,;."))
    return paths


def referenced_raws(root: Path) -> set[Path]:
    referenced = set()
    for article in iter_articles(root / KB_DIR):
        for link in raw_links_of(article.read_text(encoding="utf-8")):
            referenced.add((root / link).resolve())
    return referenced


def unreferenced_raws(root: Path) -> list[str]:
    raw_dir = root / RAW_DIR
    if not raw_dir.is_dir():
        return []
    referenced = referenced_raws(root)
    disposed = no_material_paths(root / KB_DIR / LOG_NAME)
    missing = []
    for path in sorted(raw_dir.rglob("*.md")):
        if path.resolve() not in referenced \
                and path.relative_to(root).as_posix() not in disposed:
            missing.append(path.relative_to(root).as_posix())
    return missing


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[1]
    kb_dir = root / KB_DIR
    if not kb_dir.is_dir():
        print(f"{root} 下没有 {KB_DIR}/ 目录")
        return 1

    articles = []
    for arg in argv[2:]:
        path = Path(arg)
        if not path.is_absolute():
            path = root / path
        try:
            if path.resolve().relative_to(kb_dir).as_posix() in SKIP_FILES:
                print(f"警告: {arg} 是索引/日志文件,跳过", file=sys.stderr)
                continue
        except ValueError:
            pass
        if not path.is_file():
            print(f"警告: 文章不存在: {arg}", file=sys.stderr)
            continue
        articles.append(path)
    if len(argv) <= 2:
        articles = list(iter_articles(kb_dir))

    results = {article: check_article(article, root) for article in articles}

    def label(article: Path) -> Path:
        try:
            return article.resolve().relative_to(root)
        except ValueError:
            return article

    print("# 证据核查\n")
    print("## 保真疑点")
    suspect_count = 0
    for article, (misses, _) in results.items():
        if misses:
            print(f"\n{label(article)}")
            for miss in misses:
                print(f"- {miss}")
                suspect_count += 1
    if suspect_count == 0:
        print("\n(无)")

    print("\n## 证据错误")
    error_count = 0
    for article, (_, errors) in results.items():
        if errors:
            print(f"\n{label(article)}")
            for error in errors:
                print(f"- {error}")
                error_count += 1
    if error_count == 0:
        print("(无)")

    print("\n## 未被引用的源文件")
    unreferenced = unreferenced_raws(root)
    for path in unreferenced:
        print(f"- {path}")
    if not unreferenced:
        print("(无)")

    print(f"\n## 汇总\n{suspect_count} 条保真疑点, {error_count} 条证据错误, "
          f"{len(unreferenced)} 个未被引用的源文件")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
