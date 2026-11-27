# PolicyGraphRAG

面向政策文本研究的本地知识图谱、混合检索与制图工作台。

**公开源代码发行版 · MIT · Python 3.9+ · 默认流程仅依赖标准库。**

从政策文本提取带原文位置的实体候选，构建可追溯图谱，组合文本、实体邻域与社区检索，并生成证据报告、研究图表和标准网络文件。支持研究者已有编码与关系表接入，研究分析可通过六个 Skills 组合。

0.3.0 增加研究工作流：语料质量检查、有向与正负关系网络、分组统计比较、主题一致性和检索消融评测。

## 快速开始

克隆仓库并运行：

```sh
git clone https://github.com/runzhengzhen/PolicyGraphRAG.git
cd PolicyGraphRAG
python3 -m policygraph --version
sh run_demo.sh
python3 -m unittest discover -s tests -v
```

结果位于 `outputs/demo/`：`evidence-report.html`、`figures/*.svg` 和 `network/network.graphml`、`network/network.gexf`。`outputs/relations/` 展示已有关系表的接入，`outputs/research-study/study.html` 汇集质量检查、分组比较和检索评测。所有演示政策均为合成文本。

需要安装命令行入口时：

```sh
python3 -m pip install .
policygraph --help
```

基础安装和演示不需要密钥、数据库或模型下载。`--community auto` 在有 igraph 时使用 Leiden，否则明确记录为连通分量；需要保证 Leiden 时安装可选依赖并显式选择：

```sh
python3 -m pip install '.[graph]'
policygraph build --input examples/policies.jsonl --output outputs/leiden --community leiden
```

## 一条命令完成研究工作流

```sh
policygraph study --input examples/research-policies.jsonl --output outputs/my-study --namespace study --group-field cohort --left A --right B --queries examples/retrieval-judgments.jsonl --k 3
```

打开 `outputs/my-study/study.html` 查看结果。工作流生成证据图谱、重复与模板检查、显式关系指标、分组覆盖率和 Wilson 区间、Fisher 检验与 BH 校正、社区实体 NPMI、四种检索模式的 Recall／MRR／nDCG，以及可校验的运行清单。再次运行复用内容缓存。

`metadata` 保存研究分组，`relevance` 保存检索问题的相关性标注。输入格式、独立命令和统计口径见 [研究工作流](docs/RESEARCH.md)。从本地研究资产提炼的能力见 [能力整合记录](docs/CAPABILITY_INTEGRATION.md)。

## 分析自己的语料

支持 UTF-8 TXT、TXT 目录，以及每行包含 `id,text` 的 JSONL；可加 `title,date`。也支持 TopicGPT 的 `doc_id,para_id,text` 段落格式。

```sh
policygraph build --input examples/policies.jsonl --output outputs/my-study --aliases config/aliases.json
policygraph query --graph outputs/my-study/graph.json --question '数字教材与出版质量' --mode hybrid --output outputs/my-study/query.json
policygraph report --graph outputs/my-study/graph.json --query-result outputs/my-study/query.json --output outputs/my-study/report.html
policygraph analyze --graph outputs/my-study/graph.json --kind evolution --output outputs/my-study/evolution.json
policygraph plot --graph outputs/my-study/graph.json --output outputs/my-study/figures
policygraph export-network --graph outputs/my-study/graph.json --output outputs/my-study/network
```

`data/`、`outputs/`、密钥和数据库已加入 `.gitignore`，方便分别管理源代码、研究输入和分析结果。

## 复用已有编码与关系

```sh
policygraph import-gtflow --directory /path/to/your/completed-coding --output outputs/coding.jsonl
policygraph build --input outputs/coding.jsonl --output outputs/coded-study
policygraph import-relations --input examples/relations.csv --output outputs/relations/input.jsonl
policygraph build --input outputs/relations/input.jsonl --output outputs/relations
```

GTFlow 导入器核对段落与证据编号。关系表导入保留方向、极性、立场标签和连续原文引句；相同实体对的正、负关系分别保存。字段见 [输入与关系格式](docs/INPUTS.md)。AMR、语义框架或人工编码结果均可整理为该格式接入。

## 检索链路与缓存

- `vector`：字符 TF-IDF 稀疏向量检索。
- `local`：实体邻域的原文证据检索。
- `global`：提取式社区摘要与覆盖证据检索。
- `dense`：可选语义向量检索。
- `hybrid`：RRF 融合可用通道。

PageRank 与 Leiden 使用无向加权共现投影；显式关系另行保留方向和标签。`path` 返回带证据的图关联路径。内容缓存复用抽取、向量和摘要，图投影及社区发现全量重算。

批量查询可用 Python API `RetrievalIndex(graph).search(...)`，多次查询共用文本索引、社区索引与邻接表。`evaluate` 对四种离线检索模式按政策去重评测，索引构建耗时单独记录。

已有完整本地 SentenceTransformer 模型时，可安装 `.[local-models]`，用 `build --local-embedding-model /path/to/model` 编码，再用 `query --dense-query` 检索。只接受本地目录，不自动下载模型。显式 `--llm-model` / `--embedding-model` 才启用在线接口，环境变量名见 `.env.example`；程序不会自动加载该文件。

## Neo4j 与 Skills

`policygraph export-neo4j --graph outputs/demo/graph.json --output outputs/neo4j` 生成离线 payload 和参数化 Cypher。实际写库需可选 `.[neo4j]`、环境变量和显式 `--apply`；采用独立 snapshot 的 MERGE，保留历史记录。

`skills/` 提供文本编码、工具识别、主体分析、主题演化、关系分析和工作流入口六个可迁移技能。运行 `python3 scripts/install_skills.py` 可安装；已存在且内容不同的同名技能会保留。

## 项目组成与验证

仓库包含核心代码、测试、文档、Skills、合成示例和发布脚本。可选依赖与方法参考见 [第三方说明](THIRD_PARTY_NOTICES.md)，算法细节见 [实现说明](docs/IMPLEMENTATION.md)，已完成检查见 [发布验证](docs/RELEASE_VALIDATION.md)。

```sh
python3 scripts/check_release.py
python3 scripts/build_release.py
```

第一条检查公开文件范围、凭据形态和本机绝对路径；第二条生成带 SHA-256 清单的公开源码 ZIP。Python 的 wheel/sdist 构建及 CI 见 [贡献与发布](CONTRIBUTING.md)。
