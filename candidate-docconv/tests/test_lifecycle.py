"""E1~E6: 확장·제거·장애 격리·계약 위반·의존 금지·보존."""
import ast
import glob
import json
import os
import threading
import time
import unittest

import helpers
import make_samples as ms
from kernel import constraints, flow
from kernel.kernel import CallError
from kernel.trace import Trace

payload = helpers.payload

# E5: 반드시 잡아야 하는 위반 fixture 이름(파일이 모두 있는지 먼저 확인한다)
EXPECTED_VIOLATIONS = (
    "v_dunder", "v_extpkg", "v_importlib", "v_internal", "v_kernel", "v_open", "v_os",
    "v_plugin_import", "v_relative", "v_sqlite", "v_req_os", "v_req_internal",
)

# E4: MANIFEST 타입 위반·읽기 실패 fixture 이름
EXPECTED_MANIFEST_BAD = (
    "m_requires_none", "m_timeout_str", "m_timeout_bool", "m_timeout_big", "m_inproc_requires",
    "m_formats_int", "m_formats_empty", "m_match_two", "m_match_ext", "m_match_text",
    "m_order_bool", "m_order_str", "m_name_type", "m_runtime_bad", "m_syntax", "m_not_literal",
    "m_not_utf8", "m_desc_set", "m_version_bytes", "m_order_inf",
)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


class E1Extension(unittest.TestCase):
    def test_example_plugin_added_without_restart(self):
        data, pdir = helpers.make_env(self, plugins=helpers.ALL_PLUGINS)
        k = helpers.start_kernel(self, data, pdir)
        # 설치 전: csv 는 txt 로 변환된다
        r = flow.convert(k, ms.sample_csv(), "s.csv", [], Trace("t"))
        self.assertEqual((r["format"], r["converter"]), ("txt", "txt_conv"))
        self.assertEqual([w["code"] for w in r["warnings"]], ["ext_mismatch"])
        helpers.copy_in(os.path.join(helpers.EXAMPLES, "csv_conv.py"), pdir)
        self.assertIn("csv_conv", k.rescan()["added"])
        self.assertEqual(k.plugin_info("csv_conv")["state"], "available")
        k.install("csv_conv")
        r = flow.convert(k, ms.sample_csv(), "s.csv", [], Trace("t"))
        self.assertEqual((r["format"], r["converter"]), ("csv", "csv_conv"))
        self.assertEqual(r["warnings"], [])
        self.assertIn("| 이름 | 수량 | 비고 |", r["markdown"])
        self.assertIn("|---|---|---|", r["markdown"])


class E2Remove(unittest.TestCase):
    def test_remove_blocks_plugin_others_ok(self):
        data, pdir = helpers.make_env(self, plugins=helpers.ALL_PLUGINS)
        k = helpers.start_kernel(self, data, pdir)
        k.remove("html_conv")
        with self.assertRaises(CallError) as cm:
            flow.convert(k, ms.sample_html(), "a.html", [], Trace("t"))
        self.assertEqual(cm.exception.code, "rejected")
        self.assertIn("변환기가 설치되어 있지 않음", cm.exception.message)
        r = flow.convert(k, ms.sample_txt(), "a.txt", [], Trace("t"))
        self.assertEqual(r["converter"], "txt_conv")

    def test_remove_during_call(self):
        """장벽에 걸린 호출 중 remove → 거부·409·rescan 뒤 기록 유지 → 장벽 열기 → 성공 → 새 자식."""
        data, pdir = helpers.make_env(self, fixtures=["hang_conv.py"])
        k = helpers.start_kernel(self, data, pdir)
        inst = k.instance_of("hang_conv")
        old_pid = inst.pid
        self.assertIsNotNone(old_pid)
        bar = helpers.Barrier(self, inst)
        result = {}

        def call():
            try:
                result["out"] = k.call("hang_conv", "convert", payload("n1", data=b"abc"))
            except CallError as e:
                result["err"] = e
        t = threading.Thread(target=call)
        path = os.path.join(pdir, "hang_conv.py")
        away = os.path.join(os.path.dirname(pdir), "hang_conv.py.away")

        def inflight():
            info = k.plugin_info("hang_conv")
            return info["inflight"] if info else None
        try:
            t.start()
            helpers.wait_until(self, lambda: inflight() == 1, 2.0, "inflight 1")
            k.remove("hang_conv")
            with self.assertRaises(CallError) as cm:
                k.call("hang_conv", "convert", payload("x"))
            self.assertEqual(cm.exception.code, "unavailable")
            self.assertEqual(inflight(), 1)
            with self.assertRaises(CallError) as cm:
                k.install("hang_conv")
            self.assertEqual((cm.exception.code, cm.exception.status), ("conflict", 409))
            os.replace(path, away)
            k.rescan()
            self.assertEqual(inflight(), 1, "rescan 이 진행 중 호출의 기록을 지움")
            os.replace(away, path)
            self.assertEqual(inflight(), 1)
            with self.assertRaises(CallError) as cm:
                k.install("hang_conv")
            self.assertEqual((cm.exception.code, cm.exception.status), ("conflict", 409))
        finally:
            bar.event.set()
        t.join(10)
        self.assertEqual(bar.failed, [])
        self.assertNotIn("err", result)
        self.assertEqual(result["out"]["markdown"], "n1:3")
        self.assertEqual(inflight(), 0)
        k.install("hang_conv")
        out = k.call("hang_conv", "convert", payload("again"))
        self.assertEqual(out["markdown"], "again:0")
        new_pid = k.instance_of("hang_conv").pid
        self.assertIsNotNone(new_pid)
        self.assertNotEqual(new_pid, old_pid)


