"""Browser smoke: the documented demo flow, asserted on visible outcomes and API state."""

import json
import urllib.request


def ask(page, text):
    before = page.locator(".msg.assistant:not(.thinking)").count()
    page.fill("#msg", text)
    page.keyboard.press("Enter")
    page.wait_for_function(f"document.querySelectorAll('.msg.assistant:not(.thinking)').length > {before}")
    return page.locator(".msg.assistant:not(.thinking)").last


def roster(base_url):
    with urllib.request.urlopen(base_url + "/api/work-orders") as r:
        return {w["id"]: w for w in json.load(r)["work_orders"]}


def test_demo_flow(base_url, browser):
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base_url)
    page.wait_for_selector(".empty")
    assert "Offline heuristic mode" in page.inner_text(".mode")

    kb = ask(page, "How do I reset a CU-series unit?")
    assert "60 seconds" in kb.inner_text() and kb.locator(".source").count() == 2

    card = ask(page, "Show WO-003")
    assert "Compressor lockout" in card.inner_text()
    assert "WO-003" in page.inner_text(".context-line")

    done = ask(page, "Mark it complete")
    assert "Done" in done.inner_text() and "On Hold → Completed" in done.inner_text()
    assert roster(base_url)["WO-003"]["status"] == "Completed"
    page.wait_for_selector(".panel li.active >> text=Completed")

    refused = ask(page, "Mark WO-001 complete")
    assert "Not done" in refused.inner_text() and "On Hold" in refused.inner_text()
    assert roster(base_url)["WO-001"]["status"] == "In Progress"

    foreign = ask(page, "Put WO-004 on hold")
    assert "not available" in foreign.inner_text()

    firmware = ask(page, "How do I update the thermostat firmware on WO-008?")
    assert "doesn't cover" in firmware.inner_text()

    # history survives reload (session cookie + stored session id)
    page.reload()
    page.wait_for_selector(".msg.assistant")
    assert page.locator(".msg.user").count() == 6
    assert errors == []


def test_mobile_has_no_horizontal_scroll(base_url, browser):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(base_url)
    page.wait_for_selector(".composer")
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    page.click("text=My work orders")
    page.wait_for_selector(".panel.open")
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
