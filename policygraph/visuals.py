"""Portable SVG figures and native graph export; no bundled fonts or resources."""
import html
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from .research import analyze

SVG = 'http://www.w3.org/2000/svg'
esc = lambda value: html.escape(str(value), quote=True)


def document(title, body, width=1080, height=720, note=''):
    return ('<svg xmlns="%s" width="%s" height="%s" viewBox="0 0 %s %s" role="img" aria-label="%s">'
            '<rect width="100%%" height="100%%" fill="white"/><style>text{font-family:system-ui,sans-serif;fill:#263c43}</style>'
            '<text x="32" y="42" font-size="23">%s</text>%s<text x="32" y="%s" font-size="12">%s</text></svg>') % (
                SVG, width, height, width, height, esc(title), esc(title), body, height - 18, esc(note))


def bars(title, rows, axis, note):
    height = max(260, 130 + 42 * len(rows))
    maximum = max((value for _, value in rows), default=1) or 1
    body = '<text x="260" y="70" font-size="13">%s</text>' % esc(axis)
    for i, (label, value) in enumerate(rows):
        y = 94 + 42 * i
        length = value / maximum * 620
        body += ('<text x="240" y="%s" text-anchor="end" font-size="14">%s</text>'
                 '<rect x="260" y="%s" width="%.2f" height="23" fill="#2b827c"/>'
                 '<text x="%.2f" y="%s" font-size="13">%s</text>') % (
                     y + 17, esc(label[:28]), y, length, 270 + length, y + 17,
                     ('%.4f' % value if isinstance(value, float) else value))
    return document(title, body, height=height, note=note)


def comparison_svg(comparison, top_n=18):
    """Two prevalence estimates and Wilson 95% intervals per entity."""
    rows = comparison['rows'][:top_n]
    height = max(280, 170 + 50*len(rows))
    body = '<text x="260" y="76" font-size="13">%s（绿） / %s（红） · 文档覆盖率与Wilson 95%%区间</text>' % (
        esc(comparison['left']), esc(comparison['right']))
    for tick in (0, 0.25, 0.5, 0.75, 1):
        x = 260+tick*640
        body += '<path d="M%s 98 L%s %s" stroke="#e5ecec"/><text x="%s" y="94" text-anchor="middle" font-size="10">%s%%</text>' % (
            x, x, max(115, 120+50*len(rows)), x, int(tick*100))
    for i, row in enumerate(rows):
        y = 108 + 50*i
        body += '<text x="240" y="%s" text-anchor="end" font-size="13">%s</text>' % (y+6, esc(row['name'][:28]))
        for offset, prefix, color in [(-5, 'left', '#2b827c'), (10, 'right', '#ac4b45')]:
            low, high = row[prefix+'_wilson95']
            body += ('<path d="M%.2f %s L%.2f %s" stroke="%s" stroke-width="2"/>'
                     '<circle cx="%.2f" cy="%s" r="4" fill="%s"/><text x="925" y="%s" font-size="12">%s/%s</text>') % (
                         260+low*640, y+offset, 260+high*640, y+offset, color,
                         260+row[prefix+'_rate']*640, y+offset, color, y+offset+4,
                         row[prefix+'_count'], row[prefix+'_n'])
    return document('政策分组实体覆盖比较', body, height=height,
                    note='按覆盖率差值绝对值排序；同篇政策内多次提及按一次计数。')


def graph_svg(graph, top_n=18):
    if not 2 <= top_n <= 60:
        raise ValueError('top_n must be between 2 and 60')
    nodes = sorted(graph['entities'], key=lambda e: (-e['pagerank'], e['id']))[:top_n]
    positions = {e['id']: (540 + 380 * math.cos(2 * math.pi * i / max(1, len(nodes))),
                           350 + 250 * math.sin(2 * math.pi * i / max(1, len(nodes)))) for i, e in enumerate(nodes)}
    edges = [e for e in graph['edges'] if e['source'] in positions and e['target'] in positions]
    edges.sort(key=lambda e: (e['predicate'] == 'CO_OCCURS_IN_CHUNK', -len(e['evidence']), e['id']))
    edges = edges[:45]
    body = '<defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0 L7 3.5 L0 7" fill="#65767b"/></marker></defs>'
    for edge in edges:
        x1, y1 = positions[edge['source']]
        x2, y2 = positions[edge['target']]
        length = math.hypot(x2-x1, y2-y1) or 1
        x1, y1 = x1 + (x2-x1)/length*26, y1 + (y2-y1)/length*26
        x2, y2 = x2 - (x2-x1)/length*30, y2 - (y2-y1)/length*30
        directed = edge.get('directed', edge['predicate'] != 'CO_OCCURS_IN_CHUNK')
        body += '<path d="M%.2f %.2f L%.2f %.2f" stroke="%s" stroke-width="1.5" opacity=".5" fill="none" %s><title>%s</title></path>' % (
            x1, y1, x2, y2, '#ac4b45' if edge.get('polarity') == '-' else '#65767b',
            'marker-end="url(#arrow)"' if directed else '', esc(edge['predicate'] + ' / ' + edge.get('polarity', '+')))
    for node in nodes:
        x, y = positions[node['id']]
        body += '<circle cx="%.2f" cy="%.2f" r="25" fill="#d9eae7" stroke="#2b827c"/><text x="%.2f" y="%.2f" text-anchor="middle" font-size="13">%s</text>' % (x, y, x, y + 5, esc(node['name'][:14]))
    return document('政策实体与关系网络', body, note='按PageRank选取节点；最多45条边。箭头表示记录方向，红色表示负极性。')


