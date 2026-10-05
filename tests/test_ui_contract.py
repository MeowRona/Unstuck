from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

    def test_demo_and_qloo_status_are_plain_and_honest(self):
        self.assertIn("Try a rescue · 60 sec", self.html)
        self.assertIn("Taste profile · not live yet", self.html)
        self.assertIn("Qloo was not called for this result", self.js)
        self.assertNotIn("Load the judge-friendly demo settings", self.html)
        self.assertNotIn("Demo · fixture taste", self.js)

    def test_rejection_reasons_and_undo_are_present(self):
        for reason in ("too_far", "not_my_vibe", "been_there", "skip"):
            self.assertIn(f'data-reject-reason="{reason}"', self.html)
        self.assertIn("/api/undo-reject", self.js)
        self.assertIn("Undo last skip", self.js)
        self.assertIn("does not retrain a model", self.js)

    def test_choice_flow_has_route_copy_checks_and_timeline(self):
        self.assertIn('id="choiceConstraints"', self.html)
        self.assertIn('id="choiceTimeline"', self.html)
        self.assertIn('id="choiceChecks"', self.html)
        self.assertIn('id="choiceRouteLink"', self.html)
        self.assertIn('id="copyPlan"', self.html)
        self.assertIn("This is a plan, not a reservation.", self.js)

    def test_evidence_and_about_expose_real_limits(self):
        self.assertIn("How this recommendation was made", self.html)
        self.assertIn("What did Qloo change?", self.js)
        self.assertIn("fixture preview and is not evidence of Qloo performance", self.js)
        self.assertIn("https://github.com/MeowRona/Unstuck", self.html)
        self.assertIn("scheduled Warsaw transit", self.html)
        self.assertIn("Google Places:", self.html)

    def test_main_result_meta_avoids_internal_strategy_names(self):
        self.assertNotIn("candidates left", self.js)
        self.assertNotIn("${escapeHtml(result.strategy_used)} search", self.js)

    def test_multi_element_selectors_use_the_list_helper(self):
        self.assertIn("$('.reject-inline').forEach", self.js)

    def test_new_surfaces_have_narrow_screen_rules(self):
        css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 760px)", css)
        self.assertIn(".choice-detail-grid { grid-template-columns: 1fr; }", css)
        self.assertIn("#decisionEvidenceBody { grid-template-columns: 1fr; }", css)
        self.assertIn(".reject-reasons { grid-template-columns: 1fr; }", css)


if __name__ == "__main__":
    unittest.main()
