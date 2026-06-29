\# Bot Mixed-Strategy Tuning Report — 197-Hand Guardrail Sample



Date: 2026-06-29

Branch: `logic-core-hardening`

Relevant commit: `1fb2b23 fix(bot): guard trash hands against large preflop pressure`

Sample size: \~197 hands

Table setup: 2 Easy bots, 2 Medium bots, 2 Hard bots, 1 Expert bot

Purpose: verify whether the balanced mixed-strategy bot behavior is healthy after the junk-hand guardrail patch.



\---



\## Background



The original bot behavior had one major gameplay problem: bots folded too much preflop and felt too face-up.



Old baseline from earlier 75-hand sample:



\* Preflop fold rate: \~81%

\* Preflop call rate: \~4%

\* Preflop raise rate: \~15%

\* Preflop-only hands: 59/75

\* Showdown hands: 15/75



Main old issue:



\* too much preflop folding

\* too few flats/calls

\* too many hands ended before meaningful postflop play

\* bots felt too fold-or-raise



\---



\## First Improved Sample — 101 Hands



After the balanced mixed-strategy changes, a 101-hand sample showed major improvement:



\* Preflop fold rate: 58.41%

\* Preflop call rate: 34.63%

\* Preflop raise rate: 6.95%

\* Preflop-only hands: 23/101

\* Hands reaching postflop: 78/101

\* Hands reaching showdown: 90/101

\* Personality debug: all `Balanced`



This proved the core behavior was much better than the old baseline.



However, the 101-hand sample still showed some issues:



\* preflop all-in hands: 33/101

\* big-pot hands were too frequent

\* weak offsuit junk sometimes continued versus large pressure

\* one low pair made a huge raise under heavy pressure

\* `speculative\_defend` appeared on AKs with `to\_call=0`, which was a reason-label/condition bug



Conclusion after 101 hands:



\* core direction was good

\* no broad retune was needed

\* a small guardrail patch was needed



\---



\## Guardrail Patch



Commit:



`1fb2b23 fix(bot): guard trash hands against large preflop pressure`



Guardrail goals:



1\. Weak offsuit junk should fold versus large preflop pressure.

2\. Low pocket pairs should not make huge preflop raises over large pressure.

3\. `speculative\_defend` should only apply when there is an actual call price.

4\. Premium hands like AKs with `to\_call=0` should not be labeled as speculative defense.

5\. Preserve the improved call/flat behavior and avoid reverting to overfolding.



Tests passed after patch:



\* `tests/test\_bot\_ai\_style\_profiles.py tests/test\_bot\_ai\_properties.py -q` → 61 passed

\* `tests/test\_ev\_integration.py -q` → 35 passed

\* full suite → 816 passed



\---



\## Post-Guardrail Sample — \~197 Hands



Analyzer verdict: guardrails helped materially.



Key results:



\* Preflop all-in hands: 7/197

\* Huge pot hands >= 2500: 20/197

\* Preflop-only hands: 21/197

\* Hands with postflop: 176/197

\* Hands with showdown: 153/197

\* Preflop fold rate: 58.67%

\* Preflop call rate: 34.6%

\* Preflop raise rate: 6.73%

\* Personality/style debug: `Balanced: 2897`



Compared with the 101-hand pre-guardrail sample:



\* Preflop all-in hands improved from 33/101 to 7/197

\* All-in spam was largely removed

\* Weak-junk outliers became much rarer

\* Overall table shape stayed healthy

\* The bot did not revert to old overfolding



Compared with the old 75-hand baseline:



\* Preflop fold rate improved from \~81% to \~58.67%

\* Preflop call rate improved from \~4% to \~34.6%

\* Preflop-only hands improved from 59/75 to 21/197

\* Hands reaching postflop improved massively

\* Bots now produce much more real table texture



\---



\## Remaining Outliers



Some `trash\_large\_call` flags still appeared, but they were no longer systemic.



Examples noted:



\* 92o facing 110

\* J2o facing 52

\* T3o facing 165

\* 94o facing 62

\* 95o facing 90

\* 92o facing 90

\* J4o

\* T6o

\* 33

\* 44



Deeper inspection suggested these were mostly:



\* isolated scored-action calls

\* low-pair set-mining style calls

\* borderline loose calls from lower difficulty bots

\* not repeated huge-raise or all-in nonsense



No `trash\_large\_raise` pattern was seen in the digest.



The earlier 33 huge-raise red flag appeared fixed.



\---



\## Mixed-Strategy Events



Post-guardrail sample showed sensible mixed-strategy behavior:



\* `slowplay\_trap\_mix`: 12

\* `speculative\_defend`: 1, on 86s facing a tiny price, considered plausible

\* `premium\_flat\_mix`: appeared on AA facing `to\_call=10`, exactly the intended rare premium-flat behavior



The earlier AKs zero-to-call `speculative\_defend` issue did not reappear.



\---



\## Difficulty Behavior



The table setup intentionally used mixed difficulties:



\* 2 Easy

\* 2 Medium

\* 2 Hard

\* 1 Expert



Observed behavior:



\* Easy bots were clearly looser preflop

\* Medium bots were looser than Hard/Expert

\* Hard and Expert were more disciplined

\* Expert was tightest by decision mix

\* Difficulty spread looked acceptable

\* All bots still used the `Balanced` personality core



Conclusion:



Difficulty appears to affect looseness/noise without reintroducing old personality routing problems.



\---



\## Overall Verdict



Status: healthy.



The bot is now materially better than the old baseline.



What is fixed:



\* old overfolding problem

\* near-zero call/flat problem

\* fold-or-raise feel

\* all-in spam from the 101-hand sample

\* style-routing weirdness

\* speculative\_defend mislabel on premium zero-call spots

\* huge low-pair raise under pressure



What remains:



\* small tail of loose calls with weak offsuit hands

\* some Easy/Medium weirdness, likely acceptable for casual gameplay

\* a few marginal low-pair set-mining calls



Recommendation:



Do not broadly retune bot strategy right now.



The remaining mistakes are small enough to be part of casual poker texture. Some bad calls are good for a fun table. They create memorable “how did you call that?” moments.



Only consider a future micro-guardrail if the loose calls still feel bad by eye.



Possible future micro-guardrail:



\* If hand is weak offsuit trash and `to\_call >= 8–10 BB`, force fold unless:



&#x20; \* difficulty is Easy, and

&#x20; \* a very small random exception triggers



But this should not be applied immediately.



\---



\## Next Suggested Direction



Pause bot-brain tuning for now.



Move to game feel and social features:



1\. Sound effects

2\. Table reactions / emotes

3\. Better action/result presentation

4\. Boss bot design scaffold

5\. Voice chat later



The current bot behavior is good enough to build around.



