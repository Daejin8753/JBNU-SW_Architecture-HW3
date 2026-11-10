"""MANIFEST 위반 예제: formats 가 빈 목록"""
from kernel import contract

MANIFEST = {
    "name": "m_formats_empty",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "converter",
    "formats": [],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
