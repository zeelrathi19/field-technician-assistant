"""WCAG 2.1 AA automated audit (axe-core) on the empty state, a conversation, and mobile."""

from pathlib import Path

AXE = Path(__file__).resolve().parents[1] / "frontend" / "node_modules" / "axe-core" / "axe.min.js"


def audit(page):
    page.add_script_tag(path=str(AXE))
    res = page.evaluate("""async () => (await axe.run(document, {
        runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}})).violations
        .map(v => ({id: v.id, impact: v.impact, n: v.nodes.length, target: v.nodes[0].target.join(' ')}))""")
    return res


def ask(page, text):
    n = page.locator(".msg.assistant:not(.thinking)").count()
    page.fill("#msg", text)
    page.keyboard.press("Enter")
    page.wait_for_function(f"document.querySelectorAll('.msg.assistant:not(.thinking)').length > {n}")


def test_axe_clean_light_and_dark(base_url, browser):
    for scheme in ("light", "dark"):
        page = browser.new_page(color_scheme=scheme)
        page.goto(base_url)
        page.wait_for_selector(".empty")
        assert audit(page) == [], scheme
        ask(page, "How do I reset a CU-series unit?")
        ask(page, "Mark WO-001 complete")
        page.locator(".source summary").first.click()
        assert audit(page) == [], scheme


def test_axe_clean_mobile_with_panel(base_url, browser):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(base_url)
    page.wait_for_selector(".composer")
    page.click("text=My work orders")
    assert audit(page) == []


def test_keyboard_flow(base_url, browser):
    page = browser.new_page()
    page.goto(base_url)
    page.wait_for_selector(".empty")
    first = page.evaluate("[...document.querySelectorAll('a[href],button,textarea,input,summary')]"
                          ".find(e => !e.disabled).className")
    assert first == "skip"  # the skip link is the first focusable element
    page.focus(".skip")
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "msg"
    page.keyboard.type("Show WO-003")
    page.keyboard.press("Enter")
    page.wait_for_selector(".msg.assistant:not(.thinking)")
    page.wait_for_function("document.activeElement && document.activeElement.id === 'msg'")
