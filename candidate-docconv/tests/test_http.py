"""E7 HTTP·경로와 도메인 HTTP 시험(안전 검사·파일 이름·크기 제한·후처리 경고)."""
import http.client
import json
import os
import socket
import unittest
import urllib.parse

import helpers
import make_samples as ms
from kernel import flow
from kernel.kernel import CallError
from kernel.trace import Trace

HAS_FITZ = ms.sample_pdf() is not None
LIMIT = 20 * 1024 * 1024


class HttpBase(unittest.TestCase):
    plugins = helpers.ALL_PLUGINS
    fixtures = ()

    def setUp(self):
        self.data, self.pdir = helpers.make_env(self, plugins=self.plugins, fixtures=self.fixtures)
        self.k = helpers.start_kernel(self, self.data, self.pdir)
        self.port = helpers.start_server(self, self.k)

    def convert(self, data, name, post=""):
        headers = {"X-Filename": urllib.parse.quote(name), "Content-Type": "application/octet-stream"}
        if post:
            headers["X-Post"] = post
        return helpers.jrequest(self.port, "POST", "/api/convert", data, headers)

    def failures(self, name):
        return self.k.plugin_info(name)["failures"]

    def state(self, name):
        return self.k.plugin_info(name)["state"]

    def files_left(self):
        return sorted(os.listdir(os.path.join(self.data, "files")))


