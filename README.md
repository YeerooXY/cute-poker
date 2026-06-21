# Cute Poker

A free, browser-based Texas Hold'em poker game designed for private games with friends. Create a room, share the code, and play — no accounts, no downloads, no fuss. Cute Poker runs entirely in your browser with a lightweight Python server handling game logic, secure card dealing, and real-time communication over WebSockets.

![Screenshot](screenshot.png)

## Features

- **Advanced AI Bots** — Add bots with varied difficulty levels (medium, hard, expert) that use advanced decision-making strategies
- **Real-time Multiplayer** — Play with friends over WebSocket connections with instant state updates
- **Auto-Deal** — Toggle automatic dealing after showdown so the action never stops
- **Equity Calculator** — Monte Carlo hand strength estimation for AI decision-making
- **Secure Card Dealing** — Cryptographic shuffling with `secrets.randbelow` ensures fair play
- **Private Rooms** — Create and join rooms with simple share codes
- **Reconnection Support** — Automatic reconnection with exponential backoff if your connection drops
- **No Setup Required for Players** — Just open a URL in any modern browser
- **Room Chat** — In-game chat with bot speech bubbles
- **Full Betting Rounds** — Fold, check, call, bet, and raise across preflop, flop, turn, and river
- **Casino-Style Chip Visuals** — Denomination-based chip stacks (1, 5, 25, 100, 500, 1000) with distinct colors matching real casino chips
- **BB Display Mode** — Toggle between raw chip values and Big Blind relative units across all displays
- **Card Animations** — Smooth fold animations (cards fly to muck) and staggered deal animations from a central deck
- **Full Position Labels** — See proper poker positions (UTG, MP, CO, BTN, SB, BB) color-coded by position group
- **Spectator Mode** — Watch games with a non-intrusive results sidebar instead of full-screen overlays
- **Dramatic Showdown** — All-in runouts reveal community cards one-at-a-time with suspenseful timing and winner glow effects
- **Accessibility** — All animations respect `prefers-reduced-motion` for users who need reduced motion

## Setup & Installation

### Prerequisites

- Python 3.11 or higher

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Server

```bash
python server.py
```

The server starts on `http://127.0.0.1:8000` by default.

### Play over LAN

Friends on the same network can connect using your local IP:

```
http://YOUR_LOCAL_IP:8000
```

### Play over the Internet

For remote play, use any tunneling solution:

- Cloudflare Tunnel
- ngrok
- playit.gg
- Router port forwarding
- A VPS deployment

## How to Play

### Creating a Room

1. Open the game in your browser
2. Enter your display name
3. Click **Create Room** to start a new table
4. Share the room code with your friends

### Joining a Room

1. Open the game in your browser
2. Enter your display name
3. Enter the room code shared by the host
4. Click **Join Room**

### Gameplay Flow

1. **Pre-flop** — Each player receives two private cards (dealt with a staggered animation from the dealer position). A round of betting begins with the player left of the big blind.
2. **Flop** — Three community cards are dealt face-up. Another betting round follows.
3. **Turn** — A fourth community card is dealt. Betting round.
4. **River** — A fifth and final community card is dealt. Final betting round.
5. **Showdown** — Remaining players reveal their hands. If it's an all-in runout, community cards are revealed dramatically one-at-a-time. The best five-card hand wins the pot with a winner glow effect.

Players can **fold**, **check**, **call**, **bet**, or **raise** during each betting round. When a player folds, their cards animate toward the center of the table. The room admin can add AI bots to fill empty seats and deal new hands.

### Table Display

- **Position labels** are shown on each seat during a hand: BTN (green), CO (green), MP (yellow), UTG (red), SB (blue), BB (blue). These update automatically based on player count (2–8 players supported).
- **Chip stacks** next to each player's bet show casino-style denominations — white (1), red (5), green (25), black (100), purple (500), orange (1000).
- **BB mode** can be toggled to show all monetary values relative to the big blind (e.g., "2.5 BB" instead of "50 chips"). This applies to stacks, pots, bets, action buttons, and results.

### Spectating

If you join as a spectator (or switch to spectate mode), you'll see:
- All players' hole cards and hand strength data during postflop play
- A compact results sidebar on showdown instead of the full-screen winner overlay
- Net chip changes for each player (green for winners, red for losers)

## Tech Stack

- **Python** — Server-side game logic, state management, and property-based testing with Hypothesis
- **FastAPI** — Async web framework and WebSocket handling
- **WebSockets** — Real-time bidirectional communication between server and clients
- **Vanilla JavaScript** — Client-side UI with CSS animations, no framework dependencies
- **CSS Custom Properties & Keyframes** — Card animations (fold, deal, showdown flip, winner glow)

## Credits

### Authors

- Cute Poker contributors

### Third-Party Resources

- [FastAPI](https://fastapi.tiangolo.com/) — Modern Python web framework
- [Uvicorn](https://www.uvicorn.org/) — ASGI server implementation
- Card evaluation logic inspired by common poker hand ranking algorithms
