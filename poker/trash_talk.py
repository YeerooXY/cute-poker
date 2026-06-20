"""
Bot trash talk system — personality-driven chat messages after notable events.

Each bot style has a distinct voice:
- tight_aggressive: calculated, condescending
- loose_aggressive: cocky, energetic
- calling_station: chill, unbothered
- maniac: chaotic, unhinged

Messages fire probabilistically after wins, successful bluffs, and bad beats,
limited to once per hand to avoid spam.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrashTalkEvent:
    event_type: str  # "win_pot", "bluff_success", "lose_big"
    bot_style: str
    bot_name: str
    pot_size: int = 0
    equity_at_showdown: float = 0.0
    hand_number: int = 0


# Probability of sending a message for each event type
PROBABILITIES: dict[str, float] = {
    "win_pot": 0.60,
    "bluff_success": 0.80,
    "lose_big": 0.40,
}

# Delay range (seconds) before sending the message after the event
DELAY_RANGE: tuple[float, float] = (1.0, 3.0)

# Track the last hand that produced trash talk, keyed by bot name
_last_trash_talk_hand: dict[str, int] = {}


MESSAGE_POOLS: dict[str, dict[str, list[str]]] = {
    "tight_aggressive": {
        "win_pot": [
            "Textbook play. You should take notes.",
            "Calculated risk, calculated reward.",
            "That's what discipline looks like.",
            "Read the board. Read you. Easy.",
            "Another day at the office.",
            "You walked right into that one.",
            "Position, patience, profit.",
            "I had you on the second card.",
            "Study up. I'll wait.",
            "Expected value doesn't lie.",
        ],
        "bluff_success": [
            "You didn't have the odds to call. Smart.",
            "I gave you every reason to fold. You listened.",
            "Sometimes the best hand is the one they think you have.",
            "Fold equity is a beautiful thing.",
            "Perfectly balanced, as all things should be.",
            "I bet you're wondering what I had.",
            "Information costs money. You saved some.",
            "That one was by the book... my book.",
            "Controlled aggression. Look it up.",
            "The math was never in your favor.",
        ],
        "lose_big": [
            "Variance. Nothing more.",
            "Interesting line. Won't work twice.",
            "Noted. Adjusting.",
            "That pot was a donation. Consider it charity.",
            "Run good while it lasts.",
            "Enjoy it. The correction is coming.",
            "You got lucky. I got information.",
            "One hand doesn't make a session.",
            "I'll remember that.",
            "Temporary setback. Permanent lessons.",
        ],
    },
    "loose_aggressive": {
        "win_pot": [
            "Can't stop, won't stop 🔥",
            "Get used to it, baby!",
            "Ship it! 💰💰💰",
            "That's how we do it around here.",
            "Money printer go BRRRR",
            "Too easy. Way too easy.",
            "You love to see it!",
            "Stack go up, spirits go up 📈",
            "I own this table.",
            "Another one 🎯",
        ],
        "bluff_success": [
            "PURE AIR and you folded 😂",
            "I had nothing. NOTHING. 🤣",
            "Bluff city, population: me",
            "You'll never know what I had 😏",
            "Scared money don't make money!",
            "Aggression wins, baby!",
            "I could sell ice to a penguin 🐧",
            "Folded? That's what I thought.",
            "The disrespect is intentional.",
            "My cards? Doesn't matter. Your fold does.",
        ],
        "lose_big": [
            "Whatever, I'm just warming up",
            "You needed all that help to beat me? 😂",
            "Lucky. So lucky.",
            "Reload and run it back!",
            "I'll get it back in 5 hands, watch.",
            "That one stings but I'm still vibing",
            "Bruhhh come ON 😤",
            "Fine. FINE. I'm tilted. Jk. Maybe.",
            "Next hand is mine. Book it.",
            "Temporary L, permanent W mentality 💪",
        ],
    },
    "calling_station": {
        "win_pot": [
            "eh, had to see it",
            "called and it worked out 🤷",
            "nice, i guess",
            "cool cool cool",
            "that happened",
            "oh hey, I won",
            "interesting",
            "figured I'd hang around",
            "patience pays, or whatever",
            "was curious. got paid.",
        ],
        "bluff_success": [
            "wait, you folded? ok then",
            "huh, didn't expect that",
            "oh... cool 🤷",
            "i was just betting to bet honestly",
            "lol didn't think that would work",
            "neat",
            "well that's a first",
            "guess I'll take it",
            "no complaints here",
            "did i just bluff? weird",
        ],
        "lose_big": [
            "oh well",
            "shoulda folded probably",
            "meh, next hand",
            "it is what it is",
            "eh whatever",
            "that's poker i think",
            "pain but also whatever",
            "cool, cool, didn't want those chips anyway",
            "tough one. anyway",
            "happens 🤷",
        ],
    },
    "maniac": {
        "win_pot": [
            "LETSSS GOOOOO 💀💀💀",
            "HAHAHA GET WRECKED",
            "ALL GAS NO BRAKES BABY 🚀🚀🚀",
            "I AM INEVITABLE",
            "CHAOS REIGNS SUPREME",
            "FEAR ME 👹",
            "UNSTOPPABLE FORCE MEETS MOVABLE OBJECT (you)",
            "BOW DOWN 🙇‍♂️🙇‍♂️🙇‍♂️",
            "NEVER IN DOUBT (total doubt tbh)",
            "THE MANIAC ALWAYS WINS IN THE END",
        ],
        "bluff_success": [
            "I HAD 7-2 AND YOU FOLDED HAHAHAHA",
            "BLUFF OF THE CENTURY 🏆",
            "MY CARDS ARE IRRELEVANT. I AM THE HAND.",
            "YOU FOLDED?? LMAOOO 💀",
            "DECEPTION IS AN ART AND I AM PICASSO",
            "imagine folding there couldn't be me",
            "ABSOLUTELY UNHINGED AND IT WORKED",
            "PURE CHAOS ENERGY CAN'T BE STOPPED",
            "they'll NEVER figure out my range 🤡",
            "I DON'T EVEN LOOK AT MY CARDS 🃏🃏",
        ],
        "lose_big": [
            "WHATEVER I'M GOING ALL IN NEXT HAND ANYWAY",
            "YOU THINK THAT STOPS ME??? LMAOOO",
            "pain 💀 but also LETS GOOO MORE POKER",
            "TILT IS A STATE OF MIND AND I AM ASCENDING",
            "I WILL GET THOSE CHIPS BACK x10",
            "AHHHHHHH 😤😤😤 ok im fine im fine",
            "this means NOTHING. NOTHING!!!",
            "cool NOW I'm MAD. you don't want to see me MAD.",
            "that was MY pot and you STOLE it 😡",
            "variance is my MORTAL ENEMY and also my BEST FRIEND",
        ],
    },
}


def should_send(event_type: str) -> bool:
    """
    Check probability threshold for event type.

    Returns True if a random check passes the configured probability
    for the given event type. Returns False for unknown event types.
    """
    probability = PROBABILITIES.get(event_type, 0.0)
    return random.random() < probability


def get_trash_talk(event: TrashTalkEvent) -> Optional[str]:
    """
    Return a trash talk message for the event, or None.

    Returns None if:
    - The random probability check fails
    - A message was already sent this hand (once-per-hand limit)
    - The message pool is empty for the given style/event
    - The event type or bot style is unknown
    """
    # Once-per-hand check
    last_hand = _last_trash_talk_hand.get(event.bot_name, -1)
    if last_hand == event.hand_number and event.hand_number >= 0:
        return None

    # Probability check
    if not should_send(event.event_type):
        return None

    # Look up message pool
    style_pool = MESSAGE_POOLS.get(event.bot_style)
    if not style_pool:
        return None

    messages = style_pool.get(event.event_type)
    if not messages:
        return None

    # Record that we sent a message this hand
    _last_trash_talk_hand[event.bot_name] = event.hand_number

    return random.choice(messages)


def reset_cooldowns() -> None:
    """Clear all cooldown tracking. Useful for testing."""
    _last_trash_talk_hand.clear()
