// ═══════════════════════════════════════════════════════════════
// Property-Based Tests for Action Log Frontend Formatting
// Uses fast-check with minimum 100 iterations per property
// ═══════════════════════════════════════════════════════════════
// Validates: Requirements 2.3, 2.4, 2.5, 3.2, 3.3, 6.3

const fc = require("fast-check");
const { JSDOM } = require("jsdom");

// Set up a minimal DOM environment for renderStreetSeparator
const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>");
const document = dom.window.document;

// ─── Inline pure functions from static/app.js ───

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function formatActionEntry(entry) {
  const player = entry.player || "";
  const amount = entry.amount || 0;

  // Blinds always show their specific verb regardless of all-in status
  if (entry.action === "small_blind") return `${player} posts SB ${amount}`;
  if (entry.action === "big_blind") return `${player} posts BB ${amount}`;

  // All-in handling is action-aware (except blinds handled above)
  if (entry.is_all_in) {
    if (entry.action === "fold") return `${player} folds`;
    if (entry.action === "check_call") {
      if (amount > 0) return `${player} calls ${amount} and is all-in`;
      return `${player} is all-in`;
    }
    if (entry.action === "bet_raise") {
      return entry._isFirstBetOnStreet
        ? `${player} goes all-in for ${amount}`
        : `${player} raises all-in to ${amount}`;
    }
    return `${player} is all-in`;
  }

  switch (entry.action) {
    case "fold":       return `${player} folds`;
    case "check_call": return amount > 0 ? `${player} calls ${amount}` : `${player} checks`;
    case "bet_raise":  return entry._isFirstBetOnStreet ? `${player} bets ${amount}` : `${player} raises to ${amount}`;
    default:           return `${player} ${entry.action || "acts"}`;
  }
}

function formatWinnerEntry(winner) {
  if (winner.hand_name && winner.reason !== "Everyone else folded") {
    return `${winner.name} wins ${winner.amount} with ${winner.hand_name}`;
  }
  return `${winner.name} wins ${winner.amount}`;
}

function renderStreetSeparator(phase, community) {
  const div = document.createElement("div");
  div.className = "street-separator";

  let cards = [];
  if (phase === "flop") {
    cards = (community || []).slice(0, 3);
  } else if (phase === "turn") {
    cards = (community || []).slice(3, 4);
  } else if (phase === "river") {
    cards = (community || []).slice(4, 5);
  }

  const streetName = phase.charAt(0).toUpperCase() + phase.slice(1);
  const cardSpans = cards.map(card => {
    const isRed = card.includes("♥") || card.includes("♦");
    const cls = isRed ? "card-red" : "card-white";
    return `<span class="${cls}">${esc(card)}</span>`;
  }).join(" ");

  div.innerHTML = `─── ${esc(streetName)}: ${cardSpans} ───`;
  return div;
}

// ─── Custom Arbitraries ───

const playerNameArb = fc.string({ minLength: 1, maxLength: 20 }).filter(s => s.trim().length > 0);
const amountArb = fc.integer({ min: 0, max: 100000 });
const positiveAmountArb = fc.integer({ min: 1, max: 100000 });

const actionTypeArb = fc.constantFrom("small_blind", "big_blind", "fold", "check_call", "bet_raise");

const phaseArb = fc.constantFrom("preflop", "flop", "turn", "river");

const handNameArb = fc.constantFrom(
  "Royal Flush", "Straight Flush", "Four of a Kind", "Full House",
  "Flush", "Straight", "Three of a Kind", "Two Pair", "One Pair", "High Card"
);

const ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"];
const suits = ["♠", "♥", "♦", "♣"];
const cardArb = fc.tuple(
  fc.constantFrom(...ranks),
  fc.constantFrom(...suits)
).map(([rank, suit]) => `${rank}${suit}`);

const communityCardsArb = fc.array(cardArb, { minLength: 5, maxLength: 5 });

// ─── Test runner ───
let totalPassed = 0;
let totalFailed = 0;

