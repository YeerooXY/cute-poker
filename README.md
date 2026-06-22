# Cute Poker

A free, browser-based Texas Hold'em poker game designed for private games with friends. Create a room, share the code, and play — no accounts, no downloads, no fuss. Cute Poker runs entirely in your browser with a lightweight Python server handling game logic, secure card dealing, and real-time communication over WebSockets.

![Screenshot](screenshot.png)

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
- **Casino Chip Visuals** — Round denomination-based chips (white/red/green/black/purple/gold) in multi-stack layout
- **Peek-to-Reveal Cards** — Cards dealt face-down, click to peek (toggle on/off)
- **Speech Bubbles** — Chat messages appear as floating bubbles above player seats
- **BB Display Mode** — Toggle between chip values and Big Blind units
- **Position Labels** — BTN, CO, MP, UTG, SB, BB with color coding
- **Blind Level HUD** — Shows current blinds, ante, and countdown to next level
- **Dramatic Showdown** — All-in runouts with card-by-card reveal and winner glow
- **Auto-Deal** — 5-second countdown after showdown, dismisses overlays cleanly
- **Card Animations** — Deal from center, fold to muck, community card reveals
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

### Install Dependencies

```bash
pip install -r requirements.txt
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

When creating a room, you can configure:

| Setting | Default | Description |
|---------|---------|-------------|
| Blind increase every | 0 (disabled) | Hands between blind level increases |
| Ante | 0 (disabled) | Per-player ante amount |
| Ante mode | Classic | Classic (all post) or BBA (dealer posts 1 BB) |
| Auto-scale ante | Off | Ante auto-adjusts to ~10% BB on blind increase |

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
- 3 random baselines: Random50, RandomSafe, RandomHumanish

Typical results (Expert TAG):
- vs RandomHumanish: +130 BB/100
- vs Easy: +30–100 BB/100
- vs Mixed 4P field: +50–200 BB/100
- vs Hard (same style): ~0 BB/100 (same personality, noise difference only)

## Architecture

```
poker/
  game.py              # PokerServer: rooms, hands, betting, showdown
  models.py            # Player, Room, Winner dataclasses
  bot.py               # Bot decision dispatch, preflop ranges
  odds.py              # Equity calculator (hybrid: lookup/exact/MC)
  evaluator.py         # 7-card hand evaluator
  cards.py             # Deck, display formatting
  ranges.py            # Preflop action ranges
  terminology.py       # Hand classification (made hand, draws, nuts)
  bot_ai/
    __init__.py        # Advanced AI pipeline orchestrator
    action_scorer.py   # EV-based scoring + modifiers
    bet_sizer.py       # Street-aware bet sizing
    bluff_calculator.py
    board_analyzer.py
    difficulty_controller.py
    dynamic_adjuster.py
    models.py          # AI dataclasses
    opponent_model.py
    personality_engine.py
    preflop_charts.py
    range_tracker.py
static/
  index.html           # Single-page game UI
  app.js               # Client logic, animations, state rendering
  styles.css           # Dark theme, chip visuals, responsive layout
simulate_bots.py       # Headless benchmark runner
tests/                 # 297 tests (property-based + integration)
```

## Tech Stack

- **Python** — Server-side game logic and AI
- **FastAPI** — Async web framework + WebSocket handling
- **Hypothesis** — Property-based testing
- **Vanilla JS** — Client UI, no framework dependencies
- **CSS** — Custom properties, keyframes, responsive design

## Credits

- Cute Poker contributors
- [FastAPI](https://fastapi.tiangolo.com/) — Python web framework
- [Uvicorn](https://www.uvicorn.org/) — ASGI server
