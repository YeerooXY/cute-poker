# Cute Poker Backlog
- Rework betting buttons for low-stack/all-in edge cases: disable or relabel impossible half-pot/pot/raise options and make only valid actions available.
- Fix chat panel/showdown cinema interaction: chat currently feels broken/awkward when opened during the lights-out result view; decide whether it should sit above the cinema layer, collapse, or be intentionally muted.
- Audit grayed-out controls during showdown cinema: bottom/admin/chat buttons should either remain clearly usable or be intentionally hidden/muted, not look accidentally disabled.
- Add backend betting legality tests for low-stack call/all-in/min-raise edge cases; UI disables invalid controls, but server remains the source of truth.
- Redesign post-hand reveal flow as one shared result screen: board on top, winner first, every player row shown with hidden cards by default, owner-only reveal controls.
- Add a true showdown-to-result transition later: tray/board appears first, then result stage expands/grows below it without duplicating cards.

## Betting / Game correctness
- Add backend regression test proving over-shoving against a shorter heads-up opponent does not drain uncontested extra chips.
- Audit low-stack betting UI: Call/Call All-In/Raise/All-In should stay clear when stacks are uneven.
- Keep server-side betting legality as source of truth even when UI disables invalid controls.

## Showdown / Result screen
- Keep folded/mucked cards hidden by default; only reveal cards when the owning player explicitly chooses to show them.
- Improve no-board fold-win wording: show “No board dealt” instead of “Waiting for board…” when the hand ends pre-board.
- Sort displayed hole cards high-to-low where appropriate, while keeping board cards in dealt order.
- Sort best-five result cards by made-hand grouping where possible.

## Reveal / Social features
- Add partial reveal options for uncontested winners: Show left, Show right, Show both, or Muck.
- Add optional folded-player reveal controls after the hand, respecting room settings and card privacy.
- Add rabbit hunting after uncontested wins; clearly label that rabbit board does not affect the result or pot.
- Add playful social prompts such as poking a player to show cards.
- Add bot reveal responses and light personality/flavor text without exposing hidden cards unfairly.

## Layout / UX cleanup
- Move admin/debug controls out of the right-edge floating stack; chat/sidebar can shadow them, so use a top bar, admin drawer, or room settings panel instead.
- Fix chat panel/showdown cinema interaction: chat currently feels awkward when opened during the lights-out result view.
- Audit grayed-out controls during showdown cinema: buttons should either remain clearly usable or be intentionally hidden/muted.
- Keep the floating showdown tray, but continue tuning spacing so it does not fight the result panel on small screens.
- Later, support viewer-relative seating so every player sees themselves at the bottom.

## History / Replay
- Add past hand history view with the ability to reopen a completed hand result.
- Add replay/share result card later, possibly suitable for Discord or screenshot sharing.

## Architecture / Tooling
- Split static/app.js into smaller modules once the showdown/result flow stabilizes.
- Candidate modules: cards.js, actionLog.js, postHandPanel.js, showdownTray.js, players.js, main.js.
- Keep temporary patch scripts, generated logs, timing reports, and visual artifacts out of commits.
- Revisit server port helper patch only if port killing becomes opt-in with --kill-port, not default.
