// ═══════════════════════════════════════════════════════════════
// CUTE POKER – Debug Table Client (minimal, no animations)
// Direct state rendering. No overlays, no animations, no timers.
// ═══════════════════════════════════════════════════════════════

// ─── DOM refs ───
const $ = id => document.getElementById(id);
const els = {};
["status","connectScreen","gameScreen","nameInput","roomInput","createBtn","joinBtn",
"reconnectBtn","roomsList","roomId","phaseBadge","potValue","community","playerPositions",
"winnerOverlay","winnerContent","yourHandBar","yourCards","handStrength","startBtn",
"foldBtn","checkCallBtn","betHalfPotBtn","betPotBtn","betAllInBtn","customBetInput",
"customBetBtn","resetBtn","adminActions","copyRoomBtn","leaveBtn","chatToggle","chatClose",
"chatPanel","chatMessages","chatInput","chatBtn","actionBar","turnInfo",
"pauseBtn","sitOutBtn","spectateBtn","addBotBtn","botDifficultySelect",
"hintsToggle","handHistoryToggle","handHistoryPanel","handHistoryClose","handHistoryBody","handHistoryCount","bbToggleBtn","potChips","autoDealToggle","autoDealCountdown","outsBox",
"actionLogHandNum","actionLogBody","actionLogPanel","actionLogToggle","adminPlayerList","postHandPanel","showdownTray",
"postHandKicker","postHandTitle","postHandPot","postHandBody","postHandDealBtn"
].forEach(id => { els[id] = $(id); });

// ─── State ───
let ws = null;
let roomId = localStorage.getItem("poker_room_id") || "";
let token = localStorage.getItem("poker_token") || "";
let lastState = null;
let potAnimationFrame = null;
let displayedPotAmount = null;
let selectedAvatar = localStorage.getItem("poker_avatar") || "🎭";
let reconnectAttempts = 0;
let reconnectTimer = null;
let intentionalDisconnect = false;
let selectedHistoryHandNumber = null;
let selectedHistoryReviewKey = null;
let defaultPanelsRoomId = null;

const AUTO_DEAL_DELAY_SECONDS = 10;
const AUTO_DEAL_STORAGE_KEY = "poker_auto_deal_enabled";
let autoDealEnabled = localStorage.getItem(AUTO_DEAL_STORAGE_KEY) !== "false";
let autoDealTimerId = null;
let autoDealDeadlineMs = 0;
let autoDealHandKey = "";
let autoDealFiredKey = "";

// ─── Helpers ───
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function parseCard(card) {
  const text = String(card || "");
  if (text === "🂠") return { rank: "🂠", suit: "" };
  const suit = text.slice(-1);
  const rank = text.slice(0, -1);
  return { rank, suit };
}



const DISPLAY_RANK_VALUE = {
  "A": 14,
  "K": 13,
  "Q": 12,
  "J": 11,
  "10": 10,
  "T": 10,
  "9": 9,
  "8": 8,
  "7": 7,
  "6": 6,
  "5": 5,
  "4": 4,
  "3": 3,
  "2": 2,
};

function rankValueForDisplayCard(card) {
  const text = String(card || "");
  if (!text || text === "BACK" || text === "🂠") return -1;
  const rank = text.slice(0, -1);
  return DISPLAY_RANK_VALUE[rank] || -1;
}

function cardRankForDisplay(card) {
  const text = String(card || "");
  if (!text || text === "BACK" || text === "🂠") return "";
  return text.slice(0, -1);
}

function sortCardsHighToLow(cards) {
  return [...(Array.isArray(cards) ? cards : [])].sort((a, b) => {
    const av = rankValueForDisplayCard(a);
    const bv = rankValueForDisplayCard(b);
    if (av !== bv) return bv - av;
    return String(a).localeCompare(String(b));
  });
}

function sortHoleCardsForDisplay(cards) {
  return sortCardsHighToLow(cards);
}

function isWheelStraight(cards) {
  const ranks = new Set((cards || []).map(cardRankForDisplay));
  return ranks.has("A") && ranks.has("5") && ranks.has("4") && ranks.has("3") && ranks.has("2");
}

function sortStraightCardsForDisplay(cards) {
  const sorted = sortCardsHighToLow(cards);
  if (!isWheelStraight(sorted)) return sorted;
  const ace = sorted.find(c => cardRankForDisplay(c) === "A");
  const rest = sorted.filter(c => cardRankForDisplay(c) !== "A");
  return [...rest, ace].filter(Boolean);
}

function groupCardsByRank(cards) {
  const groups = new Map();
  for (const card of cards || []) {
    const rank = cardRankForDisplay(card);
    if (!groups.has(rank)) groups.set(rank, []);
    groups.get(rank).push(card);
  }
  return [...groups.entries()]
    .map(([rank, rankCards]) => ({
      rank,
      value: DISPLAY_RANK_VALUE[rank] || -1,
      cards: sortCardsHighToLow(rankCards),
      count: rankCards.length,
    }))
    .sort((a, b) => {
      if (a.count !== b.count) return b.count - a.count;
      if (a.value !== b.value) return b.value - a.value;
      return String(a.rank).localeCompare(String(b.rank));
    });
}

function sortGroupedMadeHand(cards, countOrder) {
  const groups = groupCardsByRank(cards);
  const result = [];

  for (const wantedCount of countOrder) {
    const matching = groups
      .filter(g => g.count === wantedCount)
      .sort((a, b) => b.value - a.value);

    for (const group of matching) {
      result.push(...group.cards);
    }
  }

  const used = new Set(result);
  const kickers = sortCardsHighToLow((cards || []).filter(card => !used.has(card)));
  return [...result, ...kickers];
}

function sortBestFiveForDisplay(cards, handName = "") {
  const list = Array.isArray(cards) ? cards : [];
  if (list.length <= 1) return list;

  const name = String(handName || "").toLowerCase();

  if (name.includes("straight")) return sortStraightCardsForDisplay(list);
  if (name.includes("flush")) return sortCardsHighToLow(list);
  if (name.includes("four")) return sortGroupedMadeHand(list, [4]);
  if (name.includes("full house")) return sortGroupedMadeHand(list, [3, 2]);
  if (name.includes("three")) return sortGroupedMadeHand(list, [3]);
  if (name.includes("two pair")) return sortGroupedMadeHand(list, [2]);
  if (name.includes("one pair") || name === "pair") return sortGroupedMadeHand(list, [2]);

  return sortCardsHighToLow(list);
}

function makeCardHtml(card, extraClass = "") {
  if (card === "🂠") return '<div class="playing-card card-back">🂠</div>';
  const { rank, suit } = parseCard(card);
  const red = suit === "♥" || suit === "♦" ? " red" : "";
  const extra = extraClass ? ` ${extraClass}` : "";
  return `<div class="playing-card${red}${extra}"><span class="card-rank">${esc(rank)}</span><span class="card-suit">${esc(suit)}</span></div>`;
}

function safeGetItem(key) { try { return localStorage.getItem(key); } catch { return null; } }
function safeSetItem(key, val) { try { localStorage.setItem(key, val); } catch {} }

function getNewCardFlags(cards, previousCards) {
  const prev = Array.isArray(previousCards) ? previousCards : [];
  return (cards || []).map((card, idx) => prev[idx] !== card);
}

function totalCommittedAmount(state) {
  const players = Array.isArray(state && state.players) ? state.players : [];
  return players.reduce((sum, player) => sum + Math.max(0, Number(player && player.committed) || 0), 0);
}

function displayedCenterPotAmount(state) {
  if (!state) return 0;

  const rawPot = Math.max(0, Number(state.pot) || 0);
  const phase = String(state.phase || "").toLowerCase();

  // During active betting, keep the center pot as the settled pot only.
  // Current street commitments remain represented by the floating bet markers.
  if (["preflop", "flop", "turn", "river"].includes(phase)) {
    return Math.max(0, rawPot - totalCommittedAmount(state));
  }

  return rawPot;
}

