"""위반 예제: v_req_internal (requires 로 후보 폴더 패키지 internal 을 엶)"""
from kernel import contract

from internal import storage

MANIFEST = {
    "name": "v_req_internal",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "runtime": "process",
    "requires": ["internal"],
    "formats": ["vfmt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
