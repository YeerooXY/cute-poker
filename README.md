# Cute Poker Modular Starter

A free, tiny, browser-based Texas Hold'em starter for private games with friends.

This version adds:
- Modular poker logic
- 4-seat rooms
- Server-side secure shuffling
- Chips and simple betting
- Fold / check / call / bet / raise
- Flop / turn / river / showdown flow
- Best-hand evaluation from 7 cards
- Winner payout
- Reconnect token stored in the browser
- Simple room chat

It is still intentionally lightweight:
- No accounts
- No database
- No production anti-cheat system
- No real-money support
- Side pots/all-in edge cases are simplified

Good for learning and friendly private games.

## Run locally

Install Python 3.11+.

```bash
pip install -r requirements.txt
python server.py
```

Open:

```text
http://127.0.0.1:8000
```

## Play over LAN

The host runs:

```bash
python server.py
```

Friends on the same Wi-Fi open:

```text
http://HOST_LOCAL_IP:8000
```

For example:

```text
http://192.168.1.50:8000
```

## Play over the internet

Use one of these:
- Router port forwarding
- Cloudflare Tunnel
- ngrok
- playit.gg
- A cheap VPS

The app is free; tunnel/hosting services may have their own limits or pricing.

## Build a Windows EXE

From the project folder:

```bash
pip install pyinstaller
pyinstaller --onefile --add-data "static;static" server.py
```

The file will be created at:

```text
dist/server.exe
```

Run `server.exe`, then open the displayed address in a browser.

On Linux/macOS, the `--add-data` separator is usually `:` instead of `;`:

```bash
pyinstaller --onefile --add-data "static:static" server.py
```

## Notes for fairness

The room ID is not used for randomness.

The server shuffles using:

```python
secrets.randbelow()
```

with Fisher-Yates shuffling.

Players only receive their own private cards. The full deck remains server-side.

## Next good upgrades

- Proper side pots
- Persistent users and passwords
- Spectator mode
- Sound effects
- Better mobile UI
- Hand history export
- Dockerfile
- HTTPS deployment guide
