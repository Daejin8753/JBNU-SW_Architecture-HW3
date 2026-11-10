"""예제: CSV → Markdown 표. plugins/ 에 복사하고 [다시 검색] → [설치] 하면 csv 형식이 생긴다."""
import csv
import io

from kernel import contract

MANIFEST = {
    "name": "csv_conv",
    "kind": "converter",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "CSV 를 Markdown 표로 바꾼다(첫 행 = 머리글)",
    "formats": ["csv"],
    "match": {"extensions": [".csv"], "text": True},
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        for enc in ("utf-8-sig", "cp949"):
            try:
                text = payload["data"].decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise contract.Rejected("손상된 문서")
        try:
            rows = [r for r in csv.reader(io.StringIO(text)) if r]
        except csv.Error:
            raise contract.Rejected("손상된 문서") from None
        if not rows:
            return {"markdown": "\n", "meta": {"rows": 0}}
        n = max(len(r) for r in rows)
        rows = [[c.strip().replace("|", "\\|") for c in r] + [""] * (n - len(r)) for r in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * n]
        lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return {"markdown": "\n".join(lines) + "\n", "meta": {"rows": len(rows)}}
