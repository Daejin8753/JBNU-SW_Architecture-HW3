"""시험용 fixture: match.extensions .xyz 를 쓰는 변환기 A"""
from kernel import contract

MANIFEST = {
    "name": "ext_a",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "formats": ["xyza"],
    "match": {"extensions": [".xyz"], "text": True},
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "a", "meta": {}}
