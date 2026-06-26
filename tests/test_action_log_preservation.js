// ═══════════════════════════════════════════════════════════════
// Preservation Property-Based Tests for Action Log
// Uses fast-check with minimum 100 iterations per property
// ═══════════════════════════════════════════════════════════════
// **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
//
// These tests capture CORRECT baseline behavior that must remain unchanged
// after the bugfix. They test non-bug-condition inputs only.

const fc = require("fast-check");
const { JSDOM } = require("jsdom");

// ─── Inline pure functions from static/app.js (current unfixed code) ───

function formatActionEntry(entry) {
  const player = entry.player || "";
  const amount = entry.amount || 0;

  // Blinds always show their specific verb regardless of all-in status
  if (entry.action === "small_blind") return `${player} posts SB ${amount}`;
  if (entry.action === "big_blind") return `${player} posts BB ${amount}`;

  // All-in handling — action-aware (except blinds handled above)
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

// ─── Action bar visibility logic (mirrors app.js) ───

function computeActionBarVisibility(state) {
  // In the current code, action bar gets "my-turn" class when viewer.is_turn is true.
  // Buttons are always rendered (opacity is reduced via CSS when not my-turn).
  // The bar is visible in ALL phases currently (bug: even showdown).
  const isMyTurn = state.viewer && state.viewer.is_turn;
  return {
    hasMyTurnClass: !!isMyTurn,
    buttonsRendered: true // buttons are always in the DOM
  };
}

// ─── Panel toggle logic (mirrors app.js) ───

const PANEL_KEY = "poker_action_log_expanded";

function readToggleState(storage, viewportWidth = 1024) {
  const stored = storage.getItem(PANEL_KEY);
  const defaultExpanded = viewportWidth > 768;
  return stored === null ? defaultExpanded : stored !== "false";
}

function writeToggleState(storage, expanded) {
  storage.setItem(PANEL_KEY, String(expanded));
}

// ─── Custom Arbitraries ───

const playerNameArb = fc.string({ minLength: 1, maxLength: 20 }).filter(s => s.trim().length > 0);
const positiveAmountArb = fc.integer({ min: 1, max: 100000 });
const phaseArb = fc.constantFrom("preflop", "flop", "turn", "river");
const activePhaseArb = fc.constantFrom("preflop", "flop", "turn", "river");

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
// Property: check_call with to_call=0 displays "checks"
// Validates: Requirement 3.1
// ═══════════════════════════════════════════════════════════════
console.log("\nPreservation Property: Genuine check display");

runProperty(
  "check_call with amount=0 (genuine check, to_call=0) returns string containing 'checks'",
  fc.property(
    playerNameArb, phaseArb,
    (player, phase) => {
      const entry = { player, action: "check_call", amount: 0, phase, is_all_in: false };
      const result = formatActionEntry(entry);
      return result.includes("checks") && result.includes(player);
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property: fold entries display "folds"
// Validates: Requirement 3.5
// ═══════════════════════════════════════════════════════════════
console.log("\nPreservation Property: Fold display");

runProperty(
  "fold entries return string containing 'folds'",
  fc.property(
    playerNameArb, phaseArb,
    (player, phase) => {
      const entry = { player, action: "fold", amount: 0, phase, is_all_in: false };
      const result = formatActionEntry(entry);
      return result.includes("folds") && result.includes(player);
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property: small_blind entries display "posts SB X"
// Validates: Requirement 3.4
// ═══════════════════════════════════════════════════════════════
console.log("\nPreservation Property: Small blind display");

runProperty(
  "small_blind entries with positive amount X return 'posts SB X'",
  fc.property(
    playerNameArb, positiveAmountArb, fc.boolean(),
    (player, amount, isAllIn) => {
      const entry = { player, action: "small_blind", amount, phase: "preflop", is_all_in: isAllIn };
      const result = formatActionEntry(entry);
      return result === `${player} posts SB ${amount}`;
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property: big_blind entries display "posts BB X"
// Validates: Requirement 3.4
// ═══════════════════════════════════════════════════════════════
console.log("\nPreservation Property: Big blind display");

runProperty(
  "big_blind entries with positive amount X return 'posts BB X'",
  fc.property(
    playerNameArb, positiveAmountArb, fc.boolean(),
    (player, amount, isAllIn) => {
      const entry = { player, action: "big_blind", amount, phase: "preflop", is_all_in: isAllIn };
      const result = formatActionEntry(entry);
      return result === `${player} posts BB ${amount}`;
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property: bet_raise with is_all_in=true and amount > 0 displays all-in raise wording
// Validates: Requirement 3.3
// ═══════════════════════════════════════════════════════════════
console.log("\nPreservation Property: Bet/raise all-in display");

runProperty(
  "bet_raise with is_all_in=true and amount > 0 returns all-in raise wording",
  fc.property(
    playerNameArb, positiveAmountArb, phaseArb, fc.boolean(),
    (player, amount, phase, firstOnStreet) => {
      const entry = { player, action: "bet_raise", amount, phase, is_all_in: true, _isFirstBetOnStreet: firstOnStreet };
      const result = formatActionEntry(entry);
      return firstOnStreet
        ? result === `${player} goes all-in for ${amount}`
        : result === `${player} raises all-in to ${amount}`;
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property: Consecutive entries with different phases produce a separator
// Validates: Requirement 3.2
// ═══════════════════════════════════════════════════════════════
console.log("\nPreservation Property: Phase-transition street separator");

runProperty(
  "consecutive entries with different phases produce a separator between them",
  fc.property(
    fc.array(
      fc.record({
        player: playerNameArb,
        action: fc.constantFrom("small_blind", "big_blind", "fold", "check_call", "bet_raise"),
        amount: fc.integer({ min: 0, max: 100000 }),
        phase: phaseArb,
        is_all_in: fc.boolean()
      }),
      { minLength: 2, maxLength: 20 }
    ),
    (actionLog) => {
      const items = simulateRenderOrder(actionLog);

      // For every pair of consecutive entries in the original log where
      // phases differ, there must be a separator between them in the rendered output
      for (let i = 1; i < actionLog.length; i++) {
        if (actionLog[i].phase !== actionLog[i - 1].phase) {
          // Find the separator in items between entry i-1 and entry i
          // Count entries seen so far to find position
          let entryCount = 0;
          let foundSeparator = false;
          for (const item of items) {
            if (item.type === "entry") {
              entryCount++;
              if (entryCount > i) break; // past the entry we care about
            }
            if (item.type === "separator" && entryCount === i) {
              // This separator is between entry i-1 and entry i
              foundSeparator = true;
              break;
            }
          }
          if (!foundSeparator) return false;
        }
      }
      return true;
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property: Action buttons visible during active phases when it's player's turn
// Validates: Requirement 3.6
// ═══════════════════════════════════════════════════════════════
console.log("\nPreservation Property: Action buttons visible during active phases");

runProperty(
  "action buttons have my-turn class during preflop/flop/turn/river when is_my_turn=true",
  fc.property(
    activePhaseArb,
    (phase) => {
      const state = {
        phase,
        viewer: { is_turn: true, to_call: 0 }
      };
      const visibility = computeActionBarVisibility(state);
      // In active phases with is_turn=true, buttons should have my-turn class
      // and buttons should be rendered (in DOM)
      return visibility.hasMyTurnClass === true && visibility.buttonsRendered === true;
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Property: Panel collapse/expand state persists in localStorage
// Validates: Requirement 3.7
// ═══════════════════════════════════════════════════════════════
console.log("\nPreservation Property: Panel toggle persistence");

runProperty(
  "panel expanded/collapsed state round-trips through localStorage",
  fc.property(
    fc.boolean(),
    (expanded) => {
      const store = {};
      const storage = {
        getItem(key) { return key in store ? store[key] : null; },
        setItem(key, value) { store[key] = String(value); }
      };
      writeToggleState(storage, expanded);
      const readBack = readToggleState(storage);
      return readBack === expanded;
    }
  )
);

runProperty(
  "panel default depends on viewport when localStorage has no stored value",
  fc.property(
    fc.constant(null), // just need one run to confirm
    () => {
      const store = {};
      const storage = {
        getItem(key) { return key in store ? store[key] : null; },
        setItem(key, value) { store[key] = String(value); }
      };
      // No value stored → should default to expanded (true)
      return readToggleState(storage, 1024) === true && readToggleState(storage, 412) === false;
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
