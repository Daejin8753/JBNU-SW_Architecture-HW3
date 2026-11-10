"""E8: 별도 프로세스 플러그인 동시 호출과 멈춘 요청 격리."""
import threading
import time
import unittest

import helpers
from kernel.kernel import CallError


def payload(name):
    return helpers.payload(name, "hangfmt", name.encode())


class E8Concurrency(unittest.TestCase):
    def setUp(self):
        data, pdir = helpers.make_env(self, fixtures=["hang_conv.py"])
        self.k = helpers.start_kernel(self, data, pdir)

    def _run(self, name, sink):
        t0 = time.monotonic()
        try:
            out = self.k.call("hang_conv", "convert", payload(name))
            sink[name] = ("ok", out["markdown"], time.monotonic() - t0)
        except CallError as e:
            sink[name] = (e.code, e.message, time.monotonic() - t0)

    def test_parallel_and_hang(self):
        sink = {}
        threads = [threading.Thread(target=self._run, args=(f"n{i}", sink)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        for i in range(10):
            self.assertEqual(sink[f"n{i}"][:2], ("ok", f"n{i}:{len(f'n{i}')}"))

        sink.clear()
        adapter = self.k.instance_of("hang_conv")
        hang = threading.Thread(target=self._run, args=("hang", sink))
        hang.start()
        deadline = time.monotonic() + 2
        while not adapter.busy:
            if time.monotonic() > deadline:
                self.fail("2초 안에 busy 를 못 봄")
            time.sleep(0.01)
        normals = [threading.Thread(target=self._run, args=(f"m{i}", sink)) for i in range(2)]
        for t in normals:
            t.start()
        hang.join(10)
        for t in normals:
            t.join(10)
        code, _, took = sink["hang"]
        self.assertEqual(code, "fault")
        self.assertLess(took, 6.0)
        for i in range(2):
            code, msg, took = sink[f"m{i}"]
            self.assertIn(code, ("ok", "busy"), msg)
            if code == "ok":
                self.assertEqual(msg, f"m{i}:2")
            self.assertLess(took, 9.0)
        faults = [n for n, v in sink.items() if v[0] == "fault"]
        self.assertEqual(faults, ["hang"])
        self.assertEqual(self.k.plugin_info("hang_conv")["state"], "active")
        out = self.k.call("hang_conv", "convert", payload("after"))
        self.assertEqual(out["markdown"], "after:5")
        self.assertEqual(self.k.plugin_info("hang_conv")["failures"], 0)


if __name__ == "__main__":
    unittest.main()
