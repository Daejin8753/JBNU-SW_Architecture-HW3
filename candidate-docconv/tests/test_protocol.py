"""별도 프로세스 프로토콜: 값 검사(check_values)와 inproc·process 왕복이 같은지."""
import json
import unittest

import helpers
from kernel import contract
from kernel.kernel import CallError
from kernel.plugin_host import decode, encode

RUNTIMES = (("values_inproc", "valin"), ("values_proc", "valproc"))


class CheckValues(unittest.TestCase):
    def test_check_values_rules(self):
        ok = {"a": [1, "s", 1.5, True, None, b"x", {"b": -2**63, "c": 2**63 - 1}]}
        self.assertIsNone(contract.check_values(ok))
        for bad in ({"v": (1, 2)}, {1: "x"}, {"v": 2**63}, {"v": -2**63 - 1}, {"v": float("nan")},
                    {"v": float("inf")}, {"v": bytearray(b"x")}, {"v": {1, 2}}):
            self.assertIsNotNone(contract.check_values(bad), repr(bad))

    def test_encode_decode_escape(self):
        cases = [{"$b64": "YQ=="}, {"$esc": 1}, {"$esc": {"$b64": "x"}}, {"k": b"\x00\xff"},
                 [b"a", {"$b64": b"b"}], {"$b64": "YQ==", "other": 1}]
        for v in cases:
            wire = json.loads(json.dumps(encode(v), allow_nan=False))
            self.assertEqual(decode(wire), v, repr(v))
        self.assertEqual(encode({"$esc": 1}), {"$esc": {"$esc": 1}})
        self.assertEqual(encode(b"a"), {"$b64": "YQ=="})


class ValueRoundTrip(unittest.TestCase):
    def setUp(self):
        data, pdir = helpers.make_env(self, fixtures=["values_inproc.py", "values_proc.py"])
        self.k = helpers.start_kernel(self, data, pdir)
        for name, _ in RUNTIMES:
            self.assertEqual(self.k.plugin_info(name)["state"], "active", name)
        self.assertEqual(self.k.plugin_info("values_proc")["runtime"], "process")
        self.assertEqual(self.k.plugin_info("values_inproc")["runtime"], "inproc")

    def call(self, name, fmt, case, data=b"", members=None):
        return self.k.call(name, "convert", helpers.payload(case, fmt, data, members))

    def test_output_value_violations_are_faults(self):
        for case in ("tuple", "intkey", "bigint", "nan"):
            for name, fmt in RUNTIMES:
                with self.assertRaises(CallError) as cm:
                    self.call(name, fmt, case)
                self.assertEqual(cm.exception.code, "fault", (name, case))
                self.assertIn("출력", cm.exception.message, (name, case))
                self.assertEqual(self.k.plugin_info(name)["failures"], 1, (name, case))
                self.call(name, fmt, "plain")  # 성공하면 0 으로
                self.assertEqual(self.k.plugin_info(name)["failures"], 0, (name, case))

    def test_same_values_both_runtimes(self):
        members = {"word/document.xml": b"<a/>\x00\xff", "$b64": b"x"}
        expect = {
            "edge": {"max": 2**63 - 1, "min": -2**63},
            "esc": {"a": {"$b64": "YQ=="}, "b": {"$esc": 1}},
            "bytes": {"data": b"\x00\x01\xffdata", "members": members},
        }
        for case, meta in expect.items():
            outs = [self.call(name, fmt, case, b"\x00\x01\xffdata", members) for name, fmt in RUNTIMES]
            for (name, _), out in zip(RUNTIMES, outs):
                self.assertEqual(out, {"markdown": case, "meta": meta}, (name, case))
            self.assertEqual(outs[0], outs[1], case)
        out = self.call("values_proc", "valproc", "bytes", b"z", members)
        self.assertIsInstance(out["meta"]["data"], bytes)
        self.assertIsInstance(out["meta"]["members"]["$b64"], bytes)


if __name__ == "__main__":
    unittest.main()
