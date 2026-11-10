"""MANIFEST 위반 예제: match.text 가 bool 이 아님"""
from kernel import contract

MANIFEST = {
    "name": "m_match_text",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "converter",
    "formats": ["mfmt9"],
    "match": {"extensions": [".mn"], "text": "yes"},
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
