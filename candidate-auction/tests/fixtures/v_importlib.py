"""시험용 의존 위반: import importlib"""
from kernel import contract
import importlib

MANIFEST = {
    "name": "v_importlib",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "의존 위반 예제",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise contract.Rejected(op)
