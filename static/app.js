// ═══════════════════════════════════════════════════════════════
// CUTE POKER – Client v3 (bug fixes + polish)
// ═══════════════════════════════════════════════════════════════

// ─── Hand strength lookup ───
const HAND_RANKINGS = (() => {
  const tiers = {
    1: ["AA","KK","QQ","JJ","TT","AKs","AQs","AJs","KQs","AKo","ATs","KJs","99"],
    2: ["AQo","QJs","KTs","AJo","KQo","QTs","88","A9s","K9s","A8s","ATo","JTs","77","Q9s","J9s","KJo","A7s","A5s","A6s","A4s","T9s","66","A3s"],
    3: ["KTo","K8s","QJo","A2s","55","J8s","Q8s","K7s","JTo","T8s","K6s","98s","QTo","44","K5s","87s","Q7s","K4s","33","97s","76s","22","J7s","K3s","K2s","Q6s","T7s","Q5s","86s","65s","Q4s","J9o","Q3s","J6s","96s","54s"],
    4: ["T9o","75s","Q2s","J5s","J4s","T6s","64s","98o","J3s","85s","T5s","53s","J2s","87o","T4s","74s","43s","T3s","T2s","95s","63s","76o","92s","84s","52s","65o","42s","93s","54o","32s","73s","82s"],
    5: ["62s","72s","83s","94s","86o","75o","64o","53o","43o","97o","T8o","J8o","96o","85o","74o","42o","32o","52o","62o","72o","82o","92o","T7o","Q8o","Q9o","K9o","A9o","J7o","T6o","95o","84o","73o","63o","93o","83o","94o"]
  };
  const map = {};
  let rank = 1;
  for (let t = 1; t <= 5; t++) for (const h of tiers[t]) { map[h] = { tier: t, rank }; rank++; }
  return map;
})();

function parseRank(c) { return c.startsWith("10") ? "T" : ("AKQJT98765432".includes(c[0]) ? c[0] : null); }
function parseSuit(c) { return c.includes("♠") ? "s" : c.includes("♥") ? "h" : c.includes("♦") ? "d" : c.includes("♣") ? "c" : "?"; }
function rankVal(r) { return "23456789TJQKA".indexOf(r); }

function getHandStrength(cards) {
  if (!cards || cards.length < 2 || cards.some(c => c.includes("🂠"))) return null;
  const r1 = parseRank(cards[0]), r2 = parseRank(cards[1]);
  const s1 = parseSuit(cards[0]), s2 = parseSuit(cards[1]);
  if (!r1 || !r2) return null;
  const ranks = [r1, r2].sort((a, b) => rankVal(b) - rankVal(a));
  const key = ranks[0] === ranks[1] ? ranks[0]+ranks[1] : ranks[0]+ranks[1]+(s1===s2?"s":"o");
  const info = HAND_RANKINGS[key];
  if (!info) return { tier: 4, label: "Marginal", beats: "unranked" };
  const total = Object.keys(HAND_RANKINGS).length;
  const pct = Math.round(((total - info.rank) / total) * 100);
  const labels = { 1: "Premium", 2: "Strong", 3: "Playable", 4: "Marginal", 5: "Spec" };
  return { tier: info.tier, label: labels[info.tier], beats: `beats ${pct}%` };
}

// ─── DOM refs ───
const $ = id => document.getElementById(id);
const els = {};
["status","connectScreen","gameScreen","nameInput","roomInput","createBtn","joinBtn",
"reconnectBtn","roomsList","roomId","phaseBadge","potValue","community","playerPositions","hintsToggle",
"winnerOverlay","winnerContent","yourHandBar","yourCards","handStrength","startBtn",
"foldBtn","checkCallBtn","betHalfPotBtn","betPotBtn","betAllInBtn","customBetInput",
"customBetBtn","resetBtn","adminActions","copyRoomBtn","leaveBtn","chatToggle","chatClose",
"chatPanel","chatMessages","chatInput","chatBtn","actionBar","outsBox","turnInfo",
"pauseBtn","sitOutBtn","spectateBtn","addBotBtn","removeBotBtn",
"autoDealToggle","autoDealCountdown","bbToggleBtn","potChips"
].forEach(id => { els[id] = $(id); });

// ─── Safe localStorage helpers ───
function safeGetItem(key) {
  try { return localStorage.getItem(key); }
  catch { return null; }
}
function safeSetItem(key, value) {
  try { localStorage.setItem(key, value); }
  catch { /* suppress – private browsing */ }
}

// ─── Reduced Motion Utility ───
const ReducedMotion = (() => {
  const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  let _active = mediaQuery.matches;

  // Listen for changes (user might toggle during session)
  mediaQuery.addEventListener('change', (e) => { _active = e.matches; });

  return {
    isActive() { return _active; }
  };
})();

// ─── Game History ───
function isValidGameRecord(entry) {
  if (!entry || typeof entry !== "object") return false;
  if (typeof entry.date !== "string" || !entry.date) return false;
  if (typeof entry.roomCode !== "string" || !entry.roomCode) return false;
  if (typeof entry.chipsResult !== "number" || !Number.isInteger(entry.chipsResult)) return false;
  if (typeof entry.handsPlayed !== "number" || !Number.isInteger(entry.handsPlayed) || entry.handsPlayed <= 0) return false;
  if (typeof entry.placement !== "number" || !Number.isInteger(entry.placement) || entry.placement <= 0) return false;
  return true;
}

function loadGameHistory() {
  const raw = safeGetItem("poker_game_history");
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isValidGameRecord);
  } catch {
    return [];
  }
}

function saveGameRecord(record) {
  if (!isValidGameRecord(record)) return;
  const history = loadGameHistory();
  history.push(record);
  // Cap at 20 records (FIFO eviction of oldest)
  while (history.length > 20) history.shift();
  safeSetItem("poker_game_history", JSON.stringify(history));
}

function renderGameHistoryPanel(records) {
  const body = document.querySelector(".game-history-body");
  const countEl = document.getElementById("historyCount");
  if (!body || !countEl) return;

  countEl.textContent = records.length;

  if (!records || records.length === 0) {
    // Check localStorage availability
    try {
      localStorage.getItem("test");
      body.innerHTML = '<div class="game-history-empty">No games played yet</div>';
    } catch {
      body.innerHTML = '<div class="game-history-empty">History unavailable in this browsing mode</div>';
    }
    return;
  }

  // Sort reverse chronological
  const sorted = [...records].sort((a, b) => new Date(b.date) - new Date(a.date));

  body.innerHTML = sorted.map(r => {
    const date = new Date(r.date);
    const dateStr = date.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
                    ", " + date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    const sign = r.chipsResult > 0 ? "+" : "";
    const chipClass = r.chipsResult > 0 ? "positive" : r.chipsResult < 0 ? "negative" : "zero";
    return `<div class="game-record">
      <span class="game-record-date">${esc(dateStr)}</span>
      <span class="game-record-room">${esc(r.roomCode)}</span>
      <span class="game-record-chips ${chipClass}">${sign}${r.chipsResult}</span>
      <span class="game-record-hands">${r.handsPlayed} hands</span>
    </div>`;
  }).join("");
}

// Game history panel toggle
document.addEventListener("DOMContentLoaded", () => {
  const header = document.querySelector(".game-history-header");
  const body = document.querySelector(".game-history-body");
  if (header && body) {
    header.addEventListener("click", () => {
      const expanded = header.getAttribute("aria-expanded") === "true";
      header.setAttribute("aria-expanded", !expanded);
      if (expanded) {
        body.classList.remove("expanded");
        body.classList.add("collapsed");
      } else {
        body.classList.remove("collapsed");
        body.classList.add("expanded");
      }
    });
  }
  // Render on load
  renderGameHistoryPanel(loadGameHistory());
});

// ─── Name persistence ───
function loadSavedPlayerName() {
  const saved = safeGetItem("poker_player_name");
  if (saved && saved.trim()) {
    els.nameInput.value = saved;
  }
}

function savePlayerName(name) {
  const trimmed = (name || "").trim().slice(0, 20);
  if (trimmed) {
    safeSetItem("poker_player_name", trimmed);
  }
}

let ws = null;
let roomId = localStorage.getItem("poker_room_id") || "";
let token = localStorage.getItem("poker_token") || "";
let lastState = null, prevPhase = null, isAllInRunout = false;
let winnerTimeout = null;
let winnerDismissedForPhase = null; // FIX #7: track dismissed winner
let selectedAvatar = localStorage.getItem("poker_avatar") || "🎭";
let handsPlayedInSession = 0;

// ─── Reconnection state ───
let reconnectAttempts = 0;
let reconnectTimer = null;
let intentionalDisconnect = false;

// Hints toggle state
let hintsEnabled = localStorage.getItem("poker_hints") !== "false"; // default ON

// All-in runout timing state
let allInRunoutActive = false;        // persists across phases during an all-in runout
let lastCommunityCardTime = 0;        // timestamp when the last community card was rendered
let showdownRevealTime = 0;           // timestamp when showdown state (hands face-up) arrived
let winnerOverlayDelayTimer = null;   // timer for delayed winner overlay display

// Speech bubble tracking: { botName: { text, shownAt } }
let botSpeechBubbles = {};

// Avatar picker
document.querySelectorAll(".avatar-opt").forEach(el => {
  if (el.dataset.av === selectedAvatar) el.classList.add("selected");
  else el.classList.remove("selected");
  el.onclick = () => {
    document.querySelectorAll(".avatar-opt").forEach(e => e.classList.remove("selected"));
    el.classList.add("selected");
    // Bounce animation on selection
    el.classList.remove("bounce");
    void el.offsetWidth; // trigger reflow to restart animation
    el.classList.add("bounce");
    el.addEventListener("animationend", () => el.classList.remove("bounce"), { once: true });
    selectedAvatar = el.dataset.av;
    localStorage.setItem("poker_avatar", selectedAvatar);
  };
});

