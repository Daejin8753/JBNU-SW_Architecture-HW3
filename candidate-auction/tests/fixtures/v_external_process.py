"""시험용 의존 위반: requires 에 없는 외부 패키지(process)."""
from kernel import contract
import numpy

MANIFEST = {
    "name": "v_external_process",
    "kind": "notifier",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "requires 밖 외부 패키지",
    "runtime": "process",
    "requires": ["fitz"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        raise contract.Rejected(op)
