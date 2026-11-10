"""후처리: 줄 끝 공백을 지우고 빈 줄은 연속 2개까지만 남긴다."""
from kernel import contract

MANIFEST = {
    "name": "whitespace_post",
    "kind": "postprocessor",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "공백 정리: 줄 끝 공백 제거, 연속 빈 줄 2개 이하",
    "order": 20,
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        out, blank = [], 0
        for line in payload["markdown"].split("\n"):
            line = line.rstrip()
            blank = blank + 1 if not line else 0
            if blank <= 2:
                out.append(line)
        return {"markdown": "\n".join(out).strip("\n") + "\n"}
