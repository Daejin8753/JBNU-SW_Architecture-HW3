"""MANIFEST 위반 예제: description 이 set"""
from kernel import contract

MANIFEST = {
    "name": "m_desc_set",
    "contract": "1.0",
    "version": "0.1.0",
    "description": {1, 2},
    "kind": "converter",
    "formats": ["mdescset"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
