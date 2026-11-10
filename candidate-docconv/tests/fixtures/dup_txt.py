"""시험용: txt 형식을 또 맡겠다는 변환기(중복 install 거부)."""
from kernel import contract

MANIFEST = {
    "name": "dup_txt",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "formats": ["txt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
