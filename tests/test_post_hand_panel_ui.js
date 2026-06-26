// Unit tests for the showdown post-hand summary panel.

const { JSDOM } = require("jsdom");

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

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function makeCardHtml(card) {
  const red = card.includes("H") || card.includes("D") ? " red" : "";
  return `<div class="playing-card${red}">${esc(card)}</div>`;
}

function formatWinnerEntry(winner) {
  if (winner.hand_name && winner.reason !== "Everyone else folded") {
    const detail = winner.hand_detail || winner.hand_name;
    return `${winner.name} wins ${winner.amount} with ${detail}`;
  }
  return `${winner.name} wins ${winner.amount}`;
}

function formatPostHandTitle(winners) {
  if (!winners || winners.length === 0) return "Hand complete";
  if (winners.length === 1) return formatWinnerEntry(winners[0]);
  const names = winners.map(w => w.name).join(", ");
  const total = winners.reduce((sum, w) => sum + (Number(w.amount) || 0), 0);
  return `${names} split ${total}`;
}

function createHarness() {
  const dom = new JSDOM(`<!doctype html><body>
    <div id="postHandPanel" class="post-hand-panel hidden">
      <div id="postHandKicker"></div>
      <div id="postHandTitle"></div>
      <div id="postHandPot"></div>
      <div id="postHandBody"></div>
    </div>
  </body>`);
  const document = dom.window.document;
  const els = {
    postHandPanel: document.getElementById("postHandPanel"),
    postHandKicker: document.getElementById("postHandKicker"),
    postHandTitle: document.getElementById("postHandTitle"),
    postHandPot: document.getElementById("postHandPot"),
    postHandBody: document.getElementById("postHandBody"),
  };

  function renderPostHandPanel(state) {
    const winners = Array.isArray(state.winners) ? state.winners : [];
    const visible = state.phase === "showdown" && winners.length > 0;

    els.postHandPanel.classList.toggle("hidden", !visible);
    if (!visible) {
      els.postHandTitle.textContent = "";
      els.postHandPot.textContent = "";
      els.postHandBody.innerHTML = "";
      return;
    }

    els.postHandKicker.textContent = winners.length > 1 ? "Split pot" : "Hand complete";
    els.postHandTitle.textContent = formatPostHandTitle(winners);
    els.postHandPot.textContent = `Final pot ${state.pot || 0}`;

    const winnerNames = new Set(winners.map(w => w.name));
    const revealedPlayers = (state.players || [])
      .filter(p => p.hand_name && p.best_cards && p.best_cards.length > 0 && !p.folded);

    if (revealedPlayers.length === 0) {
      els.postHandBody.innerHTML = winners.map(w => `
        <div class="post-hand-row winner">
          <span class="post-hand-name">${esc(w.name)}</span>
          <span class="post-hand-detail">${esc(w.reason || "wins")}</span>
          <span class="post-hand-amount">+${esc(w.amount || 0)}</span>
        </div>
      `).join("");
      return;
    }

    els.postHandBody.innerHTML = revealedPlayers.map(p => {
      const isWinner = winnerNames.has(p.name);
      const detail = p.hand_detail || p.hand_name;
      const cards = p.best_cards.map(makeCardHtml).join("");
      const result = isWinner ? (winners.length > 1 ? "splits" : "wins") : "shows";
      const won = winners.find(w => w.name === p.name);
      const amount = won ? `+${won.amount}` : "";
      return `
        <div class="post-hand-row${isWinner ? " winner" : ""}">
          <div class="post-hand-player">
            <span class="post-hand-name">${esc(p.name)}</span>
            <span class="post-hand-result">${result}</span>
          </div>
          <div class="post-hand-cards">${cards}</div>
          <div class="post-hand-detail">${esc(detail)}</div>
          <div class="post-hand-amount">${esc(amount)}</div>
        </div>
      `;
    }).join("");
  }

  return { document, els, renderPostHandPanel };
}

runTest("panel is hidden outside showdown", () => {
  const { els, renderPostHandPanel } = createHarness();
  renderPostHandPanel({
    phase: "river",
    pot: 200,
    winners: [{ name: "Ada", amount: 200 }],
    players: [],
  });
  assert(els.postHandPanel.classList.contains("hidden"), "Panel should be hidden");
  assertEqual(els.postHandTitle.textContent, "", "Title should be cleared");
});

runTest("single winner showdown summarizes result and revealed hand", () => {
  const { els, renderPostHandPanel } = createHarness();
  renderPostHandPanel({
    phase: "showdown",
    pot: 420,
    winners: [{
      name: "Ada",
      amount: 420,
      hand_name: "Flush",
      hand_detail: "Ace-high Flush",
      reason: "Best hand at showdown",
    }],
    players: [{
      name: "Ada",
      hand_name: "Flush",
      hand_detail: "Ace-high Flush",
      best_cards: ["AH", "QH", "9H", "5H", "2H"],
      folded: false,
    }, {
      name: "Ben",
      hand_name: "Straight",
      hand_detail: "Ten-high Straight",
      best_cards: ["10S", "9D", "8C", "7H", "6S"],
      folded: false,
    }],
  });

  assert(!els.postHandPanel.classList.contains("hidden"), "Panel should be visible");
  assertEqual(els.postHandPot.textContent, "Final pot 420", "Final pot should be shown");
  assert(els.postHandTitle.textContent.includes("Ada wins 420"), "Winner title should name Ada");
  assert(els.postHandBody.textContent.includes("Ace-high Flush"), "Winner detail should render");
  assert(els.postHandBody.textContent.includes("Ten-high Straight"), "Losing shown hand should render");
  assertEqual(els.postHandBody.querySelectorAll(".post-hand-row.winner").length, 1, "One row should be marked winner");
});

runTest("split pot title and rows use split wording", () => {
  const { els, renderPostHandPanel } = createHarness();
  renderPostHandPanel({
    phase: "showdown",
    pot: 300,
    winners: [
      { name: "Ada", amount: 150, hand_name: "Straight" },
      { name: "Ben", amount: 150, hand_name: "Straight" },
    ],
    players: [
      { name: "Ada", hand_name: "Straight", best_cards: ["AS", "KD", "QH", "JC", "10S"], folded: false },
      { name: "Ben", hand_name: "Straight", best_cards: ["AD", "KS", "QC", "JH", "10D"], folded: false },
    ],
  });

  assertEqual(els.postHandKicker.textContent, "Split pot", "Kicker should describe split");
  assertEqual(els.postHandTitle.textContent, "Ada, Ben split 300", "Title should combine split amounts");
  assertEqual(els.postHandBody.querySelectorAll(".post-hand-row.winner").length, 2, "Both winners should be marked");
  assert(els.postHandBody.textContent.includes("splits"), "Rows should use split wording");
});

console.log(`\nPost-hand panel UI results: ${totalPassed} passed, ${totalFailed} failed`);
if (totalFailed > 0) process.exit(1);
