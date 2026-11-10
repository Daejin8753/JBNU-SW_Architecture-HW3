"""시험용: 적재 중 예외."""
from kernel import contract

MANIFEST = {
    "name": "load_error",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "formats": ["loaderrfmt"],
}

raise RuntimeError("적재 중 일부러 낸 예외")


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {}
