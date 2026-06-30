# Cute Poker Agent Workflow

This is the single file future ChatGPT/Codex contexts should read first.

Last updated: 2026-06-30

## Repository

- GitHub repo: `YeerooXY/cute-poker`
- Local path: `C:\Users\Yeeroo\Desktop\Work\Projects\cute_poker_modular`
- Active branch: `logic-core-hardening`
- Current product direction: user experience polish for the browser poker table.

## Current development focus

Work should generally improve table feel and user experience:

- UI polish.
- Sound effects.
- Poker-table feel.
- Visual feedback.
- Social/fun polish.
- Room/settings polish.
- Action log readability.
- Small animations and micro-interactions.

Avoid large backend rewrites, bot-strategy rewrites, or game-rule refactors unless directly required for UX.

## Patch-first workflow

For each implementation task, the assistant should provide one terminal-runnable PowerShell patch that:

1. Edits only the intended files.
2. Refuses to continue if expected anchors are missing.
3. Runs focused tests relevant to the changed area.
4. Runs the full suite when practical.
5. Does not push.
6. Does not blindly stage everything.

The user should then:

1. Run the patch script.
2. Start the server manually.
3. Check the UX in the browser.
4. Run `.\scripts\safe_commit.ps1 -Message "..."`
5. Push manually with `git push origin logic-core-hardening`.

Helper path in the repo: `scripts/safe_commit.ps1`.

## Commit workflow

Use:

```powershell
.\scripts\safe_commit.ps1 -Message "feat(ui): describe change"
```

The safe commit script:

- Verifies the branch is `logic-core-hardening`.
- Shows changed files.
- Runs focused tests based on touched files.
- Runs `python -m pytest -q` by default.
- Stages allowed files explicitly.
- Excludes debug/generated folders such as `logs/`, `tmp/`, `.pytest_cache/`, `__pycache__/`, `htmlcov/`, and local env files.
- Does not push.

Use `-SkipFullTests` only for emergency/local WIP commits.

Use `-AllowNoDocs` only for tiny mechanical changes where documentation really does not need updating.

## Documentation policy

Documentation is part of the codebase now.

When changing behavior, architecture, workflow, tests, SFX mapping, UI conventions, state contracts, routes, or important file responsibilities, update this file or another Markdown file under `docs/`.

For this project:

- Code changes and documentation changes should usually travel together.
- SFX asset additions must update `static/sounds/CREDITS.md`.
- Workflow/tooling changes must update this file.
- UX conventions should be documented here until a dedicated UX guide exists.
- Do not rely on chat history as the only source of truth.

## Important frontend files

### `static/app.js`

- Main browser client.
- WebSocket handling.
- State rendering.
- Action controls.
- Action log.
- Hand history.
- Post-hand review UI.
- UX micro-interactions.

### `static/sfx.js`

- Central sound system.
- Reads localStorage settings: `poker_sfx_enabled`, `poker_sfx_volume`.
- Serves sounds from `/sound/*`.
- Prefers bundled files from `static/sounds/`.
- Falls back to generated Web Audio tones.
- Handles autoplay unlock.
- Avoids duplicate state-driven action sounds.
- Must preserve history-review silence.

### `static/styles.css`

- Main UI/table styling.
- Button feel.
- Poker table.
- Player seats.
- Chips/cards.
- Action bar.
- Chat/history/admin panels.
- Small animations.

### `static/index.html`

- Main DOM structure.
- Connect screen.
- Room settings.
- Game table.
- Action bar.
- Chat/history/action-log containers.
- Loads `static/sfx.js` before `static/app.js`.

### `server.py`

- FastAPI app and WebSocket route.
- Serves bundled sound assets via `/sound/*`.

### `static/sounds/`

- Final game-ready bundled audio assets.

### `static/sounds/CREDITS.md`

- Required attribution for sound assets.
- Prefer CC0.
- CC BY 4.0 is acceptable with attribution.
- Avoid CC BY-NC for anything public/commercial.

## Important tests

### `tests/test_sfx_frontend.js`

- Node/static tests for `static/sfx.js`.
- Checks SFX mapping and duplicate-prevention behavior.

### `tests/test_sound_assets.py`

- Verifies bundled sound files are served through `/sound/*`.

### `tests/test_history_ui_static.py`

- Static frontend wiring tests.
- Used for hand history, review modal, action log, and UX wiring checks.

### `tests/test_workflow_docs.py`

- Verifies this workflow file and safe commit helper exist.

## Current UX/SFX conventions

State-driven poker sounds should come from `static/sfx.js` via `processState`.

Current poker action sound mapping includes:

- blinds/antes -> quiet chips
- check -> check
- call -> call
- bet/raise -> bet_raise
- fold -> fold
- all-in -> all_in
- showdown -> showdown
- pot win -> pot_win
- timer warning -> timer_warning

UI chrome click sounds may be added separately, but avoid double-playing sounds for main poker actions that already get state-driven SFX.

History review must remain quiet. Do not play live-table SFX while browsing old hands.

## Patch rules for future agents

Do:

- Keep patches small and safe.
- Use explicit file edits.
- Run focused tests in the patch script.
- Run the full suite before commit.
- Update docs when behavior/workflow changes.
- Add tests for new UI/SFX wiring where practical.
- Preserve existing history-review and duplicate-prevention sound behavior.

Do not:

- Push unless the user explicitly asks.
- Use `git add .`.
- Commit generated logs/debug data.
- Add CC BY-NC assets.
- Retune bots unless the task specifically asks for bot behavior.
- Rewrite backend/game logic for a purely visual UX task.
- Depend on uncommitted local scratch files.