class E3FaultIsolation(unittest.TestCase):
    def test_rejected_not_counted_exceptions_disable(self):
        data, pdir = helpers.make_env(self, plugins=["txt_conv.py"], fixtures=["faulty_conv.py"])
        k = helpers.start_kernel(self, data, pdir)
        for _ in range(10):
            with self.assertRaises(CallError) as cm:
                k.call("faulty_conv", "convert", payload("reject", "faultfmt"))
            self.assertEqual(cm.exception.code, "rejected")
        self.assertEqual(k.plugin_info("faulty_conv")["state"], "active")
        self.assertEqual(k.plugin_info("faulty_conv")["failures"], 0)
        for _ in range(3):
            with self.assertRaises(CallError) as cm:
                k.call("faulty_conv", "convert", payload("boom", "faultfmt"))
            self.assertEqual(cm.exception.code, "fault")
        info = k.plugin_info("faulty_conv")
        self.assertEqual(info["state"], "disabled")
        self.assertIn("연속 3회 장애", info["reason"])
        with self.assertRaises(CallError) as cm:
            k.call("faulty_conv", "convert", payload("ok", "faultfmt"))
        self.assertEqual(cm.exception.code, "unavailable")
        # 코어는 계속 응답한다
        self.assertEqual(flow.convert(k, b"hello", "a.txt", [], Trace("t"))["converter"], "txt_conv")
        k.install("faulty_conv")  # 다시 켜기
        self.assertEqual(k.plugin_info("faulty_conv")["state"], "active")
        self.assertEqual(k.call("faulty_conv", "convert", payload("ok", "faultfmt"))["markdown"], "ok")

    def test_success_resets_failures(self):
        data, pdir = helpers.make_env(self, fixtures=["faulty_conv.py"])
        k = helpers.start_kernel(self, data, pdir)
        for _ in range(2):
            with self.assertRaises(CallError):
                k.call("faulty_conv", "convert", payload("boom", "faultfmt"))
        self.assertEqual(k.plugin_info("faulty_conv")["failures"], 2)
        k.call("faulty_conv", "convert", payload("ok", "faultfmt"))
        self.assertEqual(k.plugin_info("faulty_conv")["failures"], 0)

    def test_process_hang_times_out_then_restarts(self):
        data, pdir = helpers.make_env(self, fixtures=["hang_conv.py"])
        k = helpers.start_kernel(self, data, pdir)
        old_pid = k.instance_of("hang_conv").pid
        t0 = time.monotonic()
        with self.assertRaises(CallError) as cm:
            k.call("hang_conv", "convert", payload("hang"))
        took = time.monotonic() - t0
        self.assertEqual(cm.exception.code, "fault")
        self.assertLess(took, 6.0)
        self.assertEqual(k.plugin_info("hang_conv")["failures"], 1)
        out = k.call("hang_conv", "convert", payload("next"))
        self.assertEqual(out["markdown"], "next:0")
        self.assertNotEqual(k.instance_of("hang_conv").pid, old_pid)
        self.assertEqual(k.plugin_info("hang_conv")["failures"], 0)

    def _after_shutdown_checks(self, k, name, adapter, failures, saved):
        self.assertIsNone(adapter.pid)
        with self.assertRaises(CallError) as cm:
            k.call(name, "convert", payload("x"))
        self.assertEqual(cm.exception.code, "unavailable")
        with self.assertRaises(CallError) as cm:
            k.install(name)
        self.assertEqual((cm.exception.code, cm.exception.status), ("unavailable", 503))
        self.assertIsNone(adapter.pid, "종료 뒤 새 자식이 생김")
        self.assertEqual(k.plugin_info(name)["failures"], failures)
        self.assertEqual(read_bytes(os.path.join(k.data_dir, "plugins.json")), saved)

    def test_shutdown_while_child_answers(self):
        """(가) 자식 안에서 도는 호출: waiting 을 본 뒤 shutdown → unavailable(3초 안)."""
        data, pdir = helpers.make_env(self, fixtures=["hold_conv.py"])
        k = helpers.start_kernel(self, data, pdir)
        adapter = k.instance_of("hold_conv")
        self.assertIsNotNone(adapter.pid)
        saved = read_bytes(os.path.join(data, "plugins.json"))
        failures = k.plugin_info("hold_conv")["failures"]
        result = {}

        def call():
            try:
                result["out"] = k.call("hold_conv", "convert", payload("hang"))
            except CallError as e:
                result["err"] = e
            result["at"] = time.monotonic()
        t = threading.Thread(target=call)
        t.start()
        helpers.wait_until(self, lambda: adapter.waiting, 2.0, "어댑터 waiting")
        t0 = time.monotonic()
        k.shutdown()
        t.join(5)
        self.assertFalse(t.is_alive())
        self.assertEqual(result["err"].code, "unavailable")
        self.assertLess(result["at"] - t0, 3.0)
        self._after_shutdown_checks(k, "hold_conv", adapter, failures, saved)

    def test_shutdown_before_handle(self):
        """(나) 참조를 잡고 handle 에 들어가기 전인 호출: 장벽 → shutdown → 장벽 열기 → unavailable."""
        data, pdir = helpers.make_env(self, fixtures=["hang_conv.py"])
        k = helpers.start_kernel(self, data, pdir)
        adapter = k.instance_of("hang_conv")
        self.assertIsNotNone(adapter.pid)
        saved = read_bytes(os.path.join(data, "plugins.json"))
        failures = k.plugin_info("hang_conv")["failures"]
        bar = helpers.Barrier(self, adapter)
        result = {}

        def call():
            try:
                result["out"] = k.call("hang_conv", "convert", payload("n1"))
            except CallError as e:
                result["err"] = e
        t = threading.Thread(target=call)
        try:
            t.start()
            helpers.wait_until(self, lambda: k.plugin_info("hang_conv")["inflight"] == 1, 2.0, "inflight 1")
            k.shutdown()
            self.assertIsNone(adapter.pid)
        finally:
            bar.event.set()
        t.join(10)
        self.assertEqual(bar.failed, [])
        self.assertNotIn("out", result)
        self.assertEqual(result["err"].code, "unavailable")
        self._after_shutdown_checks(k, "hang_conv", adapter, failures, saved)


