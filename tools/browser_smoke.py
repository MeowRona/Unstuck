from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


BASE = os.environ.get("UNSTUCK_BROWSER_URL", "http://127.0.0.1:8817")


def driver_for(width: int, height: int):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--window-size={width},{height}")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    chromedriver = shutil.which("chromedriver")
    service = Service(chromedriver) if chromedriver else Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(width, height)
    return driver


def wait_cards(driver):
    wait = WebDriverWait(driver, 30)
    wait.until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, ".recommendation-card")) > 0
        or (
            d.find_elements(By.ID, "emptyState")
            and "hidden" not in d.find_element(By.ID, "emptyState").get_attribute("class")
        )
    )
    cards = driver.find_elements(By.CSS_SELECTOR, ".recommendation-card")
    if not cards:
        empty = driver.find_element(By.ID, "emptyState").text
        console = driver.get_log("browser")
        raise AssertionError(f"demo returned no cards; empty_state={empty!r}; console={console!r}")
    wait.until(lambda d: not d.find_elements(By.CSS_SELECTOR, ".route-loading"))
    return wait


def assert_no_severe_console(driver):
    severe = [row for row in driver.get_log("browser") if row.get("level") == "SEVERE"]
    if severe:
        raise AssertionError(f"severe browser console errors: {severe}")


def desktop_flow():
    driver = driver_for(1440, 900)
    try:
        driver.get(BASE)
        wait = WebDriverWait(driver, 30)
        wait.until(EC.element_to_be_clickable((By.ID, "loadJudgeDemo"))).click()
        wait = wait_cards(driver)
        note = driver.find_element(By.ID, "demoScenarioNote").text
        assert "9 Oct 2026" in note and "scenario only" in note

        meta = driver.find_element(By.ID, "resultMeta").text
        assert "candidates left" not in meta
        assert "shorter_stay" not in meta
        cards = driver.find_elements(By.CSS_SELECTOR, ".recommendation-card")
        assert cards
        assert "HOŻA Steakhouse" not in [card.find_element(By.CSS_SELECTOR, "h3").text for card in cards]

        first_id = cards[0].get_attribute("data-card-index")
        cards[0].find_element(By.CSS_SELECTOR, ".reject-inline").click()
        wait.until(EC.visibility_of_element_located((By.ID, "rejectModal")))
        driver.find_element(By.CSS_SELECTOR, '[data-reject-reason="not_my_vibe"]').click()
        wait.until(EC.element_to_be_clickable((By.ID, "undoReject")))
        assert "skipped" in driver.find_element(By.ID, "resultMeta").text
        driver.find_element(By.ID, "undoReject").click()
        wait.until(lambda d: "Undo last skip" not in d.find_element(By.ID, "resultMeta").text)

        lock = wait.until(EC.visibility_of_element_located((By.ID, "lockCompromiseButton")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", lock)
        # Expanded real venue data can make the demo solvable without a
        # compromise. A disabled lock then correctly means nothing to undo.
        if not lock.is_enabled():
            assert ("No compromise" in lock.text or
                    "Checked conditions kept" in lock.text or
                    "No editable compromise" in lock.text), lock.text
            assert driver.find_elements(By.CSS_SELECTOR, ".recommendation-card")
        else:
            locked_label = lock.text
            lock.click()
            # A travel or stay lock must be explicit. Other allowed changes
            # may still lead to a valid plan; never demand an empty result.
            if "Keep stay at" in locked_label:
                wait.until(lambda d: d.find_element(By.ID, "summaryStayWrap").get_attribute("title") == "Locked at this minimum stay")
            elif "Keep travel at" in locked_label:
                wait.until(lambda d: d.find_element(By.ID, "summaryTravelWrap").get_attribute("title") == "Locked at this travel limit")
            else:
                wait.until(lambda d: d.find_element(By.ID, "lockCompromiseButton").text != locked_label)
            is_empty = "hidden" not in driver.find_element(By.ID, "emptyState").get_attribute("class")
            assert is_empty or driver.find_elements(By.CSS_SELECTOR, ".recommendation-card")

        driver.find_element(By.CSS_SELECTOR, '[data-menu-action="demo"]').click() if False else None
        # Reload the deterministic demo for the final-plan path.
        driver.get(BASE + "/?demo=1")
        wait = wait_cards(driver)
        wait.until(EC.element_to_be_clickable((By.ID, "chooseButton"))).click()
        wait.until(EC.visibility_of_element_located((By.ID, "choiceModal")))
        assert driver.find_element(By.ID, "choiceConstraints").text
        assert driver.find_element(By.ID, "choiceTimeline").text
        route_href = driver.find_element(By.ID, "choiceRouteLink").get_attribute("href")
        assert route_href.startswith("https://www.google.com/maps/dir/")
        driver.find_element(By.ID, "copyPlan").click()
        assert "reservation" in driver.find_element(By.CSS_SELECTOR, ".choice-note").text.lower()

        driver.find_element(By.ID, "closeChoice").click()
        driver.find_element(By.ID, "menuButton").click()
        driver.find_element(By.CSS_SELECTOR, '[data-menu-action="about"]').click()
        wait.until(EC.visibility_of_element_located((By.ID, "aboutModal")))
        about = driver.find_element(By.ID, "aboutModal").text
        assert "Qloo" in about and "Google Places" in about and "GitHub" in about
        assert_no_severe_console(driver)
    finally:
        driver.quit()


def mobile_flow():
    driver = driver_for(390, 844)
    try:
        driver.get(BASE)
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.ID, "showList")))
        overflow = driver.execute_script(
            "return document.documentElement.scrollWidth - window.innerWidth"
        )
        if overflow > 1:
            raise AssertionError(f"mobile horizontal overflow: {overflow}px")
        driver.find_element(By.ID, "showMap").click()
        assert "mobile-map" in driver.find_element(By.CSS_SELECTOR, ".workspace").get_attribute("class")
        driver.find_element(By.ID, "showList").click()
        assert "mobile-map" not in driver.find_element(By.CSS_SELECTOR, ".workspace").get_attribute("class")
        driver.find_element(By.ID, "themeToggle").click()
        assert driver.execute_script("return document.documentElement.dataset.theme") in {"light", "dark"}
        assert_no_severe_console(driver)
    finally:
        driver.quit()


