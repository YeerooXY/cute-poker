# Bot Personality Notes

Small personality hints for future bot behavior. These should be weak tendencies, not hard rules, so bots stay hard to exploit.

## General Rule

- Personality should nudge decisions, not override poker fundamentals.
- Add randomness to every personality behavior.
- Strong hands, pot odds, stack depth, and board texture should still matter.
- Trash talk can be personality-flavored, but gameplay should remain fair.

## Dyndibot

- Loves suspicious river pressure.
- If holding a pair of 2s, may bluff more often.
- Can overdo river all-ins, but only as a low-frequency tendency.
- Should sometimes make weird aggressive plays, not always.

## Jerobot

- Has a special attachment to 2s and 3s.
- If a 2 or 3 appears in hand or on board, slightly more likely to raise.
- If holding a pair of 2s or 3s, much more likely to raise big.
- With other reasonable hands, raises casually rather than wildly.
- If 6 and 7 are both on the board, may "brainfart" and fold/lose discipline sometimes.

## Giddybot

- Candidate for the weakest/easy bot.
- Tends to fold too much.
- Can be used as the "always scared" bot personality.

## Papperbot

- Has an `interested` mood flag.
- Every few hands, `interested` can randomly flip.
- If `interested = true`: plays normally.
- If `interested = false`: calls far too much and stops caring.
- Can tilt quickly after losing.

## Lamobot

- Simple, weak, and confused.
- Makes low-level mistakes more often than other bots.
- Better fit for Easy difficulty than higher tiers.

## Giribot

- Swingy personality.
- Roughly 70/30 tendency between passive/calling-station behavior and stubborn play.
- If Giribot starts winning, confidence rises and aggression increases.

## Tilt Ideas

- Add a `tilt_factor` per bot.
- For Papperbot especially: each lost hand can add a small tilt increase, e.g. `+0.1`.
- Tilt should decay slowly over time.
- Tilt should increase call/raise frequency, but not force nonsense every hand.

## Implementation Direction

- Keep these as small modifiers layered on top of the existing bot tier logic.
- Avoid deterministic triggers like "always raise with 2 or 3".
- Suggested model:
  - base decision from current AI
  - personality modifier
  - random noise
  - sanity gate

