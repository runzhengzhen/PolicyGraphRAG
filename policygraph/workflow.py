"""Offline study orchestration, artifact hashes and an inspectable HTML overview."""
import csv
import hashlib
import html
import json
import time
from pathlib import Path
from . import __version__
from .comparison import community_coherence, compare_groups
from .evaluation import evaluate_retrieval
from .extract import Cache
from .graph import build_graph
from .io import chunk_units, digest, load_corpus, write_json
from .network import network_metrics
from .quality import audit_graph
from .research import analyze, render_report
from .visuals import comparison_svg, export_network, plot_graph


def write_csv(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or (list(rows[0]) if rows else ['status'])
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            value = {key: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for key, v in row.items()}
            # Spreadsheet applications can interpret raw leading punctuation as a formula.
            writer.writerow({k: "'"+v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v
                             for k, v in value.items()})


def load_queries(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def study_html(summary, quality, network, coherence, comparison=None, evaluation=None):
    esc = lambda v: html.escape(str(v), quote=True)
    body = '<h1>PolicyGraphRAG 研究工作台</h1><p>语料 → 证据图谱 → 关系分析 → 比较与检索评测</p>'
    body += '<div class="metrics">'+''.join('<section><strong>%s</strong>%s</section>' % (summary[key], label)
                                           for key, label in [('documents', '政策'), ('chunks', '文本块'), ('entities', '实体'), ('relations', '关系')])+'</div>'
    body += '<h2>语料与证据质量</h2><p>引用完整性：%s；精确重复组：%s；相似模板组：%s；缺失日期：%s。</p>' % (
        esc(quality['integrity']), len(quality['exact_duplicate_groups']), len(quality['template_families']), len(quality['missing_date_doc_ids']))
    npmi = '%.3f' % coherence['mean_npmi'] if coherence['mean_npmi'] is not None else '—'
    body += '<h2>显式关系网络</h2><p>%s 条边；%s 个有向实体对；互惠率 %.3f；社区实体 NPMI：%s。</p>' % (
        network['edges'], network['directed_pairs'], network['reciprocity'], npmi)
    body += '<p><a href="network/network.graphml">完整 GraphML</a> · <a href="network/network.gexf">完整 GEXF</a> · <a href="tables/signed-relations.csv">正负关系表</a></p>'
    if comparison:
        body += '<h2>分组比较：%s / %s</h2><img src="figures/group-comparison.svg" alt="分组覆盖率与Wilson区间"/>' % (esc(comparison['left']), esc(comparison['right']))
        body += '<p><a href="tables/group-comparison.csv">完整比较表与统计检验</a></p>'
    if evaluation:
        body += '<h2>检索消融评测</h2><p>按政策去重；@%s；%s 个有标注问题。</p><table><tr><th>模式</th><th>Recall</th><th>MRR</th><th>nDCG</th><th>平均毫秒</th></tr>' % (evaluation['k'], evaluation['query_count'])
        for row in evaluation['summaries']:
            scores = row['mean_metrics']
            body += '<tr><td>%s</td><td>%.3f</td><td>%.3f</td><td>%.3f</td><td>%.2f</td></tr>' % (
                esc(row['mode']), scores.get('recall', 0), scores.get('mrr', 0), scores.get('ndcg', 0), row['mean_latency_ms'])
        body += '</table>'
    body += '<h2>输出文件</h2><p><a href="evidence-report.html">原文证据报告</a> · <a href="quality.json">质量检查</a> · <a href="network-metrics.json">网络指标</a> · <a href="run-manifest.json">运行记录与哈希</a></p>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>PolicyGraphRAG 研究工作台</title><style>body{font:16px/1.7 system-ui,sans-serif;max-width:1080px;margin:40px auto;padding:0 24px;color:#263c43}h1{font-size:30px}h2{margin-top:32px}.metrics{display:flex;gap:50px;flex-wrap:wrap}strong{display:block;font-size:30px;color:#2b827c}img{max-width:100%}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}a{color:#2b827c}</style>'+body+'</html>'


def run_study(input_path, output, namespace=None, algorithm='auto', max_chars=1200,
              aliases=None, lexicon=None, group_field=None, left=None, right=None,
              queries_path=None, k=5, near_threshold=0.85, max_pairs=200000):
    output = Path(output)
    if output.exists() and any(output.iterdir()) and not (output/'run-manifest.json').is_file():
        raise ValueError('Use a new study directory, or rerun an existing study with run-manifest.json')
    if any(x is not None for x in (group_field, left, right)) and not all(x is not None for x in (group_field, left, right)):
        raise ValueError('Provide --group-field, --left and --right together')
    if k < 1:
        raise ValueError('k must be positive')
    start = time.perf_counter()
    documents, units = load_corpus(input_path, namespace)
    input_digest = digest({'documents': [{k: v for k, v in d.items() if k != 'source'} for d in documents],
                           'units': [{k: v for k, v in u.items() if k not in {'source_file', 'source_line'}} for u in units]})
    chunks = chunk_units(units, max_chars)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/'run-manifest.json', {'workflow': 'offline_policy_study', 'status': 'running',
                                          'version': __version__, 'input_digest': input_digest})
    cache = Cache(output/'cache.sqlite3')
    try:
        graph = build_graph(documents, chunks, cache, aliases, lexicon, algorithm=algorithm)
        quality = audit_graph(graph, near_threshold, max_pairs)
        if quality['errors']:
            write_json(output/'quality.json', quality)
            raise ValueError('Graph evidence integrity failed; inspect quality.json')
        network = network_metrics(graph)
        coherence = community_coherence(graph)
        comparison = compare_groups(graph, group_field, left, right) if group_field else None
        queries = load_queries(queries_path) if queries_path else None
        evaluation = evaluate_retrieval(graph, queries, k=k) if queries is not None else None
        summary = analyze(graph)
        generated = []
        for name, value in [('graph.json', graph), ('quality.json', quality), ('network-metrics.json', network),
                            ('community-coherence.json', coherence), ('overview.json', summary)]:
            write_json(output/name, value)
            generated.append(name)
        render_report(graph, output/'evidence-report.html')
        generated.append('evidence-report.html')
        for name, rows in [('tables/node-metrics.csv', network['node_metrics']), ('tables/signed-relations.csv', network['signed_pairs'])]:
            write_csv(output/name, rows)
            generated.append(name)
        generated.extend('figures/'+p for p in plot_graph(graph, output/'figures')['files'])
        generated.extend('network/'+p for p in export_network(graph, output/'network')['files'])
        if comparison:
            write_json(output/'comparison.json', comparison)
            write_csv(output/'tables/group-comparison.csv', comparison['rows'])
            (output/'figures/group-comparison.svg').write_text(comparison_svg(comparison), encoding='utf-8')
            generated.extend(['comparison.json', 'tables/group-comparison.csv', 'figures/group-comparison.svg'])
        if evaluation:
            write_json(output/'evaluation.json', evaluation)
            write_csv(output/'tables/retrieval-evaluation.csv', evaluation['summaries'])
            generated.extend(['evaluation.json', 'tables/retrieval-evaluation.csv'])
        (output/'study.html').write_text(study_html(summary, quality, network, coherence, comparison, evaluation), encoding='utf-8')
        generated.append('study.html')
        manifest = {'version': __version__, 'workflow': 'offline_policy_study', 'status': 'completed',
                    'input_digest': input_digest,
                    'query_digest': digest(queries) if queries is not None else None,
                    'parameters': {'namespace': namespace, 'algorithm': algorithm, 'max_chars': max_chars,
                                   'aliases': aliases or {}, 'lexicon': lexicon, 'group_field': group_field,
                                   'left': left, 'right': right, 'k': k,
                                   'near_threshold': near_threshold, 'max_pairs': max_pairs},
                    'cache': {'hits': cache.hits, 'misses': cache.misses},
                    'elapsed_seconds': time.perf_counter()-start,
                    'artifacts': [{'path': name, 'sha256': hashlib.sha256((output/name).read_bytes()).hexdigest(),
                                   'bytes': (output/name).stat().st_size} for name in sorted(generated)]}
        write_json(output/'run-manifest.json', manifest)
        return manifest
    finally:
        cache.close()
