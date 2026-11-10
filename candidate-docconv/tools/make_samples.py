"""시연·시험 자료를 만든다. 사용: python tools/make_samples.py [출력 폴더(기본 samples/)]

본문은 직접 쓴 문장만 쓴다. 함수는 bytes 를 돌려주므로 시험도 같은 함수를 쓴다.
"""
import io
import os
import struct
import sys
import zipfile
import zlib

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS_NS = "http://www.hancom.co.kr/hwpml/2011/section"

CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/word/document.xml" ContentType="application/'
                 'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')


def sample_txt():
    return "변환기 시연용 텍스트입니다.\n두 번째 줄입니다.   \n\n\n\n빈 줄이 많은 뒤의 줄입니다.\n".encode("utf-8")


def sample_html():
    return ("<!doctype html><html><head><style>p{color:red}</style><script>var x=1;</script></head>"
            "<body><h1>HTML 시연 문서</h1><p>이 문단에는 <strong>굵은 글씨</strong>와 <em>기울임</em>,"
            " <a href=\"https://example.com/\">링크</a>가 있습니다.<br>줄바꿈 뒤 글입니다.</p>"
            "<h2>목록</h2><ul><li>첫째 항목</li><li>둘째 항목</li></ul><ol><li>하나</li><li>둘</li></ol>"
            "<table><tr><th>이름</th><th>값</th></tr><tr><td>가</td><td>1</td></tr></table>"
            "<pre><code>print(\"코드\")</code></pre></body></html>").encode("utf-8")


def _w_par(text, style=None, bold=False):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f"<w:p>{ppr}<w:r>{rpr}<w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"


