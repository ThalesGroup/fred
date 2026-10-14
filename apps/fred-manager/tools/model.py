#!/usr/bin/env python3
"""Compile the direct-role/union subset used by this service; refuse other DSL."""
import argparse
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
model = {'schema_version': '1.1', 'type_definitions': []}
current = None
for raw in (root / 'openfga/model.fga').read_text().splitlines():
    line = raw.split('#', 1)[0].strip()
    if not line or line in ('model', 'schema 1.1', 'relations'):
        continue
    if match := re.fullmatch(r'type (\w+)', line):
        current = {'type': match[1]}
        model['type_definitions'].append(current)
    elif match := re.fullmatch(r'define (\w+): (.+)', line):
        assert current is not None
        children = []
        direct = False
        for term in match[2].split(' or '):
            if term == '[user]':
                direct = True
                children.append({'this': {}})
            elif re.fullmatch(r'\w+', term):
                children.append({'computedUserset': {'relation': term}})
            else:
                raise ValueError('Unsupported model syntax')
        current.setdefault('relations', {})[match[1]] = children[0] if len(children) == 1 else {'union': {'child': children}}
        if direct:
            current.setdefault('metadata', {}).setdefault('relations', {})[match[1]] = {'directly_related_user_types': [{'type': 'user'}]}
    else:
        raise ValueError('Unsupported model syntax')
output = root / 'openfga/model.json'
if args.check:
    if json.loads(output.read_text()) != model:
        raise SystemExit('Stale model.json: run make model')
else:
    output.write_text(json.dumps(model, indent=2) + '\n')
