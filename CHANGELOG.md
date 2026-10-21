# Changelog

## v1.1.0 — SKILL.md 操作手册化

对标 Astro-Han 的 SKILL.md 把本技能从「纲领」扩写为「操作手册」:

- Ingest 全链编号步骤:Fetch(文件命名/元数据头)、Triage 四处置定义、Compile 落位判定树、Cascade 级联与 Status 块精确格式、收尾顺序依赖与日志 code block(含 No material 机器可读变体)。
- 新增 Lint 三层权威全展开与**人工裁决清单**(跨页矛盾/无 Status 旧主张/缺冲突标注等 9 类),Post-Lint 日志格式。
- 新增 Conventions:日期口径、链接口径(库内文件相对 vs 对话根相对)、**谁写哪些文件矩阵**。
- Grounding Invariant 增加覆盖边界说明(机查候选集封闭,小整数/货币/文字日期归编译纪律与人工)。
- 明确 SKILL(怎么做)与库 AGENTS.md(规则真源)的分工与冲突优先级。

## v1.0.0 — 首个版本

按 Andrej Karpathy 的 LLM Wiki 工作流初始化并维护个人主题知识库的纯中文 Agent 技能。

- **Grounding Invariant + `工具/证据.py`**:知识页里每个承重事实(数字/日期/直接引语)都能在该页 `raw` 字段链接的源文件里逐字找到;脚本全库机械复核(带 12 项单测),疑点列给人裁决——正面防住「幻觉事实被烤成知识」。
- **来源保真纪律**:写值前先在原文 locate;原文 42K 就写 42K;推导值展开成分量;找不到就不写精确形式。
- **Triage 四处置**:每篇来源先判定 New / Update / Disputed / No material;无新知只存源记日志,不硬写文章。
- **级联更新 + 主张版本**:新源入库全文检索涟漪效应;被取代的主张标 `Status: Outdated`,源冲突标 `Status: Disputed`,绝不悄悄改写历史。
- **topic 布局**:`原始资料/<主题>/` + `知识库/<主题>/` 一层;`决策/` 为约定式 Promote 落点。
- **脚本维护的唯一索引**:索引与仪表盘由 `索引.py` 机械重建;`校验.py` 0/0/0/0 抓 frontmatter/断链/孤儿/索引四类漂移。
- **懒检测增量清单**:`清单.py` 哈希基线检出待编译源;**待查问题聚合**驱动知识库生长;批量模式与 Research 调研模式;规模哨兵 200 页。
- 评测驱动打磨:subagent 对照评测(init/ingest/lint/batch),用例与现场在 `evals/`。

### 致谢

- 方法论源头:[Andrej Karpathy 的 llm-wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- Grounding Invariant、保真纪律与 Triage 移植自 [Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki)(MIT)
