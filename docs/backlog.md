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


# Playful Poker / Boss Bot Mode — Design Notes

## Core Direction

The goal is not to build unbeatable poker bots. The goal is to build a poker game that feels alive, social, funny, and difficult in the right places.

Normal online poker is often too sterile: silent tables, solver-like play, little personality, and not much community interaction beyond winning or losing chips. This project can go in a more playful direction:

* normal poker table gameplay
* believable bots
* social table interaction
* optional voice chat
* sound effects
* funny bot/table reactions
* special PvE-style modes where human players face a powerful bot boss

The best bots should be genuinely hard to beat, but they should be hard in a visible, fair, and entertaining way. The player should feel challenged, not cheated.

---

## Design Principle: Difficult, Not Unfair

Hard bots should not cheat.

Avoid:

* seeing player hole cards
* knowing future board cards
* manipulating RNG
* secretly changing odds
* impossible reads

Use visible difficulty instead:

* larger starting stack
* better strategy stage
* lower randomness
* better pressure timing
* better bluff catching
* better adaptation to player tendencies
* public “boss phase” or “mood”

A player losing should feel:

> “Damn, the boss got stronger and punished us.”

Not:

> “This bot is cheating.”

---

## Boss Bot Mode

A special mode where players face a huge-stack AI opponent.

Example setup:

* 3–7 human players
* 1 Boss Bot
* Humans start with normal stacks, e.g. 1,000 chips
* Boss starts with 25x–50x player stack, e.g. 25,000–50,000 chips
* Goal: survive, cooperate-ish, exploit the boss, and eventually bring it down

The boss should start somewhat playful and imperfect, then become increasingly dangerous.

Example progression:

| Boss State                | Behavior                                    |
| ------------------------- | ------------------------------------------- |
| Stage 1: Sleepy Giant     | splashy, loose, funny mistakes              |
| Stage 2: Wakes Up         | calls less junk, pressures obvious weakness |
| Stage 3: Angry Boss       | stronger ranges, better postflop aggression |
| Stage 4: Final Table Mode | low randomness, more disciplined            |
| Stage 5: Final Form       | very strong, difficult to exploit           |

Difficulty can scale by:

* boss stack remaining
* hand number
* number of players remaining
* boss losing a large pot
* boss catching repeated bluffs
* blind level
* special table events

---

## Social / Semi-Co-op Table Dynamic

The best part of this idea is that poker remains competitive, but players also have a shared enemy.

This creates funny social situations:

* “Stop feeding the boss.”
* “Don’t isolate with trash, we need to survive.”
* “He’s targeting you because you bluffed him twice.”
* “Let him pay us off, don’t scare him out.”
* “We almost killed him and then Dave donated 4,000 chips with J3o.”

Players are not truly a team, because side pots and individual survival still matter. That tension is good. It makes the table feel like a party game mixed with poker.

---

## Possible Game Modes

### 1. Boss Stack Mode

One huge-stack bot sits at the table.

Goal:

* defeat the boss before blinds get too high
* or survive a fixed number of hands
* or reduce boss stack below a target

Good for:

* casual groups
* streamable moments
* “raid boss” feeling

---

### 2. Raid Poker

Humans share a table objective.

Example:

* Boss starts with 50,000 chips
* Players start with 1,000 each
* Boss must be defeated before Level 10 blinds
* If all humans bust, the boss wins

Optional scoring:

* total damage dealt to boss
* biggest hero call
* biggest boss donation
* most chips fed to boss
* final surviving player
* team victory / individual MVP

---

### 3. Nemesis Boss

The boss tracks simple player tendencies during the session.

Examples:

* player folds often to raises → boss pressures more
* player bluffs river too often → boss calls lighter
* player always limps weak hands → boss isolates
* player traps monsters → boss checks back more
* player overcalls → boss value bets harder

This does not need machine learning. Simple counters are enough:

* VPIP
* fold to raise
* river aggression
* showdown bluff count
* overcall frequency
* trap history
* all-in frequency

This would make the boss feel alive.

---

### 4. Personality Bosses

Different bosses can have different identities.

Examples:

#### The Whale King

Loose early, loves seeing flops, but becomes dangerous when wounded.

#### The Professor

Tight, analytical, adapts to repeated player behavior.

#### The Goblin

Chaotic, splashy, raises weird spots, but gets sharper over time.

#### The Banker

Pressures short stacks and punishes passive tables.

#### The Sheriff

Hates bluffers and calls suspicious river bets.

#### The Mirror

