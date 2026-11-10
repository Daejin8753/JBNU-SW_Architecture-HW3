"""시험용 의존 위반: from plugins import english"""
from kernel import contract
from plugins import english

MANIFEST = {
    "name": "v_other_plugin_from",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "의존 위반 예제",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise contract.Rejected(op)