function shouldAnimatePotCountUp(previousState, state) {
  if (!previousState || !state || state.phase === "showdown") return false;
  if (previousState.room_id !== state.room_id) return false;
  if (previousState.hands_played !== state.hands_played) return false;

  const prevPot = displayedCenterPotAmount(previousState);
  const nextPot = displayedCenterPotAmount(state);
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

function chipRenderModeFromClass(extraClass = "") {
  const cls = String(extraClass || "");
  if (cls.includes("seat-committed-chips")) return "bet-marker";
  if (cls.includes("pot")) return "pot";
  return "default";
}

function compactChipStacks(amount, maxStacks = 2) {
  const stacks = decomposeChips(amount);
  if (stacks.length <= maxStacks) return stacks;

  const result = [];
  if (stacks[0]) result.push(stacks[0]);

  const tail = stacks[stacks.length - 1];
  if (tail && tail.denom !== result[0].denom) {
    result.push(tail);
  }

  return result.slice(0, maxStacks);
}

function renderChipStackHtml(amount, extraClass = "") {
  const total = Math.max(0, Math.floor(Number(amount) || 0));
  if (total <= 0) return "";

  const mode = chipRenderModeFromClass(extraClass);
  const stacks = mode === "default"
    ? compactChipStacks(total, 2)
    : compactChipStacks(total, mode === "pot" ? 2 : 1);

  const wrapperClass = extraClass ? ` chip-stack-animate ${extraClass}` : " chip-stack-animate";
  const visibleLimit = mode === "pot" ? 3 : 2;

  const stacksHtml = stacks.map(({ denom, count }) => {
    const visible = Math.min(count, visibleLimit);
    const chips = Array.from({ length: visible }, (_, idx) => {
      const label = idx === visible - 1 && mode === "pot"
        ? `<span class="chip-label">${denom}</span>`
        : "";
      return `<span class="chip-item chip-denom-${denom}" style="--chip-index:${idx}; --chip-count:${visible}">${label}</span>`;
    }).join("");
    const countLabel = count > visible ? `<span class="chip-count">×${count}</span>` : "";
    return `<span class="denom-stack">${chips}${countLabel}</span>`;
  }).join("");

  return `<div class="chip-stack chip-stack-${mode}${wrapperClass}">${stacksHtml}</div>`;
}

function setPotValue(amount, animate) {
  if (!els.potValue) return;
  const next = Number(amount) || 0;

  if (potAnimationFrame) {
    cancelAnimationFrame(potAnimationFrame);
    potAnimationFrame = null;
  }

  if (!animate || displayedPotAmount === null) {
    displayedPotAmount = next;
    els.potValue.textContent = next;
    els.potValue.classList.remove("pot-counting");
    return;
  }

  const start = displayedPotAmount;
  const delta = next - start;
  const startedAt = performance.now();
  const duration = 360;
  els.potValue.classList.add("pot-counting");

  function tick(now) {
    const t = Math.min(1, (now - startedAt) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    displayedPotAmount = Math.round(start + delta * eased);
    els.potValue.textContent = displayedPotAmount;
    if (t < 1) {
      potAnimationFrame = requestAnimationFrame(tick);
    } else {
      displayedPotAmount = next;
      els.potValue.textContent = next;
      els.potValue.classList.remove("pot-counting");
      potAnimationFrame = null;
    }
  }

  potAnimationFrame = requestAnimationFrame(tick);
}

// ─── Action Log Helpers ───
function formatActionEntry(entry) {
  const player = entry.player || "";
  const amount = entry.amount || 0;

  // Blinds always show their specific verb regardless of all-in status
  if (entry.action === "small_blind") return `${player} posts SB ${amount}`;
  if (entry.action === "big_blind") return `${player} posts BB ${amount}`;
  if (entry.action === "ante") return `${player} posts ante ${amount}`;
  if (entry.action === "big_blind_ante") return `${player} posts BBA ${amount}`;

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

// ─── Name persistence ───
function loadSavedPlayerName() {
  const saved = safeGetItem("poker_player_name");
  if (saved && saved.trim()) els.nameInput.value = saved;
}
function savePlayerName(name) {
  const t = (name || "").trim().slice(0, 20);
  if (t) safeSetItem("poker_player_name", t);
}

// ─── Avatar picker ───
document.querySelectorAll(".avatar-opt").forEach(el => {
  if (el.dataset.av === selectedAvatar) el.classList.add("selected");
  else el.classList.remove("selected");
  el.onclick = () => {
    document.querySelectorAll(".avatar-opt").forEach(e => e.classList.remove("selected"));
    el.classList.add("selected");
    selectedAvatar = el.dataset.av;
    localStorage.setItem("poker_avatar", selectedAvatar);
  };
});

// ─── Room settings / game history toggles ───
document.addEventListener("DOMContentLoaded", () => {
  // Attach auto-scroll listener to action log body
  if (els.actionLogBody) {
    els.actionLogBody.addEventListener("scroll", onActionLogScroll);
  }

  const histHeader = document.querySelector(".game-history-header");
  const histBody = document.querySelector(".game-history-body");
  if (histHeader && histBody) {
    histHeader.addEventListener("click", () => {
      const exp = histHeader.getAttribute("aria-expanded") === "true";
      histHeader.setAttribute("aria-expanded", !exp);
      histBody.classList.toggle("collapsed", exp);
      histBody.classList.toggle("expanded", !exp);
    });
  }
  const settHeader = document.querySelector(".room-settings-header");
  const settBody = document.querySelector(".room-settings-body");
  if (settHeader && settBody) {
    settHeader.addEventListener("click", () => {
      settBody.classList.toggle("collapsed");
    });
  }
});

// ─── Seat positions (8 max) ───
// Position 0 is viewer-relative bottom/hero seat.
const SEAT_POSITIONS = [
  { top: "82%", left: "50%" }, // bottom hero
  { top: "68%", left: "29%" }, // lower-left
  { top: "48%", left: "20%" }, // left
  { top: "27%", left: "31%" }, // upper-left
  { top: "27%", left: "69%" }, // upper-right
  { top: "48%", left: "80%" }, // right
  { top: "68%", left: "71%" }, // lower-right
  { top: "17%", left: "50%" }, // top
];

// Canonical server-seat offsets mapped to visual table positions.
// Offset 0 is always the viewer/bottom seat. Positive offsets follow the
// server's canonical table order, wrapping around from seat 8 back to seat 1.
//
// Visual path: bottom → left side → top center → right side.
const CANONICAL_VISUAL_SEAT_BY_OFFSET = [0, 1, 2, 3, 7, 4, 5, 6];

// Bet/chip marker positions live between each visual seat and the pot.
// These are intentionally separate from SEAT_POSITIONS so player identity
// cards stay compact while committed chips sit "in front" of each player.
const BET_POSITIONS = [
  { top: "68%", left: "50%" }, // bottom hero
  { top: "60%", left: "38%" }, // lower-left
  { top: "49%", left: "33%" }, // left
  { top: "37%", left: "40%" }, // upper-left
  { top: "37%", left: "60%" }, // upper-right
  { top: "49%", left: "67%" }, // right
  { top: "60%", left: "62%" }, // lower-right
  { top: "31%", left: "50%" }, // top
];


function stablePlayerKey(player) {
  if (!player) return "";
  return String(
    player.player_id
    || player.id
    || player.token
    || player.name
    || ""
  );
}

function canonicalSeatNumber(player) {
  if (!player) return null;

  const seat = Number(player.seat);
  if (Number.isInteger(seat) && seat >= 1 && seat <= SEAT_POSITIONS.length) {
    return seat;
  }

  // Future-proof fallback if the backend later exposes a zero-based seat_index.
  const seatIndex = Number(player.seat_index ?? player.seatIndex);
  if (Number.isInteger(seatIndex) && seatIndex >= 0 && seatIndex < SEAT_POSITIONS.length) {
    return seatIndex + 1;
  }
  if (Number.isInteger(seatIndex) && seatIndex >= 1 && seatIndex <= SEAT_POSITIONS.length) {
    return seatIndex;
  }

  return null;
}

function canonicalSeatDelta(playerSeat, viewerSeat) {
  if (!Number.isInteger(playerSeat) || !Number.isInteger(viewerSeat)) {
    return null;
  }
  return (playerSeat - viewerSeat + SEAT_POSITIONS.length) % SEAT_POSITIONS.length;
}

function firstUnusedVisualSeat(usedSeats, includeHeroSeat = false) {
  const start = includeHeroSeat ? 0 : 1;
  for (let seat = start; seat < SEAT_POSITIONS.length; seat += 1) {
    if (!usedSeats.has(seat)) return seat;
  }
  return 0;
}

function assignStableViewerSeats(players, state = null) {
  const list = Array.isArray(players) ? players : [];
  const viewer = list.find(p => p && p.is_you);
  const viewerSeat = canonicalSeatNumber(viewer);
  const usedSeats = new Set();

  const assigned = list.map((player, originalIndex) => {
    const canonicalSeat = canonicalSeatNumber(player);
    const delta = canonicalSeatDelta(canonicalSeat, viewerSeat);

    let visualSeat = null;
    if (player && player.is_you) {
      visualSeat = 0;
    } else if (delta !== null) {
      visualSeat = CANONICAL_VISUAL_SEAT_BY_OFFSET[delta];
    }

    // Defensive fallback for malformed/legacy states with missing or duplicate seats.
    if (!Number.isInteger(visualSeat) || usedSeats.has(visualSeat)) {
      visualSeat = firstUnusedVisualSeat(usedSeats, Boolean(player && player.is_you));
    }

    usedSeats.add(visualSeat);

    return {
      player,
      visualSeat,
      canonicalSeat,
      delta,
      originalIndex,
      key: stablePlayerKey(player),
    };
  });

  // Render in viewer-rotated canonical order, not incoming array order.
  return assigned.sort((a, b) => {
    if (a.player && a.player.is_you) return -1;
    if (b.player && b.player.is_you) return 1;

    if (a.delta !== null && b.delta !== null && a.delta !== b.delta) {
      return a.delta - b.delta;
    }

    if (a.canonicalSeat !== null && b.canonicalSeat !== null && a.canonicalSeat !== b.canonicalSeat) {
      return a.canonicalSeat - b.canonicalSeat;
    }

    return a.key.localeCompare(b.key) || a.originalIndex - b.originalIndex;
  });
}

// ═══════════════════════════════════════════════════════════════
// WebSocket
// ═══════════════════════════════════════════════════════════════
function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return ws;
  intentionalDisconnect = false;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    reconnectAttempts = 0;
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    els.status.textContent = "";
    fetchRooms();
  };

  ws.onmessage = ev => {
    const { event, payload } = JSON.parse(ev.data);
    if (event === "joined") {
      roomId = payload.room_id;
      token = payload.token;
      localStorage.setItem("poker_room_id", roomId);
      localStorage.setItem("poker_token", token);
      els.connectScreen.classList.add("hidden");
      els.gameScreen.classList.remove("hidden");
    }
    if (event === "state") renderState(payload);
    if (event === "left") leaveToLobby();
    if (event === "rooms_list") renderRoomsList(payload.rooms);
    if (event === "error" || event === "reconnect_failed") {
      els.status.textContent = payload.message;
      if (event === "reconnect_failed") {
        roomId = ""; token = "";
        localStorage.removeItem("poker_room_id");
        localStorage.removeItem("poker_token");
        els.gameScreen.classList.add("hidden");
        els.connectScreen.classList.remove("hidden");
        reconnectAttempts = 0;
        fetchRooms();
      }
    }
  };

  ws.onclose = () => {
    els.status.textContent = "Disconnected.";
    ws = null;
    if (!intentionalDisconnect) attemptReconnect();
  };

  return ws;
}

function send(event, payload = {}) {
  const s = connect();
  const finalPayload = { room_id: roomId, token, ...payload };
  const msg = JSON.stringify({ event, payload: finalPayload });
  if (s.readyState === WebSocket.OPEN) s.send(msg);
  else s.addEventListener("open", () => s.send(msg), { once: true });
}

function fetchRooms() {
  const s = connect();
  const msg = JSON.stringify({ event: "list_rooms", payload: {} });
  if (s.readyState === WebSocket.OPEN) s.send(msg);
  else s.addEventListener("open", () => s.send(msg), { once: true });
}

function attemptReconnect() {
  if (intentionalDisconnect || !roomId || !token) return;
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
  reconnectAttempts++;
  els.status.textContent = `Reconnecting... (attempt ${reconnectAttempts})`;

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (intentionalDisconnect) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
      reconnectAttempts = 0;
      els.status.textContent = "";
      ws.send(JSON.stringify({ event: "reconnect", payload: { room_id: roomId, token } }));
    };
    ws.onmessage = ev => {
      const { event, payload } = JSON.parse(ev.data);
      if (event === "joined") {
        roomId = payload.room_id; token = payload.token;
        localStorage.setItem("poker_room_id", roomId);
        localStorage.setItem("poker_token", token);
        els.connectScreen.classList.add("hidden");
        els.gameScreen.classList.remove("hidden");
      }
      if (event === "state") renderState(payload);
      if (event === "left") leaveToLobby();
      if (event === "rooms_list") renderRoomsList(payload.rooms);
      if (event === "error" || event === "reconnect_failed") {
        els.status.textContent = payload.message;
        if (event === "reconnect_failed") {
          roomId = ""; token = "";
          localStorage.removeItem("poker_room_id");
          localStorage.removeItem("poker_token");
          els.gameScreen.classList.add("hidden");
          els.connectScreen.classList.remove("hidden");
          reconnectAttempts = 0;
          fetchRooms();
        }
      }
    };
    ws.onclose = () => {
      ws = null;
      if (!intentionalDisconnect) attemptReconnect();
    };
  }, delay);
}

// ═══════════════════════════════════════════════════════════════
// Room list / lobby
// ═══════════════════════════════════════════════════════════════
function renderRoomsList(rooms) {
  if (!rooms || rooms.length === 0) { els.roomsList.innerHTML = ""; return; }
  els.roomsList.innerHTML = `<div class="rooms-list-title">Active Rooms</div>` +
    rooms.map(r => `<div class="room-item" data-id="${r.room_id}">
      <span class="room-item-id">${r.room_id}</span>
      <span class="room-item-info">${r.connected}/${r.max} · ${r.phase}</span>
    </div>`).join("");
  els.roomsList.querySelectorAll(".room-item").forEach(el => {
    el.onclick = () => { els.roomInput.value = el.dataset.id; joinRoom(); };
  });
}

function leaveToLobby() {
  roomId = ""; token = "";
  localStorage.removeItem("poker_room_id");
  localStorage.removeItem("poker_token");
  els.gameScreen.classList.add("hidden");
  els.connectScreen.classList.remove("hidden");
  els.winnerOverlay.classList.add("hidden");
  lastState = null;
  connect();
  setTimeout(fetchRooms, 300);
}

// ═══════════════════════════════════════════════════════════════
// Actions
// ═══════════════════════════════════════════════════════════════
function createRoom() {
  savePlayerName(els.nameInput.value);
  const blindIncrease = parseInt(document.getElementById("blindIncreaseInput")?.value || "0", 10);
  const ante = parseInt(document.getElementById("anteInput")?.value || "0", 10);
  const anteMode = document.getElementById("anteModeSelect")?.value || "classic";
  const autoAnte = document.getElementById("autoAnteCheck")?.checked || false;
  const allowFoldedReveals = document.getElementById("allowFoldedRevealsCheck")?.checked ?? true;
  send("create", {
    name: els.nameInput.value || "Player",
    avatar: selectedAvatar,
    blind_increase_hands: blindIncrease || 0,
    ante: ante || 0,
    ante_mode: anteMode,
    auto_ante: autoAnte,
    allow_folded_reveals: allowFoldedReveals,
  });
}

function joinRoom() {
  savePlayerName(els.nameInput.value);
  const targetRoom = els.roomInput.value.trim().toUpperCase();
  roomId = targetRoom;
  token = "";
  send("join", { name: els.nameInput.value || "Player", room_id: targetRoom, token: "", avatar: selectedAvatar });
}

function reconnectLast() {
  roomId = localStorage.getItem("poker_room_id") || "";
  token = localStorage.getItem("poker_token") || "";
  if (!roomId || !token) { els.status.textContent = "No saved session."; return; }
  send("reconnect", { room_id: roomId, token });
}

function action(name, extra = {}) { send("action", { action: name, ...extra }); }

function leaveGame() {
  intentionalDisconnect = true;
  try { send("leave", {}); } catch(e) {}
  setTimeout(leaveToLobby, 200);
}

// ═══════════════════════════════════════════════════════════════
// Render state — pure DOM update, no animations
// ═══════════════════════════════════════════════════════════════

function canViewerDeal(state) {
  return Boolean(
    state
    && state.viewer
    && state.viewer.is_admin
    && ["lobby", "showdown"].includes(state.phase)
    && !state.paused
  );
}

function syncDealControls(state) {
  const canDeal = canViewerDeal(state);

  const postHandDealBtn = els.postHandDealBtn || document.getElementById("postHandDealBtn");
  const postHandPanel = els.postHandPanel || document.getElementById("postHandPanel");
  const postHandActions = postHandDealBtn ? postHandDealBtn.closest(".post-hand-actions") : null;
  const postHandVisible = Boolean(
    postHandPanel
    && !postHandPanel.classList.contains("hidden")
    && state
    && state.phase === "showdown"
    && Array.isArray(state.winners)
    && state.winners.length > 0
  );

  const showBottomDeal = canDeal && !postHandVisible;
  const showModalDeal = canDeal && postHandVisible;

  const startBtn = els.startBtn || document.getElementById("startBtn");
  if (startBtn) {
    startBtn.hidden = !showBottomDeal;
    startBtn.style.setProperty("display", showBottomDeal ? "inline-flex" : "none", "important");
  }

  if (postHandPanel) {
    postHandPanel.classList.toggle("show-deal-actions", showModalDeal);
  }

  if (postHandActions) {
    postHandActions.hidden = !showModalDeal;
    postHandActions.style.setProperty("display", showModalDeal ? "flex" : "none", "important");
  }

  if (postHandDealBtn) {
    postHandDealBtn.hidden = !showModalDeal;
    postHandDealBtn.style.setProperty("display", showModalDeal ? "inline-flex" : "none", "important");
  }
}



function autoDealStateKey(state) {
  if (!state) return "";
  const winners = Array.isArray(state.winners)
    ? state.winners.map(w => `${w.player_id || w.name || ""}:${w.amount || 0}`).join("|")
    : "";
  return [
    state.room_id || "",
    state.hand_number || state.hands_played || 0,
    state.phase || "",
    winners,
  ].join(":");
}

function clearAutoDealTimer() {
  if (autoDealTimerId) {
    clearTimeout(autoDealTimerId);
    autoDealTimerId = null;
  }
}

function hideAutoDealCountdown() {
  clearAutoDealTimer();
  autoDealDeadlineMs = 0;
  autoDealHandKey = "";
  if (els.autoDealCountdown) {
    els.autoDealCountdown.classList.add("hidden");
    els.autoDealCountdown.textContent = "";
  }

  const postHandCountdown = document.getElementById("autoDealPostHandCountdown");
  if (postHandCountdown) {
    postHandCountdown.classList.add("hidden");
    postHandCountdown.textContent = "";
  }
}


