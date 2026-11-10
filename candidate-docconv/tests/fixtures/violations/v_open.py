"""위반 예제: v_open"""
from kernel import contract

def f():
    return open('x')

MANIFEST = {
    "name": "v_open",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "formats": ["vfmt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
