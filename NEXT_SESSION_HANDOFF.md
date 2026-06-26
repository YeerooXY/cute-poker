# Cute Poker - Next Session Handoff

## Current State

The latest work focused on poker action-log trust and showdown clarity.

Follow-up UI work completed this session:
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

Browser verification note:
- The local server starts at `http://127.0.0.1:8000`, but the in-app browser backend was unavailable in this Codex session (`agent.browsers.list()` returned `[]`).
- Playwright/Puppeteer are not installed in this repo, so verification stayed on the existing pytest + Node/jsdom stack.

Implemented:
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

Verification already run:
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

Previous verification:
- `python -m pytest -q --durations=30`
  - Result: `486 passed in 52.12s`
- `node tests/test_action_log_frontend.js`
  - Result: `22 passed`
- `node tests/test_action_log_preservation.js`
  - Result: `9 passed`
- `node tests/test_bug_condition_exploration_frontend.js`
  - Result: `9 passed`
- `node tests/test_action_log_ui.js`
  - Result: `13 passed`

## Important Config Change

Codex config was updated at:

`C:\Users\Yeeroo\.codex\config.toml`

The trusted project scope was narrowed from:

`C:\Users\Yeeroo`

to:

`C:\Users\Yeeroo\Desktop\Work\Projects`

A fresh Codex session may be needed for that config to fully apply.

## Next TODO

1. Relaunch Codex from:
   `C:\Users\Yeeroo\Desktop\Work\Projects\cute_poker_modular`

2. Browser-verify the latest action-log changes.
   Focus on a hand where:
   - Player bets/raises all-in.
   - Covering player calls or tries to shove over.
   - Uncalled excess chips are returned.
   - Covering player has chips left after the hand.

   Expected:
   - Log says `calls X`, not `goes all-in X`, when the covering player keeps chips behind.

3. Verify showdown rows in the action log:
   - Each revealed player shows best 5-card hand.
   - Winner row has `-- wins`.
   - Split winner rows have `-- splits`.

4. Verify the older suspicious cases:
   - Heads-up preflop SB facing BB logs `calls 5`, not `checks`.
   - River separator appears whenever 5 community cards are dealt.
   - Betting rows are hidden during showdown.

5. Next UI polish after verification:
   - Build a proper post-hand panel instead of leaving only the compact action bar options. Done.
   - Improve hero/player seat spacing around cards, badges, stack, and hand rank. Started with player-seat spacing.
   - Add tasteful animations in this order:
     1. Active player glow. Done.
     2. Card deal/reveal animation. Done.
     3. Pot count-up. Done.
     4. Chip-to-pot movement. Done.
     5. Showdown winner glow. Done.
     6. Subtle table rim/background glow. Done.

## Files Recently Touched For This Work

- `poker/game.py`
- `static/app.js`
- `static/index.html`
- `static/styles.css`
- `tests/test_action_log_unit.py`
- `tests/test_action_log_frontend.js`
- `tests/test_action_log_preservation.js`
- `tests/test_bug_condition_exploration_frontend.js`
- `tests/test_animation_helpers.js`
- `tests/test_post_hand_panel_ui.js`
- `tests/test_ui_log_polish.py`

There are also earlier uncommitted action-log/showdown changes across README, evaluator/models, frontend HTML/CSS/JS, and tests.
