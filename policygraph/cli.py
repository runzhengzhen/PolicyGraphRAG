from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from . import __version__
from .extract import Cache, ModelClient
from .graph import build_graph
from .io import adapt_gtflow, chunk_units, digest, load_corpus, read_json, write_json
from .neo4j_export import export_neo4j
from .research import analyze, render_report
from .retrieve import relation_path, retrieve


def parser():
    p = argparse.ArgumentParser(description="PolicyGraphRAG local research workbench")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="command", required=True)
    study = commands.add_parser('study', help='Run a reproducible offline research workflow')
    study.add_argument('--input', required=True)
    study.add_argument('--output', required=True)
    study.add_argument('--namespace')
    study.add_argument('--community', choices=['auto', 'leiden', 'components'], default='auto')
    study.add_argument('--max-chars', type=int, default=1200)
    study.add_argument('--aliases')
    study.add_argument('--lexicon')
    study.add_argument('--group-field')
    study.add_argument('--left')
    study.add_argument('--right')
    study.add_argument('--queries')
    study.add_argument('--k', type=int, default=5)
    study.add_argument('--near-threshold', type=float, default=0.85)
    study.add_argument('--max-pairs', type=int, default=200000)
    audit = commands.add_parser('audit', help='Check evidence, dates and duplicate/template families')
    audit.add_argument('--graph', required=True)
    audit.add_argument('--output')
    audit.add_argument('--near-threshold', type=float, default=0.85)
    audit.add_argument('--max-pairs', type=int, default=200000)
    network_stats = commands.add_parser('network', help='Analyze directed and signed relation networks')
    network_stats.add_argument('--graph', required=True)
    network_stats.add_argument('--layer', choices=['explicit', 'cooccurrence', 'all'], default='explicit')
    network_stats.add_argument('--output', required=True)
    ego = commands.add_parser('ego', help='Export a directional ego network with evidence')
    ego.add_argument('--graph', required=True)
    ego.add_argument('--entity', required=True)
    ego.add_argument('--radius', type=int, default=1)
    ego.add_argument('--direction', choices=['both', 'in', 'out'], default='both')
    ego.add_argument('--layer', choices=['explicit', 'cooccurrence', 'all'], default='explicit')
    ego.add_argument('--output', required=True)
    compare = commands.add_parser('compare', help='Compare document prevalence in two metadata groups')
    compare.add_argument('--graph', required=True)
    compare.add_argument('--field', required=True)
    compare.add_argument('--left', required=True)
    compare.add_argument('--right', required=True)
    compare.add_argument('--output', required=True)
    evaluate = commands.add_parser('evaluate', help='Evaluate offline retrieval modes against judged queries')
    evaluate.add_argument('--graph', required=True)
    evaluate.add_argument('--queries', required=True)
    evaluate.add_argument('--modes', default='vector,local,global,hybrid')
    evaluate.add_argument('--k', type=int, default=5)
    evaluate.add_argument('--output')
    relations = commands.add_parser('import-relations', help='Import evidence-backed researcher-coded CSV/TSV relations')
    relations.add_argument('--input', required=True)
    relations.add_argument('--output', required=True)
    plot = commands.add_parser('plot', help='Generate portable SVG research figures')
    plot.add_argument('--graph', required=True)
    plot.add_argument('--output', required=True)
    plot.add_argument('--top-n', type=int, default=18)
    network = commands.add_parser('export-network', help='Export GraphML and GEXF with evidence and direction')
    network.add_argument('--graph', required=True)
    network.add_argument('--output', required=True)
    build = commands.add_parser("build", help="Build graph; local lexicon extraction by default")
    build.add_argument("--input", required=True)
    build.add_argument("--output", required=True)
    build.add_argument("--namespace")
    build.add_argument("--max-chars", type=int, default=1200)
    build.add_argument("--community", choices=["auto", "leiden", "components"], default="auto")
    build.add_argument("--aliases", help="Typed explicit alias mapping JSON")
    build.add_argument("--lexicon", help="Four-type entity lexicon JSON")
    build.add_argument("--llm-model", help="Explicitly enable paid/network extraction; no default model calls")
    build.add_argument("--embedding-model", help="Explicitly enable paid/network dense embedding generation")
    build.add_argument("--local-embedding-model", help="Complete local SentenceTransformer snapshot; offline CPU encoding")
    query = commands.add_parser("query")
    query.add_argument("--graph", required=True)
    query.add_argument("--question", required=True)
    query.add_argument("--mode", choices=["hybrid", "vector", "local", "global", "dense"], default="hybrid")
    query.add_argument("--top-k", type=int, default=8)
    query.add_argument("--hops", type=int, default=2)
    query.add_argument("--dense-query", action="store_true", help="Encode query with the saved local or remote embedding model")
    query.add_argument("--output")
    analysis = commands.add_parser("analyze")
    analysis.add_argument("--graph", required=True)
    analysis.add_argument("--kind", choices=["overview", "actors", "tools", "coding", "evolution", "coherence"], default="overview")
    analysis.add_argument("--output")
    path = commands.add_parser("path")
    path.add_argument("--graph", required=True)
    path.add_argument("--source", required=True)
    path.add_argument("--target", required=True)
    path.add_argument("--max-hops", type=int, default=3)
    path.add_argument("--output")
    report = commands.add_parser("report")
    report.add_argument("--graph", required=True)
    report.add_argument("--query-result")
    report.add_argument("--output", required=True)
    gtflow = commands.add_parser("import-gtflow")
    gtflow.add_argument("--directory", required=True)
    gtflow.add_argument("--output", required=True)
    export = commands.add_parser("export-neo4j")
    export.add_argument("--graph", required=True)
    export.add_argument("--output", required=True)
    export.add_argument("--apply", action="store_true", help="Explicit live DB upsert using NEO4J_* environment variables")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == 'study':
        from .workflow import run_study
        result = run_study(args.input, args.output, args.namespace, args.community, args.max_chars,
                           read_json(args.aliases) if args.aliases else None,
                           read_json(args.lexicon) if args.lexicon else None,
                           args.group_field, args.left, args.right, args.queries, args.k,
                           args.near_threshold, args.max_pairs)
        print(json.dumps({'output': args.output, 'artifacts': len(result['artifacts']), 'cache': result['cache']}, ensure_ascii=False))
        return
    if args.command in {'network', 'ego', 'compare'}:
        from .network import ego_graph, network_metrics
        from .comparison import compare_groups
        from .visuals import comparison_svg, export_network, graph_svg
        from .workflow import write_csv
        graph = read_json(args.graph)
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        if args.command == 'network':
            result = network_metrics(graph, args.layer)
            write_json(output/'metrics.json', result)
            write_csv(output/'nodes.csv', result['node_metrics'])
            write_csv(output/'signed-pairs.csv', result['signed_pairs'])
        elif args.command == 'compare':
            result = compare_groups(graph, args.field, args.left, args.right)
            write_json(output/'comparison.json', result)
            write_csv(output/'comparison.csv', result['rows'])
            (output/'comparison.svg').write_text(comparison_svg(result), encoding='utf-8')
        else:
            result = ego_graph(graph, args.entity, args.radius, args.direction, args.layer)
            write_json(output/'graph.json', result)
            export_network(result, output)
            (output/'network.svg').write_text(graph_svg(result, min(60, max(2, len(result['entities'])))), encoding='utf-8')
        print(json.dumps({'output': str(output), 'kind': args.command}, ensure_ascii=False))
        return
    if args.command == 'import-relations':
        from .relations import import_relations
        print(json.dumps(import_relations(args.input, args.output), ensure_ascii=False, indent=2))
        return
    if args.command in {'plot', 'export-network'}:
        from .visuals import plot_graph, export_network
        graph = read_json(args.graph)
        result = plot_graph(graph, args.output, args.top_n) if args.command == 'plot' else export_network(graph, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == "build":
        build_started_at = time.monotonic()
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        if Path(args.input).resolve() == (output / "graph.json").resolve():
            raise ValueError("Input must differ from output graph")
        documents, units = load_corpus(args.input, args.namespace)
        chunks = chunk_units(units, args.max_chars)
        aliases = read_json(args.aliases) if args.aliases else {}
        lexicon = read_json(args.lexicon) if args.lexicon else None
        client = ModelClient(args.llm_model) if args.llm_model else None
        if args.embedding_model and args.local_embedding_model:
            raise ValueError("Choose either remote or local embeddings")
        embedding_client = ModelClient(args.embedding_model) if args.embedding_model else None
        if args.local_embedding_model:
            from .local_embeddings import LocalEncoder
            embedding_client = LocalEncoder(args.local_embedding_model)
        cache = Cache(output / "cache.sqlite3")
        try:
            graph = build_graph(documents, chunks, cache, aliases, lexicon, client, args.community)
            if embedding_client:
                embeddings = {}
                pending = []
                for chunk in chunks:
                    key = digest(["embedding-v1", chunk["text"], embedding_client.identity])
                    vector = cache.get(key)
                    if vector is None:
                        pending.append((chunk, key))
                    else:
                        embeddings[chunk["id"]] = vector
                for start in range(0, len(pending), 16):
                    batch = pending[start:start + 16]
                    vectors = embedding_client.embeddings([chunk["text"] for chunk, _ in batch])
                    for (chunk, key), vector in zip(batch, vectors):
                        cache.put(key, vector)
                        embeddings[chunk["id"]] = vector
                graph["embeddings"] = embeddings
                graph["embedding_provider"] = embedding_client.identity
            summary = analyze(graph)
            summary.update(cache_hits=cache.hits, cache_misses=cache.misses, elapsed_seconds=round(time.monotonic() - build_started_at, 3),
                           model_usage=client.usage if client else {"requests": 0},
                           embedding_usage=embedding_client.usage if embedding_client else {"requests": 0},
                           incremental_scope="Content-keyed extraction/embedding/community-summary cache; global graph and Leiden recomputed.")
            graph["build"] = summary
            write_json(output / "graph.json", graph)
            write_json(output / "build.json", summary)
            render_report(graph, output / "report.html")
        finally:
            cache.close()
        print(json.dumps({k: v for k, v in summary.items() if k != "top_entities"}, ensure_ascii=False, indent=2))
        return
    if args.command == "import-gtflow":
        result = adapt_gtflow(args.directory, args.output)
        print(json.dumps(dict(result, output=args.output), ensure_ascii=False))
        return
    else:
        graph = read_json(args.graph)
        if args.command == 'audit':
            from .quality import audit_graph
            result = audit_graph(graph, args.near_threshold, args.max_pairs)
            if args.output:
                write_json(args.output, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result['errors']:
                raise SystemExit(1)
            return
        elif args.command == 'evaluate':
            from .evaluation import evaluate_retrieval
            from .workflow import load_queries
            result = evaluate_retrieval(graph, load_queries(args.queries), args.modes.split(','), args.k)
        elif args.command == "query":
            query_embedding = None
            if args.dense_query:
                provider = graph.get("embedding_provider")
                if not provider:
                    raise ValueError("Build dense embeddings first")
                if provider.get("kind") == "local_sentence_transformer":
                    from .local_embeddings import LocalEncoder
                    client = LocalEncoder(provider["model"])
                else:
                    client = ModelClient(provider["model"])
                if client.identity != provider:
                    raise ValueError("Dense query endpoint/model differs from index")
                query_embedding = client.embeddings([args.question])[0]
            result = retrieve(graph, args.question, args.mode, args.top_k, args.hops, query_embedding)
        elif args.command == "analyze":
            if args.kind == 'coherence':
                from .comparison import community_coherence
                result = community_coherence(graph)
            else:
                result = analyze(graph, args.kind)
        elif args.command == "path":
            result = relation_path(graph, args.source, args.target, args.max_hops)
        elif args.command == "report":
            result = render_report(graph, args.output, read_json(args.query_result) if args.query_result else None)
            print(json.dumps({"output": args.output, "documents": result["documents"]}, ensure_ascii=False))
            return
        elif args.command == "export-neo4j":
            result = export_neo4j(graph, args.output, args.apply)
            print(json.dumps(result, ensure_ascii=False))
            return
    if args.output:
        write_json(args.output, result)
        print(json.dumps({"output": args.output}, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print("policygraph: " + str(exc), file=sys.stderr)
        sys.exit(2)
