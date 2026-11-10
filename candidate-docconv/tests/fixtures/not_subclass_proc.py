"""시험용 fixture: contract.Plugin 을 상속하지 않은 Plugin(process)"""
from kernel import contract

MANIFEST = {
    "name": "not_subclass_proc",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "runtime": "process",
    "formats": ["nosubprocfmt"],
}


class Plugin:
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
