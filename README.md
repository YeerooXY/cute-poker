# Cute Poker

A free, browser-based Texas Hold'em poker game designed for private games with friends. Create a room, share the code, and play — no accounts, no downloads, no fuss. Cute Poker runs entirely in your browser with a lightweight Python server handling game logic, secure card dealing, and real-time communication over WebSockets.

## Features

### Game Engine
- **Full Texas Hold'em** — Preflop, flop, turn, river, showdown with side pots
- **Tournament Blinds** — 13-level blind progression (~1.5× per level), configurable increase interval
- **Antes** — Classic (everyone posts) or Big Blind Ante (dealer posts 1 BB)
- **Auto-scaling Ante** — Ante automatically adjusts to ~10% of BB when blinds increase
- **Zero-sum Chip Accounting** — Verified side-pot logic, no chip leaks

### AI Bots
- **4 Difficulty Levels** — Easy, Medium, Hard, Expert with distinct playstyles
- **EV-Based Decision Engine** — Expected value scoring with fold equity, pot odds, and semi-bluff EV
- **Personality System** — TAG, LAG, Calling Station, Maniac styles with tunable parameters
- **Range-Aware Equity** — Bots estimate opponent ranges and compute equity vs weighted hand distributions
- **Modifier Pipeline** — Personality, exploit, and board texture modifiers on top of pure EV
- **Difficulty Scaling** — Exploitability noise: Easy=0.40, Medium=0.20, Hard=0.15, Expert=0.03

### UI/UX
- **Casino Chip Visuals** — Round denomination-based chips in multi-stack layout
- **Peek-to-Reveal Cards** — Cards dealt face-down, click to peek (toggle on/off)
- **Action Log Panel** — Collapsible hand history with street separators, bet/raise distinction, and showdown details
- **Rich Showdown Display** — Best 5-card hand shown per player, kicker explanations, and winner announcement
- **Speech Bubbles** — Chat messages appear as floating bubbles above player seats
- **BB Display Mode** — Toggle between chip values and Big Blind units
- **Position Labels** — BTN, CO, MP, UTG, SB, BB with color coding
- **Blind Level HUD** — Shows current blinds, ante, and countdown to next level
- **Dramatic Showdown** — All-in runouts with card-by-card reveal and winner glow
- **Auto-Deal** — 5-second countdown after showdown, dismisses overlays cleanly
- **Spectator Mode** — Watch with equity overlays and compact results sidebar
- **Bot Trash Talk** — Personality-driven chat messages on bluffs, wins, and losses

### Multiplayer
- **Real-time WebSocket** — Instant state sync across all connected clients
- **Private Rooms** — Create/join with simple share codes
- **Reconnection** — Automatic with exponential backoff
- **Room Cleanup** — Abandoned rooms (only bots left) auto-destroy
- **Up to 8 Players** — Full ring support

## Setup & Installation

### Prerequisites

- Python 3.11+
- Node.js (for running frontend tests only)

### Install Dependencies

```bash
pip install -r requirements.txt
npm install   # for frontend test dependencies (fast-check, jsdom)
```

### Run the Server

```bash
python server.py
```

The server starts on `http://127.0.0.1:8000`.

### Play over LAN

Friends on the same network can connect using your local IP:
```
http://YOUR_LOCAL_IP:8000
```

### Play over the Internet

Use any tunneling solution: Cloudflare Tunnel, ngrok, playit.gg, or port forwarding.

## Room Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Blind increase every | 0 (disabled) | Hands between blind level increases |
| Ante | 0 (disabled) | Per-player ante amount |
| Ante mode | Classic | Classic (all post) or BBA (dealer posts 1 BB) |
| Auto-scale ante | Off | Ante auto-adjusts to ~10% BB on blind increase |

## Architecture

