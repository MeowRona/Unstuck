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
        self.assertIn("Optional taste profile", self.html)
        self.assertNotIn("live Qloo ranking pending API connection", self.html)
        self.assertIn("Qloo was not called for this result", self.js)
        self.assertNotIn("Load the judge-friendly demo settings", self.html)
        self.assertNotIn("Demo · fixture taste", self.js)

    def test_rejection_reasons_and_undo_are_present(self):
        for reason in ("too_far", "not_my_vibe", "been_there", "skip"):
            self.assertIn(f'data-reject-reason="{reason}"', self.html)
        self.assertIn("/api/undo-reject", self.js)
        self.assertIn("Undo last skip", self.js)
        self.assertIn("does not retrain Qloo", self.js)
        self.assertIn('id="rejectionRefine"', self.html)
        self.assertIn("isDistance ? 'Adjust travel' : 'Refine taste'", self.js)
        self.assertIn("openEditor(isDistance ? 'travel' : 'taste')", self.js)
        self.assertIn("action.classList.remove('hidden')", self.js)
        self.assertIn("will not silently change locked conditions", self.js)

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

    def test_plan_a_day_surface_is_real_and_qloo_is_not_claimed_live(self):
        planner_js = (ROOT / "static" / "planner.js").read_text(encoding="utf-8")
        planner_css = (ROOT / "static" / "planner.css").read_text(encoding="utf-8")
        self.assertIn('id="plannerModeButton"', self.html)
        self.assertIn('id="plannerCalendar"', self.html)
        self.assertIn('id="plannerExplore"', self.html)
        self.assertIn('id="plannerMap"', self.html)
        self.assertIn("Checking taste coverage", self.html)
        self.assertIn("Qloo · eligible restaurants only", self.html)
        self.assertIn('id="plannerRescueDemo"', self.html)
        self.assertIn("SIMULATED DINNER FAILURE", planner_js)
        self.assertIn("Actual Qloo coverage:", planner_js)
        self.assertIn("What did Qloo change?", planner_js)
        self.assertIn("Same feasibility pool:", planner_js)
        self.assertIn('id="plannerStudyStart"', self.html)
        self.assertIn('id="plannerStudyExport"', self.html)
        self.assertIn("study_baseline", planner_js)
        self.assertIn("study_with_qloo", planner_js)
        self.assertIn("Math.random()", planner_js)
        self.assertIn("unstuck-anonymous-study-v1", planner_js)
        self.assertIn("Anonymous trial stored on this device.", planner_js)
        self.assertIn("Top plan changed:", planner_js)
        self.assertIn("matched shortlist", planner_js)
        self.assertIn("Insights API called.", planner_js)
        self.assertIn("/api/planner/generate", planner_js)
        self.assertIn("/api/planner/repair", planner_js)
        self.assertIn("/api/planner/route-check", planner_js)
        self.assertIn("/api/planner/ics", planner_js)
        self.assertIn("unstuck-planner-saved-v1", planner_js)
        self.assertIn('data-planner-view="plan"', self.html)
        self.assertIn('data-planner-view="explore"', self.html)
        self.assertIn('data-planner-view="map"', self.html)
        self.assertIn("@media (max-width: 760px)", planner_css)

    def test_exact_entity_picker_is_shared_and_user_triggered(self):
        picker = (ROOT / "static" / "taste-picker.js").read_text(encoding="utf-8")
        self.assertIn('src="/taste-picker.js"', self.html)
        self.assertIn("mount(document.querySelector('#plannerTasteRefs'))", picker)
        self.assertIn("document.querySelector('#editorForm", picker)
        self.assertIn("'/api/taste-entities'", picker)
        self.assertIn("find.addEventListener('click'", picker)
        self.assertIn("no result is selected automatically", picker)
        self.assertIn("qloo-id:", picker)
        self.assertIn("replace(/[|,", picker)
        self.assertIn(".qloo-picker-find", (ROOT / "static" / "styles.css").read_text(encoding="utf-8"))
        self.assertNotIn("once the Qloo API is connected", self.html)

    def test_planner_route_conflict_checks_next_variant_and_stops_after_three(self):
        planner_js = (ROOT / "static" / "planner.js").read_text(encoding="utf-8")
        browser = (ROOT / "tools" / "browser_smoke.py").read_text(encoding="utf-8")
        self.assertIn("Math.min(plans.length, startIndex + 3)", planner_js)
        self.assertIn("for (let index = startIndex; index < lastIndex; index++)", planner_js)
        self.assertIn("const serial = ++routeSerial", planner_js)
        self.assertIn("if (serial !== routeSerial) return", planner_js)
        self.assertIn("route_conflicts", planner_js)
        self.assertIn("No route-verified option", planner_js)
        self.assertIn("plan.feasibility === 'conflict'", planner_js)
        self.assertIn("planner_route_conflict_retry_flow", browser)
        self.assertIn("simulated late arrival", browser)

    def test_dish_only_price_is_not_rendered_as_whole_meal_total(self):
        app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("cost.basis === 'per_person_dish_only'", app_js)
        self.assertIn("Example dish", app_js)
        self.assertIn("meal bill unknown", app_js)
        planner_js = (ROOT / "static" / "planner.js").read_text(encoding="utf-8")
        self.assertIn("Example item", planner_js)


    def test_new_surfaces_have_narrow_screen_rules(self):
        css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 760px)", css)
        self.assertIn(".choice-detail-grid { grid-template-columns: 1fr; }", css)
        self.assertIn("#decisionEvidenceBody { grid-template-columns: 1fr; }", css)
        self.assertIn(".reject-reasons { grid-template-columns: 1fr; }", css)


if __name__ == "__main__":
    unittest.main()
