"""텍스트 → Markdown. utf-8(BOM 포함) → cp949 순서로 읽는다."""
from kernel import contract

MANIFEST = {
    "name": "txt_conv",
    "kind": "converter",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "일반 텍스트(utf-8, cp949)를 그대로 Markdown 본문으로 옮긴다",
    "formats": ["txt"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        data = payload["data"]
        for enc in ("utf-8-sig", "cp949"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise contract.Rejected("손상된 문서")
        ctx.log(f"{payload['filename']}: {enc} 로 읽음")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return {"markdown": text.rstrip("\n") + "\n", "meta": {"encoding": enc}}
