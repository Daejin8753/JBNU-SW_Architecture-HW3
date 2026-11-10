"""시험용 의존 위반: from kernel import registry"""
from kernel import contract
from kernel import registry

MANIFEST = {
    "name": "v_kernel_inner",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "의존 위반 예제",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise contract.Rejected(op)