function ensureAutoDealCountdownSurface() {
  let postHandCountdown = document.getElementById("autoDealPostHandCountdown");
  if (postHandCountdown) return postHandCountdown;

  postHandCountdown = document.createElement("div");
  postHandCountdown.id = "autoDealPostHandCountdown";
  postHandCountdown.className = "auto-deal-countdown auto-deal-post-hand-countdown hidden";

  const anchor = els.postHandBody || document.getElementById("postHandBody");
  if (els.postHandPanel && anchor && anchor.parentNode === els.postHandPanel) {
    els.postHandPanel.insertBefore(postHandCountdown, anchor);
  } else if (els.postHandPanel) {
    els.postHandPanel.appendChild(postHandCountdown);
  }

  return postHandCountdown;
}

function showAutoDealCountdown(text) {
  if (els.autoDealCountdown) {
    els.autoDealCountdown.classList.remove("hidden");
    els.autoDealCountdown.textContent = text;
  }

  const postHandCountdown = ensureAutoDealCountdownSurface();
  if (postHandCountdown) {
    postHandCountdown.classList.remove("hidden");
    postHandCountdown.textContent = text;
  }
}

function setAutoDealToggleState(canShow) {
  if (!els.autoDealToggle) return;

  els.autoDealToggle.style.display = canShow ? "inline-flex" : "none";
  els.autoDealToggle.classList.toggle("is-active", autoDealEnabled);
  els.autoDealToggle.textContent = autoDealEnabled ? "Auto On" : "Auto Off";
  els.autoDealToggle.title = autoDealEnabled
    ? "Auto-deal next hand after showdown"
    : "Auto-deal is disabled";
}

function syncAutoDeal(state) {
  const viewerIsAdmin = Boolean(state && state.viewer && state.viewer.is_admin);
  const canAdminDeal = canViewerDeal(state);
  const winners = Array.isArray(state && state.winners) ? state.winners : [];
  const handComplete = Boolean(
    state
    && state.phase === "showdown"
    && winners.length > 0
    && !state.__history_review
  );

  setAutoDealToggleState(viewerIsAdmin);

  if (!autoDealEnabled || !handComplete || state.paused) {
    hideAutoDealCountdown();
    if (!handComplete) autoDealFiredKey = "";
    return;
  }

  const key = autoDealStateKey(state);
  if (!key) {
    hideAutoDealCountdown();
    return;
  }

  if (autoDealFiredKey === key) {
    clearAutoDealTimer();
    showAutoDealCountdown(canAdminDeal ? "Dealing next hand..." : "Waiting for next hand...");
    return;
  }

  if (autoDealHandKey !== key) {
    clearAutoDealTimer();
    autoDealHandKey = key;
    autoDealDeadlineMs = Date.now() + AUTO_DEAL_DELAY_SECONDS * 1000;
  }

  const remainingMs = Math.max(0, autoDealDeadlineMs - Date.now());
  const remainingSeconds = Math.ceil(remainingMs / 1000);

  showAutoDealCountdown(`Auto-deal in ${remainingSeconds}s`);

  if (remainingMs <= 0) {
    clearAutoDealTimer();
    autoDealFiredKey = key;

    if (canAdminDeal) {
      showAutoDealCountdown("Dealing next hand...");
      action("start_hand");
    } else {
      showAutoDealCountdown("Waiting for next hand...");
    }

    return;
  }

  clearAutoDealTimer();
  autoDealTimerId = setTimeout(() => {
    if (lastState) syncAutoDeal(lastState);
  }, Math.min(250, remainingMs));
}

function initAutoDealToggle() {
  if (!els.autoDealToggle) return;

  els.autoDealToggle.addEventListener("click", () => {
    autoDealEnabled = !autoDealEnabled;
    localStorage.setItem(AUTO_DEAL_STORAGE_KEY, String(autoDealEnabled));
    if (!autoDealEnabled) {
      hideAutoDealCountdown();
    }
    if (lastState) syncAutoDeal(lastState);
  });

  setAutoDealToggleState(false);
}


function numberOrZero(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}


function adminPlayerStatusLabels(player, viewerIsAdmin = false) {
  const labels = [];
  if (!player) return labels;

  const isCurrentAdmin = Boolean(player.is_admin || (viewerIsAdmin && player.is_you));
  if (isCurrentAdmin) labels.push("Admin");
  if (player.is_you) labels.push("You");
  if (player.is_bot) {
    labels.push(player.bot_difficulty ? `Bot ${player.bot_difficulty}` : "Bot");
  } else {
    labels.push("Player");
  }
  if (player.is_spectator) labels.push("Spectator");
  if (player.sitting_out) labels.push("Sitting out");
  if (!player.connected && !player.is_bot) labels.push("Offline");
  if (player.folded) labels.push("Folded");
  if (player.all_in) labels.push("All-in");

  return labels;
}

function renderAdminPlayerList(state) {
  if (!els.adminPlayerList) return;

  const viewerIsAdmin = Boolean(state && state.viewer && state.viewer.is_admin);
  const players = Array.isArray(state && state.players) ? state.players : [];
  const safeKickPhase = Boolean(state && ["lobby", "showdown"].includes(state.phase));

  if (els.adminActions) {
    els.adminActions.classList.remove("hidden");
    els.adminActions.classList.toggle("is-table-admin", viewerIsAdmin);
    const dockTitle = els.adminActions.querySelector(".admin-dock-title");
    const dockSubtitle = els.adminActions.querySelector(".admin-dock-subtitle");
    if (dockTitle) dockTitle.textContent = viewerIsAdmin ? "Admin" : "Table";
    if (dockSubtitle) dockSubtitle.textContent = viewerIsAdmin ? "Table roster" : "Players";
  }

  if (players.length === 0) {
    els.adminPlayerList.innerHTML = '<div class="admin-player-empty">No players seated.</div>';
    return;
  }

  els.adminPlayerList.innerHTML = players
    .slice()
    .sort((a, b) => numberOrZero(a.seat) - numberOrZero(b.seat))
    .map(player => {
      const id = esc(player.id || player.player_id || "");
      const name = esc(player.name || "Player");
      const seat = esc(player.seat || "?");
      const stack = numberOrZero(player.stack);
      const isSelf = Boolean(player.is_you);
      const isCurrentAdmin = Boolean(player.is_admin || (viewerIsAdmin && isSelf));

      const labels = adminPlayerStatusLabels(player, viewerIsAdmin)
        .map(label => `<span class="admin-player-badge">${esc(label)}</span>`)
        .join("");

      const mockHtml = isSelf
        ? ""
        : `<button type="button" class="admin-player-action-btn muted" disabled title="Mock action coming soon">Mock</button>`;
      const dmHtml = isSelf
        ? ""
        : `<button type="button" class="admin-player-action-btn muted" disabled title="Direct messages coming soon">DM</button>`;

      const canKickTarget = viewerIsAdmin && !isCurrentAdmin && !isSelf && Boolean(player.id || player.player_id);
      const kickHtml = canKickTarget && safeKickPhase
        ? `<button type="button" class="admin-player-action-btn admin-kick-btn" data-admin-kick-id="${id}" title="Remove this player from the table">Kick</button>`
        : canKickTarget
          ? `<button type="button" class="admin-player-action-btn admin-kick-btn disabled" disabled title="Kick is available after the current hand">Kick after hand</button>`
          : "";

      const actionHtml = [mockHtml, dmHtml, kickHtml].filter(Boolean).join("");

      return `
        <div class="admin-player-row${isCurrentAdmin ? " is-admin" : ""}${player.is_bot ? " is-bot" : " is-human"}${isSelf ? " is-self" : ""}">
          <div class="admin-player-main">
            <span class="admin-player-name">${name}</span>
            <span class="admin-player-seat">Seat ${seat}</span>
            <span class="admin-player-stack">${stack}</span>
          </div>
          <div class="admin-player-meta">${labels || '<span class="admin-player-badge muted">Player</span>'}</div>
          <div class="admin-player-actions">${actionHtml}</div>
        </div>
      `;
    })
    .join("");

  els.adminPlayerList.querySelectorAll("[data-admin-kick-id]").forEach(btn => {
    btn.onclick = event => {
      event.preventDefault();
      event.stopPropagation();
      const targetId = btn.dataset.adminKickId || "";
      if (targetId) action("kick_player", { target_player_id: targetId });
    };
  });
}


function setActionButtonState(btn, enabled, label, title = "") {
  if (!btn) return;
  btn.disabled = !enabled;
  btn.setAttribute("aria-disabled", enabled ? "false" : "true");
  if (label != null) btn.textContent = label;
  if (title) {
    btn.title = title;
  } else {
    btn.removeAttribute("title");
  }
}

function bettingActionModel(state, isMyTurn, showdownDisplay) {
  const viewer = state && state.viewer ? state.viewer : {};
  const phase = state && state.phase ? state.phase : "";
  const activePhase = ["preflop", "flop", "turn", "river"].includes(phase);

  const stack = Math.max(0, numberOrZero(viewer.stack));
  const committed = Math.max(0, numberOrZero(viewer.committed));
  const totalChips = committed + stack;
  const toCall = Math.max(0, numberOrZero(viewer.to_call));
  const currentBet = Math.max(0, numberOrZero(state && state.current_bet));
  const fallbackMinRaise = Math.max(1, numberOrZero(state && state.big_blind));
  const minRaise = Math.max(1, numberOrZero(state && state.min_raise) || fallbackMinRaise);
  const pot = Math.max(0, numberOrZero(state && state.pot));
  const minRaiseTo = currentBet + minRaise;

  const canAct = Boolean(
    isMyTurn
    && activePhase
    && !showdownDisplay
    && state
    && !state.paused
    && stack > 0
    && !viewer.folded
    && !viewer.all_in
  );

  const canCheck = canAct && toCall <= 0;
  const canCall = canAct && toCall > 0;
  const liveOpponents = Array.isArray(state && state.players)
    ? state.players.filter(p => {
        if (!p || p.is_you || p.folded || p.is_spectator) return false;
        return Array.isArray(p.cards) && p.cards.length > 0;
      })
    : [];
  const raiseCanBeContested = liveOpponents.some(p =>
    !p.all_in && numberOrZero(p.stack) > 0
  );

  const canMakeFullRaise = canAct && raiseCanBeContested && stack > toCall && totalChips >= minRaiseTo;
  const canShortAllIn = canAct && raiseCanBeContested && stack > toCall && totalChips < minRaiseTo;
  const canAllIn = canAct && raiseCanBeContested && (toCall <= 0 || stack > toCall);

  const halfPotTarget = Math.max(minRaiseTo, currentBet + Math.floor(pot / 2));
  const potTarget = Math.max(minRaiseTo, currentBet + pot);

  const preset = (target) => {
    const enabled = canMakeFullRaise && target <= totalChips;
    let title = "";
    if (canAct && !enabled) {
      if (target > totalChips) {
        title = `Not enough chips: needs ${target}, maximum is ${totalChips}`;
      } else if (!canMakeFullRaise && canShortAllIn) {
        title = `Only all-in is available: minimum raise is ${minRaiseTo}, maximum is ${totalChips}`;
      } else if (!canMakeFullRaise) {
        title = `Minimum raise is ${minRaiseTo}`;
      }
    }
    return { target, enabled, title };
  };

  return {
    canAct,
    stack,
    committed,
    totalChips,
    toCall,
    currentBet,
    minRaise,
    minRaiseTo,
    canCheck,
    canCall,
    canMakeFullRaise,
    canShortAllIn,
    canAllIn,
    raiseCanBeContested,
    halfPot: preset(halfPotTarget),
    pot: preset(potTarget),
  };
}

function syncBettingControls(state, isMyTurn, showdownDisplay) {
  const model = bettingActionModel(state, isMyTurn, showdownDisplay);

  setActionButtonState(
    els.foldBtn,
    model.canAct,
    "Fold"
  );

  let checkCallLabel = "Check / Call";
  let checkCallEnabled = false;
  let checkCallTitle = "";

  if (model.canCheck) {
    checkCallLabel = "Check";
    checkCallEnabled = true;
  } else if (model.canCall) {
    if (model.stack < model.toCall) {
      checkCallLabel = `Call All-In ${model.stack}`;
      checkCallTitle = `You only have ${model.stack}; this calls all-in against ${model.toCall}`;
    } else {
      checkCallLabel = `Call ${model.toCall}`;
    }
    checkCallEnabled = true;
  }

  setActionButtonState(els.checkCallBtn, checkCallEnabled, checkCallLabel, checkCallTitle);

  setActionButtonState(
    els.betHalfPotBtn,
    model.halfPot.enabled,
    model.halfPot.enabled ? `Half Pot ${model.halfPot.target}` : "Half Pot",
    model.halfPot.title
  );

  setActionButtonState(
    els.betPotBtn,
    model.pot.enabled,
    model.pot.enabled ? `Pot ${model.pot.target}` : "Pot",
    model.pot.title
  );

  let allInLabel = "All-In";
  let allInTitle = "";
  if (model.canAllIn) {
    allInLabel = `All-In ${model.totalChips}`;
    if (model.canShortAllIn) {
      allInTitle = `Short all-in: below minimum raise ${model.minRaiseTo}`;
    }
  } else if (model.canCall && !model.raiseCanBeContested) {
    allInTitle = "Call closes action; no one can contest extra chips";
  } else if (model.canCall && model.stack <= model.toCall) {
    allInTitle = "Use Call All-In instead";
  }

  setActionButtonState(
    els.betAllInBtn,
    model.canAllIn,
    allInLabel,
    allInTitle
  );

  if (els.customBetInput) {
    els.customBetInput.disabled = !model.canMakeFullRaise;
    els.customBetInput.min = model.canMakeFullRaise ? String(model.minRaiseTo) : "";
    els.customBetInput.max = model.canMakeFullRaise ? String(model.totalChips) : "";

    if (model.canMakeFullRaise) {
      els.customBetInput.placeholder = `Raise ${model.minRaiseTo}-${model.totalChips}`;
    } else if (model.canShortAllIn) {
      els.customBetInput.placeholder = `Only all-in ${model.totalChips}`;
    } else if (model.canCall && !model.raiseCanBeContested) {
      els.customBetInput.placeholder = "Call closes action";
    } else if (model.canCall && model.stack <= model.toCall) {
      els.customBetInput.placeholder = "Call all-in only";
    } else {
      els.customBetInput.placeholder = "Raise to...";
    }
  }

  setActionButtonState(
    els.customBetBtn,
    model.canMakeFullRaise,
    "Raise"
  );
}



