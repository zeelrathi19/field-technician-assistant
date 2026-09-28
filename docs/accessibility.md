# Accessibility (WCAG 2.1 AA)

Audited on 29 Sep 2026 with axe-core 4 (`e2e/test_accessibility.py`, run by `make e2e`) and a manual keyboard pass.

| Area | What the UI does | Evidence |
|---|---|---|
| Colour contrast | All text/background pairs are ≥ 4.5:1 in light and dark themes. The status pill and badge colours were darkened after the audit (amber `#7a5200`, green `#166534`). | axe `color-contrast`: 0 violations, light + dark |
| Not colour alone | Each outcome has a text badge (Answer / Done / Not done / Needs detail / Error), a ✓/✕ receipt and a coloured edge. | Visual review |
| Keyboard | A skip link ("Skip to message box") is the first focusable element. **Enter** sends and **Shift+Enter** adds a new line. Focus returns to the message box after each reply. Sources use native `<details>`. Work orders are buttons. Focus is always visible (3 px outline). | `test_keyboard_flow` |
| Screen readers | The conversation is `role="log"` with `aria-live="polite"`, and `aria-busy` is set while a turn runs. The "working" indicator is `role="status"`. Errors are `role="alert"`. The input is labelled. The mobile panel toggle uses `aria-expanded`/`aria-controls`. | axe `wcag2a/aa`, `wcag21a/aa`: 0 violations |
| Motion | The typing indicator stops under `prefers-reduced-motion`. | CSS |
| Reflow | At 390 px there is no horizontal scroll, and the work-order panel stacks above the chat. | `test_mobile_has_no_horizontal_scroll`, `test_axe_clean_mobile_with_panel` |

Known limits: an automated audit can't judge content quality. The source excerpts are the approved knowledge-base text, shown verbatim.
