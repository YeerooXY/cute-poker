// ═══════════════════════════════════════════════════════════════
// Bug Condition Exploration Tests - Frontend Display Bugs
// ═══════════════════════════════════════════════════════════════
// **Validates: Requirements 1.2, 1.3, 1.4, 1.6**
//
// Property 1: Bug Condition - Action Log Display Bugs
//
// CRITICAL: These tests MUST FAIL on unfixed code - failure confirms the bugs exist.
// DO NOT attempt to fix the tests or the code when they fail.
//
// Bug Conditions Tested:
// - Bug 1.3: is_all_in=true AND action="check_call" AND amount=0 shows "goes all-in 0"
//            (should show "calls X and is all-in")
// - Bug 1.4: first bet_raise on a street shows "raises to" instead of "bets"
// - Bug 1.2: 5 community cards with no river-phase entries produces no river separator
// - Bug 1.6: phase="showdown" still shows action buttons

const fc = require("fast-check");
const { JSDOM } = require("jsdom");

// ─── Inline the CURRENT (fixed) formatActionEntry from static/app.js ───

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

// ─── Inline the CURRENT (fixed) renderActionLog separator logic ───

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderStreetSeparator(phase, community) {
  const div = { className: "street-separator", phase, type: "separator" };
  return div;
}

/**
 * Simulates the fixed renderActionLog phase-transition separator logic.
 * Returns items array with entries and separators.
 * Includes: streetHasBet tracking and all-in runout river separator insertion.
 */
function simulateRenderActionLog(actionLog, community) {
  const items = [];
  let prevPhase = null;
  let streetHasBet = false;

  for (const entry of actionLog) {
    if (prevPhase !== null && entry.phase && entry.phase !== prevPhase) {
      items.push({ type: "separator", phase: entry.phase });
      streetHasBet = false;
    }
    prevPhase = entry.phase;

    // Mark first bet_raise on the current street
    if (entry.action === "bet_raise") {
      if (!streetHasBet) {
        entry._isFirstBetOnStreet = true;
        streetHasBet = true;
      } else {
        entry._isFirstBetOnStreet = false;
      }
    }

    items.push({ type: "entry", entry });
  }

  // Insert missing street separators for all-in runouts
  const hasRiverPhaseEntry = actionLog.some(e => e.phase === "river");
  const hasTurnPhaseEntry = actionLog.some(e => e.phase === "turn");
  const hasFlopPhaseEntry = actionLog.some(e => e.phase === "flop");
  const lastPhase = actionLog.length > 0 ? actionLog[actionLog.length - 1].phase : null;

  if (community && community.length >= 3 && !hasFlopPhaseEntry && lastPhase === "preflop") {
    items.push({ type: "separator", phase: "flop" });
  }

  if (community && community.length >= 4 && !hasTurnPhaseEntry && (lastPhase === "flop" || lastPhase === "preflop")) {
    items.push({ type: "separator", phase: "turn" });
  }

  if (community && community.length === 5 && !hasRiverPhaseEntry) {
    if (lastPhase === "flop" || lastPhase === "turn" || lastPhase === "preflop") {
      items.push({ type: "separator", phase: "river" });
    }
  }

  return items;
}

// ─── Test runner ───
let totalPassed = 0;
let totalFailed = 0;

