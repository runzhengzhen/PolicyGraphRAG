import json
import math
import tempfile
import unittest
import contextlib
import io
from unittest.mock import patch
from pathlib import Path

from policygraph.extract import Cache, extract_chunk, validate_extraction
from policygraph.cli import main
from policygraph.graph import build_graph, pagerank, resolve_entity
from policygraph.io import adapt_gtflow, chunk_units, load_corpus
from policygraph.neo4j_export import export_neo4j
from policygraph.research import analyze, render_report
from policygraph.retrieve import SparseIndex, relation_path, retrieve


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cache = Cache(self.root / "cache.sqlite3")

    def tearDown(self):
        self.cache.close()
        self.temp.cleanup()

    def corpus(self, rows):
        path = self.root / "input.jsonl"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
        return load_corpus(path, "test")

    def graph(self):
        documents, units = self.corpus([
            {"id": "a", "date": "2024-01-01", "text": "教育部通过专项资金支持数字教材，提高出版质量。"},
            {"id": "b", "text": "出版社开展监督检查，保障出版质量。"},
            {"id": "c", "text": "作者披露人工智能使用情况，保障学术诚信。"},
        ])
        return build_graph(documents, chunk_units(units), self.cache, algorithm="components")

    def test_incremental_cache_and_provenance_for_identical_documents(self):
        docs, units = self.corpus([{"id": "a", "text": "作者维护学术诚信。"}, {"id": "b", "text": "作者维护学术诚信。"}])
        graph = build_graph(docs, chunk_units(units), self.cache, algorithm="components")
        self.assertEqual(self.cache.misses, 2)  # one extraction and one community summary
        self.assertEqual({m["doc_id"] for e in graph["entities"] for m in e["mentions"]}, {"test:a", "test:b"})
        misses = self.cache.misses
        build_graph(docs, chunk_units(units), self.cache, algorithm="components")
        self.assertEqual(misses, self.cache.misses)
        units[1]["text"] += "并保障数据安全。"
        changed = build_graph(docs, chunk_units(units), self.cache, algorithm="components")
        self.assertTrue(any(e["name"] == "数据安全" for e in changed["entities"]))
        self.assertGreater(self.cache.misses, misses)

    def test_literal_evidence_and_offsets(self):
        text = "作者披露人工智能。"
        result = validate_extraction({"entities": [{"name": "教育部", "type": "actor", "quote": "教育部发布政策"},
                                                    {"name": "作者", "type": "actor", "quote": "作者披露", "start": 5}],
                                      "relations": [{"source": {"name": "作者", "type": "actor"}, "target": {"name": "教育部", "type": "actor"}, "predicate": "USES", "quote": "作者披露"}]}, text)
        self.assertEqual(len(result["entities"]), 1)
        self.assertEqual(result["entities"][0]["start"], 0)
        self.assertEqual(len(result["relations"]), 0)
        self.assertEqual(len(result["rejected"]), 2)

    def test_chunk_reconstruction_and_namespace(self):
        text = "教育部通过专项资金支持教材。\n" * 30
        docs, units = self.corpus([{"doc_id": 0, "para_id": 0, "text": text}, {"doc_id": 0, "para_id": 1, "text": "第二段"}])
        chunks = chunk_units(units, 60)
        self.assertEqual("".join(c["text"] for c in chunks if c["unit_key"] == "0"), text)
        for chunk in chunks:
            unit = next(u for u in units if u["unit_key"] == chunk["unit_key"])
            self.assertEqual(unit["text"][chunk["start"]:chunk["end"]], chunk["text"])
        self.assertEqual(len(docs), 1)

    def test_duplicate_identifiers_fail(self):
        with self.assertRaises(ValueError):
            self.corpus([{"id": "same", "text": "作者。"}, {"id": "same", "text": "教材。"}])

    def test_alias_type_separation_and_cycles(self):
        aliases = {"actor": {"甲部门": "乙部门"}}
        self.assertEqual(resolve_entity("甲部门", "actor", aliases)[0], resolve_entity("乙部门", "actor", aliases)[0])
        self.assertNotEqual(resolve_entity("甲部门", "actor", aliases)[0], resolve_entity("甲部门", "target", aliases)[0])
        with self.assertRaises(ValueError):
            resolve_entity("甲", "actor", {"actor": {"甲": "乙", "乙": "甲"}})

    def test_retrieval_and_no_evidence(self):
        graph = self.graph()
        for mode in ["vector", "local", "global", "hybrid"]:
            result = retrieve(graph, "数字教材与出版质量", mode)
            self.assertTrue(result["hits"], mode)
            self.assertTrue(all(h["chunk_id"] in {c["id"] for c in graph["chunks"]} for h in result["hits"]))
        self.assertEqual(retrieve(graph, "xyzzzzquux", "hybrid")["hits"], [])
        with self.assertRaises(ValueError):
            retrieve(graph, "数字教材", "dense")

    def test_association_path_has_auditable_edges(self):
        graph = self.graph()
        path = relation_path(graph, "教育部", "出版社", 2)
        self.assertTrue(path["found"])
        self.assertEqual(len(path["edges"]), 2)
        self.assertTrue(all(e["predicate"] == "CO_OCCURS_IN_CHUNK" and e["evidence"] for e in path["edges"]))
        self.assertFalse(relation_path(graph, "教育部", "作者", 3)["found"])

    def test_pagerank_dangling_and_empty_graph(self):
        self.assertEqual(pagerank({}), {})
        scores = pagerank({"a": {"b": 1}, "b": {"a": 1}, "c": {}})
        self.assertTrue(math.isclose(sum(scores.values()), 1))
        self.assertGreater(scores["a"], scores["c"])

    def test_date_coverage_and_html_escaping(self):
        graph = self.graph()
        result = analyze(graph, "evolution")
        self.assertEqual(result["undated_documents"], 2)
        self.assertIn("2024", result["yearly_document_community_counts"])
        graph["entities"][0]["name"] = "<script>alert(1)</script>"
        render_report(graph, self.root / "report.html")
        self.assertNotIn("<script>", (self.root / "report.html").read_text())

    def test_date_coverage_includes_documents_without_entities(self):
        docs, units = self.corpus([{"id": "unmapped", "text": "一段尚未纳入词典的表达。"}])
        graph = build_graph(docs, chunk_units(units), self.cache, algorithm="components")
        self.assertFalse(graph["communities"])
        result = analyze(graph, "evolution")
        self.assertEqual(result["undated_documents"], 1)
        self.assertEqual(result["documents_without_community"], 1)

    def test_gtflow_does_not_guess_evidence_identifiers(self):
        (self.root / "segments.json").write_text(json.dumps([{"seg_id": "source-01", "text": "作者披露。", "meta": {"source_id": "source"}}]))
        (self.root / "open_codes.json").write_text(json.dumps([{"seg_id": "source-01", "initial_codes": [{"code": "披露要求", "evidence_span": "作者披露"}]}]))
        (self.root / "axial_triples.json").write_text(json.dumps([{"evidence": ["0001"]}]))
        result = adapt_gtflow(self.root, self.root / "adapted.jsonl")
        self.assertEqual(result["coded_segments"], 1)
        self.assertEqual(result["unresolved_axial_evidence"][0]["unresolved_ids"], ["0001"])
        with contextlib.redirect_stdout(io.StringIO()):
            main(["import-gtflow", "--directory", str(self.root), "--output", str(self.root / "cli-adapted.jsonl")])
        docs, units = load_corpus(self.root / "cli-adapted.jsonl")
        self.assertEqual(units[0]["text"], "作者披露。")

    def test_neo4j_export_is_snapshot_isolated_and_offline(self):
        graph = self.graph()
        result = export_neo4j(graph, self.root / "neo4j")
        self.assertFalse(result["applied"])
        query = (self.root / "neo4j" / "upsert.cypher").read_text()
        self.assertIn("snapshot:$snapshot", query)
        self.assertNotIn("DELETE", query)
        self.assertNotIn("password", (self.root / "neo4j" / "neo4j_payload.json").read_text())

    def test_batched_embedding_cli_and_elapsed_time(self):
        rows = [{"id": str(i), "text": "作者披露人工智能使用情况%s。" % i} for i in range(20)]
        self.corpus(rows)
        class FakeLocalEncoder:
            identity = {"kind": "local_sentence_transformer", "model": "fake", "fingerprint": "test"}
            usage = {"requests": 0}
            def __init__(self, path):
                pass
            def embeddings(self, texts):
                return [[1.0, 0.0] for text in texts]
        with patch('policygraph.local_embeddings.LocalEncoder', FakeLocalEncoder), contextlib.redirect_stdout(io.StringIO()):
            main(["build", "--input", str(self.root / "input.jsonl"), "--output", str(self.root / "out"),
                  "--community", "components", "--local-embedding-model", "fake"])
        graph = json.loads((self.root / "out/graph.json").read_text())
        self.assertEqual(len(graph["embeddings"]), 20)
        self.assertGreaterEqual(graph["build"]["elapsed_seconds"], 0)
        result = retrieve(graph, "AI使用", "hybrid", dense_query=[1, 0])
        self.assertTrue(result["dense_used"])
        self.assertTrue(any("dense" in h["channels"] for h in result["hits"]))


if __name__ == "__main__":
    unittest.main()