def plot_graph(graph, output, top_n=18):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    files = []
    def save(name, text):
        (output / name).write_text(text, encoding='utf-8')
        files.append(name)
    if graph['entities']:
        save('network.svg', graph_svg(graph, top_n))
        ranking = sorted(graph['entities'], key=lambda e: (-e['pagerank'], e['id']))[:top_n]
        save('entity-centrality.svg', bars('政策实体关联中心性', [(e['name'], e['pagerank']) for e in ranking],
             'PageRank（归一化权重）', '实体为候选标注；PageRank基于无向加权共现投影。'))
    if graph['communities']:
        save('community-coverage.svg', bars('社区覆盖政策数', [('社区 %s' % (i+1), len(c['doc_ids'])) for i, c in enumerate(graph['communities'])],
             '覆盖政策文档数（篇）', '同一政策可出现在多个社区；社区编号与图文件中的顺序一致。'))
    evolution = analyze(graph, 'evolution')['yearly_document_community_counts']
    if evolution:
        save('dated-community-coverage.svg', bars('按年份统计的政策—社区覆盖', [(year, sum(values.values())) for year, values in evolution.items()],
             '政策—社区对应数（条）', '仅按输入date字段；同篇跨社区重复计数，未提供日期的文档不计入。'))
    return {'files': files, 'format': 'SVG', 'entities_in_input': len(graph['entities'])}


def export_network(graph, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    fields = {'name': ('node', 'string'), 'type': ('node', 'string'), 'pagerank': ('node', 'double'),
              'predicate': ('edge', 'string'), 'polarity': ('edge', 'string'), 'stance': ('edge', 'string'),
              'weight': ('edge', 'double'), 'evidence_json': ('edge', 'string')}
    namespace = 'http://graphml.graphdrawing.org/xmlns'
    root = ET.Element('graphml', xmlns=namespace)
    for key, (scope, kind) in fields.items():
        ET.SubElement(root, 'key', {'id': key, 'for': scope, 'attr.name': key, 'attr.type': kind})
    container = ET.SubElement(root, 'graph', id='policy', edgedefault='directed')
    for entity in graph['entities']:
        node = ET.SubElement(container, 'node', id=entity['id'])
        for key in ['name', 'type', 'pagerank']:
            ET.SubElement(node, 'data', key=key).text = str(entity[key])
    for edge in graph['edges']:
        node = ET.SubElement(container, 'edge', id=edge['id'], source=edge['source'], target=edge['target'],
                             directed=str(edge.get('directed', edge['predicate'] != 'CO_OCCURS_IN_CHUNK')).lower())
        values = dict(predicate=edge['predicate'], polarity=edge.get('polarity', '+'), stance=edge.get('stance', ''),
                      weight=len(edge['evidence']), evidence_json=json.dumps(edge['evidence'], ensure_ascii=False))
        for key, value in values.items():
            ET.SubElement(node, 'data', key=key).text = str(value)
    ET.ElementTree(root).write(str(output / 'network.graphml'), encoding='utf-8', xml_declaration=True)
    # GEXF permits a per-edge type, preserving the mixed directed/undirected graph.
    root = ET.Element('gexf', xmlns='http://gexf.net/1.3', version='1.3')
    container = ET.SubElement(root, 'graph', defaultedgetype='directed', mode='static')
    attrs = ET.SubElement(container, 'attributes', {'class': 'edge'})
    for key in ['predicate', 'polarity', 'stance', 'evidence_json']:
        ET.SubElement(attrs, 'attribute', id=key, title=key, type='string')
    nodes = ET.SubElement(container, 'nodes')
    for entity in graph['entities']:
        ET.SubElement(nodes, 'node', id=entity['id'], label=entity['name'])
    edges = ET.SubElement(container, 'edges')
    for edge in graph['edges']:
        node = ET.SubElement(edges, 'edge', id=edge['id'], source=edge['source'], target=edge['target'],
                             weight=str(len(edge['evidence'])), type='directed' if edge.get('directed', edge['predicate'] != 'CO_OCCURS_IN_CHUNK') else 'undirected')
        values = ET.SubElement(node, 'attvalues')
        for key in ['predicate', 'polarity', 'stance', 'evidence_json']:
            value = json.dumps(edge['evidence'], ensure_ascii=False) if key == 'evidence_json' else edge.get(key, '')
            ET.SubElement(values, 'attvalue', {'for': key, 'value': value})
    ET.ElementTree(root).write(str(output / 'network.gexf'), encoding='utf-8', xml_declaration=True)
    return {'files': ['network.graphml', 'network.gexf'], 'nodes': len(graph['entities']), 'edges': len(graph['edges'])}