let lastAnimationStateKey = null;
let lastCardAnimationStateKey = null;

function compactAnimationCards(cards) {
  return Array.isArray(cards) ? cards.join("|") : "";
}

function compactAnimationWinners(winners) {
  return (Array.isArray(winners) ? winners : []).map(w => ({
    id: w.player_id || w.id || w.name || "",
    name: w.name || "",
    amount: Number(w.amount) || 0,
    reason: w.reason || "",
    hand: w.hand_detail || w.hand_name || "",
  }));
}

function compactAnimationPlayers(players) {
  return (Array.isArray(players) ? players : []).map(p => ({
    id: p.player_id || p.id || p.name || "",
    name: p.name || "",
    folded: Boolean(p.folded),
    all_in: Boolean(p.all_in),
    cards: compactAnimationCards(p.cards),
    best: compactAnimationCards(p.best_cards),
    hand: p.hand_detail || p.hand_name || "",
    foldedReveal: p.folded_reveal_mode || "",
    uncontestedReveal: p.uncontested_reveal_mode || "",
    canRevealFolded: Boolean(p.can_reveal_folded_hand),
    canRevealUncontested: Boolean(p.can_reveal_uncontested_hand),
  }));
}

function buildAnimationStateKey(state) {
  if (!state) return "";
  return JSON.stringify({
    room: state.room_id || "",
    hand: state.hand_id || state.hand_number || state.hands_played || 0,
    phase: state.phase || "",
    showdownMode: Boolean(state.showdown_mode),
    paused: Boolean(state.paused),
    community: compactAnimationCards(state.community),
    pot: Number(state.pot) || 0,
    winners: compactAnimationWinners(state.winners),
    players: compactAnimationPlayers(state.players),
  });
}

function buildCardAnimationStateKey(state) {
  if (!state) return "";
  return JSON.stringify({
    room: state.room_id || "",
    hand: state.hand_id || state.hand_number || state.hands_played || 0,
    phase: state.phase || "",
    showdownMode: Boolean(state.showdown_mode),
    community: compactAnimationCards(state.community),
    players: compactAnimationPlayers(state.players).map(p => ({
      id: p.id,
      cards: p.cards,
      best: p.best,
      hand: p.hand,
      folded: p.folded,
      foldedReveal: p.foldedReveal,
      uncontestedReveal: p.uncontestedReveal,
    })),
    winners: compactAnimationWinners(state.winners).map(w => ({
      id: w.id,
      reason: w.reason,
      hand: w.hand,
    })),
  });
}

function syncRefreshAnimationSuppression(state) {
  const key = buildAnimationStateKey(state);
  const cardKey = buildCardAnimationStateKey(state);

  const isRefresh = Boolean(lastAnimationStateKey && key === lastAnimationStateKey);
  const isCardRefresh = Boolean(lastCardAnimationStateKey && cardKey === lastCardAnimationStateKey);

  document.body.classList.toggle("suppress-refresh-animations", isRefresh);
  document.body.classList.toggle("suppress-card-refresh-animations", isCardRefresh);

  lastAnimationStateKey = key;
  lastCardAnimationStateKey = cardKey;
}


function renderState(state) {
  window.__pokerLastState = state;
  const previousState = lastState;
  lastState = state;
  openDefaultPanelsForRoom(state);

  const historyReviewDisplayState = selectedHistoryReviewFromState(state);
  const cinemaState = historyReviewDisplayState || state;
  const historyReviewDisplay = Boolean(historyReviewDisplayState);
  const showdownDisplay = cinemaState.phase === "showdown" || Boolean(cinemaState.showdown_mode);
  const handCompleteDisplay = showdownDisplay && Array.isArray(cinemaState.winners) && cinemaState.winners.length > 0;

  document.body.classList.toggle("showdown-cinema", showdownDisplay);
  document.body.classList.toggle("hand-complete-cinema", handCompleteDisplay);
  document.body.classList.toggle("history-review-cinema", historyReviewDisplay);
  syncRefreshAnimationSuppression(cinemaState);

  // ─── HUD ───
  els.roomId.textContent = state.room_id;
  els.phaseBadge.textContent = state.paused ? "PAUSED" : showdownDisplay ? "SHOWDOWN" : state.phase.toUpperCase();
  const animatePot = shouldAnimatePotCountUp(previousState, state);
  setPotValue(displayedCenterPotAmount(state), animatePot);

  // Pot label
  const potLabel = document.querySelector(".pot-label");
  if (potLabel) potLabel.textContent = state.phase === "showdown" ? "FINAL POT" : "POT";
  const tableFelt = document.querySelector(".table-felt");
  if (tableFelt) tableFelt.classList.toggle("showdown-table-glow", showdownDisplay);

  // Blind info
  const blindEl = document.getElementById("blindInfo");
  if (blindEl) {
    let txt = `${state.small_blind}/${state.big_blind}`;
    if (state.ante > 0) txt += state.ante_mode === "bba" ? " +BBA" : ` +${state.ante}a`;
    if (state.blind_increase_hands > 0) {
      const until = state.blind_increase_hands - (state.hands_played % state.blind_increase_hands);
      txt += ` · ↑${until}h`;
    }
    blindEl.textContent = txt;
  }

  if (els.potChips) {
    els.potChips.innerHTML = renderChipStackHtml(state.pot, animatePot ? "chip-to-pot-in" : "");
  }

  // ─── Turn indicator ───
  const isMyTurn = state.viewer && state.viewer.is_turn;
  if (isMyTurn) {
    els.turnInfo.textContent = state.viewer.to_call > 0
      ? `⚡ YOUR ACTION · Call ${state.viewer.to_call}` : "⚡ YOUR ACTION";
    els.turnInfo.className = "turn-indicator your-turn";
    els.actionBar.classList.add("my-turn");
  } else {
    els.turnInfo.textContent = "";
    els.turnInfo.className = "turn-indicator";
    els.actionBar.classList.remove("my-turn");
  }

  // ─── Hide action buttons at showdown ───
  const actionRowMain = els.actionBar.querySelector(".action-row-main");
  const actionRowRaise = els.actionBar.querySelector(".action-row-raise");
  const actionRowCustom = els.actionBar.querySelector(".action-row-custom");
  if (showdownDisplay) {
    if (actionRowMain) actionRowMain.style.display = "none";
    if (actionRowRaise) actionRowRaise.style.display = "none";
    if (actionRowCustom) actionRowCustom.style.display = "none";
  } else {
    if (actionRowMain) actionRowMain.style.display = "";
    if (actionRowRaise) actionRowRaise.style.display = "";
    if (actionRowCustom) actionRowCustom.style.display = "";
  }

  // ─── Winners in pot area (text, no overlay) ───
  if (state.winners && state.winners.length > 0 && state.phase === "showdown") {
    const winTxt = state.winners.map(w => {
      if (w.hand_name && w.reason !== "Everyone else folded") {
        return `${esc(w.name)} wins ${w.amount} with a ${esc(w.hand_name)}`;
      }
      return `${esc(w.name)} wins ${w.amount}`;
    }).join(" | ");
    if (potAnimationFrame) {
      cancelAnimationFrame(potAnimationFrame);
      potAnimationFrame = null;
    }
    displayedPotAmount = Number(state.pot) || displayedPotAmount;
    els.potValue.classList.remove("pot-counting");
    els.potValue.textContent = winTxt;
    els.winnerOverlay.classList.add("hidden");
  } else {
    els.winnerOverlay.classList.add("hidden");
  }

  // ─── Deal button visible only for room creator/admin between hands ───
  const isAdminViewer = Boolean(state.viewer && state.viewer.is_admin);
  const canDeal = isAdminViewer && ["lobby", "showdown"].includes(state.phase) && !state.paused;
  els.startBtn.style.display = canDeal ? "" : "none";

  const postHandDealBtn = els.postHandDealBtn || document.getElementById("postHandDealBtn");
  if (postHandDealBtn) {
    postHandDealBtn.style.display = canDeal ? "inline-flex" : "none";
    const postHandActions = postHandDealBtn.closest(".post-hand-actions");
    if (postHandActions) postHandActions.style.display = canDeal ? "flex" : "none";
  }

  // ─── Admin panel ───
  if (state.viewer && state.viewer.is_admin) {
    els.adminActions.classList.remove("hidden");
    if (els.pauseBtn) els.pauseBtn.textContent = state.paused ? "▶ Resume" : "⏸ Pause";
  } else {
    els.adminActions.classList.add("hidden");
  }

  // ─── Sit out / spectate ───
  const viewerData = state.players.find(p => p.is_you);
  if (els.sitOutBtn && viewerData) {
    els.sitOutBtn.textContent = viewerData.sitting_out ? "Sit In" : "Sit Out";
    const inHand = ["preflop","flop","turn","river"].includes(state.phase);
    const canSitOut = !viewerData.is_spectator && (!inHand || viewerData.folded || !viewerData.cards || viewerData.cards.length === 0);
    els.sitOutBtn.style.display = canSitOut ? "" : "none";
  }
  if (els.spectateBtn && viewerData) {
    els.spectateBtn.textContent = viewerData.is_spectator ? "Join Game" : "Spectate";
    els.spectateBtn.style.display = ["lobby","showdown"].includes(state.phase) ? "" : "none";
  }

  // ─── Community cards ───
  renderCommunity(state.community, previousState ? previousState.community : []);
  renderShowdownTray(cinemaState);

  // ─── Your hand ───
  // Hide the hero hand bar during showdown so the post-hand panel can own the result view.
  renderYourHand(showdownDisplay ? null : viewerData);

  // ─── Player seats ───
  renderPlayers(state.players, previousState, state);

  // ─── Chat ───
  // ??? Admin dock player list ???
  renderAdminPlayerList(state);

  renderChat(state.messages);

  // ─── Action Log ───
  renderActionLog(cinemaState);
  renderPostHandPanel(state);
  renderHandHistory(state);
  syncDealControls(state);

  // ─── Action button labels / enabled state ───
  syncBettingControls(state, isMyTurn, showdownDisplay);

  // Hide outs box (removed feature)
  if (els.outsBox) els.outsBox.classList.add("hidden");
  // ??? Auto-deal countdown ???
  syncAutoDeal(state);
}

// ─── Community cards ───
function renderCommunity(cards, previousCards = []) {
  if (!cards || cards.length === 0) { els.community.innerHTML = ""; return; }
  const newFlags = getNewCardFlags(cards, previousCards);
  els.community.innerHTML = cards.map((card, idx) =>
    makeCardHtml(card, newFlags[idx] ? "new-card" : "")
  ).join("");
}

// ─── Your hand ───
function renderYourHand(viewer) {
  if (!viewer || !viewer.cards || viewer.cards.length === 0) {
    els.yourHandBar.classList.add("hand-bar-hidden");
    els.yourCards.innerHTML = "";
    els.handStrength.textContent = "";
    return;
  }
  els.yourHandBar.classList.remove("hand-bar-hidden");
  els.yourCards.innerHTML = sortHoleCardsForDisplay(viewer.cards).map(makeCardHtml).join("");
  els.handStrength.textContent = viewer.hand_name || "";
}


function renderSeatBetMarker(player, visualSeat) {
  const committed = Math.max(0, numberOrZero(player && player.committed));
  if (committed <= 0) return null;

  const pos = BET_POSITIONS[visualSeat % BET_POSITIONS.length] || BET_POSITIONS[0];
  const marker = document.createElement("div");

  let cls = "seat-bet-marker";
  if (player.is_you) cls += " is-you";
  if (player.is_turn) cls += " active-turn";

  marker.className = cls;
  marker.style.top = pos.top;
  marker.style.left = pos.left;
  marker.style.transform = "translate(-50%, -50%)";
  marker.innerHTML = `
    <div class="seat-bet-chips">${renderChipStackHtml(committed, "seat-committed-chips")}</div>
    <div class="seat-bet-label">Bet ${committed}</div>
  `;

  return marker;
}