def planner_flow():
    driver = driver_for(1440, 900)
    try:
        driver.get(BASE)
        wait = WebDriverWait(driver, 45)
        wait.until(EC.element_to_be_clickable((By.ID, "plannerModeButton"))).click()
        wait.until(EC.visibility_of_element_located((By.ID, "plannerSurface")))
        wait.until(lambda d: "Loading" not in d.find_element(By.ID, "plannerCoverageStatus").text)

        driver.find_element(By.ID, "plannerDemo").click()
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".timeline-activity")) >= 2)
        ids = [row.get_attribute("data-plan-item") for row in driver.find_elements(By.CSS_SELECTOR, ".timeline-activity")]
        self_event = "event:simple-plan-2026-10-17"
        if self_event not in ids:
            raise AssertionError(f"planner demo lost locked Simple Plan event: {ids}")
        if not any(str(value).startswith("restaurant:") for value in ids):
            raise AssertionError(f"planner demo did not include meal stop: {ids}")
        if not any(str(value).startswith("attraction:") for value in ids):
            raise AssertionError(f"planner demo did not include flexible attraction: {ids}")
        assert "not live yet" in driver.find_element(By.ID, "plannerTasteStatus").text.lower()

        wait.until(EC.element_to_be_clickable((By.ID, "plannerSavePlan"))).click()
        saved = driver.execute_script("return localStorage.getItem('unstuck-planner-saved-v1')")
        if not saved or "2026-10-17" not in saved:
            raise AssertionError("planner save did not persist to localStorage")

        driver.refresh()
        wait.until(EC.visibility_of_element_located((By.ID, "plannerSurface")))
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".saved-plan-row")) > 0)
        load = driver.find_element(By.CSS_SELECTOR, '[data-saved-action="load"]')
        load.click()
        wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, ".timeline-activity")) >= 2)
        ids = [row.get_attribute("data-plan-item") for row in driver.find_elements(By.CSS_SELECTOR, ".timeline-activity")]
        if self_event not in ids:
            raise AssertionError("saved plan lost locked event")

        replace_button = None
        for row in driver.find_elements(By.CSS_SELECTOR, ".timeline-activity"):
            if row.get_attribute("data-plan-item") != self_event:
                replace_button = row.find_element(By.CSS_SELECTOR, '[data-item-action="replace"]')
                break
        if replace_button is None:
            raise AssertionError("planner demo had no replaceable stop")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", replace_button)
        replace_button.click()
        wait.until(lambda d: "Repair kept" in d.find_element(By.ID, "plannerRepairNote").text or "No feasible" in d.find_element(By.ID, "plannerTimeline").text)
        ids_after = [row.get_attribute("data-plan-item") for row in driver.find_elements(By.CSS_SELECTOR, ".timeline-activity")]
        if ids_after and self_event not in ids_after:
            raise AssertionError("repair changed the locked concert")

        # Whole-evening demo explicitly simulates a dinner failure; no invented closure.
        demo_button = wait.until(EC.element_to_be_clickable((By.ID, "plannerRescueDemo")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", demo_button)
        demo_button.click()
        wait.until(lambda d: "SIMULATED" in d.find_element(By.ID, "plannerRepairNote").text
                   and not d.find_element(By.ID, "plannerRescueDemo").get_attribute("disabled"))
        note = driver.find_element(By.ID, "plannerRepairNote").text
        assert "no live closure detected" in note.lower(), note
        assert "BEFORE:" in note and "AFTER:" in note, note
        assert "SECOND FAILURE:" in note, note
        assert "BOTH FAILED RESTAURANTS: excluded" in note, note
        assert "FINAL SUBSTITUTE:" in note and "not verified" not in note, note
        ids = [row.get_attribute("data-plan-item") for row in driver.find_elements(By.CSS_SELECTOR, ".timeline-activity")]
        assert self_event in ids, f"simulated dinner failure moved locked concert: {ids}"
        assert_no_severe_console(driver)
    finally:
        driver.quit()



def planner_route_conflict_retry_flow():
    """Mock only route-check response to exercise the browser's bounded tool retry."""
    driver = driver_for(1440, 900)
    try:
        driver.get(BASE)
        wait = WebDriverWait(driver, 45)
        wait.until(EC.element_to_be_clickable((By.ID, "plannerModeButton"))).click()
        wait.until(EC.visibility_of_element_located((By.ID, "plannerSurface")))
        wait.until(lambda d: "Loading" not in d.find_element(By.ID, "plannerCoverageStatus").text)
        driver.execute_script("""
            const nativeFetch = window.fetch.bind(window);
            window.__routeRetryProbe = {count:0, ids:[]};
            window.fetch = function(path, options) {
              if (String(path).includes('/api/planner/route-check')) {
                const request = JSON.parse(options.body);
                const probe = window.__routeRetryProbe;
                probe.ids.push(request.plan.id);
                const first = ++probe.count === 1;
                const plan = Object.assign({}, request.plan, {
                  route_status:'checked',
                  feasibility:first ? 'conflict' : 'confirmed',
                  route_conflicts:first ? ['Test fixture: simulated late arrival'] : []
                });
                return Promise.resolve(new Response(JSON.stringify({plan:plan, brief:request.brief}), {
                  status:200, headers:{'Content-Type':'application/json'}
                }));
              }
              return nativeFetch(path, options);
            };
        """)
        driver.find_element(By.ID, "plannerDemo").click()
        wait.until(lambda d: d.execute_script("return window.__routeRetryProbe.count") >= 2)
        wait.until(lambda d: "automatically validated option 2" in
                   d.find_element(By.ID, "plannerResultsMeta").text.lower())
        ids = driver.execute_script("return window.__routeRetryProbe.ids")
        if len(ids) != 2 or ids[0] == ids[1]:
            raise AssertionError(f"route conflict did not trigger next distinct variant: {ids}")
        selected = driver.find_elements(By.CSS_SELECTOR, "#plannerVariantTabs button.active")
        if not selected or "Option 2" not in selected[0].text:
            raise AssertionError("route-verified second option was not selected")
        activities = [x.get_attribute("data-plan-item")
                      for x in driver.find_elements(By.CSS_SELECTOR, ".timeline-activity")]
        if "event:simple-plan-2026-10-17" not in activities:
            raise AssertionError("bounded route retry lost the locked concert")
        assert_no_severe_console(driver)
    finally:
        driver.quit()


def taste_picker_flow():
    """Exercise the browser's real selection UI without calling live Qloo."""
    driver = driver_for(1440, 900)
    try:
        driver.get(BASE)
        wait = WebDriverWait(driver, 35)
        driver.execute_script("""
            const originalFetch = window.fetch.bind(window);
            window.__tastePickerProbe = {requests: [], resolvePending: null};
            window.fetch = function(url, opts) {
              if (String(url).includes('/api/taste-entities')) {
                const request = JSON.parse(opts.body);
                window.__tastePickerProbe.requests.push(request);
                const payload = {available:true, options:[
                  {id:'artist:first', name:'Radiohead', kind:'artist'},
                  {id:'artist:second', name:'Radiohead', kind:'artist'}
                ]};
                if (request.query === 'Delayed') {
                  return new Promise(resolve => window.__tastePickerProbe.resolvePending = () =>
                    resolve(new Response(JSON.stringify(payload), {
                      status:200,headers:{'Content-Type':'application/json'}
                    }))
                  );
                }
                return Promise.resolve(new Response(JSON.stringify(payload), {
                  status:200,headers:{'Content-Type':'application/json'}
                }));
              }
              return originalFetch(url, opts);
            };
        """)
        wait.until(EC.element_to_be_clickable((By.ID, "plannerModeButton"))).click()
        wait.until(EC.visibility_of_element_located((By.ID, "plannerSurface")))
        picker = driver.execute_script(
            "return document.querySelector('#plannerTasteRefs').closest('label').nextElementSibling"
        )
        assert "qloo-picker" in picker.get_attribute("class")
        assert driver.execute_script(
            "return document.querySelector('#editorForm [name=\\\"taste_refs\\\"]').dataset.qlooPickerMounted"
        ) == "true", "Rescue editor did not mount the shared picker"
        field = driver.find_element(By.ID, "plannerTasteRefs")
        field.clear()
        field.send_keys("artist: Radiohead")
        assert driver.execute_script("return window.__tastePickerProbe.requests.length") == 0, (
            "taste lookup must never fire on typing alone"
        )
        picker.find_element(By.CSS_SELECTOR, ".qloo-picker-find").click()
        wait.until(lambda d: len(picker.find_elements(By.CSS_SELECTOR, ".qloo-picker-option")) == 2)
        assert driver.execute_script("return window.__tastePickerProbe.requests[0].kind") == "artist"
        picker.find_elements(By.CSS_SELECTOR, ".qloo-picker-option")[1].click()
        assert field.get_attribute("value") == "qloo-id:artist:second|artist|Radiohead"
        assert len(picker.find_elements(By.CSS_SELECTOR, ".qloo-picker-chip")) == 1

        # A slower response for an older query must not overwrite newer input.
        field.clear()
        field.send_keys("artist: Delayed")
        picker.find_element(By.CSS_SELECTOR, ".qloo-picker-find").click()
        wait.until(lambda d: d.execute_script(
            "return typeof window.__tastePickerProbe.resolvePending === 'function'"
        ))
        field.clear()
        field.send_keys("artist: Changed")
        driver.execute_script("window.__tastePickerProbe.resolvePending()")
        wait.until(lambda d: picker.find_element(By.CSS_SELECTOR, ".qloo-picker-find").is_enabled())
        assert field.get_attribute("value") == "artist: Changed"
        assert not picker.find_elements(By.CSS_SELECTOR, ".qloo-picker-option"), (
            "stale Qloo matches must be dropped after the query changes"
        )
        assert driver.execute_script("return window.__tastePickerProbe.requests.length") == 2
        assert_no_severe_console(driver)
    finally:
        driver.quit()


def good_for_both_ui_flow():
    """The optional second profile persists, but fixture mode never fakes fairness."""
    driver = driver_for(1440, 900)
    try:
        driver.get(BASE + "/?demo=1")
        wait = wait_cards(driver)
        driver.execute_script("document.getElementById('openFullEditor').click()")
        wait.until(EC.visibility_of_element_located((By.ID, "editorModal")))
        editor = driver.find_element(By.ID, "editorForm")
        first = editor.find_element(By.CSS_SELECTOR, '[name="taste_refs"]')
        first.clear()
        first.send_keys("film: Amelie")
        pair = editor.find_element(By.CSS_SELECTOR, '[name="good_for_both"]')
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", pair)
        if not pair.is_selected():
            pair.click()
        second = editor.find_element(By.CSS_SELECTOR, '[name="second_taste_refs"]')
        wait.until(lambda _d: second.is_displayed())
        second.send_keys("artist: Radiohead")
        assert second.get_attribute("value") == "artist: Radiohead"
        assert second.get_attribute("data-qloo-picker-mounted") == "true"
        editor.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        wait.until(lambda d: "hidden" in d.find_element(By.ID, "editorModal").get_attribute("class"))
        wait.until(lambda d: "Good for both" in d.find_element(By.ID, "decisionEvidenceBody").text)
        text = driver.find_element(By.ID, "decisionEvidenceBody").text
        assert "not verified" in text.lower(), text
        assert "operational recommendations only" in text.lower(), text

        driver.execute_script("document.getElementById('openFullEditor').click()")
        wait.until(EC.visibility_of_element_located((By.ID, "editorModal")))
        assert editor.find_element(By.CSS_SELECTOR, '[name="good_for_both"]').is_selected()
        assert editor.find_element(By.CSS_SELECTOR, '[name="second_taste_refs"]').get_attribute("value") == "artist: Radiohead"
        assert_no_severe_console(driver)
    finally:
        driver.quit()


def planner_mobile_flow():
    driver = driver_for(390, 844)
    try:
        driver.get(BASE)
        wait = WebDriverWait(driver, 30)
        wait.until(EC.element_to_be_clickable((By.ID, "plannerModeButton"))).click()
        wait.until(EC.visibility_of_element_located((By.ID, "plannerSurface")))
        overflow = driver.execute_script("return document.documentElement.scrollWidth - window.innerWidth")
        if overflow > 1:
            raise AssertionError(f"planner mobile horizontal overflow: {overflow}px")
        driver.find_element(By.CSS_SELECTOR, '[data-planner-view="explore"]').click()
        assert driver.find_element(By.ID, "plannerSurface").get_attribute("data-mobile-view") == "explore"
        wait.until(EC.visibility_of_element_located((By.ID, "plannerExplore")))
        driver.find_element(By.CSS_SELECTOR, '[data-planner-view="map"]').click()
        assert driver.find_element(By.ID, "plannerSurface").get_attribute("data-mobile-view") == "map"
        wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "planner-map")))
        driver.find_element(By.CSS_SELECTOR, '[data-planner-view="plan"]').click()
        assert driver.find_element(By.ID, "plannerSurface").get_attribute("data-mobile-view") == "plan"
        assert_no_severe_console(driver)
    finally:
        driver.quit()


def main():
    desktop_flow()
    mobile_flow()
    planner_flow()
    planner_route_conflict_retry_flow()
    taste_picker_flow()
    good_for_both_ui_flow()
    planner_mobile_flow()
    print("browser smoke: rescue + planner desktop and 390x844 mobile flows PASS")


if __name__ == "__main__":
    main()
