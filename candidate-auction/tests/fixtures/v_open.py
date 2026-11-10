"""시험용 의존 위반: DATA = open("x.txt").read"""
from kernel import contract
DATA = open("x.txt").read

MANIFEST = {
    "name": "v_open",
    "kind": "auction_type",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "의존 위반 예제",
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise contract.Rejected(op)