// ─── Players around table ───
function renderPlayers(players, previousState = null, state = null) {
  els.playerPositions.innerHTML = "";
  const previousById = new Map((previousState?.players || []).map(p => [p.player_id || p.name, p]));
  const winnerNames = new Set(
    state && state.phase === "showdown" && Array.isArray(state.winners)
      ? state.winners.map(w => w.name)
      : []
  );

  const seatedPlayers = assignStableViewerSeats(players, state);

  seatedPlayers.forEach(({ player: p, visualSeat }) => {
    const pos = SEAT_POSITIONS[visualSeat % SEAT_POSITIONS.length];
    const seat = document.createElement("div");
    let cls = "player-seat";
    if (p.is_turn) cls += " active-turn";
    if (p.folded) cls += " folded";
    if (p.is_you) cls += " is-you";
    if (winnerNames.has(p.name)) cls += " showdown-winner-glow";
    seat.className = cls;
    seat.style.top = pos.top;
    seat.style.left = pos.left;
    seat.style.transform = "translate(-50%, -50%)";

    // Badges
    const badges = [];
    if (p.is_you) badges.push('<span class="seat-badge">YOU</span>');
    if (p.is_dealer) badges.push('<span class="seat-badge">D</span>');
    if (p.is_bot) badges.push('<span class="seat-badge">🤖</span>');
    if (p.all_in) badges.push('<span class="seat-badge">ALL-IN</span>');
    if (p.folded) badges.push('<span class="seat-badge warn">FOLD</span>');
    if (!p.connected && !p.is_bot) badges.push('<span class="seat-badge warn">DC</span>');
    if (p.sitting_out) badges.push('<span class="seat-badge warn">SIT OUT</span>');
    if (p.is_spectator) badges.push('<span class="seat-badge">👁</span>');

    // Cards in the table seat, including hero.
    // The separate bottom hand bar can still exist, but the hero seat must
    // also show the player's own hole cards so the bottom seat is readable.
    let cards = "";
    if (p.cards && p.cards.length > 0) {
      const previousPlayer = previousById.get(p.player_id || p.name);
      const newFlags = getNewCardFlags(p.cards, previousPlayer ? previousPlayer.cards : []);
      const displayedCards = p.is_you ? sortHoleCardsForDisplay(p.cards) : p.cards;
      cards = `<div class="seat-cards">${displayedCards.map((card, cardIdx) =>
        makeCardHtml(card, newFlags[cardIdx] ? "new-card" : "")
      ).join("")}</div>`;
    }

    seat.innerHTML = `
      <div class="seat-header">
        <span class="seat-avatar">${p.avatar || "🎭"}</span>
        <span class="seat-name">${esc(p.name)}</span>
        <span class="seat-stack">💰${p.stack}</span>
      </div>
      <div class="seat-badges">${badges.join("")}</div>
      ${cards}
      ${p.hand_name ? `<div class="seat-meta seat-hand-rank">${esc(p.hand_detail || p.hand_name)}</div>` : ""}
    `;
    els.playerPositions.appendChild(seat);

    const betMarker = renderSeatBetMarker(p, visualSeat);
    if (betMarker) els.playerPositions.appendChild(betMarker);
  });
}

// ─── Chat ───
function renderChat(messages) {
  if (!messages) return;
  els.chatMessages.innerHTML = messages.map(m =>
    `<div class="chat-msg"><span class="chat-name">${esc(m.name)}:</span> ${esc(m.text)}</div>`
  ).join("");
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

// ═══════════════════════════════════════════════════════════════
// Event handlers
// ═══════════════════════════════════════════════════════════════
function completedHandHistoryFromState(state) {
  if (!state || typeof state !== "object") return [];

  const rawHistory = Array.isArray(state.hand_history)
    ? state.hand_history
    : Array.isArray(state.handHistory)
      ? state.handHistory
      : [];

  const history = rawHistory.filter(hand => hand && typeof hand === "object");

  const latest = state.latest_hand_result || state.latestHandResult || null;
  if (latest && typeof latest === "object" && latest.completed !== false) {
    const latestNumber = latest.hand_number != null ? String(latest.hand_number) : "";
    const alreadyIncluded = history.some(hand => {
      if (!hand || hand.hand_number == null || !latestNumber) return false;
      return String(hand.hand_number) === latestNumber;
    });

    if (!alreadyIncluded) {
      history.push(latest);
    }
  }

  return history;
}


function historyHandKey(hand) {
  if (!hand || typeof hand !== "object") return "";
  if (hand.hand_number != null) return String(hand.hand_number);
  return `${hand.room_id || "hand"}:${hand.pot || 0}:${(Array.isArray(hand.community) ? hand.community : []).join("|")}`;
}

function fullHandHistoryDetailsFromState(state) {
  if (!state || typeof state !== "object") return [];

  const rawDetails = Array.isArray(state.hand_history_details)
    ? state.hand_history_details
    : Array.isArray(state.handHistoryDetails)
      ? state.handHistoryDetails
      : [];

  const details = rawDetails.filter(hand => hand && typeof hand === "object");

  const latest = state.latest_hand_result || state.latestHandResult || null;
  if (latest && typeof latest === "object" && latest.completed !== false) {
    const latestKey = historyHandKey(latest);
    const alreadyIncluded = details.some(hand => historyHandKey(hand) === latestKey);
    if (!alreadyIncluded) details.push(latest);
  }

  return details;
}

function findHistoryDetail(hand, details) {
  const key = historyHandKey(hand);
  if (!key) return null;
  return (Array.isArray(details) ? details : []).find(detail => historyHandKey(detail) === key) || null;
}

function historyPlayerDelta(hand, player) {
  const deltas = hand && hand.hand_deltas && typeof hand.hand_deltas === "object" ? hand.hand_deltas : {};
  const keys = [player && player.name, player && player.player_id, player && player.id].filter(Boolean);
  for (const key of keys) {
    if (Number.isFinite(Number(deltas[key]))) return Number(deltas[key]);
  }

  const direct = directPlayerDelta(player || {});
  return direct == null ? null : direct;
}

function renderHistoryCardList(cards) {
  const list = Array.isArray(cards) ? cards : [];
  if (list.length === 0) return '<span class="hand-history-muted">No cards</span>';
  return list.map(card => makeCardHtml(card, "mini-card")).join("");
}

function renderHistoryPlayerRows(hand) {
  const players = Array.isArray(hand && hand.players) ? hand.players : [];
  if (players.length === 0) {
    return '<div class="hand-history-muted">No player details available for this hand.</div>';
  }

  return players.map(player => {
    const delta = historyPlayerDelta(hand, player);
    const deltaText = delta == null ? "" : formatHandDelta(delta);
    const deltaClass = delta == null ? "" : handDeltaClass(delta);
    const handText = player.hand_detail || player.hand_name || "";
    const status = [
      player.folded ? "folded" : "",
      player.all_in ? "all-in" : "",
      player.is_bot ? "bot" : "",
    ].filter(Boolean).join(" ? ");

    return `
      <div class="hand-history-player-row">
        <div class="hand-history-player-main">
          <span class="hand-history-player-name">${esc(player.name || "Player")}</span>
          ${deltaText ? `<span class="hand-history-delta ${esc(deltaClass)}">${esc(deltaText)}</span>` : ""}
        </div>
        <div class="hand-history-detail-cards">${renderHistoryCardList(player.cards)}</div>
        ${handText ? `<div class="hand-history-player-hand">${esc(handText)}</div>` : ""}
        ${status ? `<div class="hand-history-muted">${esc(status)}</div>` : ""}
      </div>
    `;
  }).join("");
}

function renderHistoryPotBreakdown(hand) {
  const rows = Array.isArray(hand && hand.pot_breakdown) ? hand.pot_breakdown : [];
  if (rows.length === 0) return "";

  return `
    <div class="hand-history-detail-section">
      <div class="hand-history-detail-heading">Pots</div>
      ${rows.map(row => {
        const amount = Number(row && row.amount) || 0;
        const winners = Array.isArray(row && row.winners) ? row.winners.join(", ") : "";
        return `<div class="hand-history-pot-row">Pot ${amount}${winners ? ` -> ${esc(winners)}` : ""}</div>`;
      }).join("")}
    </div>
  `;
}

function renderHistoryActionLog(hand) {
  const entries = Array.isArray(hand && hand.action_log) ? hand.action_log : [];
  if (entries.length === 0) return "";

  return `
    <div class="hand-history-detail-section">
      <div class="hand-history-detail-heading">Action log</div>
      <div class="hand-history-action-list">
        ${entries.map(entry => {
          const text = actionEntryText(entry);
          return text ? `<div class="hand-history-action-entry">${esc(text)}</div>` : "";
        }).join("")}
      </div>
    </div>
  `;
}

function renderHistoryDetail(hand) {
  if (!hand || typeof hand !== "object" || !Array.isArray(hand.players)) {
    return '<div class="hand-history-detail"><div class="hand-history-muted">Full details unavailable for this hand.</div></div>';
  }

  const winnerText = summarizeHistoryWinners(hand.winners);
  const pot = Number(hand.pot) || 0;

  return `
    <div class="hand-history-detail">
      <div class="hand-history-detail-summary">
        <span>${esc(winnerText)}</span>
        <span>Final pot ${pot}</span>
      </div>
      <div class="hand-history-detail-section">
        <div class="hand-history-detail-heading">Players</div>
        ${renderHistoryPlayerRows(hand)}
      </div>
      ${renderHistoryPotBreakdown(hand)}
      ${renderHistoryActionLog(hand)}
    </div>
  `;
}

function bindHandHistoryRows() {
  if (!els.handHistoryBody) return;

  els.handHistoryBody.querySelectorAll("[data-history-hand-key]").forEach(row => {
    row.onclick = () => {
      selectedHistoryHandNumber = row.dataset.historyHandKey || "";
      if (lastState) renderHandHistory(lastState);
    };

    row.onkeydown = event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        row.click();
      }
    };
  });
}


function summarizeHistoryWinners(winners) {
  if (!Array.isArray(winners) || winners.length === 0) {
    return "No winners recorded";
  }

  return winners.map(winner => {
    const name = esc(winner && winner.name ? winner.name : "Player");
    const amount = Number(winner && winner.amount) || 0;
    const hand = winner && (winner.hand_detail || winner.hand_name)
      ? ` with ${esc(winner.hand_detail || winner.hand_name)}`
      : "";
    return `${name} +${amount}${hand}`;
  }).join(" / ");
}

function hasCurrentHandComplete(state) {
  const winners = Array.isArray(state && state.winners) ? state.winners : [];
  return Boolean(state && state.phase === "showdown" && winners.length > 0);
}

function isHiddenHistoryCard(card) {
  return !card || card === "BACK" || card === "🂠" || card === "??";
}

function inferRevealModeFromHistoryCards(cards) {
  const list = Array.isArray(cards) ? cards : [];
  if (list.length < 2) return "hidden";

  const leftShown = !isHiddenHistoryCard(list[0]);
  const rightShown = !isHiddenHistoryCard(list[1]);

  if (leftShown && rightShown) return "both";
  if (leftShown) return "left";
  if (rightShown) return "right";
  return "hidden";
}

function historyWinnerIds(hand) {
  return new Set(
    (Array.isArray(hand && hand.winners) ? hand.winners : [])
      .filter(w => w && w.reason === "Everyone else folded")
      .map(w => String(w.player_id || w.id || ""))
  );
}

function normalizeHistoryReviewPlayer(player, hand) {
  const normalized = {
    ...player,
    can_reveal_folded_hand: false,
    can_reveal_uncontested_hand: false,
    is_you: false,
  };

  const pid = String(normalized.player_id || normalized.id || "");
  const uncontestedWinnerIds = historyWinnerIds(hand);
  const inferredMode = inferRevealModeFromHistoryCards(normalized.cards);

  if (normalized.folded && (!normalized.folded_reveal_mode || normalized.folded_reveal_mode === "hidden")) {
    normalized.folded_reveal_mode = inferredMode;
  }

  if (
    !normalized.folded
    && uncontestedWinnerIds.has(pid)
    && (!normalized.uncontested_reveal_mode || normalized.uncontested_reveal_mode === "hidden")
  ) {
    normalized.uncontested_reveal_mode = inferredMode;
  }

  return normalized;
}


function selectedHistoryReviewFromState(state) {
  if (!selectedHistoryReviewKey || hasCurrentHandComplete(state)) return null;

  const details = typeof fullHandHistoryDetailsFromState === "function"
    ? fullHandHistoryDetailsFromState(state)
    : completedHandHistoryFromState(state);

  const hand = (details || []).find(detail => historyHandKey(detail) === String(selectedHistoryReviewKey));
  if (!hand) return null;

  return {
    ...hand,
    phase: "showdown",
    showdown_mode: true,
    __history_review: true,
    players: (Array.isArray(hand.players) ? hand.players : []).map(player =>
      normalizeHistoryReviewPlayer(player, hand)
    ),
  };
}

function ensureHistoryReviewCloseButton() {
  if (!els.postHandPanel) return null;

  let btn = document.getElementById("historyReviewCloseBtn");
  if (!btn) {
    btn = document.createElement("button");
    btn.id = "historyReviewCloseBtn";
    btn.type = "button";
    btn.className = "history-review-close-btn hidden";
    btn.textContent = "X";
    els.postHandPanel.appendChild(btn);
  }

  btn.onclick = closeHistoryReview;
  return btn;
}

function syncHistoryReviewChrome(visible) {
  document.body.classList.toggle("history-review-open", Boolean(visible));

  const btn = ensureHistoryReviewCloseButton();
  if (btn) {
    btn.classList.toggle("hidden", !visible);
  }
}


function rerenderStatePreservingHistoryScroll() {
  const scrollTop = els.handHistoryBody ? els.handHistoryBody.scrollTop : 0;
  if (lastState) renderState(lastState);
  if (els.handHistoryBody) els.handHistoryBody.scrollTop = scrollTop;
}

function closeHistoryReview() {
  selectedHistoryReviewKey = null;
  syncHistoryReviewChrome(false);
  rerenderStatePreservingHistoryScroll();
}

function openHistoryReview(key) {
  if (!key) return;
  selectedHistoryReviewKey = String(key);
  if (els.handHistoryPanel) els.handHistoryPanel.classList.remove("hidden");
  rerenderStatePreservingHistoryScroll();
}

function bindHandHistoryReviewButtons() {
  if (!els.handHistoryBody) return;

  els.handHistoryBody.querySelectorAll("[data-history-review-key]").forEach(btn => {
    btn.onclick = event => {
      event.preventDefault();
      event.stopPropagation();

      if (btn.disabled) return;
      openHistoryReview(btn.dataset.historyReviewKey || "");
    };
  });
}


