---
name: policygraph-pipeline
description: 编排政策语料接入、证据图谱、混合检索、制图与研究报告的公开工作流。
---

在含 pyproject.toml 和 policygraph/ 的工程目录运行 `python3 -m policygraph`，或使用已安装的 `policygraph`。先读 README.md 和 docs/INPUTS.md。输入与产物由使用者提供，本技能不假设存在任何私有研究目录。

原始TXT/JSONL用build；已有定性编码先import-gtflow，关系CSV/TSV先import-relations，再build。用query检索，report生成证据报告，plot生成SVG，export-network生成GraphML/GEXF。需要实体/工具/日期分析用analyze。可组合其他policygraph技能。
默认词典是候选抽取，PageRank与社区为共现投影；global是提取式摘要检索。缓存复用抽取/向量/摘要，全图社区仍重算。不得把本包称为完整官方GraphRAG、完整AMR算法或已验证复杂推理系统。

默认本地离线工作；在线模型需任务明确需要并显式指定。保留输入来源、原文块ID、模式与覆盖范围。输出到独立目录，不覆盖原语料；公开产物前检查其中的原文权限。
