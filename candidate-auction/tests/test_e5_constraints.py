"""E5 의존 금지: 정적 검사가 위반을 잡고, 위반 파일은 install 도 거부한다."""
import glob
import os
import unittest

from helpers import BASE, EXAMPLES, FIXTURES, PLUGINS, Env

from kernel import constraints
from kernel.kernel import CallError

VIOLATIONS = ["v_other_plugin", "v_other_plugin_from", "v_internal", "v_kernel_inner",
              "v_relative", "v_importlib", "v_dunder_import", "v_sqlite", "v_os",
              "v_open", "v_external", "v_eval", "v_external_process"]


class ConstraintTest(unittest.TestCase):
    def test_fixtures_caught_with_line(self):
        for name in VIOLATIONS:
            found = constraints.check_file(os.path.join(FIXTURES, name + ".py"))
            self.assertTrue(found, name)
            self.assertEqual(found[0][0], 3, (name, found))  # 위반 줄 번호

    def test_real_plugins_clean(self):
        files = glob.glob(os.path.join(PLUGINS, "*.py")) + glob.glob(os.path.join(EXAMPLES, "*.py"))
        self.assertGreaterEqual(len(files), 7)
        for f in files:
            self.assertEqual(constraints.check_file(f), [], f)

    def test_requires_allowed_only_for_process(self):
        self.assertEqual(constraints.check_file(os.path.join(FIXTURES, "ok_requires.py")), [])
        src = ('import fitz\nMANIFEST = {"name": "x", "kind": "notifier", "contract": "1.0",'
               ' "version": "1", "description": "d", "requires": ["fitz"]}\n')
        self.assertTrue(constraints.check_source(src))  # inproc 은 requires 무시
        ok = "from xml.etree import ElementTree\nimport xml.etree.ElementTree\nfrom kernel.contract import Rejected\n"
        self.assertEqual(constraints.check_source(ok), [])

    def test_install_rejected(self):
        env = Env(plugins=(), fixtures=VIOLATIONS)
        try:
            app = env.app()
            for name in VIOLATIONS:
                info = app.kernel.plugin_info(name)
                self.assertEqual(info["state"], "rejected", name)
                self.assertIn("정적 검사 위반", info["reason"])
                with self.assertRaises(CallError):
                    app.kernel.install(name)
                self.assertEqual(app.kernel.plugin_info(name)["state"], "rejected")
        finally:
            env.close()

    def test_tool_runs(self):
        import subprocess
        import sys
        r = subprocess.run([sys.executable, os.path.join("tools", "check_constraints.py")],
                           cwd=BASE, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, os.path.join("tools", "check_constraints.py"),
                            os.path.join("tests", "fixtures")],
                           cwd=BASE, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