function openDefaultPanelsForRoom(state) {
  const currentRoomId = state && (state.room_id || state.roomId || roomId || "");
  if (!currentRoomId || defaultPanelsRoomId === currentRoomId) return;

  defaultPanelsRoomId = currentRoomId;

  [
    els.handHistoryPanel,
    els.chatPanel,
    els.actionLogPanel,
  ].forEach(panel => {
    if (panel) panel.classList.remove("hidden");
  });

  // The action log uses collapsed/panel-collapsed state, not only .hidden.
  // Open it once when entering a room so the default table HUD is complete.
  if (els.actionLogPanel && els.actionLogToggle) {
    panelExpanded = true;
    applyPanelState();
    try {
      localStorage.setItem(PANEL_KEY, "true");
    } catch (e) {
      // Ignore private browsing/quota issues.
    }
  }
}


function renderHistoryReviewBoard(state) {
  const board = Array.isArray(state && state.community) ? state.community : [];
  if (!board.length) return "";

  return `
    <div class="history-review-board-strip">
      <div class="history-review-board-title">Board</div>
      <div class="history-review-board-cards">
        ${board.map(card => makeCardHtml(card)).join("")}
      </div>
    </div>
  `;
}

function renderHistoryBoard(cards) {
  const board = Array.isArray(cards) ? cards : [];
  if (board.length === 0) {
    return '<span class="hand-history-no-board">No board</span>';
  }
  return board.map(card => makeCardHtml(card, "mini-card")).join("");
}

function renderHandHistory(state) {
  const history = completedHandHistoryFromState(state);
  const count = history.length;
  const currentCompleteVisible = hasCurrentHandComplete(state);

  if (els.handHistoryCount) {
    els.handHistoryCount.textContent = String(count);
  }

  if (els.handHistoryToggle) {
    els.handHistoryToggle.classList.toggle("has-history", count > 0);
    els.handHistoryToggle.title = count > 0
      ? `${count} completed hand${count === 1 ? "" : "s"}`
      : "No completed hands yet";
  }

  if (!els.handHistoryBody) return;

  const previousHistoryScrollTop = els.handHistoryBody.scrollTop;

  if (count === 0) {
    els.handHistoryBody.innerHTML = '<div class="hand-history-empty">No completed hands yet.</div>';
    els.handHistoryBody.scrollTop = previousHistoryScrollTop;
    return;
  }

  els.handHistoryBody.innerHTML = [...history].reverse().map(hand => {
    const handNumber = hand && hand.hand_number != null ? hand.hand_number : "?";
    const key = historyHandKey(hand);
    const pot = Number(hand && hand.pot) || 0;
    const community = hand && Array.isArray(hand.community) ? hand.community : [];
    const winners = hand && Array.isArray(hand.winners) ? hand.winners : [];
    const winnerText = summarizeHistoryWinners(winners);
    const disabled = currentCompleteVisible ? " disabled" : "";
    const title = currentCompleteVisible
      ? "Finish the current hand-complete screen first"
      : "Open hand-complete review";

    return `
      <article class="hand-history-row compact">
        <div class="hand-history-row-top">
          <span class="hand-history-hand-num">Hand #${esc(handNumber)}</span>
          <span class="hand-history-pot">Pot ${pot}</span>
        </div>
        <div class="hand-history-board">${renderHistoryBoard(community)}</div>
        <div class="hand-history-row-bottom">
          <div class="hand-history-winners">${winnerText}</div>
          <button type="button" class="hand-history-review-btn" data-history-review-key="${esc(key)}"${disabled} title="${esc(title)}">View &gt;</button>
        </div>
      </article>
    `;
  }).join("");

  bindHandHistoryReviewButtons();
  els.handHistoryBody.scrollTop = previousHistoryScrollTop;
}

els.createBtn.onclick = createRoom;
els.joinBtn.onclick = joinRoom;
els.reconnectBtn.onclick = reconnectLast;
els.leaveBtn.onclick = leaveGame;
els.startBtn.onclick = () => action("start_hand");
if (els.postHandDealBtn) {
  els.postHandDealBtn.onclick = () => {
    if (selectedHistoryReviewKey) {
      closeHistoryReview();
      return;
    }
    action("start_hand");
  };
}
els.foldBtn.onclick = () => action("fold");
els.checkCallBtn.onclick = () => action("check_call");
els.betHalfPotBtn.onclick = () => {
  if (!lastState) return;
  action("bet_raise", { amount: Math.max(lastState.current_bet + lastState.min_raise, lastState.current_bet + Math.floor(lastState.pot / 2)) });
};
els.betPotBtn.onclick = () => {
  if (!lastState) return;
  action("bet_raise", { amount: Math.max(lastState.current_bet + lastState.min_raise, lastState.current_bet + lastState.pot) });
};
els.betAllInBtn.onclick = () => {
  if (!lastState) return;
  action("bet_raise", { amount: lastState.viewer.committed + lastState.viewer.stack });
};
els.customBetBtn.onclick = () => {
  const v = parseInt(els.customBetInput.value, 10);
  if (v > 0) { action("bet_raise", { amount: v }); els.customBetInput.value = ""; }
};
els.customBetInput.onkeydown = ev => { if (ev.key === "Enter") els.customBetBtn.click(); };
els.resetBtn.onclick = () => action("reset_stacks");
els.pauseBtn.onclick = () => action("toggle_pause");
els.addBotBtn.onclick = () => {
  const diff = els.botDifficultySelect ? els.botDifficultySelect.value : "hard";
  action("add_bot", { difficulty: diff });
};
els.sitOutBtn.onclick = () => action("sit_out");
els.spectateBtn.onclick = () => action("spectate");
els.copyRoomBtn.onclick = async () => { try { await navigator.clipboard.writeText(roomId); } catch {} };

// Hand history
if (els.handHistoryToggle) {
  els.handHistoryToggle.onclick = () => {
    if (els.handHistoryPanel) els.handHistoryPanel.classList.toggle("hidden");
  };
}
if (els.handHistoryClose) {
  els.handHistoryClose.onclick = () => {
    if (els.handHistoryPanel) els.handHistoryPanel.classList.add("hidden");
  };
}

// History review Escape key
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && selectedHistoryReviewKey) {
    closeHistoryReview();
  }
});

// History review click-outside close
document.addEventListener("pointerdown", event => {
  if (!selectedHistoryReviewKey || !els.postHandPanel) return;
  if (els.postHandPanel.classList.contains("hidden")) return;
  if (els.postHandPanel.contains(event.target)) return;

  closeHistoryReview();
});

// Chat
els.chatToggle.onclick = () => els.chatPanel.classList.toggle("hidden");
els.chatClose.onclick = () => els.chatPanel.classList.add("hidden");
els.chatBtn.onclick = () => {
  const t = els.chatInput.value.trim();
  if (t) { send("chat", { text: t }); els.chatInput.value = ""; }
};
els.chatInput.onkeydown = ev => { if (ev.key === "Enter") els.chatBtn.click(); };

// Hints toggle (kept but simplified — no outs box rendering)
if (els.hintsToggle) els.hintsToggle.onclick = () => {};

// BB toggle — just a no-op now (values shown as raw chips)
if (els.bbToggleBtn) els.bbToggleBtn.style.display = "none";

// ═══════════════════════════════════════════════════════════════
// Action Log Helpers
// ═══════════════════════════════════════════════════════════════

// ─── Auto-scroll state ───
let actionLogAutoScroll = true;

function onActionLogScroll() {
  const el = els.actionLogBody;
  if (!el) return;
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 10;
  actionLogAutoScroll = atBottom;
}

function scrollActionLogToBottom() {
  if (actionLogAutoScroll && els.actionLogBody) {
    els.actionLogBody.scrollTop = els.actionLogBody.scrollHeight;
  }
}

function formatWinnerEntry(winner) {
  if (winner.hand_name && winner.reason !== "Everyone else folded") {
    const detail = winner.hand_detail || winner.hand_name;
    return `${winner.name} wins ${winner.amount} with ${detail}`;
  }
  return `${winner.name} wins ${winner.amount}`;
}

function viewerNameFromState(state) {
  if (state && state.viewer && state.viewer.name) return state.viewer.name;
  const viewerPlayer = Array.isArray(state && state.players)
    ? state.players.find(p => p && p.is_you)
    : null;
  return viewerPlayer && viewerPlayer.name ? viewerPlayer.name : "";
}

function winnerMatchesViewer(winner, state) {
  if (!winner || !state) return false;

  const viewer = state.viewer || {};
  const viewerPlayer = Array.isArray(state.players)
    ? state.players.find(p => p && p.is_you)
    : null;

  const viewerIds = [
    viewer.player_id,
    viewer.id,
    viewer.seat_id,
    viewerPlayer && viewerPlayer.player_id,
    viewerPlayer && viewerPlayer.id,
    viewerPlayer && viewerPlayer.seat_id,
  ].filter(v => v != null).map(v => String(v));

  const winnerIds = [
    winner.player_id,
    winner.id,
    winner.seat_id,
  ].filter(v => v != null).map(v => String(v));

  if (viewerIds.length && winnerIds.some(id => viewerIds.includes(id))) return true;

  const viewerName = viewerNameFromState(state);
  return Boolean(viewerName && winner.name && String(winner.name) === String(viewerName));
}

function formatWinnerTitle(winner, state) {
  const isViewer = winnerMatchesViewer(winner, state);
  const subject = isViewer ? "You" : esc(winner.name);
  const verb = isViewer ? "win" : "wins";

  if (winner.hand_name && winner.reason !== "Everyone else folded") {
    const detail = winner.hand_detail || winner.hand_name;
    return `${subject} ${verb} ${winner.amount} with ${detail}`;
  }

  return `${subject} ${verb} ${winner.amount}`;
}

function formatPostHandTitle(winners, state = null) {
  if (!winners || winners.length === 0) return "Hand complete";
  if (winners.length === 1) return formatWinnerTitle(winners[0], state);

  const total = winners.reduce((sum, w) => sum + (Number(w.amount) || 0), 0);
  const viewerWon = winners.some(w => winnerMatchesViewer(w, state));
  if (viewerWon) return `You split ${total}`;

  const names = winners.map(w => w.name).join(", ");
  return `${names} split ${total}`;
}

const HAND_STRENGTH_ORDER = {
  "Royal Flush": 10,
  "Straight Flush": 9,
  "Four of a Kind": 8,
  "Full House": 7,
  "Flush": 6,
  "Straight": 5,
  "Three of a Kind": 4,
  "Two Pair": 3,
  "One Pair": 2,
  "High Card": 1,
};

function sortShowdownPlayersByResult(players, winners) {
  const winnerAmountByName = new Map((winners || []).map(w => [w.name, Number(w.amount) || 0]));
  return [...players].sort((a, b) => {
    const aWin = winnerAmountByName.get(a.name) || 0;
    const bWin = winnerAmountByName.get(b.name) || 0;
    if (aWin !== bWin) return bWin - aWin;

    const aStrength = HAND_STRENGTH_ORDER[a.hand_name] || 0;
    const bStrength = HAND_STRENGTH_ORDER[b.hand_name] || 0;
    if (aStrength !== bStrength) return bStrength - aStrength;

    return String(a.name).localeCompare(String(b.name));
  });
}


function collectActionEntries(state) {
  return state.action_log || state.actionLog || state.actions || state.history || state.hand_history || [];
}

function actionEntryText(entry) {
  if (typeof entry === "string") return entry;
  if (!entry) return "";
  return [
    entry.player,
    entry.actor,
    entry.name,
    entry.action,
    entry.text,
    entry.message,
    entry.amount != null ? entry.amount : "",
  ].filter(Boolean).join(" ");
}

function directPlayerDelta(player) {
  const candidates = [
    player.hand_delta,
    player.net_delta,
    player.delta,
    player.stack_delta,
    player.result_delta,
  ];
  const value = candidates.find(v => Number.isFinite(Number(v)));
  return value == null ? null : Number(value);
}

function parseContributionAmount(actionText) {
  const patterns = [
    /\bposts(?:\s+(?:sb|bb|small blind|big blind|ante|bba))?\s+(\d+)/i,
    /\bcalls\s+(\d+)/i,
    /\bbets\s+(\d+)/i,
    /\bgoes\s+all-?in\s+for\s+(\d+)/i,
    /\bis\s+all-?in\s+for\s+(\d+)/i,
    /\ball-?in\s+for\s+(\d+)/i,
  ];

  for (const pattern of patterns) {
    const match = actionText.match(pattern);
    if (match) return Number(match[1]);
  }

  return null;
}

function computeActionContributions(state) {
  const players = Array.isArray(state.players) ? state.players : [];
  const entries = collectActionEntries(state);
  const contributions = new Map(players.map(p => [p.name, 0]));
  const streetContrib = new Map(players.map(p => [p.name, 0]));

  for (const entry of entries) {
    const text = actionEntryText(entry);
    const lower = text.toLowerCase();

    if (/\bflop\b|\bturn\b|\briver\b|\bshowdown\b/.test(lower)) {
      streetContrib.clear();
      players.forEach(p => streetContrib.set(p.name, 0));
    }

    for (const player of players) {
      const name = String(player.name || "");
      if (!name || !text.startsWith(name)) continue;

      const actionText = text.slice(name.length).trim();

      const raiseMatch = actionText.match(/\braises\s+to\s+(\d+)/i);
      if (raiseMatch) {
        const target = Number(raiseMatch[1]);
        const alreadyThisStreet = streetContrib.get(name) || 0;
        const added = Math.max(0, target - alreadyThisStreet);
        contributions.set(name, (contributions.get(name) || 0) + added);
        streetContrib.set(name, target);
        continue;
      }

      const amount = parseContributionAmount(actionText);
      if (amount != null && Number.isFinite(amount)) {
        contributions.set(name, (contributions.get(name) || 0) + amount);
        streetContrib.set(name, (streetContrib.get(name) || 0) + amount);
      }
    }
  }

  return contributions;
}

