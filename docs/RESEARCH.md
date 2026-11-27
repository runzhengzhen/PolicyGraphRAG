# 研究工作流

`study` 串联语料接入、证据图谱、语料审查、关系指标、分组比较、主题一致性、检索评测与图表导出，默认全程离线。

```sh
python3 -m policygraph study --input examples/research-policies.jsonl --output outputs/study --namespace study --community components --group-field cohort --left A --right B --queries examples/retrieval-judgments.jsonl --k 3
```

入口为 `outputs/study/study.html`。`run-manifest.json` 保存版本、输入内容摘要、参数、缓存命中与逐产物 SHA-256。新目录首次运行，已有研究目录可复用缓存重跑；`status=completed` 表示完成，`running` 表示尚未完成。更换机器或输入文件位置时，namespace 和内容一致即可保留相同输入摘要。

## 分组比较

JSONL 添加 `"metadata":{"cohort":"A","country":"CN"}`，分组标签使用字符串。同一政策跨段落可以省略已有字段，填写时须一致。

```sh
python3 -m policygraph compare --graph outputs/study/graph.json --field cohort --left A --right B --output outputs/comparison
```

每个实体按独立政策计数，同篇政策多次出现计一次。输出分组篇数、覆盖率、右组减左组的覆盖率差值、各组 Wilson 95% 区间、双侧 Fisher 精确检验，以及对本次所有实体行统一计算的 Benjamini–Hochberg FDR。区间分别描述两组覆盖率。相应政策 ID 随每行导出，其他分组和缺失标签计入 excluded_documents。

`comparison.svg` 绘制两组覆盖率和区间，`comparison.csv` 可继续统计。研究抽样设计与重复模板可结合质量检查复核。

## 关系网络与主体焦点

```sh
python3 -m policygraph network --graph outputs/study/graph.json --layer explicit --output outputs/network-stats
python3 -m policygraph ego --graph outputs/study/graph.json --entity 作者 --direction out --radius 1 --layer explicit --output outputs/author-ego
```

网络层可选 `explicit`、`cooccurrence`、`all`。默认显式关系层保存方向、正负极性和立场。节点指标包括入向、出向、无向证据权重、正负证据量和邻居数。每条边以去重 `(doc_id,chunk_id)` 为权重，不同谓词或立场的边分别计数。

网络指标包括有向实体对密度、互惠率、弱连通分量和孤立点；全部实体均计入节点分母，自环从密度和互惠率中排除。按实体对、谓词和方向汇总正负证据，`signed_balance=(positive-negative)/(positive+negative)`；A/B/N 等立场标签保持原码本语义。

`ego` 按 `in/out/both` 和半径选取节点，再导出诱导子图。保留被选节点间的原始边方向，附原文证据、GraphML、GEXF 和最多60节点／45边的 SVG 预览；完整节点与边保存在网络文件中。

## 质量检查与模板组

```sh
python3 -m policygraph audit --graph outputs/study/graph.json --near-threshold 0.85 --max-pairs 200000 --output outputs/quality.json
python3 -m policygraph analyze --graph outputs/study/graph.json --kind coherence --output outputs/coherence.json
```

`audit` 检查文档、实体、边和社区引用，提及位置、连续引句、文本块长度与衔接，登记日期缺失和无实体文档。引用完整性失败时返回非零状态。日期接受四位年份或有效 ISO 日期。

文档经 NFKC、大小写和空白归一化后识别精确重复；字符5元组 Jaccard 识别相似文档，阈值图的连通分量形成模板候选组。每对相似度和成员 ID 用于模板敏感性分析选样。比较数超过 `--max-pairs` 时显式报错，可缩小语料或增大上限。

`coherence` 使用社区中 PageRank 最高的10个实体，在全语料上按文档出现计算实体对 NPMI。无共同文档记为 -1，两实体在全部文档出现记为 1；不足两个实体的社区记为 null，均值只包含可计算社区。

## 检索标注与消融评测

问题文件为 JSONL：

```json
{"id":"q1","question":"作者如何披露人工智能使用情况","relevance":{"B1":2,"B3":1}}
```

`relevance` 的键为唯一原始文档 ID 或完整命名空间 ID，值为 0–10 整数相关性等级。正等级参与 Recall、MRR 等计算，nDCG 使用 `2^grade-1` 增益；空对象表示语料没有答案。问题 ID、文档 ID 和等级在运行前核对。

```sh
python3 -m policygraph evaluate --graph outputs/study/graph.json --queries examples/retrieval-judgments.jsonl --modes vector,local,global,hybrid --k 3 --output outputs/evaluation.json
```

按每篇政策首次出现的位置去重，返回前 k 篇，计算 Recall@k、Precision@k、MRR@k、nDCG@k、命中率和每模式平均延迟。无答案问题单独计算无答案准确率；其余指标只对可回答问题做宏平均。未标注文档按等级0处理，返回不足 k 篇时 Precision 分母仍为 k。

索引构建时间单列；各模式查询延迟基于共用索引。评测检索完整候选块集合后按政策去重，评分顺序沿用检索实现。API `RetrievalIndex` 可用于其他批处理任务，使用期间保持图数据不变。

随仓库提供8条合成政策和6个问题，用于运行示例与接口回归；研究效果评估使用目标语料和独立标注问题。
