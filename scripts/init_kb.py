#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
init_kb.py — 按卡帕西 LLM Wiki 架构初始化一座新主题知识库(v3,纯中文版)

从 skill 的 assets/ 复制骨架(AGENTS.md / README / 索引 / 仪表盘 / 模板 / 四个工具),
替换 {{TOPIC}} {{KB_ROOT}} {{DATE}} 占位符,写入维护日志首行,并写入首份源清单基线。

布局:topic 为主——原始资料/<主题>/ 与 知识库/<主题>/ 在编译时按需创建;
知识层保留约定式 决策/ 目录作 Promote 落点。

用法:
  python3 init_kb.py <目标目录> --topic <主题名> [--date YYYY-MM-DD]

目标目录已存在且非空时拒绝执行。AGENTS.md §8 领域约定为占位符,
由 LLM 在脚本运行后按主题补写(建议整段复制或正则替换,占位段含全角标点)。
"""

import argparse
import datetime
import shutil
import subprocess
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"

RAW = "原始资料"
KB = "知识库"
TOP_DIRS = ["模板", "工具"]
KB_TOPICS = ["决策"]
RAW_SUBDIRS = ["附件"]
NAV = ["索引.md", "仪表盘.md", "维护日志.md"]
TOOLS = ["清单.py", "校验.py", "索引.py", "证据.py"]
LOG_SEED = "- {date} · 知识库初始化(llm-wiki-obsidian 脚手架)"

STATIC_FILES = ["知识库/索引.md", "模板/笔记模板.md", "模板/来源模板.md", "模板/主题枢纽模板.md"]
TEMPLATES = {
    "AGENTS.md.tmpl": "AGENTS.md",
    "README.md.tmpl": "README.md",
    "知识库/仪表盘.md.tmpl": "知识库/仪表盘.md",
}


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def main() -> int:
    ap = argparse.ArgumentParser(description="初始化卡帕西 LLM Wiki 架构知识库")
    ap.add_argument("target", help="新库根目录(不存在则创建)")
    ap.add_argument("--topic", required=True, help="主题名,如「分布式系统」")
    ap.add_argument("--date", default=datetime.date.today().isoformat(),
                    help="写入模板的日期(默认今天)")
    args = ap.parse_args()

    root = Path(args.target).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        fail(f"目标目录已存在且非空: {root}")
    if not ASSETS.is_dir():
        fail(f"assets 目录缺失: {ASSETS}")

    root.mkdir(parents=True, exist_ok=True)
    subs = {"{{TOPIC}}": args.topic, "{{KB_ROOT}}": str(root), "{{DATE}}": args.date}

    for d in [RAW] + [f"{RAW}/{c}" for c in RAW_SUBDIRS] + [KB] + \
             [f"{KB}/{c}" for c in KB_TOPICS] + TOP_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
        (root / d / ".gitkeep").touch()

    for rel in STATIC_FILES:
        shutil.copy2(ASSETS / rel, root / rel)

    for tmpl, out in TEMPLATES.items():
        text = (ASSETS / tmpl).read_text(encoding="utf-8")
        for k, v in subs.items():
            text = text.replace(k, v)
        (root / out).write_text(text, encoding="utf-8")

    for name in TOOLS:
        shutil.copy2(ASSETS / "工具" / name, root / "工具" / name)

    (root / KB / "维护日志.md").write_text(LOG_SEED.format(date=args.date) + "\n",
                                           encoding="utf-8")

    r = subprocess.run([sys.executable, str(root / "工具" / "清单.py"), "--update"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"WARN: 清单基线写入失败(不影响骨架): {r.stderr.strip()}", file=sys.stderr)

    print(f"✅ 已初始化知识库: {root}")
    print(f"   主题: {args.topic}")
    print("   下一步: ① LLM 补写 AGENTS.md §7 领域约定(DOMAIN-RULES 占位处)")
    print("            ② 用 Obsidian「打开文件夹作为库」选择该目录")
    return 0


if __name__ == "__main__":
    sys.exit(main())
