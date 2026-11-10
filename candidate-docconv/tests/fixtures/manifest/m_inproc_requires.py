"""MANIFEST 위반 예제: inproc 인데 requires 가 있음"""
from kernel import contract

MANIFEST = {
    "name": "m_inproc_requires",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "converter",
    "requires": ["fitz"],
    "formats": ["mfmt5"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
