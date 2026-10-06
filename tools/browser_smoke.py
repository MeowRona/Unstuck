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

        lock = wait.until(EC.element_to_be_clickable((By.ID, "lockCompromiseButton")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", lock)
        wait.until(lambda d: lock.is_displayed() and lock.is_enabled())
        lock.click()
        wait.until(EC.visibility_of_element_located((By.ID, "emptyState")))
        assert "No rescue fits" in driver.find_element(By.ID, "emptyState").text

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
    planner_mobile_flow()
    print("browser smoke: rescue + planner desktop and 390x844 mobile flows PASS")


if __name__ == "__main__":
    main()
