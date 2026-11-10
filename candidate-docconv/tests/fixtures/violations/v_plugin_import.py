"""위반 예제: v_plugin_import"""
from kernel import contract

import plugins.txt_conv

MANIFEST = {
    "name": "v_plugin_import",
    "kind": "converter",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "formats": ["vfmt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
