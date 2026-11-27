"""Reproducible document-level retrieval evaluation with graded judgments."""
import math
import time
from .retrieve import RetrievalIndex


def ranking_metrics(ranked, relevance, k):
    if k < 1:
        raise ValueError('k must be positive')
    unique = list(dict.fromkeys(ranked))[:k]
    positive = {doc for doc, grade in relevance.items() if grade > 0}
    if not positive:
        return {'no_answer_correct': float(not unique), 'returned_documents': len(unique)}
    hits = [i for i, doc in enumerate(unique, 1) if doc in positive]
    dcg = math.fsum((2**relevance.get(doc, 0)-1)/math.log2(i+1) for i, doc in enumerate(unique, 1))
    ideal = math.fsum((2**grade-1)/math.log2(i+1)
                      for i, grade in enumerate(sorted(relevance.values(), reverse=True)[:k], 1))
    return {'recall': len(hits)/len(positive), 'precision': len(hits)/k,
            'mrr': 1/hits[0] if hits else 0.0, 'ndcg': dcg/ideal if ideal else 0.0,
            'hit_rate': float(bool(hits))}


def evaluate_retrieval(graph, queries, modes=('vector', 'local', 'global', 'hybrid'), k=5):
    if k < 1 or not queries:
        raise ValueError('Positive k and at least one query required')
    if not modes or len(set(modes)) != len(modes) or set(modes)-{'vector', 'local', 'global', 'hybrid'}:
        raise ValueError('Choose unique offline retrieval modes: vector/local/global/hybrid')
    docs = {d['id'] for d in graph['documents']}
    native = {}
    for doc in graph['documents']:
        native.setdefault(doc['native_id'], []).append(doc['id'])
    prepared, seen = [], set()
    for row in queries:
        if not isinstance(row.get('id'), str) or not row['id'] or row['id'] in seen:
            raise ValueError('Query IDs must be unique nonempty strings')
        seen.add(row['id'])
        if not isinstance(row.get('question'), str) or not row['question'].strip() or not isinstance(row.get('relevance'), dict):
            raise ValueError('Each query requires question and relevance object')
        relevance = {}
        for key, grade in row['relevance'].items():
            if not isinstance(grade, int) or isinstance(grade, bool) or not 0 <= grade <= 10:
                raise ValueError('Relevance grades must be integers 0..10')
            resolved = key if key in docs else native.get(key, [])
            if isinstance(resolved, list):
                if len(resolved) != 1:
                    raise ValueError('Unknown/ambiguous judged document: '+key)
                resolved = resolved[0]
            if resolved in relevance:
                raise ValueError('Multiple judgments resolve to the same document')
            relevance[resolved] = grade
        prepared.append(dict(row, relevance=relevance))
    start = time.perf_counter()
    index = RetrievalIndex(graph)
    index_seconds = time.perf_counter()-start
    per_query, summaries = [], []
    for mode in modes:
        rows = []
        for row in prepared:
            start = time.perf_counter()
            # Retrieve the full ranked chunk set, then collapse to the first hit per document.
            result = index.search(row['question'], mode, max(1, len(graph['chunks'])))
            ranked = list(dict.fromkeys(h['doc_id'] for h in result['hits']))[:k]
            metrics = ranking_metrics(ranked, row['relevance'], k)
            value = dict(query_id=row['id'], mode=mode, ranked_doc_ids=ranked, metrics=metrics,
                         latency_ms=(time.perf_counter()-start)*1000)
            rows.append(value)
            per_query.append(value)
        answerable = [r for r in rows if 'recall' in r['metrics']]
        no_answer = [r for r in rows if 'no_answer_correct' in r['metrics']]
        summaries.append(dict(mode=mode, answerable_queries=len(answerable), no_answer_queries=len(no_answer),
                              mean_metrics={key: math.fsum(r['metrics'][key] for r in answerable)/len(answerable)
                                            for key in ('recall', 'precision', 'mrr', 'ndcg', 'hit_rate')} if answerable else {},
                              no_answer_accuracy=math.fsum(r['metrics']['no_answer_correct'] for r in no_answer)/len(no_answer) if no_answer else None,
                              mean_latency_ms=math.fsum(r['latency_ms'] for r in rows)/len(rows)))
    return {'k': k, 'unit': 'distinct_document', 'query_count': len(queries),
            'judgment_policy': 'unjudged documents receive grade 0; empty relevance means no answer',
            'index_build_seconds': index_seconds, 'summaries': summaries, 'per_query': per_query}
