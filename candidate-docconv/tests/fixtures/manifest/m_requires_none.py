"""MANIFEST 위반 예제: requires 가 None"""
from kernel import contract

MANIFEST = {
    "name": "m_requires_none",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "converter",
    "runtime": "process",
    "requires": None,
    "formats": ["mfmt1"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
