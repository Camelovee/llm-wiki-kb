#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""证据.py 的单测(移植自 Astro-Han 的 test_check_evidence,适配 v3 中文格式)。

跑法: python3 tests/test_evidence.py   (或 python3 -m unittest discover tests)
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "assets" / "工具" / "证据.py"

RAW_CONTENT = """---
source: https://example.com/ghostty
collected: 2026-04-17
---

Ghostty reached 42K stars on GitHub in April 2026.
The maintainer said "the terminal should feel invisible to users" in the interview.
Daily active users reached 10,000 by March.
"""

ARTICLE_CONTENT = """---
title: Ghostty
description: 终端模拟器。
updated: 2026-04-17
raw: [原始资料/ai-research/ghostty.md]
sources: [Example, 2026-04-16]
---

# Ghostty

## 概览

Ghostty has 42K stars and reached 10,000 daily active users.
维护者说「终端对用户应该无感」。

## 增长

Forks grew to 3,020 last week.
Install with `--limit 9000` after downloading.

```
example 78K and 9,999
```

> **Status: Outdated** (2026-07-23)
> 此后 forks 情况已变化。
"""


def fm(**fields) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


class EvidenceCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "原始资料" / "t").mkdir(parents=True)
        (self.root / "知识库" / "t").mkdir(parents=True)
        (self.root / "知识库" / "索引.md").write_text("# 索引\n", encoding="utf-8")
        (self.root / "知识库" / "维护日志.md").write_text("", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def add_raw(self, name: str, body: str):
        (self.root / "原始资料" / "t" / name).write_text(body, encoding="utf-8")

    def add_article(self, name: str, body: str):
        (self.root / "知识库" / "t" / name).write_text(body, encoding="utf-8")

    def run_script(self, *args) -> str:
        r = subprocess.run([sys.executable, str(SCRIPT), str(self.root), *args],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout


class CoreBehavior(EvidenceCase):
    def test_flags_value_absent_from_raw(self):
        self.add_raw("a.md", "# 源\n\n真实数字是 5,000。\n")
        self.add_article("a.md", fm(title="A", description="d", updated="2026-10-21",
                                    raw=["原始资料/t/a.md"])
                         + "# A\n\n文章写的是 9,000。\n")
        out = self.run_script()
        self.assertIn("9,000", out)
        self.assertNotIn("5,000", out)

    def test_passes_values_and_quotes_present_in_raw(self):
        self.add_raw("ghostty.md", RAW_CONTENT)
        self.add_article("ghostty.md", ARTICLE_CONTENT)
        out = self.run_script()
        self.assertIn("保真疑点\n\n(无)", out)
        # 代码块与 Status 块里的字面量被跳过
        self.assertNotIn("78K", out)
        self.assertNotIn("2026-07-23", out)

    def test_chinese_corner_quote_supported(self):
        self.add_raw("q.md", "# 源\n\n维护者说「终端对用户应该无感」。\n")
        self.add_article("q.md", fm(title="Q", description="d", updated="2026-10-21",
                                    raw=["原始资料/t/q.md"])
                         + "# Q\n\n维护者说「终端对用户应该无感」。\n")
        self.assertIn("保真疑点\n\n(无)", self.run_script())

    def test_frontmatter_dates_are_not_candidates(self):
        # frontmatter 里的 updated/collected 是登记信息,不该产生候选
        self.add_raw("a.md", "# 源\n\n正文没有任何数字。\n")
        self.add_article("a.md", fm(title="A", description="d", updated="2026-10-21",
                                    raw=["原始资料/t/a.md"], created="2026-10-20")
                         + "# A\n\n纯文字。\n")
        self.assertIn("保真疑点\n\n(无)", self.run_script())

    def test_small_plain_integers_are_out_of_scope(self):
        self.add_raw("a.md", "# 源\n\n他有 3 台机器。\n")
        self.add_article("a.md", fm(title="A", description="d", updated="2026-10-21",
                                    raw=["原始资料/t/a.md"])
                         + "# A\n\n他有 5 台机器。\n")  # 小整数不查
        self.assertIn("保真疑点\n\n(无)", self.run_script())

    def test_missing_raw_is_evidence_error(self):
        self.add_article("a.md", fm(title="A", description="d", updated="2026-10-21")
                         + "# A\n\n没有任何来源。\n")
        out = self.run_script()
        self.assertIn("非归档页缺少 raw 字段", out)

    def test_archived_page_without_raw_is_legitimate(self):
        self.add_article("a.md", fm(title="A", description="d", updated="2026-10-21",
                                    archived="2026-10-21")
                         + "# A\n\n提问归档页。\n")
        self.assertIn("证据错误\n(无)", self.run_script())

    def test_broken_raw_link_is_evidence_error(self):
        self.add_article("a.md", fm(title="A", description="d", updated="2026-10-21",
                                    raw=["原始资料/t/不存在.md"])
                         + "# A\n\n内容。\n")
        self.assertIn("raw 链接无法解析", self.run_script())

    def test_raw_link_escaping_raw_dir_is_evidence_error(self):
        self.add_article("a.md", fm(title="A", description="d", updated="2026-10-21",
                                    raw=["知识库/t/a.md"])
                         + "# A\n\n内容。\n")
        self.assertIn("逃出", self.run_script())



    def test_non_file_raw_source_is_legitimate(self):
        self.add_article("a.md", fm(title="A", description="d", updated="2026-10-21",
                                    raw=["对话"])
                         + "# A\n\n对话中产生的决策。\n")
        self.assertIn("证据错误\n(无)", self.run_script())

class Inventory(EvidenceCase):
    def test_unreferenced_raw_reported(self):
        self.add_raw("lonely.md", "# 源\n\n从没被编译。\n")
        out = self.run_script()
        self.assertIn("原始资料/t/lonely.md", out)

    def test_no_material_disposition_suppresses_report(self):
        self.add_raw("nothing.md", "# 源\n\n无新知。\n")
        (self.root / "知识库" / "维护日志.md").write_text(
            "## [2026-10-21] ingest | no material: 原始资料/t/nothing.md\n"
            "- Disposition: No material\n", encoding="utf-8")
        out = self.run_script()
        self.assertIn("未被引用的源文件\n(无)", out)


if __name__ == "__main__":
    unittest.main()