function runProperty(name, property) {
  try {
    fc.assert(property, { numRuns: 100 });
    totalPassed++;
    console.log(`  ✓ ${name}`);
  } catch (e) {
    totalFailed++;
    console.error(`  ✗ ${name}`);
    console.error(`    ${e.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════
// Property 2: Action entry verb mapping
// Validates: Requirements 2.3, 2.4
// ═══════════════════════════════════════════════════════════════
console.log("\nProperty 2: Action entry verb mapping");

runProperty(
  "small_blind entries contain 'posts SB'",
  fc.property(
    playerNameArb, amountArb, fc.boolean(),
    (player, amount, isAllIn) => {
      const entry = { player, action: "small_blind", amount, phase: "preflop", is_all_in: isAllIn };
      const result = formatActionEntry(entry);
      return result.includes("posts SB") && result.includes(player) && result.includes(String(amount));
    }
  )
);

runProperty(
  "big_blind entries contain 'posts BB'",
  fc.property(
    playerNameArb, amountArb, fc.boolean(),
    (player, amount, isAllIn) => {
      const entry = { player, action: "big_blind", amount, phase: "preflop", is_all_in: isAllIn };
      const result = formatActionEntry(entry);
      return result.includes("posts BB") && result.includes(player) && result.includes(String(amount));
    }
  )
);

runProperty(
  "fold entries contain 'folds'",
  fc.property(
    playerNameArb,
    (player) => {
      const entry = { player, action: "fold", amount: 0, phase: "preflop", is_all_in: false };
      const result = formatActionEntry(entry);
      return result.includes("folds") && result.includes(player);
    }
  )
);

runProperty(
  "check_call with amount > 0 contains 'calls'",
  fc.property(
    playerNameArb, positiveAmountArb,
    (player, amount) => {
      const entry = { player, action: "check_call", amount, phase: "preflop", is_all_in: false };
      const result = formatActionEntry(entry);
      return result.includes("calls") && result.includes(player) && result.includes(String(amount));
    }
  )
);

runProperty(
  "check_call with amount = 0 contains 'checks'",
  fc.property(
    playerNameArb,
    (player) => {
      const entry = { player, action: "check_call", amount: 0, phase: "preflop", is_all_in: false };
      const result = formatActionEntry(entry);
      return result.includes("checks") && result.includes(player);
    }
  )
);

runProperty(
  "bet_raise entries contain 'raises to'",
  fc.property(
    playerNameArb, positiveAmountArb,
    (player, amount) => {
      const entry = { player, action: "bet_raise", amount, phase: "preflop", is_all_in: false, _isFirstBetOnStreet: false };
      const result = formatActionEntry(entry);
      return result.includes("raises to") && result.includes(player) && result.includes(String(amount));
    }
  )
);

runProperty(
  "check_call all-in entries say calls and is all-in",
  fc.property(
    playerNameArb, positiveAmountArb,
    (player, amount) => {
      const entry = { player, action: "check_call", amount, phase: "preflop", is_all_in: true };
      const result = formatActionEntry(entry);
      return result.includes("calls") && result.includes("is all-in") && result.includes(player) && result.includes(String(amount));
    }
  )
);

runProperty(
  "bet_raise all-in entries distinguish shove from raise-all-in",
  fc.property(
    playerNameArb, positiveAmountArb, fc.boolean(),
    (player, amount, firstOnStreet) => {
      const entry = { player, action: "bet_raise", amount, phase: "preflop", is_all_in: true, _isFirstBetOnStreet: firstOnStreet };
      const result = formatActionEntry(entry);
      const expectedVerb = firstOnStreet ? "goes all-in for" : "raises all-in to";
      return result.includes(expectedVerb) && result.includes(player) && result.includes(String(amount));
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property 3: Street separator insertion at phase transitions
// Validates: Requirements 2.5
// ═══════════════════════════════════════════════════════════════
console.log("\nProperty 3: Street separator insertion at phase transitions");

/**
 * Simulates the separator insertion logic from renderActionLog.
 * Returns an array of { type: "entry" | "separator", phase } items.
 */
function simulateRenderOrder(actionLog) {
  const items = [];
  let prevPhase = null;
  for (const entry of actionLog) {
    if (prevPhase !== null && entry.phase && entry.phase !== prevPhase) {
      items.push({ type: "separator", phase: entry.phase });
    }
    prevPhase = entry.phase;
    items.push({ type: "entry", phase: entry.phase });
  }
  return items;
}

const actionEntryArb = fc.record({
  player: playerNameArb,
  action: actionTypeArb,
  amount: amountArb,
  phase: phaseArb,
  is_all_in: fc.boolean()
});

runProperty(
  "separators appear exactly at phase transitions",
  fc.property(
    fc.array(actionEntryArb, { minLength: 2, maxLength: 30 }),
    (actionLog) => {
      const items = simulateRenderOrder(actionLog);
      // Check: separators only appear between entries of different phases
      for (let i = 0; i < items.length; i++) {
        if (items[i].type === "separator") {
          // There must be an entry before this separator
          const prevEntries = items.slice(0, i).filter(it => it.type === "entry");
          if (prevEntries.length === 0) return false;
          const lastPrevEntry = prevEntries[prevEntries.length - 1];
          // The separator's phase must differ from the previous entry's phase
          if (lastPrevEntry.phase === items[i].phase) return false;
        }
      }
      return true;
    }
  )
);

runProperty(
  "no separator between consecutive entries of the same phase",
  fc.property(
    fc.array(actionEntryArb, { minLength: 2, maxLength: 30 }),
    (actionLog) => {
      const items = simulateRenderOrder(actionLog);
      for (let i = 1; i < items.length; i++) {
        if (items[i].type === "separator") {
          // A separator should never appear between same-phase entries
          const prevEntries = items.slice(0, i).filter(it => it.type === "entry");
          if (prevEntries.length > 0) {
            const lastPrevEntry = prevEntries[prevEntries.length - 1];
            if (lastPrevEntry.phase === items[i].phase) return false;
          }
        }
      }
      return true;
    }
  )
);

runProperty(
  "separator count equals number of phase transitions in the sequence",
  fc.property(
    fc.array(actionEntryArb, { minLength: 1, maxLength: 30 }),
    (actionLog) => {
      // Count expected phase transitions
      let expectedTransitions = 0;
      for (let i = 1; i < actionLog.length; i++) {
        if (actionLog[i].phase !== actionLog[i - 1].phase) {
          expectedTransitions++;
        }
      }
      const items = simulateRenderOrder(actionLog);
      const separatorCount = items.filter(it => it.type === "separator").length;
      return separatorCount === expectedTransitions;
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property 4: Winner entry formatting
// Validates: Requirements 3.2, 3.3
// ═══════════════════════════════════════════════════════════════
console.log("\nProperty 4: Winner entry formatting");

runProperty(
  "winner with hand_name (not fold-win) has format '{name} wins {amount} with {hand_name}'",
  fc.property(
    playerNameArb, positiveAmountArb, handNameArb,
    (name, amount, handName) => {
      const winner = { name, amount, hand_name: handName, reason: "Best hand" };
      const result = formatWinnerEntry(winner);
      return result === `${name} wins ${amount} with ${handName}`;
    }
  )
);

runProperty(
  "winner with reason 'Everyone else folded' has format '{name} wins {amount}' (no hand)",
  fc.property(
    playerNameArb, positiveAmountArb,
    (name, amount) => {
      const winner = { name, amount, hand_name: "Two Pair", reason: "Everyone else folded" };
      const result = formatWinnerEntry(winner);
      return result === `${name} wins ${amount}`;
    }
  )
);

runProperty(
  "winner without hand_name has format '{name} wins {amount}'",
  fc.property(
    playerNameArb, positiveAmountArb,
    (name, amount) => {
      const winner = { name, amount, hand_name: "", reason: "" };
      const result = formatWinnerEntry(winner);
      return result === `${name} wins ${amount}`;
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property 6: Card suit color classification
// Validates: Requirements 6.3
// ═══════════════════════════════════════════════════════════════
console.log("\nProperty 6: Card suit color classification");

runProperty(
  "cards with ♥ get 'card-red' class",
  fc.property(
    fc.constantFrom(...ranks),
    (rank) => {
      const card = `${rank}♥`;
      const div = renderStreetSeparator("flop", [card, "2♠", "3♣"]);
      return div.innerHTML.includes('class="card-red"') && div.innerHTML.includes(rank);
    }
  )
);

runProperty(
  "cards with ♦ get 'card-red' class",
  fc.property(
    fc.constantFrom(...ranks),
    (rank) => {
      const card = `${rank}♦`;
      const div = renderStreetSeparator("flop", [card, "2♠", "3♣"]);
      return div.innerHTML.includes('class="card-red"') && div.innerHTML.includes(rank);
    }
  )
);

runProperty(
  "cards with ♠ get 'card-white' class (default)",
  fc.property(
    fc.constantFrom(...ranks),
    (rank) => {
      const card = `${rank}♠`;
      const div = renderStreetSeparator("flop", [card, "2♥", "3♥"]);
      // The first span should be card-white for ♠
      const spans = div.querySelectorAll("span");
      const firstSpan = spans[0];
      return firstSpan && firstSpan.className === "card-white";
    }
  )
);

runProperty(
  "cards with ♣ get 'card-white' class (default)",
  fc.property(
    fc.constantFrom(...ranks),
    (rank) => {
      const card = `${rank}♣`;
      const div = renderStreetSeparator("flop", [card, "2♥", "3♥"]);
      const spans = div.querySelectorAll("span");
      const firstSpan = spans[0];
      return firstSpan && firstSpan.className === "card-white";
    }
  )
);

runProperty(
  "random cards: red suits (♥/♦) always get card-red, black suits (♠/♣) always get card-white",
  fc.property(
    cardArb,
    (card) => {
      // Place the card in first position of a flop community
      const div = renderStreetSeparator("flop", [card, "2♠", "3♠"]);
      const spans = div.querySelectorAll("span");
      const firstSpan = spans[0];
      if (!firstSpan) return false;
      const isRed = card.includes("♥") || card.includes("♦");
      if (isRed) {
        return firstSpan.className === "card-red";
      } else {
        return firstSpan.className === "card-white";
      }
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property 5: Toggle state localStorage round-trip
// Validates: Requirements 4.4, 4.5
// ═══════════════════════════════════════════════════════════════
console.log("\nProperty 5: Toggle state localStorage round-trip");

const PANEL_KEY = "poker_action_log_expanded";

/**
 * Creates a mock localStorage with getItem/setItem.
 */
function createMockLocalStorage() {
  const store = {};
  return {
    getItem(key) {
      return key in store ? store[key] : null;
    },
    setItem(key, value) {
      store[key] = String(value);
    },
    removeItem(key) {
      delete store[key];
    }
  };
}

/**
 * Reads the toggle state from localStorage using the same logic as the app:
 * localStorage.getItem(PANEL_KEY) !== "false" → true (default expanded)
 */
function readToggleState(storage, viewportWidth = 1024) {
  const stored = storage.getItem(PANEL_KEY);
  const defaultExpanded = viewportWidth > 768;
  return stored === null ? defaultExpanded : stored !== "false";
}

/**
 * Writes the toggle state to localStorage using the same logic as the app:
 * localStorage.setItem(PANEL_KEY, String(expanded))
 */
function writeToggleState(storage, expanded) {
  storage.setItem(PANEL_KEY, String(expanded));
}

runProperty(
  "round-trip: write boolean state then read back produces same value",
  fc.property(
    fc.boolean(),
    (expanded) => {
      const storage = createMockLocalStorage();
      writeToggleState(storage, expanded);
      const readBack = readToggleState(storage);
      return readBack === expanded;
    }
  )
);

runProperty(
  "default: desktop expands and mobile collapses when localStorage has no value",
  fc.property(
    // Generate arbitrary strings for unrelated keys to prove the specific key absence matters
    fc.string({ minLength: 0, maxLength: 20 }),
    (unrelatedValue) => {
      const storage = createMockLocalStorage();
      // Set some unrelated key to show it doesn't affect the toggle key
      if (unrelatedValue.length > 0) {
        storage.setItem("unrelated_key", unrelatedValue);
      }
      // The PANEL_KEY is not set, so viewport controls the default
      return readToggleState(storage, 1024) === true && readToggleState(storage, 412) === false;
    }
  )
);

runProperty(
  "multiple writes: last write wins on read-back",
  fc.property(
    fc.array(fc.boolean(), { minLength: 1, maxLength: 20 }),
    (states) => {
      const storage = createMockLocalStorage();
      // Write all states in sequence
      for (const state of states) {
        writeToggleState(storage, state);
      }
      // Read back should equal the last written state
      const lastState = states[states.length - 1];
      return readToggleState(storage) === lastState;
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Summary
// ═══════════════════════════════════════════════════════════════
console.log(`\n═══ Results: ${totalPassed} passed, ${totalFailed} failed ═══\n`);
if (totalFailed > 0) {
  process.exit(1);
}
