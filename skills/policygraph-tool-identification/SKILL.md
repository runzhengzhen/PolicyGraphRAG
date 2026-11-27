---
name: policygraph-tool-identification
description: 汇总政策工具候选并通过原文证据核验，支持自定义工具词典。
---

在含 pyproject.toml 和 policygraph/ 的工程目录运行 `python3 -m policygraph`，或使用已安装的 `policygraph`。先读 README.md 和 docs/INPUTS.md。输入与产物由使用者提供，本技能不假设存在任何私有研究目录。

用analyze --kind tools汇总tool实体，再query查看原文。正式分类应以研究码本为准；用build --lexicon提供四类词典。禁止、培训、披露等只是词典线索，不能直接推导供给/需求/环境型分类或工具效果。

默认本地离线工作；在线模型需任务明确需要并显式指定。保留输入来源、原文块ID、模式与覆盖范围。输出到独立目录，不覆盖原语料；公开产物前检查其中的原文权限。
