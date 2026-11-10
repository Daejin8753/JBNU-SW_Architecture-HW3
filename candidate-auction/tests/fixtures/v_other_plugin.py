"""시험용 의존 위반: import plugins.english"""
from kernel import contract
import plugins.english

MANIFEST = {
    "name": "v_other_plugin",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "의존 위반 예제",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise contract.Rejected(op)
