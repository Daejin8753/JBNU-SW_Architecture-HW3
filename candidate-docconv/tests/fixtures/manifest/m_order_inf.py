"""MANIFEST 위반 예제: order 가 무한대(1e999)"""
from kernel import contract

MANIFEST = {
    "name": "m_order_inf",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "postprocessor",
    "order": 1e999,
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": payload["markdown"]}
