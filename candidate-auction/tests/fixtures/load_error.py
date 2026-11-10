"""시험용: 적재 중 예외."""
from kernel import contract

MANIFEST = {
    "name": "load_error",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "적재 중 예외",
}

raise RuntimeError("적재 중 고장")


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {}
