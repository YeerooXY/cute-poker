from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


FORCED_ACTIONS = {"ante", "big_blind_ante", "small_blind", "big_blind"}
POSTFLOP_PHASES = {"flop", "turn", "river"}
RANK_ORDER = "23456789TJQKA"


def hand_no_from_path(path: Path) -> int:
    m = re.search(r"_hand_(\d+)\.json$", path.name)
    return int(m.group(1)) if m else -1


def room_id_from_path(path: Path) -> str:
    m = re.match(r"(.+)_hand_\d+\.json$", path.name)
    return m.group(1) if m else ""


def card_rank(card: str) -> str:
    return str(card or "")[0].upper()


def card_suit(card: str) -> str:
    return str(card or "")[-1].upper()


def hand_notation(cards: list[str] | None) -> str:
    if not cards or len(cards) != 2:
        return ""
    r1, r2 = card_rank(cards[0]), card_rank(cards[1])
    s1, s2 = card_suit(cards[0]), card_suit(cards[1])
    if r1 not in RANK_ORDER or r2 not in RANK_ORDER:
        return "".join(cards)
    if RANK_ORDER.index(r1) < RANK_ORDER.index(r2):
        r1, r2 = r2, r1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ("s" if s1 == s2 else "o")


def is_premium(notation: str) -> bool:
    return notation in {"AA", "KK", "QQ", "JJ", "AKs", "AKo", "AQs"}


def is_trash(notation: str) -> bool:
    if not notation:
        return False
    if len(notation) == 2 and notation[0] == notation[1]:
        return notation[0] in "234"
    if len(notation) == 3:
        hi = RANK_ORDER.index(notation[0])
        lo = RANK_ORDER.index(notation[1])
        gap = abs(hi - lo)
        # weak offsuit, non-connected, no broadway strength
        return notation.endswith("o") and hi <= RANK_ORDER.index("J") and gap >= 4
    return False


def load_logs(log_dir: Path, room: str | None, latest_room: bool) -> list[Path]:
    files = sorted(log_dir.glob("*_hand_*.json"), key=lambda p: (room_id_from_path(p), hand_no_from_path(p)))

    if room:
        files = [p for p in files if room_id_from_path(p) == room]
    elif latest_room and files:
        newest = max(files, key=lambda p: p.stat().st_mtime)
        newest_room = room_id_from_path(newest)
        files = [p for p in files if room_id_from_path(p) == newest_room]

    return sorted(files, key=hand_no_from_path)


def winner_summary(data: dict[str, Any]) -> str:
    winners = data.get("winners") or []
    parts = []
    for w in winners:
        name = w.get("name", "?")
        amount = w.get("amount", "?")
        reason = w.get("reason", "")
        hand = w.get("hand_name", "")
        label = hand or reason or "win"
        parts.append(f"{name}+{amount}({label})")
    return ", ".join(parts)


def community_count(data: dict[str, Any]) -> int:
    cc = data.get("community_cards") or {}
    total = 0
    for key in ("flop", "turn", "river"):
        v = cc.get(key) or []
        total += len(v)
    return total


