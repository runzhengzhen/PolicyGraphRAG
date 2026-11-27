from __future__ import annotations

import itertools
import random
from collections import Counter, defaultdict
from .extract import canonical, extract_chunk
from .io import digest


def resolve_entity(name, kind, aliases):
    normalized = canonical(name)
    rules = aliases.get(kind, {})
    mapped = {canonical(k): v for k, v in rules.items()}
    visited = set()
    display = name
    while normalized in mapped:
        if normalized in visited:
            raise ValueError("Alias cycle in type %s: %s" % (kind, name))
        visited.add(normalized)
        display = mapped[normalized]
        next_key = canonical(display)
        if next_key == normalized:
            break
        normalized = next_key
    return "e_" + digest([kind, normalized])[:24], display


def pagerank(adjacency, damping=0.85, tolerance=1e-10, iterations=200):
    nodes = sorted(adjacency)
    if not nodes:
        return {}
    size = len(nodes)
    rank = {node: 1 / size for node in nodes}
    totals = {node: sum(adjacency[node].values()) for node in nodes}
    for _ in range(iterations):
        dangling = sum(rank[n] for n in nodes if not totals[n])
        updated = {node: (1 - damping) / size + damping * dangling / size for node in nodes}
        for source in nodes:
            if totals[source]:
                for target, weight in adjacency[source].items():
                    updated[target] += damping * rank[source] * weight / totals[source]
        delta = sum(abs(updated[n] - rank[n]) for n in nodes)
        rank = updated
        if delta < tolerance:
            break
    return rank


def communities(adjacency, algorithm="auto", seed=42):
    names = sorted(adjacency)
    if not names:
        return [], "empty"
    if algorithm in ("auto", "leiden"):
        try:
            import igraph as ig
        except ImportError:
            if algorithm == "leiden":
                raise RuntimeError("Leiden requires python-igraph. Install the graph extra.")
        else:
            ig.set_random_number_generator(random.Random(seed))
            graph = ig.Graph(n=len(names), directed=False)
            positions = {name: i for i, name in enumerate(names)}
            pairs = [(a, b, weight) for a in names for b, weight in adjacency[a].items() if a < b]
            if not pairs:
                return [[name] for name in names], "leiden_isolates"
            graph.add_edges([(positions[a], positions[b]) for a, b, _ in pairs])
            partition = graph.community_leiden(objective_function="modularity", weights=[w for _, _, w in pairs], n_iterations=-1)
            return sorted([sorted(names[i] for i in cluster) for cluster in partition]), "leiden"
    pending = set(names)
    result = []
    while pending:
        start = min(pending)
        group, queue = set(), [start]
        while queue:
            node = queue.pop()
            if node in group:
                continue
            group.add(node)
            queue.extend(set(adjacency[node]) - group)
        pending -= group
        result.append(sorted(group))
    return result, "connected_components"