function computeHandDeltas(state, winners) {
  const players = Array.isArray(state.players) ? state.players : [];
  const deltas = new Map();

  const explicit = state.hand_deltas || state.handDeltas || state.net_deltas || state.netDeltas || null;
  if (explicit && typeof explicit === "object") {
    for (const player of players) {
      const value = explicit[player.name];
      if (Number.isFinite(Number(value))) {
        deltas.set(player.name, Number(value));
      }
    }
  }

  for (const player of players) {
    const direct = directPlayerDelta(player);
    if (direct != null) {
      deltas.set(player.name, direct);
    }
  }

  const contributions = computeActionContributions(state);
  const wins = new Map(players.map(p => [p.name, 0]));
  for (const winner of winners || []) {
    wins.set(winner.name, (wins.get(winner.name) || 0) + (Number(winner.amount) || 0));
  }

  for (const player of players) {
    if (deltas.has(player.name)) continue;

    const invested = contributions.get(player.name) || 0;
    const won = wins.get(player.name) || 0;

    if (invested || won) {
      deltas.set(player.name, won - invested);
    }
  }

  return deltas;
}

function formatHandDelta(delta) {
  if (!Number.isFinite(Number(delta))) return "";
  const value = Number(delta);
  if (value > 0) return `+${value}`;
  if (value < 0) return `${value}`;
  return "±0";
}

function handDeltaClass(delta) {
  if (!Number.isFinite(Number(delta))) return "";
  const value = Number(delta);
  if (value > 0) return "gain";
  if (value < 0) return "loss";
  return "even";
}



function removeFirstCardMatch(cards, target) {
  const idx = cards.indexOf(target);
  if (idx === -1) return false;
  cards.splice(idx, 1);
  return true;
}

function publicCardList(cards) {
  return (Array.isArray(cards) ? cards : [])
    .filter(card => card && card !== "BACK" && card !== "🂠");
}

function buildBestFiveBreakdown(player, state) {
  const best = publicCardList(player.best_cards);
  const hole = publicCardList(player.cards);
  const board = publicCardList(state.community);

  // A real showdown explanation must be exactly: 7 available cards -> best 5.
  if (best.length !== 5 || hole.length !== 2 || board.length !== 5) {
    return null;
  }

  const orderedBest = sortBestFiveForDisplay(best, player.hand_name);
  const remainingHole = [...hole];
  const remainingBoard = [...board];
  const usedHole = [];
  const usedBoard = [];
  const missing = [];

  for (const card of orderedBest) {
    if (removeFirstCardMatch(remainingHole, card)) {
      usedHole.push(card);
    } else if (removeFirstCardMatch(remainingBoard, card)) {
      usedBoard.push(card);
    } else {
      missing.push(card);
    }
  }

  // Do not render a misleading explanation if the mocked/frontend state is invalid.
  if (missing.length > 0 || usedHole.length + usedBoard.length !== 5) {
    return null;
  }

  const leftOut = sortCardsHighToLow([...remainingHole, ...remainingBoard]);
  if (leftOut.length !== 2) {
    return null;
  }

  return {
    usedHole,
    usedBoard,
    leftOut,
  };
}

function renderBreakdownCardList(cards) {
  if (!cards || cards.length === 0) {
    return '<span class="breakdown-empty">none</span>';
  }
  return cards.map(card => makeCardHtml(card, "mini-card")).join("");
}

function renderBestFiveBreakdownHtml(player, state) {
  const breakdown = buildBestFiveBreakdown(player, state);
  if (!breakdown) return "";

  return `
    <div class="post-hand-breakdown" aria-label="Best five card source explanation">
      <span class="breakdown-summary">Best 5 from 7</span>
      <span class="breakdown-group">
        <span class="breakdown-label">Hole used:</span>
        <span class="breakdown-cards">${renderBreakdownCardList(breakdown.usedHole)}</span>
      </span>
      <span class="breakdown-group">
        <span class="breakdown-label">Board used:</span>
        <span class="breakdown-cards">${renderBreakdownCardList(breakdown.usedBoard)}</span>
      </span>
      <span class="breakdown-group muted">
        <span class="breakdown-label">Left out:</span>
        <span class="breakdown-cards">${renderBreakdownCardList(breakdown.leftOut)}</span>
      </span>
    </div>
  `;
}



function cardRevealButtonLabel(card, fallback) {
  if (!card || card === "BACK" || card === "🂠") return `Show ${fallback}`;
  return `Show ${card}`;
}

function playerRevealCardLabels(player) {
  const cards = Array.isArray(player && player.cards) ? player.cards : [];
  return {
    left: cardRevealButtonLabel(cards[0], "left"),
    right: cardRevealButtonLabel(cards[1], "right"),
  };
}


function foldedRevealMode(player) {
  return String(player.folded_reveal_mode || "hidden").toLowerCase();
}

function foldedCardsForModal(player) {
  const mode = foldedRevealMode(player);
  const cards = Array.isArray(player.cards) ? player.cards : [];
  const left = !isHiddenHistoryCard(cards[0]) ? cards[0] : "🂠";
  const right = !isHiddenHistoryCard(cards[1]) ? cards[1] : "🂠";

  if (mode === "left") return [left, "🂠"];
  if (mode === "right") return ["🂠", right];
  if (mode === "both") return [left, right];
  return ["🂠", "🂠"];
}


function uncontestedRevealMode(player) {
  return String(player.uncontested_reveal_mode || "hidden").toLowerCase();
}

function uncontestedRevealIsShown(player) {
  const mode = uncontestedRevealMode(player);
  return mode === "left" || mode === "right" || mode === "both";
}

function uncontestedCardsForModal(player) {
  const mode = uncontestedRevealMode(player);
  const cards = Array.isArray(player.cards) ? player.cards : [];
  const left = !isHiddenHistoryCard(cards[0]) ? cards[0] : "🂠";
  const right = !isHiddenHistoryCard(cards[1]) ? cards[1] : "🂠";

  if (mode === "left") return [left, "🂠"];
  if (mode === "right") return ["🂠", right];
  if (mode === "both") return [left, right];
  return ["🂠", "🂠"];
}

function uncontestedRevealDetail(player) {
  const mode = uncontestedRevealMode(player);
  if (mode === "both") return "Winner revealed their hand";
  if (mode === "left" || mode === "right") return "Winner showed one card";
  return "";
}

function renderUncontestedRevealActions(player) {
  if (!player.can_reveal_uncontested_hand) return "";

  const mode = uncontestedRevealMode(player);
  if (mode === "both") return "";

  const labels = playerRevealCardLabels(player);
  const buttons = [];

  if (mode !== "left") {
    buttons.push(`<button type="button" class="btn btn-tiny btn-dim" data-uncontested-reveal="left">${esc(labels.left)}</button>`);
  }
  if (mode !== "right") {
    buttons.push(`<button type="button" class="btn btn-tiny btn-dim" data-uncontested-reveal="right">${esc(labels.right)}</button>`);
  }

  buttons.push('<button type="button" class="btn btn-tiny btn-deal" data-uncontested-reveal="both">Show both</button>');

  return `<div class="folded-reveal-actions">${buttons.join("")}</div>`;
}


function foldedRevealDetail(player) {
  const mode = foldedRevealMode(player);
  if (mode === "both") {
    const detail = player.would_have_hand_detail || player.would_have_hand_name || "";
    return detail ? `Would have made ${detail}` : "Revealed folded hand";
  }
  if (mode === "left" || mode === "right") return "Revealed one card";
  if (mode === "muck") return "Mucked";
  return "Folded hand hidden";
}

function renderFoldedRevealActions(player) {
  if (!player.can_reveal_folded_hand) return "";

  const mode = foldedRevealMode(player);
  const labels = playerRevealCardLabels(player);
  const buttons = [];

  if (mode !== "left") {
    buttons.push(`<button type="button" class="btn btn-tiny btn-dim folded-reveal-btn" data-folded-reveal="left">${esc(labels.left)}</button>`);
  }
  if (mode !== "right") {
    buttons.push(`<button type="button" class="btn btn-tiny btn-dim folded-reveal-btn" data-folded-reveal="right">${esc(labels.right)}</button>`);
  }
  buttons.push('<button type="button" class="btn btn-tiny btn-deal folded-reveal-btn" data-folded-reveal="both">Show both</button>');

  if (mode === "hidden") {
    buttons.push('<button type="button" class="btn btn-tiny btn-dim folded-reveal-btn" data-folded-reveal="muck">Muck</button>');
  }

  return `<div class="folded-reveal-actions">${buttons.join("")}</div>`;
}

function renderFoldedWouldHaveBreakdown(player, state) {
  if (foldedRevealMode(player) !== "both") return "";
  if (!player.would_have_best_cards || player.would_have_best_cards.length !== 5) return "";

  return renderBestFiveBreakdownHtml({
    ...player,
    hand_name: player.would_have_hand_name,
    hand_detail: player.would_have_hand_detail,
    best_cards: player.would_have_best_cards,
  }, state);
}

function bindFoldedRevealButtons() {
  if (!els.postHandBody) return;

  els.postHandBody.querySelectorAll("[data-folded-reveal]").forEach(btn => {
    btn.onclick = () => {
      const mode = btn.dataset.foldedReveal;
      if (mode) action("reveal_folded_hand", { mode });
    };
  });

  els.postHandBody.querySelectorAll("[data-uncontested-reveal]").forEach(btn => {
    btn.onclick = () => {
      const mode = btn.dataset.uncontestedReveal || "both";
      action("reveal_uncontested_hand", { mode });
    };
  });
}




function showdownTrayParticipants(state) {
  const winners = Array.isArray(state.winners) ? state.winners : [];
  const uncontestedWinnerIds = new Set(
    winners
      .filter(w => w && w.reason === "Everyone else folded")
      .map(w => String(w.player_id || ""))
  );

  return (Array.isArray(state.players) ? state.players : [])
    .filter(p => p && !p.folded)
    .filter(p => Array.isArray(p.cards) && p.cards.length === 2)
    .filter(p => {
      const pid = String(p.player_id || p.id || "");
      const isUncontestedWinner = uncontestedWinnerIds.has(pid);
      const hiddenCards = p.cards.every(card => card === "🂠");
      return !(isUncontestedWinner && hiddenCards);
    })
    .sort((a, b) => {
      const aHero = a.is_you ? 0 : 1;
      const bHero = b.is_you ? 0 : 1;
      if (aHero !== bHero) return aHero - bHero;
      return String(a.name || "").localeCompare(String(b.name || ""));
    });
}

function renderShowdownTray(state) {
  const tray = els.showdownTray;
  if (!tray) return;

  const showdownDisplay = state.phase === "showdown" || Boolean(state.showdown_mode);
  const board = Array.isArray(state.community) ? state.community : [];
  const winners = Array.isArray(state.winners) ? state.winners : [];
  const uncontestedFoldWin = state.phase === "showdown"
    && winners.some(w => w && w.reason === "Everyone else folded");
  const contenders = uncontestedFoldWin ? [] : showdownTrayParticipants(state);

  if (!showdownDisplay) {
    tray.classList.add("hidden");
    tray.innerHTML = "";
    return;
  }

  const emptyBoardText = state.phase === "showdown" ? "No board dealt" : "Waiting for board…";
  const boardHtml = board.length
    ? board.map(card => makeCardHtml(card)).join("")
    : `<div class="showdown-board-empty">${esc(emptyBoardText)}</div>`;

  const contenderHtml = contenders.map(p => {
    const labelBits = [
      p.is_you ? '<span class="showdown-tag showdown-tag-you">YOU</span>' : '',
      p.is_bot ? '<span class="showdown-tag showdown-tag-bot">BOT</span>' : '',
      p.is_dealer ? '<span class="showdown-tag">D</span>' : '',
      p.all_in ? '<span class="showdown-tag showdown-tag-allin">ALL-IN</span>' : '',
    ].filter(Boolean).join("");

    const handText = p.hand_detail || p.hand_name || "";

    return `
      <article class="showdown-contender${p.is_you ? " is-you" : ""}">
        <div class="showdown-contender-cards">
          ${sortHoleCardsForDisplay(p.cards).map(card => makeCardHtml(card)).join("")}
        </div>
        <div class="showdown-contender-name">${esc(p.name || "Player")}</div>
        <div class="showdown-contender-tags">${labelBits}</div>
        ${handText ? `<div class="showdown-contender-hand">${esc(handText)}</div>` : ""}
      </article>
    `;
  }).join("");

  tray.innerHTML = `
    <div class="showdown-board-frame">
      <div class="showdown-board-title">${board.length === 5 ? "SHOWDOWN BOARD" : "BOARD"}</div>
      <div class="showdown-board-cards">${boardHtml}</div>
    </div>
    ${contenderHtml ? `<div class="showdown-contenders">${contenderHtml}</div>` : ""}
  `;
  tray.classList.remove("hidden");
}

