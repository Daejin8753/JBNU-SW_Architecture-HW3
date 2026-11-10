"""HTML → Markdown. html.parser 로 제목·문단·목록·링크·강조·간단 표·코드를 옮긴다."""
import re
from html.parser import HTMLParser

from kernel import contract

MANIFEST = {
    "name": "html_conv",
    "kind": "converter",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "HTML 의 h1~h6, p, br, ul/ol/li, a, strong/em, table, pre/code 를 Markdown 으로 바꾼다",
    "formats": ["html"],
}

HEADINGS = {f"h{i}": i for i in range(1, 7)}


class _ToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []      # (종류, 텍스트)
        self.buf = []         # 현재 인라인 텍스트
        self.skip = 0         # script/style 깊이
        self.lists = []       # [종류, 번호]
        self.item = None      # 현재 li 의 머리표
        self.pre = 0
        self.table = None     # 행 목록
        self.row = None
        self.cell = None
        self.hrefs = []

    def _emit(self, text):
        (self.cell if self.cell is not None else self.buf).append(text)

    def _flush(self, prefix=None):
        """모은 인라인 텍스트를 블록 하나로. li 안이면 머리표를 붙인다."""
        lines = "".join(self.buf).split("\n")
        text = "\n".join(line.strip() for line in lines).strip()
        self.buf = []
        if prefix is None:
            prefix = self.item or ""
        if text:
            self.blocks.append(("li" if self.item else "block", prefix + text))

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        if tag in HEADINGS or tag in ("p", "div"):
            self._flush()
        elif tag == "br":
            self._emit("\n")
        elif tag in ("ul", "ol"):
            self._flush()
            self.lists.append([tag, 0])
            self.item = None
        elif tag == "li":
            self._flush()
            if not self.lists:
                self.lists.append(["ul", 0])
            kind = self.lists[-1]
            kind[1] += 1
            indent = "  " * (len(self.lists) - 1)
            self.item = indent + (f"{kind[1]}. " if kind[0] == "ol" else "- ")
        elif tag == "a":
            self.hrefs.append(a.get("href"))
            self._emit("[")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "pre":
            self._flush()
            self.pre += 1
        elif tag == "code" and not self.pre:
            self._emit("`")
        elif tag == "table":
            self._flush()
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in HEADINGS:
            self._flush("#" * HEADINGS[tag] + " ")
        elif tag in ("p", "div"):
            self._flush()
        elif tag == "li":
            self._flush()
            self.item = None
        elif tag in ("ul", "ol"):
            self._flush()
            self.item = None
            if self.lists:
                self.lists.pop()
                if not self.lists:
                    self.blocks.append(("break", ""))  # 다른 목록과 붙지 않게
        elif tag == "a":
            href = self.hrefs.pop() if self.hrefs else None
            self._emit(f"]({href})" if href else "]")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "code" and not self.pre:
            self._emit("`")
        elif tag == "pre" and self.pre:
            self.pre -= 1
            code = "".join(self.buf).strip("\n")
            self.buf = []
            self.blocks.append(("block", "```\n" + code + "\n```"))
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            text = re.sub(r"\s+", " ", "".join(self.cell)).strip().replace("|", "\\|")
            self.row.append(text)
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            if self.row:  # 닫히지 않은 행도 가능한 만큼 넣는다
                self.table.append(self.row)
            self.blocks.append(("block", render_table(self.table)))
            self.table = self.row = self.cell = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.pre:
            self.buf.append(data)
        else:
            self._emit(re.sub(r"\s+", " ", data))

    def result(self):
        self._flush()
        out = []
        prev = None
        for kind, text in self.blocks:
            if kind == "break":
                prev = None
            elif text.strip():
                sep = "\n" if (prev == "li" and kind == "li") else "\n\n"
                out.append((sep if out else "") + text)
                prev = kind
        return "".join(out) + "\n"


def render_table(rows):
    rows = [r for r in rows if r]
    if not rows:
        return ""
    n = max(len(r) for r in rows)
    rows = [r + [""] * (n - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * n]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


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
        p = _ToMarkdown()
        p.feed(text)
        p.close()
        return {"markdown": p.result(), "meta": {"encoding": enc}}
