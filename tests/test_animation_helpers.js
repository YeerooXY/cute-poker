// Unit tests for frontend animation trigger helpers.

let totalPassed = 0;
let totalFailed = 0;

function assert(condition, message) {
  if (!condition) throw new Error(message || "Assertion failed");
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message || "Assertion failed"}: expected ${expected}, got ${actual}`);
  }
}

function assertArrayEqual(actual, expected, message) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) {
    throw new Error(`${message || "Assertion failed"}: expected ${e}, got ${a}`);
  }
}

function runTest(name, testFn) {
  try {
    testFn();
    totalPassed++;
    console.log(`  PASS ${name}`);
  } catch (e) {
    totalFailed++;
    console.error(`  FAIL ${name}`);
    console.error(`    ${e.message}`);
  }
}

function getNewCardFlags(cards, previousCards) {
  const prev = Array.isArray(previousCards) ? previousCards : [];
  return (cards || []).map((card, idx) => prev[idx] !== card);
}

function shouldAnimatePotCountUp(previousState, state) {
  if (!previousState || !state || state.phase === "showdown") return false;
  if (previousState.room_id !== state.room_id) return false;
  if (previousState.hands_played !== state.hands_played) return false;
  const prevPot = Number(previousState.pot);
  const nextPot = Number(state.pot);
  return Number.isFinite(prevPot) && Number.isFinite(nextPot) && nextPot > prevPot;
}

const CHIP_DENOMINATIONS = [1000, 500, 100, 25, 5, 1];

function decomposeChips(amount) {
  let remaining = Math.max(0, Math.floor(Number(amount) || 0));
  const result = [];
  for (const denom of CHIP_DENOMINATIONS) {
    if (remaining >= denom) {
      const count = Math.floor(remaining / denom);
      result.push({ denom, count });
      remaining -= count * denom;
    }
    if (remaining === 0) break;
  }
  return result;
}

function renderChipStackHtml(amount, extraClass = "") {
  const stacks = decomposeChips(amount);
  if (stacks.length === 0) return "";
  const cls = extraClass ? ` chip-stack-animate ${extraClass}` : " chip-stack-animate";
  return `<div class="chip-stack${cls}">` + stacks.map(({ denom, count }) => {
    const visible = Math.min(count, 4);
    const chips = Array.from({ length: visible }, (_, idx) =>
      `<span class="chip-item chip-denom-${denom}" style="--chip-index:${idx}"><span class="chip-label">${denom}</span></span>`
    ).join("");
    const countLabel = count > 4 ? `<span class="chip-count">x${count}</span>` : "";
    return `<span class="denom-stack">${chips}${countLabel}</span>`;
  }).join("") + `</div>`;
}

runTest("new card flags mark appended community cards", () => {
  assertArrayEqual(
    getNewCardFlags(["AS", "KH", "2D"], ["AS"]),
    [false, true, true],
    "Only appended cards should be new"
  );
});

runTest("new card flags mark changed card at same index", () => {
  assertArrayEqual(
    getNewCardFlags(["AS", "QH"], ["AS", "KH"]),
    [false, true],
    "Changed index should be new"
  );
});

runTest("pot count-up triggers only for same hand pot increase", () => {
  const prev = { room_id: "T1", hands_played: 3, phase: "turn", pot: 120 };
  const next = { room_id: "T1", hands_played: 3, phase: "turn", pot: 260 };
  assert(shouldAnimatePotCountUp(prev, next), "Same hand pot increase should animate");
});

runTest("pot count-up does not trigger across hands", () => {
  const prev = { room_id: "T1", hands_played: 3, phase: "showdown", pot: 500 };
  const next = { room_id: "T1", hands_played: 4, phase: "preflop", pot: 15 };
  assertEqual(shouldAnimatePotCountUp(prev, next), false, "New hand reset should not animate");
});

runTest("pot count-up does not trigger during showdown headline replacement", () => {
  const prev = { room_id: "T1", hands_played: 3, phase: "river", pot: 500 };
  const next = { room_id: "T1", hands_played: 3, phase: "showdown", pot: 500 };
  assertEqual(shouldAnimatePotCountUp(prev, next), false, "Showdown text replacement should not animate");
});

runTest("pot count-up does not trigger for decreases or room changes", () => {
  assertEqual(
    shouldAnimatePotCountUp(
      { room_id: "T1", hands_played: 3, phase: "turn", pot: 260 },
      { room_id: "T1", hands_played: 3, phase: "turn", pot: 120 }
    ),
    false,
    "Pot decrease should not animate"
  );
  assertEqual(
    shouldAnimatePotCountUp(
      { room_id: "T1", hands_played: 3, phase: "turn", pot: 120 },
      { room_id: "T2", hands_played: 3, phase: "turn", pot: 260 }
    ),
    false,
    "Different room should not animate"
  );
});

runTest("chip decomposition uses descending denominations and exact total", () => {
  const result = decomposeChips(1631);
  assertArrayEqual(
    result,
    [
      { denom: 1000, count: 1 },
      { denom: 500, count: 1 },
      { denom: 100, count: 1 },
      { denom: 25, count: 1 },
      { denom: 5, count: 1 },
      { denom: 1, count: 1 },
    ],
    "Decomposition should be greedy and exact"
  );
});

runTest("chip stack renderer caps visible chips and keeps count label", () => {
  const html = renderChipStackHtml(5000, "chip-to-pot-in");
  const visibleThousandChips = (html.match(/chip-denom-1000/g) || []).length;
  assertEqual(visibleThousandChips, 4, "Only four repeated chips should render");
  assert(html.includes("x5"), "Renderer should include count label for hidden chips");
  assert(html.includes("chip-to-pot-in"), "Extra animation class should be preserved");
});

console.log(`\nAnimation helper results: ${totalPassed} passed, ${totalFailed} failed`);
if (totalFailed > 0) process.exit(1);
