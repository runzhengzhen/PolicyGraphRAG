import copy
import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

from policygraph.comparison import bh_adjust, community_coherence, compare_groups, fisher_exact, wilson
from policygraph.evaluation import evaluate_retrieval, ranking_metrics
from policygraph.extract import Cache
from policygraph.graph import build_graph
from policygraph.io import chunk_units, load_corpus
from policygraph.network import ego_graph, network_metrics
from policygraph.quality import audit_graph
from policygraph.retrieve import RetrievalIndex, SparseIndex, retrieve
from policygraph.workflow import load_queries, run_study, write_csv

ROOT = Path(__file__).resolve().parents[1]


class StatisticsTests(unittest.TestCase):
    def test_fisher_reference_and_symmetry(self):
        expected = 0.0027594561852200836
        for counts in [(1, 9, 11, 3), (11, 3, 1, 9), (9, 1, 3, 11)]:
            self.assertAlmostEqual(fisher_exact(*counts), expected, places=12)
        self.assertEqual(fisher_exact(0, 0, 0, 0), 1)
        with self.assertRaises(ValueError):
            fisher_exact(-1, 1, 2, 3)

    def test_wilson_and_bh_reference(self):
        low, high = wilson(0, 10)
        self.assertAlmostEqual(low, 0)
        self.assertAlmostEqual(high, 0.2775327998628892)
        self.assertEqual(bh_adjust([0.01, 0.04, 0.03]), [0.03, 0.04, 0.04])

    def test_rank_metrics_use_unique_documents_and_grades(self):
        metrics = ranking_metrics(['irrelevant', 'a', 'a', 'b'], {'a': 3, 'b': 1}, 3)
        self.assertEqual(metrics['recall'], 1)
        self.assertEqual(metrics['precision'], 2/3)
        self.assertEqual(metrics['mrr'], 0.5)
        self.assertAlmostEqual(metrics['ndcg'], (7/math.log2(3)+1/math.log2(4))/(7+1/math.log2(3)))
        self.assertEqual(ranking_metrics([], {}, 3)['no_answer_correct'], 1)
        self.assertEqual(ranking_metrics(['x'], {}, 3)['no_answer_correct'], 0)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = Cache(self.root/'cache.sqlite3')
        docs, units = load_corpus(ROOT/'examples/research-policies.jsonl', 'research')
        self.graph = build_graph(docs, chunk_units(units), self.cache, algorithm='components')

    def tearDown(self):
        self.cache.close()
        self.temp.cleanup()

    def test_comparison_counts_documents_not_mentions(self):
        graph = copy.deepcopy(self.graph)
        entity = next(e for e in graph['entities'] if e['name'] == '数字教材')
        entity['mentions'] *= 3
        result = compare_groups(graph, 'cohort', 'A', 'B')
        row = next(r for r in result['rows'] if r['name'] == '数字教材')
        self.assertEqual((row['left_count'], row['right_count'], row['left_n'], row['right_n']), (4, 0, 4, 4))
        self.assertEqual(row['difference_right_minus_left'], -1)
        self.assertTrue(all(r['fdr_bh'] >= r['fisher_p']-1e-12 for r in result['rows']))
        with self.assertRaises(ValueError):
            compare_groups(graph, 'cohort', 'missing', 'B')

    def test_metadata_merges_and_conflicts_are_detected(self):
        source = self.root/'paragraphs.jsonl'
        rows = [{'doc_id': 'p', 'id': '1', 'text': '教育部支持教材。', 'date': '2024', 'metadata': {'cohort': 'A'}},
                {'doc_id': 'p', 'id': '2', 'text': '出版社开展培训。'}]
        def save():
            source.write_text('\n'.join(json.dumps(r) for r in rows))
        save()
        docs, _ = load_corpus(source)
        self.assertEqual(docs[0]['metadata'], {'cohort': 'A'})
        self.assertEqual(docs[0]['date'], '2024')
        rows[1]['metadata'] = {'cohort': 'B'}
        save()
        with self.assertRaisesRegex(ValueError, 'Conflicting metadata'):
            load_corpus(source)
        rows[1]['metadata'] = {}
        rows[1]['date'] = '2025'
        save()
        with self.assertRaisesRegex(ValueError, 'Conflicting dates'):
            load_corpus(source)

    def test_signed_metrics_keep_opposite_polarities(self):
        result = network_metrics(self.graph)
        mixed = [p for p in result['signed_pairs'] if p['mixed_polarity']]
        self.assertEqual(len(mixed), 1)
        self.assertEqual(mixed[0]['positive_evidence'], 1)
        self.assertEqual(mixed[0]['negative_evidence'], 1)
        self.assertEqual(mixed[0]['signed_balance'], 0)
        self.assertEqual(result['directed_pairs'], 4)
        self.assertEqual(result['reciprocity'], 0)
        self.assertEqual(result['edges'], 5)
        self.assertGreater(network_metrics(self.graph, 'all')['edges'], result['edges'])

    def test_reciprocity_density_and_self_loops(self):
        graph = {'entities': [{'id': k, 'name': k, 'type': 'actor'} for k in ['a', 'b']],
                 'edges': [dict(id=str(i), source=a, target=b, predicate='USES', directed=True,
                                evidence=[dict(doc_id='p', chunk_id='c')])
                           for i, (a, b) in enumerate([('a','b'), ('b','a'), ('a','a')])]}
        result = network_metrics(graph)
        self.assertEqual(result['directed_density'], 1)
        self.assertEqual(result['reciprocity'], 1)
        self.assertEqual(result['weak_components'], [['a','b']])

    def test_ego_respects_direction_and_original_graph_is_unchanged(self):
        before = copy.deepcopy(self.graph)
        out = ego_graph(self.graph, '作者', direction='out')
        incoming = ego_graph(self.graph, '作者', direction='in')
        self.assertEqual({e['name'] for e in out['entities']}, {'作者', '人工智能'})
        self.assertEqual({e['name'] for e in incoming['entities']}, {'作者', '编辑部'})
        self.assertEqual(self.graph, before)
        self.assertTrue(all(e['predicate'] != 'CO_OCCURS_IN_CHUNK' for e in out['edges']))

    def test_audit_detects_duplicate_documents_and_broken_evidence(self):
        result = audit_graph(self.graph)
        self.assertEqual(result['integrity'], 'passed')
        self.assertEqual(result['exact_duplicate_groups'], [['research:A1', 'research:A2']])
        self.assertEqual(result['missing_date_doc_ids'], ['research:B4'])
        graph = copy.deepcopy(self.graph)
        graph['edges'][0]['evidence'][0]['doc_id'] = 'missing'
        graph['documents'][0]['date'] = '2024-02-30'
        result = audit_graph(graph)
        self.assertEqual(result['integrity'], 'failed')
        self.assertIn('edge_evidence', {r['kind'] for r in result['errors']})
        self.assertEqual(result['invalid_date_doc_ids'], ['research:A1'])
        with self.assertRaisesRegex(ValueError, 'pairs'):
            audit_graph(self.graph, max_pairs=1)

    def test_coherence_extremes_and_single_entity(self):
        graph = {'documents': [{'id': 'p'}, {'id': 'q'}], 'entities': [
            dict(id='a', pagerank=1, mentions=[dict(doc_id='p')]),
            dict(id='b', pagerank=1, mentions=[dict(doc_id='q')])],
            'communities': [dict(id='g', entity_ids=['a', 'b'])]}
        self.assertEqual(community_coherence(graph)['mean_npmi'], -1)
        for e in graph['entities']:
            e['mentions'] = [dict(doc_id='p'), dict(doc_id='q')]
        self.assertEqual(community_coherence(graph)['mean_npmi'], 1)
        graph['communities'][0]['entity_ids'] = ['a']
        self.assertIsNone(community_coherence(graph)['mean_npmi'])

    def test_repeated_search_reuses_two_indexes_and_preserves_results(self):
        expected = retrieve(self.graph, '数字教材出版质量')
        with patch('policygraph.retrieve.SparseIndex', wraps=SparseIndex) as constructor:
            index = RetrievalIndex(self.graph)
            self.assertEqual(index.search('数字教材出版质量'), expected)
            index.search('作者人工智能')
            self.assertEqual(constructor.call_count, 2)

    def test_evaluation_rejects_invalid_judgments(self):
        queries = load_queries(ROOT/'examples/retrieval-judgments.jsonl')
        result = evaluate_retrieval(self.graph, queries, k=3)
        self.assertEqual(len(result['summaries']), 4)
        self.assertTrue(all(row['no_answer_accuracy'] == 1 for row in result['summaries']))
        for bad in [queries+[queries[0]], [dict(id='bad', question='q', relevance={'unknown': 1})],
                    [dict(id='bad', question='q', relevance={'A1': -1})]]:
            with self.assertRaises(ValueError):
                evaluate_retrieval(self.graph, bad)

    def test_study_rerun_manifest_and_relocation_fingerprint(self):
        source, queries = ROOT/'examples/research-policies.jsonl', ROOT/'examples/retrieval-judgments.jsonl'
        options = dict(namespace='stable', algorithm='components', group_field='cohort', left='A', right='B', queries_path=queries, k=3)
        first = run_study(source, self.root/'study', **options)
        self.assertEqual(first['status'], 'completed')
        for artifact in first['artifacts']:
            self.assertEqual(hashlib.sha256((self.root/'study'/artifact['path']).read_bytes()).hexdigest(), artifact['sha256'])
        self.assertIn('Wilson', (self.root/'study/study.html').read_text())
        for artifact in first['artifacts']:
            if artifact['path'].endswith('.svg'):
                ET.parse(str(self.root/'study'/artifact['path']))
        copied = self.root/'relocated.jsonl'
        copied.write_bytes(source.read_bytes())
        second = run_study(copied, self.root/'study', **options)
        self.assertEqual(second['cache']['misses'], 0)
        self.assertEqual(second['input_digest'], first['input_digest'])
        occupied = self.root/'occupied'
        occupied.mkdir()
        (occupied/'keep.txt').write_text('original')
        with self.assertRaises(ValueError):
            run_study(source, occupied)
        self.assertEqual((occupied/'keep.txt').read_text(), 'original')

    def test_csv_exports_do_not_execute_spreadsheet_formulas(self):
        output = self.root/'table.csv'
        write_csv(output, [{'name': '=1+2', 'value': -0.2}])
        text = output.read_text(encoding='utf-8-sig')
        self.assertIn("'=1+2", text)
        self.assertIn('-0.2', text)


if __name__ == '__main__':
    unittest.main()
