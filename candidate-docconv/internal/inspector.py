"""내부 서버: 안전 검사(ZIP 안전 열기)와 형식 판별."""
import io
import os
import re
import zipfile
import zlib

from kernel.contract import Rejected

MAX_UPLOAD = 20 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_ITEM = 20 * 1024 * 1024
MAX_TOTAL = 50 * 1024 * 1024
CHUNK = 64 * 1024
HTML_RE = re.compile(rb"<(!doctype\s+html|html|head|body|p|h[1-6]|div|table|ul|ol|br)[\s>/]", re.I)
DOCTYPE_RE = re.compile(rb"<!doctype", re.I)
XML_DECL_ENC_RE = re.compile(r"""^\ufeff?\s*<\?xml[^>]*?\bencoding\s*=\s*["']([^"']*)["']""")


def _check_xml_text(name, buf):
    """XML 항목은 UTF-8 만. 디코딩 실패·NUL·선언 encoding 이 utf-8 이 아니면 거부."""
    try:
        text = bytes(buf).decode("utf-8")
    except UnicodeDecodeError:
        raise Rejected(f"UTF-8 이 아닌 XML: {name}") from None
    if "\x00" in text:
        raise Rejected(f"NUL 문자가 든 XML: {name}")
    m = XML_DECL_ENC_RE.match(text)
    if m and m.group(1).lower() != "utf-8":
        raise Rejected(f"XML 선언 encoding 이 utf-8 이 아님({m.group(1)[:20]}): {name}")


def _is_text(data):
    if b"\x00" in data:
        return False
    for enc in ("utf-8-sig", "cp949"):
        try:
            data.decode(enc)
            return True
        except UnicodeDecodeError:
            pass
    return False


def _wanted(name):
    return name.endswith(".xml") or name == "mimetype"


def open_zip(data):
    """디스크에 풀지 않고 필요한 항목만 읽는다. 결과는 {이름: bytes}."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise Rejected(f"ZIP 항목이 너무 많음({len(infos)}개)")
        for i in infos:
            if i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise Rejected(f"지원하지 않는 압축 방식: {i.filename}")
            if i.flag_bits & 0x1:
                raise Rejected(f"암호화된 항목: {i.filename}")
        members, total = {}, 0
        for i in infos:
            if not _wanted(i.filename):
                continue
            buf = bytearray()
            with zf.open(i) as f:
                while True:
                    chunk = f.read(CHUNK)
                    if not chunk:
                        break
                    buf += chunk
                    total += len(chunk)
                    if len(buf) > MAX_ITEM:
                        raise Rejected(f"ZIP 항목이 상한(20MB)을 넘음: {i.filename}")
                    if total > MAX_TOTAL:
                        raise Rejected("ZIP 풀린 크기 합계가 상한(50MB)을 넘음")
            if i.filename.endswith(".xml"):
                _check_xml_text(i.filename, buf)  # 인코딩으로 DOCTYPE 검사를 피하지 못하게 먼저 본다
                if DOCTYPE_RE.search(buf):
                    raise Rejected(f"DOCTYPE 이 든 XML 은 받지 않음: {i.filename}")
            members[i.filename] = bytes(buf)
        return members
    except Rejected:
        raise
    except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError,
            ValueError, OSError) as e:
        raise Rejected(f"손상된 ZIP: {e}") from None


class Inspector:
    def check(self, data):
        """안전 검사. zip 이면 안전 열기 결과 members 를 돌려준다."""
        if len(data) > MAX_UPLOAD:
            raise Rejected("파일이 상한(20MB)을 넘음")
        if data[:4] == b"PK\x03\x04":
            return {"members": open_zip(data)}
        return {"members": None}

    def detect(self, data, filename, members, matchers):
        """위에서부터 처음 맞는 형식."""
        if data[:5] == b"%PDF-":
            return {"format": "pdf"}
        if members is not None:
            if "[Content_Types].xml" in members and "word/document.xml" in members:
                return {"format": "docx"}
            if members.get("mimetype", b"").strip() == b"application/hwp+zip":
                return {"format": "hwpx"}
            raise Rejected("지원하지 않는 형식")
        ext = os.path.splitext(filename)[1].lower()
        for m in matchers:  # active 변환기의 MANIFEST match
            match = m["match"]
            if ext in [e.lower() for e in match.get("extensions", [])]:
                if not match.get("text") or _is_text(data):
                    return {"format": m["formats"][0]}
        if HTML_RE.search(data[:1024]):
            return {"format": "html"}
        if _is_text(data):
            return {"format": "txt"}
        raise Rejected("지원하지 않는 형식")
