"""MANIFEST 위반 예제: timeout_sec 가 bool"""
from kernel import contract

MANIFEST = {
    "name": "m_timeout_bool",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "converter",
    "runtime": "process",
    "timeout_sec": True,
    "formats": ["mfmt3"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
