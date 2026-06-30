# Desktop Readiness Plan

Last updated: 2026-06-30

## Goal

Keep the current browser game working while preparing the client for a later desktop app / exe build.

This project should not fork into two frontends.

The target shape is:

- one portable frontend codebase
- one multiplayer/backend contract
- multiple shells later:
  - browser
  - desktop app

## Current constraints

- The live client is still centered in `static/app.js`.
- The app is plain browser JavaScript, not a bundled SPA.
- We do not want a rewrite.
- We do not want to destabilize the current poker table UX.

## Recommended shell direction

If the project later becomes a desktop app, `Tauri` is the leading candidate.

Why:

- lighter than Electron
- keeps the current web UI model
- good fit for a local shell around an existing frontend
- better install footprint for a social game / party app

Electron remains viable if:

- deeper desktop integrations matter more than footprint
- a Chromium-bundled environment is preferred for predictability

Do not choose a shell yet by habit alone. The frontend boundaries should be cleaned first.

## Prepare now

These changes help both browser and future desktop builds:

- separate frontend responsibilities by file
- reduce accidental global coupling
- make shared helpers explicit
- expose stable frontend runtime seams
- keep UI state access centralized
- document browser-only assumptions

## Do later

These should wait until the frontend seams are cleaner:

- shell selection and scaffolding
- auto-update strategy
- packaging/install flow
- native file dialogs
- desktop-only persistence
- tray/window behavior

## Runtime seam introduced now

The frontend now has a shared runtime registry on `window.CutePoker.frontend`.

Purpose:

- expose explicit accessors instead of hidden cross-file state assumptions
- allow feature modules to register against one shared runtime
- support gradual extraction from `static/app.js`

This is not the final architecture. It is a safe migration seam.

## Planned modular split

Near-term modules:

- `core/format`
- `core/storage`
- `net/socket`
- `ui/lobby`
- `ui/actions`
- `ui/table`
- `ui/history`
- `ui/admin`

Recommended first extraction:

- `ui/history`

Reason:

- it is already one of the cleanest feature slices
- it has a clear DOM surface
- it has good static-test coverage
- it is low risk relative to websocket or turn/action logic

## Desktop-safe engineering rules

- keep feature modules free of direct top-level side effects where practical
- avoid hidden dependencies on script order
- centralize shell-sensitive behaviors
- keep networking and rendering separable
- prefer explicit runtime registration over implicit globals

## Next implementation step

Move history/review behavior behind the shared frontend runtime seam first, then extract it into a separate browser-loaded file without changing user-facing behavior.
