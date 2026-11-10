"""MANIFEST 위반 예제: MANIFEST 가 리터럴 dict 가 아님"""
from kernel import contract

MANIFEST = dict(name="m_not_literal", kind="converter", contract="1.0", version="0.1.0",
                description="시험용 fixture", formats=["mfmt12"])


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        return {"markdown": "", "meta": {}}
