"""시험용 의존 위반: OS = __import__("os")"""
from kernel import contract
OS = __import__("os")

MANIFEST = {
    "name": "v_dunder_import",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "의존 위반 예제",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise contract.Rejected(op)