class E4ContractViolation(unittest.TestCase):
    def test_contract_violations(self):
        data, pdir = helpers.make_env(
            self, plugins=["txt_conv.py", "future_contract.py"],
            fixtures=["no_handle.py", "load_error.py", "bad_output_conv.py"])
        k = helpers.start_kernel(self, data, pdir)
        fc = k.plugin_info("future_contract")
        self.assertEqual(fc["state"], "rejected")
        self.assertIn("계약 버전 불일치", fc["reason"])
        self.assertEqual(k.plugin_info("no_handle")["state"], "rejected")
        self.assertIn("handle 미구현", k.plugin_info("no_handle")["reason"])
        le = k.plugin_info("load_error")
        self.assertEqual(le["state"], "rejected")
        self.assertIn("적재 중 예외", le["reason"])
        self.assertEqual(k.plugin_info("txt_conv")["state"], "active")
        self.assertEqual(k.plugin_info("bad_output_conv")["state"], "active")
        with self.assertRaises(CallError) as cm:
            k.call("bad_output_conv", "convert", payload("a", "badoutfmt"))
        self.assertEqual(cm.exception.code, "fault")
        self.assertIn("출력 계약 위반", cm.exception.message)
        self.assertEqual(k.plugin_info("bad_output_conv")["failures"], 1)

    def test_not_subclass_rejected_both_runtimes(self):
        data, pdir = helpers.make_env(self, plugins=["txt_conv.py"],
                                      fixtures=["not_subclass.py", "not_subclass_proc.py"])
        k = helpers.start_kernel(self, data, pdir)
        for name in ("not_subclass", "not_subclass_proc"):
            info = k.plugin_info(name)
            self.assertEqual(info["state"], "rejected", name)
            self.assertIn("Plugin(contract.Plugin) 클래스 없음", info["reason"], name)
        self.assertIsNone(k.instance_of("not_subclass_proc"))
        self.assertEqual(k.plugin_info("txt_conv")["state"], "active")

    def test_manifest_type_violations_do_not_stop_start(self):
        data, pdir = helpers.make_env(self, plugins=["txt_conv.py"])
        files = {os.path.splitext(os.path.basename(f))[0]: f
                 for f in glob.glob(os.path.join(helpers.MANIFESTS, "*.py"))}
        self.assertEqual(sorted(files), sorted(EXPECTED_MANIFEST_BAD))
        for f in files.values():
            helpers.copy_in(f, pdir)
        k = helpers.start_kernel(self, data, pdir)  # 예외 없이 시작해야 한다
        for name in EXPECTED_MANIFEST_BAD:
            info = k.plugin_info(name)
            self.assertIsNotNone(info, name)
            self.assertEqual(info["state"], "rejected", name)
            self.assertTrue(info["reason"], name)
        self.assertEqual(k.plugin_info("txt_conv")["state"], "active")
        # rescan 도 멈추지 않는다
        k.rescan()
        self.assertEqual(flow.convert(k, b"hi", "a.txt", [], Trace("t"))["converter"], "txt_conv")
        # 같은 파일을 다시 install 해도 rejected 400 이고 앱은 계속 동작한다
        for name in ("m_requires_none", "m_formats_int", "m_syntax"):
            with self.assertRaises(CallError) as cm:
                k.install(name)
            self.assertEqual(cm.exception.code, "rejected", name)

    def test_missing_package_rejected(self):
        data, pdir = helpers.make_env(self, fixtures=["missing_pkg.py"])
        k = helpers.start_kernel(self, data, pdir)
        info = k.plugin_info("missing_pkg")
        self.assertEqual(info["state"], "rejected")
        self.assertIn("자식 기동 실패", info["reason"])

    def test_duplicate_format_install_409(self):
        data, pdir = helpers.make_env(self, plugins=["txt_conv.py"], fixtures=["dup_txt.py"])
        k = helpers.start_kernel(self, data, pdir)
        states = {k.plugin_info("txt_conv")["state"], k.plugin_info("dup_txt")["state"]}
        self.assertEqual(states, {"active", "available"})
        loser = "dup_txt" if k.plugin_info("dup_txt")["state"] == "available" else "txt_conv"
        with self.assertRaises(CallError) as cm:
            k.install(loser)
        self.assertEqual(cm.exception.status, 409)

    def test_match_extension_overlap_409(self):
        data, pdir = helpers.make_env(self, fixtures=["ext_a.py", "ext_b.py"])
        k = helpers.start_kernel(self, data, pdir)
        self.assertEqual(k.plugin_info("ext_a")["state"], "active")
        self.assertEqual(k.plugin_info("ext_b")["state"], "available")
        with self.assertRaises(CallError) as cm:
            k.install("ext_b")
        self.assertEqual((cm.exception.code, cm.exception.status), ("conflict", 409))
        self.assertIn(".xyz", cm.exception.message)
        k.remove("ext_a")
        k.install("ext_b")  # 겹치는 active 변환기가 없으면 설치된다
        self.assertEqual(k.plugin_info("ext_b")["state"], "active")

    def test_match_with_two_formats_rejected(self):
        data, pdir = helpers.make_env(self, fixtures=["manifest/m_match_two.py"])
        k = helpers.start_kernel(self, data, pdir)
        info = k.plugin_info("m_match_two")
        self.assertEqual(info["state"], "rejected")
        self.assertIn("formats", info["reason"])


