# Frontend Modularization Notes

Last updated: 2026-06-30

## Current state

The browser client is still organized around one large file: `static/app.js`.

That file currently mixes several responsibilities:

- local state helpers and persistence
- websocket transport
- lobby flows
- hotkeys
- auto-deal and auto-check-fold
- admin/player roster rendering
- action controls and betting math
- table rendering
- chat rendering
- hand history and history review
- folded/uncontested reveal UX

This works, but it makes UI polish slower because button styling, DOM structure, and behavior are spread across unrelated sections.

## Button audit

The main button variants already have CSS coverage:

- `.btn`
- `.btn-gold`
- `.btn-green`
- `.btn-dim`
- `.btn-fold`
- `.btn-call`
- `.btn-raise`
- `.btn-allin`
- `.btn-deal`
- `.btn-lg`
- `.btn-sm`
- `.btn-tiny`

The gaps found during this audit were dynamic or feature-local classes that existed in JS without dedicated CSS hooks:

- `.history-review-close-btn`
- `.post-hand-recovery-btn`
- `.folded-reveal-actions`
- `.folded-reveal-btn`

Those selectors should exist even when a button also inherits shared `.btn` styles, because they are the module-level hooks that keep layout and future polish localized.

## Buttons that still need cleanup attention

These are not missing CSS selectors, but they are still structurally inconsistent:

### Header/HUD utility buttons

- `#leaveBtn`
- `#copyRoomBtn`
- `#handHistoryToggle`
- `#bbToggleBtn`
- `#hintsToggle`
- `#chatToggle`

Issues:

- they rely on many repeated `btn btn-tiny btn-dim` combinations
- they behave like one toolbar, but are not documented as one toolbar system
- icon-only and text buttons share the same primitive without a dedicated utility-button layer

### Admin roster action buttons

- `.admin-player-action-btn`
- `.admin-kick-btn`

Issues:

- they are styled outside the shared `.btn` system
- there are multiple repeated override blocks in `static/styles.css`
- they currently depend on several late `!important` patches

### History/review action buttons

- `.hand-history-review-btn`
- `.history-review-close-btn`
- `.folded-reveal-btn`

Issues:

- these are effectively their own sub-system
- styling lives near the feature, which is good
- naming and structure should be kept grouped when files are split

## Real module boundaries already visible in `static/app.js`

The current function layout already suggests a safe modular split.

### 1. `static/js/core/format.js`

Move pure display helpers:

- `esc`
- card parsing/sorting helpers
- chip formatting helpers
- action text formatting

Reason:

- these functions are mostly pure
- low-risk first extraction

### 2. `static/js/core/storage.js`

Move browser persistence helpers:

- `safeGetItem`
- `safeSetItem`
- saved player name helpers
- hotkey/SFX/local toggle persistence helpers

### 3. `static/js/net/socket.js`

Move transport and room fetch behavior:

- `connect`
- `send`
- `fetchRooms`
- reconnect helpers

### 4. `static/js/ui/lobby.js`

Move lobby-only UI:

- `renderRoomsList`
- `createRoom`
- `joinRoom`
- `reconnectLast`
- connect-screen controls

### 5. `static/js/ui/actions.js`

Move betting/action-console behavior:

- `action`
- auto-check-fold helpers
- hotkey helpers
- `bettingActionModel`
- `syncBettingControls`
- `setActionButtonState`

### 6. `static/js/ui/table.js`

Move live table rendering:

- `renderCommunity`
- `renderYourHand`
- player-seat rendering
- bet marker rendering
- animation suppression helpers

### 7. `static/js/ui/history.js`

Move history and review behavior:

- hand history list rendering
- detail rendering
- review open/close
- `ensureHistoryReviewCloseButton`
- folded/uncontested reveal action rendering

### 8. `static/js/ui/admin.js`

Move admin dock rendering:

- `adminPlayerStatusLabels`
- `renderAdminPlayerList`
- admin kick button binding

## Recommended split order

Do not split everything at once.

Safe order:

1. Extract pure helpers first.
2. Extract history/review UI second.
3. Extract admin panel rendering third.
4. Extract action-console logic fourth.
5. Leave websocket and top-level `renderState()` orchestration for last.

That order keeps global-state churn low while creating real file boundaries around the least risky UI surfaces.

## CSS modularization direction

The CSS file is also carrying too many late feature patches.

Recommended structure:

- `static/css/base.css`
- `static/css/buttons.css`
- `static/css/table.css`
- `static/css/action-bar.css`
- `static/css/history.css`
- `static/css/chat.css`
- `static/css/admin.css`
- `static/css/responsive.css`

Practical rule:

- shared button primitives belong in `buttons.css`
- feature-local button layout belongs with the feature stylesheet
- avoid `!important` except for deliberate override layers during migration

## Recommendation

Yes, this can be modularized safely.

The correct path is:

1. keep the UI behavior stable
2. close missing CSS hooks first
3. add static tests for button-class coverage
4. split one UI surface at a time with documentation updated alongside the code

The next safe extraction target should be hand history / history review, because it already behaves like a self-contained UI feature.
