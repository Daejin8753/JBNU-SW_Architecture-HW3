"""위반 예제: v_sqlite"""
from kernel import contract

import sqlite3

MANIFEST = {
    "name": "v_sqlite",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "formats": ["vfmt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
