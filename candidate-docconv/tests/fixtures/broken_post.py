"""시험용: 항상 장애를 내는 후처리기."""
from kernel import contract

MANIFEST = {
    "name": "broken_post",
    "kind": "postprocessor",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "order": 5,
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise RuntimeError("후처리 결함")
