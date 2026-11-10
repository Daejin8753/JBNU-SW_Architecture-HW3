"""시험용 의존 위반: from internal import storage"""
from kernel import contract
from internal import storage

MANIFEST = {
    "name": "v_internal",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "의존 위반 예제",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise contract.Rejected(op)
