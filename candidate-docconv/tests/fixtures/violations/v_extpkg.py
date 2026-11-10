"""위반 예제: v_extpkg"""
from kernel import contract

import numpy

MANIFEST = {
    "name": "v_extpkg",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "runtime": "process",
    "requires": ["fitz"],
    "formats": ["vfmt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
