"""MANIFEST 위반 예제: name 이 str 이 아님"""
from kernel import contract

MANIFEST = {
    "name": 7,
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "converter",
    "formats": ["mfmt10"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