def analyze_once(args: argparse.Namespace) -> dict[str, Any]:
    files = load_logs(Path(args.logs), args.room, args.latest_room)

    if args.limit:
        files = files[-args.limit:]

    agg = {
        "room_ids": Counter(),
        "hands": 0,
        "bot_decisions": 0,
        "preflop_decisions": 0,
        "postflop_decisions": 0,
        "actions_all": Counter(),
        "actions_preflop": Counter(),
        "actions_postflop": Counter(),
        "phases": Counter(),
        "decision_reasons": Counter(),
        "personality_styles": Counter(),
        "difficulties": Counter(),
        "to_call_buckets_preflop": Counter(),
        "position_preflop": Counter(),
        "per_bot": defaultdict(Counter),
        "actions_by_difficulty": defaultdict(Counter),
        "preflop_by_difficulty": defaultdict(Counter),
        "postflop_by_difficulty": defaultdict(Counter),
        "hands_with_postflop": 0,
        "hands_with_showdown": 0,
        "preflop_only_hands": 0,
        "preflop_allin_hands": 0,
        "big_pot_hands": 0,
        "huge_pot_hands": 0,
    }

    notable: list[dict[str, Any]] = []
    per_hand: list[dict[str, Any]] = []

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            notable.append({"file": path.name, "type": "bad_json", "error": str(exc)})
            continue

        hand_no = data.get("hand_number", hand_no_from_path(path))
        room_id = data.get("room_id", room_id_from_path(path))
        actions = data.get("actions") or []
        pot = int(data.get("pot") or 0)

        agg["room_ids"][room_id] += 1
        agg["hands"] += 1

        has_postflop = any(a.get("phase") in POSTFLOP_PHASES for a in actions)
        has_showdown = any("showdown" in str(w.get("reason", "")).lower() or "best hand" in str(w.get("reason", "")).lower()
                           for w in data.get("winners", []))
        preflop_allin = False

        if has_postflop:
            agg["hands_with_postflop"] += 1
        else:
            agg["preflop_only_hands"] += 1

        if has_showdown:
            agg["hands_with_showdown"] += 1

        if pot >= 1000:
            agg["big_pot_hands"] += 1
        if pot >= 2500:
            agg["huge_pot_hands"] += 1

        hand_counts = Counter()
        hand_reasons = Counter()
        hand_flags: list[str] = []

        for a in actions:
            action = a.get("action")
            phase = a.get("phase")
            is_bot = bool(a.get("is_bot"))

            if not is_bot or action in FORCED_ACTIONS:
                continue

            dbg = a.get("ai_debug") or {}
            name = a.get("player", "UNKNOWN")
            cards = a.get("hole_cards") or []
            notation = hand_notation(cards)
            reason = dbg.get("decision_reason") or "no_reason"
            style = dbg.get("personality_style") or dbg.get("style") or "unknown"
            difficulty = dbg.get("difficulty") or "unknown"
            to_call = int(a.get("to_call") or 0)
            current_bet = int(a.get("current_bet") or 0)
            committed = int(a.get("committed") or 0)
            amount = int(a.get("amount") or 0)
            is_all_in = bool(a.get("is_all_in"))

            agg["bot_decisions"] += 1
            agg["actions_all"][action] += 1
            agg["phases"][phase] += 1
            agg["decision_reasons"][reason] += 1
            agg["personality_styles"][style] += 1
            agg["difficulties"][difficulty] += 1
            agg["actions_by_difficulty"][difficulty][action] += 1
            agg["per_bot"][name][action] += 1
            agg["per_bot"][name][f"difficulty:{difficulty}"] += 1
            agg["per_bot"][name][f"{phase}_decisions"] += 1
            hand_counts[action] += 1
            hand_reasons[reason] += 1

            if phase == "preflop":
                agg["preflop_decisions"] += 1
                agg["actions_preflop"][action] += 1
                agg["preflop_by_difficulty"][difficulty][action] += 1
                pos = dbg.get("position") or "unknown"
                agg["position_preflop"][pos] += 1

                if to_call <= 0:
                    bucket = "0"
                elif to_call <= 10:
                    bucket = "<=10"
                elif to_call <= 30:
                    bucket = "11-30"
                elif to_call <= 100:
                    bucket = "31-100"
                else:
                    bucket = ">100"
                agg["to_call_buckets_preflop"][bucket] += 1

                if is_all_in:
                    preflop_allin = True

                if is_premium(notation) and action == "fold":
                    hand_flags.append(f"premium_fold:{name}:{notation}")
                    notable.append({
                        "hand": hand_no, "file": path.name, "type": "premium_fold",
                        "player": name, "cards": cards, "notation": notation,
                        "action": action, "to_call": to_call, "reason": reason,
                    })

                if is_trash(notation) and action == "check_call" and to_call > 30:
                    hand_flags.append(f"trash_large_call:{name}:{notation}:{to_call}")
                    notable.append({
                        "hand": hand_no, "file": path.name, "type": "trash_large_call",
                        "player": name, "cards": cards, "notation": notation,
                        "action": action, "to_call": to_call, "reason": reason,
                    })

                if is_trash(notation) and action == "bet_raise" and amount > 80:
                    hand_flags.append(f"trash_large_raise:{name}:{notation}:{amount}")
                    notable.append({
                        "hand": hand_no, "file": path.name, "type": "trash_large_raise",
                        "player": name, "cards": cards, "notation": notation,
                        "action": action, "amount": amount, "to_call": to_call, "reason": reason,
                    })

                if reason in {"speculative_defend", "premium_flat_mix"}:
                    hand_flags.append(f"{reason}:{name}:{notation}")
                    notable.append({
                        "hand": hand_no, "file": path.name, "type": reason,
                        "player": name, "cards": cards, "notation": notation,
                        "action": action, "to_call": to_call, "reason": reason,
                    })

            elif phase in POSTFLOP_PHASES:
                agg["postflop_decisions"] += 1
                agg["actions_postflop"][action] += 1
                agg["postflop_by_difficulty"][difficulty][action] += 1

                if reason == "slowplay_trap_mix":
                    hand_flags.append(f"slowplay_trap:{name}:{notation}")
                    notable.append({
                        "hand": hand_no, "file": path.name, "type": "slowplay_trap_mix",
                        "player": name, "cards": cards, "notation": notation,
                        "phase": phase, "action": action, "reason": reason,
                    })

        if preflop_allin:
            agg["preflop_allin_hands"] += 1
            hand_flags.append("preflop_allin")

        per_hand.append({
            "hand": hand_no,
            "file": path.name,
            "room_id": room_id,
            "pot": pot,
            "community_cards_seen": community_count(data),
            "has_postflop": has_postflop,
            "has_showdown": has_showdown,
            "bot_actions": dict(hand_counts),
            "decision_reasons": dict(hand_reasons),
            "flags": hand_flags,
            "winners": winner_summary(data),
        })

    def counter_to_dict(c: Counter | defaultdict) -> dict[str, int]:
        return dict(sorted(Counter(c).items(), key=lambda kv: (-kv[1], kv[0])))

    def pct(n: int, d: int) -> float:
        return round((100.0 * n / d), 2) if d else 0.0

    result = {
        "meta": {
            "logs_dir": str(Path(args.logs).resolve()),
            "room_filter": args.room,
            "latest_room": args.latest_room,
            "files_analyzed": [p.name for p in files],
        },
        "summary": {
            "hands": agg["hands"],
            "bot_decisions": agg["bot_decisions"],
            "preflop_decisions": agg["preflop_decisions"],
            "postflop_decisions": agg["postflop_decisions"],
            "hands_with_postflop": agg["hands_with_postflop"],
            "hands_with_showdown": agg["hands_with_showdown"],
            "preflop_only_hands": agg["preflop_only_hands"],
            "preflop_allin_hands": agg["preflop_allin_hands"],
            "big_pot_hands_ge_1000": agg["big_pot_hands"],
            "huge_pot_hands_ge_2500": agg["huge_pot_hands"],
            "preflop_fold_rate_pct": pct(agg["actions_preflop"].get("fold", 0), agg["preflop_decisions"]),
            "preflop_call_rate_pct": pct(agg["actions_preflop"].get("check_call", 0), agg["preflop_decisions"]),
            "preflop_raise_rate_pct": pct(agg["actions_preflop"].get("bet_raise", 0), agg["preflop_decisions"]),
            "postflop_fold_rate_pct": pct(agg["actions_postflop"].get("fold", 0), agg["postflop_decisions"]),
            "postflop_call_rate_pct": pct(agg["actions_postflop"].get("check_call", 0), agg["postflop_decisions"]),
            "postflop_raise_rate_pct": pct(agg["actions_postflop"].get("bet_raise", 0), agg["postflop_decisions"]),
        },
        "distributions": {
            "room_ids": counter_to_dict(agg["room_ids"]),
            "actions_all": counter_to_dict(agg["actions_all"]),
            "actions_preflop": counter_to_dict(agg["actions_preflop"]),
            "actions_postflop": counter_to_dict(agg["actions_postflop"]),
            "phases": counter_to_dict(agg["phases"]),
            "decision_reasons": counter_to_dict(agg["decision_reasons"]),
            "personality_styles": counter_to_dict(agg["personality_styles"]),
            "difficulties": counter_to_dict(agg["difficulties"]),
            "to_call_buckets_preflop": counter_to_dict(agg["to_call_buckets_preflop"]),
            "position_preflop": counter_to_dict(agg["position_preflop"]),
            "actions_by_difficulty": {
                diff: counter_to_dict(counts)
                for diff, counts in sorted(agg["actions_by_difficulty"].items())
            },
            "preflop_by_difficulty": {
                diff: counter_to_dict(counts)
                for diff, counts in sorted(agg["preflop_by_difficulty"].items())
            },
            "postflop_by_difficulty": {
                diff: counter_to_dict(counts)
                for diff, counts in sorted(agg["postflop_by_difficulty"].items())
            },
            "per_bot": {bot: counter_to_dict(counts) for bot, counts in sorted(agg["per_bot"].items())},
        },
        "notable": notable[:200],
        "per_hand": per_hand,
    }
    return result


