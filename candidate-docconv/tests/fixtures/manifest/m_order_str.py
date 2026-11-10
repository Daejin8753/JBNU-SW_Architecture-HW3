"""MANIFEST 위반 예제: order 가 문자열"""
from kernel import contract

MANIFEST = {
    "name": "m_order_str",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "postprocessor",
    "order": "10",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
