"""Import researcher-supplied relations without inferring missing evidence."""
import csv
import json
from pathlib import Path
from .extract import PREDICATES, TYPES, validate_extraction
from .io import write_json


def import_relations(source, output):
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError('Input and output must differ')
    records, rejected, seen = [], [], set()
    with source.open(encoding='utf-8-sig', newline='') as handle:
        rows = csv.DictReader(handle, delimiter='\t' if source.suffix.lower() == '.tsv' else ',')
        required = {'id', 'doc_id', 'source', 'source_type', 'target', 'target_type', 'predicate', 'quote'}
        if not required <= set(rows.fieldnames or []):
            raise ValueError('Missing relation columns: ' + ', '.join(sorted(required - set(rows.fieldnames or []))))
        for line, row in enumerate(rows, 2):
            key = (row['doc_id'].strip(), row['id'].strip())
            if not all(key) or key in seen:
                raise ValueError('Missing/duplicate document-relation ID at line %s' % line)
            seen.add(key)
            text = row.get('text') or row['quote']
            ends = [{'name': row[n], 'type': row[n + '_type'], 'quote': row['quote']} for n in ['source', 'target']]
            relation = {'source': {'name': row['source'], 'type': row['source_type']},
                        'target': {'name': row['target'], 'type': row['target_type']},
                        'predicate': row['predicate'], 'quote': row['quote'],
                        'polarity': row.get('polarity') or '+', 'stance': row.get('stance') or ''}
            valid = validate_extraction({'entities': ends, 'relations': [relation]}, text)
            if not valid['relations']:
                rejected.append({'source_line': line, 'id': key[1], 'reasons': valid['rejected']})
                continue
            records.append({'id': key[1], 'doc_id': key[0], 'title': row.get('title') or key[0],
                            'date': row.get('date') or '', 'text': text, 'source_line': line,
                            'source_file': str(source), 'entities': valid['entities'], 'relations': valid['relations']})
    if not records:
        raise ValueError('No relations have valid endpoints and literal evidence')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf-8')
    audit = {'accepted': len(records), 'rejected': rejected,
             'meaning': 'Researcher-coded relations with validated literal evidence and endpoint locations.'}
    write_json(str(output) + '.audit.json', audit)
    return audit
