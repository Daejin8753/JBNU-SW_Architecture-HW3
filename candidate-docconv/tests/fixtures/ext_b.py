"""시험용 fixture: match.extensions 가 ext_a 와 겹치는 변환기 B(대문자)"""
from kernel import contract

MANIFEST = {
    "name": "ext_b",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "formats": ["xyzb"],
    "match": {"extensions": [".XYZ", ".qqq"], "text": True},
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "b", "meta": {}}
