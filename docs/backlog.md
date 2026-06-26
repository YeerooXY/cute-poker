# Cute Poker Backlog
- Rework betting buttons for low-stack/all-in edge cases: disable or relabel impossible half-pot/pot/raise options and make only valid actions available.
- Fix chat panel/showdown cinema interaction: chat currently feels broken/awkward when opened during the lights-out result view; decide whether it should sit above the cinema layer, collapse, or be intentionally muted.
- Audit grayed-out controls during showdown cinema: bottom/admin/chat buttons should either remain clearly usable or be intentionally hidden/muted, not look accidentally disabled.
- Add backend betting legality tests for low-stack call/all-in/min-raise edge cases; UI disables invalid controls, but server remains the source of truth.
