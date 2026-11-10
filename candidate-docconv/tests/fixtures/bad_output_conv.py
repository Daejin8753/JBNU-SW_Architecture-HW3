"""시험용: 출력 계약 위반(markdown 이 str 이 아님)."""
from kernel import contract

MANIFEST = {
    "name": "bad_output_conv",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "formats": ["badoutfmt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": 123, "meta": {}}
