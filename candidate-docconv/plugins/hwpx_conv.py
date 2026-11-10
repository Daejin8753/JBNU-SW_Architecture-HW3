"""HWPX → Markdown. members 의 Contents/section*.xml 에서 문단 글자와 간단한 표를 꺼낸다."""
import re
import xml.etree.ElementTree as ET

from kernel import contract

MANIFEST = {
    "name": "hwpx_conv",
    "kind": "converter",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "HWPX 본문(hp:p / hp:t)과 표(hp:tbl)를 Markdown 으로 바꾼다",
    "formats": ["hwpx"],
}

SECTION_RE = re.compile(r"^Contents/section(\d+)\.xml$")


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _text(el, skip_tables=True):
    """el 아래 hp:t 글자. skip_tables 면 표 안 글자는 뺀다."""
    parts = []
    for child in el:
        name = _local(child.tag)
        if name == "tbl" and skip_tables:
            continue
        if name == "t":
            parts.append(child.text or "")
            parts.append(_text(child, skip_tables))
            parts.append(child.tail or "")
        else:
            parts.append(_text(child, skip_tables))
    return "".join(parts)


def _tables(el):
    """el 아래의 바깥쪽 표들."""
    found = []
    for child in el:
        if _local(child.tag) == "tbl":
            found.append(child)
        else:
            found.extend(_tables(child))
    return found


def _render_table(tbl):
    rows = []
    for tr in tbl.iter():
        if _local(tr.tag) != "tr":
            continue
        cells = [_text(tc, skip_tables=False).strip().replace("|", "\\|")
                 for tc in tr if _local(tc.tag) == "tc"]
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
        members = payload.get("members") or {}
        try:  # 숫자가 너무 긴 섹션 이름(int 변환 상한)도 입력 오류
            sections = sorted((int(m.group(1)), name) for name in members
                              if (m := SECTION_RE.match(name)))
        except ValueError:
            raise contract.Rejected("손상된 문서: 섹션 이름") from None
        if not sections:
            raise contract.Rejected("손상된 문서: Contents/section*.xml 없음")
        blocks = []
        try:  # 입력 때문에 생긴 오류(깊은 중첩의 RecursionError 포함)는 손상된 문서
            for _, name in sections:
                root = ET.fromstring(members[name])
                for p in root:
                    if _local(p.tag) != "p":
                        continue
                    text = _text(p).strip()
                    if text:
                        blocks.append(text)
                    blocks.extend(_render_table(t) for t in _tables(p))
        except (ET.ParseError, LookupError, ValueError, RecursionError, UnicodeDecodeError):
            raise contract.Rejected("손상된 문서") from None
        md = "\n\n".join(b for b in blocks if b)
        return {"markdown": md + "\n", "meta": {"sections": len(sections)}}