def docx_document_xml(extra=""):
    cells = "".join(f"<w:tc>{_w_par(t)}</w:tc>" for t in ("항목", "설명"))
    cells2 = "".join(f"<w:tc>{_w_par(t)}</w:tc>" for t in ("코어", "절차 순서를 정함"))
    body = (_w_par("DOCX 시연 문서", "Heading1") + _w_par("작은 제목", "Heading2")
            + "<w:p><w:r><w:t xml:space=\"preserve\">보통 문단과 </w:t></w:r>"
              "<w:r><w:rPr><w:b/></w:rPr><w:t>굵은 부분</w:t></w:r></w:p>"
            + f"<w:tbl><w:tr>{cells}</w:tr><w:tr>{cells2}</w:tr></w:tbl>")
    return (f'<?xml version="1.0" encoding="UTF-8"?>{extra}'
            f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>').encode("utf-8")


def make_zip(members, compression=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


def sample_docx(compression=zipfile.ZIP_DEFLATED, document=None):
    return make_zip([("[Content_Types].xml", CONTENT_TYPES),
                     ("word/document.xml", document or docx_document_xml())], compression)


def sample_hwpx():
    def p(text):
        return f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>"
    tbl = ("<hp:p><hp:run><hp:tbl>"
           "<hp:tr><hp:tc><hp:subList>" + p("열1") + "</hp:subList></hp:tc>"
           "<hp:tc><hp:subList>" + p("열2") + "</hp:subList></hp:tc></hp:tr>"
           "<hp:tr><hp:tc><hp:subList>" + p("가") + "</hp:subList></hp:tc>"
           "<hp:tc><hp:subList>" + p("나") + "</hp:subList></hp:tc></hp:tr>"
           "</hp:tbl></hp:run></hp:p>")
    section = (f'<?xml version="1.0" encoding="UTF-8"?><hs:sec xmlns:hs="{HS_NS}" xmlns:hp="{HP_NS}">'
               + p("HWPX 시연 문서") + p("한글 문서의 본문 문단입니다.") + tbl + "</hs:sec>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/hwp+zip")  # stored, 맨 앞
        zf.writestr("Contents/section0.xml", section, zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def sample_pdf():
    """PyMuPDF 가 없으면 None."""
    try:
        import fitz
    except ImportError:
        return None
    doc = fitz.open()
    for i, text in enumerate(("First page of the sample PDF.", "Second page text."), start=1):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def sample_csv():
    return "이름,수량,비고\n사과,3,빨강\n배,5,노랑\n".encode("utf-8")


def broken_pdf():
    return b"%PDF-1.7\n" + b"this is not a real pdf body \x00\x01\x02" * 4


def zipbomb_docx(size=25 * 1024 * 1024):
    """word/document.xml 의 실제 내용이 20MB 를 넘는 docx. 스트리밍으로 써서 압축 파일은 작다."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        with zf.open("word/document.xml", "w") as f:
            f.write(f'<?xml version="1.0"?><w:document xmlns:w="{W_NS}"><w:body>'.encode())
            chunk = b"<w:p><w:r><w:t>aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</w:t></w:r></w:p>" * 1000
            written = 0
            while written < size:
                f.write(chunk)
                written += len(chunk)
            f.write(b"</w:body></w:document>")
    return buf.getvalue()


def _local_data_offset(data, name):
    """name 항목의 압축 데이터 시작 위치(로컬 헤더 뒤)."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        info = zf.getinfo(name)
    off = info.header_offset
    n_len, e_len = struct.unpack("<HH", data[off + 26:off + 30])
    return off + 30 + n_len + e_len, info.compress_size


def crc_broken_docx():
    """word/document.xml 압축 데이터 가운데 바이트 하나를 바꾼 docx."""
    data = bytearray(sample_docx())
    start, size = _local_data_offset(bytes(data), "word/document.xml")
    data[start + size // 2] ^= 0xFF
    return bytes(data)


def small_size_docx():
    """중앙 디렉터리의 word/document.xml 선언 크기를 40 으로 줄이고 CRC 를 앞 40바이트에 맞춘 docx(잘린 XML)."""
    data = bytearray(sample_docx())
    crc = zlib.crc32(docx_document_xml()[:40])
    target = b"word/document.xml"
    pos = 0
    while True:
        pos = data.find(b"PK\x01\x02", pos)
        if pos < 0:
            break
        n_len = struct.unpack("<H", data[pos + 28:pos + 30])[0]
        if data[pos + 46:pos + 46 + n_len] == target:
            data[pos + 16:pos + 20] = struct.pack("<I", crc)
            data[pos + 24:pos + 28] = struct.pack("<I", 40)
            break
        pos += 4
    return bytes(data)


def doctype_docx():
    extra = '<!DOCTYPE w:document [<!ENTITY a "aaaa">]>'
    return sample_docx(document=docx_document_xml(extra))


def utf16_doctype_docx():
    """DOCTYPE(내부 엔티티)이 든 word/document.xml 을 UTF-16 으로 넣은 docx."""
    xml = docx_document_xml('<!DOCTYPE w:document [<!ENTITY a "aaaa">]>').decode("utf-8")
    xml = xml.replace('encoding="UTF-8"', 'encoding="UTF-16"')
    return sample_docx(document=xml.encode("utf-16"))


def latin1_decl_docx():
    """XML 선언 encoding 이 utf-8 이 아닌(ASCII 내용) docx."""
    xml = (f'<?xml version="1.0" encoding="ISO-8859-1"?><w:document xmlns:w="{W_NS}"><w:body>'
           '<w:p><w:r><w:t>plain</w:t></w:r></w:p></w:body></w:document>')
    return sample_docx(document=xml.encode("ascii"))


def deep_hwpx(depth=10000):
    """요소를 depth 단계 중첩한 section 이 든 hwpx."""
    inner = "<hp:run>" * depth + "<hp:t>깊다</hp:t>" + "</hp:run>" * depth
    section = (f'<?xml version="1.0" encoding="UTF-8"?><hs:sec xmlns:hs="{HS_NS}" xmlns:hp="{HP_NS}">'
               f"<hp:p>{inner}</hp:p></hs:sec>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/hwp+zip")
        zf.writestr("Contents/section0.xml", section, zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def html_only_zip():
    """안전 열기는 통과하지만 *.xml·mimetype 항목이 없는 ZIP(readme.html 하나, stored)."""
    return make_zip([("readme.html", b"<html><p>x</p></html>")], zipfile.ZIP_STORED)


def long_section_hwpx(digits=4301):
    """섹션 번호가 digits 자리인 hwpx(int 변환 상한을 넘음)."""
    section = (f'<?xml version="1.0" encoding="UTF-8"?><hs:sec xmlns:hs="{HS_NS}" xmlns:hp="{HP_NS}">'
               "<hp:p><hp:run><hp:t>x</hp:t></hp:run></hp:p></hs:sec>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/hwp+zip")
        zf.writestr("Contents/section" + "1" * digits + ".xml", section, zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def broken_html():
    """태그 순서가 어긋난 HTML."""
    return b"<table><tr><td>a</td></table></tr>"


def long_field_csv():
    """한 칸이 csv.field_size_limit() 보다 긴 CSV."""
    import csv
    return ("a,b\n" + "x" * (csv.field_size_limit() + 10) + ",y\n").encode("ascii")


def encrypted_pdf():
    """암호가 걸린 PDF. PyMuPDF 가 없으면 None."""
    try:
        import fitz
    except ImportError:
        return None
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Secret page.")
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    doc.close()
    return data


def bzip2_docx():
    return sample_docx(compression=zipfile.ZIP_BZIP2)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")
    os.makedirs(out, exist_ok=True)
    items = {"sample.txt": sample_txt(), "sample.html": sample_html(), "sample.docx": sample_docx(),
             "sample.hwpx": sample_hwpx(), "sample.pdf": sample_pdf(), "sample.csv": sample_csv(),
             "broken.pdf": broken_pdf(), "zipbomb.docx": zipbomb_docx()}
    for name, data in items.items():
        if data is None:
            print(f"건너뜀: {name} (PyMuPDF 없음)")
            continue
        with open(os.path.join(out, name), "wb") as f:
            f.write(data)
        print(f"{name}\t{len(data)} bytes")


if __name__ == "__main__":
    main()
