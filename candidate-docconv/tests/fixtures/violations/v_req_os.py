"""위반 예제: v_req_os (requires 로 표준 모듈 os 를 엶)"""
from kernel import contract

import os

MANIFEST = {
    "name": "v_req_os",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "runtime": "process",
    "requires": ["os"],
    "formats": ["vfmt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
