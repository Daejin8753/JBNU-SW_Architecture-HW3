"""시험용 의존 위반: X = eval("1+1")"""
from kernel import contract
X = eval("1+1")

MANIFEST = {
    "name": "v_eval",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "의존 위반 예제",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise contract.Rejected(op)