def build_graph(documents, chunks, cache, aliases=None, lexicon=None, client=None, algorithm="auto"):
    aliases = aliases or {}
    entities, edges = {}, {}
    adjacency = defaultdict(Counter)
    resolution_log, rejected = [], []
    coding_audit = {"accepted_mentions": 0, "unmatched_or_missing_quote": 0}

    def add_edge(source, target, predicate, chunk, evidence, method, polarity='+', stance=''):
        identity = "r_" + digest([source, target, predicate, polarity, stance])[:24]
        edge = edges.setdefault(identity, {"id": identity, "source": source, "target": target,
                                          "predicate": predicate, "directed": predicate != 'CO_OCCURS_IN_CHUNK',
                                          "polarity": polarity, "stance": stance, "evidence": []})
        item = {"chunk_id": chunk["id"], "doc_id": chunk["doc_id"], "quote": evidence, "method": method}
        if item not in edge["evidence"]:
            edge["evidence"].append(item)

    for chunk in chunks:
        result = extract_chunk(chunk, cache, lexicon, client)
        rejected.extend(dict(r, chunk_id=chunk["id"]) for r in result.get("rejected", []))
        chunk["entity_ids"] = []
        names_to_id = {}
        for mention in result["entities"]:
            kind, raw = mention["type"], mention["name"]
            entity_id, display = resolve_entity(raw, kind, aliases)
            entity = entities.setdefault(entity_id, {"id": entity_id, "name": display, "type": kind, "aliases": [], "mentions": []})
            if raw not in entity["aliases"]:
                entity["aliases"].append(raw)
            evidence = {"chunk_id": chunk["id"], "doc_id": chunk["doc_id"], "name": raw,
                        "start": mention["start"], "end": mention["end"], "method": mention.get("method", "llm")}
            if evidence not in entity["mentions"]:
                entity["mentions"].append(evidence)
            if entity_id not in chunk["entity_ids"]:
                chunk["entity_ids"].append(entity_id)
            names_to_id[(raw, kind)] = entity_id
            resolution_log.append({"raw": raw, "type": kind, "entity_id": entity_id, "canonical": display,
                                   "rule": "typed_alias" if canonical(raw) != canonical(display) else "typed_normalization"})
        # Imported qualitative codes remain research codes, not policy actor/tool facts.
        for code in chunk.get("codes", []):
            name, quote = code.get("code"), code.get("evidence_span")
            if not name or not isinstance(quote, str) or not quote or quote not in chunk["text"]:
                coding_audit["unmatched_or_missing_quote"] += 1
                continue
            coding_audit["accepted_mentions"] += 1
            entity_id = "e_" + digest(["research_code", canonical(name)])[:24]
            entity = entities.setdefault(entity_id, {"id": entity_id, "name": name, "type": "research_code", "aliases": [name], "mentions": []})
            evidence = {"chunk_id": chunk["id"], "doc_id": chunk["doc_id"], "name": quote,
                        "start": chunk["text"].index(quote), "end": chunk["text"].index(quote) + len(quote), "method": "gtflow_code_evidence"}
            entity["mentions"].append(evidence)
            if entity_id not in chunk["entity_ids"]:
                chunk["entity_ids"].append(entity_id)
        ids = sorted(set(chunk["entity_ids"]))
        for entity_id in ids:
            adjacency[entity_id]
        # Co-occurrence is an association, never a causal or regulatory assertion.
        for a, b in itertools.combinations(ids, 2):
            adjacency[a][b] += 1
            adjacency[b][a] += 1
            add_edge(a, b, "CO_OCCURS_IN_CHUNK", chunk, "", "cooccurrence")
        for relation in result["relations"]:
            source, target = relation["source"], relation["target"]
            a = names_to_id[(source["name"], source["type"])]
            b = names_to_id[(target["name"], target["type"])]
            add_edge(a, b, relation["predicate"], chunk, relation["quote"], relation.get('method', 'llm_literal_evidence'),
                     relation.get('polarity', '+'), relation.get('stance', ''))
    ranking = pagerank(adjacency)
    groups, used_algorithm = communities(adjacency, algorithm)
    for entity_id, entity in entities.items():
        entity["pagerank"] = ranking.get(entity_id, 0)
    summaries = []
    for group in groups:
        community_id = "g_" + digest(group)[:24]
        top = sorted(group, key=lambda entity_id: (-ranking.get(entity_id, 0), entity_id))[:12]
        group_set = set(group)
        # Community coverage is represented through ALL matching chunks.
        refs = [c["id"] for c in chunks if group_set.intersection(c["entity_ids"])]
        ref_set = set(refs)
        doc_ids = sorted({c["doc_id"] for c in chunks if c["id"] in ref_set})
        names = [entities[node]["name"] for node in top]
        signature = digest(["extractive-community-v2", group, names, doc_ids, [(c["id"], c["text"]) for c in chunks if c["id"] in ref_set]])
        summary = cache.get(signature)
        if summary is None:
            summary = "关联主题：%s。覆盖 %s 篇政策、%s 个文本块。由实体共现和PageRank形成的提取式摘要，未推断政策因果或有效性。" % ("、".join(names), len(doc_ids), len(refs))
            cache.put(signature, summary)
        summaries.append({"id": community_id, "entity_ids": group, "top_entities": names,
                          "chunk_ids": refs, "doc_ids": doc_ids, "summary": summary,
                          "method": "extractive", "signature": signature})
    unique_resolutions = {digest(row): row for row in resolution_log}
    return {"schema_version": 1, "documents": documents, "chunks": chunks, "entities": list(entities.values()),
            "edges": list(edges.values()), "communities": summaries,
            "community_algorithm": used_algorithm, "projection": "undirected_weighted_chunk_cooccurrence",
            "resolution_log": list(unique_resolutions.values()), "rejected_extractions": rejected,
            "imported_code_evidence_audit": coding_audit}
