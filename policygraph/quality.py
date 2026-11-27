"""Graph evidence integrity and document template similarity."""
import datetime
import itertools
import re
import unicodedata
from collections import defaultdict
from .io import digest


def document_texts(graph):
    units = defaultdict(lambda: defaultdict(list))
    for chunk in graph['chunks']:
        units[chunk['doc_id']][chunk['unit_key']].append(chunk)
    return {doc: '\n'.join(''.join(c['text'] for c in sorted(parts, key=lambda c: c['start']))
                            for parts in records.values()) for doc, records in units.items()}


def audit_graph(graph, near_threshold=0.85, max_pairs=200000):
    if not 0 < near_threshold <= 1 or max_pairs < 0:
        raise ValueError('Require threshold in (0,1] and max_pairs >= 0')
    errors = []
    def unique(rows, kind):
        index = {}
        for row in rows:
            if row['id'] in index:
                errors.append({'kind': 'duplicate_'+kind, 'id': row['id']})
            index[row['id']] = row
        return index
    docs = unique(graph['documents'], 'document')
    chunks = unique(graph['chunks'], 'chunk')
    entities = unique(graph['entities'], 'entity')
    unique(graph['edges'], 'edge')
    units = defaultdict(list)
    for chunk in chunks.values():
        units[(chunk['doc_id'], chunk['unit_key'])].append(chunk)
        if chunk['doc_id'] not in docs or chunk['end']-chunk['start'] != len(chunk['text']) or chunk['start'] < 0:
            errors.append({'kind': 'chunk_reference_or_offset', 'id': chunk['id']})
        for key in chunk['entity_ids']:
            if key not in entities:
                errors.append({'kind': 'chunk_entity_reference', 'id': chunk['id'], 'entity_id': key})
    for parts in units.values():
        position = 0
        for chunk in sorted(parts, key=lambda c: c['start']):
            if chunk['start'] != position and not graph.get('view'):
                errors.append({'kind': 'chunk_gap_or_overlap', 'id': chunk['id']})
            position = chunk['end']
    for entity in entities.values():
        for mention in entity['mentions']:
            chunk = chunks.get(mention['chunk_id'])
            if (not chunk or mention['doc_id'] != chunk['doc_id'] or
                not 0 <= mention['start'] <= mention['end'] <= len(chunk['text']) or
                chunk['text'][mention['start']:mention['end']] != mention['name']):
                errors.append({'kind': 'mention_evidence', 'id': entity['id'], 'chunk_id': mention['chunk_id']})
    for edge in graph['edges']:
        if edge['source'] not in entities or edge['target'] not in entities:
            errors.append({'kind': 'edge_endpoint', 'id': edge['id']})
        for evidence in edge['evidence']:
            chunk = chunks.get(evidence['chunk_id'])
            if (not chunk or evidence['doc_id'] != chunk['doc_id'] or evidence['quote'] not in chunk['text'] or
                not {edge['source'], edge['target']}.issubset(set(chunk['entity_ids'])) or
                (edge['predicate'] != 'CO_OCCURS_IN_CHUNK' and not evidence['quote'])):
                errors.append({'kind': 'edge_evidence', 'id': edge['id']})
    for group in graph['communities']:
        if (set(group['entity_ids'])-set(entities) or set(group['chunk_ids'])-set(chunks) or set(group['doc_ids'])-set(docs)):
            errors.append({'kind': 'community_reference', 'id': group['id']})
    texts = document_texts(graph)
    normalized = {key: re.sub(r'\s+', '', unicodedata.normalize('NFKC', text)).casefold() for key, text in texts.items()}
    exact = defaultdict(list)
    for key, text in normalized.items():
        exact[digest(text)].append(key)
    exact_groups = sorted([sorted(group) for group in exact.values() if len(group) > 1])
    ids = sorted(normalized)
    pair_count = len(ids)*(len(ids)-1)//2
    if pair_count > max_pairs:
        raise ValueError('Similarity audit requires %s pairs; increase --max-pairs or audit a smaller corpus' % pair_count)
    shingles = {key: {text[i:i+5] for i in range(max(1, len(text)-4))} for key, text in normalized.items()}
    similar, adjacency = [], {key: set() for key in ids}
    for a, b in itertools.combinations(ids, 2):
        left, right = shingles[a], shingles[b]
        score = len(left & right)/len(left | right) if left | right else 1.0
        if score >= near_threshold:
            similar.append({'left_doc_id': a, 'right_doc_id': b, 'jaccard': score, 'exact': normalized[a] == normalized[b]})
            adjacency[a].add(b)
            adjacency[b].add(a)
    families, pending = [], set(ids)
    while pending:
        queue, found = [min(pending)], set()
        while queue:
            key = queue.pop()
            if key not in found:
                found.add(key)
                queue.extend(adjacency[key]-found)
        pending -= found
        if len(found) > 1:
            families.append(sorted(found))
    invalid_dates, missing_dates = [], []
    for doc in docs.values():
        date = doc.get('date', '')
        if not date:
            missing_dates.append(doc['id'])
        else:
            try:
                if re.fullmatch(r'\d{4}', date):
                    datetime.date(int(date), 1, 1)
                else:
                    datetime.date.fromisoformat(date)
            except ValueError:
                invalid_dates.append(doc['id'])
    covered = {m['doc_id'] for e in entities.values() for m in e['mentions']}
    return {'integrity': 'passed' if not errors else 'failed', 'errors': errors,
            'documents': len(docs), 'chunks': len(chunks), 'documents_without_entities': sorted(set(docs)-covered),
            'missing_date_doc_ids': sorted(missing_dates), 'invalid_date_doc_ids': sorted(invalid_dates),
            'exact_duplicate_groups': exact_groups, 'similar_pairs': similar, 'template_families': families,
            'similarity': {'method': 'NFKC/whitespace-normalized character-5-gram Jaccard',
                           'threshold': near_threshold, 'pairs_checked': pair_count,
                           'family_method': 'connected components of thresholded similarity pairs'}}