Learns the table style and slowly copies the players.

---

## Difficulty Philosophy

Normal table bots should be fun and beatable.

Boss bots should have difficulty tiers:

| Tier            | Purpose                             |
| --------------- | ----------------------------------- |
| Casual Boss     | funny, loose, easy for groups       |
| Standard Boss   | challenging but beatable            |
| Hard Boss       | requires discipline and cooperation |
| Nightmare Boss  | very difficult, low randomness      |
| Final Form Boss | intentionally brutal                |

The hardest bosses should feel genuinely scary. They should not be unbeatable, but beating them should feel like an event.

---

## Voice Chat

Voice chat would strongly support this direction.

Important features:

* room-based voice chat
* push-to-talk option
* mute self
* mute individual players
* volume sliders per player
* voice activity indicator around avatar
* host moderation controls
* quick “mute all except friends” option
* optional voice disabled rooms

Implementation direction:

* WebRTC for real-time voice
* start with small-room mesh voice if player count is low
* later use SFU/server relay if scaling matters
* keep voice optional, because not every table wants it

Voice chat should not be mandatory, but for party/boss mode it could be a major feature.

---

## Sound Effects

Sound effects are easier and should come before voice chat.

Needed sounds:

* card deal
* chip bet
* chip call
* raise
* all-in
* check
* fold
* pot pushed
* showdown reveal
* timer warning
* player joins/leaves
* boss enters table
* boss stage change
* boss loses big pot
* boss wins huge pot
* final boss phase

Sound controls:

* master volume
* SFX volume
* voice volume
* mute all
* reduced sounds mode

Sound should make actions feel satisfying but not annoying.

---

## Table Reactions / Emotes

Add lightweight social tools:

* emotes
* quick reactions
* “nice hand”
* “brutal”
* “boss fed”
* “suspicious call”
* “hero call”
* “donation”
* throwable table props later, maybe

These should be cosmetic/funny, not gameplay-impacting.

---

## Inspirations to Borrow

### From Social Poker Games

Useful ideas:

* friend tables
* gifts
* avatars
* casual lobby
* leaderboards
* events
* table identity

Apply to this project:

* private rooms with friends
* silly table themes
* player badges
* boss kill leaderboard
* “damage dealt to boss” stats
* weekly boss challenge

---

### From VR / Social Table Poker

Useful ideas:

* table presence
* props
* cosmetics
* visible reactions
* voice/social behavior

Apply to this project:

* voice chat
* avatar glow when speaking
* chip/card sounds
* reactions
* boss animation/stage effects
* table mood

---

### From Poker Adventure Games

Useful ideas:

* progression
* themed opponents
* unlocks
* campaign wrapper
* character bosses

Apply to this project:

* boss ladder
* different AI bosses
* unlockable table skins
* story-lite campaign
* “beat the boss table” milestones

---

### From Balatro-Like Poker Games

Useful ideas:

* boss phases
* modifiers
* antes/stages
* special challenges
* run-based progression

Apply to this project:

* boss blind-style events
* temporary rule modifiers
* table events every X hands
* escalating boss behavior
* optional challenge modes

Possible modifiers:

* boss gets more aggressive for 5 hands
* boss calls bluffs lighter
* boss protects blinds harder
* boss bounty doubles
* players get comeback bonus
* short stacks get one emergency rebuy
* boss enters final form below 20% stack

---

## MVP Feature Path

### Phase 1: Strong Casual Bot Table

* balanced bot logic
* difficulty levels
* good logs and tuning
* sound effects
* clean action history
* private rooms

### Phase 2: Social Layer

* emotes
* quick chat
* basic table reactions
* player badges
* spectator support
* optional voice chat

### Phase 3: Boss Bot Prototype

* one boss bot with huge stack
* visible boss stage
* difficulty increases over time
* boss sound effects
* boss result summary after game

### Phase 4: Boss Personalities

* Whale King
* Professor
* Goblin
* Banker
* Sheriff
* Mirror

### Phase 5: Raid / Party Poker

* shared boss objective
* boss leaderboard
* table achievements
* weekly challenge
* long-run stats

---

## Product Positioning

This should not be positioned as a gambling product or solver bot.

Better positioning:

> A social poker game with believable AI opponents and special boss-table modes, designed for friends who want poker to feel more like a party, a challenge, and a shared story.

Or:

> Poker as a social raid game: play normal Hold’em, or team up against a huge-stack AI boss that gets smarter as the table survives.

The strongest unique idea is:

> Social Poker PvE.

That is the gap worth exploring.