// ─── Connection ───
function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return ws;
  intentionalDisconnect = false;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => {
    // Reset reconnection state on successful connection
    reconnectAttempts = 0;
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    els.status.textContent = "";
    fetchRooms();
  };
  ws.onmessage = ev => {
    const { event, payload } = JSON.parse(ev.data);
    console.log("[WS recv]", event, payload);
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
      // If reconnect failed, clear stale credentials and show lobby
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
    if (!intentionalDisconnect) {
      attemptReconnect();
    }
  };
  return ws;
}

// FIX #2: send with explicit room_id and token override
function send(event, payload = {}) {
  const s = connect();
  // Merge: payload values override globals (so join can pass token:"")
  const finalPayload = { room_id: roomId, token, ...payload };
  console.log("[WS send]", event, finalPayload);
  const msg = JSON.stringify({ event, payload: finalPayload });
  if (s.readyState === WebSocket.OPEN) s.send(msg);
  else s.addEventListener("open", () => s.send(msg), { once: true });
}

function fetchRooms() {
  // list_rooms doesn't need credentials — send clean
  const s = connect();
  const msg = JSON.stringify({ event: "list_rooms", payload: {} });
  if (s.readyState === WebSocket.OPEN) s.send(msg);
  else s.addEventListener("open", () => s.send(msg), { once: true });
}

function leaveToLobby() {
  // Save game record if player played any hands
  if (handsPlayedInSession > 0 && roomId) {
    const startStack = 1000; // STARTING_STACK constant
    const finalStack = lastState && lastState.viewer ? lastState.viewer.stack : startStack;
    const chipsResult = finalStack - startStack;
    // Calculate placement: count players with more chips
    let placement = 1;
    if (lastState && lastState.players) {
      const viewerStack = finalStack;
      placement = lastState.players.filter(p => p.stack > viewerStack && !p.is_spectator).length + 1;
    }
    saveGameRecord({
      date: new Date().toISOString(),
      roomCode: roomId,
      chipsResult: chipsResult,
      handsPlayed: handsPlayedInSession,
      placement: placement,
    });
  }
  handsPlayedInSession = 0;

  roomId = ""; token = "";
  localStorage.removeItem("poker_room_id");
  localStorage.removeItem("poker_token");
  els.gameScreen.classList.add("hidden");
  els.connectScreen.classList.remove("hidden");
  els.winnerOverlay.classList.add("hidden");
  lastState = null; prevPhase = null;
  winnerDismissedForPhase = null;
  allInRunoutActive = false;
  lastCommunityCardTime = 0;
  showdownRevealTime = 0;
  prevCommunityCards = [];
  if (winnerOverlayDelayTimer) { clearTimeout(winnerOverlayDelayTimer); winnerOverlayDelayTimer = null; }
  // Clean up showdown presenter on disconnect
  if (ShowdownPresenter.isActive()) {
    ShowdownPresenter.dismiss();
  }
  connect(); // ensure WS is alive
  setTimeout(fetchRooms, 300);
  // Re-render game history panel with updated records
  renderGameHistoryPanel(loadGameHistory());
}

// ─── Reconnection logic ───
function attemptReconnect() {
  if (intentionalDisconnect) return;
  if (!roomId || !token) return;

  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
  reconnectAttempts++;

  els.status.textContent = `Reconnecting... (attempt ${reconnectAttempts})`;

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (intentionalDisconnect) return;

    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      // Successful reconnect: reset backoff state
      reconnectAttempts = 0;
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      els.status.textContent = "";
      // Send reconnect event to rejoin the previous room
      const msg = JSON.stringify({ event: "reconnect", payload: { room_id: roomId, token } });
      ws.send(msg);
    };

    ws.onmessage = ev => {
      const { event, payload } = JSON.parse(ev.data);
      console.log("[WS recv]", event, payload);
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
      if (!intentionalDisconnect) {
        attemptReconnect();
      }
    };
  }, delay);
}

// ─── Auto-Deal System ───
const AutoDealSystem = (() => {
  let enabled = false;
  let countdownTimer = null;
  let countdownRemaining = 0;

  // Load persisted state from localStorage
  try {
    enabled = localStorage.getItem("poker_auto_deal") === "true";
  } catch (e) {
    // Private browsing or localStorage unavailable – default to disabled
  }

  function getToggleEl() { return document.getElementById("autoDealToggle"); }
  function getCountdownEl() { return document.getElementById("autoDealCountdown"); }

  function updateToggleUI() {
    const btn = getToggleEl();
    if (!btn) return;
    if (enabled) btn.classList.add("active");
    else btn.classList.remove("active");
  }

  function toggle() {
    enabled = !enabled;
    try {
      localStorage.setItem("poker_auto_deal", enabled ? "true" : "false");
    } catch (e) {
      // Private browsing – operate in-memory only
    }
    updateToggleUI();
    if (!enabled) {
      cancelCountdown();
    }
  }

  function canDeal(isAdmin, phase) {
    return isAdmin === true && phase === "showdown";
  }

  function onPhaseChange(phase) {
    if (phase === "showdown" && enabled) {
      startCountdown();
    } else {
      cancelCountdown();
    }
  }

  function startCountdown() {
    cancelCountdown(); // clear any existing countdown first
    countdownRemaining = 3;
    updateCountdownDisplay();

    countdownTimer = setInterval(() => {
      countdownRemaining--;
      if (countdownRemaining <= 0) {
        clearInterval(countdownTimer);
        countdownTimer = null;
        hideCountdownDisplay();
        // Fire the deal if still allowed
        if (enabled && lastState && canDeal(lastState.viewer.is_admin, lastState.phase)) {
          send("action", { action: "start_hand" });
        }
      } else {
        updateCountdownDisplay();
      }
    }, 1000);
  }

  function cancelCountdown() {
    if (countdownTimer) {
      clearInterval(countdownTimer);
      countdownTimer = null;
    }
    countdownRemaining = 0;
    hideCountdownDisplay();
  }

  function updateCountdownDisplay() {
    const el = getCountdownEl();
    if (!el) return;
    el.textContent = `Auto-deal in ${countdownRemaining}s`;
    el.classList.remove("hidden");
  }

  function hideCountdownDisplay() {
    const el = getCountdownEl();
    if (!el) return;
    el.textContent = "";
    el.classList.add("hidden");
  }

  // Apply initial UI state
  updateToggleUI();

  return {
    toggle,
    onPhaseChange,
    startCountdown,
    cancelCountdown,
    canDeal,
    get enabled() { return enabled; }
  };
})();

// ─── BB Display Toggle ───
const BBDisplayToggle = (() => {
  let mode = "chips"; // "chips" | "bb"

  // Load persisted mode from localStorage (fall back to in-memory if unavailable)
  try {
    const stored = localStorage.getItem("poker_bb_mode");
    if (stored === "bb" || stored === "chips") {
      mode = stored;
    }
  } catch (e) {
    // localStorage unavailable (e.g., private browsing) – operate in-memory only
  }

  function formatAmount(amount, bigBlind) {
    if (mode === "bb" && bigBlind > 0) {
      return (amount / bigBlind).toFixed(1) + " BB";
    }
    return String(Math.floor(amount));
  }

  function toggle() {
    mode = mode === "chips" ? "bb" : "chips";
    try {
      localStorage.setItem("poker_bb_mode", mode);
    } catch (e) {
      // localStorage unavailable – persist in-memory only
    }
  }

  function formatTokenAmount(rawString, bigBlind) {
    if (mode === "bb" && bigBlind > 0) {
      const numeric = parseFloat(rawString.replace(/[^0-9.\-]/g, ""));
      if (isNaN(numeric)) return rawString;
      return "+" + (numeric / bigBlind).toFixed(1) + " BB";
    }
    return rawString;
  }

  function formatSignedAmount(amount, bigBlind) {
    if (amount === 0) {
      if (mode === "bb" && bigBlind > 0) {
        return "+0.0 BB";
      }
      return "+0";
    }
    const sign = amount > 0 ? "+" : "\u2212";
    const abs = Math.abs(amount);
    if (mode === "bb" && bigBlind > 0) {
      return sign + (abs / bigBlind).toFixed(1) + " BB";
    }
    return sign + String(Math.floor(abs));
  }

  function getMode() {
    return mode;
  }

  return { formatAmount, formatTokenAmount, formatSignedAmount, toggle, getMode };
})();

// ─── Chip Denomination Decomposition ───
const DENOMINATIONS = [1000, 500, 100, 25, 5, 1];
const DENOM_COLORS = {
  1000: 'orange', 500: 'purple', 100: 'black',
  25: 'green', 5: 'red', 1: 'white'
};

function decomposeChips(amount) {
  if (typeof amount !== 'number' || isNaN(amount)) return [];
  const remaining_start = Math.max(0, Math.floor(amount));
  if (remaining_start <= 0) return [];
  const result = [];
  let remaining = remaining_start;
  for (const denom of DENOMINATIONS) {
    if (remaining >= denom) {
      const count = Math.floor(remaining / denom);
      result.push({ denom, count });
      remaining -= count * denom;
    }
    if (remaining === 0) break;
  }
  return result;
}

// ─── Denomination Chip Renderer ───
function renderDenomChips(amount, options = {}) {
  const maxVisible = options.maxVisible || 12;
  const animate = options.animate || false;

  const breakdown = decomposeChips(amount);
  if (breakdown.length === 0) return "";

  // Flatten breakdown into individual chip items (higher denoms first)
  // breakdown is already in descending denomination order from decomposeChips
  let chips = [];
  for (const { denom, count } of breakdown) {
    for (let i = 0; i < count; i++) {
      chips.push(denom);
    }
  }

  // Cap visible chips at maxVisible (keep higher denoms, trim lower ones)
  if (chips.length > maxVisible) {
    chips = chips.slice(0, maxVisible);
  }

  // Render: higher denominations at the bottom of the visual stack (rendered first)
  // Chips are already sorted descending, so first rendered = bottom of stack
  const animateClass = animate ? " chip-stack-animate" : "";
  let html = `<div class="chip-stack denom-stack${animateClass}">`;
  chips.forEach((denom, i) => {
    // Apply negative margin for stacking overlap (~60%) on all chips after the first
    const style = i > 0 ? ' style="margin-top: -60%"' : "";
    html += `<div class="chip-item chip-denom-${denom}"${style}>`;
    html += `<span class="chip-label">${denom}</span>`;
    html += `</div>`;
  });
  html += "</div>";
  return html;
}

