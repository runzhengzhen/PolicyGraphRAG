"""Document-level prevalence, exact tests and community coherence."""
import math
from itertools import combinations


def wilson(successes, total, z=1.959963984540054):
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError('Require 0 <= successes <= total and total > 0')
    p = successes / total
    denominator = 1 + z*z/total
    center = (p + z*z/(2*total)) / denominator
    half = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total)) / denominator
    return [max(0.0, center-half), min(1.0, center+half)]


def fisher_exact(a, b, c, d):
    """Two-sided Fisher test, summing tables with probability <= observed."""
    if any(not isinstance(x, int) or x < 0 for x in (a, b, c, d)):
        raise ValueError('Counts must be nonnegative integers')
    total, row, col = a+b+c+d, a+b, a+c
    if total == 0:
        return 1.0
    def logchoose(n, k):
        return math.lgamma(n+1) - math.lgamma(k+1) - math.lgamma(n-k+1)
    def probability(k):
        return logchoose(col, k) + logchoose(total-col, row-k) - logchoose(total, row)
    observed = probability(a)
    values = [probability(k) for k in range(max(0, row-(total-col)), min(row, col)+1)]
    return min(1.0, math.fsum(math.exp(v) for v in values if v <= observed+1e-10))


def bh_adjust(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    adjusted, ceiling = [1.0]*len(values), 1.0
    for rank in range(len(order), 0, -1):
        index = order[rank-1]
        ceiling = min(ceiling, values[index]*len(order)/rank)
        adjusted[index] = ceiling
    return adjusted


def compare_groups(graph, field, left, right):
    """Compare distinct-document entity prevalence in two disjoint metadata groups."""
    if not isinstance(left, str) or not isinstance(right, str) or left == right:
        raise ValueError('Two different string group labels required')
    groups = {label: {d['id'] for d in graph['documents']
                      if d.get('metadata', {}).get(field) == label} for label in (left, right)}
    if any(not docs for docs in groups.values()):
        raise ValueError('Both requested metadata groups must contain documents')
    rows = []
    for entity in sorted(graph['entities'], key=lambda e: e['id']):
        present = {m['doc_id'] for m in entity['mentions']}
        a, b = len(present & groups[left]), len(present & groups[right])
        nl, nr = len(groups[left]), len(groups[right])
        rows.append({'entity_id': entity['id'], 'name': entity['name'], 'type': entity['type'],
                     'left_n': nl, 'right_n': nr, 'left_count': a, 'right_count': b,
                     'left_rate': a/nl, 'right_rate': b/nr, 'difference_right_minus_left': b/nr-a/nl,
                     'left_wilson95': wilson(a, nl), 'right_wilson95': wilson(b, nr),
                     'fisher_p': fisher_exact(a, nl-a, b, nr-b),
                     'left_doc_ids': sorted(present & groups[left]),
                     'right_doc_ids': sorted(present & groups[right])})
    for row, adjusted in zip(rows, bh_adjust([r['fisher_p'] for r in rows])):
        row['fdr_bh'] = adjusted
    rows.sort(key=lambda r: (-abs(r['difference_right_minus_left']), r['entity_id']))
    return {'field': field, 'left': left, 'right': right, 'unit': 'distinct_document',
            'excluded_documents': len(graph['documents'])-len(groups[left])-len(groups[right]),
            'multiple_testing_family': 'all entity rows in this comparison', 'rows': rows}


def community_coherence(graph, top_n=10):
    if top_n < 2:
        raise ValueError('top_n must be >= 2')
    entities = {e['id']: e for e in graph['entities']}
    postings = {key: {m['doc_id'] for m in e['mentions']} for key, e in entities.items()}
    total = len(graph['documents'])
    rows = []
    for group in graph['communities']:
        chosen = sorted(group['entity_ids'], key=lambda k: (-entities[k]['pagerank'], k))[:top_n]
        scores = []
        for a, b in combinations(chosen, 2):
            joint = len(postings[a] & postings[b])
            if not joint:
                scores.append(-1.0)
            elif joint == total:
                scores.append(1.0)
            else:
                p = joint/total
                scores.append(math.log(p / ((len(postings[a])/total)*(len(postings[b])/total))) / -math.log(p))
        rows.append({'community_id': group['id'], 'top_entity_ids': chosen, 'pairs': len(scores),
                     'npmi': math.fsum(scores)/len(scores) if scores else None})
    valid = [r['npmi'] for r in rows if r['npmi'] is not None]
    return {'unit': 'document_presence', 'top_n': top_n,
            'mean_npmi': math.fsum(valid)/len(valid) if valid else None, 'communities': rows}
