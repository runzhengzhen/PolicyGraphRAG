---
name: policygraph-actor-analysis
description: 分析政策主体候选、证据覆盖和图中关联中心性。
---

在含 pyproject.toml 和 policygraph/ 的工程目录运行 `python3 -m policygraph`，或使用已安装的 `policygraph`。先读 README.md 和 docs/INPUTS.md。输入与产物由使用者提供，本技能不假设存在任何私有研究目录。

用analyze --kind actors检查actor覆盖与PageRank，再query --mode local查看原文。通过显式类型别名表归并同义名称，遇同名异型保留类型。角色随上下文变化，应复核；PageRank只反映共现投影中的关联中心性。

默认本地离线工作；在线模型需任务明确需要并显式指定。保留输入来源、原文块ID、模式与覆盖范围。输出到独立目录，不覆盖原语料；公开产物前检查其中的原文权限。
