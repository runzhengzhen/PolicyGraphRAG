from __future__ import annotations

import math
import re
from collections import Counter, defaultdict, deque
from .extract import canonical


def tokens(text):
    text = re.sub(r"\s+", "", text.casefold())
    return [text[i:i + n] for n in (2, 3) for i in range(max(0, len(text) - n + 1))]


class SparseIndex:
    """Character 2/3-gram TF-IDF cosine. This is lexical, not dense semantics."""
    def __init__(self, rows, field="text"):
        self.rows = rows
        self.counts = [Counter(tokens(row[field])) for row in rows]
        document_frequency = Counter(term for counts in self.counts for term in counts)
        self.idf = {term: math.log((1 + len(rows)) / (1 + count)) + 1 for term, count in document_frequency.items()}
        self.norms = [math.sqrt(sum(((1 + math.log(count)) * self.idf[term]) ** 2 for term, count in counts.items()))
                      for counts in self.counts]

    def search(self, query, limit):
        counts = Counter(tokens(query))
        weights = {term: (1 + math.log(count)) * self.idf[term] for term, count in counts.items() if term in self.idf}
        norm = math.sqrt(sum(w * w for w in weights.values()))
        if not norm:
            return []
        result = []
        for i, (row, counts) in enumerate(zip(self.rows, self.counts)):
            score = sum(weight * (1 + math.log(counts[term])) * self.idf[term] for term, weight in weights.items() if term in counts)
            score = score / (norm * self.norms[i]) if self.norms[i] else 0
            if score > 0:
                result.append({"id": row["id"], "score": score})
        return sorted(result, key=lambda row: (-row["score"], row["id"]))[:limit]


def cosine(a, b):
    if len(a) != len(b):
        raise ValueError("Embedding dimensions differ")
    norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / norm if norm else 0


class RetrievalIndex:
    """Build lexical indexes and graph adjacency once for repeated queries."""
    def __init__(self, graph):
        self.graph = graph
        self.chunks = {c['id']: c for c in graph['chunks']}
        self.entities = {e['id']: e for e in graph['entities']}
        self.sparse = SparseIndex(graph['chunks'])
        self.global_index = SparseIndex(graph['communities'], 'summary')
        self.community_by_id = {c['id']: c for c in graph['communities']}
        self.adjacency = defaultdict(set)
        for edge in graph['edges']:
            self.adjacency[edge['source']].add(edge['target'])
            self.adjacency[edge['target']].add(edge['source'])

    def search(self, question, mode='hybrid', top_k=8, hops=2, dense_query=None):
        return retrieve(self.graph, question, mode, top_k, hops, dense_query, _index=self)


def retrieve(graph, question, mode="hybrid", top_k=8, hops=2, dense_query=None, _index=None):
    if top_k < 1 or not 0 <= hops <= 4:
        raise ValueError("top_k >= 1, hops between 0 and 4 required")
    index = _index or RetrievalIndex(graph)
    chunks, entities = index.chunks, index.entities
    normalized_question = canonical(question)
    seeds = {e["id"] for e in entities.values() if any(canonical(name) in normalized_question for name in [e["name"]] + e["aliases"] if name)}
    sparse = index.sparse.search(question, top_k * 3)
    adjacency = index.adjacency
    distances = {node: 0 for node in seeds}
    queue = deque(sorted(seeds))
    while queue:
        node = queue.popleft()
        if distances[node] >= hops:
            continue
        for neighbor in sorted(adjacency[node]):
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    local = []
    for chunk in chunks.values():
        matched = set(chunk["entity_ids"]) & set(distances)
        if matched:
            score = sum(1 / (1 + distances[node]) for node in matched)
            local.append({"id": chunk["id"], "score": score})
    local = sorted(local, key=lambda r: (-r["score"], r["id"]))[:top_k * 3]
    # Rank every community; map each selected report to its supporting chunks.
    global_hits = index.global_index.search(question, top_k)
    community_by_id = index.community_by_id
    global_scores = defaultdict(float)
    sparse_rank = {row["id"]: i for i, row in enumerate(sparse)}
    for rank, hit in enumerate(global_hits):
        for chunk_id in community_by_id[hit["id"]]["chunk_ids"]:
            global_scores[chunk_id] += 1 / (rank + 1)
    global_rows = [{"id": node, "score": value} for node, value in global_scores.items()]
    global_rows.sort(key=lambda r: (-r["score"], sparse_rank.get(r["id"], 1000000), r["id"]))
    rankings = {"vector": sparse, "local": local, "global": global_rows[:top_k * 3]}
    if dense_query is not None:
        embeddings = graph.get("embeddings")
        if not embeddings:
            raise ValueError("No dense embeddings were built")
        rankings["dense"] = sorted([{"id": key, "score": cosine(dense_query, vec)} for key, vec in embeddings.items()],
                                   key=lambda r: (-r["score"], r["id"]))[:top_k * 3]
    selected = list(rankings) if mode == "hybrid" else [mode]
    if any(name not in rankings for name in selected):
        raise ValueError("Selected retrieval mode requires an unavailable index")
    scores, channels = defaultdict(float), defaultdict(list)
    for name in selected:
        for rank, row in enumerate(rankings[name]):
            scores[row["id"]] += 1 / (60 + rank + 1)
            channels[row["id"]].append(name)
    hits = []
    for chunk_id in sorted(scores, key=lambda node: (-scores[node], node))[:top_k]:
        chunk = chunks[chunk_id]
        hits.append({"chunk_id": chunk_id, "doc_id": chunk["doc_id"], "text": chunk["text"],
                     "start": chunk["start"], "end": chunk["end"], "source_file": chunk["source_file"],
                     "source_line": chunk["source_line"], "score": scores[chunk_id], "channels": channels[chunk_id]})
    return {"question": question, "mode": mode, "fusion": "reciprocal_rank_k60",
            "vector_backend": "character_tfidf_sparse", "dense_used": dense_query is not None,
            "seed_entity_ids": sorted(seeds), "hits": hits,
            "community_reports": [community_by_id[h["id"]] for h in global_hits] if mode in ("hybrid", "global") else [],
            "interpretation": "Evidence retrieval; co-occurrence paths are associations, not logical entailment or causal conclusions."}


def relation_path(graph, source_name, target_name, max_hops=3):
    if not 1 <= max_hops <= 6:
        raise ValueError("max_hops must be 1..6")
    entities = {e["id"]: e for e in graph["entities"]}
    def identify(name):
        if name in entities:
            return name
        hits = [e["id"] for e in entities.values() if canonical(name) in [canonical(n) for n in [e["name"]] + e["aliases"]]]
        if len(hits) != 1:
            raise ValueError("Entity missing/ambiguous; use entity ID. Matches: %s" % hits)
        return hits[0]
    source, target = identify(source_name), identify(target_name)
    adjacency = defaultdict(list)
    for edge in graph["edges"]:
        adjacency[edge["source"]].append((edge["target"], edge))
        adjacency[edge["target"]].append((edge["source"], edge))
    queue = deque([(source, [], {source})])
    while queue:
        node, path, visited = queue.popleft()
        if node == target:
            return {"found": True, "edges": path, "interpretation": "Undirected association path; retain each edge's stored direction and predicate."}
        if len(path) >= max_hops:
            continue
        for neighbor, edge in adjacency[node]:
            if neighbor not in visited:
                queue.append((neighbor, path + [edge], visited | {neighbor}))
    return {"found": False, "edges": [], "max_hops": max_hops}
