"""시험용: 계약 2.0."""
from kernel import contract

MANIFEST = {
    "name": "contract_v2",
    "kind": "auction_type",
    "contract": "2.0",
    "version": "1.0.0",
    "description": "계약 2.0",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {}
