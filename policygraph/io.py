from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(temp), str(path))


def load_corpus(path, namespace=None):
    """Load native JSONL, TopicGPT paragraphs or a directory of UTF-8 .txt files.

    Offsets are relative to the exact input record text, not a reconstructed PDF.
    """
    path = Path(path)
    namespace = namespace or path.stem
    records = []
    if path.is_dir():
        for p in sorted(path.rglob("*.txt")):
            if p.is_symlink():
                continue
            records.append({"id": str(p.relative_to(path)), "title": p.stem,
                            "text": p.read_text(encoding="utf-8"), "source_file": str(p)})
    elif path.suffix == ".txt":
        records = [{"id": path.stem, "text": path.read_text(encoding="utf-8")}]
    elif path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("JSONL record must be an object at line %s" % line_no)
                    row = dict(row)
                    row.setdefault("source_line", line_no)
                    records.append(row)
    else:
        raise ValueError("Supported inputs: .jsonl, .txt, directory of .txt files")
    documents = {}
    units = []
    seen = set()
    for row_no, row in enumerate(records):
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Empty or missing text at record %s" % (row_no + 1))
        native_id = row.get("doc_id", row.get("id", str(row_no)))
        doc_id = namespace + ":" + str(native_id)
        unit_key = str(row.get("para_id", row.get("id", row_no)))
        key = (doc_id, unit_key)
        if key in seen:
            raise ValueError("Duplicate document/unit identifier: %r" % (key,))
        seen.add(key)
        title = str(row.get("title") or row.get("标题") or row.get("journal") or native_id)
        document = {"id": doc_id, "title": title, "namespace": namespace,
                    "date": str(row.get("date") or row.get("发布日期") or ""),
                    "source": str(path), "native_id": str(native_id)}
        metadata = row.get("metadata", {})
        if not isinstance(metadata, dict) or any(not isinstance(k, str) for k in metadata):
            raise ValueError("metadata must be an object with string keys")
        document["metadata"] = dict(metadata)
        if doc_id in documents and documents[doc_id]["title"] != title:
            raise ValueError("Conflicting titles for doc_id %s" % doc_id)
        if doc_id in documents:
            previous = documents[doc_id]
            if previous['date'] and document['date'] and previous['date'] != document['date']:
                raise ValueError("Conflicting dates for doc_id %s" % doc_id)
            document['date'] = document['date'] or previous['date']
            for field, value in previous.get('metadata', {}).items():
                if field in metadata and metadata[field] != value:
                    raise ValueError("Conflicting metadata for doc_id %s: %s" % (doc_id, field))
                document['metadata'].setdefault(field, value)
        documents[doc_id] = document
        units.append({"doc_id": doc_id, "unit_key": unit_key, "text": text,
                      "source_line": row.get("source_line"),
                      "source_file": row.get("source_file", str(path)),
                      "codes": row.get("codes", []),
                      "entities": row.get("entities", []), "relations": row.get("relations", [])})
    if not units:
        raise ValueError("No policy text found")
    return list(documents.values()), units


def chunk_units(units, max_chars=1200):
    if max_chars < 40:
        raise ValueError("max_chars must be >= 40")
    chunks = []
    for unit in units:
        text = unit["text"]
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                cut = max(text.rfind(mark, start + max_chars // 2, end)
                          for mark in ("\n", "。", "；", ";", ". "))
                if cut >= start:
                    end = cut + 1
            value = dict(unit)
            value.update(start=start, end=end, text=text[start:end])
            value["id"] = "c_" + digest([unit["doc_id"], unit["unit_key"], start, end, value["text"]])[:24]
            chunks.append(value)
            start = end
    return chunks


def adapt_gtflow(directory, output):
    """Export completed segment/code results; never execute legacy scripts."""
    directory = Path(directory)
    segments = read_json(directory / "segments.json")
    coding_path = directory / "open_codes.jsonl"
    if coding_path.exists():
        codes = [json.loads(line) for line in coding_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        codes = read_json(directory / "open_codes.json")
    by_id = {str(s["seg_id"]): s for s in segments}
    if len(by_id) != len(segments):
        raise ValueError("Duplicate GTFlow segment ids")
    coding = {}
    unresolved = []
    for item in codes:
        seg_id = str(item["seg_id"])
        if seg_id not in by_id:
            unresolved.append(seg_id)
        else:
            coding.setdefault(seg_id, []).extend(item.get("initial_codes", []))
    rows = []
    for seg_id, segment in by_id.items():
        meta = segment.get("meta") or {}
        rows.append({"doc_id": str(meta.get("source_id") or seg_id), "id": seg_id,
                     "title": str(meta.get("journal") or meta.get("source_id") or seg_id),
                     "date": str(meta.get('date') or meta.get('发布日期') or ''),
                     "metadata": dict(meta), "text": segment["text"], "codes": coding.get(seg_id, [])})
    triples_path = directory / "axial_triples.json"
    unresolved_triples = []
    if triples_path.exists():
        for i, triple in enumerate(read_json(triples_path)):
            missing = [str(s) for s in triple.get("evidence", []) if str(s) not in by_id]
            if missing:
                unresolved_triples.append({"triple_index": i, "unresolved_ids": missing})
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    report = {"segments": len(segments), "coded_segments": len(coding),
              "unresolved_open_code_ids": unresolved, "unresolved_axial_evidence": unresolved_triples,
              "note": "Axial triples are audit-only; no inferred remapping of evidence IDs."}
    write_json(str(output) + ".audit.json", report)
    return report
