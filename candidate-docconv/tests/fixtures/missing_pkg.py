"""시험용: requires 의 패키지가 없는 별도 프로세스 플러그인."""
from kernel import contract

import no_such_pkg_xyz

MANIFEST = {
    "name": "missing_pkg",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "runtime": "process",
    "requires": ["no_such_pkg_xyz"],
    "formats": ["missingfmt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
