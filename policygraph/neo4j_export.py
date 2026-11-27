from __future__ import annotations

import json
import os
from pathlib import Path
from .io import digest, write_json

QUERIES = [
    ("documents", "UNWIND $rows AS row MERGE (d:PolicyDocument {id:row.id,snapshot:$snapshot}) SET d.title=row.title,d.date=row.date,d.source=row.source"),
    ("chunks", "UNWIND $rows AS row MATCH (d:PolicyDocument {id:row.doc_id,snapshot:$snapshot}) MERGE (c:PolicyChunk {id:row.id,snapshot:$snapshot}) SET c.text=row.text,c.start=row.start,c.end=row.end,c.unit_key=row.unit_key MERGE (d)-[:HAS_CHUNK]->(c)"),
    ("entities", "UNWIND $rows AS row MERGE (e:PolicyEntity {id:row.id,snapshot:$snapshot}) SET e.name=row.name,e.type=row.type,e.pagerank=row.pagerank"),
    ("mentions", "UNWIND $rows AS row MATCH (e:PolicyEntity {id:row.entity_id,snapshot:$snapshot}), (c:PolicyChunk {id:row.chunk_id,snapshot:$snapshot}) MERGE (e)-[:MENTIONED_IN]->(c)"),
    ("edges", "UNWIND $rows AS row MATCH (a:PolicyEntity {id:row.source,snapshot:$snapshot}), (b:PolicyEntity {id:row.target,snapshot:$snapshot}) MERGE (a)-[r:POLICY_RELATION {id:row.id}]->(b) SET r.predicate=row.predicate,r.evidence_json=row.evidence_json,r.directed=row.directed,r.polarity=row.polarity,r.stance=row.stance"),
]


def export_neo4j(graph, output, apply=False):
    payload = {"snapshot": digest([graph["documents"], graph["chunks"], graph["entities"], graph["edges"]])[:24],
               "documents": graph["documents"], "chunks": graph["chunks"], "entities": graph["entities"],
               "mentions": [{"entity_id": e["id"], "chunk_id": chunk_id} for e in graph["entities"]
                            for chunk_id in sorted({m["chunk_id"] for m in e["mentions"]})],
               "edges": [dict(e, directed=e.get('directed', e['predicate'] != 'CO_OCCURS_IN_CHUNK'), polarity=e.get('polarity', '+'),
                              stance=e.get('stance', ''), evidence_json=json.dumps(e["evidence"], ensure_ascii=False)) for e in graph["edges"]]}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "neo4j_payload.json", payload)
    (output / "upsert.cypher").write_text("\n\n".join("// %s: supply rows and snapshot parameters\n%s;" % item for item in QUERIES), encoding="utf-8")
    if apply:
        from neo4j import GraphDatabase
        with GraphDatabase.driver(os.environ["NEO4J_URI"], auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])) as driver:
            driver.verify_connectivity()
            for kind, query in QUERIES:
                for start in range(0, len(payload[kind]), 500):
                    driver.execute_query(query, rows=payload[kind][start:start + 500], snapshot=payload["snapshot"], database_=os.environ.get("NEO4J_DATABASE", "neo4j"))
    return {"snapshot": payload["snapshot"], "applied": apply, "output": str(output),
            "note": "Snapshot-isolated MERGE, no deletion. Retry the same snapshot after interrupted imports."}
