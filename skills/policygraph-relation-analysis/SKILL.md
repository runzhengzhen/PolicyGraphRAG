---
name: policygraph-relation-analysis
description: 检索跨政策关联并接入带方向、极性、立场及证据的已有关系表。
---

在含 pyproject.toml 和 policygraph/ 的工程目录运行 `python3 -m policygraph`，或使用已安装的 `policygraph`。先读 README.md 和 docs/INPUTS.md。输入与产物由使用者提供，本技能不假设存在任何私有研究目录。

关系CSV/TSV先import-relations再build；检查.audit.json中未通过记录。保留源/目标、polarity、stance与原文引句，不凭A/B/N字母猜码本含义。query --mode hybrid融合检索；仅图含向量且需语义查询时加--dense-query。path为无向关联遍历，返回边保留方向，不能写成已验证多跳推理。export-network保留全图属性，plot只是选定节点的预览。Neo4j先离线export-neo4j，只有任务要求写库才选--apply。

默认本地离线工作；在线模型需任务明确需要并显式指定。保留输入来源、原文块ID、模式与覆盖范围。输出到独立目录，不覆盖原语料；公开产物前检查其中的原文权限。
