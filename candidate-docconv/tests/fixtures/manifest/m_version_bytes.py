"""MANIFEST 위반 예제: version 이 bytes"""
from kernel import contract

MANIFEST = {
    "name": "m_version_bytes",
    "contract": "1.0",
    "version": b"x",
    "description": "시험용 fixture",
    "kind": "converter",
    "formats": ["mverbytes"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
