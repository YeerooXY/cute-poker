# Cute Poker - Next Session Handoff

## Current State

The latest work focused on poker action-log trust, showdown clarity, UI polish, and repeatable visual verification.

Follow-up UI work completed:
- Added a real post-hand summary panel for showdown.
  - Shows single winner or split-pot headline.
  - Shows final pot.
  - Lists revealed players with best-card rows and hand details.
  - Marks winners/splitters and provides a `Deal Next` button.
- Replaced the inline player hand-rank style with a dedicated `seat-hand-rank` class.
- Tightened player-seat spacing for header, stack, badges, cards, committed bet, and showdown hand rank text.
- Added `tests/test_post_hand_panel_ui.js` for the new post-hand panel behavior.
- Added tasteful UI animation hooks:
  - Active player glow.
  - New community/seat card reveal classes.
  - Pot count-up when the pot increases within the same hand.
  - Compact chip stacks for pot and committed bets, with chip-to-pot movement cue.
  - Showdown winner glow on seats and post-hand winner rows.
  - Subtle table glow during showdown.
- Added `tests/test_animation_helpers.js` for frontend animation trigger and chip-stack helper behavior.

Visual verification status:
- Playwright is now installed as a dev dependency.
- `playwright.config.js` runs Chromium desktop and mobile visual smoke tests against `python server.py` at `http://127.0.0.1:8000`.
- `tests/visual/cute_poker_visual.spec.js` includes:
  - A showdown visual smoke test for post-hand panel, cards, chips, and winner/table glow.
  - An action-log edge-case visual smoke test for returned excess, showdown rows, hidden betting rows, and all-in runout separators.

Implemented action-log fixes:
- Backend normalizes unmatched covering shoves after `return_uncalled_excess()`.
- Dindybot-style case should now log an effective call when excess chips are returned.
  - Example target: `Dindybot calls 618`, not `Dindybot goes all-in 978`, if Dindybot keeps chips behind.
- Frontend action wording now distinguishes:
  - `calls X`
  - `calls X and is all-in`
  - `goes all-in for X`
  - `raises all-in to X`
- `goes all-in 0` should no longer appear.
- Showdown action-log rows now list each revealed player best 5-card hand.
- Winner rows are marked with `-- wins` or `-- splits`.
- Added regression coverage for returned-excess log normalization.

## Verification Already Run Before Latest ChatGPT Branch

- `python -m pytest -q`
  - Result: `486 passed in 47.61s`
- Node frontend suite:
  - `node tests/test_animation_helpers.js`
    - Result: `8 passed`
  - `node tests/test_post_hand_panel_ui.js`
    - Result: `3 passed`
  - `node tests/test_action_log_frontend.js`
    - Result: `22 passed`
  - `node tests/test_action_log_preservation.js`
    - Result: `9 passed`
  - `node tests/test_bug_condition_exploration_frontend.js`
    - Result: `9 passed`
  - `node tests/test_action_log_ui.js`
    - Result: `13 passed`

## Latest ChatGPT Branch

Branch created from `logic-core-hardening`:

`chatgpt/action-log-visual-coverage`

Added on this branch:
- Extended `tests/visual/cute_poker_visual.spec.js` with a second deterministic visual smoke test.
- Updated this handoff to reflect that Playwright is now present and visual verification has started.

The new Playwright test has not been run from ChatGPT. Run locally before merging.

Recommended local verification:

```powershell
npm run test:visual
python -m pytest -q
node tests/test_animation_helpers.js
node tests/test_post_hand_panel_ui.js
node tests/test_action_log_frontend.js
node tests/test_action_log_preservation.js
node tests/test_bug_condition_exploration_frontend.js
node tests/test_action_log_ui.js
```

## Important Config Change

Codex config was updated at:

`C:\Users\Yeeroo\.codex\config.toml`

The trusted project scope was narrowed from:

`C:\Users\Yeeroo`

to:

`C:\Users\Yeeroo\Desktop\Work\Projects`

A fresh Codex session may be needed for that config to fully apply.

## Next TODO

1. Pull or check out the latest branch:

   `chatgpt/action-log-visual-coverage`

2. Run visual verification:

   `npm run test:visual`

3. Inspect generated screenshots under Playwright test output.

   Focus on:
   - Returned-excess action-log case.
   - `Dindybot calls 618`, not `Dindybot goes all-in ...`, when Dindybot keeps chips behind.
   - Heads-up preflop SB facing BB logs `calls 5`, not `checks`.
   - River separator appears whenever 5 community cards are dealt.
   - Betting rows are hidden during showdown.
   - Each revealed player shows best 5-card hand.
   - Winner row has `-- wins`.
   - Split winner rows have `-- splits`.

4. If screenshots look good, merge `chatgpt/action-log-visual-coverage` into `logic-core-hardening`.

5. If screenshots show crowding, continue UI polish:
   - Finish hero/player seat spacing around cards, badges, stack, and hand rank.
   - Reduce mobile action-log obstruction further if needed.
   - Make the post-hand panel visually richer only if it still looks too empty/dark.

## Files Recently Touched For This Work

- `poker/game.py`
- `static/app.js`
- `static/index.html`
- `static/styles.css`
- `playwright.config.js`
- `package.json`
- `package-lock.json`
- `tests/visual/cute_poker_visual.spec.js`
- `tests/test_action_log_unit.py`
- `tests/test_action_log_frontend.js`
- `tests/test_action_log_preservation.js`
- `tests/test_bug_condition_exploration_frontend.js`
- `tests/test_animation_helpers.js`
- `tests/test_post_hand_panel_ui.js`
- `tests/test_ui_log_polish.py`