function renderPostHandPanel(state) {
  if (!els.postHandPanel) return;

  const currentHandCompleteVisible = hasCurrentHandComplete(state);
  if (currentHandCompleteVisible) {
    selectedHistoryReviewKey = null;
  }

  const historyReviewState = currentHandCompleteVisible ? null : selectedHistoryReviewFromState(state);
  const historyReviewMode = Boolean(historyReviewState);
  if (historyReviewMode) {
    state = historyReviewState;
  }

  const winners = Array.isArray(state.winners) ? state.winners : [];
  const visible = historyReviewMode || (state.phase === "showdown" && winners.length > 0);
  const historyReviewVisible = visible && historyReviewMode;
  els.postHandPanel.classList.toggle("post-hand-modal", visible);
  els.postHandPanel.classList.toggle("history-review-modal", historyReviewVisible);
  syncHistoryReviewChrome(historyReviewVisible);
  els.postHandPanel.classList.toggle("hidden", !visible);

  if (!visible) {
    if (els.postHandTitle) els.postHandTitle.textContent = "";
    if (els.postHandPot) els.postHandPot.textContent = "";
    if (els.postHandBody) els.postHandBody.innerHTML = "";
    return;
  }

  if (els.postHandKicker) {
    els.postHandKicker.textContent = historyReviewMode
      ? `History review - Hand #${state.hand_number || "?"}`
      : (winners.length > 1 ? "Split pot" : "Hand complete");
  }
  if (els.postHandTitle) els.postHandTitle.textContent = formatPostHandTitle(winners, state);
  if (els.postHandPot) els.postHandPot.textContent = `Final pot ${state.pot || 0}`;

  if (els.postHandDealBtn) {
    els.postHandDealBtn.textContent = historyReviewMode ? "Close review" : "Deal next hand";
    els.postHandDealBtn.disabled = false;
  }
  if (!els.postHandBody) return;

  const winnerNames = new Set(winners.map(w => w.name));
  const winnerByName = new Map(winners.map(w => [w.name, w]));
  const players = Array.isArray(state.players) ? state.players : [];

  const revealedPlayers = players
    .filter(p => p.hand_name && p.best_cards && p.best_cards.length > 0 && !p.folded);

  const handDeltas = computeHandDeltas(state, winners);

  const revealedKeys = new Set(revealedPlayers.map(p => p.id || p.name));

  // Any player who participated in the hand but does not have a valid revealed
  // showdown hand should be treated as mucked. This is safer than relying only
  // on p.folded, and prevents folded/mucked players from disappearing in visual
  // fixtures or future partial-reveal states.
  const foldedPlayers = players
    .filter(p => {
      const key = p.id || p.name;
      if (revealedKeys.has(key)) return false;

      const invested = Number(p.total_invested || 0) > 0 || Number(p.committed || 0) > 0;
      const hasDelta = handDeltas.has(p.name);
      const hadCards = Array.isArray(p.cards) && p.cards.length > 0;

      return p.folded || invested || hasDelta || hadCards;
    })
    .sort((a, b) => {
      const aWinner = winnerNames.has(a.name) ? 0 : 1;
      const bWinner = winnerNames.has(b.name) ? 0 : 1;
      if (aWinner !== bWinner) return aWinner - bWinner;
      return String(a.name).localeCompare(String(b.name));
    });

  if (revealedPlayers.length === 0 && foldedPlayers.length === 0) {
    const historyReviewBoard = "";
    els.postHandBody.innerHTML = historyReviewBoard + winners.map(w => `
      <div class="post-hand-row winner">
        <div class="post-hand-player">
          <span class="post-hand-name">${esc(w.name)}</span>
          <span class="post-hand-result">wins</span>
        </div>
        <div class="post-hand-cards"></div>
        <div class="post-hand-detail">${esc(w.reason || "wins")}</div>
        <div class="post-hand-amount gain">+${esc(w.amount || 0)}</div>
      </div>
    `).join("");
    return;
  }

  const sortedPlayers = sortShowdownPlayersByResult(revealedPlayers, winners);

  const shownRows = sortedPlayers.map(p => {
    const isWinner = winnerNames.has(p.name);
    const detail = p.hand_detail || p.hand_name;
    const cards = sortBestFiveForDisplay(p.best_cards, p.hand_name).map(card => makeCardHtml(card, "showdown-card-flip")).join("");
    const result = isWinner ? (winners.length > 1 ? "splits" : "wins") : "shows";
    const delta = handDeltas.get(p.name);
    const amount = formatHandDelta(delta);
    const amountClass = handDeltaClass(delta);
    const breakdown = renderBestFiveBreakdownHtml(p, state);
    return `
      <div class="post-hand-row${isWinner ? " winner post-hand-winner-glow" : ""}">
        <div class="post-hand-player">
          <span class="post-hand-name">${esc(p.name)}</span>
          <span class="post-hand-result">${result}</span>
        </div>
        <div class="post-hand-cards">${cards}</div>
        <div class="post-hand-detail">${esc(detail)}</div>
        <div class="post-hand-amount ${amountClass}" title="Net result this hand">${esc(amount)}</div>
        ${breakdown}
      </div>
    `;
  }).join("");

  const muckedRows = foldedPlayers.map(p => {
    const delta = handDeltas.get(p.name);
    const amount = formatHandDelta(delta);
    const amountClass = handDeltaClass(delta);
    const mode = foldedRevealMode(p);
    const winner = winnerByName.get(p.name);
    const isUncontestedWinner = Boolean(winner && winner.reason === "Everyone else folded" && !p.hand_name);

    const isUncontestedShown = isUncontestedWinner && uncontestedRevealIsShown(p);

    const modalCards = isUncontestedWinner
      ? uncontestedCardsForModal(p)
      : foldedCardsForModal(p);
    const detail = isUncontestedWinner
      ? uncontestedRevealDetail(p)
      : foldedRevealDetail(p);
    const result = isUncontestedWinner ? (isUncontestedShown ? "shown winner" : "wins uncontested") : mode === "both" ? "revealed" : "mucked";
    const revealActions = isUncontestedWinner ? renderUncontestedRevealActions(p) : renderFoldedRevealActions(p);
    const wouldHaveBreakdown = isUncontestedWinner ? "" : renderFoldedWouldHaveBreakdown(p, state);
    const baseRowClass = isUncontestedWinner ? " winner post-hand-winner-glow uncontested" : " mucked";
    const uncontestedMode = isUncontestedWinner ? uncontestedRevealMode(p) : "";
    const rowExtraClass = isUncontestedWinner
      ? (uncontestedMode === "both" ? " revealed" : (uncontestedMode === "left" || uncontestedMode === "right") ? " partial-revealed" : "")
      : mode === "both" ? " would-have" : (mode === "left" || mode === "right") ? " partial-revealed" : "";

    return `
      <div class="post-hand-row${baseRowClass}${rowExtraClass}">
        <div class="post-hand-player">
          <span class="post-hand-name">${esc(p.name)}</span>
          <span class="post-hand-result">${esc(result)}</span>
        </div>
        <div class="post-hand-cards">
          ${modalCards.map(card => makeCardHtml(card)).join("")}
        </div>
        <div class="post-hand-detail">${esc(detail)}</div>
        <div class="post-hand-amount ${amountClass}" title="Net result this hand">${esc(amount)}</div>
        ${wouldHaveBreakdown}
        ${revealActions}
      </div>
    `;
  }).join("");

  const historyReviewBoard = "";
  els.postHandBody.innerHTML = `${historyReviewBoard}${shownRows}${muckedRows}`;
  bindFoldedRevealButtons();
}

function formatPlayerShowdownEntry(player, winnerNames) {
  if (!player.hand_name || !player.best_cards || player.best_cards.length === 0) return null;
  const cardsStr = sortBestFiveForDisplay(player.best_cards, player.hand_name).map(c => {
    const isRed = c.includes("♥") || c.includes("♦");
    return `<span class="${isRed ? "card-red" : "card-white"}">${esc(c)}</span>`;
  }).join(" ");
  const detail = player.hand_detail || player.hand_name;
  const isWinner = winnerNames && winnerNames.has(player.name);
  return { name: player.name, detail, cardsHtml: cardsStr, isWinner };
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

// ─── Render Action Log ───
function renderActionLog(state) {
  // Update hand number
  if (els.actionLogHandNum) {
    els.actionLogHandNum.textContent = state.hand_number || state.hands_played || 0;
  }

  // Clear the body
  if (!els.actionLogBody) return;
  els.actionLogBody.innerHTML = "";

  // Handle missing/undefined action_log gracefully
  const actionLog = state.action_log;
  if (!actionLog || !Array.isArray(actionLog) || actionLog.length === 0) {
    // If showdown with winners but no action log, still show winners
    if (state.phase === "showdown" && state.winners && state.winners.length > 0) {
      state.winners.forEach(winner => {
        const winDiv = document.createElement("div");
        winDiv.className = "winner-entry";
        winDiv.textContent = formatWinnerEntry(winner);
        els.actionLogBody.appendChild(winDiv);
      });
    }
    scrollActionLogToBottom();
    return;
  }

  // Iterate action_log entries with phase transition detection
  let prevPhase = null;
  let streetHasBet = false; // tracks if a bet_raise has been seen on the current street
  actionLog.forEach(entry => {
    // Detect phase transition and insert street separator
    if (prevPhase !== null && entry.phase && entry.phase !== prevPhase) {
      const separator = renderStreetSeparator(entry.phase, state.community);
      els.actionLogBody.appendChild(separator);
      streetHasBet = false; // reset on new street
    }
    prevPhase = entry.phase;

    // Mark first bet_raise on the current street for bet vs. raise distinction
    if (entry.action === "bet_raise") {
      if (!streetHasBet) {
        entry._isFirstBetOnStreet = true;
        streetHasBet = true;
      } else {
        entry._isFirstBetOnStreet = false;
      }
    }

    // Create action entry div
    const entryDiv = document.createElement("div");
    entryDiv.className = "action-entry";
    entryDiv.textContent = formatActionEntry(entry);
    els.actionLogBody.appendChild(entryDiv);
  });

  // Insert missing street separators for all-in runouts
  // (no actions logged on turn/river phases, but community cards were dealt)
  const hasRiverPhaseEntry = actionLog.some(e => e.phase === "river");
  const hasTurnPhaseEntry = actionLog.some(e => e.phase === "turn");
  const hasFlopPhaseEntry = actionLog.some(e => e.phase === "flop");
  const lastPhase = actionLog.length > 0 ? actionLog[actionLog.length - 1].phase : null;

  if (state.community && state.community.length >= 3 && !hasFlopPhaseEntry && lastPhase === "preflop") {
    const flopSeparator = renderStreetSeparator("flop", state.community);
    els.actionLogBody.appendChild(flopSeparator);
  }

  if (state.community && state.community.length >= 4 && !hasTurnPhaseEntry && (lastPhase === "flop" || lastPhase === "preflop")) {
    const turnSeparator = renderStreetSeparator("turn", state.community);
    els.actionLogBody.appendChild(turnSeparator);
  }

  if (state.community && state.community.length === 5 && !hasRiverPhaseEntry) {
    if (lastPhase === "flop" || lastPhase === "turn" || lastPhase === "preflop") {
      const riverSeparator = renderStreetSeparator("river", state.community);
      els.actionLogBody.appendChild(riverSeparator);
    }
  }

  // Append showdown details and winner entries at the bottom during showdown
  if (state.phase === "showdown" && state.winners && state.winners.length > 0) {
    // Show a showdown separator
    const showdownSep = document.createElement("div");
    showdownSep.className = "street-separator";
    showdownSep.innerHTML = `─── Showdown ───`;
    els.actionLogBody.appendChild(showdownSep);

    // Display each revealed player's best 5-card hand
    if (state.players) {
      const winners = state.winners || [];
      const winnerNames = new Set(winners.map(w => w.name));
      const winnerSuffix = winners.length > 1 ? " — splits" : " — wins";
      const revealedPlayers = state.players.filter(p => p.hand_name && p.best_cards && p.best_cards.length > 0 && !p.folded);
      revealedPlayers.forEach(p => {
        const info = formatPlayerShowdownEntry(p, winnerNames);
        if (info) {
          const handDiv = document.createElement("div");
          handDiv.className = `action-entry showdown-hand${info.isWinner ? " showdown-winner-hand" : ""}`;
          const resultSuffix = info.isWinner ? winnerSuffix : "";
          handDiv.innerHTML = `${esc(info.name)}: ${esc(info.detail)} ${info.cardsHtml}${resultSuffix}`;
          els.actionLogBody.appendChild(handDiv);
        }
      });
    }

    // Winner entries
    state.winners.forEach(winner => {
      const winDiv = document.createElement("div");
      winDiv.className = "winner-entry";
      winDiv.textContent = formatWinnerEntry(winner);
      els.actionLogBody.appendChild(winDiv);
    });
  }

  // Auto-scroll to bottom (respects manual scroll-up)
  scrollActionLogToBottom();
}

// ─── Action Log Toggle ───
const PANEL_KEY = "poker_action_log_expanded";
let panelExpanded = true; // default to expanded

function applyPanelState() {
  if (!els.actionLogPanel || !els.actionLogToggle) return;
  document.body.classList.toggle("action-log-open", panelExpanded);

  if (panelExpanded) {
    els.actionLogPanel.classList.remove("collapsed");
    els.actionLogToggle.classList.remove("panel-collapsed");
    els.actionLogToggle.textContent = "◀";
  } else {
    els.actionLogPanel.classList.add("collapsed");
    els.actionLogToggle.classList.add("panel-collapsed");
    els.actionLogToggle.textContent = "▶";
  }
}

function initActionLogToggle() {
  // Read initial state from localStorage (default to expanded/true)
  try {
    const stored = localStorage.getItem(PANEL_KEY);
    const defaultExpanded = true;
    panelExpanded = stored === null ? defaultExpanded : stored !== "false";
  } catch (e) {
    panelExpanded = true;
  }

  applyPanelState();

  // Attach click handler
  if (els.actionLogToggle) {
    els.actionLogToggle.addEventListener("click", () => {
      panelExpanded = !panelExpanded;
      applyPanelState();
      try {
        localStorage.setItem(PANEL_KEY, String(panelExpanded));
      } catch (e) {
        // Private browsing or quota exceeded — silently ignore
      }
    });
  }
}

// ═══════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════
loadSavedPlayerName();
initActionLogToggle();
initAutoDealToggle();

if (roomId && token) {
  reconnectLast();
} else {
  roomId = ""; token = "";
  connect();
  setTimeout(fetchRooms, 500);
}
