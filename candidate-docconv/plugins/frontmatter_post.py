"""후처리: YAML frontmatter(title, source_file, converter, converted_at)를 앞에 붙인다."""
import datetime
import json

from kernel import contract

MANIFEST = {
    "name": "frontmatter_post",
    "kind": "postprocessor",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "frontmatter 붙이기: 첫 제목 또는 파일 이름을 title 로 쓴다",
    "order": 10,
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        md, meta = payload["markdown"], payload["meta"]
        title = meta.get("filename", "")
        for line in md.splitlines():
            if line.startswith("#"):
                title = line.lstrip("#").strip() or title
                break
        now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        head = ["---",
                f"title: {json.dumps(title, ensure_ascii=False)}",
                f"source_file: {json.dumps(meta.get('filename', ''), ensure_ascii=False)}",
                f"converter: {json.dumps(meta.get('converter', ''), ensure_ascii=False)}",
                f"converted_at: {json.dumps(now)}",
                "---", ""]
        return {"markdown": "\n".join(head) + "\n" + md}
