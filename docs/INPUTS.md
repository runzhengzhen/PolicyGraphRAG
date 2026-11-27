# 输入、证据与关系格式

## 政策 JSONL

每行是一个对象，必需 `text`，推荐 `id,title,date`。同一文档的多个段落可使用 `doc_id,para_id`。`date` 使用显式研究日期；不从正文年份或文件修改时间猜测。

`metadata` 接受研究者提供的对象，例如 `{"cohort":"A","country":"CN"}`。同一政策跨段落的非空日期与同名 metadata 字段需一致；分组比较使用指定字段中的字符串标签。

`source_file,source_line` 可用于保留来源位置。图内 `start,end` 相对于输入记录的原始 `text`，采用 Python 字符索引；不是 PDF 页码。

`codes` 可提供 `code,evidence_span`；只有 `evidence_span` 能逐字在块中匹配时才作为研究编码证据。研究编码实体的类型为 `research_code`，不冒充政策主体。

## 关系 CSV / TSV

必须列：`id,doc_id,source,source_type,target,target_type,predicate,quote`。

可选列：`title,date,text,polarity,stance`。`text` 缺省时使用 `quote`。每个 `(doc_id,id)` 必须唯一，表示一条研究者编码的关系记录。

实体类型为 `actor,tool,target,goal`。关系谓词为 `USES,GOVERNS,TARGETS,AIMS_AT,ISSUED_BY,REQUIRES,PROHIBITS`，源与目标按该方向保存。`polarity` 为 `+` 或 `-`，缺省 `+`；`stance` 可为 `A,B,N,support,oppose,neutral` 或空，编码含义由研究码本定义，不自动翻转或归类。

两个实体名称都必须逐字出现在 `quote` 中，`quote` 必须是 `text` 连续片段。不满足条件的关系不接入有效图边；包含有效记录时，未通过记录出现在输出旁的 `.audit.json`。

JSONL 也可直接包含 `entities:[{name,type,quote}]` 与 `relations:[{source:{name,type},target:{name,type},predicate,quote,polarity,stance}]`。导入检查研究者编码中的字面证据与实体位置，语义编码结合研究码本复核。超过文本块长度的引句无法在该块核验，可通过 `--max-chars` 调整分块或缩短证据引句。

## 图格式

主图 `graph.json` 保存文档、原文块、实体提及、边、社区和构建记录。`CO_OCCURS_IN_CHUNK` 为无向共现，其他显式关系保存 `directed,polarity,stance`。检索和路径寻找使用无向关联邻域，结果保留边的原始方向；不要把反向遍历改述为反向事实。

GraphML/GEXF 导出保存混合边方向、极性、立场、证据 JSON 和证据数量权重；GraphML 还保存节点类型与 PageRank。部分网络工具不支持混合图，应按自身需求分别筛选显式边与共现边，不要为了导入方便丢失方向。

SVG 展示 PageRank 最高的若干节点和最多45条边，完整节点和边保存在标准网络文件中。SVG 使用系统字体。
