"""MANIFEST 위반 예제: match 가 있는데 formats 가 2개"""
from kernel import contract

MANIFEST = {
    "name": "m_match_two",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "converter",
    "formats": ["mfmt6", "mfmt7"],
    "match": {"extensions": [".mm"], "text": True},
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
