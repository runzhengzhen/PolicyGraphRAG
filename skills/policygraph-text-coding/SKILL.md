---
name: policygraph-text-coding
description: 对政策文本做可回溯实体候选标注，或导入已有GTFlow定性编码。
---

在含 pyproject.toml 和 policygraph/ 的工程目录运行 `python3 -m policygraph`，或使用已安装的 `policygraph`。先读 README.md 和 docs/INPUTS.md。输入与产物由使用者提供，本技能不假设存在任何私有研究目录。

区分四类实体候选与定性研究编码。build做候选实体标注；已有GTFlow结果先import-gtflow再build。检查.audit.json中的覆盖与未解析ID，优先JSONL开放编码。只有逐字引句匹配的编码进入research_code，不把词典命中写成已完成扎根理论编码。

默认本地离线工作；在线模型需任务明确需要并显式指定。保留输入来源、原文块ID、模式与覆盖范围。输出到独立目录，不覆盖原语料；公开产物前检查其中的原文权限。
