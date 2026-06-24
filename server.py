from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from poker.game import PokerServer

# ─── Timestamped logging setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("poker")


STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Cute Poker Modular Starter")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

server = PokerServer()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/rooms")
def api_rooms():
    """REST endpoint for listing active rooms."""
    rooms_list = []
    for room in server.rooms.values():
        connected = len([p for p in room.players.values() if p.connected])
        if connected > 0:
            rooms_list.append({
                "room_id": room.room_id,
                "players": len(room.players),
                "connected": connected,
                "max": 8,
                "phase": room.phase,
            })
    return {"rooms": rooms_list}


async def send(ws: WebSocket, event: str, payload: dict):
    await ws.send_text(json.dumps({"event": event, "payload": payload}))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    current_room_id: Optional[str] = None
    current_player_token: Optional[str] = None

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")
            payload = msg.get("payload", {})

            logger.info(f"[WS] event={event} room_id={payload.get('room_id','')} token={payload.get('token','')[:8]}...")

            result = await server.handle(ws, event, payload)

            if result.room_id:
                current_room_id = result.room_id
            if result.player_token:
                current_player_token = result.player_token

            # If the player left, clear tracking so disconnect doesn't double-process
            if event == "leave":
                current_room_id = None
                current_player_token = None

    except WebSocketDisconnect:
        pass
    finally:
        if current_room_id and current_player_token:
            await server.disconnect(current_room_id, current_player_token)


if __name__ == "__main__":
    logger.info("Cute Poker Modular Starter")
    logger.info("Open locally: http://127.0.0.1:8000")
    logger.info("LAN play: http://YOUR_LOCAL_IP:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
