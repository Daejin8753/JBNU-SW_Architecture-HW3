"""DOCX → Markdown. 코어가 준 members["word/document.xml"] 만 쓴다(zip 을 직접 열지 않음)."""
import re
import xml.etree.ElementTree as ET

from kernel import contract

MANIFEST = {
    "name": "docx_conv",
    "kind": "converter",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "DOCX 문단·제목(Heading1~6)·표·굵게를 Markdown 으로 바꾼다",
    "formats": ["docx"],
}

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
HEADING_RE = re.compile(r"^(?:heading|제목)\s?([1-6])$", re.I)


def _on(el):
    """w:b 같은 켜짐 표시. w:val 이 0/false 면 꺼짐."""
    if el is None:
        return False
    return el.get(W + "val", "true").lower() not in ("0", "false", "off")


def _runs_text(p):
    parts = []
    for r in p.iter(W + "r"):
        bold = _on(r.find(f"{W}rPr/{W}b"))
        text = ""
        for node in r:
            if node.tag == W + "t":
                text += node.text or ""
            elif node.tag == W + "tab":
                text += "\t"
            elif node.tag in (W + "br", W + "cr"):
                text += "\n"
        if bold and text.strip():
            text = f"**{text}**"
        parts.append(text)
    return "".join(parts).replace("**" + "**", "")


def _paragraph(p):
    text = _runs_text(p).strip()
    if not text:
        return ""
    style = p.find(f"{W}pPr/{W}pStyle")
    m = HEADING_RE.match(style.get(W + "val", "")) if style is not None else None
    if m:
        return "#" * int(m.group(1)) + " " + text.replace("**", "")
    return text


def _table(tbl):
    rows = []
    for tr in tbl.findall(W + "tr"):
        cells = []
        for tc in tr.findall(W + "tc"):
            txt = " ".join(_runs_text(p).strip() for p in tc.findall(W + "p"))
            cells.append(txt.strip().replace("|", "\\|").replace("\n", " "))
        rows.append(cells)
    if not rows:
        return ""
    n = max(len(r) for r in rows)
    rows = [r + [""] * (n - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * n]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        xml = (payload.get("members") or {}).get("word/document.xml")
        if xml is None:
            raise contract.Rejected("손상된 문서: word/document.xml 없음")
        try:  # 입력 때문에 생긴 오류는 손상된 문서
            root = ET.fromstring(xml)
            body = root.find(W + "body")
            if body is None:
                raise contract.Rejected("손상된 문서: body 없음")
            blocks = []
            for el in body:
                if el.tag == W + "p":
                    blocks.append(_paragraph(el))
                elif el.tag == W + "tbl":
                    blocks.append(_table(el))
        except (ET.ParseError, LookupError, ValueError, RecursionError, UnicodeDecodeError):
            raise contract.Rejected("손상된 문서") from None
        md = "\n\n".join(b for b in blocks if b)
        return {"markdown": md + "\n", "meta": {"blocks": len(blocks)}}
