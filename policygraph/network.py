"""Directed, signed evidence networks and ego views."""
from collections import defaultdict, deque
from .extract import canonical


def selected_edges(graph, layer='explicit'):
    if layer not in {'explicit', 'cooccurrence', 'all'}:
        raise ValueError('layer must be explicit, cooccurrence or all')
    return [e for e in graph['edges'] if layer == 'all' or
            (e['predicate'] == 'CO_OCCURS_IN_CHUNK') == (layer == 'cooccurrence')]


def network_metrics(graph, layer='explicit'):
    edges = selected_edges(graph, layer)
    ids = {e['id'] for e in graph['entities']}
    adjacency = {key: set() for key in ids}
    nodes = {key: {'entity_id': key, 'in_evidence': 0, 'out_evidence': 0,
                   'undirected_evidence': 0, 'positive_evidence': 0, 'negative_evidence': 0} for key in ids}
    pairs, directed_pairs = {}, set()
    for edge in edges:
        a, b = edge['source'], edge['target']
        directed = edge.get('directed', edge['predicate'] != 'CO_OCCURS_IN_CHUNK')
        weight = len({(r['doc_id'], r['chunk_id']) for r in edge['evidence']})
        adjacency[a].add(b)
        adjacency[b].add(a)
        polarity = 'negative' if edge.get('polarity', '+') == '-' else 'positive'
        nodes[a][polarity+'_evidence'] += weight
        if b != a:
            nodes[b][polarity+'_evidence'] += weight
        if directed:
            nodes[a]['out_evidence'] += weight
            nodes[b]['in_evidence'] += weight
            if a != b:
                directed_pairs.add((a, b))
        else:
            nodes[a]['undirected_evidence'] += weight
            if b != a:
                nodes[b]['undirected_evidence'] += weight
        endpoints = (a, b) if directed else tuple(sorted((a, b)))
        key = endpoints + (edge['predicate'], directed)
        pair = pairs.setdefault(key, dict(source=endpoints[0], target=endpoints[1],
                                         predicate=edge['predicate'], directed=directed,
                                         positive_evidence=0, negative_evidence=0, edge_ids=[]))
        pair[polarity+'_evidence'] += weight
        pair['edge_ids'].append(edge['id'])
    for pair in pairs.values():
        positive, negative = pair['positive_evidence'], pair['negative_evidence']
        pair['signed_balance'] = (positive-negative)/(positive+negative) if positive+negative else None
        pair['mixed_polarity'] = positive > 0 and negative > 0
    groups, pending = [], set(ids)
    while pending:
        found, queue = set(), [min(pending)]
        while queue:
            key = queue.pop()
            if key not in found:
                found.add(key)
                queue.extend(adjacency[key]-found)
        pending -= found
        groups.append(sorted(found))
    for entity in graph['entities']:
        nodes[entity['id']].update(name=entity['name'], type=entity['type'],
                                  neighbors=len(adjacency[entity['id']] - {entity['id']}))
    n = len(ids)
    return {'layer': layer, 'nodes': n, 'edges': len(edges), 'directed_pairs': len(directed_pairs),
            'directed_density': len(directed_pairs)/(n*(n-1)) if n > 1 else 0.0,
            'reciprocity': sum((b, a) in directed_pairs for a, b in directed_pairs)/len(directed_pairs) if directed_pairs else 0.0,
            'isolates': sorted(key for key in ids if not adjacency[key]-{key}),
            'weak_components': groups, 'node_metrics': sorted(nodes.values(), key=lambda r: r['entity_id']),
            'signed_pairs': sorted(pairs.values(), key=lambda r: (r['source'], r['target'], r['predicate'])),
            'weight_unit': 'distinct document/chunk references per edge; self loops excluded from density'}


def ego_graph(graph, entity, radius=1, direction='both', layer='explicit'):
    if not 1 <= radius <= 4 or direction not in {'both', 'in', 'out'}:
        raise ValueError('radius must be 1..4 and direction both/in/out')
    matches = [e['id'] for e in graph['entities'] if entity == e['id'] or
               canonical(entity) in {canonical(n) for n in [e['name']] + e['aliases']}]
    if len(matches) != 1:
        raise ValueError('Entity missing/ambiguous; use unique entity ID')
    edges = selected_edges(graph, layer)
    adjacency = defaultdict(set)
    for edge in edges:
        a, b = edge['source'], edge['target']
        directed = edge.get('directed', edge['predicate'] != 'CO_OCCURS_IN_CHUNK')
        if direction in {'both', 'out'} or not directed:
            adjacency[a].add(b)
        if direction in {'both', 'in'} or not directed:
            adjacency[b].add(a)
    distance, queue = {matches[0]: 0}, deque([matches[0]])
    while queue:
        key = queue.popleft()
        if distance[key] >= radius:
            continue
        for neighbor in sorted(adjacency[key]):
            if neighbor not in distance:
                distance[neighbor] = distance[key]+1
                queue.append(neighbor)
    result = dict(graph)
    result['entities'] = [e for e in graph['entities'] if e['id'] in distance]
    result['edges'] = [e for e in edges if e['source'] in distance and e['target'] in distance]
    refs = {m['chunk_id'] for e in result['entities'] for m in e['mentions']}
    result['chunks'] = [dict(c, entity_ids=[k for k in c['entity_ids'] if k in distance])
                        for c in graph['chunks'] if c['id'] in refs]
    docs = {c['doc_id'] for c in result['chunks']}
    result['documents'] = [d for d in graph['documents'] if d['id'] in docs]
    result['communities'] = []
    result['view'] = dict(entity_id=matches[0], radius=radius, direction=direction, layer=layer, distances=distance)
    # Dense vectors remain aligned with the selected chunks.
    if 'embeddings' in result:
        result['embeddings'] = {k: v for k, v in result['embeddings'].items() if k in refs}
    return result