// ─── Chip Stack Visuals ───
function getChipTier(amount, bigBlind) {
  if (amount <= 0) return null;
  if (bigBlind <= 0) return { chips: 6, tier: "medium" };
  const ratio = amount / bigBlind;
  if (ratio < 0.5) return { chips: 2, tier: "tiny" };
  if (ratio <= 2) return { chips: 4, tier: "short" };
  if (ratio <= 10) return { chips: 6, tier: "medium" };
  return { chips: 9, tier: "tall" };
}

function renderChipVisual(amount, bigBlind) {
  const tierInfo = getChipTier(amount, bigBlind);
  if (!tierInfo) return "";
  const { chips, tier } = tierInfo;
  let html = `<div class="chip-stack chip-stack-${tier}">`;
  for (let i = 0; i < chips; i++) {
    html += `<div class="chip chip-${tier}"></div>`;
  }
  html += "</div>";
  return html;
}

// ─── Position Calculator ───
const POSITION_MAP = {
  2: ['BTN', 'BB'],
  3: ['BTN', 'SB', 'BB'],
  4: ['BTN', 'SB', 'BB', 'UTG'],
  5: ['BTN', 'SB', 'BB', 'UTG', 'CO'],
  6: ['BTN', 'SB', 'BB', 'UTG', 'MP', 'CO'],
  7: ['BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'CO'],
  8: ['BTN', 'SB', 'BB', 'UTG', 'UTG+1', 'MP', 'MP+1', 'CO'],
};

const POSITION_COLORS = {
  'BTN': 'green', 'CO': 'green',
  'MP': 'yellow', 'MP+1': 'yellow',
  'UTG': 'red', 'UTG+1': 'red',
  'SB': 'blue', 'BB': 'blue',
};

function getPositionName(activePlayerCount, seatOffsetFromDealer) {
  const positions = POSITION_MAP[activePlayerCount];
  if (!positions || seatOffsetFromDealer < 0 || seatOffsetFromDealer >= positions.length) return null;
  const name = positions[seatOffsetFromDealer];
  return { name, colorGroup: POSITION_COLORS[name] };
}

// ─── Fold Animator ───
const FoldAnimator = (() => {
  /**
   * Compute CSS custom properties (--fold-dx, --fold-dy, --fold-rot) that
   * direct the card animation toward the center of the table based on the
   * player's seat position (0-indexed clockwise from dealer).
   *
   * The table center is treated as the origin. Seat positions are mapped to
   * approximate angles around the table, then the translation vector points
   * inward (toward center). Rotation is derived from the angle for variety.
   */
  function computeFoldDirection(seatPosition) {
    // Normalize seat position to an angle (radians). We distribute seats
    // evenly around the table starting from the top (12-o'clock = dealer).
    // For a generic approach, map seatPosition 0-7 onto 0–2π.
    const maxSeats = 8;
    const seat = (typeof seatPosition === "number" && seatPosition >= 0) ? seatPosition % maxSeats : 0;
    // Angle of the seat relative to center (0 = top, clockwise)
    const angle = (seat / maxSeats) * 2 * Math.PI;

    // Translation toward center: invert the seat's outward direction.
    // The magnitude is a fixed value (px) that the CSS animation will use.
    const distance = 120; // px – distance cards travel toward center
    // sin/cos give outward direction from center; negate for inward.
    const dx = Math.round(-Math.sin(angle) * distance);
    const dy = Math.round(Math.cos(angle) * distance);

    // Rotation: slight twist based on angle, capped at ±30deg
    const rot = Math.round(Math.sin(angle) * 30);

    return { dx, dy, rot };
  }

  /**
   * Play the fold animation on the given card elements.
   * Adds .fold-animate class, sets directional CSS custom properties,
   * and returns a Promise that resolves when the animation ends
   * (after removing the elements from the DOM).
   *
   * @param {HTMLElement[]} cardElements - Array of card DOM elements to animate
   * @param {number} seatPosition - Clockwise offset from dealer (0 = dealer)
   * @returns {Promise<void>}
   */
  function play(cardElements, seatPosition) {
    if (!cardElements || cardElements.length === 0) {
      return Promise.resolve();
    }

    const { dx, dy, rot } = computeFoldDirection(seatPosition);

    const promises = cardElements.map(el => {
      return new Promise(resolve => {
        // Set CSS custom properties for the animation direction
        el.style.setProperty("--fold-dx", dx + "px");
        el.style.setProperty("--fold-dy", dy + "px");
        el.style.setProperty("--fold-rot", rot + "deg");

        // Listen for animationend to remove element and resolve
        const onEnd = () => {
          el.removeEventListener("animationend", onEnd);
          if (el.parentNode) {
            el.parentNode.removeChild(el);
          }
          resolve();
        };
        el.addEventListener("animationend", onEnd);

        // Trigger the animation by adding the class
        el.classList.add("fold-animate");
      });
    });

    return Promise.all(promises).then(() => undefined);
  }

  /**
   * Instantly hide the card elements without animation.
   * Used when prefers-reduced-motion is active.
   *
   * @param {HTMLElement[]} cardElements - Array of card DOM elements to hide
   * @returns {Promise<void>}
   */
  function skipAnimation(cardElements) {
    if (!cardElements || cardElements.length === 0) {
      return Promise.resolve();
    }
    cardElements.forEach(el => {
      if (el.parentNode) {
        el.parentNode.removeChild(el);
      }
    });
    return Promise.resolve();
  }

  return { play, skipAnimation };
})();

// ─── Deal Animator ───
const DealAnimator = (() => {
  let _isPlaying = false;
  let _animationTimers = [];
  let _abortController = null;

  // Timing constants (within spec range)
  const DEAL_STAGGER = 100;       // ms between cards (range: 80–150ms)
  const DEAL_CARD_TRAVEL = 300;   // ms per card flight (range: 200–400ms)
  const DEAL_MAX_TOTAL = 5000;    // ms total sequence cap

  // Action button IDs to block during deal
  const ACTION_BTN_IDS = ['foldBtn', 'checkCallBtn', 'betHalfPotBtn', 'betPotBtn', 'betAllInBtn', 'customBetBtn'];

  function blockActions() {
    ACTION_BTN_IDS.forEach(id => {
      const btn = els[id];
      if (btn) {
        btn.disabled = true;
        btn.dataset.dealBlocked = 'true';
      }
    });
  }

  function unblockActions() {
    ACTION_BTN_IDS.forEach(id => {
      const btn = els[id];
      if (btn && btn.dataset.dealBlocked === 'true') {
        btn.disabled = false;
        delete btn.dataset.dealBlocked;
      }
    });
  }

  /**
   * Compute deal order: clockwise starting from left-of-dealer.
   * Returns an array of player indices in dealing order.
   */
  function computeDealOrder(players, dealerPosition) {
    const count = players.length;
    if (count === 0) return [];
    // Start from the player immediately after the dealer (clockwise = next index)
    const order = [];
    for (let i = 1; i <= count; i++) {
      order.push((dealerPosition + i) % count);
    }
    return order;
  }

  /**
   * Get the dealer position's screen coordinates (center-top of table area).
   * The dealer position is the origin for card animation.
   */
  function getDealerScreenPosition() {
    // Dealer position = center-top of the table area
    return { top: '15%', left: '50%' };
  }

  /**
   * Get the screen position for a player seat by index.
   */
  function getPlayerSeatPosition(playerIndex) {
    const pos = SEAT_POSITIONS[playerIndex % SEAT_POSITIONS.length];
    return pos || { top: '50%', left: '50%' };
  }

  /**
   * Create a card-back element positioned at the dealer location.
   */
  function createCardBackElement(container) {
    const card = document.createElement('div');
    card.className = 'playing-card card-back deal-card-anim';
    card.textContent = '🂠';
    card.style.position = 'absolute';
    card.style.top = '15%';
    card.style.left = '50%';
    card.style.transform = 'translate(-50%, -50%)';
    card.style.opacity = '1';
    card.style.transition = `top ${DEAL_CARD_TRAVEL}ms ease-out, left ${DEAL_CARD_TRAVEL}ms ease-out, transform ${DEAL_CARD_TRAVEL}ms ease-out`;
    card.style.zIndex = '100';
    container.appendChild(card);
    return card;
  }

  /**
   * Animate a card from dealer position to a player seat.
   * Returns a Promise that resolves when the card arrives.
   */
  function animateCardToSeat(card, playerIndex, travelTime) {
    return new Promise(resolve => {
      const seatPos = getPlayerSeatPosition(playerIndex);
      // Force reflow so the transition triggers
      void card.offsetWidth;
      card.style.top = seatPos.top;
      card.style.left = seatPos.left;
      card.style.transform = 'translate(-50%, -50%) scale(0.85)';

      const timer = setTimeout(() => {
        resolve();
      }, travelTime);
      _animationTimers.push(timer);
    });
  }

  /**
   * Flip a card element to reveal its face value.
   */
  function flipCardToFace(card, faceValue) {
    card.classList.remove('card-back');
    card.classList.add('deal-card-flip');
    card.textContent = faceValue || '';
    if (faceValue && (faceValue.includes('♥') || faceValue.includes('♦'))) {
      card.classList.add('red');
    }
  }

  /**
   * Play the full deal animation sequence.
   * @param {Array} players - Array of player objects from game state
   * @param {number} dealerPosition - Index of the dealer in the players array
   * @param {string} viewerToken - Token identifying the viewing player
   * @returns {Promise<void>}
   */
  async function play(players, dealerPosition, viewerToken) {
    if (_isPlaying) return;
    _isPlaying = true;
    _animationTimers = [];
    _abortController = { aborted: false };

    // Check prefers-reduced-motion via shared utility
    if (ReducedMotion.isActive()) {
      skip();
      return;
    }

    blockActions();

    const container = els.playerPositions;
    if (!container) {
      _isPlaying = false;
      unblockActions();
      return;
    }

    const activePlayers = players.filter(p => p.cards && p.cards.length > 0 && !p.is_spectator);
    if (activePlayers.length === 0) {
      _isPlaying = false;
      unblockActions();
      return;
    }

    // Map active players back to their indices in the full players array
    const playerIndices = activePlayers.map(p => players.indexOf(p));
    const dealerIdx = playerIndices.indexOf(dealerPosition);
    const adjustedDealerIdx = dealerIdx >= 0 ? dealerIdx : 0;

    // Compute deal order: clockwise from left-of-dealer
    const dealOrder = computeDealOrder(playerIndices, adjustedDealerIdx);
    // dealOrder contains indices into playerIndices; map to actual player array indices
    const actualDealOrder = dealOrder.map(i => playerIndices[i]);

    // Total cards = 2 per player (deal one round, then second round)
    const totalCards = actualDealOrder.length * 2;

    // Calculate actual stagger to fit within max duration cap
    // Total time = (totalCards - 1) * stagger + DEAL_CARD_TRAVEL
    const maxStagger = totalCards > 1 ? Math.floor((DEAL_MAX_TOTAL - DEAL_CARD_TRAVEL) / (totalCards - 1)) : DEAL_STAGGER;
    const stagger = Math.min(DEAL_STAGGER, maxStagger);
    const travelTime = DEAL_CARD_TRAVEL;

    // Find viewer player index
    const viewerPlayerIdx = players.findIndex(p =>
      (p.is_you) || (viewerToken && p.token === viewerToken)
    );

    // Deal sequence: round 1 (one card each), then round 2 (second card each)
    const cardElements = [];
    let cardIndex = 0;

    for (let round = 0; round < 2; round++) {
      for (let i = 0; i < actualDealOrder.length; i++) {
        if (_abortController.aborted) break;

        const playerIdx = actualDealOrder[i];
        const player = players[playerIdx];

        // Create card-back at dealer position
        const card = createCardBackElement(container);
        cardElements.push({ card, playerIdx, round });

        // Stagger delay before animating (except first card)
        if (cardIndex > 0) {
          await new Promise(resolve => {
            const t = setTimeout(resolve, stagger);
            _animationTimers.push(t);
          });
        }

        if (_abortController.aborted) break;

        // Animate to player seat
        await animateCardToSeat(card, playerIdx, travelTime);

        if (_abortController.aborted) break;

        // If this is the viewer's card, flip to reveal face
        if (playerIdx === viewerPlayerIdx && player.cards && player.cards[round]) {
          flipCardToFace(card, player.cards[round]);
        }

        cardIndex++;
      }
      if (_abortController.aborted) break;
    }

    // Clean up: remove animated card elements after a brief pause
    if (!_abortController.aborted) {
      await new Promise(resolve => {
        const t = setTimeout(resolve, 200);
        _animationTimers.push(t);
      });
    }

    // Remove deal animation cards from DOM
    cardElements.forEach(({ card }) => {
      if (card.parentNode) card.parentNode.removeChild(card);
    });

    _isPlaying = false;
    unblockActions();
  }

  /**
   * Skip animation: place cards at final positions immediately.
   * Used for reconnection/interruption scenarios.
   */
  function skip() {
    if (_abortController) {
      _abortController.aborted = true;
    }
    // Clear all pending timers
    _animationTimers.forEach(t => clearTimeout(t));
    _animationTimers = [];

    // Remove any in-flight deal animation elements
    if (els.playerPositions) {
      const dealCards = els.playerPositions.querySelectorAll('.deal-card-anim');
      dealCards.forEach(card => {
        if (card.parentNode) card.parentNode.removeChild(card);
      });
    }

    _isPlaying = false;
    unblockActions();
  }

  /**
   * Returns whether the deal animation is currently in progress.
   */
  function isPlaying() {
    return _isPlaying;
  }

  return { play, skip, isPlaying };
})();

// ─── Spectator Results Panel ───
const SpectatorResultsPanel = (() => {
  let _visible = false;
  let _panelEl = null;

  function _getOrCreatePanel() {
    if (_panelEl && _panelEl.parentNode) return _panelEl;
    _panelEl = document.createElement("div");
    _panelEl.className = "spectator-results-panel hidden";
    _panelEl.setAttribute("role", "complementary");
    _panelEl.setAttribute("aria-label", "Hand results");
    document.body.appendChild(_panelEl);
    return _panelEl;
  }

  function _formatChipChange(amount, bigBlind, bbMode) {
    if (bbMode && bigBlind > 0) {
      return BBDisplayToggle.formatSignedAmount(amount, bigBlind);
    }
    // Manual signed formatting in chips mode
    if (amount === 0) return "+0";
    const sign = amount > 0 ? "+" : "\u2212";
    return sign + String(Math.abs(amount));
  }

  /**
   * Show the spectator results sidebar.
   * @param {Array} winners - Array of winner objects with name, amount, hand_name, best_cards, etc.
   * @param {Array} players - Array of player objects from the showdown state.
   * @param {number} bigBlind - Current big blind value.
   * @param {boolean} bbMode - Whether BB display mode is active.
   */
  function show(winners, players, bigBlind, bbMode) {
    if (!winners || winners.length === 0) return;

    const panel = _getOrCreatePanel();

    // Build set of winner names for quick lookup
    const winnerNames = new Set(winners.map(w => w.name));

    // Compute total pot won (sum of winner amounts)
    const isSplitPot = winners.length > 1;

    // Build results: combine winners and losers from showdown players
    const results = [];

    // Add winners first
    for (const w of winners) {
      results.push({
        name: w.name,
        handName: w.hand_name || w.reason || "",
        bestCards: w.best_cards || [],
        netChange: w.amount || 0,
        isWinner: true,
        potShare: isSplitPot ? (w.amount || 0) : null
      });
    }

    // Add losing players (those in showdown but not winners)
    if (players && players.length > 0) {
      for (const p of players) {
        if (winnerNames.has(p.name)) continue;
        // Only include players who were in the showdown (have cards shown or committed)
        if (!p.cards || p.cards.length === 0 || p.folded) continue;
        // Net loss = their committed amount for the hand (negative)
        const netLoss = p.committed ? -p.committed : 0;
        results.push({
          name: p.name,
          handName: p.hand_name || "",
          bestCards: [],
          netChange: netLoss,
          isWinner: false,
          potShare: null
        });
      }
    }

    // Render panel HTML
    let html = `<div class="spectator-panel-header">
      <span class="spectator-panel-title">Hand Results</span>
      <button class="spectator-panel-close" aria-label="Close results panel">&times;</button>
    </div>
    <div class="spectator-panel-body">`;

    for (const r of results) {
      const changeClass = r.isWinner ? "chip-positive" : "chip-negative";
      const changeText = _formatChipChange(r.netChange, bigBlind, bbMode);

      html += `<div class="spectator-result-row ${r.isWinner ? "winner" : "loser"}">
        <div class="spectator-result-name">${esc(r.name)}</div>`;

      if (r.handName) {
        html += `<div class="spectator-result-hand">${esc(r.handName)}</div>`;
      }

      if (r.isWinner && r.bestCards && r.bestCards.length > 0) {
        html += `<div class="spectator-result-cards">${r.bestCards.map(makeCardHtml).join("")}</div>`;
      }

      if (isSplitPot && r.isWinner && r.potShare !== null) {
        const shareText = bbMode && bigBlind > 0
          ? BBDisplayToggle.formatAmount(r.potShare, bigBlind)
          : String(r.potShare);
        html += `<div class="spectator-result-share">Share: ${shareText}</div>`;
      }

      html += `<div class="spectator-result-change ${changeClass}">${changeText}</div>`;
      html += `</div>`;
    }

    html += `</div>`;

    panel.innerHTML = html;
    panel.classList.remove("hidden");
    _visible = true;

    // Attach close button handler
    const closeBtn = panel.querySelector(".spectator-panel-close");
    if (closeBtn) {
      closeBtn.onclick = () => hide();
    }
  }

  /**
   * Hide the spectator results panel.
   */
  function hide() {
    if (_panelEl) {
      _panelEl.classList.add("hidden");
    }
    _visible = false;
  }

  /**
   * Returns whether the panel is currently visible.
   */
  function isVisible() {
    return _visible;
  }

  return { show, hide, isVisible };
})();

// ─── Showdown Presenter ───
const ShowdownPresenter = (() => {
  // Timing constants (within spec ranges)
  const SHOWDOWN_CARD_DELAY = 1500;            // ms between community cards (range: 1000–2000ms)
  const SHOWDOWN_FLIP_DURATION = 500;          // ms card-flip animation (range: 400–600ms)
  const SHOWDOWN_WINNER_GLOW = 3000;           // ms winner highlight (range: 2000–4000ms)
  const SHOWDOWN_CLASSIFICATION_UPDATE = 200;  // ms max after card reveal

  let _active = false;
  let _timers = [];
  let _abortController = null;
  let _containerEl = null;
  let _dismissHandler = null;

  /**
   * Check if user prefers reduced motion (delegates to shared utility).
   */
  function _prefersReducedMotion() {
    return ReducedMotion.isActive();
  }

  /**
   * Create or get the showdown presentation container.
   */
  function _getOrCreateContainer() {
    if (_containerEl && _containerEl.parentNode) return _containerEl;
    _containerEl = document.createElement("div");
    _containerEl.className = "showdown-presenter";
    _containerEl.setAttribute("role", "region");
    _containerEl.setAttribute("aria-label", "Showdown presentation");
    _containerEl.setAttribute("aria-live", "polite");
    document.body.appendChild(_containerEl);
    return _containerEl;
  }

  /**
   * Remove the container from DOM and clean up.
   */
  function _removeContainer() {
    if (_containerEl && _containerEl.parentNode) {
      _containerEl.parentNode.removeChild(_containerEl);
    }
    _containerEl = null;
  }

  /**
   * Clear all pending timers.
   */
  function _clearTimers() {
    _timers.forEach(t => clearTimeout(t));
    _timers = [];
  }

  /**
   * Create a delayed promise that can be aborted.
   */
  function _delay(ms) {
    return new Promise(resolve => {
      if (_abortController && _abortController.aborted) { resolve(); return; }
      const t = setTimeout(resolve, ms);
      _timers.push(t);
    });
  }

  /**
   * Render hole cards for all showdown players face-up.
   */
  function _renderHoleCards(container, players) {
    let html = '<div class="showdown-hands">';
    for (const p of players) {
      const cards = (p.cards || []).map(c => makeCardHtml(c)).join("");
      const handName = p.hand_name || "";
      html += `<div class="showdown-player-hand" data-player="${esc(p.name)}">
        <div class="showdown-player-name">${esc(p.name)}</div>
        <div class="showdown-player-cards">${cards}</div>
        <div class="showdown-hand-classification">${esc(handName)}</div>
      </div>`;
    }
    html += '</div>';
    return html;
  }

  /**
   * Render community board with revealed and unrevealed cards.
   */
  function _renderCommunityBoard(revealedCards, unrevealedCount) {
    let html = '<div class="showdown-community">';
    for (const c of revealedCards) {
      html += `<div class="showdown-community-card revealed">${makeCardHtml(c)}</div>`;
    }
    for (let i = 0; i < unrevealedCount; i++) {
      html += `<div class="showdown-community-card unrevealed"><div class="playing-card card-back">🂠</div></div>`;
    }
    html += '</div>';
    return html;
  }

  /**
   * Update a specific community card slot to reveal a card with flip animation.
   */
  function _revealCommunityCard(container, cardIndex, cardValue, animate) {
    const slots = container.querySelectorAll('.showdown-community-card');
    const slot = slots[cardIndex];
    if (!slot) return;

    slot.classList.remove('unrevealed');
    slot.classList.add('revealed');
    if (animate) {
      slot.classList.add('showdown-card-flip');
    }
    slot.innerHTML = makeCardHtml(cardValue);
  }

  /**
   * Update hand classification text for all players.
   */
  function _updateClassifications(container, players) {
    for (const p of players) {
      const el = container.querySelector('[data-player="' + p.name.replace(/"/g, '\\"') + '"] .showdown-hand-classification');
      if (el && p.hand_name) {
        el.textContent = p.hand_name;
      }
    }
  }

  /**
   * Highlight winner(s) with glow effect.
   */
  function _highlightWinners(container, winners) {
    if (!winners || winners.length === 0) return;
    const winnerNames = new Set(winners.map(w => w.name));

    const handEls = container.querySelectorAll('.showdown-player-hand');
    handEls.forEach(el => {
      const playerName = el.getAttribute('data-player');
      if (winnerNames.has(playerName)) {
        el.classList.add('showdown-winner-glow');
        // Also highlight best cards if available
        const winner = winners.find(w => w.name === playerName);
        if (winner && winner.best_cards && winner.best_cards.length > 0) {
          const cardsContainer = el.querySelector('.showdown-player-cards');
          if (cardsContainer) {
            cardsContainer.classList.add('showdown-best-hand');
          }
        }
      }
    });

    // Show winner info (amount, split pot)
    const isSplitPot = winners.length > 1;
    let winnerInfoHtml = '<div class="showdown-winner-info">';
    for (const w of winners) {
      const shareLabel = isSplitPot ? ` (Split: ${w.amount || 0})` : ` (+${w.amount || 0})`;
      winnerInfoHtml += `<div class="showdown-winner-entry">
        <span class="showdown-winner-name">${esc(w.name)}</span>
        <span class="showdown-winner-hand-name">${esc(w.hand_name || w.reason || "")}</span>
        <span class="showdown-winner-amount">${shareLabel}</span>
      </div>`;
    }
    winnerInfoHtml += '</div>';

    const existingInfo = container.querySelector('.showdown-winner-info');
    if (existingInfo) existingInfo.remove();
    container.insertAdjacentHTML('beforeend', winnerInfoHtml);
  }

  /**
   * Show the final result state immediately (used by skip and reduced motion).
   */
  function _showFinalState(state) {
    const container = _getOrCreateContainer();

    // Compute the full community (revealed + remaining)
    const allCommunity = (state.community || []).concat(state.remaining_community || []);

    // Build final layout
    let html = _renderCommunityBoard(allCommunity, 0);
    html += _renderHoleCards(container, state.players || []);
    container.innerHTML = html;

    // Update all classifications to final values
    _updateClassifications(container, state.players || []);

    // Highlight winners
    _highlightWinners(container, state.winners || []);

    container.classList.add('showdown-visible');
  }

  /**
   * Present the dramatic showdown sequence.
   * @param {Object} state - Showdown state with players, community, winners, remaining_community
   */
  async function present(state) {
    if (_active) skip();

    _active = true;
    _abortController = { aborted: false };
    _timers = [];

    const container = _getOrCreateContainer();
    container.classList.add('showdown-visible');

    // Check reduced motion preference
    if (_prefersReducedMotion()) {
      _showFinalState(state);
      _active = false;
      return;
    }

    // Wire early dismissal handler (click/tap skips remaining delays)
    _dismissHandler = () => { skip(); };
    container.addEventListener('click', _dismissHandler);
    document.addEventListener('keydown', _onKeyDismiss);

    const players = state.players || [];
    const community = state.community || [];
    const remainingCommunity = state.remaining_community || [];
    const winners = state.winners || [];

    // Step 1: Display all players' hole cards face-up
    const revealedCount = community.length;
    const unrevealedCount = remainingCommunity.length;

    let html = _renderCommunityBoard(community, unrevealedCount);
    html += _renderHoleCards(container, players);
    container.innerHTML = html;

    if (_abortController.aborted) return;

    // Step 2: If community cards remain (all-in runout), reveal one-at-a-time
    if (remainingCommunity.length > 0) {
      for (let i = 0; i < remainingCommunity.length; i++) {
        if (_abortController.aborted) break;

        // Delay between cards
        await _delay(SHOWDOWN_CARD_DELAY);
        if (_abortController.aborted) break;

        // Reveal card with flip animation
        const cardIndex = revealedCount + i;
        _revealCommunityCard(container, cardIndex, remainingCommunity[i], true);

        // Wait for flip animation to complete
        await _delay(SHOWDOWN_FLIP_DURATION);
        if (_abortController.aborted) break;

        // Update hand classifications within 200ms
        // (In production, the server would send updated classifications;
        //  here we use whatever is in the state, updated per-card if available)
        if (state.classifications_per_card && state.classifications_per_card[i]) {
          // Update players' hand_name with per-card classification data
          for (const p of players) {
            const classification = state.classifications_per_card[i][p.name];
            if (classification) {
              p.hand_name = classification;
            }
          }
        }
        _updateClassifications(container, players);

        await _delay(SHOWDOWN_CLASSIFICATION_UPDATE);
        if (_abortController.aborted) break;
      }
    }
    // Step 4: If all 5 community cards already dealt, skip card reveal
    // (handled implicitly: remainingCommunity will be empty)

    if (_abortController.aborted) return;

    // Step 3: Highlight winner(s) with glow effect
    _highlightWinners(container, winners);

    // Winner glow duration
    await _delay(SHOWDOWN_WINNER_GLOW);

    // Presentation complete
    _cleanup();
  }

  /**
   * Handle keyboard dismissal (Escape or Enter).
   */
  function _onKeyDismiss(e) {
    if (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') {
      skip();
    }
  }

  /**
   * Clean up event listeners and state (but leave DOM visible for final result).
   */
  function _cleanup() {
    if (_dismissHandler && _containerEl) {
      _containerEl.removeEventListener('click', _dismissHandler);
    }
    document.removeEventListener('keydown', _onKeyDismiss);
    _dismissHandler = null;
    _clearTimers();
    _active = false;
  }

  /**
   * Jump to final result immediately, skipping remaining delays.
   */
  function skip() {
    if (!_active && !_containerEl) return;

    // Abort any in-progress sequence
    if (_abortController) {
      _abortController.aborted = true;
    }
    _clearTimers();

    // If we have a container, show the final state
    // Try to reconstruct from the last state passed to present()
    if (_containerEl) {
      // Show final result by ensuring all cards are revealed and winners highlighted
      const unrevealed = _containerEl.querySelectorAll('.showdown-community-card.unrevealed');
      unrevealed.forEach(slot => {
        // Mark as revealed without animation
        slot.classList.remove('unrevealed');
        slot.classList.add('revealed');
      });

      // Ensure winner glow is applied
      const hasGlow = _containerEl.querySelector('.showdown-winner-glow');
      if (!hasGlow) {
        // Winners info might not be applied yet; at minimum mark presentation as done
      }
    }

    _cleanup();
  }

  /**
   * Returns whether showdown presentation is currently in progress.
   */
  function isActive() {
    return _active;
  }

  /**
   * Completely remove the showdown presentation from DOM.
   * Called when moving to next hand or cleaning up.
   */
  function dismiss() {
    skip();
    _removeContainer();
  }

  return { present, skip, isActive, dismiss };
})();

// ─── Room list ───
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

// ─── Actions ───
function createRoom() {
  savePlayerName(els.nameInput.value);
  send("create", { name: els.nameInput.value || "Player", avatar: selectedAvatar });
}

// FIX #2: Clear globals BEFORE sending join so payload is clean
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

// ─── Render ───
function renderState(state) {
  const active = state.players.filter(p => !p.folded && p.cards && p.cards.length > 0);
  const canAct = active.filter(p => !p.all_in && p.stack > 0);
  const newPhase = prevPhase && prevPhase !== state.phase;

  // Detect all-in runout: all active players are all-in (none can act)
  // Set the persistent flag when we first detect it, keep it until new hand
  if (newPhase && canAct.length === 0 && active.length > 1 && !["showdown","lobby","preflop"].includes(state.phase)) {
    allInRunoutActive = true;
  }
  isAllInRunout = allInRunoutActive && !["showdown","lobby"].includes(state.phase);

  // Track when community cards change (new card dealt)
  const prevCommunityCount = lastState ? (lastState.community ? lastState.community.length : 0) : 0;
  const currCommunityCount = state.community ? state.community.length : 0;
  if (currCommunityCount > prevCommunityCount) {
    lastCommunityCardTime = Date.now();
  }

  // Track when showdown arrives (hands revealed face-up)
  if (newPhase && state.phase === "showdown" && allInRunoutActive) {
    showdownRevealTime = Date.now();
  }

  // FIX #7: Reset winner dismissed tracker on new hand
  if (newPhase && state.phase === "preflop") {
    winnerDismissedForPhase = null;
    allInRunoutActive = false;
    lastCommunityCardTime = 0;
    showdownRevealTime = 0;
    prevCommunityCards = [];
    if (winnerOverlayDelayTimer) { clearTimeout(winnerOverlayDelayTimer); winnerOverlayDelayTimer = null; }
    handsPlayedInSession++;
    // Hide spectator results panel when next hand begins
    if (SpectatorResultsPanel.isVisible()) {
      SpectatorResultsPanel.hide();
    }
    // ─── ShowdownPresenter interruption: dismiss on next hand (req 7.6, 7.7) ───
    if (ShowdownPresenter.isActive()) {
      ShowdownPresenter.dismiss();
    }
  }

  // ─── ShowdownPresenter Integration (req 7.1, 7.6, 7.7) ───
  // Detect showdown state transition: phase just changed to showdown with 2+ active players
  if (newPhase && state.phase === "showdown" && active.length >= 2) {
    // Build the showdown state object expected by present()
    const showdownPlayers = active.map(p => ({
      name: p.name,
      cards: p.cards || [],
      hand_name: p.hand_name || "",
      best_cards: p.best_cards || []
    }));
    const community = state.community || [];
    // Determine remaining community cards for all-in runouts
    // If fewer than 5 community cards and it was an all-in situation, there may be remaining cards
    const remainingCommunity = (allInRunoutActive && community.length < 5 && state.remaining_community)
      ? state.remaining_community
      : [];
    const showdownState = {
      players: showdownPlayers,
      community: community,
      remaining_community: remainingCommunity,
      winners: state.winners || [],
      classifications_per_card: state.classifications_per_card || null
    };
    ShowdownPresenter.present(showdownState);
  }

  // ─── ShowdownPresenter: update winners if they arrive in a subsequent state update ───
  if (state.phase === "showdown" && !newPhase && ShowdownPresenter.isActive()
      && state.winners && state.winners.length > 0) {
    // Winners arrived after initial showdown trigger; the presenter may need winner info
    // Re-present is not ideal, so we let the current presentation finish—
    // the winners are already passed to present() if available at initial trigger.
    // If they weren't available initially, we can skip() to show final results with winners.
    const container = document.querySelector('.showdown-presenter');
    if (container && !container.querySelector('.showdown-winner-glow')) {
      // Winners weren't highlighted yet — skip to final state showing winners
      ShowdownPresenter.skip();
    }
  }
  // Auto-deal: notify on phase change only (avoid restarting countdown on re-renders)
  if (newPhase) {
    AutoDealSystem.onPhaseChange(state.phase);
  }

  // ─── Deal Animation Integration ───
  // Mid-deal interruption: if DealAnimator is playing and phase changes unexpectedly, snap to final
  if (DealAnimator.isPlaying() && newPhase && state.phase !== "preflop") {
    DealAnimator.skip();
  }

  // Detect new hand deal or reconnection
  const playersHaveCards = state.players.some(p => p.cards && p.cards.length > 0 && !p.is_spectator);
  if (state.phase === "preflop" && playersHaveCards) {
    if (!prevPhase && !lastState) {
      // Reconnection: first state received with cards already present → skip animation
      DealAnimator.skip();
    } else if (newPhase && (prevPhase === "lobby" || prevPhase === "showdown")) {
      // New hand starting: trigger deal animation
      const dealerIdx = state.players.findIndex(p => p.is_dealer);
      const dealerPosition = dealerIdx >= 0 ? dealerIdx : 0;
      DealAnimator.play(state.players, dealerPosition, token);
    }
  }

  // ─── Fold Detection: compare previous state to detect newly-folded players ───
  let newlyFoldedIndices = [];
  if (lastState && lastState.players) {
    state.players.forEach((p, idx) => {
      const prev = lastState.players[idx];
      if (prev && !prev.folded && p.folded) {
        newlyFoldedIndices.push(idx);
      }
    });
  }

  // Capture previous message count BEFORE reassigning lastState (used for bot speech bubble detection below)
  const prevMsgCount = lastState && lastState.messages ? lastState.messages.length : 0;

  prevPhase = state.phase;
  lastState = state;

  els.roomId.textContent = state.room_id;
  els.phaseBadge.textContent = state.paused ? "PAUSED" : state.phase.toUpperCase();
  els.potValue.textContent = BBDisplayToggle.formatAmount(state.pot, state.big_blind);

  // Render pot chip visual proportional to total pot size
  if (els.potChips) {
    els.potChips.innerHTML = state.pot > 0 ? renderDenomChips(state.pot, { animate: true }) : "";
  }

  // FIX #3: Turn indication - highlight action bar
  const isMyTurn = state.viewer.is_turn;
  if (isMyTurn) {
    els.turnInfo.textContent = state.viewer.to_call > 0 ? `⚡ YOUR TURN · Call ${BBDisplayToggle.formatAmount(state.viewer.to_call, state.big_blind)}` : "⚡ YOUR TURN";
    els.turnInfo.className = "turn-indicator your-turn";
    els.actionBar.classList.add("my-turn");
  } else {
    els.turnInfo.textContent = "";
    els.turnInfo.className = "turn-indicator";
    els.actionBar.classList.remove("my-turn");
  }

  // Admin / deal button
  const canDeal = ["lobby", "showdown"].includes(state.phase) && !state.paused;

  // Start button in action row
  els.startBtn.style.display = canDeal ? "" : "none";

  // Admin side panel
  if (state.viewer.is_admin) {
    els.adminActions.classList.remove("hidden");
    els.resetBtn.style.display = "";
    els.pauseBtn.style.display = "";
    els.addBotBtn.style.display = "";
    els.removeBotBtn.style.display = "";
    if (els.pauseBtn) els.pauseBtn.textContent = state.paused ? "▶ Resume" : "⏸ Pause";
  } else {
    els.adminActions.classList.add("hidden");
  }

  // Sit-out / spectate
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

  renderCommunity(state.community);
  renderYourHand(viewerData);

  // Detect new bot messages for speech bubbles
  if (state.messages && state.messages.length > 0) {
    if (state.messages.length > prevMsgCount) {
      const newMsgs = state.messages.slice(prevMsgCount);
      const botNames = state.players.filter(p => p.is_bot).map(p => p.name);
      newMsgs.forEach(m => {
        if (botNames.includes(m.name)) {
          botSpeechBubbles[m.name] = { text: m.text, shownAt: Date.now() };
        }
      });
    }
  }

  renderPlayers(state.players);

  // ─── Fold Animation: trigger for newly-folded players after DOM is built ───
  if (newlyFoldedIndices.length > 0) {
    const prefersReducedMotion = ReducedMotion.isActive();
    const seatElements = els.playerPositions.querySelectorAll('.player-seat');

    newlyFoldedIndices.forEach(idx => {
      const seatEl = seatElements[idx];
      if (!seatEl) return;

      // Immediately apply .folded opacity state (req 3.4)
      seatEl.classList.add('folded');

      // Get seat_offset_from_dealer for animation direction
      const player = state.players[idx];
      const seatPosition = player && player.seat_offset_from_dealer != null
        ? player.seat_offset_from_dealer
        : idx;

      // For the viewer (is_you), cards are in the hand bar, not in the seat
      let cardElements = [];
      if (player && player.is_you) {
        cardElements = Array.from(els.yourCards.querySelectorAll('.playing-card'));
      } else {
        const cardContainer = seatEl.querySelector('.seat-cards');
        if (cardContainer) {
          cardElements = Array.from(cardContainer.querySelectorAll('.playing-card'));
        }
      }
      if (cardElements.length === 0) return;

      if (prefersReducedMotion) {
        // Skip animation: instantly remove cards (req 3.6)
        FoldAnimator.skipAnimation(cardElements);
      } else {
        // Play fold animation (req 3.1, 3.2, 3.3, 3.5)
        FoldAnimator.play(cardElements, seatPosition);
      }
    });
  }

  renderActionDirection(state);

  // ─── Spectator vs Active Player winner display ───
  // Spectators see the non-intrusive sidebar panel; active players see the full-screen overlay
  if (state.winners && state.winners.length > 0 && viewerData && viewerData.is_spectator === true) {
    // Spectator: show SpectatorResultsPanel, suppress full-screen winner overlay
    SpectatorResultsPanel.show(
      state.winners,
      state.players,
      state.big_blind,
      BBDisplayToggle.getMode() === "bb"
    );
    // Ensure the winner overlay is hidden for spectators
    els.winnerOverlay.classList.add("hidden");
    if (winnerTimeout) { clearTimeout(winnerTimeout); winnerTimeout = null; }
  } else {
    // Active player: use existing winner overlay behavior
    renderWinners(state.winners, viewerData);
  }

  // Hide spectator panel when phase transitions away from showdown (e.g., hand ended without new preflop yet)
  if (newPhase && state.phase !== "showdown" && state.phase !== "preflop" && SpectatorResultsPanel.isVisible()) {
    SpectatorResultsPanel.hide();
  }

  renderChat(state.messages);

  // Button labels
  if (isMyTurn) {
    els.checkCallBtn.textContent = state.viewer.to_call > 0 ? `Call ${BBDisplayToggle.formatAmount(state.viewer.to_call, state.big_blind)}` : "Check";
    els.customBetInput.placeholder = `Min ${BBDisplayToggle.formatAmount(state.current_bet + state.min_raise, state.big_blind)}`;
  } else {
    els.checkCallBtn.textContent = "Check / Call";
    els.customBetInput.placeholder = "Raise to...";
  }

  // Disable action buttons while deal animation is in progress (req 4.5)
  // DealAnimator.play() calls blockActions() internally, but reinforce here in case
  // renderState fires between _isPlaying=true and blockActions() during async setup.
  if (DealAnimator.isPlaying()) {
    [els.foldBtn, els.checkCallBtn, els.betHalfPotBtn, els.betPotBtn, els.betAllInBtn, els.customBetBtn].forEach(btn => {
      if (btn) {
        btn.disabled = true;
        btn.dataset.dealBlocked = 'true';
      }
    });
  }
}

// FIX #4: Longer stagger delays for card dealing
let prevCommunityCards = [];
function renderCommunity(cards) {
  els.community.innerHTML = "";
  if (!cards || cards.length === 0) {
    els.community.innerHTML = '<span class="hint-text">Waiting for deal...</span>';
    prevCommunityCards = [];
    return;
  }
  const prevCount = prevCommunityCards.length;
  cards.forEach((c, i) => {
    const el = makeCard(c);
    if (isAllInRunout && i >= prevCount) {
      // Only slow-reveal NEW cards, not already-visible ones
      el.classList.add("slow-reveal");
      el.style.animationDelay = `${(i - prevCount) * 0.5}s`;
    } else if (i >= prevCount) {
      el.style.animationDelay = `${(i - prevCount) * 0.12}s`;
    }
    els.community.appendChild(el);
  });
  prevCommunityCards = [...cards];
}

function renderYourHand(viewer) {
  if (!viewer || !viewer.cards || viewer.cards.length === 0) {
    els.yourHandBar.classList.remove("hand-bar-enter");
    els.yourHandBar.classList.add("hand-bar-hidden");
    return;
  }
  const isBack = c => c === "🂠" || c.includes("🂠") || c === "BACK";
  if (viewer.cards.every(isBack)) {
    els.yourHandBar.classList.remove("hand-bar-enter");
    els.yourHandBar.classList.add("hand-bar-hidden");
    return;
  }

  els.yourHandBar.classList.remove("hand-bar-hidden");
  els.yourHandBar.classList.add("hand-bar-enter");
  els.yourCards.innerHTML = "";
  viewer.cards.forEach(c => els.yourCards.appendChild(makeCard(c)));

  const odds = lastState && lastState.viewer && lastState.viewer.odds;
  if (odds && hintsEnabled) {
    let parts = [];
    if (odds.made_hand) parts.push(odds.made_hand);
    if (odds.is_nuts) parts.push("🔥 NUTS");
    else if (odds.nuts_rank === 2) parts.push("2nd Nuts");
    else if (odds.nuts_rank === 3) parts.push("3rd Nuts");
    if (odds.draws && odds.draws.length > 0) parts.push(odds.draws.join(" + "));
    if (odds.equity !== null && odds.equity !== undefined) {
      let eqStr = `${odds.equity}%`;
      if (odds.current_ahead !== null) eqStr += `/${odds.current_ahead}%ahead`;
      parts.push(eqStr);
    }
    els.handStrength.textContent = parts.join(" · ");
    const eq = odds.equity || 50;
    const tier = odds.is_nuts ? 1 : eq >= 65 ? 1 : eq >= 45 ? 2 : eq >= 30 ? 3 : eq >= 15 ? 4 : 5;
    els.handStrength.className = `hand-strength-badge tier-${tier}`;
  } else if (hintsEnabled) {
    const str = getHandStrength(viewer.cards);
    if (str) { els.handStrength.textContent = `${str.label} · ${str.beats}`; els.handStrength.className = `hand-strength-badge tier-${str.tier}`; }
    else { els.handStrength.textContent = ""; els.handStrength.className = "hand-strength-badge"; }
  } else {
    els.handStrength.textContent = "";
    els.handStrength.className = "hand-strength-badge";
  }
}

// ─── Seat Indicator & Position Badge ───
function renderSeatIndicator(player) {
  const seatNum = player.seat || 0;
  if (seatNum < 1 || seatNum > 8) return "";
  return `<span class="seat-indicator">${seatNum}</span>`;
}

function renderPositionBadge(player, activePlayerCount) {
  // Only display position labels during an active hand
  const activePhases = ["preflop", "flop", "turn", "river", "showdown"];
  if (!lastState || !activePhases.includes(lastState.phase)) return "";

  // Skip unoccupied/sitting-out/spectating seats (their offset will be null)
  if (player.sitting_out || player.is_spectator) return "";
  if (player.seat_offset_from_dealer == null) return "";

  const posInfo = getPositionName(activePlayerCount, player.seat_offset_from_dealer);
  if (!posInfo) return "";

  return `<span class="position-label pos-${posInfo.colorGroup}">${posInfo.name}</span>`;
}

// ─── Active Player Highlighting ───
function renderActiveHighlight(player) {
  // Returns the active-turn class string if this player is the current actor.
  // Used by renderPlayers to apply border glow on the action player's seat.
  if (player.is_action) return " active-turn";
  return "";
}

// ─── Action Direction Indicator ───
function renderActionDirection(state) {
  // Remove any existing direction arrow
  const existing = document.querySelector(".action-direction-arrow");
  if (existing) existing.remove();

  // Only show during active betting phases
  if (!["preflop", "flop", "turn", "river"].includes(state.phase)) return;

  // Find the current action player and the next action player
  const players = state.players;
  const actionIdx = players.findIndex(p => p.is_action);
  if (actionIdx === -1) return;

  // Find the next non-folded, non-all-in player after the action player (clockwise)
  let nextIdx = -1;
  for (let offset = 1; offset < players.length; offset++) {
    const idx = (actionIdx + offset) % players.length;
    const p = players[idx];
    if (!p.folded && !p.all_in && p.stack > 0 && p.cards && p.cards.length > 0) {
      nextIdx = idx;
      break;
    }
  }
  if (nextIdx === -1) return;

  // Get positions of the current and next action player seats
  const fromPos = SEAT_POSITIONS[actionIdx % SEAT_POSITIONS.length];
  const toPos = SEAT_POSITIONS[nextIdx % SEAT_POSITIONS.length];

  // Parse percentage positions to numeric values
  const fromX = parseFloat(fromPos.left);
  const fromY = parseFloat(fromPos.top);
  const toX = parseFloat(toPos.left);
  const toY = parseFloat(toPos.top);

  // Calculate midpoint and angle for the arrow
  const midX = (fromX + toX) / 2;
  const midY = (fromY + toY) / 2;
  const angle = Math.atan2(toY - fromY, toX - fromX) * (180 / Math.PI);

  // Create the arrow element
  const arrow = document.createElement("div");
  arrow.className = "action-direction-arrow";
  arrow.style.top = midY + "%";
  arrow.style.left = midX + "%";
  arrow.style.transform = `translate(-50%, -50%) rotate(${angle}deg)`;
  arrow.innerHTML = "➤";

  els.playerPositions.appendChild(arrow);
}

function renderPlayers(players) {
  els.playerPositions.innerHTML = "";

  // Calculate active player count (non-sitting-out, non-spectator) for position labels
  const activePlayerCount = players.filter(p => !p.sitting_out && !p.is_spectator).length;

  players.forEach((p, idx) => {
    const pos = SEAT_POSITIONS[idx % SEAT_POSITIONS.length];
    const seat = document.createElement("div");
    let cls = "player-seat";
    cls += renderActiveHighlight(p);
    if (p.folded) cls += " folded";
    if (p.is_you) cls += " is-you";
    seat.className = cls;
    seat.style.top = pos.top;
    seat.style.left = pos.left;
    seat.style.transform = "translate(-50%, -50%)";

    const badges = [];
    if (p.is_you) badges.push('<span class="seat-badge">YOU</span>');
    if (p.is_bot) badges.push('<span class="seat-badge">🤖</span>');
    if (p.all_in) badges.push('<span class="seat-badge">ALL-IN</span>');
    if (p.folded) badges.push('<span class="seat-badge warn">FOLD</span>');
    if (!p.connected && !p.is_bot) badges.push('<span class="seat-badge warn">DC</span>');
    if (p.sitting_out) badges.push('<span class="seat-badge warn">SIT OUT</span>');
    if (p.is_spectator) badges.push('<span class="seat-badge">👁</span>');

    let cards = "";
    if (p.cards && p.cards.length > 0 && !p.is_you) {
      cards = `<div class="seat-cards">${p.cards.map(makeCardHtml).join("")}</div>`;
    }

    // Spectator hand strength display
    let spectatorInfo = "";
    if (p.hand_classification) {
      const tierColors = { gold: "#ffca28", green: "#66bb6a", blue: "#42a5f5", gray: "#78909c" };
      const tierTextColors = { gold: "#1a1a1a", green: "#1a1a1a", blue: "#1a1a1a", gray: "#fff" };
      const equityBadge = p.equity_pct != null && p.equity_tier
        ? `<span class="spectator-equity" style="background:${tierColors[p.equity_tier] || '#78909c'};color:${tierTextColors[p.equity_tier] || '#fff'}">${p.equity_pct}%</span>`
        : "";
      spectatorInfo = `<div class="spectator-info"><span class="spectator-hand-class">${esc(p.hand_classification)}</span>${equityBadge}</div>`;
    }

    // Speech bubble: show most recent chat from this bot (within last 5 seconds)
    let speechBubble = "";
    if (p.is_bot && botSpeechBubbles[p.name]) {
      const bubble = botSpeechBubbles[p.name];
      if (Date.now() - bubble.shownAt < 5000) {
        speechBubble = `<div class="speech-bubble">${esc(bubble.text)}</div>`;
      }
    }

    const seatIndicator = renderSeatIndicator(p);
    const positionBadge = renderPositionBadge(p, activePlayerCount);

    seat.innerHTML = `
      ${speechBubble}
      ${seatIndicator}
      <div class="seat-header"><span class="seat-avatar">${p.avatar||"🎭"}</span><span class="seat-name">${esc(p.name)}</span><span class="seat-stack">💰${BBDisplayToggle.formatAmount(p.stack, lastState.big_blind)}</span></div>
      ${positionBadge ? `<div class="seat-position-row">${positionBadge}</div>` : ""}
      <div class="seat-badges">${badges.join("")}</div>
      ${cards}
      ${spectatorInfo}
      ${p.committed > 0 ? `<div class="seat-chips">${renderDenomChips(p.committed, { animate: true })}</div>` : ""}
      ${p.committed > 0 ? `<div class="seat-meta">Bet: ${BBDisplayToggle.formatAmount(p.committed, lastState.big_blind)}</div>` : ""}
      ${p.hand_name ? `<div class="seat-meta" style="color:var(--gold-light)">${esc(p.hand_name)}</div>` : ""}
    `;
    els.playerPositions.appendChild(seat);
  });
}

// FIX #6 & #7: Winner differentiation + don't re-show after dismiss
function renderWinners(winners, viewer) {
  if (winnerTimeout) { clearTimeout(winnerTimeout); winnerTimeout = null; }

  if (!winners || winners.length === 0) {
    els.winnerOverlay.classList.add("hidden");
    return;
  }

  // FIX #7: Don't re-show if user already dismissed for this showdown
  if (winnerDismissedForPhase === "showdown") {
    return;
  }

  // All-in runout delay: ensure the winner overlay doesn't appear too quickly
  // after cards are revealed and hands are shown face-up
  if (allInRunoutActive && !winnerOverlayDelayTimer) {
    const now = Date.now();
    // Calculate minimum delay based on timing requirements:
    // - At least 2.5s after last community card appeared
    // - At least 2.0s after showdown state (hands face-up)
    // - At least 1.5s from when showdown card reveal became visible
    const sinceLastCard = lastCommunityCardTime ? now - lastCommunityCardTime : Infinity;
    const sinceShowdown = showdownRevealTime ? now - showdownRevealTime : Infinity;

    const delayForCards = Math.max(0, 2500 - sinceLastCard);
    const delayForFaceUp = Math.max(0, 2000 - sinceShowdown);
    const delayForReveal = Math.max(0, 1500 - sinceShowdown);

    const delay = Math.max(delayForCards, delayForFaceUp, delayForReveal);

    if (delay > 0) {
      winnerOverlayDelayTimer = setTimeout(() => {
        winnerOverlayDelayTimer = null;
        showWinnerOverlay(winners, viewer);
      }, delay);
      return;
    }
  }

  showWinnerOverlay(winners, viewer);
}

function showWinnerOverlay(winners, viewer) {
  // FIX #7: Don't re-show if user already dismissed for this showdown
  if (winnerDismissedForPhase === "showdown") {
    return;
  }

  els.winnerOverlay.classList.remove("hidden");
  const w = winners[0];
  const viewerWon = viewer && winners.some(x => x.name === viewer.name);
  const best = w.best_cards && w.best_cards.length ? `<div class="winner-best-cards">${w.best_cards.map(makeCardHtml).join("")}</div>` : "";
  const others = winners.length > 1 ? `<div style="font-size:12px;color:var(--text-dim);margin-top:6px">Split: ${winners.slice(1).map(x=>esc(x.name)).join(", ")}</div>` : "";

  // FIX #6: Different message if you won vs lost
  const trophy = viewerWon ? "🎉" : "💀";
  const headline = viewerWon ? "You Won!" : "You Lost";
  const subline = viewerWon ? "" : `<div style="font-size:14px;color:var(--text-dim);margin-bottom:4px">${esc(w.name)} wins with ${esc(w.hand_name||w.reason)}</div>`;

  els.winnerContent.innerHTML = `
    <div class="winner-trophy">${trophy}</div>
    <div class="winner-name">${headline}</div>
    ${viewerWon ? `<div class="winner-amount">${BBDisplayToggle.formatTokenAmount("+" + w.amount, lastState ? lastState.big_blind : 0)}</div>` : subline}
    ${viewerWon ? `<div class="winner-hand">${esc(w.hand_name||w.reason)}</div>` : ""}
    ${best}${others}
    <div class="winner-dismiss">Tap to dismiss</div>
  `;

  // Auto-dismiss: shorter if you lost
  const dismissTime = viewerWon ? 10000 : 5000;
  winnerTimeout = setTimeout(() => els.winnerOverlay.classList.add("hidden"), dismissTime);
}

// FIX #7: Chat rendering is separate from winner display
function renderChat(messages) {
  if (!messages) return;
  els.chatMessages.innerHTML = messages.map(m =>
    `<div class="chat-msg"><span class="chat-name">${esc(m.name)}:</span> ${esc(m.text)}</div>`
  ).join("");
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

// ─── Card helpers ───
function makeCard(card) {
  const d = document.createElement("div"); d.className = "playing-card";
  if (card === "🂠") { d.classList.add("card-back"); d.textContent = "🂠"; return d; }
  d.textContent = card;
  if (card.includes("♥") || card.includes("♦")) d.classList.add("red");
  return d;
}
function makeCardHtml(card) {
  if (card === "🂠") return '<div class="playing-card card-back">🂠</div>';
  return `<div class="playing-card${card.includes("♥")||card.includes("♦")?" red":""}">${esc(card)}</div>`;
}
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

// Player positions around the table
const SEAT_POSITIONS = [
  { top: "78%", left: "50%" },   // 1: bottom center
  { top: "65%", left: "10%" },   // 2: lower left
  { top: "30%", left: "5%" },    // 3: mid left
  { top: "5%",  left: "25%" },   // 4: upper left
  { top: "5%",  left: "75%" },   // 5: upper right
  { top: "30%", left: "95%" },   // 6: mid right
  { top: "65%", left: "90%" },   // 7: lower right
  { top: "5%",  left: "50%" },   // 8: top center
];

// ─── Event handlers ───
els.createBtn.onclick = createRoom;
els.joinBtn.onclick = joinRoom;
els.reconnectBtn.onclick = reconnectLast;
els.leaveBtn.onclick = leaveGame;
els.startBtn.onclick = () => action("start_hand");
els.foldBtn.onclick = () => action("fold");
els.checkCallBtn.onclick = () => action("check_call");
els.betHalfPotBtn.onclick = () => { if(!lastState)return; action("bet_raise",{amount:Math.max(lastState.current_bet+lastState.min_raise, lastState.current_bet+Math.floor(lastState.pot/2))}); };
els.betPotBtn.onclick = () => { if(!lastState)return; action("bet_raise",{amount:Math.max(lastState.current_bet+lastState.min_raise, lastState.current_bet+lastState.pot)}); };
els.betAllInBtn.onclick = () => { if(!lastState)return; action("bet_raise",{amount:lastState.viewer.committed+lastState.viewer.stack}); };
els.customBetBtn.onclick = () => { const v=parseInt(els.customBetInput.value,10); if(v>0){action("bet_raise",{amount:v});els.customBetInput.value="";} };
els.customBetInput.onkeydown = ev => { if(ev.key==="Enter") els.customBetBtn.click(); };
els.resetBtn.onclick = () => action("reset_stacks");
els.pauseBtn.onclick = () => action("toggle_pause");
els.addBotBtn.onclick = () => { console.log("[BTN] add_bot clicked, roomId=", roomId, "token=", token.slice(0,8), "ws=", ws && ws.readyState); action("add_bot"); };
els.removeBotBtn.onclick = () => { console.log("[BTN] remove_bot clicked"); action("remove_bot"); };
els.sitOutBtn.onclick = () => action("sit_out");
els.spectateBtn.onclick = () => action("spectate");
els.copyRoomBtn.onclick = async () => { try{await navigator.clipboard.writeText(roomId);}catch{} };
if (els.autoDealToggle) els.autoDealToggle.onclick = () => AutoDealSystem.toggle();
if (els.bbToggleBtn) {
  // Set initial visual state based on current mode
  if (BBDisplayToggle.getMode() === "bb") els.bbToggleBtn.classList.add("active");
  els.bbToggleBtn.onclick = () => {
    BBDisplayToggle.toggle();
    els.bbToggleBtn.classList.toggle("active");
    // Re-render current state to reflect the new display mode
    if (lastState) renderState(lastState);
  };
}

// FIX #7: Track dismiss so re-broadcasts don't re-show
els.winnerOverlay.onclick = () => {
  els.winnerOverlay.classList.add("hidden");
  winnerDismissedForPhase = "showdown";
};

els.chatToggle.onclick = () => els.chatPanel.classList.toggle("hidden");
els.hintsToggle.onclick = () => {
  hintsEnabled = !hintsEnabled;
  localStorage.setItem("poker_hints", hintsEnabled ? "true" : "false");
  els.hintsToggle.textContent = hintsEnabled ? "💡" : "🚫";
  if (lastState) renderState(lastState);
};
// Apply initial hints button state
if (!hintsEnabled) els.hintsToggle.textContent = "🚫";
els.chatClose.onclick = () => els.chatPanel.classList.add("hidden");
els.chatBtn.onclick = () => { const t=els.chatInput.value.trim(); if(t){send("chat",{text:t});els.chatInput.value="";} };
els.chatInput.onkeydown = ev => { if(ev.key==="Enter") els.chatBtn.click(); };

// ─── Init ───
loadSavedPlayerName();

if (roomId && token) {
  reconnectLast();
} else {
  // Clear any stale data
  roomId = ""; token = "";
  connect();
  setTimeout(fetchRooms, 500);
}