def write_outputs(result: dict[str, Any], out_json: Path, out_md: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    s = result["summary"]
    d = result["distributions"]

    lines = []
    lines.append("# Bot Log Digest")
    lines.append("")
    lines.append("## Summary")
    for k, v in s.items():
        lines.append(f"- **{k}**: {v}")

    lines.append("")
    lines.append("## Preflop Actions")
    for k, v in d["actions_preflop"].items():
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## Postflop Actions")
    for k, v in d["actions_postflop"].items():
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## Decision Reasons")
    for k, v in d["decision_reasons"].items():
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## Personality Debug")
    for k, v in d["personality_styles"].items():
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## Difficulty Debug")
    for k, v in d["difficulties"].items():
        lines.append(f"- {k}: {v}")

    lines.append("")
    lines.append("## Actions by Difficulty")
    for diff, counts in d["actions_by_difficulty"].items():
        lines.append(f"- **{diff}**: {counts}")

    lines.append("")
    lines.append("## Preflop Actions by Difficulty")
    for diff, counts in d["preflop_by_difficulty"].items():
        lines.append(f"- **{diff}**: {counts}")

    lines.append("")
    lines.append("## Postflop Actions by Difficulty")
    for diff, counts in d["postflop_by_difficulty"].items():
        lines.append(f"- **{diff}**: {counts}")

    lines.append("")
    lines.append("## Notable Flags")
    if result["notable"]:
        for item in result["notable"][:80]:
            lines.append(f"- hand {item.get('hand')} `{item.get('type')}` {item}")
    else:
        lines.append("- No notable flags detected.")

    lines.append("")
    lines.append("## Compact Per-Hand Digest")
    for h in result["per_hand"]:
        flags = ", ".join(h["flags"]) if h["flags"] else "-"
        lines.append(
            f"- H{h['hand']} pot={h['pot']} postflop={h['has_postflop']} showdown={h['has_showdown']} "
            f"actions={h['bot_actions']} reasons={h['decision_reasons']} flags={flags} winners={h['winners']}"
        )

    out_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="logs", help="Log directory")
    ap.add_argument("--room", default=None, help="Room id / filename prefix, e.g. 5HZQG")
    ap.add_argument("--latest-room", action="store_true", help="Analyze only the room id from the newest log file")
    ap.add_argument("--limit", type=int, default=0, help="Analyze only the latest N hands after filtering")
    ap.add_argument("--out-json", default="logs/bot_log_digest.json")
    ap.add_argument("--out-md", default="logs/bot_log_digest.md")
    ap.add_argument("--watch", type=int, default=0, help="Repeat every N seconds")
    args = ap.parse_args()

    while True:
        result = analyze_once(args)
        write_outputs(result, Path(args.out_json), Path(args.out_md))

        s = result["summary"]
        print(
            f"hands={s['hands']} bot_decisions={s['bot_decisions']} "
            f"preflop_fold={s['preflop_fold_rate_pct']}% "
            f"preflop_call={s['preflop_call_rate_pct']}% "
            f"preflop_raise={s['preflop_raise_rate_pct']}% "
            f"postflop_hands={s['hands_with_postflop']} "
            f"showdowns={s['hands_with_showdown']} "
            f"preflop_allin_hands={s['preflop_allin_hands']}"
        )
        print(f"Wrote {args.out_json} and {args.out_md}")

        if not args.watch:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
