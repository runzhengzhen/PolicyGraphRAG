# 来源与第三方依赖

本发行版的 `policygraph/`、脚本、测试、文档、Skills 及合成示例采用根目录 MIT 许可。核心整合代码由本项目工作台代码整理，关系表导入、SVG 制图与标准图导出为本公开版编写。

## 可选依赖与方法参考

- igraph：可选 Leiden 社区发现依赖，按其 GNU GPL 许可独立分发；本发行包不包含其源码或二进制。https://igraph.org/python/
- Neo4j Python Driver：可选数据库客户端，Apache-2.0。https://github.com/neo4j/neo4j-python-driver
- sentence-transformers：可选本地向量编码依赖，Apache-2.0；相关运行依赖各有许可。模型权重需另行核实模型许可，本包不附带任何模型。https://github.com/UKPLab/sentence-transformers
- GraphRAG 的 local/global 检索概念参考 Microsoft 文档，检索链路由本项目自行实现。https://microsoft.github.io/graphrag/
- GTFlow 和 TopicGPT 仅作为外部结果格式适配对象，未打包其源码；其上游采用 MIT。源码、必要声明和引用应从相应项目取得，本项目格式适配不变更上游许可。

可选依赖的许可证不因根目录 MIT 而改变。默认标准库流程不依赖上述软件；选择安装 GPL 组件并重新分发组合软件时，应继续遵守相应条款。

## 外部研究格式参考

- soteu-narratives：叙事研究方法参考。https://github.com/pournaki/soteu-narratives ，论文：https://doi.org/10.1057/s41599-025-06017-x 。
- VerbAtlas：语义框架参考。https://verbatlas.org/ 。

以上外部研究代码和资源独立获取，按各自许可使用；本仓库提供编码结果接入格式。
