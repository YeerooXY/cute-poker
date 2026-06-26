const { test, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

function artifactPath(testInfo, name) {
  const dir = path.join(testInfo.project.outputDir, "visual-artifacts");
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, name);
}

function showGameWithState(page, state) {
  return page.evaluate((nextState) => {
    document.getElementById("connectScreen").classList.add("hidden");
    document.getElementById("gameScreen").classList.remove("hidden");
    window.renderState(nextState);
  }, state);
}

async function waitForVisualSettle(page) {
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready.catch(() => {});
    }

    const finiteAnimations = document.getAnimations()
      .filter(animation => {
        const timing = animation.effect && animation.effect.getTiming
          ? animation.effect.getTiming()
          : null;
        return timing && timing.iterations !== Infinity;
      });

    await Promise.all(finiteAnimations.map(animation =>
      animation.finished.catch(() => {})
    ));
  });

  // One extra frame cushion for layout/paint after animations finish.
  await page.waitForTimeout(150);
}

const showdownState = {
  room_id: "VISUAL",
  paused: false,
  phase: "showdown",
  pot: 840,
  small_blind: 5,
  big_blind: 10,
  ante: 0,
  ante_mode: "classic",
  blind_increase_hands: 0,
  hands_played: 7,
  current_bet: 0,
  min_raise: 10,
  community: ["A♠", "K♥", "10♥", "7♥", "2♦"],
  messages: [],
  viewer: {
    is_turn: false,
    is_admin: true,
    to_call: 0,
    committed: 0,
    stack: 1180,
  },
  players: [
    {
      player_id: "p1",
      name: "Nemo",
      avatar: "🎭",
      seat: 1,
      stack: 1180,
      committed: 0,
      cards: ["A♥", "Q♥"],
      is_you: true,
      is_turn: false,
      is_dealer: true,
      is_bot: false,
      all_in: false,
      folded: false,
      connected: true,
      sitting_out: false,
      is_spectator: false,
      hand_name: "Flush",
      hand_detail: "Ace-high Flush",
      best_cards: ["A♥", "K♥", "Q♥", "10♥", "7♥"],
    },
    {
      player_id: "p2",
      name: "Dindybot",
      avatar: "🤖",
      seat: 2,
      stack: 0,
      committed: 420,
      cards: ["J♥", "9♥"],
      is_you: false,
      is_turn: false,
      is_dealer: false,
      is_bot: true,
      all_in: true,
      folded: false,
      connected: true,
      sitting_out: false,
      is_spectator: false,
      hand_name: "Flush",
      hand_detail: "King-high Flush",
      best_cards: ["K♥", "J♥", "10♥", "9♥", "7♥"],
    },
    {
      player_id: "p3",
      name: "Papperbot",
      avatar: "💎",
      seat: 3,
      stack: 920,
      committed: 0,
      cards: ["A♦", "K♣"],
      is_you: false,
      is_turn: false,
      is_dealer: false,
      is_bot: true,
      all_in: false,
      folded: false,
      connected: true,
      sitting_out: false,
      is_spectator: false,
      hand_name: "One Pair",
      hand_detail: "Pair of Aces",
      best_cards: ["A♦", "A♣", "K♥", "10♥", "7♥"],
    },
  ],
  winners: [
    {
      name: "Nemo",
      amount: 840,
      hand_name: "Flush",
      hand_detail: "Ace-high Flush",
      reason: "Best hand at showdown",
    },
  ],
    hand_deltas: {
    Nemo: 420,
    Dindybot: -420,
    Papperbot: 0,
  },
action_log: [
    { player: "Nemo", action: "small_blind", amount: 5, phase: "preflop", is_all_in: false },
    { player: "Dindybot", action: "big_blind", amount: 10, phase: "preflop", is_all_in: false },
    { player: "Papperbot", action: "check_call", amount: 10, phase: "preflop", is_all_in: false },
    { player: "Nemo", action: "bet_raise", amount: 420, phase: "flop", is_all_in: false },
    { player: "Dindybot", action: "check_call", amount: 410, phase: "flop", is_all_in: true },
  ],
};