```
cute_poker_modular/
├── server.py                  # Entry point: FastAPI + WebSocket server
├── simulate_bots.py           # Headless bot-vs-bot benchmark runner
├── start.bat                  # Windows quick-start script
├── requirements.txt           # Python deps (FastAPI, Uvicorn)
├── package.json               # Node deps for frontend tests (fast-check, jsdom)
├── pytest.ini                 # Pytest configuration
│
├── poker/                     # Server-side game engine & AI
│   ├── game.py                # PokerServer: rooms, hands, betting, showdown, bot loop
│   ├── models.py              # Dataclasses: Player, Room, Winner, ChatMessage
│   ├── evaluator.py           # 7-card hand evaluator + hand description generator
│   ├── bot.py                 # Bot decision dispatch, preflop open/call/3bet ranges
│   ├── odds.py                # Equity calculator (hybrid: lookup/exact/Monte Carlo)
│   ├── cards.py               # Deck creation, display formatting (unicode suits)
│   ├── ranges.py              # Preflop action ranges (positional open, call, 3bet)
│   ├── terminology.py         # Hand classification (made hand, draws, nuts, board texture)
│   ├── trash_talk.py          # Bot chat message generation
│   ├── logs.py                # Hand log persistence (JSON per hand)
│   └── bot_ai/                # Advanced AI decision pipeline
│       ├── __init__.py        # Pipeline orchestrator (bot_decide entry point)
│       ├── action_scorer.py   # EV-based action scoring with modifier pipeline
│       ├── bet_sizer.py       # Street-aware bet sizing (pot fractions, all-in thresholds)
│       ├── bluff_calculator.py# Semi-bluff EV, fold equity estimation
│       ├── board_analyzer.py  # Board texture: wetness, connectivity, flush potential
│       ├── difficulty_controller.py # Noise injection by difficulty level
│       ├── dynamic_adjuster.py# In-session style adaptation
│       ├── exploit_metrics.py # Opponent tendency tracking (VPIP, PFR, AF, fold-to-cbet)
│       ├── models.py          # AI-specific dataclasses
│       ├── opponent_model.py  # Range estimation from observed actions
│       ├── personality_engine.py # TAG/LAG/Station/Maniac personality modifiers
│       ├── preflop_charts.py  # GTO-inspired preflop decision charts
│       ├── range_tracker.py   # Combo-level range tracking with Bayesian updates
│       └── sanity_gates.py    # Final action validation (prevent -EV blunders)
│
├── static/                    # Client-side (served as static files)
│   ├── index.html             # Single-page game UI
│   ├── app.js                 # Client logic: state rendering, animations, action log
│   └── styles.css             # Dark theme, chip visuals, responsive layout
│
└── tests/                     # Test suite (~42 files, property-based + unit + integration)
    ├── test_ui_log_polish.py          # Showdown display, all-in wording, kicker descriptions
    ├── test_action_log_unit.py        # Action log schema, sanitization, blind entries
    ├── test_action_log_properties.py  # PBT: broadcast schema invariants
    ├── test_action_log_frontend.js    # Frontend formatActionEntry + renderActionLog
    ├── test_action_log_preservation.js# PBT: non-bug-condition behavior preserved
    ├── test_bug_condition_exploration.py       # Backend bug condition confirmation
    ├── test_bug_condition_exploration_frontend.js # Frontend bug condition confirmation
    ├── test_bot_ai_properties.py      # PBT: AI decision invariants
    ├── test_ev_scoring_properties.py  # PBT: EV calculation correctness
    ├── test_allin_invariants.py       # All-in accounting, side pot correctness
    ├── test_gameplay_preservation.py  # Regression suite for game flow
    └── ...                            # (40+ total test files)
```

## Module Reference

### `server.py` — Entry Point

FastAPI application with a single WebSocket endpoint (`/ws`). Serves the static frontend and delegates all game logic to `PokerServer`. Includes timestamped logging.

### `poker/game.py` — Game Engine

The core module. `PokerServer` manages:
- **Room lifecycle** — create, join, leave, reconnect, cleanup
- **Hand flow** — deal, blinds/antes, betting rounds, street advancement
- **Player actions** — fold, check/call, bet/raise with validation
- **Bot loop** — Async bot decision execution with timeout/fallback
- **Showdown** — Hand evaluation, side pot calculation, winner determination
- **Broadcasting** — Real-time state sync to all clients via `visible_state()`
- **Action log** — Records every action with metadata (phase, amount, is_all_in)

### `poker/models.py` — Data Models

Dataclasses for the core domain:
- `Player` — stack, cards, state flags (folded, all_in, sitting_out), showdown results
- `Room` — game state, community cards, pot, blinds, action log, winners
- `Winner` — player info, amount won, hand name/detail, best cards
- `ChatMessage` — player chat with timestamp

### `poker/evaluator.py` — Hand Evaluation

- `evaluate_5(cards)` — Score a 5-card hand, returns `((category, kickers), name)`
- `evaluate_7(cards)` — Find best 5-card combination from 7 cards
- `describe_hand(score, name)` — Human-readable detail with kicker explanation
  - Examples: "Flush, Ace-high", "Two pair, Kings and Tens, Ace kicker", "Full house, Queens full of Sevens"

