import csv
import hashlib
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from policygraph.extract import Cache
from policygraph.graph import build_graph
from policygraph.io import chunk_units, load_corpus
from policygraph.relations import import_relations
from policygraph.visuals import export_network, graph_svg, plot_graph


class PublicWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = Cache(self.root / 'cache.sqlite3')

    def tearDown(self):
        self.cache.close()
        self.temp.cleanup()

    def relation_graph(self):
        source = Path(__file__).resolve().parents[1] / 'examples/relations.csv'
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        import_relations(source, self.root / 'relations.jsonl')
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        docs, units = load_corpus(self.root / 'relations.jsonl')
        return build_graph(docs, chunk_units(units), self.cache, algorithm='components')

    def test_direction_polarity_stance_and_literal_evidence_survive_import(self):
        graph = self.relation_graph()
        edges = [e for e in graph['edges'] if e['predicate'] == 'USES']
        self.assertEqual(len(edges), 3)
        negative = next(e for e in edges if e['polarity'] == '-')
        positive = next(e for e in edges if e['source'] == negative['source'] and e['polarity'] == '+')
        self.assertEqual(negative['target'], positive['target'])
        self.assertNotEqual(negative['id'], positive['id'])
        self.assertEqual(negative['stance'], 'B')
        self.assertTrue(all(e['directed'] for e in edges))
        chunks = {c['id']: c for c in graph['chunks']}
        for edge in edges:
            for evidence in edge['evidence']:
                self.assertIn(evidence['quote'], chunks[evidence['chunk_id']]['text'])
                self.assertEqual(evidence['method'], 'provided_annotation')

    def test_annotation_changes_invalidate_content_cache(self):
        row = {'id': 'same', 'text': '作者使用人工智能。',
               'entities': [{'name': '作者', 'type': 'actor', 'quote': '作者'},
                            {'name': '人工智能', 'type': 'target', 'quote': '人工智能'}],
               'relations': [{'source': {'name': '作者', 'type': 'actor'}, 'target': {'name': '人工智能', 'type': 'target'},
                              'predicate': 'USES', 'quote': '作者使用人工智能。', 'polarity': '+'}]}
        path = self.root / 'annotations.jsonl'
        path.write_text(json.dumps(row))
        docs, units = load_corpus(path)
        original = build_graph(docs, chunk_units(units), self.cache, algorithm='components')
        row['relations'][0]['polarity'] = '-'
        path.write_text(json.dumps(row))
        docs, units = load_corpus(path)
        updated = build_graph(docs, chunk_units(units), self.cache, algorithm='components')
        self.assertEqual([e['polarity'] for e in original['edges'] if e['predicate'] == 'USES'], ['+'])
        self.assertEqual([e['polarity'] for e in updated['edges'] if e['predicate'] == 'USES'], ['-'])

    def test_relation_without_endpoint_evidence_is_rejected(self):
        source = Path(__file__).resolve().parents[1] / 'examples/relations.csv'
        with source.open(encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        rows.append(dict(rows[0], id='unsupported', target='未出现的实体'))
        bad = self.root / 'mixed.csv'
        with bad.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        audit = import_relations(bad, self.root / 'accepted.jsonl')
        self.assertEqual(audit['accepted'], 3)
        self.assertEqual(audit['rejected'][0]['id'], 'unsupported')

    def test_network_formats_preserve_evidence_and_mixed_direction(self):
        graph = self.relation_graph()
        result = export_network(graph, self.root)
        self.assertEqual(result['edges'], len(graph['edges']))
        graphml = ET.parse(str(self.root / 'network.graphml'))
        edges = graphml.findall('.//{http://graphml.graphdrawing.org/xmlns}edge')
        self.assertEqual(len(edges), len(graph['edges']))
        self.assertIn('true', {e.attrib['directed'] for e in edges})
        self.assertIn('false', {e.attrib['directed'] for e in edges})
        stored = next(e for e in edges if any(n.attrib['key'] == 'polarity' and n.text == '-' for n in e))
        evidence = json.loads(next(n.text for n in stored if n.attrib['key'] == 'evidence_json'))
        self.assertTrue(evidence[0]['quote'])
        gexf = ET.parse(str(self.root / 'network.gexf'))
        exported = gexf.findall('.//{http://gexf.net/1.3}edge')
        self.assertEqual(len(exported), len(graph['edges']))

    def test_svg_is_valid_and_escapes_user_labels(self):
        graph = self.relation_graph()
        graph['entities'][0]['name'] = '<script>alert(1)</script>'
        svg = graph_svg(graph)
        self.assertNotIn('<script>', svg)
        ET.fromstring(svg)
        result = plot_graph(graph, self.root / 'figures')
        self.assertEqual(len(result['files']), 4)
        for name in result['files']:
            ET.parse(str(self.root / 'figures' / name))


class PublicReleaseScopeTests(unittest.TestCase):
    def test_scope_and_content_checks_catch_private_materials(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        from check_release import inspect_content, is_public_name, source_files
        self.assertFalse(is_public_name('original_research/result.csv'))
        self.assertFalse(is_public_name('docs/.env'))
        self.assertFalse(is_public_name('../private.txt'))
        self.assertTrue(is_public_name('examples/policies.jsonl'))
        personal_path = '/' + 'Users' + '/example-person/document'
        token = 'sk-' + 'x' * 32
        reasons = {r['reason'] for r in inspect_content('docs/example.md', (personal_path + '\n' + token).encode())}
        self.assertEqual(reasons, {'home_directory', 'api_token'})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'README.md').write_text('Synthetic source distribution')
            (root / 'release-manifest.json').write_text('{}')
            (root / 'PKG-INFO').write_text('Metadata-Version: 2.4')
            (root / 'setup.cfg').write_text('[egg_info]\n')
            files, problems = source_files(root)
            self.assertFalse(problems)
            self.assertEqual([p.name for p in files], ['README.md'])


if __name__ == '__main__':
    unittest.main()