const actionLogEdgeState = {
  ...showdownState,
  room_id: "EDGE",
  pot: 1246,
  hands_played: 8,
  community: ["A♠", "K♥", "10♥", "7♥", "2♦"],
  viewer: {
    ...showdownState.viewer,
    is_turn: false,
    to_call: 0,
  },
  players: [
    {
      ...showdownState.players[0],
      name: "SmallBlind",
      player_id: "sb",
      stack: 1175,
      committed: 0,
      hand_name: "",
      hand_detail: "",
      best_cards: [],
    },
    {
      ...showdownState.players[1],
      name: "Dindybot",
      player_id: "dindy",
      stack: 362,
      committed: 0,
      all_in: false,
      hand_name: "Flush",
      hand_detail: "King-high Flush",
      best_cards: ["K♥", "J♥", "10♥", "9♥", "7♥"],
    },
    {
      ...showdownState.players[2],
      name: "Papperbot",
      player_id: "papper",
      stack: 0,
      committed: 0,
      all_in: true,
      hand_name: "Two Pair",
      hand_detail: "Aces and Kings",
      best_cards: ["A♦", "A♠", "K♥", "K♣", "10♥"],
    },
  ],
  winners: [
    {
      name: "Dindybot",
      amount: 1246,
      hand_name: "Flush",
      hand_detail: "King-high Flush",
      reason: "Best hand at showdown",
    },
  ],
    hand_deltas: {
    Dindybot: 638,
    Papperbot: -628,
    SmallBlind: -10,
  },
action_log: [
    { player: "SmallBlind", action: "small_blind", amount: 5, phase: "preflop", is_all_in: false },
    { player: "Dindybot", action: "big_blind", amount: 10, phase: "preflop", is_all_in: false },
    { player: "SmallBlind", action: "check_call", amount: 5, phase: "preflop", is_all_in: false },
    { player: "Papperbot", action: "bet_raise", amount: 628, phase: "flop", is_all_in: true },
    { player: "Dindybot", action: "check_call", amount: 618, phase: "flop", is_all_in: false },
    { player: "SmallBlind", action: "fold", amount: 0, phase: "flop", is_all_in: false },
  ],
};

test("showdown visual smoke renders panel, cards, chips, and glow", async ({ page }, testInfo) => {
  await page.goto("/");
  await showGameWithState(page, showdownState);

  await expect(page.locator("#postHandPanel")).toBeVisible();
  await expect(page.locator("#postHandPanel")).toHaveClass(/post-hand-modal/);
  await expect(page.locator("#yourHandBar")).toHaveClass(/hand-bar-hidden/);
  await expect(page.locator(".playing-card .card-rank")).not.toHaveCount(0);
  await expect(page.locator("#postHandTitle")).toContainText("Nemo wins 840");
  await expect(page.locator(".post-hand-row.winner")).toHaveCount(1);
  await expect(page.locator(".post-hand-row").first().locator(".post-hand-name")).toContainText("Nemo");
  await expect(page.locator(".table-felt")).toHaveClass(/showdown-table-glow/);
  await expect(page.locator(".player-seat.showdown-winner-glow")).toHaveCount(1);
  await expect(page.locator("#community .playing-card")).toHaveCount(5);
  await expect(page.locator("#potChips .chip-item")).not.toHaveCount(0);
  await expect(page.locator(".seat-chips .chip-item")).not.toHaveCount(0);

  if (page.viewportSize().width <= 768) {
    await expect(page.locator("#actionLogPanel")).toHaveClass(/collapsed/);
    const panelZ = await page.locator("#postHandPanel").evaluate(el => Number(getComputedStyle(el).zIndex));
    const adminZ = await page.locator("#adminActions").evaluate(el => Number(getComputedStyle(el).zIndex));
    expect(panelZ).toBeGreaterThan(adminZ);
  } else {
    await expect(page.locator("#actionLogPanel")).not.toHaveClass(/collapsed/);
  }

  const panelBox = await page.locator("#postHandPanel").boundingBox();
  const actionBarBox = await page.locator("#actionBar").boundingBox();
  expect(panelBox).toBeTruthy();
  expect(actionBarBox).toBeTruthy();
  expect(panelBox.y + panelBox.height).toBeLessThanOrEqual(actionBarBox.y + 4);

  await waitForVisualSettle(page);

  const screenshot = await page.screenshot({
    path: artifactPath(testInfo, `showdown-${testInfo.project.name}.png`),
    fullPage: false,
  });
  expect(screenshot.length).toBeGreaterThan(10_000);
});

test("action log visual smoke covers returned excess, showdown rows, and runout separators", async ({ page }, testInfo) => {
  await page.goto("/");
  await showGameWithState(page, actionLogEdgeState);

  const logText = await page.locator("#actionLogBody").innerText();
  expect(logText).toContain("SmallBlind folds");
  expect(logText).not.toContain("SmallBlind checks");
  expect(logText).toContain("Dindybot calls 618");
  expect(logText).not.toContain("Dindybot goes all-in");
  expect(logText).toContain("River:");
  expect(logText).toContain("Showdown");
  expect(logText).toContain("Dindybot: King-high Flush");
  expect(logText).toContain("— wins");
  expect(logText).toContain("Dindybot wins 1246 with King-high Flush");

  await expect(page.locator(".action-row-main")).toBeHidden();
  await expect(page.locator(".action-row-raise")).toBeHidden();
  await expect(page.locator(".action-row-custom")).toBeHidden();
  await expect(page.locator(".showdown-hand.showdown-winner-hand")).toHaveCount(1);
  await expect(page.locator(".post-hand-row").first().locator(".post-hand-name")).toContainText("Dindybot");
  await expect(page.locator(".post-hand-row").first().locator(".post-hand-amount")).toContainText("+638");
  await expect(page.locator(".post-hand-row").filter({ hasText: "Papperbot" }).locator(".post-hand-amount")).toContainText("-628");
  const smallBlindRow = page.locator(".post-hand-row").filter({ hasText: "SmallBlind" });
  await expect(smallBlindRow.locator(".post-hand-amount")).toContainText("-10");
  await expect(smallBlindRow.locator(".post-hand-result")).toContainText("mucked");
  await expect(smallBlindRow.locator(".post-hand-breakdown")).toHaveCount(0);
  await expect(page.locator("#postHandTitle")).toContainText("Dindybot wins 1246");
  await expect(page.locator(".post-hand-row").first().locator(".post-hand-detail")).toContainText("King-high Flush");
  await expect(page.locator(".post-hand-row").first().locator(".post-hand-breakdown")).toContainText("Best 5 from 7");
  await expect(page.locator("#yourHandBar")).toHaveClass(/hand-bar-hidden/);
  await expect(page.locator(".playing-card .card-rank")).not.toHaveCount(0);

  await waitForVisualSettle(page);

  const screenshot = await page.screenshot({
    path: artifactPath(testInfo, `action-log-edge-${testInfo.project.name}.png`),
    fullPage: false,
  });
  expect(screenshot.length).toBeGreaterThan(10_000);
});

