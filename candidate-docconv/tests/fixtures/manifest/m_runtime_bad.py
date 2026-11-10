"""MANIFEST 위반 예제: runtime 이 모르는 값"""
from kernel import contract

MANIFEST = {
    "name": "m_runtime_bad",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "converter",
    "runtime": "thread",
    "formats": ["mfmt11"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
