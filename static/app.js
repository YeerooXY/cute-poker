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
"pauseBtn","sitOutBtn","spectateBtn","addBotBtn","removeBotBtn","botDifficultySelect",
"hintsToggle","bbToggleBtn","potChips","autoDealToggle","autoDealCountdown","outsBox",
"actionLogHandNum","actionLogBody","actionLogPanel","actionLogToggle","postHandPanel",
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

// ─── Helpers ───
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function parseCard(card) {
  const text = String(card || "");
  if (text === "🂠") return { rank: "🂠", suit: "" };
  const suit = text.slice(-1);
  const rank = text.slice(0, -1);
  return { rank, suit };
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
    const chips = Array.from({ length: visible }, (_, idx) => {
      const label = idx === visible - 1 ? `<span class="chip-label">${denom}</span>` : "";
      return `<span class="chip-item chip-denom-${denom}" style="--chip-index:${idx}; --chip-count:${visible}">${label}</span>`;
    }).join("");
    const countLabel = count > 4 ? `<span class="chip-count">×${count}</span>` : "";
    return `<span class="denom-stack">${chips}${countLabel}</span>`;
  }).join("") + `</div>`;
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
const SEAT_POSITIONS = [
  { top: "78%", left: "50%" },
  { top: "65%", left: "10%" },
  { top: "30%", left: "5%" },
  { top: "5%",  left: "25%" },
  { top: "5%",  left: "75%" },
  { top: "30%", left: "95%" },
  { top: "65%", left: "90%" },
  { top: "5%",  left: "50%" },
];

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
function renderState(state) {
  const previousState = lastState;
  lastState = state;
  const showdownDisplay = state.phase === "showdown" || Boolean(state.showdown_mode);

  // ─── HUD ───
  els.roomId.textContent = state.room_id;
  els.phaseBadge.textContent = state.paused ? "PAUSED" : showdownDisplay ? "SHOWDOWN" : state.phase.toUpperCase();
  const animatePot = shouldAnimatePotCountUp(previousState, state);
  setPotValue(state.pot, animatePot);

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
      ? `⚡ YOUR TURN · Call ${state.viewer.to_call}` : "⚡ YOUR TURN";
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

  // ─── Deal button visible in showdown/lobby ───
  const canDeal = ["lobby", "showdown"].includes(state.phase) && !state.paused;
  els.startBtn.style.display = canDeal ? "" : "none";

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

  // ─── Your hand ───
  // Hide the hero hand bar during showdown so the post-hand panel can own the result view.
  renderYourHand(showdownDisplay ? null : viewerData);

  // ─── Player seats ───
  renderPlayers(state.players, previousState, state);

  // ─── Chat ───
  renderChat(state.messages);

  // ─── Action Log ───
  renderActionLog(state);
  renderPostHandPanel(state);

  // ─── Action button labels ───
  if (isMyTurn) {
    els.checkCallBtn.textContent = state.viewer.to_call > 0 ? `Call ${state.viewer.to_call}` : "Check";
    els.customBetInput.placeholder = `Min ${state.current_bet + state.min_raise}`;
  } else {
    els.checkCallBtn.textContent = "Check / Call";
    els.customBetInput.placeholder = "Raise to...";
  }

  // Hide outs box (removed feature)
  if (els.outsBox) els.outsBox.classList.add("hidden");
  // Hide auto-deal countdown
  if (els.autoDealCountdown) els.autoDealCountdown.classList.add("hidden");
  if (els.autoDealToggle) els.autoDealToggle.style.display = "none";
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
  els.yourCards.innerHTML = viewer.cards.map(makeCardHtml).join("");
  els.handStrength.textContent = viewer.hand_name || "";
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

  players.forEach((p, idx) => {
    const pos = SEAT_POSITIONS[idx % SEAT_POSITIONS.length];
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

    // Cards (other players, not you)
    let cards = "";
    if (p.cards && p.cards.length > 0 && !p.is_you) {
      const previousPlayer = previousById.get(p.player_id || p.name);
      const newFlags = getNewCardFlags(p.cards, previousPlayer ? previousPlayer.cards : []);
      cards = `<div class="seat-cards">${p.cards.map((card, cardIdx) =>
        makeCardHtml(card, newFlags[cardIdx] ? "new-card" : "")
      ).join("")}</div>`;
    }
    const committedChips = p.committed > 0
      ? `<div class="seat-chips">${renderChipStackHtml(p.committed, "seat-committed-chips")}</div>`
      : "";

    seat.innerHTML = `
      <div class="seat-header">
        <span class="seat-avatar">${p.avatar || "🎭"}</span>
        <span class="seat-name">${esc(p.name)}</span>
        <span class="seat-stack">💰${p.stack}</span>
      </div>
      <div class="seat-badges">${badges.join("")}</div>
      ${cards}
      ${committedChips}
      ${p.committed > 0 ? `<div class="seat-meta">Bet: ${p.committed}</div>` : ""}
      ${p.hand_name ? `<div class="seat-meta seat-hand-rank">${esc(p.hand_detail || p.hand_name)}</div>` : ""}
    `;
    els.playerPositions.appendChild(seat);
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
els.createBtn.onclick = createRoom;
els.joinBtn.onclick = joinRoom;
els.reconnectBtn.onclick = reconnectLast;
els.leaveBtn.onclick = leaveGame;
els.startBtn.onclick = () => action("start_hand");
if (els.postHandDealBtn) els.postHandDealBtn.onclick = () => action("start_hand");
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
els.removeBotBtn.onclick = () => action("remove_bot");
els.sitOutBtn.onclick = () => action("sit_out");
els.spectateBtn.onclick = () => action("spectate");
els.copyRoomBtn.onclick = async () => { try { await navigator.clipboard.writeText(roomId); } catch {} };

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

function formatPostHandTitle(winners) {
  if (!winners || winners.length === 0) return "Hand complete";
  if (winners.length === 1) return formatWinnerEntry(winners[0]);
  const names = winners.map(w => w.name).join(", ");
  const total = winners.reduce((sum, w) => sum + (Number(w.amount) || 0), 0);
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

  const remainingHole = [...hole];
  const remainingBoard = [...board];
  const usedHole = [];
  const usedBoard = [];
  const missing = [];

  for (const card of best) {
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

  const leftOut = [...remainingHole, ...remainingBoard];
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


function foldedRevealMode(player) {
  return String(player.folded_reveal_mode || "hidden").toLowerCase();
}

function foldedCardsForModal(player) {
  const mode = foldedRevealMode(player);
  const cards = Array.isArray(player.cards) ? player.cards : [];
  const left = cards[0] && cards[0] !== "BACK" ? cards[0] : "🂠";
  const right = cards[1] && cards[1] !== "BACK" ? cards[1] : "🂠";

  if (mode === "left") return [left, "🂠"];
  if (mode === "right") return ["🂠", right];
  if (mode === "both") return [left, right];
  return ["🂠", "🂠"];
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
  const buttons = [];

  if (mode !== "left") {
    buttons.push('<button type="button" class="btn btn-tiny btn-dim folded-reveal-btn" data-folded-reveal="left">Show left</button>');
  }
  if (mode !== "right") {
    buttons.push('<button type="button" class="btn btn-tiny btn-dim folded-reveal-btn" data-folded-reveal="right">Show right</button>');
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


function renderPostHandPanel(state) {
  if (!els.postHandPanel) return;
  const winners = Array.isArray(state.winners) ? state.winners : [];
  const visible = state.phase === "showdown" && winners.length > 0;

  els.postHandPanel.classList.toggle("hidden", !visible);
  els.postHandPanel.classList.toggle("post-hand-modal", visible);

  if (!visible) {
    if (els.postHandTitle) els.postHandTitle.textContent = "";
    if (els.postHandPot) els.postHandPot.textContent = "";
    if (els.postHandBody) els.postHandBody.innerHTML = "";
    return;
  }

  if (els.postHandKicker) {
    els.postHandKicker.textContent = winners.length > 1 ? "Split pot" : "Hand complete";
  }
  if (els.postHandTitle) els.postHandTitle.textContent = formatPostHandTitle(winners);
  if (els.postHandPot) els.postHandPot.textContent = `Final pot ${state.pot || 0}`;
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
    els.postHandBody.innerHTML = winners.map(w => `
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
    const cards = p.best_cards.map(card => makeCardHtml(card, "showdown-card-flip")).join("");
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

    const uncontestedRevealMode = String(p.uncontested_reveal_mode || "hidden").toLowerCase();
    const isUncontestedRevealed = isUncontestedWinner && uncontestedRevealMode === "both";
    const canRevealUncontested = Boolean(isUncontestedWinner && p.can_reveal_uncontested_hand && !isUncontestedRevealed);

    const modalCards = isUncontestedWinner
      ? (isUncontestedRevealed && Array.isArray(p.cards) && p.cards.length > 0 ? p.cards : ["🂠", "🂠"])
      : foldedCardsForModal(p);
    const detail = isUncontestedWinner
      ? (isUncontestedRevealed ? "Winner revealed their hand after everyone folded" : "Hand not shown · Everyone else folded")
      : foldedRevealDetail(p);
    const result = isUncontestedWinner ? (isUncontestedRevealed ? "revealed winner" : "wins uncontested") : mode === "both" ? "revealed" : "mucked";
    const uncontestedActions = canRevealUncontested
      ? '<div class="folded-reveal-actions"><button type="button" class="btn btn-tiny btn-deal" data-uncontested-reveal="both">Show hand</button></div>'
      : "";
    const revealActions = isUncontestedWinner ? uncontestedActions : renderFoldedRevealActions(p);
    const wouldHaveBreakdown = isUncontestedWinner ? "" : renderFoldedWouldHaveBreakdown(p, state);
    const baseRowClass = isUncontestedWinner ? " winner post-hand-winner-glow uncontested" : " mucked";
    const rowExtraClass = mode === "both" ? " would-have" : (mode === "left" || mode === "right") ? " partial-revealed" : "";

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

  els.postHandBody.innerHTML = `${shownRows}${muckedRows}`;
  bindFoldedRevealButtons();
}

function formatPlayerShowdownEntry(player, winnerNames) {
  if (!player.hand_name || !player.best_cards || player.best_cards.length === 0) return null;
  const cardsStr = player.best_cards.map(c => {
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
    els.actionLogHandNum.textContent = state.hands_played || 0;
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
    const defaultExpanded = !window.matchMedia || !window.matchMedia("(max-width: 768px)").matches;
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

if (roomId && token) {
  reconnectLast();
} else {
  roomId = ""; token = "";
  connect();
  setTimeout(fetchRooms, 500);
}