const foldedRevealOwnerHiddenState = {
  ...actionLogEdgeState,
  room_id: "REVEAL-HIDDEN",
  allow_folded_reveals: true,
  players: actionLogEdgeState.players.map(p => p.name === "SmallBlind"
    ? {
        ...p,
        is_you: true,
        cards: ["A♥", "Q♥"],
        folded: true,
        folded_reveal_mode: "hidden",
        can_reveal_folded_hand: true,
      }
    : { ...p, is_you: false }
  ),
};

const foldedRevealLeftState = {
  ...foldedRevealOwnerHiddenState,
  room_id: "REVEAL-LEFT",
  players: foldedRevealOwnerHiddenState.players.map(p => p.name === "SmallBlind"
    ? {
        ...p,
        folded_reveal_mode: "left",
        can_reveal_folded_hand: true,
      }
    : p
  ),
};

const foldedRevealBothState = {
  ...foldedRevealOwnerHiddenState,
  room_id: "REVEAL-BOTH",
  players: foldedRevealOwnerHiddenState.players.map(p => p.name === "SmallBlind"
    ? {
        ...p,
        folded_reveal_mode: "both",
        can_reveal_folded_hand: false,
        would_have_hand_name: "Flush",
        would_have_hand_detail: "Ace-high Flush",
        would_have_best_cards: ["A♥", "K♥", "Q♥", "10♥", "7♥"],
      }
    : p
  ),
};

test("folded owner gets reveal controls and both-revealed hand gets would-have breakdown", async ({ page }) => {
  await page.goto("/");
  await showGameWithState(page, foldedRevealOwnerHiddenState);

  const hiddenRow = page.locator(".post-hand-row").filter({ hasText: "SmallBlind" });
  await expect(hiddenRow.locator(".post-hand-detail")).toContainText("Folded hand hidden");
  await expect(hiddenRow.locator(".playing-card.card-back")).toHaveCount(2);
  await expect(hiddenRow.locator("[data-folded-reveal='left']")).toHaveCount(1);
  await expect(hiddenRow.locator("[data-folded-reveal='right']")).toHaveCount(1);
  await expect(hiddenRow.locator("[data-folded-reveal='both']")).toHaveCount(1);
  await expect(hiddenRow.locator("[data-folded-reveal='muck']")).toHaveCount(1);
  await expect(hiddenRow.locator(".post-hand-breakdown")).toHaveCount(0);

  await showGameWithState(page, foldedRevealLeftState);

  const leftRow = page.locator(".post-hand-row").filter({ hasText: "SmallBlind" });
  await expect(leftRow.locator(".post-hand-detail")).toContainText("Revealed one card");
  await expect(leftRow.locator(".post-hand-cards .playing-card.card-back")).toHaveCount(1);
  await expect(leftRow.locator(".post-hand-cards")).toContainText("A");
  await expect(leftRow.locator(".post-hand-cards")).toContainText("♥");
  await expect(leftRow.locator(".post-hand-breakdown")).toHaveCount(0);

  await showGameWithState(page, foldedRevealBothState);

  const revealedRow = page.locator(".post-hand-row").filter({ hasText: "SmallBlind" });
  await expect(revealedRow.locator(".post-hand-detail")).toContainText("Would have made Ace-high Flush");
  await expect(revealedRow.locator(".post-hand-cards .playing-card.card-back")).toHaveCount(0);
  await expect(revealedRow.locator(".post-hand-cards")).toContainText("A");
  await expect(revealedRow.locator(".post-hand-cards")).toContainText("Q");
  await expect(revealedRow.locator(".post-hand-cards")).toContainText("♥");
  await expect(revealedRow.locator(".post-hand-breakdown")).toContainText("Best 5 from 7");
  await expect(revealedRow.locator("[data-folded-reveal]")).toHaveCount(0);
});
