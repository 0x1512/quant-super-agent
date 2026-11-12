"""Bull/bear review-gate tests: structured claims, mechanical aggregation."""
from __future__ import annotations

import json
import unittest

from qsa.llm import LLMError
from qsa.review import parse_review, review_gate

BULL = json.dumps({"side": "bull", "claims": [
    {"kind": "mechanism", "statement": "documented effect", "checkable": False},
    {"kind": "robustness", "statement": "stable across halves",
     "checkable": True, "check": "halves_stability"}]})

BEAR = json.dumps({"side": "bear", "claims": [
    {"kind": "robustness", "statement": "unstable across halves",
     "checkable": True, "check": "halves_stability"}]})


def _card(side: str, rnd: int = 1):
    text = BULL if side == "bull" else BEAR
    card = parse_review(text, side=side, expected_round=rnd, exp_id="E-0001",
                        reviewer="factor" if side == "bull" else "risk",
                        as_of_iso="2024-05-06")
    card["review_id"] = f"R-000{rnd}{'b' if side == 'bear' else 'u'}"
    return card


class TestParseReview(unittest.TestCase):
    def test_parse_bull_and_bear(self):
        bull = parse_review(BULL, side="bull", expected_round=1,
                            exp_id="E-0001", reviewer="factor",
                            as_of_iso="2024-05-06")
        self.assertEqual(bull["side"], "bull")
        self.assertEqual(bull["round"], 1)
        self.assertEqual(len(bull["claims"]), 2)
        # checkable requires a known check name
        self.assertTrue(bull["claims"][1]["checkable"])
        self.assertFalse(bull["claims"][0]["checkable"])

    def test_wrong_side_rejected(self):
        with self.assertRaises(LLMError):
            parse_review(BULL, side="bear", expected_round=1, exp_id="E-0001",
                         reviewer="risk", as_of_iso="2024-05-06")

    def test_unknown_check_rejected(self):
        bad = json.dumps({"side": "bear", "claims": [
            {"kind": "statistical", "statement": "x", "checkable": True,
             "check": "vibes"}]})
        with self.assertRaises(LLMError):
            parse_review(bad, side="bear", expected_round=1, exp_id="E-0001",
                         reviewer="risk", as_of_iso="2024-05-06")

    def test_empty_claims_rejected(self):
        bad = json.dumps({"side": "bull", "claims": []})
        with self.assertRaises(LLMError):
            parse_review(bad, side="bull", expected_round=1, exp_id="E-0001",
                         reviewer="factor", as_of_iso="2024-05-06")

    def test_round_mismatch_rejected(self):
        off = json.dumps({"side": "bull", "round": 3, "claims": [
            {"kind": "mechanism", "statement": "x"}]})
        with self.assertRaises(LLMError):
            parse_review(off, side="bull", expected_round=1, exp_id="E-0001",
                         reviewer="factor", as_of_iso="2024-05-06")


class TestReviewGate(unittest.TestCase):
    def _e(self, exp_id="E-0001"):
        return {"exp_id": exp_id, "verdict": "pass"}

    def test_bear_objection_upheld_when_check_fails(self):
        reviews = [_card("bull"), _card("bear")]
        admitted, report = review_gate(self._e(), {}, reviews, 1,
                                       {"halves_stability": False,
                                        "oos_pass": True,
                                        "window_alignment": True})
        self.assertFalse(admitted)
        self.assertEqual(len(report["upheld_objections"]), 1)
        self.assertEqual(report["upheld_objections"][0]["check"],
                         "halves_stability")

    def test_bear_objection_dismissed_when_check_passes(self):
        reviews = [_card("bull"), _card("bear")]
        admitted, report = review_gate(self._e(), {}, reviews, 1,
                                       {"halves_stability": True,
                                        "oos_pass": True,
                                        "window_alignment": True})
        self.assertTrue(admitted)
        self.assertEqual(len(report["dismissed_objections"]), 1)
        self.assertFalse(report["upheld_objections"])

    def test_rhetoric_never_decides(self):
        bear_talk = _card("bear")
        bear_talk["claims"] = [{"kind": "mechanism",
                                "statement": "i dislike this factor",
                                "checkable": False, "check": None}]
        admitted, _ = review_gate(self._e(), {}, [_card("bull"), bear_talk], 1,
                                  {"halves_stability": False,
                                   "oos_pass": True,
                                   "window_alignment": True})
        self.assertTrue(admitted)  # no verified objection -> admitted

    def test_refuted_bull_claim_recorded_not_fatal(self):
        admitted, report = review_gate(
            self._e(), {}, [_card("bull"), _card("bear")], 1,
            {"halves_stability": True, "oos_pass": True,
             "window_alignment": True})
        # bull also claimed halves_stability (asserts it passes) — it passes,
        # so no refutation here; flip it to refute
        self.assertTrue(admitted)
        self.assertEqual(report["refuted_bull_claims"], [])
        admitted2, report2 = review_gate(
            self._e(), {}, [_card("bull"), _card("bear")], 1,
            {"halves_stability": False, "oos_pass": True,
             "window_alignment": True})
        self.assertFalse(admitted2)
        self.assertEqual(len(report2["refuted_bull_claims"]), 1)

    def test_missing_round_is_a_structure_error(self):
        admitted, report = review_gate(self._e(), {}, [_card("bull")], 1,
                                       {"halves_stability": True})
        self.assertFalse(admitted)
        self.assertIn("round 1: missing bear review",
                      report["structure_errors"])

    def test_two_rounds_require_both_rounds(self):
        reviews = [_card("bull", 1), _card("bear", 1),
                   _card("bull", 2), _card("bear", 2)]
        admitted, report = review_gate(self._e(), {}, reviews, 2,
                                       {"halves_stability": True,
                                        "oos_pass": True,
                                        "window_alignment": True})
        self.assertTrue(admitted)
        self.assertEqual(len(report["review_ids"]), 4)


if __name__ == "__main__":
    unittest.main()
