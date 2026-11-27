---
name: policygraph-topic-evolution
description: 依据显式政策日期统计社区覆盖，核对日期缺失与主题归纳边界。
---

在含 pyproject.toml 和 policygraph/ 的工程目录运行 `python3 -m policygraph`，或使用已安装的 `policygraph`。先读 README.md 和 docs/INPUTS.md。输入与产物由使用者提供，本技能不假设存在任何私有研究目录。

先analyze --kind evolution核对undated_documents与documents_without_community。只使用输入date或发布日期，不从正文年份、路径或修改时间猜日期。plot可输出年份覆盖SVG。同一篇政策可跨社区重复计数；不称为动态主题演化模型。
analyze --kind coherence按文档共现计算社区实体NPMI，区分实体与分词主题词口径。audit登记日期质量及重复模板。compare按metadata分组比较实体覆盖，Wilson区间分别描述两组比例，Fisher与BH检验口径见docs/RESEARCH.md。

默认本地离线工作；在线模型需任务明确需要并显式指定。保留输入来源、原文块ID、模式与覆盖范围。输出到独立目录，不覆盖原语料；公开产物前检查其中的原文权限。
