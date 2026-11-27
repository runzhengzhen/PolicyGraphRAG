from __future__ import annotations

import html
from collections import Counter, defaultdict
from pathlib import Path


def analyze(graph, kind="overview"):
    documents = {d["id"]: d for d in graph["documents"]}
    entities = graph["entities"]
    types = Counter(e["type"] for e in entities)
    result = {"kind": kind, "documents": len(documents), "chunks": len(graph["chunks"]),
              "entities": len(entities), "relations": len(graph["edges"]), "entity_types": dict(types),
              "community_algorithm": graph["community_algorithm"], "communities": len(graph["communities"])}
    requested_type = {"actors": "actor", "tools": "tool", "coding": "research_code"}.get(kind)
    selected = [e for e in entities if requested_type is None or e["type"] == requested_type]
    result["top_entities"] = [dict(id=e["id"], name=e["name"], type=e["type"], pagerank=e["pagerank"],
                                   document_count=len({m["doc_id"] for m in e["mentions"]}),
                                   chunk_ids=sorted({m["chunk_id"] for m in e["mentions"]}))
                              for e in sorted(selected, key=lambda e: (-e["pagerank"], e["id"]))[:30]]
    if kind == "evolution":
        years = defaultdict(Counter)
        def explicit_year(document):
            date = document.get("date", "")
            return date[:4] if len(date) >= 4 and date[:4].isdigit() else None
        unknown = {doc_id for doc_id, document in documents.items() if explicit_year(document) is None}
        mapped_documents = {doc_id for c in graph["communities"] for doc_id in c["doc_ids"]}
        for community in graph["communities"]:
            for doc_id in community["doc_ids"]:
                year = explicit_year(documents[doc_id])
                if year is not None:
                    years[year][community["id"]] += 1
        result.update(yearly_document_community_counts={year: dict(counts) for year, counts in sorted(years.items())},
                      undated_documents=len(unknown),
                      documents_without_community=len(set(documents) - mapped_documents),
                      temporal_method="Counts by explicit document date; a document may occur in multiple communities. Undated texts excluded, no date imputation.")
    result["analysis_methods"] = ["实体候选采用词典匹配，保留连续原文证据与位置。",
                                  "关联分析采用无向加权共现投影，显式关系保留方向与标签。",
                                  "社区主题采用提取式摘要，支持原文证据回溯。"]
    return result


def render_report(graph, output, query_result=None):
    summary = analyze(graph)
    esc = lambda value: html.escape(str(value))
    rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%.6f</td></tr>" %
                   (esc(e["name"]), esc(e["type"]), e["document_count"], e["pagerank"]) for e in summary["top_entities"])
    groups = "".join("<section><h3>%s</h3><p>%s</p><small>%s 篇政策 · %s 个证据块</small></section>" %
                     (esc(c["id"]), esc(c["summary"]), len(c["doc_ids"]), len(c["chunk_ids"])) for c in graph["communities"])
    evidence = ""
    if query_result:
        evidence = "<h2>检索问题：%s</h2>" % esc(query_result["question"])
        for hit in query_result["hits"]:
            evidence += "<section><h3>%s</h3><small>%s · %s · %s:%s</small><pre>%s</pre></section>" % (
                esc(hit["doc_id"]), esc(hit["chunk_id"]), esc(", ".join(hit["channels"])), hit["start"], hit["end"], esc(hit["text"]))
    content = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>政策图谱分析报告</title>
<style>body{font:16px/1.65 system-ui,sans-serif;max-width:1080px;margin:40px auto;padding:0 24px;color:#222}h1{font-size:28px}h2{margin-top:36px}small{color:#666}table{border-collapse:collapse;width:100%%}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left}section{padding:12px 0;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;font:inherit}.metrics{display:flex;gap:30px;flex-wrap:wrap}.metric strong{font-size:24px;display:block}</style>
<h1>政策文本图谱分析工作台</h1><p>基于输入语料的可追溯政策分析</p>
<div class="metrics">%s</div><p>社区算法：%s；图投影：%s</p>
<h2>政策实体与关联强度</h2><p>PageRank来自无向加权共现图；文档数按实体去重计数。</p>
<table><thead><tr><th>实体</th><th>类型</th><th>政策篇数</th><th>PageRank</th></tr></thead><tbody>%s</tbody></table>
<h2>社区主题</h2>%s%s<h2>分析方法</h2><ul>%s</ul></html>""" % (
        "".join('<div class="metric"><strong>%s</strong>%s</div>' % (summary[key], label)
                for key, label in [("documents", "政策文档"), ("chunks", "文本块"), ("entities", "实体"), ("communities", "社区")]),
        esc(graph["community_algorithm"]), esc(graph["projection"]), rows, groups, evidence,
        "".join("<li>%s</li>" % esc(value) for value in summary["analysis_methods"]))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return summary