class E5Dependency(unittest.TestCase):
    def test_all_violations_caught(self):
        files = {os.path.splitext(os.path.basename(f))[0]: f
                 for f in glob.glob(os.path.join(helpers.VIOLATIONS, "*.py"))}
        for name in EXPECTED_VIOLATIONS:
            self.assertIn(name, files, f"fixture 없음: {name}")
        for name in EXPECTED_VIOLATIONS:
            _, bad = constraints.check_file(files[name])
            self.assertTrue(bad, f"잡지 못함: {name}")
            self.assertTrue(all(isinstance(ln, int) and ln > 0 for ln, _ in bad), name)

    def test_requires_cannot_open_banned(self):
        for name, module in (("v_req_os", "os"), ("v_req_internal", "internal")):
            _, bad = constraints.check_file(os.path.join(helpers.VIOLATIONS, name + ".py"))
            msgs = " ".join(m for _, m in bad)
            self.assertIn("requires", msgs, name)
            self.assertIn(module, msgs, name)

    def test_real_plugins_clean(self):
        files = glob.glob(os.path.join(helpers.PLUGINS, "*.py")) + glob.glob(os.path.join(helpers.EXAMPLES, "*.py"))
        self.assertGreaterEqual(len(files), 9)
        for f in files:
            self.assertEqual(constraints.check_file(f)[1], [], f)

    def test_violation_install_rejected(self):
        data, pdir = helpers.make_env(self)
        for name in EXPECTED_VIOLATIONS:
            helpers.copy_in(os.path.join(helpers.VIOLATIONS, name + ".py"), pdir)
        k = helpers.start_kernel(self, data, pdir)
        plugins = {p["name"]: p for p in k.list_plugins()}
        self.assertEqual(sorted(plugins), sorted(EXPECTED_VIOLATIONS))
        for name in EXPECTED_VIOLATIONS:
            p = plugins[name]
            self.assertEqual(p["state"], "rejected", name)
            self.assertIn("정적 검사 위반", p["reason"], name)
            self.assertRegex(p["reason"], r"\d+행", name)
            with self.assertRaises(CallError) as cm:
                k.install(name)
            self.assertEqual(cm.exception.code, "rejected", name)

    def test_kernel_does_not_import_adapters(self):
        files = sorted(glob.glob(os.path.join(helpers.BASE, "kernel", "*.py")))
        names = {os.path.basename(f) for f in files}
        self.assertTrue({"kernel.py", "loader.py", "flow.py", "plugin_host.py", "contract.py"} <= names, names)
        for f in files:
            with open(f, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), f)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for n in names:
                    self.assertNotEqual(n.split(".")[0], "adapters", f"{os.path.basename(f)}:{node.lineno}")


