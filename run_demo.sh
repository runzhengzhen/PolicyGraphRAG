#!/bin/sh
set -eu
cd "$(dirname "$0")"
POLICYGRAPH_BIN="${POLICYGRAPH_PYTHON:-python3}"
"$POLICYGRAPH_BIN" -m policygraph build --input examples/policies.jsonl --output outputs/demo --community auto
"$POLICYGRAPH_BIN" -m policygraph query --graph outputs/demo/graph.json --question '数字教材与出版质量' --output outputs/demo/query.json
"$POLICYGRAPH_BIN" -m policygraph report --graph outputs/demo/graph.json --query-result outputs/demo/query.json --output outputs/demo/evidence-report.html
"$POLICYGRAPH_BIN" -m policygraph plot --graph outputs/demo/graph.json --output outputs/demo/figures
"$POLICYGRAPH_BIN" -m policygraph export-network --graph outputs/demo/graph.json --output outputs/demo/network
"$POLICYGRAPH_BIN" -m policygraph import-relations --input examples/relations.csv --output outputs/relations/input.jsonl
"$POLICYGRAPH_BIN" -m policygraph build --input outputs/relations/input.jsonl --output outputs/relations --community auto
"$POLICYGRAPH_BIN" -m policygraph plot --graph outputs/relations/graph.json --output outputs/relations/figures
"$POLICYGRAPH_BIN" -m policygraph study --input examples/research-policies.jsonl --output outputs/research-study --namespace research-demo --group-field cohort --left A --right B --queries examples/retrieval-judgments.jsonl --k 3
"$POLICYGRAPH_BIN" -m policygraph ego --graph outputs/research-study/graph.json --entity 作者 --direction out --output outputs/research-ego