Categories (0–8): High card, One pair, Two pair, Three of a kind, Straight, Flush, Full house, Four of a kind, Straight flush/Royal flush.

### `poker/bot.py` — Bot Decision Dispatch

Entry point for bot decisions. Routes to the advanced AI pipeline (`bot_ai/`) for Hard/Expert bots, or uses simpler heuristics for Easy/Medium. Handles preflop range lookups and fallback logic.

### `poker/bot_ai/` — Advanced AI Pipeline

A multi-stage decision engine:

1. **Board Analysis** (`board_analyzer.py`) — Texture scoring (wetness, straightness, flush potential)
2. **Range Tracking** (`range_tracker.py`) — Bayesian combo-level opponent range estimation
3. **Equity Calculation** — Monte Carlo equity vs estimated opponent range
4. **Action Scoring** (`action_scorer.py`) — EV for each action (fold/check/call/bet/raise)
5. **Modifier Pipeline** — Personality, exploit, and texture-based adjustments
6. **Bet Sizing** (`bet_sizer.py`) — Pot-fraction sizing tuned per street and texture
7. **Sanity Gates** (`sanity_gates.py`) — Final validation preventing catastrophic errors
8. **Difficulty Control** (`difficulty_controller.py`) — Noise injection for easier bots

### `poker/odds.py` — Equity Calculator

Hybrid equity computation:
- **Preflop lookup** — Pre-computed matchup tables for speed
- **Exact enumeration** — Small deck remaining cases
- **Monte Carlo** — Random sampling for complex multi-way pots

### `poker/cards.py` — Deck & Display

Standard 52-card deck creation and unicode display formatting (e.g., `A♠`, `K♥`, `10♦`).

### `poker/ranges.py` — Preflop Ranges

Position-aware opening, calling, and 3-betting ranges. Used by both the simple bot logic and the advanced AI preflop charts.

### `poker/terminology.py` — Hand Classification

Classifies board texture and made hands into categories useful for the AI pipeline: draws, made hands, nut potential, board danger levels.

### `static/app.js` — Client Application

Single-file vanilla JavaScript client handling:
- **WebSocket connection** — Auto-reconnect with exponential backoff
- **State rendering** — Player seats, community cards, pot, chips, phase badges
- **Action log** — Collapsible panel with street separators, bet/raise distinction, showdown details
- **Showdown display** — Best 5-card hands per player, kicker descriptions, winner announcement
- **Action bar** — Fold/Check-Call/Raise buttons with pot-fraction shortcuts, hidden at showdown
- **Animations** — Card deals, chip moves, winner glow, speech bubbles
- **Persistence** — Name, panel state in localStorage

### `static/styles.css` — Visual Design

Dark casino theme with CSS custom properties, chip denomination colors, card styling, responsive layout, and keyframe animations.

## Testing

### Run Python Tests

```bash
python -m pytest tests/ -v
```

### Run Frontend Tests

```bash
node tests/test_action_log_preservation.js
node tests/test_action_log_frontend.js
node tests/test_bug_condition_exploration_frontend.js
```

### Test Categories

| Category | Description |
|----------|-------------|
| `test_*_properties.py` | Property-based tests (Hypothesis) — generate random inputs, verify invariants |
| `test_*_unit.py` | Unit tests — targeted function/method validation |
| `test_*_preservation.py` | Regression tests — ensure correct behavior isn't broken by changes |
| `test_*_exploration.py` | Bug condition tests — confirm bugs existed before fix |
| `test_*_frontend.js` | Frontend logic tests (fast-check) — formatters, renderers, separators |

## Bot Simulation Benchmark

Run headless bot-vs-bot simulations to validate bot strength:

```bash
$env:POKER_SIMULATION="1"  # Windows PowerShell
python simulate_bots.py
```

Features:
- Parallel execution via ProcessPoolExecutor
- Zero-sum chip accounting with assertions
- BB/100 as primary performance metric
- Multiple scenarios: HU, mixed tables, difficulty ladders

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Server | Python 3.11+ | Game logic, AI, WebSocket handling |
| Framework | FastAPI + Uvicorn | Async HTTP + WebSocket server |
| Client | Vanilla JS | No framework deps, single-file UI |
| Styling | CSS Custom Properties | Dark theme, animations, responsive |
| Testing (Python) | pytest + Hypothesis | Unit + property-based tests |
| Testing (JS) | fast-check + jsdom | Frontend property tests |

## License

ISC