class E6Persistence(unittest.TestCase):
    def test_new_instance_keeps_data_and_states(self):
        data, pdir = helpers.make_env(self, plugins=["txt_conv.py", "whitespace_post.py"],
                                      fixtures=["faulty_conv.py"])
        k = helpers.start_kernel(self, data, pdir)
        r = flow.convert(k, b"hello", "a.txt", ["whitespace_post"], Trace("t"))
        k.remove("whitespace_post")
        for _ in range(3):
            with self.assertRaises(CallError):
                k.call("faulty_conv", "convert", payload("boom", "faultfmt"))
        reason = k.plugin_info("faulty_conv")["reason"]
        k.shutdown()
        k2 = helpers.start_kernel(self, data, pdir)
        self.assertEqual(k2.plugin_info("faulty_conv")["state"], "disabled")
        self.assertEqual(k2.plugin_info("faulty_conv")["reason"], reason)
        self.assertEqual(k2.plugin_info("whitespace_post")["state"], "available")
        self.assertEqual(k2.plugin_info("txt_conv")["state"], "active")
        hist = flow.history(k2, Trace("t"))["items"]
        self.assertEqual(hist[0]["id"], r["id"])
        self.assertEqual(flow.download(k2, r["id"], Trace("t"))["body"], b"hello\n")
        with open(os.path.join(data, "plugins.json"), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["faulty_conv"]["state"], "disabled")


if __name__ == "__main__":
    unittest.main()