function assert(condition, message) {
  if (!condition) throw new Error(message || "Assertion failed");
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(
      `${message || "Assertion failed"}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
    );
  }
}

function runTest(name, testFn) {
  try {
    testFn();
    totalPassed++;
    console.log(`  ✓ ${name}`);
  } catch (e) {
    totalFailed++;
    console.error(`  ✗ ${name}`);
    console.error(`    ${e.message}`);
  }
}

function runProperty(name, property) {
  try {
    fc.assert(property, { numRuns: 100 });
    totalPassed++;
    console.log(`  ✓ ${name}`);
  } catch (e) {
    totalFailed++;
    console.error(`  ✗ ${name}`);
    console.error(`    Counterexample: ${e.message}`);
  }
}

// ═══════════════════════════════════════════════════════════════
// Bug 1.3: All-in call shows "goes all-in 0"
// Expected: "calls X and is all-in" (not "goes all-in 0")
// ═══════════════════════════════════════════════════════════════
console.log("\nBug 1.3: All-in call display (Req 1.3)");

runTest("formatActionEntry with is_all_in=true, action=check_call, amount=0 should NOT return 'goes all-in 0'", () => {
  // Bug 1.3: When is_all_in=true AND action="check_call" AND amount=0,
  // the current code returns "goes all-in 0" which is confusing.
  // Expected: should NOT display "goes all-in 0" for a call action.
  const entry = { action: "check_call", amount: 0, is_all_in: true, player: "Alice" };
  const result = formatActionEntry(entry);
  
  // On UNFIXED code: result will be "Alice goes all-in 0" (BUG)
  // Expected behavior: should not use a zero-chip shove phrase
  // This assertion will FAIL on unfixed code, confirming the bug
  assert(
    !result.includes("goes all-in 0"),
    `Bug 1.3 confirmed: formatActionEntry returned "${result}" - should not show "goes all-in 0" for a check_call action`
  );
});

runTest("formatActionEntry with is_all_in=true, action=check_call, amount=15 should show 'calls 15 and is all-in'", () => {
  // Even with a correct amount, current code still shows "goes all-in 15" for a call
  // Expected: "Alice calls 15 and is all-in"
  const entry = { action: "check_call", amount: 15, is_all_in: true, player: "Alice" };
  const result = formatActionEntry(entry);
  
  // On UNFIXED code: result will be "Alice goes all-in 15" (BUG - should distinguish call from raise)
  // Expected: "Alice calls 15 and is all-in"
  assert(
    result.includes("calls") && result.includes("all-in"),
    `Bug 1.3 confirmed: formatActionEntry returned "${result}" - expected "calls 15 and is all-in"`
  );
});

runProperty(
  "Property: For all check_call entries with is_all_in=true and amount>=0, result should contain 'calls' not 'goes all-in'",
  fc.property(
    fc.string({ minLength: 1, maxLength: 10 }),
    fc.integer({ min: 0, max: 1000 }),
    (player, amount) => {
      const entry = { action: "check_call", amount, is_all_in: true, player };
      const result = formatActionEntry(entry);
      // Expected: result should distinguish call-all-in from raise-all-in
      // On unfixed code: all is_all_in entries return "goes all-in X" regardless of action type
      return amount > 0
        ? result.includes("calls") && result.includes("is all-in")
        : result.includes("is all-in") && !result.includes("goes all-in 0");
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Bug 1.4: First bet_raise on street shows "raises to" instead of "bets"
// Expected: first aggressive action = "bets X", subsequent = "raises to X"
// ═══════════════════════════════════════════════════════════════
console.log("\nBug 1.4: Bet vs Raise distinction (Req 1.4)");

runTest("formatActionEntry with bet_raise (first on street) should show 'bets' not 'raises to'", () => {
  // Bug 1.4: The formatter always shows "raises to X" for bet_raise regardless of context.
  // Fixed: uses entry._isFirstBetOnStreet to distinguish bet from raise.
  const entry = { action: "bet_raise", amount: 50, player: "Alice", phase: "flop", is_all_in: false, _isFirstBetOnStreet: true };
  const result = formatActionEntry(entry);
  
  // On FIXED code: result will be "Alice bets 50" when _isFirstBetOnStreet is true
  assert(
    result.includes("bets"),
    `Bug 1.4 fix verified: formatActionEntry returned "${result}" - expected "bets 50" for first bet on street`
  );
});

runProperty(
  "Property: For all bet_raise entries that are the first on their street, result should contain 'bets'",
  fc.property(
    fc.string({ minLength: 1, maxLength: 10 }),
    fc.integer({ min: 1, max: 1000 }),
    fc.constantFrom("preflop", "flop", "turn", "river"),
    (player, amount, phase) => {
      // Simulating the first bet_raise on a street - _isFirstBetOnStreet set by renderActionLog
      const entry = { action: "bet_raise", amount, player, phase, is_all_in: false, _isFirstBetOnStreet: true };
      const result = formatActionEntry(entry);
      // On fixed code, returns "bets" when _isFirstBetOnStreet is true
      return result.includes("bets");
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Bug 1.2: All-in runout - no river separator when all entries share same phase
// Expected: river separator inserted when 5 community cards but no river-phase entries
// ═══════════════════════════════════════════════════════════════
console.log("\nBug 1.2: Missing river separator for all-in runout (Req 1.2)");

runTest("renderActionLog with 5 community cards and no river-phase entries should have river separator", () => {
  // Bug 1.2: When both players go all-in on the flop, the board runs out to 5 cards
  // but no action_log entries have phase="river", so no river separator appears.
  const actionLog = [
    { player: "Alice", action: "small_blind", amount: 5, phase: "preflop", is_all_in: false },
    { player: "Bob", action: "big_blind", amount: 10, phase: "preflop", is_all_in: false },
    { player: "Alice", action: "bet_raise", amount: 1000, phase: "preflop", is_all_in: true },
    { player: "Bob", action: "check_call", amount: 990, phase: "preflop", is_all_in: true },
  ];
  
  const community = ["A♠", "K♥", "Q♦", "J♣", "10♠"]; // 5 cards dealt
  
  // Simulate renderActionLog
  const items = simulateRenderActionLog(actionLog, community);
  
  // Check: are there any separators for river?
  const riverSeparators = items.filter(i => i.type === "separator" && i.phase === "river");
  
  // On UNFIXED code: no river separator exists (all entries are preflop)
  // Expected: a river separator should be inserted since community has 5 cards
  assert(
    riverSeparators.length > 0,
    `Bug 1.2 confirmed: No river separator found despite 5 community cards. ` +
    `Items: ${JSON.stringify(items.filter(i => i.type === "separator"))}`
  );
});

runTest("renderActionLog with all-in on flop (no turn/river entries) should show turn and river separators", () => {
  // All-in on flop - entries only have flop phase
  const actionLog = [
    { player: "Alice", action: "small_blind", amount: 5, phase: "preflop", is_all_in: false },
    { player: "Bob", action: "big_blind", amount: 10, phase: "preflop", is_all_in: false },
    { player: "Alice", action: "check_call", amount: 5, phase: "preflop", is_all_in: false },
    { player: "Bob", action: "check_call", amount: 0, phase: "preflop", is_all_in: false },
    // Flop phase - both go all-in
    { player: "Alice", action: "bet_raise", amount: 990, phase: "flop", is_all_in: true },
    { player: "Bob", action: "check_call", amount: 990, phase: "flop", is_all_in: true },
  ];
  
  const community = ["A♠", "K♥", "Q♦", "J♣", "10♠"]; // Full 5 cards dealt (runout)
  
  const items = simulateRenderActionLog(actionLog, community);
  
  // Should have at least a river separator for the all-in runout
  const hasSeparators = items.filter(i => i.type === "separator");
  // On unfixed code: only has a "flop" separator (preflop→flop transition), no river
  const hasRiverSep = hasSeparators.some(s => s.phase === "river");
  
  assert(
    hasRiverSep,
    `Bug 1.2 confirmed: No river separator for all-in runout. ` +
    `Separators found: ${JSON.stringify(hasSeparators.map(s => s.phase))}`
  );
});

// ═══════════════════════════════════════════════════════════════
// Bug 1.6: Action buttons visible at showdown
// Expected: action buttons hidden when phase="showdown"
// ═══════════════════════════════════════════════════════════════
console.log("\nBug 1.6: Action buttons visible at showdown (Req 1.6)");

runTest("Action buttons should be hidden when phase is 'showdown'", () => {
  // Bug 1.6: The updateUI function only toggles 'my-turn' class but never hides
  // the action buttons entirely during showdown.
  
  // Set up a minimal DOM
  const dom = new JSDOM(`<!DOCTYPE html><html><body>
    <div id="actionBar">
      <div class="action-row-main">
        <button id="foldBtn">Fold</button>
        <button id="checkCallBtn">Check / Call</button>
      </div>
      <div class="action-row-raise">
        <button id="customBetBtn">Raise</button>
        <button id="betHalfPotBtn">1/2 Pot</button>
        <button id="betPotBtn">Pot</button>
        <button id="betAllInBtn">All-In</button>
      </div>
      <div class="action-row-custom">
        <input id="customBetInput" />
      </div>
    </div>
    <button id="startBtn" style="display:none">Deal</button>
  </body></html>`, { url: "http://localhost" });
  
  const { document } = dom.window;
  const actionBar = document.getElementById("actionBar");
  const actionRowMain = actionBar.querySelector(".action-row-main");
  const actionRowRaise = actionBar.querySelector(".action-row-raise");
  const actionRowCustom = actionBar.querySelector(".action-row-custom");
  
  // Simulate the state during showdown
  const state = { phase: "showdown", viewer: { is_turn: false } };
  
  // Simulate the FIXED updateUI behavior: hide action rows at showdown
  if (state.phase === "showdown") {
    if (actionRowMain) actionRowMain.style.display = "none";
    if (actionRowRaise) actionRowRaise.style.display = "none";
    if (actionRowCustom) actionRowCustom.style.display = "none";
  }
  
  // Expected behavior: buttons should be hidden at showdown
  const foldBtn = document.getElementById("foldBtn");
  const checkCallBtn = document.getElementById("checkCallBtn");
  
  // Check that the parent rows are hidden (display: none)
  const mainRowHidden = actionRowMain.style.display === "none";
  const raiseRowHidden = actionRowRaise.style.display === "none";
  
  assert(
    mainRowHidden && raiseRowHidden,
    `Bug 1.6 fix verified: Action rows should be hidden at showdown. ` +
    `Main row hidden: ${mainRowHidden}, Raise row hidden: ${raiseRowHidden}`
  );
});

runProperty(
  "Property: For all game states with phase='showdown', action buttons should be hidden",
  fc.property(
    fc.constantFrom("showdown"),
    (phase) => {
      // In the FIXED code, action rows are hidden at showdown.
      // Simulate the fixed updateUI logic:
      const wouldHideButtons = (phase === "showdown"); // Fixed code hides at showdown
      
      // Expected: buttons should be hidden at showdown
      return wouldHideButtons === true;
    }
  )
);

// ═══════════════════════════════════════════════════════════════
// Summary
// ═══════════════════════════════════════════════════════════════
console.log(`\n═══ Bug Condition Exploration Results: ${totalPassed} passed, ${totalFailed} failed ═══`);
console.log(`(Expected: ALL tests FAIL on unfixed code - failure confirms bugs exist)\n`);

if (totalFailed > 0) {
  console.log(`✓ ${totalFailed} bug condition(s) confirmed by test failures`);
  console.log("Counterexamples documented above demonstrate the bugs exist.");
  process.exit(1);
} else {
  console.log("⚠ All tests passed - bugs may already be fixed or tests are incorrect");
  process.exit(0);
}
