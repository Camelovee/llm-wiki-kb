# 评测现场构造说明(v3)

每个用例的现场由 `scripts/init_kb.py` 生成,再注入本目录的 fixture:

## eval-0(初始化,无 fixture)

代理直接执行,无需预置。

## eval-1(摄取)

```bash
python3 scripts/init_kb.py <run>/KB --topic "大模型推理优化"
python3 <run>/KB/工具/清单.py --update                     # 先写基线(不含文章)
mkdir -p <run>/KB/原始资料/推理优化
cp evals/fixtures/eval-1-article-kv-cache.md <run>/KB/原始资料/推理优化/
```

## eval-2(体检)

```bash
python3 scripts/init_kb.py <run>/KB --topic "分布式系统"
cp -R evals/fixtures/eval-2-pages/. <run>/KB/知识库/
```

## eval-3(批量摄取)

```bash
python3 scripts/init_kb.py <run>/KB --topic "大模型推理优化"
python3 <run>/KB/工具/清单.py --update
mkdir -p <run>/KB/原始资料/推理优化
cp evals/fixtures/eval-1-article-kv-cache.md \
   evals/fixtures/eval-3-article-speculative.md \
   evals/fixtures/eval-3-article-continuous-batching.md \
   <run>/KB/原始资料/推理优化/
```

## 验收口径

- 机械预筛:`校验.py` 0/0/0/0(frontmatter / 断链 / 孤儿 / 索引)。
- 事实保真:`证据.py` 证据错误为 0(疑点由人裁决)。
- 溯源:全部知识页带 `raw` 字段(对话决策填 `[对话]`)。
