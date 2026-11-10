"""MANIFEST 위반 예제: match.extensions 가 점으로 시작하지 않음"""
from kernel import contract

MANIFEST = {
    "name": "m_match_ext",
    "contract": "1.0",
    "version": "0.1.0",
    "description": "시험용 fixture",
    "kind": "converter",
    "formats": ["mfmt8"],
    "match": {"extensions": ["mm"], "text": True},
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