class E7HttpTrace(HttpBase):
    def test_api_roundtrip_and_trace(self):
        st, _, body = helpers.jrequest(self.port, "GET", "/api/plugins")
        self.assertEqual(st, 200)
        names = {p["name"]: p for p in body["plugins"]}
        self.assertEqual(names["txt_conv"]["state"], "active")
        self.assertEqual(names["pdf_conv"]["runtime"], "process")
        self.assertIn("convert", names["txt_conv"]["contract"])

        st, h, body = self.convert(ms.sample_txt(), "a.txt", "whitespace_post")
        self.assertEqual(st, 200, body)
        tid = body["trace_id"]
        self.assertEqual(h["X-Trace-Id"], tid)
        st, _, tr = helpers.jrequest(self.port, "GET", f"/api/trace/{tid}")
        self.assertEqual(st, 200)
        hops = tr["trace"]["hops"]
        route = [(x["from"], x["to"]) for x in hops]
        want = [("http_adapter", "kernel"), ("kernel", "internal:inspector"), ("kernel", "internal:inspector"),
                ("kernel", "registry"), ("kernel", "plugin:txt_conv"), ("plugin:txt_conv", "kernel"),
                ("kernel", "internal:storage"), ("kernel", "registry"), ("kernel", "plugin:whitespace_post"),
                ("kernel", "internal:storage"), ("kernel", "internal:storage")]
        self.assertEqual(route, want)
        self.assertEqual([x["seq"] for x in hops], list(range(1, len(hops) + 1)))
        self.assertTrue(all(x["ok"] for x in hops))
        # plugin → kernel → internal 은 부모 관계로 이어진다
        log_hop = hops[5]
        self.assertEqual(hops[6]["parent"], log_hop["seq"])
        self.assertEqual(log_hop["parent"], hops[4]["seq"])

        st, _, lst = helpers.jrequest(self.port, "GET", "/api/trace?limit=5")
        self.assertIn(tid, [t["trace_id"] for t in lst["traces"]])
        st, _, hist = helpers.jrequest(self.port, "GET", "/api/history")
        self.assertEqual(hist["items"][0]["id"], body["id"])

        st, h, raw = helpers.request(self.port, "GET", f"/api/files/{body['id']}.md")
        self.assertEqual(st, 200)
        self.assertIn("filename*=UTF-8''a.md", h["Content-Disposition"])
        self.assertRegex(h["X-Trace-Id"], r"^[0-9a-f]{8}$")
        self.assertEqual(raw.decode("utf-8"), body["markdown"])

        st, _, ui = helpers.request(self.port, "GET", "/")
        self.assertEqual(st, 200)
        self.assertIn(b"<html", ui)
        self.assertEqual(helpers.request(self.port, "GET", "/ui/app.js")[0], 200)
        self.assertEqual(helpers.request(self.port, "GET", "/ui/../app.py")[0], 404)

    def assert_traced(self, status, headers, body, want_status, code=None):
        """응답에 X-Trace-Id 와 본문 trace_id 가 같고, /api/trace/{id} 로 읽힌다."""
        self.assertEqual(status, want_status, body)
        tid = headers.get("X-Trace-Id")
        self.assertRegex(tid or "", r"^[0-9a-f]{8}$")
        self.assertEqual(body["trace_id"], tid)
        if code:
            self.assertEqual(body["error"]["code"], code)
        st, _, tr = helpers.jrequest(self.port, "GET", f"/api/trace/{tid}")
        self.assertEqual(st, 200)
        self.assertEqual(tr["trace"]["trace_id"], tid)
        self.assertGreaterEqual(len(tr["trace"]["hops"]), 1)
        return tr["trace"]

    def raw_post(self, length=None):
        """Content-Length 를 직접 정해 보낸다(본문은 보내지 않는다). (상태, 헤더, JSON 본문)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest("POST", "/api/convert")
            conn.putheader("X-Filename", "big.txt")
            if length is not None:
                conn.putheader("Content-Length", str(length))
            conn.endheaders()
            r = conn.getresponse()
            return r.status, dict(r.getheaders()), json.loads(r.read().decode("utf-8"))
        finally:
            conn.close()

    def test_get_and_early_rejects_are_traced(self):
        for path in ("/api/plugins", "/api/history"):
            tr = self.assert_traced(*helpers.jrequest(self.port, "GET", path), 200)
            self.assertEqual(tr["hops"][0]["from"], "http_adapter")
        tr = self.assert_traced(*helpers.jrequest(self.port, "POST", "/api/plugins/rescan",
                                                  headers={"Origin": "http://evil.example"}), 403, "forbidden")
        self.assertEqual(len(tr["hops"]), 1)
        tr = self.assert_traced(*self.raw_post(None), 411, "length_required")
        self.assertEqual(len(tr["hops"]), 1)
        tr = self.assert_traced(*self.raw_post(LIMIT + 1), 413, "too_large")
        self.assertEqual(len(tr["hops"]), 1)
        self.assert_traced(*helpers.jrequest(self.port, "GET", "/api/nope"), 404, "not_found")
        self.assert_traced(*helpers.jrequest(self.port, "GET", "/api/files/0123456789ab.md"), 404, "not_found")
        # 조회 API 자체는 기록하지 않는다
        st, h, _ = helpers.jrequest(self.port, "GET", "/api/trace?limit=200")
        self.assertNotIn("X-Trace-Id", h)

    def test_plugin_management_api(self):
        st, _, b = helpers.jrequest(self.port, "POST", "/api/plugins/html_conv/remove")
        self.assertEqual((st, b["plugin"]["state"]), (200, "available"))
        st, _, b = self.convert(ms.sample_html(), "a.html")
        self.assertEqual(st, 400)
        st, _, b = helpers.jrequest(self.port, "POST", "/api/plugins/html_conv/install")
        self.assertEqual((st, b["plugin"]["state"]), (200, "active"))
        st, _, b = helpers.jrequest(self.port, "POST", "/api/plugins/rescan")
        self.assertEqual(st, 200)
        st, _, b = helpers.jrequest(self.port, "POST", "/api/plugins/future_contract/install")
        self.assertEqual((st, b["error"]["code"]), (400, "rejected"))
        st, _, b = helpers.jrequest(self.port, "POST", "/api/plugins/nope/install")
        self.assertEqual(st, 404)
        st, _, b = helpers.jrequest(self.port, "POST", "/api/plugins/Bad-Name/install")
        self.assertEqual(st, 404)

    def test_cross_origin_post_403(self):
        st, _, b = helpers.jrequest(self.port, "POST", "/api/plugins/rescan",
                                    headers={"Origin": "http://evil.example"})
        self.assertEqual((st, b["error"]["code"]), (403, "forbidden"))
        st, _, _ = helpers.jrequest(self.port, "POST", "/api/plugins/rescan",
                                    headers={"Host": f"evil.example:{self.port}"})
        self.assertEqual(st, 403)
        st, _, _ = helpers.jrequest(self.port, "POST", "/api/plugins/rescan",
                                    headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(st, 200)


class DomainHttp(HttpBase):
    def test_formats(self):
        cases = [("a.txt", ms.sample_txt(), "txt", "변환기 시연용"),
                 ("a.html", ms.sample_html(), "html", "# HTML 시연 문서"),
                 ("a.docx", ms.sample_docx(), "docx", "| 항목 | 설명 |"),
                 ("a.hwpx", ms.sample_hwpx(), "hwpx", "| 열1 | 열2 |")]
        for name, data, fmt, needle in cases:
            st, _, b = self.convert(data, name)
            self.assertEqual(st, 200, (name, b))
            self.assertEqual(b["format"], fmt)
            self.assertIn(needle, b["markdown"])
        st, _, b = self.convert(ms.sample_docx(), "a.docx")
        self.assertIn("# DOCX 시연 문서", b["markdown"])

    def test_zip_attacks_400_and_no_fault(self):
        attacks = {"zipbomb.docx": ms.zipbomb_docx(), "bz.docx": ms.bzip2_docx(),
                   "crc.docx": ms.crc_broken_docx(), "small.docx": ms.small_size_docx(),
                   "doctype.docx": ms.doctype_docx(), "other.zip": ms.make_zip([("a.xml", "<a/>")])}
        for name, data in attacks.items():
            st, _, b = self.convert(data, name)
            self.assertEqual((st, b["error"]["code"]), (400, "rejected"), name)
        self.assertEqual(self.failures("docx_conv"), 0)
        # 선언 크기를 줄인 파일은 잘린 XML 이 되어 변환기에서 손상된 문서로 거부된다
        st, _, b = self.convert(ms.small_size_docx(), "small.docx")
        self.assertEqual((st, b["error"]["message"]), (400, "손상된 문서"))
        hist = helpers.jrequest(self.port, "GET", "/api/history")[2]["items"]
        self.assertEqual(hist[0]["converter"], "docx_conv")
        self.assertEqual(self.failures("docx_conv"), 0)
        self.assertEqual(self.convert(ms.sample_txt(), "ok.txt")[0], 200)
        hist = helpers.jrequest(self.port, "GET", "/api/history")[2]["items"]
        self.assertFalse(hist[1]["ok"])
        self.assertTrue(hist[1]["reason"])

    def test_xml_encoding_400_and_no_fault(self):
        for name, data in (("u16.docx", ms.utf16_doctype_docx()), ("latin.docx", ms.latin1_decl_docx())):
            st, _, b = self.convert(data, name)
            self.assertEqual((st, b["error"]["code"]), (400, "rejected"), (name, b))
        self.assertEqual(self.failures("docx_conv"), 0)
        self.assertEqual(self.state("docx_conv"), "active")

    def test_deep_nesting_hwpx_not_fault(self):
        st, _, b = self.convert(ms.deep_hwpx(10000), "deep.hwpx")
        self.assertIn(st, (200, 400), b)
        if st == 400:
            self.assertEqual(b["error"]["code"], "rejected")
        self.assertEqual(self.failures("hwpx_conv"), 0)
        self.assertEqual(self.state("hwpx_conv"), "active")

    def test_zip_without_known_members_rejected(self):
        for name in ("a.html", "a.zip"):
            st, _, b = self.convert(ms.html_only_zip(), name)
            self.assertEqual((st, b["error"]["code"], b["error"]["message"]),
                             (400, "rejected", "지원하지 않는 형식"), name)
        for n in ("html_conv", "txt_conv", "docx_conv", "hwpx_conv"):
            self.assertEqual(self.failures(n), 0, n)
        hist = helpers.jrequest(self.port, "GET", "/api/history")[2]["items"]
        self.assertEqual([h["converter"] for h in hist[:2]], ["", ""])

    def test_long_section_number_hwpx_three_times(self):
        for _ in range(3):
            st, _, b = self.convert(ms.long_section_hwpx(), "long.hwpx")
            self.assertEqual((st, b["error"]["code"]), (400, "rejected"), b)
            self.assertIn("손상된 문서", b["error"]["message"])
        self.assertEqual(self.failures("hwpx_conv"), 0)
        self.assertEqual(self.state("hwpx_conv"), "active")

    def test_broken_html_three_times(self):
        for _ in range(3):
            st, _, b = self.convert(ms.broken_html(), "broken.html")
            self.assertEqual(st, 200, b)
            self.assertEqual(b["format"], "html")
            self.assertIn("a", b["markdown"])
        self.assertEqual(self.failures("html_conv"), 0)
        self.assertEqual(self.state("html_conv"), "active")

    def test_length_and_size_limits(self):
        def raw_status(length_header):
            # 본문을 보내지 않고 헤더만 보낸다. 411·413 은 본문을 읽기 전에 와야 한다.
            s = socket.create_connection(("127.0.0.1", self.port), timeout=10)
            try:
                s.sendall((f"POST /api/convert HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                           f"{length_header}X-Filename: big.txt\r\n\r\n").encode())
                return s.recv(4096).split(b"\r\n", 1)[0]
            finally:
                s.close()
        self.assertIn(b" 411 ", raw_status(""))
        self.assertIn(b" 413 ", raw_status(f"Content-Length: {LIMIT + 1}\r\n"))

    def test_path_names_and_download_ids(self):
        for raw in ("../../x.txt", "C:\\x.txt", "..%2F..%2Fx.txt"):
            st, _, b = helpers.jrequest(self.port, "POST", "/api/convert", b"hi",
                                        {"X-Filename": urllib.parse.quote(raw)})
            self.assertEqual(st, 200, raw)
            self.assertRegex(b["id"], r"^[0-9a-f]{12}$")
            # 한 번만 디코딩하므로 이중 인코딩된 이름은 구분자가 되지 않는다
            self.assertEqual(b["filename"], "x.txt" if "%" not in raw else raw)
        self.assertEqual(len(self.files_left()), 6)  # 3건 × (.in, .md)
        for f in self.files_left():
            self.assertRegex(f, r"^[0-9a-f]{12}\.(in|md)$")
        st, _, _ = helpers.request(self.port, "GET", "/api/files/../../app.py")
        self.assertEqual(st, 404)
        self.assertEqual(helpers.request(self.port, "GET", "/api/files/ABCDEF123456.md")[0], 404)
        self.assertEqual(helpers.request(self.port, "GET", "/api/files/0123456789ab.md")[0], 404)

    def test_unknown_post_and_unsupported(self):
        st, _, b = self.convert(ms.sample_txt(), "a.txt", "no_such_post")
        self.assertEqual(st, 400)
        self.assertIn("모르는 후처리기", b["error"]["message"])
        st, _, b = self.convert(ms.sample_txt(), "a.txt", "txt_conv")  # kind 가 다름
        self.assertEqual(st, 400)
        st, _, b = self.convert(bytes(range(256)) * 4, "a.bin")
        self.assertEqual(st, 400)
        self.assertIn("지원하지 않는 형식", b["error"]["message"])

    def test_inactive_post_warns_unavailable(self):
        self.k.remove("whitespace_post")
        st, _, b = self.convert(b"x  \n", "a.txt", "whitespace_post")
        self.assertEqual(st, 200, b)
        self.assertEqual(b["markdown"], "x  \n")
        self.assertEqual([(w["plugin"], w["code"]) for w in b["warnings"]], [("whitespace_post", "unavailable")])

    def test_postprocessors_frontmatter_whitespace(self):
        st, _, b = self.convert(ms.sample_docx(), "보고서.docx", "whitespace_post,frontmatter_post")
        self.assertEqual(st, 200)
        md = b["markdown"]
        self.assertTrue(md.startswith("---\ntitle: \"DOCX 시연 문서\""))
        self.assertIn('source_file: "보고서.docx"', md)
        self.assertIn('converter: "docx_conv"', md)
        st, _, b = self.convert("a  \n\n\n\n\nb\n".encode(), "w.txt", "whitespace_post")
        self.assertEqual(b["markdown"], "a\n\n\nb\n")

    def test_size_boundary_postprocessor(self):
        data = b"a" * (LIMIT - 50)
        st, _, b = self.convert(data, "big.txt")
        self.assertEqual(st, 200)
        base = b["markdown"]
        self.assertGreaterEqual(len(base.encode("utf-8")), LIMIT - 50)
        st, _, b = self.convert(data, "big.txt", "frontmatter_post")
        self.assertEqual(st, 200, b.get("error"))
        self.assertEqual(len(b["warnings"]), 1)
        w = b["warnings"][0]
        self.assertEqual((w["plugin"], w["code"]), ("frontmatter_post", "rejected"))
        self.assertIn("20MB", w["message"])
        self.assertEqual(b["markdown"], base)
        self.assertEqual(self.failures("frontmatter_post"), 0)

    def test_converter_result_too_large_rejected(self):
        with self.assertRaises(CallError) as cm:
            flow.convert(self.k, b"a" * LIMIT, "max.txt", [], Trace("t"))  # 결과 = 입력 + 줄바꿈 1바이트
        self.assertEqual((cm.exception.code, cm.exception.status), ("rejected", 400))
        self.assertIn("결과가 20MB 를 넘음", cm.exception.message)
        self.assertEqual(self.failures("txt_conv"), 0)
        self.assertEqual(self.files_left(), [])

    def test_storage_write_failure(self):
        st_srv = self.k.internals["storage"]
        orig_write = st_srv._write_file

        def fail_md(path, data):
            if path.endswith(".md"):
                raise OSError("시험용 쓰기 실패")
            return orig_write(path, data)
        st_srv._write_file = fail_md
        st, _, b = self.convert(b"hello", "a.txt")
        self.assertEqual((st, b["error"]["code"]), (500, "internal"), b)
        self.assertEqual(self.files_left(), [])
        hist = helpers.jrequest(self.port, "GET", "/api/history")[2]["items"]
        self.assertEqual(len(hist), 1)
        self.assertFalse(hist[0]["ok"])
        self.assertIn("저장 실패", hist[0]["reason"])
        self.assertNotIn("파일 정리 실패", hist[0]["reason"])
        st_srv._write_file = orig_write
        st, _, b = self.convert(b"hello", "a.txt")
        self.assertEqual(st, 200, b)

    def test_storage_write_and_cleanup_failure(self):
        st_srv = self.k.internals["storage"]
        orig_write = st_srv._write_file

        def fail_md(path, data):
            if path.endswith(".md"):
                raise OSError("시험용 쓰기 실패")
            return orig_write(path, data)

        def fail_remove(file_id, ext):
            raise OSError("시험용 지우기 실패")
        st_srv._write_file = fail_md
        st_srv.remove_file = fail_remove
        st, _, b = self.convert(b"hello", "a.txt")
        self.assertEqual((st, b["error"]["code"]), (500, "internal"), b)
        hist = helpers.jrequest(self.port, "GET", "/api/history")[2]["items"]
        self.assertEqual(len(hist), 1)
        self.assertIn("저장 실패", hist[0]["reason"])
        self.assertIn("파일 정리 실패", hist[0]["reason"])


@unittest.skipUnless(HAS_FITZ, "PyMuPDF 없음: PDF 정상 변환·broken.pdf·암호 PDF 시험 건너뜀")
class PdfWithPyMuPDF(HttpBase):
    def test_pdf_converts(self):
        st, _, b = self.convert(ms.sample_pdf(), "a.pdf")
        self.assertEqual((st, b["format"]), (200, "pdf"), b)
        self.assertIn("Second page text.", b["markdown"])

    def test_broken_pdf(self):
        st, _, b = self.convert(ms.broken_pdf(), "broken.pdf")
        self.assertEqual(st, 400)
        self.assertIn("손상된 문서", b["error"]["message"])
        self.assertEqual(self.failures("pdf_conv"), 0)
        self.assertEqual(self.state("pdf_conv"), "active")
        self.assertEqual(self.convert(ms.sample_txt(), "ok.txt")[0], 200)

    def test_encrypted_pdf(self):
        st, _, b = self.convert(ms.encrypted_pdf(), "secret.pdf")
        self.assertEqual((st, b["error"]["code"]), (400, "rejected"), b)
        self.assertIn("암호가 걸린 PDF", b["error"]["message"])
        self.assertEqual(self.failures("pdf_conv"), 0)
        self.assertEqual(self.state("pdf_conv"), "active")


@unittest.skipIf(HAS_FITZ, "PyMuPDF 가 있는 환경: 없는 환경 시험은 PdfWithPyMuPDF 가 대신함")
class PdfWithoutPyMuPDF(HttpBase):
    def test_pdf_conv_rejected_and_pdf_400(self):
        info = self.k.plugin_info("pdf_conv")
        self.assertEqual(info["state"], "rejected")
        self.assertIn("PyMuPDF 없음", info["reason"])
        st, _, b = self.convert(ms.broken_pdf(), "a.pdf")
        self.assertEqual(st, 400)
        self.assertIn("이 형식의 변환기가 설치되어 있지 않음", b["error"]["message"])


class PostprocessorFailure(HttpBase):
    plugins = ["txt_conv.py", "whitespace_post.py"]
    fixtures = ["broken_post.py", "reject_post.py"]

    def test_fault_gives_warning(self):
        st, _, b = self.convert("x  \n".encode(), "a.txt", "broken_post,whitespace_post")
        self.assertEqual(st, 200)
        self.assertEqual(b["markdown"], "x\n")
        self.assertEqual([(w["plugin"], w["code"]) for w in b["warnings"]], [("broken_post", "fault")])
        self.assertEqual(self.failures("broken_post"), 1)
        self.assertEqual(self.failures("txt_conv"), 0)

    def test_rejected_gives_warning_not_counted(self):
        for _ in range(3):
            st, _, b = self.convert("x  \n".encode(), "a.txt", "reject_post,whitespace_post")
            self.assertEqual(st, 200)
            self.assertEqual(b["markdown"], "x\n")
            self.assertEqual([(w["plugin"], w["code"]) for w in b["warnings"]], [("reject_post", "rejected")])
            self.assertIn("시험용 후처리 거부", b["warnings"][0]["message"])
        self.assertEqual(self.failures("reject_post"), 0)
        self.assertEqual(self.state("reject_post"), "active")
        hist = helpers.jrequest(self.port, "GET", "/api/history")[2]["items"]
        self.assertTrue(all(h["ok"] for h in hist))


class CsvExample(HttpBase):
    plugins = ["txt_conv.py"]

    def install_csv(self):
        helpers.copy_in(helpers.EXAMPLES + "/csv_conv.py", self.pdir)
        st, _, r = helpers.jrequest(self.port, "POST", "/api/plugins/rescan")
        self.assertIn("csv_conv", r["added"])
        st, _, r = helpers.jrequest(self.port, "POST", "/api/plugins/csv_conv/install")
        self.assertEqual(st, 200)

    def test_csv_before_after_install(self):
        st, _, b = self.convert(ms.sample_csv(), "s.csv")
        self.assertEqual(b["format"], "txt")
        self.install_csv()
        st, _, b = self.convert(ms.sample_csv(), "s.csv")
        self.assertEqual((b["format"], b["converter"]), ("csv", "csv_conv"))
        self.assertIn("| 사과 | 3 | 빨강 |", b["markdown"])

    def test_csv_field_limit_three_times(self):
        self.install_csv()
        for _ in range(3):
            st, _, b = self.convert(ms.long_field_csv(), "long.csv")
            self.assertEqual((st, b["error"]["code"]), (400, "rejected"), b)
            self.assertIn("손상된 문서", b["error"]["message"])
        self.assertEqual(self.failures("csv_conv"), 0)
        self.assertEqual(self.state("csv_conv"), "active")


class BadManifestView(HttpBase):
    """rejected 기록의 MANIFEST 원시 값이 /api/plugins 응답을 깨지 않는다."""
    plugins = ("txt_conv.py",)
    fixtures = ("manifest/m_desc_set.py", "manifest/m_version_bytes.py",
                "manifest/m_order_inf.py", "manifest/m_formats_int.py")

    def test_plugins_api_is_json_with_bad_manifests(self):
        for path in ("/api/plugins", "/api/plugins"):  # rescan 전·후
            st, h, raw = helpers.request(self.port, "GET", path)
            self.assertEqual(st, 200)
            body = json.loads(raw.decode("utf-8"), parse_constant=lambda c: self.fail(f"비 JSON 상수 {c}"))
            got = {p["name"]: p for p in body["plugins"]}
            for n in ("m_desc_set", "m_version_bytes", "m_order_inf", "m_formats_int"):
                self.assertEqual(got[n]["state"], "rejected", n)
            self.assertIsNone(got["m_desc_set"]["description"])
            self.assertIsNone(got["m_version_bytes"]["version"])
            self.assertIsNone(got["m_order_inf"]["order"])
            self.assertIsNone(got["m_formats_int"]["formats"])
            self.assertEqual(got["txt_conv"]["formats"], ["txt"])
            helpers.jrequest(self.port, "POST", "/api/plugins/rescan")


class DuplicateConverter(HttpBase):
    plugins = ["txt_conv.py"]
    fixtures = ["dup_txt.py"]

    def test_duplicate_format_409(self):
        losers = [p["name"] for p in self.k.list_plugins() if p["state"] == "available"]
        self.assertEqual(len(losers), 1)
        st, _, b = helpers.jrequest(self.port, "POST", f"/api/plugins/{losers[0]}/install")
        self.assertEqual((st, b["error"]["code"]), (409, "conflict"))


if __name__ == "__main__":
    unittest.main()
