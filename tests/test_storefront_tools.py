"""Storefront tooling tests (5th correction).

Covers the README policy mechanics: the forbidden-number lint, the
status-card renderer SSOT, the freeze assertion, and the badge counter.
Everything runs on temp copies — the real READMEs are never touched.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_readme as cr  # noqa: E402
import render_readme as rr  # noqa: E402
import write_badge as wb  # noqa: E402


class LintTests(unittest.TestCase):
    def test_clean_prose_passes(self):
        text = ("# Storefront\n\nWe score candidates and settle orders in "
                "minutes. The 30-factor cited library ships. 4.0x anchor.\n")
        self.assertEqual(cr.lint(text), [])

    def test_forbidden_patterns_are_caught(self):
        cases = [
            "78 candidates were scored",
            "14 settled orders per run",
            "the run took 49.2 s",
            "finishes in ~3 min",
            "snapshot d86e69253189c37b",
            "as of 2026-11-16 the bar",
            "run on 20261116",
            "the suite is 353 tests",
            "IC +0.0418 clears it",
        ]
        for line in cases:
            self.assertTrue(cr.lint(f"# t\n\n{line}\n"), f"missed: {line}")

    def test_fenced_code_is_exempt(self):
        text = ("# t\n\n```\n78 candidates scored in 49.2 s\n"
                "```\nprose stays clean\n")
        self.assertEqual(cr.lint(text), [])

    def test_status_card_is_exempt(self):
        card = rr.card_text("en")
        text = f"# t\n\n{card}\n\nclean prose\n"
        self.assertEqual(cr.lint(text), [])

    def test_zh_counts_are_caught(self):
        for line in ["84 个候选", "28 张订单", "353 项测试"]:
            self.assertTrue(cr.lint(f"# t\n\n{line}\n"), f"missed: {line}")


class CardRendererTests(unittest.TestCase):
    def test_card_has_no_unresolved_placeholder(self):
        for lang in ("en", "zh"):
            self.assertNotIn("{{", rr.card_text(lang))

    def test_render_is_idempotent_and_check_detects_drift(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "README.md"
            p.write_text(f"# t\n\n{rr.card_text('en')}\ntrailer\n", "utf-8")
            self.assertFalse(rr.render(p, "en"))  # unchanged
            self.assertTrue(rr.check(p, "en"))
            p.write_text(p.read_text("utf-8").replace(
                "| test suite |", "| test suite | tampered |"), "utf-8")
            self.assertFalse(rr.check(p, "en"))
            self.assertTrue(rr.render(p, "en"))
            self.assertTrue(rr.check(p, "en"))


class FreezeTests(unittest.TestCase):
    def test_freeze_requires_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td)
            readme = fake / "README.md"
            readme.write_text("x", "utf-8")
            orig = cr.RELEASES, cr.ROOT
            try:
                cr.RELEASES = fake / "releases"
                cr.ROOT = fake
                ok, why = cr.freeze_ok(readme)
                self.assertFalse(ok)
                self.assertIn("release-readme", why)
            finally:
                cr.RELEASES, cr.ROOT = orig

    def test_diff_without_convention_fails(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td)
            (fake / "releases" / "v1.0.0").mkdir(parents=True)
            (fake / "releases" / "v1.0.0" / "README.md").write_text(
                "frozen", "utf-8")
            readme = fake / "README.md"
            readme.write_text("changed", "utf-8")
            orig_releases, orig_root, orig_head = cr.RELEASES, cr.ROOT, cr.head_subject
            try:
                cr.RELEASES = fake / "releases"
                cr.ROOT = fake
                cr.head_subject = lambda: "feat: something else"
                ok, why = cr.freeze_ok(readme)
                self.assertFalse(ok)
                cr.head_subject = lambda: "docs(readme): reword opening"
                ok, why = cr.freeze_ok(readme)
                self.assertTrue(ok)
            finally:
                cr.RELEASES, cr.ROOT = orig_releases, orig_root
                cr.head_subject = orig_head


class BadgeTests(unittest.TestCase):
    def test_count_tests_is_positive_int(self):
        n = wb.count_tests()
        self.assertIsInstance(n, int)
        self.assertGreater(n, 100)

    def test_badge_writer_json_shape(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "tests.json"
            orig_argv = sys.argv
            try:
                sys.argv = ["write_badge.py", str(out)]
                rc = wb.main()
            finally:
                sys.argv = orig_argv
            self.assertEqual(rc, 0)
            loaded = json.loads(out.read_text("utf-8"))
            self.assertEqual(loaded["label"], "tests")
            self.assertTrue(loaded["message"].endswith(" passed"))
            self.assertEqual(loaded["color"], "brightgreen")


if __name__ == "__main__":
    unittest.main()
