"""PDF → Markdown. 별도 프로세스에서 PyMuPDF 로 쪽별 텍스트를 뽑고 쪽 구분선을 넣는다."""
from kernel import contract

try:
    import fitz
except ImportError:
    raise ImportError("PyMuPDF 없음") from None

MANIFEST = {
    "name": "pdf_conv",
    "kind": "converter",
    "contract": "1.0",
    "version": "1.0.0",
    "description": "PDF 쪽별 텍스트를 뽑는다(PyMuPDF, 별도 프로세스)",
    "runtime": "process",
    "requires": ["fitz"],
    "timeout_sec": 15,
    "formats": ["pdf"],
}


class Plugin(contract.Plugin):
    def handle(self, op, payload, ctx):
        try:
            doc = fitz.open(stream=payload["data"], filetype="pdf")
        except (RuntimeError, ValueError):  # FileDataError 는 RuntimeError 의 하위
            raise contract.Rejected("손상된 문서") from None
        try:
            if doc.needs_pass:
                raise contract.Rejected("암호가 걸린 PDF")
            if doc.page_count == 0:
                raise contract.Rejected("손상된 문서: 쪽 없음")
            pages = []
            for i, page in enumerate(doc, start=1):
                text = page.get_text("text").strip()
                pages.append(f"<!-- page {i} -->\n\n{text}" if text else f"<!-- page {i} -->")
        except (RuntimeError, ValueError):  # 쪽 읽기 오류
            raise contract.Rejected("손상된 문서") from None
        finally:
            doc.close()
        return {"markdown": "\n\n---\n\n".join(pages) + "\n", "meta": {"pages": len(pages)}}
