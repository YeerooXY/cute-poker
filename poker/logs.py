"""Game log persistence for post-game analysis."""

import json
import os
from datetime import datetime, timezone
from typing import Any


LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


def save_hand_log(room: Any) -> None:
    """
    Save a structured log entry for the completed hand.

    Captures: hand number, players, cards, pot, and winners.
    Writes to logs/{room_id}_hand_{hand_number}.json
    """
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)

        # Build player data
        players_data = []
        for p in room.seated_players():
            player_entry = {
                "name": p.name,
                "seat": p.seat,
                "hole_cards": p.cards if p.cards else [],
                "stack_after": p.stack,
                "total_invested": p.total_invested,
                "folded": p.folded,
                "all_in": p.all_in,
            }
            players_data.append(player_entry)

        # Build community cards breakdown
        community = room.community if room.community else []
        community_data = {
            "flop": community[:3] if len(community) >= 3 else [],
            "turn": [community[3]] if len(community) >= 4 else [],
            "river": [community[4]] if len(community) >= 5 else [],
        }

        # Build winners data
        winners_data = []
        for w in room.winners:
            winners_data.append({
                "name": w.name,
                "amount": w.amount,
                "reason": w.reason,
                "hand_name": w.hand_name,
            })

        log_entry = {
            "hand_number": room.hands_played,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "room_id": room.room_id,
            "players": players_data,
            "community_cards": community_data,
            "pot": room.pot,
            "winners": winners_data,
        }

        filename = f"{room.room_id}_hand_{room.hands_played}.json"
        filepath = os.path.join(LOGS_DIR, filename)

        with open(filepath, "w") as f:
            json.dump(log_entry, f, indent=2)

    except Exception as e:
        # Log saving should never crash the game
        print(f"[LOG] Failed to save hand log: {e}")
