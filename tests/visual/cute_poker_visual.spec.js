const { test, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

function artifactPath(testInfo, name) {
  const dir = path.join(testInfo.project.outputDir, "visual-artifacts");
  fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, name);
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
  community: ["A♠", "K♥", "10♥", "7♣", "2♦"],
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
      cards: ["A♦", "A♣"],
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
      best_cards: ["A♦", "A♣", "K♥", "10♥", "7♣"],
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
  action_log: [
    { player: "Nemo", action: "small_blind", amount: 5, phase: "preflop", is_all_in: false },
    { player: "Dindybot", action: "big_blind", amount: 10, phase: "preflop", is_all_in: false },
    { player: "Papperbot", action: "check_call", amount: 10, phase: "preflop", is_all_in: false },
    { player: "Nemo", action: "bet_raise", amount: 420, phase: "flop", is_all_in: false },
    { player: "Dindybot", action: "check_call", amount: 410, phase: "flop", is_all_in: true },
  ],
};

test("showdown visual smoke renders panel, cards, chips, and glow", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.evaluate((state) => {
    document.getElementById("connectScreen").classList.add("hidden");
    document.getElementById("gameScreen").classList.remove("hidden");
    window.renderState(state);
  }, showdownState);

  await expect(page.locator("#postHandPanel")).toBeVisible();
  await expect(page.locator("#postHandTitle")).toContainText("Nemo wins 840");
  await expect(page.locator(".post-hand-row.winner")).toHaveCount(1);
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

  await page.waitForTimeout(750);

  const screenshot = await page.screenshot({
    path: artifactPath(testInfo, `showdown-${testInfo.project.name}.png`),
    fullPage: false,
  });
  expect(screenshot.length).toBeGreaterThan(10_000);
});
