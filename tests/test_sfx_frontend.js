const assert = require("assert");

const { createPokerSfx, mapActionToSound } = require("../static/sfx.js");

function mockStorage() {
  const store = {};
  return {
    getItem(key) {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
    },
    setItem(key, value) {
      store[key] = String(value);
    },
  };
}

function makeState(overrides = {}) {
  return {
    room_id: "ROOM1",
    hands_played: 1,
    phase: "preflop",
    community: [],
    winners: [],
    action_log: [],
    action_timer_active: false,
    action_timer_player_id: "",
    action_timer_remaining_seconds: 0,
    ...overrides,
  };
}

function run() {
  assert.strictEqual(mapActionToSound({ action: "ante" }), "chip_quiet");
  assert.strictEqual(mapActionToSound({ action: "small_blind" }), "chip_quiet");
  assert.strictEqual(mapActionToSound({ action: "check_call", amount: 0 }), "check");
  assert.strictEqual(mapActionToSound({ action: "check_call", amount: 15 }), "call");
  assert.strictEqual(mapActionToSound({ action: "bet_raise" }), "bet_raise");
  assert.strictEqual(mapActionToSound({ action: "bet_raise", is_all_in: true }), "all_in");
  assert.strictEqual(mapActionToSound({ action: "fold" }), "fold");
  assert.strictEqual(mapActionToSound({ action: "showdown" }), "showdown");
  assert.strictEqual(mapActionToSound({ action: "pot_win" }), "pot_win");

  const played = [];
  const sfx = createPokerSfx({
    storage: mockStorage(),
    audioContextCtor: null,
    playback: (name, meta) => {
      played.push({ name, meta });
    },
  });

  sfx.setEnabled(true);
  sfx.setVolume(0.25);

  const first = makeState({
    action_log: [
      { action: "small_blind" },
      { action: "check_call", amount: 0 },
      { action: "bet_raise", amount: 60 },
    ],
  });
  sfx.processState(first, { previousState: null, historyReviewDisplay: false });
  assert.deepStrictEqual(played.map(item => item.name), ["chip_quiet", "check", "bet_raise"]);

  sfx.processState(first, { previousState: first, historyReviewDisplay: false });
  assert.deepStrictEqual(played.map(item => item.name), ["chip_quiet", "check", "bet_raise"]);

  const next = makeState({
    action_log: [
      { action: "small_blind" },
      { action: "check_call", amount: 0 },
      { action: "bet_raise", amount: 60 },
      { action: "check_call", amount: 15 },
    ],
  });
  sfx.processState(next, { previousState: first, historyReviewDisplay: false });
  assert.deepStrictEqual(played.map(item => item.name), ["chip_quiet", "check", "bet_raise", "call"]);

  const reviewState = makeState({
    room_id: "ROOM2",
    hands_played: 7,
    action_log: [
      { action: "fold" },
      { action: "check_call", amount: 30 },
    ],
  });
  const reviewPlayed = [];
  const reviewSfx = createPokerSfx({
    storage: mockStorage(),
    audioContextCtor: null,
    playback: (name, meta) => {
      reviewPlayed.push(name);
    },
  });
  reviewSfx.processState(reviewState, { previousState: null, historyReviewDisplay: true });
  reviewSfx.processState(reviewState, { previousState: reviewState, historyReviewDisplay: false });
  assert.deepStrictEqual(reviewPlayed, []);

  const handFlip = makeState({
    room_id: "ROOM1",
    hands_played: 2,
    action_log: [{ action: "small_blind" }],
  });
  sfx.processState(handFlip, { previousState: next, historyReviewDisplay: false });
  assert.deepStrictEqual(played.map(item => item.name), ["chip_quiet", "check", "bet_raise", "call", "chip_quiet"]);
}

run();
console.log("test_sfx_frontend.js passed");
